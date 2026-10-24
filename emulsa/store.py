"""Favourites, custom looks and app settings, kept in one JSON file in the user's app data folder."""
from __future__ import annotations

import copy
import json
import os
import sys
import time

from .looks import BUILTIN, slug


def data_dir() -> str:
    """Where settings live: %APPDATA%\\Emulsa on Windows, ~/Library/Application Support/Emulsa on macOS,
    $XDG_CONFIG_HOME/emulsa (usually ~/.config/emulsa) on Linux. EMULSA_HOME overrides all of these."""
    override = os.environ.get("EMULSA_HOME")
    if override:
        path = override
    elif sys.platform == "win32":
        path = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Emulsa")
    elif sys.platform == "darwin":
        path = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "Emulsa")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
        path = os.path.join(base, "emulsa")
    os.makedirs(path, exist_ok=True)
    return path


class Store:
    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(data_dir(), "settings.json")
        self.data = {"favourites": [], "custom": [], "settings": {}}
        try:
            with open(self.path, encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                self.data.update(loaded)
        except (OSError, ValueError):
            pass

    def save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=1)
        os.replace(tmp, self.path)

    # looks ---------------------------------------------------------------
    def looks(self) -> list[dict]:
        custom = [dict(l, builtin=False, brand="Custom") for l in self.data["custom"]]
        return custom + BUILTIN

    def look(self, look_id: str) -> dict | None:
        return next((l for l in self.looks() if l["id"] == look_id), None)

    def add_custom(self, name: str, params: dict, based_on: str | None) -> dict:
        look = {"id": f"custom-{slug(name) or 'look'}-{int(time.time())}", "name": name.strip() or "Custom look",
                "params": copy.deepcopy(params), "based_on": based_on}
        self.data["custom"].insert(0, look)
        self.save()
        return dict(look, builtin=False, brand="Custom")

    def rename_custom(self, look_id: str, name: str) -> None:
        for l in self.data["custom"]:
            if l["id"] == look_id:
                l["name"] = name.strip() or l["name"]
        self.save()

    def delete_custom(self, look_id: str) -> None:
        self.data["custom"] = [l for l in self.data["custom"] if l["id"] != look_id]
        self.data["favourites"] = [f for f in self.data["favourites"] if f != look_id]
        self.save()

    # favourites ----------------------------------------------------------
    def is_favourite(self, look_id: str) -> bool:
        return look_id in self.data["favourites"]

    def toggle_favourite(self, look_id: str) -> bool:
        favs = self.data["favourites"]
        if look_id in favs:
            favs.remove(look_id)
        else:
            favs.append(look_id)
        self.save()
        return look_id in favs

    # settings ------------------------------------------------------------
    def get(self, key: str, default=None):
        return self.data["settings"].get(key, default)

    def set(self, key: str, value) -> None:
        self.data["settings"][key] = value
        self.save()
