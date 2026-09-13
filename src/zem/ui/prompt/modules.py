"""The modules a prompt is assembled from.

A module does not render itself. It reports variables — `$branch`,
`$status`, `$path` — and its own format string decides what to do with
them. That is what makes " on [$branch]($style)" configurable without
touching Python.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


@dataclass
class PromptContext:
    """What a module gets to work with."""

    shell: Any
    cwd: str
    exit_code: int
    duration: Optional[float] = None

    @property
    def config(self):
        return self.shell.config


class PromptModule:
    """One named source of prompt variables.

    `variables()` returns a mapping, or `None` when the module has nothing
    to say right now — no virtualenv, not a repository, a command too fast
    to be worth timing. A module that returns None disappears, and so does
    any conditional group that referred only to it.
    """

    name: str = ""
    #: Used when the config does not override it. `$style` resolves to
    #: `default_style`, which is usually a theme colour key.
    default_format: str = ""
    default_style: str = ""

    def variables(self, ctx: PromptContext) -> Optional[dict]:
        raise NotImplementedError


class VenvModule(PromptModule):
    name = "venv"
    default_format = "[\\[$name\\] ]($style)"
    default_style = "venv"

    def variables(self, ctx):
        if not getattr(ctx.config.input, "show_venv_info", True):
            return None
        from zem.utils.venv import get_venv_info

        info = get_venv_info()
        return {"name": info} if info else None


class ExitCodeModule(PromptModule):
    name = "exit_code"
    default_format = "[$code ]($style)"
    default_style = "exit_code_ok"

    def variables(self, ctx):
        if not getattr(ctx.config.input, "show_exit_code", True):
            return None
        return {"code": str(ctx.exit_code)}

    def style_for(self, ctx: PromptContext) -> str:
        return "exit_code_ok" if ctx.exit_code == 0 else "exit_code_err"


class PathModule(PromptModule):
    name = "path"
    default_format = "[$path]($style)"
    default_style = "path"

    def variables(self, ctx):
        return {"path": format_path_display(format_path(ctx.cwd, ctx.config))}


class GitModule(PromptModule):
    name = "git"
    # The parentheses are literal, hence escaped: bare ones would read as a
    # conditional group.
    default_format = "[ \\($branch$status\\)]($style)"
    default_style = "git_branch"

    def variables(self, ctx):
        if not getattr(ctx.config.input, "show_git_info", True):
            return None
        from zem.utils.git import get_git_info

        info = get_git_info(ctx.cwd, timeout_ms=_setting(ctx, "git", "timeout_ms"))
        if not info:
            return None
        branch, status = info
        return {"branch": _shorten(branch, _setting(ctx, "git", "max_length") or 20),
                "status": status}


class SymbolModule(PromptModule):
    name = "symbol"
    default_format = " [$symbol]($style) "
    default_style = "prompt_symbol"

    def variables(self, ctx):
        return {"symbol": ctx.config.input.prompt}


class DurationModule(PromptModule):
    name = "duration"
    default_format = "[⏱ $duration ]($style)"
    default_style = "duration"

    #: Below this a command is not worth timing on screen.
    THRESHOLD = 0.1

    def variables(self, ctx):
        if ctx.duration is None or ctx.duration < self.THRESHOLD:
            return None
        text = format_duration(ctx.duration)
        return {"duration": text} if text else None


class TimeModule(PromptModule):
    name = "time"
    default_format = "[$time]($style)"
    default_style = "rprompt"

    def variables(self, ctx):
        fmt = getattr(ctx.config.prompt, "time_format", "%H:%M:%S")
        return {"time": datetime.now().strftime(fmt)}


class UserModule(PromptModule):
    name = "user"
    default_format = "[$user]($style)"
    default_style = "info"

    def variables(self, ctx):
        try:
            return {"user": os.getlogin()}
        except OSError:
            return {"user": os.environ.get("USER", "")}


class HostModule(PromptModule):
    name = "host"
    default_format = "[$host]($style)"
    default_style = "info"

    def variables(self, ctx):
        import socket

        return {"host": socket.gethostname().split(".")[0]}


class JobsModule(PromptModule):
    name = "jobs"
    default_format = "[✦$count ]($style)"
    default_style = "warning"

    def variables(self, ctx):
        jobs = getattr(ctx.shell.context, "_jobs", None)
        count = len(list(jobs)) if jobs is not None else 0
        return {"count": str(count)} if count else None


BUILTIN_MODULES: tuple = (
    VenvModule, ExitCodeModule, PathModule, GitModule, SymbolModule,
    DurationModule, TimeModule, UserModule, HostModule, JobsModule,
)


def _setting(ctx: PromptContext, module: str, key: str):
    """One option of a module's own config section, or ``None``.

    The renderer keeps these settings to itself (it applies `format`,
    `style` and `disabled`); a module that takes an option of its own --
    how long to wait for git, how much of a branch name to show -- reads
    it from here.
    """
    modules = getattr(ctx.config.prompt, "modules", {})
    section = modules.get(module) if isinstance(modules, dict) else None
    value = section.get(key) if isinstance(section, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _shorten(branch: str, max_length: int = 20) -> str:
    return branch if len(branch) <= max_length else branch[:max_length - 1] + "…"


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
