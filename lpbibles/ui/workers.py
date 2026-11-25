"""Runs downloads and file reading in the background so the window never freezes."""

from __future__ import annotations

import threading
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from ..model import BibleError
from ..netutil import Cancelled, NetworkError


class _Job(QRunnable):
    def __init__(self, runner: "Runner", key: str, fn: Callable, cancel: threading.Event):
        super().__init__()
        self.runner, self.key, self.fn, self.cancel = runner, key, fn, cancel

    def run(self) -> None:
        r = self.runner
        try:
            result = self.fn(self.cancel, lambda d, t, eta=None: r.progress.emit(self.key, int(d), int(t), eta))
        except Cancelled:
            r.cancelled.emit(self.key)
        except NetworkError as e:
            r.failed.emit(self.key, str(e), True)
        except BibleError as e:
            r.failed.emit(self.key, str(e), False)
        except Exception as e:  # never let a thread die silently
            r.failed.emit(self.key, f"Something went wrong ({type(e).__name__}: {e}).", False)
        else:
            if self.cancel.is_set():
                r.cancelled.emit(self.key)
            else:
                r.done.emit(self.key, result)


class Runner(QObject):
    """start(key, fn): fn(cancel_event, progress) runs in a thread; the signals arrive in the window's thread."""
    done = Signal(str, object)
    failed = Signal(str, str, bool)   # key, message, True when it was a network problem
    cancelled = Signal(str)
    progress = Signal(str, int, int, object)

    def __init__(self, threads: int = 4):
        super().__init__()
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(threads)
        self.events: dict[str, threading.Event] = {}

    def start(self, key: str, fn: Callable) -> threading.Event:
        ev = threading.Event()
        self.events[key] = ev
        self.pool.start(_Job(self, key, fn, ev))
        return ev

    def cancel(self, key: str) -> None:
        ev = self.events.get(key)
        if ev:
            ev.set()

    def finished(self, key: str) -> None:
        self.events.pop(key, None)

    def cancel_all(self) -> None:
        for ev in list(self.events.values()):
            ev.set()

    def wait(self, ms: int = 4000) -> bool:
        return self.pool.waitForDone(ms)
