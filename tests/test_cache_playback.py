import threading
import time
import numpy as np
import pytest
from frm.media import discover
from frm.playback import PlayerSession, SourceReader
from frm.window import MainWindow
from test_core import app, until, write_image


@pytest.mark.parametrize("mode", ["ram", "disk"])
def test_prepare_reuses_every_frame_and_cleans_up(mode, tmp_path, app, monkeypatch):
    for i in range(12):
        write_image(tmp_path / f"shot.{i:04}.png", np.full((16,32,3), i/20, np.float32))
    reads = []
    original = SourceReader.read
    def read(self, index, stop):
        reads.append(index)
        return original(self,index,stop)
    monkeypatch.setattr(SourceReader,"read",read)
    session = PlayerSession()
    session.open(discover(tmp_path),mode,1024**2,1280)
    until(app,lambda: session.cached == 1)
    folder = session.cache.path
    session.prepare_cache()
    until(app,lambda: session.cached == 12 and not session.preparing)
    assert session.index == 0  # Background preparation must not move the viewer.
    before = len(reads)
    for index in (11,0,5,3,9,1):
        session.request(index)
        until(app,lambda: not session.busy and session.index == index)
    assert len(reads) == before
    if folder:
        assert len(list(folder.glob("*.npy"))) == 12
    session.close()
    until(app,lambda: session.worker is None)
    assert folder is None or not folder.exists()


@pytest.mark.parametrize("mode", ["ram", "disk"])
def test_new_scrub_interrupts_obsolete_work(mode,tmp_path,app,monkeypatch):
    for i in range(2):
        write_image(tmp_path / f"shot.{i:04}.png")
    entered = threading.Event()
    original = SourceReader.read
    def slow(self,index,stop):
        if index == 1:
            entered.set()
            for _ in range(200):
                if stop():
                    raise InterruptedError()
                time.sleep(.01)
        return original(self,index,stop)
    monkeypatch.setattr(SourceReader,"read",slow)
    session = PlayerSession()
    session.open(discover(tmp_path),mode,1024**2,1280)
    until(app,lambda: session.cached == 1)
    session.request(1)
    until(app,entered.is_set)
    session.request(0)
    start = time.monotonic()
    until(app,lambda:not session.busy and session.index == 0)
    assert time.monotonic()-start < 1
    assert session.worker.isRunning()
    session.close(); until(app,lambda:session.worker is None)


def test_slow_cache_playback_does_not_skip_frames(tmp_path,app,monkeypatch):
    for i in range(10):
        write_image(tmp_path / f"shot.{i:04}.png")
    original = SourceReader.read
    def slow(self,index,stop):
        time.sleep(.02)
        return original(self,index,stop)
    monkeypatch.setattr(SourceReader,"read",slow)
    window = MainWindow()
    try:
        window.open_path(str(tmp_path))
        until(app,lambda:window.sessions['A'].cached == 1)
        window.fps.setValue(240);window.loop.setChecked(False)
        window.set_playing(True)
        until(app,lambda:not window.playing and window.sessions['A'].cached == 10)
        assert window.index == 9
    finally:
        window.document.dirty = False;window.close()
        until(app,lambda:all(s.worker is None for s in window.sessions.values()))


def test_prepare_stops_at_budget_without_eviction(tmp_path,app):
    for i in range(10):
        write_image(tmp_path / f"shot.{i:04}.png")
    session = PlayerSession()
    session.open(discover(tmp_path),"ram",32*64*3*3,1280)
    until(app,lambda:session.cached == 1)
    session.prepare_cache()
    until(app,lambda:session.cached == 3 and not session.preparing)
    assert "budget" in session.notice.lower()
    assert set(session.cache.entries) == {0,1,2}
    session.close();until(app,lambda:session.worker is None)
