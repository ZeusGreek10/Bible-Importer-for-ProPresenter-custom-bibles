"""Export for ProPresenter 7: a .rvbible file (a zip), and installing it.

An .rvbible holds  metadata.xml, rvmetadata.xml and USX_1/<BOOK>.usx  (Unified Scripture XML).
Notes from the original tool (kept because they matter):
  * XML comments in metadata.xml make ProPresenter on Mac crash: none are written.
  * On Windows ProPresenter only knows Bibles whose abbreviation is one it already has, so a
    new Bible is installed by taking the place of one of its free Bibles ("overwrite"), or it is
    put in the "sideload" folder (advanced; ProPresenter may then not list it).
  * A broken Bible file can make ProPresenter on Mac crash: files are written completely or not at all.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Optional
from uuid import uuid4

from lxml import etree
from lxml.etree import Element, SubElement, tostring

from .books import BOOKS
from .model import BibleError, ParsedBible
from .paths import resource_path

MAC_RELATIVE = Path("Library") / "Application Support" / "RenewedVision" / "RVBibles" / "v2"


def _xml(elem) -> bytes:
    return tostring(elem, encoding="utf-8", xml_declaration=True)


def usx_book(pb: ParsedBible, book: int) -> bytes:
    code = BOOKS[book - 1][0]
    usx = Element("usx", version="2.0")
    SubElement(usx, "book", code=code, style="id").text = code
    for c in sorted(pb.verses[book]):
        SubElement(usx, "chapter", number=str(c), style="c")
        for v, text in sorted(pb.verses[book][c].items()):
            para = SubElement(usx, "para", style="p")
            SubElement(para, "verse", number=str(v), style="v").tail = text
    return _xml(usx)


def metadata_xml(pb: ParsedBible) -> bytes:
    tree = etree.parse(resource_path("metadata.xml"))
    name = pb.name or pb.short
    ident = tree.xpath("//identification")[0]
    SubElement(ident, "name").text = name
    SubElement(ident, "nameLocal").text = name
    SubElement(ident, "abbreviation").text = pb.short
    SubElement(ident, "abbreviationLocal").text = pb.short
    lang = tree.xpath("//language")[0]
    SubElement(lang, "iso").text = pb.lang_code or "eng"
    SubElement(lang, "name").text = pb.language or "English"
    SubElement(lang, "scriptDirection").text = pb.direction or "ltr"
    # the template names a Dutch Bible here; describe this one instead
    book_list = tree.xpath("//bookList")[0]
    for tag, value in (("name", name), ("nameLocal", name), ("abbreviation", pb.short),
                       ("abbreviationLocal", pb.short), ("description", name)):
        el = book_list.find(tag)
        if el is not None:
            el.text = value
    holder = tree.xpath("//rightsHolderAbbreviation")
    if holder:
        holder[0].text = pb.short
    names_el = tree.xpath("//bookNames")[0]
    books_el = tree.xpath("//bookList/books")[0]
    seen_short: set[str] = set()
    for b in sorted(pb.verses):
        code = BOOKS[b - 1][0]
        long_, short, abbr = pb.name_of(b, 0), pb.name_of(b, 1), pb.name_of(b, 2)
        if short in seen_short:          # two books with one short name confuse ProPresenter
            short = long_
        seen_short.add(short)
        el = SubElement(names_el, "book", code=code)
        SubElement(el, "long").text = long_
        SubElement(el, "short").text = short
        SubElement(el, "abbr").text = abbr
        SubElement(books_el, "book", code=code)
    return _xml(tree.getroot())


def rvmetadata_xml(pb: ParsedBible, abbreviation: Optional[str] = None) -> bytes:
    root = Element("RVBibleMetdata")     # (sic) the spelling ProPresenter uses
    SubElement(root, "name").text = pb.name or pb.short
    SubElement(root, "abbreviation").text = abbreviation or pb.short
    SubElement(root, "displayAbbreviation").text = pb.short
    SubElement(root, "version").text = "1"
    SubElement(root, "revision").text = "0"
    SubElement(root, "licenseType").text = "0"
    SubElement(root, "license")
    return _xml(root)


def write_files(pb: ParsedBible, folder: Path, abbreviation: Optional[str] = None) -> None:
    """Writes the three parts of a Bible into a folder."""
    pb.validate()
    (folder / "USX_1").mkdir(parents=True, exist_ok=True)
    for b in sorted(pb.verses):
        (folder / "USX_1" / f"{BOOKS[b - 1][0]}.usx").write_bytes(usx_book(pb, b))
    (folder / "metadata.xml").write_bytes(metadata_xml(pb))
    (folder / "rvmetadata.xml").write_bytes(rvmetadata_xml(pb, abbreviation))


def write_rvbible(pb: ParsedBible, path: Path) -> Path:
    """Makes a .rvbible file (a zip of the three parts). The file appears only when it is complete."""
    path = Path(path)
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "bible"
        write_files(pb, folder)
        part = path.with_name(path.name + ".part")
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(folder.rglob("*")):
                if f.is_file():
                    z.write(f, f.relative_to(folder).as_posix())
        os.replace(part, path)
    return path


# ---- installing -----------------------------------------------------------------------------------

def mac_bible_folder(home: Optional[Path] = None, system_root: Path = Path("/")) -> Path:
    """The folder ProPresenter on Mac reads: the per-user one, or the old system-wide one if that exists."""
    new = Path(home or Path.home()) / MAC_RELATIVE
    old = system_root / MAC_RELATIVE
    for candidate in (new, old):
        if candidate.exists():
            return candidate
    return new


def install_mac(rvbible: Path, folder: Optional[Path] = None) -> Path:
    folder = folder or mac_bible_folder()
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / Path(rvbible).name
    shutil.copyfile(rvbible, dest)
    return dest


def windows_bible_folder(programdata: Optional[str] = None) -> Path:
    pd = programdata or os.environ.get("PROGRAMDATA")
    if not pd:
        raise BibleError("ProPresenter's folder was not found on this computer.")
    return Path(pd) / "RenewedVision" / "ProPresenter" / "Bibles"


def install_windows_sideload(rvbible: Path, bibles_folder: Optional[Path] = None) -> Path:
    folder = (bibles_folder or windows_bible_folder()) / "sideload"
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / Path(rvbible).name
    shutil.copyfile(rvbible, dest)
    return dest


_INSTALLED = re.compile(r"InstalledBiblesNew=(?P<array>\[[^\]]*?]);?")


def _read_installed(pref: Path) -> list[str]:
    try:
        m = _INSTALLED.match(pref.read_text(encoding="utf-8"))
        return json.loads(m.group("array")) if m else []
    except (OSError, ValueError, AttributeError):
        return []


def windows_free_bibles(bibles_folder: Optional[Path] = None, available: Optional[Path] = None) -> list[dict]:
    """ProPresenter's free Bibles that this computer has not installed: a new Bible can take the place of one."""
    folder = bibles_folder or windows_bible_folder()
    pref = folder / "BibleData.proPref"
    if not pref.exists():
        raise BibleError("ProPresenter's Bible list was not found. Open ProPresenter once, then try again.")
    used = {entry.split("|")[1] for entry in _read_installed(pref) if entry.count("|") >= 3}
    source = available or Path(resource_path("available_bibles.json"))
    free = json.loads(Path(source).read_text(encoding="utf-8"))
    return [f for f in free if f["internalAbbreviation"] not in used]


def install_windows_overwrite(pb: ParsedBible, choice: dict, bibles_folder: Optional[Path] = None) -> Path:
    """Installs a Bible in the place of one of ProPresenter's free Bibles (the recommended way on Windows)."""
    folder = bibles_folder or windows_bible_folder()
    pref = folder / "BibleData.proPref"
    if not pref.exists():
        raise BibleError("ProPresenter's Bible list was not found. Open ProPresenter once, then try again.")
    overwrite_abbr = choice["internalAbbreviation"]
    folder_id = str(uuid4())
    target = folder / folder_id
    try:
        write_files(pb, target, abbreviation=overwrite_abbr)
        entries = _read_installed(pref)
        entries.append("|".join([folder_id, overwrite_abbr, pb.name or pb.short, "1"]))
        tmp = pref.with_name(pref.name + ".part")
        tmp.write_text("InstalledBiblesNew=" + json.dumps(entries) + ";\n", encoding="utf-8")
        os.replace(tmp, pref)
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise
    return target


def is_windows() -> bool:
    return sys.platform == "win32"


def is_mac() -> bool:
    return sys.platform == "darwin"
