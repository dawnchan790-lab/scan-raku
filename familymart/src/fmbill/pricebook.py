"""商品マスタ（config/products.yaml）の書き換え。

売価は季節や仕入れで毎週変わる。発注書ブックからまとめて取り込むほかに、
画面から1品ずつ直せるようにしておく。

原価は売価と掛け率から毎回計算しているので、売価を直せば原価も自動で追随する。
現行のExcelのように「売価を下げたのに仕入額が古いまま」ということは起こらない。
"""

from __future__ import annotations

from pathlib import Path

import yaml

HEADER = """# 商品マスタ
#
# retail_price … 想定税込売価
# margin_rate  … 粗利益率（掛け率）。原価＝ROUNDUP(retail_price×(1−margin_rate),0)
#                書いていない品目は config/stores.yaml の店舗の掛け率が効く
# min_lot      … 最小発注ロット。ロット制の店舗は「ロット数×min_lot」が数量になる
# groups       … この商品を扱うグループ
# reduced_tax  … true=軽減税率8%（食品）/ false=標準税率10%
#
# 売価は入力画面（価格の編集）からも直せます。
# 発注書ブックからまとめて取り込み直すときは tools/import_products.py を使ってください。

"""

# 出力するときの項目の並び。読みやすさのために固定する。
FIELD_ORDER = [
    "code",
    "name",
    "retail_price",
    "margin_rate",
    "groups",
    "min_lot",
    "spec",
    "origin",
    "storage",
    "shelf_life_days",
    "reduced_tax",
    "aliases",
    "store_overrides",
]


def load_raw(path: str | Path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def update_prices(path: str | Path, prices: dict[str, int]) -> int:
    """{商品コード: 売価} を受け取って products.yaml を書き換える。

    実際に値が変わった件数を返す。存在しない商品コードは無視する。
    """
    data = load_raw(path)
    changed = 0
    for entry in data.get("products") or []:
        code = str(entry.get("code"))
        if code in prices:
            new_price = int(prices[code])
            if new_price < 0:
                raise ValueError(f"売価が負の数です: {code} = {new_price}")
            if entry.get("retail_price") != new_price:
                entry["retail_price"] = new_price
                changed += 1

    if changed:
        write(path, data)
    return changed


def write(path: str | Path, data: dict) -> None:
    """読みやすい並びで products.yaml を書き出す。"""
    lines = [HEADER.rstrip("\n"), ""]

    defaults = data.get("defaults")
    if defaults:
        lines.append(yaml.safe_dump({"defaults": defaults}, allow_unicode=True, sort_keys=False).rstrip())
        lines.append("")

    lines.append("products:")
    for entry in data.get("products") or []:
        ordered = {key: entry[key] for key in FIELD_ORDER if key in entry}
        # 並びから漏れた項目も落とさずに残す
        ordered.update({k: v for k, v in entry.items() if k not in ordered})
        block = yaml.safe_dump([ordered], allow_unicode=True, sort_keys=False, width=200)
        lines.append("\n".join("  " + line for line in block.rstrip().splitlines()))

    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
