"""FAX（OCRテキスト）・LINEテキストを注文データに変換する。

どちらの経路も「店舗名・日付・明細行が混ざった行の並び」という点は同じなので、
1つのパーサで処理し、source だけを differentiating する。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from .masters import ProductMaster, StoreMaster
from .models import Order, OrderLine
from .textutil import normalize, parse_date, parse_item_line

# 店舗名の見出し行に付きがちな飾り。残りかすの判定から取り除く。
_HEADING_NOISE = re.compile(r"納品|注文|発注|御中|[店様殿行分:：\-—ー()（）\[\]【】。、,.\s]")
# 見出し行に同居している日付部分
_DATE_FRAGMENT = re.compile(
    r"(?:令和|平成|R|H)?\s*\d{1,4}\s*[/年月.\-]\s*\d{1,2}\s*(?:[/月.\-]\s*\d{1,2})?\s*日?"
    r"(?:\s*[(（][月火水木金土日][)）])?"
)


@dataclass
class ParseResult:
    orders: list[Order] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def line_count(self) -> int:
        return sum(len(o.lines) for o in self.orders)

    @property
    def unmatched_count(self) -> int:
        return sum(len(o.unmatched_lines) for o in self.orders)


class OrderParser:
    def __init__(self, stores: StoreMaster, products: ProductMaster):
        self.stores = stores
        self.products = products

    def parse(
        self,
        text: str,
        source: str = "line",
        source_ref: str = "",
        default_store_code: Optional[str] = None,
        default_date: Optional[date] = None,
        received_at: Optional[date] = None,
    ) -> ParseResult:
        """テキストを解析して注文の一覧を返す。

        1通のメッセージに複数店舗・複数納品日が混在していても、
        店舗名の行・日付の行を境に自動で仕分ける。
        """
        result = ParseResult()
        today = received_at or date.today()

        current_store = self.stores.get(default_store_code) if default_store_code else None
        current_date = default_date
        buckets: dict[tuple[str, date], Order] = {}

        for raw_line in text.splitlines():
            line = normalize(raw_line)
            if not line:
                continue

            # 1) 店舗名の行か？
            matched = self.stores.match_in_text(line)
            if matched is not None and _is_store_heading(line, matched[1]):
                current_store = matched[0]
                # 店舗名と同じ行に日付が書かれていることもある
                found = parse_date(line, default_year=today.year)
                if found:
                    current_date = found
                continue

            # 2) 日付だけの行か？
            if parse_item_line(line) is None:
                found = parse_date(line, default_year=today.year)
                if found:
                    current_date = found
                    continue

            # 3) 明細行か？
            parsed = parse_item_line(line)
            if parsed is None:
                continue
            item_text, qty, unit = parsed

            if current_store is None:
                result.warnings.append(f"店舗が特定できないため取り込めません: 「{line}」")
                continue
            if current_date is None:
                result.warnings.append(f"納品日が特定できないため取り込めません: 「{line}」")
                continue

            order_line = self._to_order_line(current_store.code, raw_line, item_text, qty, unit)
            if not order_line.matched:
                result.warnings.append(
                    f"商品マスタに無い品目です（要確認）: 「{item_text}」 / {current_store.display_name}"
                )

            key = (current_store.code, current_date)
            if key not in buckets:
                buckets[key] = Order(
                    store_code=current_store.code,
                    delivery_date=current_date,
                    source=source,
                    source_ref=source_ref,
                    received_at=today,
                )
            buckets[key].lines.append(order_line)

        result.orders = [buckets[key] for key in sorted(buckets)]
        return result

    def _to_order_line(
        self, store_code: str, raw: str, item_text: str, qty: float, unit: str
    ) -> OrderLine:
        # 店舗独自の呼称をまず自社の正式名称に読み替える
        store = self.stores.get(store_code)
        alias_target = store.item_aliases.get(normalize(item_text)) or store.item_aliases.get(
            item_text
        )
        lookup = alias_target or item_text

        product = self.products.find(lookup)
        if product is None:
            return OrderLine(raw_text=raw.strip(), item_name=lookup, qty=qty, unit=unit)

        return OrderLine(
            raw_text=raw.strip(),
            item_name=product.name,
            qty=qty,
            unit=unit or product.unit,
            product_code=product.code,
        )


def _is_store_heading(line: str, matched_name: str) -> bool:
    """その行が「店舗名の見出し」かどうかを判定する。

    店舗名・日付・飾りを取り除いて何も残らなければ見出しとみなす。
    「国見ヶ丘 きゅうり 3」のように品目が続く行は見出しではなく明細として扱う。
    店舗名が数字で終わる場合（サンプル2 など）でも誤って明細と判定しないための処理。
    """
    residual = normalize(line).replace(matched_name, "", 1)
    residual = _DATE_FRAGMENT.sub("", residual)
    residual = _HEADING_NOISE.sub("", residual)
    if not residual:
        return True
    # 飾りが残っていても、明細として読めない行なら見出し扱いにする
    return parse_item_line(line) is None
