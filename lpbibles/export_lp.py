"""Export for Live Presenter: a JSON file in the getBible layout.

Live Presenter's "Import Zefania or OSIS XML…" button (and the Add Bibles window's file import)
reads this layout. Extra fields (numbering, copyright) are ignored by older versions.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from .books import BOOKS
from .model import ParsedBible

# ISO 639-3 to ISO 639-1, for the languages churches use most. Live Presenter keeps the first two letters.
ISO3_TO_2 = {
    "eng": "en", "rus": "ru", "nld": "nl", "spa": "es", "deu": "de", "ell": "el", "grc": "el", "fra": "fr", "por": "pt",
    "ukr": "uk", "zho": "zh", "cmn": "zh", "jpn": "ja", "kor": "ko", "ita": "it", "pol": "pl", "ron": "ro", "arb": "ar",
    "ara": "ar", "heb": "he", "tur": "tr", "hun": "hu", "ces": "cs", "swe": "sv", "fin": "fi", "dan": "da", "nor": "no",
    "nob": "no", "bul": "bg", "srp": "sr", "hrv": "hr", "hin": "hi", "vie": "vi", "ind": "id", "hye": "hy", "kat": "ka",
    "swa": "sw", "tgl": "tl", "tha": "th", "fas": "fa", "pes": "fa", "slk": "sk", "slv": "sl", "lit": "lt", "lav": "lv",
    "est": "et", "bel": "be", "mkd": "mk", "sqi": "sq", "afr": "af", "amh": "am", "ben": "bn", "tam": "ta", "tel": "te",
}


def lang2(code: str) -> str:
    c = (code or "").lower()
    if len(c) == 2:
        return c
    return ISO3_TO_2.get(c, c[:2])


def to_dict(pb: ParsedBible, numbering: str = "kjv") -> dict:
    books = []
    for b in sorted(pb.verses):
        chapters = []
        for c in sorted(pb.verses[b]):
            chapters.append({"chapter": c, "verses": [{"verse": v, "text": t} for v, t in sorted(pb.verses[b][c].items())]})
        # "name" stays English: Live Presenter trusts the name before the number when it reads a file.
        books.append({"nr": b, "name": BOOKS[b - 1][1], "name_local": pb.name_of(b, 0), "chapters": chapters})
    return {
        "translation": pb.name, "abbreviation": pb.short, "lang": lang2(pb.lang_code), "language": pb.language,
        "direction": pb.direction.upper(), "numbering": numbering, "copyright": pb.copyright, "books": books,
    }


def write(pb: ParsedBible, path: Path, numbering: str = "kjv") -> Path:
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{uuid4().hex[:10]}.tmp")
    try:
        tmp.write_text(json.dumps(to_dict(pb, numbering), ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return path
