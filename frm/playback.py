"""On-demand decoding: one active frame and one replaceable request, never a full-shot queue."""
from threading import Condition
import av
import numpy as np
import OpenImageIO as oiio
from PySide6.QtCore import QObject, QThread, Signal
from .cache import MemoryCache, SessionCache
from .color import ColorSettings, load_config, processor, to_display
from .media import read_image, MAX_PIXELS
from .metadata import inspect


class SourceReader:
    def __init__(self, source):
        self.source = source
        self.container = self.iterator = None
        self.position = -1

    def close(self):
        self.iterator = None
        if self.container:
            self.container.close()
            self.container = None
        self.position = -1

    def read(self, index, stop):
        if index < 0:
            raise EOFError(0)
        if not self.source.movie:
            if index >= len(self.source.paths):
                raise EOFError(len(self.source.paths))
            return read_image(self.source.paths[index])
        # Preserve exact frame indexing for VFR/B-frame sources. A backward cache miss
        # restarts decoding; do not estimate a frame index from a timestamp.
        if self.container is None or index <= self.position:
            self.close()
            self.container = av.open(str(self.source.paths[0]))
            stream = self.container.streams.video[0]
            if stream.width * stream.height > MAX_PIXELS:
                raise ValueError("Video exceeds the 100 megapixel limit.")
            stream.thread_type = "AUTO"
            self.iterator = iter(self.container.decode(stream))
        while self.position < index:
            if stop():
                raise InterruptedError()
            try:
                frame = next(self.iterator)
            except StopIteration:
                raise EOFError(self.position + 1)
            self.position += 1
        return frame.to_ndarray(format="rgb48le").astype(np.float32) / 65535.0


def preview(rgb, width, cpu):
    h, w, _ = rgb.shape
    if w > width:
        nh = max(1, round(h * width / w))
        src = oiio.ImageBuf(oiio.ImageSpec(w, h, 3, oiio.FLOAT))
        src.set_pixels(oiio.ROI(0, w, 0, h, 0, 1, 0, 3), rgb)
        dst = oiio.ImageBuf(oiio.ImageSpec(width, nh, 3, oiio.FLOAT))
        if not oiio.ImageBufAlgo.resize(dst, src):
            raise ValueError(dst.geterror())
        rgb = np.asarray(dst.get_pixels(oiio.FLOAT))
    return to_display(rgb, cpu)


class PlaybackWorker(QThread):
    prepared = Signal(object, object)
    frame = Signal(int, object, int)
    failed = Signal(str, int)
    ended = Signal(int, int)
    stats = Signal(int, object, int)
    warning = Signal(str)

    def __init__(self, source, cache, settings, width):
        super().__init__()
        self.source, self.cache, self.settings, self.width = source, cache, settings, width
        self.condition = Condition()
        self.requested = None

    def request(self, index, ticket):
        with self.condition:
            self.requested = (index, ticket)
            self.condition.notify()

    def stop(self):
        self.requestInterruption()
        with self.condition:
            self.condition.notify()

    def run(self):
        reader = SourceReader(self.source)
        hits = 0
        cache_enabled = self.cache is not None
        try:
            config = load_config(self.settings.config if self.settings else "")
            info = inspect(self.source, config)
            settings = self.settings
            if settings is None:
                display = config.getDefaultDisplay()
                settings = ColorSettings(enabled=bool(info.input_space) and info.scene_referred,
                    input_space=info.input_space or "ACEScg", display=display, view=config.getDefaultView(display))
            cpu = processor(settings)
            self.prepared.emit(info, settings)
            while not self.isInterruptionRequested():
                with self.condition:
                    self.condition.wait_for(lambda: self.requested is not None or self.isInterruptionRequested())
                    if self.isInterruptionRequested():
                        break
                    index, ticket = self.requested
                    self.requested = None
                try:
                    rgb = None
                    if cache_enabled:
                        try:
                            rgb = self.cache.get(index)
                        except (OSError, ValueError) as exc:
                            cache_enabled = False
                            self.warning.emit(f"Cache unavailable; reading directly. {exc}")
                    hit = rgb is not None
                    if not hit:
                        rgb = preview(reader.read(index, self.isInterruptionRequested), self.width, cpu)
                    else:
                        hits += 1
                    if self.isInterruptionRequested():
                        break
                    # Display first. Disk writes never block the Qt UI or delay first delivery.
                    self.frame.emit(index, rgb, ticket)
                    if cache_enabled and not hit:
                        try:
                            stored = self.cache.put(index, rgb)
                            if not stored:
                                self.warning.emit("Frame exceeds cache budget; direct reading continues.")
                        except (OSError, MemoryError) as exc:
                            cache_enabled = False
                            self.warning.emit(f"Cache paused; direct reading continues. {exc}")
                    self.stats.emit(len(self.cache.entries) if self.cache else 0, self.cache.used if self.cache else 0, hits)
                except EOFError as exc:
                    self.ended.emit(int(exc.args[0]), ticket)
                except InterruptedError:
                    break
                except Exception as exc:
                    self.failed.emit(str(exc), ticket)
        except Exception as exc:
            self.failed.emit(str(exc), -1)
        finally:
            reader.close()


