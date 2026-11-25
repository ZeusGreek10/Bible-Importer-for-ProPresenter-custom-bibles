"""Takes screenshots of the window with sample data (no network), to compare with the drawings in design/.

    QT_QPA_PLATFORM=offscreen python tools/screenshots.py OUTPUT_FOLDER
"""

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_SCALE_FACTOR", "2")      # the drawings are 2x
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from lpbibles.backend import Backend
from lpbibles.catalog import FreeCatalog, Language
from lpbibles.library import Library
from lpbibles.model import Entry, ParsedBible
from lpbibles.ui import theme
from lpbibles.ui.dialogs import ExplainDialog
from lpbibles.ui.main_window import MainWindow

ENGLISH = [("American Standard Version", "ASV", 3), ("Berean Standard Bible", "BSB", 4), ("Bible in Basic English", "BBE", 3),
           ("Darby Bible", "DARBY", 4), ("Douay-Rheims 1899", "DRA", 4), ("English Revised Version", "ERV", 4),
           ("Geneva Bible 1599", "GNV", 4), ("King James Version", "KJV", 4), ("Webster's Bible", "WBT", 4),
           ("World English Bible", "WEB", 4), ("World Messianic Bible", "WMB", 4), ("Young's Literal Translation", "YLT", 4)]
OTHER = {"Russian": 4, "Dutch": 3, "Spanish": 6, "German": 5, "Greek": 4, "French": 5, "Portuguese": 4, "Ukrainian": 2, "Chinese": 3}
DUTCH_LICENSED = [("Nieuwe Bijbelvertaling 2021", "NBV21"), ("Herziene Statenvertaling", "HSV"), ("BasisBijbel", "BB"),
                  ("Groot Nieuws Bijbel", "GNB"), ("Willibrordvertaling 1995", "WV95"), ("Het Boek", "HTB")]


def free_entries():
    out = [Entry(key=f"getbible:{s.lower()}", source="getbible", name=n, short=s, language="English", size_mb=float(mb),
                 lang_code="en") for n, s, mb in ENGLISH]
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
        from lpbibles.catalog import NATIVE
        return [Language(english=k, native=NATIVE.get(k, k), count=v, tag=k[:3].lower()) for k, v in counts.items()], False

    def bc_versions(self, tag, english, cancel):
        return [Entry(key=f"biblecom:{s}", source="biblecom", name=n, short=s, language=english, licensed=True,
                      lang_code="nl", ref={"id": i}) for i, (n, s) in enumerate(DUTCH_LICENSED)], False


def sample_library():
    lib = Library(Path(tempfile.mkdtemp()))
    for name, short, lang, code, key in (("King James Version", "KJV", "English", "en", "getbible:kjv"),
                                         ("World English Bible", "WEB", "English", "en", "getbible:web")):
        pb = ParsedBible(name=name, short=short, language=lang, lang_code=code)
        for b in range(1, 67):
            pb.add(b, 1, 1, "x")
        lib.save(pb, "getbible", key)
    return lib


def pump(app, seconds=0.4, until=None):
    end = time.time() + seconds
    while time.time() < end or (until and not until() and time.time() < end + 10):
        app.processEvents()
        time.sleep(0.01)
        if until and until():
            break
    app.processEvents()


def make(app, platform, system_language="English"):
    settings = QSettings(tempfile.mkdtemp() + "/s.ini", QSettings.IniFormat)
    w = MainWindow(sample_library(), FakeBackend(), system_language=system_language, platform=platform, settings=settings)
    w.folder = Path("Documents/Bible Importer")
    w.show()
    pump(app, until=lambda: w.free_loaded)
    pump(app, 0.3)
    return w


