"""One test for each problem found in the code review (they must not come back)."""

import io
import json
import zipfile
from pathlib import Path

import pytest

from lpbibles import export_lp, export_pp, getbible, importers, usfm
from lpbibles.library import Library, make_code
from lpbibles.model import BibleError, ParsedBible, clean_text, safe_file_stem


def bible(name="Test Bible", short="TB", text="x", books=66):
    pb = ParsedBible(name=name, short=short, language="English", lang_code="eng")
    for b in range(1, books + 1):
        for v in (1, 2):
            pb.add(b, 1, v, f"{text} {b}.{v}")
    return pb


# ---- 1. a copy that fails half way must not leave a half file in ProPresenter's folder -------------------

def test_a_failed_copy_leaves_nothing_behind(tmp_path, monkeypatch):
    src = tmp_path / "KJV.rvbible"
    src.write_bytes(b"x" * 1000)
    folder = tmp_path / "pp"
    real = Path.write_bytes

    def cut(self, data):
        real(self, data[:100])
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(Path, "write_bytes", cut)
    with pytest.raises(OSError):
        export_pp.copy_without_overwriting(src, folder)
    monkeypatch.undo()
    assert list(folder.iterdir()) == []                   # no KJV.rvbible, no temporary file either


def test_copy_makes_the_whole_file_and_no_leftovers(tmp_path):
    src = tmp_path / "KJV.rvbible"
    src.write_bytes(b"abc" * 100)
    dest = export_pp.copy_without_overwriting(src, tmp_path / "pp")
    assert dest.read_bytes() == src.read_bytes() and [p.name for p in dest.parent.iterdir()] == ["KJV.rvbible"]


def test_mac_install_falls_back_to_the_per_user_folder(tmp_path, monkeypatch):
    src = tmp_path / "KJV.rvbible"
    src.write_bytes(b"abc")
    system, user = tmp_path / "system", tmp_path / "home" / export_pp.MAC_RELATIVE
    monkeypatch.setattr(export_pp, "mac_bible_folder", lambda *a, **k: system)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    real = export_pp.copy_without_overwriting

    def fake(s, folder):
        if Path(folder) == system:
            raise PermissionError("needs an administrator")
        return real(s, folder)
    monkeypatch.setattr(export_pp, "copy_without_overwriting", fake)
    assert export_pp.install_mac(src) == user / "KJV.rvbible"


# ---- 2. a damaged index must not let a new Bible replace a saved one ----------------------------------

def test_damaged_index_keeps_every_saved_bible(tmp_path):
    lib = Library(tmp_path)
    lib.save(bible("Old Bible", "KJV", "OLD TEXT"), "getbible", "getbible:kjv")
    (tmp_path / "Bibles" / "index.json").write_text("{broken", encoding="utf-8")

    again = Library(tmp_path)                                            # the app starts again
    assert [i.code for i in again.items] == ["kjv"]                       # still listed
    assert again.get("kjv").source_key == "getbible:kjv" and again.get("kjv").name == "Old Bible"   # what it was is recovered
    assert list((tmp_path / "Bibles").glob("index.json.bad-*"))           # the damaged one is kept for a look
    new = again.save(bible("A Different Bible", "KJV", "NEW TEXT"), "file", "")
    assert new.code == "kjv-2"                                            # a new name: nothing is replaced
    assert "OLD TEXT" in (tmp_path / "Bibles" / "kjv.json").read_text(encoding="utf-8")


def test_a_bible_file_the_index_forgot_is_listed_again(tmp_path):
    lib = Library(tmp_path)
    lib.save(bible("One", "ONE"), "file", "")
    (tmp_path / "Bibles" / "index.json").unlink()
    assert [i.code for i in Library(tmp_path).items] == ["one"]


def test_save_never_takes_the_name_of_a_file_that_is_there(tmp_path):
    lib = Library(tmp_path)
    (tmp_path / "Bibles" / "tb.json").write_text("some other file", encoding="utf-8")   # not a Bible of ours
    assert lib.save(bible(), "file", "").code == "tb-2"
    assert (tmp_path / "Bibles" / "tb.json").read_text(encoding="utf-8") == "some other file"


