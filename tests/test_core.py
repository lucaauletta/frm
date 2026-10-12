from pathlib import Path
from fractions import Fraction
import time

import av
import numpy as np
import OpenImageIO as oiio
import pytest
from PySide6.QtWidgets import QApplication
from frm.cache import SessionCache
from frm.color import ColorSettings, processor, to_display, load_config
from frm.media import discover, read_image, frames, probe
from frm.worker import CacheWorker
from frm.app import MainWindow, ColorDialog, configure_app


def write_image(path, pixels=None):
    if pixels is None:
        pixels = np.full((32, 64, 3), 0.25, np.float32)
    out = oiio.ImageOutput.create(str(path))
    assert out
    spec = oiio.ImageSpec(pixels.shape[1], pixels.shape[0], pixels.shape[2], oiio.FLOAT if path.suffix == ".exr" else oiio.UINT16)
    assert out.open(str(path), spec), out.geterror()
    assert out.write_image(pixels), out.geterror()
    assert out.close()


def test_discovery_padding_gaps_and_folder_ambiguity(tmp_path):
    for name in ["shot.0010.exr", "shot.0012.exr", "shot.0011.png", "shot.13.exr", "other.exr"]:
        (tmp_path / name).touch()
    source = discover(tmp_path / "shot.0012.exr")
    assert [p.name for p in source.paths] == ["shot.0010.exr", "shot.0012.exr"]
    assert source.gaps == 1
    with pytest.raises(ValueError, match="multiple sequences"):
        discover(tmp_path)
    with pytest.raises(ValueError, match="missing"):
        discover(tmp_path / "absent.png")


@pytest.mark.parametrize("ext", ["dpx", "exr", "tiff", "jpg", "png"])
def test_image_codecs(tmp_path, ext):
    path = tmp_path / f"frame.0001.{ext}"
    write_image(path)
    rgb = read_image(path)
    assert rgb.dtype == np.float32
    assert rgb.shape == (32, 64, 3)
    assert np.allclose(rgb, 0.25, atol=0.015)


@pytest.mark.parametrize("codec,ext,pix_fmt,size,profile", [
    ("prores_ks", "mov", "yuv422p10le", (64, 32), None),
    ("dnxhd", "mov", "yuv422p", (1920, 1080), None),
    ("dnxhd", "mov", "yuv422p10le", (320, 240), "dnxhr_hqx"),
    ("libx264", "mp4", "yuv420p", (64, 32), None),
    ("libx265", "mp4", "yuv420p", (64, 64), None),
])
def test_movie_codecs(tmp_path, codec, ext, pix_fmt, size, profile):
    path = tmp_path / f"clip.{ext}"
    with av.open(str(path), "w") as output:
        stream = output.add_stream(codec, rate=Fraction(24, 1))
        stream.width, stream.height = size
        stream.pix_fmt = pix_fmt
        if codec == "dnxhd":
            stream.bit_rate = 120_000_000
        if profile:
            stream.options = {"profile": profile}
        if codec == "libx265":
            stream.options = {"x265-params": "log-level=error:pools=1"}
        for i in range(3):
            pixels = np.full((size[1], size[0], 3), 40 + i * 30, np.uint8)
            frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
            for packet in stream.encode(frame):
                output.mux(packet)
        for packet in stream.encode():
            output.mux(packet)
    source = discover(path)
    decoded = list(frames(source, lambda: False))
    assert len(decoded) == 3
    assert decoded[0].shape == (size[1], size[0], 3)
    assert np.mean(decoded[2]) > np.mean(decoded[0])
    assert probe(source)[0] == 24


def test_float_color_and_lut(tmp_path):
    rgb = np.array([[[0.18, 0.5, 2.0], [-1.0, float("nan"), float("inf")]]], np.float32)
    result = to_display(rgb, processor(ColorSettings()))
    assert result.tolist() == [[[46, 128, 255], [0, 0, 255]]]
    config = load_config()
    display = config.getDefaultDisplay()
    settings = ColorSettings(True, "", "ACEScg", display, config.getDefaultView(display))
    transformed = to_display(rgb[:, :1], processor(settings))
    assert not np.array_equal(transformed, result[:, :1])
    lut = tmp_path / "invert.cube"
    lut.write_text("LUT_1D_SIZE 2\n1 1 1\n0 0 0\n")
    result = to_display(np.zeros((1, 1, 3), np.float32), processor(ColorSettings(lut=str(lut))))
    assert result.tolist() == [[[255, 255, 255]]]


def test_cache_limit_and_cleanup():
    cache = SessionCache(limit_bytes=1000)
    root = cache.path
    rgb = np.zeros((4, 4, 3), np.uint8)
    cache.put(0, rgb)
    assert np.array_equal(cache.get(0), rgb)
    with pytest.raises(ValueError, match="Cache limit"):
        cache.put(1, np.zeros((100, 100, 3), np.uint8))
    cache.close()
    assert not root.exists()


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    configure_app(application)
    return application


def until(app, condition, timeout=15):
    end = time.monotonic() + timeout
    while not condition():
        app.processEvents()
        if time.monotonic() > end:
            raise AssertionError("Qt operation timed out")
        time.sleep(0.005)
    app.processEvents()


def test_worker_resize_and_gui_lifecycle(tmp_path, app):
    for i in range(5):
        write_image(tmp_path / f"test.{i:04d}.exr")
    cache = SessionCache()
    worker = CacheWorker(discover(tmp_path), cache, ColorSettings(), 32)
    errors = []
    worker.failed.connect(errors.append)
    worker.start()
    until(app, lambda: worker.isFinished())
    assert not errors
    assert cache.get(0).shape == (16, 32, 3)
    cache.close()
    window = MainWindow()
    dialog = ColorDialog(ColorSettings(), window)
    assert dialog.input_space.currentText() == "ACEScg"
    processor(dialog.settings())
    dialog.close()
    window.open_path(str(tmp_path))
    until(app, lambda: not window.building)
    assert window.available == 5, window.error_text
    assert not window.viewer.image.isNull()
    window.step(2)
    assert window.index == 2
    window.toggle_play()
    window.anchor -= 0.05
    window.tick()
    assert window.index >= 3
    root = window.cache.path
    window.clear_media()
    assert not root.exists()
    # Replacing a running generation must never display stale frames or delete the new cache.
    window.open_path(str(tmp_path))
    window.rebuild()
    until(app, lambda: window.pending is None and not window.building)
    assert window.available == 5, window.error_text
    root = window.cache.path
    window.close()
    until(app, lambda: not root.exists())


def test_close_while_decoding(tmp_path, app):
    for i in range(15):
        write_image(tmp_path / f"test.{i:04d}.png")
    window = MainWindow()
    window.open_path(str(tmp_path))
    root = window.cache.path
    window.close()
    until(app, lambda: not root.exists())
