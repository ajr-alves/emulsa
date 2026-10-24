"""The look assistant: chat with Claude about a look, optionally showing it reference photos.

Safety rules this module follows:
- The API key belongs to the user. It is kept in the operating system's keychain (Windows Credential
  Manager, macOS Keychain, Linux Secret Service), never in Emulsa's settings file, never logged.
  If no keychain is available it is kept in memory for the session only.
- Photos are downscaled before upload (long edge 1024 px) and sent only when the user presses Send.
- Claude's answer is treated as data. It is parsed against a fixed JSON schema, every number is clamped
  to the range the engine accepts, and unknown keys are dropped. Nothing in a reply is ever executed,
  and reply text is shown as plain text, never as HTML.
"""
from __future__ import annotations

import base64
import copy
import io
import json
import os

import numpy as np
from PIL import Image

from .engine import HSL_CENTERS, resolve

KEYRING_SERVICE = "Emulsa"
KEYRING_USER = "anthropic-api-key"

MODELS = [
    ("claude-sonnet-5-5", "Claude Sonnet 5.5 (recommended)"),
    ("claude-opus-5-5", "Claude Opus 5.5 (most capable, slower)"),
    ("claude-haiku-5-5", "Claude Haiku 5.5 (fastest, cheapest)"),
]
DEFAULT_MODEL = MODELS[0][0]
MAX_SIDE = 1024
MAX_TURNS_KEPT = 12        # older turns are dropped so requests stay small and cheap
REQUEST_TIMEOUT = 90.0     # seconds

# The range of every number Claude may set. Anything outside is clamped.
RANGES = {
    "exposure": (-2.0, 2.0), "temperature": (-150.0, 150.0), "tint": (-10.0, 10.0),
    "contrast": (-1.0, 1.0), "highlights": (-1.0, 1.0), "shadows": (-1.0, 1.0),
    "fade": (-0.15, 0.2), "saturation": (0.0, 2.0), "grain": (0.0, 1.0), "vignette": (0.0, 1.0),
}
HSL_RANGES = {"hue": (-30.0, 30.0), "sat": (0.0, 2.0), "lum": (-1.0, 1.0)}

