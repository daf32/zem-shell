"""Isolation for hint tests: no real subprocesses, no leaked providers."""

import subprocess

import pytest

from zem.hints import providers, sources


@pytest.fixture(autouse=True)
def _clear_source_cache():
    sources.clear_cache()
    yield
    sources.clear_cache()


@pytest.fixture(autouse=True)
def _isolate_providers():
    """Snapshot/restore the process-wide provider registry."""
    saved = dict(providers.PROVIDERS._providers)
    yield
    providers.PROVIDERS._providers.clear()
    providers.PROVIDERS._providers.update(saved)


@pytest.fixture(autouse=True)
def _no_real_subprocess(monkeypatch, request):
    """Hint tests never shell out for real.

    Results would depend on the machine, on whether tmp_path happens to sit
    inside a git repo, and on whether docker is installed.
    """
    if "allow_subprocess" in request.keywords:
        return

    def _boom(*args, **kwargs):
        raise AssertionError(f"unexpected subprocess in a hints test: {args!r}")

    monkeypatch.setattr(sources.subprocess, "run", _boom)


@pytest.fixture
def fake_run(monkeypatch):
    """Replace subprocess.run with a scripted, call-counting stub."""
    calls = []

    def _install(stdout="", returncode=0, exc=None):
        def _run(argv, **kwargs):
            calls.append((tuple(argv), kwargs))
            if exc is not None:
                raise exc
            return subprocess.CompletedProcess(argv, returncode, stdout, "")

        monkeypatch.setattr(sources.subprocess, "run", _run)
        return calls

    _install.calls = calls
    return _install


@pytest.fixture(autouse=True)
def _no_hint_subprocess():
    """Undo the suite-wide stub: these tests drive sources on purpose."""
    yield
