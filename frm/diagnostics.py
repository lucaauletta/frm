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
    app = QApplication.instance() or QApplication([])
    configure_app(app)
    result = {}
    window = None
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
            window.show()
            window.open_path(str(root / "gradient.exr"))
            deadline = time.monotonic() + 30
            while window.building:
                app.processEvents()
                if time.monotonic() > deadline:
                    raise TimeoutError("Preview decoding timed out")
                time.sleep(0.01)
            app.processEvents()
            assert window.available == 1, window.error_text
            assert not window.viewer.image.isNull()
            report.parent.mkdir(parents=True, exist_ok=True)
            assert window.grab().save(str(report.with_suffix(".png")))
            cache_path = window.cache.path
            window.close()
            app.processEvents()
            assert not cache_path.exists()
            result["gui"] = "Rendered preview; cache deleted on close"
            result["ok"] = True
    except Exception:
        result["error"] = traceback.format_exc()
        result["ok"] = False
    finally:
        if window:
            window.close()
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1
