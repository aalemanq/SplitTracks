import tempfile
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

from harmony import (
    ChordChart,
    ChordLine,
    ChordSection,
    HarmonyCache,
    _extract_sections,
    chord_degree,
    guess_artist_title,
    transpose_chord,
)


class HarmonyTest(unittest.TestCase):
    def test_parses_legacy_cifra_club_sections_and_skips_tabs(self) -> None:
        html = """
        <pre>[Intro] <b>G</b> <b>B</b> <b>C</b> <b>Cm</b>
        <span class="tablatura"><b>G</b>E|---|</span>
        [Verse]
        <b>G</b> When you were here
        <b>B</b> Couldn't look you in the eye
        </pre>
        """
        sections = _extract_sections(BeautifulSoup(html, "html.parser"))

        self.assertEqual(sections[0].title, "Intro")
        self.assertEqual(sections[0].lines[0].chords, ("G", "B", "C", "Cm"))
        self.assertEqual(sections[1].title, "Verse")
        self.assertEqual(tuple(line.chords for line in sections[1].lines), (("G",), ("B",)))

    def test_transposes_chords_slash_chords_and_degrees(self) -> None:
        chart = ChordChart(
            source_id="fixture",
            source_name="Fixture",
            url="https://example.invalid/chart",
            artist="Radiohead",
            title="Creep",
            version="Principal",
            key_name="G",
            scale="mayor",
            capo=0,
            reviewed=True,
            instrument="Guitarra",
            sections=(ChordSection("Intro", (ChordLine(("G", "B", "C", "Cm", "G/B")),)),),
        )

        self.assertEqual(chart.transposed_key(1), "A♭")
        self.assertEqual(chart.transposed_sections(1)[0].lines[0].chords, ("A♭", "C", "D♭", "D♭m", "A♭/C"))
        self.assertEqual(chart.degrees()[0].lines[0].chords, ("I", "III", "IV", "iv", "I"))
        self.assertEqual(chart.degrees(1)[0].lines[0].chords, ("I", "III", "IV", "iv", "I"))
        self.assertEqual(transpose_chord("F#m7/C#", 1, key_name="E"), "Gm7/D")
        self.assertEqual(chord_degree("B", "G", "mayor"), "III")

    def test_guess_artist_title_uses_metadata_and_cleans_video_tags(self) -> None:
        self.assertEqual(
            guess_artist_title("Radiohead - Creep (Official Video)"),
            ("Radiohead", "Creep"),
        )
        self.assertEqual(
            guess_artist_title("Creep by Radiohead [Lyrics]", fallback_artist="Radiohead"),
            ("Radiohead", "Creep"),
        )
        self.assertEqual(
            guess_artist_title("Creep Official Audio", fallback_artist="Radiohead"),
            ("Radiohead", "Creep"),
        )
        self.assertEqual(
            guess_artist_title(
                "RAYE - WHERE IS MY HUSBAND! (Live on The Graham Norton show)",
                fallback_artist="RAYE",
            ),
            ("RAYE", "WHERE IS MY HUSBAND!"),
        )

    def test_cache_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = HarmonyCache(Path(directory), ttl_seconds=60)
            cache.write("fixture", "song", {"value": "ok"})
            self.assertEqual(cache.read("fixture", "song"), {"value": "ok"})


if __name__ == "__main__":
    unittest.main()
