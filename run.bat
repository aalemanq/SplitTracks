@echo off
REM Split Tracks — Windows launcher
set DIR=%~dp0

cd /d "%DIR%"

if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
)

call .venv\Scripts\activate.bat
pip install -q -r requirements-web.txt

echo Starting Split Tracks at http://127.0.0.1:8745
python launcher.py
pause
