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
