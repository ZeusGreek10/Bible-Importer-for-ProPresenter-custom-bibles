"""Problems found in the second review of the whole code (each one was shown with an input first)."""

import io
import json
import time
import zipfile
from pathlib import Path

import pytest

from lpbibles import biblecom, catalog, export_lp, export_pp, importers, library, model, netutil, usfm
from lpbibles import windows_helper as wh
from lpbibles.model import BibleError, Entry, ParsedBible, clean_text

import test_biblecom as T


def full(text="x", short="TB"):
    pb = ParsedBible(name="T", short=short, language="English", lang_code="eng")
    for b in range(1, 67):
        pb.add(b, 1, 1, text)
    return pb


def test_words_in_angle_brackets_are_kept_but_markup_goes():
    assert clean_text("The Lord <is> my shepherd; I shall <not> want") == "The Lord <is> my shepherd; I shall <not> want"
    assert clean_text("3 < 4 and 5 > 2") == "3 < 4 and 5 > 2"
    assert clean_text("In the <i>beginning</i> God<WH430> made<br/>it <!-- note -->now <span class='x'>ok</span>") == \
        "In the beginning God made it now ok"


def test_the_zefania_words_are_not_lost_end_to_end():
    z = (b'<XMLBIBLE biblename="X"><BIBLEBOOK bnumber="1"><CHAPTER cnumber="1"><VERS vnumber="1">The Lord &lt;is&gt; my shepherd'
         b'</VERS></CHAPTER></BIBLEBOOK></XMLBIBLE>')
    assert importers.parse_zefania(z).verses[1][1][1] == "The Lord <is> my shepherd"


def test_an_unclosed_footnote_does_not_swallow_the_next_verses():
    pb = ParsedBible()
    usfm.parse_book("\\id GEN\n\\c 1\n\\v 1 One \\f + \\ft note\n\\v 2 Two\n\\v 3 Three\n\\v 4 Four \\f + \\ft ok\\f* end\n\\v 5 Five", pb)
    v = pb.verses[1][1]
    assert sorted(v) == [1, 2, 3, 4, 5] and v[2] == "Two" and v[4] == "Four end" and v[1] == "One"
    # and it stays quick with many of them
    big = "\\id GEN\n\\c 1\n" + "".join(f"\\v {i} word \\f + \\ft x\n" for i in range(1, 3000))
    t0 = time.time()
    usfm.parse_book(big, ParsedBible())
    assert time.time() - t0 < 3


def test_line_breaks_comments_and_titles_in_zefania_and_osis():
    z = (b'<XMLBIBLE><BIBLEBOOK bnumber="1"><CHAPTER cnumber="1"><VERS vnumber="1">Blessed is the man<BR/>that walketh'
         b'<!-- editorial --> not<?pi proc?></VERS><VERS vnumber="2"><title>Heading</title>Text</VERS></CHAPTER></BIBLEBOOK></XMLBIBLE>')
    pb = importers.parse_zefania(z)
    assert pb.verses[1][1][1] == "Blessed is the man that walketh not" and pb.name == ""
    o = (b'<osis><osisText osisIDWork="KJV"><div osisID="Gen"><chapter osisID="Gen.1"><verse osisID="KJV:Gen.1.1">Line one<lb/>line two'
         b'</verse></chapter></div></osisText></osis>')
    assert importers.parse_osis(o).verses[1][1][1] == "Line one line two"


def test_bible_com_odd_pages_do_not_throw_away_the_download(monkeypatch):
    monkeypatch.setattr(model, "MIN_BOOKS", 1)
    entry = Entry(key="biblecom:1", source="biblecom", name="x", short="x", language="", ref={"id": 1, "abbr": "NBV21"})
    for bad in ("", "   ", '<div class="chapter"><div class="p"><span class="verse v1"><span class="label">1</span>'
                '<span class="content">x</span></span></div></div>',
                '<div class="chapter" data-usfm="JHN.1"><div class="p"><span class="verse v1"><span class="label"></span>'
                '<span class="content">x</span></span></div></div>'):
        T.fake_site(monkeypatch, {"JHN.1": T.page(bad, None)})
        try:
            biblecom.download(entry, pause=0)
        except BibleError:
            pass                              # "no verses found" is a plain message; a crash would be another type
    T.fake_site(monkeypatch, {"JHN.1": T.page(T.CHAPTER_JHN_1, "JHN.2"), "JHN.2": T.page("", None)})
    assert biblecom.download(entry, pause=0).verse_count == 3        # the good chapter is kept, the empty one is skipped


