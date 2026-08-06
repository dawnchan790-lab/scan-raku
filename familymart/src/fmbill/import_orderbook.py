"""現行の発注書ブックから商品マスタを取り込む。

品目・売価は季節や仕入れで毎週変わるため、手入力ではなく
いま使っている発注書ブックからそのまま読み込めるようにする。

現行ブックには2つの書式があり、どちらも自動判別する。

  高野原店様オーナー   : 「印刷・FAX　発注書」シート。産地・規格・保存・最小発注ロットあり
  宗久グループ: 「入力　発注書」シート。品名・賞味期限・売価のみ
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from openpyxl import load_workbook

FAX_SHEET = "印刷・FAX　発注書"
ENTRY_SHEET = "入力　発注書"

# 商品ではない行（送料など）
_NOT_A_PRODUCT = {"送料", "配送料"}

# 食品でない品目は軽減税率の対象外（標準税率10%）。
# 現行の発注書は税率を持っていないので品名から判定し、取り込み時に一覧を出す。
_NON_FOOD = ("仏花", "花束", "切花", "鉢")


@dataclass
class ImportedProduct:
    code: str
    name: str
    retail_price: int
    margin_rate: float
    min_lot: int = 1
    origin: str = ""
    spec: str = ""
    storage: str = ""
    shelf_life_days: Optional[int] = None
    reduced_tax: bool = True
    aliases: list[str] = field(default_factory=list)


def is_food(name: str) -> bool:
    """軽減税率8%の対象（食品）かどうかを品名から判定する。"""
    return not any(word in name for word in _NON_FOOD)


def import_products(path: str | Path) -> list[ImportedProduct]:
    """発注書ブックから商品を読み取る。"""
    workbook = load_workbook(path, data_only=False)
    if FAX_SHEET in workbook.sheetnames:
        return _import_maruka(workbook[FAX_SHEET])
    if ENTRY_SHEET in workbook.sheetnames:
        return _import_munehisa(workbook[ENTRY_SHEET])
    raise ValueError(
        f"発注書のシートが見つかりません: {path}\n"
        f"「{FAX_SHEET}」または「{ENTRY_SHEET}」が必要です。"
    )


def _import_maruka(sheet) -> list[ImportedProduct]:
    """高野原店様オーナー（産地・規格・保存・最小発注ロットあり）。"""
    products = []
    for row in range(13, 64):
        name = _text(sheet[f"B{row}"].value)
        if not name or name in _NOT_A_PRODUCT:
            continue
        price = _number(sheet[f"H{row}"].value)
        if not price:
            continue
        # 規格はD列とE列に分かれている（例: D="太め" E="１本"）
        spec = " ".join(x for x in (_text(sheet[f"D{row}"].value), _text(sheet[f"E{row}"].value)) if x)
        products.append(
            ImportedProduct(
                code="",
                name=name,
                retail_price=int(price),
                margin_rate=float(_number(sheet[f"L{row}"].value) or 0),
                min_lot=int(_number(sheet[f"M{row}"].value) or 1),
                origin=_text(sheet[f"C{row}"].value),
                spec=spec,
                storage=_text(sheet[f"F{row}"].value),
                shelf_life_days=_int_or_none(sheet[f"G{row}"].value),
                reduced_tax=is_food(name),
            )
        )
    return _assign_codes(products)


def _import_munehisa(sheet) -> list[ImportedProduct]:
    """宗久グループ（品名・賞味期限・売価のみ）。"""
    products = []
    for row in range(13, 70):
        name = _text(sheet[f"B{row}"].value)
        if not name or name in _NOT_A_PRODUCT:
            continue
        price = _number(sheet[f"D{row}"].value)
        if not price:
            continue
        products.append(
            ImportedProduct(
                code="",
                name=name,
                retail_price=int(price),
                margin_rate=float(_number(sheet[f"H{row}"].value) or 0),
                shelf_life_days=_int_or_none(sheet[f"C{row}"].value),
                reduced_tax=is_food(name),
            )
        )
    return _assign_codes(products)


def _assign_codes(products: list[ImportedProduct]) -> list[ImportedProduct]:
    """品名＋規格から商品コードを決める。

    同じ品名でも規格違い（バナナの1本売りとパック）は別商品なので、
    重複したら連番を足して区別する。
    """
    used: dict[str, int] = {}
    for product in products:
        base = _slug(f"{product.name}{product.spec}")
        used[base] = used.get(base, 0) + 1
        product.code = base if used[base] == 1 else f"{base}-{used[base]}"
    return products


def _slug(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    return re.sub(r"[\s　/()（）]+", "", normalized) or "ITEM"


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str) and value.startswith("="):
        return ""    # 数式は読み取れないので空扱い
    return unicodedata.normalize("NFKC", str(value)).strip()


def _number(value) -> Optional[float]:
    return float(value) if isinstance(value, (int, float)) else None


def _int_or_none(value) -> Optional[int]:
    return int(value) if isinstance(value, (int, float)) else None
