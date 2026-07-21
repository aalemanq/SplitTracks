#!/usr/bin/env python3
"""Lightweight local music analysis for Split Tracks.

The analysis intentionally uses the NumPy already required by the CPU build and
FFmpeg for decoding/loudness. It is designed as a best-effort companion to the
audio engine: separation never depends on BPM or key detection succeeding.
"""

from __future__ import annotations

import math
import os
import re
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np


class AnalysisError(RuntimeError):
    """A non-fatal audio-analysis error."""


class AnalysisCancelled(AnalysisError):
    """The user cancelled an in-progress analysis subprocess."""


NOTE_NAMES = ("C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B")
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
SAMPLE_RATE = 11025
FFT_SIZE = 2048
HOP_SIZE = 512
ANALYSIS_DURATION_SECONDS = 180.0


def _signal_process_tree(process: subprocess.Popen, *, force: bool = False) -> None:
    signal_value = signal.SIGKILL if force else signal.SIGTERM
    try:
        os.killpg(os.getpgid(process.pid), signal_value)
    except (ProcessLookupError, PermissionError):
        try:
            (process.kill if force else process.terminate)()
        except ProcessLookupError:
            pass



@dataclass(frozen=True)
class ChordEvent:
    start: float
    end: float
    label: str
    confidence: float

    def as_dict(self) -> dict[str, object]:
        return {
            "start": self.start,
            "end": self.end,
            "label": self.label,
            "confidence": self.confidence,
        }


def chord_degree(label: str, key_name: str | None, scale: str | None) -> str:
    if label in {"", "N"} or not key_name or not scale:
        return "—"
    root_text = label[:2] if len(label) > 1 and label[1] in {"♯", "#"} else label[:1]
    quality = label[len(root_text):]
    try:
        root = NOTE_NAMES.index(root_text.replace("#", "♯"))
        tonic = NOTE_NAMES.index(key_name.replace("#", "♯"))
    except ValueError:
        return "—"

    if scale == "mayor":
        offsets = (0, 2, 4, 5, 7, 9, 11)
    else:
        offsets = (0, 2, 3, 5, 7, 8, 10)
    numerals = ("I", "II", "III", "IV", "V", "VI", "VII")
    semitones = (root - tonic) % 12
    if semitones in offsets:
        index = offsets.index(semitones)
        accidental = ""
    else:
        nearby = min(range(7), key=lambda position: min(
            (semitones - offsets[position]) % 12,
            (offsets[position] - semitones) % 12,
        ))
        index = nearby
        difference = (semitones - offsets[index]) % 12
        accidental = "♯" if difference == 1 else "♭" if difference == 11 else "?"
    numeral = numerals[index]
    if quality == "m":
        numeral = numeral.lower()
    elif quality == "dim":
        numeral = numeral.lower() + "°"
    return accidental + numeral


def transpose_note_name(name: str | None, semitones: int) -> str | None:
    if not name:
        return name
    try:
        index = NOTE_NAMES.index(name.replace("#", "♯"))
    except ValueError:
        return name
    return NOTE_NAMES[(index + semitones) % 12]


