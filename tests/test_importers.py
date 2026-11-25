import io
import json
import zipfile

import pytest

from lpbibles import export_pp, importers
from lpbibles.model import BibleError, ParsedBible

ZEFANIA = b"""<?xml version="1.0" encoding="UTF-8"?>
<XMLBIBLE biblename="Zef Test"><INFORMATION><language>eng</language><identifier>ZT</identifier></INFORMATION>
<BIBLEBOOK bnumber="43"><CHAPTER cnumber="3"><VERS vnumber="16">For God so loved <NOTE>skip me</NOTE>the world.</VERS>
<VERS vnumber="17">Second verse.</VERS></CHAPTER></BIBLEBOOK></XMLBIBLE>"""

OSIS = b"""<?xml version="1.0"?><osis xmlns="http://www.bibletechnologies.net/2003/OSIS/namespace">
<osisText osisIDWork="OT1" xml:lang="en"><header><work osisWork="OT1"><title>Osis Test</title></work></header>
<div type="book" osisID="John"><chapter osisID="John.3">
<verse osisID="John.3.16">For God so loved<note>skip</note> the world.</verse>
<verse sID="John.3.17" osisID="John.3.17"/>Milestone verse <title>Heading</title>text.<verse eID="John.3.17"/>
</chapter></div></osisText></osis>"""

USX2 = b"""<usx version="2.0"><book code="JHN" style="id">JHN</book><chapter number="3" style="c"/>
<para style="s1">A heading</para><para style="p"><verse number="16" style="v"/>For God so loved the world.</para>
<para style="p"><verse number="17" style="v"/>Second <note caller="+" style="f">footnote</note>verse.</para></usx>"""

USX3 = b"""<usx version="3.0"><book code="JHN" style="id"/><chapter number="3" style="c" sid="JHN 3"/>
<para style="p"><verse number="16" style="v" sid="JHN 3:16"/>For God <char style="nd">so</char> loved.<verse eid="JHN 3:16"/></para>
<chapter eid="JHN 3"/></usx>"""

USFX = b"""<usfx><book id="JHN"><h>John</h><c id="3"/><p><v id="16"/>For God so loved <f>note</f>the world.<ve/></p>
<s>A heading</s><p><v id="17"/>Second verse.<ve/></p></book></usfx>"""


def test_zefania():
    pb = importers.parse_bytes(ZEFANIA, "x.xml")
    assert pb.name == "Zef Test" and pb.short == "ZT" and pb.verses[43][3][16] == "For God so loved the world."


def test_osis():
    pb = importers.parse_bytes(OSIS, "x.xml")
    assert pb.name == "Osis Test" and pb.short == "OT1"
    assert pb.verses[43][3][16] == "For God so loved the world."
    assert pb.verses[43][3][17] == "Milestone verse text."          # heading inside the verse is left out


@pytest.mark.parametrize("data", [USX2, USX3])
def test_usx(data):
    pb = importers.parse_bytes(data, "JHN.usx")
    assert pb.verses[43][3][16].startswith("For God")
    if data is USX2:
        assert pb.verses[43][3][16] == "For God so loved the world."       # the heading does not leak into verse 16
        assert pb.verses[43][3][17] == "Second verse."
    else:
        assert pb.verses[43][3][16] == "For God so loved."


def test_usfx():
    pb = importers.parse_bytes(USFX, "x.xml")
    assert pb.verses[43][3][16] == "For God so loved the world."
    assert pb.verses[43][3][17] == "Second verse."


def test_json_formats():
    d = {"translation": "J", "abbreviation": "j", "books": [{"nr": 43, "name": "John", "chapters": [
        {"chapter": 3, "verses": [{"verse": 16, "text": "Yes."}]}]}]}
    assert importers.parse_bytes(json.dumps(d).encode(), "a.json").verses[43][3][16] == "Yes."


def test_unknown_file():
    with pytest.raises(BibleError):
        importers.parse_bytes(b"hello", "a.txt")
    with pytest.raises(BibleError):
        importers.parse_bytes(b"PK not a zip", "a.zip")


def big():
    pb = ParsedBible(name="Round Trip", short="RT", language="English", lang_code="eng")
    for b in range(1, 67):
        for v in (1, 2):
            pb.add(b, 1, v, f"Book {b} verse {v}.")
    pb.book_names[43] = ("Evangelie volgens Johannes", "Johannes", "Joh")
    return pb


def test_our_own_rvbible_comes_back(tmp_path):
    """What we write for ProPresenter, we can read again (names, language, book names, text)."""
    rv = export_pp.write_rvbible(big(), tmp_path / "RT.rvbible")
    pb = importers.read_files([rv])
    assert pb.name == "Round Trip" and pb.short == "RT" and pb.lang_code == "eng" and pb.book_count == 66
    assert pb.verses[43][1][2] == "Book 43 verse 2."
    assert pb.book_names[43][1] == "Johannes"


def test_several_files_make_one_bible(tmp_path):
    for b, name in ((43, "JHN"), (1, "GEN")):
        (tmp_path / f"{name}.usfm").write_text(f"\\id {name}\n\\c 1\n\\p\n\\v 1 Text of {name}.\n", encoding="utf-8")
    pb = importers.ParsedBible()
    parsed = [importers.parse_bytes(p.read_bytes(), p.name) for p in sorted(tmp_path.glob("*.usfm"))]
    assert {1, 43} == set().union(*[set(p.verses) for p in parsed])
    with pytest.raises(BibleError):          # two books are far too few for a Bible
        importers.read_files(sorted(tmp_path.glob("*.usfm")))
