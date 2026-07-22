# Split Tracks — Web App

Versión multiplataforma (macOS / Windows / Linux) con interfaz web.

## Ejecutar

```bash
# Linux / macOS
./web-app/run.sh

# Windows
web-app\run.bat
```

Abre `http://localhost:8745` en el navegador.

## Funcionalidades

- Carga de audio local (MP3, WAV, FLAC) o descarga desde YouTube
- Separación 6 stems con Demucs `htdemucs_6s` en CPU
- Mixer multitrack: volumen, mute, solo por pista
- Volumen maestro, timeline con seek, transport (play/pause/stop)
- Búsqueda manual de acordes en Cifra Club con selección de versiones
- Búsqueda automática desde metadatos de YouTube
- Panel de acordes (4 columnas, secciones, colores)
- Panel de grados de escala
- Transposición en vivo (−/+/Original, −12 a +12 semitonos)
- 12 métricas de análisis: tonalidad, BPM, duración, escala, LUFS, dinámica
- Exportar mezcla MP3 (con mute/solo/volumen aplicados)
- Exportar pistas MP3 activas
- Exportar pista individual MP3
- Tiempo transcurrido durante el procesado
- Atajos de teclado (Espacio = play/pause)
- Estado persistente del mixer (localStorage)
- Tema dark solarized

## Construir distribuciones

### macOS (.app + DMG)
```bash
./web-app/build/build-macos.sh
```
Requiere: `brew install create-dmg`

### Windows (.exe + ZIP)
```cmd
web-app\build\build-windows.bat
```

### Genérico (PyInstaller)
```bash
.venv/bin/python web-app/build/build.py
```

## Estructura

```
web-app/
├── server.py              # FastAPI backend (290 líneas)
├── launcher.py            # Desktop launcher (abre navegador)
├── run.sh / run.bat       # Scripts de arranque
├── requirements-web.txt   # Dependencias Python
├── static/
│   ├── index.html         # Interfaz (sidebar + workspace + footer)
│   ├── css/style.css      # Tema dark solarized
│   └── js/
│       ├── api.js         # Comunicación con API
│       ├── player.js      # Web Audio mixer multitrack
│       └── app.js         # UI completa (stem chips, harmony, pitch, mixer, export)
└── build/
    ├── build.py           # PyInstaller unificado
    ├── build-macos.sh     # macOS .app + DMG
    └── build-windows.bat  # Windows .exe + ZIP
```

## API

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | /api/jobs | Crear trabajo (archivo o URL YouTube) |
| GET | /api/jobs/{id} | Estado del trabajo + métricas + acordes |
| GET | /api/jobs/{id}/stems/{file} | Servir stem WAV |
| GET | /api/jobs/{id}/stems-mp3/{file} | Servir stem MP3 (transcodifica on-demand) |
| POST | /api/jobs/{id}/cancel | Cancelar trabajo |
| POST | /api/jobs/{id}/pitch | Cambiar pitch (semitones) |
| POST | /api/jobs/{id}/export/mix | Exportar mezcla MP3 |
| POST | /api/jobs/{id}/export/stems | Exportar pistas activas MP3 |
| GET | /api/chords/search | Buscar acordes (artista, canción) |
| GET | /api/chords/fetch | Obtener cifrado (URL) |
| POST | /api/chords/transpose | Transponer acordes (URL + semitonos) |
| GET | /health | Estado del servidor |

## Ramas

- `main` — versión GTK4 para Linux
- `feature/cross-platform` — versión web multiplataforma (esta rama)
