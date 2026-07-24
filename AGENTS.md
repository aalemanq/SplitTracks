# Split Tracks · instrucciones para agentes

Antes de cambiar código, lee `docs/PROJECT_CONTEXT.md`, `docs/DEVELOPMENT.md` y `docs/CONSOLIDATION_PLAN.md`.

## Reglas esenciales

- Aplicación web multiplataforma (FastAPI + HTML/CSS/JS + Web Audio API). Ejecutable standalone en Windows/macOS/Linux.
- Es una herramienta personal sin cuentas, premium, paywall, ventas ni arquitectura de biblioteca.
- Mantén la separación local con `htdemucs_6s` en CPU, los WAV internos y la exportación MP3 bajo demanda.
- No sustituyas el cifrado humano por análisis de acordes de audio: Cifra Club es la fuente canónica actual.
- Conserva la transposición en vivo: cambia preescucha, tonalidad, acordes y grados sin guardar copias intermedias.
- No hagas `git push` salvo petición explícita. Antes de commitear ejecuta sintaxis, tests y `git diff --check`.
- No borres ni resetees cambios del usuario. No uses `git reset --hard` ni `git checkout --` sin autorización.
- Ramas: trabaja **siempre** en ramas de feature, nunca directamente en `main`.
- Pregunta antes de mergear. No hagas merge sin confirmación del usuario.
- Flujo por tarea: feature branch → validar plan con usuario → cambios → validar → commit → preguntar merge → (si aprueba) merge y push.
- Antes de escribir código, confirma el diseño con el usuario. No implementes sin clarificar requisitos.
- Para nuevas funcionalidades: escribe los tests primero (TDD), luego el código que los hace pasar.
- No muestres código en las respuestas a menos que el usuario lo pida explícitamente. Sé conciso.

## Ramas del proyecto

- **`main`**: versión web multiplataforma canónica (FastAPI + HTML/CSS/JS + Web Audio API). Releases para Windows, macOS y Linux.
- **`feature/*`**: ramas de desarrollo para nuevas funcionalidades. Se mergean a `main` tras validar.

Las ramas `feature/cross-platform` y `feature/windows-port` han sido consolidadas en `main`. La versión GTK4 (`app.py`, `player.py`, `style.css`) queda archivada.

## Mapa rápido

### Motor compartido
- `engine.py`: ffprobe/FFmpeg, yt-dlp, Demucs, cancelación, mezcla y MP3. Soporte Windows/Linux/macOS.
- `harmony.py`: modelo de cifrado, scraping/cache de Cifra Club, secciones y transposición.
- `analysis.py`: BPM, tonalidad estimada, loudness y análisis legado de audio.
- `tests/`: tests unitarios de análisis y armonía.

### Servidor y frontend (raíz)
- `server.py`: servidor FastAPI, 12 endpoints REST, jobs asíncronos.
- `launcher.py`: lanzador desktop que abre el navegador automáticamente.
- `static/index.html`: layout sidebar + workspace + transport bar.
- `static/css/style.css`: tema dark/solarized para la web.
- `static/js/app.js`: UI completa (chips, harmony, pitch, mixer, export).
- `static/js/player.js`: mixer Web Audio API con pitch (SoundTouchJS + playbackRate).
- `static/js/api.js`: comunicación con el backend.
- `static/js/lib/soundtouch.js`: librería SoundTouchJS para pitch shifting real.

### Builds y empaquetado
- `build/build.py`: script genérico de PyInstaller.
- `build/build-linux.sh`: build + tar.gz portable para Linux.
- `build/build-windows.bat`: build + ZIP portable para Windows.
- `build/build-macos.sh`: build .app + DMG para macOS.
- `run.sh` / `run.bat`: scripts de arranque rápido para desarrollo.
- `setup-model.sh`: instalación de PyTorch CPU + Demucs en `.venv`.
- `setup-windows.bat`: instalación del entorno ML en Windows.

## Estado actual

- **Servidor**: `.venv/bin/python server.py` → http://localhost:8745
- **Funcionalidades completas**: carga YouTube/archivo, Demucs, mixer, mute/solo/vol, pitch (SoundTouchJS), acordes Cifra Club, grados, métricas, export MP3
- **Jobs en memoria**: se pierden al reiniciar el servidor
- **Sin waveform real** (placeholder visual)
- **Builds Windows** en desarrollo (testear en máquina real, bundlear FFmpeg/yt-dlp)

## Pendiente conocido

- Visualizador de espectro por track (AnalyserNode + canvas)
- Persistencia de jobs en disco
- Waveform real
- CI/CD con GitHub Actions para releases automáticos
- Probar builds en Windows/macOS reales
- Build Linux (AppImage o tar.gz portable)
- **Windows**: Bundlear FFmpeg/yt-dlp, probar Demucs desde el .exe, optimizar tamaño

## Principios de calidad

- **Planificar antes de codificar**: valida el diseño con el usuario. No asumas requisitos.
- **TDD para features nuevas**: escribe el test primero, observa que falle, implementa, verifica que pase.
- **Commits atómicos**: un cambio lógico por commit. Mensajes claros en español.
- **Sin archivos monstruo**: si un archivo supera ~500 líneas, considera partirlo.
- **Revisar antes de merge**: ejecuta `py_compile`, `unittest`, `git diff --check`.

Lee la documentación enlazada antes de proponer una arquitectura nueva.
