#!/usr/bin/env python3
"""StemForge — local stereo stem utility for Ubuntu."""

from __future__ import annotations

import shutil
import sys
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gst", "1.0")
from gi.repository import Gdk, Gio, GLib, GObject, Gtk

from engine import AudioEngineError, SeparationCancelled, SeparationEngine, SeparationResult, STEM_LABELS, STEM_ORDER
from player import MixerPlayer


APP_NAME = "StemForge"


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


class Waveform(Gtk.DrawingArea):
    def __init__(self):
        super().__init__()
        self.progress = 0.0
        self.set_content_height(88)
        self.set_draw_func(self._draw)

    def set_progress(self, value: float) -> None:
        self.progress = max(0.0, min(1.0, value))
        self.queue_draw()

    def _draw(self, _area, context, width, height) -> None:
        import math

        context.set_line_width(2.0)
        bars = max(1, int(width / 7))
        for index in range(bars):
            x = (index + 0.5) * width / bars
            wave = abs(math.sin(index * 0.83) * 0.46 + math.sin(index * 0.19) * 0.27)
            bar_height = max(7, (height - 18) * (0.20 + wave * 0.8))
            active = (index / bars) <= self.progress
            if active:
                context.set_source_rgba(0.43, 0.88, 0.69, 0.95)
            else:
                context.set_source_rgba(0.34, 0.39, 0.49, 0.62)
            context.move_to(x, (height - bar_height) / 2)
            context.line_to(x, (height + bar_height) / 2)
            context.stroke()


