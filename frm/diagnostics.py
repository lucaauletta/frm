"""Offline smoke check for the actual frozen application, including its Qt plugins."""
import json
import os
from pathlib import Path
import tempfile
import time
import traceback


def self_test(report: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import av
    import numpy as np
    import OpenImageIO as oiio
    from PySide6.QtWidgets import QApplication
    from .app import MainWindow, configure_app, ColorDialog
    from .color import ColorSettings, processor
    from .media import discover, frames
    from .review import Stroke, ReviewDocument
    app = QApplication.instance() or QApplication([])
    configure_app(app)
    result = {}
    window = None
    def wait_for(condition):
        deadline = time.monotonic() + 30
        while not condition():
            app.processEvents()
            if time.monotonic() > deadline:
                raise TimeoutError("Playback operation timed out")
            time.sleep(.005)
        app.processEvents()
    try:
        with tempfile.TemporaryDirectory(prefix="frm-test-") as folder:
            root = Path(folder)
            y, x = np.mgrid[0:360, 0:640]
            rgb = np.stack((x / 640, y / 360, (1 - x / 640) * 0.75), axis=2).astype(np.float32)
            for ext in ("dpx", "exr", "tiff", "jpg", "png"):
                path = root / f"gradient.{ext}"
                out = oiio.ImageOutput.create(str(path))
                assert out.open(str(path), oiio.ImageSpec(640, 360, 3, oiio.FLOAT if ext == "exr" else oiio.UINT16))
                assert out.write_image(rgb)
                out.close()
                assert next(frames(discover(path), lambda: False)).shape == rgb.shape
                result[ext] = "decoded"
            for codec in ("prores", "dnxhd", "h264", "hevc"):
                av.Codec(codec, "r")
                result[codec] = "decoder available"
            window = MainWindow()
            dialog = ColorDialog(ColorSettings(), window)
            dialog.enabled.setChecked(True)
            processor(dialog.settings())
            dialog.close()
            result["ocio"] = "ACES display processor compiled"
            for index, label in ((2, "direct"), (0, "RAM"), (1, "disk")):
                window.cache_mode.setCurrentIndex(index)
                window.open_path(str(root / "gradient.exr"))
                wait_for(lambda: window.sessions["A"].index == 0)
                assert not window.viewer.images["A"].isNull()
                cache = window.sessions["A"].cache
                cache_path = cache.path if cache else None
                window.clear_media()
                wait_for(lambda: window.sessions["A"].worker is None)
                assert cache is None or cache.used == 0
                assert cache_path is None or not cache_path.exists()
                result[label] = "First frame displayed; cache freed on close"
            window.open_path(str(root / "gradient.exr"), "A")
            window.open_path(str(root / "gradient.png"), "B")
            window.show()
            wait_for(lambda: all(not image.isNull() for image in window.viewer.images.values()))
            entry = window.current_annotation("A")
            entry.strokes.append(Stroke([[.2, .3], [.7, .6]], "#ff4b55", .008))
            entry.note = "Review the transition and highlight detail.\nCheck continuity against version B."
            window.refresh_notes()
            report.parent.mkdir(parents=True, exist_ok=True)
            assert window.grab().save(str(report.with_suffix(".png")))
            window.document.export_pdf(report.with_suffix(".pdf"))
            review_path = report.with_suffix(".frmreview")
            window.document.save(review_path, window.state())
            restored, state = ReviewDocument.load(review_path)
            assert len(restored.active()) == 1 and "A" in state["sources"]
            result["review"] = "A/B rendered; paint, PDF export and saved review verified"
            window.close()
            wait_for(lambda: all(s.worker is None for s in window.sessions.values()))
            result["gui"] = "Rendered review workspace; both caches closed"
            result["ok"] = True
    except Exception:
        result["error"] = traceback.format_exc()
        result["ok"] = False
    finally:
        if window:
            window.document.dirty = False
            window.close()
            wait_for(lambda: all(s.worker is None for s in window.sessions.values()))
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1
