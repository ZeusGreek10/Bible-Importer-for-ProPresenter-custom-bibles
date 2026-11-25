"""Where the app keeps its files, and where its bundled resources are."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_FOLDER = "Bible Importer"


def data_dir() -> Path:
    """The folder with the library and the saved lists (per user)."""
    override = os.environ.get("BIBLE_IMPORTER_DATA")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / APP_FOLDER
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_FOLDER
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / APP_FOLDER
    base.mkdir(parents=True, exist_ok=True)
    return base


def cache_dir() -> Path:
    p = data_dir() / "cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def resource_path(relative: str) -> str:
    """A bundled file, in development and inside a PyInstaller app."""
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = str(Path(__file__).resolve().parent.parent / "Resources")
    return os.path.join(base, relative)
