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

## Estructura

```
web-app/
├── server.py          # FastAPI backend
├── launcher.py        # Desktop launcher (abre navegador)
├── run.sh / run.bat   # Scripts de arranque
├── static/
│   ├── index.html
│   ├── css/style.css
│   └── js/
│       ├── api.js     # Comunicación API
│       ├── player.js  # Web Audio mixer
│       └── app.js     # UI y flujo
└── build/
    ├── build.py       # PyInstaller unificado
    ├── build-macos.sh
    └── build-windows.bat
```

## API

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | /api/jobs | Crear trabajo (YouTube o archivo) |
| GET | /api/jobs/{id} | Estado del trabajo |
| GET | /api/jobs/{id}/stems/{file} | Servir stem WAV |
| POST | /api/jobs/{id}/cancel | Cancelar trabajo |
| POST | /api/jobs/{id}/mix | Exportar mezcla MP3 |
| GET | /api/search | Buscar acordes |
| GET | /health | Estado del servidor |
