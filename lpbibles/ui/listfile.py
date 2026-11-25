"""Remembers "Your list" between launches (a small file in the app's folder)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from ..library import NUMBERINGS, Library
from ..model import Entry
from .widgets import ListItem


def save_list(path: Path, items: list[ListItem]) -> None:
    doc = {"format": 1, "items": [
        {"key": i.key, "short": i.short, "name": i.name, "numbering": i.numbering, "code": i.code,
         "entry": asdict(i.entry) if i.entry is not None else None} for i in items]}
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def load_list(path: Path, library: Library) -> list[ListItem]:
    """The list as it was, with every Bible marked saved or waiting by what is on the disk now.
    A Bible that came from a file is only kept while its saved copy still exists (there is nothing to download)."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        raw = doc["items"]
    except (OSError, ValueError, KeyError, TypeError):
        return []
    out: list[ListItem] = []
    seen: set[str] = set()
    for d in raw:
        try:
            key = str(d["key"])
            if key in seen:
                continue
            entry = Entry(**d["entry"]) if d.get("entry") else None
            code = str(d.get("code") or "")
            if code and library.get(code) is None:
                code = ""
            if not code and entry is not None:
                code = next((i.code for i in library.items if i.source_key == entry.key), "")
            if entry is None and not code:
                continue
            numbering = d.get("numbering") if d.get("numbering") in NUMBERINGS else "kjv"
            note = ("from a file" if entry is None else "saved on this computer") if code else ""
            out.append(ListItem(key=key, entry=entry, short=str(d["short"]), name=str(d["name"]),
                                status="saved" if code else "waiting", note=note, numbering=numbering, code=code))
            seen.add(key)
        except (KeyError, TypeError):
            continue
    return out
