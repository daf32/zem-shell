"""Bytes that are not valid UTF-8 pass through the shell unharmed."""

import os
import subprocess
import sys

import pytest

from zem.core.executor import STREAM_ERRORS, managed_fd
from zem.main import _configure_streams

#: Three bytes no UTF-8 decoder accepts, then something readable.
RAW = b"\xff\xfe\xfd tail\n"


# -- the descriptors a builtin is handed ----------------------------------------

def test_managed_fd_reads_undecodable_bytes(tmp_path):
    path = tmp_path / "raw.bin"
    path.write_bytes(RAW)
    fd = os.open(path, os.O_RDONLY)
    with managed_fd(fd, "r") as handle:
        text = handle.read()
    assert text.encode("utf-8", STREAM_ERRORS) == RAW


def test_managed_fd_writes_them_back_unchanged(tmp_path):
    path = tmp_path / "out.bin"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT)
    with managed_fd(fd, "w") as handle:
        handle.write(RAW.decode("utf-8", STREAM_ERRORS))
    assert path.read_bytes() == RAW


def test_managed_fd_closes_the_descriptor_it_was_given(tmp_path):
    path = tmp_path / "f"
    path.write_text("x")
    fd = os.open(path, os.O_RDONLY)
    with managed_fd(fd, "r"):
        pass
    with pytest.raises(OSError):
        os.fstat(fd)  # closed, as promised


def test_a_descriptor_that_cannot_be_wrapped_is_still_closed(tmp_path, monkeypatch):
    """`os.fdopen` leaves the fd open when it fails; the leak was ours."""
    path = tmp_path / "f"
    path.write_text("x")
    fd = os.open(path, os.O_RDONLY)

    def boom(*a, **k):
        raise OSError("nope")

    monkeypatch.setattr(os, "fdopen", boom)
    with pytest.raises(OSError):
        with managed_fd(fd, "r"):
            pass
    with pytest.raises(OSError):
        os.fstat(fd)


# -- the shell's own streams ------------------------------------------------------

def test_configure_streams_asks_for_surrogateescape(monkeypatch):
    asked = []

    class Stream:
        def reconfigure(self, **kwargs):
            asked.append(kwargs)

    monkeypatch.setattr(sys, "stdin", Stream())
    monkeypatch.setattr(sys, "stdout", Stream())
    _configure_streams()
    assert asked == [{"errors": "surrogateescape"}] * 2


def test_configure_streams_survives_a_stream_it_cannot_touch(monkeypatch):
    class Captured:
        pass  # no reconfigure, as under pytest's capture

    monkeypatch.setattr(sys, "stdout", Captured())
    _configure_streams()  # must not raise


# -- end to end, with a locale that would otherwise refuse the bytes -------------

def test_raw_bytes_survive_a_round_trip(tmp_path):
    """In a subprocess, because it is the process's own stdio under test."""
    source = tmp_path / "raw.bin"
    source.write_bytes(RAW)
    line = f"read X < {source}; echo $X"
    code = f"from zem.main import main; raise SystemExit(main(['-c', {line!r}]))"
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        env={
            "PATH": "/usr/bin:/bin",
            "ZEM_CONFIG_PATH": str(tmp_path / "config.json"),
            "HOME": str(tmp_path),
            # Strict stdio is what a machine with an ordinary locale gives
            # us, and what used to turn this into a decoding error.
            "PYTHONIOENCODING": "utf-8:strict",
        },
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == RAW
