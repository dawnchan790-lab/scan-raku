#!/bin/bash
# ファミリーマート 納品・請求システム  起動用（Mac）
cd "$(dirname "$0")" || exit 1

# 何があってもこの画面を閉じない。エラーが読めるようにするため。
finish() {
  echo
  read -r -p "  Enterキーを押すと閉じます "
}
trap finish EXIT

echo
echo "  ファミリーマート 納品・請求システム"
echo "  ------------------------------------"
echo

if ! command -v python3 > /dev/null 2>&1; then
  echo "  [エラー] Python が見つかりません。"
  echo "  https://www.python.org/downloads/ からインストールしてから、もう一度開いてください。"
  exit 1
fi
echo "  Python: $(python3 --version 2>&1)"

# このフォルダ専用のPython環境を作る（パソコン全体のPythonを触らない）
if [ ! -d ".venv" ]; then
  echo "  はじめての起動なので、準備をします（1〜2分かかります）..."
  if ! python3 -m venv .venv; then
    echo
    echo "  [エラー] 準備用の環境を作れませんでした。"
    echo "  上に出ている英語のメッセージをそのままお知らせください。"
    exit 1
  fi
fi

PY="./.venv/bin/python"
"$PY" -m pip install --quiet --upgrade pip 2>/dev/null

echo "  必要な部品を確認しています..."
if ! "$PY" -m pip install --quiet -r requirements.txt; then
  echo
  echo "  [エラー] 必要な部品を入れられませんでした。"
  echo "  インターネットにつながっているか確認してください。"
  echo "  上に出ている英語のメッセージをそのままお知らせください。"
  exit 1
fi

# FAXの読み取りに使う部品。入らなくても他の画面は動くので、失敗しても止めない。
if ! "$PY" -m pip install --quiet -r requirements-fax.txt 2>/dev/null; then
  echo
  echo "  [お知らせ] FAX読み取り用の部品が入りませんでした。"
  echo "  「FAXから入れる」画面だけ使えませんが、他の画面はそのまま使えます。"
  echo
fi

echo
echo "  画面を開きます。"
echo "  ★ 使っている間、この画面は閉じないでください。"
echo
PYTHONPATH=src "$PY" -m fmbill nyuryoku
