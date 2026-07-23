# Split Tracks · Plan para Windows

## Objetivo

El usuario final recibe un archivo ZIP, lo descomprime, ejecuta `SplitTracks.bat` (o `.exe`) y la app se abre automáticamente en el navegador. No necesita instalar Python, FFmpeg ni ninguna dependencia.

## Estado actual (feature/cross-platform)

La rama `feature/cross-platform` ya tiene una versión web funcional:
- **Backend**: FastAPI + Uvicorn (`web-app/server.py`)
- **Frontend**: HTML/CSS/JS con Web Audio API (`web-app/static/`)
- **Motor compartido**: `engine.py`, `harmony.py`, `analysis.py`
- **Builds**: Scripts de PyInstaller en `web-app/build/`
- **Launcher**: `web-app/launcher.py` abre el navegador automáticamente

### Funcionalidades completas
- Carga de YouTube y archivos locales
- Separación Demucs (6 stems en CPU)
- Mixer con mute/solo/volumen
- Pitch en vivo (playbackRate)
- Acordes Cifra Club con transposición
- Métricas de análisis (BPM, tonalidad, LUFS)
- Exportación MP3

## Arquitectura para Windows

```
SplitTracks-windows/
├── SplitTracks.exe          # PyInstaller bundle
├── SplitTracks.bat          # Launcher alternativo
├── bin/
│   ├── ffmpeg.exe           # Bundled
│   ├── ffprobe.exe          # Bundled
│   └── yt-dlp.exe           # Bundled
├── .venv/                   # Python virtualenv (Demucs, PyTorch)
├── _internal/               # PyInstaller runtime
└── static/                  # Frontend (embebido en .exe)
```

## Plan de implementación

### Fase 1: Preparar entorno de build en Windows

**Objetivo**: Tener todas las herramientas necesarias para compilar.

1. **Python 3.12+** instalado con "Add to PATH"
2. **FFmpeg** descargado (binarios estáticos)
3. **yt-dlp.exe** descargado (binario standalone)
4. **Git** para clonar el repo

**Comandos**:
```cmd
winget install Python.Python.3.12
winget install Gyan.FFmpeg
winget install Git.Git
```

### Fase 2: Preparar el motor ML (Demucs)

**Objetivo**: Instalar PyTorch CPU y Demucs en `.venv`.

```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-cpu.txt
pip install -r web-app/requirements-web.txt
```

**Verificación**:
```cmd
.venv\Scripts\python -c "import torch, demucs; print('OK')"
```

### Fase 3: Probar el servidor en desarrollo

**Objetivo**: Verificar que todo funciona antes de compilar.

```cmd
.venv\Scripts\python web-app/server.py
```

Abrir `http://localhost:8745` y probar:
- [ ] Cargar archivo local
- [ ] Separar con Demucs
- [ ] Reproducir/mixer
- [ ] Cambiar pitch
- [ ] Buscar acordes Cifra Club
- [ ] Exportar MP3

### Fase 4: Compilar con PyInstaller

**Objetivo**: Generar el ejecutable standalone.

```cmd
.venv\Scripts\python web-app/build/build.py
```

El resultado queda en `dist/SplitTracks-win32/`.

### Fase 5: Bundle final

**Objetivo**: Crear el ZIP distribuible.

```cmd
web-app\build\build-windows.bat
```

Genera:
- `dist/SplitTracks-windows/SplitTracks/` → carpeta con todo
- `dist/SplitTracks-windows/SplitTracks-windows.zip` → ZIP portable

### Fase 6: Empaquetar binarios externos

**Objetivo**: Incluir FFmpeg y yt-dlp en el bundle.

El script `build-windows.bat` ya busca FFmpeg en PATH y lo copia a `bin/`. Para yt-dlp:
- Descargar `yt-dlp.exe` desde https://github.com/yt-dlp/yt-dlp/releases
- Colocar en `bin/yt-dlp.exe` antes de compilar

## Problemas conocidos y soluciones

### 1. PyInstaller no incluye Demucs correctamente

**Problema**: Demucs usa entry points y archivos de modelo que PyInstaller no detecta.

**Solución**: 
- Asegurar que `.venv/` se copia completa con el bundle
- El script `build.py` ya hace `shutil.copytree(.venv, bundle/.venv)`
- El launcher debe usar `.venv/Scripts/python` para ejecutar Demucs

### 2. FFmpeg no se encuentra en Windows

**Problema**: `engine.py` llama a `ffmpeg` y `ffprobe` directamente.

