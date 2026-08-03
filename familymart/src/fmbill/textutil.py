"""FAX/LINEの生テキストを扱うための文字列ユーティリティ。"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Optional

# 数量に添えられる単位。ここに無い単位は商品マスタ側の単位を使う。
UNITS = ["ケース", "パック", "袋", "箱", "本", "個", "束", "玉", "枚", "kg", "g", "P", "c/s"]

_UNIT_PATTERN = "|".join(re.escape(u) for u in sorted(UNITS, key=len, reverse=True))

# 「きゅうり 3袋」「きゅうり×3」「きゅうり…3」など、品目のあとに数量が来る形
_QTY_AFTER = re.compile(
    rf"^(?P<item>.+?)[\s:：×xX*・.、,\-—ー…]*"
    rf"(?P<qty>\d+(?:\.\d+)?)\s*(?P<unit>{_UNIT_PATTERN})?\s*$"
)
# 「3袋 きゅうり」など、数量が先に来る形
_QTY_BEFORE = re.compile(
    rf"^(?P<qty>\d+(?:\.\d+)?)\s*(?P<unit>{_UNIT_PATTERN})?[\s:：×xX*・、,\-]+(?P<item>.+?)\s*$"
)

# 合計行など、明細として取り込んではいけない行
_EXCLUDE = re.compile(r"合計|小計|総計|税込|税抜|消費税|以上|よろしく|お願い|注文|発注|納品|様$|店$")

# 「8/7」「8月7日(木)」のような日付だけの行。
# 数字を含むので放っておくと「品目=8/ 数量=7」と誤読されるため、明細判定より先に弾く。
DATE_ONLY = re.compile(
    r"^(?:(?:令和|平成|R|H)\s*\d{1,2}\D{0,2})?"
    r"(?:\d{4}\D{1,2})?"
    r"\d{1,2}\s*[/年月.\-]\s*\d{1,2}\s*日?"
    r"(?:\s*[(（][月火水木金土日][)）])?$"
)

_ERA_START = {"令和": 2018, "平成": 1988, "R": 2018, "H": 1988}


def normalize(text: str) -> str:
    """全角→半角、カナ統一、空白の圧縮を行う。照合の前段として必ず通す。"""
    if not text:
        return ""
    # NFKC で全角英数・半角カナをまとめて正規化する
    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.replace("　", " ")
    return re.sub(r"\s+", " ", normalized).strip()


def parse_date(text: str, default_year: Optional[int] = None) -> Optional[date]:
    """テキストから日付を1つ取り出す。和暦・年省略にも対応する。"""
    hay = normalize(text)
    year_hint = default_year or date.today().year

    # 令和7年8月7日 / R7.8.7
    era = re.search(r"(令和|平成|R|H)\s*(\d{1,2})\D{0,2}(\d{1,2})\D{0,2}(\d{1,2})", hay)
    if era:
        base = _ERA_START[era.group(1)]
        return _safe_date(base + int(era.group(2)), int(era.group(3)), int(era.group(4)))

    # 2026/8/7, 2026-08-07, 2026年8月7日
    full = re.search(r"(\d{4})\D{1,2}(\d{1,2})\D{1,2}(\d{1,2})", hay)
    if full:
        return _safe_date(int(full.group(1)), int(full.group(2)), int(full.group(3)))

    # 8/7, 8月7日 （年は補完する）
    short = re.search(r"(?<!\d)(\d{1,2})\s*[/月.\-]\s*(\d{1,2})\s*日?(?!\d)", hay)
    if short:
        return _safe_date(year_hint, int(short.group(1)), int(short.group(2)))

    return None


def parse_item_line(line: str) -> Optional[tuple[str, float, str]]:
    """明細行を (品目名, 数量, 単位) に分解する。明細でなければ None。"""
    text = normalize(line)
    if not text or _EXCLUDE.search(text):
        return None
    if not re.search(r"\d", text):
        return None
    if DATE_ONLY.match(text):
        return None

    for pattern in (_QTY_AFTER, _QTY_BEFORE):
        match = pattern.match(text)
        if not match:
            continue
        item = match.group("item").strip(" :：×xX*・.、,-—ー…")
        qty = float(match.group("qty"))
        unit = (match.group("unit") or "").strip()
        # 品目名が数字だけ・空になった行は明細ではない
        if not item or item.isdigit():
            continue
        return item, qty, unit

    return None


def _safe_date(year: int, month: int, day: int) -> Optional[date]:
    try:
        return date(year, month, day)
    except ValueError:
        return None
