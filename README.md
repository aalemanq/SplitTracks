# StemForge

Aplicación de escritorio para Ubuntu que prepara dos pistas reales a partir de una mezcla estéreo, las reproduce en un mezclador sincronizado y exporta una mezcla WAV offline.

## Estado de esta primera versión

StemForge usa una transformación determinista centro/lados de FFmpeg. La pista `Voces.wav` contiene el centro estéreo y `Other.wav` el complemento lateral; juntas reconstruyen la mezcla original cuando se mantienen al 100 %. No es un modelo de IA y puede contener filtración.

Las categorías que requieren pesos entrenados —batería, bajo, guitarras, piano, coros y efectos— aparecen desactivadas. No se incluyen modelos de terceros ni archivos silenciosos de relleno. `models/manifest.json` aplica una política fail-closed para futuras integraciones.

## Ejecutar en Ubuntu 24.04.4 LTS

Dependencias del sistema:

```bash
sudo apt install python3 python3-gi gir1.2-gtk-4.0 gir1.2-gstreamer-1.0 ffmpeg gstreamer1.0-plugins-base gstreamer1.0-plugins-good
```

Después:

```bash
./run.sh
```

También se puede abrir `stemforge.desktop` desde un lanzador, ajustando `Exec` si el proyecto se mueve a otra carpeta.

## Flujo

1. Selecciona un audio estéreo y una carpeta de trabajo explícita.
2. Pulsa `Separar y preparar pistas`.
3. Reproduce las pistas con un único pipeline GStreamer; `M`, `S`, volumen y la línea temporal se aplican sin reiniciar el motor.
4. Usa `Exportar mezcla` para crear `StemForge - mezcla.wav` con el estado actual del mezclador.

Cada sesión genera `INFORME.md` y `PROVENANCE.json` con el método, limitaciones y hashes de salida.

## Verificación rápida

```bash
python3 -m py_compile app.py engine.py player.py
```

La separación necesita una mezcla de dos canales y requiere que FFmpeg pueda leerla. La reproducción requiere un backend de audio GStreamer disponible en el escritorio.

## Licencias y distribución

Este desarrollo no redistribuye pesos de IA. El runtime usa los paquetes de Ubuntu instalados por el usuario; no pretende ser todavía un binario autocontenido ni una compilación comercial final. Antes de distribuir un modelo o empaquetar una versión final hay que comprobar por separado la licencia del código, la de los pesos, la procedencia, los hashes y la compatibilidad de redistribución.
