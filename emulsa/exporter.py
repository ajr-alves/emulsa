"""Exporting photos with a look: the work behind the export queue, kept free of Qt so it can be tested."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

from . import imageio
from .engine import bake_lut, render

EXTENSIONS = {"JPEG": ".jpg", "TIFF": ".tif", "PNG": ".png"}


@dataclass
class ExportSpec:
    """Everything one export needs: which photos, which look, and how to save them."""
    look_name: str
    files: list
    params: dict
    strength: float
    out_dir: str
    fmt: str = "JPEG"
    quality: int = 92
    long_edge: int | None = None
    suffix: str = ""


def target_path(out_dir: str, source: str, suffix: str, fmt: str) -> str:
    """Where an exported copy of ``source`` goes. Never overwrites a file and never leaves ``out_dir``."""
    ext = EXTENSIONS[fmt]
    name = os.path.splitext(os.path.basename(source))[0]
    target = os.path.join(out_dir, f"{name}{suffix}{ext}")
    if os.path.dirname(os.path.abspath(target)) != os.path.abspath(out_dir):
        raise ValueError("refusing to write outside the export folder")
    n = 2
    while os.path.exists(target):
        target = os.path.join(out_dir, f"{name}{suffix}-{n}{ext}")
        n += 1
    return target


def export_photos(spec: ExportSpec, progress: Callable[[int, int, str], None] | None = None,
                  should_stop: Callable[[], bool] | None = None) -> tuple[int, list]:
    """Export every photo in ``spec``. Returns (photos exported, [(file name, error)]).

    ``progress(done, total, name)`` is called before each photo and once at the end with an empty name.
    ``should_stop()`` is checked before each photo; when it returns True the export stops there.
    """
    lut = bake_lut(spec.params)
    total = len(spec.files)
    errors: list = []
    count = done = 0
    for path in spec.files:
        if should_stop and should_stop():
            break
        if progress:
            progress(done, total, os.path.basename(path))
        try:
            arr, exif = imageio.load_full(path)
            full_width = arr.shape[1]
            arr = imageio.resize_long_edge(arr, spec.long_edge)
            out = render(arr, spec.params, strength=spec.strength, scale=arr.shape[1] / full_width, lut=lut)
            imageio.save(target_path(spec.out_dir, path, spec.suffix, spec.fmt), out, spec.fmt, spec.quality, exif)
            count += 1
        except Exception as exc:  # one bad file must not stop the rest
            errors.append((os.path.basename(path), str(exc)))
        done += 1
    if progress:
        progress(done, total, "")
    return count, errors
