from datetime import date

import pytest

from fmbill.billing import build_invoice, closing_period, period_containing
from fmbill.models import Order, OrderLine


def _order(store_code: str, day: date, items: list[tuple[str, str, float]]) -> Order:
    return Order(
        store_code=store_code,
        delivery_date=day,
        lines=[
            OrderLine(raw_text="", item_name=name, qty=qty, unit="", product_code=code)
            for code, name, qty in items
        ],
    )


class TestClosingPeriod:
    def test_20th_closing_runs_from_21st_of_previous_month(self):
        period = closing_period(2026, 8, closing_day=20)
        assert period.start == date(2026, 7, 21)
        assert period.end == date(2026, 8, 20)

    def test_january_closing_crosses_the_year_boundary(self):
        period = closing_period(2026, 1, closing_day=20)
        assert period.start == date(2025, 12, 21)
        assert period.end == date(2026, 1, 20)

    def test_march_closing_handles_short_february(self):
        period = closing_period(2026, 3, closing_day=20)
        assert period.start == date(2026, 2, 21)
        assert period.end == date(2026, 3, 20)

    def test_month_end_closing_covers_whole_month(self):
        period = closing_period(2026, 2, closing_day=31)
        assert period.start == date(2026, 2, 1)
        assert period.end == date(2026, 2, 28)

    @pytest.mark.parametrize(
        "day,expected_end",
        [
            (date(2026, 8, 20), date(2026, 8, 20)),   # 締め日当日は当月締め
            (date(2026, 8, 21), date(2026, 9, 20)),   # 締め日翌日から次期間
            (date(2026, 12, 25), date(2027, 1, 20)),  # 年をまたぐ
        ],
    )
    def test_period_containing(self, day, expected_end):
        assert period_containing(day, closing_day=20).end == expected_end


class TestInvoice:
    def test_store_with_delivery_fee_gets_one_550_yen_line_per_month(self, stores, products):
        store = stores.get("0807230")
        period = closing_period(2026, 8)
        orders = [
            _order("0807230", date(2026, 7, 25), [("P001", "キュウリ", 10)]),
            _order("0807230", date(2026, 8, 3), [("P001", "キュウリ", 5)]),
        ]

        invoice = build_invoice(store, period, orders, products)

        fee_lines = [ln for ln in invoice.lines if ln.item_name == "配送料"]
        assert len(fee_lines) == 1
        # 税込550円 → 税抜500円 + 消費税50円
        assert fee_lines[0].unit_price == 500
        assert fee_lines[0].tax_rate == 10

    def test_store_without_delivery_fee_gets_no_fee_line(self, stores, products):
        store = stores.get("SAMPLE-02")
        period = closing_period(2026, 8)
        orders = [_order("SAMPLE-02", date(2026, 8, 3), [("P001", "キュウリ", 5)])]

        invoice = build_invoice(store, period, orders, products)

        assert [ln for ln in invoice.lines if ln.item_name == "配送料"] == []
        assert invoice.tax_total == 5 * 150 * 8 // 100

    def test_totals_split_food_8_percent_from_delivery_fee_10_percent(self, stores, products):
        store = stores.get("0807230")
        period = closing_period(2026, 8)
        # キュウリ150円 × 10 = 1,500円（8%）、配送料 税抜500円（10%）
        orders = [_order("0807230", date(2026, 8, 3), [("P001", "キュウリ", 10)])]

        invoice = build_invoice(store, period, orders, products)
        by_rate = {st.tax_rate: st for st in invoice.tax_subtotals}

        assert by_rate[8].taxable_amount == 1500
        assert by_rate[8].tax_amount == 120
        assert by_rate[10].taxable_amount == 500
        assert by_rate[10].tax_amount == 50
        assert invoice.subtotal == 2000
        assert invoice.total == 2170

    def test_store_specific_price_overrides_standard_price(self, stores, products):
        store = stores.get("0807230")
        period = closing_period(2026, 8)
        orders = [_order("0807230", date(2026, 8, 3), [("P002", "トマト", 3)])]

        invoice = build_invoice(store, period, orders, products)
        tomato = next(ln for ln in invoice.lines if ln.item_name == "トマト")

        assert tomato.unit_price == 230  # 標準220円ではなく店舗別単価
        assert tomato.amount == 690

    def test_same_item_on_the_same_day_is_merged(self, stores, products):
        store = stores.get("0807230")
        period = closing_period(2026, 8)
        orders = [
            _order("0807230", date(2026, 8, 3), [("P001", "キュウリ", 3)]),
            _order("0807230", date(2026, 8, 3), [("P001", "キュウリ", 4)]),
            _order("0807230", date(2026, 8, 5), [("P001", "キュウリ", 2)]),
        ]

        invoice = build_invoice(store, period, orders, products)
        cucumbers = [ln for ln in invoice.lines if ln.item_name == "キュウリ"]

        # 同じ日ぶんは1行にまとまり、別の日は別行のまま残る
        assert len(cucumbers) == 2
        assert cucumbers[0].qty == 7
        assert cucumbers[1].qty == 2

    def test_per_delivery_fee_charges_each_delivery_day(self, stores, products):
        store = stores.get("0807230")
        store.delivery_fee.charge_unit = "per_delivery"
        period = closing_period(2026, 8)
        orders = [
            _order("0807230", date(2026, 8, 3), [("P001", "キュウリ", 1)]),
            _order("0807230", date(2026, 8, 5), [("P001", "キュウリ", 1)]),
        ]

        invoice = build_invoice(store, period, orders, products)

        assert len([ln for ln in invoice.lines if ln.item_name == "配送料"]) == 2
