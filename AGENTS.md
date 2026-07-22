# Split Tracks · instrucciones para agentes

Antes de cambiar código, lee `docs/PROJECT_CONTEXT.md` y `docs/DEVELOPMENT.md`.

## Reglas esenciales

- Aplicación GTK4 exclusiva para Ubuntu/Linux; no migres a web, macOS ni Windows salvo petición explícita.
- Es una herramienta personal sin cuentas, premium, paywall, ventas ni arquitectura de biblioteca.
- Mantén la separación local con `htdemucs_6s` en CPU, los WAV internos y la exportación MP3 bajo demanda.
- No sustituyas el cifrado humano por análisis de acordes de audio: Cifra Club es la fuente canónica actual.
- Conserva la transposición en vivo: cambia preescucha, tonalidad, acordes y grados sin guardar copias intermedias.
- No hagas `git push` salvo petición explícita. Antes de commitear ejecuta sintaxis, tests y `git diff --check`.
- No borres ni resetees cambios del usuario. No uses `git reset --hard` ni `git checkout --` sin autorización.
- Ramas: trabaja **siempre** en ramas de feature desde `main`, nunca directamente en `main`.
- Pregunta antes de mergear a `main`. No hagas merge sin confirmación del usuario.
- Flujo por tarea: feature branch → cambios → validar → commit → preguntar merge → (si aprueba) merge a main y push.
- No muestres código en las respuestas a menos que el usuario lo pida explícitamente. Sé conciso.

## Ramas del proyecto

- **`main`**: versión GTK4 para Ubuntu/Linux (app.py + player.py GStreamer + interfaz nativa)
- **`feature/cross-platform`**: versión web multiplataforma (FastAPI + HTML/CSS/JS + Web Audio API)

Las dos ramas comparten el motor: `engine.py`, `harmony.py`, `analysis.py`. La rama `feature/cross-platform` añade `web-app/` con su propio servidor, frontend y builds.

## Mapa rápido

### Compartido (ambas ramas)
- `engine.py`: ffprobe/FFmpeg, yt-dlp, Demucs, cancelación, mezcla y MP3.
- `harmony.py`: modelo de cifrado, scraping/cache de Cifra Club, secciones y transposición.
- `analysis.py`: BPM, tonalidad estimada, loudness y análisis legado de audio.
- `tests/`: tests unitarios de análisis y armonía.

### Rama `main` (GTK Linux)
- `app.py`: ventana GTK, flujo de carga/YouTube, análisis, cifrado humano, tono, mixer y exportación.
- `player.py`: mixer GStreamer sincronizado y cambio de pitch en vivo.
- `style.css`: tema dark/solarized y layout GTK.

### Rama `feature/cross-platform` (Web)
- `web-app/server.py`: servidor FastAPI, 12 endpoints REST, jobs asíncronos.
- `web-app/launcher.py`: lanzador desktop que abre el navegador.
- `web-app/static/index.html`: layout sidebar + workspace + footer.
- `web-app/static/css/style.css`: tema dark/solarized para la web.
- `web-app/static/js/app.js`: UI completa (chips, harmony, pitch, mixer, export).
- `web-app/static/js/player.js`: mixer Web Audio API con pitch (playbackRate).
- `web-app/static/js/api.js`: comunicación con el backend.
- `web-app/build/`: scripts PyInstaller para Windows y macOS.
- `web-app/run.sh` / `run.bat`: scripts de arranque rápido.

## Estado actual (feature/cross-platform)
- Server: `cd web-app && ../.venv/bin/python server.py` → http://localhost:8745
- Funcionalidades completas: carga YouTube/archivo, Demucs, mixer, mute/solo/vol, pitch, acordes Cifra Club, grados, métricas, export MP3
- Pitch del audio: usa playbackRate (cambia velocidad y tono juntos)
- Jobs en memoria: se pierden al reiniciar el servidor
- Sin waveform real (placeholder visual)
- Builds Windows/Mac creados pero no testeados en máquinas reales

## Pendiente conocido
- Visualizador de espectro por track (AnalyserNode + canvas)
- Persistencia de jobs en disco
- Waveform real
- Probar builds en Windows/macOS reales

Lee la documentación enlazada antes de proponer una arquitectura nueva.
