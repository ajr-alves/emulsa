"""Small custom widgets: the photo preview and labelled adjustment sliders."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

from . import theme


class PreviewView(QWidget):
    """Shows the graded photo fitted to the space. Hold the Before button or the \\ key for the original."""
    files_dropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumSize(320, 240)
        self.setFocusPolicy(Qt.StrongFocus)
        self.graded: QImage | None = None
        self.original: QImage | None = None
        self.show_original = False
        self.busy = False
        self.message = "Open a folder or drop photos here"

    def set_images(self, graded: QImage | None = None, original: QImage | None = None):
        if graded is not None:
            self.graded = graded
        if original is not None:
            self.original = original
        self.update()

    def clear(self, message: str):
        self.graded = self.original = None
        self.message = message
        self.update()

    def set_show_original(self, on: bool):
        self.show_original = on
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.BG))
        img = self.original if (self.show_original and self.original is not None) else self.graded or self.original
        if img is None:
            p.setPen(QColor(theme.MUTED))
            f = QFont(self.font()); f.setPointSize(f.pointSize() + 2)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignCenter, self.message)
            return
        margin = 24
        area = self.rect().adjusted(margin, margin, -margin, -margin)
        s = min(area.width() / img.width(), area.height() / img.height())
        w, h = img.width() * s, img.height() * s
        target = QRectF(area.x() + (area.width() - w) / 2, area.y() + (area.height() - h) / 2, w, h)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.drawImage(target, img)
        if self.show_original:
            self._badge(p, target, "Before")
        elif self.busy:
            self._badge(p, target, "Rendering…")

    def _badge(self, p, target, text):
        f = QFont(self.font()); f.setBold(True)
        p.setFont(f)
        r = QRectF(target.x() + 12, target.y() + 12, 110, 26)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 150))
        p.drawRoundedRect(r, 5, 5)
        p.setPen(QPen(QColor(theme.TEXT)))
        p.drawText(r, Qt.AlignCenter, text)

    # drag and drop of files or folders
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)


class AdjustSlider(QWidget):
    """A label, a value readout and a slider. Double-click the slider to go back to the look's value."""
    changed = Signal(str, float)

    def __init__(self, key: str, label: str, lo: float, hi: float, step: float, fmt: str = "{:+.2f}", parent=None):
        super().__init__(parent)
        self.key, self.lo, self.step, self.fmt = key, lo, step, fmt
        self.default = 0.0
        self.name = QLabel(label)
        self.value_label = QLabel()
        self.value_label.setObjectName("hint")
        self.value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, round((hi - lo) / step))
        self.slider.setAccessibleName(label)
        self.slider.valueChanged.connect(self._moved)
        self.slider.mouseDoubleClickEvent = lambda e: self.set_value(self.default, emit=True)
        top = QHBoxLayout(); top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(self.name); top.addStretch(1); top.addWidget(self.value_label)
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 2, 0, 2); lay.setSpacing(2)
        lay.addLayout(top); lay.addWidget(self.slider)
        self._quiet = False

    def value(self) -> float:
        return self.lo + self.slider.value() * self.step

    def set_value(self, v: float, emit: bool = False):
        self._quiet = not emit
        self.slider.setValue(round((v - self.lo) / self.step))
        self._quiet = False
        self.value_label.setText(self.fmt.format(self.value()))

    def _moved(self, _):
        self.value_label.setText(self.fmt.format(self.value()))
        if not self._quiet:
            self.changed.emit(self.key, self.value())
