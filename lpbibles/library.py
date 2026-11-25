"""The Bibles saved on this computer (the INSTALLED list of the window).

Folder layout:   <data folder>/Bibles/<code>.json   one file per Bible (the text)
                 <data folder>/Bibles/index.json    names and settings only (small, read at start)
Files are written to a temporary name first and moved into place, so a failed or cancelled
download never replaces a good Bible.
"""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional
from uuid import uuid4

from .model import WINDOWS_RESERVED, BibleError, ParsedBible, from_dense, xml_safe

FORMAT = "bible-importer-1"
NUMBERINGS = {"kjv": "KJV (English)", "synodal": "Synodal (Russian)"}


@dataclass
class Installed:
    code: str
    name: str
    short: str
    language: str
    lang_code: str
    source: str            # "getbible", "ebible", "biblecom" or "file"
    source_key: str        # the catalog key it came from ("" for a file)
    numbering: str = "kjv"
    copyright: str = ""


def default_numbering(language: str, lang_code: str, name: str) -> str:
    """Russian Bibles use the Synodal numbering (Psalms etc.); everything else the KJV one."""
    low = f"{language} {lang_code} {name}".lower()
    if language.lower() == "russian" or lang_code.lower() in ("ru", "rus") or "synodal" in low or "синод" in low:
        return "synodal"
    return "kjv"


def make_code(short: str, name: str) -> str:
    code = re.sub(r"[^a-z0-9]", "", (short or name).lower())[:12]
    if code.upper() in WINDOWS_RESERVED or code == "index":      # "con", "nul"… cannot be file names on Windows; "index" is ours
        code += "-bible"
    return code or "bible"


