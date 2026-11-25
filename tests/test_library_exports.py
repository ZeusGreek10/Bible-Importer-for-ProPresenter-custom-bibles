import json
import time
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from lpbibles import catalog, ebible, export_lp, export_pp, getbible, netutil
from lpbibles.library import Library, default_numbering
from lpbibles.model import BibleError, Entry, ParsedBible


def big_bible(name="Test Bible", short="TB", books=66) -> ParsedBible:
    pb = ParsedBible(name=name, short=short, language="English", lang_code="eng")
    for b in range(1, books + 1):
        for c in (1, 2):
            for v in (1, 2, 3):
                pb.add(b, c, v, f"Book {b} chapter {c} verse {v}.")
    return pb


# ---- catalogs ---------------------------------------------------------------------------------------

EBIBLE_CSV = '﻿"languageCode",translationId,languageName,languageNameInEnglish,title,Redistributable,Copyright,OTbooks,NTbooks,OTverses,NTverses,downloadable,textDirection,shortTitle\n' \
    'eng,engwebp,English,English,World English Bible,True,public domain,39,27,23145,7958,True,ltr,WEB\n' \
    'nld,nld1939,Nederlands,Dutch,Statenvertaling 1939,True,PD,39,27,23000,7900,True,ltr,SV\n' \
    'aai,aai,Miniafia,Miniafia,NT only small,True,c,0,3,0,200,True,ltr,\n' \
    'eng,engnope,English,English,Not for sharing,False,c,39,27,1,1,True,ltr,\n' \
    'eng,engnt,English,English,Only the NT,True,c,0,27,0,7958,True,ltr,\n'


def test_ebible_catalog_filters():
    entries = ebible.parse_catalog(EBIBLE_CSV)
    # not redistributable and too small (3 books) are left out; a whole New Testament (27 books) is kept
    assert [e.ref["id"] for e in entries] == ["engwebp", "nld1939", "engnt"]
    assert entries[0].short == "WEBP" and entries[1].language == "Dutch" and entries[1].language_native == "Nederlands"
    assert entries[0].size_mb == 4.0 and entries[0].note == "" and entries[2].note == "NT only"


def test_getbible_catalog():
    data = {"kjv": {"translation": "King James Version", "abbreviation": "kjv", "lang": "en", "language": "English", "direction": "LTR"},
            "x": {"translation": "No abbreviation"}}
    e = getbible.parse_catalog(data)
    assert len(e) == 1 and e[0].short == "KJV" and e[0].key == "getbible:kjv"


def test_free_catalog_merges_caches_and_survives_offline(tmp_path, monkeypatch):
    gb = [Entry(key="getbible:web", source="getbible", name="World English Bible", short="WEB", language="English")]
    eb = ebible.parse_catalog(EBIBLE_CSV)
    eb[0].name = "World English Bible"          # the same Bible in both lists: getBible wins
    monkeypatch.setattr(getbible, "fetch_catalog", lambda cancel=None: gb)
    monkeypatch.setattr(ebible, "fetch_catalog", lambda cancel=None: eb)
    now = 1_000_000.0
    res = catalog.load_free(tmp_path, now=now)
    assert [e.key for e in res.entries] == ["getbible:web", "ebible:nld1939", "ebible:engnt"] and not res.stale

    def down(cancel=None):
        raise netutil.NetworkError("No internet connection.", offline=True)
    monkeypatch.setattr(getbible, "fetch_catalog", down)
    monkeypatch.setattr(ebible, "fetch_catalog", down)
    # a day later the saved list is old, the network is down: the saved list is shown with a message
    res = catalog.load_free(tmp_path, now=now + 3 * 86400)
    assert res.stale and len(res.entries) == 3
    # nothing saved and no network: a plain error
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(netutil.NetworkError):
        catalog.load_free(empty, now=now)


def test_language_order_and_names():
    entries = [Entry(key=f"k{i}", source="getbible", name=f"B{i}", short="B", language=lang)
               for i, lang in enumerate(["Dutch"] * 3 + ["Russian"] * 4 + ["English"] * 2 + ["Spanish"] * 6 + ["Zulu"])]
    langs = catalog.languages(entries, system_language="Dutch")
    assert [l.english for l in langs][:4] == ["Dutch", "English", "Russian", "Spanish"]
    assert [l.native for l in langs][:3] == ["Nederlands", "English", "Русский"]
    assert langs[-1].native == "Zulu" and langs[-1].count == 1
    assert [e.name for e in catalog.for_language(entries, "Dutch", "b1")] == ["B1"]


