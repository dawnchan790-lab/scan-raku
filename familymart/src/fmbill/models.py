"""業務データのモデル定義。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class DeliveryFeeRule:
    """配送料のルール。店舗ごとに有無・金額が変わる。"""

    enabled: bool = False
    amount: int = 550          # 税込金額
    tax_rate: int = 10
    charge_unit: str = "per_month"   # per_month | per_delivery
    label: str = "配送料"

    @property
    def amount_excluding_tax(self) -> int:
        """税込金額から税抜金額を求める（円未満切り捨て）。"""
        return self.amount * 100 // (100 + self.tax_rate)


@dataclass
class DocumentRule:
    """帳票（納品書・請求書）の出力ルール。"""

    template: str
    layout: str
    copies: int = 1


@dataclass
class Store:
    code: str
    name: str
    short_name: str = ""
    honorific: str = "御中"
    closing_day: int = 20
    aliases: list[str] = field(default_factory=list)
    item_aliases: dict[str, str] = field(default_factory=dict)
    delivery_fee: DeliveryFeeRule = field(default_factory=DeliveryFeeRule)
    delivery_note: Optional[DocumentRule] = None
    invoice: Optional[DocumentRule] = None

    @property
    def display_name(self) -> str:
        return self.short_name or self.name

    def match_names(self) -> list[str]:
        """店舗特定に使う名前の候補（長い順）。"""
        names = [self.name, self.short_name, *self.aliases, self.code]
        return sorted({n for n in names if n}, key=len, reverse=True)


@dataclass
class Product:
    code: str
    name: str
    unit: str = "個"
    price: int = 0
    tax_rate: int = 8
    aliases: list[str] = field(default_factory=list)
    store_prices: dict[str, int] = field(default_factory=dict)

    def price_for(self, store_code: str) -> int:
        """店舗別単価があればそれを、なければ標準単価を返す。"""
        return self.store_prices.get(store_code, self.price)

    def match_names(self) -> list[str]:
        names = [self.name, *self.aliases]
        return sorted({n for n in names if n}, key=len, reverse=True)


@dataclass
class OrderLine:
    """注文1行 = 品目1つ分。"""

    raw_text: str            # 元のFAX/LINE文字列（監査用に必ず残す）
    item_name: str           # 正規化後の品目名
    qty: float
    unit: str = ""
    product_code: str = ""   # 商品マスタと一致しなかった場合は空
    note: str = ""

    @property
    def matched(self) -> bool:
        return bool(self.product_code)


@dataclass
class Order:
    """1店舗・1納品日ぶんの注文。仕分け帳の1レコードに相当する。"""

    store_code: str
    delivery_date: date
    lines: list[OrderLine] = field(default_factory=list)
    source: str = ""          # line | fax | manual
    source_ref: str = ""      # 画像ファイル名やメッセージIDなど
    received_at: Optional[date] = None
    note: str = ""
    order_id: Optional[int] = None

    @property
    def unmatched_lines(self) -> list[OrderLine]:
        return [ln for ln in self.lines if not ln.matched]


@dataclass
class BilledLine:
    """納品書・請求書に印字する1行。"""

    item_name: str
    qty: float
    unit: str
    unit_price: int
    tax_rate: int
    delivery_date: Optional[date] = None

    @property
    def amount(self) -> int:
        """金額（税抜、円未満切り捨て）。"""
        return int(self.qty * self.unit_price)


@dataclass
class TaxSubtotal:
    """税率ごとの小計。区分記載請求書に必要。"""

    tax_rate: int
    taxable_amount: int   # 税抜合計
    tax_amount: int       # 消費税額

    @property
    def total(self) -> int:
        return self.taxable_amount + self.tax_amount


@dataclass
class DeliveryNote:
    """納品書1枚ぶん。"""

    store: Store
    delivery_date: date
    lines: list[BilledLine] = field(default_factory=list)
    number: str = ""

    @property
    def subtotal(self) -> int:
        return sum(ln.amount for ln in self.lines)


@dataclass
class Invoice:
    """請求書1枚ぶん（1店舗・1締め期間）。"""

    store: Store
    period_start: date
    period_end: date
    issue_date: date
    lines: list[BilledLine] = field(default_factory=list)
    tax_subtotals: list[TaxSubtotal] = field(default_factory=list)
    number: str = ""

    @property
    def subtotal(self) -> int:
        """税抜合計。"""
        return sum(st.taxable_amount for st in self.tax_subtotals)

    @property
    def tax_total(self) -> int:
        return sum(st.tax_amount for st in self.tax_subtotals)

    @property
    def total(self) -> int:
        """税込請求金額。"""
        return self.subtotal + self.tax_total
