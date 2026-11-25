"""The Add Bibles window (layout from the approved Live Presenter renderings, specs/add-bibles/)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QLocale, Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QMainWindow, QMessageBox, QPushButton, QRadioButton, QScrollArea, QVBoxLayout, QWidget)

from .. import catalog, export_lp, export_pp, importers
from ..backend import Backend
from ..catalog import Language
from ..library import Installed, Library
from ..model import BibleError, Entry, ParsedBible
from . import theme
from .widgets import BibleRow, DropZone, InstalledRow, LanguageList, fmt_eta
from .workers import Runner

BIBLECOM_FAIL = "Bible.com did not answer. Try again later, or import a file."
OFFLINE_STALE = "⚠ Could not reach the list. Showing the saved list."


def system_language_name() -> str:
    return QLocale.languageToString(QLocale.system().language())


class InstallDialog(QDialog):
    """Windows only: how to put a Bible into ProPresenter."""

    def __init__(self, parent, short: str, choices: list[dict]):
        super().__init__(parent)
        self.setWindowTitle("Install in ProPresenter")
        self.setModal(True)
        self.setMinimumWidth(520)
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 20, 22, 18)
        v.setSpacing(12)
        t = QLabel(f"Install {short} in ProPresenter")
        t.setObjectName("dlgtitle")
        v.addWidget(t)
        self.overwrite = QRadioButton("Take the place of one of ProPresenter's free Bibles (recommended)")
        self.overwrite.setChecked(bool(choices))
        self.overwrite.setEnabled(bool(choices))
        v.addWidget(self.overwrite)
        self.combo = QComboBox()
        for c in choices:
            self.combo.addItem(f'{c["language"]} · {c["name"]} ({c["displayAbbreviation"]})', c)
        self.combo.setEnabled(bool(choices))
        v.addWidget(self.combo)
        warn = QLabel("The Bible you pick here can no longer be used in ProPresenter.")
        warn.setObjectName("dlgwarn")
        v.addWidget(warn)
        self.sideload = QRadioButton("Sideload (advanced): ProPresenter may not list it, and old files can stay behind")
        self.sideload.setChecked(not choices)
        v.addWidget(self.sideload)
        row = QHBoxLayout()
        row.addStretch(1)
        no = QPushButton("Cancel")
        no.setObjectName("secondary")
        no.clicked.connect(self.reject)
        yes = QPushButton("Install")
        yes.setObjectName("primary")
        yes.clicked.connect(self.accept)
        row.addWidget(no)
        row.addWidget(yes)
        v.addLayout(row)

    def choice(self) -> Optional[dict]:
        return self.combo.currentData() if self.overwrite.isChecked() else None


class MainWindow(QMainWindow):
    def __init__(self, library: Library, backend: Backend, system_language: Optional[str] = None):
        super().__init__()
        self.setWindowTitle("Add Bibles")
        self.resize(1100, 720)
        self.setMinimumSize(900, 600)
        self.library = library
        self.backend = backend
        self.system_language = system_language or system_language_name()
        self.runner = Runner()
        self.runner.done.connect(self._job_done)
        self.runner.failed.connect(self._job_failed)
        self.runner.cancelled.connect(self._job_cancelled)
        self.runner.progress.connect(self._job_progress)

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
        self.failed: dict[str, str] = {}
        self.busy_text: dict[str, tuple[str, Optional[float]]] = {}

        self._build()
        self._refresh_installed()
        self._switch_tab("free")
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
        header.setFixedHeight(46)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 16, 0)
        title = QLabel("Add Bibles")
        title.setObjectName("title")
        hl.addWidget(title)
        col.addWidget(header)

        tabs = QFrame()
        tabs.setObjectName("tabs")
        tabs.setFixedHeight(40)
        tl = QHBoxLayout(tabs)
        tl.setContentsMargins(18, 0, 18, 0)
        tl.setSpacing(22)
        self.tab_buttons: dict[str, QPushButton] = {}
        for key, text in (("free", "Free Bibles"), ("biblecom", "Bible.com")):
            b = QPushButton(text)
            b.setObjectName("tab")
            b.setCheckable(True)
            b.setAutoExclusive(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c=False, k=key: self._switch_tab(k))
            tl.addWidget(b, 0, Qt.AlignBottom)
            self.tab_buttons[key] = b
        tl.addStretch(1)
        col.addWidget(tabs)

        self.amber = QFrame()
        self.amber.setObjectName("amber")
        al = QHBoxLayout(self.amber)
        al.setContentsMargins(18, 7, 18, 7)
        al.addWidget(QLabel("⚠  These Bibles are copyrighted. Add one only if your church has the right to use it."))
        al.addStretch(1)
        col.addWidget(self.amber)

        body = QHBoxLayout()
        body.setSpacing(0)
        col.addLayout(body, 1)

        left = QFrame()
        left.setObjectName("lc")
        left.setFixedWidth(260)
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
        body.addWidget(left)

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
        self.scroll_body = QWidget()
        self.scroll_body.setObjectName("scrollbody")
        sb = QVBoxLayout(self.scroll_body)
        sb.setContentsMargins(0, 0, 0, 0)
        sb.setSpacing(8)
        self.list_frame = QFrame()
        self.list_frame.setObjectName("lst")
        self.list_layout = QVBoxLayout(self.list_frame)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(0)
        sb.addWidget(self.list_frame)
        self.message = QLabel("")
        self.message.setObjectName("message")
        self.message.setWordWrap(True)
        self.message.setContentsMargins(2, 0, 2, 0)
        sb.addWidget(self.message)
        sb.addStretch(1)
        self.scroll.setWidget(self.scroll_body)
        rl.addWidget(self.scroll, 1)
        body.addWidget(right, 1)

        bb = QFrame()
        bb.setObjectName("bb")
        bb.setFixedHeight(136)
        bl = QHBoxLayout(bb)
        bl.setContentsMargins(16, 10, 16, 10)
        bl.setSpacing(16)
        il = QVBoxLayout()
        il.setSpacing(4)
        lab = QLabel("INSTALLED")
        lab.setObjectName("lab")
        il.addWidget(lab)
        self.inst_scroll = QScrollArea()
        self.inst_scroll.setWidgetResizable(True)
        self.inst_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.inst_body = QWidget()
        self.inst_body.setObjectName("scrollbody")
        self.inst_layout = QVBoxLayout(self.inst_body)
        self.inst_layout.setContentsMargins(0, 0, 0, 0)
        self.inst_layout.setSpacing(0)
        self.inst_scroll.setWidget(self.inst_body)
        il.addWidget(self.inst_scroll, 1)
        bl.addLayout(il, 1)
        self.drop = DropZone()
        self.drop.import_clicked.connect(self._import_dialog)
        self.drop.files_dropped.connect(self.import_files)
        bl.addWidget(self.drop)
        col.addWidget(bb)

    # ---- small helpers -------------------------------------------------------------------------------

    def set_message(self, text: str, kind: str = "ok") -> None:
        self.message.setStyleSheet(f"color: {theme.MESSAGE_COLORS.get(kind, theme.DIM)};")
        self.message.setText(text)

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

    # ---- tabs, languages, search ---------------------------------------------------------------------

    def _switch_tab(self, key: str) -> None:
        self.tab = key
        self.tab_buttons[key].setChecked(True)
        self.amber.setVisible(key == "biblecom")
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
            self._rebuild_list()

    def _language_search_changed(self, text: str) -> None:
        self.searches[self.tab + "_lang"] = text
        self._fill_languages()

    def _bible_search_changed(self, text: str) -> None:
        self.searches[self.tab] = text
        self._rebuild_list()

    def _language_chosen(self, lang: Language) -> None:
        self.selected[self.tab] = lang.english
        if self.tab == "biblecom" and lang.tag not in self.bc_entries:
            key = f"load-bc:{lang.tag}"
            if key not in self.runner.events:
                self.set_message("Loading the list…", "dim")
                self.runner.start(key, lambda cancel, progress, l=lang: self.backend.bc_versions(l.tag, l.english, cancel))
        self._rebuild_list()

    # ---- the list of Bibles --------------------------------------------------------------------------

    def _visible_entries(self) -> list[Entry]:
        text = self.searches[self.tab]
        if self.tab == "free":
            if text.strip():
                return catalog.search_all(self.free_entries, text)
            return catalog.for_language(self.free_entries, self.selected["free"] or "", "")
        lang = next((l for l in self.bc_langs if l.english == self.selected["biblecom"]), None)
        if lang is None:
            return []
        entries = self.bc_entries.get(lang.tag, [])
        t = text.strip().lower()
        # Bible.com's own order (the most used first) is kept
        return [e for e in entries if not t or t in e.name.lower() or t in e.short.lower()]

    def _rebuild_list(self) -> None:
        self._clear(self.list_layout)
        self.rows.clear()
        entries = self._visible_entries()
        for i, e in enumerate(entries):
            row = BibleRow(e, last=(i == len(entries) - 1), cancel_text=(self.tab == "biblecom"))
            row.download_clicked.connect(self.start_download)
            row.cancel_clicked.connect(self.cancel_download)
            self.rows[e.key] = row
            self.list_layout.addWidget(row)
            self._apply_row_state(row)
        self.list_frame.setVisible(bool(entries))

    def _apply_row_state(self, row: BibleRow) -> None:
        key = row.entry.key
        if key in self.runner.events:
            text, frac = self.busy_text.get(key, ("Downloading…", None))
            row.set_state("busy", text, frac)
        elif self.library.is_installed(key):
            row.set_state("installed")
        elif key in self.failed:
            row.set_state("failed")
        else:
            row.set_state("idle")

    # ---- downloads -----------------------------------------------------------------------------------

    def start_download(self, entry: Entry) -> None:
        if entry.key in self.runner.events:
            return
        self.failed.pop(entry.key, None)
        self.busy_text[entry.key] = ("Downloading…", None)
        row = self.rows.get(entry.key)
        if row:
            row.set_state("busy", "Downloading…", None)
        self.set_message(f"Downloading {entry.short}…", "dim")
        self.runner.start(entry.key, lambda cancel, progress, e=entry: self.backend.download(e, cancel, progress))

    def cancel_download(self, entry: Entry) -> None:
        self.runner.cancel(entry.key)
        row = self.rows.get(entry.key)
        if row:
            row.set_cancelling()

    # ---- job results ---------------------------------------------------------------------------------

    def _job_progress(self, key: str, done: int, total: int, eta) -> None:
        entry = self._entries_by_key().get(key)
        if entry is None:
            return
        frac = (done / total) if total > 0 else None
        if entry.source == "biblecom":
            text = f"Downloading chapter by chapter… {done:,} of {total:,}"
            if eta is not None:
                text += f" · {fmt_eta(eta)}"
        else:
            text = f"Downloading… {int(frac * 100)}%" if frac is not None else "Downloading…"
        self.busy_text[key] = (text, frac)
        row = self.rows.get(key)
        if row and row.state == "busy" and row.cancel.isEnabled():
            row.set_state("busy", text, frac)

    def _job_done(self, key: str, result) -> None:
        self.runner.finished(key)
        self.busy_text.pop(key, None)
        if key == "load-free":
            self._free_loaded(result)
        elif key == "load-bc-langs":
            self._bc_langs_loaded(result)
        elif key.startswith("load-bc:"):
            self._bc_versions_loaded(key.split(":", 1)[1], result)
        elif key.startswith("import:"):
            self._imported(result)
        else:
            self._downloaded(key, result)

    def _job_failed(self, key: str, message: str, network: bool = False) -> None:
        self.runner.finished(key)
        self.busy_text.pop(key, None)
        if key == "load-free":
            self.set_message(message, "error")
        elif key == "load-bc-langs" or key.startswith("load-bc:"):
            self.set_message(BIBLECOM_FAIL, "error")
        elif key.startswith("import:"):
            self.set_message(message, "error")
        else:
            entry = self._entries_by_key().get(key)
            self.failed[key] = message
            short = entry.short if entry else key
            if entry and entry.source == "biblecom" and network:
                self.set_message(BIBLECOM_FAIL, "error")
            else:
                self.set_message(f"Could not download {short}: {message}", "error")
            row = self.rows.get(key)
            if row:
                row.set_state("failed")

    def _job_cancelled(self, key: str) -> None:
        self.runner.finished(key)
        self.busy_text.pop(key, None)
        row = self.rows.get(key)
        if row:
            row.set_state("idle")
        if key.startswith("import:") or key.startswith("load"):
            return
        self.set_message("Download cancelled.", "dim")

    def _free_loaded(self, cat: catalog.FreeCatalog) -> None:
        self.free_entries = cat.entries
        self.free_langs = catalog.languages(cat.entries, self.system_language)
        self.free_loaded = True
        self.set_message(OFFLINE_STALE if cat.stale else "", "warn")
        if self.tab == "free":
            self._fill_languages()

    def _bc_langs_loaded(self, result) -> None:
        langs, stale = result
        self.bc_langs = langs
        self.bc_loaded = True
        ordered = [l for l in langs]
        first = [self.system_language, "English", "Russian"]
        ordered.sort(key=lambda l: (first.index(l.english) if l.english in first else 99, l.english.lower()))
        self.bc_langs = ordered
        self.set_message(OFFLINE_STALE if stale else "Bible.com can change without notice. If a download fails, import a file instead.",
                         "warn" if stale else "dim")
        if self.tab == "biblecom":
            self._fill_languages()

    def _bc_versions_loaded(self, tag: str, result) -> None:
        entries, stale = result
        self.bc_entries[tag] = entries
        for l in self.bc_langs:
            if l.tag == tag:
                l.count = len(entries)
        self.langs.refresh_counts()
        self.set_message(OFFLINE_STALE if stale else "Bible.com can change without notice. If a download fails, import a file instead.",
                         "warn" if stale else "dim")
        if self.tab == "biblecom":
            self._rebuild_list()

    def _downloaded(self, key: str, pb: ParsedBible) -> None:
        entry = self._entries_by_key().get(key)
        try:
            self.library.save(pb, entry.source if entry else "file", key)
        except (BibleError, OSError) as e:
            self.failed[key] = str(e)
            self.set_message(f"Could not save {pb.short or pb.name}: {e}", "error")
            row = self.rows.get(key)
            if row:
                row.set_state("failed")
            return
        row = self.rows.get(key)
        if row:
            row.set_state("installed")
        self.set_message(f"✓ {pb.short or pb.name} downloaded", "ok")
        self._refresh_installed()

    def _imported(self, pb: ParsedBible) -> None:
        try:
            item = self.library.save(pb, "file", "")
        except (BibleError, OSError) as e:
            self.set_message(f"Could not save {pb.name}: {e}", "error")
            return
        self.set_message(f"✓ {item.name} imported", "ok")
        self._refresh_installed()

    # ---- import --------------------------------------------------------------------------------------

    def _import_dialog(self) -> None:
        names, _ = QFileDialog.getOpenFileNames(
            self, "Import a Bible file", str(Path.home()),
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

    # ---- installed list ------------------------------------------------------------------------------

    def _refresh_installed(self) -> None:
        self._clear(self.inst_layout)
        items = self.library.items
        can_install = export_pp.is_mac() or export_pp.is_windows()
        for i, item in enumerate(items):
            r = InstalledRow(item, last=(i == len(items) - 1), can_install=can_install)
            r.numbering_changed.connect(self.library.set_numbering)
            r.remove_clicked.connect(self._remove)
            r.export_json.connect(self._export_json)
            r.export_rvbible.connect(self._export_rvbible)
            r.install_pp.connect(self._install_pp)
            self.inst_layout.addWidget(r)
        if not items:
            empty = QLabel("No Bibles yet. Download one above, or import a file.")
            empty.setObjectName("dzsmall")
            self.inst_layout.addWidget(empty)
        self.inst_layout.addStretch(1)
        for row in self.rows.values():
            self._apply_row_state(row)

    def _remove(self, code: str) -> None:
        item = self.library.get(code)
        if item is None:
            return
        if item.source == "file":
            ok = QMessageBox.question(self, "Remove Bible",
                                      f"Remove {item.name}? It came from a file, so it can only come back by importing the file again.")
            if ok != QMessageBox.Yes:
                return
        self.library.remove(code)
        self.set_message(f"{item.short} removed", "dim")
        self._refresh_installed()

    # ---- export --------------------------------------------------------------------------------------

    def _load(self, code: str) -> Optional[tuple[Installed, ParsedBible]]:
        item = self.library.get(code)
        if item is None:
            return None
        try:
            return item, self.library.load(code)
        except BibleError as e:
            self.set_message(str(e), "error")
            return None

    def _export_json(self, code: str, path: Optional[str] = None) -> None:
        got = self._load(code)
        if not got:
            return
        item, pb = got
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, "Save for Live Presenter", str(Path.home() / f"{item.short}.json"),
                                                  "JSON (*.json)")
        if not path:
            return
        try:
            export_lp.write(pb, Path(path), item.numbering)
        except OSError as e:
            self.set_message(f"Could not save the file: {e}", "error")
            return
        self.set_message(f"✓ Saved {Path(path).name}. In Live Presenter, use Import a file.", "ok")

    def _export_rvbible(self, code: str, path: Optional[str] = None) -> None:
        got = self._load(code)
        if not got:
            return
        item, pb = got
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, "Save for ProPresenter", str(Path.home() / f"{item.short}.rvbible"),
                                                  "ProPresenter Bible (*.rvbible)")
        if not path:
            return
        try:
            export_pp.write_rvbible(pb, Path(path))
        except (OSError, BibleError) as e:
            self.set_message(f"Could not save the file: {e}", "error")
            return
        self.set_message(f"✓ Saved {Path(path).name}", "ok")

    def _install_pp(self, code: str) -> None:
        got = self._load(code)
        if not got:
            return
        item, pb = got
        try:
            if export_pp.is_mac():
                with tempfile.TemporaryDirectory() as tmp:
                    rv = export_pp.write_rvbible(pb, Path(tmp) / f"{item.short}.rvbible")
                    export_pp.install_mac(rv)
            elif export_pp.is_windows():
                try:
                    choices = export_pp.windows_free_bibles()
                except BibleError as e:
                    self.set_message(str(e), "error")
                    return
                dlg = InstallDialog(self, item.short, choices)
                if dlg.exec() != QDialog.Accepted:
                    return
                choice = dlg.choice()
                if choice:
                    export_pp.install_windows_overwrite(pb, choice)
                else:
                    with tempfile.TemporaryDirectory() as tmp:
                        rv = export_pp.write_rvbible(pb, Path(tmp) / f"{item.short}.rvbible")
                        export_pp.install_windows_sideload(rv)
            else:
                self.set_message("ProPresenter installs on Mac and Windows only.", "warn")
                return
        except (OSError, BibleError) as e:
            self.set_message(f"Could not install in ProPresenter: {e}", "error")
            return
        self.set_message(f"✓ {item.short} installed. Close and reopen ProPresenter to see it.", "ok")

    # ---- closing -------------------------------------------------------------------------------------

    def closeEvent(self, e: QCloseEvent) -> None:
        self.runner.cancel_all()
        self.runner.wait(4000)
        super().closeEvent(e)
