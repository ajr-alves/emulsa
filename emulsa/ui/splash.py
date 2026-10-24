"""Startup animation: the e develops grain by grain, like a print coming up in the developer tray,
then the wordmark slides in. About 1.4 seconds; a click or any key skips it, and it can be turned off
in the ••• menu (Startup animation)."""
from __future__ import annotations

import math
import random

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication, QWidget

from . import logo_data, theme

DURATION = 1.45      # seconds until the window hands over
FADE = 0.22          # fade-out at the end
W, H = 500, 220
ICON = 132           # icon size in px


def _ease_out_back(t: float) -> float:
    c1, c3 = 1.4, 2.4
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def _smooth(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(round(a.red() + (b.red() - a.red()) * t), round(a.green() + (b.green() - a.green()) * t),
                  round(a.blue() + (b.blue() - a.blue()) * t))


class Splash(QWidget):
    handover = Signal()   # time to show the main window (the splash fades out on top of it)
    finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(W, H)
        self.setAccessibleName("Emulsa is starting")
        self.setCursor(Qt.PointingHandCursor)
        self.clock = QElapsedTimer()
        self.timer = QTimer(self, interval=16, timeout=self._tick)
        self.t = 0.0
        self.running = False
        self.done = False
        self.handed = False
        # only decides when each grain appears in the animation, nothing security-related
        rnd = random.Random(11)  # nosec B311
        # each grain develops a little after the one to its left, with some randomness, as developer washes over
        self.grains = []
        for x, y, r in logo_data.GRAINS:
            delay = 0.08 + 0.42 * ((x - 15) / 70) * 0.7 + rnd.uniform(0, 0.25)
            self.grains.append((x, y, r, delay))
        self.specks = [(x, y, r, rnd.uniform(0.3, 0.9)) for x, y, r in logo_data.SPECKS]
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.center().x() - W // 2, screen.center().y() - H // 2)

    # ------------------------------------------------------------------ control
    def start(self):
        """Begin the animation. Call once the main window has been built, so nothing stalls it."""
        self.running = True
        self.clock.start()
        self.timer.start()

    def skip(self):
        if not self.done:
            self.t = DURATION + FADE
            self._finish()

    def mousePressEvent(self, e):
        self.skip()

    def keyPressEvent(self, e):
        self.skip()

    def _tick(self):
        self.t = self.clock.elapsed() / 1000.0
        if self.t >= DURATION and not self.handed:
            self.handed = True
            self.handover.emit()
        if self.t >= DURATION:
            self.setWindowOpacity(max(0.0, 1.0 - (self.t - DURATION) / FADE))
        if self.t >= DURATION + FADE:
            self._finish()
            return
        self.update()

    def _finish(self):
        if self.done:
            return
        self.done = True
        self.timer.stop()
        if not self.handed:
            self.handed = True
            self.handover.emit()
        self.hide()
        self.finished.emit()
        self.deleteLater()

    # ------------------------------------------------------------------ drawing
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self.t if self.running else 0.0
        ink = QColor(logo_data.INK)
        amber = QColor(logo_data.AMBER)
        latent = QColor("#3A2C18")          # undeveloped grain: a dim brown, like an image just appearing

        # the card
        card = QPainterPath()
        card.addRoundedRect(QRectF(0.5, 0.5, W - 1, H - 1), 22, 22)
        p.fillPath(card, QColor("#0F0F0E"))

        # the icon tile
        ox, oy = 36, (H - ICON) / 2
        s = ICON / 100.0
        x0, y0, w0, h0, r0 = logo_data.TILE
        tile_a = _smooth(t / 0.18)
        tile = QPainterPath()
        tile.addRoundedRect(QRectF(ox + x0 * s, oy + y0 * s, w0 * s, h0 * s), r0 * s, r0 * s)
        c = QColor(ink)
        c.setAlphaF(tile_a)
        p.fillPath(tile, c)

        p.setPen(Qt.NoPen)
        for x, y, r, delay in self.specks:
            a = _smooth((t - 0.5 - delay * 0.4) / 0.5) * 0.35
            if a > 0:
                c = QColor(amber)
                c.setAlphaF(a)
                p.setBrush(c)
                p.drawEllipse(QPointF(ox + x * s, oy + y * s), r * s, r * s)
        for x, y, r, delay in self.grains:
            k = (t - delay) / 0.42
            if k <= 0:
                continue
            k = min(1.0, k)
            grow = _ease_out_back(k)
            p.setBrush(_mix(latent, amber, _smooth(k * 1.3)))
            p.drawEllipse(QPointF(ox + x * s, oy + y * s), r * s * grow, r * s * grow)

        # the wordmark slides in once most of the e is there
        k = _smooth((t - 0.78) / 0.42)
        if k > 0:
            f = QFont(theme.DISPLAY_FONT or self.font().family())
            f.setPixelSize(68)
            f.setWeight(QFont.Bold)
            f.setLetterSpacing(QFont.AbsoluteSpacing, -1.8)
            p.setFont(f)
            c = QColor("#F2F1EE")
            c.setAlphaF(k)
            p.setPen(c)
            tx = ox + ICON + 26 + (1 - k) * 18
            p.drawText(QRectF(tx, 0, W - tx - 20, H - 8), Qt.AlignVCenter | Qt.AlignLeft, "emulsa")
        p.end()
