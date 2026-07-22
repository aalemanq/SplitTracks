@echo off
REM Split Tracks — Windows launcher
set DIR=%~dp0
set ROOT=%DIR%..

cd /d "%ROOT%"

if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
)

call .venv\Scripts\activate.bat
pip install -q -r web-app\requirements-web.txt

echo Starting Split Tracks at http://127.0.0.1:8745
python web-app\launcher.py
pause
