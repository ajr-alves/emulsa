"""Colour engine: turns a set of look parameters into a 3D LUT and applies it to images.

Every look is a plain dict of parameters (see ``DEFAULTS``). The engine runs those parameters
through one fixed pipeline on a lattice of colours, which gives a 3D LUT. Images are then graded
by trilinear lookup into that LUT, so what you preview, what you export and the .cube file you
save are always the same transform. Grain and vignette depend on pixel position, so they are
applied after the LUT and are not part of a .cube export.
"""
from __future__ import annotations

import math
from typing import Callable

import numpy as np

LUT_SIZE = 33

# Every adjustable parameter with its neutral value. A look only stores what differs.
DEFAULTS: dict = {
    "exposure": 0.0,        # stops
    "temperature": 0.0,     # mireds, positive = warmer
    "tint": 0.0,            # positive = greener, negative = more magenta
    "contrast": 0.0,        # -1 .. 1
    "highlights": 0.0,      # -1 .. 1, negative = softer roll-off
    "shadows": 0.0,         # -1 .. 1, positive = lift shadows (like DRO)
    "fade": 0.0,            # -0.15 .. 0.2, positive = lifted blacks, negative = crushed blacks
    "saturation": 1.0,      # multiplier
    "hsl": {},              # {"blue": {"sat": 0.8, "hue": -10, "lum": 0}, ...}
    "split_shadows": [0, 0.0],     # [hue degrees, amount 0..1]
    "split_highlights": [0, 0.0],  # [hue degrees, amount 0..1]
    "mono": False,
    "mono_mix": [0.30, 0.59, 0.11],  # channel mix for black & white (colour filter)
    "grain": 0.0,           # 0 .. 1, applied after the LUT
    "vignette": 0.0,        # 0 .. 1, applied after the LUT
}

HSL_CENTERS = {"red": 0, "orange": 30, "yellow": 60, "green": 120,
               "aqua": 180, "blue": 225, "purple": 270, "magenta": 320}

_Y = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def resolve(params: dict | None) -> dict:
    """Fill a look's parameters in from the defaults."""
    out = {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v)
           for k, v in DEFAULTS.items()}
    for k, v in (params or {}).items():
        if k in out:
            out[k] = v
    return out


# ------------------------------------------------------------------ colour helpers
def srgb_to_linear(x: np.ndarray) -> np.ndarray:
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, None)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def _blackbody_rgb(kelvin: float) -> np.ndarray:
    """Approximate linear RGB of a blackbody (Tanner Helland's fit), normalised to green."""
    t = kelvin / 100.0
    r = 255.0 if t <= 66 else 329.698727446 * ((t - 60) ** -0.1332047592)
    g = (99.4708025861 * math.log(t) - 161.1195681661) if t <= 66 else 288.1221695283 * ((t - 60) ** -0.0755148492)
    b = 255.0 if t >= 66 else (0.0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307)
    rgb = np.clip(np.array([r, g, b], dtype=np.float64), 1.0, 255.0) / 255.0
    rgb = srgb_to_linear(rgb)
    return rgb / rgb[1]


def white_balance_gains(temperature_mired: float, tint: float) -> np.ndarray:
    """Channel gains for a warm/cool shift in mireds plus a green/magenta tint.

    A positive shift means the camera assumed a cooler light than there was, so the picture turns
    warmer. Gains are normalised so overall brightness stays put.
    """
    base = 1e6 / 5500.0
    k_assumed = 1e6 / max(base - temperature_mired, 40.0)
    gains = _blackbody_rgb(5500.0) / _blackbody_rgb(k_assumed)
    gains = gains * np.array([1.0, 1.0 + 0.03 * tint, 1.0])
    gains = gains / float(np.dot(gains, _Y))
    return gains.astype(np.float32)


def _hsv_hue(rgb: np.ndarray) -> np.ndarray:
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx = np.max(rgb, axis=-1)
    mn = np.min(rgb, axis=-1)
    d = mx - mn + 1e-8
    h = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4))
    return (h * 60.0) % 360.0


def _hue_vector(hue_deg: float) -> np.ndarray:
    """Chroma direction (Cb, Cr) of a fully saturated HSV hue."""
    h = (hue_deg % 360) / 60.0
    x = 1 - abs(h % 2 - 1)
    rgb = [(1, x, 0), (x, 1, 0), (0, 1, x), (0, x, 1), (x, 0, 1), (1, 0, x)][int(h) % 6]
    rgb = np.array(rgb, dtype=np.float32)
    y = float(np.dot(rgb, _Y))
    v = np.array([(rgb[2] - y) / 1.8556, (rgb[0] - y) / 1.5748], dtype=np.float32)
    return v / (np.linalg.norm(v) + 1e-8)


def _to_ycc(rgb):
    y = rgb @ _Y
    cb = (rgb[..., 2] - y) / 1.8556
    cr = (rgb[..., 0] - y) / 1.5748
    return y, cb, cr


