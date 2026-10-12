"""FRM desktop application. SPDX-License-Identifier: GPL-3.0-only."""
from pathlib import Path
import sys
import time

from PySide6.QtCore import Qt, QTimer, QLocale
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QComboBox, QDoubleSpinBox, QCheckBox, QFileDialog,
    QMessageBox, QFrame, QFormLayout, QProgressBar, QDialog, QDialogButtonBox,
)
from . import __version__
from .cache import SessionCache
from .color import ColorSettings, load_config, processor
from .media import discover
from .worker import CacheWorker

STYLE = """
QWidget { background: #15171b; color: #e8e9eb; font-family: 'Inter'; font-size: 13px; }
QMainWindow { background: #101115; }
QLabel#brand { color: #c3f477; font-size: 26px; font-weight: 800; letter-spacing: 3px; }
QLabel#muted { color: #989da7; }
QLabel#title { font-size: 15px; font-weight: 600; }
QFrame#bar { background: #1b1e23; border-radius: 10px; }
QPushButton { background: #272b33; border: 1px solid #383e48; border-radius: 6px; padding: 8px 15px; }
QPushButton:hover { background: #363d47; border-color: #77818e; }
QPushButton:disabled { color: #626873; }
QPushButton#primary { background: #c3f477; color: #151c0d; border: none; font-weight: 700; }
QComboBox, QDoubleSpinBox { background: #242830; border: 1px solid #3b424e; border-radius: 5px; padding: 6px; }
QSlider::groove:horizontal { height: 5px; background: #383e48; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #c3f477; }
QSlider::handle:horizontal { background: #e6efdb; width: 12px; margin: -5px 0; border-radius: 6px; }
QProgressBar { border: none; background: #2b3038; max-height: 3px; }
QProgressBar::chunk { background: #c3f477; }
QToolTip { background: #272b33; color: #ffffff; border: 1px solid #68717f; }
"""


class Viewer(QWidget):
    def __init__(self):
        super().__init__()
        self.image = QImage()
        self.setMinimumSize(320, 200)

    def set_rgb(self, rgb):
        h, w, _ = rgb.shape
        self.image = QImage(rgb.data, w, h, rgb.strides[0], QImage.Format.Format_RGB888).copy()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0b0d10"))
        if self.image.isNull():
            p.setPen(QColor("#e8e9eb"))
            p.setFont(QFont("Inter", 24, QFont.Weight.DemiBold))
            p.drawText(self.rect().adjusted(0, -50, 0, -50), Qt.AlignmentFlag.AlignCenter, "Drop a frame. See the sequence.")
            p.setFont(QFont("Inter", 11))
            p.setPen(QColor("#9098a5"))
            p.drawText(self.rect().adjusted(0, 40, 0, 40), Qt.AlignmentFlag.AlignCenter,
                       "DPX · EXR · TIFF · JPEG · PNG     /     MOV · MP4\n\nOr choose Open media to get started")
        else:
            size = self.image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
            x, y = (self.width() - size.width()) // 2, (self.height() - size.height()) // 2
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawImage(self.rect().__class__(x, y, size.width(), size.height()), self.image)


