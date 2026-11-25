import json
import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QSettings
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QMessageBox

from lpbibles import export_lp, export_pp, netutil
from lpbibles.backend import Backend
from lpbibles.catalog import FreeCatalog, Language
from lpbibles.library import Library
from lpbibles.model import BibleError, Entry, ParsedBible
from lpbibles.ui import theme
from lpbibles.ui.dialogs import ExplainDialog
from lpbibles.ui.main_window import BIBLECOM_FAIL, MainWindow


def bible(name="Test Bible", short="TB", lang="English", code="en"):
    pb = ParsedBible(name=name, short=short, language=lang, lang_code=code)
    for b in range(1, 67):
        for v in (1, 2, 3):
            pb.add(b, 1, v, f"Book {b} verse {v}.")
    return pb


class Fake(Backend):
    def __init__(self, tmp):
        super().__init__(tmp)
        self.stale = False
        self.errors = {}          # key -> exception raised once
        self.slow = set()
        self.bc_fail = False
        self.downloads = []

    def load_free(self, cancel):
        e = [Entry(key=f"getbible:{s.lower()}", source="getbible", name=n, short=s, language="English", lang_code="en", size_mb=4.0)
             for n, s in (("King James Version", "KJV"), ("World English Bible", "WEB"), ("Slow Bible", "SLOW"))]
        e.append(Entry(key="getbible:nl", source="getbible", name="Nederlandse Bijbel", short="NB", language="Dutch", lang_code="nl"))
        return FreeCatalog(e, stale=self.stale)

    def bc_languages(self, cancel):
        if self.bc_fail:
            raise netutil.NetworkError("The server answered 403.")
        return [Language("Dutch", "Nederlands", None, "nld")], False

    def bc_versions(self, tag, english, cancel):
        return [Entry(key="biblecom:1", source="biblecom", name="Nieuwe Bijbelvertaling 2021", short="NBV21",
                      language=english, lang_code="nl", licensed=True, ref={"id": 1})], False

    def download(self, entry, cancel, progress):
        self.downloads.append(entry.key)
        progress(1, 4)
        if entry.key in self.errors:
            raise self.errors.pop(entry.key)
        if entry.key in self.slow:
            while not cancel.is_set():
                time.sleep(0.01)
            raise netutil.Cancelled()
        progress(4, 4)
        return bible(entry.name, entry.short, entry.language, entry.lang_code)


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    a.setStyleSheet(theme.stylesheet())
    return a


def pump(app, cond=lambda: False, timeout=6.0):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    app.processEvents()
    return cond()


def make(app, tmp_path, platform="win"):
    backend = Fake(tmp_path / "cache")
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat)
    w = MainWindow(Library(tmp_path / "data"), backend, system_language="English", platform=platform, settings=settings)
    w.folder = tmp_path / "out"
    w.show()
    assert pump(app, lambda: w.free_loaded)
    pump(app, lambda: bool(w.rows))
    return w


@pytest.fixture
def win(app, tmp_path):
    w = make(app, tmp_path)
    yield w
    w.close()


def add(w, key):
    w.add_to_list(w._entries_by_key()[key])


def finished(app, w):
    return pump(app, lambda: not w.exporting and w.last_done is not None)


def test_start(win):
    assert win.selected["free"] == "English"
    assert [r.entry.short for r in win.rows.values()] == ["KJV", "SLOW", "WEB"]
    assert win.amber.isHidden() and win.items == []
    assert not win.go.isEnabled()


def test_add_and_remove(win):
    add(win, "getbible:kjv")
    assert [i.short for i in win.items] == ["KJV"]
    assert win.rows["getbible:kjv"].inlist.isHidden() is False and win.rows["getbible:kjv"].add.isHidden()
    assert win.go.text() == "Export 1 Bible" and win.go.isEnabled()
    add(win, "getbible:web")
    assert win.go.text() == "Export 2 Bibles" and win.count_label.text() == "2 Bibles"
    win.remove_from_list("getbible:kjv")
    assert [i.short for i in win.items] == ["WEB"]
    assert win.rows["getbible:kjv"].add.isHidden() is False


