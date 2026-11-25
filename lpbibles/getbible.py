"""getBible (api.getbible.net): free public-domain Bibles, one JSON file each."""

from __future__ import annotations

import json
import threading
from typing import Optional

from . import netutil
from .model import BibleError, Entry, ParsedBible

LIST_URL = "https://api.getbible.net/v2/translations.json"
BIBLE_URL = "https://api.getbible.net/v2/{abbr}.json"


def fetch_catalog(cancel: Optional[threading.Event] = None) -> list[Entry]:
    data = netutil.get(LIST_URL, cancel=cancel, timeout=30).json()
    return parse_catalog(data)


def parse_catalog(data: dict) -> list[Entry]:
    out: list[Entry] = []
    items = data.values() if isinstance(data, dict) else data
    for d in items:
        abbr = str(d.get("abbreviation") or "").strip()
        if not abbr:
            continue
        language = str(d.get("language") or d.get("lang") or "").strip()
        out.append(Entry(
            key=f"getbible:{abbr}", source="getbible", name=str(d.get("translation") or abbr).strip(),
            short=abbr.upper(), language=language or "Other", lang_code=str(d.get("lang") or "").strip(),
            licensed=False, size_mb=None, note="", ref={"abbr": abbr, "direction": str(d.get("direction") or "LTR")}))
    return out


def decode(data: dict, entry: Optional[Entry] = None) -> ParsedBible:
    """Reads the getBible layout: books[nr, name, chapters[chapter, verses[verse, text]]].

    Also accepts the same layout as a file chosen by hand.
    """
    if not isinstance(data, dict):
        raise BibleError("This JSON file is not a Bible file.")
    pb = ParsedBible()
    pb.name = str(data.get("translation") or data.get("name") or (entry.name if entry else ""))
    pb.short = str(data.get("abbreviation") or (entry.short if entry else "")).upper()
    pb.language = str(data.get("language") or (entry.language if entry else ""))
    pb.lang_code = str(data.get("lang") or (entry.lang_code if entry else ""))
    pb.direction = "rtl" if str(data.get("direction") or "").lower() == "rtl" else "ltr"
    pb.copyright = str(data.get("distribution_about") or data.get("description") or "").replace("\\par", "\n").strip()
    books = data.get("books")
    if isinstance(books, dict):
        books = [books[k] for k in sorted(books, key=lambda x: int(x) if str(x).isdigit() else 0)]
    for bi, book in enumerate(books or []):
        if not isinstance(book, dict):
            continue
        try:
            nr = int(book.get("nr") or (bi + 1))
        except (TypeError, ValueError):
            nr = bi + 1
        if not 1 <= nr <= 66:
            continue
        name = str(book.get("name") or "").strip()
        if name:
            pb.book_names[nr] = (name, name, name)
        chapters = book.get("chapters")
        if isinstance(chapters, dict):
            chapters = [chapters[k] for k in sorted(chapters, key=lambda x: int(x) if str(x).isdigit() else 0)]
        for ci, ch in enumerate(chapters or []):
            if not isinstance(ch, dict):
                continue
            try:
                cn = int(ch.get("chapter") or (ci + 1))
            except (TypeError, ValueError):
                cn = ci + 1
            verses = ch.get("verses")
            if isinstance(verses, dict):
                verses = [verses[k] for k in sorted(verses, key=lambda x: int(x) if str(x).isdigit() else 0)]
            for vi, v in enumerate(verses or []):
                if not isinstance(v, dict):
                    continue
                try:
                    vn = int(v.get("verse") or (vi + 1))
                except (TypeError, ValueError):
                    vn = vi + 1
                pb.add(nr, cn, vn, str(v.get("text") or ""))
    return pb


def download(entry: Entry, cancel: Optional[threading.Event] = None, progress=None) -> ParsedBible:
    url = BIBLE_URL.format(abbr=entry.ref["abbr"])
    if progress:
        progress(0, 1)
    raw = netutil.download(url, cancel=cancel, progress=progress)
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except ValueError:
        raise BibleError("The Bible file could not be read.")
    pb = decode(data, entry)
    pb.validate()
    return pb
