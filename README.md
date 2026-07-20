# StemForge

Aplicación de escritorio para Ubuntu que descarga audio de YouTube o carga una mezcla local, prepara dos pistas reales a partir de una mezcla estéreo, las reproduce en un mezclador sincronizado y exporta una mezcla WAV offline.

## Estado actual

StemForge usa una transformación determinista centro/lados de FFmpeg. `Voces.wav` contiene el centro estéreo y `Other.wav` el complemento lateral; juntas reconstruyen la mezcla original cuando se mantienen al 100 %. No es un modelo de IA y puede contener filtración.

No hay cuentas, modo premium, paywall ni funciones limitadas por ventas: es una aplicación de uso personal. Las categorías que necesitan pesos entrenados —batería, bajo, guitarras, piano, coros y efectos— aparecen desactivadas porque todavía no existe un modelo real integrado para ellas.

## Ejecutar en Ubuntu 24.04.4 LTS

Dependencias del sistema:

```bash
sudo apt install python3 python3-gi gir1.2-gtk-4.0 gir1.2-gstreamer-1.0 ffmpeg gstreamer1.0-plugins-base gstreamer1.0-plugins-good
```

El ejecutable de `yt-dlp` se incluye en `bin/yt-dlp`; si se elimina, StemForge también puede usar un `yt-dlp` instalado en el `PATH`.

Después:

```bash
./run.sh
```

También se puede abrir `stemforge.desktop` desde un lanzador, ajustando `Exec` si el proyecto se mueve a otra carpeta.

## Flujo

1. Pega un enlace de YouTube y pulsa `Descargar`, o selecciona/arrastra un archivo local.
2. La descarga usa solo el vídeo indicado (`--no-playlist`) y conserva el audio como WAV temporal local.
3. Elige una carpeta de trabajo explícita.
4. Pulsa `Separar y preparar pistas`.
5. Reproduce las pistas con un único pipeline GStreamer; `M`, `S`, volumen y la línea temporal se aplican sin reiniciar el motor.
6. Usa `Exportar mezcla` para crear `StemForge - mezcla.wav` con el estado actual del mezclador.

Las descargas de YouTube son solo para uso personal y deben respetar los derechos y condiciones aplicables al contenido.

Cada sesión genera `INFORME.md` y `PROVENANCE.json` con el método, limitaciones y hashes de salida.

## Verificación rápida

```bash
python3 -m py_compile app.py engine.py player.py
bin/yt-dlp --version
```

La separación necesita una mezcla de dos canales y requiere que FFmpeg pueda leerla. La reproducción requiere un backend de audio GStreamer disponible en el escritorio.

## Modelos

Este desarrollo no incluye pesos de IA de terceros. `models/manifest.json` mantiene un registro vacío hasta que exista un modelo real que pueda integrarse de forma explícita. No se generan archivos silenciosos para aparentar capacidades.