def test_export_files_for_propresenter(app, win, tmp_path):
    add(win, "getbible:kjv")
    add(win, "getbible:web")
    win._go_clicked()
    assert finished(app, win)
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["KJV.rvbible", "WEB.rvbible"]
    assert [i.status for i in win.items] == ["done", "done"]
    assert win.done_box.isHidden() is False and "2 Bibles saved" in win.done_head.text()
    assert "see the ? below" in win.done_text.text()
    assert win.library.is_installed("getbible:kjv")
    # what was written is a real Bible
    from lpbibles import importers
    assert importers.read_files([tmp_path / "out" / "KJV.rvbible"]).verse_count == 66 * 3
    # nothing left to do: the button is off until the list changes
    assert not win.go.isEnabled()


def test_export_for_live_presenter_with_numbering(app, win, tmp_path):
    win.seg.buttons["lp"].click()
    assert win.fmt == "lp"
    add(win, "getbible:kjv")
    row = win.item_rows["getbible:kjv"]
    assert not row.picker.isHidden()                      # the numbering picker shows in this mode only
    row.picker.setCurrentIndex(row.picker.findData("synodal"))
    win._go_clicked()
    assert finished(app, win)
    d = json.loads((tmp_path / "out" / "KJV.json").read_text(encoding="utf-8"))
    assert d["numbering"] == "synodal" and len(d["books"]) == 66
    assert "Import a file" in win.done_text.text()
    # exporting again never overwrites a file: a second copy gets its own name
    win.seg.buttons["pp"].click()
    win.seg.buttons["lp"].click()
    assert win.items[0].status == "saved"
    win._go_clicked()
    assert finished(app, win)
    assert (tmp_path / "out" / "KJV (2).json").exists()


def test_format_choice_is_remembered(app, tmp_path):
    w = make(app, tmp_path)
    w.seg.buttons["lp"].click()
    w.close()
    w2 = make(app, tmp_path)
    assert w2.fmt == "lp" and w2.seg.buttons["lp"].isChecked()
    w2.close()


def test_mac_adds_to_propresenter(app, tmp_path, monkeypatch):
    w = make(app, tmp_path, platform="mac")
    target = tmp_path / "pp"
    monkeypatch.setattr(export_pp, "mac_bible_folder", lambda *a, **k: target)
    assert not w.save_btn.isHidden() and w.dest_row.isHidden() and w.help_row.isHidden()
    add(w, "getbible:kjv")
    assert w.go.text() == "Add 1 Bible to ProPresenter"
    w._go_clicked()
    assert finished(app, w)
    assert (target / "KJV.rvbible").exists()
    assert "added to ProPresenter" in w.done_head.text() and "close and reopen" in w.done_text.text()
    assert w.items[0].done_text == "Added ✓"
    w.close()


def test_windows_has_the_question_mark_and_no_install(win):
    assert win.fmt == "pp" and not win.help_row.isHidden() and win.save_btn.isHidden()
    win.seg.buttons["lp"].click()
    assert win.help_row.isHidden()


def test_failure_then_retry(app, win, tmp_path):
    win.backend.errors["getbible:web"] = netutil.NetworkError("No internet connection.", offline=True)
    add(win, "getbible:kjv")
    add(win, "getbible:web")
    win._go_clicked()
    assert finished(app, win)
    statuses = {i.short: i.status for i in win.items}
    assert statuses == {"KJV": "done", "WEB": "failed"}
    assert win.done_head.text() == "✓ 1 of 2 Bibles saved"
    assert win._item("getbible:web").note == "No internet connection."
    assert win.go.isEnabled() and win.go.text() == "Export 1 Bible"          # the failed one can be tried again
    win._go_clicked()
    assert finished(app, win)
    assert [i.status for i in win.items] == ["done", "done"]
    assert (tmp_path / "out" / "WEB.rvbible").exists() and not (tmp_path / "out" / "KJV (2).rvbible").exists()


