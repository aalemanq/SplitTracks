#!/usr/bin/env python3
"""Local audio operations used by StemForge.

The first Linux build deliberately uses a transparent stereo center/side
transform instead of shipping model weights with unclear redistribution
rights.  The engine is kept separate from the UI so an approved local ML
backend can be added later without changing the mixer workflow.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


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


ProgressCallback = Callable[[float, str], None]


def _run(command: list[str], *, capture_output: bool = True) -> subprocess.CompletedProcess[str]:
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
            "No encuentro FFmpeg. Instala ffmpeg y vuelve a abrir StemForge."
        ) from exc


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
    """FFmpeg-backed, local and deterministic audio processing."""

    def probe(self, path: str | Path) -> AudioInfo:
        audio_path = Path(path).expanduser().resolve()
        if not audio_path.is_file():
            raise AudioEngineError("El archivo de audio ya no está disponible.")

        result = _run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=format_name,duration:stream=codec_type,codec_name,sample_rate,channels,channel_layout,duration",
                "-of",
                "json",
                str(audio_path),
            ]
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

    def separate(
        self,
        input_path: str | Path,
        destination: str | Path,
        selected_categories: Iterable[str],
        progress: ProgressCallback | None = None,
        cancel_event=None,
    ) -> SeparationResult:
        info = self.probe(input_path)
        selected = set(selected_categories)
        if "vocals" not in selected:
            raise AudioEngineError(
                "La versión actual necesita seleccionar Voces: es la única separación local disponible."
            )
        if info.channels != 2:
            raise AudioEngineError(
                "El motor estéreo actual necesita una mezcla de 2 canales. "
                "La arquitectura queda preparada para añadir modelos multicanal."
            )
        if info.duration <= 0:
            raise AudioEngineError("La pista no tiene una duración válida para procesarse.")

        destination_path = Path(destination).expanduser().resolve()
        destination_path.mkdir(parents=True, exist_ok=True)
        folder = destination_path / f"StemForge - {_safe_name(info.path.stem)}"
        suffix = 2
        while folder.exists():
            folder = destination_path / f"StemForge - {_safe_name(info.path.stem)} ({suffix})"
            suffix += 1
        folder.mkdir(parents=True)

        vocals = folder / "Voces.wav"
        other = folder / "Other.wav"
        filter_graph = (
            "[0:a]pan=stereo|c0=0.5*c0+0.5*c1|c1=0.5*c0+0.5*c1[voces];"
            "[0:a]pan=stereo|c0=0.5*c0-0.5*c1|c1=-0.5*c0+0.5*c1[other]"
        )
        command = [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-y",
            "-progress",
            "pipe:1",
            "-i",
            str(info.path),
            "-filter_complex",
            filter_graph,
            "-map",
            "[voces]",
            "-c:a",
            "pcm_s24le",
            str(vocals),
            "-map",
            "[other]",
            "-c:a",
            "pcm_s24le",
            str(other),
        ]
        if progress:
            progress(0.04, "Preparando el motor local")
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        last_progress = 0.04
        output_time = 0.0
        try:
            assert process.stdout is not None
            for line in process.stdout:
                if cancel_event is not None and cancel_event.is_set():
                    process.terminate()
                    process.wait(timeout=5)
                    raise SeparationCancelled("Separación cancelada. No se han conservado archivos parciales.")
                line = line.strip()
                if line.startswith("out_time_ms="):
                    try:
                        output_time = int(line.split("=", 1)[1]) / 1_000_000
                    except ValueError:
                        pass
                    last_progress = min(0.92, 0.08 + 0.84 * output_time / info.duration)
                    if progress:
                        progress(last_progress, "Separando centro y lados de la mezcla")
            return_code = process.wait()
        except SeparationCancelled:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        except Exception:
            process.kill()
            process.wait()
            shutil.rmtree(folder, ignore_errors=True)
            raise

        if return_code != 0 or not vocals.is_file() or not other.is_file():
            shutil.rmtree(folder, ignore_errors=True)
            raise AudioEngineError(
                "FFmpeg no pudo completar la separación. Revisa el formato y los permisos de la carpeta."
            )

        if progress:
            progress(0.94, "Verificando que ambas pistas contienen señal")
        if not self._has_audio_signal(vocals) or not self._has_audio_signal(other):
            shutil.rmtree(folder, ignore_errors=True)
            raise AudioEngineError(
                "La mezcla no contiene suficiente información estéreo para producir dos pistas reales. "
                "No se ha creado un archivo silencioso para aparentar una separación."
            )

        stems = (
            StemFile("Voces", vocals, "#f4a7b9", "available"),
            StemFile("Other", other, "#a6b8ff", "complement"),
        )
        report_path = folder / "INFORME.md"
        report_path.write_text(self._report(info, folder, stems), encoding="utf-8")
        (folder / "PROVENANCE.json").write_text(
            json.dumps(
                {
                    "application": "StemForge",
                    "method": "stereo-center-side-v1",
                    "method_type": "deterministic DSP, not machine learning",
                    "input": str(info.path),
                    "input_sha256": _sha256(info.path),
                    "outputs": [
                        {"name": stem.name, "path": stem.path.name, "sha256": _sha256(stem.path)}
                        for stem in stems
                    ],
                    "license_note": "No model weights are distributed by this build.",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if progress:
            progress(1.0, "Separación completada")
        return SeparationResult(folder, stems, report_path)

    def mix(
        self,
        stems: Iterable[dict],
        destination: str | Path,
        sample_rate: int,
        channels: int,
        progress: ProgressCallback | None = None,
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
        output = Path(destination) / "StemForge - mezcla.wav"
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
            "ffmpeg",
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
            "-c:a",
            "pcm_s24le",
            str(output),
        ]
        if progress:
            progress(0.12, "Mezclando las pistas sincrónicamente")
        result = _run(command)
        if result.returncode != 0 or not output.is_file():
            raise AudioEngineError("No se pudo exportar la mezcla WAV.")
        warning = None
        peak = self._max_volume(output)
        if peak is not None and peak > 0:
            warning = f"La mezcla alcanza {peak:+.1f} dBFS y puede recortar; se ha exportado sin normalizar."
        if progress:
            progress(1.0, "Mezcla exportada")
        return output, warning

    def _has_audio_signal(self, path: Path) -> bool:
        return self._max_volume(path) is not None

    def _max_volume(self, path: Path) -> float | None:
        result = _run(
            ["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        )
        text = result.stderr or result.stdout
        match = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", text)
        if not match:
            return None
        value = float(match.group(1))
        return None if value <= -90 else value

    def _report(self, info: AudioInfo, folder: Path, stems: tuple[StemFile, ...]) -> str:
        lines = [
            "# Informe de separación — StemForge",
            "",
            f"- Entrada: `{info.filename}`",
            f"- Duración: `{info.duration_label}`",
            f"- Formato detectado: `{info.format_name}`",
            f"- Muestreo: `{info.sample_rate_label}`",
            f"- Canales: `{info.channels}` ({info.channel_layout or 'no indicado'})",
            "- Método: transformación determinista estéreo centro/lados mediante FFmpeg.",
            "- Procesamiento: completamente local; no se ha subido el audio.",
            "- Modelos de IA: ninguno incluido en esta compilación.",
            "",
            "## Archivos generados",
            "",
        ]
        lines.extend(f"- `{stem.path.name}` — {stem.kind}" for stem in stems)
        lines += [
            "",
            "## Limitaciones conocidas",
            "",
            "Esta versión extrae el contenido central y lateral de una mezcla estéreo. "
            "No equivale a una separación vocal entrenada y puede contener filtración. "
            "Las categorías de batería, bajo, guitarras, piano y detalles vocales permanecen bloqueadas "
            "hasta integrar un modelo con licencia de pesos verificable.",
            "",
            f"Resultados: `{folder}`",
        ]
        return "\n".join(lines) + "\n"
