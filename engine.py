#!/usr/bin/env python3
"""Local audio operations used by Split Tracks, including Demucs inference."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from urllib.parse import urlparse
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

try:
    import queue
except ImportError:
    import Queue as queue  # type: ignore  # Python 2 fallback

IS_WINDOWS = platform.system() == "Windows"


class AudioEngineError(RuntimeError):
    """A user-facing error raised by the local audio engine."""


class SeparationCancelled(AudioEngineError):
    """The user cancelled a running separation."""


@dataclass(frozen=True)
class AudioInfo:
    path: Path
    filename: str
    format_name: str
    duration: float
    sample_rate: int
    channels: int
    channel_layout: str

    @property
    def duration_label(self) -> str:
        minutes, seconds = divmod(max(0, int(self.duration)), 60)
        return f"{minutes}:{seconds:02d}"

    @property
    def sample_rate_label(self) -> str:
        return f"{self.sample_rate / 1000:g} kHz" if self.sample_rate else "—"


@dataclass(frozen=True)
class StemFile:
    name: str
    path: Path
    color: str
    kind: str


@dataclass(frozen=True)
class SeparationResult:
    output_dir: Path
    stems: tuple[StemFile, ...]
    report_path: Path


@dataclass(frozen=True)
class YoutubeDownloadResult:
    path: Path
    temporary_dir: Path
    title: str
    artist: str = ""


ProgressCallback = Callable[[float, str], None]


def _read_process_lines(stream, process, cancel_event):
    """Yield lines from a subprocess stdout pipe. Works on Windows where select()
    does not support pipe file descriptors."""
    line_queue: queue.Queue = queue.Queue()
    finished = threading.Event()

    def _reader():
        try:
            for raw in iter(stream.readline, ""):
                if finished.is_set():
                    break
                line_queue.put(raw)
        except (ValueError, OSError):
            pass
        finally:
            line_queue.put(None)

    reader = threading.Thread(target=_reader, daemon=True)
    reader.start()
    try:
        while True:
            try:
                raw = line_queue.get(timeout=0.2)
            except queue.Empty:
                if cancel_event is not None and cancel_event.is_set():
                    return
                if process.poll() is not None and line_queue.empty():
                    return
                continue
            if raw is None:
                return
            yield raw
    finally:
        finished.set()


def _signal_process_tree(process: subprocess.Popen, *, force: bool = False) -> None:
    if IS_WINDOWS:
        try:
            (process.kill if force else process.terminate)()
        except ProcessLookupError:
            pass
        return
    signal_value = signal.SIGKILL if force else signal.SIGTERM
    try:
        os.killpg(os.getpgid(process.pid), signal_value)
    except (ProcessLookupError, PermissionError):
        try:
            (process.kill if force else process.terminate)()
        except ProcessLookupError:
            pass


def _find_bin(name: str) -> str:
    bundled = Path(__file__).resolve().parent / "bin" / f"{name}{'.exe' if IS_WINDOWS else ''}"
    if bundled.is_file():
        return str(bundled)
    return name


MODEL_NAME = "htdemucs_6s"
STEM_ORDER = ("vocals", "drums", "bass", "guitar", "piano", "other")
STEM_LABELS = {
    "vocals": ("Voces", "modelo Demucs · señal vocal", "#f4a7b9"),
    "drums": ("Batería completa", "modelo Demucs · batería", "#f4c98a"),
    "bass": ("Bajo", "modelo Demucs · bajo", "#a6b8ff"),
    "guitar": ("Guitarra", "modelo Demucs · guitarra", "#d2b2ff"),
    "piano": ("Piano y teclados", "modelo Demucs · piano", "#9ee7e0"),
    "other": ("Other", "complemento Demucs", "#9ba4b6"),
}


def _run(command: list[str], *, capture_output: bool = True, cancel_event=None) -> subprocess.CompletedProcess[str]:
    if cancel_event is None:
        try:
            return subprocess.run(
                command,
                check=False,
                text=True,
                capture_output=capture_output,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError as exc:
            raise AudioEngineError(
                "No encuentro FFmpeg. Instala ffmpeg y vuelve a abrir Split Tracks."
            ) from exc

    if cancel_event.is_set():
        raise SeparationCancelled("Operación cancelada por el usuario.")
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        raise AudioEngineError(
            "No encuentro FFmpeg. Instala ffmpeg y vuelve a abrir Split Tracks."
        ) from exc

    while True:
        try:
            stdout, stderr = process.communicate(timeout=0.2)
            return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        except subprocess.TimeoutExpired:
            if not cancel_event.is_set():
                continue
            _signal_process_tree(process)
            try:
                process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                _signal_process_tree(process, force=True)
                process.communicate()
            raise SeparationCancelled("Operación cancelada por el usuario.")


def _safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9À-ÿ _.-]+", "", value).strip(" .")
    return value or "Mezcla"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class SeparationEngine:
    """Local audio probing, Demucs separation, pitch shifting and MP3 export."""

    mp3_bitrate = "320k"

    def probe(self, path: str | Path, cancel_event=None) -> AudioInfo:
        audio_path = Path(path).expanduser().resolve()
        if not audio_path.is_file():
            raise AudioEngineError("El archivo de audio ya no está disponible.")

        result = _run(
            [
                _find_bin("ffprobe"),
                "-v",
                "error",
                "-show_entries",
                "format=format_name,duration:stream=codec_type,codec_name,sample_rate,channels,channel_layout,duration",
                "-of",
                "json",
                str(audio_path),
            ],
            cancel_event=cancel_event,
        )
        if result.returncode != 0:
            raise AudioEngineError(
                "No puedo leer este archivo. Prueba con WAV, FLAC, OGG, MP3 o M4A."
            )
        try:
            payload = json.loads(result.stdout)
            stream = next(
                stream for stream in payload.get("streams", []) if stream.get("codec_type") == "audio"
            )
        except (ValueError, StopIteration, TypeError) as exc:
            raise AudioEngineError("El archivo no contiene una pista de audio válida.") from exc

        format_data = payload.get("format", {})
        duration = float(stream.get("duration") or format_data.get("duration") or 0)
        return AudioInfo(
            path=audio_path,
            filename=audio_path.name,
            format_name=(format_data.get("format_name") or "audio").split(",")[0].upper(),
            duration=duration,
            sample_rate=int(stream.get("sample_rate") or 0),
            channels=int(stream.get("channels") or 0),
            channel_layout=stream.get("channel_layout") or ("stereo" if stream.get("channels") == 2 else ""),
        )

    def download_youtube(
        self,
        url: str,
        progress: ProgressCallback | None = None,
        cancel_event=None,
    ) -> YoutubeDownloadResult:
        """Download one YouTube video as a temporary local WAV file."""
        parsed = urlparse(url.strip())
        host = (parsed.hostname or "").lower().removeprefix("www.")
        allowed_hosts = {"youtube.com", "youtu.be", "m.youtube.com", "music.youtube.com"}
        if parsed.scheme not in {"http", "https"} or host not in allowed_hosts:
            raise AudioEngineError("Pega un enlace válido de YouTube.")

        ytdlp = self._find_ytdlp()
        if not ytdlp:
            raise AudioEngineError(
                "No encuentro yt-dlp. Coloca el binario en bin/yt-dlp o instala yt-dlp con Ubuntu."
            )
        temporary_dir = Path(tempfile.mkdtemp(prefix="stemforge-youtube-"))
        command = [
            str(ytdlp),
            "--no-playlist",
            "--no-part",
            "--restrict-filenames",
            "--no-warnings",
            "--newline",
            "--progress",
            "--print",
            "after_move:STEMFORGE_META:%(artist)s\t%(creator)s\t%(uploader)s\t%(title)s",
            "--extract-audio",
            "--audio-format",
            "wav",
            "--audio-quality",
            "0",
            "--output",
            str(temporary_dir / "%(title)s.%(ext)s"),
            url.strip(),
        ]
        if progress:
            progress(0.03, "Conectando con YouTube")
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            start_new_session=True,
        )
        output_lines: list[str] = []
        try:
            assert process.stdout is not None
            for raw_line in _read_process_lines(process.stdout, process, cancel_event):
                if cancel_event is not None and cancel_event.is_set():
                    _signal_process_tree(process)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        _signal_process_tree(process, force=True)
                        process.wait()
                    raise SeparationCancelled("Descarga cancelada. No se ha conservado el archivo temporal.")
                line = raw_line.strip()
                if line:
                    output_lines.append(line)
                match = re.search(r"\[download\]\s+(\d+(?:\.\d+)?)%", line)
                if match and progress:
                    percent = float(match.group(1)) / 100
                    progress(min(0.84, 0.06 + percent * 0.76), "Descargando audio de YouTube")
            return_code = process.wait()
        except SeparationCancelled:
            shutil.rmtree(temporary_dir, ignore_errors=True)
            raise
        except Exception:
            _signal_process_tree(process, force=True)
            process.wait()
            shutil.rmtree(temporary_dir, ignore_errors=True)
            raise

        wav_files = sorted(temporary_dir.glob("*.wav"))
        if return_code != 0 or not wav_files:
            shutil.rmtree(temporary_dir, ignore_errors=True)
            detail = self._youtube_error(output_lines)
            raise AudioEngineError(detail)
        audio_path = wav_files[0]
        metadata_artist, metadata_title = self._youtube_metadata(output_lines)
        if progress:
            progress(0.94, "Audio descargado; comprobando el archivo")
        return YoutubeDownloadResult(
            audio_path,
            temporary_dir,
            metadata_title or audio_path.stem,
            metadata_artist,
        )

    @staticmethod
    def _youtube_metadata(lines: list[str]) -> tuple[str, str]:
        prefix = "STEMFORGE_META:"
        for line in reversed(lines):
            if not line.startswith(prefix):
                continue
            payload = line[len(prefix):]
            fields = payload.split("\t", 3)
            if len(fields) != 4:
                fields = payload.split("\\t", 3)
            if len(fields) != 4:
                continue

            def useful(value: str) -> str:
                value = value.strip()
                return "" if value.upper() in {"", "NA", "N/A", "NONE", "UNKNOWN"} else value

            artist = useful(fields[0]) or useful(fields[1]) or useful(fields[2])
            return artist, useful(fields[3])
        return "", ""

    @staticmethod
    def _find_ytdlp() -> Path | None:
        bundled = Path(__file__).resolve().parent / "bin" / f"yt-dlp{'.exe' if IS_WINDOWS else ''}"
        if bundled.is_file():
            return bundled
        system = shutil.which("yt-dlp")
        return Path(system) if system else None

    @staticmethod
    def _youtube_error(lines: list[str]) -> str:
        joined = " ".join(lines).lower()
        if "sign in" in joined or "confirm you are" in joined:
            return "YouTube pide verificar la sesión para este vídeo. Prueba otro enlace."
        if "private video" in joined or "video unavailable" in joined:
            return "El vídeo no está disponible públicamente o es privado."
        if "age-restricted" in joined or "age restricted" in joined:
            return "El vídeo tiene restricción de edad y yt-dlp no puede acceder sin sesión."
        return "No se pudo descargar el audio de YouTube. Comprueba el enlace y tu conexión."

    def separate(
        self,
        input_path: str | Path,
        destination: str | Path,
        selected_categories: Iterable[str],
        progress: ProgressCallback | None = None,
        cancel_event=None,
    ) -> SeparationResult:
        info = self.probe(input_path, cancel_event=cancel_event)
        selected = set(selected_categories) & set(STEM_ORDER)
        if not selected:
            raise AudioEngineError("Selecciona al menos una pista para separar.")
        if info.channels != 2:
            raise AudioEngineError("El modelo multistem actual necesita una mezcla estéreo de 2 canales.")
        if info.duration <= 0:
            raise AudioEngineError("La pista no tiene una duración válida para procesarse.")
        separator_python = self._find_separator_python()
        if not separator_python:
            raise AudioEngineError(
                "No encuentro el entorno ML de Split Tracks. Ejecuta ./setup-model.sh para instalar Demucs en CPU."
            )

        destination_path = Path(destination).expanduser().resolve()
        destination_path.mkdir(parents=True, exist_ok=True)
        folder = destination_path / f"Split Tracks - {_safe_name(info.path.stem)}"
        suffix = 2
        while folder.exists():
            folder = destination_path / f"Split Tracks - {_safe_name(info.path.stem)} ({suffix})"
            suffix += 1
        folder.mkdir(parents=True)
        raw_dir = folder / ".model-output"
        command = [
            str(separator_python),
            "-m",
            "demucs.separate",
            "-n",
            MODEL_NAME,
            "-d",
            "cpu",
            "--segment",
            "7",
            "--shifts",
            "1",
            "--overlap",
            "0.25",
            "-j",
            "1",
            "-o",
            str(raw_dir),
            str(info.path),
        ]
        if progress:
            progress(0.03, "Cargando modelo Demucs 6s")
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
            start_new_session=True,
        )
        output_lines: list[str] = []
        try:
            assert process.stdout is not None
            for raw_line in _read_process_lines(process.stdout, process, cancel_event):
                if cancel_event is not None and cancel_event.is_set():
                    _signal_process_tree(process)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        _signal_process_tree(process, force=True)
                        process.wait()
                    raise SeparationCancelled("Separación cancelada. No se han conservado archivos parciales.")
                line = raw_line.strip()
                if line:
                    output_lines.append(line)
                match = re.search(r"(?:^|\s)(\d{1,3})%", line)
                if match and progress:
                    percent = min(100, int(match.group(1))) / 100
                    progress(0.08 + percent * 0.70, "Separando voces, batería, bajo, guitarra y piano")
            return_code = process.wait()
        except SeparationCancelled:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        except Exception:
            _signal_process_tree(process, force=True)
            process.wait()
            shutil.rmtree(folder, ignore_errors=True)
            raise

        if return_code != 0:
            shutil.rmtree(folder, ignore_errors=True)
            raise AudioEngineError(self._demucs_error(output_lines))

        raw_stems = {path.stem.lower(): path for path in raw_dir.rglob("*.wav")}
        missing = [name for name in STEM_ORDER if name not in raw_stems]
        if missing:
            shutil.rmtree(folder, ignore_errors=True)
            raise AudioEngineError("Demucs no generó todas las pistas esperadas: " + ", ".join(missing))

        final_stems: list[StemFile] = []
        requested = [name for name in STEM_ORDER if name in selected and name != "other"]
        for index, name in enumerate(requested):
            display_name, kind, color = STEM_LABELS[name]
            output = folder / f"{display_name}.wav"
            shutil.move(str(raw_stems[name]), output)
            final_stems.append(StemFile(display_name, output, color, kind))
            if progress:
                progress(0.80 + 0.06 * (index + 1) / max(1, len(requested) + 1), f"Preparando {display_name}")

        complement_inputs = [raw_stems["other"]]
        complement_inputs.extend(raw_stems[name] for name in STEM_ORDER if name != "other" and name not in selected)
        other_output = folder / "Other.wav"
        if progress:
            progress(0.88, "Preparando Other")
        self._render_audio(tuple(complement_inputs), other_output, info.sample_rate, info.channels, cancel_event=cancel_event)
        final_stems.append(StemFile("Other", other_output, STEM_LABELS["other"][2], "complemento de las pistas no seleccionadas"))
        shutil.rmtree(raw_dir, ignore_errors=True)

        stems_tuple = tuple(final_stems)
        report_path = folder / "INFORME.md"
        report_path.write_text(self._report(info, folder, stems_tuple, selected), encoding="utf-8")
        (folder / "PROVENANCE.json").write_text(
            json.dumps(
                {
                    "application": "Split Tracks",
                    "method": MODEL_NAME,
                    "method_type": "local neural music source separation",
                    "input": str(info.path),
                    "input_sha256": _sha256(info.path),
                    "selected_categories": sorted(selected),
                    "output_format": "wav_internal_mp3_on_demand",
                    "output_bitrate": self.mp3_bitrate,
                    "model_cache": str(Path.home() / ".cache"),
                    "outputs": [
                        {"name": stem.name, "path": stem.path.name, "sha256": _sha256(stem.path)}
                        for stem in stems_tuple
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if progress:
            progress(1.0, "Separación multistem completada")
        return SeparationResult(folder, stems_tuple, report_path)

    @staticmethod
    def _find_separator_python() -> Path | None:
        bundled = Path(__file__).resolve().parent / ".venv" / ("Scripts" if IS_WINDOWS else "bin") / f"python{'.exe' if IS_WINDOWS else ''}"
        if bundled.is_file():
            try:
                check = subprocess.run(
                    [str(bundled), "-c", "import demucs"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
            except OSError:
                check = None
            if check is not None and check.returncode == 0:
                return bundled
        executable = shutil.which("python3") or sys.executable
        try:
            check = subprocess.run(
                [executable, "-c", "import demucs"],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            return None
        return Path(executable) if check.returncode == 0 else None

    @staticmethod
    def _demucs_error(lines: list[str]) -> str:
        joined = " ".join(lines).lower()
        if "no module named" in joined:
            return "El entorno Demucs está incompleto. Ejecuta ./setup-model.sh y vuelve a intentarlo."
        if "out of memory" in joined or "memoryerror" in joined:
            return "Demucs se quedó sin memoria. Cierra otras aplicaciones y vuelve a probar."
        if "download" in joined or "connection" in joined:
            return "No se pudo descargar el modelo Demucs. Comprueba la conexión y vuelve a intentarlo."
        return "Demucs no pudo completar la separación. Revisa el audio o prueba con una mezcla más corta."

    def _render_audio(self, inputs: tuple[Path, ...], output: Path, sample_rate: int, channels: int, cancel_event=None) -> None:
        if len(inputs) == 1:
            command = [_find_bin("ffmpeg"), "-hide_banner", "-nostdin", "-y", "-i", str(inputs[0])]
            filter_args: list[str] = []
        else:
            command = [_find_bin("ffmpeg"), "-hide_banner", "-nostdin", "-y"]
            for source in inputs:
                command.extend(["-i", str(source)])
            labels = "".join(f"[{index}:a]" for index in range(len(inputs)))
            filter_args = [
                "-filter_complex",
                f"{labels}amix=inputs={len(inputs)}:duration=longest:dropout_transition=0:normalize=0[sum]",
                "-map",
                "[sum]",
            ]
        command.extend(filter_args)
        command.extend(["-ar", str(sample_rate), "-ac", str(channels), *self._codec_args(output), str(output)])
        result = _run(command, cancel_event=cancel_event)
        if result.returncode != 0 or not output.is_file() or output.stat().st_size < 1024:
            raise AudioEngineError(f"No se pudo preparar la pista {output.name}.")


    def render_transposed_stems(
        self,
        stems: Iterable[dict],
        destination: str | Path,
        semitones: int,
        sample_rate: int,
        channels: int,
        duration: float,
        progress: ProgressCallback | None = None,
    ) -> tuple[Path, ...]:
        """Render all session stems at a new pitch while preserving tempo and sync."""
        if not -12 <= semitones <= 12:
            raise AudioEngineError("La transposición debe estar entre -12 y +12 semitonos.")
        stem_list = list(stems)
        if not stem_list:
            raise AudioEngineError("No hay pistas disponibles para cambiar de tonalidad.")
        if semitones == 0:
            return tuple(Path(item.get("base_path", item["path"])) for item in stem_list)

        direction = "mas" if semitones > 0 else "menos"
        shift_dir = Path(destination).expanduser().resolve() / f"Transpuestas {direction}-{abs(semitones)} semitonos"
        shift_dir.mkdir(parents=True, exist_ok=True)
        pitch = 2 ** (semitones / 12)
        outputs: list[Path] = []
        for index, item in enumerate(stem_list):
            source = Path(item.get("base_path", item["path"]))
            output = shift_dir / f"{_safe_name(Path(item['name']).stem)}.mp3"
            partial = shift_dir / f"{_safe_name(Path(item['name']).stem)}.part.mp3"
            if not output.is_file() or output.stat().st_size < 1024:
                command = [
                    _find_bin("ffmpeg"),
                    "-hide_banner",
                    "-nostdin",
                    "-y",
                    "-i",
                    str(source),
                    "-af",
                    f"rubberband=tempo=1:pitch={pitch:.9f}",
                    "-t",
                    f"{max(0.1, duration):.6f}",
                    "-ar",
                    str(sample_rate),
                    "-ac",
                    str(channels),
                    *self._codec_args(partial),
                    str(partial),
                ]
                result = _run(command)
                if result.returncode != 0 or not partial.is_file() or partial.stat().st_size < 1024:
                    partial.unlink(missing_ok=True)
                    raise AudioEngineError(f"No se pudo transponer {item['name']}.")
                partial.replace(output)
            outputs.append(output)
            if progress:
                progress(0.15 + 0.75 * (index + 1) / len(stem_list), f"Transponiendo {item['name']}")
        return tuple(outputs)

    def _codec_args(self, output: Path) -> list[str]:
        if output.suffix.lower() == ".mp3":
            return ["-c:a", "libmp3lame", "-b:a", self.mp3_bitrate, "-id3v2_version", "3"]
        return ["-c:a", "pcm_s16le"]

    def export_stem_mp3(
        self,
        stem: dict,
        destination: str | Path,
        sample_rate: int,
        channels: int,
        cancel_event=None,
    ) -> Path:
        destination_path = Path(destination).expanduser().resolve()
        destination_path.mkdir(parents=True, exist_ok=True)
        output = destination_path / f"{_safe_name(Path(stem['name']).stem)}.mp3"
        self._render_audio((Path(stem["path"]),), output, sample_rate, channels, cancel_event=cancel_event)
        return output

    def export_stems_mp3(
        self,
        stems: Iterable[dict],
        destination: str | Path,
        sample_rate: int,
        channels: int,
        progress: ProgressCallback | None = None,
        cancel_event=None,
    ) -> tuple[Path, ...]:
        stem_list = list(stems)
        if not stem_list:
            raise AudioEngineError("No hay pistas disponibles para exportar.")
        outputs: list[Path] = []
        for index, stem in enumerate(stem_list):
            output = self.export_stem_mp3(stem, destination, sample_rate, channels, cancel_event=cancel_event)
            outputs.append(output)
            if progress:
                progress((index + 1) / len(stem_list), f"Exportando {stem['name']} MP3")
        return tuple(outputs)

    def mix(
        self,
        stems: Iterable[dict],
        destination: str | Path,
        sample_rate: int,
        channels: int,
        progress: ProgressCallback | None = None,
        cancel_event=None,
    ) -> tuple[Path, str | None]:
        stem_list = list(stems)
        solo_exists = any(item.get("solo", False) for item in stem_list)
        active = [
            item
            for item in stem_list
            if not item.get("mute", False) and (not solo_exists or item.get("solo", False))
        ]
        if not active:
            raise AudioEngineError("No hay ninguna pista audible. Desactiva Mute o Solo antes de exportar.")
        output = Path(destination) / "Split Tracks - mezcla.mp3"
        inputs: list[str] = []
        filters: list[str] = []
        for index, item in enumerate(active):
            inputs += ["-i", str(item["path"])]
            gain = max(0.0, min(1.25, float(item.get("volume", 1.0))))
            filters.append(f"[{index}:a]volume={gain:.6f}[a{index}]")
        labels = "".join(f"[a{index}]" for index in range(len(active)))
        filters.append(
            f"{labels}amix=inputs={len(active)}:duration=longest:dropout_transition=0:normalize=0[mix]"
        )
        command = [
            _find_bin("ffmpeg"),
            "-hide_banner",
            "-nostdin",
            "-y",
            *inputs,
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[mix]",
            "-ar",
            str(sample_rate),
            "-ac",
            str(channels),
            *self._codec_args(output),
            str(output),
        ]
        if progress:
            progress(0.12, "Mezclando las pistas sincrónicamente")
        result = _run(command, cancel_event=cancel_event)
        if result.returncode != 0 or not output.is_file():
            raise AudioEngineError("No se pudo exportar la mezcla MP3.")
        warning = None
        peak = self._max_volume(output, cancel_event=cancel_event)
        if peak is not None and peak > 0:
            warning = f"La mezcla alcanza {peak:+.1f} dBFS y puede recortar; se ha exportado sin normalizar."
        if progress:
            progress(1.0, "Mezcla exportada")
        return output, warning

    def _has_audio_signal(self, path: Path) -> bool:
        return self._max_volume(path) is not None

    def _max_volume(self, path: Path, cancel_event=None) -> float | None:
        result = _run(
            [_find_bin("ffmpeg"), "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
            cancel_event=cancel_event,
        )
        text = result.stderr or result.stdout
        match = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", text)
        if not match:
            return None
        value = float(match.group(1))
        return None if value <= -90 else value

    def _report(self, info: AudioInfo, folder: Path, stems: tuple[StemFile, ...], selected: set[str]) -> str:
        lines = [
            "# Informe de separación — Split Tracks",
            "",
            f"- Entrada: `{info.filename}`",
            f"- Duración: `{info.duration_label}`",
            f"- Formato detectado: `{info.format_name}`",
            f"- Muestreo de entrada/salida: `{info.sample_rate_label}`",
            f"- Canales: `{info.channels}` ({info.channel_layout or 'no indicado'})",
            f"- Modelo: `{MODEL_NAME}` (Demucs 6 fuentes, ejecución CPU local)",
            "- Sesión interna: `WAV` PCM de 16 bits para reproducir y mezclar sin recodificación; los MP3 se generan bajo demanda a `320 kbps`.",
            f"- Selección: `{', '.join(sorted(selected))}`",
            "- Procesamiento: completamente local; no se ha subido el audio.",
            "",
            "## Archivos generados",
            "",
        ]
        lines.extend(f"- `{stem.path.name}` — {stem.kind}" for stem in stems)
        lines += [
            "",
            "## Notas",
            "",
            "`Other.wav` se calcula sumando el stem Other del modelo y todas las categorías no seleccionadas. "
            "Las salidas de guitarra y piano pueden contener más filtración y el bajo puede perder presencia cuando comparte graves con bombo o sintetizadores; son limitaciones conocidas del modelo htdemucs_6s.",
            "",
            f"Resultados: `{folder}`",
        ]
        return "\n".join(lines) + "\n"
