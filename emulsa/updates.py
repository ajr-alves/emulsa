"""Checking GitHub for a newer Emulsa.

What it does, and what it doesn't:
- At most once a day (or when asked) it reads the public "latest release" record of this project from
  GitHub. Nothing about you or your photos is sent; GitHub sees an ordinary web request.
- It never downloads or runs anything by itself. It only tells you, and opens the release page or
  installer link in your browser if you click.
- Only links on github.com under this project are ever opened.
"""
from __future__ import annotations

import platform
import re
import sys
import time
from dataclasses import dataclass
from urllib.parse import urlparse

from . import __version__

REPO = "ajr-alves/emulsa"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases/latest"
CHECK_EVERY = 24 * 3600          # seconds between automatic checks
TIMEOUT = 6.0

_VERSION = re.compile(r"^v?(\d{1,4})\.(\d{1,4})\.(\d{1,4})$")


@dataclass
class Release:
    version: str          # "0.4.0"
    page_url: str         # the release page
    download_url: str     # the installer for this computer, or the release page if none matches
    notes: str            # first lines of the release notes, plain text


def parse_version(text: str) -> tuple[int, int, int] | None:
    m = _VERSION.match((text or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def is_newer(candidate: str, current: str = __version__) -> bool:
    a, b = parse_version(candidate), parse_version(current)
    return bool(a and b and a > b)


def safe_url(url: str) -> bool:
    """Only https links to this project on github.com may be opened."""
    try:
        u = urlparse(url)
    except ValueError:
        return False
    return (u.scheme == "https" and u.hostname in ("github.com", "www.github.com")
            and u.path.lower().startswith(f"/{REPO}/".lower()))


def asset_for_this_computer(assets: list[dict]) -> str | None:
    names = {a.get("name", ""): a.get("browser_download_url", "") for a in assets if isinstance(a, dict)}
    if sys.platform == "win32":
        want = lambda n: n.lower().endswith(".exe")
    elif sys.platform == "darwin":
        arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x86_64"
        want = lambda n: n.lower().endswith(".dmg") and arch in n
    else:
        want = lambda n: n.endswith(".AppImage") and platform.machine().lower() in n.lower()
    for name, url in names.items():
        if want(name) and safe_url(url):
            return url
    return None


def parse_release(data: dict) -> Release | None:
    """Turn GitHub's JSON into a Release, or None if it isn't a usable, newer-looking release."""
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        return None
    version = str(data.get("tag_name", "")).lstrip("v")
    if not parse_version(version):
        return None
    page = str(data.get("html_url", ""))
    if not safe_url(page):
        page = RELEASES_URL
    download = asset_for_this_computer(data.get("assets") or []) or page
    body = str(data.get("body") or "")
    notes = " ".join(line.strip("#*- ").strip() for line in body.splitlines()[:6] if line.strip())[:300]
    return Release(version=version, page_url=page, download_url=download, notes=notes)


class _UrllibClient:
    """Minimal HTTPS GET with certificate checking (certifi's list when present, else the system's)."""

    def get(self, url):
        import json
        import ssl
        import urllib.error
        import urllib.request
        import os
        if os.environ.get("SSL_CERT_FILE"):       # a company proxy's certificates, set by the user or IT
            ctx = ssl.create_default_context(cafile=os.environ["SSL_CERT_FILE"])
        else:
            try:
                import certifi
                ctx = ssl.create_default_context(cafile=certifi.where())
            except ImportError:
                ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                                   "User-Agent": f"Emulsa/{__version__}"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:  # nosec B310
                return _Response(resp.status, json.loads(resp.read(512_000).decode("utf-8")))
        except urllib.error.HTTPError as err:
            return _Response(err.code, None)


class _Response:
    def __init__(self, status_code, data):
        self.status_code, self._data = status_code, data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"GitHub answered {self.status_code}")

    def json(self):
        return self._data


def fetch_latest(client=None) -> Release | None:
    """Ask GitHub for the latest release. Raises on network problems; the caller decides what to show."""
    client = client or _UrllibClient()
    r = client.get(API_URL)
    if r.status_code == 404:          # no releases yet
        return None
    r.raise_for_status()
    return parse_release(r.json())


def due(store, now: float | None = None) -> bool:
    """Whether an automatic check should run now."""
    if not store.get("check_updates", True):
        return False
    last = float(store.get("last_update_check", 0) or 0)
    return (now or time.time()) - last >= CHECK_EVERY


def should_announce(release: Release | None, store) -> bool:
    return bool(release and is_newer(release.version) and store.get("skipped_version") != release.version)