def transpose_chord_label(label: str, semitones: int) -> str:
    if not label or label == "N" or semitones == 0:
        return label
    root_text = label[:2] if len(label) > 1 and label[1] in {"♯", "#"} else label[:1]
    root = transpose_note_name(root_text, semitones)
    return f"{root}{label[len(root_text):]}" if root else label


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
    chords: tuple[ChordEvent, ...] = ()

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

    @property
    def compact_chords(self) -> tuple[ChordEvent, ...]:
        compact: list[ChordEvent] = []
        previous_label: str | None = None
        for event in self.chords:
            if event.label == "N" or event.label == previous_label:
                continue
            compact.append(event)
            previous_label = event.label
        return tuple(compact)

    @property
    def chord_summary(self) -> str:
        items = []
        for event in self.compact_chords:
            minutes, seconds = divmod(max(0, int(event.start)), 60)
            items.append(f"{minutes}:{seconds:02d} {event.label}")
        if not items:
            return "Progresión de acordes no disponible"
        if len(items) > 24:
            items = [*items[:24], "…"]
        valid_events = [event for event in self.chords if event.label != "N"]
        confidence = (
            sum(event.confidence for event in valid_events) / len(valid_events)
            if valid_events
            else 0.0
        )
        return f"Progresión: {'  ·  '.join(items)}  ·  confianza {confidence:.0%}"

    @property
    def degree_sequence(self) -> tuple[str, ...]:
        return self.degree_sequence_for(0)

    def transposed_compact_chords(self, semitones: int) -> tuple[ChordEvent, ...]:
        return tuple(
            ChordEvent(
                start=event.start,
                end=event.end,
                label=transpose_chord_label(event.label, semitones),
                confidence=event.confidence,
            )
            for event in self.compact_chords
        )

    def degree_sequence_for(self, semitones: int) -> tuple[str, ...]:
        shifted_key = transpose_note_name(self.key_name, semitones)
        return tuple(
            chord_degree(transpose_chord_label(event.label, semitones), shifted_key, self.scale)
            for event in self.compact_chords
        )

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
            "chords": [event.as_dict() for event in self.chords],
        }


def _run_analysis_process(command: list[str], *, text: bool, cancel_event=None):
    if cancel_event is None:
        try:
            return subprocess.run(command, check=False, capture_output=True, text=text)
        except FileNotFoundError as exc:
            raise AnalysisError("No encuentro FFmpeg para analizar el audio.") from exc

    if cancel_event.is_set():
        raise AnalysisCancelled("Análisis cancelado por el usuario.")
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=text,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        raise AnalysisError("No encuentro FFmpeg para analizar el audio.") from exc

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
            raise AnalysisCancelled("Análisis cancelado por el usuario.")


def _decode_mono(path: Path, cancel_event=None) -> np.ndarray:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-t",
        str(ANALYSIS_DURATION_SECONDS),
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
        "-f",
        "f32le",
        "pipe:1",
    ]
    result = _run_analysis_process(command, text=False, cancel_event=cancel_event)
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
    raw_values: list[float] = []
    for low, high in zip(edges[:-1], edges[1:]):
        band = power[:, (frequencies >= low) & (frequencies < high)]
        raw_values.append(float(band.mean()) if band.size else 0.0)
    peak = max(max(raw_values, default=0.0), 1e-12)
    return tuple(
        max(-60.0, min(0.0, 10.0 * math.log10(max(value, 1e-12) / peak)))
        for value in raw_values
    )


def _chroma_frames(power: np.ndarray, frequencies: np.ndarray) -> np.ndarray:
    mask = (frequencies >= 65) & (frequencies <= 2500)
    if not np.any(mask):
        return np.empty((power.shape[0], 0), dtype=np.float32)
    selected = frequencies[mask]
    midi = np.rint(69 + 12 * np.log2(selected / 440.0)).astype(int) % 12
    amplitudes = np.sqrt(power[:, mask])
    chroma = np.zeros((power.shape[0], 12), dtype=np.float64)
    for pitch_class in range(12):
        chroma[:, pitch_class] = amplitudes[:, midi == pitch_class].sum(axis=1)
    norms = np.linalg.norm(chroma, axis=1, keepdims=True)
    return (chroma / np.maximum(norms, 1e-12)).astype(np.float32)



def _root_index(label: str) -> int | None:
    if label in {"", "N"}:
        return None
    root_text = label[:2] if len(label) > 1 and label[1] in {"♯", "#"} else label[:1]
    try:
        return NOTE_NAMES.index(root_text.replace("#", "♯"))
    except ValueError:
        return None


