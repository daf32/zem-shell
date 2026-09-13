"""The prompt, assembled from named segments.

The prompt used to be built by two hand-written functions with the order
of its parts baked in. Segments make that order configuration, and let a
plugin add one of its own.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Optional

log = logging.getLogger(__name__)

#: One piece of rendered prompt: prompt_toolkit `(style, text)` pairs.
Fragments = list


@dataclass
class PromptContext:
    """What a segment gets to work with."""

    shell: Any
    cwd: str
    exit_code: int
    duration: Optional[float] = None

    @property
    def config(self):
        return self.shell.config


class PromptSegment:
    """One named piece of the prompt.

    `render` returns `(style, text)` pairs, or `None` when the segment has
    nothing to show right now — an empty venv, a directory outside a git
    repository, a command too fast to time.
    """

    name: str = ""

    def render(self, ctx: PromptContext) -> Optional[Fragments]:
        raise NotImplementedError


class VenvSegment(PromptSegment):
    name = "venv"

    def render(self, ctx):
        if not getattr(ctx.config.input, "show_venv_info", False):
            return None
        from zem.utils.venv import get_venv_info

        info = get_venv_info()
        return [("class:venv", f"[{info}] ")] if info else None


class ExitCodeSegment(PromptSegment):
    name = "exit_code"

    def render(self, ctx):
        if not ctx.config.input.show_exit_code:
            return None
        style = "exit_code_ok" if ctx.exit_code == 0 else "exit_code_err"
        return [(f"class:{style}", f"{ctx.exit_code} ")]


class PathSegment(PromptSegment):
    name = "path"

    def render(self, ctx):
        return [("class:path", format_path_display(format_path(ctx.cwd, ctx.config)))]


class GitSegment(PromptSegment):
    name = "git"

    def render(self, ctx):
        if not getattr(ctx.config.input, "show_git_info", False):
            return None
        from zem.utils.git import format_git_branch, get_git_info

        info = get_git_info(ctx.cwd)
        if not info:
            return None
        branch, status = info
        return [("class:git_branch", f" ({format_git_branch(branch, status)})")]


class SymbolSegment(PromptSegment):
    name = "symbol"

    def render(self, ctx):
        return [
            ("", " "),
            ("class:prompt_symbol", ctx.config.input.prompt),
            ("", " "),
        ]


class DurationSegment(PromptSegment):
    name = "duration"

    #: Below this a command is not worth timing on screen.
    THRESHOLD = 0.1

    def render(self, ctx):
        if ctx.duration is None or ctx.duration < self.THRESHOLD:
            return None
        text = format_duration(ctx.duration)
        return [("class:duration", f"⏱ {text} ")] if text else None


class TimeSegment(PromptSegment):
    name = "time"

    def render(self, ctx):
        return [("class:rprompt", datetime.now().strftime("%H:%M:%S"))]


BUILTIN_SEGMENTS: tuple = (
    VenvSegment, ExitCodeSegment, PathSegment, GitSegment, SymbolSegment,
    DurationSegment, TimeSegment,
)


class PromptRenderer:
    """Holds the available segments and assembles a prompt from them."""

    def __init__(self, shell, extra: Optional[dict] = None):
        self.shell = shell
        self.segments: dict = {cls.name: cls() for cls in BUILTIN_SEGMENTS}
        if extra:
            # Plugins go last, so one may replace a builtin segment.
            self.segments.update(extra)
        self._warned: set = set()

    def render(self, names: Iterable[str], ctx: PromptContext, colored: bool = True):
        """Render `names` in order; a string when `colored` is false."""
        fragments: Fragments = []
        for name in names:
            segment = self.segments.get(name)
            if segment is None:
                if name not in self._warned:
                    self._warned.add(name)
                    log.warning("unknown prompt segment %r", name)
                continue
            try:
                piece = segment.render(ctx)
            except Exception as exc:
                # A segment that raises must not cost the user their prompt.
                if name not in self._warned:
                    self._warned.add(name)
                    log.warning("prompt segment %r failed: %s", name, exc)
                continue
            if piece:
                fragments.extend(piece)

        if colored:
            return fragments
        return "".join(text for _style, text in fragments)


def format_path(current_dir: str, config) -> str:
    """Shorten `current_dir` for display, honouring the path settings."""
    home = os.path.expanduser("~")
    display_path = current_dir.replace(home, "~") if current_dir.startswith(home) \
        else current_dir

    if config.input.show_full_path:
        return display_path

    parts = display_path.strip("/").split("/")
    depth = config.input.path_depth
    if len(parts) > depth:
        return "/".join(parts[-depth:])
    return display_path


def format_path_display(path: str) -> str:
    """Add a `~` prefix when the path is not already under home."""
    return path if path.startswith("~") else f"~ {path}"


def format_duration(seconds: float) -> str:
    """How long the last command took, for the right-hand prompt."""
    if seconds < 0.001:
        return ""  # too fast to be worth saying
    if seconds < 1:
        return f"{int(seconds * 1000)}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m{int(seconds % 60)}s"
    return f"{int(seconds // 3600)}h{int((seconds % 3600) // 60)}m"
