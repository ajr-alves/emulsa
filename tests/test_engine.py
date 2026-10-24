import os
import tempfile
import unittest

import numpy as np

from emulsa import imageio
from emulsa.engine import apply_lut, bake_lut, grade, render, resolve, write_cube
from emulsa.looks import BUILTIN, RECIPES
from emulsa.store import Store


def sample(h=48, w=64):
    rng = np.random.default_rng(1)
    return rng.random((h, w, 3)).astype(np.float32)


class EngineTests(unittest.TestCase):
    def test_neutral_look_changes_nothing(self):
        img = sample()
        out = apply_lut(img, bake_lut({}))
        self.assertLess(float(np.abs(out - img).max()), 1e-5)

    def test_lut_matches_direct_grade(self):
        params = BUILTIN[11]["params"]  # Classic Chrome: curves, hue shifts, split toning
        img = sample()
        via_lut = apply_lut(img, bake_lut(params, 65))
        direct = grade(img, params)
        self.assertLess(float(np.abs(via_lut - direct).mean()), 0.004)

    def test_every_look_stays_in_range(self):
        img = sample()
        for look in BUILTIN:
            out = render(img, look["params"], scale=0.3)
            self.assertTrue(np.isfinite(out).all(), look["name"])
            self.assertGreaterEqual(float(out.min()), 0.0, look["name"])
            self.assertLessEqual(float(out.max()), 1.0, look["name"])

    def test_tones_stay_in_order(self):
        ramp = np.linspace(0, 1, 256, dtype=np.float32)[:, None].repeat(3, axis=1)[None]
        for look in BUILTIN:
            y = grade(ramp, look["params"])[0] @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
            self.assertGreaterEqual(float(np.diff(y).min()), -1e-3, look["name"])

    def test_mono_looks_are_grey(self):
        img = sample()
        for look in BUILTIN:
            p = resolve(look["params"])
            if p["mono"] and p["split_shadows"][1] == 0 and p["split_highlights"][1] == 0:
                out = grade(img, look["params"])
                self.assertLess(float(np.ptp(out, axis=-1).max()), 1e-4, look["name"])

    def test_strength_blends_toward_original(self):
        img = sample()
        lut = bake_lut(BUILTIN[9]["params"])
        self.assertLess(float(np.abs(apply_lut(img, lut, strength=0.0) - img).max()), 1e-6)

    def test_all_recipes_become_looks_with_unique_ids(self):
        self.assertEqual(len(BUILTIN), len(RECIPES))
        self.assertEqual(len({l["id"] for l in BUILTIN}), len(BUILTIN))

    def test_cube_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "look.cube")
            write_cube(path, BUILTIN[3]["params"], "Vivid", size=17)
            lines = open(path).read().splitlines()
            self.assertIn("LUT_3D_SIZE 17", lines)
            data = [l for l in lines if l and l[0].isdigit()]
            self.assertEqual(len(data), 17 ** 3)


class FileTests(unittest.TestCase):
    def test_jpeg_round_trip_and_resize(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "photo.jpg")
            Image.fromarray((sample(300, 400) * 255).astype(np.uint8)).save(src, quality=95)
            self.assertEqual(imageio.list_photos(d), [src])
            arr, _ = imageio.load_full(src)
            self.assertEqual(arr.shape, (300, 400, 3))
            small = imageio.resize_long_edge(arr, 200)
            self.assertEqual(small.shape, (150, 200, 3))
            out = os.path.join(d, "out.jpg")
            imageio.save(out, render(small, BUILTIN[20]["params"]), "JPEG", 90)
            with Image.open(out) as im:
                self.assertEqual(im.size, (200, 150))


class StoreTests(unittest.TestCase):
    def test_favourites_and_custom_looks_persist(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "settings.json")
            s = Store(path)
            s.toggle_favourite("velvia")
            look = s.add_custom("Mine", {"contrast": 0.3}, "velvia")
            s2 = Store(path)
            self.assertTrue(s2.is_favourite("velvia"))
            self.assertEqual(s2.look(look["id"])["name"], "Mine")
            s2.delete_custom(look["id"])
            self.assertIsNone(Store(path).look(look["id"]))


if __name__ == "__main__":
    unittest.main()
