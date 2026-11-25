import json
import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QMessageBox

from lpbibles import export_lp, netutil
from lpbibles.backend import Backend
from lpbibles.catalog import FreeCatalog, Language
from lpbibles.library import Library
from lpbibles.model import BibleError, Entry, ParsedBible
from lpbibles.ui import theme
from lpbibles.ui.main_window import BIBLECOM_FAIL, MainWindow


def bible(name="Test Bible", short="TB"):
    pb = ParsedBible(name=name, short=short, language="English", lang_code="en")
    for b in range(1, 67):
        for v in (1, 2, 3):
            pb.add(b, 1, v, f"Book {b} verse {v}.")
    return pb


class Fake(Backend):
    def __init__(self, tmp):
        super().__init__(tmp)
        self.stale = False
        self.fail_once = set()
        self.slow = set()
        self.bc_fail = False
        self.errors = {}

    def load_free(self, cancel):
        e = [Entry(key=f"getbible:{s.lower()}", source="getbible", name=n, short=s, language="English", size_mb=4.0)
             for n, s in (("King James Version", "KJV"), ("World English Bible", "WEB"), ("Slow Bible", "SLOW"))]
        e.append(Entry(key="getbible:nl", source="getbible", name="Nederlandse Bijbel", short="NB", language="Dutch"))
        return FreeCatalog(e, stale=self.stale)

    def bc_languages(self, cancel):
        if self.bc_fail:
            raise netutil.NetworkError("The server answered 403.")
        return [Language("Dutch", "Nederlands", None, "nld")], False

    def bc_versions(self, tag, english, cancel):
        return [Entry(key="biblecom:1", source="biblecom", name="Nieuwe Bijbelvertaling 2021", short="NBV21",
                      language=english, licensed=True, ref={"id": 1})], False

    def download(self, entry, cancel, progress):
        progress(1, 4)
        if entry.key in self.errors:
            raise self.errors[entry.key]
        if entry.key in self.slow:
            while not cancel.is_set():
                time.sleep(0.01)
            raise netutil.Cancelled()
        if entry.key in self.fail_once:
            self.fail_once.discard(entry.key)
            raise netutil.NetworkError("No internet connection.", offline=True)
        progress(4, 4)
        return bible(entry.name, entry.short)


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    a.setStyleSheet(theme.stylesheet())
    return a


