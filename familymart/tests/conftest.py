import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fmbill.masters import ProductMaster, StoreMaster  # noqa: E402


@pytest.fixture
def stores() -> StoreMaster:
    return StoreMaster.load(ROOT / "config" / "stores.yaml")


@pytest.fixture
def products() -> ProductMaster:
    return ProductMaster.load(ROOT / "config" / "products.yaml")
