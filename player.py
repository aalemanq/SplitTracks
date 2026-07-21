#!/usr/bin/env python3
"""A single-clock GStreamer mixer for generated Split Tracks stems."""

from __future__ import annotations

import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst


class MixerPlayer:
    def __init__(self, on_error=None, on_eos=None):
        Gst.init(None)
        self.pipeline: Gst.Pipeline | None = None
        self.volumes: list[Gst.Element] = []
        self.master_volume: Gst.Element | None = None
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
        self.master_volume = Gst.ElementFactory.make("volume", "master-volume")
        pitch = Gst.ElementFactory.make("pitch", "master-pitch") if self.pitch_supported else None
        convert = Gst.ElementFactory.make("audioconvert", "master-convert")
        resample = Gst.ElementFactory.make("audioresample", "master-resample")
        sink = Gst.ElementFactory.make("autoaudiosink", "master-sink")
        if not all((pipeline, mixer, self.master_volume, convert, resample, sink)) or (self.pitch_supported and pitch is None):
            raise RuntimeError("GStreamer no tiene los elementos de audio necesarios.")
        elements = (mixer, self.master_volume, pitch, convert, resample, sink) if pitch else (mixer, self.master_volume, convert, resample, sink)
        for element in elements:
            pipeline.add(element)
        self.master_volume.set_property("volume", 1.0)
        if pitch:
            if not mixer.link(self.master_volume) or not self.master_volume.link(pitch) or not pitch.link(convert):
                raise RuntimeError("No se pudo preparar el cambio de tonalidad en directo.")
            self.pitch_effects = [pitch]
        elif not mixer.link(self.master_volume) or not self.master_volume.link(convert):
            raise RuntimeError("No se pudo conectar el mezclador de audio.")
        if not convert.link(resample) or not resample.link(sink):
            raise RuntimeError("No se pudo conectar la salida de audio.")

        self.volumes = []
        for index, stem in enumerate(stems):
            source = Gst.ElementFactory.make("filesrc", f"source-{index}")
            decoder = Gst.ElementFactory.make("decodebin", f"decoder-{index}")
            queue = Gst.ElementFactory.make("queue", f"queue-{index}")
            audio_convert = Gst.ElementFactory.make("audioconvert", f"convert-{index}")
            audio_resample = Gst.ElementFactory.make("audioresample", f"resample-{index}")
            volume = Gst.ElementFactory.make("volume", f"volume-{index}")
            if not all((source, decoder, queue, audio_convert, audio_resample, volume)):
                raise RuntimeError("GStreamer no tiene soporte para decodificar este audio.")
            source.set_property("location", str(stem["path"]))
            volume.set_property("volume", 0.0)
            elements = (source, decoder, queue, audio_convert, audio_resample, volume)
            for element in elements:
                pipeline.add(element)
            if not source.link(decoder):
                raise RuntimeError("No se pudo abrir una pista separada.")
            decoder.connect("pad-added", self._on_pad_added, queue)
            if not queue.link(audio_convert) or not audio_convert.link(audio_resample) or not audio_resample.link(volume):
                raise RuntimeError("No se pudo preparar una pista del mezclador.")
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
        self.seek(0.0)

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

    def set_master_volume(self, volume: float) -> None:
        if self.master_volume:
            self.master_volume.set_property("volume", max(0.0, min(1.5, float(volume))))

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