def test_cancel(app, win):
    win.backend.slow.add("getbible:slow")
    add(win, "getbible:slow")
    win._go_clicked()
    assert pump(app, lambda: win._item("getbible:slow").status == "busy")
    assert win.go.text() == "Cancel"
    win._go_clicked()
    assert pump(app, lambda: not win.exporting)
    assert win._item("getbible:slow").status == "waiting"
    assert "cancelled" in win.done_head.text().lower()
    assert not win.library.is_installed("getbible:slow")


def test_closing_during_an_export_does_not_hang(app, win):
    win.backend.slow.add("getbible:slow")
    add(win, "getbible:slow")
    win._go_clicked()
    pump(app, lambda: win._item("getbible:slow").status == "busy")
    start = time.time()
    win.close()
    assert time.time() - start < 4.5


def test_folder_that_cannot_be_used(app, win, tmp_path, monkeypatch):
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a))
    blocker = tmp_path / "file.txt"
    blocker.write_text("x")
    win.folder = blocker / "sub"          # a folder inside a file cannot be made
    add(win, "getbible:kjv")
    win._go_clicked()
    assert warned and not win.exporting and win.items[0].status == "waiting"


def test_saved_copy_is_used_the_second_time(app, win):
    add(win, "getbible:kjv")
    win._go_clicked()
    assert finished(app, win)
    assert win.backend.downloads == ["getbible:kjv"]
    win.seg.buttons["lp"].click()          # changing the format makes the Bible ready again
    win._go_clicked()
    assert finished(app, win)
    assert win.backend.downloads == ["getbible:kjv"]      # not downloaded again


def test_changing_the_list_clears_the_done_box(app, win):
    add(win, "getbible:kjv")
    win._go_clicked()
    assert finished(app, win)
    assert not win.done_box.isHidden()
    add(win, "getbible:web")
    assert win.done_box.isHidden() and win._item("getbible:kjv").status == "saved"


def test_stale_list_message(app, tmp_path):
    backend = Fake(tmp_path / "c")
    backend.stale = True
    w = MainWindow(Library(tmp_path / "d"), backend, system_language="English", platform="win",
                   settings=QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat))
    w.show()
    assert pump(app, lambda: w.free_loaded)
    assert "Could not reach the list. Showing the saved list." in w.message.text()
    w.close()


def test_bible_com_tab(app, win):
    win.tab_buttons["biblecom"].click()
    assert not win.amber.isHidden()
    assert pump(app, lambda: win.bc_loaded)
    assert pump(app, lambda: "biblecom:1" in win.rows)
    assert win.rows["biblecom:1"].entry.licensed
    add(win, "biblecom:1")
    win.backend.errors["biblecom:1"] = netutil.NetworkError("The server answered 403.")
    win._go_clicked()
    assert finished(app, win)
    assert win._item("biblecom:1").status == "failed" and win._item("biblecom:1").note == BIBLECOM_FAIL
    win.tab_buttons["free"].click()
    assert win.amber.isHidden()


def test_bible_com_failure_message(app, tmp_path):
    w = make(app, tmp_path)
    w.backend.bc_fail = True
    w.tab_buttons["biblecom"].click()
    assert pump(app, lambda: w.message.text() == BIBLECOM_FAIL)
    w.close()


def test_from_a_file(app, win, tmp_path):
    src = export_lp.write(bible("Church Bible", "CB"), tmp_path / "cb.json")
    win.tab_buttons["file"].click()
    assert not win.file_page.isHidden() and win.browse.isHidden()
    win.import_files([src])
    assert pump(app, lambda: bool(win.items))
    item = win.items[0]
    assert item.short == "CB" and item.status == "saved" and item.note == "from a file" and item.entry is None
    win._go_clicked()
    assert finished(app, win)
    assert (tmp_path / "out" / "CB.rvbible").exists()


def test_a_bad_file_is_a_plain_message(app, win, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    win.import_files([bad])
    assert pump(app, lambda: "No verses" in win.file_message.text())
    assert win.items == []


def test_explanation_box(app, win):
    d = ExplainDialog(win)
    d.show()
    d.copy_btn.click()
    text = QGuiApplication.clipboard().text()
    assert text.startswith("Name code | Bible | Language") and "RVA" in text
    assert d.copy_btn.text() == "Copied ✓"
    d.close()