def _from_ycc(y, cb, cr):
    r = y + 1.5748 * cr
    b = y + 1.8556 * cb
    g = (y - _Y[0] * r - _Y[2] * b) / _Y[1]
    return np.stack([r, g, b], axis=-1)


def _s_curve(x: np.ndarray, amount: float, pivot: float = 0.45) -> np.ndarray:
    """Monotonic S-curve with fixed end points. amount -1..1."""
    if abs(amount) < 1e-4:
        return x
    g = 2.0 ** (amount * 1.25)
    x = np.clip(x, 0.0, 1.0)
    lo = pivot * np.power(np.clip(x / pivot, 0, 1), g)
    hi = 1.0 - (1.0 - pivot) * np.power(np.clip((1.0 - x) / (1.0 - pivot), 0, 1), g)
    return np.where(x < pivot, lo, hi)


# ------------------------------------------------------------------ the pipeline
def grade(rgb: np.ndarray, params: dict) -> np.ndarray:
    """Apply a look to sRGB values in 0..1 (any shape ending in 3). Returns sRGB 0..1."""
    p = resolve(params)
    x = srgb_to_linear(np.clip(rgb.astype(np.float32), 0, 1))

    # 1. white balance and exposure, in linear light
    x = x * white_balance_gains(p["temperature"], p["tint"])
    x = x * (2.0 ** p["exposure"])

    # 2. highlight roll-off: a soft shoulder when highlights are pulled down or exposure is pushed up,
    #    so bright areas compress instead of clipping hard. Neutral settings leave values untouched.
    knee = 1.0 - 0.45 * max(-p["highlights"], 0.0) - 0.25 * min(max(p["exposure"], 0.0), 1.0)
    if knee < 0.999:
        span = 1.0 - knee
        over = np.maximum(x - knee, 0.0)
        x = np.where(x > knee, knee + span * (1.0 - np.exp(-over / span)), x)

    x = linear_to_srgb(x)
    if p["highlights"] > 0:  # brighter, crisper highlights
        x = x + p["highlights"] * 0.6 * np.clip(x, 0, 1) ** 2 * (1.0 - np.clip(x, 0, 1))

    # 3. shadow recovery (DRO-like): lifts dark tones, leaves highlights alone
    if p["shadows"]:
        w = np.clip(1.0 - x, 0, 1) ** 3 * np.sqrt(np.clip(x, 0, 1))
        x = x + p["shadows"] * 0.35 * w

    # 4. contrast
    x = _s_curve(x, p["contrast"])

    # 5. colour: saturation, per-hue adjustments, split toning, or black & white
    y, cb, cr = _to_ycc(np.clip(x, 0, 1))
    if p["mono"]:
        mix = np.asarray(p["mono_mix"], dtype=np.float32)
        mix = mix / (mix.sum() + 1e-8)
        y = np.clip(np.clip(x, 0, 1) @ mix, 0, 1)
        cb = np.zeros_like(y)
        cr = np.zeros_like(y)
    else:
        sat = np.full(y.shape, float(p["saturation"]), dtype=np.float32)
        hshift = np.zeros(y.shape, dtype=np.float32)
        lum = np.zeros(y.shape, dtype=np.float32)
        if p["hsl"]:
            hue = _hsv_hue(np.clip(x, 0, 1))
            chroma = np.sqrt(cb * cb + cr * cr)
            presence = np.clip(chroma * 6.0, 0, 1)   # greys are left alone
            for name, adj in p["hsl"].items():
                if name not in HSL_CENTERS:
                    continue
                d = np.abs(((hue - HSL_CENTERS[name]) + 180.0) % 360.0 - 180.0)
                wgt = np.clip(1.0 - d / 45.0, 0, 1)
                wgt = wgt * wgt * (3 - 2 * wgt) * presence
                sat = sat * (1.0 + (adj.get("sat", 1.0) - 1.0) * wgt)
                hshift = hshift + adj.get("hue", 0.0) * wgt
                lum = lum + adj.get("lum", 0.0) * 0.15 * wgt
        a = np.deg2rad(hshift)
        cb, cr = cb * np.cos(a) - cr * np.sin(a), cb * np.sin(a) + cr * np.cos(a)
        cb = cb * sat
        cr = cr * sat
        y = np.clip(y + lum * (1 - y) * y * 4, 0, 1)

    for key, weight in (("split_shadows", (1.0 - y) ** 2), ("split_highlights", y ** 2)):
        hue, amt = p[key]
        if amt:
            v = _hue_vector(hue)
            cb = cb + v[0] * amt * 0.12 * weight
            cr = cr + v[1] * amt * 0.12 * weight

    x = _from_ycc(y, cb, cr)

    # 6. fade (lifted blacks) or crush
    f = p["fade"]
    if f > 0:
        x = f + x * (1.0 - f * 0.6)
    elif f < 0:
        x = (x + f) / (1.0 + f)

    return np.clip(x, 0.0, 1.0).astype(np.float32)