def _is_major_chord(label: str) -> bool:
    root = _root_index(label)
    if root is None:
        return False
    root_text = NOTE_NAMES[root]
    return label == root_text


def _merge_adjacent_chords(events: list[ChordEvent]) -> list[ChordEvent]:
    merged: list[ChordEvent] = []
    for event in events:
        if merged and merged[-1].label == event.label:
            previous = merged[-1]
            merged[-1] = ChordEvent(
                start=previous.start,
                end=event.end,
                label=event.label,
                confidence=(previous.confidence + event.confidence) / 2.0,
            )
        else:
            merged.append(event)
    return merged


def _stabilize_chords(
    events: tuple[ChordEvent, ...],
    key_name: str | None,
    scale: str | None,
    segment_seconds: float,
) -> tuple[ChordEvent, ...]:
    if not events:
        return ()
    stable = list(events)

    # In a major key, I–III–IV–iv is a common chromatic pattern. If the
    # repeated III position contains any major evidence, use that quality for
    # the same contextual position instead of allowing B/Bm-style flicker.
    try:
        tonic = NOTE_NAMES.index((key_name or "").replace("#", "♯"))
    except ValueError:
        tonic = None
    if tonic is not None and scale == "mayor":
        chromatic_third = (tonic + 4) % 12
        subdominant = (tonic + 5) % 12
        promote_third = False
        for index, event in enumerate(stable):
            if _root_index(event.label) != chromatic_third:
                continue
            left = index - 1
            while left >= 0 and _root_index(stable[left].label) == chromatic_third:
                left -= 1
            right = index + 1
            while right < len(stable) and _root_index(stable[right].label) == chromatic_third:
                right += 1
            if left >= 0 and right < len(stable):
                if _root_index(stable[left].label) == tonic and _root_index(stable[right].label) == subdominant:
                    group = stable[left + 1:right]
                    if any(_is_major_chord(candidate.label) for candidate in group):
                        promote_third = True
                        break
        if promote_third:
            major_label = NOTE_NAMES[chromatic_third]
            for index, event in enumerate(stable):
                if _root_index(event.label) == chromatic_third:
                    stable[index] = ChordEvent(event.start, event.end, major_label, event.confidence)

    stable = _merge_adjacent_chords(stable)
    short_limit = max(0.8, segment_seconds * 1.15)
    for index in range(1, len(stable) - 1):
        event = stable[index]
        if event.label == "N" or event.end - event.start > short_limit or event.confidence > 0.13:
            continue
        previous = stable[index - 1]
        following = stable[index + 1]
        previous_root = _root_index(previous.label)
        following_root = _root_index(following.label)
        if previous_root == following_root or (previous.end - previous.start) >= (following.end - following.start):
            replacement = previous
        else:
            replacement = following
        stable[index] = ChordEvent(event.start, event.end, replacement.label, event.confidence)

    return tuple(_merge_adjacent_chords(stable))


