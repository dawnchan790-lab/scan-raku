"""店舗マスタ・商品マスタの読み込み。"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Optional

import yaml

from .models import DeliveryFeeRule, DocumentRule, Product, Store
from .textutil import normalize


def _deep_merge(base: dict, override: dict) -> dict:
    """defaults の上に個別設定を重ねる（ネストした dict も再帰的に）。"""
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


class StoreMaster:
    def __init__(self, stores: list[Store]):
        self._stores = stores
        self._by_code = {s.code: s for s in stores}
        # 表記ゆれ → 店舗コード の逆引き表。長い名前を優先して照合する。
        self._by_name: list[tuple[str, str]] = []
        for store in stores:
            for name in store.match_names():
                self._by_name.append((normalize(name), store.code))
        self._by_name.sort(key=lambda pair: len(pair[0]), reverse=True)

    @classmethod
    def load(cls, path: str | Path) -> "StoreMaster":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        defaults = data.get("defaults") or {}
        stores = []
        for entry in data.get("stores") or []:
            merged = _deep_merge(defaults, entry)
            stores.append(
                Store(
                    code=str(merged["code"]),
                    name=merged["name"],
                    short_name=merged.get("short_name", ""),
                    group=merged.get("group", ""),
                    honorific=merged.get("honorific", "御中"),
                    note_name=merged.get("note_name", ""),
                    closing_day=int(merged.get("closing_day", 20)),
                    margin_rate=float(merged.get("margin_rate", 0.25)),
                    order_unit=merged.get("order_unit", "qty"),
                    aliases=[str(a) for a in merged.get("aliases") or []],
                    item_aliases={
                        str(k): str(v) for k, v in (merged.get("item_aliases") or {}).items()
                    },
                    delivery_fee=DeliveryFeeRule(**(merged.get("delivery_fee") or {})),
                    delivery_note=_document_rule(merged.get("delivery_note")),
                    invoice=_document_rule(merged.get("invoice")),
                )
            )
        return cls(stores)

    def __iter__(self):
        return iter(self._stores)

    def __len__(self) -> int:
        return len(self._stores)

    def get(self, code: str) -> Store:
        if code not in self._by_code:
            raise KeyError(f"店舗コードが見つかりません: {code}")
        return self._by_code[code]

    def find_in_text(self, text: str) -> Optional[Store]:
        """FAX/LINEの本文から店舗を特定する。見つからなければ None。"""
        found = self.match_in_text(text)
        return found[0] if found else None

    def match_in_text(self, text: str) -> Optional[tuple[Store, str]]:
        """店舗と、実際に一致した表記（正規化済み）を返す。

        一致した表記の長さは「その行が店舗名の見出し行かどうか」の判定に使う。
        """
        hay = normalize(text)
        for name, code in self._by_name:
            if name and name in hay:
                return self._by_code[code], name
        return None


class ProductMaster:
    def __init__(self, products: list[Product]):
        self._products = products
        self._by_code = {p.code: p for p in products}
        self._by_name: list[tuple[str, str]] = []
        for product in products:
            for name in product.match_names():
                self._by_name.append((normalize(name), product.code))
        self._by_name.sort(key=lambda pair: len(pair[0]), reverse=True)

    @classmethod
    def load(cls, path: str | Path, aliases_path: str | Path | None = None) -> "ProductMaster":
        """商品マスタを読み込む。

        products.yaml は発注書から自動生成するため再生成で上書きされる。
        手で育てる表記ゆれ辞書は aliases.yaml に分けてあり、ここで合流させる。
        """
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        defaults = data.get("defaults") or {}
        extra_aliases = _load_aliases(aliases_path)
        products = []
        for entry in data.get("products") or []:
            merged = _deep_merge(defaults, entry)
            products.append(
                Product(
                    code=str(merged["code"]),
                    name=merged["name"],
                    unit=merged.get("unit", "個"),
                    retail_price=int(merged.get("retail_price", 0)),
                    margin_rate=(
                        float(merged["margin_rate"]) if merged.get("margin_rate") is not None else None
                    ),
                    min_lot=int(merged.get("min_lot", 1)),
                    reduced_tax=bool(merged.get("reduced_tax", True)),
                    origin=merged.get("origin", ""),
                    spec=merged.get("spec", ""),
                    storage=merged.get("storage", ""),
                    shelf_life_days=merged.get("shelf_life_days"),
                    aliases=[
                        str(a)
                        for a in (merged.get("aliases") or [])
                        + extra_aliases.get(str(merged["code"]), [])
                    ],
                    groups=[str(g) for g in merged.get("groups") or []],
                    store_overrides={
                        str(k): dict(v) for k, v in (merged.get("store_overrides") or {}).items()
                    },
                )
            )
        return cls(products)

    def __iter__(self):
        return iter(self._products)

    def __len__(self) -> int:
        return len(self._products)

    def get(self, code: str) -> Product:
        if code not in self._by_code:
            raise KeyError(f"商品コードが見つかりません: {code}")
        return self._by_code[code]

    def find(self, name: str, store=None) -> Optional[Product]:
        """品目名（表記ゆれ含む）から商品を特定する。見つからなければ None。

        store を渡すと、その店舗のグループが扱う商品だけに絞り込む。
        同じ「バナナ」でもグループごとに売価が違うため、絞り込みは必須に近い。
        """
        hay = normalize(name)
        if not hay:
            return None
        for candidate, code in self._by_name:
            if not candidate or candidate not in hay:
                continue
            product = self._by_code[code]
            if product.applies_to(store):
                return product
        return None


def _load_aliases(path: str | Path | None) -> dict[str, list[str]]:
    """aliases.yaml から {商品コード: [表記ゆれ, ...]} を読む。無ければ空。"""
    if path is None or not Path(path).exists():
        return {}
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return {
        str(code): [str(a) for a in names or []]
        for code, names in (data.get("item_aliases") or {}).items()
    }


def _document_rule(raw: Optional[dict]) -> Optional[DocumentRule]:
    if not raw:
        return None
    return DocumentRule(
        template=raw.get("template", ""),
        layout=raw.get("layout", ""),
        copies=int(raw.get("copies", 1)),
    )