# ---- 8. names Windows cannot use -----------------------------------------------------------------------

def test_reserved_and_long_names():
    assert [safe_file_stem(x) for x in ("CON", "nul", "Com1", "AUX.txt")] == ["_CON", "_nul", "_Com1", "_AUX.txt"]
    assert safe_file_stem("a" * 300) == "a" * 80 and safe_file_stem('Bible: the "New"? one.') == "Bible the New one"
    assert safe_file_stem("..") == "Bible" and safe_file_stem("") == "Bible"
    assert make_code("CON", "") == "con-bible" and make_code("NUL", "") == "nul-bible" and make_code("KJV", "") == "kjv"


# ---- 7. control characters make an XML file invalid ----------------------------------------------------

def test_control_characters_do_not_break_the_export(tmp_path):
    pb = bible(name="Bible\x0b2", short="B\x01")
    pb.add(1, 1, 3, "text with \x01 and \x0b control characters")
    assert pb.verses[1][1][3] == "text with and control characters"
    out = export_pp.write_rvbible(pb, tmp_path / "t.rvbible")
    assert importers.read_files([out]).verse_count == pb.verse_count
    assert clean_text("a\x00b\x1fc\td") == "abc d"


# ---- 4. zips made on a Mac -----------------------------------------------------------------------------

def test_a_zip_made_on_a_mac_can_be_imported(tmp_path):
    rv = export_pp.write_rvbible(bible(), tmp_path / "t.rvbible")
    out = tmp_path / "mac.zip"
    with zipfile.ZipFile(rv) as zin, zipfile.ZipFile(out, "w") as z:
        for n in zin.namelist():
            z.writestr(n, zin.read(n))
            if n.endswith(".usx"):
                z.writestr("__MACOSX/USX_1/._" + Path(n).name, b"\x00\x05\x16\x07" + b"\x00" * 80)
    assert importers.read_files([out]).verse_count == 66 * 2


def test_a_zip_of_usfm_made_on_a_mac(tmp_path):
    out = tmp_path / "u.zip"
    with zipfile.ZipFile(out, "w") as z:
        for i in range(1, 67):
            code = ["GEN", "EXO", "LEV", "NUM", "DEU", "JOS", "JDG", "RUT", "1SA", "2SA", "1KI", "2KI", "1CH", "2CH", "EZR", "NEH", "EST", "JOB",
                    "PSA", "PRO", "ECC", "SNG", "ISA", "JER", "LAM", "EZK", "DAN", "HOS", "JOL", "AMO", "OBA", "JON", "MIC", "NAM", "HAB", "ZEP",
                    "HAG", "ZEC", "MAL", "MAT", "MRK", "LUK", "JHN", "ACT", "ROM", "1CO", "2CO", "GAL", "EPH", "PHP", "COL", "1TH", "2TH", "1TI",
                    "2TI", "TIT", "PHM", "HEB", "JAS", "1PE", "2PE", "1JN", "2JN", "3JN", "JUD", "REV"][i - 1]
            z.writestr(f"{i:02d}-{code}.usfm", f"\\id {code}\n\\c 1\n\\p\n\\v 1 Text {i}.\n")
            z.writestr(f"__MACOSX/._{i:02d}-{code}.usfm", b"\x00\x05\x16\x07binary junk \xff\xfe")
    assert importers.read_files([out]).verse_count == 66


# ---- 5. poetry lines must not be glued together -------------------------------------------------------

def test_poetry_lines_get_a_space():
    usx = (b'<usx version="2.0"><book code="PSA"/><chapter number="1"/>'
           b'<para style="q1"><verse number="1"/>Blessed is the man</para><para style="q2">who walks not</para>'
           b'<para style="p"><verse number="2"/>x</para></usx>')
    assert importers.parse_usx(usx).verses[19][1][1] == "Blessed is the man who walks not"
    usfx = b'<usfx><book id="PSA"><c id="1"/><q><v id="1"/>Blessed is the man</q><q>who walks not</q><ve/></book></usfx>'
    assert importers.parse_usfx(usfx).verses[19][1][1] == "Blessed is the man who walks not"
    osis = (b'<osis><osisText osisIDWork="x"><div type="book" osisID="Ps"><chapter osisID="Ps.1"><verse osisID="Ps.1.1">'
            b'<l>Blessed is the man</l><l>who walks not</l></verse></chapter></div></osisText></osis>')
    assert importers.parse_osis(osis).verses[19][1][1] == "Blessed is the man who walks not"


