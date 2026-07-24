@echo off
REM Split Tracks — Windows setup
REM Descarga las herramientas necesarias y crea el entorno virtual.

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ================================================
echo  Split Tracks — Instalacion para Windows
echo ================================================
echo.

REM ── 1. Verificar Python ─────────────────────────
echo [1/4] Verificando Python...
where python >nul 2>&1
if !errorlevel! neq 0 (
    echo Python no encontrado.
    echo Instalalo desde https://www.python.org/downloads/
    echo Asegurate de marcar "Add Python to PATH" durante la instalacion.
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo   Python %%v

REM ── 2. Crear venv ───────────────────────────────
echo.
echo [2/4] Creando entorno virtual (portable)...
if not exist ".venv\Scripts\python.exe" (
    python -m venv --copies .venv
    echo   .venv portable creado
) else (
    echo   .venv ya existe
)

REM ── 3. Instalar dependencias ────────────────────
echo.
echo [3/4] Instalando dependencias...
call .venv\Scripts\activate.bat

pip install -q --no-cache-dir --index-url https://download.pytorch.org/whl/cpu ^
  "torch==2.11.0+cpu" "torchaudio==2.11.0+cpu"
if !errorlevel! neq 0 (
    echo ERROR: Fallo al instalar PyTorch. Comprueba la conexion.
    pause
    exit /b 1
)

pip install -q --no-cache-dir ^
  "demucs==4.1.0" "numpy>=2,<3" "scipy>=1.13,<2" ^
  "requests>=2.31,<3" "beautifulsoup4>=4.12,<5" ^
  "fastapi>=0.100.0" "uvicorn>=0.23.0" ^
  "python-multipart>=0.0.6" "aiofiles>=23.0"
if !errorlevel! neq 0 (
    echo ERROR: Fallo al instalar dependencias web.
    pause
    exit /b 1
)
echo   Dependencias instaladas

REM ── 4. Descargar herramientas ───────────────────
echo.
echo [4/4] Descargando herramientas externas...
if not exist "bin" mkdir bin

REM yt-dlp (Windows binary)
if not exist "bin\yt-dlp.exe" (
    echo   Descargando yt-dlp.exe...
    powershell -Command "Invoke-WebRequest -Uri 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe' -OutFile 'bin\yt-dlp.exe'" 2>nul
    if !errorlevel! neq 0 (
        echo   AVISO: No se pudo descargar yt-dlp.exe. Descargalo manualmente de:
        echo   https://github.com/yt-dlp/yt-dlp/releases
    ) else (
        echo   yt-dlp.exe listo
    )
) else (
    echo   yt-dlp.exe ya existe
)

REM FFmpeg
where ffmpeg >nul 2>&1
if !errorlevel! neq 0 (
    echo.
    echo   [!] FFmpeg no esta en PATH.
    echo   Instalalo con:  winget install Gyan.FFmpeg
    echo   O descargalo de: https://ffmpeg.org/download.html
    echo   Y copia ffmpeg.exe y ffprobe.exe a la carpeta bin\
) else (
    for /f "delims=" %%i in ('where ffmpeg') do (
        if not exist "bin\ffmpeg.exe" copy "%%i" "bin\ffmpeg.exe" >nul 2>&1
    )
    for /f "delims=" %%i in ('where ffprobe') do (
        if not exist "bin\ffprobe.exe" copy "%%i" "bin\ffprobe.exe" >nul 2>&1
    )
    echo   FFmpeg encontrado en PATH
)

REM ── Verificar ───────────────────────────────────
echo.
echo ================================================
echo  Verificando instalacion...
echo ================================================
.venv\Scripts\python -c "import torch, demucs; print('  PyTorch + Demucs: OK')" 2>nul || echo   ERROR: PyTorch/Demucs no se cargaron
if exist "bin\yt-dlp.exe" (echo   yt-dlp.exe: OK) else (echo   yt-dlp.exe: NO ENCONTRADO)
if exist "bin\ffmpeg.exe" (echo   ffmpeg.exe: OK) else (echo   ffmpeg.exe: NO ENCONTRADO - Necesario)

echo.
echo ================================================
echo  Instalacion completada.
echo.
echo  Para ejecutar Split Tracks:
echo    run.bat
echo.
echo  Para compilar el ejecutable:
echo    build\build-windows.bat
echo ================================================
pause
