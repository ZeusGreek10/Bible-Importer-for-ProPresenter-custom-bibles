"""Bible Importer: a window to add Bibles (Mac and Windows). Start with:  python bible_gui.py

    python bible_gui.py --self-test     opens the window for a moment and quits (used by the build check)
"""

import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from lpbibles import paths
from lpbibles.backend import Backend
from lpbibles.library import Library
from lpbibles.ui import theme
from lpbibles.ui.main_window import MainWindow

BUNDLED = ("metadata.xml", "available_bibles.json", os.path.join("ui", "chevron-down.svg"), os.path.join("icon", "icon.png"))


def pipeline_check() -> None:
    """Writes a small Bible for both programs and reads it back (checks lxml and the bundled files)."""
    import tempfile
    from pathlib import Path

    from lpbibles import export_lp, export_pp, importers
    from lpbibles.model import ParsedBible

    pb = ParsedBible(name="Check Bible", short="CHK", language="English", lang_code="eng")
    for b in range(1, 67):
        pb.add(b, 1, 1, f"Book {b}.")
    with tempfile.TemporaryDirectory() as tmp:
        for out in (export_lp.write(pb, Path(tmp) / "c.json"), export_pp.write_rvbible(pb, Path(tmp) / "c.rvbible")):
            back = importers.read_files([out])
            assert back.verse_count == 66 and back.name == "Check Bible", out.name


def main() -> int:
    self_test = "--self-test" in sys.argv
    if self_test:
        missing = [f for f in BUNDLED if not os.path.exists(paths.resource_path(f))]
        if missing:
            print("self-test FAILED, missing files:", ", ".join(missing))
            return 1
        try:
            pipeline_check()
        except Exception as e:
            print("self-test FAILED:", type(e).__name__, e)
            return 1
    app = QApplication([a for a in sys.argv if a != "--self-test"])
    app.setApplicationName("Bible Importer")
    app.setWindowIcon(QIcon(paths.resource_path(os.path.join("icon", "icon.png"))))
    app.setStyleSheet(theme.stylesheet())
    window = MainWindow(Library(paths.data_dir()), Backend(paths.cache_dir()), list_path=paths.data_dir() / "list.json")
    window.show()
    if self_test:
        QTimer.singleShot(2500, app.quit)
        code = app.exec()
        print("self-test ok" if code == 0 else "self-test FAILED")
        return code
    code = app.exec()
    if window.runner.pool.activeThreadCount() > 0:
        # A download is still waiting for a slow server: leave at once instead of hanging.
        # Nothing is lost: Bibles are written to a temporary file and moved into place only when complete.
        sys.stdout and sys.stdout.flush()
        os._exit(code)
    return code


if __name__ == "__main__":
    sys.exit(main())