class TrackRow(Gtk.Box):
    def __init__(self, index: int, stem: dict, changed):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.add_css_class("track-row")
        self.index = index
        self.stem = stem
        self.changed = changed
        self.set_margin_bottom(8)

        dot = Gtk.Label(label="●")
        dot.add_css_class("track-dot")
        dot.set_width_chars(1)
        dot.set_xalign(0.5)
        dot.set_hexpand(False)
        dot.set_markup(f'<span foreground="{stem["color"]}">●</span>')
        self.append(dot)

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info.set_hexpand(True)
        info.append(label(stem["name"], "track-name"))
        info.append(label(stem["kind"], "track-kind"))
        self.append(info)

        self.mute = Gtk.ToggleButton(label="M")
        self.mute.add_css_class("track-toggle")
        self.mute.set_tooltip_text("Mute")
        self.mute.connect("toggled", self._on_toggle)
        self.append(self.mute)

        self.solo = Gtk.ToggleButton(label="S")
        self.solo.add_css_class("track-toggle")
        self.solo.add_css_class("solo")
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
        self.output_folder: Path | None = None
        self.result: SeparationResult | None = None
        self.track_states: list[dict] = []
        self.cancel_event: threading.Event | None = None
        self.youtube_temp_dir: Path | None = None
        self.track_checks: dict[str, Gtk.CheckButton] = {}
        self._busy = False
        self._updating_timeline = False

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
        header.set_show_title_buttons(True)
        brand = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        mark = label("S", "brand-mark")
        mark.set_xalign(0.5)
        mark.set_yalign(0.5)
        brand.append(mark)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        titles.append(label(APP_NAME, "brand-title"))
        titles.append(label("STUDIO LOCAL DE STEMS", "brand-subtitle"))
        brand.append(titles)
        header.set_title_widget(brand)

        local = label("●  UBUNTU · LOCAL", "status-pill")
        local.set_tooltip_text("Procesamiento local; el audio no sale de este equipo")
        header.pack_end(local)
        self.set_titlebar(header)

    def _build_content(self) -> None:
        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.set_child(root)
        root.append(self._build_sidebar())
        root.append(self._build_workspace())

    def _card(self) -> Gtk.Box:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.add_css_class("card")
        return card

    def _build_sidebar(self) -> Gtk.Widget:
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        sidebar.add_css_class("sidebar")
        sidebar.set_size_request(362, -1)

        scroll = Gtk.ScrolledWindow()
        scroll.add_css_class("sidebar-scroll")
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        sidebar.append(scroll)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        body.set_margin_top(24)
        body.set_margin_bottom(22)
        body.set_margin_start(22)
        body.set_margin_end(22)
        scroll.set_child(body)

        body.append(label("01  ·  NUEVA SESIÓN", "eyebrow"))
        body.append(label("Divide tu mezcla", "page-title"))
        body.append(label("Carga un audio estéreo o pega un enlace de YouTube; después escucha el resultado en un mismo reloj.", "page-subtitle", wrap=True))

        source_card = self._card()
        source_card.append(label("Fuente de audio", "card-title"))
        source_card.append(label("WAV · FLAC · OGG · MP3 · M4A", "card-caption"))
        drop = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        drop.add_css_class("drop-zone")
        drop.set_halign(Gtk.Align.FILL)
        icon = label("↥", "drop-icon")
        icon.set_halign(Gtk.Align.CENTER)
        icon.set_xalign(0.5)
        drop.append(icon)
        drop_title = label("Suelta una canción aquí", "card-title")
        drop_title.set_halign(Gtk.Align.CENTER)
        drop_title.set_xalign(0.5)
        drop.append(drop_title)
        browse = Gtk.Button(label="Seleccionar audio")
        browse.add_css_class("secondary-action")
        browse.set_halign(Gtk.Align.CENTER)
        browse.connect("clicked", self._choose_audio)
        drop.append(browse)
        self.drop_zone = drop
        target = Gtk.DropTarget.new(Gio.File, Gdk.DragAction.COPY)
        target.connect("drop", self._drop_audio)
        drop.add_controller(target)
        source_card.append(drop)

        source_card.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        source_card.append(label("O pega un enlace de YouTube", "card-title"))
        source_card.append(label("Se descarga solo el audio y se guarda como archivo temporal local.", "card-caption", wrap=True))
        youtube_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.youtube_entry = Gtk.Entry()
        self.youtube_entry.set_placeholder_text("https://www.youtube.com/watch?v=…")
        self.youtube_entry.set_hexpand(True)
        self.youtube_entry.connect("activate", self._download_youtube)
        youtube_row.append(self.youtube_entry)
        self.youtube_button = Gtk.Button(label="Descargar")
        self.youtube_button.add_css_class("secondary-action")
        self.youtube_button.connect("clicked", self._download_youtube)
        youtube_row.append(self.youtube_button)
        source_card.append(youtube_row)

        self.file_card = self._card()
        self.file_card.set_visible(False)
        self.file_name = label("", "file-name")
        self.file_meta = label("", "file-meta")
        self.file_card.append(self.file_name)
        self.file_card.append(self.file_meta)
        body.append(source_card)
        body.append(self.file_card)

        extract_card = self._card()
        extract_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        extract_header.append(label("Qué extraer", "card-title"))
        all_button = Gtk.Button(label="Todas")
        all_button.add_css_class("secondary-action")
        all_button.set_hexpand(True)
        all_button.set_halign(Gtk.Align.END)
        all_button.connect("clicked", lambda *_: self._set_available(True))
        none_button = Gtk.Button(label="Ninguna")
        none_button.add_css_class("secondary-action")
        none_button.connect("clicked", lambda *_: self._set_available(False))
        extract_header.append(all_button)
        extract_header.append(none_button)
        extract_card.append(extract_header)
        extract_card.append(label("Solo mostramos salidas que el motor actual puede producir de forma real.", "card-caption", wrap=True))
        extract_card.append(label("Selecciona las pistas que quieres conservar. Other se calcula como complemento.", "card-caption", wrap=True))
        for key in ("vocals", "drums", "bass", "guitar", "piano"):
            display_name, kind, _color = STEM_LABELS[key]
            check = Gtk.CheckButton(label=display_name)
            check.set_active(True)
            check.connect("toggled", self._selection_changed)
            self.track_checks[key] = check
            extract_card.append(check)
            note = label(kind, "card-caption")
            note.set_margin_start(31)
            extract_card.append(note)
        other_row = Gtk.CheckButton(label="Other")
        other_row.set_active(True)
        other_row.set_sensitive(False)
        other_row.set_tooltip_text("Se genera siempre sumando el Other del modelo y las pistas no seleccionadas")
        self.track_checks["other"] = other_row
        extract_card.append(other_row)
        other_note = label("Complemento automático de las categorías no seleccionadas", "card-caption")
        other_note.set_margin_start(31)
        extract_card.append(other_note)
        body.append(extract_card)

        output_card = self._card()
        output_card.append(label("Carpeta de trabajo", "card-title"))
        output_card.append(label("Elige dónde se guardarán los WAV y el informe.", "card-caption", wrap=True))
        folder_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.folder_label = label("Ninguna carpeta elegida", "folder-path")
        self.folder_label.set_ellipsize(3)
        self.folder_label.set_hexpand(True)
        folder_row.append(self.folder_label)
        folder_button = Gtk.Button(label="Elegir")
        folder_button.add_css_class("folder-button")
        folder_button.connect("clicked", self._choose_folder)
        folder_row.append(folder_button)
        output_card.append(folder_row)
        body.append(output_card)

        self.separate_button = Gtk.Button(label="Separar y preparar pistas")
        self.separate_button.add_css_class("primary-action")
        self.separate_button.set_sensitive(False)
        self.separate_button.connect("clicked", self._start_or_cancel)
        body.append(self.separate_button)
        self.sidebar_status = label("Selecciona un audio y una carpeta para comenzar.", "helper", wrap=True)
        body.append(self.sidebar_status)

        note = label("Uso personal: acceso completo, sin premium. Motor local Demucs 6s para voces, batería, bajo, guitarra, piano y Other.", "license-note", wrap=True)
        body.append(note)
        return sidebar

    def _build_workspace(self) -> Gtk.Widget:
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.set_hexpand(True)
        outer.set_vexpand(True)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        outer.append(scroll)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.set_margin_top(24)
        content.set_margin_bottom(24)
        content.set_margin_start(26)
        content.set_margin_end(26)
        scroll.set_child(content)

        title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        title_stack = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        title_stack.set_hexpand(True)
        title_stack.append(label("02  ·  MIXER", "eyebrow"))
        title_stack.append(label("Tu espacio de escucha", "page-title"))
        title_stack.append(label("Un reloj, dos pistas y control directo sobre cada stem.", "page-subtitle"))
        title_row.append(title_stack)
        self.export_button = Gtk.Button(label="Exportar mezcla")
        self.export_button.add_css_class("secondary-action")
        self.export_button.set_sensitive(False)
        self.export_button.connect("clicked", self._export_mix)
        title_row.append(self.export_button)
        open_button = Gtk.Button(label="Abrir carpeta")
        open_button.add_css_class("secondary-action")
        open_button.connect("clicked", self._open_results)
        title_row.append(open_button)
        content.append(title_row)

        self.status_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        self.status_card.add_css_class("status-card")
        status_stack = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        status_stack.set_hexpand(True)
        self.status_title = label("Listo para empezar", "status-title")
        self.status_detail = label("La sesión aparecerá aquí cuando cargues una mezcla.", "status-detail")
        status_stack.append(self.status_title)
        status_stack.append(self.status_detail)
        self.status_card.append(status_stack)
        self.status_pill = label("ESPERANDO AUDIO", "status-pill pending")
        self.status_card.append(self.status_pill)
        content.append(self.status_card)

        self.progress = Gtk.ProgressBar()
        self.progress.set_visible(False)
        self.progress.set_show_text(False)
        content.append(self.progress)

        wave_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        wave_card.add_css_class("wave-card")
        self.waveform = Waveform()
        wave_card.append(self.waveform)
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
        wave_card.append(timeline_row)

        transport = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        transport.add_css_class("transport")
        transport.set_halign(Gtk.Align.CENTER)
        stop = Gtk.Button(label="■")
        stop.set_tooltip_text("Volver al inicio")
        stop.connect("clicked", lambda *_: self._stop())
        transport.append(stop)
        self.play_button = Gtk.Button(label="▶")
        self.play_button.add_css_class("play-button")
        self.play_button.set_tooltip_text("Reproducir / pausar · Espacio")
        self.play_button.connect("clicked", lambda *_: self._toggle_play())
        transport.append(self.play_button)
        wave_card.append(transport)
        content.append(wave_card)

        mix_heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        mix_heading.append(label("Pistas separadas", "section-heading"))
        mix_heading.append(label("Mute · Solo · Volumen", "section-note"))
        content.append(mix_heading)

        self.track_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.track_list.append(self._empty_state())
        content.append(self.track_list)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        footer.append(label("STEMFORGE / UBUNTU", "eyebrow"))
        footer.append(label("·  Demucs 6s CPU  ·  Audio local  ·  WAV PCM", "section-note"))
        content.append(footer)
        return outer

    def _empty_state(self) -> Gtk.Widget:
        empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        empty.add_css_class("empty-state")
        empty.set_halign(Gtk.Align.FILL)
        icon = label("∿", "empty-icon")
        icon.set_halign(Gtk.Align.CENTER)
        icon.set_xalign(0.5)
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
        self.separate_button.set_label("Cancelar descarga")
        self.progress.set_visible(True)
        self.progress.set_fraction(0.0)
        self._set_status("Descargando audio", "La descarga se procesa localmente para esta sesión", "DESCARGANDO")
        self.sidebar_status.set_text("Puedes cancelar la descarga en cualquier momento.")
        threading.Thread(target=self._youtube_worker, args=(url,), daemon=True).start()

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
        self.separate_button.set_label("Separar y preparar pistas")
        self.progress.set_visible(False)
        self.youtube_temp_dir = result.temporary_dir
        self._load_audio(str(result.path), keep_youtube_temp=True)
        self.sidebar_status.set_text(f"Audio descargado: {result.title}")
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
        if not keep_youtube_temp:
            self._cleanup_youtube_temp()
        self.input_path = Path(path).expanduser().resolve()
        self.file_card.set_visible(True)
        self.file_name.set_text(self.input_path.name)
        self.file_meta.set_text("Analizando archivo…")
        self._set_status("Analizando audio", "Comprobando duración, formato y canales", "ANALIZANDO", pending=True)
        threading.Thread(target=self._probe_worker, args=(self.input_path,), daemon=True).start()

    def _probe_worker(self, path: Path) -> None:
        try:
            info = self.engine.probe(path)
            GLib.idle_add(self._probe_success, info)
        except AudioEngineError as exc:
            GLib.idle_add(self._operation_error, str(exc))

    def _probe_success(self, info) -> bool:
        self.audio_info = info
        self.file_meta.set_text(f"{info.format_name}  ·  {info.duration_label}  ·  {info.sample_rate_label}  ·  {info.channels} ch")
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

    def _set_available(self, active: bool) -> None:
        for key, check in self.track_checks.items():
            if key != "other":
                check.set_active(active)
        self._selection_changed()

    def _selection_changed(self, *_args) -> None:
        self._update_start_state()

    def _update_start_state(self) -> None:
        selected = any(check.get_active() for key, check in self.track_checks.items() if key != "other")
        ready = bool(self.audio_info and self.output_folder and selected and self.audio_info.channels == 2)
        self.separate_button.set_sensitive(ready or self._busy)

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
        self.separate_button.set_label("Cancelar separación")
        self.progress.set_visible(True)
        self.progress.set_fraction(0.0)
        self._set_status("Preparando separación", "Demucs 6s se ejecuta únicamente en este equipo", "PROCESANDO")
        self.sidebar_status.set_text("Puedes cancelar; se eliminarán los archivos parciales.")
        threading.Thread(target=self._separation_worker, daemon=True).start()

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
        self.result = result
        self.separate_button.set_label("Separar y preparar pistas")
        self.progress.set_visible(False)
        self._load_stems(result)
        self._cleanup_youtube_temp()
        self._set_status("Pistas listas para escuchar", "Separación Demucs 6s completada", "LISTO")
        self.sidebar_status.set_text(f"Guardado en {result.output_dir}")
        self.export_button.set_sensitive(True)
        self._update_start_state()
        return False

    def _load_stems(self, result: SeparationResult) -> None:
        self.player.close()
        self.track_states = [
            {"name": stem.name, "path": stem.path, "color": stem.color, "kind": stem.kind, "volume": 1.0, "mute": False, "solo": False}
            for stem in result.stems
        ]
        while child := self.track_list.get_first_child():
            self.track_list.remove(child)
        for index, state in enumerate(self.track_states):
            self.track_list.append(TrackRow(index, state, self._track_changed))
        try:
            self.player.load(self.track_states, self.audio_info.duration)
        except Exception as exc:
            self._set_status("Pistas exportadas", f"La reproducción no está disponible: {exc}", "REVISAR", pending=True)
        self.timeline.set_range(0, max(0.1, self.audio_info.duration))
        self.timeline.set_value(0)
        self.total_time.set_text(fmt_time(self.audio_info.duration))
        self.waveform.set_progress(0)

    def _track_changed(self, index: int, state: dict) -> None:
        if index >= len(self.track_states):
            return
        self.track_states[index] = state
        self.player.update_mix(self.track_states)

    def _toggle_play(self) -> None:
        if not self.result:
            return
        if self.player.playing:
            self.player.pause()
            self.play_button.set_label("▶")
        else:
            self.player.play()
            self.play_button.set_label("Ⅱ")

    def _stop(self) -> None:
        self.player.stop()
        self.play_button.set_label("▶")
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
        self.waveform.set_progress(seconds / duration)

    def _update_playback(self) -> bool:
        if self.result and self.player.pipeline:
            position = self.player.position()
            self._set_timeline(position)
            if not self.player.playing and position >= max(0.1, self.audio_info.duration - 0.2):
                self.play_button.set_label("▶")
        return True

    def _export_mix(self, _button) -> None:
        if not self.result or self._busy:
            return
        self._busy = True
        self.export_button.set_sensitive(False)
        self.progress.set_visible(True)
        self.progress.set_fraction(0)
        self._set_status("Exportando mezcla", "Aplicando volumen, mute y solo offline", "EXPORTANDO")
        threading.Thread(target=self._mix_worker, daemon=True).start()

    def _mix_worker(self) -> None:
        try:
            output, warning = self.engine.mix(
                self.track_states,
                self.result.output_dir,
                self.audio_info.sample_rate,
                self.audio_info.channels,
                progress=lambda value, phase: GLib.idle_add(self._operation_progress, value, phase),
            )
            GLib.idle_add(self._mix_success, output, warning)
        except AudioEngineError as exc:
            GLib.idle_add(self._operation_error, str(exc))

    def _mix_success(self, output: Path, warning: str | None) -> bool:
        self._busy = False
        self.progress.set_visible(False)
        self.export_button.set_sensitive(True)
        detail = f"{output.name} guardado en la sesión"
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
        self.progress.set_visible(False)
        self.youtube_button.set_sensitive(True)
        self.separate_button.set_label("Separar y preparar pistas")
        self._cleanup_youtube_temp()
        self._set_status("Separación cancelada", detail, "CANCELADO", pending=True)
        self.sidebar_status.set_text("No se han conservado archivos parciales.")
        self._update_start_state()
        return False

    def _operation_error(self, detail: str) -> bool:
        self._busy = False
        self.cancel_event = None
        self.progress.set_visible(False)
        self.youtube_button.set_sensitive(True)
        self.separate_button.set_label("Separar y preparar pistas")
        self._cleanup_youtube_temp()
        self._set_status("No se pudo completar", detail, "REVISAR", pending=True)
        self.sidebar_status.set_text(detail)
        self.export_button.set_sensitive(bool(self.result))
        self._update_start_state()
        return False

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
        self.play_button.set_label("▶")
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
        self.player.close()
        self._cleanup_youtube_temp()
        return super().close_request()


class StemForgeApplication(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="com.stemforge.StemForge", flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_activate(self) -> None:
        window = self.props.active_window
        if not window:
            window = MainWindow(self)
        window.present()


def main() -> int:
    app = StemForgeApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
