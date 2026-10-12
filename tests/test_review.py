from pathlib import Path
import numpy as np
import OpenImageIO as oiio
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QImage, QColor
from PySide6.QtTest import QTest
from frm.cache import MemoryCache, SessionCache
from frm.color import load_config
from frm.media import discover
from frm.metadata import inspect, image_color, rate
from frm.review import ReviewDocument, Stroke, render_annotation
from frm.window import MainWindow, aligned_frame
from test_core import app, until, write_image
from fractions import Fraction
import av
from frm.playback import SourceReader
from frm.viewer import ReviewViewer


def test_lru_bounded_ram_and_disk(tmp_path):
    for cache in (MemoryCache(100), SessionCache(450)):
        for i in range(8):
            cache.put(i, np.zeros((4, 4, 3), np.uint8))
            assert cache.used <= cache.limit
        assert cache.get(0) is None
        assert cache.get(7) is not None
        assert not cache.put(9, np.zeros((100, 100, 3), np.uint8))
        cache.close()
        assert not cache.entries and cache.used == 0


def test_metadata_rational_fps_and_aces(tmp_path):
    path = tmp_path / "linear.1001.exr"
    spec = oiio.ImageSpec(16, 16, 3, oiio.FLOAT)
    spec.attribute("FramesPerSecond", oiio.TypeDesc("rational"), (24000, 1001))
    spec.attribute("chromaticities", oiio.TypeDesc("float[8]"), (.713, .293, .165, .830, .128, .044, .32168, .33767))
    out = oiio.ImageOutput.create(str(path)); assert out.open(str(path), spec)
    out.write_image(np.ones((16, 16, 3), np.float32)); out.close()
    info = inspect(discover(path), load_config())
    assert abs(info.fps - 24000 / 1001) < .000001
    assert info.fps_exact == "24000/1001"
    assert info.input_space == "ACEScg", info
    assert info.scene_referred
    assert "chromaticities" in info.attributes
    assert rate((24, 0)) is None
    assert rate("nan") is None
    assert image_color({"oiio:ColorSpace": "linear"}, load_config())[0] == ""
    assert image_color({"oiio:ColorSpace": "ACEScg", "acesImageContainerFlag": 1}, load_config())[0] == ""


def test_review_roundtrip_and_exports(tmp_path, app):
    doc = ReviewDocument()
    image = QImage(640, 360, QImage.Format.Format_RGB32); image.fill(QColor("#405468"))
    entry = doc.ensure("/shots/version_A.1001.exr", 12, "A / Frame 13 / Source 1013", "24 fps / B = A +10 / ACEScg", image)
    entry.strokes.append(Stroke([[.2, .2], [.8, .8]], "#ff0000", .015))
    entry.note = "Rivedere il bordo: qualità, esposizione e continuità.\nDo not change the background."
    assert render_annotation(entry).pixelColor(320, 180).red() > 200
    path = tmp_path / "review.frmreview"
    doc.save(path, {"offset": 10})
    loaded, state = ReviewDocument.load(path)
    assert state["offset"] == 10
    assert loaded.active()[0].note == entry.note
    assert loaded.active()[0].strokes[0].points == entry.strokes[0].points
    for ext in ("png", "jpg"):
        folder = loaded.export_images(tmp_path, ext)
        assert len(list(folder.glob(f"*.{ext}"))) == 1
        assert (folder / "notes.json").exists()
    loaded.export_pdf(tmp_path / "report.pdf")
    from pypdf import PdfReader
    text = "\n".join(page.extract_text() for page in PdfReader(tmp_path / "report.pdf").pages)
    assert "continuità" in text
    assert "Frame 13" in text


