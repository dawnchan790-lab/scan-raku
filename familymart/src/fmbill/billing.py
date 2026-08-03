"""締め処理。仕分け帳から納品書・請求書のデータを組み立てる。"""

from __future__ import annotations

import calendar
from collections import OrderedDict
from datetime import date, timedelta
from typing import Iterable, Optional

from .masters import ProductMaster
from .models import (
    DeliveryLine,
    DeliveryNote,
    Invoice,
    InvoiceRow,
    Order,
    Store,
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
    """1店舗・1納品日ぶんの納品書データを作る。同一品目は合算する。

    送料はその日に1品でも納品があれば加算する（現行の発注書の式と同じ）。
    """
    target = [o for o in orders if o.store_code == store.code and o.delivery_date == delivery_date]
    lines = _aggregate_lines(store, target, products)

    note = DeliveryNote(store=store, delivery_date=delivery_date, lines=lines, number=number)
    if lines and store.delivery_fee.enabled:
        note.shipping_fee = store.delivery_fee.amount
    return note


def build_invoice(
    store: Store,
    period: ClosingPeriod,
    orders: Iterable[Order],
    products: ProductMaster,
    issue_date: Optional[date] = None,
    payment_due: Optional[date] = None,
    number: str = "",
) -> Invoice:
    """1店舗・1締め期間ぶんの請求書データを作る。

    現行の請求書にならい、明細は品目単位ではなく **納品日ごとに1行**（品名「売上」）。
    送料をもらう店舗は、同じ納品日にもう1行（10%対象）を足す。
    """
    invoice = Invoice(
        store=store,
        period_start=period.start,
        period_end=period.end,
        issue_date=issue_date or period.end,
        payment_due=payment_due,
        number=number,
    )

    target = [
        o
        for o in orders
        if o.store_code == store.code and period.start <= o.delivery_date <= period.end
    ]
    for delivery_date in sorted({o.delivery_date for o in target}):
        note = build_delivery_note(store, delivery_date, target, products)
        if note.cost_total:
            invoice.rows.append(
                InvoiceRow(
                    sale_date=delivery_date,
                    item_name="売上",
                    amount=note.cost_total,
                    reduced_tax=True,
                )
            )
        if note.shipping_fee:
            invoice.rows.append(
                InvoiceRow(
                    sale_date=delivery_date,
                    item_name=store.delivery_fee.label,
                    amount=note.shipping_fee,
                    reduced_tax=False,
                )
            )

    return invoice


def _aggregate_lines(
    store: Store, orders: Iterable[Order], products: ProductMaster
) -> list[DeliveryLine]:
    """注文行を品目単位でまとめて納品書の明細にする。"""
    buckets: "OrderedDict[tuple, DeliveryLine]" = OrderedDict()

    for order in sorted(orders, key=lambda o: (o.delivery_date, o.order_id or 0)):
        for line in order.lines:
            product = products.get(line.product_code) if line.matched else None
            retail = product.retail_price_for(store) if product else 0
            cost = product.cost_price_for(store) if product else 0
            unit = line.unit or (product.unit if product else "")
            reduced = product.reduced_tax if product else True

            key = (line.item_name, unit, retail, cost, reduced)
            if key in buckets:
                buckets[key].qty += line.qty
            else:
                buckets[key] = DeliveryLine(
                    item_name=line.item_name,
                    qty=line.qty,
                    unit=unit,
                    retail_price=retail,
                    cost_price=cost,
                    reduced_tax=reduced,
                )

    return list(buckets.values())
