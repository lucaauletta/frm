"""Bounded, disposable preview caches, owned by the playback worker."""
from collections import OrderedDict
from pathlib import Path
import shutil
import tempfile
import numpy as np


class MemoryCache:
    """Least-recently-used RGB frames. No files and no spill-to-disk path."""
    def __init__(self, limit_bytes=512 * 1024**2):
        self.limit = limit_bytes
        self.used = 0
        self.path = None
        self.entries = OrderedDict()

    def get(self, index):
        rgb = self.entries.get(index)
        if rgb is not None:
            self.entries.move_to_end(index)
        return rgb

    def put(self, index, rgb):
        if rgb.nbytes > self.limit:
            return False
        previous = self.entries.pop(index, None)
        if previous is not None:
            self.used -= previous.nbytes
        while self.used + rgb.nbytes > self.limit:
            _, evicted = self.entries.popitem(last=False)
            self.used -= evicted.nbytes
        rgb.setflags(write=False)
        self.entries[index] = rgb
        self.used += rgb.nbytes
        return True

    def close(self):
        self.entries.clear()
        self.used = 0


class SessionCache:
    """LRU disk cache; only this object's private directory may be removed."""
    def __init__(self, limit_bytes=8 * 1024**3):
        self._temp = tempfile.TemporaryDirectory(prefix="frm-session-")
        self.path = Path(self._temp.name)
        self.limit = limit_bytes
        self.used = 0
        self.entries = OrderedDict()

    def put(self, index, rgb):
        needed = rgb.nbytes + 256
        if needed > self.limit:
            return False
        if index in self.entries:
            self.entries.move_to_end(index)
            return True
        while self.entries and self.used + needed > self.limit:
            old, size = self.entries.popitem(last=False)
            (self.path / f"{old:09d}.npy").unlink()
            self.used -= size
        if shutil.disk_usage(self.path).free < needed + 512 * 1024**2:
            raise OSError("Disk cache paused: less than 512 MiB free. Direct reading continues.")
        path = self.path / f"{index:09d}.npy"
        try:
            np.save(path, rgb, allow_pickle=False)
        except OSError:
            path.unlink(missing_ok=True)
            raise
        size = path.stat().st_size
        self.entries[index] = size
        self.used += size
        return True

    def get(self, index):
        if index not in self.entries:
            return None
        rgb = np.load(self.path / f"{index:09d}.npy", allow_pickle=False)
        self.entries.move_to_end(index)
        return rgb

    def close(self):
        self._temp.cleanup()
        self.entries.clear()
        self.used = 0
