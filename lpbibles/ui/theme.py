"""Colours and the style sheet. Values come from the approved renderings (design/*.html)."""

from __future__ import annotations

from ..paths import resource_path

BG = "#17181B"
SHEET = "#1d1e22"
PANEL = "#202226"
PANEL2 = "#2B2E34"
LEFT = "#1a1b1e"
FIELD = "#141518"
LINE = "#3A3D44"
LINE2 = "#2B2E34"
TEXT = "#E8E9EC"
TEXT2 = "#C9CCD2"
DIM = "#8C9099"
ORANGE = "#FF8A1E"
GREEN = "#34C759"
DONE_BG = "#173322"
AMBER_BG = "#2a2417"
AMBER_LINE = "#5a4a24"
AMBER_TEXT = "#e8d9b0"
LICENSED = "#e8c46a"
WARN = "#e8c46a"
ERROR = "#FF8A6E"

FONT_STACK = '"Inter", "Segoe UI", "SF Pro Text", "Helvetica Neue", "Helvetica", "Arial", sans-serif'

MESSAGE_COLORS = {"ok": GREEN, "warn": WARN, "error": ERROR, "dim": DIM}


def stylesheet() -> str:
    chevron = resource_path("ui/chevron-down.svg").replace("\\", "/")
    return f"""
* {{ font-family: {FONT_STACK}; font-size: 12px; color: {TEXT}; }}
QMainWindow, QDialog {{ background: {SHEET}; }}
QToolTip {{ background: {PANEL2}; color: {TEXT}; border: 1px solid {LINE}; padding: 4px 6px; }}

QFrame#header {{ background: {PANEL}; border-bottom: 1px solid {LINE2}; }}
QLabel#title {{ font-size: 16px; font-weight: 700; }}
QLabel#subtitle {{ color: {DIM}; font-size: 12px; }}

QFrame#tabs {{ background: {PANEL}; border-bottom: 1px solid {LINE}; }}
QPushButton#tab {{ background: transparent; border: none; border-bottom: 2px solid transparent; color: {DIM};
    font-size: 13px; font-weight: 600; padding: 0 0 10px 0; margin: 0; }}
QPushButton#tab:checked {{ color: #ffffff; border-bottom: 2px solid {ORANGE}; }}
QPushButton#tab:hover:!checked {{ color: {TEXT2}; }}

QLabel#stepnum {{ background: {ORANGE}; color: #111111; border-radius: 9px; font-size: 10px; font-weight: 800; }}
QLabel#steptext {{ color: {DIM}; font-size: 10px; font-weight: 800; letter-spacing: 1px; }}
QLabel#stepright {{ color: {DIM}; font-size: 11px; font-weight: 600; }}

QFrame#amber {{ background: {AMBER_BG}; border-bottom: 1px solid {AMBER_LINE}; }}
QFrame#amber QLabel {{ color: {AMBER_TEXT}; font-size: 11.5px; }}

QFrame#lc {{ background: {LEFT}; border-right: 1px solid {LINE2}; }}
QFrame#rc {{ background: {SHEET}; }}

QLineEdit#field {{ background: {FIELD}; border: 1px solid {LINE}; border-radius: 7px; padding: 7px 10px; color: {TEXT};
    font-size: 12px; selection-background-color: {ORANGE}; selection-color: #111111; }}
QLineEdit#field:focus {{ border: 1px solid {ORANGE}; }}

QListWidget#langs {{ background: transparent; border: none; outline: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {LINE}; border-radius: 4px; min-height: 24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

QScrollArea {{ background: transparent; border: none; }}
QWidget#scrollbody {{ background: transparent; }}
QFrame#lst {{ background: {PANEL}; border: 1px solid {LINE2}; border-radius: 10px; }}
QFrame#brow {{ background: transparent; border: none; border-bottom: 1px solid {LINE2}; }}
QFrame#brow[last="true"] {{ border-bottom: none; }}
QFrame#brow QLabel#name {{ font-size: 12.5px; font-weight: 700; color: #ffffff; }}
QFrame#brow QLabel#saved {{ color: {DIM}; font-size: 9.5px; font-weight: 600; }}
QFrame#brow QLabel#short {{ color: {DIM}; font-weight: 700; font-size: 11px; }}
QFrame#brow QLabel#size {{ color: {DIM}; font-size: 11px; }}
QLabel#tagfree {{ background: rgba(52,199,89,0.13); color: {GREEN}; border: 1px solid rgba(52,199,89,0.33);
    border-radius: 4px; font-size: 10px; font-weight: 800; padding: 2px 7px; }}
QLabel#taglic {{ background: {AMBER_BG}; color: {LICENSED}; border: 1px solid {AMBER_LINE};
    border-radius: 4px; font-size: 10px; font-weight: 800; padding: 2px 7px; }}
QPushButton#add {{ background: transparent; color: {ORANGE}; font-weight: 800; font-size: 11px;
    border: 1.5px solid {ORANGE}; border-radius: 7px; padding: 3px 12px; }}
QPushButton#add:hover {{ background: rgba(255,138,30,0.14); }}
QPushButton#add:pressed {{ background: rgba(255,138,30,0.28); }}
QLabel#inlist {{ color: {DIM}; font-weight: 700; font-size: 11.5px; }}
QLabel#message {{ font-size: 11.5px; font-weight: 600; }}

QFrame#panel {{ background: {PANEL}; border-left: 1px solid {LINE}; }}
QFrame#items {{ background: {BG}; border: 1px solid {LINE2}; border-radius: 10px; }}
QFrame#irow {{ background: transparent; border: none; border-bottom: 1px solid {LINE2}; }}
QFrame#irow[last="true"] {{ border-bottom: none; }}
QLabel#chip {{ background: {PANEL2}; color: {TEXT2}; font-size: 11px; font-weight: 700; border-radius: 5px; padding: 3px 8px; }}
QLabel#iname {{ font-size: 12px; }}
QLabel#isub {{ color: {DIM}; font-size: 10.5px; }}
QLabel#isuberr {{ color: {ERROR}; font-size: 10.5px; }}
QLabel#st_ok {{ color: {GREEN}; font-weight: 700; font-size: 11px; }}
QLabel#st_wait {{ color: {DIM}; font-size: 11px; }}
QLabel#st_fail {{ color: {ERROR}; font-weight: 700; font-size: 11px; }}
QPushButton#x {{ background: {PANEL2}; color: {DIM}; border: none; border-radius: 5px; font-size: 10px; }}
QPushButton#x:hover {{ background: {LINE}; color: {TEXT}; }}
QPushButton#x:disabled {{ color: {LINE}; }}
QPushButton#cleanup {{ background: {PANEL2}; color: {TEXT2}; border: none; border-radius: 6px; font-size: 11px; font-weight: 700; padding: 6px 12px; }}
QPushButton#cleanup:hover {{ background: #4a2a2a; color: {ERROR}; }}
QPushButton#cleanup:disabled {{ background: {PANEL2}; color: {LINE}; }}
QProgressBar {{ background: {LINE}; border: none; border-radius: 2px; max-height: 4px; min-height: 4px; }}
QProgressBar::chunk {{ background: {ORANGE}; border-radius: 2px; }}

QFrame#seg {{ background: {PANEL2}; border-radius: 9px; }}
QPushButton#segbtn {{ background: transparent; color: {DIM}; font-weight: 700; font-size: 13px; border: none;
    border-radius: 7px; padding: 9px 0; }}
QPushButton#segbtn:checked {{ background: {ORANGE}; color: #111111; }}
QPushButton#segbtn:disabled {{ color: {LINE}; }}
QLabel#hint {{ color: {DIM}; font-size: 11.5px; }}
QLabel#pathbox {{ background: {FIELD}; border: 1px solid {LINE}; border-radius: 6px; padding: 6px 9px; color: {TEXT2}; font-size: 11.5px; }}
QPushButton#btn {{ background: {PANEL2}; color: {TEXT}; border: none; border-radius: 6px; padding: 6px 12px;
    font-weight: 700; font-size: 11.5px; }}
QPushButton#btn:hover {{ background: {LINE}; }}
QPushButton#btn:disabled {{ color: {DIM}; }}
QPushButton#qmark {{ background: {PANEL2}; border: 1.5px solid #5a5e68; border-radius: 11px; color: {TEXT}; font-weight: 800; font-size: 13px; }}
QPushButton#qmark:hover {{ border-color: {ORANGE}; }}
QPushButton#helplink {{ background: transparent; border: none; color: {TEXT}; font-weight: 600; font-size: 12px; text-align: left; padding: 0; }}
QPushButton#helplink:hover {{ color: {ORANGE}; }}
QPushButton#go {{ background: {ORANGE}; color: #111111; border: none; border-radius: 9px; padding: 13px 0;
    font-weight: 800; font-size: 14px; }}
QPushButton#go:hover {{ background: #ff9d40; }}
QPushButton#go:pressed {{ background: #e07a12; }}
QPushButton#go:disabled {{ background: {PANEL2}; color: {DIM}; }}
QPushButton#go2 {{ background: {PANEL2}; color: {TEXT}; border: none; border-radius: 9px; padding: 13px 16px;
    font-weight: 700; font-size: 13px; }}
QPushButton#go2:hover {{ background: {LINE}; }}
QPushButton#go2:disabled {{ color: {DIM}; }}

QFrame#done {{ background: {DONE_BG}; border: 1px solid rgba(52,199,89,0.33); border-radius: 10px; }}
QFrame#done QLabel#donehead {{ color: {GREEN}; font-size: 13px; font-weight: 700; }}
QFrame#done QLabel#donetext {{ color: {TEXT2}; font-size: 11.5px; }}

QComboBox {{ background: {FIELD}; border: 1px solid {LINE}; border-radius: 6px; padding: 3px 8px; font-size: 10.5px; font-weight: 600; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox::down-arrow {{ image: url({chevron}); width: 10px; height: 6px; }}
QComboBox QAbstractItemView {{ background: {FIELD}; border: 1px solid {LINE}; selection-background-color: {PANEL2};
    selection-color: {TEXT}; outline: none; }}

QFrame#dz {{ background: transparent; border: 2px dashed {LINE}; border-radius: 14px; }}
QFrame#dz[hover="true"] {{ border: 2px dashed {ORANGE}; background: rgba(255,138,30,0.06); }}
QPushButton#importbtn {{ background: {PANEL2}; color: {TEXT}; border: none; border-radius: 8px; padding: 9px 20px;
    font-weight: 700; font-size: 13px; }}
QPushButton#importbtn:hover {{ background: {LINE}; }}
QLabel#dzp {{ color: {TEXT2}; font-size: 12.5px; }}
QLabel#dzsmall {{ color: {DIM}; font-size: 11px; }}

QDialog QLabel#dlgtitle {{ font-size: 16px; font-weight: 700; }}
QFrame#dlghead {{ background: {PANEL}; border-bottom: 1px solid {LINE2}; }}
QFrame#dlgfoot {{ background: {PANEL}; border-top: 1px solid {LINE2}; }}
QFrame#warnbox {{ background: {AMBER_BG}; border: 1px solid {AMBER_LINE}; border-radius: 10px; }}
QFrame#warnbox QLabel {{ color: {AMBER_TEXT}; font-size: 11.5px; }}
QTextBrowser {{ background: transparent; border: none; }}
QMenu {{ background: {PANEL}; border: 1px solid {LINE}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 5px; }}
QMenu::item:selected {{ background: {PANEL2}; }}
"""
