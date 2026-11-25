"""Reads USFM (the format of eBible.org downloads) into a ParsedBible.

Only verse text is kept. Headings, notes, cross references, Strong's numbers and
other markup are left out.
"""

from __future__ import annotations

import io
import re
import zipfile
from typing import Optional

from .books import book_number
from .model import BibleError, ParsedBible

# Notes and the like: removed together with their content.
_NOTE_SPANS = re.compile(
    r"\\(f|fe|ef|x|ex|fig|va|vp|ca|cp|zw|esb)\b.*?\\\1\*", re.S)
# Markers that carry attributes after a "|" (\w word|strong="G1"\w*): keep the word, drop the attributes.
_ATTRS = re.compile(r"\|[^\\|]*(?=\\[+a-z0-9]+\*)", re.I)
# Closing character markers, and opening ones (one following space goes with them).
# Milestones: \\ts\\*, \\zaln-s |x-strong="H1"\\*, \\zaln-e\\* … (they carry no text: removed, so the text after them is kept)
_MILESTONE = re.compile(r"\\[A-Za-z][A-Za-z0-9\-]*(?:\s+[^\\]*)?\\\*")
_CLOSE = re.compile(r"\\[+a-z0-9]+\*", re.I)
_CHAR_OPEN = re.compile(
    r"\\\+?(w|wg|wh|wa|nd|add|wj|bk|qt|sc|tl|em|bd|it|bdit|no|sig|k|dc|ord|pn|png|addpn|lit|sup|ior|iqt|qs|"
    r"qac|jmp|ndx|pro|rb|rq|sls|fv|fk|fq|fqa|fl|fm|ft|fr|fp|xo|xk|xq|xt|xta|xop|xot|xnt|xdc|ca)(?=[\s\\])[ ]?")
# A marker at the start of a piece of text.
_MARKER = re.compile(r"\\([a-z]+[0-9]?)(?=[\s\\]|$)", re.I)
# Paragraph and poetry markers: their text belongs to the current verse.
_BODY = {"p", "m", "mi", "nb", "pi", "pi1", "pi2", "pi3", "pc", "pr", "pmo", "pm", "pmc", "pmr", "cls",
         "q", "q1", "q2", "q3", "q4", "qr", "qc", "qa", "qm", "qm1", "qm2", "qm3", "b", "li", "li1", "li2",
         "li3", "li4", "lh", "lf", "lim", "lim1", "lim2", "tr", "tc1", "tc2", "tc3", "th1", "th2", "th3", "tcr1",
         "tcr2", "tcr3", "tcr4"}
_VERSE = re.compile(r"\s*(\d+)([a-z]?)(?:\s*[-–,]\s*(\d+)([a-z]?))?\s*(.*)", re.S)


def parse_book(text: str, out: ParsedBible, default_book: int = 0) -> None:
    """Adds the verses of one USFM book (one .usfm file) to `out`."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _MILESTONE.sub("", text)
    text = _NOTE_SPANS.sub("", text)
    text = _ATTRS.sub("", text)
    text = _CLOSE.sub("", text)
    text = _CHAR_OPEN.sub("", text)

    book = default_book
    chapter = 0
    verse = 0
    buf: list[str] = []

    def flush() -> None:
        if book and chapter and verse and buf:
            out.add(book, chapter, verse, " ".join(buf))
        buf.clear()

    pos = 0
    matches = list(_MARKER.finditer(text))
    for i, m in enumerate(matches):
        marker = m.group(1).lower()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[m.end():end]
        if marker == "id":
            flush()
            code = content.strip().split()[0] if content.strip() else ""
            b = book_number(code)
            book = b if b else (default_book if not code else 0)
            chapter = verse = 0
        elif marker == "c":
            flush()
            mm = re.match(r"\s*(\d+)", content)
            chapter = int(mm.group(1)) if mm else chapter + 1
            verse = 0
        elif marker == "v":
            flush()
            mm = _VERSE.match(content)
            if mm:
                verse = int(mm.group(1))
                buf.append(mm.group(5))
            else:
                verse = 0
        elif marker in _BODY:
            if verse and content.strip():
                buf.append(content)
        # every other marker (headings, titles, intro, remarks…) is skipped
    flush()


def parse_zip(data: bytes, out: Optional[ParsedBible] = None) -> ParsedBible:
    """Reads an eBible `*_usfm.zip`: one .usfm / .sfm file per book."""
    out = out or ParsedBible()
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise BibleError("The downloaded file is not a valid zip file.")
    names = sorted(n for n in zf.namelist() if n.lower().endswith((".usfm", ".sfm", ".usf"))
                   and not n.startswith("__MACOSX/") and "/__MACOSX/" not in n and not n.rsplit("/", 1)[-1].startswith("._"))
    if not names:
        raise BibleError("The zip file has no USFM books in it.")
    for n in names:
        raw = zf.read(n)
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        parse_book(text, out)
    return out