_NUM = {"type": "number"}
LOOK_SCHEMA = {
    "type": "object",
    "properties": {
        **{k: {"type": "number", "description": f"{lo} to {hi}"} for k, (lo, hi) in RANGES.items()},
        "mono": {"type": "boolean", "description": "true for black and white"},
        "split_shadows_hue": {"type": "number", "description": "0-360 hue tinting the shadows"},
        "split_shadows_amount": {"type": "number", "description": "0 to 1"},
        "split_highlights_hue": {"type": "number", "description": "0-360 hue tinting the highlights"},
        "split_highlights_amount": {"type": "number", "description": "0 to 1"},
        "hsl": {
            "type": "array",
            "description": "per-colour adjustments; empty if none",
            "items": {
                "type": "object",
                "properties": {
                    "color": {"type": "string", "enum": list(HSL_CENTERS)},
                    "hue": {"type": "number", "description": "-30 to 30 degrees"},
                    "sat": {"type": "number", "description": "0 to 2, 1 = unchanged"},
                    "lum": {"type": "number", "description": "-1 to 1"},
                },
                "required": ["color", "hue", "sat", "lum"],
                "additionalProperties": False,
            },
        },
    },
    "required": list(RANGES) + ["mono", "split_shadows_hue", "split_shadows_amount",
                                "split_highlights_hue", "split_highlights_amount", "hsl"],
    "additionalProperties": False,
}
REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string", "description": "What you say to the photographer. Plain text, short."},
        "apply_look": {"type": "boolean", "description": "true when this reply proposes a new look"},
        "look_name": {"type": "string", "description": "Short name for the proposed look"},
        "look": LOOK_SCHEMA,
    },
    "required": ["reply", "apply_look", "look_name", "look"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You are the look assistant inside Emulsa, a desktop app that applies film looks to photos.
The photographer describes a look in words, shows reference photos, or both. You answer briefly and,
when it helps, propose a look as settings for Emulsa's colour engine.

How the engine works (applied to an sRGB photo, in this order):
- temperature: warm/cool shift in mireds (+ warmer). tint: + greener, - more magenta.
- exposure in stops. highlights: negative = softer roll-off. shadows: positive lifts dark tones.
- contrast: S-curve, -1..1. fade: positive lifts blacks (matte), negative crushes them.
- saturation: multiplier, 1 = unchanged. hsl: per-colour hue shift (degrees), saturation multiplier,
  luminance; colours are red, orange, yellow, green, aqua, blue, purple, magenta.
- split toning: a hue (0 red, 30 orange, 60 yellow, 120 green, 180 cyan, 210 teal-blue, 240 blue,
  300 magenta) and amount 0..1 for shadows and for highlights. Typical amounts are 0.1 to 0.4.
- mono: black and white. grain and vignette: 0..1.
Subtle values look best: contrast within +-0.4, saturation 0.6 to 1.4, temperature within +-40,
fade within 0..0.08, grain 0.1 to 0.4 for a film feel.

You receive the current settings and simple measurements of the photographer's photo and of any
reference photo (brightness percentiles, saturation, colour cast). Use them to match a reference:
compare the numbers, then adjust the settings to close the gap. Describe what you changed and why in
one to three short sentences. If the request is unclear, ask one question and set apply_look to false.
When apply_look is false, return the current settings unchanged in "look".
Never claim to see details you cannot see. Only discuss photography and this app."""


# ---------------------------------------------------------------------- API key storage
class KeyStore:
    """Keeps the API key in the OS keychain, or in memory if there is no keychain."""

    def __init__(self):
        self._session_key: str | None = None
        try:
            import keyring
            from keyring.backends import fail
            self._keyring = None if isinstance(keyring.get_keyring(), fail.Keyring) else keyring
        except Exception:
            self._keyring = None

    @property
    def persistent(self) -> bool:
        return self._keyring is not None

    def get(self) -> str | None:
        env = os.environ.get("ANTHROPIC_API_KEY")
        if env:
            return env
        if self._keyring is not None:
            try:
                return self._keyring.get_password(KEYRING_SERVICE, KEYRING_USER) or self._session_key
            except Exception:
                return self._session_key
        return self._session_key

    def set(self, key: str) -> None:
        key = key.strip()
        self._session_key = key or None
        if self._keyring is not None:
            try:
                if key:
                    self._keyring.set_password(KEYRING_SERVICE, KEYRING_USER, key)
                else:
                    self._keyring.delete_password(KEYRING_SERVICE, KEYRING_USER)
            # the keychain refused; the key still works for this session from memory
            except Exception:  # nosec B110
                pass

    def clear(self) -> None:
        self.set("")


def mask_key(key: str | None) -> str:
    """Show only the end of a key, for the settings screen."""
    if not key:
        return "Not set"
    return "…" + key[-4:] if len(key) > 8 else "Set"


# ---------------------------------------------------------------------- photo preparation
def encode_image(arr: np.ndarray) -> dict:
    """Float RGB 0..1 -> a downscaled JPEG image block for the API."""
    img = Image.fromarray((np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": base64.b64encode(buf.getvalue()).decode("ascii")}}


def measure(arr: np.ndarray) -> dict:
    """Simple, robust statistics Claude can compare between a reference and the user's photo."""
    small = arr
    if max(arr.shape[:2]) > 400:
        step = int(np.ceil(max(arr.shape[:2]) / 400))
        small = arr[::step, ::step]
    px = np.clip(small.reshape(-1, 3).astype(np.float32), 0, 1)
    y = px @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    mx, mn = px.max(axis=1), px.min(axis=1)
    sat = np.where(mx > 1e-4, (mx - mn) / np.maximum(mx, 1e-4), 0)
    mid = (y > 0.25) & (y < 0.75)
    ref = px[mid] if mid.sum() > 50 else px
    cast_warm = float((ref[:, 0] - ref[:, 2]).mean())
    cast_green = float((ref[:, 1] - (ref[:, 0] + ref[:, 2]) / 2).mean())
    p = np.percentile(y, [5, 25, 50, 75, 95])
    return {
        "brightness_p5_p25_p50_p75_p95": [round(float(v), 3) for v in p],
        "mean_saturation": round(float(sat.mean()), 3),
        "midtone_warmth (red minus blue)": round(cast_warm, 3),
        "midtone_green_vs_magenta": round(cast_green, 3),
        "black_point (darkest 1%)": round(float(np.percentile(y, 1)), 3),
    }


# ---------------------------------------------------------------------- reading Claude's answer
def _clamp(v, lo, hi, default):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    if not np.isfinite(v):
        return default
    return max(lo, min(hi, v))


def sanitize_look(look: dict | None, fallback: dict | None = None) -> dict:
    """Turn whatever came back into valid engine parameters. Never raises."""
    base = resolve(fallback)
    if not isinstance(look, dict):
        return base
    out = copy.deepcopy(base)
    for key, (lo, hi) in RANGES.items():
        if key in look:
            out[key] = _clamp(look[key], lo, hi, base[key])
    if isinstance(look.get("mono"), bool):
        out["mono"] = look["mono"]
    for side in ("shadows", "highlights"):
        hue = _clamp(look.get(f"split_{side}_hue"), 0.0, 360.0, base[f"split_{side}"][0])
        amt = _clamp(look.get(f"split_{side}_amount"), 0.0, 1.0, base[f"split_{side}"][1])
        out[f"split_{side}"] = [round(hue, 1), round(amt, 3)]
    if isinstance(look.get("hsl"), list):
        hsl = {}
        for item in look["hsl"][:16]:
            if not isinstance(item, dict):
                continue
            color = str(item.get("color", "")).lower()
            if color not in HSL_CENTERS:
                continue
            hsl[color] = {k: _clamp(item.get(k), lo, hi, 1.0 if k == "sat" else 0.0)
                          for k, (lo, hi) in HSL_RANGES.items()}
        out["hsl"] = hsl
    return out


def look_to_schema(params: dict) -> dict:
    """Current engine parameters in the same shape as the reply schema, to show Claude."""
    p = resolve(params)
    d = {k: round(float(p[k]), 3) for k in RANGES}
    d["mono"] = bool(p["mono"])
    d["split_shadows_hue"], d["split_shadows_amount"] = p["split_shadows"]
    d["split_highlights_hue"], d["split_highlights_amount"] = p["split_highlights"]
    d["hsl"] = [{"color": c, "hue": a.get("hue", 0.0), "sat": a.get("sat", 1.0), "lum": a.get("lum", 0.0)}
                for c, a in p["hsl"].items()]
    return d


def parse_reply(text: str, fallback: dict) -> tuple[str, dict | None, str]:
    """Returns (message, look params or None, look name)."""
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return (text or "").strip()[:4000], None, ""
    if not isinstance(data, dict):
        return "The assistant sent an answer Emulsa couldn't read. Try again.", None, ""
    message = str(data.get("reply", "")).strip()[:4000]
    name = " ".join(str(data.get("look_name", "")).split())[:60] or "Assistant look"
    if data.get("apply_look") is True:
        return message, sanitize_look(data.get("look"), fallback), name
    return message, None, name


# ---------------------------------------------------------------------- the conversation
class Conversation:
    """Holds the chat history and sends it to Claude. ``client`` is injectable for tests."""

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, client=None):
        if client is None:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key, timeout=REQUEST_TIMEOUT, max_retries=2)
        self.client = client
        self.model = model
        self.history: list[dict] = []

    def build_user_turn(self, text: str, photo: np.ndarray | None, references: list[np.ndarray],
                        params: dict) -> dict:
        content: list[dict] = []
        if photo is not None:
            content.append({"type": "text", "text": "My photo, with the current look applied:"})
            content.append(encode_image(photo))
        for i, ref in enumerate(references[:4], 1):
            content.append({"type": "text", "text": f"Reference photo {i}:"})
            content.append(encode_image(ref))
        info = {"current_settings": look_to_schema(params)}
        if photo is not None:
            info["my_photo_measurements"] = measure(photo)
        for i, ref in enumerate(references[:4], 1):
            info[f"reference_{i}_measurements"] = measure(ref)
        content.append({"type": "text", "text": json.dumps(info)})
        content.append({"type": "text", "text": text.strip() or "Match the reference photo."})
        return {"role": "user", "content": content}

    def _trimmed(self) -> list[dict]:
        msgs = self.history[-MAX_TURNS_KEPT:]
        while msgs and msgs[0]["role"] != "user":
            msgs = msgs[1:]
        return msgs

    def send(self, text: str, photo, references, params: dict) -> tuple[str, dict | None, str]:
        turn = self.build_user_turn(text, photo, references, params)
        self.history.append(turn)
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                system=SYSTEM_PROMPT,
                messages=self._trimmed(),
                output_config={"format": {"type": "json_schema", "schema": REPLY_SCHEMA}},
            )
        except Exception:
            self.history.pop()  # keep history valid so the user can retry
            raise
        if getattr(response, "stop_reason", None) == "refusal":
            self.history.pop()
            return "The assistant can't help with that request.", None, ""
        text_out = "".join(getattr(b, "text", "") for b in response.content if getattr(b, "type", "") == "text")
        self.history.append({"role": "assistant", "content": text_out or "{}"})
        return parse_reply(text_out, params)


def friendly_error(exc: Exception) -> str:
    """A message the photographer can act on. Never includes the key."""
    try:
        import anthropic
    except ImportError:
        return "The assistant isn't available in this build."
    if isinstance(exc, anthropic.AuthenticationError):
        return "Your API key was rejected. Check it in the assistant's settings."
    if isinstance(exc, anthropic.PermissionDeniedError):
        return "This API key isn't allowed to use that model. Pick another model in settings."
    if isinstance(exc, anthropic.RateLimitError):
        return "Too many requests right now. Wait a minute and try again."
    if isinstance(exc, (anthropic.APITimeoutError,)):
        return "The assistant took too long to answer. Try again."
    if isinstance(exc, anthropic.APIConnectionError):
        return "Couldn't reach the assistant. Check your internet connection."
    if isinstance(exc, anthropic.BadRequestError):
        return "The request was refused as invalid. Try a smaller reference photo or start a new chat."
    if isinstance(exc, anthropic.APIStatusError):
        return f"The assistant had a problem (error {exc.status_code}). Try again shortly."
    return "Something went wrong talking to the assistant. Try again."
