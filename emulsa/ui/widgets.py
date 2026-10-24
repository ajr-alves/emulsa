"""Small custom widgets: the photo canvas, sliders, collapsible sections and the assistant bubble."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractButton, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QPushButton, QSlider, QToolButton,
                               QVBoxLayout, QWidget)

from . import icons, theme


class PreviewView(QWidget):
    """The photo canvas. Fits the photo by default; zoom with the wheel, a trackpad pinch or a double-click,
    drag to look around. When zoomed in past the preview's own resolution it asks (``detail_needed``)
    for a full-resolution tile of the visible area, which is painted over the preview.
    Shows the original instead of the graded image while ``show_original`` is on."""
    files_dropped = Signal(list)
    open_photos = Signal()
    open_folder = Signal()
    zoom_changed = Signal(object)          # None for fit, else 1.0 = 100 %
    detail_needed = Signal(QRectF, float)  # visible area in 0..1 image coords, full-image px per screen px

    MAX_ZOOM = 8.0
    MARGIN = 28

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumSize(320, 240)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.graded: QImage | None = None
        self.original: QImage | None = None
        self.tile = None                   # (QRectF normalised area, graded QImage, original QImage)
        self.full_size = None              # (w, h) of the full-resolution photo
        self.show_original = False
        self.busy = False
        self.dragging = False
        self.zoom = None                   # None = fit to window
        self.center = QPointF(0.5, 0.5)
        self._pan_from = None
        self.title = "Drop photos or a folder here"
        self.message = "JPEG, PNG, TIFF and RAW files work."
        self.badge_until = 0
        self.photos_btn = QPushButton("Choose photos", self)
        self.photos_btn.setObjectName("secondary")
        self.photos_btn.clicked.connect(self.open_photos.emit)
        self.folder_btn = QPushButton("Choose a folder", self)
        self.folder_btn.setObjectName("primary")
        self.folder_btn.clicked.connect(self.open_folder.emit)
        for b in (self.photos_btn, self.folder_btn):
            b.setCursor(Qt.PointingHandCursor)
        self._sync_empty_buttons()

    # ------------------------------------------------------------------ content
    def set_images(self, graded: QImage | None = None, original: QImage | None = None):
        if graded is not None:
            self.graded = graded
        if original is not None:
            self.original = original
        self._sync_empty_buttons()
        self.update()

    def set_photo(self, original: QImage, full_size):
        """A new photo: reset the view to fit and forget any detail tile."""
        self.original, self.graded, self.tile = original, None, None
        self.full_size = full_size if full_size and full_size[0] > 0 else (original.width(), original.height())
        self.zoom, self.center = None, QPointF(0.5, 0.5)
        self.zoom_changed.emit(None)
        self._sync_empty_buttons()
        self.update()

    def set_tile(self, tile):
        self.tile = tile
        self.update()

    def clear(self, title: str, message: str = ""):
        self.graded = self.original = self.tile = None
        self.full_size = None
        self.zoom = None
        self.title, self.message = title, message
        self._sync_empty_buttons()
        self.update()

    def set_show_original(self, on: bool):
        self.show_original = on
        self.update()

    # ------------------------------------------------------------------ geometry
    def _dims(self):
        fw, fh = self.full_size or (self.original.width(), self.original.height())
        return float(fw), float(fh)

    def fit_scale(self) -> float:
        fw, fh = self._dims()
        area = self.rect().adjusted(self.MARGIN, self.MARGIN, -self.MARGIN, -self.MARGIN)
        return max(1e-6, min(area.width() / fw, area.height() / fh))

    def scale(self) -> float:
        """Screen (logical) px per full-image px."""
        if self.zoom is None:
            return self.fit_scale()
        return self.zoom / max(self.devicePixelRatioF(), 1.0)

    def image_rect(self) -> QRectF:
        fw, fh = self._dims()
        s = self.scale()
        w, h = fw * s, fh * s
        if self.zoom is None:
            return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)
        x = self.width() / 2 - self.center.x() * w
        y = self.height() / 2 - self.center.y() * h
        return QRectF(x, y, w, h)

    def _clamp_center(self):
        fw, fh = self._dims()
        s = self.scale()
        w, h = fw * s, fh * s
        cx, cy = self.center.x(), self.center.y()
        hx = self.width() / 2 / w if w else 0.5
        hy = self.height() / 2 / h if h else 0.5
        cx = 0.5 if w <= self.width() else min(max(cx, hx), 1 - hx)
        cy = 0.5 if h <= self.height() else min(max(cy, hy), 1 - hy)
        self.center = QPointF(cx, cy)

    def visible_area(self) -> QRectF:
        r = self.image_rect()
        vis = r.intersected(QRectF(self.rect()))
        if r.width() <= 0 or vis.isEmpty():
            return QRectF(0, 0, 1, 1)
        return QRectF((vis.x() - r.x()) / r.width(), (vis.y() - r.y()) / r.height(),
                      vis.width() / r.width(), vis.height() / r.height())

    def set_zoom(self, zoom, anchor: QPointF | None = None):
        """zoom: None to fit, else 1.0 = 100 %. anchor: the widget point that stays still."""
        if self.original is None:
            return
        fit_zoom = self.fit_scale() * max(self.devicePixelRatioF(), 1.0)
        if zoom is not None:
            zoom = min(self.MAX_ZOOM, zoom)
            if zoom <= fit_zoom * 1.001:
                zoom = None
        if anchor is not None and zoom is not None:
            r = self.image_rect()
            nx = (anchor.x() - r.x()) / r.width()
            ny = (anchor.y() - r.y()) / r.height()
            old_zoom = self.zoom
            self.zoom = zoom
            fw, fh = self._dims()
            s = self.scale()
            # keep the image point under the anchor where it is
            self.center = QPointF(nx - (anchor.x() - self.width() / 2) / (fw * s),
                                  ny - (anchor.y() - self.height() / 2) / (fh * s))
            if old_zoom is None and not (0 <= nx <= 1 and 0 <= ny <= 1):
                self.center = QPointF(0.5, 0.5)
        else:
            self.zoom = zoom
        self._clamp_center()
        import time
        self.badge_until = time.monotonic() + 1.2
        QTimer.singleShot(1250, self.update)
        self.zoom_changed.emit(self.zoom)
        self._request_detail()
        self.update()

    def current_zoom(self) -> float:
        return self.scale() * max(self.devicePixelRatioF(), 1.0)

    def _request_detail(self):
        if self.original is None:
            return
        fw, _ = self._dims()
        preview_px_per_full_px = self.original.width() / fw
        screen_px_per_full_px = self.current_zoom()
        if screen_px_per_full_px > preview_px_per_full_px * 1.05:
            self.detail_needed.emit(self.visible_area(), screen_px_per_full_px)

    # ------------------------------------------------------------------ painting
    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), theme.qc("canvas"))
        img = self.original if (self.show_original and self.original is not None) else self.graded or self.original
        if img is None:
            self._empty(p)
            return
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        target = self.image_rect()
        self._draw_part(p, img, target, QRectF(0, 0, 1, 1))
        if self.tile is not None and self.zoom is not None:
            area, graded, original = self.tile
            tile_img = original if self.show_original else graded
            if tile_img is not None:
                self._draw_part(p, tile_img, target, area)
        if self.show_original:
            self._badge(p, QPointF(14, 14), "Original")
        import time
        if time.monotonic() < self.badge_until:
            text = "Fit" if self.zoom is None else f"{round(self.current_zoom() * 100)}%"
            self._badge(p, QPointF(14, self.height() - 40), text)

    def _draw_part(self, p, img, target: QRectF, area: QRectF):
        """Draw ``img`` (which shows the normalised ``area`` of the photo) where it belongs inside ``target``,
        only the part that is on screen."""
        dest = QRectF(target.x() + area.x() * target.width(), target.y() + area.y() * target.height(),
                      area.width() * target.width(), area.height() * target.height())
        vis = dest.intersected(QRectF(self.rect()))
        if vis.isEmpty() or dest.width() <= 0:
            return
        sx = img.width() / dest.width()
        sy = img.height() / dest.height()
        src = QRectF((vis.x() - dest.x()) * sx, (vis.y() - dest.y()) * sy, vis.width() * sx, vis.height() * sy)
        p.drawImage(vis, img, src)

    def _empty_box(self) -> QRectF:
        r = self.rect()
        return QRectF(r.center().x() - 190, r.center().y() - 110, 380, 220)

    def _empty(self, p: QPainter):
        box = self._empty_box()
        pen = QPen(theme.qc("accent" if self.dragging else "faint"), 1.5, Qt.DashLine)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(pen)
        p.setBrush(theme.qc("accent_soft") if self.dragging else Qt.NoBrush)
        p.drawRoundedRect(box, 14, 14)
        icons.icon("image", 28, "faint").paint(p, int(box.center().x() - 14), int(box.y() + 30), 28, 28)
        f = QFont(self.font()); f.setPointSizeF(f.pointSizeF() + 2); f.setBold(True)
        p.setFont(f); p.setPen(theme.qc("text"))
        p.drawText(QRectF(box.x(), box.y() + 68, box.width(), 26), Qt.AlignCenter, self.title)
        p.setFont(self.font()); p.setPen(theme.qc("muted"))
        p.drawText(QRectF(box.x() + 20, box.y() + 96, box.width() - 40, 40), Qt.AlignHCenter | Qt.TextWordWrap, self.message)

    def _sync_empty_buttons(self):
        empty = self.original is None and self.graded is None
        for b in (self.photos_btn, self.folder_btn):
            b.setVisible(empty)
        if empty:
            box = self._empty_box()
            self.photos_btn.adjustSize(); self.folder_btn.adjustSize()
            gap = 10
            total = self.photos_btn.width() + gap + self.folder_btn.width()
            x = int(box.center().x() - total / 2)
            y = int(box.bottom() - 56)
            self.photos_btn.move(x, y)
            self.folder_btn.move(x + self.photos_btn.width() + gap, y)
        self.setCursor(Qt.PointingHandCursor if empty else Qt.ArrowCursor)

    def resizeEvent(self, e):
        self._sync_empty_buttons()
        if self.zoom is not None:
            self._clamp_center()
            self._request_detail()
        super().resizeEvent(e)

    def _badge(self, p, at: QPointF, text):
        f = QFont(self.font()); f.setBold(True)
        p.setFont(f)
        w = max(64, p.fontMetrics().horizontalAdvance(text) + 24)
        r = QRectF(at.x(), at.y(), w, 26)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 140))
        p.drawRoundedRect(r, 13, 13)
        p.setPen(QColor("#ffffff"))
        p.drawText(r, Qt.AlignCenter, text)

    # ------------------------------------------------------------------ mouse, wheel, pinch
    def mousePressEvent(self, e):
        if self.original is None:
            if e.button() == Qt.LeftButton and self._empty_box().contains(e.position()):
                self.open_folder.emit()
            return
        if e.button() == Qt.LeftButton and self.zoom is not None:
            self._pan_from = (e.position(), QPointF(self.center))
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        if self._pan_from is not None:
            start, c0 = self._pan_from
            r = self.image_rect()
            d = e.position() - start
            self.center = QPointF(c0.x() - d.x() / r.width(), c0.y() - d.y() / r.height())
            self._clamp_center()
            self.update()
        elif self.original is not None:
            self.setCursor(Qt.OpenHandCursor if self.zoom is not None else Qt.ArrowCursor)

    def mouseReleaseEvent(self, e):
        if self._pan_from is not None:
            self._pan_from = None
            self.setCursor(Qt.OpenHandCursor)
            self._request_detail()

    def mouseDoubleClickEvent(self, e):
        if self.original is None:
            return
        self.set_zoom(None if self.zoom is not None else 1.0, e.position())

    def wheelEvent(self, e):
        if self.original is None:
            return
        steps = e.angleDelta().y() / 120.0 or e.pixelDelta().y() / 60.0
        if not steps:
            return
        self.set_zoom(self.current_zoom() * (1.25 ** steps), e.position())
        e.accept()

    def event(self, e):
        if e.type() == QEvent.NativeGesture and self.original is not None:
            if e.gestureType() == Qt.ZoomNativeGesture:
                self.set_zoom(self.current_zoom() * (1.0 + e.value()), e.position())
                return True
            if e.gestureType() == Qt.SmartZoomNativeGesture:
                self.set_zoom(None if self.zoom is not None else 1.0, e.position())
                return True
        return super().event(e)

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
