"""The Bible.com files of the app must be the files of the original tool, byte for byte.

tests/reference/bible_import_original.py is the original script (commit a181715), untouched. Its
`process_bible_files` and `construct_metadataxmls` are run on chapter pages saved in a folder, exactly as the
original ran after a download; the app's own code is run on the same pages. Every file must be identical.
"""

import importlib.util
import json
import os
import zipfile
from pathlib import Path

import pytest

for module in ("click", "tqdm", "prompt_toolkit", "requests", "lxml"):
    pytest.importorskip(module)

from lpbibles import biblecom, export_pp
from lpbibles.biblecom_pp import chapter_key
from lpbibles.library import Library
from lpbibles.model import Entry, ParsedBible

ROOT = Path(__file__).resolve().parent.parent


def load_original():
    spec = importlib.util.spec_from_file_location("bible_import_original", ROOT / "tests" / "reference" / "bible_import_original.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def page(book, chapter, verses, heading=None, extra=""):
    """A chapter page in the shape Bible.com serves it."""
    body = ""
    if heading:
        body += f'<div class="s1"><span class="heading">{heading}</span></div>'
    body += '<div class="p">'
    for label, text in verses:
        classes = " ".join("v" + str(n) for n in _numbers(label))
        body += (f'<span class="verse {classes}" data-usfm="{book}.{chapter}.{label}"><span class="label">{label}</span>'
                 f'<span class="content">{text}</span></span>')
    body += "</div>" + extra
    return f'<div class="ChapterContent_chapter__x chapter ch{chapter}" data-usfm="{book}.{chapter}">{body}</div>'


def _numbers(label):
    import re
    nums = [int(n) for n in re.findall(r"\d+", label)]
    if len(nums) == 2:
        return list(range(nums[0], nums[1] + 1))
    return nums[:1]


PAGES = {
    "GEN": {1: page("GEN", 1, [("1", "In het begin schiep God de hemel en de aarde."), ("2", "De aarde was woest en leeg.")],
                    heading="De schepping"),
            2: page("GEN", 2, [("1", "Zo werden de hemel en de aarde voltooid."), ("3-4", "Een bereik van verzen ¶ hier.")]),
            10: page("GEN", 10, [("1", "Dit is de familie van Noach.")])},     # chapter 10 must come after chapter 2
    "JHN": {1: page("JHN", 1, [("1", "In het begin was het Woord."), ("2a", "Het was bij God.")], heading="Het Woord"),
            3: page("JHN", 3, [("16", "Want zo lief heeft God de wereld gehad.")])},
    "TOB": {1: page("TOB", 1, [("1", "Een boek buiten de 66.")], heading="Tobit")},   # an extra book is kept
}

META = {
    "title": "New Bible", "local_title": "Nieuwe Bijbel", "abbreviation": "NB", "local_abbreviation": "NBV21",
    "language": {"name": "Dutch", "iso_639_3": "nld", "text_direction": "ltr"},
    "books": [{"usfm": "GEN", "canon": "ot", "human": "Genesis", "human_long": "Het boek Genesis", "abbreviation": "Gen"},
              {"usfm": "JHN", "canon": "nt", "human": "Johannes", "human_long": "Johannes", "abbreviation": "Joh"},
              {"usfm": "TOB", "canon": "dc", "human": "Genesis", "human_long": "Tobit", "abbreviation": "Tob"}],   # same short name as GEN
}


def test_same_files_as_the_original(tmp_path, monkeypatch):
    monkeypatch.setattr("lpbibles.model.MIN_BOOKS", 1)      # the sample has two books
    monkeypatch.chdir(ROOT)           # the original looks for Resources/ in the folder it is started from
    original = load_original()

    # --- the original: chapter files in a folder, then its own conversion
    download = tmp_path / "download"
    download.mkdir()
    for book, chapters in PAGES.items():
        for number, html in chapters.items():
            (download / f"{book}.{number}").write_text(html, encoding="utf-8")
    out_original = tmp_path / "original"
    (out_original / "USX_1").mkdir(parents=True)
    original.process_bible_files(str(download), str(out_original / "USX_1"))
    original.construct_metadataxmls(str(out_original), META)

    # --- the app: the same pages, collected as the downloader collects them
    pb = ParsedBible(name="Nieuwe Bijbel", short="NBV21", language="Dutch", lang_code="nld")
    pages = {}
    for name in os.listdir(download):
        key = chapter_key(name)
        pages.setdefault(key[0], {})[key[1]] = (download / name).read_text(encoding="utf-8")
    biblecom.assemble(pb, pages, dict(META, extra_field="ignored"))
    rv = export_pp.write_rvbible(pb, tmp_path / "app.rvbible")
    out_app = tmp_path / "app"
    with zipfile.ZipFile(rv) as z:
        z.extractall(out_app)

    def files(folder):
        return {str(p.relative_to(folder)).replace(os.sep, "/"): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}

    a, b = files(out_original), files(out_app)
    assert sorted(a) == sorted(b) == ["USX_1/GEN.usx", "USX_1/JHN.usx", "USX_1/TOB.usx", "metadata.xml", "rvmetadata.xml"]
    for name in a:
        assert a[name] == b[name], f"{name} is not the same as the original"

    # the things the first version of the app lost are in the file
    gen = a["USX_1/GEN.usx"].decode("utf-8")
    assert 'style="s1">De schepping' in gen          # section heading kept
    assert 'number="3-4"' in gen                      # verse range kept as written
    assert gen.index('number="2"') < gen.index('number="10"')       # chapters in numeric order
    assert "Tobit" in a["USX_1/TOB.usx"].decode("utf-8") and b"TOB" in a["metadata.xml"]   # extra book kept

    # the verses the app uses for Live Presenter still come out of the same pages
    assert pb.verses[1][2][3] == "Een bereik van verzen hier."
    assert pb.verses[43][1][2] == "Het was bij God."
    assert 47 not in pb.verses and pb.verses[43][3][16].startswith("Want zo lief")


def test_saved_copy_exports_the_same_file(tmp_path, monkeypatch):
    """After saving to the library and loading again, the ProPresenter file is still the original's."""
    monkeypatch.setattr("lpbibles.model.MIN_BOOKS", 1)
    pb = ParsedBible(name="Nieuwe Bijbel", short="NBV21", language="Dutch", lang_code="nld")
    pages = {b: dict(ch) for b, ch in PAGES.items()}
    biblecom.assemble(pb, pages, META)
    first = export_pp.write_rvbible(pb, tmp_path / "first.rvbible")
    lib = Library(tmp_path / "lib")
    item = lib.save(pb, "biblecom", "biblecom:1")
    again = Library(tmp_path / "lib").load(item.code)
    second = export_pp.write_rvbible(again, tmp_path / "second.rvbible")
    with zipfile.ZipFile(first) as a, zipfile.ZipFile(second) as b:
        assert sorted(a.namelist()) == sorted(b.namelist())
        for n in a.namelist():
            assert a.read(n) == b.read(n), n


def test_headers_are_the_originals():
    original = load_original()
    assert biblecom.HEADERS == original.headers
