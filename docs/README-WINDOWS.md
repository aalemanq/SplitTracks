# Split Tracks para Windows

## Requisitos previos

1. **Python 3.12+**: descarga desde [python.org](https://www.python.org/downloads/)
   - Durante la instalación, marca ✅ "Add Python to PATH"

2. **FFmpeg**: descarga desde [ffmpeg.org](https://ffmpeg.org/download.html)
   - O instalación rápida con winget: `winget install Gyan.FFmpeg`

## Ejecutar

```cmd
cd SplitTracks
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-web.txt
python server.py
```

Abre `http://localhost:8745` en tu navegador.

## Crear ejecutable (.exe)

```cmd
.venv\Scripts\python build\build.py
```

El ejecutable se genera en `dist\SplitTracks-win32\`

## Crear ejecutable + ZIP portable

```cmd
build\build-windows.bat
```

El ZIP se genera en `dist\SplitTracks-windows\SplitTracks-windows.zip`
