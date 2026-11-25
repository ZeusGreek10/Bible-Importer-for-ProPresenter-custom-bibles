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
from pathlib import Path
from typing import Optional
from uuid import uuid4

from lxml import etree
from lxml.etree import Element, SubElement, tostring

from .books import BOOKS
from .model import BibleError, ParsedBible, xml_safe
from .biblecom_pp import construct_metadataxmls, toxml
from .paths import resource_path

MAC_RELATIVE = Path("Library") / "Application Support" / "RenewedVision" / "RVBibles" / "v2"


def usx_book(pb: ParsedBible, book: int) -> bytes:
    """One book as USX, in the same form the original tool wrote (one <para> per verse)."""
    code = BOOKS[book - 1][0]
    usx = Element("usx", version="2.0")
    SubElement(usx, "book", code=code).text = code
    for c in sorted(pb.verses[book]):
        SubElement(usx, "chapter", number=str(c), style="c")
        for v, text in sorted(pb.verses[book][c].items()):
            para = SubElement(usx, "para", style="p")
            SubElement(para, "verse", number=str(v), style="v").tail = text
    return toxml(usx)


def synthetic_metadata(pb: ParsedBible) -> dict:
    """The Bible.com-style details `construct_metadataxmls` needs, for a Bible that did not come from Bible.com."""
    x = xml_safe
    books = []
    for b in sorted(pb.verses):
        books.append({"usfm": BOOKS[b - 1][0], "canon": "ot" if b <= 39 else "nt", "human": x(pb.name_of(b, 1)),
                      "human_long": x(pb.name_of(b, 0)), "abbreviation": x(pb.name_of(b, 2))})
    return {"title": x(pb.name or pb.short), "local_title": x(pb.name or pb.short), "abbreviation": x(pb.short),
            "local_abbreviation": x(pb.short),
            "language": {"iso_639_3": x(pb.lang_code or "eng"), "name": x(pb.language or "English"),
                         "text_direction": x(pb.direction or "ltr")},
            "books": books}


def write_files(pb: ParsedBible, folder: Path, abbreviation: Optional[str] = None) -> None:
    """Writes the three parts of a Bible into a folder.

    A Bible from Bible.com uses the USX and details saved when it was downloaded (exactly the original tool's
    output); any other Bible is written in the same form from its verses.
    """
    pb.validate()
    (folder / "USX_1").mkdir(parents=True, exist_ok=True)
    if pb.usx and pb.source_meta:
        for code, data in pb.usx.items():
            (folder / "USX_1" / f"{code}.usx").write_bytes(data)
        meta = pb.source_meta
    else:
        for b in sorted(pb.verses):
            (folder / "USX_1" / f"{BOOKS[b - 1][0]}.usx").write_bytes(usx_book(pb, b))
        meta = synthetic_metadata(pb)
    construct_metadataxmls(str(folder), meta)
    if abbreviation:
        # Windows "take the place of a free Bible": same as the original (the abbreviation of the Bible to replace)
        rvmetadata = folder / "rvmetadata.xml"
        xtree = etree.parse(str(rvmetadata))
        xtree.xpath("//abbreviation")[0].text = abbreviation
        rvmetadata.write_bytes(toxml(xtree))


def write_rvbible(pb: ParsedBible, path: Path) -> Path:
    """Makes a .rvbible file (a zip of the three parts, made as the original tool made it).
    The file appears only when it is complete."""
    path = Path(path)
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "bible"
        write_files(pb, folder)
        part = shutil.make_archive(str(Path(tmp) / "archive"), "zip", str(folder))
        tmp_target = path.with_name(f".{path.name}.{uuid4().hex[:10]}.part")
        shutil.copyfile(part, tmp_target)
        os.replace(tmp_target, path)
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


def unique_path(folder: Path, base: str, ext: str) -> Path:
    """folder/base.ext, or folder/base (2).ext, folder/base (3).ext… when that name is taken."""
    p = Path(folder) / f"{base}{ext}"
    n = 2
    while p.exists():
        p = Path(folder) / f"{base} ({n}){ext}"
        n += 1
    return p


