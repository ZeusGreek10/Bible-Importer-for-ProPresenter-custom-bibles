import json
import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QSettings
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox

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


def make(app, tmp_path, platform="win", list_path=None):
    backend = Fake(tmp_path / "cache")
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat)
    w = MainWindow(Library(tmp_path / "data"), backend, system_language="English", platform=platform, settings=settings,
                   list_path=list_path)
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
    assert "Get ready for ProPresenter" in win.done_text.text()
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
    win._go_clicked()                                   # the second click of a double click: ignored
    assert win.exporting and win.go.text() == "Cancel"
    win._export_started = 0.0                           # a person waits a moment, then clicks Cancel
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
    # the done box goes, but the Bible already exported stays exported: it is not exported (and put in ProPresenter) twice
    assert win.done_box.isHidden() and win._item("getbible:kjv").status == "done"
    assert win.go.text() == "Export 1 Bible"
    win._go_clicked()
    assert finished(app, win)
    assert sorted(p.name for p in (win.folder).iterdir()) == ["KJV.rvbible", "WEB.rvbible"]
    # a change of format does start again
    win.seg.buttons["lp"].click()
    assert win._item("getbible:kjv").status == "saved"


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


def test_delete_a_saved_copy(app, win, tmp_path, monkeypatch):
    asked = []
    monkeypatch.setattr(MainWindow, "_confirm_delete", lambda self, item, from_file: (asked.append(from_file) or True))
    add(win, "getbible:kjv")
    row = win.item_rows["getbible:kjv"]
    assert row.trash.isHidden()                              # nothing saved yet: nothing to delete
    win._go_clicked()
    assert finished(app, win)
    assert not row.trash.isHidden() and row.trash.isEnabled()
    assert win.library.is_installed("getbible:kjv")
    assert "saved on this computer" in [l.text() for l in win.rows["getbible:kjv"].findChildren(QLabel)]
    row.trash.click()
    assert asked == [False]
    assert not win.library.is_installed("getbible:kjv")
    assert not any((win.library.folder).glob("kjv*.json"))     # the file is gone from the disk
    item = win._item("getbible:kjv")
    assert item.status == "waiting" and item.code == "" and row.trash.isHidden()
    assert (tmp_path / "out" / "KJV.rvbible").exists()         # what was already exported is not touched
    # the list of Bibles on the left no longer says "saved on this computer" for it
    assert "saved on this computer" not in [l.text() for l in win.rows["getbible:kjv"].findChildren(QLabel)]
    # it can be exported again: it is downloaded again
    win._go_clicked()
    assert finished(app, win)
    assert win.backend.downloads == ["getbible:kjv", "getbible:kjv"]


def test_keep_it_when_asked(app, win, monkeypatch):
    monkeypatch.setattr(MainWindow, "_confirm_delete", lambda self, item, from_file: False)
    add(win, "getbible:kjv")
    win._go_clicked()
    assert finished(app, win)
    win.item_rows["getbible:kjv"].trash.click()
    assert win.library.is_installed("getbible:kjv") and win._item("getbible:kjv").status == "done"


