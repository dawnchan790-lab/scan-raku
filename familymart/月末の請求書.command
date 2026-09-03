#!/bin/bash
# 締め月の請求書を全店ぶん作ります（Mac）
# 何も入れずにEnterを押すと「先月の締め分」を作ります。
cd "$(dirname "$0")" || exit 1
trap 'echo; read -r -p "  Enterキーを押すと閉じます "' EXIT

PY="./.venv/bin/python"
[ -x "$PY" ] || PY="python3"

echo
echo "  請求書をまとめて作ります"
echo "  ------------------------"
echo "  締め年月を入れてください（例: 2026-08）"
echo "  そのままEnterを押すと、先月の締め分を作ります。"
echo
read -r -p "  締め年月: " MONTH
"$PY" tools/auto.py --seikyu $MONTH
