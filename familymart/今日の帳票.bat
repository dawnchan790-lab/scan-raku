@echo off
chcp 65001 > nul
cd /d "%~dp0"
set PY=.venv\Scripts\python.exe
if not exist "%PY%" set PY=python
echo.
echo   今日の帳票をまとめて作ります
echo   ----------------------------
%PY% tools\auto.py
pause