def add(w, key):
    w.add_to_list(w._entries_by_key()[key])


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv)
    app.setStyleSheet(theme.stylesheet())

    # 01 Mac, Free Bibles, ProPresenter
    w = make(app, "mac")
    for k in ("getbible:kjv", "getbible:bsb", "getbible:web"):
        add(w, k)
    w.library.disk_size = lambda: 12_400_000        # the sample Bibles are tiny; real ones are about 4 MB each
    w._refresh_panel()
    pump(app, 0.2)
    w.grab().save(str(out / "01-Main-Free-ProPresenter.png"))

    # 01W Windows
    w.close()
    w = make(app, "win")
    for k in ("getbible:kjv", "getbible:bsb", "getbible:darby"):
        add(w, k)
    pump(app, 0.2)
    w.grab().save(str(out / "01W-Main-ProPresenter-on-Windows.png"))

    # 06 explanation (on Windows)
    d = ExplainDialog(w)
    d.show()
    pump(app, 0.3)
    d.grab().save(str(out / "06-Windows-explanation-dialog.png"))
    d.close()

    # 07 Windows, done
    w._on_export_event("getbible:kjv", "done", "KJV.rvbible", -1, "kjv")
    w._on_export_event("getbible:bsb", "done", "BSB.rvbible", -1, "bsb")
    w._on_export_event("getbible:darby", "done", "DARBY.rvbible", -1, "darby")
    w.last_done = {"ok": {"a": "x", "b": "y", "c": "z"}, "failed": {}, "mode": "files", "dest": "Documents/Bible Importer", "fmt": "pp"}
    w._refresh_panel()
    pump(app, 0.2)
    w.grab().save(str(out / "07-Done-ProPresenter-on-Windows.png"))
    w.close()

    # 08 Mac, done (added)
    w = make(app, "mac")
    for k in ("getbible:kjv", "getbible:bsb", "getbible:darby"):
        add(w, k)
    w.export_mode = "install"
    for k, c in (("getbible:kjv", "kjv"), ("getbible:bsb", "bsb"), ("getbible:darby", "darby")):
        w._on_export_event(k, "done", "added to ProPresenter", -1, c)
    w.last_done = {"ok": {"a": "x", "b": "y", "c": "z"}, "failed": {}, "mode": "install", "dest": "", "fmt": "pp"}
    w._refresh_panel()
    pump(app, 0.2)
    w.grab().save(str(out / "08-Done-ProPresenter-on-Mac.png"))
    w.close()

    # 02 Bible.com, Live Presenter
    w = make(app, "mac")
    w.seg.buttons["lp"].click()
    w.tab_buttons["biblecom"].click()
    pump(app, until=lambda: w.bc_loaded)
    for i in range(w.langs.count()):
        if w.langs.item(i).data(0x0100).english == "Dutch":
            w.langs.setCurrentRow(i)
    pump(app, until=lambda: "dut" in w.bc_entries)
    pump(app, 0.3)
    add(w, "biblecom:NBV21")
    add(w, "biblecom:HSV")
    w.set_message("Bible.com can change without notice. If a download fails, import a file instead.", "dim")
    pump(app, 0.2)
    w.grab().save(str(out / "02-Main-BibleCom-LivePresenter.png"))

    # 03 exporting
    w.tab_buttons["free"].click()
    w.set_message("", "dim")
    pump(app, 0.3)
    w.items.clear()
    w._refresh_panel()
    for k in ("getbible:kjv", "getbible:bsb", "getbible:darby"):
        add(w, k)
    w.exporting = True
    w.export_total = 3
    w.export_mode = "files"
    w.export_seen = {"getbible:kjv", "getbible:bsb"}
    w.count_label.setText("Exporting 2 of 3…")
    w._on_export_event("getbible:kjv", "done", "kjv.json", -1, "kjv")
    w._on_export_event("getbible:bsb", "busy", "Downloading… 34%", 0.34, "")
    w._on_export_event("getbible:darby", "waiting", "", -1, "")
    w._refresh_export_block(2)
    w.count_label.setText("Exporting 2 of 3…")
    pump(app, 0.2)
    w.grab().save(str(out / "03-Exporting.png"))

    # 04 done with one failure
    w.exporting = False
    w._on_export_event("getbible:bsb", "done", "bsb.json", -1, "bsb")
    w._on_export_event("getbible:darby", "failed", "No internet connection.", -1, "")
    w.last_done = {"ok": {"a": "x", "b": "y"}, "failed": {"c": "No internet connection."}, "mode": "files",
                   "dest": "Documents/Bible Importer", "fmt": "lp"}
    w._refresh_panel()
    pump(app, 0.2)
    w.grab().save(str(out / "04-Done.png"))

    # 05 from a file
    w.items.clear()
    w.last_done = None
    w.fmt = "pp"
    w.seg.set_value("pp")
    w.platform = "mac"
    w._refresh_panel()
    w.tab_buttons["file"].click()
    from lpbibles.ui.widgets import ListItem
    w.items.append(ListItem(key="file:cb", entry=None, short="CB", name="Church Bible (cb.json)", status="saved", note="from a file"))
    w._refresh_panel()
    pump(app, 0.2)
    w.grab().save(str(out / "05-From-a-file.png"))
    w.close()
    print("saved to", out)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "screenshots"))
