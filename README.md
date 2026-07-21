# Split Tracks

Aplicación de escritorio para Ubuntu que descarga audio de YouTube o carga una mezcla local, separa seis stems con Demucs en CPU, los reproduce en un mezclador sincronizado, permite transponerlos por semitonos y exporta MP3 offline.

## Separación real

Split Tracks usa el modelo local `htdemucs_6s` de Demucs 4.1.0. Genera `Voces`, `Batería completa`, `Bajo`, `Guitarra`, `Piano y teclados` y `Other`. El modelo trabaja internamente a 44,1 kHz; Split Tracks convierte las salidas al muestreo y número de canales de la entrada antes de guardarlas como MP3 a 320 kbps.

`Other` siempre se genera como complemento: suma el `Other` del modelo y todas las categorías que no hayas seleccionado. Las salidas de piano y guitarra pueden contener más filtración que voces, batería o bajo; además, el bajo puede perder presencia cuando comparte frecuencias con el bombo, sintetizadores o instrumentos graves. Son limitaciones conocidas de `htdemucs_6s`, no un recorte aplicado por la interfaz: cuando seleccionas Bajo, la aplicación exporta directamente el `bass.wav` generado por el modelo.

### Estado del modelo

La aplicación mantiene `htdemucs_6s` como modelo predeterminado porque es el que permite conservar las seis categorías en una sola separación. Se comparó con el modelo estándar `htdemucs` en una mezcla real y el nivel de graves fue prácticamente equivalente; el modelo estándar no ofreció una mejora suficientemente clara para sustituirlo y tampoco genera piano ni guitarra. `htdemucs_ft` queda como posible modo de calidad futuro: puede mejorar ligeramente los cuatro stems principales, pero requiere bastante más tiempo de CPU.

La calidad depende mucho de la mezcla de origen. En canciones con bajo muy comprimido, distorsionado, sintetizado, paneado o solapado con el bombo pueden faltar notas o aparecer parte del bajo en `Other`. Subir el volumen del stem puede mejorar la escucha cuando el bajo sí está presente, pero no puede recuperar información que el modelo no haya separado.

No hay cuentas, modo premium, paywall ni funciones limitadas por ventas: es una aplicación de uso personal.

## Biblioteca local

Los archivos de audio locales se mantienen en su ubicación original: Split Tracks no los mueve, copia ni elimina. Al analizarlos, la aplicación guarda una referencia y sus metadatos básicos en `~/.local/share/split-tracks/library.sqlite3` (o dentro de XDG_DATA_HOME si está configurada). Desde ahí se conservan los favoritos y el análisis musical de cada pista: BPM estimado, tonalidad/escala, LUFS integrados, pico, rango dinámico y un resumen del espectro. La aplicación solo guarda referencias y metadatos; no mueve, copia ni elimina el audio original. Los archivos descargados de YouTube siguen siendo temporales hasta que se implemente su almacenamiento persistente.



## Análisis musical local

Al cargar un archivo, el análisis se ejecuta en segundo plano con FFmpeg y NumPy para no bloquear la interfaz. La tarjeta muestra un resumen con BPM, tonalidad, LUFS y dinámica, además de un espectro compacto; los valores completos quedan en SQLite para usarlos después en la biblioteca y el reproductor. BPM y tonalidad son estimaciones y conviene confirmarlos de oído, especialmente en canciones con cambios de tempo, modulaciones o mucha percusión.

## Ejecutar en Ubuntu 24.04.4 LTS

Dependencias del sistema:

```bash
sudo apt install python3 python3-venv python3-gi gir1.2-gtk-4.0 gir1.2-gstreamer-1.0 ffmpeg gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad
```

Instala el motor ML una vez:

```bash
./setup-model.sh
```

El script instala las ruedas CPU oficiales de PyTorch y Demucs en `.venv`; no instala CUDA. El modelo se descarga la primera vez que se separa una canción y queda en la caché local de PyTorch/Hugging Face.

El ejecutable de `yt-dlp` se incluye en `bin/yt-dlp`.

Después:

```bash
./run.sh
```

## Flujo

1. Pega un enlace de YouTube y pulsa `Descargar`, o selecciona/arrastra un archivo local.
2. Elige las categorías que quieres conservar; `Other` se calcula automáticamente.
3. Elige una carpeta de trabajo explícita.
4. Pulsa `Separar y preparar pistas`.
5. Escucha y ajusta cada stem con mute, solo y volumen.
6. Usa `Exportar mezcla MP3` para crear `Split Tracks - mezcla.mp3`.
7. Pulsa `−` y `+` para preescuchar cada semitono al vuelo mientras la canción sigue sonando.
8. Cuando te guste, pulsa `Guardar tonalidad` para crear las pistas MP3 en esa tonalidad.

Las descargas de YouTube son solo para uso personal y deben respetar los derechos y condiciones aplicables al contenido.

Cada sesión genera `INFORME.md` y `PROVENANCE.json` con el modelo, categorías, método y hashes de salida.

## Verificación rápida

```bash
python3 -m py_compile app.py analysis.py engine.py library.py player.py
./.venv/bin/python -c "import torch, torchaudio, demucs; print(torch.__version__, torch.cuda.is_available())"
```

La separación actual necesita una mezcla estéreo de dos canales. La preescucha usa el elemento `pitch` de GStreamer SoundTouch y cambia la tonalidad en tiempo real manteniendo el tempo. Al guardar, la aplicación utiliza el filtro Rubber Band incluido en FFmpeg y crea una carpeta visible con las copias MP3 transpuestas; ese es el único paso que requiere renderizado. El procesamiento es CPU y puede tardar aproximadamente lo mismo o más que la duración de la canción según el tamaño y la memoria disponible.

## Fuentes del motor

- Demucs: https://github.com/facebookresearch/demucs
- Modelo `htdemucs_6s`: seis fuentes (`drums`, `bass`, `other`, `vocals`, `piano`, `guitar`).
- Demucs documenta que `htdemucs_6s` es experimental y que piano puede tener más artefactos; la interfaz no oculta esas limitaciones.
