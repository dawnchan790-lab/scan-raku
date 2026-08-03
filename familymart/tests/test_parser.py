from datetime import date

from fmbill.parser import OrderParser


def test_parses_store_date_and_items_from_a_line_message(stores, products):
    text = """
    ファミリーマート国見ヶ丘店
    8/7 納品でお願いします
    きゅうり　3
    トマト 2パック
    なす×5
    """
    result = OrderParser(stores, products).parse(text, received_at=date(2026, 8, 1))

    assert len(result.orders) == 1
    order = result.orders[0]
    assert order.store_code == "0807230"
    assert order.delivery_date == date(2026, 8, 7)
    assert [(ln.item_name, ln.qty) for ln in order.lines] == [
        ("キュウリ", 3.0),
        ("トマト", 2.0),
        ("ナス", 5.0),
    ]
    assert all(ln.matched for ln in order.lines)


def test_splits_one_message_into_multiple_stores_and_dates(stores, products):
    text = """
    国見ヶ丘
    8/7
    きゅうり 3
    サンプル2
    8/8
    トマト 1
    """
    result = OrderParser(stores, products).parse(text, received_at=date(2026, 8, 1))

    assert len(result.orders) == 2
    keys = {(o.store_code, o.delivery_date) for o in result.orders}
    assert keys == {("0807230", date(2026, 8, 7)), ("SAMPLE-02", date(2026, 8, 8))}


def test_store_name_ending_in_a_digit_is_still_a_heading(stores, products):
    # 「サンプル2」を「品目=サンプル 数量=2」と読んでしまわないこと
    text = "サンプル2\n8/8\nトマト 1"
    result = OrderParser(stores, products).parse(text, received_at=date(2026, 8, 1))

    assert len(result.orders) == 1
    assert result.orders[0].store_code == "SAMPLE-02"
    assert [ln.item_name for ln in result.orders[0].lines] == ["トマト"]


def test_store_name_followed_by_an_item_on_the_same_line_is_a_detail(stores, products):
    text = "国見ヶ丘\n8/7\n国見ヶ丘 きゅうり 3"
    result = OrderParser(stores, products).parse(text, received_at=date(2026, 8, 1))

    assert [ln.item_name for ln in result.orders[0].lines] == ["キュウリ"]


def test_store_and_date_on_the_same_line(stores, products):
    text = "国見ヶ丘店 8/7\nきゅうり 3"
    result = OrderParser(stores, products).parse(text, received_at=date(2026, 8, 1))

    assert result.orders[0].store_code == "0807230"
    assert result.orders[0].delivery_date == date(2026, 8, 7)


def test_store_alias_is_resolved(stores, products):
    text = "国見ケ丘\n8/7\nきゅうり 3"
    result = OrderParser(stores, products).parse(text, received_at=date(2026, 8, 1))
    assert result.orders[0].store_code == "0807230"


def test_unknown_item_is_kept_but_flagged(stores, products):
    text = "国見ヶ丘\n8/7\nドラゴンフルーツ 2"
    result = OrderParser(stores, products).parse(text, received_at=date(2026, 8, 1))

    line = result.orders[0].lines[0]
    assert line.item_name == "ドラゴンフルーツ"
    assert not line.matched
    assert result.unmatched_count == 1
    assert any("商品マスタに無い品目" in w for w in result.warnings)


def test_raw_text_is_preserved_for_audit(stores, products):
    text = "国見ヶ丘\n8/7\nきゅうり　3"
    result = OrderParser(stores, products).parse(text, received_at=date(2026, 8, 1))
    assert result.orders[0].lines[0].raw_text == "きゅうり　3"


def test_lines_without_a_store_are_reported_not_silently_dropped(stores, products):
    text = "8/7\nきゅうり 3"
    result = OrderParser(stores, products).parse(text, received_at=date(2026, 8, 1))

    assert result.orders == []
    assert any("店舗が特定できない" in w for w in result.warnings)


def test_defaults_fill_in_missing_store_and_date(stores, products):
    result = OrderParser(stores, products).parse(
        "きゅうり 3",
        default_store_code="0807230",
        default_date=date(2026, 8, 7),
    )
    assert result.orders[0].store_code == "0807230"
    assert result.orders[0].delivery_date == date(2026, 8, 7)


def test_noise_lines_from_ocr_are_ignored(stores, products):
    text = """
    ファミリーマート国見ヶ丘店
    令和8年8月7日
    きゅうり 3
    合計 3
    以上よろしくお願いします
    """
    result = OrderParser(stores, products).parse(
        text, source="fax", received_at=date(2026, 8, 1)
    )
    assert len(result.orders[0].lines) == 1