class PlayerSession(QObject):
    """UI-thread owner of a single version. Stops writers before freeing any cache."""
    prepared = Signal()
    displayed = Signal(int, object)
    changed = Signal()
    failed = Signal(str)
    closed = Signal()
    ended = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.source = self.worker = self.cache = self.info = None
        self.settings = None
        self.index = -1
        self.busy = False
        self.total = 0
        self.count_exact = True
        self.generation = self.ticket = 0
        self.cached = self.used = self.hits = 0
        self.notice = ""
        self.pending = None

    def open(self, source, mode, limit, width, settings=None, index=0):
        self.pending = (source, mode, limit, width, settings, index)
        self._stop()

    def close(self):
        self.pending = None
        self._stop()

    def _stop(self):
        self.generation += 1
        self.busy = False
        if self.worker and self.worker.isRunning():
            self.worker.stop()
        else:
            self._stopped()

    def _stopped(self):
        if self.worker and self.worker.isRunning():
            return
        if self.worker:
            self.worker.deleteLater()
        self.worker = None
        if self.cache:
            try:
                self.cache.close()
            except OSError as exc:
                self.failed.emit(f"Could not delete cache at {self.cache.path}: {exc}")
                self.pending = None
                self.cache = None
                self.closed.emit()
                return
        self.cache = None
        self.source = self.info = None
        self.index = -1
        self.cached = self.used = self.hits = 0
        if self.pending:
            args, self.pending = self.pending, None
            self._start(*args)
        else:
            self.closed.emit()

    def _start(self, source, mode, limit, width, settings, index):
        self.source, self.settings = source, settings
        self.notice = ""
        self.total = 0
        self.count_exact = True
        try:
            self.cache = MemoryCache(limit) if mode == "ram" else SessionCache(limit) if mode == "disk" else None
        except OSError as exc:
            self.cache = None
            self.notice = f"Cache unavailable; direct reading. {exc}"
        worker = PlaybackWorker(source, self.cache, settings, width)
        self.worker = worker
        generation = self.generation
        worker.prepared.connect(lambda info, color: self._prepared(info, color) if generation == self.generation else None)
        worker.frame.connect(lambda i, rgb, ticket: self._frame(i, rgb, ticket) if generation == self.generation else None)
        worker.stats.connect(lambda n, size, hits: self._stats(n, size, hits) if generation == self.generation else None)
        worker.warning.connect(lambda message: self._warning(message) if generation == self.generation else None)
        worker.failed.connect(lambda message, ticket: self._failed(message, ticket) if generation == self.generation else None)
        worker.ended.connect(lambda total, ticket: self._ended(total, ticket) if generation == self.generation else None)
        worker.finished.connect(self._stopped)
        self.request(index)
        worker.start()

    def _prepared(self, info, settings):
        self.info, self.settings = info, settings
        self.total, self.count_exact = info.total, info.count_exact
        self.prepared.emit()

    def request(self, index):
        if self.worker:
            self.ticket += 1
            self.busy = True
            self.worker.request(index, self.ticket)

    def _frame(self, index, rgb, ticket):
        if ticket != self.ticket:
            return
        self.busy = False
        self.index = index
        if not self.count_exact:
            self.total = max(self.total, index + 1)
        self.displayed.emit(index, rgb)

    def _stats(self, frames, used, hits):
        self.cached, self.used, self.hits = frames, used, hits
        self.changed.emit()

    def _warning(self, message):
        self.notice = message
        self.changed.emit()

    def _failed(self, message, ticket):
        if ticket in (-1, self.ticket):
            self.busy = False
            self.failed.emit(message)

    def _ended(self, total, ticket):
        if ticket != self.ticket:
            return
        self.busy = False
        self.total = total
        self.count_exact = True
        self.ended.emit()
