"""FAXで返ってきた発注書を、1行ずつの画像に切り分ける。

**数字の自動判定は行わない。** 数量を取り違えると請求金額がそのまま狂うため、
機械は「行を切り出して見やすく並べる」ところまでを担い、
数字の確定は画面上で人が目で見て行う（web.py / static/fax.html）。

FAXの縦罫線はかすれて消えることが多く列の自動検出は当てにならないので、
**横罫線だけを頼りに行を切り出す**方式にしている。


店舗に送っているのは決まった書式の用紙なので、
自由な文字を読むのではなく **表の枠を見つけて、発注数のマスを1つずつ切り出す**。

手書きの数字を機械が断定するのは危ないので、このモジュールは
「どのマスに書き込みがあるか」と「そのマスの画像」までを出す。
数字の確定は画面上で人が目で見て行う（切り出した画像を横に並べて表示する）。
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageFile, ImageOps

ImageFile.LOAD_TRUNCATED_IMAGES = True

# 発注書の明細は最大57行（1〜58行目のうち最後は送料）
MAX_ROWS = 60


@dataclass
class FaxCell:
    """発注数のマス1つ分。"""

    row_index: int          # 表の上から何行目か（0起点）
    ink_ratio: float        # マスの中の黒い画素の割合
    image: Image.Image      # 発注数のあたりを切り出した画像
    name_image: Optional[Image.Image] = None   # 同じ行の品名側

    written: bool = False   # 書き込みがあるとみなすか（用紙全体を見て判定する）

    @property
    def has_writing(self) -> bool:
        return self.written


@dataclass
class FaxSheet:
    """FAX1枚ぶんの読み取り結果。"""

    page: int
    cells: list[FaxCell]
    header: Image.Image     # 発注日・納品日・店名が書かれている上部
    full: Image.Image       # ページ全体（確認用）

    @property
    def written_cells(self) -> list[FaxCell]:
        return [c for c in self.cells if c.has_writing]


# 書き込みの判定。FAXの濃さは1枚ごとに大きく変わるので、決め打ちの値では当てにならない。
# 同じ用紙の中の「ふつうの空欄」と比べて、はっきり濃い行だけを書き込みありとみなす。
INK_MIN = 0.05           # これ以下は罫線のかすれとみなす
INK_RELATIVE = 2.0       # 空欄の中央値の何倍で書き込みとみなすか

# 表の左端からの割合で、切り出す範囲を決める。用紙の書式が変わったらここを直す。
NAME_RIGHT_RATIO = 0.34    # 品名までの範囲
QTY_LEFT_RATIO = 0.81      # 発注数の欄の左（最小発注ロットの右）
QTY_RIGHT_RATIO = 0.86     # 発注数の欄の右（計算表の手前）


def load_pages(path: str | Path, dpi: int = 200) -> list[Image.Image]:
    """PDFでも画像でも受け取れるようにして、ページ画像の一覧を返す。"""
    path = Path(path)
    if path.suffix.lower() != ".pdf":
        return [ImageOps.exif_transpose(Image.open(path)).convert("L")]

    with tempfile.TemporaryDirectory() as tmp:
        prefix = Path(tmp) / "page"
        subprocess.run(
            ["pdftoppm", "-r", str(dpi), "-png", str(path), str(prefix)],
            check=True,
            capture_output=True,
        )
        return [Image.open(p).convert("L") for p in sorted(Path(tmp).glob("page-*.png"))]


def read_sheet(image: Image.Image, page: int = 1) -> Optional[FaxSheet]:
    """1ページを行ごとに切り分ける。表が見つからなければ None。

    FAXの縦罫線はかすれて消えることが多く、列を自動で当てるのは当てにならない。
    そこで **横罫線だけを頼りに行を切り出し**、各行の右側（発注数のあたり）と
    左側（品名）をそれぞれ画像として残す。数字の確定は画面で人が行う。
    """
    # FAXやスマホ撮影は紙が傾く。傾いたままだと罫線を見つけられないので先に直す。
    image = deskew(image)
    binary = _binarize(image)

    rows = _fill_gaps(_find_lines(binary.sum(axis=1), binary.shape[1], ratio=0.15))
    if len(rows) < 10:
        return None

    left, right = _table_extent(binary, rows)
    width = right - left
    if width < 100:
        return None

    # 発注数の欄は表の右のほう。多少ずれても入るよう広めに取る。
    qty_left = left + int(width * QTY_LEFT_RATIO)
    qty_right = left + int(width * QTY_RIGHT_RATIO)
    name_right = left + int(width * NAME_RIGHT_RATIO)

    cells = []
    for index in range(min(len(rows) - 1, MAX_ROWS)):
        top, bottom = rows[index], rows[index + 1]
        if bottom - top < 8:      # 罫線が二重に検出された分は飛ばす
            continue
        qty_crop = image.crop((qty_left, top + 2, qty_right, bottom - 2))
        cells.append(
            FaxCell(
                row_index=len(cells),
                ink_ratio=_ink_ratio(qty_crop),
                image=qty_crop,
                name_image=image.crop((left, top + 2, name_right, bottom - 2)),
            )
        )

    _mark_written(cells)
    header = image.crop((0, 0, image.width, rows[0]))
    return FaxSheet(page=page, cells=cells, header=header, full=image)


def _mark_written(cells: list[FaxCell]) -> None:
    """用紙全体を見て、どの行に書き込みがあるかを決める。

    空欄の行にも罫線のかすれで多少の黒が出る。その「ふつうの濃さ」を
    中央値で捉え、そこからはっきり離れた行だけを書き込みありとする。
    """
    if not cells:
        return
    baseline = float(np.median([c.ink_ratio for c in cells]))
    threshold = max(INK_MIN, baseline * INK_RELATIVE)
    for cell in cells:
        cell.written = cell.ink_ratio >= threshold


def _table_extent(binary: np.ndarray, rows: list[int]) -> tuple[int, int]:
    """横罫線が伸びている範囲から、表の左端と右端を求める。"""
    band = binary[rows[0] : rows[-1], :]
    # 罫線の行だけを足し合わせると、表の外は黒画素がほぼ0になる
    column_hits = band.sum(axis=0).astype(np.float64)
    # スキャンの左右の縁が黒く出ることがあるので、外周は表の一部とみなさない
    margin = int(len(column_hits) * 0.03)
    column_hits[:margin] = 0
    column_hits[-margin:] = 0

    # 罫線の本数のうち半分以上に黒が乗っている列だけを表の内側とみなす
    threshold = max(2, int(len(rows) * 0.5))
    inside = np.flatnonzero(column_hits > threshold)
    if inside.size == 0:
        return 0, binary.shape[1]
    return int(inside[0]), int(inside[-1])


def read_file(path: str | Path, dpi: int = 200) -> list[FaxSheet]:
    """ファイル1つを読み、ページごとの結果を返す。"""
    sheets = []
    for index, page_image in enumerate(load_pages(path, dpi=dpi), start=1):
        sheet = read_sheet(page_image, page=index)
        if sheet is not None:
            sheets.append(sheet)
    return sheets


def deskew(image: Image.Image, limit: float = 4.0, step: float = 0.25) -> Image.Image:
    """紙の傾きを直す。

    少しずつ回しながら「横方向の黒画素の偏り」がいちばん大きくなる角度を選ぶ。
    罫線がまっすぐ横になったとき、その行に黒が集中して偏りが最大になる。
    """
    # 探索は縮小画像で行う（全画素で回すと遅いため）
    scale = 900 / max(image.width, 1)
    small = image.resize((900, max(1, int(image.height * scale))), Image.BILINEAR)

    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-limit, limit + step / 2, step):
        rotated = small.rotate(angle, resample=Image.BILINEAR, fillcolor=255)
        projection = _binarize(rotated).sum(axis=1).astype(np.float64)
        score = float((projection**2).sum())     # 偏りが大きいほど大きくなる
        if score > best_score:
            best_angle, best_score = float(angle), score

    if abs(best_angle) < step / 2:
        return image
    return image.rotate(best_angle, resample=Image.BICUBIC, fillcolor=255)


# --------------------------------------------------------------------- 内部
def _binarize(image: Image.Image) -> np.ndarray:
    """罫線を探すための白黒化。1 = 黒。"""
    array = np.asarray(image, dtype=np.uint8)
    return (array < 128).astype(np.uint8)


def _find_lines(projection: np.ndarray, span: int, ratio: float = 0.45) -> list[int]:
    """黒画素の投影から罫線の位置を拾う。

    表の罫線はページを横切るので、その方向の黒画素が突出して多くなる。
    近い位置に出た検出はまとめて1本として扱う。
    """
    # スキャンの縁が黒くなることがあるので、外周は見ない
    margin = int(len(projection) * 0.02)
    window = projection.copy()
    window[:margin] = 0
    window[-margin:] = 0

    threshold = span * ratio
    hits = np.flatnonzero(window > threshold)
    if hits.size == 0:
        return []

    # 罫線は太さがあり数画素にわたって当たるので、近いものは1本にまとめる。
    # まとめる幅は画像の大きさに応じて決める（解像度が変わっても効くように）。
    gap = max(4, int(len(projection) * 0.006))
    lines = [int(hits[0])]
    for position in hits[1:]:
        if position - lines[-1] > gap:
            lines.append(int(position))
    return lines


def _fill_gaps(lines: list[int]) -> list[int]:
    """かすれて拾えなかった罫線を、行の間隔から補って埋める。

    1本見落とすとその2行が1つにつながり、発注数を取りこぼす。
    行の高さはほぼ一定なので、間隔が広すぎるところに等間隔で足す。
    """
    if len(lines) < 4:
        return lines

    gaps = np.diff(lines)
    typical = float(np.median(gaps))
    if typical <= 0:
        return lines

    filled = [lines[0]]
    for previous, current in zip(lines, lines[1:]):
        missing = int(round((current - previous) / typical)) - 1
        for step in range(1, missing + 1):
            filled.append(previous + int(round(typical * step)))
        filled.append(current)
    return filled


def _ink_ratio(crop: Image.Image) -> float:
    """マスの中の黒画素の割合。罫線が入らないよう内側を少し削って測る。"""
    array = np.asarray(crop, dtype=np.uint8)
    if array.size == 0:
        return 0.0
    margin_y = max(1, array.shape[0] // 8)
    margin_x = max(1, array.shape[1] // 8)
    inner = array[margin_y:-margin_y, margin_x:-margin_x]
    if inner.size == 0:
        return 0.0
    return float((inner < 128).mean())
