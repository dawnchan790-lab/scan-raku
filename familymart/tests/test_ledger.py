from datetime import date

from fmbill.ledger import Ledger
from fmbill.models import Order, OrderLine


def _order(day: date, source_ref: str = "msg-1") -> Order:
    return Order(
        store_code="0807230",
        delivery_date=day,
        lines=[OrderLine(raw_text="きゅうり 3", item_name="キュウリ", qty=3, product_code="P001")],
        source="line",
        source_ref=source_ref,
    )


def test_saves_and_reads_back_orders(tmp_path):
    ledger = Ledger(tmp_path / "test.db")
    ledger.add_orders([_order(date(2026, 8, 7))])

    orders = ledger.orders_on(date(2026, 8, 7))
    assert len(orders) == 1
    assert orders[0].lines[0].item_name == "キュウリ"
    assert orders[0].lines[0].qty == 3


def test_same_message_imported_twice_is_not_double_counted(tmp_path):
    ledger = Ledger(tmp_path / "test.db")
    ledger.add_orders([_order(date(2026, 8, 7))])
    saved = ledger.add_orders([_order(date(2026, 8, 7))])

    assert saved == []
    assert len(ledger.orders_on(date(2026, 8, 7))) == 1


def test_period_query_includes_both_end_dates(tmp_path):
    ledger = Ledger(tmp_path / "test.db")
    ledger.add_orders(
        [
            _order(date(2026, 7, 20), "a"),  # 期間外
            _order(date(2026, 7, 21), "b"),  # 期間の初日
            _order(date(2026, 8, 20), "c"),  # 期間の最終日
            _order(date(2026, 8, 21), "d"),  # 期間外
        ]
    )

    orders = ledger.orders_between(date(2026, 7, 21), date(2026, 8, 20))
    assert [o.delivery_date for o in orders] == [date(2026, 7, 21), date(2026, 8, 20)]


def test_replace_order_overwrites_the_previous_entry(tmp_path):
    """入力画面で開き直して数量を直したとき、前の内容が残らないこと。"""
    ledger = Ledger(tmp_path / "test.db")

    def manual(qty: float) -> Order:
        return Order(
            store_code="KUNIMIGAOKA",
            delivery_date=date(2026, 7, 30),
            lines=[
                OrderLine(
                    raw_text="", item_name="バナナ", qty=qty, input_qty=qty,
                    product_code="宗久-バナナ",
                )
            ],
            source="manual",
            source_ref="入力画面",
        )

    ledger.replace_order(manual(10))
    ledger.replace_order(manual(3))

    orders = ledger.orders_on(date(2026, 7, 30))
    assert len(orders) == 1
    assert [ln.qty for ln in orders[0].lines] == [3]


def test_replace_order_leaves_other_sources_alone(tmp_path):
    """入力画面の保存で、FAXから取り込んだ同じ日の注文まで消さないこと。"""
    ledger = Ledger(tmp_path / "test.db")
    fax = Order(
        store_code="KUNIMIGAOKA",
        delivery_date=date(2026, 7, 30),
        lines=[OrderLine(raw_text="", item_name="トマト", qty=2, product_code="宗久-トマト")],
        source="fax",
        source_ref="fax-1",
    )
    ledger.add_orders([fax])

    ledger.replace_order(
        Order(
            store_code="KUNIMIGAOKA",
            delivery_date=date(2026, 7, 30),
            lines=[OrderLine(raw_text="", item_name="バナナ", qty=1, product_code="宗久-バナナ")],
            source="manual",
        )
    )

    sources = sorted(o.source for o in ledger.orders_on(date(2026, 7, 30)))
    assert sources == ["fax", "manual"]
