"""What every source produces before it is saved: one Bible as book > chapter > verse > text."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .books import BOOKS

MAX_CHAPTER = 200
MAX_VERSE = 200
MIN_BOOKS = 20  # a Bible with fewer books is refused (at least the New Testament or 20 books)


class BibleError(Exception):
    """A problem a volunteer can read (the message is shown as it is)."""


@dataclass
class Entry:
    """One Bible in a catalog (not downloaded yet)."""
    key: str                 # "getbible:kjv", "ebible:engwebp", "biblecom:1"
    source: str              # "getbible", "ebible" or "biblecom"
    name: str
    short: str
    language: str            # English name of the language ("Dutch")
    lang_code: str = ""
    licensed: bool = False
    size_mb: float | None = None
    note: str = ""           # "NT only"
    ref: dict = field(default_factory=dict)  # what the source needs to download it
    language_native: str = ""  # "Nederlands" when the catalog knows it


# Characters XML cannot hold (everything below 0x20 except tab, line feed and carriage return).
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")   # also lone surrogates: they cannot be saved

# Names Windows will not accept as a file name (with or without an extension).
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def xml_safe(text: str) -> str:
    """Text without the control characters that make an XML file invalid."""
    return _CONTROL.sub("", text or "")


def safe_file_stem(text: str, limit: int = 80) -> str:
    """A name that is safe as a file name on Mac and Windows (no forbidden characters, no reserved names)."""
    t = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", text or "").strip(" .")[:limit].strip(" .")
    if not t:
        return "Bible"
    if t.split(".")[0].upper() in WINDOWS_RESERVED:
        t = "_" + t
    return t


_MARKUP = re.compile(r"<!--.*?-->|<\?.*?\?>|<(/?)([A-Za-z][A-Za-z0-9:_.-]*)([^<>]*)>", re.S)
_TAG_NAMES = {"a", "b", "i", "u", "em", "strong", "span", "br", "p", "div", "sup", "sub", "font", "small", "big", "center",
              "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "table", "tr", "td", "th", "note", "ref", "q", "l", "lg",
              "lb", "w", "add", "wj", "nd", "sc", "title", "seg", "hi", "foreign", "catchword", "reference", "verse", "chapter",
              "milestone", "fi", "rf", "cm", "ts", "wh", "wg"}
_SEPARATING = {"br", "p", "div", "li", "tr", "td", "th", "l", "lg", "lb", "q", "h1", "h2", "h3", "h4", "h5", "h6"}


def _markup(m: "re.Match") -> str:
    name = m.group(2)
    if name is None:                        # a comment or a processing instruction
        return ""
    low = name.lower()
    # a real tag: a closing or self-closing tag, one with attributes or digits (<WH430>), or a known one.
    # A plain word in angle brackets (<is>, <not>: words a translation adds) is text and stays.
    if m.group(1) or m.group(3).strip() or any(c.isdigit() for c in name) or low in _TAG_NAMES:
        return " " if low in _SEPARATING else ""
    return m.group(0)


def clean_text(text: str) -> str:
    """Removes leftover markup and tidies spaces in one verse."""
    t = xml_safe(text or "")
    if "<" in t:
        t = _MARKUP.sub(_markup, t)
    t = t.replace("¶", "")
    t = re.sub(r"\s+", " ", t)
    return t.strip()


@dataclass
class ParsedBible:
    name: str = ""
    short: str = ""          # "KJV"
    language: str = ""       # English name of the language, "Dutch"
    lang_code: str = ""      # "en", "eng", "nld"
    direction: str = "ltr"
    copyright: str = ""
    # book number (1..66) > chapter > verse > text
    verses: dict[int, dict[int, dict[int, str]]] = field(default_factory=dict)
    # book number > (long name, short name, abbreviation) in the Bible's own language
    book_names: dict[int, tuple[str, str, str]] = field(default_factory=dict)
    # Bible.com Bibles only: the USX of every book as the original tool made it (headings, verse ranges and all
    # books kept) and the Bible.com details it needs. When these are there, the ProPresenter file is made from them.
    usx: dict[str, bytes] = field(default_factory=dict)
    source_meta: dict = field(default_factory=dict)

    def add(self, book: int, chapter: int, verse: int, text: str) -> None:
        t = clean_text(text)
        if not (1 <= book <= 66 and 1 <= chapter < MAX_CHAPTER and 1 <= verse < MAX_VERSE) or not t:
            return
        chapters = self.verses.setdefault(book, {})
        vs = chapters.setdefault(chapter, {})
        old = vs.get(verse, "")
        vs[verse] = f"{old} {t}" if old else t

    @property
    def verse_count(self) -> int:
        return sum(len(vs) for ch in self.verses.values() for vs in ch.values())

    @property
    def book_count(self) -> int:
        return len(self.verses)

    def validate(self) -> None:
        """Raises BibleError when this is not a usable Bible. Called before anything is saved."""
        if self.verse_count == 0:
            raise BibleError("No verses were found in this Bible.")
        if self.book_count < MIN_BOOKS:
            raise BibleError(f"This Bible has only {self.book_count} books, so it was not added.")

    def dense(self) -> dict[str, list[list[str]]]:
        """books["43"][2][15] is John 3:16 (1-based positions; a missing verse is "")."""
        out: dict[str, list[list[str]]] = {}
        for b, chapters in self.verses.items():
            rows: list[list[str]] = []
            for c in range(1, max(chapters) + 1):
                vs = chapters.get(c, {})
                top = max(vs) if vs else 0
                rows.append([vs.get(v, "") for v in range(1, top + 1)])
            out[str(b)] = rows
        return out

    def name_of(self, book: int, kind: int = 0) -> str:
        """Book name in the Bible's own language when known, else English. kind: 0 long, 1 short, 2 abbr."""
        names = self.book_names.get(book)
        if names and names[kind]:
            return names[kind]
        return BOOKS[book - 1][1 if kind == 0 else 2]


def from_dense(books: dict[str, list[list[str]]]) -> dict[int, dict[int, dict[int, str]]]:
    out: dict[int, dict[int, dict[int, str]]] = {}
    for key, chapters in books.items():
        try:
            b = int(key)
        except ValueError:
            continue
        for ci, vs in enumerate(chapters):
            for vi, t in enumerate(vs):
                if t:
                    out.setdefault(b, {}).setdefault(ci + 1, {})[vi + 1] = t
    return out
