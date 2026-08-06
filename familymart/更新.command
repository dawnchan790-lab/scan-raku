#!/bin/bash
# 最新版に更新する（Mac）
# 入力したデータ（data）と設定（config）はそのまま残します。
cd "$(dirname "$0")" || exit 1

if [ -x "./.venv/bin/python" ]; then
  PY="./.venv/bin/python"
elif command -v python3 > /dev/null 2>&1; then
  PY="python3"
else
  echo "  [エラー] Python が見つかりません。"
  read -r -p "  Enterキーで閉じます "
  exit 1
fi

"$PY" tools/update.py
echo "  「起動.command」を開いてお使いください。"
echo
read -r -p "  Enterキーで閉じます "
