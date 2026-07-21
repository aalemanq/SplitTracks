# Split Tracks

Aplicación de escritorio para Ubuntu que descarga audio de YouTube o carga una mezcla local, separa seis stems con Demucs en CPU, los reproduce desde WAV internos en un mezclador sincronizado, permite transponerlos por semitonos y exporta MP3 bajo demanda.

## Separación real

Split Tracks usa el modelo local `htdemucs_6s` de Demucs 4.1.0. Genera `Voces`, `Batería completa`, `Bajo`, `Guitarra`, `Piano y teclados` y `Other`. El modelo trabaja internamente a 44,1 kHz; Split Tracks conserva las salidas como WAV PCM de 16 bits para evitar recodificaciones durante la separación y las convierte a MP3 320 kbps solo al exportarlas.

`Other` siempre se genera como complemento: suma el `Other` del modelo y todas las categorías que no hayas seleccionado. Las salidas de piano y guitarra pueden contener más filtración que voces, batería o bajo; además, el bajo puede perder presencia cuando comparte frecuencias con el bombo, sintetizadores o instrumentos graves. Son limitaciones conocidas de `htdemucs_6s`, no un recorte aplicado por la interfaz: cuando seleccionas Bajo, la aplicación conserva directamente el `bass.wav` generado por el modelo y lo convierte a MP3 solo si lo exportas.

### Estado del modelo

La aplicación mantiene `htdemucs_6s` como modelo predeterminado porque es el que permite conservar las seis categorías en una sola separación. Se comparó con el modelo estándar `htdemucs` en una mezcla real y el nivel de graves fue prácticamente equivalente; el modelo estándar no ofreció una mejora suficientemente clara para sustituirlo y tampoco genera piano ni guitarra. `htdemucs_ft` queda como posible modo de calidad futuro: puede mejorar ligeramente los cuatro stems principales, pero requiere bastante más tiempo de CPU.

La calidad depende mucho de la mezcla de origen. En canciones con bajo muy comprimido, distorsionado, sintetizado, paneado o solapado con el bombo pueden faltar notas o aparecer parte del bajo en `Other`. Subir el volumen del stem puede mejorar la escucha cuando el bajo sí está presente, pero no puede recuperar información que el modelo no haya separado.

No hay cuentas, modo premium, paywall ni funciones limitadas por ventas: es una aplicación de uso personal.

## Análisis musical local

Al cargar un archivo, el análisis se ejecuta en segundo plano con FFmpeg y NumPy para no bloquear la interfaz. La tarjeta muestra un panel de métricas con tonalidad destacada, BPM, duración, escala, LUFS, dinámica, formato, muestreo, canales, estabilidad del tempo, confianza tonal y el número de acordes de la fuente humana seleccionada. Los acordes y grados se muestran en cuatro columnas para facilitar la lectura.
Los botones `−`, `+` y `Original` de `Transponer análisis` son el único control de tonalidad: cambian la preescucha en vivo manteniendo el tempo y actualizan los acordes y grados mostrados.

Mientras se comprueba un audio aparece el botón "Cancelar análisis". Ese botón detiene los procesos auxiliares de FFmpeg, descarta los resultados parciales y deja la interfaz lista para seleccionar otro archivo. Si se cierra la ventana durante una descarga, análisis, separación o exportación, la aplicación solicita la cancelación de esos workers y espera brevemente a que terminen antes de salir, evitando dejar FFmpeg, yt-dlp o Demucs ejecutándose en segundo plano.

El detector de acordes por audio queda disponible solo como diagnóstico opcional; no se usa como fuente canónica ni se ejecuta durante la carga normal. La aplicación usa ahora un cifrado humano seleccionado por el usuario, que conserva secciones, orden y cambios de acorde publicados.

### Acordes de fuentes humanas