# ---- library ----------------------------------------------------------------------------------------

def test_library_save_load_remove_and_replace(tmp_path):
    lib = Library(tmp_path)
    item = lib.save(big_bible(), "getbible", "getbible:tb")
    assert item.code == "tb" and lib.is_installed("getbible:tb") and item.numbering == "kjv"
    lib.set_numbering("tb", "synodal")
    again = Library(tmp_path)                                  # survives a restart
    assert again.get("tb").numbering == "synodal"
    assert again.load("tb").verses[43][2][3] == "Book 43 chapter 2 verse 3."
    # downloading the same Bible again replaces it and keeps the numbering the volunteer chose
    again.save(big_bible(name="Test Bible 2"), "getbible", "getbible:tb")
    assert len(again.items) == 1 and again.get("tb").name == "Test Bible 2" and again.get("tb").numbering == "synodal"
    # another Bible with the same short name gets its own code
    second = again.save(big_bible(name="Other"), "file", "")
    assert second.code == "tb-2"
    again.remove("tb")
    assert not (tmp_path / "Bibles" / "tb.json").exists() and again.get("tb") is None and again.get("tb-2")


def test_bad_bible_is_not_saved(tmp_path):
    lib = Library(tmp_path)
    with pytest.raises(BibleError):
        lib.save(big_bible(books=5), "ebible", "ebible:x")
    assert lib.items == [] and list((tmp_path / "Bibles").glob("*.json")) == []


def test_numbering_default():
    assert default_numbering("Russian", "ru", "Синодальный перевод") == "synodal"
    assert default_numbering("English", "en", "King James Version") == "kjv"


# ---- Live Presenter export ---------------------------------------------------------------------------

def test_live_presenter_json(tmp_path):
    pb = big_bible()
    pb.book_names[43] = ("Evangelie volgens Johannes", "Johannes", "Joh")
    pb.add(43, 3, 16, "For God so loved the world.")
    out = export_lp.write(pb, tmp_path / "tb.json")
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["translation"] == "Test Bible" and d["abbreviation"] == "TB" and d["lang"] == "en"
    john = next(b for b in d["books"] if b["nr"] == 43)
    assert john["name"] == "John" and john["name_local"] == "Evangelie volgens Johannes"   # name stays English
    ch3 = next(c for c in john["chapters"] if c["chapter"] == 3)
    assert ch3["verses"] == [{"verse": 16, "text": "For God so loved the world."}]
    assert export_lp.lang2("spa") == "es" and export_lp.lang2("nl") == "nl"


# ---- ProPresenter export -----------------------------------------------------------------------------

def test_rvbible_has_the_three_parts(tmp_path):
    out = export_pp.write_rvbible(big_bible(), tmp_path / "TB.rvbible")
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert "metadata.xml" in names and "rvmetadata.xml" in names
        assert len([n for n in names if n.startswith("USX_1/") and n.endswith(".usx")]) == 66
        assert b"<!--" not in z.read("metadata.xml")                    # comments crash ProPresenter on Mac
        meta = etree.fromstring(z.read("metadata.xml"))
        assert meta.xpath("//identification/name")[0].text == "Test Bible"
        # the original leaves the template's own text in <bookList> (it works in ProPresenter); so do we
        assert meta.xpath("//bookList/name")[0].text == "Nieuwe Bijbelvertaling"
        assert len(meta.xpath("//bookNames/book")) == 66
        usx = etree.fromstring(z.read("USX_1/JHN.usx"))
        assert usx.xpath("//chapter")[1].get("number") == "2"
        assert usx.xpath("//verse")[2].tail == "Book 43 chapter 1 verse 3."
        assert etree.fromstring(z.read("rvmetadata.xml")).find("abbreviation").text == "TB"
    assert not list(tmp_path.glob("*.part"))


