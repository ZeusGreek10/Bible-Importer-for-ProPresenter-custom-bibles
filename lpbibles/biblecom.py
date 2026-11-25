"""Bible.com (YouVersion) source: licensed Bibles, for churches that have the right to use them.

Not verified against the live site from the build server (it refuses datacenter addresses), so every
failure is reported in plain words and never touches the Bibles that are already saved.

Two ways to get a Bible, as in the original command-line tool:
  1. the offline zip, when the Bible has one;
  2. otherwise chapter by chapter, with retries and a small pause between chapters.
"""

from __future__ import annotations

import html
import io
import json
import re
import threading
import time
import zipfile
from pathlib import PurePosixPath
from typing import Callable, Optional

import requests

from . import netutil
from .biblecom_html import add_chapter, decode_yves_bytes
from .books import book_number
from .model import BibleError, Entry, ParsedBible

SITE = "https://www.bible.com"
CONFIG_URL = SITE + "/api/bible/configuration"
VERSIONS_URL = SITE + "/api/bible/versions"
METADATA_URL = "https://nodejs.bible.com/api/bible/version/3.3"
CHAPTER_URL = SITE + "/_next/data/{api_id}/en/bible/{bible_id}/{usfm}.{abbr}.json"

HEADERS = {"Accept": "application/json"}

#: seconds to wait between chapters when a Bible is read page by page (be kind to the server)
CHAPTER_PAUSE = 0.4

Progress = Callable[[int, int, Optional[float]], None]  # done, total, seconds left or None


def _get(url: str, **kw) -> requests.Response:
    """One place for every request, so tests can replace it."""
    kw.setdefault("headers", HEADERS)
    return netutil.get(url, **kw)


def _json(r: requests.Response):
    try:
        return r.json()
    except ValueError:
        raise netutil.NetworkError("Bible.com sent something we could not read.")


def fetch_languages(cancel: Optional[threading.Event] = None) -> list[dict]:
    """[{"tag": "nld", "native": "Nederlands", "english": "Dutch"}, …]"""
    data = _json(_get(CONFIG_URL, cancel=cancel))
    try:
        versions = data["response"]["data"]["default_versions"]
    except (KeyError, TypeError):
        raise netutil.NetworkError("Bible.com sent something we could not read.")
    out = []
    for v in versions:
        tag = v.get("language_tag")
        if not tag:
            continue
        out.append({"tag": tag, "native": v.get("local_name") or v.get("name") or tag,
                    "english": v.get("name") or v.get("local_name") or tag})
    return out


def fetch_versions(tag: str, cancel: Optional[threading.Event] = None) -> list[Entry]:
    data = _json(_get(VERSIONS_URL, params={"language_tag": tag, "type": "all"}, cancel=cancel))
    try:
        items = data["response"]["data"]["versions"]
    except (KeyError, TypeError):
        raise netutil.NetworkError("Bible.com sent something we could not read.")
    out = []
    for v in items:
        vid = v.get("id")
        if vid is None:
            continue
        out.append(Entry(
            key=f"biblecom:{vid}", source="biblecom",
            name=str(v.get("local_title") or v.get("title") or vid).strip(),
            short=str(v.get("local_abbreviation") or v.get("abbreviation") or vid).strip(),
            language="", lang_code=tag, licensed=True, size_mb=None, note="",
            ref={"id": int(vid), "abbr": str(v.get("local_abbreviation") or v.get("abbreviation") or "")}))
    return out


def fetch_metadata(bible_id: int, cancel: Optional[threading.Event] = None) -> dict:
    return _json(_get(METADATA_URL, params={"id": bible_id}, cancel=cancel))


def _api_id(cancel) -> str:
    """The build id of the website, needed to ask for single chapters."""
    html = _get(SITE, cancel=cancel).text
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise netutil.NetworkError("Bible.com changed its pages. Import a file instead.")
    try:
        return json.loads(m.group(1))["buildId"]
    except (ValueError, KeyError):
        raise netutil.NetworkError("Bible.com changed its pages. Import a file instead.")


