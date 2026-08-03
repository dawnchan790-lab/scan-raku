"""締め処理。仕分け帳から納品書・請求書のデータを組み立てる。"""

from __future__ import annotations

import calendar
from collections import OrderedDict
from datetime import date, timedelta
from typing import Iterable, Optional

from .masters import ProductMaster, StoreMaster
from .models import (
    BilledLine,
    DeliveryNote,
    Invoice,
    Order,
    Store,
    TaxSubtotal,
)


class ClosingPeriod:
    """締め期間。20日締めなら「前月21日〜当月20日」。"""

    def __init__(self, start: date, end: date, closing_day: int):
        self.start = start
        self.end = end
        self.closing_day = closing_day

    def __repr__(self) -> str:
        return f"ClosingPeriod({self.start}〜{self.end})"

    @property
    def label(self) -> str:
        return f"{self.start:%Y/%m/%d}〜{self.end:%Y/%m/%d}"


def closing_period(year: int, month: int, closing_day: int = 20) -> ClosingPeriod:
    """締め年月から締め期間を求める。

    closing_day=20, 2026年8月 → 2026-07-21 〜 2026-08-20
    closing_day が月末を超える指定（31など）の場合は当月1日〜月末とする。
    """
    last_day = calendar.monthrange(year, month)[1]
    if closing_day >= last_day:
        return ClosingPeriod(date(year, month, 1), date(year, month, last_day), closing_day)

    end = date(year, month, closing_day)
    prev_end = date(year, month, 1) - timedelta(days=1)
    prev_last_day = calendar.monthrange(prev_end.year, prev_end.month)[1]
    # 前月に closing_day が存在しない場合（例: 2月30日）は前月末の翌日を開始日にする
    start_day = min(closing_day, prev_last_day)
    start = date(prev_end.year, prev_end.month, start_day) + timedelta(days=1)
    return ClosingPeriod(start, end, closing_day)


def period_containing(day: date, closing_day: int = 20) -> ClosingPeriod:
    """ある日付が属する締め期間を返す。"""
    if day.day <= closing_day:
        return closing_period(day.year, day.month, closing_day)
    nxt = date(day.year, day.month, 1) + timedelta(days=32)
    return closing_period(nxt.year, nxt.month, closing_day)


def build_delivery_note(
    store: Store,
    delivery_date: date,
    orders: Iterable[Order],
    products: ProductMaster,
    number: str = "",
) -> DeliveryNote:
    """1店舗・1納品日ぶんの納品書データを作る。同一品目は合算する。"""
    note = DeliveryNote(store=store, delivery_date=delivery_date, number=number)
    note.lines = _aggregate_lines(store, orders, products, keep_date=False)
    return note


def build_invoice(
    store: Store,
    period: ClosingPeriod,
    orders: Iterable[Order],
    products: ProductMaster,
    issue_date: Optional[date] = None,
    number: str = "",
) -> Invoice:
    """1店舗・1締め期間ぶんの請求書データを作る。

    明細は納品日ごとに残す（照合しやすさを優先）。
    配送料はこの店舗の設定に従って加算する。
    """
    invoice = Invoice(
        store=store,
        period_start=period.start,
        period_end=period.end,
        issue_date=issue_date or period.end,
        number=number,
    )
    target = [o for o in orders if o.store_code == store.code]
    invoice.lines = _aggregate_lines(store, target, products, keep_date=True)
    invoice.lines.extend(_delivery_fee_lines(store, target))
    invoice.tax_subtotals = _tax_subtotals(invoice.lines)
    return invoice


def _aggregate_lines(
    store: Store,
    orders: Iterable[Order],
    products: ProductMaster,
    keep_date: bool,
) -> list[BilledLine]:
    """注文行を (納品日,) 品目 単位でまとめて請求行にする。"""
    buckets: "OrderedDict[tuple, BilledLine]" = OrderedDict()

    for order in sorted(orders, key=lambda o: (o.delivery_date, o.order_id or 0)):
        for line in order.lines:
            product = products.get(line.product_code) if line.matched else None
            unit_price = product.price_for(store.code) if product else 0
            tax_rate = product.tax_rate if product else 8
            unit = line.unit or (product.unit if product else "")
            day = order.delivery_date if keep_date else None

            key = (day, line.item_name, unit, unit_price, tax_rate)
            if key in buckets:
                buckets[key].qty += line.qty
            else:
                buckets[key] = BilledLine(
                    item_name=line.item_name,
                    qty=line.qty,
                    unit=unit,
                    unit_price=unit_price,
                    tax_rate=tax_rate,
                    delivery_date=day,
                )

    return list(buckets.values())


def _delivery_fee_lines(store: Store, orders: Iterable[Order]) -> list[BilledLine]:
    """配送料の行を作る。取らない店舗では空リストを返す。"""
    rule = store.delivery_fee
    if not rule.enabled:
        return []

    order_list = list(orders)
    if not order_list:
        return []

    unit_price = rule.amount_excluding_tax  # 税込550円 → 税抜500円
    if rule.charge_unit == "per_delivery":
        days = sorted({o.delivery_date for o in order_list})
        return [
            BilledLine(
                item_name=rule.label,
                qty=1,
                unit="回",
                unit_price=unit_price,
                tax_rate=rule.tax_rate,
                delivery_date=day,
            )
            for day in days
        ]

    return [
        BilledLine(
            item_name=rule.label,
            qty=1,
            unit="式",
            unit_price=unit_price,
            tax_rate=rule.tax_rate,
            delivery_date=None,
        )
    ]


def _tax_subtotals(lines: Iterable[BilledLine]) -> list[TaxSubtotal]:
    """税率ごとに小計と消費税額を出す。消費税は税率ごとに1回だけ端数処理する。"""
    totals: dict[int, int] = {}
    for line in lines:
        totals[line.tax_rate] = totals.get(line.tax_rate, 0) + line.amount

    return [
        TaxSubtotal(
            tax_rate=rate,
            taxable_amount=amount,
            tax_amount=amount * rate // 100,  # 円未満切り捨て
        )
        for rate, amount in sorted(totals.items())
    ]
