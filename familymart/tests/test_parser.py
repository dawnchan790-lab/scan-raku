from datetime import date

from fmbill.parser import OrderParser


def test_parses_store_date_and_items_from_a_line_message(stores, products):
    text = """
    ファミリーマート国見ケ丘店
    8/7 納品でお願いします
    バナナ　3
    トマト 2
    ほうれん草×5
    """
    result = OrderParser(stores, products).parse(text, received_at=date(2026, 8, 1))

    assert len(result.orders) == 1
    order = result.orders[0]
    assert order.store_code == "KUNIMIGAOKA"
    assert order.delivery_date == date(2026, 8, 7)
    assert [(ln.item_name, ln.qty) for ln in order.lines] == [
        ("バナナ", 3.0),
        ("トマト", 2.0),
        ("ほうれん草", 5.0),
    ]
    assert all(ln.matched for ln in order.lines)


def test_splits_one_message_into_multiple_stores_and_dates(stores, products):
    text = """
    国見ケ丘
    8/7
    バナナ 3
    堤町
    8/8
    トマト 1
    """
    result = OrderParser(stores, products).parse(text, received_at=date(2026, 8, 1))

    assert len(result.orders) == 2
    keys = {(o.store_code, o.delivery_date) for o in result.orders}
    assert keys == {("KUNIMIGAOKA", date(2026, 8, 7)), ("TSUTSUMICHO", date(2026, 8, 8))}


def test_store_alias_is_resolved(stores, products):
    # 「国見ヶ丘」（大きいヶ）でも同じ店舗として扱う
    text = "国見ヶ丘\n8/7\nバナナ 3"
    result = OrderParser(stores, products).parse(text, received_at=date(2026, 8, 1))
    assert result.orders[0].store_code == "KUNIMIGAOKA"


def test_store_and_date_on_the_same_line(stores, products):
    text = "国見ケ丘店 8/7\nバナナ 3"
    result = OrderParser(stores, products).parse(text, received_at=date(2026, 8, 1))

    assert result.orders[0].store_code == "KUNIMIGAOKA"
    assert result.orders[0].delivery_date == date(2026, 8, 7)


def test_store_name_followed_by_an_item_on_the_same_line_is_a_detail(stores, products):
    text = "国見ケ丘\n8/7\n国見ケ丘 バナナ 3"
    result = OrderParser(stores, products).parse(text, received_at=date(2026, 8, 1))

    assert [ln.item_name for ln in result.orders[0].lines] == ["バナナ"]


def test_product_is_matched_within_the_stores_group(stores, products):
    """同じ「バナナ」でもグループごとに売価が違うので、店舗のグループで引き分ける。"""
    parser = OrderParser(stores, products)

    kunimi = parser.parse("国見ケ丘\n8/7\nバナナ 1", received_at=date(2026, 8, 1))
    omachi = parser.parse("大町２丁目\n8/7\nバナナ 1", received_at=date(2026, 8, 1))

    kunimi_code = kunimi.orders[0].lines[0].product_code
    omachi_code = omachi.orders[0].lines[0].product_code
    assert kunimi_code.startswith("宗久-")
    assert omachi_code.startswith("大町-")
    assert kunimi_code != omachi_code


def test_lot_store_multiplies_by_the_minimum_lot(stores, products):
    """マルカ系は「ロット数」で発注する。数量＝ロット数×最小発注ロット。"""
    # バナナ（太め1本）の最小発注ロットは4
    assert products.get("マル-バナナ太め1本").min_lot == 4

    result = OrderParser(stores, products).parse(
        "仙台高野原\n8/7\nバナナ 3", received_at=date(2026, 8, 1)
    )
    line = result.orders[0].lines[0]

    assert line.input_qty == 3     # 注文票に書かれた数（ロット数）
    assert line.qty == 12          # 実数量 3ロット × 4


def test_qty_store_uses_the_number_as_written(stores, products):
    result = OrderParser(stores, products).parse(
        "国見ケ丘\n8/7\nバナナ 3", received_at=date(2026, 8, 1)
    )
    line = result.orders[0].lines[0]

    assert line.input_qty == 3
    assert line.qty == 3


def test_unknown_item_is_kept_but_flagged(stores, products):
    text = "国見ケ丘\n8/7\nドラゴンフルーツ 2"
    result = OrderParser(stores, products).parse(text, received_at=date(2026, 8, 1))

    line = result.orders[0].lines[0]
    assert line.item_name == "ドラゴンフルーツ"
    assert not line.matched
    assert result.unmatched_count == 1
    assert any("商品マスタに無い品目" in w for w in result.warnings)


def test_raw_text_is_preserved_for_audit(stores, products):
    text = "国見ケ丘\n8/7\nバナナ　3"
    result = OrderParser(stores, products).parse(text, received_at=date(2026, 8, 1))
    assert result.orders[0].lines[0].raw_text == "バナナ　3"


def test_lines_without_a_store_are_reported_not_silently_dropped(stores, products):
    text = "8/7\nバナナ 3"
    result = OrderParser(stores, products).parse(text, received_at=date(2026, 8, 1))

    assert result.orders == []
    assert any("店舗が特定できない" in w for w in result.warnings)


def test_defaults_fill_in_missing_store_and_date(stores, products):
    result = OrderParser(stores, products).parse(
        "バナナ 3",
        default_store_code="KUNIMIGAOKA",
        default_date=date(2026, 8, 7),
    )
    assert result.orders[0].store_code == "KUNIMIGAOKA"
    assert result.orders[0].delivery_date == date(2026, 8, 7)


def test_noise_lines_from_ocr_are_ignored(stores, products):
    text = """
    ファミリーマート国見ケ丘店
    令和8年8月7日
    バナナ 3
    合計 3
    以上よろしくお願いします
    """
    result = OrderParser(stores, products).parse(
        text, source="fax", received_at=date(2026, 8, 1)
    )
    assert len(result.orders[0].lines) == 1
