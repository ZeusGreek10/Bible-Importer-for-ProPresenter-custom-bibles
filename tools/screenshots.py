"""Takes screenshots of the window with sample data (no network), to compare with the approved renderings.

    QT_QPA_PLATFORM=offscreen python tools/screenshots.py OUTPUT_FOLDER
"""

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_SCALE_FACTOR", "1.5")      # the renderings are 1.5x
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication

from lpbibles.backend import Backend
from lpbibles.catalog import FreeCatalog, Language
from lpbibles.library import Library
from lpbibles.model import Entry, ParsedBible
from lpbibles.ui import theme
from lpbibles.ui.main_window import MainWindow

ENGLISH = [("American Standard Version", "ASV", 3), ("Berean Standard Bible", "BSB", 4), ("Bible in Basic English", "BBE", 3),
           ("Darby Bible", "DARBY", 4), ("Douay-Rheims 1899", "DRA", 4), ("English Revised Version", "ERV", 4),
           ("Geneva Bible 1599", "GNV", 4), ("King James Version", "KJV", 4), ("Webster's Bible", "WBT", 4),
           ("World English Bible", "WEB", 4), ("World Messianic Bible", "WMB", 4), ("Young's Literal Translation", "YLT", 4)]
OTHER = {"Russian": 4, "Dutch": 3, "Spanish": 6, "German": 5, "Greek": 4, "French": 5, "Portuguese": 4, "Ukrainian": 2, "Chinese": 3}
DUTCH_LICENSED = [("Nieuwe Bijbelvertaling 2021", "NBV21"), ("Herziene Statenvertaling", "HSV"), ("BasisBijbel", "BB"),
                  ("Groot Nieuws Bijbel", "GNB"), ("Willibrordvertaling 1995", "WV95"), ("Het Boek", "HTB")]


def free_entries():
    out = [Entry(key=f"getbible:{s.lower()}", source="getbible", name=n, short=s, language="English", size_mb=float(mb))
           for n, s, mb in ENGLISH]
    for lang, count in OTHER.items():
        for i in range(count):
            out.append(Entry(key=f"getbible:{lang}{i}", source="getbible", name=f"{lang} Bible {i + 1}", short=f"{lang[:2].upper()}{i + 1}",
                             language=lang, size_mb=4.0))
    return out


class FakeBackend(Backend):
    def __init__(self, stale=False):
        super().__init__(Path(tempfile.mkdtemp()))
        self.stale = stale

    def load_free(self, cancel):
        return FreeCatalog(free_entries(), stale=self.stale)

    def bc_languages(self, cancel):
        counts = {"English": 41, "Russian": 9, "Dutch": 6, "Spanish": 22, "German": 17, "Greek": 5, "French": 14,
                  "Portuguese": 13, "Ukrainian": 4, "Chinese": 11}
        return [Language(english=k, native=k, count=v, tag=k[:3].lower()) for k, v in counts.items()], False

    def bc_versions(self, tag, english, cancel):
        entries = [Entry(key=f"biblecom:{s}", source="biblecom", name=n, short=s, language="Dutch", licensed=True,
                         ref={"id": i}) for i, (n, s) in enumerate(DUTCH_LICENSED)]
        return entries, False


def sample_library():
    lib = Library(Path(tempfile.mkdtemp()))
    for name, short, lang, code, key in (("King James Version", "KJV", "English", "en", "getbible:kjv"),
                                         ("World English Bible", "WEB", "English", "en", "getbible:web"),
                                         ("Синодальный перевод", "Синодальный", "Russian", "ru", "")):
        pb = ParsedBible(name=name, short=short, language=lang, lang_code=code)
        for b in range(1, 67):
            pb.add(b, 1, 1, "x")
        lib.save(pb, "getbible" if key else "file", key)
    return lib


def pump(app, seconds=0.4, until=None):
    end = time.time() + seconds
    while time.time() < end or (until and not until() and time.time() < end + 10):
        app.processEvents()
        time.sleep(0.01)
        if until and until():
            break
    app.processEvents()


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv)
    app.setStyleSheet(theme.stylesheet())

    w = MainWindow(sample_library(), FakeBackend(), system_language="English")
    w.show()
    pump(app, until=lambda: w.free_loaded)
    pump(app)
    row = w.rows.get("getbible:gnv")
    row.set_state("busy", "Downloading… 34%", 0.34)
    w.set_message("✓ KJV downloaded", "ok")
    pump(app, 0.2)
    w.grab().save(str(out / "01-free.png"))

    w.tab_buttons["biblecom"].click()
    pump(app, until=lambda: w.bc_loaded)
    # choose Dutch
    for i in range(w.langs.count()):
        if w.langs.item(i).data(0x0100).english == "Dutch":
            w.langs.setCurrentRow(i)
    pump(app, until=lambda: "dut" in w.bc_entries)
    pump(app)
    r = w.rows["biblecom:NBV21"]
    r.set_state("busy", "Downloading chapter by chapter… 412 of 1,189 · about 3 min", 412 / 1189)
    w.set_message("Bible.com can change without notice. If a download fails, import a file instead.", "dim")
    pump(app, 0.2)
    w.grab().save(str(out / "02-biblecom.png"))

    r.set_state("failed")
    w.set_message("Bible.com did not answer. Try again later, or import a file.", "error")
    pump(app, 0.2)
    w.grab().save(str(out / "03b-failed.png"))
    w.close()

    w2 = MainWindow(sample_library(), FakeBackend(stale=True), system_language="English")
    w2.show()
    pump(app, until=lambda: w2.free_loaded)
    pump(app)
    w2.grab().save(str(out / "03a-offline.png"))
    w2.close()
    print("saved to", out)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "screenshots"))
