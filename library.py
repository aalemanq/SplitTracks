#!/usr/bin/env python3
"""Persistent local library metadata for Split Tracks.

The library references audio files in their original locations. It never
moves, copies, or deletes user media.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


class LibraryError(RuntimeError):
    """A user-facing library error."""


@dataclass(frozen=True)
class LibraryTrack:
    track_id: str
    path: Path
    title: str
    duration: float
    format_name: str
    sample_rate: int
    channels: int
    favorite: bool
    created_at: str
    updated_at: str
    thumbnail_path: Path | None = None
    bpm: float | None = None
    tempo_confidence: float | None = None
    key_name: str | None = None
    scale: str | None = None
    key_confidence: float | None = None
    lufs: float | None = None
    peak_dbfs: float | None = None
    dynamic_range_db: float | None = None
    spectrum: tuple[float, ...] = ()

    @property
    def available(self) -> bool:
        return self.path.is_file()

    def as_dict(self) -> dict:
        return {
            "id": self.track_id,
            "path": str(self.path),
            "title": self.title,
            "duration": self.duration,
            "format": self.format_name,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "favorite": self.favorite,
            "available": self.available,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "thumbnail_path": str(self.thumbnail_path) if self.thumbnail_path else None,
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


class Library:
    """SQLite-backed metadata index that leaves original audio untouched."""

    def __init__(self, data_dir: str | Path | None = None):
        if data_dir is None:
            base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
            data_dir = base / "split-tracks"
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.database_path = self.data_dir / "library.sqlite3"
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialise(self) -> None:
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            with self._connect() as connection:
                connection.executescript(
                    """
                    PRAGMA foreign_keys = ON;
                    CREATE TABLE IF NOT EXISTS tracks (
                        id TEXT PRIMARY KEY,
                        path TEXT NOT NULL UNIQUE,
                        title TEXT NOT NULL,
                        duration REAL NOT NULL DEFAULT 0,
                        format_name TEXT NOT NULL DEFAULT '',
                        sample_rate INTEGER NOT NULL DEFAULT 0,
                        channels INTEGER NOT NULL DEFAULT 0,
                        favorite INTEGER NOT NULL DEFAULT 0,
                        thumbnail_path TEXT,
                        bpm REAL,
                        tempo_confidence REAL,
                        key_name TEXT,
                        scale TEXT,
                        key_confidence REAL,
                        lufs REAL,
                        peak_dbfs REAL,
                        dynamic_range_db REAL,
                        spectrum_json TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS tracks_favorite_idx
                        ON tracks (favorite DESC, updated_at DESC);
                    """
                )
                existing_columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(tracks)").fetchall()
                }
                migrations = {
                    "bpm": "REAL",
                    "tempo_confidence": "REAL",
                    "key_name": "TEXT",
                    "scale": "TEXT",
                    "key_confidence": "REAL",
                    "lufs": "REAL",
                    "peak_dbfs": "REAL",
                    "dynamic_range_db": "REAL",
                    "spectrum_json": "TEXT",
                }
                for column, column_type in migrations.items():
                    if column not in existing_columns:
                        connection.execute(f"ALTER TABLE tracks ADD COLUMN {column} {column_type}")
        except OSError as exc:
            raise LibraryError(f"No puedo preparar la biblioteca local: {exc}") from exc
        except sqlite3.Error as exc:
            raise LibraryError(f"No puedo abrir la biblioteca local: {exc}") from exc

    @staticmethod
    def _track_id(path: Path) -> str:
        return hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:20]

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def _from_row(row: sqlite3.Row) -> LibraryTrack:
        thumbnail = Path(row["thumbnail_path"]) if row["thumbnail_path"] else None
        spectrum_raw = row["spectrum_json"]
        try:
            spectrum = tuple(float(value) for value in (json.loads(spectrum_raw) if spectrum_raw else []))
        except (TypeError, ValueError, json.JSONDecodeError):
            spectrum = ()
        return LibraryTrack(
            track_id=row["id"],
            path=Path(row["path"]),
            title=row["title"],
            duration=float(row["duration"]),
            format_name=row["format_name"],
            sample_rate=int(row["sample_rate"]),
            channels=int(row["channels"]),
            favorite=bool(row["favorite"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            thumbnail_path=thumbnail,
            bpm=float(row["bpm"]) if row["bpm"] is not None else None,
            tempo_confidence=float(row["tempo_confidence"]) if row["tempo_confidence"] is not None else None,
            key_name=row["key_name"],
            scale=row["scale"],
            key_confidence=float(row["key_confidence"]) if row["key_confidence"] is not None else None,
            lufs=float(row["lufs"]) if row["lufs"] is not None else None,
            peak_dbfs=float(row["peak_dbfs"]) if row["peak_dbfs"] is not None else None,
            dynamic_range_db=float(row["dynamic_range_db"]) if row["dynamic_range_db"] is not None else None,
            spectrum=spectrum,
        )

    def upsert_track(
        self,
        *,
        path: str | Path,
        title: str | None = None,
        duration: float = 0.0,
        format_name: str = "",
        sample_rate: int = 0,
        channels: int = 0,
        thumbnail_path: str | Path | None = None,
        analysis: Mapping[str, object] | None = None,
    ) -> LibraryTrack:
        audio_path = Path(path).expanduser().resolve()
        if not audio_path.is_file():
            raise LibraryError("El archivo ya no está disponible para añadirlo a la biblioteca.")
        track_id = self._track_id(audio_path)
        now = self._now()
        display_title = title or audio_path.stem
        thumbnail = str(Path(thumbnail_path).expanduser().resolve()) if thumbnail_path else None
        analysis_values = analysis or {}

        def analysis_float(name: str) -> float | None:
            value = analysis_values.get(name)
            return float(value) if value is not None else None

        spectrum_value = analysis_values.get("spectrum")
        if spectrum_value is None or isinstance(spectrum_value, str):
            spectrum_json = spectrum_value
        else:
            spectrum_json = json.dumps([float(value) for value in spectrum_value], separators=(",", ":"))
        bpm = analysis_float("bpm")
        tempo_confidence = analysis_float("tempo_confidence")
        key_name = analysis_values.get("key_name")
        scale = analysis_values.get("scale")
        key_confidence = analysis_float("key_confidence")
        lufs = analysis_float("lufs")
        peak_dbfs = analysis_float("peak_dbfs")
        dynamic_range_db = analysis_float("dynamic_range_db")
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO tracks
                        (id, path, title, duration, format_name, sample_rate, channels,
                         thumbnail_path, bpm, tempo_confidence, key_name, scale, key_confidence,
                         lufs, peak_dbfs, dynamic_range_db, spectrum_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(path) DO UPDATE SET
                        title = excluded.title,
                        duration = excluded.duration,
                        format_name = excluded.format_name,
                        sample_rate = excluded.sample_rate,
                        channels = excluded.channels,
                        thumbnail_path = COALESCE(excluded.thumbnail_path, tracks.thumbnail_path),
                        bpm = COALESCE(excluded.bpm, tracks.bpm),
                        tempo_confidence = COALESCE(excluded.tempo_confidence, tracks.tempo_confidence),
                        key_name = COALESCE(excluded.key_name, tracks.key_name),
                        scale = COALESCE(excluded.scale, tracks.scale),
                        key_confidence = COALESCE(excluded.key_confidence, tracks.key_confidence),
                        lufs = COALESCE(excluded.lufs, tracks.lufs),
                        peak_dbfs = COALESCE(excluded.peak_dbfs, tracks.peak_dbfs),
                        dynamic_range_db = COALESCE(excluded.dynamic_range_db, tracks.dynamic_range_db),
                        spectrum_json = COALESCE(excluded.spectrum_json, tracks.spectrum_json),
                        updated_at = excluded.updated_at
                    """,
                    (
                        track_id,
                        str(audio_path),
                        display_title,
                        max(0.0, float(duration)),
                        format_name,
                        max(0, int(sample_rate)),
                        max(0, int(channels)),
                        thumbnail,
                        bpm,
                        tempo_confidence,
                        key_name,
                        scale,
                        key_confidence,
                        lufs,
                        peak_dbfs,
                        dynamic_range_db,
                        spectrum_json,
                        now,
                        now,
                    ),
                )
                row = connection.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone()
        except sqlite3.Error as exc:
            raise LibraryError(f"No puedo registrar el audio en la biblioteca: {exc}") from exc
        if row is None:
            raise LibraryError("La biblioteca no devolvió el audio recién registrado.")
        return self._from_row(row)

    def get(self, track_id: str) -> LibraryTrack | None:
        try:
            with self._connect() as connection:
                row = connection.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone()
        except sqlite3.Error as exc:
            raise LibraryError(f"No puedo leer la biblioteca local: {exc}") from exc
        return self._from_row(row) if row else None

    def list_tracks(self, *, favorites_first: bool = True) -> list[LibraryTrack]:
        order = "favorite DESC, updated_at DESC" if favorites_first else "updated_at DESC"
        try:
            with self._connect() as connection:
                rows = connection.execute(f"SELECT * FROM tracks ORDER BY {order}").fetchall()
        except sqlite3.Error as exc:
            raise LibraryError(f"No puedo listar la biblioteca local: {exc}") from exc
        return [self._from_row(row) for row in rows]

    def set_favorite(self, track_id: str, favorite: bool) -> LibraryTrack:
        now = self._now()
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    "UPDATE tracks SET favorite = ?, updated_at = ? WHERE id = ?",
                    (int(favorite), now, track_id),
                )
                if cursor.rowcount != 1:
                    raise LibraryError("La pista ya no existe en la biblioteca.")
                row = connection.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone()
        except LibraryError:
            raise
        except sqlite3.Error as exc:
            raise LibraryError(f"No puedo actualizar el favorito: {exc}") from exc
        if row is None:
            raise LibraryError("La biblioteca no devolvió la pista actualizada.")
        return self._from_row(row)