# ---- 6. USFM milestones -------------------------------------------------------------------------------

def test_usfm_milestones_do_not_eat_text():
    pb = ParsedBible()
    usfm.parse_book('\\id MAT\n\\c 1\n\\p\n\\v 1 In the \\ts\\* beginning God\n\\v 2 \\zaln-s |x-strong="H1"\\*\\w word|x\\w*\\zaln-e\\* more\n', pb)
    assert pb.verses[40][1] == {1: "In the beginning God", 2: "word more"}


# ---- 3 (in test_gui), 11, 12 and the XML parser --------------------------------------------------------

def test_json_that_is_not_an_object_is_refused_plainly(tmp_path):
    p = tmp_path / "x.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(BibleError, match="not a Bible file"):
        importers.read_files([p])


def test_xml_entities_are_not_expanded(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("SECRET-CONTENT", encoding="utf-8")
    xml = (f'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file://{secret}"><!ENTITY big "AAAA">]>'
           '<XMLBIBLE biblename="Evil"><BIBLEBOOK bnumber="1"><CHAPTER cnumber="1"><VERS vnumber="1">a &e; b &big; c</VERS>'
           '</CHAPTER></BIBLEBOOK></XMLBIBLE>').encode()
    text = importers.parse_zefania(xml).verses[1][1][1]
    assert "SECRET" not in text and "AAAA" not in text


# ---- the Windows list of ProPresenter is never rewritten when it cannot be read ----------------------------

def test_unreadable_propresenter_list_is_left_alone(tmp_path):
    bibles = tmp_path / "Bibles"
    bibles.mkdir()
    pref = bibles / "BibleData.proPref"
    pref.write_text("this is not the file we know", encoding="utf-8")
    with pytest.raises(BibleError):
        export_pp.windows_free_bibles(bibles)
    assert pref.read_text(encoding="utf-8") == "this is not the file we know"
    assert [p.name for p in bibles.iterdir()] == ["BibleData.proPref"]      # no half-made Bible folder either


# ---- license files -------------------------------------------------------------------------------------

def test_license_files_are_there_and_shipped():
    root = Path(__file__).resolve().parent.parent
    mit = (root / "LICENSE").read_text(encoding="utf-8")
    assert mit.startswith("MIT License") and 'THE SOFTWARE IS PROVIDED "AS IS"' in mit
    notice = (root / "NOTICE").read_text(encoding="utf-8")
    assert "Martijn Lentink" in notice and "NOT under the MIT" in notice and "LGPL" in notice
    # every file the notice points to is in the licenses folder
    import re
    for name in re.findall(r"licenses/([A-Za-z0-9_.\-]+\.txt)", notice):
        assert (root / "licenses" / name).exists(), name
    assert "GNU LESSER GENERAL PUBLIC LICENSE" in (root / "licenses" / "LGPL-3.0.txt").read_text(encoding="utf-8")
    spec = (root / "bible_gui.spec").read_text(encoding="utf-8")
    assert "('LICENSE', '.')" in spec and "('NOTICE', '.')" in spec and "('licenses', 'licenses')" in spec
    # the files the notice puts outside the MIT license really exist (the list stays true)
    for f in ("bible_import.py", "lpbibles/biblecom_html.py", "lpbibles/biblecom_pp.py", "lpbibles/biblecom.py", "lpbibles/export_pp.py",
              "tests/reference/bible_import_original.py", "Resources/metadata.xml", "Resources/available_bibles.json"):
        assert (root / f).exists() and f.split("/")[-1] in notice, f
