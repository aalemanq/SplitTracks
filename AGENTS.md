# Split Tracks · instrucciones para agentes

Antes de cambiar código, lee `docs/PROJECT_CONTEXT.md` y `docs/DEVELOPMENT.md`.

## Reglas esenciales

- Aplicación GTK4 exclusiva para Ubuntu/Linux; no migres a web, macOS ni Windows salvo petición explícita.
- Es una herramienta personal sin cuentas, premium, paywall, ventas ni arquitectura de biblioteca.
- Mantén la separación local con `htdemucs_6s` en CPU, los WAV internos y la exportación MP3 bajo demanda.
- No sustituyas el cifrado humano por análisis de acordes de audio: Cifra Club es la fuente canónica actual.
- Conserva la transposición en vivo: cambia preescucha, tonalidad, acordes y grados sin guardar copias intermedias.
- No hagas `git push` salvo petición explícita. Antes de commitear ejecuta sintaxis, tests y `git diff --check`.
- Usa `apply_patch` para editar; si el entorno lo impide, realiza el cambio equivalente de forma segura y documenta la validación.
- No borres ni resetees cambios del usuario. No uses `git reset --hard` ni `git checkout --` sin autorización.

## Mapa rápido

- `app.py`: ventana GTK, flujo de carga/YouTube, análisis, cifrado humano, tono, mixer y exportación.
- `engine.py`: ffprobe/FFmpeg, yt-dlp, Demucs, cancelación, mezcla y MP3.
- `analysis.py`: BPM, tonalidad estimada, loudness y análisis legado de audio; no es fuente canónica de acordes.
- `harmony.py`: modelo de cifrado, scraping/cache de Cifra Club, secciones y transposición.
- `player.py`: mixer GStreamer sincronizado y cambio de pitch en vivo.
- `style.css`: tema dark/solarized y layout GTK.
- `tests/`: tests unitarios de análisis y armonía.

Lee la documentación enlazada antes de proponer una arquitectura nueva.
