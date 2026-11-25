"""eBible.org: free, redistributable Bibles in many languages (USFM zip downloads)."""

from __future__ import annotations

import csv
import io
import threading
from typing import Optional

from . import netutil, usfm
from .model import BibleError, Entry, ParsedBible

LIST_URL = "https://ebible.org/Scriptures/translations.csv"
ZIP_URL = "https://ebible.org/Scriptures/{id}_usfm.zip"
MIN_BOOKS = 20


def fetch_catalog(cancel: Optional[threading.Event] = None) -> list[Entry]:
    r = netutil.get(LIST_URL, cancel=cancel, timeout=60)
    return parse_catalog(r.content.decode("utf-8-sig", errors="replace"))


def _int(v: str) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def parse_catalog(text: str) -> list[Entry]:
    """Keeps only Bibles that may be redistributed, can be downloaded and have enough books."""
    out: list[Entry] = []
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        row = {(k or "").strip().strip('"').lstrip("﻿"): (v or "") for k, v in row.items()}
        tid = row.get("translationId", "").strip()
        if not tid or row.get("Redistributable", "").lower() != "true" or row.get("downloadable", "").lower() != "true":
            continue
        ot, nt = _int(row.get("OTbooks")), _int(row.get("NTbooks"))
        if ot + nt < MIN_BOOKS:
            continue
        verses = _int(row.get("OTverses")) + _int(row.get("NTverses"))
        title = (row.get("title") or row.get("shortTitle") or tid).strip()
        short = (row.get("shortTitle") or "").strip()
        # eBible has no short code like "WEB": use the id without the language prefix in capitals.
        abbr = (tid[3:] if len(tid) > 3 else tid).upper() or tid.upper()
        english = (row.get("languageNameInEnglish") or row.get("languageName") or "Other").strip()
        out.append(Entry(
            key=f"ebible:{tid}", source="ebible", name=title, short=abbr, language=english,
            lang_code=row.get("languageCode", "").strip(), licensed=False,
            size_mb=round(verses * 130 / 1_000_000, 1) if verses else None,
            note="NT only" if ot == 0 else "",
            ref={"id": tid, "direction": (row.get("textDirection") or "ltr").lower(),
                 "copyright": (row.get("Copyright") or "").strip(), "short_title": short},
            language_native=(row.get("languageName") or "").strip()))
    return out


def download(entry: Entry, cancel: Optional[threading.Event] = None, progress=None) -> ParsedBible:
    url = ZIP_URL.format(id=entry.ref["id"])
    if progress:
        progress(0, 1)
    raw = netutil.download(url, cancel=cancel, progress=progress, timeout=60)
    pb = ParsedBible(name=entry.name, short=entry.short, language=entry.language, lang_code=entry.lang_code,
                     direction="rtl" if entry.ref.get("direction") == "rtl" else "ltr",
                     copyright=entry.ref.get("copyright", ""))
    usfm.parse_zip(raw, pb)
    # Book names in the Bible's own language from \toc1/\toc2/\toc3 are a later improvement.
    pb.validate()
    return pb