**Solución**:
- Bundlear `ffmpeg.exe` y `ffprobe.exe` en `bin/`
- Modificar `engine.py` para buscar en `bin/` antes que en PATH
- Usar variable de entorno `SPLITTRACKS_FFMPEG_PATH` como fallback

### 3. yt-dlp no se encuentra

**Problema**: `engine.py` busca `bin/yt-dlp` (Linux) o `yt-dlp.exe` (Windows).

**Solución**:
- Bundlear `yt-dlp.exe` en `bin/`
- Modificar `engine.py` para usar `bin/yt-dlp.exe` en Windows

### 4. Pitch con playbackRate cambia velocidad

**Problema**: Web Audio API `playbackRate` cambia tono Y velocidad juntos.

**Solución actual**: Se acepta como comportamiento (no es pitch real).

**Solución futura**: Integrar SoundTouch.js o usar `pitch` de GStreamer via WASM.

### 5. PyTorch es muy grande (~2GB)

**Problema**: El bundle final pesa mucho por PyTorch CPU.

**Solución**:
- Usar `--onedir` (no `--onefile`) para evitar compresión excesiva
- Aceptar que el ZIP pesará ~500MB-1GB comprimido
- Considerar modelo más ligero en el futuro (htdemucs_ft con menos shifts)

## Modificaciones necesarias en el código

### engine.py

```python
# Detectar plataforma
import platform
IS_WINDOWS = platform.system() == "Windows"

# Buscar FFmpeg en bin/ primero
def _find_ffmpeg():
    bin_dir = Path(__file__).parent / "bin"
    if IS_WINDOWS:
        ffmpeg = bin_dir / "ffmpeg.exe"
        ffprobe = bin_dir / "ffprobe.exe"
    else:
        ffmpeg = bin_dir / "ffmpeg"
        ffprobe = bin_dir / "ffprobe"
    
    if ffmpeg.exists():
        return str(ffmpeg), str(ffprobe)
    return "ffmpeg", "ffprobe"

FFMPEG, FFPROBE = _find_ffmpeg()
```

### engine.py (yt-dlp)

```python
# Buscar yt-dlp
def _find_ytdlp():
    bin_dir = Path(__file__).parent / "bin"
    if IS_WINDOWS:
        ytdlp = bin_dir / "yt-dlp.exe"
    else:
        ytdlp = bin_dir / "yt-dlp"
    
    if ytdlp.exists():
        return str(ytdlp)
    return "yt-dlp"

YTDLP = _find_ytdlp()
```

### launcher.py

```python
# Asegurar que el servidor usa el Python del .venv para Demucs
import subprocess
import sys

def run_demucs_with_venv(args):
    venv_python = Path(__file__).parent / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        subprocess.run([str(venv_python), "-m", "demucs.separate"] + args)
    else:
        subprocess.run([sys.executable, "-m", "demucs.separate"] + args)
```

## Checklist de distribución

- [ ] Python 3.12 instalado
- [ ] FFmpeg binarios descargados
- [ ] yt-dlp.exe descargado
- [ ] `.venv` creado con Demucs y PyTorch
- [ ] Servidor probado en desarrollo
- [ ] PyInstaller ejecutado sin errores
- [ ] Binarios copiados a `bin/`
- [ ] ZIP creado y probado en máquina limpia
- [ ] `SplitTracks.bat` abre el navegador correctamente
- [ ] Demucs funciona desde el bundle
- [ ] YouTube download funciona
- [ ] Export MP3 funciona

## Experiencia del usuario final

1. Recibe `SplitTracks-windows.zip`
2. Descomprime en cualquier carpeta (ej: `C:\SplitTracks\`)
3. Ejecuta `SplitTracks.bat` (doble clic)
4. Se abre el navegador en `http://127.0.0.1:8745`
5. Usa la app normalmente

**No necesita**:
- Instalar Python
- Instalar FFmpeg
- Configurar variables de entorno
- Usar línea de comandos

## Tamaño estimado del bundle

- PyTorch CPU: ~800MB
- Demucs + deps: ~200MB
- FFmpeg: ~150MB
- yt-dlp: ~80MB
- Frontend + server: ~10MB
- **Total sin comprimir**: ~1.2GB
- **ZIP comprimido**: ~400-600MB

## Futuras optimizaciones

1. **Modelo más ligero**: Usar `htdemucs` (4 stems) si no se necesitan piano/guitarra
2. **ONNX Runtime**: Reemplazar PyTorch por ONNX para reducir tamaño
3. **WebAssembly**: Portar Demucs a WASM para eliminar dependencia de Python
4. **Descarga bajo demanda**: Descargar modelo solo la primera vez que se usa
5. **Compresión UPX**: Usar UPX para comprimir el .exe final
