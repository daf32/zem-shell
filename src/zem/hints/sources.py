"""Turning a spec's value source into concrete suggestions."""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Iterable, NamedTuple, Optional

from zem.hints.spec import (
    CommandSource,
    CommandsSource,
    Guard,
    ParseSpec,
    ProviderSource,
    ValuesSource,
)

log = logging.getLogger(__name__)

#: A binary that is not installed must not be probed on every keystroke.
NEGATIVE_TTL_MS = 10_000
#: stdout past this is a spec doing something silly (`git ls-files` in a
#: monorepo); parse what we have and move on.
_MAX_OUTPUT = 1_000_000
_MAX_CACHE_ENTRIES = 64

_CACHE: "OrderedDict[tuple, tuple[float, tuple]]" = OrderedDict()
_LOCK = threading.Lock()


class Suggestion(NamedTuple):
    value: str
    description: str = ""


@dataclass
class SourceContext:
    """Everything a source may need to produce values."""

    cwd: str
    shell: Any = None
    #: Words of the command typed so far, aliases already expanded.
    words: tuple[str, ...] = ()
    #: Path through the spec: ("git", "remote", "add").
    node_path: tuple[str, ...] = ()
    #: What the user has typed for the value being completed.
    prefix: str = ""
    #: `args` from a provider source.
    args: dict = field(default_factory=dict)
    settings: Any = None


def clear_cache() -> None:
    """Forget every cached command result (`config reload`, tests)."""
    with _LOCK:
        _CACHE.clear()


def resolve(source, ctx: SourceContext) -> list[Suggestion]:
    """Suggestions for one value source.

    Path-shaped sources (`files`, `dirs`, `none`) are not handled here —
    the completer serves those from prompt_toolkit's path completer.
    """
    if isinstance(source, ValuesSource):
        return [Suggestion(c.value, c.description) for c in source.choices()]

    if isinstance(source, CommandsSource):
        from zem.utils.executables import get_system_commands

        return [Suggestion(name) for name in get_system_commands()]

    if isinstance(source, ProviderSource):
        if not _dynamic_allowed(ctx) or len(ctx.prefix) < source.min_prefix:
            return []
        from zem.hints.providers import PROVIDERS

        fn = PROVIDERS.get(source.name)
        if fn is None:
            log.debug("no provider named %r", source.name)
            return []
        provider_ctx = SourceContext(
            cwd=ctx.cwd, shell=ctx.shell, words=ctx.words, node_path=ctx.node_path,
            prefix=ctx.prefix, args=dict(source.args), settings=ctx.settings,
        )
        try:
            return _normalize(fn(provider_ctx))
        except Exception:  # a broken provider must not break the prompt
            log.debug("provider %r failed", source.name, exc_info=True)
            return []

    if isinstance(source, CommandSource):
        if not _dynamic_allowed(ctx) or len(ctx.prefix) < source.min_prefix:
            return []
        return list(run_command(source, ctx))

    return []


def _dynamic_allowed(ctx: SourceContext) -> bool:
    return getattr(ctx.settings, "dynamic", True)


def _normalize(items: Iterable) -> list[Suggestion]:
    """Accept `Suggestion`, plain strings and `(value, description)`."""
    out = []
    for item in items:
        if isinstance(item, Suggestion):
            out.append(item)
        elif isinstance(item, str):
            out.append(Suggestion(item))
        else:
            pair = tuple(item)
            out.append(Suggestion(str(pair[0]), str(pair[1]) if len(pair) > 1 else ""))
    return out


def run_command(source: CommandSource, ctx: SourceContext) -> tuple[Suggestion, ...]:
    """Run a `command` source, honouring its guard, timeout and cache."""
    key = _cache_key(tuple(source.run), source.cache_scope, ctx)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    if source.guard is not None and not _guard_passes(source.guard, ctx):
        _cache_put(key, (), source.cache_ttl_ms)
        return ()

    timeout_ms = min(source.timeout_ms, _ceiling(ctx, "command_timeout_ms", source.timeout_ms))
    out, failed = _capture(list(source.run), ctx, timeout_ms, source.accept_nonzero)
    values = tuple(_parse(out, source.parse))
    ttl = max(source.cache_ttl_ms, NEGATIVE_TTL_MS) if failed else source.cache_ttl_ms
    _cache_put(key, values, ttl)
    return values


def _guard_passes(guard: Guard, ctx: SourceContext) -> bool:
    key = _cache_key(("guard", *guard.run), "cwd", ctx)
    cached = _cache_get(key)
    if cached is not None:
        return bool(cached)
    _, failed = _capture(list(guard.run), ctx, guard.timeout_ms, accept_nonzero=False)
    _cache_put(key, () if failed else (Suggestion("ok"),), guard.cache_ttl_ms)
    return not failed


def _capture(argv: list[str], ctx: SourceContext, timeout_ms: int,
             accept_nonzero: bool) -> tuple[str, bool]:
    """Run `argv` and return `(stdout, failed)`. Never raises."""
    try:
        proc = subprocess.run(
            argv,
            cwd=ctx.cwd,
            capture_output=True,
            text=True,
            timeout=timeout_ms / 1000,
            stdin=subprocess.DEVNULL,
            # The shell hands the terminal to foreground process groups with
            # `tcsetpgrp`. A completion helper that joined that group could
            # grab the terminal and hang the prompt, so give it its own
            # session.
            start_new_session=True,
            env=_child_env(),
        )
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError) as exc:
        log.debug("hint source %r failed: %s", argv, exc)
        return "", True
    if proc.returncode != 0 and not accept_nonzero:
        return "", True
    return proc.stdout[:_MAX_OUTPUT], False


def _child_env() -> dict:
    """A predictable environment: stable parsing, no locks, no colour."""
    return {
        **os.environ,
        "LC_ALL": "C",
        "NO_COLOR": "1",
        "TERM": "dumb",
        # Never let a completion touch .git/index.lock.
        "GIT_OPTIONAL_LOCKS": "0",
    }


def _parse(out: str, parse: ParseSpec) -> list[Suggestion]:
    suggestions: list[Suggestion] = []
    lines = out.splitlines()[parse.skip_lines:]
    for line in lines:
        if len(suggestions) >= parse.max_items:
            break
        line = line.rstrip()
        if not line.strip():
            continue
        if parse.separator is None:
            suggestions.append(Suggestion(line.strip()))
            continue
        fields = line.split(parse.separator)
        value = _column(fields, parse.value_column)
        if not value:
            continue
        description = ""
        if parse.description_column is not None:
            description = _column(fields, parse.description_column)
        suggestions.append(Suggestion(value, description))
    return suggestions


def _column(fields: list[str], index: int) -> str:
    return fields[index].strip() if index < len(fields) else ""


def _ceiling(ctx: SourceContext, name: str, default: int) -> int:
    return getattr(ctx.settings, name, default) if ctx.settings is not None else default


def _cache_key(run: tuple, scope: str, ctx: SourceContext) -> tuple:
    return (run, ctx.cwd if scope == "cwd" else None)


def _cache_get(key: tuple) -> Optional[tuple]:
    now = time.monotonic()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit is None:
            return None
        if hit[0] <= now:
            del _CACHE[key]
            return None
        _CACHE.move_to_end(key)
        return hit[1]


def _cache_put(key: tuple, values: tuple, ttl_ms: int) -> None:
    with _LOCK:
        _CACHE[key] = (time.monotonic() + ttl_ms / 1000, values)
        _CACHE.move_to_end(key)
        while len(_CACHE) > _MAX_CACHE_ENTRIES:
            _CACHE.popitem(last=False)
