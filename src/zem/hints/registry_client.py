"""Fetching hint specs from the spec registry.

Specs for niche tools do not ship in the wheel: they live in a registry
that is updated without releasing Zem. This is the client for it —
`zem hints search|install|update|remove`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

from zem.hints.spec import SpecError, parse_spec

log = logging.getLogger(__name__)

DEFAULT_REGISTRY_URL = "https://raw.githubusercontent.com/daf32/zem-shell/main/registry"
HTTP_TIMEOUT = 15
#: The index is small and changes rarely; `search` should not hit the
#: network every time someone browses.
INDEX_CACHE_SECONDS = 3600
#: Cache file name. It is kept *beside* the spec directory, never inside
#: it: anything ending in .json in there is loaded as a spec, and a cache
#: file would be reported as a broken one.
INDEX_CACHE_NAME = "hints-index.json"


def cache_path_for(user_dir: str) -> Path:
    """Where to cache the index for a given spec directory.

    Derived from the configured directory rather than hard-coded, so the
    test suite (which points `hints.user_dir` at tmp_path) never writes to
    the developer's real `~/.zem`.
    """
    return Path(user_dir).expanduser().parent / "cache" / INDEX_CACHE_NAME


class RegistryError(Exception):
    """The registry could not be reached, or answered with nonsense."""


def index_url(base: str) -> str:
    return f"{base.rstrip('/')}/index.json"


def spec_url(base: str, name: str) -> str:
    return f"{base.rstrip('/')}/hints/{urllib.parse.quote(name)}.json"


def fetch_index(base: str, cache: Optional[Path] = None,
                refresh: bool = False) -> list[dict]:
    """The registry's catalogue, cached for an hour."""
    if cache is not None and not refresh:
        cached = _read_cache(cache, base)
        if cached is not None:
            return cached

    raw = _get(index_url(base))
    try:
        data = json.loads(raw)
        entries = data["hints"]
        if not isinstance(entries, list):
            raise TypeError
    except (ValueError, KeyError, TypeError) as exc:
        raise RegistryError(f"{index_url(base)}: not a valid registry index") from exc

    if cache is not None:
        _write_cache(cache, base, entries)
    return entries


def fetch_spec(base: str, name: str, expected_sha256: Optional[str] = None) -> bytes:
    """Download one spec and check it before it is trusted."""
    raw = _get(spec_url(base, name))
    if expected_sha256:
        digest = hashlib.sha256(raw).hexdigest()
        if digest != expected_sha256:
            raise RegistryError(
                f"{name}: checksum mismatch (index says {expected_sha256[:12]}…, "
                f"download is {digest[:12]}…)"
            )
    try:
        document = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise RegistryError(f"{name}: downloaded file is not valid JSON") from exc

    # `SpecError` is a `ValueError`, so it must not share a handler with the
    # JSON decode above -- the message would blame the wrong thing.
    try:
        spec = parse_spec(document)
    except SpecError as exc:
        messages = exc.args[0] if isinstance(exc.args[0], list) else [str(exc)]
        raise RegistryError(f"{name}: invalid spec: {'; '.join(messages)}") from exc
    log.debug("fetched spec %s for command %s", name, spec.command)
    return raw


def install(base: str, name: str, target_dir: Path,
            expected_sha256: Optional[str] = None) -> Path:
    """Download a spec into `target_dir`, atomically."""
    raw = fetch_spec(base, name, expected_sha256)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{name}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_bytes(raw)
    tmp.replace(path)
    return path


def _get(url: str) -> bytes:
    if not url.startswith(("https://", "http://")):
        raise RegistryError(f"refusing to fetch a non-HTTP URL: {url}")
    try:
        with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT) as response:  # noqa: S310
            return response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise RegistryError(f"{url}: not found in the registry") from exc
        raise RegistryError(f"{url}: HTTP {exc.code}") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise RegistryError(f"{url}: {exc}") from exc


def _read_cache(path: Path, base: str) -> Optional[list[dict]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if data.get("base") != base:
        return None
    if time.time() - data.get("fetched_at", 0) > INDEX_CACHE_SECONDS:
        return None
    entries = data.get("hints")
    return entries if isinstance(entries, list) else None


def _write_cache(path: Path, base: str, entries: list[dict]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"base": base, "fetched_at": time.time(), "hints": entries}),
            encoding="utf-8",
        )
    except OSError as exc:
        log.debug("could not cache the registry index: %s", exc)
