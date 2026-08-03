from datetime import date

import pytest

from fmbill.billing import build_delivery_note, build_invoice, closing_period, period_containing
from fmbill.models import Order, OrderLine


def _order(store_code: str, day: date, items: list[tuple[str, float]]) -> Order:
    return Order(
        store_code=store_code,
        delivery_date=day,
        lines=[
            OrderLine(raw_text="", item_name=code, qty=qty, input_qty=qty, product_code=code)
            for code, qty in items
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


class TestCostPrice:
    """原価 = ROUNDUP(想定税込売価 × (1 − 粗利益率), 0)"""

    def test_matches_the_current_workbook(self, stores, products):
        # 現行ブック（宗久グループ 掛け率25%）: バナナ 売価218 → 原価164
        store = stores.get("KUNIMIGAOKA")
        banana = products.get("宗久-バナナ")
        assert banana.retail_price_for(store) == 218
        assert banana.cost_price_for(store) == 164   # 218×0.75=163.5 → 切り上げ

    def test_store_margin_rate_changes_the_cost(self, stores, products):
        # 同じ商品でも大郷山崎店は掛け率10%なので原価が上がる
        banana = products.get("宗久-バナナ")
        assert banana.cost_price_for(stores.get("KUNIMIGAOKA")) == 164     # 25%
        assert banana.cost_price_for(stores.get("OOSATOYAMAZAKI")) == 197  # 10% → 196.2 切り上げ

    def test_roundup_never_rounds_down(self, stores, products):
        store = stores.get("KUNIMIGAOKA")
        for product in products:
            retail = product.retail_price_for(store)
            cost = product.cost_price_for(store)
            assert cost >= retail * (1 - product.margin_rate_for(store))


class TestDeliveryNote:
    def test_shipping_is_added_once_for_a_store_that_charges_it(self, stores, products):
        store = stores.get("KUNIMIGAOKA")
        orders = [
            _order("KUNIMIGAOKA", date(2026, 8, 3), [("宗久-バナナ", 10)]),
            _order("KUNIMIGAOKA", date(2026, 8, 3), [("宗久-トマト", 2)]),  # 同じ日の2件目
        ]

        note = build_delivery_note(store, date(2026, 8, 3), orders, products)

        assert note.shipping_fee == 550
        assert note.cost_total == 10 * 164 + 2 * 216   # トマト 288×0.75=216
        assert note.total == note.cost_total + 550

    def test_takanohara_gets_no_shipping(self, stores, products):
        store = stores.get("TAKANOHARA")
        orders = [_order("TAKANOHARA", date(2026, 8, 3), [("マル-バナナ太め1本", 4)])]

        note = build_delivery_note(store, date(2026, 8, 3), orders, products)

        assert note.shipping_fee == 0
        assert note.total == note.cost_total

    def test_no_order_means_no_shipping(self, stores, products):
        note = build_delivery_note(stores.get("KUNIMIGAOKA"), date(2026, 8, 3), [], products)
        assert note.shipping_fee == 0
        assert note.total == 0

    def test_same_item_is_merged(self, stores, products):
        store = stores.get("KUNIMIGAOKA")
        orders = [
            _order("KUNIMIGAOKA", date(2026, 8, 3), [("宗久-バナナ", 3)]),
            _order("KUNIMIGAOKA", date(2026, 8, 3), [("宗久-バナナ", 4)]),
        ]

        note = build_delivery_note(store, date(2026, 8, 3), orders, products)

        assert len(note.lines) == 1
        assert note.lines[0].qty == 7


class TestInvoice:
    def test_one_row_per_delivery_date_plus_a_shipping_row(self, stores, products):
        store = stores.get("KUNIMIGAOKA")
        period = closing_period(2026, 8)
        orders = [
            _order("KUNIMIGAOKA", date(2026, 7, 25), [("宗久-バナナ", 10)]),
            _order("KUNIMIGAOKA", date(2026, 8, 3), [("宗久-バナナ", 5)]),
        ]

        invoice = build_invoice(store, period, orders, products)

        assert [(r.sale_date, r.item_name, r.amount) for r in invoice.rows] == [
            (date(2026, 7, 25), "売上", 1640),
            (date(2026, 7, 25), "送料", 550),
            (date(2026, 8, 3), "売上", 820),
            (date(2026, 8, 3), "送料", 550),
        ]

    def test_takanohara_invoice_has_no_shipping_rows(self, stores, products):
        store = stores.get("TAKANOHARA")
        period = closing_period(2026, 8)
        orders = [_order("TAKANOHARA", date(2026, 8, 3), [("マル-バナナ太め1本", 4)])]

        invoice = build_invoice(store, period, orders, products)

        assert [r.item_name for r in invoice.rows] == ["売上"]
        assert invoice.standard_total == 0

    def test_totals_split_8_percent_from_10_percent(self, stores, products):
        store = stores.get("KUNIMIGAOKA")
        period = closing_period(2026, 8)
        orders = [_order("KUNIMIGAOKA", date(2026, 8, 3), [("宗久-バナナ", 10)])]

        invoice = build_invoice(store, period, orders, products)

        assert invoice.reduced_total == 1640    # 商品（軽減税率8%）
        assert invoice.standard_total == 550    # 送料（標準税率10%）
        assert invoice.total == 2190

    def test_tax_is_derived_from_tax_inclusive_amounts(self, stores, products):
        """税込金額から内消費税を逆算する。10%は「÷11」相当（現行ファイルは÷10で誤り）。"""
        store = stores.get("KUNIMIGAOKA")
        period = closing_period(2026, 8)
        # 送料550円が7回分 = 3,850円（現行の請求書と同じ条件）
        orders = [
            _order("KUNIMIGAOKA", date(2026, 8, day), [("宗久-バナナ", 1)])
            for day in (3, 4, 5, 6, 7, 10, 11)
        ]

        invoice = build_invoice(store, period, orders, products)

        assert invoice.standard_total == 3850
        assert round(invoice.standard_tax_amount) == 350   # 3850/11。385ではない

    def test_orders_outside_the_period_are_excluded(self, stores, products):
        store = stores.get("KUNIMIGAOKA")
        period = closing_period(2026, 8)     # 2026/07/21〜2026/08/20
        orders = [
            _order("KUNIMIGAOKA", date(2026, 7, 20), [("宗久-バナナ", 1)]),  # 期間外
            _order("KUNIMIGAOKA", date(2026, 7, 21), [("宗久-バナナ", 1)]),  # 初日
            _order("KUNIMIGAOKA", date(2026, 8, 20), [("宗久-バナナ", 1)]),  # 最終日
            _order("KUNIMIGAOKA", date(2026, 8, 21), [("宗久-バナナ", 1)]),  # 期間外
        ]

        invoice = build_invoice(store, period, orders, products)

        assert sorted({r.sale_date for r in invoice.rows}) == [
            date(2026, 7, 21),
            date(2026, 8, 20),
        ]

    def test_other_stores_are_not_mixed_in(self, stores, products):
        period = closing_period(2026, 8)
        orders = [
            _order("KUNIMIGAOKA", date(2026, 8, 3), [("宗久-バナナ", 1)]),
            _order("TSUTSUMICHO", date(2026, 8, 3), [("宗久-バナナ", 9)]),
        ]

        invoice = build_invoice(stores.get("KUNIMIGAOKA"), period, orders, products)

        assert invoice.reduced_total == 164
