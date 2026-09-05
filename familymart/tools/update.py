"""最新版に更新する。

入力したデータ（data）と設定（config）はそのまま残し、プログラムだけを入れ替える。

ZIPの展開は Python の zipfile で行う。OS付属の unzip コマンドは
日本語のファイル名を壊すことがあるため（「実データ...」が「#U5b9f#U30c7...」になる）。

    python3 tools/update.py
"""

from __future__ import annotations

import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ZIP_URL = (
    "https://github.com/dawnchan790-lab/scan-raku/archive/refs/heads/"
    "claude/familymart-invoice-billing-system-3x4y49.zip"
)

# 入れ替えるもの。data と config は触らない（入力したデータと設定を守るため）
REPLACE = ["src", "templates", "tools", "docs", "samples"]
COPY_FILES = [
    "requirements.txt", "requirements-fax.txt", "README.md",
    "はじめかた.md", "導入マニュアル.md",
    "起動.command", "起動.bat", "更新.command", "更新.bat",
    "今日の帳票.command", "今日の帳票.bat", "月末の請求書.command", "月末の請求書.bat",
]


def main() -> int:
    print()
    print("  ファミリーマート 納品・請求システム  更新")
    print("  ----------------------------------------")
    print()
    print("  入力したデータ（data）と設定（config）は残したまま、")
    print("  プログラムだけを新しくします。")
    print()

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        print("  最新版を取ってきています...")
        try:
            urllib.request.urlretrieve(ZIP_URL, work / "new.zip")
        except Exception as error:
            print(f"  [エラー] 取得できませんでした: {error}")
            print("  インターネットにつながっているか確認してください。")
            return 1

        # zipfile はファイル名をUTF-8のまま扱うので、日本語名が壊れない
        with zipfile.ZipFile(work / "new.zip") as archive:
            archive.extractall(work)

        found = list(work.glob("*/familymart"))
        if not found:
            print("  [エラー] 中身が見つかりませんでした。")
            return 1
        new = found[0]

        # 取り違えたときに戻せるよう、消す前に控えを取る
        backup = ROOT / "更新前の控え"
        if backup.exists():
            shutil.rmtree(backup)
        backup.mkdir()

        for name in REPLACE:
            source = new / name
            if not source.exists():
                continue
            target = ROOT / name
            if target.exists():
                shutil.copytree(target, backup / name)
                shutil.rmtree(target)
            shutil.copytree(source, target)

        for name in COPY_FILES:
            source = new / name
            if source.exists():
                shutil.copy2(source, ROOT / name)

        # 設定は上書きしない。新しい版は見比べられるよう別名で置く
        if (new / "config").exists():
            spare = ROOT / "config_新しい版"
            if spare.exists():
                shutil.rmtree(spare)
            shutil.copytree(new / "config", spare)

    for name in ("起動.command", "更新.command", "今日の帳票.command", "月末の請求書.command"):
        path = ROOT / name
        if path.exists():
            path.chmod(0o755)

    print()
    print("  更新しました。")
    print("  ・入力したデータ（data）はそのままです")
    print("  ・設定（config）もそのままです")
    print("    新しい版の設定は config_新しい版 に入れてあります（必要なときだけ見てください）")
    print("  ・更新前のプログラムは 更新前の控え に残してあります")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