La tarjeta "Cifrado humano" busca artista y canción directamente en [Cifra Club en español](https://www.cifraclub.com.br/?locale=es), muestra las versiones que la página ofrece y permite abrir la fuente antes de elegirla. Se valida que cada versión contenga un bloque de acordes legible, por lo que las páginas de letra, tablatura o versiones sin acordes no aparecen como opciones utilizables.

Al seleccionar una versión, la app muestra sus acordes y grados en columnas de cuatro, conserva las secciones de la fuente y usa la tonalidad publicada cuando está disponible. Cuando la búsqueda devuelve varias versiones, la primera versión válida se carga y se muestra automáticamente; las demás quedan disponibles para cambiar manualmente. En descargas de YouTube, la búsqueda se inicia sola cuando se han obtenido artista y título. Los botones de transposición cambian a la vez la tonalidad, los acordes, las inversiones y los grados, sin reanalizar el audio. La información se cachea durante siete días en ~/.cache/split-tracks/harmony para no repetir consultas.

Esta primera integración prioriza una fuente estable y revisada. Ultimate Guitar queda como siguiente proveedor independiente, porque sus páginas y mecanismos de carga cambian con frecuencia; no se mezclan datos de varios sitios ni se inventan compases cuando la fuente no los publica. La app conserva el enlace de cada versión para comprobarla manualmente.

La cabecera concentra ahora la URL de YouTube, la apertura de archivos locales, los accesos rápidos por stem y el botón Separar. La columna lateral queda reservada para la carpeta de trabajo y el análisis musical, con una lectura más amplia de sus metadatos y acordes.

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

1. Pega un enlace de YouTube y pulsa Añadir, o pulsa Subir audio para elegir un archivo local. Al descargar desde YouTube, yt-dlp rellena automáticamente artista y canción; si el vídeo no publica esos metadatos, se limpian formatos habituales como Artista - Canción (Official Video) y puedes corregirlos antes de buscar.
2. Elige las categorías que quieres conservar; Other se calcula automáticamente.
3. Elige una carpeta de trabajo explícita.
4. Pulsa `Separar` en la cabecera; durante el proceso se muestra el tiempo transcurrido.
5. Escucha y ajusta cada stem con mute, solo y volumen.
6. Usa `Exportar mezcla MP3` para crear `Split Tracks - mezcla.mp3`; el estado final indica la carpeta y el nombre exacto del archivo guardado.
7. Usa `Exportar pistas MP3` para exportar las pistas activas (respetando Mute/Solo), o pulsa `MP3` en una pista concreta.
8. Pulsa `−` y `+` para preescuchar cada semitono al vuelo mientras la canción sigue sonando.

La entrada de YouTube se descarga solo para uso personal y debe respetar los derechos y condiciones aplicables al contenido.

Cada sesión genera `INFORME.md` y `PROVENANCE.json` con el modelo, categorías, método y hashes de salida.

## Verificación rápida

```bash
python3 -m py_compile app.py analysis.py engine.py player.py
./.venv/bin/python -c "import torch, torchaudio, demucs; print(torch.__version__, torch.cuda.is_available())"
```

La separación actual necesita una mezcla estéreo de dos canales. La preescucha usa el elemento `pitch` de GStreamer SoundTouch y cambia la tonalidad en tiempo real manteniendo el tempo. El cambio de tonalidad afecta a la escucha y al análisis mostrado; no crea copias nuevas ni altera los stems internos.

La separación conserva WAV para acelerar la reproducción y la mezcla. Los MP3 se generan solo mediante `Exportar mezcla MP3`, `Exportar pistas MP3` o el botón `MP3` de cada pista. El procesamiento es CPU y puede tardar aproximadamente lo mismo o más que la duración de la canción según el tamaño y la memoria disponible.

## Fuentes del motor

- Demucs: https://github.com/facebookresearch/demucs
- Modelo `htdemucs_6s`: seis fuentes (`drums`, `bass`, `other`, `vocals`, `piano`, `guitar`).
- Demucs documenta que `htdemucs_6s` es experimental y que piano puede tener más artefactos; la interfaz no oculta esas limitaciones.
