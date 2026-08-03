from datetime import date

from fmbill.textutil import normalize, parse_date, parse_item_line


def test_normalize_converts_fullwidth_and_collapses_spaces():
    assert normalize("きゅうり　　３袋") == "きゅうり 3袋"
    assert normalize("ﾄﾏﾄ") == "トマト"


def test_parse_date_full_formats():
    assert parse_date("2026/8/7") == date(2026, 8, 7)
    assert parse_date("2026年8月7日") == date(2026, 8, 7)
    assert parse_date("2026-08-07") == date(2026, 8, 7)


def test_parse_date_japanese_era():
    assert parse_date("令和8年8月7日") == date(2026, 8, 7)
    assert parse_date("R8.8.7") == date(2026, 8, 7)


def test_parse_date_short_form_uses_year_hint():
    assert parse_date("8/7", default_year=2026) == date(2026, 8, 7)
    assert parse_date("8月7日", default_year=2026) == date(2026, 8, 7)


def test_parse_date_returns_none_for_invalid():
    assert parse_date("よろしくお願いします") is None
    assert parse_date("2026/2/30") is None


def test_parse_item_line_variants():
    assert parse_item_line("きゅうり 3袋") == ("きゅうり", 3.0, "袋")
    assert parse_item_line("きゅうり　3") == ("きゅうり", 3.0, "")
    assert parse_item_line("トマト×2パック") == ("トマト", 2.0, "パック")
    assert parse_item_line("なす:5") == ("なす", 5.0, "")
    assert parse_item_line("3袋 きゅうり") == ("きゅうり", 3.0, "袋")


def test_parse_item_line_does_not_mistake_a_date_for_an_item():
    # 「8/7」を「品目=8/ 数量=7」と読んでしまわないこと
    assert parse_item_line("8/7") is None
    assert parse_item_line("8月7日") is None
    assert parse_item_line("8/7(金)") is None
    assert parse_item_line("2026/8/7") is None
    assert parse_item_line("令和8年8月7日") is None


def test_parse_item_line_rejects_non_detail_rows():
    assert parse_item_line("合計 12") is None
    assert parse_item_line("消費税 960") is None
    assert parse_item_line("よろしくお願いします") is None
    assert parse_item_line("") is None
