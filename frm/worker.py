"""Cancelable background decoder; Qt widgets are touched only by the UI thread."""
import numpy as np
import OpenImageIO as oiio
from PySide6.QtCore import QThread, Signal
from .media import frames, probe
from .color import processor, to_display


class CacheWorker(QThread):
    metadata = Signal(float, int, str)
    ready = Signal(int, int, int)
    failed = Signal(str)

    def __init__(self, source, cache, settings, width):
        super().__init__()
        self.source, self.cache, self.settings, self.width = source, cache, settings, width

    def run(self):
        try:
            self.metadata.emit(*probe(self.source))
            cpu = processor(self.settings)
            for index, rgb in enumerate(frames(self.source, self.isInterruptionRequested)):
                if self.isInterruptionRequested():
                    break
                h, w, _ = rgb.shape
                if w > self.width:
                    nh = max(1, round(h * self.width / w))
                    src = oiio.ImageBuf(oiio.ImageSpec(w, h, 3, oiio.FLOAT))
                    src.set_pixels(oiio.ROI(0, w, 0, h, 0, 1, 0, 3), rgb)
                    out = oiio.ImageBuf(oiio.ImageSpec(self.width, nh, 3, oiio.FLOAT))
                    if not oiio.ImageBufAlgo.resize(out, src):
                        raise ValueError(out.geterror())
                    rgb = np.asarray(out.get_pixels(oiio.FLOAT))
                self.cache.put(index, to_display(rgb, cpu))
                self.ready.emit(index, w, h)
        except Exception as exc:
            self.failed.emit(str(exc))
