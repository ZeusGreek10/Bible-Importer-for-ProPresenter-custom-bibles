"""Network helper: timeouts, retries and a Cancel that works between requests."""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

import requests

USER_AGENT = "BibleImporter/1.0 (+https://github.com/ZeusGreek10/LivePresenter-custom-bibles)"


class Cancelled(Exception):
    """The volunteer pressed Cancel."""


class NetworkError(Exception):
    """The server did not answer, or answered with something we cannot use."""

    def __init__(self, message: str, offline: bool = False):
        super().__init__(message)
        self.offline = offline


def check(cancel: Optional[threading.Event]) -> None:
    if cancel is not None and cancel.is_set():
        raise Cancelled()


def sleep(seconds: float, cancel: Optional[threading.Event]) -> None:
    """Sleeps but wakes up at once when Cancel is pressed."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        check(cancel)
        time.sleep(min(0.2, max(0.0, end - time.monotonic())))


def get(url: str, *, headers: Optional[dict] = None, timeout: float = 30, retries: int = 3,
        cancel: Optional[threading.Event] = None, params: Optional[dict] = None,
        session: Optional[requests.Session] = None, backoff: float = 2.0) -> requests.Response:
    """GET with retries. Raises NetworkError (readable) or Cancelled."""
    h = {"User-Agent": USER_AGENT}
    h.update(headers or {})
    getter = session.get if session is not None else requests.get
    last: Optional[Exception] = None
    for attempt in range(max(1, retries)):
        check(cancel)
        try:
            r = getter(url, headers=h, timeout=timeout, params=params)
            if r.status_code == 200:
                return r
            last = NetworkError(f"The server answered {r.status_code}.")
            if r.status_code in (400, 401, 403, 404):
                break  # trying again will not help
        except requests.exceptions.ConnectionError as e:
            last = NetworkError("No internet connection.", offline=True)
            last.__cause__ = e
        except requests.exceptions.RequestException as e:
            last = NetworkError("The server did not answer in time.")
            last.__cause__ = e
        if attempt + 1 < retries:
            sleep(backoff * (attempt + 1), cancel)
    assert last is not None
    raise last


def download(url: str, *, headers: Optional[dict] = None, timeout: float = 30,
             cancel: Optional[threading.Event] = None,
             progress: Optional[Callable[[int, int], None]] = None) -> bytes:
    """Downloads a big file in pieces, reporting (bytes so far, total or 0)."""
    h = {"User-Agent": USER_AGENT}
    h.update(headers or {})
    try:
        with requests.get(url, headers=h, timeout=timeout, stream=True) as r:
            if r.status_code != 200:
                raise NetworkError(f"The server answered {r.status_code}.")
            total = int(r.headers.get("Content-Length") or 0)
            chunks: list[bytes] = []
            done = 0
            for chunk in r.iter_content(65536):
                check(cancel)
                chunks.append(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
            return b"".join(chunks)
    except requests.exceptions.ConnectionError as e:
        err = NetworkError("No internet connection.", offline=True)
        err.__cause__ = e
        raise err
    except requests.exceptions.RequestException as e:
        err = NetworkError("The download was interrupted.")
        err.__cause__ = e
        raise err
