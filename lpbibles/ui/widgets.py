"""Widgets of the Bible Importer window (layout from design/*.html)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QProgressBar, QPushButton, QSizePolicy, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget)

from ..catalog import Language
from ..library import NUMBERINGS
from ..model import Entry
from . import theme


def fmt_eta(seconds: Optional[float]) -> str:
    if seconds is None:
        return ""
    if seconds < 60:
        return "less than 1 min"
    return f"about {round(seconds / 60)} min"


def plural(n: int, one: str = "Bible", many: str = "Bibles") -> str:
    return f"{n} {one if n == 1 else many}"


def step_header(number: str, text: str) -> tuple[QWidget, QLabel]:
    """The orange numbered circle with a small-caps title. Returns (widget, label on the right)."""
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(8)
    n = QLabel(number)
    n.setObjectName("stepnum")
    n.setFixedSize(18, 18)
    n.setAlignment(Qt.AlignCenter)
    t = QLabel(text)
    t.setObjectName("steptext")
    h.addWidget(n)
    h.addWidget(t)
    h.addStretch(1)
    r = QLabel("")
    r.setObjectName("stepright")
    h.addWidget(r)
    return w, r


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
        p.drawText(QRect(r.left() + 16, r.top(), r.width() - 60, r.height()), Qt.AlignVCenter | Qt.AlignLeft,
                   p.fontMetrics().elidedText(lang.native, Qt.ElideRight, r.width() - 70))
        if lang.count is not None:
            f2 = QFont(option.font)
            f2.setPixelSize(11)
            f2.setBold(True)
            p.setFont(f2)
            p.setPen(QColor(theme.DIM))
            p.drawText(QRect(r.right() - 48, r.top(), 34, r.height()), Qt.AlignVCenter | Qt.AlignRight, str(lang.count))
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

    def _changed(self, cur: Optional[QListWidgetItem], _prev) -> None:
        if cur is not None:
            self.chosen.emit(cur.data(Qt.UserRole))

    def set_languages(self, languages: list[Language], select: Optional[str] = None) -> None:
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
    add_clicked = Signal(object)

    def __init__(self, entry: Entry, last: bool, in_list: bool, saved: bool):
        super().__init__()
        self.entry = entry
        self.setObjectName("brow")
        self.setProperty("last", last)
        self.setMinimumHeight(36)
        g = QGridLayout(self)
        g.setContentsMargins(12, 0, 12, 0)
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(0)
        namebox = QWidget()
        nv = QVBoxLayout(namebox)
        nv.setContentsMargins(0, 3, 0, 3)
        nv.setSpacing(0)
        name = QLabel(entry.name)
        name.setObjectName("name")
        name.setToolTip(entry.name)
        name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        nv.addWidget(name)
        if saved:
            s = QLabel("saved on this computer")
            s.setObjectName("saved")
            nv.addWidget(s)
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
        size = QLabel(self._size_text(entry))
        size.setObjectName("size")
        size.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.add = QPushButton("＋ Add")
        self.add.setObjectName("add")
        self.add.setCursor(Qt.PointingHandCursor)
        self.add.setAccessibleName(f"Add {entry.short} to the list")
        self.add.clicked.connect(lambda: self.add_clicked.emit(self.entry))
        self.inlist = QLabel("In list ✓")
        self.inlist.setObjectName("inlist")
        action = QWidget()
        action.setFixedWidth(118)
        al = QHBoxLayout(action)
        al.setContentsMargins(0, 0, 0, 0)
        al.addStretch(1)
        al.addWidget(self.add)
        al.addWidget(self.inlist)
        g.addWidget(namebox, 0, 0)
        g.addWidget(short, 0, 1)
        g.addWidget(tag_cell, 0, 2)
        g.addWidget(size, 0, 3)
        g.addWidget(action, 0, 4)
        g.setColumnStretch(0, 1)
        g.setColumnMinimumWidth(1, 54)
        g.setColumnMinimumWidth(2, 70)
        g.setColumnMinimumWidth(3, 40)
        self.set_in_list(in_list)

    @staticmethod
    def _size_text(e: Entry) -> str:
        if e.size_mb:
            return f"{max(1, round(e.size_mb))} MB"
        return "NT" if e.note == "NT only" else "—"

    def set_in_list(self, on: bool) -> None:
        self.add.setVisible(not on)
        self.inlist.setVisible(on)


# ---- your list ----------------------------------------------------------------------------------------

@dataclass
class ListItem:
    key: str                       # entry key, or "file:<code>" for a file
    entry: Optional[Entry]
    short: str
    name: str
    status: str = "waiting"        # waiting, saved, busy, done, failed
    note: str = ""                 # small text under the name
    fraction: Optional[float] = None
    numbering: str = "kjv"
    code: str = ""                 # code in the local library once saved
    done_text: str = "Exported ✓"


class ListItemRow(QFrame):
    remove_clicked = Signal(str)
    numbering_changed = Signal(str, str)

    def __init__(self, item: ListItem):
        super().__init__()
        self.key = item.key
        self.setObjectName("irow")
        self.setMinimumHeight(42)
        g = QGridLayout(self)
        g.setContentsMargins(10, 6, 10, 6)
        g.setHorizontalSpacing(9)
        g.setVerticalSpacing(0)
        self.chip = QLabel(item.short)
        self.chip.setObjectName("chip")
        chipcell = QWidget()
        chipcell.setFixedWidth(62)
        cl = QHBoxLayout(chipcell)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(self.chip, 0, Qt.AlignLeft | Qt.AlignVCenter)
        cl.addStretch(1)
        mid = QWidget()
        mv = QVBoxLayout(mid)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.setSpacing(2)
        self.name = QLabel(item.name)
        self.name.setObjectName("iname")
        self.name.setWordWrap(True)
        self.name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.sub = QLabel("")
        self.sub.setObjectName("isub")
        self.sub.setWordWrap(True)
        self.sub.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 1000)
        mv.addWidget(self.name)
        mv.addWidget(self.sub)
        mv.addWidget(self.bar)
        self.status = QLabel("")
        self.picker = QComboBox()
        self.picker.setFixedWidth(116)
        for key, title in NUMBERINGS.items():
            self.picker.addItem(title, key)
        self.picker.setAccessibleName(f"Verse numbering of {item.short}")
        self.picker.setToolTip("How the verses of the Psalms are numbered")
        self.picker.currentIndexChanged.connect(lambda _i: self.numbering_changed.emit(self.key, self.picker.currentData()))
        right = QWidget()
        rl = QHBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.status, 0, Qt.AlignRight | Qt.AlignVCenter)
        rl.addWidget(self.picker, 0, Qt.AlignRight | Qt.AlignVCenter)
        self.remove = QPushButton("✕")
        self.remove.setObjectName("x")
        self.remove.setFixedSize(20, 20)
        self.remove.setCursor(Qt.PointingHandCursor)
        self.remove.setToolTip("Take it out of the list")
        self.remove.setAccessibleName(f"Remove {item.short} from the list")
        self.remove.clicked.connect(lambda: self.remove_clicked.emit(self.key))
        g.addWidget(chipcell, 0, 0)
        g.addWidget(mid, 0, 1)
        g.addWidget(right, 0, 2)
        g.addWidget(self.remove, 0, 3, Qt.AlignVCenter)
        g.setColumnStretch(1, 1)
        self.apply(item, show_picker=False, can_remove=True)

    def apply(self, item: ListItem, show_picker: bool, can_remove: bool) -> None:
        self.name.setText(item.name)
        self.sub.setText(item.note)
        self.sub.setVisible(bool(item.note))
        self.sub.setObjectName("isuberr" if item.status == "failed" else "isub")
        self.sub.style().unpolish(self.sub)
        self.sub.style().polish(self.sub)
        busy = item.status == "busy"
        self.bar.setVisible(busy and item.fraction is not None)
        if item.fraction is not None:
            self.bar.setValue(int(max(0.0, min(1.0, item.fraction)) * 1000))
        pick = show_picker and item.status in ("waiting", "saved")
        self.picker.setVisible(pick)
        self.picker.blockSignals(True)
        self.picker.setCurrentIndex(max(0, self.picker.findData(item.numbering)))
        self.picker.blockSignals(False)
        text, obj = {"waiting": ("Waiting", "st_wait"), "saved": ("Saved ✓", "st_ok"), "busy": ("", "st_wait"),
                     "done": (item.done_text, "st_ok"), "failed": ("Failed", "st_fail")}[item.status]
        self.status.setText(text)
        self.status.setObjectName(obj)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.status.setVisible(not pick and bool(text))
        self.remove.setEnabled(can_remove)


# ---- the format switch -------------------------------------------------------------------------------

class Segmented(QFrame):
    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]]):
        super().__init__()
        self.setObjectName("seg")
        h = QHBoxLayout(self)
        h.setContentsMargins(3, 3, 3, 3)
        h.setSpacing(0)
        self.buttons: dict[str, QPushButton] = {}
        for key, text in options:
            b = QPushButton(text)
            b.setObjectName("segbtn")
            b.setCheckable(True)
            b.setAutoExclusive(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c=False, k=key: self.changed.emit(k))
            h.addWidget(b, 1)
            self.buttons[key] = b

    def set_value(self, key: str) -> None:
        self.buttons[key].setChecked(True)

    def set_enabled(self, on: bool) -> None:
        for b in self.buttons.values():
            b.setEnabled(on)


# ---- drop area of the "From a file" tab ------------------------------------------------------------------

class DropArea(QFrame):
    choose_clicked = Signal()
    files_dropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setObjectName("dz")
        self.setAcceptDrops(True)
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(10)
        v.addStretch(1)
        btn = QPushButton("Choose a file…")
        btn.setObjectName("importbtn")
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(self.choose_clicked)
        v.addWidget(btn, 0, Qt.AlignHCenter)
        p = QLabel("Drop a Bible file here.\nOnly add Bibles you have the right to use.")
        p.setObjectName("dzp")
        p.setAlignment(Qt.AlignCenter)
        v.addWidget(p)
        s = QLabel("Zefania · OSIS · USX · USFM · USFX · ProPresenter .rvbible · Live Presenter / getBible JSON")
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