def copy_without_overwriting(src: Path, folder: Path) -> Path:
    """Copies a file into a folder under its own name, or "name (2)", "name (3)"… when a file with that name is
    already there.

    The copy is written under a temporary name first and then given its final name in one step that fails if that
    name is taken, so (1) a file that exists is never replaced, even if another program creates it a moment
    before, and (2) a copy that fails or is cut off half way never leaves a half-written file under a real name
    (ProPresenter on Mac can crash on a broken Bible file)."""
    src = Path(src)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    data = src.read_bytes()
    part = folder / f".{src.stem}.{uuid4().hex[:10]}.part"
    try:
        part.write_bytes(data)
        n = 1
        while True:
            dest = folder / (src.name if n == 1 else f"{src.stem} ({n}){src.suffix}")
            try:
                os.link(part, dest)          # fails if dest exists: nothing is ever replaced
                return dest
            except FileExistsError:
                n += 1
            except OSError:                  # a disk without hard links (for example exFAT): rename if the name is free
                if dest.exists():
                    n += 1
                    continue
                try:
                    os.rename(part, dest)    # on Windows this also fails if dest exists
                    return dest
                except FileExistsError:
                    n += 1
    finally:
        try:
            part.unlink()
        except FileNotFoundError:
            pass


def install_mac(rvbible: Path, folder: Optional[Path] = None) -> Path:
    """Puts the .rvbible where ProPresenter on Mac looks. An existing file with the same name is kept: the new one
    gets "(2)" in its name. If the older system-wide folder is the one in use but cannot be written (it needs an
    administrator), the per-user folder is used."""
    if folder is not None:
        return copy_without_overwriting(rvbible, folder)
    target = mac_bible_folder()
    try:
        return copy_without_overwriting(rvbible, target)
    except PermissionError:
        return copy_without_overwriting(rvbible, Path.home() / MAC_RELATIVE)


def windows_bible_folder(programdata: Optional[str] = None) -> Path:
    pd = programdata or os.environ.get("PROGRAMDATA")
    if not pd:
        raise BibleError("ProPresenter's folder was not found on this computer.")
    return Path(pd) / "RenewedVision" / "ProPresenter" / "Bibles"


def install_windows_sideload(rvbible: Path, bibles_folder: Optional[Path] = None) -> Path:
    folder = (bibles_folder or windows_bible_folder()) / "sideload"
    return copy_without_overwriting(rvbible, folder)


_INSTALLED = re.compile(r"InstalledBiblesNew=(?P<array>\[[^\]]*?]);?")


def _read_installed(pref: Path) -> list[str]:
    """The Bibles ProPresenter lists. If the file cannot be read, stop: writing it again would drop the others."""
    try:
        text = pref.read_text(encoding="utf-8")
    except OSError:
        raise BibleError("ProPresenter's Bible list could not be read.")
    if not text.strip():
        return []
    m = _INSTALLED.match(text)
    try:
        if not m:
            raise ValueError
        return json.loads(m.group("array"))
    except ValueError:
        raise BibleError("ProPresenter's Bible list is not in the form this program knows, so it was left alone.")


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


def free_bible_code_list() -> str:
    """The name codes of ProPresenter's own free Bibles (one per line), for the Windows explanation."""
    free = json.loads(Path(resource_path("available_bibles.json")).read_text(encoding="utf-8"))
    lines = ["Name code | Bible | Language"]
    for f in sorted(free, key=lambda x: (x.get("language", ""), x.get("name", ""))):
        lines.append(f'{f["internalAbbreviation"]} | {f.get("name", "")} | {f.get("language", "")}')
    return "\n".join(lines)


def windows_bibles_folder_text() -> str:
    return r"C:\ProgramData\RenewedVision\ProPresenter\Bibles"
