#!/usr/bin/env python3
"""A single-clock GStreamer mixer for generated StemForge stems."""

from __future__ import annotations

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst


class MixerPlayer:
    def __init__(self, on_error=None, on_eos=None):
        Gst.init(None)
        self.pipeline: Gst.Pipeline | None = None
        self.volumes: list[Gst.Element] = []
        self.pitch_effects: list[Gst.Element] = []
        self.pitch_supported = Gst.ElementFactory.find("pitch") is not None
        self.duration = 0.0
        self.on_error = on_error
        self.on_eos = on_eos
        self.playing = False

    def load(self, stems: list[dict], duration: float) -> None:
        self.close()
        pipeline = Gst.Pipeline.new("stemforge-single-clock")
        mixer = Gst.ElementFactory.make("audiomixer", "mixer")
        convert = Gst.ElementFactory.make("audioconvert", "master-convert")
        resample = Gst.ElementFactory.make("audioresample", "master-resample")
        sink = Gst.ElementFactory.make("autoaudiosink", "master-sink")
        if not all((pipeline, mixer, convert, resample, sink)):
            raise RuntimeError("GStreamer no tiene los elementos de audio necesarios.")
        pipeline.add(mixer)
        pipeline.add(convert)
        pipeline.add(resample)
        pipeline.add(sink)
        if not mixer.link(convert) or not convert.link(resample) or not resample.link(sink):
            raise RuntimeError("No se pudo conectar el mezclador de audio.")

        self.volumes = []
        self.pitch_effects = []
        for index, stem in enumerate(stems):
            source = Gst.ElementFactory.make("filesrc", f"source-{index}")
            decoder = Gst.ElementFactory.make("decodebin", f"decoder-{index}")
            queue = Gst.ElementFactory.make("queue", f"queue-{index}")
            audio_convert = Gst.ElementFactory.make("audioconvert", f"convert-{index}")
            audio_resample = Gst.ElementFactory.make("audioresample", f"resample-{index}")
            volume = Gst.ElementFactory.make("volume", f"volume-{index}")
            pitch = Gst.ElementFactory.make("pitch", f"pitch-{index}") if self.pitch_supported else None
            if not all((source, decoder, queue, audio_convert, audio_resample, volume)) or (self.pitch_supported and pitch is None):
                raise RuntimeError("GStreamer no tiene soporte para decodificar este audio.")
            source.set_property("location", str(stem["path"]))
            volume.set_property("volume", 0.0)
            elements = (source, decoder, queue, audio_convert, audio_resample, pitch, volume) if pitch else (source, decoder, queue, audio_convert, audio_resample, volume)
            for element in elements:
                pipeline.add(element)
            if not source.link(decoder):
                raise RuntimeError("No se pudo abrir una pista separada.")
            decoder.connect("pad-added", self._on_pad_added, queue)
            if not queue.link(audio_convert) or not audio_convert.link(audio_resample):
                raise RuntimeError("No se pudo preparar una pista del mezclador.")
            if pitch:
                if not audio_resample.link(pitch) or not pitch.link(volume):
                    raise RuntimeError("No se pudo preparar el cambio de tonalidad en directo.")
                self.pitch_effects.append(pitch)
            elif not audio_resample.link(volume):
                raise RuntimeError("No se pudo conectar una pista del mezclador.")
            if not volume.link(mixer):
                raise RuntimeError("No se pudo conectar una pista al mezclador.")
            self.volumes.append(volume)

        bus = pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_message)
        self.pipeline = pipeline
        self.duration = duration
        self.update_mix(stems)
        pipeline.set_state(Gst.State.PAUSED)

    @staticmethod
    def _on_pad_added(_decodebin, pad, queue) -> None:
        sink_pad = queue.get_static_pad("sink")
        if sink_pad and not sink_pad.is_linked():
            caps = pad.get_current_caps() or pad.query_caps(None)
            structure = caps.get_structure(0) if caps and caps.get_size() else None
            if structure and structure.get_name().startswith("audio/"):
                pad.link(sink_pad)

    def _on_message(self, _bus, message) -> None:
        if message.type == Gst.MessageType.ERROR:
            error, debug = message.parse_error()
            if self.on_error:
                self.on_error(error.message or debug or "Error de reproducción")
        elif message.type == Gst.MessageType.EOS:
            self.playing = False
            if self.on_eos:
                self.on_eos()

    def play(self) -> None:
        if self.pipeline:
            self.pipeline.set_state(Gst.State.PLAYING)
            self.playing = True

    def pause(self) -> None:
        if self.pipeline:
            self.pipeline.set_state(Gst.State.PAUSED)
            self.playing = False

    def stop(self) -> None:
        if self.pipeline:
            self.pipeline.set_state(Gst.State.PAUSED)
            self.seek(0.0)
            self.playing = False

    def seek(self, seconds: float) -> None:
        if self.pipeline:
            self.pipeline.seek_simple(
                Gst.Format.TIME,
                Gst.SeekFlags.FLUSH | Gst.SeekFlags.ACCURATE,
                max(0, int(seconds * Gst.SECOND)),
            )

    def position(self) -> float:
        if not self.pipeline:
            return 0.0
        success, value = self.pipeline.query_position(Gst.Format.TIME)
        if not success:
            return 0.0
        return max(0.0, value / Gst.SECOND)

    def set_pitch(self, semitones: int) -> None:
        if not self.pitch_supported or not self.pitch_effects:
            raise RuntimeError(
                "Falta el plugin GStreamer de cambio de tonalidad. Instala gstreamer1.0-plugins-bad."
            )
        ratio = 2 ** (semitones / 12)
        for effect in self.pitch_effects:
            effect.set_property("pitch", ratio)

    def update_mix(self, stems: list[dict]) -> None:
        solo_exists = any(stem.get("solo", False) for stem in stems)
        for index, stem in enumerate(stems):
            if index >= len(self.volumes):
                continue
            audible = not stem.get("mute", False) and (not solo_exists or stem.get("solo", False))
            gain = max(0.0, min(1.25, float(stem.get("volume", 1.0)))) if audible else 0.0
            self.volumes[index].set_property("volume", gain)

    def close(self) -> None:
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
        self.pipeline = None
        self.volumes = []
        self.pitch_effects = []
        self.playing = False
