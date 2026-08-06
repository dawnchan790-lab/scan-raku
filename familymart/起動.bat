@echo off
rem ファミリーマート 納品・請求システム  起動用（Windows）
rem このファイルをダブルクリックすると、画面がブラウザで開きます。
chcp 65001 > nul
cd /d "%~dp0"

echo.
echo   ファミリーマート 納品・請求システム
echo   ------------------------------------
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

rem このフォルダ専用のPython環境を作る（パソコン全体のPythonを触らない）
if not exist ".venv" (
  echo   はじめての起動なので、準備をします（1〜2分かかります）...
  python -m venv .venv
  if errorlevel 1 (
    echo   [エラー] 準備に失敗しました。
    pause
    exit /b 1
  )
)

.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
.venv\Scripts\python.exe -m pip install --quiet -r requirements.txt
if errorlevel 1 (
  echo   [エラー] 必要な部品を入れられませんでした。
  pause
  exit /b 1
)

echo   画面を開きます。終わるときはこの黒い画面を閉じてください。
echo.
set PYTHONPATH=src
.venv\Scripts\python.exe -m fmbill nyuryoku

pause
