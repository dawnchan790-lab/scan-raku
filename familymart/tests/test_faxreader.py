"""FAX読み取りの回帰テスト。

実際に返送されたFAX（仙台高野原店 2026/8/3発注 → 8/6納品）を使う。
数字の自動判定は行わない方針なので、ここで確かめるのは
「行を正しく切り出せているか」と「切り出した画像が作れているか」まで。
"""

from pathlib import Path

import pytest

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "FAX返信_仙台高野原店_20260803.pdf"

pytest.importorskip("numpy")
pytest.importorskip("PIL")


@pytest.fixture(scope="module")
def sheet():
    from fmbill.faxreader import read_file

    sheets = read_file(SAMPLE, dpi=150)
    if not sheets:
        pytest.skip("pdftoppm が無いため読み取れません（poppler-utils が必要）")
    return sheets[0]


def test_rows_are_separated(sheet):
    # 用紙の明細は40行。見出しや欄外を含めても極端な数にはならない
    assert 30 <= len(sheet.cells) <= 45


def test_every_row_has_crops_to_show(sheet):
    """どの行も、画面に出す品名側と数量側の画像が作れていること。"""
    for cell in sheet.cells:
        assert cell.name_image is not None
        assert cell.image.width > 0 and cell.image.height > 0
        assert cell.name_image.width > cell.image.width   # 品名側のほうが広い


def test_blank_rows_are_not_reported_as_written(sheet):
    """まったく書き込みの無い行が「書き込みあり」にならないこと。"""
    quiet = [c for c in sheet.cells if c.ink_ratio < 0.001]
    assert quiet, "白紙の行が1つも無いのは切り出し位置がずれている疑いがある"
    assert not any(c.has_writing for c in quiet)


def test_header_is_kept_for_checking_store_and_date(sheet):
    """発注日・納品日・店名を目で確かめるための上部画像が残っていること。"""
    assert sheet.header.height > 50
