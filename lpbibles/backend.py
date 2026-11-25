"""The window asks this object for lists and downloads. Tests and the screenshot tool use a fake one."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Optional

from . import biblecom, catalog, ebible, getbible
from .catalog import FreeCatalog, Language
from .model import BibleError, Entry, ParsedBible

Progress = Callable[[int, int, Optional[float]], None]


class Backend:
    def __init__(self, cache: Path):
        self.cache = Path(cache)

    def load_free(self, cancel: threading.Event) -> FreeCatalog:
        return catalog.load_free(self.cache, cancel)

    def bc_languages(self, cancel: threading.Event) -> tuple[list[Language], bool]:
        return catalog.load_biblecom_languages(self.cache, cancel)

    def bc_versions(self, tag: str, english: str, cancel: threading.Event) -> tuple[list[Entry], bool]:
        return catalog.load_biblecom_versions(self.cache, tag, english, cancel)

    def download(self, entry: Entry, cancel: threading.Event, progress: Progress) -> ParsedBible:
        if entry.source == "getbible":
            return getbible.download(entry, cancel, progress)
        if entry.source == "ebible":
            return ebible.download(entry, cancel, progress)
        if entry.source == "biblecom":
            return biblecom.download(entry, cancel, progress)
        raise BibleError("Unknown source for this Bible.")