# ------------------------------------------------------------------ LUTs
def bake_lut(params: dict, size: int = LUT_SIZE) -> np.ndarray:
    """3D LUT indexed [r, g, b] -> output RGB, shape (size, size, size, 3)."""
    axis = np.linspace(0.0, 1.0, size, dtype=np.float32)
    r, g, b = np.meshgrid(axis, axis, axis, indexing="ij")
    lattice = np.stack([r, g, b], axis=-1)
    return grade(lattice, params)


def apply_lut(img: np.ndarray, lut: np.ndarray, strength: float = 1.0,
              chunk: int = 1 << 20, progress: Callable[[float], None] | None = None) -> np.ndarray:
    """Trilinear lookup of an sRGB float image (H, W, 3) in 0..1. Works in chunks to keep memory low."""
    size = lut.shape[0]
    flat = img.reshape(-1, 3)
    out = np.empty_like(flat, dtype=np.float32)
    n = flat.shape[0]
    for start in range(0, n, chunk):
        px = np.clip(flat[start:start + chunk].astype(np.float32), 0, 1) * (size - 1)
        i0 = np.minimum(px.astype(np.int32), size - 2)
        f = px - i0
        r0, g0, b0 = i0[:, 0], i0[:, 1], i0[:, 2]
        fr, fg, fb = f[:, 0:1], f[:, 1:2], f[:, 2:3]
        c000 = lut[r0, g0, b0]; c100 = lut[r0 + 1, g0, b0]
        c010 = lut[r0, g0 + 1, b0]; c110 = lut[r0 + 1, g0 + 1, b0]
        c001 = lut[r0, g0, b0 + 1]; c101 = lut[r0 + 1, g0, b0 + 1]
        c011 = lut[r0, g0 + 1, b0 + 1]; c111 = lut[r0 + 1, g0 + 1, b0 + 1]
        c00 = c000 + (c100 - c000) * fr; c10 = c010 + (c110 - c010) * fr
        c01 = c001 + (c101 - c001) * fr; c11 = c011 + (c111 - c011) * fr
        c0 = c00 + (c10 - c00) * fg; c1 = c01 + (c11 - c01) * fg
        res = c0 + (c1 - c0) * fb
        if strength < 1.0:
            res = flat[start:start + chunk] + (res - flat[start:start + chunk]) * strength
        out[start:start + chunk] = res
        if progress:
            progress(min(1.0, (start + chunk) / n))
    return out.reshape(img.shape)


def apply_spatial(img: np.ndarray, params: dict, seed: int = 7, scale: float = 1.0) -> np.ndarray:
    """Grain and vignette, which depend on where a pixel is. ``scale`` keeps grain size consistent
    between a small preview and the full-size export (preview width / full width)."""
    p = resolve(params)
    h, w = img.shape[:2]
    out = img
    if p["vignette"] > 0:
        yy = (np.arange(h, dtype=np.float32) - h / 2) / (h / 2)
        xx = (np.arange(w, dtype=np.float32) - w / 2) / (w / 2)
        d = np.sqrt(xx[None, :] ** 2 + yy[:, None] ** 2) / math.sqrt(2)
        mask = 1.0 - p["vignette"] * 0.55 * np.clip(d, 0, 1) ** 2.2
        out = out * mask[..., None]
    if p["grain"] > 0:
        rng = np.random.default_rng(seed)
        noise = rng.standard_normal((h + 1, w + 1)).astype(np.float32)
        if scale >= 0.5:
            # at (near) full size, clump neighbouring pixels so grain reads as film, not sensor noise
            noise = (noise[:-1, :-1] + noise[1:, :-1] + noise[:-1, 1:] + noise[1:, 1:]) * 0.5
        else:
            noise = noise[:h, :w]
        # a downscaled preview averages grain away, so show it weaker there, as a real resize would
        size_factor = math.sqrt(min(max(scale, 0.15), 1.0))
        lum = out @ _Y
        amp = p["grain"] * 0.06 * size_factor * (0.35 + 4.0 * lum * (1 - lum))  # strongest in the midtones
        out = out + (noise * amp)[..., None]
    return np.clip(out, 0, 1).astype(np.float32)


def render(img: np.ndarray, params: dict, strength: float = 1.0, scale: float = 1.0,
           lut: np.ndarray | None = None, progress=None) -> np.ndarray:
    """Full grade of an sRGB float image: LUT, then grain and vignette."""
    if lut is None:
        lut = bake_lut(params)
    out = apply_lut(img, lut, strength, progress=progress)
    return apply_spatial(out, params, scale=scale)


def write_cube(path: str, params: dict, title: str, size: int = LUT_SIZE) -> None:
    """Save a look as a .cube LUT (Resolve, Premiere, Final Cut, OBS, ...). Red changes fastest."""
    lut = bake_lut(params, size)
    lines = [f'TITLE "{title}"', "# Made with Emulsa", f"LUT_3D_SIZE {size}",
             "DOMAIN_MIN 0.0 0.0 0.0", "DOMAIN_MAX 1.0 1.0 1.0"]
    for b in range(size):
        for g in range(size):
            for r in range(size):
                c = lut[r, g, b]
                lines.append(f"{c[0]:.6f} {c[1]:.6f} {c[2]:.6f}")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
