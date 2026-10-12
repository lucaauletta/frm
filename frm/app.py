"""FRM desktop application. SPDX-License-Identifier: GPL-3.0-only."""
from pathlib import Path
import sys

from PySide6.QtCore import Qt, QTimer, QLocale
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QApplication, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QDoubleSpinBox, QCheckBox, QFileDialog,
    QMessageBox, QFormLayout, QDialog, QDialogButtonBox,
)
from . import __version__
from .color import ColorSettings, load_config, processor

STYLE = """
QWidget { background: #15171b; color: #e8e9eb; font-family: 'Inter'; font-size: 12px; }
QMainWindow { background: #101115; }
QLabel#brand { color: #9dcaff; font-size: 23px; font-weight: 800; letter-spacing: 3px; }
QLabel#muted { color: #989da7; }
QLabel#title { font-size: 15px; font-weight: 600; }
QFrame#bar { background: #1b1e23; border-radius: 10px; }
QPushButton { background: #272b33; border: 1px solid #383e48; border-radius: 6px; padding: 6px 11px; }
QPushButton:hover { background: #363d47; border-color: #77818e; }
QPushButton:disabled { color: #626873; }
QPushButton#primary { background: #9dcaff; color: #101d2c; border: none; font-weight: 700; }
QComboBox, QDoubleSpinBox { background: #242830; border: 1px solid #3b424e; border-radius: 5px; padding: 6px; }
QSlider::groove:horizontal { height: 5px; background: #383e48; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #9dcaff; }
QSlider::handle:horizontal { background: #e6efdb; width: 12px; margin: -5px 0; border-radius: 6px; }
QProgressBar { border: none; background: #2b3038; max-height: 3px; }
QProgressBar::chunk { background: #9dcaff; }
QPushButton:checked { background: #365476; border: 1px solid #9dcaff; }
QListWidget { background: #11161e; border: 1px solid #303945; }
QListWidget::item { padding: 12px 6px; border-bottom: 1px solid #26313f; }
QListWidget::item:selected { background: #263f5c; }
QPlainTextEdit { background: #11161e; border: 1px solid #303945; }
QMenuBar, QMenu { background: #171d26; }
QMenuBar::item:selected, QMenu::item:selected { background: #304965; }
QToolTip { background: #272b33; color: #ffffff; border: 1px solid #68717f; }
"""


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


from .window import MainWindow


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