def test_delete_a_bible_from_a_file_takes_it_out_of_the_list(app, win, tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(MainWindow, "_confirm_delete", lambda self, item, from_file: (seen.append(from_file) or True))
    src = export_lp.write(bible("Church Bible", "CB"), tmp_path / "cb.json")
    win.import_files([src])
    assert pump(app, lambda: bool(win.items))
    code = win.items[0].code
    win.item_rows[win.items[0].key].trash.click()
    assert seen == [True] and win.items == [] and win.library.get(code) is None


def test_no_delete_while_exporting(app, win):
    win.backend.slow.add("getbible:slow")
    add(win, "getbible:kjv")
    win._go_clicked()
    assert finished(app, win)
    add(win, "getbible:slow")
    win._go_clicked()
    assert pump(app, lambda: win._item("getbible:slow").status == "busy")
    assert not win.item_rows["getbible:kjv"].trash.isEnabled()
    win._go_clicked()
    pump(app, lambda: not win.exporting)


def test_delete_question_says_what_goes_and_what_stays():
    from lpbibles.ui.main_window import delete_message
    m = delete_message("King James Version", False)
    assert "Delete the saved copy of King James Version?" in m
    assert "only deletes the copy that Bible Importer keeps on this computer" in m
    assert "Files you saved in a folder, and Bibles already added to ProPresenter, stay as they are." in m
    assert "download it again later" in m
    assert "choosing the file again" in delete_message("My Bible", True) and "download it again" not in delete_message("My Bible", True)


def test_adding_to_propresenter_twice_keeps_the_first_file(app, tmp_path, monkeypatch):
    w = make(app, tmp_path, platform="mac")
    target = tmp_path / "pp"
    monkeypatch.setattr(export_pp, "mac_bible_folder", lambda *a, **k: target)
    add(w, "getbible:kjv")
    w._go_clicked()
    assert finished(app, w)
    first_bytes = (target / "KJV.rvbible").read_bytes()
    assert w._item("getbible:kjv").note == "added to ProPresenter"
    # add the same Bible again (a change to the list makes it ready again)
    w.seg.buttons["lp"].click()
    w.seg.buttons["pp"].click()
    w._go_clicked()
    assert finished(app, w)
    assert sorted(p.name for p in target.iterdir()) == ["KJV (2).rvbible", "KJV.rvbible"]
    assert (target / "KJV.rvbible").read_bytes() == first_bytes            # the first one was not replaced
    assert w._item("getbible:kjv").note == "added to ProPresenter as KJV (2).rvbible"
    w.close()


# ---- the ✕ on a Bible from a file, the remembered list, the cleanup ---------------------------------------

def import_church_bible(app, w, tmp_path, name="Church Bible", short="CB"):
    src = export_lp.write(bible(name, short), tmp_path / f"{short.lower()}.json")
    n = len(w.items)
    w.import_files([src])
    assert pump(app, lambda: len(w.items) == n + 1)
    return w.items[-1]


def test_x_on_a_downloaded_bible_keeps_its_saved_copy(app, win):
    add(win, "getbible:kjv")
    win._go_clicked()
    assert finished(app, win)
    win.remove_from_list("getbible:kjv")
    assert win.items == [] and win.library.is_installed("getbible:kjv")


def test_x_on_a_bible_from_a_file_deletes_its_saved_copy_after_asking(app, win, tmp_path, monkeypatch):
    item = import_church_bible(app, win, tmp_path)
    code = item.code
    assert win.item_rows[item.key].remove.toolTip().startswith("Delete this Bible")
    answers = iter([False, True])
    asked = []
    monkeypatch.setattr(MainWindow, "_confirm_delete", lambda self, it, from_file: (asked.append(from_file) or next(answers)))
    win.remove_from_list(item.key)                          # "Keep it": nothing happens
    assert win.items == [item] and win.library.get(code) is not None
    win.remove_from_list(item.key)                          # "Delete": gone from the list and from the disk
    assert asked == [True, True] and win.items == [] and win.library.get(code) is None
    assert not (win.library.folder / f"{code}.json").exists()


def test_the_list_is_remembered(app, tmp_path):
    lp = tmp_path / "list.json"
    w = make(app, tmp_path, list_path=lp)
    add(w, "getbible:kjv")
    w._go_clicked()
    assert finished(app, w)
    add(w, "getbible:web")                                  # in the list, not downloaded
    file_item = import_church_bible(app, w, tmp_path)
    w.seg.buttons["lp"].click()
    row = w.item_rows["getbible:web"]
    row.picker.setCurrentIndex(row.picker.findData("synodal"))
    w.close()

    w2 = make(app, tmp_path, list_path=lp)                  # a new start of the app
    assert [(i.short, i.status) for i in w2.items] == [("KJV", "saved"), ("WEB", "waiting"), ("CB", "saved")]
    assert w2._item("getbible:kjv").note == "saved on this computer" and w2._item(file_item.key).note == "from a file"
    assert w2._item("getbible:web").numbering == "synodal"
    assert not w2.item_rows["getbible:kjv"].trash.isHidden() and w2.item_rows["getbible:web"].trash.isHidden()
    assert w2.rows["getbible:kjv"].add.isHidden() and not w2.rows["getbible:kjv"].inlist.isHidden()   # "In list ✓"
    assert w2.go.text() == "Export 3 Bibles" or w2.go.text().startswith("Export")
    w2.close()


def test_a_bible_from_a_file_without_its_saved_copy_is_not_brought_back(app, tmp_path):
    lp = tmp_path / "list.json"
    w = make(app, tmp_path, list_path=lp)
    item = import_church_bible(app, w, tmp_path)
    (w.library.folder / f"{item.code}.json").unlink()      # the saved copy is gone from the disk
    w.close()
    w2 = make(app, tmp_path, list_path=lp)
    assert w2.items == []
    w2.close()


def test_a_damaged_list_file_is_ignored(app, tmp_path):
    lp = tmp_path / "list.json"
    lp.write_text("{ not json", encoding="utf-8")
    w = make(app, tmp_path, list_path=lp)
    assert w.items == []
    add(w, "getbible:kjv")                                  # and it is simply written again
    assert "getbible:kjv" in lp.read_text(encoding="utf-8")
    w.close()


def test_cleanup_deletes_every_saved_copy(app, win, tmp_path, monkeypatch):
    assert win.cleanup_btn.isHidden()                       # nothing saved: no button
    add(win, "getbible:kjv")
    add(win, "getbible:web")
    win._go_clicked()
    assert finished(app, win)
    file_item = import_church_bible(app, win, tmp_path)
    win.remove_from_list("getbible:kjv")                    # saved, but no longer in the list
    assert not win.cleanup_btn.isHidden() and win.cleanup_btn.text().startswith("Delete all saved Bibles (3 · ")
    monkeypatch.setattr(MainWindow, "_confirm_delete_all", lambda self, n, size: False)
    win.cleanup_btn.click()
    assert len(win.library.items) == 3                      # "Keep them"
    monkeypatch.setattr(MainWindow, "_confirm_delete_all", lambda self, n, size: True)
    win.cleanup_btn.click()
    assert win.library.items == [] and [p.name for p in win.library.folder.glob("*.json")] == ["index.json"]   # only the (empty) index is left
    assert [(i.short, i.status) for i in win.items] == [("WEB", "waiting")]      # the one from a file left the list
    assert win.cleanup_btn.isHidden() and "3 saved Bibles deleted" in win.message.text()
    assert (tmp_path / "out" / "WEB.rvbible").exists()      # what was exported is not touched


def test_cleanup_is_off_while_exporting(app, win):
    add(win, "getbible:kjv")
    win._go_clicked()
    assert finished(app, win)
    win.backend.slow.add("getbible:slow")
    add(win, "getbible:slow")
    win._go_clicked()
    assert pump(app, lambda: win._item("getbible:slow").status == "busy")
    assert not win.cleanup_btn.isEnabled()
    win._export_started = 0.0
    win._go_clicked()
    pump(app, lambda: not win.exporting)
    assert win.cleanup_btn.isEnabled()


# ---- from the code review ------------------------------------------------------------------------------

def test_adding_during_an_export_keeps_the_marks_of_finished_bibles(app, win):
    win.backend.slow.add("getbible:slow")
    add(win, "getbible:kjv")
    add(win, "getbible:slow")
    win._go_clicked()
    assert pump(app, lambda: win._item("getbible:kjv").status == "done" and win._item("getbible:slow").status == "busy")
    add(win, "getbible:web")                                   # the volunteer clicks + Add while it is exporting
    assert win._item("getbible:kjv").status == "done" and win.exporting
    win._go_clicked()
    pump(app, lambda: not win.exporting)
    assert win._item("getbible:kjv").status == "done"


def test_names_from_catalogs_and_files_are_shown_as_plain_text(app, win, tmp_path):
    from PySide6.QtCore import Qt
    from lpbibles.ui.widgets import ListItem, ListItemRow
    item = ListItem(key="k", entry=None, short="<i>X</i>", name="<b>Evil</b> Bible", status="saved", code="x")
    row = ListItemRow(item)
    assert row.name.textFormat() == Qt.PlainText and row.name.text() == "<b>Evil</b> Bible"
    assert row.chip.textFormat() == Qt.PlainText and win.message.textFormat() == Qt.PlainText


def test_the_folder_in_the_done_box_is_escaped(app, win, tmp_path):
    win.folder = tmp_path / "<b>odd</b> & folder"
    add(win, "getbible:kjv")
    win._go_clicked()
    assert finished(app, win)
    assert "&lt;b&gt;odd&lt;/b&gt; &amp; folder" in win.done_text.text()


def test_exported_files_have_safe_names(app, win, tmp_path):
    win.backend.load_free  # (the fake catalog has a Bible whose short name we change below)
    entry = win._entries_by_key()["getbible:kjv"]
    entry.short, entry.name = "CON", "Console Bible"
    add(win, "getbible:kjv")
    win._go_clicked()
    assert finished(app, win)
    assert [p.name for p in (tmp_path / "out").iterdir()] == ["_CON.rvbible"]


# ---- from the second code review ------------------------------------------------------------------------

def test_a_damaged_list_file_does_not_stop_the_app(app, tmp_path):
    from lpbibles.ui.listfile import load_list
    lib = Library(tmp_path / "d")
    for text in ('{"items": null}', '{"items": 5}', '[]', '{"items": [1, "x", null, {"key": 3}]}', "not json"):
        f = tmp_path / "list.json"
        f.write_text(text, encoding="utf-8")
        assert load_list(f, lib) == []
        w = make(app, tmp_path / "w", list_path=f)
        assert w.items == []
        w.close()


def test_retry_goes_to_the_folder_that_was_chosen(app, tmp_path, monkeypatch):
    w = make(app, tmp_path, platform="mac")
    chosen = tmp_path / "chosen"
    monkeypatch.setattr("lpbibles.ui.main_window.QFileDialog.getExistingDirectory", lambda *a, **k: str(chosen))
    w.backend.errors["getbible:web"] = netutil.NetworkError("No internet connection.")
    add(w, "getbible:kjv")
    add(w, "getbible:web")
    w._save_files_clicked()
    assert finished(app, w)
    assert [p.name for p in chosen.iterdir()] == ["KJV.rvbible"]
    installed = []
    monkeypatch.setattr(export_pp, "install_mac", lambda *a, **k: installed.append(a) or Path("x"))
    w.last_done and w._retry_clicked()
    assert pump(app, lambda: not w.exporting)
    assert sorted(p.name for p in chosen.iterdir()) == ["KJV.rvbible", "WEB.rvbible"] and not installed
    w.close()


def test_the_list_is_saved_when_the_window_is_closed_during_an_export(app, tmp_path):
    lp = tmp_path / "list.json"
    w = make(app, tmp_path, list_path=lp)
    w.backend.slow.add("getbible:slow")
    add(w, "getbible:slow")
    w._go_clicked()
    assert pump(app, lambda: w._item("getbible:slow").status == "busy")
    add(w, "getbible:web")                               # added while exporting
    w.close()
    assert [d["short"] for d in json.loads(lp.read_text(encoding="utf-8"))["items"]] == ["SLOW", "WEB"]


def test_the_free_list_is_asked_again_when_it_did_not_load(app, tmp_path):
    w = make(app, tmp_path)
    w.free_loaded = False
    calls = []
    real = w.backend.load_free
    w.backend.load_free = lambda cancel: calls.append(1) or real(cancel)
    w.tab_buttons["biblecom"].click()
    w.tab_buttons["free"].click()
    assert pump(app, lambda: w.free_loaded) and calls
    w.close()


def test_a_search_with_thousands_of_matches_stays_quick(app, tmp_path):
    w = make(app, tmp_path)
    w.free_entries = [Entry(key=f"getbible:x{i}", source="getbible", name=f"Test Bible {i}", short=f"T{i}", language="English",
                            lang_code="en") for i in range(1500)]
    t0 = time.time()
    w.bible_search.setText("t")
    assert pump(app, lambda: len(w.rows) == 150)
    assert "first 150 of 1500" in w.message.text() and time.time() - t0 < 3
    w.bible_search.setText("Test Bible 77")                # a narrower search: the note goes
    pump(app, lambda: len(w.rows) < 150)
    assert len(w.rows) == 11 and "first 150" not in w.message.text()
    w.close()


def test_file_errors_are_shown_in_plain_words():
    from lpbibles.ui.main_window import plain_error
    assert "Choose another folder" in plain_error(PermissionError(13, "Permission denied", "/x/.KJV.part"))
    assert plain_error(OSError(28, "No space left on device")) == "The disk is full."
    assert "Errno" not in plain_error(OSError(5, "Input/output error", "C:\\x"))
    assert plain_error(BibleError("This Bible is damaged.")) == "This Bible is damaged."
