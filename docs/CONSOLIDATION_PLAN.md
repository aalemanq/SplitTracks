# Split Tracks · Plan de consolidación multiplataforma

## Objetivo

Una sola codebase que produce releases para Windows, macOS y Linux. Un cambio en el motor o la UI se refleja automáticamente en los 3 sistemas operativos.

## Decisión tomada

La versión web (FastAPI + HTML/CSS/JS + Web Audio API) es la **versión canónica única**. La versión GTK4 se archiva.

## Fases

### Fase 1 — Unificar ramas en `main`

1. Mergear `feature/cross-platform` → `main`
2. Mergear `feature/windows-port` → `main`
3. Aplanar estructura: mover `web-app/server.py`, `launcher.py`, `static/`, `build/` a la raíz
4. Eliminar archivos obsoletos GTK: `app.py`, `player.py`, `style.css`
5. Actualizar imports, rutas relativas y scripts
6. Validar: compilación, tests, lint

### Fase 2 — Builds por plataforma

Crear/refinar scripts de empaquetado:

- `build/build-linux.sh` → AppImage o tar.gz portable
- `build/build-macos.sh` → .app + DMG
- `build/build-windows.bat` → .exe + ZIP portable

Cada build incluye:
- El ejecutable PyInstaller (servidor + frontend embebido)
- `.venv/` con PyTorch CPU + Demucs
- `bin/` con ffmpeg, ffprobe, yt-dlp

### Fase 3 — CI/CD con GitHub Actions

Al pushear un tag semántico (`v1.0.0`):

1. Workflow construye los 3 paquetes en paralelo (ubuntu-latest, macos-latest, windows-latest)
2. Publica los artefactos como GitHub Release
3. El usuario descarga el ZIP/DMG/AppImage según su SO

Estructura del workflow: `.github/workflows/release.yml`

## Estructura final del repo

```
splitmusic/
├── engine.py              # Motor compartido (Demucs, FFmpeg, yt-dlp)
├── harmony.py             # Armonía, scraping Cifra Club, transposición
├── analysis.py            # Análisis de audio (BPM, tonalidad, LUFS)
├── server.py              # Servidor FastAPI (único backend)
├── launcher.py            # Abre navegador al iniciar el servidor
├── static/                # Frontend HTML/CSS/JS
│   ├── index.html
│   ├── css/
│   │   └── style.css
│   └── js/
│       ├── app.js
│       ├── player.js
│       └── api.js
├── build/                 # Scripts de empaquetado por SO
│   ├── build.py           # PyInstaller genérico
│   ├── build-linux.sh
│   ├── build-macos.sh
│   └── build-windows.bat
├── bin/                   # Herramientas externas bundleadas
│   ├── ffmpeg / ffmpeg.exe
│   ├── ffprobe / ffprobe.exe
│   └── yt-dlp / yt-dlp.exe
├── tests/
│   ├── test_analysis.py
│   └── test_harmony.py
├── docs/
│   ├── PROJECT_CONTEXT.md
│   ├── DEVELOPMENT.md
│   ├── WINDOWS_PLAN.md
│   └── CONSOLIDATION_PLAN.md
├── assets/
│   └── icons/
├── models/                # Modelos Demucs cacheados
├── requirements-cpu.txt   # Dependencias ML (PyTorch CPU, Demucs)
├── requirements-web.txt   # Dependencias web (FastAPI, uvicorn)
├── setup-model.sh         # Instalación del entorno ML
├── setup-windows.bat      # Instalación del entorno ML en Windows
├── run.sh                 # Script de arranque rápido
├── split-tracks.desktop   # Entrada de escritorio Linux
├── .github/
│   └── workflows/
│       └── release.yml    # CI/CD para releases
├── .gitignore
├── AGENTS.md
├── README.md
├── PROVENANCE.json
└── THIRD_PARTY_NOTICES.txt
```

## Archivos eliminados / archivados

- `app.py` — UI GTK4 (solo Linux, reemplazada por web)
- `player.py` — Mixer GStreamer (solo Linux, reemplazado por Web Audio API)
- `style.css` — Tema GTK (reemplazado por `static/css/style.css`)

## Principios

- **Código una vez**: cambios en `engine.py`, `server.py` o `static/` afectan a los 3 SO
- **Builds separados**: cada SO tiene su script de empaquetado, comparten el mismo código fuente
- **Sin regresiones**: los tests se ejecutan antes de cada merge y en CI
- **Releases automáticos**: un tag = releases para los 3 SO generados por GitHub Actions
