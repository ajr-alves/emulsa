"""Background jobs so the window never freezes while images load or render."""
from __future__ import annotations

import traceback

import numpy as np
from PySide6.QtCore import QObject, QRectF, QRunnable, Signal
from PySide6.QtGui import QImage

from .. import imageio
from ..engine import bake_lut, render


def to_qimage(arr: np.ndarray) -> QImage:
    a = np.ascontiguousarray((np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8))
    h, w = a.shape[:2]
    return QImage(a.data, w, h, 3 * w, QImage.Format_RGB888).copy()


def pil_to_qimage(img) -> QImage:
    img = img.convert("RGB")
    data = img.tobytes()
    return QImage(data, img.width, img.height, 3 * img.width, QImage.Format_RGB888).copy()


class Signals(QObject):
    done = Signal(object, object)    # (key, result)
    failed = Signal(object, object)  # (key, exception)


class Job(QRunnable):
    """Runs ``fn()`` on the thread pool and reports back with a key."""

    def __init__(self, key, fn):
        super().__init__()
        self.key, self.fn = key, fn
        self.signals = Signals()
        self.setAutoDelete(True)

    def run(self):
        try:
            result = self.fn()
        except Exception as exc:  # report, never crash the pool
            traceback.print_exc()
            self._emit(self.signals.failed, exc)
            return
        self._emit(self.signals.done, result)

    def _emit(self, signal, value):
        try:
            signal.emit(self.key, value)
        except RuntimeError:  # whoever asked has gone (the window closed while this ran); nothing to report to
            pass


def thumbnail_job(path: str, size: int) -> Job:
    return Job(path, lambda: pil_to_qimage(imageio.load_thumbnail(path, size)))


def preview_job(path: str) -> Job:
    return Job(path, lambda: imageio.load_preview(path))


def render_job(token: int, img: np.ndarray, params: dict, strength: float, scale: float) -> Job:
    return Job(token, lambda: to_qimage(render(img, params, strength=strength, scale=scale)))


def detail_job(token, full_u8, area, screen_per_full, params, strength) -> Job:
    """Grade the visible part of the full-resolution photo for zooming. ``area`` is (x, y, w, h) in 0..1."""
    def run():
        h, w = full_u8.shape[:2]
        x0, y0, aw, ah = area
        # a little margin so small pans don't show the blurry preview at the edges
        mx, my = aw * 0.15, ah * 0.15
        x0, y0 = max(0.0, x0 - mx), max(0.0, y0 - my)
        x1, y1 = min(1.0, x0 + aw + 2 * mx), min(1.0, y0 + ah + 2 * my)
        px0, py0, px1, py1 = int(x0 * w), int(y0 * h), max(int(x0 * w) + 1, int(round(x1 * w))), max(int(y0 * h) + 1, int(round(y1 * h)))
        crop = full_u8[py0:py1, px0:px1]
        if screen_per_full < 1.0:   # zoomed in, but still below 100 %: no need for every pixel
            from PIL import Image
            img = Image.fromarray(crop)
            img = img.resize((max(1, round(crop.shape[1] * screen_per_full)), max(1, round(crop.shape[0] * screen_per_full))),
                             Image.LANCZOS)
            crop = np.asarray(img)
        arr = crop.astype(np.float32) / 255.0
        graded = render(arr, params, strength=strength, scale=min(1.0, screen_per_full))
        real = QRectF(px0 / w, py0 / h, (px1 - px0) / w, (py1 - py0) / h)
        return real, to_qimage(graded), to_qimage(arr)
    return Job(token, run)


def look_icons_job(token: int, img: np.ndarray, looks: list[dict]) -> Job:
    def run():
        out = {}
        for look in looks:
            out[look["id"]] = to_qimage(render(img, look["params"], scale=0.1, lut=bake_lut(look["params"], 17)))
        return out
    return Job(token, run)
