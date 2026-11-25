"""Colours and the style sheet. Values are the ones in the approved Live Presenter renderings
(specs/add-bibles/*.html), so this window looks like the Add Bibles window of Live Presenter."""

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
AMBER_BG = "#2a2417"
AMBER_LINE = "#5a4a24"
AMBER_TEXT = "#e8d9b0"
LICENSED = "#e8c46a"
WARN = "#e8c46a"
ERROR = "#FF8A6E"
FAILED = "#FF5E5E"

FONT_STACK = '"Inter", "Segoe UI", "SF Pro Text", "Helvetica Neue", "Helvetica", "Arial", sans-serif'

MESSAGE_COLORS = {"ok": GREEN, "warn": WARN, "error": ERROR, "dim": DIM}


def stylesheet() -> str:
    chevron = resource_path("ui/chevron-down.svg").replace("\\", "/")
    return f"""
* {{ font-family: {FONT_STACK}; font-size: 12px; color: {TEXT}; }}
QMainWindow, QDialog {{ background: {SHEET}; }}
QToolTip {{ background: {PANEL2}; color: {TEXT}; border: 1px solid {LINE}; padding: 4px 6px; }}

QFrame#header {{ background: {PANEL}; border-bottom: 1px solid {LINE2}; }}
QLabel#title {{ font-size: 15px; font-weight: 700; }}

QFrame#tabs {{ background: {PANEL}; border-bottom: 1px solid {LINE}; }}
QPushButton#tab {{ background: transparent; border: none; border-bottom: 2px solid transparent; color: {DIM};
    font-size: 13px; font-weight: 600; padding: 0 0 9px 0; margin: 0; }}
QPushButton#tab:checked {{ color: #ffffff; border-bottom: 2px solid {ORANGE}; }}
QPushButton#tab:hover:!checked {{ color: {TEXT2}; }}

QFrame#amber {{ background: {AMBER_BG}; border-bottom: 1px solid {AMBER_LINE}; }}
QFrame#amber QLabel {{ color: {AMBER_TEXT}; font-size: 11.5px; }}

QFrame#lc {{ background: {LEFT}; border-right: 1px solid {LINE2}; }}
QFrame#rc {{ background: {SHEET}; }}

QLineEdit#field {{ background: {FIELD}; border: 1px solid {LINE}; border-radius: 7px; padding: 7px 10px; color: {TEXT};
    font-size: 12px; selection-background-color: {ORANGE}; selection-color: #111111; }}
QLineEdit#field:focus {{ border: 1px solid {ORANGE}; }}

QListWidget#langs {{ background: transparent; border: none; outline: none; }}
QListWidget#langs QScrollBar:vertical, QScrollArea QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {LINE}; border-radius: 4px; min-height: 24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

QScrollArea {{ background: transparent; border: none; }}
QWidget#scrollbody {{ background: transparent; }}
QFrame#lst {{ background: {PANEL}; border: 1px solid {LINE2}; border-radius: 10px; }}
QFrame#brow {{ background: transparent; border: none; border-bottom: 1px solid {LINE2}; }}
QFrame#brow[last="true"] {{ border-bottom: none; }}
QFrame#brow QLabel#name {{ font-size: 12.5px; font-weight: 700; color: #ffffff; }}
QFrame#brow QLabel#short {{ color: {DIM}; font-weight: 700; font-size: 11px; }}
QFrame#brow QLabel#size {{ color: {DIM}; font-size: 11px; }}
QLabel#tagfree {{ background: rgba(52,199,89,0.13); color: {GREEN}; border: 1px solid rgba(52,199,89,0.33);
    border-radius: 4px; font-size: 10px; font-weight: 800; padding: 2px 7px; }}
QLabel#taglic {{ background: {AMBER_BG}; color: {LICENSED}; border: 1px solid {AMBER_LINE};
    border-radius: 4px; font-size: 10px; font-weight: 800; padding: 2px 7px; }}
QLabel#installed {{ color: {GREEN}; font-weight: 800; font-size: 11.5px; }}
QLabel#failed {{ color: {FAILED}; font-size: 11px; }}
QLabel#progresstext {{ color: {TEXT2}; font-size: 10px; }}

QPushButton#download, QPushButton#retry {{ background: {ORANGE}; color: #111111; font-weight: 800; font-size: 11px;
    border: none; border-radius: 7px; padding: 4px 14px; }}
QPushButton#download:hover, QPushButton#retry:hover {{ background: #ff9d40; }}
QPushButton#download:pressed, QPushButton#retry:pressed {{ background: #e07a12; }}
QPushButton#cancel {{ background: {PANEL2}; color: {TEXT}; font-weight: 700; font-size: 11px; border: none;
    border-radius: 7px; padding: 5px 12px; }}
QPushButton#cancelx {{ background: {PANEL2}; color: {DIM}; font-size: 10px; border: none; border-radius: 5px; }}
QPushButton#cancel:hover, QPushButton#cancelx:hover {{ background: {LINE}; }}
QProgressBar {{ background: {LINE}; border: none; border-radius: 2px; max-height: 4px; min-height: 4px; }}
QProgressBar::chunk {{ background: {ORANGE}; border-radius: 2px; }}

QLabel#message {{ font-size: 11.5px; font-weight: 600; }}

QFrame#bb {{ background: {PANEL}; border-top: 1px solid {LINE}; }}
QLabel#lab {{ font-size: 10px; font-weight: 800; color: {DIM}; letter-spacing: 1px; }}
QFrame#irow {{ background: transparent; border: none; border-bottom: 1px solid {LINE2}; }}
QFrame#irow[last="true"] {{ border-bottom: none; }}
QLabel#chip {{ background: {PANEL2}; color: {TEXT2}; font-size: 11px; font-weight: 700; border-radius: 5px; padding: 3px 9px; }}
QLabel#iname {{ font-size: 12px; }}
QComboBox {{ background: {FIELD}; border: 1px solid {LINE}; border-radius: 6px; padding: 4px 9px; font-size: 11.5px; font-weight: 600; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: url({chevron}); width: 10px; height: 6px; }}
QComboBox QAbstractItemView {{ background: {FIELD}; border: 1px solid {LINE}; selection-background-color: {PANEL2};
    selection-color: {TEXT}; outline: none; }}
QPushButton#small, QToolButton#small {{ background: {PANEL2}; color: {TEXT}; border: none; border-radius: 6px;
    padding: 4px 8px; font-weight: 700; font-size: 11px; }}
QPushButton#small:hover, QToolButton#small:hover {{ background: {LINE}; }}
QToolButton#small::menu-indicator {{ image: none; width: 0; }}
QMenu {{ background: {PANEL}; border: 1px solid {LINE}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 5px; }}
QMenu::item:selected {{ background: {PANEL2}; }}
QMenu::item:disabled {{ color: {DIM}; }}

QFrame#dz {{ background: transparent; border: 2px dashed {LINE}; border-radius: 12px; }}
QFrame#dz[hover="true"] {{ border: 2px dashed {ORANGE}; background: rgba(255,138,30,0.06); }}
QPushButton#importbtn {{ background: {PANEL2}; color: {TEXT}; border: none; border-radius: 7px; padding: 6px 16px;
    font-weight: 700; font-size: 12px; }}
QPushButton#importbtn:hover {{ background: {LINE}; }}
QLabel#dzp {{ color: {TEXT2}; font-size: 11.5px; }}
QLabel#dzsmall {{ color: {DIM}; font-size: 10px; }}

QDialog QLabel#dlgtitle {{ font-size: 15px; font-weight: 700; }}
QDialog QLabel#dlgtext {{ color: {TEXT2}; font-size: 12px; }}
QDialog QLabel#dlgwarn {{ color: {WARN}; font-size: 11.5px; }}
QRadioButton {{ spacing: 8px; font-size: 12px; }}
QPushButton#primary {{ background: {ORANGE}; color: #111111; font-weight: 800; border: none; border-radius: 7px; padding: 7px 18px; }}
QPushButton#secondary {{ background: {PANEL2}; color: {TEXT}; font-weight: 700; border: none; border-radius: 7px; padding: 7px 18px; }}
"""
