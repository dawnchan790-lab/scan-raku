"""設定ファイルの場所とマスタをまとめて保持するアプリケーションコンテキスト。"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from .excel import Layout, load_layouts
from .ledger import Ledger
from .masters import ProductMaster, StoreMaster

# familymart/ ディレクトリ
BASE_DIR = Path(__file__).resolve().parents[2]


@dataclass
class AppContext:
    base_dir: Path = BASE_DIR

    @property
    def config_dir(self) -> Path:
        return self.base_dir / "config"

    @property
    def data_dir(self) -> Path:
        return self.base_dir / "data"

    @property
    def output_dir(self) -> Path:
        return self.base_dir / "output"

    @cached_property
    def stores(self) -> StoreMaster:
        return StoreMaster.load(self.config_dir / "stores.yaml")

    @cached_property
    def products(self) -> ProductMaster:
        return ProductMaster.load(self.config_dir / "products.yaml")

    @cached_property
    def layouts(self) -> dict[str, Layout]:
        return load_layouts(self.config_dir / "layouts.yaml")

    @cached_property
    def ledger(self) -> Ledger:
        return Ledger(self.data_dir / "shiwake.db")

    def resolve(self, relative: str) -> Path:
        """設定ファイルに書かれた相対パスを familymart/ 基準で解決する。"""
        path = Path(relative)
        return path if path.is_absolute() else self.base_dir / path
