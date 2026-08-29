@echo off
rem ファミリーマート 納品・請求システム  起動用（Windows）
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
  pause
  exit /b 1
)

if not exist ".venv" (
  echo   はじめての起動なので、準備をします（1〜2分かかります）...
  python -m venv .venv
  if errorlevel 1 (
    echo   [エラー] 準備用の環境を作れませんでした。
    echo   上に出ている英語のメッセージをそのままお知らせください。
    pause
    exit /b 1
  )
)

set PY=.venv\Scripts\python.exe
%PY% -m pip install --quiet --upgrade pip 2>nul

echo   必要な部品を確認しています...
%PY% -m pip install --quiet -r requirements.txt
if errorlevel 1 (
  echo   [エラー] 必要な部品を入れられませんでした。
  echo   インターネットにつながっているか確認してください。
  pause
  exit /b 1
)

rem FAX読み取り用。入らなくても他の画面は動くので止めない。
%PY% -m pip install --quiet -r requirements-fax.txt 2>nul
if errorlevel 1 (
  echo.
  echo   [お知らせ] FAX読み取り用の部品が入りませんでした。
  echo   「FAXから入れる」画面だけ使えませんが、他の画面は使えます。
  echo.
)

echo.
echo   画面を開きます。
echo   ★ 使っている間、この黒い画面は閉じないでください。
echo.
set PYTHONPATH=src
%PY% -m fmbill nyuryoku

pause
