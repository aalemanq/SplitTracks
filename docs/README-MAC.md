# Split Tracks para macOS

## Requisitos previos

1. **Python 3.12+**: ya viene instalado en macOS. Si no:
   ```bash
   brew install python@3.12
   ```

2. **FFmpeg**:
   ```bash
   brew install ffmpeg
   ```

## Ejecutar

```bash
cd SplitTracks
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-web.txt
python server.py
```

Abre `http://localhost:8745` en tu navegador.

## Crear aplicación (.app)

```bash
.venv/bin/python build/build.py
```

La aplicación se genera en `dist/SplitTracks-darwin/`

## Crear .app + DMG

```bash
brew install create-dmg
chmod +x build/build-macos.sh
./build/build-macos.sh
```

El DMG se genera en `dist/SplitTracks-macos/SplitTracks-macOS.dmg`
