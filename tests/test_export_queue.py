"""The export queue and the RAW / JPEG filter."""
import os
import tempfile
import time
import unittest

import numpy as np
from PIL import Image

from emulsa import imageio
from emulsa.exporter import ExportSpec, export_photos, target_path
from emulsa.looks import BUILTIN

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False


def make_photos(folder, n, ext=".jpg"):
    rng = np.random.default_rng(3)
    paths = []
    for i in range(n):
        p = os.path.join(folder, f"photo{i}{ext}")
        Image.fromarray((rng.random((40, 60, 3)) * 255).astype(np.uint8)).save(p, quality=90)
        paths.append(p)
    return paths


def spec_for(files, out_dir, name="Kodak Portra 400"):
    look = next(l for l in BUILTIN if l["name"] == name)
    return ExportSpec(look_name=name, files=files, params=look["params"], strength=1.0, out_dir=out_dir,
                      suffix="_test")


class ExporterTests(unittest.TestCase):
    def test_exports_every_photo_and_reports_progress(self):
        with tempfile.TemporaryDirectory() as d:
            files = make_photos(d, 3)
            out = os.path.join(d, "out"); os.makedirs(out)
            calls = []
            count, errors = export_photos(spec_for(files, out), progress=lambda *a: calls.append(a))
            self.assertEqual((count, errors), (3, []))
            self.assertEqual(sorted(os.listdir(out)), ["photo0_test.jpg", "photo1_test.jpg", "photo2_test.jpg"])
            self.assertEqual(calls[0], (0, 3, "photo0.jpg"))
            self.assertEqual(calls[-1], (3, 3, ""))

    def test_stops_when_asked(self):
        with tempfile.TemporaryDirectory() as d:
            files = make_photos(d, 3)
            out = os.path.join(d, "out"); os.makedirs(out)
            count, _ = export_photos(spec_for(files, out), should_stop=lambda: True)
            self.assertEqual(count, 0)
            self.assertEqual(os.listdir(out), [])

    def test_one_bad_file_does_not_stop_the_rest(self):
        with tempfile.TemporaryDirectory() as d:
            files = make_photos(d, 2)
            bad = os.path.join(d, "broken.jpg")
            with open(bad, "wb") as f:
                f.write(b"not a photo")
            out = os.path.join(d, "out"); os.makedirs(out)
            count, errors = export_photos(spec_for([files[0], bad, files[1]], out))
            self.assertEqual(count, 2)
            self.assertEqual([e[0] for e in errors], ["broken.jpg"])

    def test_target_never_overwrites_or_leaves_the_folder(self):
        with tempfile.TemporaryDirectory() as d:
            first = target_path(d, "/x/a.ARW", "_look", "JPEG")
            open(first, "w").close()
            self.assertTrue(target_path(d, "/x/a.ARW", "_look", "JPEG").endswith("a_look-2.jpg"))
            with self.assertRaises(ValueError):
                target_path(d, "/x/a.ARW", "/../../escape", "JPEG")


class FilterTests(unittest.TestCase):
    FILES = ["/p/a.ARW", "/p/a.JPG", "/p/b.arw", "/p/b.jpeg", "/p/c.png", "/p/d.dng"]

    def test_kinds(self):
        self.assertEqual([imageio.photo_kind(f) for f in self.FILES], ["raw", "jpeg", "raw", "jpeg", "other", "raw"])

    def test_filter(self):
        self.assertEqual(imageio.filter_photos(self.FILES, "raw"), ["/p/a.ARW", "/p/b.arw", "/p/d.dng"])
        self.assertEqual(imageio.filter_photos(self.FILES, "jpeg"), ["/p/a.JPG", "/p/b.jpeg"])
        self.assertEqual(imageio.filter_photos(self.FILES, "all"), self.FILES)

    def test_mixed(self):
        self.assertTrue(imageio.has_raw_and_jpeg(self.FILES))
        self.assertFalse(imageio.has_raw_and_jpeg(["/p/a.jpg", "/p/b.png"]))
        self.assertFalse(imageio.has_raw_and_jpeg(["/p/a.ARW"]))


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class QueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait_until(self, cond, seconds=60):
        end = time.time() + seconds
        while not cond() and time.time() < end:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertTrue(cond(), "timed out")

    def test_jobs_run_in_order_and_cancelled_ones_are_skipped(self):
        from emulsa.ui.export_queue import CANCELLED, DONE, ExportQueue
        with tempfile.TemporaryDirectory() as d:
            files = make_photos(d, 2)
            q = ExportQueue()
            finished = []
            q.job_finished.connect(lambda j: finished.append(j.spec.look_name))
            a = q.add(spec_for(files, os.path.join(d, "a"), "Kodak Portra 400"))
            b = q.add(spec_for(files, os.path.join(d, "b"), "Ilford HP5"))
            c = q.add(spec_for(files, os.path.join(d, "c"), "Velvia"))
            q.cancel(b)                       # still waiting, so it never starts
            self.wait_until(lambda: not q.active_jobs())
            self.assertEqual((a.state, b.state, c.state), (DONE, CANCELLED, DONE))
            self.assertEqual(finished, ["Ilford HP5", "Kodak Portra 400", "Velvia"])
            self.assertEqual(len(os.listdir(os.path.join(d, "a"))), 2)
            self.assertFalse(os.path.exists(os.path.join(d, "b")))
            self.assertEqual(q.photos_left(), 0)
            q.clear_finished()
            self.assertEqual(q.jobs, [])


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class WindowFilterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from emulsa.ui import theme
        theme.apply("light")

    def test_switch_appears_for_raw_plus_jpeg_and_filters_the_strip(self):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as d:
            os.environ["EMULSA_HOME"] = home
            try:
                from emulsa.store import Store
                from emulsa.ui.main_window import MainWindow
                jpgs = make_photos(d, 2)
                raws = [os.path.join(d, f"photo{i}.ARW") for i in range(2)]
                w = MainWindow(Store())
                w.set_files(jpgs + raws)
                self.assertFalse(w.kind_bar.isHidden())
                self.assertEqual(w.kind_btns["raw"].text(), "RAW  2")
                w._set_file_filter("jpeg")
                self.assertEqual(w.files, jpgs)
                self.assertEqual(w.filmstrip.count(), 2)
                w._set_file_filter("all")
                self.assertEqual(w.filmstrip.count(), 4)
                w.set_files(jpgs)              # only JPEGs: no switch, everything shown
                self.assertTrue(w.kind_bar.isHidden())
                self.assertEqual(w.files, jpgs)
                self.assertTrue(w.queue_btn.isHidden())   # nothing exported yet
                for _ in range(3):           # let thumbnail, preview and render jobs finish before the folder goes
                    w.pool.waitForDone(30000)
                    self.app.processEvents()
                w.close()
            finally:
                os.environ.pop("EMULSA_HOME", None)


if __name__ == "__main__":
    unittest.main()
