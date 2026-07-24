# Split Tracks

Separación de audio en stems por instrumentos con inteligencia artificial local. Descarga desde YouTube o carga archivos locales, separa voces, batería, bajo, guitarra, piano y otros con Demucs, y visualiza los acordes desde Cifra Club.

**Windows · macOS · Linux** — una sola aplicación, tres plataformas.

## Características

- **Separación IA local**: modelo `htdemucs_6s` en CPU, sin subir audio a ningún servidor
- **6 stems**: Voces, Batería, Bajo, Guitarra, Piano/Teclados y Other
- **Acordes en vivo**: búsqueda automática en Cifra Club con transposición por semitonos
- **Mezclador multitrack**: mute, solo y volumen por pista
- **Cambio de tono**: SoundTouchJS para pitch shifting real (+/- 12 semitonos)
- **Exportación MP3**: mezcla completa o pistas individuales a 320 kbps
- **Portable**: descarga, descomprime y ejecuta — sin instalar dependencias

## Descarga

Descarga la versión para tu sistema operativo desde [GitHub Releases](https://github.com/aalemanq/SplitTracks/releases):

| Plataforma | Archivo |
|------------|---------|
| Linux | `SplitTracks-linux-x86_64.tar.gz` |
| macOS | `SplitTracks-macOS.dmg` |
| Windows | `SplitTracks-windows.zip` |

## Uso rápido

### Linux
```bash
tar xzf SplitTracks-linux-x86_64.tar.gz
cd SplitTracks-linux
./SplitTracks
```

### macOS
Abre el `.dmg`, arrastra `Split Tracks.app` a Aplicaciones y ejecútalo.

### Windows
Descomprime el ZIP y ejecuta `SplitTracks.vbs`.

El navegador se abre automáticamente en `http://127.0.0.1:8745`.

## Flujo de trabajo

1. Pega un enlace de YouTube o sube un archivo de audio local
2. Selecciona los stems que quieres conservar
3. Pulsa **Separar** — Demucs procesa en local
4. Ajusta volumen, mute y solo en el mezclador
5. Cambia el tono con los botones `−` `+` o busca acordes desde Cifra Club
6. Exporta la mezcla o pistas individuales a MP3

## Desarrollo

```bash
git clone https://github.com/aalemanq/SplitTracks.git
cd SplitTracks
./setup-model.sh          # Instala PyTorch CPU + Demucs
.venv/bin/python server.py  # Arranca en http://localhost:8745
```

Requisitos: Python 3.12+, ffmpeg, [yt-dlp](https://github.com/yt-dlp/yt-dlp) en `bin/`.

Para contribuir, lee [AGENTS.md](AGENTS.md) y [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Cómo funciona

Split Tracks es un servidor web local (FastAPI) con frontend HTML/CSS/JS (Web Audio API). El motor de audio usa:

- **[Demucs](https://github.com/facebookresearch/demucs)** (`htdemucs_6s`) para separación de fuentes
- **FFmpeg** para decodificación, mezcla y codificación MP3
- **yt-dlp** para descarga desde YouTube
- **SoundTouchJS** para pitch shifting en tiempo real
- **NumPy + FFmpeg** para análisis de BPM, tonalidad y loudness

Los stems se mantienen en WAV internamente para evitar recodificación. El MP3 se genera solo al exportar.

## Limitaciones conocidas

- `htdemucs_6s` es experimental: piano y guitarra pueden tener más artefactos
- El bajo puede perder presencia cuando comparte frecuencias con el bombo
- El pitch en el navegador usa playbackRate (cambia velocidad y tono juntos); SoundTouchJS ofrece pitch real pero con mayor latencia
- Los trabajos se pierden al reiniciar el servidor (estado en memoria)

## Licencia

Uso personal. Consulta [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt) para las licencias de las dependencias.
