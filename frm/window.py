"""FRM player and review workspace."""
from dataclasses import asdict
import json
from pathlib import Path
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence, QShortcut, QColor
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QSpinBox, QDoubleSpinBox, QSlider, QCheckBox, QFileDialog,
    QMessageBox, QDialog, QPlainTextEdit, QListWidget, QListWidgetItem, QSplitter,
    QColorDialog, QInputDialog, QFrame)
from . import __version__
from .color import ColorSettings
from .media import discover, NUMBER
from .playback import PlayerSession
from .review import ReviewDocument
from .viewer import ReviewViewer


def aligned_frame(frame_a, offset):
    return frame_a + offset


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"FRM {__version__} / Player & Review")
        self.resize(1420, 900)
        self.setAcceptDrops(True)
        self.sessions = {slot: PlayerSession(self) for slot in ("A", "B")}
        self.document = ReviewDocument()
        self.index = 0
        self.target = 0
        self.playing = self.closing = False
        self.anchor = time.monotonic()
        self.anchor_frame = 0
        self.skipped = 0
        self.error_text = ""
        self.review_state = None
        self.incoming = {}
        self.file_filter = "Media (*.dpx *.exr *.tif *.tiff *.jpg *.jpeg *.png *.mov *.mp4 *.m4v);;All files (*)"
        self._menus()
        root = QWidget(); self.setCentralWidget(root)
        layout = QVBoxLayout(root); layout.setContentsMargins(12, 8, 12, 10); layout.setSpacing(8)
        header = QHBoxLayout()
        brand = QLabel("FRM"); brand.setObjectName("brand"); header.addWidget(brand)
        tag = QLabel("PLAYER / REVIEW"); tag.setObjectName("muted"); header.addWidget(tag)
        header.addSpacing(16)
        self._button(header, "Open A", lambda: self.open_dialog("A"))
        self._button(header, "Open B", lambda: self.open_dialog("B"))
        self.compare = QComboBox()
        for label, data in [("View A", "A"), ("View B", "B"), ("Side by side", "side"), ("Wipe A / B", "wipe")]:
            self.compare.addItem(label, data)
        self.compare.currentIndexChanged.connect(self.compare_changed); header.addWidget(self.compare)
        header.addWidget(QLabel("B offset"))
        self.offset = QSpinBox(); self.offset.setRange(-1000000, 1000000); self.offset.setSuffix(" fr")
        self.offset.setToolTip("B frame = A frame + offset. +10 advances B by ten frames. Missing frames stay blank.")
        self.offset.valueChanged.connect(self.offset_changed); header.addWidget(self.offset)
        header.addStretch()
        self.active = QComboBox(); self.active.addItems(["Source A", "Source B"]); header.addWidget(self.active)
        self._button(header, "Color", self.color_dialog)
        self._button(header, "Metadata", self.metadata_dialog)
        layout.addLayout(header)
        self.source_label = QLabel("Open a shot. Compare a version. Leave a note.")
        self.source_label.setObjectName("muted"); layout.addWidget(self.source_label)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.viewer = ReviewViewer(self.document)
        self.viewer.interaction.connect(self.pause_for_interaction)
        self.viewer.target_changed.connect(lambda slot: self.active.setCurrentIndex(0 if slot == "A" else 1))
        self.viewer.stroke_added.connect(self.add_stroke)
        self.splitter.addWidget(self.viewer)
        panel = QWidget(); panel.setMinimumWidth(260); panel.setMaximumWidth(380)
        notes_layout = QVBoxLayout(panel); notes_layout.setContentsMargins(12, 8, 6, 8)
        notes_layout.addWidget(QLabel("REVIEW NOTES"))
        self.notes = QListWidget(); self.notes.setWordWrap(True)
        self.notes.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.notes.itemClicked.connect(self.jump_note); notes_layout.addWidget(self.notes)
        self.note_preview = QPlainTextEdit(); self.note_preview.setReadOnly(True); self.note_preview.setMaximumHeight(130)
        self.note_preview.setPlaceholderText("Select a marked frame to read its note."); notes_layout.addWidget(self.note_preview)
        self._button(notes_layout, "Save review…", self.save_review)
        self._button(notes_layout, "Export annotated frames…", self.export_images)
        self._button(notes_layout, "Export PDF report…", self.export_pdf)
        self.splitter.addWidget(panel); self.splitter.setStretchFactor(0, 1)
        self.notes_panel = panel
        layout.addWidget(self.splitter, 1)
        line = QHBoxLayout()
        self.frame_label = QLabel("A — / B —"); line.addWidget(self.frame_label)
        line.addStretch()
        self.cache_label = QLabel("Ready"); self.cache_label.setObjectName("muted"); line.addWidget(self.cache_label)
        layout.addLayout(line)
        self.timeline = QSlider(Qt.Orientation.Horizontal); self.timeline.setRange(0, 0)
        self.timeline.valueChanged.connect(self.seek); layout.addWidget(self.timeline)
        transport = QHBoxLayout()
        self.cache_mode = QComboBox()
        for label, data in [("RAM cache while playing", "ram"), ("Disk cache while playing", "disk"), ("Direct / no cache", "off")]:
            self.cache_mode.addItem(label, data)
        self.cache_mode.currentIndexChanged.connect(self.cache_changed); transport.addWidget(self.cache_mode)
        self.budget = QComboBox()
        for label, size in [("256 MiB", 256 * 1024**2), ("512 MiB", 512 * 1024**2), ("1 GiB", 1024**3), ("2 GiB", 2 * 1024**3)]:
            self.budget.addItem(label, size)
        self.budget.setCurrentIndex(1)
        self.budget.setToolTip("Total preview cache budget, shared by A and B; decoder, display and note memory are additional.")
        self.budget.currentIndexChanged.connect(self.rebuild); transport.addWidget(self.budget)
        transport.addStretch()
        self._button(transport, "|‹", lambda: self.go(0))
        self._button(transport, "‹", lambda: self.step(-1))
        self.play_button = self._button(transport, "Play", self.toggle_play); self.play_button.setObjectName("primary")
        self._button(transport, "›", lambda: self.step(1))
        self.loop = QCheckBox("Loop"); self.loop.setChecked(True); transport.addWidget(self.loop)
        transport.addStretch()
        self.auto_fps = QCheckBox("Auto FPS"); self.auto_fps.setChecked(True); self.auto_fps.toggled.connect(self.auto_rate_changed)
        transport.addWidget(self.auto_fps)
        self.fps = QDoubleSpinBox(); self.fps.setRange(.001, 1000); self.fps.setDecimals(3); self.fps.setValue(24)
        self.fps.valueChanged.connect(self.manual_fps); transport.addWidget(self.fps)
        self.preview = QComboBox()
        for width in (1280, 1920, 3840):
            self.preview.addItem(f"Preview {width}", width)
        self.preview.currentIndexChanged.connect(self.rebuild); transport.addWidget(self.preview)
        layout.addLayout(transport)
        tools = QHBoxLayout()
        self.pen = QPushButton("Paint"); self.pen.setCheckable(True); self.pen.toggled.connect(self.set_painting); tools.addWidget(self.pen)
        self.swatch = self._button(tools, "Brush color", self.brush_color)
        self.brush = QSpinBox(); self.brush.setRange(1, 20); self.brush.setValue(4); self.brush.setSuffix(" px")
        self.brush.valueChanged.connect(lambda value: setattr(self.viewer, "brush_width", value)); tools.addWidget(self.brush)
        self._button(tools, "Undo stroke", self.undo_stroke)
        self._button(tools, "Clear frame", self.clear_annotation)
        self._button(tools, "Add / edit note", self.edit_note)
        tools.addStretch()
        self._button(tools, "Review notes", lambda: panel.setVisible(not panel.isVisible()))
        self._button(tools, "Fullscreen", self.fullscreen)
        layout.addLayout(tools)
        self.status = QLabel("Direct start / RAM cache fills as you play / Silent video preview")
        self.status.setObjectName("muted"); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.timer = QTimer(self); self.timer.setInterval(4); self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick); self.timer.start()
        for slot, session in self.sessions.items():
            session.prepared.connect(lambda s=slot: self.on_prepared(s))
            session.displayed.connect(lambda index, rgb, s=slot: self.on_frame(s, index, rgb))
            session.changed.connect(self.update_status)
            session.failed.connect(lambda message, s=slot: self.on_error(f"{s}: {message}"))
            session.ended.connect(lambda s=slot: self.on_end(s))
            session.closed.connect(self.session_closed)
        for key, callback in [("Space", self.toggle_play), ("Left", lambda: self.step(-1)), ("Right", lambda: self.step(1)),
                              ("Home", lambda: self.go(0)), ("F", self.fullscreen), ("Escape", self.showNormal)]:
            QShortcut(QKeySequence(key), self, activated=callback)

    @staticmethod
    def _button(layout, label, callback):
        button = QPushButton(label); button.clicked.connect(callback); layout.addWidget(button); return button

    def _menus(self):
        groups = {
            "Session": [("Open source A…", lambda: self.open_dialog("A"), "Ctrl+O"),
                        ("Open source B…", lambda: self.open_dialog("B"), "Ctrl+Shift+O"),
                        ("Open review…", self.load_review, "Ctrl+R"), ("Save review…", self.save_review, "Ctrl+S"),
                        ("Close source B", self.close_b, None), ("Close media", self.clear_media, "Ctrl+W"),
                        ("New review", self.new_review, None)],
            "Playback": [("Play / Pause", self.toggle_play, None)],
            "Annotations": [("Add / edit note", self.edit_note, None), ("Export PNG / JPG…", self.export_images, None),
                            ("Export PDF report…", self.export_pdf, None)],
            "Help": [("About FRM", self.about, None)],
        }
        for title, entries in groups.items():
            menu = self.menuBar().addMenu(title)
            for label, callback, shortcut in entries:
                action = QAction(label, self); action.triggered.connect(callback)
                if shortcut:
                    action.setShortcut(QKeySequence(shortcut))
                menu.addAction(action)

    def about(self):
        QMessageBox.information(self, "FRM", f"FRM {__version__} / Player & Review\nGPL-3.0-only\n\n"
            "Direct reading with optional bounded RAM or disk cache.\nA/B comparison, frame offsets, paint, notes and review reports.\n\n"
            "Space: play/pause · Arrows: step · F: fullscreen\nCache clears on normal close. RAM creates no FRM cache files.\nDisk cache may remain after a crash or forced termination.\n\n"
            "8-bit silent preview; no HDR/ICC reference output.\nMovie timing uses average FPS. Backward uncached movie seeks\nmay decode from the beginning to preserve frame accuracy.")

    def open_dialog(self, slot):
        path, _ = QFileDialog.getOpenFileName(self, f"Open source {slot}", "", self.file_filter)
        if path:
            self.open_path(path, slot)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and all(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if len(urls) not in (1, 2):
            self.on_error("Drop one shot, or two files for A/B comparison."); return
        self.open_path(urls[0].toLocalFile(), "A")
        if len(urls) == 2:
            self.open_path(urls[1].toLocalFile(), "B")

    def open_path(self, path, slot="A", index=0, settings=None):
        try:
            source = discover(Path(path))
        except Exception as exc:
            self.on_error(str(exc)); return
        self.set_playing(False)
        if slot == "A":
            self.index = self.target = index
            self.auto_fps.setChecked(True)
        self.viewer.set_frame(slot, None, None, f"{slot} / Opening {source.name}")
        self.incoming.pop(slot, None)
        self.error_text = ""
        self._open_session(slot, source, settings, index)
        if slot == "B":
            self.compare.setCurrentIndex(2)
            # Split the configured total cache budget between both versions.
            if self.sessions["A"].source:
                a = self.sessions["A"]
                self._open_session("A", a.source, a.settings, self.target)
        self.document.dirty = True

    def _open_session(self, slot, source, settings, index):
        both = slot == "B" or self.sessions["B"].source is not None or self.sessions["B"].pending is not None
        limit = int(self.budget.currentData()) // (2 if both else 1)
        self.sessions[slot].open(source, self.cache_mode.currentData(), limit, self.preview.currentData(), settings, max(0, index))

    def cache_changed(self):
        self.budget.setEnabled(self.cache_mode.currentData() != "off")
        self.rebuild()

    def rebuild(self, *_):
        self.set_playing(False)
        for slot, session in self.sessions.items():
            if session.source:
                index = self.target if slot == "A" else aligned_frame(self.target, self.offset.value())
                self._open_session(slot, session.source, session.settings, index)

    def on_prepared(self, slot):
        session = self.sessions[slot]
        if slot == "A":
            if self.auto_fps.isChecked():
                self.fps.blockSignals(True); self.fps.setValue(session.info.fps); self.fps.blockSignals(False)
            self.fps.setToolTip(f"{session.info.fps_exact} fps / {session.info.fps_origin}")
            self.timeline.setRange(0, max(0, session.total - 1))
            b = self.sessions["B"]
            if b.info and b.worker:
                b_index = aligned_frame(self.target, self.offset.value())
                if b_index >= 0 and (not b.count_exact or b_index < b.total):
                    b.request(b_index)
                else:
                    b.ticket += 1; b.busy = False
                    self.viewer.set_frame("B", None, None, "B / Outside source range")
        else:
            index = aligned_frame(self.target, self.offset.value())
            if index < 0 or (session.count_exact and index >= session.total):
                session.ticket += 1; session.busy = False
                self.viewer.set_frame("B", None, None, "B / Outside source range")
            elif index != 0:
                session.request(index)
        self.source_label.setText("   |   ".join(f"{key}  {s.source.name} / {s.info.width} × {s.info.height} / {s.info.fps_exact} fps" for key, s in self.sessions.items() if s.info and s.source))
        self.update_status()

    def label_for(self, slot, index):
        session = self.sessions[slot]
        label = f"{slot} / Frame {index + 1:,}"
        if session.source and not session.source.movie and index < len(session.source.paths):
            match = NUMBER.match(session.source.paths[index].stem)
            if match:
                label += f" / Source {match[2]}"
        return label

    def on_frame(self, slot, index, rgb):
        session = self.sessions[slot]
        if not session.source:
            return
        if slot == "B" and index != aligned_frame(self.target, self.offset.value()):
            return
        if slot == "A" and index != self.target:
            return
        self.incoming[slot] = (index, rgb)
        a = self.incoming.get("A")
        b = self.incoming.get("B")
        b_session = self.sessions["B"]
        b_index = aligned_frame(self.target, self.offset.value())
        needs_b = self.viewer.mode != "A" and b_session.info and b_index >= 0 and (not b_session.count_exact or b_index < b_session.total)
        if not a or a[0] != self.target or (needs_b and (not b or b[0] != b_index)):
            return
        self.present_frame("A", *a)
        if b and b[0] == b_index:
            self.present_frame("B", *b)
        elif not needs_b:
            self.viewer.set_frame("B", None, None, "B / Outside source range")
        self.frame_label.setText("  |  ".join(self.label_for(s, self.viewer.keys[s][1]) if self.viewer.keys[s] else f"{s} / —" for s in ("A", "B")))
        self.update_status()

    def present_frame(self, slot, index, rgb):
        session = self.sessions[slot]
        key = (str(session.source.paths[0]), index)
        self.viewer.set_frame(slot, rgb, key, self.label_for(slot, index))
        if slot == "A":
            self.index = index
            self.timeline.blockSignals(True)
            self.timeline.setMaximum(max(session.total - 1, index))
            self.timeline.setValue(index); self.timeline.blockSignals(False)

    def on_error(self, message):
        self.error_text = message
        self.set_playing(False)
        self.status.setText(message)

    def update_status(self):
        count = sum(s.cached for s in self.sessions.values())
        used = sum(s.used for s in self.sessions.values())
        hits = sum(s.hits for s in self.sessions.values())
        self.cache_label.setText(f"{self.cache_mode.currentText()} / {count:,} frames / {used / 1024**2:.1f} MiB / {hits:,} hits")
        if self.error_text:
            self.status.setText(self.error_text); return
        notices = [s.notice for s in self.sessions.values() if s.notice]
        if notices:
            self.status.setText(" | ".join(notices)); return
        info = self.sessions["A"].info
        text = info.color_origin if info else "Open media to begin"
        if info:
            text += f" / FPS: {info.fps_exact} ({info.fps_origin})"
        a, b = self.sessions["A"].info, self.sessions["B"].info
        if a and b and abs(a.fps - b.fps) > .001:
            text += " / Different source FPS: comparison is frame-for-frame at A's rate"
        self.status.setText(text)

    def request_frame(self, index):
        a = self.sessions["A"]
        if not a.worker or not a.info:
            return
        self.target = max(0, min(index, a.total - 1)) if a.count_exact else max(0, index)
        self.incoming.clear()
        a.request(self.target)
        b = self.sessions["B"]
        if b.worker and b.info:
            b_index = aligned_frame(self.target, self.offset.value())
            if b_index < 0 or (b.count_exact and b_index >= b.total):
                b.ticket += 1; b.busy = False
                self.viewer.set_frame("B", None, None, "B / Outside source range")
            else:
                b.request(b_index)

    def seek(self, value):
        self.set_playing(False); self.request_frame(value)

    def go(self, index):
        self.seek(index)

    def step(self, delta):
        self.go(self.target + delta)

    def frame_rate(self):
        info = self.sessions["A"].info
        return info.fps if self.auto_fps.isChecked() and info else self.fps.value()

    def manual_fps(self):
        self.auto_fps.setChecked(False); self.reset_clock()

    def auto_rate_changed(self, enabled):
        info = self.sessions["A"].info
        if enabled and info:
            self.fps.blockSignals(True); self.fps.setValue(info.fps); self.fps.blockSignals(False)
        self.reset_clock()

    def reset_clock(self, *_):
        self.anchor, self.anchor_frame = time.monotonic(), self.index

    def set_playing(self, playing):
        self.playing = playing
        if hasattr(self, "play_button"):
            self.play_button.setText("Pause" if playing else "Play")
        self.reset_clock()

    def toggle_play(self):
        a = self.sessions["A"]
        if a.info and (not a.count_exact or a.total > 1):
            if not self.playing and a.count_exact and self.index >= a.total - 1:
                self.request_frame(0)
                self.index = 0
            self.pen.setChecked(False)
            self.set_playing(not self.playing)

    def tick(self):
        a, b = self.sessions["A"], self.sessions["B"]
        if not self.playing or not a.info or a.busy or (self.viewer.mode != "A" and b.busy):
            return
        target = self.anchor_frame + int((time.monotonic() - self.anchor) * self.frame_rate())
        if a.count_exact and target >= a.total:
            if self.loop.isChecked():
                self.request_frame(0); self.index = 0; self.reset_clock()
            else:
                self.request_frame(max(0, a.total - 1)); self.set_playing(False)
            return
        if target > self.index:
            self.skipped += max(0, target - self.index - 1)
            self.play_button.setToolTip(f"{self.skipped} frames skipped to follow playback time")
            self.request_frame(target)

    def on_end(self, slot):
        session = self.sessions[slot]
        if slot == "A":
            self.timeline.setMaximum(max(0, session.total - 1))
            if self.playing and self.loop.isChecked() and session.total:
                self.request_frame(0); self.index = 0; self.reset_clock()
            else:
                self.set_playing(False)
                if session.total:
                    self.request_frame(session.total - 1)
        else:
            self.viewer.set_frame("B", None, None, "B / End of source")
            pending_a = self.incoming.get("A")
            if pending_a and pending_a[0] == self.target:
                self.on_frame("A", *pending_a)

    def compare_changed(self):
        self.viewer.mode = self.compare.currentData(); self.viewer.update()
        if self.viewer.mode == "B":
            self.active.setCurrentIndex(1)
        self.document.dirty = True
        self.set_playing(False)
        if self.sessions["A"].info:
            self.request_frame(self.target)

    def offset_changed(self):
        self.set_playing(False); self.request_frame(self.index); self.document.dirty = True

    def pause_for_interaction(self):
        self.set_playing(False)
        # Discard a pending playback result before the brush captures the visible frame.
        for session in self.sessions.values():
            session.ticket += 1; session.busy = False
        self.target = self.index

    def set_painting(self, enabled):
        self.pause_for_interaction()
        self.viewer.painting = enabled
        self.viewer.setCursor(Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor)

    def brush_color(self):
        color = QColorDialog.getColor(QColor(self.viewer.brush_color), self, "Annotation color")
        if color.isValid():
            self.viewer.brush_color = color.name()

    def current_annotation(self, slot=None):
        slot = slot or ("A" if self.active.currentIndex() == 0 else "B")
        key = self.viewer.keys[slot]
        if key is None or self.viewer.images[slot].isNull():
            raise ValueError(f"No visible frame in source {slot}.")
        session = self.sessions[slot]
        color = session.settings
        context = f"{slot} / {self.frame_rate():.6g} fps / B = A {self.offset.value():+d} frames / "
        input_name = color.input_space if color.enabled else (session.info.input_space or "unspecified")
        context += f"Input: {input_name}; view: {color.view if color.enabled else 'bypass'}; LUT: {Path(color.lut).name if color.lut else 'none'}"
        return self.document.ensure(*key, self.label_for(slot, key[1]), context, self.viewer.images[slot])

    def add_stroke(self, slot, stroke):
        try:
            entry = self.current_annotation(slot); entry.strokes.append(stroke)
            self.document.dirty = True; self.refresh_notes()
        except Exception as exc:
            self.on_error(str(exc))

    def edit_note(self):
        self.pause_for_interaction()
        try:
            entry = self.current_annotation()
        except ValueError as exc:
            self.on_error(str(exc)); return
        text, accepted = QInputDialog.getMultiLineText(self, "Frame review note", entry.label, entry.note)
        if accepted:
            entry.note = text
            self.document.dirty = True
        self.document.remove_empty(entry.key)
        self.refresh_notes()

    def undo_stroke(self):
        slot = "A" if self.active.currentIndex() == 0 else "B"
        entry = self.document.entries.get(self.viewer.keys[slot])
        if entry and entry.strokes:
            entry.strokes.pop(); self.document.dirty = True
            self.document.remove_empty(entry.key); self.refresh_notes()

    def clear_annotation(self):
        slot = "A" if self.active.currentIndex() == 0 else "B"
        key = self.viewer.keys[slot]
        if key in self.document.entries:
            del self.document.entries[key]; self.document.dirty = True; self.refresh_notes()

    def refresh_notes(self):
        self.notes.clear()
        for entry in self.document.active():
            item = QListWidgetItem(f"{entry.label}\n{Path(entry.source).name}\n{entry.note[:75] or 'Paint annotation'}")
            item.setData(Qt.ItemDataRole.UserRole, entry.key); self.notes.addItem(item)
        self.viewer.update()

    def jump_note(self, item):
        entry = self.document.entries[item.data(Qt.ItemDataRole.UserRole)]
        self.note_preview.setPlainText(entry.note)
        self.set_playing(False)
        for slot, session in self.sessions.items():
            if session.source and str(session.source.paths[0]) == entry.source:
                self.active.setCurrentIndex(0 if slot == "A" else 1)
                a_frame = entry.frame if slot == "A" else entry.frame - self.offset.value()
                if a_frame >= 0 and (not self.sessions["A"].count_exact or a_frame < self.sessions["A"].total):
                    self.compare.setCurrentIndex(0 if slot == "A" else 1); self.go(a_frame); return
        self.compare.setCurrentIndex(0)
        self.open_path(entry.source, "A", entry.frame)

    def color_dialog(self):
        from .app import ColorDialog
        slot = "A" if self.active.currentIndex() == 0 else "B"
        session = self.sessions[slot]
        if not session.info:
            return
        self.set_playing(False)
        try:
            dialog = ColorDialog(session.settings, self)
            if dialog.exec():
                self._open_session(slot, session.source, dialog.settings(), max(0, session.index))
                self.document.dirty = True
        except Exception as exc:
            self.on_error(str(exc))

    def metadata_dialog(self):
        slot = "A" if self.active.currentIndex() == 0 else "B"
        info = self.sessions[slot].info
        if not info:
            return
        dialog = QDialog(self); dialog.setWindowTitle(f"Source {slot} / Metadata"); dialog.resize(760, 620)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit(); text.setReadOnly(True)
        data = asdict(info)
        text.setPlainText(json.dumps(data, indent=2, ensure_ascii=False)); layout.addWidget(text)
        layout.addWidget(QLabel("First image / first video stream. Decoder-exposed fields; missing metadata is not inferred."))
        dialog.exec()

    def state(self):
        return {"sources": {slot: {"path": str(s.source.paths[0]), "color": asdict(s.settings) if s.settings else None}
                            for slot, s in self.sessions.items() if s.source},
                "frame": self.index, "offset": self.offset.value(), "compare": self.compare.currentIndex(),
                "fps": self.fps.value(), "auto_fps": self.auto_fps.isChecked(), "wipe": self.viewer.wipe}

    def save_review(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save review", str(self.document.path or "FRM-review.frmreview"), "FRM review (*.frmreview)")
        if not path:
            return False
        if not path.lower().endswith(".frmreview"):
            path += ".frmreview"
        try:
            self.document.save(path, self.state()); self.status.setText("Review saved / Cache remains temporary"); return True
        except Exception as exc:
            self.on_error(str(exc)); return False

    def confirm_review(self):
        if not self.document.dirty or (not self.document.active() and self.document.path is None):
            return True
        result = QMessageBox.question(self, "Save review notes?", "Save your review notes before closing this document?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        return self.save_review() if result == QMessageBox.StandardButton.Save else result == QMessageBox.StandardButton.Discard

    def load_review(self):
        if not self.confirm_review():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open review", "", "FRM review (*.frmreview)")
        if not path:
            return
        try:
            document, state = ReviewDocument.load(path)
            sources = {slot: (discover(Path(record["path"])), ColorSettings(**record["color"]) if record.get("color") else None)
                       for slot, record in state.get("sources", {}).items() if slot in self.sessions and Path(record["path"]).exists()}
            self.clear_media()
            self.document = document; self.viewer.document = document; self.refresh_notes()
            self.offset.blockSignals(True); self.offset.setValue(int(state.get("offset", 0))); self.offset.blockSignals(False)
            self.index = self.target = max(0, int(state.get("frame", 0)))
            for slot, (source, color) in sources.items():
                self._open_session(slot, source, color, self.target if slot == "A" else max(0, self.target + self.offset.value()))
            self.compare.setCurrentIndex(int(state.get("compare", 0)))
            self.viewer.wipe = max(0, min(1, float(state.get("wipe", .5))))
            self.auto_fps.setChecked(bool(state.get("auto_fps", True)))
            self.fps.blockSignals(True); self.fps.setValue(float(state.get("fps", 24))); self.fps.blockSignals(False)
            self.document.dirty = False
            if len(sources) < len(state.get("sources", {})):
                self.status.setText("Review notes loaded. Some original media is missing; snapshots can still be exported.")
        except Exception as exc:
            self.on_error(str(exc))

    def new_review(self):
        if self.confirm_review():
            self.clear_media()
            self.document = ReviewDocument(); self.viewer.document = self.document; self.refresh_notes()

    def export_images(self):
        if not self.document.active():
            self.on_error("Paint a frame or add a note before exporting."); return
        extension, ok = QInputDialog.getItem(self, "Export annotated frames", "Image format", ["PNG", "JPG"], editable=False)
        if not ok:
            return
        folder = QFileDialog.getExistingDirectory(self, "Choose export folder")
        if folder:
            try:
                target = self.document.export_images(folder, extension.lower())
                self.status.setText(f"Annotated frames and notes exported to {target}")
            except Exception as exc:
                self.on_error(str(exc))

    def export_pdf(self):
        if not self.document.active():
            self.on_error("Paint a frame or add a note before exporting."); return
        path, _ = QFileDialog.getSaveFileName(self, "Export review PDF", "FRM-review.pdf", "PDF report (*.pdf)")
        if path:
            try:
                self.document.export_pdf(path if path.lower().endswith(".pdf") else path + ".pdf")
                self.status.setText("Review PDF exported successfully")
            except Exception as exc:
                self.on_error(str(exc))

    def close_b(self):
        self.set_playing(False); self.sessions["B"].close()
        self.viewer.set_frame("B", None, None, "B"); self.compare.setCurrentIndex(0)

    def clear_media(self):
        self.set_playing(False)
        self.incoming.clear()
        for slot, session in self.sessions.items():
            session.close(); self.viewer.set_frame(slot, None, None, slot)
        self.timeline.setRange(0, 0)
        self.index = self.target = 0
        self.source_label.setText("Media closed / Review notes retained")

    def session_closed(self):
        if self.closing and all(s.worker is None for s in self.sessions.values()):
            QTimer.singleShot(0, self.close)

    def fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def closeEvent(self, event):
        if not self.closing:
            if not self.confirm_review():
                event.ignore(); return
            self.closing = True
            self.setEnabled(False)
            self.setAcceptDrops(False)
            self.set_playing(False)
            for session in self.sessions.values():
                session.close()
        if any(s.worker is not None for s in self.sessions.values()):
            event.ignore()
        else:
            self.timer.stop(); event.accept()
