"""On-demand decoding: one active frame and one replaceable request, never a full-shot queue."""
from threading import Condition
import sys
from time import perf_counter
import av
import numpy as np
import OpenImageIO as oiio
from PySide6.QtCore import QObject, QThread, Signal
from .cache import MemoryCache, SessionCache
from .color import ColorSettings, load_config, processor, to_display
from .media import read_image, MAX_PIXELS
from .metadata import inspect


class SourceReader:
    def __init__(self, source, decoder="cpu", preview_width=None):
        self.source = source
        self.decoder = decoder
        self.preview_width = preview_width
        self.backend = "CPU"
        self.hardware_failed = False
        self.fallback_reason = ""
        self.container = self.iterator = None
        self.position = -1

    def close(self):
        self.iterator = None
        if self.container:
            self.container.close()
            self.container = None
        self.position = -1

    def read(self, index, stop):
        try:
            return self._read(index, stop)
        except (EOFError, InterruptedError):
            raise
        except Exception as exc:
            if self.decoder == "cpu" or self.hardware_failed or not self.source.movie:
                raise
            self.hardware_failed = True
            self.fallback_reason = f"Hardware unavailable; CPU fallback ({type(exc).__name__})"
            self.close()
            return self._read(index, stop)

    def _read(self, index, stop):
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
            options = {}
            if self.decoder != "cpu" and not self.hardware_failed:
                from av.codec.hwaccel import HWAccel, hwdevices_available
                device = "videotoolbox" if sys.platform == "darwin" else "cuda"
                if device in hwdevices_available():
                    options["hwaccel"] = HWAccel(device, allow_software_fallback=True)
            self.container = av.open(str(self.source.paths[0]), **options)
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
        self.backend = ("VideoToolbox" if sys.platform == "darwin" else "NVIDIA NVDEC") if stream_hw(self.container) else "CPU"
        if self.preview_width and frame.width > self.preview_width:
            # In fast mode libswscale combines video conversion and downsampling,
            # avoiding a full-resolution float RGB buffer plus an OIIO copy.
            frame = frame.reformat(width=self.preview_width,
                height=max(1, round(frame.height*self.preview_width/frame.width)),
                format="rgb48le", interpolation="BILINEAR")
        return frame.to_ndarray(format="rgb48le").astype(np.float32) / 65535.0


def stream_hw(container):
    return bool(container and container.streams.video[0].codec_context.is_hwaccel)


def preview(rgb, width, cpu, fast=False):
    h, w, _ = rgb.shape
    if w > width:
        nh = max(1, round(h * width / w))
        src = oiio.ImageBuf(oiio.ImageSpec(w, h, 3, oiio.FLOAT))
        src.set_pixels(oiio.ROI(0, w, 0, h, 0, 1, 0, 3), rgb)
        dst = oiio.ImageBuf(oiio.ImageSpec(width, nh, 3, oiio.FLOAT))
        ok = oiio.ImageBufAlgo.resample(dst, src, True) if fast else oiio.ImageBufAlgo.resize(dst, src)
        if not ok:
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
    measured = Signal(object)

    def __init__(self, source, cache, settings, width, decoder="cpu", fast_preview=True):
        super().__init__()
        self.source, self.cache, self.settings, self.width = source, cache, settings, width
        self.condition = Condition()
        self.requested = None
        self.decoder = decoder
        self.fast_preview = fast_preview

    def request(self, index, ticket):
        with self.condition:
            self.requested = (index, ticket)
            self.condition.notify()

    def stop(self):
        self.requestInterruption()
        with self.condition:
            self.condition.notify()

    def run(self):
        reader = SourceReader(self.source, self.decoder, self.width if self.fast_preview else None)
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
                    started = perf_counter()
                    decode_ms = transform_ms = write_ms = 0.0
                    rgb = None
                    if cache_enabled:
                        try:
                            rgb = self.cache.get(index)
                        except (OSError, ValueError) as exc:
                            cache_enabled = False
                            self.warning.emit(f"Cache unavailable; reading directly. {exc}")
                    hit = rgb is not None
                    if not hit:
                        before = perf_counter()
                        raw = reader.read(index, self.isInterruptionRequested)
                        decode_ms = (perf_counter() - before) * 1000
                        before = perf_counter()
                        rgb = preview(raw, self.width, cpu, self.fast_preview)
                        transform_ms = (perf_counter() - before) * 1000
                    else:
                        hits += 1
                    if self.isInterruptionRequested():
                        break
                    # Display first. Disk writes never block the Qt UI or delay first delivery.
                    self.frame.emit(index, rgb, ticket)
                    if cache_enabled and not hit:
                        try:
                            before = perf_counter()
                            stored = self.cache.put(index, rgb)
                            write_ms = (perf_counter() - before) * 1000
                            if not stored:
                                self.warning.emit("Frame exceeds cache budget; direct reading continues.")
                        except (OSError, MemoryError) as exc:
                            cache_enabled = False
                            self.warning.emit(f"Cache paused; direct reading continues. {exc}")
                    self.stats.emit(len(self.cache.entries) if self.cache else 0, self.cache.used if self.cache else 0, hits)
                    self.measured.emit(dict(backend=reader.backend, cache_hit=hit,
                        decode_ms=decode_ms, transform_ms=transform_ms, write_ms=write_ms,
                        total_ms=(perf_counter()-started)*1000, fallback=reader.fallback_reason))
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
        self.decoder = "cpu"
        self.fast_preview = True
        self.performance = {}

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
        self.performance = {}
        worker = PlaybackWorker(source, self.cache, settings, width, self.decoder, self.fast_preview)
        self.worker = worker
        generation = self.generation
        worker.prepared.connect(lambda info, color: self._prepared(info, color) if generation == self.generation else None)
        worker.frame.connect(lambda i, rgb, ticket: self._frame(i, rgb, ticket) if generation == self.generation else None)
        worker.stats.connect(lambda n, size, hits: self._stats(n, size, hits) if generation == self.generation else None)
        worker.warning.connect(lambda message: self._warning(message) if generation == self.generation else None)
        worker.measured.connect(lambda values: self._measured(values) if generation == self.generation else None)
        worker.failed.connect(lambda message, ticket: self._failed(message, ticket) if generation == self.generation else None)
        worker.ended.connect(lambda total, ticket: self._ended(total, ticket) if generation == self.generation else None)
        worker.finished.connect(self._stopped)
        self.request(index)
        worker.start()

    def _prepared(self, info, settings):
        self.info, self.settings = info, settings
        self.total, self.count_exact = info.total, info.count_exact
        self.prepared.emit()

    def _measured(self, values):
        self.performance = values

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
