"""Small custom widgets: the photo canvas, sliders, collapsible sections and the assistant bubble."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractButton, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QSlider, QToolButton,
                               QVBoxLayout, QWidget)

from . import icons, theme


class PreviewView(QWidget):
    """The graded photo, fitted to the space. Shows the original while ``show_original`` is on."""
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
        self.dragging = False
        self.title = "Drop photos here"
        self.message = "or open a folder. JPEG, PNG, TIFF and RAW files work."

    def set_images(self, graded: QImage | None = None, original: QImage | None = None):
        if graded is not None:
            self.graded = graded
        if original is not None:
            self.original = original
        self.update()

    def clear(self, title: str, message: str = ""):
        self.graded = self.original = None
        self.title, self.message = title, message
        self.update()

    def set_show_original(self, on: bool):
        self.show_original = on
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), theme.qc("canvas"))
        img = self.original if (self.show_original and self.original is not None) else self.graded or self.original
        if img is None:
            self._empty(p)
            return
        margin = 28
        area = self.rect().adjusted(margin, margin, -margin, -margin)
        s = min(area.width() / img.width(), area.height() / img.height())
        w, h = img.width() * s, img.height() * s
        target = QRectF(area.x() + (area.width() - w) / 2, area.y() + (area.height() - h) / 2, w, h)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.drawImage(target, img)
        if self.show_original:
            self._badge(p, target, "Original")

    def _empty(self, p: QPainter):
        r = self.rect().adjusted(40, 40, -40, -40)
        box = QRectF(r.center().x() - 170, r.center().y() - 90, 340, 180)
        pen = QPen(theme.qc("accent" if self.dragging else "faint"), 1.5, Qt.DashLine)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(box, 14, 14)
        icons.icon("image", 28, "faint").paint(p, int(box.center().x() - 14), int(box.y() + 34), 28, 28)
        f = QFont(self.font()); f.setPointSizeF(f.pointSizeF() + 2); f.setBold(True)
        p.setFont(f); p.setPen(theme.qc("text"))
        p.drawText(QRectF(box.x(), box.y() + 74, box.width(), 26), Qt.AlignCenter, self.title)
        p.setFont(self.font()); p.setPen(theme.qc("muted"))
        p.drawText(QRectF(box.x() + 20, box.y() + 102, box.width() - 40, 50), Qt.AlignHCenter | Qt.TextWordWrap, self.message)

    def _badge(self, p, target, text):
        f = QFont(self.font()); f.setBold(True)
        p.setFont(f)
        r = QRectF(target.x() + 12, target.y() + 12, 84, 26)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 140))
        p.drawRoundedRect(r, 13, 13)
        p.setPen(QColor("#ffffff"))
        p.drawText(r, Qt.AlignCenter, text)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            self.dragging = True
            self.update()
            e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self.dragging = False
        self.update()

    def dropEvent(self, e):
        self.dragging = False
        self.update()
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)


class AdjustSlider(QWidget):
    """Label and value on one line, slider below. Double-click the slider to return to the look's value."""
    changed = Signal(str, float)

    def __init__(self, key: str, label: str, lo: float, hi: float, step: float, fmt: str = "{:+.2f}", parent=None):
        super().__init__(parent)
        self.key, self.lo, self.step, self.fmt = key, lo, step, fmt
        self.default = 0.0
        self.name = QLabel(label)
        self.value_label = QLabel()
        self.value_label.setObjectName("subtle")
        self.value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, round((hi - lo) / step))
        self.slider.setAccessibleName(label)
        self.slider.setToolTip("Double-click to reset")
        self.slider.valueChanged.connect(self._moved)
        self.slider.mouseDoubleClickEvent = lambda e: self.set_value(self.default, emit=True)
        top = QHBoxLayout(); top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(self.name); top.addStretch(1); top.addWidget(self.value_label)
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 3, 0, 3); lay.setSpacing(3)
        lay.addLayout(top); lay.addWidget(self.slider)
        self._quiet = False

    def value(self) -> float:
        return self.lo + self.slider.value() * self.step

    def set_value(self, v: float, emit: bool = False):
        self._quiet = not emit
        self.slider.setValue(round((v - self.lo) / self.step))
        self._quiet = False
        self._update_label()

    def _update_label(self):
        self.value_label.setText(self.fmt.format(self.value()))
        changed = abs(self.value() - self.default) > self.step / 2
        self.name.setStyleSheet(f"color: {theme.c('accent')};" if changed else "")

    def _moved(self, _):
        self._update_label()
        if not self._quiet:
            self.changed.emit(self.key, self.value())


class Section(QWidget):
    """A titled group that folds away, like a Notion toggle."""

    def __init__(self, title: str, parent=None, expanded: bool = True):
        super().__init__(parent)
        self.head = QToolButton()
        self.head.setObjectName("section")
        self.head.setText(title)
        self.head.setCheckable(True)
        self.head.setChecked(expanded)
        self.head.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.head.setIconSize(QSize(14, 14))
        self.head.toggled.connect(self._toggle)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 6)
        self.body_layout.setSpacing(2)
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        lay.addWidget(self.head); lay.addWidget(self.body)
        self._toggle(expanded)

    def add(self, w: QWidget):
        self.body_layout.addWidget(w)

    def _toggle(self, on: bool):
        self.body.setVisible(on)
        self.head.setIcon(icons.icon("chevron-down" if on else "chevron-right", 14))

    def refresh_icons(self):
        self._toggle(self.head.isChecked())


class AssistantBubble(QAbstractButton):
    """The round button in the corner of the photo that opens the look assistant."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(52, 52)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Look assistant: describe a look or show a reference photo")
        self.setAccessibleName("Open the look assistant")
        self.setCheckable(True)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18); shadow.setOffset(0, 3); shadow.setColor(QColor(0, 0, 0, 70))
        self.setGraphicsEffect(shadow)

    def sizeHint(self):
        return QSize(52, 52)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(3, 3, self.width() - 6, self.height() - 6)
        p.setPen(Qt.NoPen)
        p.setBrush(theme.qc("accent") if not self.underMouse() else theme.qc("accent").lighter(108))
        p.drawEllipse(r)
        name = "close" if self.isChecked() else "sparkle"
        icons.icon(name, 22, theme.c("accent_text")).paint(p, int(r.center().x() - 11), int(r.center().y() - 11), 22, 22)
        if self.hasFocus():
            p.setPen(QPen(theme.qc("text"), 2)); p.setBrush(Qt.NoBrush)
            p.drawEllipse(r.adjusted(-2, -2, 2, 2))

    def enterEvent(self, e):
        self.update()

    def leaveEvent(self, e):
        self.update()
