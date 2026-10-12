"""Frame-bound review notes, exports and portable review documents (media stays external)."""
from dataclasses import dataclass, field, asdict
from io import BytesIO
import json
from pathlib import Path
import re
import tempfile
import zipfile
from xml.sax.saxutils import escape

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QPointF, Qt
from PySide6.QtGui import QImage, QPainter, QPen, QColor, QPainterPath

MAX_SNAPSHOTS = 256 * 1024**2


def png_bytes(image):
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise ValueError("Could not capture this review frame.")
    return bytes(data)


@dataclass
class Stroke:
    points: list
    color: str = "#ff4b55"
    width: float = .004


@dataclass
class Annotation:
    source: str
    frame: int
    label: str
    context: str
    png: bytes = b""
    strokes: list = field(default_factory=list)
    note: str = ""

    @property
    def key(self):
        return self.source, self.frame

    @property
    def active(self):
        return bool(self.strokes or self.note.strip())


def paint_strokes(painter, rect, strokes):
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setClipRect(rect, Qt.ClipOperation.IntersectClip)
    for stroke in strokes:
        if not stroke.points:
            continue
        pen = QPen(QColor(stroke.color), max(1.0, stroke.width * rect.width()), Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        points = [QPointF(rect.x() + x * rect.width(), rect.y() + y * rect.height()) for x, y in stroke.points]
        if len(points) == 1:
            painter.drawPoint(points[0])
        else:
            path = QPainterPath(points[0])
            for point in points[1:]:
                path.lineTo(point)
            painter.drawPath(path)
    painter.restore()


def render_annotation(annotation):
    image = QImage.fromData(annotation.png).convertToFormat(QImage.Format.Format_RGB32)
    if image.isNull():
        raise ValueError("Review snapshot is missing or invalid.")
    painter = QPainter(image)
    paint_strokes(painter, image.rect(), annotation.strokes)
    painter.end()
    return image


class ReviewDocument:
    def __init__(self):
        self.entries = {}
        self.dirty = False
        self.path = None

    def active(self):
        return [entry for entry in self.entries.values() if entry.active]

    def ensure(self, source, frame, label, context, image):
        key = (source, frame)
        if key not in self.entries:
            png = png_bytes(image)
            if sum(len(entry.png) for entry in self.entries.values()) + len(png) > MAX_SNAPSHOTS:
                raise ValueError("Review snapshots reached 256 MiB. Save this review and start a new review document.")
            self.entries[key] = Annotation(source, frame, label, context, png)
        return self.entries[key]

    def remove_empty(self, key):
        if key in self.entries and not self.entries[key].active:
            del self.entries[key]

    def save(self, path, state):
        path = Path(path)
        manifest = {"format": "FRM review", "version": 1, "state": state, "annotations": []}
        handle = tempfile.NamedTemporaryFile(prefix=".frm-review-", suffix=".tmp", dir=path.parent, delete=False)
        temp = Path(handle.name)
        handle.close()
        try:
            with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for i, entry in enumerate(self.active()):
                    record = {"source": entry.source, "frame": entry.frame, "label": entry.label,
                              "context": entry.context, "note": entry.note,
                              "strokes": [asdict(stroke) for stroke in entry.strokes], "snapshot": f"frames/{i}.png"}
                    manifest["annotations"].append(record)
                    archive.writestr(record["snapshot"], entry.png)
                archive.writestr("review.json", json.dumps(manifest, ensure_ascii=False))
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)
        self.dirty, self.path = False, path

    @classmethod
    def load(cls, path):
        document = cls()
        with zipfile.ZipFile(path) as archive:
            if sum(item.file_size for item in archive.infolist()) > MAX_SNAPSHOTS + 32 * 1024**2:
                raise ValueError("Review archive exceeds the supported size.")
            payload = json.loads(archive.read("review.json"))
            if payload.get("format") != "FRM review" or payload.get("version") != 1:
                raise ValueError("Unsupported FRM review format.")
            for record in payload["annotations"]:
                frame = record["frame"]
                if not isinstance(frame, int) or frame < 0:
                    raise ValueError("Invalid annotation frame.")
                png = archive.read(record["snapshot"])
                image = QImage.fromData(png)
                if image.isNull() or image.width() * image.height() > 100_000_000:
                    raise ValueError("Invalid review snapshot.")
                strokes = []
                for stroke in record["strokes"]:
                    if not QColor(stroke["color"]).isValid() or not 0 < stroke["width"] <= .2:
                        raise ValueError("Invalid annotation brush.")
                    for point in stroke["points"]:
                        if len(point) != 2 or not all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in point):
                            raise ValueError("Invalid annotation coordinates.")
                    strokes.append(Stroke(**stroke))
                entry = Annotation(record["source"], frame, record["label"], record["context"], png, strokes, record["note"])
                document.entries[entry.key] = entry
        document.path = Path(path)
        return document, payload["state"]

    def export_images(self, folder, extension):
        # Always create a fresh directory: never overwrite unrelated review exports.
        if extension not in ("png", "jpg"):
            raise ValueError("Choose PNG or JPG.")
        target = Path(tempfile.mkdtemp(prefix="FRM-review-", dir=folder))
        manifest = []
        for number, entry in enumerate(self.active(), 1):
            name = re.sub(r"[^\w.-]+", "_", Path(entry.source).stem)[:80]
            filename = f"{number:04d}_{name}_frame-{entry.frame + 1:06d}.{extension}"
            if not render_annotation(entry).save(str(target / filename), extension.upper(), 95):
                raise OSError(f"Could not write {filename}")
            manifest.append({"image": filename, "source": entry.source, "frame_index": entry.frame,
                             "label": entry.label, "context": entry.context, "note": entry.note})
        (target / "notes.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        return target

    def export_pdf(self, path):
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak
        font = "FRMInter"
        if font not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(font, str(Path(__file__).parent / "assets" / "Inter.ttf")))
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle("FRMTitle", fontName=font, fontSize=20, leading=26, textColor=colors.HexColor("#142234")))
        styles.add(ParagraphStyle("FRMBody", fontName=font, fontSize=10, leading=15, spaceAfter=8, splitLongWords=True))
        styles.add(ParagraphStyle("FRMMeta", parent=styles["FRMBody"], fontSize=8, leading=12, textColor=colors.HexColor("#576574")))
        story = []
        entries = self.active()
        for number, entry in enumerate(entries, 1):
            if number > 1:
                story.append(PageBreak())
            story.extend([Paragraph("FRM / Review notes", styles["FRMTitle"]), Spacer(1, 14),
                          Paragraph(f"{number:02d} / {escape(entry.label)}", styles["FRMBody"]),
                          Paragraph(escape(entry.source), styles["FRMMeta"]),
                          Paragraph(escape(entry.context), styles["FRMMeta"])])
            image = render_annotation(entry)
            scale = min(499 / image.width(), 330 / image.height())
            story.extend([Image(BytesIO(png_bytes(image)), width=image.width() * scale, height=image.height() * scale),
                          Spacer(1, 18), Paragraph("Review note", styles["FRMBody"]),
                          Paragraph(escape(entry.note or "Paint annotation only.").replace("\n", "<br/>"), styles["FRMBody"])])
        if not story:
            raise ValueError("No annotated frames to export.")
        def footer(canvas, doc):
            canvas.setFont(font, 8)
            canvas.setFillColor(colors.HexColor("#576574"))
            canvas.drawString(48, 27, "FRM review | Display preview - not source-resolution mastering output")
            canvas.drawRightString(A4[0] - 48, 27, str(doc.page))
        # Atomic replacement prevents a failed export from destroying an existing report.
        path = Path(path)
        handle = tempfile.NamedTemporaryFile(prefix=".frm-report-", suffix=".pdf", dir=path.parent, delete=False)
        temporary = Path(handle.name); handle.close()
        try:
            doc = SimpleDocTemplate(str(temporary), pagesize=A4, leftMargin=48, rightMargin=48,
                topMargin=44, bottomMargin=48, title="FRM review notes", author="FRM")
            doc.build(story, onFirstPage=footer, onLaterPages=footer)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
