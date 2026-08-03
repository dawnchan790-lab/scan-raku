"""現行の発注書ブックから config/products.yaml を作り直す。

品目・売価は毎週変わるので、最新の発注書ブックを渡して随時作り直す想定。

    python3 tools/import_products.py \\
        "templates/現行/⑥発注書納品書_宗久グループ_0807230.xlsx:宗久グループ" \\
        "templates/現行/⑧発注書納品書_大町2丁目店_080801.xlsx:大町2丁目店（別オーナー）" \\
        "templates/現行/③発注書納品書_マルカ系_7.21納品.xlsx:マルカ系"

引数は「ブックのパス:グループ名」。グループ名は config/stores.yaml の group と合わせる。
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fmbill.import_orderbook import import_products  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "config" / "products.yaml"

HEADER = """# 商品マスタ（現行の発注書ブックから取り込み）
#
# retail_price … 想定税込売価
# margin_rate  … 粗利益率（掛け率）。原価＝ROUNDUP(retail_price×(1−margin_rate),0)
# min_lot      … 最小発注ロット。ロット制の店舗は「ロット数×min_lot」が数量になる
# groups       … この商品を扱うグループ。品目も売価もグループごとに違うため必須
# reduced_tax  … true=軽減税率8%（食品）/ false=標準税率10%
#
# ★ このファイルは tools/import_products.py で作り直せます。
#   売価が変わったら、最新の発注書ブックを渡して再生成してください。
#   手で足した aliases（表記ゆれ）は再生成で消えるので、別途控えておいてください。

defaults:
  reduced_tax: true
  unit: 個

products:
"""


def _quote(text: str) -> str:
    escaped = str(text).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def main(specs: list[str]) -> int:
    entries: list[str] = []
    seen: dict[str, str] = {}
    non_food: list[str] = []
    total = 0

    for spec in specs:
        path_text, _, group = spec.rpartition(":")
        if not path_text or not group:
            print(f"引数の形式が正しくありません: {spec}（ブックのパス:グループ名）")
            return 2
        path = Path(path_text)
        if not path.is_absolute():
            path = ROOT / path

        products = import_products(path)
        total += len(products)

        # そのブックで最も多い粗利益率をグループの既定とみなす。
        # 商品側に書くのは既定から外れた「例外」だけにして、
        # ふだんは config/stores.yaml の margin_rate（店舗の掛け率）が効くようにする。
        rates = Counter(p.margin_rate for p in products)
        common_rate = rates.most_common(1)[0][0] if rates else None
        exceptions = sum(1 for p in products if p.margin_rate != common_rate)
        print(
            f"{group}: {len(products)}品目  ← {path.name}"
            f"  （掛け率の既定 {common_rate:.0%} / 例外 {exceptions}品目）"
        )
        print(f"    → config/stores.yaml のこのグループの margin_rate を {common_rate} にしてください")

        for product in products:
            # グループをまたぐと同じ品名でも別商品なので、コードにグループを混ぜる
            code = f"{group[:2]}-{product.code}"
            if code in seen:
                print(f"  [注意] 商品コードが重複したため読み飛ばしました: {code}")
                continue
            seen[code] = group

            lines = [
                f"  - code: {_quote(code)}",
                f"    name: {_quote(product.name)}",
                f"    retail_price: {product.retail_price}",
                f"    groups: [{_quote(group)}]",
            ]
            if product.margin_rate != common_rate:
                # 店舗の掛け率ではなくこの値を使う（例外品目）
                lines.append(f"    margin_rate: {product.margin_rate}")
            if product.min_lot != 1:
                lines.append(f"    min_lot: {product.min_lot}")
            for field_name, value in (
                ("spec", product.spec),
                ("origin", product.origin),
                ("storage", product.storage),
            ):
                if value:
                    lines.append(f"    {field_name}: {_quote(value)}")
            if product.shelf_life_days is not None:
                lines.append(f"    shelf_life_days: {product.shelf_life_days}")
            if not product.reduced_tax:
                lines.append("    reduced_tax: false   # 食品ではないため標準税率10%")
                non_food.append(f"{group} / {product.name}")
            entries.append("\n".join(lines))

    OUT.write_text(HEADER + "\n".join(entries) + "\n", encoding="utf-8")
    print(f"\n{OUT} に {len(entries)}品目を書き出しました（読み取り {total}件）")
    if non_food:
        print("\n食品ではないと判定し、標準税率10%にした品目（要確認）:")
        for item in non_food:
            print(f"  - {item}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1:]))
