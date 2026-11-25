"""The "Get ready for ProPresenter" window, on a fake ProPresenter folder."""

import json
from pathlib import Path

import pytest

from PySide6.QtWidgets import QApplication, QMessageBox

from lpbibles import windows_helper as wh
from lpbibles.model import ParsedBible
from lpbibles.ui import helper_dialog, theme
from lpbibles.ui.helper_dialog import HelperDialog

LIST = 'InstalledBiblesNew=["6fb4fb55-78a4-43bc-ac6a-076818c7abfc|BB|BasisBijbel|1"];\n'


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    a.setStyleSheet(theme.stylesheet())
    return a


def bible(name="Test Bible", short="TB"):
    pb = ParsedBible(name=name, short=short, language="English", lang_code="eng")
    for b in range(1, 67):
        pb.add(b, 1, 1, f"Book {b}.")
    return pb


def pp_folder(tmp_path):
    f = tmp_path / "PD" / "RenewedVision" / "ProPresenter" / "Bibles"
    f.mkdir(parents=True)
    (f / "BibleData.proPref").write_text(LIST, encoding="utf-8")
    return f


def answer(monkeypatch, label):
    """Clicks the button with this text in the next question box."""
    def fake_exec(self):
        for b in self.buttons():
            if b.text() == label:
                self._clicked = b
        return 0
    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: self._clicked)


def make(tmp_path, folder, running=lambda: False):
    return HelperDialog(None, [bible("King James Version", "KJV"), bible("Two", "TW")], tmp_path / "Ready", folder, running)


def test_choose_page_offers_only_free_bibles_not_installed(app, tmp_path):
    d = make(tmp_path, pp_folder(tmp_path))
    codes = [d.combos[0].itemData(i) for i in range(d.combos[0].count())]
    assert "BB" not in codes and len(codes) > 3
    assert len(set(d.chosen_codes())) == 2 and d.make_btn.isEnabled()
    d.combos[1].setCurrentIndex(d.combos[0].currentIndex())          # the same twice
    assert not d.make_btn.isEnabled() and "different" in d.choice_error.text()


def test_make_ready_does_not_touch_propresenter_and_offers_do_it(app, tmp_path):
    folder = pp_folder(tmp_path)
    before = (folder / "BibleData.proPref").read_bytes()
    d = make(tmp_path, folder)
    d.make_ready()
    assert d.prepared and (tmp_path / "Ready" / "BibleData.proPref").exists()
    assert (folder / "BibleData.proPref").read_bytes() == before and d.installed is None
    assert d.auto_box is not None and d.auto_btn.text().startswith("Do it for me")


def test_do_it_asks_first_and_no_changes_nothing(app, tmp_path, monkeypatch):
    folder = pp_folder(tmp_path)
    before = (folder / "BibleData.proPref").read_bytes()
    d = make(tmp_path, folder)
    d.make_ready()
    answer(monkeypatch, "No, I will do it myself")
    d.do_it()
    assert d.installed is None and (folder / "BibleData.proPref").read_bytes() == before
    assert sorted(p.name for p in folder.iterdir()) == ["BibleData.proPref"]


def test_do_it_yes_installs_and_undo_removes(app, tmp_path, monkeypatch):
    folder = pp_folder(tmp_path)
    d = make(tmp_path, folder)
    d.make_ready()
    answer(monkeypatch, "Do it")
    d.do_it()
    assert d.installed is not None
    text = (folder / "BibleData.proPref").read_text(encoding="utf-8")
    assert "King James Version" in text and (folder / "BibleData.proPref.old").exists()
    assert len([p for p in folder.iterdir() if p.is_dir()]) == 2
    assert d.undo_btn.text().startswith("Undo")
    answer(monkeypatch, "Undo")
    d.undo_it()
    assert d.installed is None
    assert (folder / "BibleData.proPref").read_text(encoding="utf-8") == LIST
    assert [p for p in folder.iterdir() if p.is_dir()] == []


def test_do_it_refuses_while_propresenter_is_open(app, tmp_path, monkeypatch):
    folder = pp_folder(tmp_path)
    d = make(tmp_path, folder, running=lambda: True)
    d.make_ready()
    answer(monkeypatch, "Do it")
    d.do_it()
    assert d.installed is None and "Close it" in d.auto_msg.text()
    assert (folder / "BibleData.proPref").read_text(encoding="utf-8") == LIST


def test_without_propresenter_there_are_lines_and_no_do_it(app, tmp_path):
    d = make(tmp_path, None)
    assert "not found" in d.findChild(type(d.body.itemAt(0).widget()), "helperstatus").text()
    d.make_ready()
    assert d.prepared.lines_file.exists() and d.auto_box is None
    assert not (tmp_path / "Ready" / "BibleData.proPref").exists()


def test_main_window_buttons_open_the_helper(app, tmp_path, monkeypatch):
    from test_gui import add, finished, make as make_window
    w = make_window(app, tmp_path)
    assert not w.helper_btn.isHidden()
    seen = []
    monkeypatch.setattr(helper_dialog.HelperDialog, "exec", lambda self: seen.append(self.bibles) or 0)
    w._open_helper()                                    # nothing exported yet: a plain message, no window
    assert not seen and "export" in w.message.text().lower()
    add(w, "getbible:kjv")
    w._go_clicked()
    assert finished(app, w)
    assert any(t == "Get ready for ProPresenter…" for t in [b.text() for b in w.done_box.findChildren(type(w.go))])
    w._open_helper()
    assert len(seen) == 1 and seen[0][0].short == "KJV"
    w.close()


def test_the_window_opens_even_when_the_list_cannot_be_read(app, tmp_path):
    folder = pp_folder(tmp_path)
    (folder / "BibleData.proPref").write_text("not the file we know", encoding="utf-8")
    d = make(tmp_path, folder)
    assert "left alone" in d.findChild(type(d.body.itemAt(0).widget()), "helperstatus").text()
    d.make_ready()
    assert d.prepared.lines_file.exists() and d.auto_box is None
    assert (folder / "BibleData.proPref").read_text(encoding="utf-8") == "not the file we know"


def test_after_an_undo_there_is_no_dead_end(app, tmp_path, monkeypatch):
    folder = pp_folder(tmp_path)
    (folder / "BibleData.proPref").write_text(LIST.replace('"];', '","0aa4c0f1-2b7d-4c1a-8f3e-4d5b6c7e8f90|KJV|K|1"];'), encoding="utf-8")
    d = make(tmp_path, folder)
    d.make_ready()
    answer(monkeypatch, "Do it")
    d.do_it()
    answer(monkeypatch, "Undo")
    d.undo_it()
    assert not d.auto_btn.isEnabled() and "again" in d.auto_msg.text() and d.steps_host.isHidden()
