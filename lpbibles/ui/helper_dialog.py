"""The "Get ready for ProPresenter (Windows)" window (layout from design/windows-helper/)."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
                               QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from .. import windows_helper as wh
from ..model import BibleError, ParsedBible
from . import theme

PP_PATH = r"C:\ProgramData\RenewedVision\ProPresenter\Bibles"


def _open(path: Path) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def _label(text: str = "", name: str = "", rich: bool = False, wrap: bool = True) -> QLabel:
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setTextFormat(Qt.RichText if rich else Qt.PlainText)
    lab.setWordWrap(wrap)
    return lab


def _code(text: str) -> str:
    return (f'<span style="font-family:Consolas,Menlo,monospace;color:{theme.LICENSED};background-color:{theme.FIELD}">'
            f'&nbsp;{html.escape(text)}&nbsp;</span>')


class HelperDialog(QDialog):
    """bibles: the Bibles to put in ProPresenter. ready_dir: where the ready folders are made (must not exist yet)."""

    def __init__(self, parent, bibles: list[ParsedBible], ready_dir: Path, bibles_folder: Optional[Path],
                 running: Callable[[], bool] = wh.is_propresenter_running):
        super().__init__(parent)
        self.setWindowTitle("Get ready for ProPresenter (Windows)")
        self.setModal(True)
        self.resize(860, 640)
        self.bibles = bibles
        self.ready_dir = Path(ready_dir)
        self.bibles_folder = Path(bibles_folder) if bibles_folder else None
        self.running = running
        self.prepared: Optional[wh.Prepared] = None
        self.installed: Optional[wh.Installed] = None
        self.problem = ""
        try:
            self.free = wh.free_bibles(self.bibles_folder)
        except (BibleError, OSError, ValueError) as e:
            # ProPresenter is here but its list cannot be read: do not touch it, make the lines to add by hand instead
            self.problem = str(e) if isinstance(e, BibleError) else "ProPresenter's Bible list could not be read."
            self.bibles_folder = None
            self.free = wh.free_bibles(None)
        self.combos: list[QComboBox] = []

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        head = QFrame()
        head.setObjectName("dlghead")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(20, 12, 16, 12)
        title = QLabel("Get ready for ProPresenter (Windows)")
        title.setObjectName("dlgtitle")
        hl.addWidget(title)
        hl.addStretch(1)
        x = QPushButton("✕")
        x.setObjectName("x")
        x.setFixedSize(26, 26)
        x.setAccessibleName("Close")
        x.clicked.connect(self.reject)
        hl.addWidget(x)
        v.addWidget(head)

        bar = QFrame()
        bar.setObjectName("stepbar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(20, 10, 20, 10)
        bl.setSpacing(8)
        self.pills: list[QLabel] = []
        for text in ("1  Choose", "2  Make ready", "3  Put in ProPresenter"):
            p = QLabel(text)
            p.setObjectName("steppill")
            p.setProperty("state", "idle")
            self.pills.append(p)
            bl.addWidget(p)
        bl.addStretch(1)
        v.addWidget(bar)

        self.body_host = QWidget()
        self.body = QVBoxLayout(self.body_host)
        self.body.setContentsMargins(20, 14, 20, 12)
        self.body.setSpacing(12)
        v.addWidget(self.body_host, 1)

        foot = QFrame()
        foot.setObjectName("dlgfoot")
        self.foot = QHBoxLayout(foot)
        self.foot.setContentsMargins(20, 12, 20, 14)
        self.foot.setSpacing(10)
        v.addWidget(foot)
        self._choose_page()

    # ---- helpers ----------------------------------------------------------------------------------

    def _pills(self, active: int) -> None:
        for i, p in enumerate(self.pills, 1):
            state = "on" if i == active else ("ok" if i < active else "idle")
            p.setProperty("state", state)
            p.setText(("✓  " if state == "ok" else f"{i}  ") + ["Choose", "Make ready", "Put in ProPresenter"][i - 1])
            p.style().unpolish(p)
            p.style().polish(p)

    def _clear(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
            elif item.layout():
                self._clear(item.layout())

    def _button(self, text: str, fn: Callable, name: str = "btn") -> QPushButton:
        b = QPushButton(text)
        b.setObjectName(name)
        b.setCursor(Qt.PointingHandCursor)
        b.setAutoDefault(False)
        b.clicked.connect(lambda _c=False: fn())
        return b

    def _set_footer(self, left: list[QPushButton], right: QPushButton) -> None:
        self._clear(self.foot)
        for b in left:
            self.foot.addWidget(b)
        self.foot.addStretch(1)
        self.foot.addWidget(right)

    def _status_line(self) -> QLabel:
        if self.problem:
            lab = _label(f'<span style="color:{theme.WARN};font-weight:600">● {html.escape(self.problem)} Nothing in ProPresenter will be '
                         f'changed: the app makes the lines to add by hand instead.</span>', rich=True)
        elif self.bibles_folder is not None:
            lab = _label(f'<span style="color:{theme.GREEN}">●</span> <span style="color:{theme.GREEN};font-weight:600">'
                         f'ProPresenter found on this PC:</span> {_code(str(self.bibles_folder))}', rich=True)
        else:
            lab = _label(f'<span style="color:{theme.WARN};font-weight:600">● ProPresenter was not found on this PC. '
                         f'That is fine if you will add the Bibles on another PC.</span>', rich=True)
        lab.setObjectName("helperstatus")
        return lab

    # ---- stage 1: choose -----------------------------------------------------------------------------

    def _choose_page(self) -> None:
        self._pills(1)
        self._clear(self.body)
        self.body.addWidget(self._status_line())
        extra = ("The list only shows free Bibles you have not installed." if self.bibles_folder is not None else
                 "This PC has no ProPresenter list, so every free Bible is shown. Make sure the ones you pick are ones nobody uses on the PC with ProPresenter.")
        intro = _label("ProPresenter for Windows only accepts Bibles it already knows. So each of your Bibles takes the place of one of "
                       f"ProPresenter's <b style='color:{theme.TEXT}'>own free Bibles</b>. Pick free Bibles you never use: the one you pick "
                       f"can no longer be used in ProPresenter. {html.escape(extra)}", "hint", rich=True)
        self.body.addWidget(intro)

        table = QFrame()
        table.setObjectName("items")
        g = QVBoxLayout(table)
        g.setContentsMargins(0, 0, 0, 0)
        g.setSpacing(0)
        self.combos = []
        for i, pb in enumerate(self.bibles):
            row = QFrame()
            row.setObjectName("irow")
            row.setProperty("last", i == len(self.bibles) - 1)
            h = QHBoxLayout(row)
            h.setContentsMargins(14, 8, 14, 8)
            h.setSpacing(12)
            chip = QLabel(pb.short or pb.name[:8])
            chip.setObjectName("chip")
            chip.setTextFormat(Qt.PlainText)
            name = QLabel(pb.name)
            name.setObjectName("iname")
            name.setTextFormat(Qt.PlainText)
            name.setMinimumWidth(190)
            name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            arrow = QLabel("takes the place of")
            arrow.setObjectName("isub")
            combo = QComboBox()
            combo.setAccessibleName(f"Free ProPresenter Bible replaced by {pb.name}")
            for f in self.free:
                combo.addItem(f'{f.get("language", "")} · {f.get("name", "")} ({f.get("displayAbbreviation", "")})',
                              f["internalAbbreviation"])
            combo.setCurrentIndex(min(i, max(0, combo.count() - 1)))
            combo.setMaximumWidth(460)
            combo.setMinimumWidth(330)
            combo.currentIndexChanged.connect(lambda _i: self._check_choices())
            self.combos.append(combo)
            h.addWidget(chip)
            h.addWidget(name, 1)
            h.addWidget(arrow)
            h.addWidget(combo)
            g.addWidget(row)
        self.body.addWidget(table)
        self.choice_error = _label("", "helpererror")
        self.body.addWidget(self.choice_error)
        warn = QFrame()
        warn.setObjectName("warnbox")
        wl = QVBoxLayout(warn)
        wl.setContentsMargins(12, 9, 12, 9)
        wl.addWidget(_label("In ProPresenter your Bible shows under its own name. The free Bible's name is only used to make ProPresenter "
                            "accept it. Nothing in ProPresenter is changed in this step: the app only makes files in your Documents folder."))
        self.body.addWidget(warn)
        self.body.addStretch(1)
        self.make_btn = self._button("Make them ready", self.make_ready, "go")
        self.make_btn.setMinimumWidth(170)
        self._set_footer([self._button("Cancel", self.reject)], self.make_btn)
        self._check_choices()

    def chosen_codes(self) -> list[str]:
        return [c.currentData() for c in self.combos]

    def _check_choices(self) -> None:
        codes = self.chosen_codes()
        dup = len(set(codes)) != len(codes) or not codes or any(c is None for c in codes)
        self.choice_error.setText("Pick a different free Bible for each one of your Bibles." if dup else "")
        self.make_btn.setEnabled(not dup)

    def make_ready(self) -> None:
        try:
            self.prepared = wh.prepare(self.bibles, self.chosen_codes(), self.ready_dir, self.bibles_folder)
        except (BibleError, OSError) as e:
            self.choice_error.setText(str(e))
            return
        self._ready_page()

    # ---- stage 3: put them in ProPresenter ---------------------------------------------------------------

    def _numbered(self, n: int, rich_text: str) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(11)
        num = QLabel(str(n))
        num.setObjectName("hstepnum")
        num.setFixedSize(22, 22)
        num.setAlignment(Qt.AlignCenter)
        h.addWidget(num, 0, Qt.AlignTop)
        h.addWidget(_label(rich_text, "todotext", rich=True), 1)
        return w

    def _ready_page(self) -> None:
        p = self.prepared
        assert p is not None
        self._pills(3)
        self._clear(self.body)
        self.body.addWidget(self._status_line())
        n = len(p.folders)
        ready_name = html.escape(str(p.ready_dir))
        ok = QFrame()
        ok.setObjectName("done")
        ol = QVBoxLayout(ok)
        ol.setContentsMargins(14, 10, 14, 10)
        ol.setSpacing(3)
        ol.addWidget(_label(f"✓ Ready: {n} {'Bible' if n == 1 else 'Bibles'}", "donehead"))
        if p.new_pref is not None:
            ol.addWidget(_label(f"Made in <b style='color:{theme.TEXT}'>{ready_name}</b>: one folder for each Bible, and a new "
                                f"{_code('BibleData.proPref')} that is your ProPresenter list plus your Bible{'s' if n != 1 else ''}.",
                                "donetext", rich=True))
        else:
            ol.addWidget(_label(f"Made in <b style='color:{theme.TEXT}'>{ready_name}</b>: one folder for each Bible, and a text file "
                                f"{_code('Lines for BibleData.proPref.txt')}. Copy the whole folder to the PC with ProPresenter.",
                                "donetext", rich=True))
        self.body.addWidget(ok)

        if p.new_pref is None:
            lines = ",\n".join(json.dumps(e) for e in p.entries)
            self.body.addWidget(_label(f"THE {'LINE' if n == 1 else 'LINES'} TO ADD (the app does not know which free Bibles that PC has "
                                       "installed: make sure these are ones nobody uses)", "lab"))
            box = QPlainTextEdit(lines)
            box.setObjectName("codebox")
            box.setReadOnly(True)
            box.setMaximumHeight(18 * (n + 2) + 12)
            self.body.addWidget(box)

        self.steps_host = QWidget()
        sl = QVBoxLayout(self.steps_host)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(9)
        if p.new_pref is not None:
            sl.addWidget(_label("NOW DO THIS, IN THIS ORDER", "lab"))
            sl.addWidget(self._numbered(1, "<b style='color:#fff'>Close ProPresenter.</b>"))
            sl.addWidget(self._numbered(2, f"Click <b style='color:#fff'>Open both folders</b>. In the ProPresenter Bibles folder, "
                                           f"<b style='color:#fff'>rename</b> {_code('BibleData.proPref')} to {_code('BibleData.proPref.old')} "
                                           "(this keeps your old list safe)."))
            sl.addWidget(self._numbered(3, "From the <b style='color:#fff'>Ready for ProPresenter</b> folder, <b style='color:#fff'>drag everything</b> "
                                           f"(the Bible folder{'s' if n != 1 else ''} and {_code('BibleData.proPref')}) into the ProPresenter Bibles folder."))
            names = " and ".join(html.escape(x) for x in p.names)
            sl.addWidget(self._numbered(4, f"<b style='color:#fff'>Open ProPresenter.</b> {names} {'is' if n == 1 else 'are'} in the Bible list."))
            sl.addWidget(_label(f"<b style='color:{theme.TEXT2}'>To undo:</b> delete the added folder{'s' if n != 1 else ''} and rename "
                                f"{_code('BibleData.proPref.old')} back to {_code('BibleData.proPref')}. Do these steps now: if you add a Bible in "
                                "ProPresenter first, this list is out of date (close this window and click Get ready for ProPresenter again).", "hint", rich=True))
        else:
            sl.addWidget(self._numbered(1, f"On the PC with ProPresenter: <b style='color:#fff'>close ProPresenter</b>, then open {_code(PP_PATH)}."))
            sl.addWidget(self._numbered(2, f"<b style='color:#fff'>Drag the {n} Bible folder{'s' if n != 1 else ''}</b> from the ready folder into it."))
            sl.addWidget(self._numbered(3, f"Open {_code('BibleData.proPref')} in Notepad and paste the line{'s' if n != 1 else ''} just before the final "
                                           f"{_code(']')}, after a comma. Save."))
            sl.addWidget(self._numbered(4, "<b style='color:#fff'>Open ProPresenter.</b>"))
        self.body.addWidget(self.steps_host)

        # the choice to let the app do steps 2 and 3 (nothing happens unless the person clicks it)
        self.auto_box = None
        if p.new_pref is not None:
            self.auto_box = QFrame()
            self.auto_box.setObjectName("autobox")
            al = QVBoxLayout(self.auto_box)
            al.setContentsMargins(14, 10, 14, 10)
            al.setSpacing(6)
            al.addWidget(_label("Or let Bible Importer do steps 2 and 3 for me", "autotitle"))
            al.addWidget(_label("It checks that ProPresenter is closed, keeps your old list as BibleData.proPref.old, copies the Bible "
                                "folders in and puts the new list in place. You can undo it. It only happens if you click the button "
                                "and say yes.", "hint"))
            row = QHBoxLayout()
            self.auto_btn = self._button("Do it for me…", self.do_it)
            row.addWidget(self.auto_btn)
            row.addStretch(1)
            al.addLayout(row)
            self.auto_msg = _label("", "helpererror")
            self.auto_msg.setVisible(False)
            al.addWidget(self.auto_msg)
            self.body.addWidget(self.auto_box)
        self.body.addStretch(1)

        left = []
        if p.new_pref is not None:
            left.append(self._button("Open both folders", self.open_both))
        left.append(self._button("Open the ready folder", lambda: _open(p.ready_dir)))
        if p.new_pref is None:
            left.append(self._button("Copy the lines", self.copy_lines))
        done = self._button("Done", self.accept, "go")
        done.setMinimumWidth(110)
        self._set_footer(left, done)

    @staticmethod
    def _say(label: QLabel, text: str) -> None:
        label.setText(text)
        label.setVisible(bool(text))

    def open_both(self) -> None:
        if self.prepared:
            _open(self.prepared.ready_dir)
            if self.prepared.bibles_folder:
                _open(self.prepared.bibles_folder)

    def copy_lines(self) -> None:
        if self.prepared:
            QGuiApplication.clipboard().setText(",\n".join(json.dumps(e) for e in self.prepared.entries))

    # ---- "Do it for me" (only when the person asks) ---------------------------------------------------------

    def _confirm_install(self) -> bool:
        box = QMessageBox(QMessageBox.Question, "Put the Bibles in ProPresenter?",
                          "Close ProPresenter first. Then Bible Importer will:\n\n"
                          "• check that ProPresenter is closed\n"
                          "• keep your old list as BibleData.proPref.old\n"
                          "• copy the Bible folders into ProPresenter's Bibles folder\n"
                          "• put the new list in place\n\n"
                          "If anything goes wrong it puts everything back as it was. You can undo this afterwards.",
                          QMessageBox.NoButton, self)
        yes = box.addButton("Do it", QMessageBox.AcceptRole)
        no = box.addButton("No, I will do it myself", QMessageBox.RejectRole)
        box.setDefaultButton(no)
        self._widen(box)
        box.exec()
        return box.clickedButton() is yes

    @staticmethod
    def _widen(box: QMessageBox) -> None:
        box.setMinimumWidth(560)
        text = box.findChild(QLabel, "qt_msgbox_label")
        if text is not None:
            text.setMinimumWidth(400)

    def do_it(self) -> None:
        if self.prepared is None or self.prepared.new_pref is None:
            return
        self._say(self.auto_msg, "")
        if not self._confirm_install():
            return
        try:
            self.installed = wh.install(self.prepared, running=self.running)
        except BibleError as e:
            self._say(self.auto_msg, str(e))
            return
        self._installed_page()

    def _installed_page(self) -> None:
        inst = self.installed
        assert inst is not None
        n = len(inst.ids)
        self.steps_host.hide()
        if self.auto_box:
            self.auto_box.hide()
        ok = QFrame()
        ok.setObjectName("done")
        ol = QVBoxLayout(ok)
        ol.setContentsMargins(14, 10, 14, 10)
        ol.setSpacing(3)
        ol.addWidget(_label(f"✓ Done: {n} {'Bible' if n == 1 else 'Bibles'} put in ProPresenter", "donehead"))
        ol.addWidget(_label("Open ProPresenter: " + (" and ".join(self.prepared.names) if self.prepared else "your Bibles") +
                            f" {'is' if n == 1 else 'are'} in the Bible list. Your old list is kept as {inst.backup.name}.", "donetext"))
        row = QHBoxLayout()
        self.undo_btn = self._button("Undo this…", self.undo_it)
        row.addWidget(self.undo_btn)
        row.addStretch(1)
        ol.addLayout(row)
        self.undo_msg = _label("", "helpererror")
        self.undo_msg.setVisible(False)
        ol.addWidget(self.undo_msg)
        self.body.insertWidget(self.body.count() - 1, ok)
        self.done_box = ok

    def _confirm_undo(self) -> bool:
        box = QMessageBox(QMessageBox.Question, "Undo",
                          "Take these Bibles out of ProPresenter again?\n\nOnly the Bibles put there by this program are removed. "
                          "ProPresenter must be closed.", QMessageBox.NoButton, self)
        yes = box.addButton("Undo", QMessageBox.DestructiveRole)
        no = box.addButton("Keep them", QMessageBox.RejectRole)
        box.setDefaultButton(no)
        self._widen(box)
        box.exec()
        return box.clickedButton() is yes

    def undo_it(self) -> None:
        if self.installed is None or not self._confirm_undo():
            return
        try:
            wh.undo(self.installed, running=self.running)
        except BibleError as e:
            self._say(self.undo_msg, str(e))
            return
        self.installed = None
        self.done_box.hide()
        # the list was changed again by the undo: to put the Bibles back, start again from the main window
        # (the steps by hand would use a list that is out of date, so they stay hidden)
        if self.auto_box:
            self.auto_box.show()
            self.auto_btn.setEnabled(False)
            self._say(self.auto_msg, "Undone: the Bibles were taken out of ProPresenter. To put them back, close this window "
                                     "and click Get ready for ProPresenter again.")
            self.auto_msg.setStyleSheet(f"color: {theme.TEXT2};")