def _apply_metadata(pb: ParsedBible, meta: dict) -> None:
    pb.name = str(meta.get("local_title") or meta.get("title") or pb.name)
    pb.short = str(meta.get("local_abbreviation") or meta.get("abbreviation") or pb.short)
    lang = meta.get("language") or {}
    pb.language = str(lang.get("name") or pb.language)
    pb.lang_code = str(lang.get("iso_639_3") or lang.get("language_tag") or pb.lang_code)
    pb.direction = "rtl" if str(lang.get("text_direction") or "").lower() == "rtl" else "ltr"
    pb.copyright = str(meta.get("copyright_long") or meta.get("copyright_short") or "").strip()
    seen_short: set[str] = set()
    for b in meta.get("books") or []:
        num = book_number(str(b.get("usfm") or ""))
        if not num:
            continue
        long_ = str(b.get("human_long") or b.get("human") or "")
        short = str(b.get("human") or long_)
        if short in seen_short:      # two books with the same short name: use the long one
            short = long_
        seen_short.add(short)
        pb.book_names[num] = (long_, short, str(b.get("abbreviation") or short))


def _chapter_total(meta: dict) -> int:
    total = 0
    for b in meta.get("books") or []:
        if book_number(str(b.get("usfm") or "")):
            total += len(b.get("chapters") or [])
    return total


class _Rate:
    """Estimates the time left from the speed so far."""

    def __init__(self):
        self.start = time.monotonic()

    def eta(self, done: int, total: int) -> Optional[float]:
        if done < 3 or total <= done:
            return None
        per = (time.monotonic() - self.start) / done
        return per * (total - done)


def download(entry: Entry, cancel: Optional[threading.Event] = None,
             progress: Optional[Progress] = None, pause: float = CHAPTER_PAUSE) -> ParsedBible:
    """Downloads one Bible. Raises NetworkError, Cancelled or BibleError."""
    meta = fetch_metadata(entry.ref["id"], cancel)
    pb = ParsedBible(name=entry.name, short=entry.short, language=entry.language, lang_code=entry.lang_code)
    _apply_metadata(pb, meta)
    total = max(_chapter_total(meta), 1)
    if progress:
        progress(0, total, None)
    rate = _Rate()
    done = 0

    def chapter_done() -> None:
        nonlocal done
        done += 1
        if progress:
            progress(done, total, rate.eta(done, total))

    offline = meta.get("offline")
    if isinstance(offline, dict) and offline.get("url"):
        try:
            raw = netutil.download("https:" + offline["url"], cancel=cancel)
            _read_offline_zip(raw, pb, chapter_done, cancel)
        except (zipfile.BadZipFile, netutil.NetworkError) as e:
            if isinstance(e, netutil.NetworkError) and e.offline:
                raise
            pb.verses.clear()          # start again page by page
            done = 0
            rate = _Rate()
            _read_pages(meta, entry, pb, chapter_done, cancel, pause)
    else:
        _read_pages(meta, entry, pb, chapter_done, cancel, pause)
    pb.validate()
    return pb


def _read_offline_zip(raw: bytes, pb: ParsedBible, chapter_done, cancel) -> None:
    zf = zipfile.ZipFile(io.BytesIO(raw))
    for name in sorted(zf.namelist()):
        if not name.lower().endswith(".yves"):
            continue
        netutil.check(cancel)
        p = PurePosixPath(name)
        html = decode_yves_bytes(zf.read(name))
        add_chapter(html, p.parent.name, pb)
        chapter_done()


def _read_pages(meta: dict, entry: Entry, pb: ParsedBible, chapter_done, cancel, pause: float) -> None:
    books = meta.get("books") or []
    if not books or not (books[0].get("chapters") or []):
        raise BibleError("Bible.com did not list the chapters of this Bible.")
    api_id = _api_id(cancel)
    abbr = str(entry.ref.get("abbr") or pb.short)
    usfm: Optional[str] = books[0]["chapters"][0]["usfm"]
    seen: set[str] = set()
    while usfm and usfm not in seen:
        seen.add(usfm)
        netutil.check(cancel)
        url = CHAPTER_URL.format(api_id=api_id, bible_id=entry.ref["id"], usfm=usfm, abbr=abbr)
        data = _json(_get(url, cancel=cancel, retries=5, backoff=3.0))
        props = data.get("pageProps") or {}
        info = props.get("chapterInfo")
        if "__N_REDIRECT" in props or info is None:
            data = _json(_get(url, params={"version": entry.ref["id"], "usfm": f"{usfm}.{abbr}"}, cancel=cancel))
            props = data.get("pageProps") or {}
            info = props.get("chapterInfo")
        if not info:
            raise netutil.NetworkError("Bible.com changed its pages. Import a file instead.")
        add_chapter(html.unescape(str(info.get("content") or "")), usfm.split(".")[0], pb)
        chapter_done()
        nxt = info.get("next")
        usfm = nxt["usfm"][0] if nxt else None
        if usfm:
            netutil.sleep(pause, cancel)
