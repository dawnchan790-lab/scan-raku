"""仕分け表（倉庫のピッキング用）のテスト。"""

from datetime import date

from fmbill.picking import build_picking_tables, export_picking_sheet
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


DAY = date(2026, 7, 30)


def test_same_price_stores_share_one_sheet(stores, products):
    """宗久グループと大町2丁目は売価が同じなので1枚にまとめる。"""
    orders = [
        _order("KUNIMIGAOKA", DAY, [("宗久-バナナ", 10)]),
        _order("OMACHI2", DAY, [("宗久-バナナ", 4)]),
        _order("TSUTSUMICHO", DAY, [("宗久-バナナ", 6)]),
    ]

    tables = build_picking_tables(DAY, orders, stores, products)

    assert len(tables) == 1
    assert sorted(s.code for s in tables[0].stores) == ["KUNIMIGAOKA", "OMACHI2", "TSUTSUMICHO"]


def test_maruka_gets_its_own_sheet(stores, products):
    """マルカ系は品目も売価も違うので別の表にする。"""
    orders = [
        _order("KUNIMIGAOKA", DAY, [("宗久-バナナ", 1)]),
        _order("TAKANOHARA", DAY, [("マル-バナナ太め1本", 1)]),
    ]

    groups = {t.group for t in build_picking_tables(DAY, orders, stores, products)}

    assert groups == {"宗久グループ", "マルカ系"}


def test_quantities_are_laid_out_by_store(stores, products):
    orders = [
        _order("KUNIMIGAOKA", DAY, [("宗久-バナナ", 10), ("宗久-トマト", 4)]),
        _order("OMACHI2", DAY, [("宗久-トマト", 2)]),
    ]

    table = build_picking_tables(DAY, orders, stores, products)[0]
    rows = {r.item_name: r for r in table.rows}

    assert rows["バナナ"].quantities == {"KUNIMIGAOKA": 10}
    assert rows["トマト"].quantities == {"KUNIMIGAOKA": 4, "OMACHI2": 2}
    assert rows["トマト"].total == 6
    assert table.total_for("KUNIMIGAOKA") == 14


def test_items_without_orders_are_left_out(stores, products):
    """注文の無い品目は載せない（商品マスタ全部が並ぶと使いにくいため）。"""
    orders = [_order("KUNIMIGAOKA", DAY, [("宗久-バナナ", 1)])]

    table = build_picking_tables(DAY, orders, stores, products)[0]

    assert [r.item_name for r in table.rows] == ["バナナ"]


def test_rows_follow_the_product_master_order(stores, products):
    """並びは商品マスタ順。発注書と同じ並びで倉庫を回れるようにするため。"""
    codes = [p.code for p in products if p.applies_to(stores.get("KUNIMIGAOKA"))]
    picked = [codes[5], codes[1], codes[3]]
    orders = [_order("KUNIMIGAOKA", DAY, [(c, 1) for c in picked])]

    table = build_picking_tables(DAY, orders, stores, products)[0]
    names = [r.item_name for r in table.rows]

    expected = [products.get(c).name for c in (codes[1], codes[3], codes[5])]
    assert names == expected


def test_unknown_item_is_kept_and_flagged(stores, products):
    """商品マスタに無い品目も落とさない（積み忘れを防ぐため）。"""
    order = Order(
        store_code="KUNIMIGAOKA",
        delivery_date=DAY,
        lines=[OrderLine(raw_text="", item_name="ドラゴンフルーツ", qty=2)],
    )

    table = build_picking_tables(DAY, [order], stores, products)[0]

    assert [(r.item_name, r.matched) for r in table.rows] == [("ドラゴンフルーツ", False)]


def test_other_days_are_excluded(stores, products):
    orders = [
        _order("KUNIMIGAOKA", DAY, [("宗久-バナナ", 1)]),
        _order("KUNIMIGAOKA", date(2026, 7, 31), [("宗久-トマト", 9)]),
    ]

    table = build_picking_tables(DAY, orders, stores, products)[0]

    assert [r.item_name for r in table.rows] == ["バナナ"]


def test_excel_is_written(stores, products, tmp_path):
    from openpyxl import load_workbook

    orders = [
        _order("KUNIMIGAOKA", DAY, [("宗久-バナナ", 10)]),
        _order("OMACHI2", DAY, [("宗久-バナナ", 4)]),
    ]
    tables = build_picking_tables(DAY, orders, stores, products)

    out = export_picking_sheet(tables, tmp_path / "仕分け表.xlsx")
    sheet = load_workbook(out)["宗久グループ"]

    assert sheet["A3"].value == "品名"
    assert sheet["A4"].value == "バナナ"
    assert sheet["G3"].value is None or "合計" in str(sheet.cell(row=3, column=6).value or "")
