# Split Tracks · guía de desarrollo

## Entorno

Ubuntu 24.04.4 LTS, Python del sistema para GTK4 y `.venv` para el motor ML. Dependencias del sistema:

```bash
sudo apt install python3 python3-venv python3-gi gir1.2-gtk-4.0 gir1.2-gstreamer-1.0 ffmpeg gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad
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
python3 -m py_compile app.py analysis.py engine.py player.py harmony.py
./.venv/bin/python -m unittest discover -s tests -v
git diff --check
```

Para validar CSS GTK cuando hay backend disponible:

```bash
GDK_BACKEND=headless ./.venv/bin/python - <<'PY'
from pathlib import Path
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk
provider = Gtk.CssProvider()
provider.load_from_path(str(Path("style.css").resolve()))
print("CSS válido")
PY
```

El warning de GDK sobre backend headless puede aparecer en este entorno aunque el proveedor CSS cargue correctamente.

## Tests actuales

- `tests/test_analysis.py`: metadata, espectro, acordes legados y estabilización.
- `tests/test_harmony.py`: cache, URLs españolas, metadatos, secciones legacy, traducciones y transposición.

Los tests no deben depender de una consulta de red real. Para probar scraping, usa HTML/fixtures controlados; una comprobación live de Cifra Club es manual y puede fallar por cambios del sitio.

## Flujo Git

- Trabaja en una rama descriptiva desde `master`.
- Revisa `git status` antes de editar y conserva cambios ajenos.
- Commits pequeños, con mensaje claro y sin incluir `.venv`, cachés, audio ni secretos.
- No hagas push ni abras PR sin petición explícita.
- No uses `git reset --hard`, `git checkout --` ni borrados amplios para resolver conflictos.
- Al fusionar, verifica que el árbol queda limpio y repite tests en la rama destino.

## Puntos delicados

- GTK solo se toca desde el hilo principal; los workers devuelven callbacks con `GLib.idle_add`.
- Toda operación de FFmpeg/Demucs/yt-dlp larga debe tener cancelación y limpieza de temporales.
- No uses `subprocess.run()` sin cancelación en una ruta que pueda ejecutarse mientras la ventana está abierta.
- Cualquier nueva fuente de acordes debe devolver `ChordCandidate`/`ChordChart`, no contaminar `app.py` con HTML.
- Si cambias el modelo, formato interno o pipeline de audio, actualiza README, `PROVENANCE.json` y tests afectados.

## Desarrollo web (rama `feature/cross-platform`)

### Arranque rápido

```bash
cd web-app && ../.venv/bin/python server.py
# → http://localhost:8745
```

### Validación

```bash
python3 -m py_compile web-app/server.py web-app/launcher.py
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
# Genérico
.venv/bin/python web-app/build/build.py

# macOS (.app + DMG)
./web-app/build/build-macos.sh

# Windows (.exe + ZIP)
web-app\build\build-windows.bat
```

### Estado del server

Jobs en memoria: `_jobs` dict. Reiniciar = perder jobs. Archivos en `~/Split Tracks/`.
