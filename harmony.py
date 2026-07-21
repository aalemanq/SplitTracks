#!/usr/bin/env python3
"""Human-sourced chord charts and reliable chord transposition.

The audio analyser remains useful for BPM, loudness and a best-effort key
estimate, but it is deliberately not used as the canonical chord source.
This module keeps source-specific scraping behind a small provider interface so
the GTK application can add more sites without changing its chart model.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover - explained to the user at runtime
    requests = None
    BeautifulSoup = None


class HarmonyError(RuntimeError):
    """A user-facing error raised while finding or parsing a chord chart."""


NOTE_NAMES_SHARP = ("C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B")
NOTE_NAMES_FLAT = ("C", "D♭", "D", "E♭", "E", "F", "G♭", "G", "A♭", "A", "B♭", "B")
NOTE_TO_PITCH = {
    "C": 0,
    "B#": 0,
    "C#": 1,
    "C♯": 1,
    "Db": 1,
    "D♭": 1,
    "D": 2,
    "D#": 3,
    "D♯": 3,
    "Eb": 3,
    "E♭": 3,
    "E": 4,
    "Fb": 4,
    "F♭": 4,
    "E#": 5,
    "F": 5,
    "F#": 6,
    "F♯": 6,
    "Gb": 6,
    "G♭": 6,
    "G": 7,
    "G#": 8,
    "G♯": 8,
    "Ab": 8,
    "A♭": 8,
    "A": 9,
    "A#": 10,
    "A♯": 10,
    "Bb": 10,
    "B♭": 10,
    "B": 11,
}
MAJOR_OFFSETS = (0, 2, 4, 5, 7, 9, 11)
MINOR_OFFSETS = (0, 2, 3, 5, 7, 8, 10)
MAJOR_NUMERALS = ("I", "II", "III", "IV", "V", "VI", "VII")
MINOR_NUMERALS = ("i", "ii", "III", "iv", "v", "VI", "VII")
CHORD_ROOT_RE = re.compile(r"^(?P<root>[A-G](?:[#♯b♭]{1,2})?)(?P<suffix>.*)$")
KEY_RE = re.compile(r"(?:tonalidad|tono|tom)\s*[:：]?\s*([A-G](?:[#♯b♭])?)", re.IGNORECASE)
CAPO_RE = re.compile(r"(?:capo|cejilla)\s*[:：-]?\s*(?:traste\s*)?(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class ChordLine:
    """One source line, retaining order and explicit bar separators."""

    chords: tuple[str, ...]
    bars: int = 0


@dataclass(frozen=True)
class ChordSection:
    title: str
    lines: tuple[ChordLine, ...]


@dataclass(frozen=True)
class ChordCandidate:
    source_id: str
    source_name: str
    url: str
    artist: str
    title: str
    version: str
    instrument: str = ""
    key_name: str | None = None
    scale: str | None = None
    capo: int | None = None
    reviewed: bool = False
    rating: float | None = None
    votes: int | None = None


@dataclass(frozen=True)
class ChordChart:
    source_id: str
    source_name: str
    url: str
    artist: str
    title: str
    version: str
    key_name: str | None
    scale: str | None
    capo: int | None
    reviewed: bool
    instrument: str
    sections: tuple[ChordSection, ...]

    @property
    def all_chords(self) -> tuple[str, ...]:
        return tuple(chord for section in self.sections for line in section.lines for chord in line.chords)

    @property
    def compact_chords(self) -> tuple[str, ...]:
        compact: list[str] = []
        for chord in self.all_chords:
            if chord and (not compact or compact[-1] != chord):
                compact.append(chord)
        return tuple(compact)

    @property
    def chord_count(self) -> int:
        return len(dict.fromkeys(self.all_chords))

    @property
    def display_key(self) -> str | None:
        if not self.key_name:
            return None
        return f"{self.key_name} {self.scale}" if self.scale else self.key_name

    def transposed_sections(self, semitones: int) -> tuple[ChordSection, ...]:
        return tuple(
            ChordSection(
                section.title,
                tuple(
                    ChordLine(
                        tuple(transpose_chord(chord, semitones, key_name=self.key_name) for chord in line.chords),
                        line.bars,
                    )
                    for line in section.lines
                ),
            )
            for section in self.sections
        )

    def transposed_key(self, semitones: int) -> str | None:
        return transpose_note(self.key_name, semitones, key_name=self.key_name) if self.key_name else None

    def degrees(self, semitones: int = 0) -> tuple[ChordSection, ...]:
        shifted_key = self.transposed_key(semitones)
        return tuple(
            ChordSection(
                section.title,
                tuple(
                    ChordLine(
                        tuple(
                            chord_degree(
                                transpose_chord(chord, semitones, key_name=self.key_name),
                                shifted_key,
                                self.scale,
                            )
                            for chord in line.chords
                        ),
                        line.bars,
                    )
                    for line in section.lines
                ),
            )
            for section in self.sections
        )


def _require_web_dependencies() -> None:
    if requests is None or BeautifulSoup is None:
        raise HarmonyError(
            "Faltan las librerías de búsqueda de acordes. Ejecuta setup-model.sh para instalarlas."
        )


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", normalized.lower()).strip("-")
    return normalized


def _clean_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _normal_note(value: str) -> str:
    return value.replace("#", "♯").replace("b", "♭")


def _note_pitch(value: str) -> int | None:
    return NOTE_TO_PITCH.get(value) or (0 if value in {"C", "B#"} else None)


def _parse_key(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    labelled = re.search(
        r"(?:tonalidad|tono|tom|key)\s*[:：]?\s*"
        r"([A-G](?:[#♯b♭])?)(?:\s*(major|minor|mayor|menor|maj|min|m))?",
        value,
        re.IGNORECASE,
    )
    match = labelled or re.search(
        r"(?<![A-Za-z])([A-G](?:[#♯b♭])?)"
        r"(?:\s*(major|minor|mayor|menor|maj|min|m))?",
        value,
        re.IGNORECASE,
    )
    if not match:
        return None, None
    note = _normal_note(match.group(1))
    mode = match.group(2)
    scale = None
    if mode and mode.lower() in {"minor", "menor", "min", "m"}:
        scale = "menor"
    elif mode:
        scale = "mayor"
    return note, scale


def _preferred_note(pitch: int, key_name: str | None = None) -> str:
    use_flats = any(char in (key_name or "") for char in ("♭", "b")) or pitch % 12 in {1, 3, 8, 10}
    names = NOTE_NAMES_FLAT if use_flats else NOTE_NAMES_SHARP
    return names[pitch % 12]


def _split_chord(label: str) -> tuple[str, str, str | None] | None:
    clean = label.strip().replace("−", "-")
    if not clean or clean.upper() in {"N", "NC", "N.C.", "—", "-"}:
        return None
    parts = clean.split("/", 1)
    match = CHORD_ROOT_RE.match(parts[0])
    if not match:
        return None
    bass = None
    if len(parts) == 2:
        bass_match = CHORD_ROOT_RE.match(parts[1].strip())
        if bass_match and not bass_match.group("suffix"):
            bass = bass_match.group("root")
    return match.group("root"), match.group("suffix"), bass


def transpose_note(note: str | None, semitones: int, *, key_name: str | None = None) -> str | None:
    if not note:
        return note
    pitch = _note_pitch(note)
    if pitch is None:
        return note
    return _preferred_note(pitch + semitones, key_name=transpose_note(key_name, semitones) if key_name else key_name)


def transpose_chord(label: str, semitones: int, *, key_name: str | None = None) -> str:
    if not label or semitones == 0:
        return label
    parsed = _split_chord(label)
    if not parsed:
        return label
    root, suffix, bass = parsed
    new_root = transpose_note(root, semitones, key_name=key_name) or root
    result = f"{new_root}{suffix}"
    if bass:
        new_bass = transpose_note(bass, semitones, key_name=key_name) or bass
        result = f"{result}/{new_bass}"
    return result


def chord_degree(label: str, key_name: str | None, scale: str | None) -> str:
    parsed = _split_chord(label)
    tonic = _note_pitch(key_name or "")
    if not parsed or tonic is None:
        return "—"
    root, suffix, _bass = parsed
    root_pitch = _note_pitch(root)
    if root_pitch is None:
        return "—"
    minor = scale == "menor"
    offsets = MINOR_OFFSETS if minor else MAJOR_OFFSETS
    numerals = MINOR_NUMERALS if minor else MAJOR_NUMERALS
    interval = (root_pitch - tonic) % 12
    if interval in offsets:
        index = offsets.index(interval)
        accidental = ""
    else:
        distances = [min((interval - value) % 12, (value - interval) % 12) for value in offsets]
        index = distances.index(min(distances))
        delta = (interval - offsets[index]) % 12
        accidental = "♯" if delta == 1 else "♭" if delta == 11 else ""
    numeral = numerals[index]
    quality = suffix.lower()
    if quality.startswith(("dim", "°", "o")):
        numeral = numeral.lower() + "°"
    elif quality.startswith(("m", "min", "-")):
        numeral = numeral.lower()
    return accidental + numeral


def _guess_scale(key_name: str | None, chords: Iterable[str]) -> str | None:
    if not key_name:
        return None
    tonic = _note_pitch(key_name)
    if tonic is None:
        return None
    first = next(iter(chords), "")
    parsed = _split_chord(first)
    if parsed and parsed[1].lower().startswith(("m", "min")):
        return "menor"
    return "mayor"


def _parse_capo(text: str) -> int | None:
    if re.search(r"(?:sin|sem)\s+capo", text, re.IGNORECASE):
        return 0
    match = CAPO_RE.search(text)
    return int(match.group(1)) if match else None


def _translation_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", _clean_text(value))
    return "".join(char for char in normalized if not unicodedata.combining(char)).casefold()


SECTION_TRANSLATIONS = {
    "primeira parte": "Primera parte",
    "segunda parte": "Segunda parte",
    "terceira parte": "Tercera parte",
    "quarta parte": "Cuarta parte",
    "refrão": "Estribillo",
    "refrao": "Estribillo",
    "coro": "Estribillo",
    "ponte": "Puente",
    "pré-refrão": "Preestribillo",
    "pre-refrao": "Preestribillo",
    "verso": "Verso",
    "intro": "Intro",
    "final": "Final",
}


def _spanish_section_title(value: str) -> str:
    return SECTION_TRANSLATIONS.get(_translation_key(value), _clean_text(value))


def _spanish_instrument(value: str) -> str:
    key = _translation_key(value)
    if key == "violao":
        return "Guitarra"
    if key == "guitarra":
        return "Guitarra"
    if key == "teclado":
        return "Teclado"
    if key == "baixo":
        return "Bajo"
    if key == "bateria":
        return "Batería"
    return _clean_text(value)


def _version_label(value: str) -> str:
    clean = _clean_text(value)
    lowered = _translation_key(clean)
    if "simplificada" in lowered or "simplificar cifra" in lowered or "simplificar acordes" in lowered:
        return "Simplificada"
    if "acustica" in lowered:
        return "Acústica"
    if "violao" in lowered:
        return "Guitarra"
    if "teclado" in lowered:
        return "Teclado"
    version_match = re.search(r"vers(?:ão|ión)\s+(\d+)", clean, re.IGNORECASE)
    if version_match:
        return f"Versión {version_match.group(1)}"
    if "indefinida" in lowered:
        return "Otra versión"
    if "principal" in lowered:
        return "Principal"
    fallback = re.split(r"\s+(?:b[aá]sico|intermedi[aá]rio)\b", clean, maxsplit=1, flags=re.IGNORECASE)[0]
    return _spanish_instrument(fallback) or "Versión"


def _parse_source_metadata(soup, fallback_key: str | None = None) -> tuple[str | None, str | None, int | None, str, bool]:
    text = _clean_text(soup.get_text(" ", strip=True))
    key_match = KEY_RE.search(text)
    key_name, scale = _parse_key(key_match.group(0) if key_match else fallback_key)
    capo = _parse_capo(text)
    instrument = ""
    marker = re.search(r"(?:instrumento|instrument|instrumento musical)\s+(.{0,70})", text, re.IGNORECASE)
    if marker:
        instrument = _spanish_instrument(marker.group(1).split("Tono", 1)[0].split("Tom", 1)[0].strip(" ·|"))
    reviewed = bool(re.search(r"revisad|equipo de calidad|quality team|revised", text, re.IGNORECASE))
    return key_name, scale, capo, instrument, reviewed


def _extract_sections(soup) -> tuple[ChordSection, ...]:
    pre = soup.find("pre", attrs={"data-chord-content": True}) or soup.find("pre")
    if pre is None:
        raise HarmonyError("La fuente no contiene un bloque de acordes reconocible.")

    sections: list[ChordSection] = []
    current_title = "General"
    current_lines: list[ChordLine] = []

    def flush() -> None:
        nonlocal current_lines
        if current_lines:
            sections.append(ChordSection(current_title, tuple(current_lines)))
            current_lines = []

    blocks = pre.find_all("div", class_=re.compile(r"kvMV"))
    if not blocks and not pre.find(attrs={"data-chord-name": True}):
        for tab in pre.find_all("span", class_=re.compile(r"tablatura|tab", re.IGNORECASE)):
            tab.decompose()
        for raw_line in pre.decode_contents().splitlines():
            if not raw_line.strip():
                continue
            line_soup = BeautifulSoup(f"<span>{raw_line}</span>", "html.parser")
            text = _clean_text(line_soup.get_text(" ", strip=True))
            section_match = re.match(r"^\[([^\]]+)\]", text)
            if section_match:
                title = _clean_text(section_match.group(1))
                if not title.lower().startswith(("tab", "riff", "solo")) and title != current_title:
                    flush()
                    current_title = _spanish_section_title(title)
            chords = tuple(
                _clean_text(tag.get_text(" ", strip=True))
                for tag in line_soup.find_all("b")
                if _split_chord(tag.get_text(" ", strip=True))
            )
            if chords:
                current_lines.append(ChordLine(chords, text.count("|")))
        flush()
        if not sections:
            raise HarmonyError("No he encontrado acordes legibles en esta versión.")
        return tuple(sections)
    if not blocks:
        blocks = [pre]
    for block in blocks:
        if block.find(class_=re.compile(r"\btabs?\b")):
            continue
        chords = tuple(
            _clean_text(tag.get("data-chord-name") or tag.get_text(" ", strip=True))
            for tag in block.find_all(attrs={"data-chord-name": True})
            if _split_chord(tag.get("data-chord-name") or tag.get_text(" ", strip=True))
        )
        text = _clean_text(block.get_text(" ", strip=True))
        section_match = re.match(r"^\[([^\]]+)\]", text)
        if section_match:
            title = _clean_text(section_match.group(1))
            if title.lower().startswith(("tab", "riff", "solo")):
                continue
            if title.lower() not in {"intro", "verso", "estribillo", "coro", "bridge", "puente"} or chords:
                if title != current_title:
                    flush()
                    current_title = _spanish_section_title(title)
        if chords:
            bars = text.count("|")
            current_lines.append(ChordLine(chords, bars))
    flush()
    if not sections:
        raise HarmonyError("No he encontrado acordes legibles en esta versión.")
    return tuple(sections)


def _candidate_to_dict(candidate: ChordCandidate) -> dict:
    return asdict(candidate)


def _candidate_from_dict(value: dict) -> ChordCandidate:
    return ChordCandidate(**value)


def _chart_to_dict(chart: ChordChart) -> dict:
    return {
        **asdict(chart),
        "sections": [
            {"title": section.title, "lines": [asdict(line) for line in section.lines]}
            for section in chart.sections
        ],
    }


def _chart_from_dict(value: dict) -> ChordChart:
    return ChordChart(
        source_id=value["source_id"],
        source_name=value["source_name"],
        url=value["url"],
        artist=value["artist"],
        title=value["title"],
        version=value["version"],
        key_name=value.get("key_name"),
        scale=value.get("scale"),
        capo=value.get("capo"),
        reviewed=bool(value.get("reviewed", False)),
        instrument=value.get("instrument", ""),
        sections=tuple(
            ChordSection(
                section["title"],
                tuple(ChordLine(tuple(line["chords"]), int(line.get("bars", 0))) for line in section["lines"]),
            )
            for section in value.get("sections", [])
        ),
    )


class HarmonyCache:
    def __init__(self, root: str | Path | None = None, ttl_seconds: int = 7 * 24 * 3600):
        self.root = Path(root or Path.home() / ".cache" / "split-tracks" / "harmony")
        self.ttl_seconds = ttl_seconds

    def _path(self, prefix: str, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.root / f"{prefix}-{digest}.json"

    def read(self, prefix: str, key: str) -> dict | None:
        path = self._path(prefix, key)
        if not path.is_file() or time.time() - path.stat().st_mtime > self.ttl_seconds:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def write(self, prefix: str, key: str, value: dict) -> None:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            path = self._path(prefix, key)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            temporary.replace(path)
        except OSError:
            pass


class CifraClubProvider:
    source_id = "cifraclub"
    source_name = "Cifra Club"
    base_url = "https://www.cifraclub.com.br/"

    def __init__(self, cache: HarmonyCache | None = None):
        self.cache = cache or HarmonyCache()

    @staticmethod
    def _localized_url(url: str) -> str:
        parsed = urlparse(url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query["locale"] = "es"
        return urlunparse(parsed._replace(query=urlencode(query)))

    def _get(self, url: str):
        _require_web_dependencies()
        localized_url = self._localized_url(url)
        try:
            response = requests.get(
                localized_url,
                headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) SplitTracks/1.0"},
                timeout=20,
            )
        except requests.RequestException as exc:
            raise HarmonyError("Cifra Club no responde ahora mismo.") from exc
        if response.status_code == 404:
            raise HarmonyError("No he encontrado ese cifrado en Cifra Club.")
        if response.status_code >= 400:
            raise HarmonyError(f"Cifra Club ha respondido con HTTP {response.status_code}.")
        return BeautifulSoup(response.text, "html.parser")

    def _base_url(self, artist: str, title: str) -> str:
        return self._localized_url(urljoin(self.base_url, f"{_slug(artist)}/{_slug(title)}/"))

    def search(self, artist: str, title: str) -> tuple[ChordCandidate, ...]:
        artist = _clean_text(artist)
        title = _clean_text(title)
        if not artist or not title:
            raise HarmonyError("Escribe el artista y el título para buscar acordes.")
        key = f"v7::{artist.lower()}::{title.lower()}"
        cached = self.cache.read("search", key)
        if cached:
            return tuple(_candidate_from_dict(item) for item in cached.get("candidates", []))

        url = self._base_url(artist, title)
        soup = self._get(url)
        key_name, scale, capo, instrument, reviewed = _parse_source_metadata(soup)
        song_title = _clean_text((soup.find("h1") or {}).get_text(" ", strip=True) if soup.find("h1") else title)
        candidates: list[ChordCandidate] = [ChordCandidate(
            source_id=self.source_id,
            source_name=self.source_name,
            url=url,
            artist=artist,
            title=song_title,
            version="Principal",
            instrument=instrument,
            key_name=key_name,
            scale=scale,
            capo=capo,
            reviewed=reviewed,
        )]
        seen: set[str] = {url}
        base_parts = urlparse(url)
        base_path = base_parts.path.rstrip("/") + "/"
        for link in soup.find_all("a", href=True):
            href = self._localized_url(urljoin(url, link["href"]))
            text = _clean_text(link.get_text(" ", strip=True))
            if "#" in href:
                continue
            href_parts = urlparse(href)
            href_path = href.lower()
            same_song = (
                href_parts.netloc == base_parts.netloc
                and (href_parts.path.rstrip("/") == base_parts.path.rstrip("/") or href_parts.path.startswith(base_path))
            )
            if any(marker in href_path for marker in ("/tabs-", "/letra", "imprimir", "guitar-pro", "partitura")):
                continue
            if not same_song:
                continue
            if href in seen or not text or text.lower() in {"letra", "lyrics"}:
                continue
            seen.add(href)
            version = "Principal" if href_parts.path.rstrip("/") == base_parts.path.rstrip("/") else _version_label(text)
            candidates.append(ChordCandidate(
                source_id=self.source_id,
                source_name=self.source_name,
                url=href,
                artist=artist,
                title=song_title,
                version=version,
                instrument=instrument,
                key_name=key_name,
                scale=scale,
                capo=capo,
                reviewed=reviewed,
            ))
        valid_candidates: list[ChordCandidate] = []
        for candidate in candidates:
            try:
                _extract_sections(self._get(candidate.url))
            except HarmonyError:
                continue
            valid_candidates.append(candidate)
        candidates = valid_candidates
        if not candidates:
            candidates.append(ChordCandidate(self.source_id, self.source_name, url, artist, song_title, "Principal", instrument, key_name, scale, capo, reviewed))
        self.cache.write("search", key, {"candidates": [_candidate_to_dict(item) for item in candidates]})
        return tuple(candidates)

    def fetch(self, candidate: ChordCandidate) -> ChordChart:
        chart_key = f"v5::{candidate.url}::{candidate.version}"
        cached = self.cache.read("chart", chart_key)
        if cached:
            return _chart_from_dict(cached)
        soup = self._get(candidate.url)
        sections = _extract_sections(soup)
        key_name, scale, capo, instrument, reviewed = _parse_source_metadata(soup, candidate.key_name)
        if not scale:
            scale = _guess_scale(key_name, (chord for section in sections for line in section.lines for chord in line.chords))
        title = _clean_text(soup.find("h1").get_text(" ", strip=True)) if soup.find("h1") else candidate.title
        chart = ChordChart(
            source_id=candidate.source_id,
            source_name=candidate.source_name,
            url=candidate.url,
            artist=candidate.artist,
            title=title,
            version=candidate.version,
            key_name=key_name or candidate.key_name,
            scale=scale or candidate.scale,
            capo=capo if capo is not None else candidate.capo,
            reviewed=reviewed or candidate.reviewed,
            instrument=instrument or candidate.instrument,
            sections=sections,
        )
        self.cache.write("chart", chart_key, _chart_to_dict(chart))
        return chart


_VIDEO_TAG_RE = re.compile(
    r"(?:official|audio|music|lyric|lyrics|video|visualizer|live|"
    r"remaster(?:ed)?|version|performance|session|hd|4k|topic|"
    r"subtit(?:led|les?)|full album)",
    re.IGNORECASE,
)


def _clean_video_title(value: str) -> str:
    cleaned = _clean_text(value).strip(" -_|")
    if cleaned.lower().endswith((".wav", ".mp3", ".m4a", ".flac", ".ogg")):
        cleaned = _clean_text(Path(cleaned).stem)

    changed = True
    while changed:
        changed = False
        matches = list(re.finditer(r"\(([^()]*)\)|\[([^\]]*)\]", cleaned))
        for match in reversed(matches):
            content = match.group(1) or match.group(2) or ""
            if _VIDEO_TAG_RE.search(content):
                cleaned = f"{cleaned[:match.start()]} {cleaned[match.end():]}".strip(" -_|")
                changed = True
                break

    cleaned = re.sub(
        r"\s*(?:[-|:]\s*)?(?:official(?:\s+(?:music|audio))?\s+video|official\s+audio|"
        r"lyrics?|visualizer|audio|video|live|remastered?|hd|4k)\s*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return _clean_text(cleaned).strip(" -_|")


def _normalise_title_piece(value: str) -> str:
    return _clean_text(value).casefold().replace("–", "-").replace("—", "-")


def guess_artist_title(value: str, *, fallback_artist: str = "") -> tuple[str, str]:
    """Split common YouTube title formats using yt-dlp metadata when available."""
    cleaned = _clean_video_title(value)
    fallback_artist = _clean_text(fallback_artist)
    separators = (" - ", " – ", " — ", " | ")
    parsed: tuple[str, str] | None = None
    for separator in separators:
        if separator in cleaned:
            left, right = cleaned.split(separator, 1)
            if left.strip() and right.strip():
                parsed = (left.strip(), right.strip())
                break

    by_match = re.match(r"^(.+?)\s+\bby\b\s+(.+)$", cleaned, re.IGNORECASE)
    if by_match:
        parsed = (by_match.group(2).strip(), by_match.group(1).strip())

    if parsed:
        left, right = parsed
        if fallback_artist:
            fallback_normalised = _normalise_title_piece(fallback_artist)
            if _normalise_title_piece(left) == fallback_normalised:
                return fallback_artist, right
            if _normalise_title_piece(right) == fallback_normalised:
                return fallback_artist, left
            return fallback_artist, right
        return left, right

    return fallback_artist, cleaned
