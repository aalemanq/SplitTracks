import importlib.util
import math
import tempfile
import unittest
import wave
from pathlib import Path

if importlib.util.find_spec("numpy") is not None:
    import numpy as np
    from analysis import analyze_audio
else:
    analyze_audio = None


@unittest.skipUnless(analyze_audio is not None, "NumPy no está instalado en este intérprete")
class AudioAnalysisTest(unittest.TestCase):
    def test_analysis_returns_metadata_and_spectrum(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tone.wav"
            sample_rate = 44100
            samples = []
            for index in range(sample_rate * 3):
                value = 0.35 * math.sin(2.0 * math.pi * 440.0 * index / sample_rate)
                samples.append(int(value * 32767))

            with wave.open(str(path), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(sample_rate)
                audio.writeframes(b"".join(sample.to_bytes(2, "little", signed=True) for sample in samples))

            result = analyze_audio(path)

            self.assertIsNotNone(result.lufs)
            self.assertIsNotNone(result.peak_dbfs)
            self.assertLess(result.peak_dbfs, 0)
            self.assertGreater(result.dynamic_range_db, 0)
            self.assertEqual(len(result.spectrum), 47)
            self.assertGreater(max(result.spectrum) - min(result.spectrum), 10.0)
            self.assertTrue(result.summary)

    def test_chord_progression_returns_timed_events(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "progression.wav"
            sample_rate = 22050
            chord_notes = [
                [130.81, 164.81, 196.00],
                [196.00, 246.94, 293.66],
                [110.00, 130.81, 164.81],
                [87.31, 130.81, 174.61],
            ]
            parts = []
            for notes in chord_notes:
                time = np.arange(sample_rate * 2) / sample_rate
                parts.append(sum(0.18 * np.sin(2 * np.pi * frequency * time) for frequency in notes))
            audio = np.concatenate(parts)
            with wave.open(str(path), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(sample_rate)
                output.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())

            result = analyze_audio(path)

            self.assertGreaterEqual(len(result.chords), 3)
            self.assertIn("C", result.chord_summary)
            self.assertIn("G", result.chord_summary)
            self.assertIn("Am", result.chord_summary)
            self.assertEqual(result.degree_sequence[:4], ("I", "V", "vi", "IV"))
            self.assertTrue(all(event.end > event.start for event in result.chords))


if __name__ == "__main__":
    unittest.main()
