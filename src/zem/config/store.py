"""Single writer for the JSON config file.

Every code path that modifies ``config.json`` (`config set`, theme
switching, plugin default sync) goes through :func:`update_raw`, which
does a locked read-modify-write and an atomic replace, so concurrent
shells cannot interleave partial documents or clobber each other's keys.
"""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from typing import Any, Callable, Iterator


def _lock_path(path: str) -> str:
    return path + ".lock"


@contextmanager
def _locked(path: str) -> Iterator[None]:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(_lock_path(path), "a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def read_raw(path: str) -> dict[str, Any]:
    """The on-disk document as a dict (``{}`` when missing or empty)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return {}
    if not text.strip():
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top-level JSON value must be an object")
    return data


def write_raw(path: str, data: dict[str, Any]) -> None:
    """Atomically replace ``path`` with ``data`` (temp file + rename)."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".config-", suffix=".json.tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def update_raw(path: str, mutate: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    """Read, apply ``mutate`` in place, write back — all under a lock.

    Returns the document that was written.
    """
    with _locked(path):
        data = read_raw(path)
        mutate(data)
        write_raw(path, data)
        return data
