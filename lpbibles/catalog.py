"""The lists the Add Bibles window shows: free Bibles (getBible + eBible.org) and Bible.com.

Lists are saved on this computer for a day. If the network is down the saved list is shown
(however old it is) with a message; with no saved list there is a plain error.
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional

from . import biblecom, ebible, getbible, netutil
from .model import Entry

MAX_AGE = 24 * 3600

# Native names for the languages most churches ask for (the catalogs only give English names).
NATIVE = {
    "English": "English", "Russian": "Русский", "Dutch": "Nederlands", "Spanish": "Español", "German": "Deutsch",
    "Greek": "Ελληνικά", "French": "Français", "Portuguese": "Português", "Ukrainian": "Українська",
    "Chinese": "中文", "Japanese": "日本語", "Korean": "한국어", "Italian": "Italiano", "Polish": "Polski",
    "Romanian": "Română", "Arabic": "العربية", "Hebrew": "עברית", "Turkish": "Türkçe", "Hungarian": "Magyar",
    "Czech": "Čeština", "Swedish": "Svenska", "Finnish": "Suomi", "Danish": "Dansk", "Norwegian": "Norsk",
    "Bulgarian": "Български", "Serbian": "Српски", "Croatian": "Hrvatski", "Hindi": "हिन्दी",
    "Vietnamese": "Tiếng Việt", "Indonesian": "Bahasa Indonesia", "Armenian": "Հայերեն", "Georgian": "ქართული",
}


@dataclass
class Language:
    english: str
    native: str
    count: Optional[int]   # None when not known yet (Bible.com counts arrive when a language is opened)
    tag: str = ""          # Bible.com language tag


@dataclass
class FreeCatalog:
    entries: list[Entry]
    stale: bool = False    # True when a saved list was used because the network failed


def _entries_from(items: list[dict]) -> list[Entry]:
    return [Entry(**d) for d in items]


def _cached(path: Path, fetch: Callable[[], list[Entry]], now: float) -> tuple[list[Entry], bool, bool]:
    """(entries, used_stale_after_failure, failed_completely)"""
    saved: Optional[list[Entry]] = None
    saved_time = 0.0
    if path.exists():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            saved = _entries_from(doc["entries"])
            saved_time = float(doc["time"])
        except (ValueError, KeyError, TypeError, OSError):
            saved = None
    if saved is not None and now - saved_time < MAX_AGE:
        return saved, False, False
    try:
        fresh = fetch()
    except netutil.Cancelled:
        raise
    except Exception:
        if saved is not None:
            return saved, True, False
        return [], False, True
    try:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"time": now, "entries": [asdict(e) for e in fresh]}), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass
    return fresh, False, False


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def load_free(cache: Path, cancel: Optional[threading.Event] = None, now: Optional[float] = None) -> FreeCatalog:
    """getBible and eBible.org together. getBible wins when both have the same Bible."""
    now = time.time() if now is None else now
    gb, gb_stale, gb_fail = _cached(cache / "free-getbible.json", lambda: getbible.fetch_catalog(cancel), now)
    eb, eb_stale, eb_fail = _cached(cache / "free-ebible.json", lambda: ebible.fetch_catalog(cancel), now)
    if gb_fail and eb_fail:
        raise netutil.NetworkError("Could not reach the list. Check the internet connection.", offline=True)
    seen = {(_norm(e.language), _norm(e.name)) for e in gb}
    entries = list(gb)
    for e in eb:
        if (_norm(e.language), _norm(e.name)) not in seen:
            entries.append(e)
    return FreeCatalog(entries, stale=gb_stale or eb_stale or gb_fail or eb_fail)


def languages(entries: list[Entry], system_language: str = "English") -> list[Language]:
    """Languages of a list: the Mac's language, English and Russian first, then the biggest."""
    counts: dict[str, int] = {}
    native: dict[str, str] = {}
    for e in entries:
        name = e.language or "Other"
        counts[name] = counts.get(name, 0) + 1
        if e.language_native and name not in native:
            native[name] = e.language_native
    first = [system_language, "English", "Russian"]
    order: list[str] = []
    for n in first:
        if n in counts and n not in order:
            order.append(n)
    rest = sorted((n for n in counts if n not in order), key=lambda n: (-counts[n], n.lower()))
    return [Language(n, NATIVE.get(n) or native.get(n) or n, counts[n]) for n in order + rest]


def for_language(entries: list[Entry], english: str, text: str = "") -> list[Entry]:
    """The Bibles of one language, filtered by a search text, sorted by name."""
    t = text.strip().lower()
    out = [e for e in entries if (e.language or "Other") == english
           and (not t or t in e.name.lower() or t in e.short.lower())]
    return sorted(out, key=lambda e: e.name.lower())


def search_all(entries: list[Entry], text: str) -> list[Entry]:
    t = text.strip().lower()
    return sorted((e for e in entries if t in e.name.lower() or t in e.short.lower()), key=lambda e: e.name.lower())


# ---- Bible.com lists (separate, because they are fetched one language at a time) -------------------

def load_biblecom_languages(cache: Path, cancel: Optional[threading.Event] = None,
                            now: Optional[float] = None) -> tuple[list[Language], bool]:
    now = time.time() if now is None else now
    path = cache / "biblecom-languages.json"
    saved = None
    if path.exists():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            saved = (doc["languages"], float(doc["time"]))
        except (ValueError, KeyError, TypeError, OSError):
            saved = None
    if saved and now - saved[1] < MAX_AGE:
        return [Language(**d) for d in saved[0]], False
    try:
        raw = biblecom.fetch_languages(cancel)
    except netutil.Cancelled:
        raise
    except Exception:
        if saved:
            return [Language(**d) for d in saved[0]], True
        raise
    langs = [Language(english=r["english"], native=NATIVE.get(r["english"]) or r["native"], count=None, tag=r["tag"])
             for r in raw]
    try:
        path.write_text(json.dumps({"time": now, "languages": [asdict(l) for l in langs]}), encoding="utf-8")
    except OSError:
        pass
    return langs, False


def load_biblecom_versions(cache: Path, tag: str, english: str, cancel: Optional[threading.Event] = None,
                           now: Optional[float] = None) -> tuple[list[Entry], bool]:
    now = time.time() if now is None else now
    path = cache / f"biblecom-{re.sub(r'[^A-Za-z0-9_-]', '', tag)}.json"

    def fetch() -> list[Entry]:
        out = biblecom.fetch_versions(tag, cancel)
        for e in out:
            e.language = english
        return out
    entries, stale, failed = _cached(path, fetch, now)
    if failed:
        raise netutil.NetworkError("Bible.com did not answer. Try again later, or import a file.")
    return entries, stale
