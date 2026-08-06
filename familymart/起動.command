#!/bin/bash
# ファミリーマート 納品・請求システム  起動用（Mac）
# このファイルをダブルクリックすると、画面がブラウザで開きます。
cd "$(dirname "$0")" || exit 1

echo
echo "  ファミリーマート 納品・請求システム"
echo "  ------------------------------------"
echo

if ! command -v python3 > /dev/null 2>&1; then
  echo "  [エラー] Python が見つかりません。"
  echo "  https://www.python.org/downloads/ からインストールしてから、もう一度開いてください。"
  echo
  read -r -p "  Enterキーで閉じます "
  exit 1
fi

# このフォルダ専用のPython環境を作る。
# パソコン全体のPythonを触らないので、権限のエラーが起きません。
if [ ! -d ".venv" ]; then
  echo "  はじめての起動なので、準備をします（1〜2分かかります）..."
  python3 -m venv .venv || {
    echo "  [エラー] 準備に失敗しました。"
    read -r -p "  Enterキーで閉じます "
    exit 1
  }
fi

./.venv/bin/python -m pip install --quiet --upgrade pip
./.venv/bin/python -m pip install --quiet -r requirements.txt || {
  echo "  [エラー] 必要な部品を入れられませんでした。"
  read -r -p "  Enterキーで閉じます "
  exit 1
}

echo "  画面を開きます。終わるときはこの画面を閉じてください。"
echo
PYTHONPATH=src ./.venv/bin/python -m fmbill nyuryoku
