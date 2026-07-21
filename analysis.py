#!/usr/bin/env python3
"""Lightweight local music analysis for Split Tracks.

The analysis intentionally uses the NumPy already required by the CPU build and
FFmpeg for decoding/loudness. It is designed as a best-effort companion to the
audio engine: separation never depends on BPM or key detection succeeding.
"""

from __future__ import annotations

import math
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np


class AnalysisError(RuntimeError):
    """A non-fatal audio-analysis error."""


NOTE_NAMES = ("C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B")
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
SAMPLE_RATE = 11025
FFT_SIZE = 2048
HOP_SIZE = 512


@dataclass(frozen=True)
class AudioAnalysis:
    bpm: float | None
    tempo_confidence: float | None
    key_name: str | None
    scale: str | None
    key_confidence: float | None
    lufs: float | None
    peak_dbfs: float | None
    dynamic_range_db: float | None
    spectrum: tuple[float, ...]

    @property
    def key_label(self) -> str | None:
        if not self.key_name or not self.scale:
            return None
        return f"{self.key_name} {self.scale}"

    @property
    def summary(self) -> str:
        parts: list[str] = []
        if self.bpm is not None:
            parts.append(f"BPM {self.bpm:.0f}")
        if self.key_label:
            parts.append(self.key_label)
        if self.lufs is not None:
            parts.append(f"{self.lufs:.1f} LUFS")
        if self.dynamic_range_db is not None:
            parts.append(f"Dinámica {self.dynamic_range_db:.1f} dB")
        return "  ·  ".join(parts) or "Análisis musical no disponible"

    def as_dict(self) -> dict[str, object]:
        return {
            "bpm": self.bpm,
            "tempo_confidence": self.tempo_confidence,
            "key_name": self.key_name,
            "scale": self.scale,
            "key_confidence": self.key_confidence,
            "lufs": self.lufs,
            "peak_dbfs": self.peak_dbfs,
            "dynamic_range_db": self.dynamic_range_db,
            "spectrum": list(self.spectrum),
        }


def _decode_mono(path: Path) -> np.ndarray:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
        "-f",
        "f32le",
        "pipe:1",
    ]
    try:
        result = subprocess.run(command, check=False, capture_output=True)
    except FileNotFoundError as exc:
        raise AnalysisError("No encuentro FFmpeg para analizar el audio.") from exc
    if result.returncode != 0:
        raise AnalysisError("FFmpeg no pudo decodificar el audio para analizarlo.")
    samples = np.frombuffer(result.stdout, dtype=np.float32).copy()
    if samples.size < FFT_SIZE:
        raise AnalysisError("El audio es demasiado corto para calcular su análisis musical.")
    return samples


def _frames(samples: np.ndarray) -> np.ndarray:
    count = 1 + (samples.size - FFT_SIZE) // HOP_SIZE
    return np.lib.stride_tricks.as_strided(
        samples,
        shape=(count, FFT_SIZE),
        strides=(samples.strides[0] * HOP_SIZE, samples.strides[0]),
        writeable=False,
    )


def _db(value: float) -> float:
    return 20.0 * math.log10(max(float(value), 1e-12))


def _dynamic_range(frames: np.ndarray) -> float | None:
    rms = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1))
    active = rms[rms > 1e-5]
    if active.size < 2:
        return None
    return float(_db(np.percentile(active, 95)) - _db(np.percentile(active, 10)))


def _detect_tempo(magnitude: np.ndarray) -> tuple[float | None, float | None]:
    onset = np.maximum(np.diff(np.log1p(magnitude), axis=0), 0).sum(axis=1)
    if onset.size < 12 or float(np.std(onset)) < 1e-8:
        return None, None
    onset = (onset - onset.mean()) / (onset.std() + 1e-9)
    autocorrelation = np.correlate(onset, onset, mode="full")[onset.size - 1 :]
    min_lag = max(1, int(SAMPLE_RATE * 60 / (220 * HOP_SIZE)))
    max_lag = min(autocorrelation.size - 1, int(SAMPLE_RATE * 60 / (40 * HOP_SIZE)))
    if max_lag <= min_lag:
        return None, None
    region = autocorrelation[min_lag : max_lag + 1]
    peak_index = int(np.argmax(region))
    lag = float(min_lag + peak_index)
    if 0 < peak_index < region.size - 1:
        left = float(region[peak_index - 1])
        centre = float(region[peak_index])
        right = float(region[peak_index + 1])
        denominator = left - 2.0 * centre + right
        if abs(denominator) > 1e-9:
            lag += 0.5 * (left - right) / denominator
    bpm = 60.0 * SAMPLE_RATE / (lag * HOP_SIZE)
    while bpm < 80:
        bpm *= 2
    while bpm > 180:
        bpm /= 2
    baseline = float(np.median(region))
    confidence = max(0.0, min(1.0, (float(region.max()) - baseline) / (abs(float(region.max())) + 1e-9)))
    return float(bpm), float(confidence)


