"""Zoom geometry of the photo view: fit, 100%, anchoring and panning limits."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class ZoomTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from emulsa.ui import theme
        theme.apply("light")

    def make(self):
        from emulsa.ui.widgets import PreviewView
        v = PreviewView()
        v.resize(800, 600)
        img = QImage(1200, 800, QImage.Format_RGB888)
        img.fill(0x808080)
        v.set_photo(img, (6000, 4000))
        return v

    def test_starts_at_fit(self):
        v = self.make()
        self.assertIsNone(v.zoom)
        self.assertAlmostEqual(v.scale(), v.fit_scale())

    def test_100_percent_is_full_resolution(self):
        v = self.make()
        v.set_zoom(1.0)
        dpr = v.devicePixelRatioF()
        # one full-resolution pixel per physical screen pixel
        self.assertAlmostEqual(v.image_rect().width() * dpr, 6000, delta=1)

    def test_anchor_point_stays_put(self):
        v = self.make()
        anchor = QPointF(600, 200)
        r0 = v.image_rect()
        u = ((anchor.x() - r0.x()) / r0.width(), (anchor.y() - r0.y()) / r0.height())
        v.set_zoom(0.5, anchor)
        r1 = v.image_rect()
        self.assertAlmostEqual(r1.x() + u[0] * r1.width(), anchor.x(), delta=1.5)
        self.assertAlmostEqual(r1.y() + u[1] * r1.height(), anchor.y(), delta=1.5)

    def test_pan_is_clamped_to_photo(self):
        v = self.make()
        v.set_zoom(1.0)
        v.center = QPointF(-5, 9)
        v._clamp_center()
        area = v.visible_area()
        self.assertGreaterEqual(area.left(), -1e-6)
        self.assertLessEqual(area.bottom(), 1 + 1e-6)

    def test_zoom_is_limited(self):
        v = self.make()
        v.set_zoom(1000)
        self.assertLessEqual(v.zoom, v.MAX_ZOOM)


if __name__ == "__main__":
    unittest.main()
