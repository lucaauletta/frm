"""Optional GitHub release checks; never download or execute updates silently."""
import json
import re
import sys
from pathlib import Path
from PySide6.QtCore import QObject, QSettings, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtWidgets import QMessageBox
from . import __version__

RELEASES = "https://github.com/lucaauletta/frm/releases"


def version_tuple(value):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", value)
    return tuple(map(int, match.groups())) if match else None


def newest_release(items, current=__version__):
    candidates = []
    for item in items:
        version = version_tuple(item.get("tag_name", ""))
        url = item.get("html_url", "")
        if (not item.get("draft") and item.get("assets") and version
                and version > version_tuple(current)
                and url.startswith(RELEASES + "/tag/")):
            candidates.append((version, item))
    return max(candidates, key=lambda pair: pair[0])[1] if candidates else None


class UpdateChecker(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.manager = QNetworkAccessManager(self)
        self.reply = None
        self.settings = QSettings("FRM", "FRM")
        installed = sys.platform == "win32" and (Path(sys.executable).parent / "unins000.exe").exists()
        self.automatic = self.settings.value("updates/automatic", installed, type=bool)
        if self.automatic:
            QTimer.singleShot(4000, lambda: self.check(False))

    def set_automatic(self, enabled):
        self.automatic = enabled
        self.settings.setValue("updates/automatic", enabled)

    def check(self, manual=True):
        if self.reply:
            return
        request = QNetworkRequest(QUrl("https://api.github.com/repos/lucaauletta/frm/releases?per_page=30"))
        request.setRawHeader(b"User-Agent", b"FRM-release-check")
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        request.setTransferTimeout(10000)
        self.reply = self.manager.get(request)
        self.reply.finished.connect(lambda: self.finished(manual))

    def finished(self, manual):
        reply, self.reply = self.reply, None
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                raise ValueError("Cannot contact GitHub. Check your connection and try again.")
            payload = bytes(reply.readAll())
            if len(payload) > 4 * 1024 * 1024:
                raise ValueError("Release response is too large.")
            items = json.loads(payload)
            if not isinstance(items, list):
                raise ValueError("Unexpected release response.")
            release = newest_release(items)
            if release:
                answer = QMessageBox.question(self.window, "FRM update available",
                    f"FRM {release['tag_name']} is available (installed: {__version__}).\n\n"
                    "Open the official download page? On Windows, download Setup to update an installed copy. "
                    "Save your review and close FRM before running Setup. Portable users replace their executable.")
                if answer == QMessageBox.StandardButton.Yes:
                    QDesktopServices.openUrl(QUrl(release["html_url"]))
            elif manual:
                QMessageBox.information(self.window, "FRM updates", f"FRM {__version__} is up to date.")
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            if manual:
                QMessageBox.warning(self.window, "Cannot check for updates", str(exc))
        finally:
            reply.deleteLater()
