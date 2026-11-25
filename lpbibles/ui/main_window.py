"""The Bible Importer window: find Bibles, build a list, export it (layout from design/*.html)."""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QLocale, QSettings, QStandardPaths, Qt, QUrl, Signal
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from .. import catalog, export_lp, export_pp, importers
from ..backend import Backend
from ..catalog import Language
from ..library import Library, default_numbering
from ..model import BibleError, Entry, ParsedBible
from ..netutil import Cancelled, NetworkError
from . import theme
from .dialogs import ExplainDialog
from .widgets import (BibleRow, DropArea, LanguageList, ListItem, ListItemRow, Segmented, fmt_eta, plural,
                      step_header)
from .workers import Runner

BIBLECOM_FAIL = "Bible.com did not answer. Try again later, or import a file."
OFFLINE_STALE = "⚠ Could not reach the list. Showing the saved list."
BC_NOTE = "Bible.com can change without notice. If a download fails, import a file instead."


def system_language_name() -> str:
    return QLocale.languageToString(QLocale.system().language())


def default_platform() -> str:
    return "mac" if sys.platform == "darwin" else "win"


def safe_name(text: str) -> str:
    t = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", text).strip(" .")
    return t or "Bible"


def unique_path(folder: Path, base: str, ext: str) -> Path:
    p = folder / f"{base}{ext}"
    n = 2
    while p.exists():
        p = folder / f"{base} ({n}){ext}"
        n += 1
    return p


def delete_message(name: str, from_file: bool) -> str:
    """What the question before deleting a saved copy says (plain words: what goes, and what stays)."""
    again = ("It came from a file, so it can only come back by choosing the file again." if from_file
             else "You can download it again later.")
    return (f"Delete the saved copy of {name}?\n\n"
            "This only deletes the copy that Bible Importer keeps on this computer. "
            "Files you saved in a folder, and Bibles already added to ProPresenter, stay as they are.\n\n"
            + again)


def hint_html(text: str) -> str:
    return text.replace("<b>", f'<b style="color:{theme.TEXT}">')