def test_install_mac(tmp_path):
    rv = export_pp.write_rvbible(big_bible(), tmp_path / "TB.rvbible")
    home = tmp_path / "home"
    folder = export_pp.mac_bible_folder(home=home, system_root=tmp_path / "root")   # neither exists: the user one
    assert folder == home / "Library/Application Support/RenewedVision/RVBibles/v2"
    dest = export_pp.install_mac(rv, folder)
    assert dest.exists() and dest.read_bytes() == rv.read_bytes()
    # an existing old system-wide folder is used when the per-user one is missing
    old = tmp_path / "root" / export_pp.MAC_RELATIVE
    old.mkdir(parents=True)
    assert export_pp.mac_bible_folder(home=tmp_path / "other", system_root=tmp_path / "root") == old


def test_install_windows(tmp_path):
    bibles = tmp_path / "RenewedVision/ProPresenter/Bibles"
    bibles.mkdir(parents=True)
    pref = bibles / "BibleData.proPref"
    pref.write_text('InstalledBiblesNew=["6fb4fb55-78a4-43bc-ac6a-076818c7abfc|BB|BasisBijbel|1"];\n', encoding="utf-8")
    free = tmp_path / "free.json"
    free.write_text(json.dumps([
        {"internalAbbreviation": "BB", "displayAbbreviation": "BB", "name": "BasisBijbel", "language": "Dutch"},
        {"internalAbbreviation": "RVA", "displayAbbreviation": "RVES", "name": "Reina-Valera Antigua", "language": "Spanish"}]))
    choices = export_pp.windows_free_bibles(bibles, free)
    assert [c["internalAbbreviation"] for c in choices] == ["RVA"]       # BB is already in use
    folder = export_pp.install_windows_overwrite(big_bible(), choices[0], bibles)
    text = pref.read_text(encoding="utf-8")
    assert text.startswith("InstalledBiblesNew=[") and f"{folder.name}|RVA|Test Bible|1" in text and "BasisBijbel" in text
    rv = etree.parse(str(folder / "rvmetadata.xml")).getroot()
    assert rv.find("abbreviation").text == "RVA" and rv.find("displayAbbreviation").text == "TB"
    assert len(list((folder / "USX_1").glob("*.usx"))) == 66
    # sideload
    rvfile = export_pp.write_rvbible(big_bible(), tmp_path / "TB.rvbible")
    assert export_pp.install_windows_sideload(rvfile, bibles).parent.name == "sideload"
    # a failed install leaves nothing behind
    pref.unlink()
    with pytest.raises(BibleError):
        export_pp.install_windows_overwrite(big_bible(), choices[0], bibles)


def test_existing_files_are_never_overwritten(tmp_path):
    """Add to ProPresenter (Mac) and the Windows sideload copy keep a file that is already there."""
    a = export_pp.write_rvbible(big_bible(name="First Bible", short="TB"), tmp_path / "TB.rvbible")
    (tmp_path / "other").mkdir()
    other = export_pp.write_rvbible(big_bible(name="Another Bible", short="TB"), tmp_path / "other" / "TB.rvbible")
    folder = tmp_path / "pp"
    first = export_pp.install_mac(a, folder)
    original_bytes = first.read_bytes()
    second = export_pp.install_mac(other, folder)           # a different Bible with the same name
    third = export_pp.install_mac(a, folder)                # the same Bible again
    assert [p.name for p in (first, second, third)] == ["TB.rvbible", "TB (2).rvbible", "TB (3).rvbible"]
    assert first.read_bytes() == original_bytes             # the first file is untouched
    assert second.read_bytes() == other.read_bytes() and second.read_bytes() != original_bytes
    assert sorted(p.name for p in folder.iterdir()) == ["TB (2).rvbible", "TB (3).rvbible", "TB.rvbible"]
    # the same for the Windows sideload folder
    bibles = tmp_path / "Bibles"
    s1 = export_pp.install_windows_sideload(a, bibles)
    s2 = export_pp.install_windows_sideload(a, bibles)
    assert (s1.name, s2.name) == ("TB.rvbible", "TB (2).rvbible") and s1.parent.name == "sideload"


def test_copy_never_replaces_even_when_the_name_appears_late(tmp_path, monkeypatch):
    """The copy is made with an 'exclusive create', so a file that shows up at the last moment is not replaced."""
    src = tmp_path / "KJV.rvbible"
    src.write_bytes(b"new")
    folder = tmp_path / "pp"
    folder.mkdir()
    (folder / "KJV.rvbible").write_bytes(b"someone else's file")
    dest = export_pp.copy_without_overwriting(src, folder)
    assert dest.name == "KJV (2).rvbible" and (folder / "KJV.rvbible").read_bytes() == b"someone else's file"