def test_a_lone_surrogate_is_removed_and_the_bible_saves_and_exports(tmp_path):
    pb = importers.parse_bytes(json.dumps({"books": [{"nr": b, "chapters": [{"chapter": 1, "verses": [{"verse": 1,
                               "text": "ab\\ud800cd"}]}]} for b in range(1, 67)]}).replace("\\\\ud800", "\\ud800").encode(), "a.json")
    assert pb.verses[1][1][1] == "abcd"
    pb.name = "Bad \ud800 name"
    lib = library.Library(tmp_path / "lib")
    saved = lib.save(pb, "file", "")
    assert saved.name == "Bad  name" and lib.load(saved.code).verse_count == 66
    export_pp.write_rvbible(pb, tmp_path / "x.rvbible")
    export_lp.write(pb, tmp_path / "x.json")


def test_a_bible_called_index_is_not_overwritten_by_the_index(tmp_path):
    lib = library.Library(tmp_path)
    saved = lib.save(full(short="INDEX"), "file", "")
    assert saved.code != "index"
    assert library.Library(tmp_path).load(saved.code).verse_count == 66


def test_an_empty_answer_never_replaces_a_good_list(tmp_path):
    good = [Entry(key="k", source="getbible", name="A", short="A", language="English")]
    path = tmp_path / "c.json"
    assert catalog._cached(path, lambda: good, 1000.0)[0] == good
    later = 1000.0 + catalog.MAX_AGE + 5
    entries, stale, failed = catalog._cached(path, lambda: [], later)          # a maintenance page: no entries
    assert entries == good and stale and not failed
    entries, stale, failed = catalog._cached(tmp_path / "none.json", lambda: [], later)
    assert entries == [] and failed                                               # nothing saved as "fresh"
    assert not (tmp_path / "none.json").exists()


def test_a_half_copied_bible_folder_is_removed_again(tmp_path, monkeypatch):
    import shutil
    f = tmp_path / "PD" / "RenewedVision" / "ProPresenter" / "Bibles"
    f.mkdir(parents=True)
    (f / "BibleData.proPref").write_text('InstalledBiblesNew=["6fb4fb55-78a4-43bc-ac6a-076818c7abfc|BB|A|1"];\n', encoding="utf-8")
    p = wh.prepare([full()], ["RVA"], tmp_path / "Ready", f)
    real = shutil.copytree
    def half(src, dst, *a, **k):
        Path(dst).mkdir()
        (Path(dst) / "one.usx").write_text("x")
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(shutil, "copytree", half)
    with pytest.raises(BibleError):
        wh.install(p, running=lambda: False)
    assert [x.name for x in f.iterdir()] == ["BibleData.proPref"]


def test_damaged_files_give_plain_messages(tmp_path):
    def zipped(**files):
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w") as z:
            for n, d in files.items():
                z.writestr(n.replace("_", "."), d)
        return b.getvalue()
    cases = {"a.zip": zipped(rvmetadata_xml=b"garbage", GEN_usx=b"garbage"),
             "b.json": b"[" * 100000,
             "c.xml": b"<usx>garbage",
             "d.json": json.dumps({"books": [{"nr": 1, "chapters": 5}]}).encode(),
             "e.json": b'{"books": {"\xc2\xb2": {"nr": 1}}}'}
    for name, data in cases.items():
        p = tmp_path / name
        p.write_bytes(data)
        with pytest.raises(BibleError):
            importers.read_files([p])


def test_a_zip_that_is_far_too_big_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(importers, "MAX_FILE", 1024 * 1024)
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("a.usfm", b"\\id GEN\n" + b" " * (5 * 1024 * 1024))
    p = tmp_path / "bomb.zip"
    p.write_bytes(b.getvalue())
    with pytest.raises(BibleError) as e:
        importers.read_files([p])
    assert "too big" in str(e.value)


def test_a_content_length_that_is_not_a_number_is_ignored(monkeypatch):
    class R:
        status_code = 200
        headers = {"Content-Length": "abc"}
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def iter_content(self, n): yield b"data"
    monkeypatch.setattr(netutil.requests, "get", lambda *a, **k: R())
    assert netutil.download("https://example.invalid/x") == b"data"
