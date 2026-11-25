# -*- mode: python ; coding: utf-8 -*-
# Builds the Bible Importer app:  pyinstaller bible_gui.spec
#   Windows: dist/BibleImporter/BibleImporter.exe   Mac: dist/Bible Importer.app
import os
import sys

# Mac: one app for Intel and Apple chips (universal2). BI_ARCH=native builds for this computer's chip only.
MAC_ARCH = None if os.environ.get('BI_ARCH') == 'native' else 'universal2'

a = Analysis(
    ['bible_gui.py'],
    pathex=[],
    binaries=[],
    datas=[('Resources/available_bibles.json', '.'), ('Resources/metadata.xml', '.'), ('Resources/ui', 'ui'),
           ('Resources/icon', 'icon'), ('LICENSE', '.'), ('NOTICE', '.'), ('licenses', 'licenses')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'PySide6.QtWebEngineCore', 'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.Qt3DCore'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BibleImporter',
    icon='Resources/icon/icon.ico' if sys.platform == 'win32' else None,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=MAC_ARCH if sys.platform == 'darwin' else None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='BibleImporter')

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='Bible Importer.app',
        icon='Resources/icon/icon.icns',
        bundle_identifier='com.zeusgreek10.bibleimporter',
        info_plist={'NSHighResolutionCapable': True, 'CFBundleShortVersionString': '1.0.0'},
    )