def test_ab_offset_and_frame_bound_paint(tmp_path, app):
    folder_a, folder_b = tmp_path / "a", tmp_path / "b"
    folder_a.mkdir(); folder_b.mkdir()
    for i in range(6):
        write_image(folder_a / f"a.{1001+i}.png", np.full((64, 128, 3), .1 + i * .1, np.float32))
    for i in range(4):
        write_image(folder_b / f"b.{1001+i}.png", np.full((64, 128, 3), .2 + i * .1, np.float32))
    window = MainWindow(); window.show()
    window.open_path(str(folder_a), "A")
    window.open_path(str(folder_b), "B")
    until(app, lambda: all(s.info and s.index == 0 for s in window.sessions.values()))
    window.offset.setValue(2)
    until(app, lambda: window.sessions["B"].index == 2 and not window.sessions["A"].busy)
    assert aligned_frame(0, 2) == 2
    assert window.viewer.keys["B"][1] == 2
    window.pen.setChecked(True)
    rect = window.viewer.image_rect("B")
    start = QPoint(int(rect.left()+rect.width()*.2), int(rect.top()+rect.height()*.3))
    end = QPoint(int(rect.left()+rect.width()*.8), int(rect.top()+rect.height()*.7))
    QTest.mousePress(window.viewer, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(window.viewer, end)
    QTest.mouseRelease(window.viewer, Qt.MouseButton.LeftButton, pos=end)
    assert len(window.document.active()) == 1
    annotation = window.document.active()[0]
    assert annotation.frame == 2 and "b.1001" in annotation.source
    window.go(5)
    until(app, lambda: window.index == 5)
    assert window.viewer.images["B"].isNull()
    assert len(window.document.active()) == 1
    window.document.dirty = False
    window.close()
    until(app, lambda: all(s.worker is None for s in window.sessions.values()))


def test_movie_metadata_and_exact_backward_read(tmp_path):
    path = tmp_path / "tagged.mp4"
    with av.open(str(path), "w") as container:
        stream = container.add_stream("libx264", rate=Fraction(24000, 1001))
        stream.width, stream.height, stream.pix_fmt = 64, 32, "yuv420p"
        stream.codec_context.color_primaries = 1
        stream.codec_context.color_trc = 1
        stream.codec_context.colorspace = 1
        stream.codec_context.color_range = 1
        for i in range(6):
            frame = av.VideoFrame.from_ndarray(np.full((32, 64, 3), 20 + i * 30, np.uint8), format="rgb24")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    source = discover(path)
    info = inspect(source, load_config())
    assert info.fps_exact == "24000/1001"
    assert info.input_space == "Camera Rec.709"
    assert info.attributes["Color range"] == "limited / video (1)"
    reader = SourceReader(source)
    try:
        for index in (0, 4, 1, 5, 0):
            rgb = reader.read(index, lambda: False)
            assert abs(float(np.mean(rgb)) - (20 + index * 30) / 255) < .025
    finally:
        reader.close()


def test_wipe_clips_paint_to_its_own_version(app):
    doc = ReviewDocument()
    viewer = ReviewViewer(doc); viewer.resize(800, 450)
    a = np.zeros((450, 800, 3), np.uint8)
    b = np.zeros_like(a); b[:, :, 2] = 255
    viewer.set_frame("A", a, ("a.png", 0), "A")
    viewer.set_frame("B", b, ("b.png", 0), "B")
    entry = doc.ensure("a.png", 0, "A", "test", viewer.images["A"])
    entry.strokes.append(Stroke([[0, .5], [1, .5]], "#ff0000", .1))
    viewer.mode = "wipe"; viewer.wipe = .5; viewer.show(); app.processEvents()
    image = viewer.grab().toImage()
    scale = image.width() / viewer.width()
    assert image.pixelColor(int(200 * scale), int(225 * scale)).red() > 200
    assert image.pixelColor(int(600 * scale), int(225 * scale)).blue() > 200
    assert image.pixelColor(int(600 * scale), int(225 * scale)).red() < 10
    viewer.close()


def test_source_replacement_and_negative_padding(tmp_path, app):
    for name in ("a", "b", "c"):
        folder = tmp_path / name; folder.mkdir()
        for i in range(5):
            write_image(folder / f"{name}.{i:04d}.png")
    window = MainWindow()
    window.open_path(str(tmp_path / "a"), "A")
    window.open_path(str(tmp_path / "b"), "B")
    until(app, lambda: all(not image.isNull() for image in window.viewer.images.values()))
    window.go(3)
    until(app, lambda: window.index == 3)
    window.open_path(str(tmp_path / "c"), "A")
    until(app, lambda: window.viewer.keys["A"] is not None and "c.0000" in window.viewer.keys["A"][0])
    assert window.viewer.keys["B"][1] == 0
    window.offset.setValue(-2)
    until(app, lambda: not window.sessions["A"].busy)
    assert window.viewer.images["B"].isNull()
    window.go(3)
    until(app, lambda: window.index == 3)
    assert window.viewer.keys["B"][1] == 1
    window.close()
    until(app, lambda: all(s.worker is None for s in window.sessions.values()))


def test_disk_failure_keeps_direct_playback(tmp_path, app, monkeypatch):
    from frm.playback import PlayerSession
    for i in range(3):
        write_image(tmp_path / f"shot.{i:04d}.png")
    def no_space(*args):
        raise OSError("simulated disk full")
    monkeypatch.setattr(SessionCache, "put", no_space)
    session = PlayerSession(); received = []
    session.displayed.connect(lambda i, rgb: received.append(i))
    session.open(discover(tmp_path), "disk", 1024**2, 1280)
    until(app, lambda: bool(session.notice))
    assert received == [0]
    session.request(2)
    until(app, lambda: received == [0, 2])
    root = session.cache.path
    session.close(); until(app, lambda: session.worker is None)
    assert not root.exists()
