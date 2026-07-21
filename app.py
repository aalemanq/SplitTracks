#!/usr/bin/env python3
"""Split Tracks — local stereo stem utility for Ubuntu."""

from __future__ import annotations

import shutil
import sys
import threading
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gst", "1.0")
from gi.repository import Gdk, Gio, GLib, GObject, Gtk

from analysis import AnalysisCancelled, AnalysisError, AudioAnalysis, analyze_audio, transpose_note_name
from engine import AudioEngineError, SeparationCancelled, SeparationEngine, SeparationResult, STEM_LABELS, STEM_ORDER
from harmony import ChordCandidate, ChordChart, CifraClubProvider, HarmonyError, guess_artist_title
from player import MixerPlayer


APP_NAME = "Split Tracks"
ICON_DIR = Path(__file__).with_name("assets") / "icons"

TRACK_ASSETS = {
    "Voces": "vocals.svg",
    "Batería completa": "drums.svg",
    "Bajo": "bass.svg",
    "Guitarra": "guitar.svg",
    "Piano y teclados": "piano.svg",
    "Other": "other.svg",
}
CATEGORY_ASSETS = {
    "vocals": "vocals.svg",
    "drums": "drums.svg",
    "bass": "bass.svg",
    "guitar": "guitar.svg",
    "piano": "piano.svg",
}
TRACK_CLASSES = {
    "Voces": "track-vocals",
    "Batería completa": "track-drums",
    "Bajo": "track-bass",
    "Guitarra": "track-guitar",
    "Piano y teclados": "track-piano",
    "Other": "track-other",
}


def ui_icon(name: str, size: int = 16, css: str | None = None) -> Gtk.Image:
    image = Gtk.Image.new_from_icon_name(name)
    image.set_pixel_size(size)
    if css:
        image.add_css_class(css)
    return image


def ui_asset(name: str, size: int = 18, css: str | None = None) -> Gtk.Image:
    image = Gtk.Image.new_from_file(str(ICON_DIR / name))
    image.set_pixel_size(size)
    if css:
        image.add_css_class(css)
    return image


def centered_image(image: Gtk.Image) -> Gtk.Image:
    image.set_hexpand(True)
    image.set_halign(Gtk.Align.CENTER)
    image.set_valign(Gtk.Align.CENTER)
    return image


def icon_button(text: str, icon_name: str, css: str = "secondary-action") -> Gtk.Button:
    button = Gtk.Button()
    button.add_css_class(css)
    contents = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
    contents.append(ui_icon(icon_name, 15))
    contents.append(label(text, "button-label"))
    button.set_child(contents)
    return button


def set_icon_button_text(button: Gtk.Button, text: str) -> None:
    child = button.get_child()
    if child:
        label_child = child.get_last_child()
        if isinstance(label_child, Gtk.Label):
            label_child.set_text(text)


