"""Getting Bibles into ProPresenter on Windows (the "Get ready for ProPresenter" helper).

ProPresenter for Windows only accepts a Bible whose name code it already knows, so each of our Bibles takes the
place of one of ProPresenter's own free Bibles (the same idea as the original tool's "overwrite a free Bible").

Two steps:
  prepare()  makes everything in a folder of our own (nothing in ProPresenter is touched): one folder for each
             Bible, and either a new BibleData.proPref (ProPresenter's list plus our Bibles) or, when
             ProPresenter is not on this PC, a text file with the lines to add.
  install()  (only when the person asks for it) puts the prepared folders and list into ProPresenter's folder.
             ProPresenter must be closed, the old list is kept as BibleData.proPref.old, the list must not have
             changed since prepare(), and anything that fails is rolled back.
  undo()     takes our Bibles out again.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from . import export_pp
from .model import BibleError, ParsedBible, xml_safe
from .paths import resource_path

PREF_NAME = "BibleData.proPref"
LINES_FILE = "Lines for BibleData.proPref.txt"
_ARRAY = re.compile(r"InstalledBiblesNew=(\[[^\]]*?\]);?")
_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def clean_entry_name(text: str) -> str:
    """A Bible name that is safe inside a ProPresenter list entry ("id|CODE|name|1"): no | " \\ ] or control characters."""
    t = xml_safe(text or "").replace("|", "/")
    t = re.sub(r'["\\\]\[]', "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t or "Bible"


def find_bibles_folder(programdata: Optional[str] = None) -> Optional[Path]:
    """ProPresenter's Bibles folder on this PC, or None when ProPresenter is not here."""
    pd = programdata or os.environ.get("PROGRAMDATA")
    if not pd:
        return None
    folder = Path(pd) / "RenewedVision" / "ProPresenter" / "Bibles"
    return folder if (folder / PREF_NAME).is_file() else None


def is_propresenter_running() -> bool:
    """True when ProPresenter is open (Windows). Anywhere else: False."""
    if sys.platform != "win32":
        return False
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ProPresenter.exe", "/NH"], capture_output=True, text=True,
                             timeout=15, creationflags=flags).stdout
        return "propresenter.exe" in out.lower()
    except (OSError, subprocess.SubprocessError):
        return False        # cannot tell: the person is asked to close it anyway


def free_bibles(bibles_folder: Optional[Path]) -> list[dict]:
    """ProPresenter's free Bibles a new Bible may take the place of (the ones not installed, when the list is known)."""
    if bibles_folder is not None:
        return export_pp.windows_free_bibles(bibles_folder)
    free = json.loads(Path(resource_path("available_bibles.json")).read_text(encoding="utf-8"))
    return sorted(free, key=lambda f: (f.get("language", ""), f.get("name", "")))


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _array_of(text: str) -> tuple[re.Match, list[str]]:
    m = _ARRAY.search(text)
    if not m:
        raise BibleError("ProPresenter's Bible list is not in the form this program knows, so it was left alone.")
    try:
        return m, json.loads(m.group(1))
    except ValueError:
        raise BibleError("ProPresenter's Bible list could not be read, so it was left alone.")


def add_entries(text: str, entries: list[str]) -> str:
    """The text of ProPresenter's list with entries added (everything else in the file stays as it is)."""
    if not text.strip():
        return "InstalledBiblesNew=" + json.dumps(entries) + ";\n"
    m, existing = _array_of(text)
    return text[:m.start(1)] + json.dumps(existing + entries) + text[m.end(1):]


def remove_entries(text: str, ids: set[str]) -> str:
    m, existing = _array_of(text)
    kept = [e for e in existing if e.split("|", 1)[0] not in ids]
    return text[:m.start(1)] + json.dumps(kept) + text[m.end(1):]


@dataclass
class Prepared:
    ready_dir: Path
    bibles_folder: Optional[Path]                  # ProPresenter's folder when it is on this PC
    folders: list[Path] = field(default_factory=list)      # one folder per Bible (named by its id)
    entries: list[str] = field(default_factory=list)       # "id|CODE|name|1"
    names: list[str] = field(default_factory=list)
    new_pref: Optional[Path] = None                 # the ready BibleData.proPref (ProPresenter on this PC)
    lines_file: Optional[Path] = None               # the text file with the lines (ProPresenter not on this PC)
    pref_hash: str = ""                             # the list as it was when we read it


