"""Private, bounded cache. Only directories created by this process are removed."""
from pathlib import Path
import shutil
import tempfile
import numpy as np


class SessionCache:
    def __init__(self, limit_bytes=8 * 1024**3):
        self._temp = tempfile.TemporaryDirectory(prefix="frm-session-")
        self.path = Path(self._temp.name)
        self.limit = limit_bytes
        self.used = 0

    def put(self, index, rgb):
        needed = rgb.nbytes + 256
        if self.used + needed > self.limit:
            raise ValueError("Cache limit reached (8 GiB). Open a shorter clip or choose a smaller preview size.")
        if shutil.disk_usage(self.path).free < needed + 512 * 1024**2:
            raise ValueError("Cache stopped: less than 512 MiB of free disk space would remain.")
        path = self.path / f"{index:09d}.npy"
        np.save(path, rgb, allow_pickle=False)
        self.used += path.stat().st_size

    def get(self, index):
        return np.load(self.path / f"{index:09d}.npy", allow_pickle=False)

    def close(self):
        self._temp.cleanup()
