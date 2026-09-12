"""Installing plugin packages into whatever environment Zem lives in.

A plugin is an ordinary Python package, so installing one means asking
the tool that installed Zem to add it alongside. Which tool that is has
to be detected: `uv tool`, `pipx` and a plain virtualenv each want a
different command, and getting it wrong either fails or — worse —
installs into the wrong interpreter, where Zem will never see it.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

log = logging.getLogger(__name__)

#: The tool name Zem is installed under.
TOOL_NAME = "zem"

#: A package name with an optional extras list and version specifier:
#: `zem-plugin-foo`, `zem-plugin-foo[extra]`, `zem-plugin-foo==1.2.3`.
REQUIREMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(\[[A-Za-z0-9,._-]+\])?"
                         r"((==|>=|<=|~=|!=|>|<)[A-Za-z0-9._*+!-]+)?$")

LIST_TIMEOUT = 15
INSTALL_TIMEOUT = 600


class InstallError(Exception):
    """The installation could not be attempted, or it failed."""


@dataclass
class Environment:
    """How Zem was installed, and what that implies."""

    kind: str          # "uv-tool" | "pipx" | "venv" | "system"
    description: str
    can_install: bool = True
    reason: str = ""   # why not, when can_install is False

    def install_command(self, packages: Sequence[str]) -> list[str]:
        if self.kind == "uv-tool":
            # `uv tool install` *replaces* the extras rather than adding to
            # them, so the current ones have to be passed again or the
            # plugins already installed would be silently removed.
            keep = [p for p in uv_tool_extras() if p not in packages]
            return ["uv", "tool", "install", TOOL_NAME,
                    *_with_flags([*keep, *packages])]
        if self.kind == "pipx":
            return ["pipx", "inject", TOOL_NAME, *packages]
        return [sys.executable, "-m", "pip", "install", *packages]

    def uninstall_command(self, packages: Sequence[str]) -> list[str]:
        if self.kind == "uv-tool":
            keep = [p for p in uv_tool_extras() if p not in packages]
            return ["uv", "tool", "install", TOOL_NAME, "--reinstall",
                    *_with_flags(keep)]
        if self.kind == "pipx":
            return ["pipx", "uninject", TOOL_NAME, *packages]
        return [sys.executable, "-m", "pip", "uninstall", "-y", *packages]


def _with_flags(packages: Sequence[str]) -> list[str]:
    flags: list[str] = []
    for package in packages:
        flags += ["--with", package]
    return flags


def detect_environment() -> Environment:
    """Work out how this Zem was installed."""
    prefix = Path(sys.prefix)

    if (prefix / "uv-receipt.toml").is_file():
        if shutil.which("uv") is None:
            return Environment("uv-tool", "uv tool", False,
                               "uv installed this shell but is not on PATH now")
        return Environment("uv-tool", f"uv tool ({prefix})")

    if (prefix / "pipx_metadata.json").is_file():
        if shutil.which("pipx") is None:
            return Environment("pipx", "pipx", False,
                               "pipx installed this shell but is not on PATH now")
        return Environment("pipx", f"pipx ({prefix})")

    if sys.prefix != sys.base_prefix:
        return Environment("venv", f"virtualenv ({prefix})")

    # A system interpreter: installing into it needs root, or breaks the
    # distribution's packaging. Not our call to make.
    return Environment(
        "system", f"system Python ({prefix})", False,
        "zem is running from a system Python; install the plugin the same way "
        "you installed zem, or reinstall zem with uv or pipx",
    )


def uv_tool_extras() -> list[str]:
    """Packages currently installed alongside Zem by `uv tool`.

    Read from `uv tool list --show-with` rather than by parsing
    `uv-receipt.toml`: the receipt is TOML, and `tomllib` only exists on
    Python 3.11+, while this shell supports 3.10.
    """
    try:
        proc = subprocess.run(
            ["uv", "tool", "list", "--show-with"],
            capture_output=True, text=True, timeout=LIST_TIMEOUT,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.debug("could not list uv tools: %s", exc)
        return []
    if proc.returncode != 0:
        return []

    for line in proc.stdout.splitlines():
        # "zem v0.11.1 [with: pyfiglet, cowsay]"
        if not line.startswith(f"{TOOL_NAME} "):
            continue
        match = re.search(r"\[with: ([^\]]+)\]", line)
        if match is None:
            return []
        return [part.strip() for part in match.group(1).split(",") if part.strip()]
    return []


def validate(packages: Sequence[str]) -> None:
    """Reject anything that is not a plain requirement."""
    for package in packages:
        if not REQUIREMENT.match(package):
            raise InstallError(
                f"{package!r} does not look like a package name; "
                "install it yourself if you meant something else"
            )


def run(command: Sequence[str], stdout=None, stderr=None) -> int:
    """Run an installer command, streaming its output to the user."""
    try:
        proc = subprocess.run(
            list(command),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=INSTALL_TIMEOUT,
        )
    except FileNotFoundError as exc:
        raise InstallError(f"{command[0]}: not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise InstallError(f"{command[0]}: timed out after {INSTALL_TIMEOUT}s") from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise InstallError(f"{command[0]}: {exc}") from exc

    if proc.stdout:
        (stdout or sys.stdout).write(proc.stdout)
    if proc.stderr:
        (stderr or sys.stderr).write(proc.stderr)
    return proc.returncode


def installed_distributions(prefix: str = "") -> list[tuple[str, str]]:
    """Installed distributions that advertise a zem plugin entry point."""
    import importlib.metadata

    from zem.plugin.manager import ENTRY_POINT_GROUP

    found: list[tuple[str, str]] = []
    for dist in importlib.metadata.distributions():
        try:
            entry_points = dist.entry_points
        except Exception:  # a broken .dist-info in the environment
            continue
        if any(ep.group == ENTRY_POINT_GROUP for ep in entry_points):
            name = dist.metadata["Name"] or ""
            if name and (not prefix or name.startswith(prefix)):
                found.append((name, dist.version or ""))
    return sorted(set(found))


def find_distribution_for(plugin_name: str) -> Optional[str]:
    """The distribution that provides a plugin, for `plugin remove`."""
    import importlib.metadata

    from zem.plugin.manager import ENTRY_POINT_GROUP

    for dist in importlib.metadata.distributions():
        try:
            entry_points = dist.entry_points
        except Exception:
            continue
        for entry_point in entry_points:
            if entry_point.group == ENTRY_POINT_GROUP and entry_point.name == plugin_name:
                return dist.metadata["Name"]
    return None