class MainWindow(QMainWindow):
    # key, status, note, fraction (-1 = none), library code
    export_event = Signal(str, str, str, float, str)

    def __init__(self, library: Library, backend: Backend, system_language: Optional[str] = None,
                 platform: Optional[str] = None, settings: Optional[QSettings] = None):
        super().__init__()
        self.setWindowTitle("Bible Importer")
        self.resize(1200, 760)
        self.setMinimumSize(1000, 640)
        self.library = library
        self.backend = backend
        self.platform = platform or default_platform()          # "mac" or "win" (win: save the files only)
        self.settings = settings or QSettings("Bible Importer", "Bible Importer")
        self.system_language = system_language or system_language_name()
        self.runner = Runner()
        self.runner.done.connect(self._job_done)
        self.runner.failed.connect(self._job_failed)
        self.runner.cancelled.connect(self._job_cancelled)
        self.runner.progress.connect(self._job_progress)
        self.export_event.connect(self._on_export_event)

        self.fmt = self.settings.value("format", "pp") if self.settings.value("format", "pp") in ("pp", "lp") else "pp"
        docs = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation) or str(Path.home())
        self.folder = Path(str(self.settings.value("folder", str(Path(docs) / "Bible Importer"))))

        self.tab = "free"
        self.free_entries: list[Entry] = []
        self.free_langs: list[Language] = []
        self.free_loaded = False
        self.bc_langs: list[Language] = []
        self.bc_entries: dict[str, list[Entry]] = {}
        self.bc_loaded = False
        self.selected: dict[str, Optional[str]] = {"free": None, "biblecom": None}
        self.searches = {"free": "", "biblecom": "", "free_lang": "", "biblecom_lang": ""}
        self.rows: dict[str, BibleRow] = {}
        self.items: list[ListItem] = []
        self.item_rows: dict[str, ListItemRow] = {}
        self.exporting = False
        self.export_seen: set[str] = set()
        self.export_total = 0
        self.export_mode = ""
        self.last_done: Optional[dict] = None

        self._build()
        self._switch_tab("free")
        self._refresh_panel()
        self.runner.start("load-free", lambda cancel, progress: self.backend.load_free(cancel))
        self.set_message("Loading the list…", "dim")

    # ---- layout --------------------------------------------------------------------------------------

    def _build(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        col = QVBoxLayout(root)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(54)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(18, 0, 18, 0)
        hl.setSpacing(12)
        title = QLabel("Bible Importer")
        title.setObjectName("title")
        sub = QLabel("Get Bibles and save them for ProPresenter or Live Presenter")
        sub.setObjectName("subtitle")
        hl.addWidget(title)
        hl.addWidget(sub)
        hl.addStretch(1)
        col.addWidget(header)

        main = QHBoxLayout()
        main.setSpacing(0)
        col.addLayout(main, 1)

        find = QWidget()
        fv = QVBoxLayout(find)
        fv.setContentsMargins(0, 0, 0, 0)
        fv.setSpacing(0)
        main.addWidget(find, 1)

        tabs = QFrame()
        tabs.setObjectName("tabs")
        tabs.setFixedHeight(44)
        tl = QHBoxLayout(tabs)
        tl.setContentsMargins(18, 0, 18, 0)
        tl.setSpacing(22)
        self.tab_buttons: dict[str, QPushButton] = {}
        for key, text in (("free", "Free Bibles"), ("biblecom", "Bible.com"), ("file", "From a file")):
            b = QPushButton(text)
            b.setObjectName("tab")
            b.setCheckable(True)
            b.setAutoExclusive(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c=False, k=key: self._switch_tab(k))
            tl.addWidget(b, 0, Qt.AlignBottom)
            self.tab_buttons[key] = b
        tl.addStretch(1)
        s1, _ = step_header("1", "FIND BIBLES")
        s1.setFixedHeight(32)
        tl.addWidget(s1, 0, Qt.AlignVCenter)
        fv.addWidget(tabs)

        self.amber = QFrame()
        self.amber.setObjectName("amber")
        al = QHBoxLayout(self.amber)
        al.setContentsMargins(18, 7, 18, 7)
        al.addWidget(QLabel("⚠  These Bibles are copyrighted. Add one only if your church has the right to use it."))
        al.addStretch(1)
        fv.addWidget(self.amber)

        # --- browse (Free Bibles, Bible.com)
        self.browse = QWidget()
        bl = QHBoxLayout(self.browse)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)
        left = QFrame()
        left.setObjectName("lc")
        left.setFixedWidth(210)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 10, 0, 10)
        ll.setSpacing(8)
        self.lang_search = QLineEdit()
        self.lang_search.setObjectName("field")
        self.lang_search.setPlaceholderText("⌕  Search languages")
        self.lang_search.setClearButtonEnabled(True)
        self.lang_search.textChanged.connect(self._language_search_changed)
        sw = QHBoxLayout()
        sw.setContentsMargins(12, 0, 12, 0)
        sw.addWidget(self.lang_search)
        ll.addLayout(sw)
        self.langs = LanguageList()
        self.langs.chosen.connect(self._language_chosen)
        ll.addWidget(self.langs, 1)
        bl.addWidget(left)

        right = QFrame()
        right.setObjectName("rc")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(14, 10, 14, 0)
        rl.setSpacing(8)
        self.bible_search = QLineEdit()
        self.bible_search.setObjectName("field")
        self.bible_search.setPlaceholderText("⌕  Search Bibles")
        self.bible_search.setClearButtonEnabled(True)
        self.bible_search.textChanged.connect(self._bible_search_changed)
        rl.addWidget(self.bible_search)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("scrollbody")
        sb = QVBoxLayout(body)
        sb.setContentsMargins(0, 0, 0, 0)
        sb.setSpacing(0)
        self.list_frame = QFrame()
        self.list_frame.setObjectName("lst")
        self.list_layout = QVBoxLayout(self.list_frame)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(0)
        sb.addWidget(self.list_frame)
        self.message = QLabel("")
        self.message.setObjectName("message")
        self.message.setWordWrap(True)
        self.message.setContentsMargins(2, 8, 2, 0)
        sb.addWidget(self.message)
        sb.addStretch(1)
        self.scroll.setWidget(body)
        rl.addWidget(self.scroll, 1)
        bl.addWidget(right, 1)
        fv.addWidget(self.browse, 1)

        # --- from a file
        self.file_page = QWidget()
        fpl = QVBoxLayout(self.file_page)
        fpl.setContentsMargins(14, 14, 14, 14)
        self.drop = DropArea()
        self.drop.choose_clicked.connect(self._choose_file)
        self.drop.files_dropped.connect(self.import_files)
        fpl.addWidget(self.drop, 1)
        self.file_message = QLabel("")
        self.file_message.setObjectName("message")
        self.file_message.setWordWrap(True)
        fpl.addWidget(self.file_message)
        fv.addWidget(self.file_page, 1)

        # --- right panel: your list + export
        panel = QFrame()
        panel.setObjectName("panel")
        panel.setFixedWidth(400)
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(16, 14, 16, 14)
        pv.setSpacing(12)
        s2, self.count_label = step_header("2", "YOUR LIST")
        pv.addWidget(s2)
        self.items_scroll = QScrollArea()
        self.items_scroll.setWidgetResizable(True)
        self.items_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        ib = QWidget()
        ib.setObjectName("scrollbody")
        ibl = QVBoxLayout(ib)
        ibl.setContentsMargins(0, 0, 0, 0)
        ibl.setSpacing(12)
        self.items_frame = QFrame()
        self.items_frame.setObjectName("items")
        self.items_layout = QVBoxLayout(self.items_frame)
        self.items_layout.setContentsMargins(0, 0, 0, 0)
        self.items_layout.setSpacing(0)
        ibl.addWidget(self.items_frame)
        self.done_box = QFrame()
        self.done_box.setObjectName("done")
        dl = QVBoxLayout(self.done_box)
        dl.setContentsMargins(14, 12, 14, 12)
        dl.setSpacing(4)
        self.done_head = QLabel("")
        self.done_head.setObjectName("donehead")
        self.done_text = QLabel("")
        self.done_text.setObjectName("donetext")
        self.done_text.setWordWrap(True)
        self.done_text.setTextFormat(Qt.RichText)
        dl.addWidget(self.done_head)
        dl.addWidget(self.done_text)
        self.done_buttons = QHBoxLayout()
        self.done_buttons.setSpacing(8)
        self.done_buttons.setContentsMargins(0, 8, 0, 0)
        dl.addLayout(self.done_buttons)
        ibl.addWidget(self.done_box)
        ibl.addStretch(1)
        self.items_scroll.setWidget(ib)
        pv.addWidget(self.items_scroll, 1)

        s3, _ = step_header("3", "EXPORT FOR")
        pv.addWidget(s3)
        self.seg = Segmented([("pp", "ProPresenter"), ("lp", "Live Presenter")])
        self.seg.set_value(self.fmt)
        self.seg.changed.connect(self._format_changed)
        pv.addWidget(self.seg)
        self.hint1 = QLabel("")
        self.hint1.setObjectName("hint")
        self.hint1.setWordWrap(True)
        self.hint1.setTextFormat(Qt.RichText)
        self.hint2 = QLabel("")
        self.hint2.setObjectName("hint")
        self.hint2.setWordWrap(True)
        self.hint2.setTextFormat(Qt.RichText)
        pv.addWidget(self.hint1)
        pv.addWidget(self.hint2)
        self.dest_row = QWidget()
        dr = QHBoxLayout(self.dest_row)
        dr.setContentsMargins(0, 0, 0, 0)
        dr.setSpacing(8)
        self.path_label = QLabel("")
        self.path_label.setObjectName("pathbox")
        self.choose_btn = QPushButton("Choose…")
        self.choose_btn.setObjectName("btn")
        self.choose_btn.clicked.connect(self._choose_folder)
        dr.addWidget(self.path_label, 1)
        dr.addWidget(self.choose_btn)
        pv.addWidget(self.dest_row)
        self.help_row = QWidget()
        hr = QHBoxLayout(self.help_row)
        hr.setContentsMargins(0, 0, 0, 0)
        hr.setSpacing(8)
        self.qmark = QPushButton("?")
        self.qmark.setObjectName("qmark")
        self.qmark.setFixedSize(22, 22)
        self.qmark.setCursor(Qt.PointingHandCursor)
        self.qmark.setAccessibleName("How to add the files to ProPresenter on Windows")
        self.qmark.clicked.connect(self._explain)
        link = QPushButton("How do I add them to ProPresenter on Windows?")
        link.setObjectName("helplink")
        link.setCursor(Qt.PointingHandCursor)
        link.clicked.connect(self._explain)
        hr.addWidget(self.qmark)
        hr.addWidget(link, 1)
        pv.addWidget(self.help_row)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.go = QPushButton("")
        self.go.setObjectName("go")
        self.go.setCursor(Qt.PointingHandCursor)
        self.go.clicked.connect(self._go_clicked)
        self.save_btn = QPushButton("Save files…")
        self.save_btn.setObjectName("go2")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.clicked.connect(self._save_files_clicked)
        buttons.addWidget(self.go, 1)
        buttons.addWidget(self.save_btn)
        pv.addLayout(buttons)
        main.addWidget(panel)

    # ---- small helpers -------------------------------------------------------------------------------

    def set_message(self, text: str, kind: str = "ok") -> None:
        for label in (self.message, self.file_message):
            label.setStyleSheet(f"color: {theme.MESSAGE_COLORS.get(kind, theme.DIM)};")
            label.setText(text)

    @staticmethod
    def _clear(layout) -> None:
        """Takes every widget out of a layout at once (deleteLater alone leaves them visible for a moment)."""
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()

    def _entries_by_key(self) -> dict[str, Entry]:
        out = {e.key: e for e in self.free_entries}
        for lst in self.bc_entries.values():
            out.update({e.key: e for e in lst})
        return out

    def _item(self, key: str) -> Optional[ListItem]:
        return next((i for i in self.items if i.key == key), None)

    # ---- tabs, languages, search ---------------------------------------------------------------------

    def _switch_tab(self, key: str) -> None:
        self.tab = key
        self.tab_buttons[key].setChecked(True)
        self.amber.setVisible(key == "biblecom")
        self.browse.setVisible(key != "file")
        self.file_page.setVisible(key == "file")
        if key == "file":
            return
        self.lang_search.blockSignals(True)
        self.bible_search.blockSignals(True)
        self.lang_search.setText(self.searches[key + "_lang"])
        self.bible_search.setText(self.searches[key])
        self.lang_search.blockSignals(False)
        self.bible_search.blockSignals(False)
        if key == "biblecom" and not self.bc_loaded and "load-bc-langs" not in self.runner.events:
            self.set_message("Loading the list…", "dim")
            self.runner.start("load-bc-langs", lambda cancel, progress: self.backend.bc_languages(cancel))
        self._fill_languages()

    def _current_languages(self) -> list[Language]:
        langs = self.free_langs if self.tab == "free" else self.bc_langs
        t = self.searches[self.tab + "_lang"].strip().lower()
        if t:
            langs = [l for l in langs if t in l.native.lower() or t in l.english.lower()]
        return langs

    def _fill_languages(self) -> None:
        self.langs.set_languages(self._current_languages(), select=self.selected[self.tab])
        if not self._current_languages():
            self._rebuild_rows()

    def _language_search_changed(self, text: str) -> None:
        self.searches[self.tab + "_lang"] = text
        self._fill_languages()

    def _bible_search_changed(self, text: str) -> None:
        self.searches[self.tab] = text
        self._rebuild_rows()

    def _language_chosen(self, lang: Language) -> None:
        self.selected[self.tab] = lang.english
        if self.tab == "biblecom" and lang.tag not in self.bc_entries:
            key = f"load-bc:{lang.tag}"
            if key not in self.runner.events:
                self.set_message("Loading the list…", "dim")
                self.runner.start(key, lambda cancel, progress, l=lang: self.backend.bc_versions(l.tag, l.english, cancel))
        self._rebuild_rows()

    # ---- the Bibles of the chosen language -----------------------------------------------------------

    def _visible_entries(self) -> list[Entry]:
        text = self.searches[self.tab]
        if self.tab == "free":
            if text.strip():
                return catalog.search_all(self.free_entries, text)
            return catalog.for_language(self.free_entries, self.selected["free"] or "", "")
        lang = next((l for l in self.bc_langs if l.english == self.selected["biblecom"]), None)
        if lang is None:
            return []
        t = text.strip().lower()
        # Bible.com's own order (the most used first) is kept
        return [e for e in self.bc_entries.get(lang.tag, []) if not t or t in e.name.lower() or t in e.short.lower()]

    def _rebuild_rows(self) -> None:
        self._clear(self.list_layout)
        self.rows.clear()
        entries = self._visible_entries()
        for i, e in enumerate(entries):
            row = BibleRow(e, last=(i == len(entries) - 1), in_list=self._item(e.key) is not None,
                           saved=self.library.is_installed(e.key))
            row.add_clicked.connect(self.add_to_list)
            self.rows[e.key] = row
            self.list_layout.addWidget(row)
        self.list_frame.setVisible(bool(entries))

    # ---- your list -----------------------------------------------------------------------------------

    def add_to_list(self, entry: Entry) -> None:
        if self._item(entry.key) is not None:
            return
        self._reset_done()
        saved = self.library.is_installed(entry.key)
        item = ListItem(key=entry.key, entry=entry, short=entry.short, name=entry.name,
                        status="saved" if saved else "waiting", note="saved on this computer" if saved else "",
                        numbering=default_numbering(entry.language, entry.lang_code, entry.name),
                        code=next((i.code for i in self.library.items if i.source_key == entry.key), ""))
        self.items.append(item)
        row = self.rows.get(entry.key)
        if row:
            row.set_in_list(True)
        self._refresh_panel()

    def remove_from_list(self, key: str) -> None:
        if self.exporting:
            return
        item = self._item(key)
        if item is None:
            return
        self._reset_done()
        self.items.remove(item)
        row = self.rows.get(key)
        if row:
            row.set_in_list(False)
        self._refresh_panel()

    def _confirm_delete(self, item: ListItem, from_file: bool) -> bool:
        text = delete_message(item.name, from_file)
        box = QMessageBox(QMessageBox.Question, "Delete saved copy", text, QMessageBox.NoButton, self)
        yes = box.addButton("Delete", QMessageBox.DestructiveRole)
        box.addButton("Keep it", QMessageBox.RejectRole)
        box.exec()
        return box.clickedButton() is yes

    def delete_saved(self, key: str) -> None:
        """Deletes the saved copy of a Bible from this computer (the files already exported are not touched)."""
        if self.exporting:
            return
        item = self._item(key)
        if item is None or not item.code or self.library.get(item.code) is None:
            return
        from_file = item.entry is None
        if not self._confirm_delete(item, from_file):
            return
        self.library.remove(item.code)
        if from_file:
            self.items.remove(item)           # nothing left to download: it leaves the list
        else:
            item.code = ""
            item.status = "waiting"
            item.note = ""
            item.fraction = None
        self.last_done = None
        self.set_message(f"{item.short} deleted from this computer", "dim")
        self._refresh_panel()
        self._finish_rows()

    def _numbering_changed(self, key: str, value: str) -> None:
        item = self._item(key)
        if item:
            item.numbering = value

    def _reset_done(self) -> None:
        """Something changed: the old 'done' marks and the done box no longer describe the list."""
        for i in self.items:
            if i.status in ("done", "failed"):
                i.status = "saved" if self.library.is_installed(i.key) else "waiting"
                i.note = "saved on this computer" if i.status == "saved" else ""
        self.last_done = None

    def _refresh_panel(self) -> None:
        existing = {i.key for i in self.items}
        for key in list(self.item_rows):
            if key not in existing:
                w = self.item_rows.pop(key)
                self.items_layout.removeWidget(w)
                w.hide()
                w.setParent(None)
                w.deleteLater()
        for i, item in enumerate(self.items):
            row = self.item_rows.get(item.key)
            if row is None:
                row = ListItemRow(item)
                row.remove_clicked.connect(self.remove_from_list)
                row.delete_clicked.connect(self.delete_saved)
                row.numbering_changed.connect(self._numbering_changed)
                self.item_rows[item.key] = row
                self.items_layout.addWidget(row)
            row.setProperty("last", i == len(self.items) - 1)
            row.style().unpolish(row)
            row.style().polish(row)
            row.apply(item, show_picker=(self.fmt == "lp" and not self.exporting), can_remove=not self.exporting,
                      can_delete=not self.exporting)
        self.items_frame.setVisible(bool(self.items))
        pending = [i for i in self.items if i.status != "done"]
        if not self.exporting:
            self.count_label.setText(plural(len(self.items)) if self.items else "")
        self._refresh_export_block(len(pending))
        self._refresh_done_box()

    # ---- the export block ----------------------------------------------------------------------------

    def _format_changed(self, fmt: str) -> None:
        if self.exporting or fmt == self.fmt:
            self.seg.set_value(self.fmt)
            return
        self.fmt = fmt
        self.settings.setValue("format", fmt)
        self._reset_done()
        self._refresh_panel()

    def _refresh_export_block(self, pending: int) -> None:
        pp = self.fmt == "pp"
        mac_install = pp and self.platform == "mac"
        win_pp = pp and self.platform != "mac"
        self.seg.set_enabled(not self.exporting)
        if mac_install:
            self.hint1.setText(hint_html(
                "One <b>.rvbible</b> file for each Bible. <b>Add to ProPresenter</b> puts them where ProPresenter looks for "
                "Bibles, so you do not have to do anything by hand. ProPresenter usually shows them by itself; if not, "
                "close and reopen it."))
            self.hint2.setText(hint_html("Or use <b>Save files…</b> to keep the files in a folder you choose."))
        elif pp:
            self.hint1.setText(hint_html("One <b>.rvbible</b> file for each Bible, saved in a folder."))
            self.hint2.setText("")
        else:
            self.hint1.setText(hint_html("One <b>.json</b> file for each Bible. In Live Presenter use <b>Import a file</b>."))
            self.hint2.setText("")
        self.hint2.setVisible(bool(self.hint2.text()))
        self.dest_row.setVisible(not mac_install)
        self.path_label.setText("📁 " + str(self.folder))
        self.path_label.setToolTip(str(self.folder))
        self.choose_btn.setEnabled(not self.exporting)
        self.help_row.setVisible(win_pp)
        self.save_btn.setVisible(mac_install)
        total = len(self.items)
        n = pending if pending else total
        if self.exporting:
            self.go.setText("Cancel")
            self.go.setObjectName("go2")
            self.go.setEnabled(True)
            self.save_btn.setEnabled(False)
        else:
            if mac_install:
                label = f"Add {plural(n)} to ProPresenter" if total else "Add to ProPresenter"
            else:
                label = f"Export {plural(n)}" if total else "Export"
            self.go.setText(label)
            self.go.setObjectName("go")
            self.go.setEnabled(pending > 0)
            self.save_btn.setEnabled(pending > 0)
        self.go.style().unpolish(self.go)
        self.go.style().polish(self.go)

    def _choose_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Choose a folder for the files", str(self.folder.parent if not self.folder.exists() else self.folder))
        if d:
            self.folder = Path(d)
            self.settings.setValue("folder", d)
            self._refresh_panel()

    def _explain(self) -> None:
        ExplainDialog(self).exec()

    # ---- starting an export --------------------------------------------------------------------------

    def _go_clicked(self) -> None:
        if self.exporting:
            self.runner.cancel("export")
            self.go.setEnabled(False)
            self.go.setText("Cancelling…")
            return
        if self.fmt == "pp" and self.platform == "mac":
            self.start_export("install")
        else:
            self.start_export("files")

    def _save_files_clicked(self) -> None:
        """Mac, ProPresenter: save the files in a folder you choose instead of adding them."""
        if self.exporting:
            return
        d = QFileDialog.getExistingDirectory(self, "Choose a folder for the files", str(self.folder.parent if not self.folder.exists() else self.folder))
        if not d:
            return
        self.folder = Path(d)
        self.settings.setValue("folder", d)
        self.start_export("files")

    def start_export(self, mode: str, folder: Optional[Path] = None) -> None:
        """mode: "install" (Mac: into ProPresenter's folder) or "files" (into the chosen folder)."""
        if self.exporting:
            return
        todo = [i for i in self.items if i.status != "done"]
        if not todo:
            return
        dest = Path(folder or self.folder)
        if mode == "files":
            try:
                dest.mkdir(parents=True, exist_ok=True)
                probe = dest / ".bible-importer-test"
                probe.write_text("", encoding="utf-8")
                probe.unlink()
            except OSError as e:
                QMessageBox.warning(self, "Cannot save here", f"The files cannot be saved in\n{dest}\n\n{e}")
                return
        self.last_done = None
        self.exporting = True
        self.export_mode = mode
        self.export_seen = set()
        self.export_total = len(todo)
        fmt = self.fmt
        for i in todo:
            i.status = "waiting" if not self.library.is_installed(i.key) else "saved"
            i.note = ""
            i.fraction = None
        self.count_label.setText(f"Exporting 0 of {self.export_total}…")
        self._refresh_panel()
        jobs = [{"key": i.key, "entry": i.entry, "short": i.short, "name": i.name, "numbering": i.numbering,
                 "code": i.code} for i in todo]
        self.runner.start("export", lambda cancel, progress: self._export_worker(cancel, jobs, mode, dest, fmt))

    # ---- the export itself (runs in a background thread) -----------------------------------------------

    def _emit(self, key: str, status: str, note: str = "", fraction: Optional[float] = None, code: str = "") -> None:
        self.export_event.emit(key, status, note, -1.0 if fraction is None else float(fraction), code)

    def _export_worker(self, cancel, jobs: list[dict], mode: str, dest: Path, fmt: str) -> dict:
        ok: dict[str, str] = {}
        failed: dict[str, str] = {}
        for job in jobs:
            key, entry = job["key"], job["entry"]
            code = job["code"]
            try:
                if cancel.is_set():
                    raise Cancelled()
                if code and self.library.get(code):
                    pb = self.library.load(code)
                    self._emit(key, "busy", "Packaging…", None, code)
                else:
                    self._emit(key, "busy", "Downloading…", 0.0, "")

                    def progress(done: int, total: int, eta=None, e=entry, k=key) -> None:
                        frac = (done / total) if total > 0 else None
                        if e.source == "biblecom":
                            text = f"Downloading chapter by chapter… {done:,} of {total:,}"
                            if eta is not None:
                                text += f" · {fmt_eta(eta)}"
                        else:
                            text = f"Downloading… {int(frac * 100)}%" if frac is not None else "Downloading…"
                        self._emit(k, "busy", text, frac, "")
                    pb = self.backend.download(entry, cancel, progress)
                    saved = self.library.save(pb, entry.source, key)
                    code = saved.code
                    self._emit(key, "busy", "Packaging…", None, code)
                if cancel.is_set():
                    raise Cancelled()
                where = self._write_one(pb, job, mode, dest, fmt)
                ok[key] = where
                self._emit(key, "done", Path(where).name if mode == "files" else "added to ProPresenter", None, code)
            except Cancelled:
                self._emit(key, "saved" if code and self.library.get(code) else "waiting", "", None, code)
                break
            except (NetworkError, BibleError, OSError) as e:
                msg = BIBLECOM_FAIL if (entry is not None and entry.source == "biblecom" and isinstance(e, NetworkError)) else str(e)
                failed[key] = msg
                self._emit(key, "failed", msg, None, code)
            except Exception as e:  # never let the export thread die silently
                msg = f"Something went wrong ({type(e).__name__}: {e})."
                failed[key] = msg
                self._emit(key, "failed", msg, None, code)
        return {"ok": ok, "failed": failed, "mode": mode, "dest": str(dest), "fmt": fmt}

    def _write_one(self, pb: ParsedBible, job: dict, mode: str, dest: Path, fmt: str) -> str:
        base = safe_name(pb.short or pb.name)
        if fmt == "lp":
            path = unique_path(dest, base, ".json")
            export_lp.write(pb, path, job["numbering"])
            return str(path)
        if mode == "install":
            with tempfile.TemporaryDirectory() as tmp:
                rv = export_pp.write_rvbible(pb, Path(tmp) / f"{base}.rvbible")
                return str(export_pp.install_mac(rv))
        path = unique_path(dest, base, ".rvbible")
        export_pp.write_rvbible(pb, path)
        return str(path)

    # ---- results coming back --------------------------------------------------------------------------

    def _on_export_event(self, key: str, status: str, note: str, fraction: float, code: str) -> None:
        item = self._item(key)
        if item is None:
            return
        item.status = status
        item.note = note
        item.fraction = None if fraction < 0 else fraction
        if code:
            item.code = code
        if status == "done":
            item.done_text = "Added ✓" if self.export_mode == "install" else "Exported ✓"
        if status == "busy":
            self.export_seen.add(key)
            self.count_label.setText(f"Exporting {len(self.export_seen)} of {self.export_total}…")
        row = self.item_rows.get(key)
        if row:
            row.apply(item, show_picker=False, can_remove=False, can_delete=False)

    def _job_progress(self, key: str, done: int, total: int, eta) -> None:
        pass  # catalog downloads are shown through the export events

    def _job_done(self, key: str, result) -> None:
        self.runner.finished(key)
        if key == "load-free":
            self._free_loaded(result)
        elif key == "load-bc-langs":
            self._bc_langs_loaded(result)
        elif key.startswith("load-bc:"):
            self._bc_versions_loaded(key.split(":", 1)[1], result)
        elif key.startswith("import:"):
            self._imported(result)
        elif key == "export":
            self._export_finished(result)

    def _job_failed(self, key: str, message: str, network: bool = False) -> None:
        self.runner.finished(key)
        if key == "load-free":
            self.set_message(message, "error")
        elif key == "load-bc-langs" or key.startswith("load-bc:"):
            self.set_message(BIBLECOM_FAIL, "error")
        elif key.startswith("import:"):
            self.set_message(message, "error")
        elif key == "export":
            self.exporting = False
            self.set_message(message, "error")
            self._refresh_panel()

    def _job_cancelled(self, key: str) -> None:
        self.runner.finished(key)
        if key == "export":
            self.exporting = False
            for i in self.items:
                if i.status == "busy":
                    i.status = "saved" if self.library.is_installed(i.key) else "waiting"
                    i.note = "saved on this computer" if i.status == "saved" else ""
                    i.fraction = None
            self.count_label.setText(plural(len(self.items)) if self.items else "")
            self._finish_rows()
            self._refresh_panel()
            self.last_done = {"cancelled": True}
            self._refresh_done_box()

    def _export_finished(self, result: dict) -> None:
        self.exporting = False
        self.last_done = result
        self.count_label.setText(plural(len(self.items)))
        self._finish_rows()
        self._refresh_panel()

    def _finish_rows(self) -> None:
        """Bibles that were downloaded are now saved on this computer: show it in the list of Bibles."""
        if self.tab != "file":
            self._rebuild_rows()

    # ---- the green box -------------------------------------------------------------------------------

    def _refresh_done_box(self) -> None:
        d = self.last_done
        if not d or d.get("cancelled"):
            self.done_box.setVisible(False)
            if d and d.get("cancelled"):
                self.done_box.setVisible(True)
                self.done_head.setText("Export cancelled")
                self.done_text.setText("The Bibles already finished are kept.")
                self._set_done_buttons([])
            return
        ok, failed = len(d["ok"]), len(d["failed"])
        total = ok + failed
        install = d["mode"] == "install"
        noun = "added to ProPresenter" if install else ("saved" if d["fmt"] == "pp" and self.platform != "mac" else "exported")
        if failed and ok:
            head = f"✓ {ok} of {total} Bibles {noun}"
        elif failed:
            head = f"{plural(failed)} could not be {('added' if install else 'saved')}"
        else:
            head = f"✓ {plural(ok)} {noun}"
        self.done_head.setText(head)
        buttons: list[tuple[str, callable]] = []
        if install:
            text = ("ProPresenter usually shows them by itself.<br>If you do not see them, close and reopen ProPresenter.")
            if ok:
                buttons.append(("Show the files in Finder", self._show_install_folder))
        else:
            folder = d["dest"]
            text = f'Saved in <b style="color:{theme.TEXT}">{folder}</b><br>'
            if d["fmt"] == "lp":
                text += "In Live Presenter, use Import a file and pick them."
            elif self.platform != "mac":
                text += "To use them in ProPresenter you still need to add them: see the ? below."
            if ok:
                buttons.append(("Open the folder", lambda: self._open_folder(folder)))
            if d["fmt"] == "pp" and self.platform != "mac" and ok:
                buttons.append(("How to add them to ProPresenter", self._explain))
        if failed:
            buttons.append((f"Retry the failed one" if failed == 1 else "Retry the failed ones", self._go_clicked))
        self.done_text.setText(text)
        self._set_done_buttons(buttons)
        self.done_box.setVisible(True)

    def _set_done_buttons(self, buttons: list) -> None:
        self._clear(self.done_buttons)
        for text, fn in buttons:
            b = QPushButton(text)
            b.setObjectName("btn")
            b.clicked.connect(lambda _c=False, f=fn: f())
            self.done_buttons.addWidget(b)
        self.done_buttons.addStretch(1)

    def _open_folder(self, folder: str) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _show_install_folder(self) -> None:
        self._open_folder(str(export_pp.mac_bible_folder()))

    # ---- catalogs -------------------------------------------------------------------------------------

    def _free_loaded(self, cat: catalog.FreeCatalog) -> None:
        self.free_entries = cat.entries
        self.free_langs = catalog.languages(cat.entries, self.system_language)
        self.free_loaded = True
        self.set_message(OFFLINE_STALE if cat.stale else "", "warn")
        if self.tab == "free":
            self._fill_languages()

    def _bc_langs_loaded(self, result) -> None:
        langs, stale = result
        first = [self.system_language, "English", "Russian"]
        self.bc_langs = sorted(langs, key=lambda l: (first.index(l.english) if l.english in first else 99, l.english.lower()))
        self.bc_loaded = True
        self.set_message(OFFLINE_STALE if stale else BC_NOTE, "warn" if stale else "dim")
        if self.tab == "biblecom":
            self._fill_languages()

    def _bc_versions_loaded(self, tag: str, result) -> None:
        entries, stale = result
        self.bc_entries[tag] = entries
        for l in self.bc_langs:
            if l.tag == tag:
                l.count = len(entries)
        self.langs.refresh_counts()
        self.set_message(OFFLINE_STALE if stale else BC_NOTE, "warn" if stale else "dim")
        if self.tab == "biblecom":
            self._rebuild_rows()

    # ---- from a file ----------------------------------------------------------------------------------

    def _choose_file(self) -> None:
        names, _ = QFileDialog.getOpenFileNames(
            self, "Choose a Bible file", str(Path.home()),
            "Bible files (*.json *.xml *.zefania *.osis *.usx *.usfm *.sfm *.usf *.usfx *.rvbible *.zip);;All files (*)")
        if names:
            self.import_files([Path(n) for n in names])

    def import_files(self, paths: list[Path]) -> None:
        paths = [Path(p) for p in paths]
        key = f"import:{paths[0].name}"
        if key in self.runner.events:
            return
        self.set_message(f"Reading {paths[0].name}…", "dim")
        self.runner.start(key, lambda cancel, progress, p=paths: importers.read_files(p))

    def _imported(self, pb: ParsedBible) -> None:
        try:
            saved = self.library.save(pb, "file", "")
        except (BibleError, OSError) as e:
            self.set_message(f"Could not read this Bible: {e}", "error")
            return
        key = f"file:{saved.code}"
        if self._item(key) is None:
            self._reset_done()
            self.items.append(ListItem(key=key, entry=None, short=saved.short, name=saved.name, status="saved",
                                       note="from a file", numbering=saved.numbering, code=saved.code))
        self.set_message(f"✓ {saved.name} added to the list", "ok")
        self._refresh_panel()

    # ---- closing --------------------------------------------------------------------------------------

    def closeEvent(self, e: QCloseEvent) -> None:
        self.runner.cancel_all()
        self.runner.wait(4000)
        super().closeEvent(e)
