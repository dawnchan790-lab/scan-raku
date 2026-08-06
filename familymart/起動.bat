@echo off
rem ファミリーマート 納品書・請求書システム  起動用
rem このファイルをダブルクリックすると、画面がブラウザで開きます。
chcp 65001 > nul
cd /d "%~dp0"

echo.
echo   ファミリーマート 納品書・請求書システム
echo   ----------------------------------------
echo.

where python > nul 2>&1
if errorlevel 1 (
  echo   [エラー] Python が見つかりません。
  echo   https://www.python.org/downloads/ からインストールしてください。
  echo   インストール時に「Add python.exe to PATH」に必ずチェックを入れてください。
  echo.
  pause
  exit /b 1
)

echo   必要な部品を確認しています...
python -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo   [エラー] 部品の準備に失敗しました。
  pause
  exit /b 1
)

echo   画面を開きます。終わるときはこの黒い画面を閉じてください。
echo.
set PYTHONPATH=src
python -m fmbill nyuryoku

pause
