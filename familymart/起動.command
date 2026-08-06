#!/bin/bash
# ファミリーマート 納品書・請求書システム  起動用（Mac）
# このファイルをダブルクリックすると、画面がブラウザで開きます。
cd "$(dirname "$0")" || exit 1

echo
echo "  ファミリーマート 納品書・請求書システム"
echo "  ----------------------------------------"
echo

if ! command -v python3 > /dev/null 2>&1; then
  echo "  [エラー] Python が見つかりません。"
  echo "  https://www.python.org/downloads/ からインストールしてください。"
  read -r -p "  Enterキーで閉じます "
  exit 1
fi

echo "  必要な部品を確認しています..."
python3 -m pip install --quiet --disable-pip-version-check -r requirements.txt || {
  echo "  [エラー] 部品の準備に失敗しました。"
  read -r -p "  Enterキーで閉じます "
  exit 1
}

echo "  画面を開きます。終わるときはこの画面を閉じてください。"
echo
PYTHONPATH=src python3 -m fmbill nyuryoku
