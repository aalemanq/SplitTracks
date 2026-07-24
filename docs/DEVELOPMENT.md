# Split Tracks · guía de desarrollo

## Entorno

Ubuntu 24.04.4 LTS, `.venv` para el motor ML. Dependencias del sistema:

```bash
sudo apt install python3 python3-venv ffmpeg
```

Preparación ML:

```bash
./setup-model.sh
./run.sh
```

`setup-model.sh` instala PyTorch CPU, Demucs y dependencias de armonía en `.venv`. El modelo se descarga bajo demanda. No ejecutes la descarga del modelo durante tests unitarios.

## Validación antes de commit

Desde la raíz:

```bash
python3 -m py_compile analysis.py engine.py harmony.py server.py launcher.py
.venv/bin/python -m unittest discover -s tests -v
git diff --check
```

### Checklist pre-merge

- [ ] `py_compile` sin errores en todos los `.py` modificados
- [ ] `unittest discover` pasa todos los tests
- [ ] `git diff --check` sin trailing whitespace
- [ ] Ningún archivo nuevo supera ~500 líneas; si lo hace, considerar partirlo
- [ ] Los cambios de API tienen tests
- [ ] Las features nuevas siguen TDD (test primero, código después)
- [ ] El build de Linux produce un tar.gz funcional (`./build/build-linux.sh`)

### TDD para features nuevas

1. Escribe un test que falle (rojo)
2. Implementa el código mínimo para que pase (verde)
3. Refactoriza si es necesario, manteniendo tests en verde
4. Confirma que `unittest discover` sigue pasando

Ejemplo:
```bash
# 1. Escribir test en tests/test_nueva_feature.py
# 2. Verificar que falla
.venv/bin/python -m unittest tests.test_nueva_feature
# 3. Implementar feature
# 4. Verificar que pasa
.venv/bin/python -m unittest discover -s tests -v
```

## Tests actuales

- `tests/test_analysis.py`: metadata, espectro, acordes legados y estabilización.
- `tests/test_harmony.py`: cache, URLs españolas, metadatos, secciones legacy, traducciones y transposición.

Los tests no deben depender de una consulta de red real. Para probar scraping, usa HTML/fixtures controlados; una comprobación live de Cifra Club es manual y puede fallar por cambios del sitio.

## Flujo Git

- Trabaja en una rama descriptiva desde `main`.
- Revisa `git status` antes de editar y conserva cambios ajenos.
- Commits pequeños, con mensaje claro y sin incluir `.venv`, cachés, audio ni secretos.
- No hagas push ni abras PR sin petición explícita.
- No uses `git reset --hard`, `git checkout --` ni borrados amplios para resolver conflictos.
- Al fusionar, verifica que el árbol queda limpio y repite tests en la rama destino.

## Puntos delicados

- Toda operación de FFmpeg/Demucs/yt-dlp larga debe tener cancelación y limpieza de temporales.
- No uses `subprocess.run()` sin cancelación en una ruta que pueda ejecutarse mientras el servidor está activo.
- Cualquier nueva fuente de acordes debe devolver `ChordCandidate`/`ChordChart`, no contaminar `server.py` con HTML.
- Si cambias el modelo, formato interno o pipeline de audio, actualiza README, `PROVENANCE.json` y tests afectados.

## Desarrollo web

### Arranque rápido

```bash
.venv/bin/python server.py
# → http://localhost:8745
```

### Validación

```bash
python3 -m py_compile server.py launcher.py
./.venv/bin/python -m unittest discover -s tests -v
```

### Tests manuales

```bash
# Health check
curl -s http://127.0.0.1:8745/health

# Probar con YouTube (canción corta)
curl -s -X POST -F "url=https://www.youtube.com/watch?v=28d_A_NuJ7A" -F 'stems=["vocals"]' http://127.0.0.1:8745/api/jobs

# Buscar acordes
curl -s "http://127.0.0.1:8745/api/chords/search?artist=Adele&title=Someone%20Like%20You"
```

### Builds

```bash
# Genérico (cualquier SO)
.venv/bin/python build/build.py

# Linux (tar.gz portable)
./build/build-linux.sh

# macOS (.app + DMG)
./build/build-macos.sh

# Windows (.exe + ZIP)
build\build-windows.bat
```

### Estado del server

Jobs en memoria: `_jobs` dict. Reiniciar = perder jobs. Archivos en `~/Split Tracks/`.

## Desarrollo Windows

### Requisitos previos

1. **Python 3.12+**: `winget install Python.Python.3.12`
   - Marcar "Add Python to PATH" durante instalación
2. **FFmpeg**: `winget install Gyan.FFmpeg`
3. **Git**: `winget install Git.Git`

### Preparar entorno

```cmd
git clone https://github.com/aalemanq/SplitTracks.git
cd SplitTracks

REM Crear venv con Demucs
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-cpu.txt
pip install -r requirements-web.txt

REM Verificar
python -c "import torch, demucs; print('OK')"
```

### Ejecutar en desarrollo

```cmd
.venv\Scripts\python server.py
REM Abre http://localhost:8745
```

O con el launcher automático:

```cmd
run.bat
```

### Compilar ejecutable

```cmd
REM Build completo con ZIP portable
build\build-windows.bat

REM O solo el .exe
.venv\Scripts\python build\build.py
```

Resultado en `dist/SplitTracks-windows/`.

### Probar el bundle

1. Copiar la carpeta `dist/SplitTracks-windows/SplitTracks/` a otra ubicación
2. Ejecutar `SplitTracks.bat`
3. Verificar que el navegador se abre y la app funciona
4. Probar descarga de YouTube, separación, exportación

### Binarios externos

Antes de compilar, colocar en `bin/`:
- `ffmpeg.exe` y `ffprobe.exe` (de FFmpeg)
- `yt-dlp.exe` (de https://github.com/yt-dlp/yt-dlp/releases)

El script `build-windows.bat` los copia automáticamente al bundle.

### Validación en Windows

```cmd
REM Sintaxis
.venv\Scripts\python -m py_compile engine.py harmony.py analysis.py server.py

REM Tests unitarios
.venv\Scripts\python -m unittest discover -s tests -v

REM Verificar binarios
bin\ffmpeg.exe -version
bin\ffprobe.exe -version
bin\yt-dlp.exe --version
```

### Puntos delicados en Windows

- Las rutas usan `\` en vez de `/`, pero Python las maneja bien con `Path`
- `os.killpg()` no funciona en Windows; usar `process.kill()` directamente
- Los scripts `.sh` no funcionan; usar `.bat` o PowerShell
- El `.venv` debe copiarse completo al bundle (PyTorch no se empaqueta bien con PyInstaller)
- FFmpeg/yt-dlp deben estar en `bin/` o en PATH