def prepare(bibles: list[ParsedBible], codes: list[str], ready_dir: Path, bibles_folder: Optional[Path]) -> Prepared:
    """Makes the ready folders and list in ready_dir (which must not exist yet). Nothing in ProPresenter is touched."""
    if not bibles or len(bibles) != len(codes):
        raise BibleError("Pick a free Bible for every Bible in the list.")
    if len(set(codes)) != len(codes):
        raise BibleError("Pick a different free Bible for each one of your Bibles.")
    valid = {f["internalAbbreviation"] for f in free_bibles(bibles_folder)}
    for c in codes:
        if c not in valid:
            raise BibleError("One of the free Bibles you picked is already installed in ProPresenter. Pick another one.")
    pref_text, pref_bytes = "", b""
    if bibles_folder is not None:
        pref_bytes = (Path(bibles_folder) / PREF_NAME).read_bytes()
        pref_text = pref_bytes.decode("utf-8")
        add_entries(pref_text, [])                  # refuse a list we cannot read before making anything
    ready_dir = Path(ready_dir)
    ready_dir.mkdir(parents=True, exist_ok=False)
    p = Prepared(ready_dir=ready_dir, bibles_folder=Path(bibles_folder) if bibles_folder else None,
                 pref_hash=_sha(pref_bytes) if bibles_folder is not None else "")
    try:
        for pb, code in zip(bibles, codes):
            bible_id = str(uuid4())
            folder = ready_dir / bible_id
            export_pp.write_files(pb, folder, abbreviation=code)
            name = clean_entry_name(pb.name or pb.short)
            p.folders.append(folder)
            p.entries.append("|".join([bible_id, code, name, "1"]))
            p.names.append(name)
        if bibles_folder is not None:
            p.new_pref = ready_dir / PREF_NAME
            p.new_pref.write_text(add_entries(pref_text, p.entries), encoding="utf-8")
        else:
            p.lines_file = ready_dir / LINES_FILE
            p.lines_file.write_text(",\n".join(json.dumps(e) for e in p.entries) + "\n", encoding="utf-8")
    except Exception:
        shutil.rmtree(ready_dir, ignore_errors=True)
        raise
    return p


@dataclass
class Installed:
    bibles_folder: Path
    folders: list[Path]
    ids: list[str]
    backup: Path
    pref_hash: str = ""


def _backup(pref: Path) -> Path:
    """Keeps a copy of the list as BibleData.proPref.old (or .old-2…): an earlier copy is never replaced."""
    data = pref.read_bytes()
    n = 1
    while True:
        path = pref.with_name(PREF_NAME + (".old" if n == 1 else f".old-{n}"))
        try:
            with open(path, "xb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            return path
        except FileExistsError:
            n += 1


def _plain(e: OSError) -> BibleError:
    """The problem in plain words (shutil.Error holds a raw list of file problems: never shown as it is)."""
    denied = isinstance(e, PermissionError) or "denied" in str(e).lower() or "permission" in str(e).lower()
    if denied:
        return BibleError("Windows will not let Bible Importer change ProPresenter's folder. "
                          "Use the steps instead, or start Bible Importer as an administrator.")
    if isinstance(e, shutil.Error):
        return BibleError("Could not copy the Bibles into ProPresenter's folder. Nothing was changed.")
    return BibleError(f"Could not put the Bibles in ProPresenter's folder: {e}")


def install(p: Prepared, running: Callable[[], bool] = is_propresenter_running) -> Installed:
    """Puts the prepared Bibles into ProPresenter. Raises BibleError (plain words) and leaves ProPresenter as it was."""
    if p.bibles_folder is None or p.new_pref is None:
        raise BibleError("ProPresenter was not found on this PC, so there is nothing to put the Bibles into.")
    if running():
        raise BibleError("ProPresenter is open. Close it first, then try again.")
    folder = p.bibles_folder
    pref = folder / PREF_NAME
    try:
        current = pref.read_bytes()
    except OSError as e:
        raise _plain(e)
    if _sha(current) != p.pref_hash:
        raise BibleError("ProPresenter's list has changed since the files were made. Click Make them ready again.")
    targets = [folder / f.name for f in p.folders]
    if any(t.exists() for t in targets):
        raise BibleError("A folder with the same name is already in ProPresenter's Bibles folder.")
    backup: Optional[Path] = None
    copied: list[Path] = []
    tmp = folder / f".{PREF_NAME}.{uuid4().hex[:8]}.part"
    try:
        backup = _backup(pref)
        for src, dst in zip(p.folders, targets):
            shutil.copytree(src, dst)
            copied.append(dst)
        shutil.copyfile(p.new_pref, tmp)
        os.replace(tmp, pref)                     # the list changes last: until now ProPresenter sees nothing new
    except OSError as e:
        for d in copied:
            shutil.rmtree(d, ignore_errors=True)
        if backup is not None and pref.read_bytes() == current:
            try:
                backup.unlink()
            except OSError:
                pass
        raise _plain(e)
    except Exception:
        for d in copied:
            shutil.rmtree(d, ignore_errors=True)
        raise
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
    return Installed(bibles_folder=folder, folders=copied, ids=[f.name for f in copied], backup=backup,
                     pref_hash=_sha(pref.read_bytes()))


def undo(done: Installed, running: Callable[[], bool] = is_propresenter_running) -> None:
    """Takes our Bibles out of ProPresenter again. Other Bibles added since stay (only our entries are removed)."""
    if running():
        raise BibleError("ProPresenter is open. Close it first, then try again.")
    pref = done.bibles_folder / PREF_NAME
    try:
        text = pref.read_text(encoding="utf-8")
        new = remove_entries(text, set(done.ids))
        tmp = pref.with_name(f".{PREF_NAME}.{uuid4().hex[:8]}.part")
        tmp.write_text(new, encoding="utf-8")
        os.replace(tmp, pref)
        for f in done.folders:
            if _ID.fullmatch(f.name) and f.parent == done.bibles_folder:       # only a folder we made
                shutil.rmtree(f, ignore_errors=True)
    except OSError as e:
        raise _plain(e)