def _atomic_write(path: Path, data: str) -> None:
    """Writes a file completely or not at all (a temporary name, flushed to the disk, then moved into place)."""
    tmp = path.with_name(f".{path.name}.{uuid4().hex[:10]}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _locked(method):
    """The export runs in a background thread while the window reads the list: one at a time."""
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    wrapper.__name__ = method.__name__
    wrapper.__doc__ = method.__doc__
    return wrapper


class Library:
    def __init__(self, root: Path):
        self.folder = Path(root) / "Bibles"
        self.folder.mkdir(parents=True, exist_ok=True)
        self.index_path = self.folder / "index.json"
        self.items: list[Installed] = []
        self._lock = threading.RLock()
        self._load()

    # ---- reading --------------------------------------------------------------------------------

    def _load(self) -> None:
        """Reads the index. A damaged index is set aside (index.json.bad) and every Bible file on the disk is listed
        again, so a Bible that is saved is never forgotten and never replaced by a new one with the same code."""
        self.items = []
        changed = False
        if self.index_path.exists():
            try:
                doc = json.loads(self.index_path.read_text(encoding="utf-8"))
                for d in doc.get("bibles", []):
                    item = Installed(**{k: d.get(k, "") for k in Installed.__dataclass_fields__})
                    if (self.folder / f"{item.code}.json").exists():
                        self.items.append(item)
                    else:
                        changed = True
            except (ValueError, TypeError, OSError, AttributeError):
                try:
                    os.replace(self.index_path, self.folder / f"index.json.bad-{uuid4().hex[:6]}")
                except OSError:
                    pass
                changed = True
        # Bible files the index does not know about (a lost index, or a crash between the two writes)
        known = {i.code for i in self.items}
        for path in sorted(self.folder.glob("*.json")):
            if path.name == "index.json" or path.stem in known or not re.fullmatch(r"[a-z0-9-]+", path.stem):
                continue
            adopted = self._adopt(path)
            if adopted is not None:
                self.items.append(adopted)
                changed = True
        if changed:
            try:
                self._save_index()
            except OSError:
                pass

    def _adopt(self, path: Path) -> Optional[Installed]:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            if doc.get("format") != FORMAT:
                return None
            return Installed(code=path.stem, name=str(doc.get("name") or path.stem), short=str(doc.get("short") or path.stem),
                             language=str(doc.get("language") or ""), lang_code=str(doc.get("lang_code") or ""),
                             source=str(doc.get("source") or "file"), source_key=str(doc.get("source_key") or ""),
                             numbering=doc.get("numbering") if doc.get("numbering") in NUMBERINGS else
                             default_numbering(str(doc.get("language") or ""), str(doc.get("lang_code") or ""), str(doc.get("name") or "")),
                             copyright=str(doc.get("copyright") or ""))
        except (OSError, ValueError, AttributeError):
            return None

    def _save_index(self) -> None:
        _atomic_write(self.index_path, json.dumps({"format": FORMAT, "bibles": [asdict(i) for i in self.items]},
                                                  ensure_ascii=False, indent=1))

    @_locked
    def get(self, code: str) -> Optional[Installed]:
        return next((i for i in self.items if i.code == code), None)

    @_locked
    def is_installed(self, source_key: str) -> bool:
        return bool(source_key) and any(i.source_key == source_key for i in self.items)

    @_locked
    def load(self, code: str) -> ParsedBible:
        """The whole Bible, read from its file."""
        item = self.get(code)
        if item is None:
            raise BibleError("This Bible is not in the list.")
        try:
            doc = json.loads((self.folder / f"{code}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise BibleError("The Bible file could not be read.")
        pb = ParsedBible(name=item.name, short=item.short, language=item.language, lang_code=item.lang_code,
                         direction=doc.get("direction", "ltr"), copyright=item.copyright,
                         verses=from_dense(doc.get("books", {})))
        pb.book_names = {int(k): tuple(v) for k, v in (doc.get("book_names") or {}).items()}
        pb.usx = {k: v.encode("utf-8") for k, v in (doc.get("usx") or {}).items()}
        pb.source_meta = doc.get("source_meta") or {}
        return pb

    # ---- writing --------------------------------------------------------------------------------

    @_locked
    def save(self, pb: ParsedBible, source: str, source_key: str = "") -> Installed:
        """Checks and saves a Bible. Replaces the one with the same source_key (a second download)."""
        pb.validate()
        for attr in ("name", "short", "language", "lang_code", "copyright"):
            setattr(pb, attr, xml_safe(getattr(pb, attr)))          # a lone surrogate cannot be written to a file
        existing = next((i for i in self.items if source_key and i.source_key == source_key), None)
        if existing:
            code = existing.code
        else:
            base = make_code(pb.short, pb.name)
            code, n = base, 2
            while self.get(code) or (self.folder / f"{code}.json").exists():     # never take the name of a file that is there
                code = f"{base}-{n}"
                n += 1
        numbering = existing.numbering if existing else default_numbering(pb.language, pb.lang_code, pb.name)
        doc = {"format": FORMAT, "code": code, "name": pb.name, "short": pb.short, "language": pb.language,
               "lang_code": pb.lang_code, "direction": pb.direction, "books": pb.dense(),
               "book_names": {str(k): list(v) for k, v in pb.book_names.items()},
               "source": source, "source_key": source_key, "numbering": numbering, "copyright": pb.copyright}
        if pb.usx and pb.source_meta:     # Bible.com: what the ProPresenter file is made from
            doc["usx"] = {k: v.decode("utf-8") for k, v in pb.usx.items()}
            doc["source_meta"] = pb.source_meta
        _atomic_write(self.folder / f"{code}.json", json.dumps(doc, ensure_ascii=False, separators=(",", ":")))
        item = Installed(code=code, name=pb.name, short=pb.short or pb.name[:10], language=pb.language,
                         lang_code=pb.lang_code, source=source, source_key=source_key,
                         numbering=numbering, copyright=pb.copyright)
        if existing:
            self.items[self.items.index(existing)] = item
        else:
            self.items.append(item)
        self._save_index()
        return item

    @_locked
    def all(self) -> list:
        """A copy of the list of saved Bibles (safe to use while the export thread saves another one)."""
        return list(self.items)

    @_locked
    def disk_size(self) -> int:
        """Bytes the saved Bibles take on the disk."""
        total = 0
        for item in self.items:
            try:
                total += (self.folder / f"{item.code}.json").stat().st_size
            except OSError:
                pass
        return total

    @_locked
    def set_numbering(self, code: str, numbering: str) -> None:
        item = self.get(code)
        if item and numbering in NUMBERINGS:
            item.numbering = numbering
            self._save_index()

    @_locked
    def remove(self, code: str) -> None:
        item = self.get(code)
        if item is None:
            return
        # only ever delete a file inside the library folder
        if re.fullmatch(r"[a-z0-9-]+", code):
            try:
                (self.folder / f"{code}.json").unlink()
            except FileNotFoundError:
                pass
        self.items.remove(item)
        self._save_index()
