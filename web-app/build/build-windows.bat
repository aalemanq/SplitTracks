@echo off
REM Build Split Tracks for Windows
REM Requirements: Python 3 with pip

setlocal enabledelayedexpansion
cd /d "%~dp0\..\.."

set APP_NAME=SplitTracks
set VENV_PYTHON=.venv\Scripts\python.exe
set DIST=dist\%APP_NAME%-windows

echo === Building Split Tracks for Windows ===

echo [1/4] Installing dependencies...
%VENV_PYTHON% -m pip install -q -r web-app\requirements-web.txt pyinstaller

echo [2/4] Building .exe...
%VENV_PYTHON% -m PyInstaller ^
  --onedir ^
  --name "%APP_NAME%" ^
  --add-data "web-app\static;static" ^
  --distpath "%DIST%" ^
  --workpath "%DIST%\build" ^
  --specpath "%DIST%" ^
  --noconfirm ^
  --clean ^
  web-app\launcher.py

echo [3/4] Bundling tools...
mkdir "%DIST%\%APP_NAME%\bin" 2>nul

if exist "bin\yt-dlp.exe" (
  copy "bin\yt-dlp.exe" "%DIST%\%APP_NAME%\bin\" >nul
)

REM Find FFmpeg
where ffmpeg >nul 2>&1
if !errorlevel! equ 0 (
  for /f "delims=" %%i in ('where ffmpeg') do copy "%%i" "%DIST%\%APP_NAME%\bin\" >nul
)
where ffprobe >nul 2>&1
if !errorlevel! equ 0 (
  for /f "delims=" %%i in ('where ffprobe') do copy "%%i" "%DIST%\%APP_NAME%\bin\" >nul
)

REM Create launcher batch
echo @echo off > "%DIST%\%APP_NAME%\SplitTracks.bat"
echo start "" "%APP_NAME%.exe" >> "%DIST%\%APP_NAME%\SplitTracks.bat"

echo [4/4] Creating portable zip...
if exist "%DIST%\SplitTracks-windows.zip" del "%DIST%\SplitTracks-windows.zip"
powershell -command "Compress-Archive -Path '%DIST%\%APP_NAME%' -DestinationPath '%DIST%\SplitTracks-windows.zip'" 2>nul
if exist "%DIST%\SplitTracks-windows.zip" (
  echo ZIP created: %DIST%\SplitTracks-windows.zip
) else (
  echo ZIP creation failed, but exe is ready at: %DIST%\%APP_NAME%
)

echo.
echo === Done! ===
echo Folder: %DIST%\%APP_NAME%
if exist "%DIST%\SplitTracks-windows.zip" echo ZIP: %DIST%\SplitTracks-windows.zip
pause