class ColorDialog(QDialog):
    def __init__(self, settings, parent):
        super().__init__(parent)
        self.setWindowTitle("Viewing color")
        self.setMinimumWidth(570)
        self.config_path, self.lut_path = settings.config, settings.lut
        self.config = load_config(settings.config)
        layout = QVBoxLayout(self)
        note = QLabel("Choose the source color space explicitly.\nViewing changes never modify your original media.")
        note.setObjectName("muted")
        layout.addWidget(note)
        form = QFormLayout()
        self.enabled = QCheckBox("Enable ACES / OpenColorIO display transform")
        self.enabled.setChecked(settings.enabled)
        form.addRow(self.enabled)
        self.input_space, self.display, self.view = QComboBox(), QComboBox(), QComboBox()
        self.input_space.setMinimumContentsLength(26)
        self.input_space.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        for label, control in [("Input color space", self.input_space), ("Display", self.display), ("View", self.view)]:
            form.addRow(label, control)
        self.exposure = QDoubleSpinBox()
        self.exposure.setRange(-10, 10)
        self.exposure.setSingleStep(0.25)
        self.exposure.setValue(settings.exposure)
        form.addRow("Exposure offset (stops)", self.exposure)
        layout.addLayout(form)
        self.config_label = QLabel()
        self.config_label.setWordWrap(True)
        layout.addWidget(self.config_label)
        config_row = QHBoxLayout()
        for label, callback in [("Load .ocio config", self.choose_config), ("Use built-in ACES", self.reset_config)]:
            b = QPushButton(label); b.clicked.connect(callback); config_row.addWidget(b)
        layout.addLayout(config_row)
        self.lut_label = QLabel()
        self.lut_label.setWordWrap(True)
        layout.addWidget(self.lut_label)
        row = QHBoxLayout()
        for label, callback in [("Load viewing LUT", self.choose_lut), ("Remove LUT", self.clear_lut)]:
            b = QPushButton(label); b.clicked.connect(callback); row.addWidget(b)
        layout.addLayout(row)
        hint = QLabel("Order: source RGB → exposure → display transform → LUT.\nLUT input must match the display output. With ACES disabled,\nexposure and LUT act directly on source RGB. Alpha is ignored.")
        hint.setObjectName("muted")
        layout.addWidget(hint)
        self.display.currentTextChanged.connect(self.update_views)
        self.populate()
        if self.input_space.findText(settings.input_space) >= 0:
            self.input_space.setCurrentText(settings.input_space)
        if settings.display:
            self.display.setCurrentText(settings.display)
        if settings.view:
            self.view.setCurrentText(settings.view)
        self.update_labels()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def populate(self):
        self.input_space.clear(); self.input_space.addItems([s.getName() for s in self.config.getColorSpaces()])
        self.input_space.setCurrentText("ACEScg")
        self.display.clear(); self.display.addItems(list(self.config.getDisplays()))
        self.display.setCurrentText(self.config.getDefaultDisplay())
        self.update_views()
        self.update_labels()

    def update_views(self):
        self.view.clear()
        if self.display.currentText():
            self.view.addItems(list(self.config.getViews(self.display.currentText())))
            self.view.setCurrentText(self.config.getDefaultView(self.display.currentText()))

    def update_labels(self):
        self.config_label.setText("Config: " + (self.config_path or "Built-in ACES 2.0 Studio"))
        self.lut_label.setText("LUT: " + (self.lut_path or "None"))

    def choose_config(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open OCIO configuration", "", "OCIO configuration (*.ocio)")
        if path:
            try:
                config = load_config(path)
                config.validate()
                self.config, self.config_path = config, path
                self.populate()
            except Exception as exc:
                QMessageBox.warning(self, "Cannot load configuration", str(exc))

    def reset_config(self):
        self.config, self.config_path = load_config(), ""
        self.populate()

    def choose_lut(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open viewing LUT", "", "LUT files (*.cube *.3dl *.spi1d *.spi3d *.csp);;All files (*)")
        if path:
            self.lut_path = path
            self.update_labels()

    def clear_lut(self):
        self.lut_path = ""
        self.update_labels()

    def settings(self):
        return ColorSettings(self.enabled.isChecked(), self.config_path, self.input_space.currentText(),
                             self.display.currentText(), self.view.currentText(), self.lut_path, self.exposure.value())

    def validate(self):
        try:
            processor(self.settings())
        except Exception as exc:
            QMessageBox.warning(self, "Cannot apply viewing color", str(exc))
            return
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"FRM {__version__} · Review, simply")
        self.resize(1200, 790)
        self.setAcceptDrops(True)
        self.source = self.cache = self.worker = None
        self.settings = ColorSettings()
        self.available = self.index = self.total = 0
        self.building = self.closing = False
        self.error_text = ""
        self.generation = 0
        self.pending = None
        self.playing = False
        self.anchor = time.monotonic()
        self.anchor_frame = 0
        self.skipped = 0
        root = QWidget(); self.setCentralWidget(root)
        layout = QVBoxLayout(root); layout.setContentsMargins(24, 18, 24, 18); layout.setSpacing(15)
        header = QHBoxLayout()
        brand = QLabel("FRM"); brand.setObjectName("brand"); header.addWidget(brand)
        tagline = QLabel("REVIEW, SIMPLY"); tagline.setObjectName("muted"); header.addWidget(tagline)
        header.addStretch()
        self.open_button = QPushButton("Open media"); self.open_button.setObjectName("primary")
        self.open_button.clicked.connect(self.open_dialog); header.addWidget(self.open_button)
        color_button = QPushButton("Viewing color"); color_button.clicked.connect(self.color_dialog); header.addWidget(color_button)
        help_button = QPushButton("?"); help_button.clicked.connect(self.about); header.addWidget(help_button)
        layout.addLayout(header)
        info = QHBoxLayout()
        self.title = QLabel("Your next shot starts here"); self.title.setObjectName("title"); info.addWidget(self.title, 1)
        self.color_label = QLabel("Color: bypass"); self.color_label.setObjectName("muted"); info.addWidget(self.color_label)
        layout.addLayout(info)
        self.viewer = Viewer(); layout.addWidget(self.viewer, 1)
        self.progress = QProgressBar(); self.progress.setTextVisible(False); self.progress.setRange(0, 1); self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.timeline = QSlider(Qt.Orientation.Horizontal); self.timeline.setRange(0, 0)
        self.timeline.valueChanged.connect(self.seek); layout.addWidget(self.timeline)
        controls = QHBoxLayout()
        for label, callback in [("|‹", lambda: self.step(-self.index)), ("‹", lambda: self.step(-1))]:
            b = QPushButton(label); b.clicked.connect(callback); controls.addWidget(b)
        self.play_button = QPushButton("Play"); self.play_button.setObjectName("primary")
        self.play_button.clicked.connect(self.toggle_play); controls.addWidget(self.play_button)
        b = QPushButton("›"); b.clicked.connect(lambda: self.step(1)); controls.addWidget(b)
        self.loop = QCheckBox("Loop"); self.loop.setChecked(True); controls.addWidget(self.loop)
        self.counter = QLabel("Frame — / —"); controls.addWidget(self.counter)
        controls.addStretch()
        controls.addWidget(QLabel("FPS"))
        self.fps = QDoubleSpinBox(); self.fps.setRange(1, 120); self.fps.setDecimals(3); self.fps.setValue(24)
        self.fps.valueChanged.connect(self.reset_clock); controls.addWidget(self.fps)
        self.preview = QComboBox(); self.preview.addItems(["Preview · 1280", "Preview · 1920", "Preview · 3840"])
        self.preview.currentIndexChanged.connect(self.rebuild); controls.addWidget(self.preview)
        full = QPushButton("Fullscreen"); full.clicked.connect(self.fullscreen); controls.addWidget(full)
        layout.addLayout(controls)
        self.status = QLabel("Ready  ·  Temporary cache clears on exit  ·  Silent video preview")
        self.status.setObjectName("muted"); layout.addWidget(self.status)
        self.timer = QTimer(self); self.timer.setTimerType(Qt.TimerType.PreciseTimer); self.timer.setInterval(4)
        self.timer.timeout.connect(self.tick); self.timer.start()
        for key, callback in [("Space", self.toggle_play), ("Left", lambda: self.step(-1)), ("Right", lambda: self.step(1)),
                              ("Home", lambda: self.step(-self.index)), ("F", self.fullscreen), ("Escape", self.showNormal),
                              ("Ctrl+O", self.open_dialog), ("Ctrl+W", self.clear_media)]:
            QShortcut(QKeySequence(key), self, activated=callback)
        self.play_button.setEnabled(False)

    def about(self):
        QMessageBox.information(self, "About FRM", f"FRM {__version__} — early preview\nGPL-3.0-only · github.com/lucaauletta/frm\n\n"
            "Drop one frame to discover its numbered sequence.\nSpace: play/pause · Arrows: step · Home: first frame\nF: fullscreen · Esc: leave fullscreen · Ctrl+W: close media\n\n"
            "8-bit RGB preview, up to 8 GiB temporary disk cache.\nNo audio, HDR output, ICC monitor correction or SDI output.\nMovies play at the reported average FPS (VFR timing is not preserved).\n"
            "Select the correct input space in Viewing color for ACES.\nReview preview only; not a mastering reference.")

    def open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open media or one sequence frame", "",
            "Supported media (*.dpx *.exr *.tif *.tiff *.jpg *.jpeg *.png *.mov *.mp4 *.m4v);;All files (*)")
        if path:
            self.open_path(path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and all(u.isLocalFile() for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if len(urls) != 1:
            QMessageBox.information(self, "Open one sequence", "Drop a single frame or folder to load a sequence, or one movie.")
            return
        self.open_path(urls[0].toLocalFile())

    def open_path(self, path):
        try:
            source = discover(Path(path))
        except Exception as exc:
            QMessageBox.warning(self, "Cannot open media", str(exc)); return
        self.source = source
        # Start safely in bypass; never reuse a previous shot's input color space silently.
        self.settings = ColorSettings()
        self.color_label.setText("Color: bypass")
        self.rebuild()

    def color_dialog(self):
        try:
            dialog = ColorDialog(self.settings, self)
            if dialog.exec():
                self.settings = dialog.settings()
                self.color_label.setText("Color: " + (self.settings.view if self.settings.enabled else "bypass") + (" + LUT" if self.settings.lut else ""))
                self.rebuild()
        except Exception as exc:
            QMessageBox.warning(self, "Viewing color unavailable", str(exc))

    def rebuild(self, *_):
        if not self.source:
            return
        self.set_playing(False)
        self.pending = self.start_cache
        self.stop_worker()

    def stop_worker(self):
        self.generation += 1  # Ignore queued signals from any previous cache generation.
        self.building = False
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.status.setText("Finishing current decode…")
        else:
            self.worker_stopped()

    def worker_stopped(self):
        if self.worker and self.worker.isRunning():
            return
        self.worker = None
        if self.cache:
            self.cache.close(); self.cache = None
        if self.closing:
            self.close(); return
        if self.pending:
            callback, self.pending = self.pending, None
            callback()

    def start_cache(self):
        self.cache = SessionCache()
        self.available = self.index = self.total = self.skipped = 0
        self.error_text = ""
        self.viewer.image = QImage(); self.viewer.update()
        self.timeline.setRange(0, 0); self.counter.setText("Frame — / —")
        self.play_button.setEnabled(False)
        self.title.setText(self.source.name)
        self.title.setToolTip(str(self.source.paths[0]))
        self.building = True
        self.progress.setRange(0, 0)
        self.status.setText("Preparing preview…")
        generation = self.generation
        worker = CacheWorker(self.source, self.cache, self.settings, [1280, 1920, 3840][self.preview.currentIndex()])
        self.worker = worker
        worker.metadata.connect(lambda *args: self.on_metadata(*args) if generation == self.generation else None)
        worker.ready.connect(lambda *args: self.on_ready(*args) if generation == self.generation else None)
        worker.failed.connect(lambda message: self.on_error(message) if generation == self.generation else None)
        worker.finished.connect(lambda: self.on_finished(generation))
        worker.start()

    def on_metadata(self, fps, total, codec):
        self.total, self.codec = total, codec
        if self.source.movie:
            self.fps.setValue(max(1, min(120, fps)))

    def on_ready(self, index, width, height):
        self.available = index + 1
        self.timeline.setMaximum(index)
        self.play_button.setEnabled(True)
        if index == 0:
            self.show_frame(0)
        if self.total:
            self.progress.setRange(0, max(self.total, self.available)); self.progress.setValue(self.available)
        self.status.setText(f"Caching {self.available:,}" + (f" / {self.total:,}" if self.total else "") +
                            f"  ·  {width} × {height} source  ·  {self.cache.used / 1024**2:.0f} MiB  ·  {self.codec}")

    def on_error(self, message):
        self.error_text = message
        self.status.setText("Preview incomplete: " + message)

    def on_finished(self, generation):
        if generation != self.generation:
            self.worker_stopped(); return
        self.building = False
        self.total = self.available
        self.progress.setRange(0, 1); self.progress.setValue(1 if self.available else 0)
        self.counter.setText(f"Frame {self.index + 1 if self.available else 0:,} / {self.available:,}")
        if not self.error_text:
            gaps = f"  ·  Warning: {self.source.gaps} missing frame numbers (gaps collapsed)" if self.source.gaps else ""
            self.status.setText(f"Cached {self.available:,} frames  ·  {self.cache.used / 1024**2:.0f} MiB  ·  Clears on exit" + gaps)

    def show_frame(self, index):
        if not self.cache or not 0 <= index < self.available:
            return
        try:
            self.viewer.set_rgb(self.cache.get(index))
        except Exception as exc:
            self.set_playing(False); self.on_error(str(exc)); return
        self.index = index
        self.timeline.blockSignals(True); self.timeline.setValue(index); self.timeline.blockSignals(False)
        self.counter.setText(f"Frame {index + 1:,} / {self.available:,}")

    def seek(self, value):
        self.show_frame(value); self.reset_clock()

    def step(self, delta):
        self.set_playing(False)
        self.show_frame(max(0, min(self.available - 1, self.index + delta)))

    def reset_clock(self, *_):
        self.anchor, self.anchor_frame = time.monotonic(), self.index

    def set_playing(self, playing):
        self.playing = playing
        self.play_button.setText("Pause" if playing else "Play")
        self.reset_clock()

    def toggle_play(self):
        if self.available > 1:
            if not self.playing and self.index == self.available - 1 and not self.building:
                self.show_frame(0)
            self.set_playing(not self.playing)

    def tick(self):
        if not self.playing or not self.available:
            return
        target = self.anchor_frame + int((time.monotonic() - self.anchor) * self.fps.value())
        if target >= self.available:
            if self.building:
                self.show_frame(self.available - 1); self.reset_clock(); return
            if self.loop.isChecked():
                target %= self.available
                self.show_frame(target); self.reset_clock(); return
            self.show_frame(self.available - 1); self.set_playing(False); return
        if target != self.index:
            skipped = max(0, target - self.index - 1)
            self.skipped += skipped
            self.play_button.setToolTip(f"{self.skipped} preview frames skipped to maintain playback timing")
            self.show_frame(target)

    def fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def clear_media(self):
        self.source = None
        self.set_playing(False)
        self.available = 0
        self.pending = self.reset_view
        self.stop_worker()

    def reset_view(self):
        self.viewer.image = QImage(); self.viewer.update()
        self.title.setText("Your next shot starts here")
        self.counter.setText("Frame — / —"); self.timeline.setRange(0, 0)
        self.play_button.setEnabled(False); self.progress.setValue(0)
        self.status.setText("Media closed · Temporary cache cleared")

    def closeEvent(self, event):
        self.set_playing(False)
        self.pending = None
        if self.worker and self.worker.isRunning():
            self.closing = True
            self.stop_worker()
            event.ignore()
        else:
            if self.cache:
                self.cache.close(); self.cache = None
            event.accept()


def configure_app(app):
    QLocale.setDefault(QLocale("en_US"))
    QFontDatabase.addApplicationFont(str(Path(__file__).parent / "assets" / "Inter.ttf"))
    app.setFont(QFont("Inter", 10))
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        from .diagnostics import self_test
        sys.exit(self_test(Path(sys.argv[2])))
    app = QApplication(sys.argv)
    app.setApplicationName("FRM")
    app.setApplicationVersion(__version__)
    configure_app(app)
    window = MainWindow()
    window.show()
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        QTimer.singleShot(0, lambda: window.open_path(sys.argv[1]))
    sys.exit(app.exec())
