# Split Tracks · contexto de proyecto

## Producto y alcance

Split Tracks es una aplicación de escritorio para separación de audio en stems. Tiene dos versiones:

- **GTK4 para Ubuntu/Linux** (rama `main`): aplicación nativa con interfaz GTK4, mixer GStreamer y transposición en vivo.
- **Web multiplataforma** (rama `feature/cross-platform`): servidor FastAPI + frontend HTML/CSS/JS, mixer Web Audio API, compatible con macOS/Windows/Linux.

Es de uso personal: no hay cuentas, premium, paywall, ventas, biblioteca gestionada ni sincronización web.

El nombre visible actual es **Split Tracks**. El repositorio remoto es `git@github.com:aalemanq/SplitTracks.git`.

## Flujo funcional actual

1. El usuario pega una URL de YouTube y pulsa Añadir, o pulsa Subir audio y elige un archivo local.
2. YouTube se descarga con el binario incluido `bin/yt-dlp` a una carpeta temporal. Se extrae WAV para trabajar internamente sin recodificación adicional.
3. `ffprobe` obtiene duración, formato, frecuencia, canales y layout. La mezcla debe ser estéreo de dos canales.
4. FFmpeg + NumPy calculan BPM, tonalidad estimada, escala, LUFS, pico, dinámica, estabilidad/confianza y espectro. Es análisis auxiliar y best-effort.
5. Si YouTube entrega artista y título, se buscan acordes automáticamente en Cifra Club y se carga la primera versión válida. Las demás versiones quedan disponibles para seleccionar manualmente. Para un archivo local sin artista hay que introducir artista/canción.
6. El usuario elige las categorías deseadas; `Other` se construye como complemento del `other` de Demucs más las categorías no seleccionadas. La carpeta de salida es `~/Split Tracks` por defecto (configurable mediante `default_output_folder()` en `app.py`).
7. Separar ejecuta `htdemucs_6s` en CPU y produce `Voces`, `Batería completa`, `Bajo`, `Guitarra`, `Piano y teclados` y `Other` en WAV PCM.
8. El mixer GStreamer reproduce todos los stems con un reloj común. Cada pista tiene volumen, Mute, Solo y exportación MP3 individual.
9. `−`, `+` y `Original` hacen transposición en vivo de la preescucha y del cifrado mostrado. No hay botón Guardar de tonalidad ni se crean WAV transpuestos.
10. `Exportar mezcla MP3` mezcla las pistas activas a MP3 320 kbps. `Exportar pistas MP3` exporta las pistas activas respetando Mute/Solo.

## Arquitectura por archivo

### `app.py`

`MainWindow` construye toda la interfaz. La carga de audio inicia workers daemon y usa `GLib.idle_add` para devolver resultados al hilo GTK. Hay dos eventos de cancelación: `analysis_cancel_event` para ffprobe/análisis y `cancel_event` para descarga, Demucs y exportaciones. Los workers de procesos se registran en `_process_threads`; `close_request()` marca el cierre, señala eventos, detiene el reloj, cierra el player y espera brevemente antes de cerrar la ventana.

El panel de armonía está en `_build_harmony_source_panel()`. `_harmony_search_success()` pinta las versiones y llama automáticamente a `_select_harmony_candidate()` para la primera. `_harmony_fetch_success()` instala el `ChordChart` y actualiza métricas, acordes y grados.

`_build_chord_line_flow()` usa cuatro columnas y reserva celdas de 64×32 px, centradas verticalmente, para impedir que `♯`/`♭` muevan el layout. La métrica grande de tonalidad también reserva altura para glifos accidentales.

### `engine.py`

`SeparationEngine` contiene operaciones locales. `_run()` ejecuta FFmpeg cancelable. yt-dlp y Demucs se lanzan en grupos de procesos (`start_new_session=True`) para poder terminar también hijos. `select.select()` evita bloquear la cancelación cuando no hay salida de texto. La cancelación elimina carpetas parciales.

`separate()` utiliza:

```text
demucs.separate -n htdemucs_6s -d cpu --segment 7 --shifts 1 --overlap 0.25 -j 1
```

El modelo y la separación son CPU. No introduzcas CUDA ni cambies el modelo por defecto sin comparar calidad, tiempo y memoria.

### `analysis.py`

Usa FFmpeg para decodificar a mono a 11025 Hz y NumPy para FFT/chroma. `AnalysisCancelled` interrumpe los FFmpeg del análisis. Las funciones de acordes de este archivo son legado/diagnóstico: el usuario decidió que no sean fuente canónica porque daban progresiones erróneas.

### `harmony.py`

Contiene `ChordCandidate`, `ChordChart`, `ChordSection` y `ChordLine`. `CifraClubProvider` consulta `https://www.cifraclub.com.br/` añadiendo `locale=es`, filtra enlaces de letra/tablatura y valida que las versiones tengan secciones de acordes. Cachea búsquedas y charts en `~/.cache/split-tracks/harmony` durante siete días.

La transposición conserva secciones, orden y separadores de compás. Cambia raíces, bajos, tonalidad y grados; no inventa compases. Cifra Club puede cambiar HTML, nombres de versiones o locale: mantén el parser tolerante y los tests de compatibilidad.

### `player.py`

Construye un mixer GStreamer con un único reloj y un elemento `pitch` maestro. La preescucha de pitch requiere `gstreamer1.0-plugins-bad`/SoundTouch. El pitch afecta a la escucha, no altera los WAV internos ni la exportación.

### `style.css` y assets

Tema dark/solarized con paneles GTK. Los iconos de instrumento están en `assets/icons/*.svg`. Mantén consistencia geométrica: badges centrados, botones M/S iguales y grids de acordes estables.

## Decisiones y límites conocidos

