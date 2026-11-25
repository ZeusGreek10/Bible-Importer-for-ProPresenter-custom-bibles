import io
import json
import threading
import zipfile

import pytest

from lpbibles import biblecom, netutil
from lpbibles.biblecom_html import add_chapter, decode_yves_bytes
from lpbibles.model import BibleError, Entry, ParsedBible

# A chapter page in the shape Bible.com serves (class names as the original tool expects them).
CHAPTER_JHN_1 = """
<div class="ChapterContent_chapter__abc chapter ch1" data-usfm="JHN.1">
  <div class="ChapterContent_label__x label">1</div>
  <div class="ChapterContent_s1__y s1"><span class="ChapterContent_heading__z heading">The Word</span></div>
  <div class="p">
    <span class="verse v1" data-usfm="JHN.1.1"><span class="label">1</span><span class="content">In the beginning was the Word,</span></span>
    <span class="verse v2" data-usfm="JHN.1.2"><span class="label">2</span><span class="content"> and the Word  was with God. ¶</span></span>
  </div>
  <div class="q">
    <span class="verse v3 v4" data-usfm="JHN.1.3+JHN.1.4"><span class="label">3-4</span><span class="content">All things were made through him.</span></span>
  </div>
</div>
"""

CHAPTER_BAD_NUMBER = '<div class="chapter" data-usfm="JHN.intro"><div class="p"><span class="verse v1"><span class="label">1</span><span class="content">x</span></span></div></div>'


def test_chapter_page_is_read():
    pb = ParsedBible()
    assert add_chapter(CHAPTER_JHN_1, "JHN", pb)
    assert pb.verses[43][1][1] == "In the beginning was the Word,"
    assert pb.verses[43][1][2] == "and the Word was with God."          # spaces tidied, ¶ removed
    assert pb.verses[43][1][3] == "All things were made through him."   # range label "3-4" is kept at verse 3


def test_odd_pages_are_skipped_not_fatal():
    pb = ParsedBible()
    assert not add_chapter(CHAPTER_BAD_NUMBER, "JHN", pb)
    assert not add_chapter("<p>nothing here</p>", "JHN", pb)
    assert not add_chapter(CHAPTER_JHN_1, "XYZ", pb)      # a book outside the 66
    assert pb.verse_count == 0


def _scramble(plain: bytes) -> bytes:
    """The reverse of decode_yves_bytes (to make a test file)."""
    out = bytearray(plain)
    n = len(out)

    def inv(b):  # inverse of ((b >> 5) | (b << 3)) & 0xFF is a rotate right by 3 ... i.e. rotate left by 5
        return ((b << 5) | (b >> 3)) & 0xFF
    for i in range(0, n, 2):
        j = i + 1
        if n > j:
            a, b = out[i], out[j]
            out[i] = inv(b)
            out[j] = inv(a)
        else:
            out[i] = inv(out[i])
    return bytes(out)


def test_yves_roundtrip():
    text = CHAPTER_JHN_1.encode("utf-8")
    assert decode_yves_bytes(_scramble(text)) == CHAPTER_JHN_1


META = {
    "title": "New Bible", "local_title": "Nieuwe Bijbel", "abbreviation": "NB", "local_abbreviation": "NBV21",
    "language": {"name": "Dutch", "iso_639_3": "nld", "text_direction": "ltr", "language_tag": "nld"},
    "copyright_long": "© Test publisher", "offline": None,
    "books": [{"usfm": "JHN", "human": "Johannes", "human_long": "Evangelie volgens Johannes", "abbreviation": "Joh",
               "chapters": [{"usfm": "JHN.1"}, {"usfm": "JHN.2"}]},
              {"usfm": "TOB", "human": "Tobit", "human_long": "Tobit", "abbreviation": "Tob", "chapters": [{"usfm": "TOB.1"}]}],
}


class FakeResponse:
    def __init__(self, payload=None, text=""):
        self._p, self.text, self.status_code = payload, text, 200

    def json(self):
        return self._p