def fmt_time(seconds: float) -> str:
    whole = max(0, int(seconds))
    minutes, secs = divmod(whole, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def add_css_class(widget: Gtk.Widget, name: str) -> Gtk.Widget:
    widget.add_css_class(name)
    return widget


def label(text: str, css: str | None = None, *, wrap: bool = False) -> Gtk.Label:
    widget = Gtk.Label(label=text)
    widget.set_xalign(0)
    if wrap:
        widget.set_wrap(True)
    if css:
        widget.add_css_class(css)
    return widget


def spacer(height: int = 8) -> Gtk.Box:
    box = Gtk.Box()
    box.set_size_request(-1, height)
    return box


class TrackRow(Gtk.Box):
    def __init__(self, index: int, stem: dict, changed, export_stem):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.add_css_class("track-row")
        self.index = index
        self.stem = stem
        self.changed = changed
        self.export_stem = export_stem
        self.set_margin_bottom(8)

        icon_badge = Gtk.Box()
        icon_badge.add_css_class("track-icon-badge")
        icon_badge.add_css_class(TRACK_CLASSES.get(stem["name"], "track-other"))
        icon_badge.set_size_request(34, 34)
        icon_badge.set_hexpand(False)
        icon_badge.set_vexpand(False)
        icon_badge.set_valign(Gtk.Align.CENTER)
        icon_badge.append(centered_image(ui_asset(TRACK_ASSETS.get(stem["name"], "other.svg"), 18)))
        self.append(icon_badge)

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info.set_hexpand(True)
        info.set_valign(Gtk.Align.CENTER)
        info.append(label(stem["name"], "track-name"))
        info.append(label(stem["kind"], "track-kind"))
        self.append(info)

        self.mute = Gtk.ToggleButton(label="M")
        self.mute.add_css_class("track-toggle")
        self.mute.add_css_class("mute")
        self.mute.set_size_request(34, 34)
        self.mute.set_hexpand(False)
        self.mute.set_vexpand(False)
        self.mute.set_valign(Gtk.Align.CENTER)
        self.mute.set_tooltip_text("Mute")
        self.mute.connect("toggled", self._on_toggle)
        self.append(self.mute)

        self.solo = Gtk.ToggleButton(label="S")
        self.solo.add_css_class("track-toggle")
        self.solo.add_css_class("solo")
        self.solo.set_size_request(34, 34)
        self.solo.set_hexpand(False)
        self.solo.set_vexpand(False)
        self.solo.set_valign(Gtk.Align.CENTER)
        self.solo.set_tooltip_text("Solo")
        self.solo.connect("toggled", self._on_toggle)
        self.append(self.solo)

        self.volume = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 1.25, 0.01)
        self.volume.set_value(1.0)
        self.volume.set_draw_value(False)
        self.volume.set_size_request(145, -1)
        self.volume.set_tooltip_text("Volumen")
        self.volume.connect("value-changed", self._on_volume)
        self.append(self.volume)

        self.value_label = label("100%", "track-value")
        self.value_label.set_xalign(1)
        self.append(self.value_label)

        self.export_button = Gtk.Button(label="MP3")
        self.export_button.add_css_class("track-export")
        self.export_button.set_tooltip_text("Exportar esta pista como MP3")
        self.export_button.set_size_request(48, 30)
        self.export_button.set_valign(Gtk.Align.CENTER)
        self.export_button.connect("clicked", lambda *_: self.export_stem(self.index))
        self.append(self.export_button)

    def _on_toggle(self, _button) -> None:
        self.changed(self.index, self.state())

    def _on_volume(self, scale) -> None:
        self.value_label.set_text(f"{round(scale.get_value() * 100):d}%")
        self.changed(self.index, self.state())

    def state(self) -> dict:
        return {
            **self.stem,
            "path": self.stem["path"],
            "volume": self.volume.get_value(),
            "mute": self.mute.get_active(),
            "solo": self.solo.get_active(),
        }


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application):
        super().__init__(application=application, title=APP_NAME)
        self.set_default_size(1420, 900)
        self.set_size_request(1080, 720)
        self.engine = SeparationEngine()
        self.player = MixerPlayer(on_error=self._player_error, on_eos=self._player_eos)
        self.input_path: Path | None = None
        self.audio_info = None
        self.audio_analysis: AudioAnalysis | None = None
        self.harmony_chart: ChordChart | None = None
        self.harmony_candidates: tuple[ChordCandidate, ...] = ()
        self._harmony_busy = False
        self.output_folder: Path | None = None
        self.result: SeparationResult | None = None
        self.track_states: list[dict] = []
        self.cancel_event: threading.Event | None = None
        self.youtube_temp_dir: Path | None = None
        self.track_checks: dict[str, Gtk.CheckButton] = {}
        self.header_extract_buttons: dict[str, Gtk.ToggleButton] = {}
        self.header_split_button: Gtk.Button | None = None
        self._syncing_header_extract = False
        self._busy = False
        self._updating_timeline = False
        self.pitch_shift = 0
        self.processing_started_at: float | None = None
        self.processing_timer_id: int | None = None
        self.analysis_cancel_event: threading.Event | None = None
        self._probe_generation = 0
        self._process_threads: list[threading.Thread] = []
        self._closing = False

        self._load_css()
        self._build_header()
        self._build_content()
        self._install_keyboard_shortcut()
        GLib.timeout_add(180, self._update_playback)

    def _load_css(self) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_path(str(Path(__file__).with_name("style.css")))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )



    def _build_header(self) -> None:
        header = Gtk.HeaderBar()
        header.add_css_class("topbar")
        header.set_show_title_buttons(True)
        header.set_title_widget(Gtk.Box())

        brand = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        brand.add_css_class("header-brand")
        brand.append(label(APP_NAME, "brand-title"))
        brand.append(label("SEPARACIÓN MULTISTEM LOCAL", "brand-subtitle"))
        brand.set_halign(Gtk.Align.START)
        brand.set_valign(Gtk.Align.CENTER)
        header.pack_start(brand)

        source = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
        source.add_css_class("header-source")
        source.set_hexpand(True)
        self.youtube_entry = Gtk.Entry()
        self.youtube_entry.add_css_class("header-youtube-entry")
        self.youtube_entry.set_placeholder_text("Pega aquí una URL de YouTube…")
        self.youtube_entry.set_hexpand(True)
        self.youtube_entry.connect("activate", self._download_youtube)
        source.append(self.youtube_entry)
        self.youtube_button = Gtk.Button(label="Añadir")
        self.youtube_button.add_css_class("header-action")
        self.youtube_button.connect("clicked", self._download_youtube)
        source.append(self.youtube_button)
        open_audio = Gtk.Button(label="Subir audio")
        open_audio.add_css_class("header-action")
        open_audio.connect("clicked", self._choose_audio)
        source.append(open_audio)
        header.pack_start(source)

        extract = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        extract.add_css_class("header-extract")
        for key in ("vocals", "drums", "bass", "guitar", "piano"):
            display_name, _kind, _color = STEM_LABELS[key]
            toggle = Gtk.ToggleButton(label=display_name)
            toggle.add_css_class("header-stem-toggle")
            toggle.add_css_class(f"header-stem-{key}")
            toggle.set_tooltip_text(f"Conservar {display_name}")
            toggle.connect("toggled", lambda button, selected_key=key: self._header_extract_toggled(selected_key, button))
            self.header_extract_buttons[key] = toggle
            extract.append(toggle)
        other_toggle = Gtk.Button(label="Other")
        other_toggle.add_css_class("header-stem-toggle")
        other_toggle.add_css_class("header-stem-other")
        other_toggle.set_sensitive(False)
        other_toggle.set_tooltip_text("Other se calcula automáticamente")
        extract.append(other_toggle)
        header.pack_start(extract)

        self.header_split_button = Gtk.Button(label="Separar")
        self.header_split_button.add_css_class("header-split-action")
        self.header_split_button.set_sensitive(False)
        self.header_split_button.connect("clicked", self._start_or_cancel)
        header.pack_end(self.header_split_button)
        self.set_titlebar(header)

    def _build_content(self) -> None:
        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        root.add_css_class("app-root")
        self.set_child(root)
        root.append(self._build_sidebar())
        root.append(self._build_workspace())

    def _card(self) -> Gtk.Box:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.add_css_class("card")
        return card

    def _launch_process_worker(self, target, args: tuple = ()) -> None:
        thread = threading.Thread(target=target, args=args, daemon=True)
        self._process_threads.append(thread)
        thread.start()

    def _build_chord_panel(self, title: str, css: str) -> tuple[Gtk.Box, Gtk.Box]:
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        panel.add_css_class("chord-panel")
        panel.add_css_class(css)
        panel.append(label(title, "chord-panel-title"))
        flow = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        flow.add_css_class("chord-flow")
        flow.set_hexpand(True)
        panel.append(flow)
        return panel, flow

    def _build_chord_line_flow(self, values: tuple[str, ...], section_title: str) -> Gtk.FlowBox:
        flow = Gtk.FlowBox()
        flow.add_css_class("chord-line-flow")
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_homogeneous(True)
        flow.set_min_children_per_line(4)
        flow.set_max_children_per_line(4)
        flow.set_row_spacing(4)
        flow.set_column_spacing(4)
        flow.set_hexpand(True)
        for value in values:
            chip = label(value or "—", "chord-chip")
            chip.set_xalign(0.5)
            # Reserve the same cell width for every pitch so the four-column
            # grid stays still when a root changes from C to C♯/D♭.
            chip.set_size_request(64, 32)
            chip.set_tooltip_text(f"{section_title} · cifrado de la fuente")
            flow.append(chip)
        return flow

    def _set_chord_panels(self, analysis: AudioAnalysis | None) -> None:
        for flow in (self.chord_flow, self.degree_flow):
            while child := flow.get_first_child():
                flow.remove(child)

        if not self.harmony_chart:
            placeholder_text = "Busca una versión humana para cargar los acordes."
            for flow in (self.chord_flow, self.degree_flow):
                placeholder = label(placeholder_text, "chord-placeholder", wrap=True)
                placeholder.set_xalign(0.5)
                flow.append(placeholder)
            return

        chart_sections = self.harmony_chart.transposed_sections(self.pitch_shift)
        degree_sections = self.harmony_chart.degrees(self.pitch_shift)
        for chart_section, degree_section in zip(chart_sections, degree_sections):
            chord_values = tuple(chord for line in chart_section.lines for chord in line.chords)
            degree_values = tuple(degree for line in degree_section.lines for degree in line.chords)
            if not chord_values:
                continue
            self.chord_flow.append(label(chart_section.title, "chord-section-title"))
            self.degree_flow.append(label(degree_section.title, "chord-section-title"))
            self.chord_flow.append(self._build_chord_line_flow(chord_values, chart_section.title))
            self.degree_flow.append(self._build_chord_line_flow(degree_values, degree_section.title))

    def _build_harmony_source_panel(self) -> Gtk.Box:
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        panel.add_css_class("harmony-source-panel")
        heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        heading.append(label("Cifrado humano", "section-heading"))
        heading.append(label("Cifra Club · versiones revisadas", "section-note"))
        panel.append(heading)
        panel.append(label("Busca el artista y la canción para cargar acordes reales, secciones y tonalidad.", "section-note", wrap=True))

        search_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.harmony_artist_entry = Gtk.Entry()
        self.harmony_artist_entry.set_placeholder_text("Artista")
        self.harmony_artist_entry.set_hexpand(True)
        self.harmony_title_entry = Gtk.Entry()
        self.harmony_title_entry.set_placeholder_text("Canción")
        self.harmony_title_entry.set_hexpand(True)
        self.harmony_title_entry.connect("activate", self._search_harmony)
        self.harmony_search_button = icon_button("Buscar acordes", "system-search-symbolic", "primary-action")
        self.harmony_search_button.connect("clicked", self._search_harmony)
        search_row.append(self.harmony_artist_entry)
        search_row.append(self.harmony_title_entry)
        search_row.append(self.harmony_search_button)
        panel.append(search_row)

        self.harmony_status = label("Aún no se ha seleccionado una fuente.", "harmony-status", wrap=True)
        panel.append(self.harmony_status)
        self.harmony_results = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.harmony_results.add_css_class("harmony-results")
        panel.append(self.harmony_results)
        return panel

    def _clear_harmony_results(self) -> None:
        while child := self.harmony_results.get_first_child():
            self.harmony_results.remove(child)

    def _candidate_detail(self, candidate: ChordCandidate) -> str:
        details: list[str] = []
        if candidate.key_name:
            details.append(candidate.key_name + (f" {candidate.scale}" if candidate.scale else ""))
        if candidate.capo is not None and candidate.capo > 0:
            details.append(f"capo {candidate.capo}")
        if candidate.instrument:
            details.append(candidate.instrument)
        if candidate.reviewed:
            details.append("revisada")
        return "  ·  ".join(details) or "tonalidad y formato se leerán al abrirla"

    def _open_harmony_source(self, _button, url: str) -> None:
        Gio.AppInfo.launch_default_for_uri(url, None)

    def _select_harmony_candidate(self, _button, candidate: ChordCandidate) -> None:
        if self._harmony_busy:
            return
        self._harmony_busy = True
        self.harmony_search_button.set_sensitive(False)
        self.harmony_status.set_text(f"Cargando {candidate.source_name} · {candidate.version}…")
        threading.Thread(target=self._harmony_fetch_worker, args=(candidate,), daemon=True).start()

    def _harmony_fetch_worker(self, candidate: ChordCandidate) -> None:
        try:
            chart = CifraClubProvider().fetch(candidate)
            GLib.idle_add(self._harmony_fetch_success, chart)
        except HarmonyError as exc:
            GLib.idle_add(self._harmony_error, str(exc))
        except Exception as exc:
            GLib.idle_add(self._harmony_error, f"Error inesperado: {exc}")

    def _harmony_fetch_success(self, chart: ChordChart) -> bool:
        self._harmony_busy = False
        self.harmony_chart = chart
        self.harmony_search_button.set_sensitive(True)
        source_note = " · revisión de calidad" if chart.reviewed else ""
        key_note = chart.display_key or "tonalidad no indicada"
        capo_note = f" · capo {chart.capo}" if chart.capo else ""
        self.harmony_status.set_text(f"{chart.source_name} · {chart.version} · {key_note}{capo_note}{source_note}")
        self._set_analysis_metrics(self.audio_info, self.audio_analysis)
        self._set_chord_panels(self.audio_analysis)
        self._set_pitch_controls(True)
        return False

    def _harmony_error(self, detail: str) -> bool:
        self._harmony_busy = False
        self.harmony_search_button.set_sensitive(True)
        self.harmony_status.set_text(f"No se pudo cargar el cifrado: {detail}")
        return False

    def _search_harmony(self, _button) -> None:
        if self._harmony_busy:
            return
        artist = self.harmony_artist_entry.get_text().strip()
        title = self.harmony_title_entry.get_text().strip()
        if not artist or not title:
            self.harmony_status.set_text("Escribe artista y canción para buscar el cifrado.")
            return
        self._harmony_busy = True
        self.harmony_search_button.set_sensitive(False)
        self.harmony_status.set_text("Buscando versiones en Cifra Club…")
        self._clear_harmony_results()
        threading.Thread(target=self._harmony_search_worker, args=(artist, title), daemon=True).start()

    def _harmony_search_worker(self, artist: str, title: str) -> None:
        try:
            candidates = CifraClubProvider().search(artist, title)
            GLib.idle_add(self._harmony_search_success, candidates)
        except HarmonyError as exc:
            GLib.idle_add(self._harmony_error, str(exc))
        except Exception as exc:
            GLib.idle_add(self._harmony_error, f"Error inesperado: {exc}")

    def _harmony_search_success(self, candidates: tuple[ChordCandidate, ...]) -> bool:
        self._harmony_busy = False
        self.harmony_candidates = candidates
        self.harmony_search_button.set_sensitive(True)
        self._clear_harmony_results()
        if not candidates:
            self.harmony_status.set_text("No hay versiones disponibles.")
            return False
        first_candidate = candidates[0]
        self.harmony_status.set_text(
            f"{len(candidates)} versiones encontradas · cargando {first_candidate.version}"
        )
        for candidate in candidates:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.add_css_class("harmony-candidate-row")
            info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            info.set_hexpand(True)
            info.append(label(f"{candidate.source_name} · {candidate.version}", "harmony-candidate-title"))
            info.append(label(self._candidate_detail(candidate), "harmony-candidate-detail", wrap=True))
            row.append(info)
            source_button = icon_button("Fuente", "globe-symbolic", "compact-action")
            source_button.connect("clicked", self._open_harmony_source, candidate.url)
            use_button = icon_button("Usar", "check-symbolic", "primary-action")
            use_button.connect("clicked", self._select_harmony_candidate, candidate)
            row.append(source_button)
            row.append(use_button)
            self.harmony_results.append(row)
        self._select_harmony_candidate(None, first_candidate)
        return False

    def _build_analysis_metric(self, key: str, title: str) -> Gtk.Box:
        cell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        cell.add_css_class("analysis-metric")
        cell.add_css_class(f"analysis-metric-{key.replace("_", "-")}")
        cell.append(label(title, "metric-label"))
        value = label("—", "metric-value")
        value.set_hexpand(True)
        value.set_ellipsize(3)
        cell.append(value)
        detail = label("", "metric-detail")
        detail.set_hexpand(True)
        detail.set_ellipsize(3)
        cell.append(detail)
        self.analysis_metric_values[key] = value
        self.analysis_metric_details[key] = detail
        return cell

    def _set_analysis_metrics(self, info, analysis: AudioAnalysis | None) -> None:
        values = {key: "—" for key in self.analysis_metric_values}
        details = {key: "" for key in self.analysis_metric_details}
        if info is None:
            values.update({key: "…" for key in values})
            details["key"] = "calculando análisis musical"
        else:
            values.update({
                "duration": info.duration_label,
                "format": info.format_name,
                "sample_rate": info.sample_rate_label,
                "channels": f"{info.channels} ch" if info.channels else "—",
            })
            details.update({
                "duration": "tiempo total",
                "format": "archivo de entrada",
                "sample_rate": "frecuencia",
                "channels": info.channel_layout or "canales de audio",
            })
        if analysis:
            source_key = self.harmony_chart.transposed_key(self.pitch_shift) if self.harmony_chart else None
            displayed_key = source_key or transpose_note_name(analysis.key_name, self.pitch_shift) or "—"
            displayed_scale = self.harmony_chart.scale if self.harmony_chart else analysis.scale
            chord_count = self.harmony_chart.chord_count if self.harmony_chart else len(analysis.compact_chords)
            values.update({
                "key": displayed_key,
                "bpm": f"{analysis.bpm:.0f}" if analysis.bpm is not None else "—",
                "scale": displayed_scale.capitalize() if displayed_scale else "—",
                "lufs": f"{analysis.lufs:.1f}" if analysis.lufs is not None else "—",
                "dynamic": f"{analysis.dynamic_range_db:.1f}" if analysis.dynamic_range_db is not None else "—",
                "tempo_confidence": f"{analysis.tempo_confidence:.0%}" if analysis.tempo_confidence is not None else "—",
                "key_confidence": f"{analysis.key_confidence:.0%}" if analysis.key_confidence is not None else "—",
                "chords": str(chord_count),
            })
            if self.harmony_chart and self.harmony_chart.key_name:
                key_detail = f"Fuente {self.harmony_chart.source_name} · original {self.harmony_chart.key_name}"
            elif self.pitch_shift and analysis.key_name:
                key_detail = f"Original {analysis.key_name} · {self._pitch_text()}"
            else:
                key_detail = f"confianza {analysis.key_confidence:.0%}" if analysis.key_confidence is not None else "tonalidad estimada"
            details.update({
                "key": key_detail,
                "bpm": f"confianza {analysis.tempo_confidence:.0%}" if analysis.tempo_confidence is not None else "tempo detectado",
                "scale": "modo de la fuente" if self.harmony_chart else "modo estimado",
                "lufs": f"pico {analysis.peak_dbfs:.1f} dBFS" if analysis.peak_dbfs is not None else "sonoridad integrada",
                "dynamic": "dB de rango dinámico",
                "tempo_confidence": "estabilidad del tempo",
                "key_confidence": "fuente humana seleccionada" if self.harmony_chart else "confianza tonal",
                "chords": "acordes de la fuente" if self.harmony_chart else "selecciona un cifrado humano",
            })
        if self.harmony_chart:
            source_key = self.harmony_chart.transposed_key(self.pitch_shift)
            values.update({
                "key": source_key or "—",
                "scale": self.harmony_chart.scale.capitalize() if self.harmony_chart.scale else "—",
                "chords": str(self.harmony_chart.chord_count),
            })
            details.update({
                "key": f"Fuente {self.harmony_chart.source_name} · original {self.harmony_chart.key_name or 'no indicada'}",
                "scale": "modo de la fuente",
                "chords": "acordes de la fuente",
            })
        for key, widget in self.analysis_metric_values.items():
            widget.set_text(values[key])
            self.analysis_metric_details[key].set_text(details[key])

    def _build_sidebar(self) -> Gtk.Widget:
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        sidebar.add_css_class("sidebar")
        sidebar.set_size_request(380, -1)

        scroll = Gtk.ScrolledWindow()
        scroll.add_css_class("sidebar-scroll")
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        sidebar.append(scroll)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        body.set_margin_top(20)
        body.set_margin_bottom(20)
        body.set_margin_start(20)
        body.set_margin_end(20)
        scroll.set_child(body)

        output_card = self._card()
        output_card.add_css_class("output-card")
        output_heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        output_heading.append(ui_icon("folder-open-symbolic", 17))
        output_heading.append(label("Carpeta de trabajo", "card-title"))
        output_card.append(output_heading)
        output_card.append(label("Las pistas se mantienen en WAV para reproducir y mezclar rápido; los MP3 se exportan cuando los pides.", "card-caption", wrap=True))
        folder_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.folder_label = label("Ninguna carpeta elegida", "folder-path")
        self.folder_label.set_ellipsize(3)
        self.folder_label.set_hexpand(True)
        folder_row.append(self.folder_label)
        folder_button = icon_button("Elegir", "folder-open-symbolic", "folder-button")
        folder_button.connect("clicked", self._choose_folder)
        folder_row.append(folder_button)
        output_card.append(folder_row)
        body.append(output_card)

        self.file_card = self._card()
        self.file_card.add_css_class("analysis-file-card")
        self.file_card.set_visible(False)
        file_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        file_header.set_hexpand(True)
        self.file_name = label("", "file-name")
        self.file_name.set_hexpand(True)
        file_header.append(self.file_name)

        self.harmony_source_panel = self._build_harmony_source_panel()

        self.analysis_metric_values: dict[str, Gtk.Label] = {}
        self.analysis_metric_details: dict[str, Gtk.Label] = {}
        self.analysis_metrics = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.analysis_metrics.add_css_class("analysis-metrics")
        metric_grid = Gtk.Grid()
        metric_grid.add_css_class("analysis-metric-grid")
        metric_grid.set_column_homogeneous(True)
        metric_grid.set_row_spacing(6)
        metric_grid.set_column_spacing(6)
        metric_keys = (
            ("key", "TONALIDAD"),
            ("bpm", "BPM"),
            ("duration", "DURACIÓN"),
            ("scale", "ESCALA"),
            ("lufs", "LUFS"),
            ("dynamic", "DINÁMICA"),
            ("format", "FORMATO"),
            ("sample_rate", "MUESTREO"),
            ("channels", "CANALES"),
            ("tempo_confidence", "TEMPO ESTABLE"),
            ("key_confidence", "CONFIANZA TONAL"),
            ("chords", "ACORDES"),
        )
        for index, (key, title) in enumerate(metric_keys):
            metric = self._build_analysis_metric(key, title)
            metric_grid.attach(metric, index % 3, index // 3, 1, 1)
        self.analysis_metrics.append(metric_grid)
        self._set_analysis_metrics(None, None)

        self.analysis_tone_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.analysis_tone_bar.add_css_class("tone-card")
        analysis_title = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        analysis_title.set_hexpand(True)
        analysis_title.append(label("Transponer análisis", "section-heading"))
        analysis_title.append(label("Cambia la preescucha y los acordes/grados en vivo", "section-note"))
        self.analysis_tone_bar.append(analysis_title)
        self.analysis_pitch_down = Gtk.Button(label="−")
        self.analysis_pitch_down.add_css_class("tone-button")
        self.analysis_pitch_down.set_tooltip_text("Bajar un semitono")
        self.analysis_pitch_down.connect("clicked", lambda *_: self._adjust_pitch(-1))
        self.analysis_tone_bar.append(self.analysis_pitch_down)
        self.analysis_pitch_value = label("Original · 0 semitonos", "tone-value")
        self.analysis_pitch_value.set_xalign(0.5)
        self.analysis_pitch_value.set_size_request(140, -1)
        self.analysis_tone_bar.append(self.analysis_pitch_value)
        self.analysis_pitch_up = Gtk.Button(label="+")
        self.analysis_pitch_up.add_css_class("tone-button")
        self.analysis_pitch_up.set_tooltip_text("Subir un semitono")
        self.analysis_pitch_up.connect("clicked", lambda *_: self._adjust_pitch(1))
        self.analysis_tone_bar.append(self.analysis_pitch_up)
        self.analysis_pitch_reset = Gtk.Button(label="Original")
        self.analysis_pitch_reset.add_css_class("secondary-action")
        self.analysis_pitch_reset.set_tooltip_text("Volver a la tonalidad original")
        self.analysis_pitch_reset.connect("clicked", lambda *_: self._reset_pitch())
        self.analysis_tone_bar.append(self.analysis_pitch_reset)

        self.chord_panels = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.chord_panels.set_hexpand(True)
        self.chord_panel, self.chord_flow = self._build_chord_panel("Acordes de la fuente", "chord-panel-chords")
        self.degree_panel, self.degree_flow = self._build_chord_panel("Grados de escala", "chord-panel-degrees")
        self.chord_panel.set_hexpand(True)
        self.degree_panel.set_hexpand(True)
        self.chord_panels.append(self.chord_panel)
        self.chord_panels.append(self.degree_panel)
        self.file_card.append(file_header)
        self.file_card.append(self.harmony_source_panel)
        self.file_card.append(self.analysis_metrics)
        self.file_card.append(self.analysis_tone_bar)
        self.file_card.append(self.chord_panels)
        self._set_pitch_controls(False)
        self._set_chord_panels(None)
        body.append(self.file_card)

        for key in ("vocals", "drums", "bass", "guitar", "piano"):
            check = Gtk.CheckButton()
            check.set_active(True)
            check.set_visible(False)
            check.connect("toggled", self._selection_changed)
            self.track_checks[key] = check
        other_check = Gtk.CheckButton()
        other_check.set_active(True)
        other_check.set_sensitive(False)
        other_check.set_visible(False)
        self.track_checks["other"] = other_check
        self._sync_header_extract_buttons()

        self.sidebar_status = label("Selecciona un audio y una carpeta para comenzar.", "helper", wrap=True)
        self.sidebar_status.set_visible(False)

        return sidebar

    def _build_workspace(self) -> Gtk.Widget:
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.add_css_class("workspace")
        outer.set_hexpand(True)
        outer.set_vexpand(True)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        outer.append(scroll)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.add_css_class("workspace-content")
        content.set_margin_top(24)
        content.set_margin_bottom(24)
        content.set_margin_start(26)
        content.set_margin_end(26)
        scroll.set_child(content)

        title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        title_stack = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        title_stack.set_hexpand(True)
        title_stack.append(label("02  ·  RESULTADO", "eyebrow"))
        title_stack.append(label("La exportación está preparada.", "page-title"))
        title_stack.append(label("Reproduce tus stems sincronizados y ajusta cada pista con claridad.", "page-subtitle"))
        title_row.append(title_stack)
        self.export_button = icon_button("Exportar mezcla MP3", "document-save-symbolic")
        self.export_button.set_sensitive(False)
        self.export_button.connect("clicked", self._export_mix)
        title_row.append(self.export_button)
        self.export_stems_button = icon_button("Exportar pistas MP3", "document-save-symbolic")
        self.export_stems_button.set_sensitive(False)
        self.export_stems_button.connect("clicked", self._export_stems)
        title_row.append(self.export_stems_button)
        open_button = icon_button("Abrir carpeta", "folder-open-symbolic")
        open_button.connect("clicked", self._open_results)
        title_row.append(open_button)
        content.append(title_row)

        self.status_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.status_card.add_css_class("status-card")
        status_mark = Gtk.Box()
        status_mark.add_css_class("status-mark")
        status_mark.set_size_request(38, 38)
        status_mark.set_hexpand(False)
        status_mark.set_vexpand(False)
        status_mark.set_valign(Gtk.Align.CENTER)
        status_mark.append(centered_image(ui_icon("audio-x-generic-symbolic", 19)))
        self.status_card.append(status_mark)
        status_stack = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        status_stack.set_hexpand(True)
        self.status_title = label("Listo para empezar", "status-title")
        self.status_detail = label("La sesión aparecerá aquí cuando cargues una mezcla.", "status-detail", wrap=True)
        status_stack.append(self.status_title)
        status_stack.append(self.status_detail)
        self.processing_elapsed = label("Tiempo transcurrido · 0,0 s", "processing-elapsed")
        self.processing_elapsed.set_visible(False)
        status_stack.append(self.processing_elapsed)
        self.status_card.append(status_stack)
        self.cancel_analysis_button = icon_button("Cancelar análisis", "window-close-symbolic", "cancel-action")
        self.cancel_analysis_button.set_visible(False)
        self.cancel_analysis_button.connect("clicked", self._cancel_analysis)
        self.status_card.append(self.cancel_analysis_button)
        self.status_pill = label("ESPERANDO AUDIO", "status-pill pending")
        self.status_card.append(self.status_pill)
        content.append(self.status_card)

        self.progress = Gtk.ProgressBar()
        self.progress.set_visible(False)
        self.progress.set_show_text(False)
        content.append(self.progress)

        player_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        player_card.add_css_class("player-card")
        timeline_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.current_time = label("0:00", "time-label")
        timeline_row.append(self.current_time)
        self.timeline = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 0.001)
        self.timeline.set_draw_value(False)
        self.timeline.set_hexpand(True)
        self.timeline.connect("value-changed", self._timeline_changed)
        timeline_row.append(self.timeline)
        self.total_time = label("0:00", "time-label")
        self.total_time.set_xalign(1)
        timeline_row.append(self.total_time)
        player_card.append(timeline_row)

        transport = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        transport.add_css_class("transport")
        transport.set_halign(Gtk.Align.CENTER)
        stop = Gtk.Button()
        stop.add_css_class("transport-button")
        stop.set_child(ui_icon("media-playback-stop-symbolic", 16))
        stop.set_tooltip_text("Volver al inicio")
        stop.connect("clicked", lambda *_: self._stop())
        transport.append(stop)
        self.play_button = Gtk.Button()
        self.play_button.add_css_class("play-button")
        self.play_button.set_tooltip_text("Reproducir / pausar · Espacio")
        self.play_button.connect("clicked", lambda *_: self._toggle_play())
        self._set_play_icon(False)
        transport.append(self.play_button)

        player_card.append(transport)
        content.append(player_card)
        mix_heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        mix_heading.append(label("Pistas separadas", "section-heading"))
        mix_heading.append(label("Mute · Solo · Volumen", "section-note"))
        content.append(mix_heading)

        self.track_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.track_list.append(self._empty_state())
        content.append(self.track_list)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        footer.append(label("SPLIT TRACKS / UBUNTU", "eyebrow"))
        footer.append(label("·  Demucs 6s CPU  ·  WAV interno  ·  MP3 bajo demanda", "section-note"))
        content.append(footer)
        return outer

    def _empty_state(self) -> Gtk.Widget:
        empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        empty.add_css_class("empty-state")
        empty.set_halign(Gtk.Align.FILL)
        icon = ui_icon("audio-x-generic-symbolic", 30, "empty-icon")
        icon.set_halign(Gtk.Align.CENTER)
        empty.append(icon)
        title = label("Todavía no hay pistas", "empty-title")
        title.set_halign(Gtk.Align.CENTER)
        title.set_xalign(0.5)
        empty.append(title)
        copy = label("Cuando termine la separación, tus stems aparecerán aquí sincronizados y listos para escuchar.", "empty-copy", wrap=True)
        copy.set_halign(Gtk.Align.CENTER)
        copy.set_xalign(0.5)
        empty.append(copy)
        return empty


    def _set_separation_button_text(self, text: str) -> None:
        if self.header_split_button:
            self.header_split_button.set_label("Cancelar" if text.startswith("Cancelar") else "Separar")

    def _download_youtube(self, _button) -> None:
        if self._busy:
            return
        url = self.youtube_entry.get_text().strip()
        if not url:
            self._set_status("Falta el enlace", "Pega una URL de YouTube para descargar el audio", "REVISAR", pending=True)
            return
        self._busy = True
        self.cancel_event = threading.Event()
        self.youtube_button.set_sensitive(False)
        self._set_separation_button_text("Cancelar descarga")
        self.progress.set_visible(True)
        self.progress.set_fraction(0.0)
        self._set_status("Descargando audio", "La descarga se procesa localmente para esta sesión", "DESCARGANDO")
        self.sidebar_status.set_text("Puedes cancelar la descarga en cualquier momento.")
        self._launch_process_worker(self._youtube_worker, (url,))

    def _youtube_worker(self, url: str) -> None:
        try:
            result = self.engine.download_youtube(
                url,
                progress=lambda value, phase: GLib.idle_add(self._operation_progress, value, phase),
                cancel_event=self.cancel_event,
            )
            GLib.idle_add(self._youtube_success, result)
        except SeparationCancelled as exc:
            GLib.idle_add(self._operation_cancelled, str(exc))
        except AudioEngineError as exc:
            GLib.idle_add(self._operation_error, str(exc))
        except Exception as exc:
            GLib.idle_add(self._operation_error, f"Error inesperado: {exc}")

    def _youtube_success(self, result) -> bool:
        self._busy = False
        self.cancel_event = None
        self.youtube_button.set_sensitive(True)
        self._set_separation_button_text("Separar y preparar pistas")
        self.progress.set_visible(False)
        self.youtube_temp_dir = result.temporary_dir
        self._load_audio(str(result.path), keep_youtube_temp=True)
        artist, title = guess_artist_title(result.title, fallback_artist=result.artist)
        self.harmony_artist_entry.set_text(artist)
        self.harmony_title_entry.set_text(title)
        self.sidebar_status.set_text(f"Audio descargado: {result.title}")
        if artist and title:
            self._search_harmony(None)
        self._update_start_state()
        return False

    def _cleanup_youtube_temp(self) -> None:
        if self.youtube_temp_dir:
            shutil.rmtree(self.youtube_temp_dir, ignore_errors=True)
            self.youtube_temp_dir = None

    def _choose_audio(self, _button) -> None:
        dialog = Gtk.FileDialog(title="Seleccionar mezcla")
        dialog.open(self, None, self._audio_dialog_done)

    def _audio_dialog_done(self, dialog, result) -> None:
        try:
            selected = dialog.open_finish(result)
        except GLib.Error:
            return
        if selected:
            self._load_audio(selected.get_path())

    def _drop_audio(self, _target, value, _x, _y) -> bool:
        if isinstance(value, Gio.File):
            path = value.get_path()
            if path:
                self._load_audio(path)
                return True
        return False

    def _load_audio(self, path: str | None, *, keep_youtube_temp: bool = False) -> None:
        if not path:
            return
        if self.analysis_cancel_event:
            self.analysis_cancel_event.set()
        self._probe_generation += 1
        probe_generation = self._probe_generation
        analysis_cancel_event = threading.Event()
        self.analysis_cancel_event = analysis_cancel_event
        if not keep_youtube_temp:
            self._cleanup_youtube_temp()
        self.input_path = Path(path).expanduser().resolve()
        self.audio_info = None
        self.audio_analysis = None
        self.harmony_chart = None
        self.harmony_candidates = ()
        self._clear_harmony_results()
        self.harmony_artist_entry.set_text("")
        self.harmony_title_entry.set_text(self.input_path.stem)
        self.harmony_status.set_text("Aún no se ha seleccionado una fuente.")
        self._set_pitch_controls(False)
        self.pitch_shift = 0
        self._set_pitch_display()
        self.file_card.set_visible(True)
        self.file_name.set_text(self.input_path.name)
        self._set_analysis_metrics(None, None)
        self._set_chord_panels(None)
        self.progress.set_visible(True)
        self.progress.set_fraction(0.0)
        self.cancel_analysis_button.set_visible(True)
        self.cancel_analysis_button.set_sensitive(True)
        self._set_status("Analizando audio", "Comprobando duración, formato, canales y análisis armónico", "ANALIZANDO", pending=True)
        self._start_processing_clock()
        self._launch_process_worker(
            self._probe_worker,
            (self.input_path, analysis_cancel_event, probe_generation),
        )

    def _cancel_analysis(self, _button) -> None:
        if not self.analysis_cancel_event:
            return
        self.analysis_cancel_event.set()
        self.cancel_analysis_button.set_sensitive(False)
        self._set_status("Cancelando análisis", "Deteniendo FFmpeg y descartando el resultado parcial…", "CANCELANDO", pending=True)
        self.sidebar_status.set_text("Cancelando el análisis de esta canción…")

    def _probe_worker(self, path: Path, cancel_event: threading.Event, generation: int) -> None:
        try:
            info = self.engine.probe(path, cancel_event=cancel_event)
            if cancel_event.is_set():
                raise AnalysisCancelled("Análisis cancelado por el usuario.")
            analysis = None
            try:
                analysis = analyze_audio(path, cancel_event=cancel_event)
            except AnalysisCancelled:
                raise
            except (AnalysisError, OSError, ValueError):
                pass
            if cancel_event.is_set():
                raise AnalysisCancelled("Análisis cancelado por el usuario.")
            GLib.idle_add(self._probe_success, info, analysis, generation)
        except (AnalysisCancelled, SeparationCancelled) as exc:
            GLib.idle_add(self._analysis_cancelled, generation, str(exc))
        except AudioEngineError as exc:
            GLib.idle_add(self._analysis_error, generation, str(exc))

    def _analysis_error(self, generation: int, detail: str) -> bool:
        if generation != self._probe_generation or self._closing:
            return False
        self.analysis_cancel_event = None
        self.cancel_analysis_button.set_visible(False)
        return self._operation_error(detail)

    def _analysis_cancelled(self, generation: int, detail: str) -> bool:
        if generation != self._probe_generation or self._closing:
            return False
        self.analysis_cancel_event = None
        self._stop_processing_clock()
        self.progress.set_visible(False)
        self.cancel_analysis_button.set_visible(False)
        self._set_status("Análisis cancelado", detail, "CANCELADO", pending=True)
        self.sidebar_status.set_text("Carga otro audio o vuelve a seleccionarlo para analizarlo.")
        self._update_start_state()
        return False

    def _probe_success(self, info, analysis: AudioAnalysis | None = None, generation: int | None = None) -> bool:
        if self._closing or (generation is not None and generation != self._probe_generation):
            return False
        self.analysis_cancel_event = None
        self.cancel_analysis_button.set_visible(False)
        self.audio_info = info
        self.audio_analysis = analysis
        self._stop_processing_clock()
        self.progress.set_visible(False)
        self._set_pitch_controls(bool(self.harmony_chart))
        self._set_analysis_metrics(info, analysis)
        self._set_chord_panels(analysis)
        if info.channels == 2:
            self._set_status("Mezcla lista", "Estéreo detectado · Demucs puede preparar seis categorías", "LISTO")
            self.sidebar_status.set_text("Elige una carpeta de trabajo y pulsa separar.")
        else:
            self._set_status("Necesito una mezcla estéreo", "El motor Demucs actual trabaja con 2 canales", "REVISAR", pending=True)
            self.sidebar_status.set_text("Este build necesita una entrada estéreo para separar seis categorías reales.")
        self._update_start_state()
        return False

    def _choose_folder(self, _button) -> None:
        dialog = Gtk.FileDialog(title="Elegir carpeta de trabajo")
        dialog.select_folder(self, None, self._folder_dialog_done)

    def _folder_dialog_done(self, dialog, result) -> None:
        try:
            selected = dialog.select_folder_finish(result)
        except GLib.Error:
            return
        if selected and selected.get_path():
            self.output_folder = Path(selected.get_path()).expanduser().resolve()
            self.folder_label.set_text(str(self.output_folder))
            self._update_start_state()

    def _sync_header_extract_buttons(self) -> None:
        if not self.header_extract_buttons or not self.track_checks:
            return
        self._syncing_header_extract = True
        try:
            for key, button in self.header_extract_buttons.items():
                check = self.track_checks.get(key)
                if check:
                    button.set_active(check.get_active())
        finally:
            self._syncing_header_extract = False

    def _header_extract_toggled(self, key: str, button: Gtk.ToggleButton) -> None:
        if self._syncing_header_extract:
            return
        check = self.track_checks.get(key)
        if check:
            check.set_active(button.get_active())
        self._selection_changed()

    def _set_available(self, active: bool) -> None:
        for key, check in self.track_checks.items():
            if key != "other":
                check.set_active(active)
        self._selection_changed()

    def _selection_changed(self, *_args) -> None:
        self._sync_header_extract_buttons()
        self._update_start_state()

    def _update_start_state(self) -> None:
        selected = any(check.get_active() for key, check in self.track_checks.items() if key != "other")
        ready = bool(self.audio_info and self.output_folder and selected and self.audio_info.channels == 2)
        if self.header_split_button:
            self.header_split_button.set_sensitive(ready or self._busy)

    def _start_or_cancel(self, _button) -> None:
        if self._busy:
            if self.cancel_event:
                self.cancel_event.set()
                self.sidebar_status.set_text("Cancelando de forma segura…")
            return
        self._start_separation()

    def _start_separation(self) -> None:
        if not self.input_path or not self.output_folder:
            return
        self._busy = True
        self.cancel_event = threading.Event()
        self._set_separation_button_text("Cancelar separación")
        self.progress.set_visible(True)
        self.progress.set_fraction(0.0)
        self._set_status("Preparando separación", "Demucs 6s se ejecuta únicamente en este equipo", "PROCESANDO")
        self._start_processing_clock()
        self.sidebar_status.set_text("Puedes cancelar; se eliminarán los archivos parciales.")
        self._launch_process_worker(self._separation_worker)

    def _separation_worker(self) -> None:
        try:
            selected = tuple(key for key, check in self.track_checks.items() if check.get_active())
            result = self.engine.separate(
                self.input_path,
                self.output_folder,
                selected,
                progress=lambda value, phase: GLib.idle_add(self._operation_progress, value, phase),
                cancel_event=self.cancel_event,
            )
            GLib.idle_add(self._separation_success, result)
        except SeparationCancelled as exc:
            GLib.idle_add(self._operation_cancelled, str(exc))
        except AudioEngineError as exc:
            GLib.idle_add(self._operation_error, str(exc))
        except Exception as exc:
            GLib.idle_add(self._operation_error, f"Error inesperado: {exc}")

    def _operation_progress(self, value: float, phase: str) -> bool:
        self.progress.set_fraction(value)
        self.status_detail.set_text(phase)
        return False

    def _separation_success(self, result: SeparationResult) -> bool:
        self._busy = False
        self.cancel_event = None
        self._stop_processing_clock()
        self.result = result
        self.pitch_shift = 0
        self._set_pitch_display()
        self._set_separation_button_text("Separar y preparar pistas")
        self.progress.set_visible(False)
        self._load_stems(result)
        self._cleanup_youtube_temp()
        self._set_status("Pistas listas para escuchar", "Separación Demucs 6s completada", "LISTO")
        self.sidebar_status.set_text(f"Guardado en {result.output_dir}")
        self.export_button.set_sensitive(True)
        self.export_stems_button.set_sensitive(True)
        self._set_pitch_controls(True)
        self._update_start_state()
        return False

    def _load_stems(self, result: SeparationResult) -> None:
        self.player.close()
        self.track_states = [
            {"name": stem.name, "path": stem.path, "base_path": stem.path, "color": stem.color, "kind": stem.kind, "volume": 1.0, "mute": False, "solo": False}
            for stem in result.stems
        ]
        while child := self.track_list.get_first_child():
            self.track_list.remove(child)
        for index, state in enumerate(self.track_states):
            self.track_list.append(TrackRow(index, state, self._track_changed, self._export_track))
        try:
            self.player.load(self.track_states, self.audio_info.duration)
        except Exception as exc:
            self._set_status("Pistas preparadas", f"La reproducción no está disponible: {exc}", "REVISAR", pending=True)
        self.timeline.set_range(0, max(0.1, self.audio_info.duration))
        self.timeline.set_value(0)
        self.total_time.set_text(fmt_time(self.audio_info.duration))

    def _track_changed(self, index: int, state: dict) -> None:
        if index >= len(self.track_states):
            return
        self.track_states[index] = state
        self.player.update_mix(self.track_states)

    def _set_play_icon(self, playing: bool) -> None:
        if hasattr(self, "play_button"):
            name = "media-playback-pause-symbolic" if playing else "media-playback-start-symbolic"
            self.play_button.set_child(ui_icon(name, 18))

    def _toggle_play(self) -> None:
        if not self.result:
            return
        if self.player.playing:
            self.player.pause()
            self._set_play_icon(False)
        else:
            self.player.play()
            self._set_play_icon(True)

    def _stop(self) -> None:
        self.player.stop()
        self._set_play_icon(False)
        self._set_timeline(0)

    def _timeline_changed(self, scale) -> None:
        if not self._updating_timeline and self.result:
            self.player.seek(scale.get_value())

    def _set_timeline(self, seconds: float) -> None:
        duration = max(self.audio_info.duration if self.audio_info else 1, 1)
        self._updating_timeline = True
        self.timeline.set_value(max(0, min(duration, seconds)))
        self._updating_timeline = False
        self.current_time.set_text(fmt_time(seconds))

    def _update_playback(self) -> bool:
        if self.result and self.player.pipeline:
            position = self.player.position()
            self._set_timeline(position)
            if not self.player.playing and position >= max(0.1, self.audio_info.duration - 0.2):
                self._set_play_icon(False)
        return True

    def _pitch_text(self) -> str:
        if self.pitch_shift == 0:
            return "Original · 0 semitonos"
        sign = "+" if self.pitch_shift > 0 else "−"
        amount = abs(self.pitch_shift)
        unit = "semitono" if amount == 1 else "semitonos"
        return f"{sign}{amount} {unit}"

    def _set_pitch_display(self) -> None:
        if hasattr(self, "analysis_pitch_value"):
            self.analysis_pitch_value.set_text(self._pitch_text())
        if self.audio_analysis or self.harmony_chart:
            self._set_analysis_metrics(self.audio_info, self.audio_analysis)
            self._set_chord_panels(self.audio_analysis)

    def _set_pitch_controls(self, enabled: bool) -> None:
        if not hasattr(self, "analysis_pitch_down"):
            return
        has_chart = bool(self.harmony_chart)
        has_playback = bool(self.result and self.audio_info and self.player.pitch_supported)
        available = bool(enabled and not self._busy and (has_chart or has_playback))
        self.analysis_pitch_down.set_sensitive(available and self.pitch_shift > -12)
        self.analysis_pitch_up.set_sensitive(available and self.pitch_shift < 12)
        self.analysis_pitch_reset.set_sensitive(available and self.pitch_shift != 0)

    def _adjust_pitch(self, delta: int) -> None:
        self._preview_pitch(max(-12, min(12, self.pitch_shift + delta)))

    def _reset_pitch(self) -> None:
        self._preview_pitch(0)

    def _preview_pitch(self, semitones: int) -> None:
        if self._busy or not self.audio_info or semitones == self.pitch_shift or not (self.result or self.harmony_chart):
            return
        previous = self.pitch_shift
        if self.result:
            if not self.player.pitch_supported:
                self._set_status(
                    "Preescucha no disponible",
                    "Instala gstreamer1.0-plugins-bad para cambiar el tono mientras suena.",
                    "REVISAR",
                    pending=True,
                )
                return
            try:
                self.player.set_pitch(semitones)
            except Exception as exc:
                self._set_status("No se pudo cambiar la preescucha", str(exc), "REVISAR", pending=True)
                return
        self.pitch_shift = semitones
        self._set_pitch_display()
        self._set_pitch_controls(True)
        if self.result:
            detail = f"Escuchando {self._pitch_text()} · cambio solo en la preescucha"
            self._set_status("Preescucha de tonalidad", detail, "ESCUCHANDO")
            if previous != semitones:
                self._set_timeline(self.player.position())
        elif self.harmony_chart:
            shown_key = self.harmony_chart.transposed_key(semitones) or "otra tonalidad"
            self.harmony_status.set_text(f"Cifrado mostrado en {shown_key} · {self._pitch_text()}")

    def _begin_stems_export(self, stems: tuple[dict, ...], single: bool) -> None:
        if not self.result or self._busy or not stems:
            return
        self._busy = True
        self.youtube_button.set_sensitive(False)
        if self.header_split_button:
            self.header_split_button.set_sensitive(False)
        self.export_button.set_sensitive(False)
        self.export_stems_button.set_sensitive(False)
        self.cancel_event = threading.Event()
        self.progress.set_visible(True)
        self.progress.set_fraction(0.0)
        title = "Exportando pista MP3" if single else "Exportando pistas MP3"
        self._set_status(title, "Preparando archivos MP3 sin alterar los WAV internos", "EXPORTANDO")
        self._launch_process_worker(self._stems_export_worker, (stems,))

    def _export_track(self, index: int) -> None:
        if index < 0 or index >= len(self.track_states):
            return
        self._begin_stems_export((dict(self.track_states[index]),), True)

    def _active_track_states(self) -> tuple[dict, ...]:
        solo_exists = any(item.get("solo", False) for item in self.track_states)
        return tuple(
            dict(item)
            for item in self.track_states
            if not item.get("mute", False) and (not solo_exists or item.get("solo", False))
        )

    def _export_stems(self, _button) -> None:
        stems = self._active_track_states()
        if not stems:
            self._set_status("No hay pistas activas", "Desactiva Mute o Solo antes de exportar los MP3", "REVISAR", pending=True)
            return
        self._begin_stems_export(stems, False)

    def _stems_export_worker(self, stems: tuple[dict, ...]) -> None:
        try:
            paths = self.engine.export_stems_mp3(
                stems,
                self.result.output_dir,
                self.audio_info.sample_rate,
                self.audio_info.channels,
                progress=lambda value, phase: GLib.idle_add(self._operation_progress, value, phase),
                cancel_event=self.cancel_event,
            )
            GLib.idle_add(self._stems_export_success, paths)
        except AudioEngineError as exc:
            GLib.idle_add(self._stems_export_error, str(exc))
        except Exception as exc:
            GLib.idle_add(self._stems_export_error, f"Error inesperado: {exc}")

    def _stems_export_success(self, paths: tuple[Path, ...]) -> bool:
        self._busy = False
        self.cancel_event = None
        self.progress.set_visible(False)
        self.youtube_button.set_sensitive(True)
        self.export_button.set_sensitive(True)
        self.export_stems_button.set_sensitive(True)
        self._update_start_state()
        if len(paths) == 1:
            detail = f"{paths[0].name} guardado en {paths[0].parent}"
        else:
            detail = f"{len(paths)} pistas MP3 guardadas en {paths[0].parent}"
        self._set_status("Pistas MP3 exportadas", detail, "LISTO")
        return False

    def _stems_export_error(self, detail: str) -> bool:
        self._busy = False
        self.cancel_event = None
        self.progress.set_visible(False)
        self.youtube_button.set_sensitive(True)
        self.export_button.set_sensitive(bool(self.result))
        self.export_stems_button.set_sensitive(bool(self.result))
        self._update_start_state()
        self._set_status("No se pudieron exportar las pistas", detail, "REVISAR", pending=True)
        return False

    def _export_mix(self, _button) -> None:
        if not self.result or self._busy:
            return
        self._busy = True
        self.cancel_event = threading.Event()
        self.export_button.set_sensitive(False)
        self.export_stems_button.set_sensitive(False)
        self.progress.set_visible(True)
        self.progress.set_fraction(0)
        self._set_status("Exportando mezcla", "Aplicando volumen, mute y solo offline", "EXPORTANDO")
        self._launch_process_worker(self._mix_worker)

    def _mix_worker(self) -> None:
        try:
            output, warning = self.engine.mix(
                self.track_states,
                self.result.output_dir,
                self.audio_info.sample_rate,
                self.audio_info.channels,
                progress=lambda value, phase: GLib.idle_add(self._operation_progress, value, phase),
                cancel_event=self.cancel_event,
            )
            GLib.idle_add(self._mix_success, output, warning)
        except AudioEngineError as exc:
            GLib.idle_add(self._operation_error, str(exc))

    def _mix_success(self, output: Path, warning: str | None) -> bool:
        self._busy = False
        self.cancel_event = None
        self.progress.set_visible(False)
        self.export_button.set_sensitive(True)
        self.export_stems_button.set_sensitive(True)
        detail = f"Mezcla guardada en {output.parent} · archivo {output.name}"
        if warning:
            detail += f" · {warning}"
        self._set_status("Mezcla exportada", detail, "LISTO")
        return False

    def _open_results(self, _button) -> None:
        target = self.result.output_dir if self.result else self.output_folder
        if target and target.exists():
            Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(str(target)).get_uri(), None)
        else:
            self._set_status("Aún no hay resultados", "Primero prepara una separación", "ESPERANDO", pending=True)

    def _operation_cancelled(self, detail: str) -> bool:
        self._busy = False
        self.cancel_event = None
        self._stop_processing_clock()
        self.progress.set_visible(False)
        self.youtube_button.set_sensitive(True)
        self._set_separation_button_text("Separar y preparar pistas")
        self._cleanup_youtube_temp()
        self._set_status("Separación cancelada", detail, "CANCELADO", pending=True)
        self.sidebar_status.set_text("No se han conservado archivos parciales.")
        self._update_start_state()
        return False

    def _operation_error(self, detail: str) -> bool:
        self._busy = False
        self.cancel_event = None
        self._stop_processing_clock()
        self.progress.set_visible(False)
        self.youtube_button.set_sensitive(True)
        self._set_separation_button_text("Separar y preparar pistas")
        self._cleanup_youtube_temp()
        self._set_status("No se pudo completar", detail, "REVISAR", pending=True)
        self.sidebar_status.set_text(detail)
        self.export_button.set_sensitive(bool(self.result))
        self.export_stems_button.set_sensitive(bool(self.result))
        self._update_start_state()
        return False


    def _start_processing_clock(self) -> None:
        self.processing_started_at = time.monotonic()
        self.processing_elapsed.set_visible(True)
        self._update_processing_clock()
        if self.processing_timer_id is None:
            self.processing_timer_id = GLib.timeout_add(250, self._update_processing_clock)

    def _stop_processing_clock(self) -> None:
        self.processing_started_at = None
        self.processing_elapsed.set_visible(False)
        if self.processing_timer_id is not None:
            GLib.source_remove(self.processing_timer_id)
            self.processing_timer_id = None

    def _update_processing_clock(self) -> bool:
        if self.processing_started_at is None:
            self.processing_timer_id = None
            return False
        elapsed = max(0.0, time.monotonic() - self.processing_started_at)
        self.processing_elapsed.set_text(f"Tiempo transcurrido · {elapsed:.1f} s")
        if self.progress.get_visible() and self.progress.get_fraction() <= 0.001:
            self.progress.pulse()
        return True

    def _set_status(self, title: str, detail: str, pill: str, pending: bool = False) -> None:
        self.status_title.set_text(title)
        self.status_detail.set_text(detail)
        self.status_pill.set_text(pill)
        self.status_pill.set_css_classes(["status-pill", "pending"] if pending else ["status-pill"])

    def _player_error(self, message: str) -> None:
        GLib.idle_add(self._set_player_error, message)

    def _set_player_error(self, message: str) -> bool:
        self._set_status("Error de reproducción", message, "REVISAR", pending=True)
        return False

    def _player_eos(self) -> None:
        GLib.idle_add(self._eos_ui)

    def _eos_ui(self) -> bool:
        self._set_play_icon(False)
        return False

    def _install_keyboard_shortcut(self) -> None:
        controller = Gtk.EventControllerKey()
        controller.connect("key-pressed", self._key_pressed)
        self.add_controller(controller)

    def _key_pressed(self, _controller, keyval, _keycode, _state) -> bool:
        if keyval != Gdk.KEY_space:
            return False
        focus = self.get_focus()
        if isinstance(focus, (Gtk.Entry, Gtk.TextView, Gtk.SearchEntry)):
            return False
        self._toggle_play()
        return True

    def close_request(self) -> bool:
        self._closing = True
        if self.analysis_cancel_event:
            self.analysis_cancel_event.set()
        if self.cancel_event:
            self.cancel_event.set()
        self._stop_processing_clock()
        self.player.close()
        deadline = time.monotonic() + 3.0
        for thread in self._process_threads:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if thread.is_alive():
                thread.join(remaining)
        self._cleanup_youtube_temp()
        return super().close_request()


class SplitTracksApplication(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="com.splittracks.SplitTracks", flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_activate(self) -> None:
        window = self.props.active_window
        if not window:
            window = MainWindow(self)
        window.present()


def main() -> int:
    app = SplitTracksApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