- `htdemucs_6s` permite las seis categorías en una sola pasada; bajo, piano y guitarra pueden tener filtración según la mezcla.
- WAV es formato interno para evitar pérdidas y acelerar mezcla/reproducción; MP3 solo se crea al exportar.
- La entrada debe ser estéreo; no implementes downmix silencioso sin decisión de producto.
- El cifrado humano es aproximado a la grabación y depende de la versión publicada. No se debe afirmar sincronización exacta con el audio si la fuente no la publica.
- Cifra Club es la fuente actual. Ultimate Guitar queda como proveedor futuro independiente; no mezcles fuentes ni hagas scraping indiscriminado de Google sin una decisión explícita.
- La app no necesita biblioteca: los resultados se conservan en `~/Split Tracks` (o la carpeta que defina `default_output_folder()`) y los archivos originales permanecen en su ubicación.
- La aplicación debe poder cancelar análisis/separación/exportación y no dejar yt-dlp, FFmpeg o Demucs ejecutándose tras cerrar.

## Futuras mejoras coherentes

- Mejorar selección/orden de versiones de Cifra Club mediante rating, instrumento y coincidencia artista/título.
- Añadir proveedores humanos independientes con tests por parser.
- Mostrar secciones/compases del chart con mejor lectura sin alterar la fuente.
- Medir rendimiento Demucs con audios de referencia antes de tocar modelo, segmento, shifts o jobs.
- Migrar a web solo como proyecto separado cuando el producto GTK esté cerrado; no mezclar esa migración con mejoras pequeñas.

## Historial reciente relevante

- `b203586`: cancelación de análisis y cierre limpio de procesos.
- `e37ccfe`: carga automática de la primera versión de Cifra Club.
- `d8028f9`: celdas de acordes con ancho estable.
- `48d17d4`: alineado estable de tonalidades con sostenidos/bemoles.
- Migración web: versión multiplataforma con FastAPI + Web Audio API en rama `feature/cross-platform`.

La rama de trabajo histórica es `feature/human-chord-sources`. Tras este trabajo se fusiona localmente en `master` según la petición del usuario; no hagas push automáticamente.

## Versión web multiplataforma (`feature/cross-platform`)

La versión web comparte el motor (`engine.py`, `harmony.py`, `analysis.py`) con la versión GTK pero reemplaza la UI con un frontend HTML/CSS/JS y el sistema de audio GStreamer por Web Audio API.

### Arquitectura

- **`web-app/server.py`**: servidor FastAPI que expone los endpoints REST. Las operaciones bloqueantes (descarga, análisis, separación) se ejecutan en threads daemon para no bloquear el event loop. Los trabajos son asíncronos: el POST `/api/jobs` devuelve el ID al instante y el cliente sondea el progreso.
- **`web-app/static/index.html`**: layout de dos paneles: sidebar (acordes, métricas, pitch) + workspace (progreso, acordes, mixer).
- **`web-app/static/js/player.js`**: mixer multitrack con Web Audio API. Cada stem se carga como AudioBuffer y se reproduce sincronizado mediante BufferSource nodes con ganancia individual.
- **`web-app/static/js/app.js`**: lógica de UI completa: chips de stems, búsqueda de acordes, selección de versiones, transposición, métricas, mixer, exportación.

### Endpoints principales

| Ruta | Función |
|------|---------|
| POST /api/jobs | Crear trabajo (YouTube o archivo) — asíncrono |
| GET /api/jobs/{id} | Estado, stems, métricas, acordes |
| GET /api/jobs/{id}/stems/{file} | Servir stem WAV |
| GET /api/jobs/{id}/stems-mp3/{file} | Transcodificar y servir stem MP3 |
| POST /api/jobs/{id}/pitch | Cambiar pitch (semitones) |
| GET /api/chords/search | Buscar en Cifra Club |
| POST /api/chords/transpose | Transponer acordes |
| POST /api/jobs/{id}/export/mix | Exportar mezcla MP3 |

### Builds

- **macOS**: `build/build-macos.sh` → PyInstaller .app + DMG
- **Windows**: `build/build-windows.bat` → PyInstaller .exe + ZIP

### Límites conocidos

- El pitch del audio no se transpone (Web Audio API no tiene pitch shift nativo); solo se transpone la visualización de acordes.
- Los trabajos se pierden al reiniciar el servidor (estado en memoria).
- La versión web no tiene waveform real (placeholder visual).

## Portabilidad Windows (`feature/windows-port`)

La rama `feature/windows-port` se enfoca en que la versión web funcione como ejecutable standalone en Windows. El objetivo es que el usuario final reciba un ZIP, lo descomprima, ejecute `SplitTracks.bat` y la app se abra en el navegador sin instalar nada.

### Estrategia

- **PyInstaller** empaqueta el servidor FastAPI + frontend en un `.exe`
- **FFmpeg/ffprobe/yt-dlp** se bundlean en `bin/` como binarios standalone
- **PyTorch + Demucs** se incluyen via `.venv/` copiada al bundle
- El launcher abre el navegador automáticamente al iniciar el servidor

### Dependencias externas

| Binario | Uso | Origen |
|---------|-----|--------|
| `ffmpeg.exe` | Decodificación, mezcla, MP3 | https://ffmpeg.org/download.html |
| `ffprobe.exe` | Metadata de audio | Incluido con FFmpeg |
| `yt-dlp.exe` | Descarga de YouTube | https://github.com/yt-dlp/yt-dlp/releases |

### Tamaño estimado

- Bundle sin comprimir: ~1.2GB (PyTorch CPU es grande)
- ZIP comprimido: ~400-600MB
- Ver `docs/WINDOWS_PLAN.md` para el plan detallado y optimizaciones futuras.
