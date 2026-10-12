"""Explicit source drop targets and sequence-aware import planning."""
from pathlib import Path
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QSizePolicy
from .media import discover, sequence_key, IMAGES


def discover_shots(paths):
    shots, seen = [], set()
    for value in paths:
        path = Path(value).resolve()
        key = (path.parent, sequence_key(path)) if path.suffix.lower() in IMAGES else path
        if key in seen:
            continue
        seen.add(key)
        source = discover(path)
        if any(existing.paths == source.paths for existing in shots):
            continue
        shots.append(source)
        if len(shots) > 2:
            raise ValueError("Drop one shot into A or B, or two shots into the viewer. Frames from the same sequence count as one shot.")
    return shots


class SourceDropCard(QFrame):
    dropped = Signal(object, str)
    browse = Signal(str)

    def __init__(self, slot):
        super().__init__()
        self.slot = slot
        self.setAcceptDrops(True)
        self.setObjectName("sourceDrop")
        self.setStyleSheet("QFrame#sourceDrop { background: #1c222b; border: 1px solid #414c5c; border-radius: 7px; }")
        row = QHBoxLayout(self); row.setContentsMargins(10, 6, 10, 6)
        badge = QLabel(slot); badge.setStyleSheet("font-size: 20px; font-weight: bold; color: #9dcaff;"); row.addWidget(badge)
        text = QVBoxLayout(); text.setSpacing(2)
        self.name = QLabel("Drop a movie, sequence frame or folder")
        self.name.setTextFormat(Qt.TextFormat.PlainText)
        self.name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.hint = QLabel("Primary source / playback timeline" if slot == "A" else "Comparison version / synchronized to A")
        self.hint.setObjectName("muted")
        text.addWidget(self.name); text.addWidget(self.hint); row.addLayout(text, 1)
        self.button = QPushButton("Browse…"); self.button.clicked.connect(lambda: self.browse.emit(slot)); row.addWidget(self.button)
        self.loaded = False

    def set_source(self, source):
        self.loaded = source is not None
        self.name.setText(source.name if source else "Drop a movie, sequence frame or folder")
        self.setToolTip(str(source.paths[0]) if source else f"Drop here to load source {self.slot}")
        self.button.setText("Replace…" if source else "Browse…")
        self.hint.setText(f"Drop here to replace {self.slot}" if source else
                          ("Primary source / playback timeline" if self.slot == "A" else "Comparison version / synchronized to A"))

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if urls and all(u.isLocalFile() for u in urls):
            self.setStyleSheet("QFrame#sourceDrop { background: #294562; border: 2px solid #9dcaff; border-radius: 7px; }")
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.reset_style()
        event.accept()

    def dragMoveEvent(self, event):
        urls = event.mimeData().urls()
        if urls and all(u.isLocalFile() for u in urls):
            event.acceptProposedAction()

    def reset_style(self):
        self.setStyleSheet("QFrame#sourceDrop { background: #1c222b; border: 1px solid #414c5c; border-radius: 7px; }")

    def dropEvent(self, event):
        self.reset_style()
        urls = event.mimeData().urls()
        if urls and all(u.isLocalFile() for u in urls):
            self.dropped.emit([u.toLocalFile() for u in urls], self.slot)
            event.acceptProposedAction()
