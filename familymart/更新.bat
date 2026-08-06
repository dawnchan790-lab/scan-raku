@echo off
rem 最新版に更新する（Windows）
rem 入力したデータ（data）と設定（config）はそのまま残します。
chcp 65001 > nul
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  set PY=.venv\Scripts\python.exe
) else (
  where python > nul 2>&1
  if errorlevel 1 (
    echo   [エラー] Python が見つかりません。
    pause
    exit /b 1
  )
  set PY=python
)

%PY% tools\update.py
echo   「起動.bat」を開いてお使いください。
echo.
pause