def fake_site(monkeypatch, pages):
    calls = []

    def fake_get(url, **kw):
        calls.append(url)
        if url == biblecom.METADATA_URL:
            return FakeResponse(META)
        if url == biblecom.SITE:
            return FakeResponse(text='<html><script id="__NEXT_DATA__" type="application/json">{"buildId": "B1"}</script></html>')
        for usfm, body in pages.items():
            if f"/{usfm}." in url:
                return FakeResponse(body)
        raise netutil.NetworkError("The server answered 404.")
    monkeypatch.setattr(biblecom, "_get", fake_get)
    return calls


def page(content, nxt):
    return {"pageProps": {"chapterInfo": {"content": content, "next": {"usfm": [nxt]} if nxt else None}}}


def test_download_page_by_page_with_progress(monkeypatch):
    monkeypatch.setattr("lpbibles.model.MIN_BOOKS", 1)   # the sample has one book
    fake_site(monkeypatch, {"JHN.1": page(CHAPTER_JHN_1, "JHN.2"),
                            "JHN.2": page(CHAPTER_JHN_1.replace("JHN.1", "JHN.2").replace('ch1', 'ch2'), None)})
    seen = []
    entry = Entry(key="biblecom:1", source="biblecom", name="x", short="x", language="", ref={"id": 1, "abbr": "NBV21"})
    pb = biblecom.download(entry, progress=lambda d, t, eta: seen.append((d, t)), pause=0)
    assert seen[0] == (0, 2) and seen[-1] == (2, 2)          # the book outside the 66 is not counted
    assert pb.name == "Nieuwe Bijbel" and pb.short == "NBV21" and pb.lang_code == "nld"
    assert pb.book_names[43][0] == "Evangelie volgens Johannes" and pb.copyright.startswith("©")
    assert pb.verses[43][1][1].startswith("In the beginning")


def test_download_can_be_cancelled(monkeypatch):
    fake_site(monkeypatch, {"JHN.1": page(CHAPTER_JHN_1, "JHN.2")})
    cancel = threading.Event()
    entry = Entry(key="biblecom:1", source="biblecom", name="x", short="x", language="", ref={"id": 1, "abbr": "NBV21"})

    def progress(d, t, eta):
        if d == 1:
            cancel.set()
    with pytest.raises(netutil.Cancelled):
        biblecom.download(entry, cancel=cancel, progress=progress, pause=0)


def test_site_change_gives_a_plain_message(monkeypatch):
    calls = fake_site(monkeypatch, {"JHN.1": {"pageProps": {"chapterInfo": None}}})
    entry = Entry(key="biblecom:1", source="biblecom", name="x", short="x", language="", ref={"id": 1, "abbr": "NBV21"})
    with pytest.raises((netutil.NetworkError, BibleError)):
        biblecom.download(entry, pause=0)


def test_offline_zip(monkeypatch):
    meta = dict(META, offline={"url": "//example.invalid/nbv.zip"})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("JHN/1.yves", _scramble(CHAPTER_JHN_1.encode()))
    monkeypatch.setattr(biblecom, "fetch_metadata", lambda i, c=None: meta)
    monkeypatch.setattr(netutil, "download", lambda url, **kw: buf.getvalue())
    entry = Entry(key="biblecom:1", source="biblecom", name="x", short="x", language="", ref={"id": 1, "abbr": "NBV21"})
    with pytest.raises(BibleError):         # one chapter only: refused by the size check, after reading it
        biblecom.download(entry, pause=0)


def test_language_and_version_lists(monkeypatch):
    def fake_get(url, **kw):
        if url == biblecom.CONFIG_URL:
            return FakeResponse({"response": {"data": {"default_versions": [
                {"language_tag": "nld", "local_name": "Nederlands", "name": "Dutch"}]}}})
        return FakeResponse({"response": {"data": {"versions": [
            {"id": 75, "local_title": "Nieuwe Bijbelvertaling 2021", "local_abbreviation": "NBV21"}]}}})
    monkeypatch.setattr(biblecom, "_get", fake_get)
    assert biblecom.fetch_languages() == [{"tag": "nld", "native": "Nederlands", "english": "Dutch"}]
    v = biblecom.fetch_versions("nld")
    assert v[0].short == "NBV21" and v[0].licensed and v[0].ref["id"] == 75
