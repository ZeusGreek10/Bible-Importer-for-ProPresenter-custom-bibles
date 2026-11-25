"""Reading a Bible file the church already has: Zefania, OSIS, USX, USFM, USFX, .rvbible and JSON.

Notes, cross references and headings are left out; only verse text is kept.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path
from typing import Iterable, Optional

from lxml import etree

from . import getbible, usfm
from .books import BOOKS, book_number
from .model import BibleError, ParsedBible

OSIS_IDS = ["Gen", "Exod", "Lev", "Num", "Deut", "Josh", "Judg", "Ruth", "1Sam", "2Sam", "1Kgs", "2Kgs", "1Chr", "2Chr",
            "Ezra", "Neh", "Esth", "Job", "Ps", "Prov", "Eccl", "Song", "Isa", "Jer", "Lam", "Ezek", "Dan", "Hos", "Joel",
            "Amos", "Obad", "Jonah", "Mic", "Nah", "Hab", "Zeph", "Hag", "Zech", "Mal", "Matt", "Mark", "Luke", "John",
            "Acts", "Rom", "1Cor", "2Cor", "Gal", "Eph", "Phil", "Col", "1Thess", "2Thess", "1Tim", "2Tim", "Titus", "Phlm",
            "Heb", "Jas", "1Pet", "2Pet", "1John", "2John", "3John", "Jude", "Rev"]
OSIS_TO_NUM = {x.lower(): i + 1 for i, x in enumerate(OSIS_IDS)}

SKIP = {"note", "f", "x", "fig", "ref", "remark", "rt", "title", "head", "h", "toc", "fr", "xo", "ft", "fq", "xt"}

EXTENSIONS = (".json", ".xml", ".zefania", ".osis", ".usx", ".usfm", ".sfm", ".usf", ".usfx", ".rvbible", ".zip")


def _local(tag) -> str:
    if not isinstance(tag, str):
        return ""
    return etree.QName(tag).localname.lower()


def _verse_inner_text(el) -> str:
    """The text inside one element, without notes and cross references."""
    parts: list[str] = []

    def walk(node) -> None:
        if node.text:
            parts.append(node.text)
        for child in node:
            if _local(child.tag) not in SKIP:
                walk(child)
            if child.tail:
                parts.append(child.tail)
    walk(el)
    return "".join(parts)


USX_HEADINGS = {"s", "s1", "s2", "s3", "s4", "r", "d", "ms", "ms1", "ms2", "mr", "sr", "sp", "h", "toc1", "toc2", "toc3",
                "mt", "mt1", "mt2", "mt3", "imt", "is", "ip", "rem", "cl", "cp", "id", "ide"}
USFX_HEADINGS = {"s", "s1", "s2", "r", "d", "ms", "mr", "sr", "sp", "h", "toc", "mt", "mt1", "mt2", "rem", "cl", "id", "ide"}


def _usx_heading(el, name: str) -> bool:
    return name == "para" and (el.get("style") or "") in USX_HEADINGS


def _usfx_heading(el, name: str) -> bool:
    return name in USFX_HEADINGS


def _walk_milestones(root, on_start, on_end, on_text, skip_el=None) -> None:
    """Document-order walk that gives start/end of elements and the text between them (notes skipped)."""
    skip = 0
    for event, el in etree.iterwalk(root, events=("start", "end")):
        name = _local(el.tag)
        if event == "start":
            if skip or name in SKIP or (skip_el is not None and skip_el(el, name)):
                skip += 1
            else:
                on_start(el, name)
            if not skip and el.text:
                on_text(el.text)
        else:
            if skip:
                skip -= 1
            else:
                on_end(el, name)
            # the tail belongs to the parent, so it is read even when the element itself was skipped
            if not skip and el.tail:
                on_text(el.tail)


# ---- Zefania -----------------------------------------------------------------------------------------

def parse_zefania(data: bytes) -> ParsedBible:
    root = etree.fromstring(data, etree.XMLParser(recover=True, huge_tree=True))
    pb = ParsedBible(name=root.get("biblename") or "")
    for info in root.iter():
        n = _local(info.tag)
        text = (info.text or "").strip()
        if n == "title" and text and not pb.name:
            pb.name = text
        elif n == "language" and text:
            pb.lang_code = text
        elif n == "identifier" and text and not pb.short:
            pb.short = text
    for bi, book in enumerate(root.iter()):
        if _local(book.tag) != "biblebook":
            continue
        try:
            num = int(book.get("bnumber"))
        except (TypeError, ValueError):
            num = book_number(book.get("bsname") or "")
        if not 1 <= num <= 66:
            continue
        for ci, ch in enumerate(c for c in book if _local(c.tag) == "chapter"):
            try:
                cn = int(ch.get("cnumber"))
            except (TypeError, ValueError):
                cn = ci + 1
            for vi, v in enumerate(x for x in ch if _local(x.tag) == "vers"):
                try:
                    vn = int(v.get("vnumber"))
                except (TypeError, ValueError):
                    vn = vi + 1
                pb.add(num, cn, vn, _verse_inner_text(v))
    return pb


# ---- OSIS --------------------------------------------------------------------------------------------

def parse_osis(data: bytes) -> ParsedBible:
    root = etree.fromstring(data, etree.XMLParser(recover=True, huge_tree=True))
    pb = ParsedBible()
    for el in root.iter():
        n = _local(el.tag)
        if n == "osistext":
            pb.short = el.get("osisIDWork") or ""
            pb.lang_code = el.get("{http://www.w3.org/XML/1998/namespace}lang") or el.get("lang") or ""
        elif n == "title" and not pb.name and el.getparent() is not None and _local(el.getparent().tag) == "work":
            pb.name = "".join(el.itertext()).strip()
    state = {"ref": None, "container": False, "buf": []}

    def ref_of(osis_id: str) -> Optional[tuple[int, int, int]]:
        parts = (osis_id or "").split(" ")[0].split(".")
        if len(parts) >= 3 and parts[0].lower() in OSIS_TO_NUM and parts[1].isdigit() and parts[2].isdigit():
            return OSIS_TO_NUM[parts[0].lower()], int(parts[1]), int(parts[2])
        return None

    def flush() -> None:
        if state["ref"]:
            pb.add(*state["ref"], "".join(state["buf"]))
        state["buf"] = []

    def on_start(el, name) -> None:
        if name == "verse":
            if el.get("eID"):
                flush()
                state["ref"] = None
            else:
                r = ref_of(el.get("osisID") or el.get("sID") or "")
                if r:
                    flush()
                    state["ref"] = r
                    state["container"] = el.get("sID") is None

    def on_end(el, name) -> None:
        if name == "verse" and state["container"] and not el.get("eID"):
            flush()
            state["ref"] = None
            state["container"] = False

    _walk_milestones(root, on_start, on_end, lambda t: state["buf"].append(t) if state["ref"] else None)
    flush()
    return pb


# ---- USX (also inside .rvbible) and USFX --------------------------------------------------------------

def parse_usx(data: bytes, pb: Optional[ParsedBible] = None) -> ParsedBible:
    """One USX book (2.x with <verse number>, 3.x with <verse sid> and <verse eid>)."""
    pb = pb or ParsedBible()
    root = etree.fromstring(data, etree.XMLParser(recover=True, huge_tree=True))
    st = {"book": 0, "chapter": 0, "verse": 0, "buf": [], "open": False}

    def flush() -> None:
        if st["book"] and st["chapter"] and st["verse"]:
            pb.add(st["book"], st["chapter"], st["verse"], "".join(st["buf"]))
        st["buf"] = []

    def on_start(el, name) -> None:
        if name == "book":
            st["book"] = book_number(el.get("code") or "")
        elif name == "chapter" and (el.get("number") or el.get("sid")):
            flush()
            st["verse"] = 0
            try:
                st["chapter"] = int(el.get("number") or el.get("sid").split(".")[-1].split()[-1])
            except (TypeError, ValueError):
                st["chapter"] += 1
        elif name == "verse":
            if el.get("eid"):
                flush()
                st["verse"] = 0
            else:
                flush()
                m = re.match(r"\s*(\d+)", el.get("number") or (el.get("sid") or "").split(":")[-1])
                st["verse"] = int(m.group(1)) if m else 0

    def on_text(t) -> None:
        if st["verse"]:
            st["buf"].append(t)

    _walk_milestones(root, on_start, lambda e, n: None, on_text, _usx_heading)
    flush()
    return pb


def parse_usfx(data: bytes) -> ParsedBible:
    pb = ParsedBible()
    root = etree.fromstring(data, etree.XMLParser(recover=True, huge_tree=True))
    st = {"book": 0, "chapter": 0, "verse": 0, "buf": []}

    def flush() -> None:
        if st["book"] and st["chapter"] and st["verse"]:
            pb.add(st["book"], st["chapter"], st["verse"], "".join(st["buf"]))
        st["buf"] = []

    def on_start(el, name) -> None:
        if name == "book":
            flush()
            st["book"], st["chapter"], st["verse"] = book_number(el.get("id") or ""), 0, 0
        elif name == "c":
            flush()
            st["verse"] = 0
            st["chapter"] = int(el.get("id")) if (el.get("id") or "").isdigit() else st["chapter"] + 1
        elif name == "v":
            flush()
            m = re.match(r"\s*(\d+)", el.get("id") or "")
            st["verse"] = int(m.group(1)) if m else 0
        elif name == "ve":
            flush()
            st["verse"] = 0

    _walk_milestones(root, on_start, lambda e, n: None, lambda t: st["buf"].append(t) if st["verse"] else None,
                     _usfx_heading)
    flush()
    return pb


# ---- reading any file -------------------------------------------------------------------------------

def _from_zip(data: bytes) -> ParsedBible:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise BibleError("This file is not a valid zip file.")
    names = zf.namelist()
    usx = sorted(n for n in names if n.lower().endswith(".usx"))
    if usx:
        pb = ParsedBible()
        for n in usx:
            parse_usx(zf.read(n), pb)
        _read_pp_metadata(zf, pb)
        return pb
    if any(n.lower().endswith((".usfm", ".sfm", ".usf")) for n in names):
        return usfm.parse_zip(data)
    for n in names:
        if n.lower().endswith(".xml") and not n.lower().startswith(("metadata", "rvmetadata")):
            return parse_bytes(zf.read(n), n)
    raise BibleError("There is no Bible text in this zip file.")


def _read_pp_metadata(zf: zipfile.ZipFile, pb: ParsedBible) -> None:
    """Name, short name and language from a ProPresenter .rvbible."""
    try:
        rv = etree.fromstring(zf.read("rvmetadata.xml"))
        pb.name = (rv.findtext("name") or "").strip()
        pb.short = (rv.findtext("displayAbbreviation") or rv.findtext("abbreviation") or "").strip()
    except (KeyError, etree.XMLSyntaxError):
        pass
    try:
        meta = etree.fromstring(zf.read("metadata.xml"))
        pb.lang_code = (meta.findtext(".//language/iso") or "").strip()
        pb.language = (meta.findtext(".//language/name") or "").strip()
        pb.direction = "rtl" if (meta.findtext(".//language/scriptDirection") or "").lower() == "rtl" else "ltr"
        for b in meta.iterfind(".//bookNames/book"):
            num = book_number(b.get("code") or "")
            if num:
                pb.book_names[num] = (b.findtext("long") or "", b.findtext("short") or "", b.findtext("abbr") or "")
        if not pb.name:
            pb.name = (meta.findtext(".//identification/name") or "").strip()
    except (KeyError, etree.XMLSyntaxError):
        pass


def parse_bytes(data: bytes, filename: str) -> ParsedBible:
    low = filename.lower()
    if low.endswith((".zip", ".rvbible")) or data[:2] == b"PK":
        return _from_zip(data)
    if low.endswith(".json"):
        try:
            return getbible.decode(json.loads(data.decode("utf-8-sig")))
        except ValueError:
            raise BibleError("This JSON file could not be read.")
    if low.endswith((".usfm", ".sfm", ".usf")):
        pb = ParsedBible()
        usfm.parse_book(data.decode("utf-8-sig", errors="replace"), pb)
        return pb
    head = data[:4096].decode("utf-8", errors="ignore").lower()
    if "<xmlbible" in head or "<biblebook" in head:
        return parse_zefania(data)
    if "<osis" in head:
        return parse_osis(data)
    if "<usfx" in head:
        return parse_usfx(data)
    if "<usx" in head:
        return parse_usx(data)
    raise BibleError("This file is not a Bible file Bible Importer can read.")


def read_files(paths: Iterable[Path]) -> ParsedBible:
    """One Bible from one file, or from several (for example one USFM or USX file per book)."""
    paths = [Path(p) for p in paths]
    if not paths:
        raise BibleError("No file was chosen.")
    result: Optional[ParsedBible] = None
    for p in paths:
        try:
            pb = parse_bytes(p.read_bytes(), p.name)
        except OSError:
            raise BibleError(f"{p.name} could not be opened.")
        if not pb.name:
            pb.name = p.stem
        if not pb.short:
            pb.short = re.sub(r"[^A-Za-z0-9]", "", p.stem).upper()[:8] or "BIBLE"
        if result is None:
            result = pb
            continue
        for b, chapters in pb.verses.items():       # more files of the same Bible: put the books together
            for c, vs in chapters.items():
                for v, t in vs.items():
                    result.add(b, c, v, t)
    assert result is not None
    result.validate()
    return result
