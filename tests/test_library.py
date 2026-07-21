import sqlite3
import tempfile
import unittest
from pathlib import Path

from library import Library


class LibraryTest(unittest.TestCase):
    def test_library_keeps_original_path_and_favorite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "ensayo.mp3"
            audio.write_bytes(b"fake audio")
            library = Library(root / "data")

            record = library.upsert_track(
                path=audio,
                title="Ensayo",
                duration=123.4,
                format_name="mp3",
                sample_rate=44100,
                channels=2,
            )

            self.assertEqual(record.path, audio.resolve())
            self.assertEqual(record.title, "Ensayo")
            self.assertFalse(record.favorite)
            self.assertTrue(record.available)

            favorite = library.set_favorite(record.track_id, True)
            self.assertTrue(favorite.favorite)
            self.assertTrue(library.get(record.track_id).favorite)
            self.assertEqual(library.list_tracks()[0].track_id, record.track_id)

    def test_analysis_metadata_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "analizado.mp3"
            audio.write_bytes(b"fake audio")
            library = Library(root / "data")
            record = library.upsert_track(
                path=audio,
                analysis={
                    "bpm": 123,
                    "key_name": "A",
                    "scale": "menor",
                    "lufs": -14.2,
                    "peak_dbfs": -0.4,
                    "dynamic_range_db": 8.5,
                    "spectrum": [-3.0, -12.5, -30.0],
                },
            )

            loaded = library.get(record.track_id)
            self.assertEqual(loaded.bpm, 123)
            self.assertEqual(loaded.key_name, "A")
            self.assertEqual(loaded.scale, "menor")
            self.assertEqual(loaded.spectrum, (-3.0, -12.5, -30.0))

    def test_existing_library_schema_is_migrated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "data"
            data_dir.mkdir()
            database = data_dir / "library.sqlite3"
            with sqlite3.connect(database) as connection:
                connection.executescript(
                    """
                    CREATE TABLE tracks (
                        id TEXT PRIMARY KEY,
                        path TEXT NOT NULL UNIQUE,
                        title TEXT NOT NULL,
                        duration REAL NOT NULL DEFAULT 0,
                        format_name TEXT NOT NULL DEFAULT '',
                        sample_rate INTEGER NOT NULL DEFAULT 0,
                        channels INTEGER NOT NULL DEFAULT 0,
                        favorite INTEGER NOT NULL DEFAULT 0,
                        thumbnail_path TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    """
                )

            library = Library(data_dir)
            columns = {
                row[1]
                for row in sqlite3.connect(database).execute("PRAGMA table_info(tracks)").fetchall()
            }
            self.assertIn("bpm", columns)
            self.assertIn("spectrum_json", columns)
            self.assertEqual(library.list_tracks(), [])

    def test_upsert_preserves_favorite_and_does_not_copy_audio(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "original.flac"
            audio.write_bytes(b"fake audio")
            library = Library(root / "data")

            first = library.upsert_track(path=audio, title="Original")
            library.set_favorite(first.track_id, True)
            second = library.upsert_track(path=audio, title="Renamed", duration=8)

            self.assertEqual(second.track_id, first.track_id)
            self.assertEqual(second.title, "Renamed")
            self.assertTrue(second.favorite)
            self.assertFalse((root / "data" / audio.name).exists())


if __name__ == "__main__":
    unittest.main()
