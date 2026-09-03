#!/bin/bash
# 今日の納品ぶんの「仕分け表」と「納品書」をまとめて作ります（Mac）
cd "$(dirname "$0")" || exit 1
trap 'echo; read -r -p "  Enterキーを押すと閉じます "' EXIT

PY="./.venv/bin/python"
[ -x "$PY" ] || PY="python3"

echo
echo "  今日の帳票をまとめて作ります"
echo "  ----------------------------"
"$PY" tools/auto.py
