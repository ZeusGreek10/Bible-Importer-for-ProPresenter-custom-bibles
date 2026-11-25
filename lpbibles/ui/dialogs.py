"""The ? box: how to add the files to ProPresenter on Windows by hand."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTextBrowser,
                               QVBoxLayout, QWidget)

from .. import export_pp
from . import theme

BODY = f"""
<style>
  body {{ color:{theme.TEXT2}; font-size:12.2px; }}
  h3 {{ color:{theme.DIM}; font-size:10px; letter-spacing:1px; margin:10px 0 2px 0; }}
  li {{ margin-bottom:5px; }}
  b {{ color:#ffffff; }}
  code {{ background-color:{theme.FIELD}; color:{theme.LICENSED}; font-family:Consolas,Menlo,monospace; font-size:11.5px; }}
</style>
<p>Bible Importer saves each Bible as a <code>.rvbible</code> file. ProPresenter for Windows cannot open that file by
itself, so there are a few steps to do yourself. (On Mac the app can add the files for you.)</p>
<h3>GOOD TO KNOW FIRST</h3>
<ul>
<li>ProPresenter on Windows only lists Bibles whose <b>name code</b> it already knows. A new Bible has to take the
place of one of ProPresenter's own free Bibles.</li>
<li>The free Bible you give up <b>can no longer be used</b>. Each free Bible can be given up once, so two new Bibles
need two different ones.</li>
<li>A damaged Bible simply does not appear in ProPresenter's list.</li>
<li>Close ProPresenter first, and keep a copy of the <code>Bibles</code> folder as a backup.</li>
<li>The folder is hidden. Use the button below, or type <code>%PROGRAMDATA%</code> in the Explorer address bar.</li>
</ul>
<h3>STEPS</h3>
<ol>
<li>Close ProPresenter. Copy <code>C:\\ProgramData\\RenewedVision\\ProPresenter\\Bibles</code> somewhere safe.</li>
<li>Make a copy of your <code>.rvbible</code> file, rename the copy to <code>.zip</code> and extract it into a new folder.
Give the folder any new unique name (for example <code>5b1f0c2e-7a4d-4c1b-9d3e-0a6f8e2c4b19</code>) and move it into the
<code>Bibles</code> folder.</li>
<li>In your new folder, open <code>rvmetadata.xml</code> in Notepad. Replace the text between
<code>&lt;abbreviation&gt;</code> and <code>&lt;/abbreviation&gt;</code> with the <b>name code</b> of the free Bible you
are giving up.</li>
<li>Open <code>BibleData.proPref</code> in Notepad and add one entry to the list:
<code>"folder-name|NAMECODE|Your Bible name|1"</code>.</li>
<li>Open ProPresenter. Your Bible is in the Bible list under its own name.</li>
</ol>
"""

NOTE = ("These steps come from the notes of the original tool. They have not been tested with every ProPresenter "
        "version. Advanced: you can also put the .rvbible file in Bibles\\sideload, but ProPresenter may not list it.")


class ExplainDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Adding Bibles to ProPresenter on Windows")
        self.setModal(True)
        self.resize(820, 640)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        head = QFrame()
        head.setObjectName("dlghead")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(20, 12, 16, 12)
        title = QLabel("Adding Bibles to ProPresenter on Windows")
        title.setObjectName("dlgtitle")
        hl.addWidget(title)
        hl.addStretch(1)
        x = QPushButton("✕")
        x.setObjectName("x")
        x.setFixedSize(26, 26)
        x.setAccessibleName("Close")
        x.clicked.connect(self.accept)
        hl.addWidget(x)
        v.addWidget(head)

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(20, 10, 20, 10)
        bl.setSpacing(10)
        text = QTextBrowser()
        text.setOpenLinks(False)
        text.setHtml(BODY)
        bl.addWidget(text, 1)
        warn = QFrame()
        warn.setObjectName("warnbox")
        wl = QVBoxLayout(warn)
        wl.setContentsMargins(12, 9, 12, 9)
        note = QLabel(NOTE)
        note.setWordWrap(True)
        wl.addWidget(note)
        bl.addWidget(warn)
        v.addWidget(body, 1)

        foot = QFrame()
        foot.setObjectName("dlgfoot")
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(20, 12, 20, 14)
        fl.setSpacing(10)
        self.open_btn = QPushButton("Open the Bibles folder")
        self.open_btn.setObjectName("btn")
        self.open_btn.clicked.connect(self.open_folder)
        self.copy_btn = QPushButton("Copy the list of name codes")
        self.copy_btn.setObjectName("btn")
        self.copy_btn.clicked.connect(self.copy_codes)
        close = QPushButton("Close")
        close.setObjectName("go")
        close.setMinimumWidth(110)
        close.clicked.connect(self.accept)
        fl.addWidget(self.open_btn)
        fl.addWidget(self.copy_btn)
        fl.addStretch(1)
        fl.addWidget(close)
        v.addWidget(foot)

    def open_folder(self) -> None:
        folder = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "RenewedVision" / "ProPresenter" / "Bibles"
        if sys.platform != "win32" or not folder.exists():
            QMessageBox.information(self, "Bibles folder",
                                    f"The folder was not found on this computer.\nOn the Windows computer with ProPresenter it is:\n"
                                    f"{export_pp.windows_bibles_folder_text()}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def copy_codes(self) -> None:
        QGuiApplication.clipboard().setText(export_pp.free_bible_code_list())
        self.copy_btn.setText("Copied ✓")
