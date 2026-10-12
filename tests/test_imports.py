from pathlib import Path
import numpy as np
import pytest
from PySide6.QtCore import QMimeData, QUrl, QPointF, Qt
from PySide6.QtGui import QDropEvent
from frm.imports import discover_shots, SourceDropCard
from frm.playback import SourceReader
from frm.media import Source
from test_core import app, write_image
from test_core import until
from frm.window import MainWindow


def test_selected_sequence_frames_are_one_shot(tmp_path):
    for n in (1001, 1002, 1003):
        write_image(tmp_path / f"shot.{n}.png", np.zeros((8, 8, 3), np.float32))
    shots = discover_shots([tmp_path / "shot.1003.png", tmp_path / "shot.1001.png"])
    assert len(shots) == 1 and len(shots[0].paths) == 3


def test_multi_shot_validation_is_before_import(tmp_path):
    paths = []
    for name in ("one", "two", "three"):
        path = tmp_path / f"{name}.png"
        write_image(path, np.zeros((8, 8, 3), np.float32)); paths.append(path)
    assert len(discover_shots(paths[:2])) == 2
    with pytest.raises(ValueError):
        discover_shots(paths)
    with pytest.raises(ValueError):
        discover_shots([paths[0], tmp_path / "missing.png"])


def test_drop_card_routes_to_its_slot(app, tmp_path):
    card = SourceDropCard("B")
    received = []
    card.dropped.connect(lambda paths, slot: received.append((paths, slot)))
    mime = QMimeData(); mime.setUrls([QUrl.fromLocalFile(str(tmp_path / "shot.png"))])
    event = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    card.dropEvent(event)
    assert event.isAccepted() and received[0][1] == "B"
    assert Path(received[0][0][0]) == tmp_path / "shot.png"
    card.close()


def test_hardware_failure_restarts_once_on_cpu(monkeypatch):
    reader = SourceReader(Source((Path("movie.mp4"),), movie=True), "hardware")
    calls = []
    def read(index, stop):
        calls.append((index, reader.hardware_failed))
        if not reader.hardware_failed:
            raise RuntimeError("device unavailable")
        return np.ones((1, 1, 3))
    monkeypatch.setattr(reader, "_read", read)
    assert reader.read(7, lambda: False).shape == (1, 1, 3)
    assert calls == [(7, False), (7, True)]
    assert "CPU fallback" in reader.fallback_reason


def test_import_b_preserves_a_and_invalid_selection_changes_neither(tmp_path, app):
    for name in ("primary", "comparison", "extra"):
        write_image(tmp_path / f"{name}.png", np.zeros((16, 16, 3), np.float32))
    window = MainWindow()
    try:
        window.import_paths([tmp_path / "primary.png"], "A")
        until(app, lambda: window.viewer.keys["A"] is not None)
        window.import_paths([tmp_path / "comparison.png"], "B")
        until(app, lambda: window.viewer.keys["B"] is not None)
        before = [s.source.paths for s in window.sessions.values()]
        window.import_paths([tmp_path / "extra.png", tmp_path / "missing.png"], "A")
        assert [s.source.paths for s in window.sessions.values()] == before
        assert window.source_cards["B"].name.text() == "comparison.png"
        window.close_b()
        until(app, lambda: window.sessions["B"].worker is None)
        window.go(0)
        until(app, lambda: not window.sessions["A"].busy)
        assert window.viewer.keys["A"] is not None and window.viewer.keys["B"] is None
    finally:
        window.document.dirty = False
        window.close()
        until(app, lambda: all(s.worker is None for s in window.sessions.values()))
