# Split Tracks · contexto de proyecto

## Producto y alcance

Split Tracks es una aplicación de escritorio para separación de audio en stems. Versión web multiplataforma: servidor FastAPI + frontend HTML/CSS/JS + Web Audio API. Compatible con Windows, macOS y Linux.

Es de uso personal: no hay cuentas, premium, paywall, ventas, biblioteca gestionada ni sincronización web.

La versión GTK4 para Linux queda archivada (reemplazada por la versión web).

## Flujo funcional

1. El usuario pega una URL de YouTube y pulsa Añadir, o pulsa Subir audio y elige un archivo local.
2. YouTube se descarga con yt-dlp a WAV temporal.
3. `ffprobe` obtiene duración, formato, frecuencia, canales y layout. La entrada debe ser estéreo de dos canales.
4. FFmpeg + NumPy calculan BPM, tonalidad estimada, escala, LUFS, pico, dinámica y confianza. Es análisis auxiliar y best-effort.
5. Si YouTube entrega artista y título, se buscan acordes automáticamente en Cifra Club y se carga la primera versión válida.
6. Demucs (`htdemucs_6s`) separa en CPU los stems seleccionados. `Other` es el complemento del other del modelo más las categorías no seleccionadas.
7. El mixer Web Audio API reproduce los stems sincronizados. Cada pista tiene volumen, Mute, Solo.
8. `−`, `+` y `Original` cambian el pitch y actualizan acordes y grados en vivo. No se crean WAV transpuestos.
9. Exportación de mezcla MP3 320 kbps y pistas individuales, respetando Mute/Solo.

## Arquitectura

### Motor compartido
- `engine.py`: ffprobe/FFmpeg, yt-dlp, Demucs, cancelación, mezcla y MP3. Soporte Windows/Linux/macOS.
- `harmony.py`: modelo de cifrado, scraping/cache de Cifra Club, secciones y transposición.
- `analysis.py`: BPM, tonalidad estimada, loudness y análisis de audio.

### Servidor y frontend
- `server.py`: servidor FastAPI con endpoints REST. Operaciones bloqueantes en threads daemon.
- `launcher.py`: lanzador desktop que abre el navegador automáticamente.
- `static/index.html`: layout sidebar + workspace + transport bar.
- `static/js/player.js`: mixer multitrack con Web Audio API.
- `static/js/app.js`: lógica de UI completa (chips, harmony, pitch, mixer, export).
- `static/js/api.js`: comunicación con el backend.

### Builds
- `build/build.py`: script genérico de PyInstaller.
- `build/build-linux.sh`: tar.gz portable para Linux.
- `build/build-macos.sh`: .app + DMG para macOS.
- `build/build-windows.bat`: .exe + ZIP portable para Windows.

Cada build incluye: ejecutable PyInstaller (servidor + frontend), `.venv` con PyTorch CPU + Demucs, y binarios ffmpeg/ffprobe/yt-dlp.

## Decisiones y límites

- `htdemucs_6s` permite 6 categorías en una sola pasada. Bajo, piano y guitarra pueden tener filtración según la mezcla.
- WAV es formato interno para evitar pérdidas. MP3 solo al exportar.
- La entrada debe ser estéreo (2 canales).
- Cifra Club es la fuente canónica de acordes. No se usa análisis de audio para acordes.
- No hay persistencia de jobs: se pierden al reiniciar el servidor.
- Jobs en memoria (`_jobs` dict en `server.py`).

## Pendiente

- Visualizador de espectro por track (AnalyserNode + canvas)
- Waveform real con peaks del audio
- Persistencia de jobs en disco
- Probar builds en Windows/macOS reales
- Static ffmpeg builds para portabilidad completa
