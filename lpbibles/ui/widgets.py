"""Small widgets of the Add Bibles window."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QEvent, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QMenu, QProgressBar, QPushButton, QSizePolicy, QStackedWidget, QStyle,
                               QStyledItemDelegate, QToolButton, QVBoxLayout, QWidget)

from ..catalog import Language
from ..library import NUMBERINGS, Installed
from ..model import Entry
from . import theme


def fmt_eta(seconds: Optional[float]) -> str:
    if seconds is None:
        return ""
    if seconds < 60:
        return "less than 1 min"
    return f"about {round(seconds / 60)} min"


# ---- language list -----------------------------------------------------------------------------------

class LanguageDelegate(QStyledItemDelegate):
    ROW = 33

    def sizeHint(self, option, index) -> QSize:
        return QSize(option.rect.width(), self.ROW)

    def paint(self, p: QPainter, option, index) -> None:
        lang: Language = index.data(Qt.UserRole)
        selected = bool(option.state & QStyle.State_Selected)
        hover = bool(option.state & QStyle.State_MouseOver)
        r = option.rect
        p.save()
        p.setRenderHint(QPainter.Antialiasing, False)
        if selected:
            p.fillRect(r, QColor(theme.PANEL2))
            p.fillRect(QRect(r.left(), r.top(), 3, r.height()), QColor(theme.ORANGE))
        elif hover:
            p.fillRect(r, QColor(255, 255, 255, 10))
        f = QFont(option.font)
        f.setPixelSize(13)
        f.setBold(selected)
        p.setFont(f)
        p.setPen(QColor("#ffffff" if selected else theme.TEXT2))
        p.drawText(QRect(r.left() + 16, r.top(), r.width() - 70, r.height()), Qt.AlignVCenter | Qt.AlignLeft,
                   p.fontMetrics().elidedText(lang.native, Qt.ElideRight, r.width() - 80))
        if lang.count is not None:
            f2 = QFont(option.font)
            f2.setPixelSize(11)
            f2.setBold(True)
            p.setFont(f2)
            p.setPen(QColor(theme.DIM))
            p.drawText(QRect(r.right() - 54, r.top(), 40, r.height()), Qt.AlignVCenter | Qt.AlignRight, str(lang.count))
        p.restore()


class LanguageList(QListWidget):
    chosen = Signal(object)   # Language

    def __init__(self):
        super().__init__()
        self.setObjectName("langs")
        self.setItemDelegate(LanguageDelegate(self))
        self.setMouseTracking(True)
        self.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        self.currentItemChanged.connect(self._changed)
        self._languages: list[Language] = []

    def _changed(self, cur: Optional[QListWidgetItem], _prev) -> None:
        if cur is not None:
            self.chosen.emit(cur.data(Qt.UserRole))

    def set_languages(self, languages: list[Language], select: Optional[str] = None) -> None:
        self._languages = languages
        self.blockSignals(True)
        self.clear()
        for lang in languages:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, lang)
            item.setSizeHint(QSize(100, LanguageDelegate.ROW))
            self.addItem(item)
        self.blockSignals(False)
        row = next((i for i, l in enumerate(languages) if l.english == select), 0 if languages else -1)
        if row >= 0:
            self.setCurrentRow(row)   # emits `chosen`

    def refresh_counts(self) -> None:
        self.viewport().update()


# ---- one Bible of a catalog ---------------------------------------------------------------------------

class BibleRow(QFrame):
    download_clicked = Signal(object)
    cancel_clicked = Signal(object)

    # short name, tag, size, action: widths from the renderings (the Bible.com tab has a wider action column)
    COLS = (62, 74, 54, 188)
    COLS_WIDE = (62, 74, 30, 300)

    def __init__(self, entry: Entry, last: bool = False, cancel_text: bool = False):
        super().__init__()
        self.entry = entry
        self.setObjectName("brow")
        self.setProperty("last", last)
        self.setMinimumHeight(33)
        self._cancel_text = cancel_text
        self.cols = self.COLS_WIDE if cancel_text else self.COLS
        g = QGridLayout(self)
        g.setContentsMargins(12, 0, 12, 0)
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(0)
        self.name = QLabel(entry.name)
        self.name.setObjectName("name")
        self.name.setToolTip(entry.name)
        self.name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        short = QLabel(entry.short)
        short.setObjectName("short")
        tag = QLabel("Licensed" if entry.licensed else "Free")
        tag.setObjectName("taglic" if entry.licensed else "tagfree")
        tag.setAlignment(Qt.AlignCenter)
        tag_cell = QWidget()
        tl = QHBoxLayout(tag_cell)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(tag, 0, Qt.AlignLeft | Qt.AlignVCenter)
        tl.addStretch(1)
        self.size = QLabel(self._size_text())
        self.size.setObjectName("size")
        self.size.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.stack = QStackedWidget()
        self.stack.setFixedWidth(self.cols[3])
        self.stack.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        # 0 download, 1 busy, 2 installed, 3 failed
        self.btn = QPushButton("Download")
        self.btn.setObjectName("download")
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.clicked.connect(lambda: self.download_clicked.emit(self.entry))
        self.stack.addWidget(self._right(self.btn))
        busy = QWidget()
        bl = QHBoxLayout(busy)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(8)
        col = QVBoxLayout()
        col.setSpacing(3)
        col.setContentsMargins(0, 0, 0, 0)
        self.ptext = QLabel("Downloading…")
        self.ptext.setObjectName("progresstext")
        self.ptext.setWordWrap(True)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 1000)
        col.addWidget(self.ptext)
        col.addWidget(self.bar)
        bl.addLayout(col, 1)
        if cancel_text:
            self.cancel = QPushButton("Cancel")
            self.cancel.setObjectName("cancel")
        else:
            self.cancel = QPushButton("✕")
            self.cancel.setObjectName("cancelx")
            self.cancel.setFixedSize(20, 20)
        self.cancel.setCursor(Qt.PointingHandCursor)
        self.cancel.setToolTip("Cancel")
        self.cancel.clicked.connect(lambda: self.cancel_clicked.emit(self.entry))
        bl.addWidget(self.cancel, 0, Qt.AlignVCenter)
        self.stack.addWidget(busy)
        self.ins = QLabel("Installed ✓")
        self.ins.setObjectName("installed")
        self.stack.addWidget(self._right(self.ins))
        failed = QWidget()
        fl = QHBoxLayout(failed)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.addStretch(1)
        self.retry = QPushButton("Retry")
        self.retry.setObjectName("retry")
        self.retry.setCursor(Qt.PointingHandCursor)
        self.retry.clicked.connect(lambda: self.download_clicked.emit(self.entry))
        fl.addWidget(self.retry)
        self.stack.addWidget(failed)

        g.addWidget(self.name, 0, 0)
        g.addWidget(short, 0, 1)
        g.addWidget(tag_cell, 0, 2)
        g.addWidget(self.size, 0, 3)
        g.addWidget(self.stack, 0, 4)
        g.setColumnStretch(0, 1)
        g.setColumnMinimumWidth(1, self.cols[0])
        g.setColumnMinimumWidth(2, self.cols[1])
        g.setColumnMinimumWidth(3, self.cols[2])
        self.state = "idle"

    @staticmethod
    def _right(w: QWidget) -> QWidget:
        host = QWidget()
        h = QHBoxLayout(host)
        h.setContentsMargins(0, 0, 0, 0)
        h.addStretch(1)
        h.addWidget(w)
        return host

    def _size_text(self) -> str:
        e = self.entry
        if e.size_mb:
            return f"{max(1, round(e.size_mb))} MB"
        return "NT" if e.note == "NT only" else "—"

    def set_state(self, state: str, text: str = "", fraction: Optional[float] = None) -> None:
        """state: idle, busy, installed, failed."""
        self.state = state
        self.setMinimumHeight(58 if (state == "busy" and self._cancel_text) else 33)
        self.stack.setCurrentIndex({"idle": 0, "busy": 1, "installed": 2, "failed": 3}[state])
        if state == "busy":
            self.ptext.setText(text or "Downloading…")
            if fraction is None:
                self.bar.setValue(0)
            else:
                self.bar.setValue(int(max(0.0, min(1.0, fraction)) * 1000))
            self.cancel.setEnabled(True)
        self.size.setText("Failed" if state == "failed" else self._size_text())
        self.size.setObjectName("size")
        self.size.setStyleSheet(f"color: {theme.FAILED}; font-size: 11px;" if state == "failed" else "")

    def set_cancelling(self) -> None:
        self.ptext.setText("Cancelling…")
        self.cancel.setEnabled(False)


# ---- installed list ------------------------------------------------------------------------------------

class InstalledRow(QFrame):
    numbering_changed = Signal(str, str)
    remove_clicked = Signal(str)
    export_json = Signal(str)
    export_rvbible = Signal(str)
    install_pp = Signal(str)

    def __init__(self, item: Installed, last: bool, can_install: bool):
        super().__init__()
        self.code = item.code
        self.setObjectName("irow")
        self.setProperty("last", last)
        self.setFixedHeight(30)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        chip_cell = QWidget()
        chip_cell.setFixedWidth(96)
        cl = QHBoxLayout(chip_cell)
        cl.setContentsMargins(0, 0, 0, 0)
        chip = QLabel(item.short)
        chip.setObjectName("chip")
        chip.setMaximumWidth(96)
        cl.addWidget(chip, 0, Qt.AlignLeft | Qt.AlignVCenter)
        cl.addStretch(1)
        h.addWidget(chip_cell)
        name = QLabel(item.name)
        name.setObjectName("iname")
        name.setToolTip(item.copyright[:600] if item.copyright else item.name)
        name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        h.addWidget(name, 1)
        combo = QComboBox()
        combo.setFixedWidth(168)
        for key, title in NUMBERINGS.items():
            combo.addItem(title, key)
        combo.setCurrentIndex(max(0, combo.findData(item.numbering)))
        combo.setAccessibleName(f"Numbering of {item.short}")
        combo.currentIndexChanged.connect(lambda _i: self.numbering_changed.emit(self.code, combo.currentData()))
        h.addWidget(combo)
        export = QToolButton()
        export.setObjectName("small")
        export.setText("Export ▾")
        export.setPopupMode(QToolButton.InstantPopup)
        export.setFixedWidth(76)
        export.setCursor(Qt.PointingHandCursor)
        menu = QMenu(export)
        menu.addAction("For Live Presenter (.json)…", lambda: self.export_json.emit(self.code))
        menu.addAction("For ProPresenter (.rvbible)…", lambda: self.export_rvbible.emit(self.code))
        menu.addSeparator()
        a = menu.addAction("Install in ProPresenter…", lambda: self.install_pp.emit(self.code))
        a.setEnabled(can_install)
        if not can_install:
            a.setToolTip("ProPresenter installs on Mac and Windows only")
        export.setMenu(menu)
        h.addWidget(export)
        remove = QPushButton("Remove")
        remove.setObjectName("small")
        remove.setFixedWidth(72)
        remove.setCursor(Qt.PointingHandCursor)
        remove.setAccessibleName(f"Remove {item.short}")
        remove.clicked.connect(lambda: self.remove_clicked.emit(self.code))
        h.addWidget(remove)


# ---- import drop zone ---------------------------------------------------------------------------------

class DropZone(QFrame):
    import_clicked = Signal()
    files_dropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setObjectName("dz")
        self.setAcceptDrops(True)
        self.setFixedWidth(360)
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 8, 18, 8)
        v.setSpacing(7)
        v.addStretch(1)
        btn = QPushButton("Import a file…")
        btn.setObjectName("importbtn")
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(self.import_clicked)
        v.addWidget(btn, 0, Qt.AlignHCenter)
        p = QLabel("Drop a Bible file here.\nOnly add Bibles you have the right to use.")
        p.setObjectName("dzp")
        p.setAlignment(Qt.AlignCenter)
        v.addWidget(p)
        s = QLabel("Zefania · OSIS · USX · USFM · USFX · ProPresenter .rvbible · JSON")
        s.setObjectName("dzsmall")
        s.setAlignment(Qt.AlignCenter)
        s.setWordWrap(True)
        v.addWidget(s)
        v.addStretch(1)

    def _set_hover(self, on: bool) -> None:
        self.setProperty("hover", on)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._set_hover(True)

    def dragLeaveEvent(self, e) -> None:
        self._set_hover(False)

    def dropEvent(self, e) -> None:
        self._set_hover(False)
        paths = [Path(u.toLocalFile()) for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
            e.acceptProposedAction()
