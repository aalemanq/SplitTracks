import importlib.util
import math
import tempfile
import unittest
import wave
from pathlib import Path

if importlib.util.find_spec("numpy") is not None:
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
            self.assertTrue(result.summary)


if __name__ == "__main__":
    unittest.main()
