@echo off
REM Build Split Tracks for Windows — ZIP portable
setlocal enabledelayedexpansion
cd /d "%~dp0\.."

set APP_NAME=SplitTracks
set VENV_PYTHON=.venv\Scripts\python.exe
set DIST=dist\%APP_NAME%-windows
set BUNDLE=%DIST%\%APP_NAME%

echo === Building Split Tracks for Windows ===

echo [1/3] Installing dependencies...
%VENV_PYTHON% -m pip install -q -r requirements-web.txt pyinstaller

echo [2/3] Building .exe...
%VENV_PYTHON% build\build.py

echo [3/4] Bundling FFmpeg...
mkdir "%BUNDLE%\bin" 2>nul

if exist "bin\yt-dlp.exe" (
  copy "bin\yt-dlp.exe" "%BUNDLE%\bin\" >nul
)

where ffmpeg >nul 2>&1
if !errorlevel! equ 0 (
  for /f "delims=" %%i in ('where ffmpeg') do copy "%%i" "%BUNDLE%\bin\" >nul
)
where ffprobe >nul 2>&1
if !errorlevel! equ 0 (
  for /f "delims=" %%i in ('where ffprobe') do copy "%%i" "%BUNDLE%\bin\" >nul
)

REM Create launcher VBS (no console window)
echo CreateObject("Wscript.Shell").Run "%APP_NAME%.exe", 0, False > "%BUNDLE%\SplitTracks.vbs"

echo [4/4] Creating portable ZIP...
if exist "%DIST%\SplitTracks-windows.zip" del "%DIST%\SplitTracks-windows.zip"
powershell -command "Compress-Archive -Path '%BUNDLE%' -DestinationPath '%DIST%\SplitTracks-windows.zip'" 2>nul
if exist "%DIST%\SplitTracks-windows.zip" (
  echo ZIP: %DIST%\SplitTracks-windows.zip
) else (
  echo ZIP failed, folder ready: %BUNDLE%
)

echo === Done ===