def _detect_chords(
    chroma: np.ndarray,
    bpm: float | None,
    duration: float,
    key_name: str | None = None,
    scale: str | None = None,
) -> tuple[ChordEvent, ...]:
    if chroma.size == 0 or chroma.shape[0] < 4:
        return ()
    hop_seconds = HOP_SIZE / SAMPLE_RATE
    segment_seconds = 1.5 if bpm is None else max(0.75, min(2.0, 120.0 / bpm))
    frames_per_segment = max(4, round(segment_seconds / hop_seconds))
    templates: list[tuple[str, tuple[int, ...], tuple[float, ...]]] = [
        ("", (0, 4, 7), (1.0, 0.82, 0.92)),
        ("m", (0, 3, 7), (1.0, 0.86, 0.92)),
    ]
    events: list[ChordEvent] = []
    for start_frame in range(0, chroma.shape[0], frames_per_segment):
        end_frame = min(chroma.shape[0], start_frame + frames_per_segment)
        block = chroma[start_frame:end_frame]
        if block.shape[0] < max(3, frames_per_segment // 3):
            break
        profile = block.mean(axis=0)
        energy = float(np.linalg.norm(profile))
        if energy < 1e-5:
            label = "N"
            confidence = 0.0
        else:
            candidates: list[tuple[float, str]] = []
            for root in range(12):
                for suffix, intervals, weights in templates:
                    template = np.zeros(12, dtype=np.float64)
                    for interval, weight in zip(intervals, weights):
                        template[(root + interval) % 12] = weight
                    score = float(np.dot(profile, template) / (energy * np.linalg.norm(template)))
                    candidates.append((score, NOTE_NAMES[root] + suffix))
            candidates.sort(reverse=True)
            best_score, label = candidates[0]
            second_score = candidates[1][0]
            confidence = max(0.0, min(1.0, (best_score - second_score) / max(best_score, 1e-9)))
            if best_score < 0.42:
                label = "N"
        start = min(duration, start_frame * hop_seconds)
        end = min(duration, end_frame * hop_seconds)
        if end <= start:
            continue
        if events and events[-1].label == label:
            previous = events[-1]
            events[-1] = ChordEvent(
                start=previous.start,
                end=end,
                label=label,
                confidence=(previous.confidence + confidence) / 2.0,
            )
        else:
            events.append(ChordEvent(start=start, end=end, label=label, confidence=confidence))
    return _stabilize_chords(tuple(events), key_name, scale, segment_seconds)


def _measure_loudness(path: Path, cancel_event=None) -> float | None:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-nostats",
        "-i",
        str(path),
        "-t",
        str(ANALYSIS_DURATION_SECONDS),
        "-filter_complex",
        "ebur128=framelog=verbose",
        "-f",
        "null",
        "-",
    ]
    try:
        result = _run_analysis_process(command, text=True, cancel_event=cancel_event)
    except FileNotFoundError:
        return None
    match = re.findall(r"\bI:\s*(-?\d+(?:\.\d+)?)\s*LUFS", result.stderr)
    return float(match[-1]) if match else None


def analyze_audio(path: str | Path, *, detect_chords: bool = False, cancel_event=None) -> AudioAnalysis:
    """Extract fast metadata, optionally retaining the legacy chord estimate.

    Human chord charts are now the canonical source in the application. Keeping
    the old detector behind an opt-in flag preserves it for diagnostics and
    tests without making every upload pay its extra chroma-analysis cost.
    """
    audio_path = Path(path).expanduser().resolve()
    if not audio_path.is_file():
        raise AnalysisError("El archivo ya no está disponible para analizarlo.")
    samples = _decode_mono(audio_path, cancel_event=cancel_event)
    frames = _frames(samples)
    window = np.hanning(FFT_SIZE).astype(np.float32)
    magnitude = np.abs(np.fft.rfft(frames * window, axis=1))
    power = magnitude**2
    frequencies = np.fft.rfftfreq(FFT_SIZE, 1.0 / SAMPLE_RATE)
    bpm, tempo_confidence = _detect_tempo(magnitude)
    key_name, scale, key_confidence = _detect_key(power, frequencies)
    chords: tuple[ChordEvent, ...] = ()
    if detect_chords:
        chroma = _chroma_frames(power, frequencies)
        chords = _detect_chords(chroma, bpm, samples.size / SAMPLE_RATE, key_name, scale)
    peak_dbfs = _db(float(np.max(np.abs(samples))))
    return AudioAnalysis(
        bpm=bpm,
        tempo_confidence=tempo_confidence,
        key_name=key_name,
        scale=scale,
        key_confidence=key_confidence,
        lufs=_measure_loudness(audio_path, cancel_event=cancel_event),
        peak_dbfs=peak_dbfs,
        dynamic_range_db=_dynamic_range(frames),
        spectrum=_spectrum(power, frequencies),
        chords=chords,
    )