def _detect_key(power: np.ndarray, frequencies: np.ndarray) -> tuple[str | None, str | None, float | None]:
    mask = (frequencies >= 55) & (frequencies <= 5000)
    if not np.any(mask):
        return None, None, None
    selected = frequencies[mask]
    midi = np.rint(69 + 12 * np.log2(selected / 440.0)).astype(int) % 12
    chroma = np.zeros(12, dtype=np.float64)
    selected_power = power[:, mask].mean(axis=0)
    for pitch_class in range(12):
        chroma[pitch_class] = selected_power[midi == pitch_class].sum()
    if float(chroma.sum()) <= 1e-10:
        return None, None, None
    chroma /= np.linalg.norm(chroma) + 1e-12
    candidates: list[tuple[float, str, str]] = []
    for tonic in range(12):
        major = np.roll(MAJOR_PROFILE, tonic)
        minor = np.roll(MINOR_PROFILE, tonic)
        candidates.append((float(np.dot(chroma, major / np.linalg.norm(major))), NOTE_NAMES[tonic], "mayor"))
        candidates.append((float(np.dot(chroma, minor / np.linalg.norm(minor))), NOTE_NAMES[tonic], "menor"))
    candidates.sort(reverse=True)
    best = candidates[0]
    second = candidates[1][0]
    confidence = max(0.0, min(1.0, (best[0] - second) / (abs(best[0]) + 1e-12)))
    return best[1], best[2], float(confidence)


def _spectrum(power: np.ndarray, frequencies: np.ndarray) -> tuple[float, ...]:
    edges = np.geomspace(40, min(8000, SAMPLE_RATE / 2), 48)
    values: list[float] = []
    peak = max(float(power.mean()), 1e-12)
    for low, high in zip(edges[:-1], edges[1:]):
        band = power[:, (frequencies >= low) & (frequencies < high)]
        value = float(band.mean()) if band.size else 0.0
        values.append(max(-60.0, min(0.0, 10.0 * math.log10(max(value, 1e-12) / peak))))
    return tuple(values)


def _measure_loudness(path: Path) -> float | None:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-i",
        str(path),
        "-filter_complex",
        "ebur128=framelog=verbose",
        "-f",
        "null",
        "-",
    ]
    try:
        result = subprocess.run(command, check=False, text=True, capture_output=True, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return None
    match = re.findall(r"\bI:\s*(-?\d+(?:\.\d+)?)\s*LUFS", result.stderr)
    return float(match[-1]) if match else None


def analyze_audio(path: str | Path) -> AudioAnalysis:
    audio_path = Path(path).expanduser().resolve()
    if not audio_path.is_file():
        raise AnalysisError("El archivo ya no está disponible para analizarlo.")
    samples = _decode_mono(audio_path)
    frames = _frames(samples)
    window = np.hanning(FFT_SIZE).astype(np.float32)
    magnitude = np.abs(np.fft.rfft(frames * window, axis=1))
    power = magnitude**2
    frequencies = np.fft.rfftfreq(FFT_SIZE, 1.0 / SAMPLE_RATE)
    bpm, tempo_confidence = _detect_tempo(magnitude)
    key_name, scale, key_confidence = _detect_key(power, frequencies)
    peak_dbfs = _db(float(np.max(np.abs(samples))))
    return AudioAnalysis(
        bpm=bpm,
        tempo_confidence=tempo_confidence,
        key_name=key_name,
        scale=scale,
        key_confidence=key_confidence,
        lufs=_measure_loudness(audio_path),
        peak_dbfs=peak_dbfs,
        dynamic_range_db=_dynamic_range(frames),
        spectrum=_spectrum(power, frequencies),
    )

