"""業務データのモデル定義。

金額はすべて**税込**で扱う。現行のExcelがそうなっているため。
単価マスタは持たず、想定税込売価と粗利益率（掛け率）から原価を毎回計算する。

    原価（税込） = ROUNDUP( 想定税込売価 × ( 1 − 粗利益率 ), 0 )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_CEILING, Decimal
from typing import Optional

# 軽減税率（食品）と標準税率（送料など）
REDUCED_TAX_RATE = 8
STANDARD_TAX_RATE = 10


def roundup_yen(value: Decimal) -> int:
    """Excel の ROUNDUP(x, 0) と同じ（円未満を切り上げ）。"""
    return int(value.quantize(Decimal(1), rounding=ROUND_CEILING))


@dataclass
class DeliveryFeeRule:
    """送料のルール。店舗ごとに有無が変わる。"""

    enabled: bool = True
    amount: int = 550          # 税込
    label: str = "送料"

    @property
    def tax_rate(self) -> int:
        return STANDARD_TAX_RATE


@dataclass
class DocumentRule:
    """帳票（納品書・請求書）の出力ルール。"""

    template: str
    layout: str
    copies: int = 1


@dataclass
class Store:
    code: str
    name: str                      # 請求書の宛名に使う正式名
    short_name: str = ""
    group: str = ""                # 宗久グループ など。請求のまとめ方の目印
    honorific: str = "御中"        # 請求書の宛名に添える敬称
    note_name: str = ""            # 納品書の宛名。省略時は「○○店　様」
    closing_day: int = 20
    margin_rate: float = 0.25      # 粗利益率（掛け率）。原価の計算に使う
    order_unit: str = "qty"        # qty = 数量を直接入力 / lot = ロット数を入力
    aliases: list[str] = field(default_factory=list)
    item_aliases: dict[str, str] = field(default_factory=dict)
    delivery_fee: DeliveryFeeRule = field(default_factory=DeliveryFeeRule)
    delivery_note: Optional[DocumentRule] = None
    invoice: Optional[DocumentRule] = None

    @property
    def display_name(self) -> str:
        return self.short_name or self.name

    @property
    def note_addressee(self) -> str:
        """納品書の宛名（C8）。現行は「仙台高野原店　様」の形。"""
        return self.note_name or f"{self.display_name}店　様"

    def match_names(self) -> list[str]:
        """店舗特定に使う名前の候補（長い順）。"""
        names = [self.name, self.short_name, self.note_name, *self.aliases, self.code]
        return sorted({n for n in names if n}, key=len, reverse=True)


@dataclass
class Product:
    code: str
    name: str
    unit: str = "個"
    retail_price: int = 0          # 想定税込売価
    margin_rate: Optional[float] = None   # 商品固有の粗利益率。無ければ店舗の値を使う
    min_lot: int = 1               # 最小発注ロット
    reduced_tax: bool = True       # 食品は軽減税率8%
    origin: str = ""               # 産地
    spec: str = ""                 # 規格
    storage: str = ""              # 保存方法
    shelf_life_days: Optional[int] = None
    aliases: list[str] = field(default_factory=list)
    # この商品を扱うグループ。空なら全店共通。
    # 品目リストと売価はグループごとに違うため、照合をグループで絞り込む。
    groups: list[str] = field(default_factory=list)
    # 店舗ごとに売価・掛け率が違う場合の上書き: {店舗コード: {"retail_price": .., "margin_rate": ..}}
    store_overrides: dict[str, dict] = field(default_factory=dict)

    def applies_to(self, store: Optional["Store"]) -> bool:
        if not self.groups or store is None:
            return True
        return store.group in self.groups

    @property
    def tax_rate(self) -> int:
        return REDUCED_TAX_RATE if self.reduced_tax else STANDARD_TAX_RATE

    def retail_price_for(self, store: Store) -> int:
        override = self.store_overrides.get(store.code, {})
        return int(override.get("retail_price", self.retail_price))

    def margin_rate_for(self, store: Store) -> float:
        override = self.store_overrides.get(store.code, {})
        if "margin_rate" in override:
            return float(override["margin_rate"])
        if self.margin_rate is not None:
            return self.margin_rate
        return store.margin_rate

    def cost_price_for(self, store: Store) -> int:
        """原価（税込）＝ ROUNDUP( 売価 × ( 1 − 粗利益率 ), 0 )"""
        retail = Decimal(self.retail_price_for(store))
        margin = Decimal(str(self.margin_rate_for(store)))
        return roundup_yen(retail * (Decimal(1) - margin))

    def match_names(self) -> list[str]:
        names = [self.name, *self.aliases]
        return sorted({n for n in names if n}, key=len, reverse=True)


@dataclass
class OrderLine:
    """注文1行 = 品目1つ分。"""

    raw_text: str            # 元のFAX/LINE文字列（監査用に必ず残す）
    item_name: str           # 正規化後の品目名
    qty: float               # 実数量（ロット制の店舗はロット数×最小発注ロット）
    input_qty: float = 0     # 注文に書かれていた数（ロット制ならロット数）
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
class DeliveryLine:
    """納品書に印字する1行。金額はすべて税込。"""

    item_name: str
    qty: float
    unit: str
    retail_price: int        # 単価（売価）
    cost_price: int          # 単価（原価）
    reduced_tax: bool = True

    @property
    def retail_amount(self) -> int:
        """金額（売価）"""
        return int(self.qty * self.retail_price)

    @property
    def cost_amount(self) -> int:
        """金額（原価）"""
        return int(self.qty * self.cost_price)


@dataclass
class DeliveryNote:
    """納品書1枚ぶん（1店舗・1納品日）。"""

    store: Store
    delivery_date: date
    lines: list[DeliveryLine] = field(default_factory=list)
    shipping_fee: int = 0    # 税込。送料をもらわない店舗は0
    number: str = ""

    @property
    def retail_total(self) -> int:
        """8%対象の金額（売価）合計"""
        return sum(ln.retail_amount for ln in self.lines)

    @property
    def cost_total(self) -> int:
        """8%対象の金額（原価）合計"""
        return sum(ln.cost_amount for ln in self.lines)

    @property
    def total(self) -> int:
        """税込合計金額（原価合計）。納品書のC11に出る金額。"""
        return self.cost_total + self.shipping_fee


@dataclass
class InvoiceRow:
    """請求書の明細1行。納品日ごとに「売上」1行にまとめる。"""

    sale_date: date
    item_name: str
    amount: int              # 税込
    reduced_tax: bool
    qty: int = 1
    unit: str = ""

    @property
    def tax_rate(self) -> int:
        return REDUCED_TAX_RATE if self.reduced_tax else STANDARD_TAX_RATE


@dataclass
class Invoice:
    """請求書1枚ぶん（1店舗・1締め期間）。"""

    store: Store
    period_start: date
    period_end: date
    issue_date: date
    rows: list[InvoiceRow] = field(default_factory=list)
    number: str = ""
    payment_due: Optional[date] = None

    @property
    def reduced_total(self) -> int:
        """8%対象の税込合計"""
        return sum(r.amount for r in self.rows if r.reduced_tax)

    @property
    def standard_total(self) -> int:
        """10%対象の税込合計"""
        return sum(r.amount for r in self.rows if not r.reduced_tax)

    @property
    def total(self) -> int:
        """ご請求金額（税込）"""
        return self.reduced_total + self.standard_total

    @property
    def reduced_tax_amount(self) -> Decimal:
        """8%対象に含まれる消費税額（税込 − 税込÷1.08）"""
        amount = Decimal(self.reduced_total)
        return amount - (amount / Decimal("1.08"))

    @property
    def standard_tax_amount(self) -> Decimal:
        """10%対象に含まれる消費税額（税込 − 税込÷1.1）"""
        amount = Decimal(self.standard_total)
        return amount - (amount / Decimal("1.1"))

    @property
    def tax_total(self) -> Decimal:
        return self.reduced_tax_amount + self.standard_tax_amount