def pump(app, cond=lambda: False, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    app.processEvents()
    return cond()


@pytest.fixture
def win(app, tmp_path):
    backend = Fake(tmp_path / "cache")
    lib = Library(tmp_path / "data")
    w = MainWindow(lib, backend, system_language="English")
    w.show()
    assert pump(app, lambda: w.free_loaded)
    pump(app, lambda: bool(w.rows))
    yield w
    w.close()


def test_start_shows_english_list(win):
    assert win.selected["free"] == "English"
    assert [r.entry.short for r in win.rows.values()] == ["KJV", "SLOW", "WEB"]
    assert win.message.text() == ""
    assert win.amber.isHidden()


def test_download_installs_and_shows_it(app, win):
    win.start_download(win.rows["getbible:kjv"].entry)
    assert win.rows["getbible:kjv"].state == "busy"
    assert pump(app, lambda: win.library.is_installed("getbible:kjv"))
    pump(app, lambda: win.rows["getbible:kjv"].state == "installed")
    assert win.rows["getbible:kjv"].state == "installed"
    assert "KJV downloaded" in win.message.text()
    assert win.inst_layout.count() >= 2           # row + stretch


def test_failure_then_retry(app, win):
    win.backend.fail_once.add("getbible:web")
    win.start_download(win.rows["getbible:web"].entry)
    assert pump(app, lambda: win.rows["getbible:web"].state == "failed")
    assert "Could not download WEB" in win.message.text() and "No internet" in win.message.text()
    assert not win.library.is_installed("getbible:web")
    win.rows["getbible:web"].retry.click()
    assert pump(app, lambda: win.library.is_installed("getbible:web"))


def test_cancel(app, win):
    win.backend.slow.add("getbible:slow")
    win.start_download(win.rows["getbible:slow"].entry)
    assert pump(app, lambda: "getbible:slow" in win.busy_text)
    win.rows["getbible:slow"].cancel.click()
    assert pump(app, lambda: win.rows["getbible:slow"].state == "idle")
    assert win.message.text() == "Download cancelled."
    assert not win.library.is_installed("getbible:slow")


def test_closing_during_a_download_does_not_hang(app, win):
    win.backend.slow.add("getbible:slow")
    win.start_download(win.rows["getbible:slow"].entry)
    pump(app, lambda: "getbible:slow" in win.busy_text)
    start = time.time()
    win.close()
    assert time.time() - start < 4.5


def test_stale_list_message(app, tmp_path):
    backend = Fake(tmp_path / "c")
    backend.stale = True
    w = MainWindow(Library(tmp_path / "d"), backend, system_language="English")
    w.show()
    assert pump(app, lambda: w.free_loaded)
    assert "Could not reach the list. Showing the saved list." in w.message.text()
    w.close()


def test_bible_com_tab(app, win):
    win.tab_buttons["biblecom"].click()
    assert not win.amber.isHidden()
    assert pump(app, lambda: win.bc_loaded)
    assert pump(app, lambda: "biblecom:1" in win.rows)
    row = win.rows["biblecom:1"]
    assert row.entry.licensed and row.cancel.text() == "Cancel"
    win.start_download(row.entry)
    assert pump(app, lambda: win.library.is_installed("biblecom:1"))
    win.tab_buttons["free"].click()
    assert win.amber.isHidden() and "getbible:kjv" in win.rows


def test_bible_com_failure_is_plain(app, tmp_path):
    backend = Fake(tmp_path / "c")
    backend.bc_fail = True
    w = MainWindow(Library(tmp_path / "d"), backend, system_language="English")
    w.show()
    pump(app, lambda: w.free_loaded)
    w.tab_buttons["biblecom"].click()
    assert pump(app, lambda: w.message.text() == BIBLECOM_FAIL)
    w.close()


def test_import_remove_and_numbering(app, win, tmp_path, monkeypatch):
    src = export_lp.write(bible("Church Bible", "CB"), tmp_path / "cb.json")
    win.import_files([src])
    assert pump(app, lambda: win.library.get("cb") is not None)
    assert "imported" in win.message.text()
    win.library.set_numbering("cb", "synodal")
    win._refresh_installed()
    # a Bible that came from a file asks before it is removed
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    win._remove("cb")
    assert win.library.get("cb") is not None
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    win._remove("cb")
    assert win.library.get("cb") is None and not (win.library.folder / "cb.json").exists()


def test_bad_file_is_a_plain_message(app, win, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    win.import_files([bad])
    assert pump(app, lambda: "No verses" in win.message.text() or "could not" in win.message.text().lower())
    assert win.library.items == []


def test_exports(app, win, tmp_path):
    win.start_download(win.rows["getbible:kjv"].entry)
    assert pump(app, lambda: win.library.is_installed("getbible:kjv"))
    code = win.library.items[0].code
    win._export_json(code, str(tmp_path / "out.json"))
    d = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
    assert d["translation"] == "King James Version" and len(d["books"]) == 66
    win._export_rvbible(code, str(tmp_path / "out.rvbible"))
    assert (tmp_path / "out.rvbible").stat().st_size > 1000
    assert "Saved out.rvbible" in win.message.text()


def test_bible_com_errors_say_the_right_thing(app, win):
    win.tab_buttons["biblecom"].click()
    pump(app, lambda: "biblecom:1" in win.rows)
    entry = win.rows["biblecom:1"].entry
    win.backend.errors["biblecom:1"] = netutil.NetworkError("The server answered 403.")
    win.start_download(entry)
    assert pump(app, lambda: win.rows["biblecom:1"].state == "failed")
    assert win.message.text() == BIBLECOM_FAIL
    # a Bible that came back too small is not "Bible.com did not answer"
    win.backend.errors["biblecom:1"] = BibleError("This Bible has only 5 books, so it was not added.")
    win.rows["biblecom:1"].retry.click()
    assert pump(app, lambda: "only 5 books" in win.message.text())
    assert BIBLECOM_FAIL not in win.message.text()
