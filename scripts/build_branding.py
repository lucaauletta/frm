"""Package the approved raster artwork for native application icons."""
from pathlib import Path
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QImage, QPainter, QColor
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def artwork(name):
    image = QImage(str(ROOT / "docs" / "branding" / name))
    if image.isNull():
        raise RuntimeError(f"Missing branding artwork: {name}")
    # Ignore near-transparent raster noise when aligning the actual artwork.
    alpha = Image.open(ROOT / "docs" / "branding" / name).getchannel("A")
    box = alpha.point(lambda value: 255 if value >= 128 else 0).getbbox()
    left, top, right, bottom = box
    return image.copy(left, top, right - left, bottom - top)


def main():
    app = QApplication.instance() or QApplication([])
    destination = ROOT / "frm" / "assets"
    destination.mkdir(exist_ok=True)
    logo = artwork("frm-wordmark-black.png")
    painter = QPainter(logo)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(logo.rect(), QColor("white"))
    painter.end()
    logo.save(str(destination / "wordmark-white.png"))
    symbol = artwork("frm-symbol-black.png")
    icon = QImage(1024, 1024, QImage.Format.Format_ARGB32_Premultiplied)
    icon.fill(Qt.GlobalColor.transparent)
    painter = QPainter(icon)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#f4f4f4"))
    painter.drawRoundedRect(QRectF(32, 32, 960, 960), 196, 196)
    size = symbol.size().scaled(660, 660, Qt.AspectRatioMode.KeepAspectRatio)
    painter.drawImage(QRectF((1024-size.width())/2, (1024-size.height())/2,
                            size.width(), size.height()), symbol)
    painter.end()
    icon.save(str(destination / "app-icon.png"))
    # Format conversion only; the same rendered artwork is used on all systems.
    image = Image.open(destination / "app-icon.png")
    image.save(destination / "app-icon.ico", sizes=[(n, n) for n in (16,24,32,48,64,128,256)])
    image.save(destination / "app-icon.icns")


if __name__ == "__main__":
    main()
