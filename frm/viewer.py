"""A/B canvas, wipe handle and normalized frame annotations."""
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QImage, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget
from .review import Stroke, paint_strokes


class ReviewViewer(QWidget):
    stroke_added = Signal(str, object)
    interaction = Signal()
    target_changed = Signal(str)

    def __init__(self, document):
        super().__init__()
        self.document = document
        self.images = {"A": QImage(), "B": QImage()}
        self.keys = {"A": None, "B": None}
        self.labels = {"A": "A", "B": "B"}
        self.mode = "A"
        self.wipe = .5
        self.painting = False
        self.brush_color = "#ff4b55"
        self.brush_width = 4
        self.draft = None
        self.draft_slot = None
        self.drag_wipe = False
        self.setMinimumSize(400, 240)
        self.setMouseTracking(True)

    def set_frame(self, slot, rgb, key, label):
        if rgb is None:
            image = QImage()
        else:
            h, w, _ = rgb.shape
            image = QImage(rgb.data, w, h, rgb.strides[0], QImage.Format.Format_RGB888).copy()
        self.images[slot], self.keys[slot], self.labels[slot] = image, key, label
        self.update()

    def area(self, slot):
        rect = QRectF(self.rect())
        if self.mode == "side":
            half = rect.width() / 2
            rect = QRectF(0 if slot == "A" else half + 1, 0, half - 1, rect.height())
        return rect

    def image_rect(self, slot):
        image = self.images[slot]
        area = self.area(slot)
        if image.isNull():
            return area
        ratio = min(area.width() / image.width(), area.height() / image.height())
        w, h = image.width() * ratio, image.height() * ratio
        return QRectF(area.center().x() - w / 2, area.center().y() - h / 2, w, h)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#07090c"))
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        slots = [self.mode] if self.mode in ("A", "B") else ["A", "B"]
        for slot in slots:
            painter.save()
            if self.mode == "wipe":
                x = self.width() * self.wipe
                painter.setClipRect(QRectF(0, 0, x, self.height()) if slot == "A" else QRectF(x, 0, self.width() - x, self.height()))
            image = self.images[slot]
            rect = self.image_rect(slot)
            if image.isNull():
                painter.setPen(QColor("#667282")); painter.setFont(QFont("Inter", 13))
                text = "Drop a shot to start your review" if slot == "A" and self.keys[slot] is None else f"{slot} / No frame at this position"
                painter.drawText(self.area(slot), Qt.AlignmentFlag.AlignCenter, text)
            else:
                painter.drawImage(rect, image)
                entry = self.document.entries.get(self.keys[slot])
                strokes = list(entry.strokes) if entry else []
                if self.draft_slot == slot and self.draft:
                    strokes.append(self.draft)
                # Preserve the wipe clip when drawing normalized strokes.
                painter.save()
                if self.mode == "wipe":
                    clip = painter.clipBoundingRect()
                    painter.setClipRect(clip.intersected(rect))
                paint_strokes(painter, rect, strokes)
                painter.restore()
            painter.restore()
        if self.mode == "side":
            painter.setPen(QPen(QColor("#303945"), 2)); painter.drawLine(self.width() // 2, 0, self.width() // 2, self.height())
        if self.mode == "wipe":
            x = round(self.width() * self.wipe)
            painter.setPen(QPen(QColor("#94c7ff"), 2)); painter.drawLine(x, 0, x, self.height())
            painter.setBrush(QColor("#94c7ff")); painter.drawEllipse(QPointF(x, self.height() / 2), 6, 18)
        painter.setFont(QFont("Inter", 9))
        for slot in slots:
            area = self.area(slot)
            x = area.left() + 12 if slot == "A" or self.mode != "wipe" else self.width() - 230
            label = self.labels[slot][:65]
            painter.fillRect(QRectF(x, 10, min(450, area.width() - 24), 24), QColor(12, 16, 22, 205))
            painter.setPen(QColor("#aecff0")); painter.drawText(QPointF(x + 8, 27), label)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.interaction.emit()
        if not self.painting and self.mode == "wipe":
            self.drag_wipe = True
            self.wipe = max(0, min(1, event.position().x() / self.width())); self.update(); return
        slot = self.mode if self.mode in ("A", "B") else ("A" if event.position().x() < self.width() * (.5 if self.mode == "side" else self.wipe) else "B")
        self.target_changed.emit(slot)
        rect = self.image_rect(slot)
        if self.painting and not self.images[slot].isNull() and rect.contains(event.position()):
            self.draft_slot = slot
            self.draft = Stroke([self.normalized(event.position(), rect)], self.brush_color, min(.2, self.brush_width / rect.width()))
            self.update()

    @staticmethod
    def normalized(point, rect):
        return [max(0, min(1, (point.x() - rect.x()) / rect.width())), max(0, min(1, (point.y() - rect.y()) / rect.height()))]

    def mouseMoveEvent(self, event):
        if self.drag_wipe:
            self.wipe = max(0, min(1, event.position().x() / self.width())); self.update()
        elif self.draft:
            self.draft.points.append(self.normalized(event.position(), self.image_rect(self.draft_slot)))
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.drag_wipe = False
        if self.draft:
            slot, stroke = self.draft_slot, self.draft
            self.draft = self.draft_slot = None
            self.stroke_added.emit(slot, stroke)
            self.update()
