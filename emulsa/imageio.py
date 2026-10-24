"""Reading photos (JPEG, PNG, TIFF, RAW) and writing exports."""
from __future__ import annotations

import io
import os

import numpy as np
from PIL import Image, ImageOps

try:
    import rawpy
except ImportError:  # the app still works on JPEGs without it
    rawpy = None

RAW_EXT = {".arw", ".srf", ".sr2", ".cr2", ".cr3", ".nef", ".nrw", ".raf", ".dng", ".orf",
           ".rw2", ".pef", ".srw", ".3fr", ".iiq", ".x3f"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".bmp"}
SUPPORTED = RAW_EXT | IMAGE_EXT

Image.MAX_IMAGE_PIXELS = 400_000_000


def is_raw(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in RAW_EXT


def is_supported(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in SUPPORTED


def list_photos(folder: str) -> list[str]:
    try:
        names = sorted(os.listdir(folder), key=str.lower)
    except OSError:
        return []
    return [os.path.join(folder, n) for n in names
            if is_supported(n) and os.path.isfile(os.path.join(folder, n))]


def _to_float(img: Image.Image) -> np.ndarray:
    if img.mode in ("I;16", "I;16B", "I;16L", "I"):
        arr = np.asarray(img, dtype=np.float32) / 65535.0
        return np.repeat(arr[..., None], 3, axis=-1)
    if img.mode != "RGB":
        img = img.convert("RGB")
    return np.asarray(img, dtype=np.float32) / 255.0


def _fit(img: Image.Image, max_side: int) -> Image.Image:
    if max(img.size) > max_side:
        img = img.copy()
        img.thumbnail((max_side, max_side), Image.LANCZOS)
    return img


def _raw_rgb(path: str, half: bool) -> np.ndarray:
    if rawpy is None:
        raise RuntimeError("RAW support needs the rawpy package.")
    with rawpy.imread(path) as raw:
        rgb = raw.postprocess(use_camera_wb=True, half_size=half, output_bps=16,
                              output_color=rawpy.ColorSpace.sRGB, no_auto_bright=False,
                              bright=1.0, user_flip=None)
    return rgb.astype(np.float32) / 65535.0


def full_width(path: str) -> int:
    """Width of the full-resolution image, read cheaply from the header (upright orientation)."""
    try:
        if is_raw(path) and rawpy is not None:
            with rawpy.imread(path) as raw:
                s = raw.sizes
                return s.height if s.flip in (5, 6) else s.width
        with Image.open(path) as img:
            w, h = img.size
            return h if img.getexif().get(0x0112, 1) in (5, 6, 7, 8) else w
    except Exception:
        return 0


def load_preview(path: str, max_side: int = 1800) -> np.ndarray:
    """A screen-sized version of the photo as float RGB 0..1, correctly rotated."""
    if is_raw(path):
        arr = _raw_rgb(path, half=True)
        img = Image.fromarray((arr * 255 + 0.5).astype(np.uint8))
        return _to_float(_fit(img, max_side))
    with Image.open(path) as img:
        img.draft("RGB", (max_side, max_side))
        img = ImageOps.exif_transpose(img)
        return _to_float(_fit(img, max_side))


def load_thumbnail(path: str, size: int = 160) -> Image.Image:
    """Fast small image for the filmstrip. Uses the RAW's embedded JPEG when there is one."""
    if is_raw(path) and rawpy is not None:
        try:
            with rawpy.imread(path) as raw:
                thumb = raw.extract_thumb()
                flip = raw.sizes.flip
            if thumb.format == rawpy.ThumbFormat.JPEG:
                img = Image.open(io.BytesIO(thumb.data))
                img.draft("RGB", (size * 2, size * 2))
                img = img.convert("RGB")
            else:
                img = Image.fromarray(thumb.data)
            img = {3: img.transpose(Image.ROTATE_180), 5: img.transpose(Image.ROTATE_90),
                   6: img.transpose(Image.ROTATE_270)}.get(flip, img)
            img.thumbnail((size, size), Image.LANCZOS)
            return img
        except Exception:  # nosec B110 - no usable embedded preview; decode the RAW itself below
            pass
        arr = _raw_rgb(path, half=True)
        img = Image.fromarray((arr * 255 + 0.5).astype(np.uint8))
        img.thumbnail((size, size), Image.LANCZOS)
        return img
    with Image.open(path) as img:
        img.draft("RGB", (size * 2, size * 2))
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((size, size), Image.LANCZOS)
        return img


def load_full(path: str) -> tuple[np.ndarray, bytes | None]:
    """Full-resolution float RGB plus EXIF to carry over (JPEG/TIFF only)."""
    if is_raw(path):
        return _raw_rgb(path, half=False), None
    with Image.open(path) as img:
        exif = None
        try:
            ex = img.getexif()
            if ex:
                ex[0x0112] = 1  # pixels get rotated upright below, so reset the orientation tag
                exif = ex.tobytes()
        except Exception:
            exif = None
        img = ImageOps.exif_transpose(img)
        return _to_float(img), exif


def resize_long_edge(arr: np.ndarray, long_edge: int | None) -> np.ndarray:
    if not long_edge or max(arr.shape[:2]) <= long_edge:
        return arr
    h, w = arr.shape[:2]
    s = long_edge / max(h, w)
    size = (max(1, round(w * s)), max(1, round(h * s)))
    # resize each channel in float so 16-bit RAW data keeps its precision
    chans = [np.asarray(Image.fromarray(np.ascontiguousarray(arr[..., c]), "F").resize(size, Image.LANCZOS))
             for c in range(3)]
    return np.clip(np.stack(chans, axis=-1), 0, 1).astype(np.float32)


def save(path: str, arr: np.ndarray, fmt: str = "JPEG", quality: int = 92, exif: bytes | None = None) -> None:
    """Write a float RGB image. fmt is JPEG, PNG or TIFF."""
    img = Image.fromarray((np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB")
    kwargs = {}
    if fmt == "JPEG":
        kwargs.update(quality=int(quality), subsampling=0 if quality >= 90 else 2, optimize=True)
    elif fmt == "TIFF":
        kwargs.update(compression="tiff_lzw")
    if exif and fmt in ("JPEG", "TIFF"):
        kwargs["exif"] = exif
    tmp = path + ".part"
    img.save(tmp, fmt, **kwargs)
    os.replace(tmp, path)
