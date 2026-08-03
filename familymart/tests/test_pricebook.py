"""売価の書き換えのテスト。

売価は毎週変わるので、画面から直せるようにしてある。
原価は売価と掛け率から毎回計算するため、売価を直せば原価も追随する。
"""

import shutil
from pathlib import Path

import pytest

from fmbill.masters import ProductMaster, StoreMaster
from fmbill.pricebook import load_raw, update_prices

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def products_file(tmp_path) -> Path:
    path = tmp_path / "products.yaml"
    shutil.copy(ROOT / "config" / "products.yaml", path)
    return path


def test_price_is_updated(products_file):
    changed = update_prices(products_file, {"宗久-トマト": 320})
    assert changed == 1
    prices = {p["code"]: p["retail_price"] for p in load_raw(products_file)["products"]}
    assert prices["宗久-トマト"] == 320


def test_other_products_are_left_alone(products_file):
    before = {p["code"]: p["retail_price"] for p in load_raw(products_file)["products"]}
    update_prices(products_file, {"宗久-トマト": 320})
    after = {p["code"]: p["retail_price"] for p in load_raw(products_file)["products"]}

    assert len(after) == len(before)
    assert all(after[c] == before[c] for c in before if c != "宗久-トマト")


def test_file_can_still_be_loaded_after_writing(products_file):
    update_prices(products_file, {"宗久-トマト": 320})
    master = ProductMaster.load(products_file)
    assert len(master) == len(load_raw(products_file)["products"])
    assert master.get("宗久-トマト").retail_price == 320


def test_cost_follows_the_new_price(products_file):
    """売価を直すと原価も計算し直される（現行Excelのように古い値が残らない）。"""
    stores = StoreMaster.load(ROOT / "config" / "stores.yaml")
    store = stores.get("KUNIMIGAOKA")     # 掛け率25%

    update_prices(products_file, {"宗久-トマト": 200})
    product = ProductMaster.load(products_file).get("宗久-トマト")

    assert product.retail_price_for(store) == 200
    assert product.cost_price_for(store) == 150      # 200×0.75


def test_unknown_code_is_ignored(products_file):
    assert update_prices(products_file, {"そんな商品ない": 100}) == 0


def test_negative_price_is_rejected(products_file):
    with pytest.raises(ValueError):
        update_prices(products_file, {"宗久-トマト": -1})
