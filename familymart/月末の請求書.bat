@echo off
chcp 65001 > nul
cd /d "%~dp0"
set PY=.venv\Scripts\python.exe
if not exist "%PY%" set PY=python
echo.
echo   請求書をまとめて作ります
echo   ------------------------
echo   締め年月を入れてください（例: 2026-08）
echo   そのままEnterを押すと、先月の締め分を作ります。
echo.
set /p MONTH="  締め年月: "
%PY% tools\auto.py --seikyu %MONTH%
pause
