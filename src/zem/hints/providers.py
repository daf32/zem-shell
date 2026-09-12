"""Named value providers a spec can point at.

A spec refers to a provider by name, and the name is resolved lazily, at
completion time. That indirection is what lets a plugin ship a provider
for a spec that already exists — and it is the hook the plugin API will
sit on.
"""

from __future__ import annotations

import glob
import json
import logging
import os
import re
from typing import Callable, Iterable, Literal, Optional, Union

from zem.hints.sources import SourceContext, Suggestion, run_command
from zem.hints.spec import CommandSource, Guard, ParseSpec

log = logging.getLogger(__name__)

ProviderResult = Iterable[Union[Suggestion, str, tuple]]
ProviderFn = Callable[[SourceContext], ProviderResult]

_GIT_GUARD = Guard(run=["git", "rev-parse", "--is-inside-work-tree"])


class ProviderRegistry:
    """Process-wide registry of named providers."""

    def __init__(self) -> None:
        self._providers: dict[str, ProviderFn] = {}

    def register(self, name: str, fn: ProviderFn, *, override: bool = False) -> None:
        if name in self._providers and not override:
            raise ValueError(
                f"provider {name!r} is already registered; pass override=True to replace it"
            )
        self._providers[name] = fn

    def get(self, name: str) -> Optional[ProviderFn]:
        return self._providers.get(name)

    def names(self) -> list[str]:
        return sorted(self._providers)


PROVIDERS = ProviderRegistry()


def provider(name: str, *, override: bool = False):
    """Decorator registering a provider under `name`."""

    def decorate(fn: ProviderFn) -> ProviderFn:
        PROVIDERS.register(name, fn, override=override)
        return fn

    return decorate


def _run(ctx: SourceContext, argv: list[str], *, separator: str | None = None,
         guard: Guard | None = None, ttl_ms: int = 2000, timeout_ms: int = 300,
         scope: Literal["cwd", "global"] = "cwd",
         max_items: int = 200) -> list[Suggestion]:
    """Shell out through the cached, guarded runner in `sources`."""
    source = CommandSource(
        type="command",
        run=argv,
        timeout_ms=timeout_ms,
        cache_ttl_ms=ttl_ms,
        cache_scope=scope,
        guard=guard,
        parse=ParseSpec(separator=separator, max_items=max_items),
    )
    return list(run_command(source, ctx))


# --- git ------------------------------------------------------------------

@provider("git.branches")
def _git_branches(ctx: SourceContext) -> list[Suggestion]:
    """Local branches, most recently touched first, with commit subjects."""
    refs = ["refs/heads"]
    if ctx.args.get("include_remotes"):
        refs.append("refs/remotes")
    return _run(ctx, [
        "git", "for-each-ref", "--sort=-committerdate",
        "--format=%(refname:short)\t%(contents:subject)", *refs,
    ], separator="\t", guard=_GIT_GUARD)


@provider("git.remotes")
def _git_remotes(ctx: SourceContext) -> list[Suggestion]:
    return _run(ctx, ["git", "remote"], guard=_GIT_GUARD, ttl_ms=10_000)


@provider("git.tags")
def _git_tags(ctx: SourceContext) -> list[Suggestion]:
    return _run(ctx, ["git", "tag", "--sort=-creatordate"], guard=_GIT_GUARD, ttl_ms=10_000)


@provider("git.dirty_files")
def _git_dirty_files(ctx: SourceContext) -> list[Suggestion]:
    """Files git considers changed.

    `git ls-files` would list the whole index — tens of megabytes in a
    monorepo. What `git add`/`restore` actually need is what changed.
    """
    out = _run(ctx, ["git", "status", "--porcelain", "-uall"], guard=_GIT_GUARD, ttl_ms=1000)
    files = []
    for item in out:
        # Porcelain v1 is `XY<space>path`. Splitting on whitespace (rather
        # than slicing fixed columns) survives the leading blank of an
        # unstaged-only status, which `_run` has already stripped.
        status, _, path = item.value.partition(" ")
        path = path.strip()
        if not path:
            continue
        # Renames read as "old -> new"; the new name is the useful one.
        path = path.split(" -> ")[-1].strip('"')
        files.append(Suggestion(path, _PORCELAIN.get(status, status)))
    return files


_PORCELAIN = {
    "??": "untracked",
    "M": "modified",
    "A": "added",
    "D": "deleted",
    "R": "renamed",
    "MM": "staged + modified",
    "AM": "added + modified",
}


@provider("git.stashes")
def _git_stashes(ctx: SourceContext) -> list[Suggestion]:
    return _run(ctx, ["git", "stash", "list", "--format=%gd\t%gs"],
                separator="\t", guard=_GIT_GUARD, ttl_ms=5000)


# --- docker ---------------------------------------------------------------

@provider("docker.containers_running")
def _docker_running(ctx: SourceContext) -> list[Suggestion]:
    return _run(ctx, ["docker", "ps", "--format", "{{.Names}}\t{{.Image}}"],
                separator="\t", scope="global", ttl_ms=5000, timeout_ms=800)


@provider("docker.containers_all")
def _docker_all(ctx: SourceContext) -> list[Suggestion]:
    return _run(ctx, ["docker", "ps", "-a", "--format", "{{.Names}}\t{{.Status}}"],
                separator="\t", scope="global", ttl_ms=5000, timeout_ms=800)


@provider("docker.images")
def _docker_images(ctx: SourceContext) -> list[Suggestion]:
    return _run(ctx, ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}\t{{.Size}}"],
                separator="\t", scope="global", ttl_ms=10_000, timeout_ms=800)


@provider("docker.compose_services")
def _docker_compose_services(ctx: SourceContext) -> list[Suggestion]:
    return _run(ctx, ["docker", "compose", "config", "--services"],
                ttl_ms=10_000, timeout_ms=1500)


# --- node -----------------------------------------------------------------

@provider("pip.packages")
def _pip_packages(ctx: SourceContext) -> list[Suggestion]:
    """Installed distributions, for `pip uninstall`/`pip show`."""
    return _run(ctx, ["pip", "list", "--format=freeze", "--disable-pip-version-check"],
                separator="==", ttl_ms=30_000, timeout_ms=1500, max_items=500)


@provider("npm.dependencies")
def _npm_dependencies(ctx: SourceContext) -> list[Suggestion]:
    """Dependencies declared in package.json, for `npm uninstall`."""
    data = _package_json(ctx)
    out: list[Suggestion] = []
    for section in ("dependencies", "devDependencies", "optionalDependencies"):
        declared = data.get(section)
        if isinstance(declared, dict):
            out += [Suggestion(name, f"{version} ({section})")
                    for name, version in declared.items()]
    return out


@provider("npm.scripts")
def _npm_scripts(ctx: SourceContext) -> list[Suggestion]:
    """Scripts from package.json — read directly, no `npm` process."""
    scripts = _package_json(ctx).get("scripts")
    if not isinstance(scripts, dict):
        return []
    return [Suggestion(name, str(cmd)[:60]) for name, cmd in scripts.items()]


@provider("uv.tools")
def _uv_tools(ctx: SourceContext) -> list[Suggestion]:
    out = _run(ctx, ["uv", "tool", "list"], scope="global", ttl_ms=30_000, timeout_ms=1500)
    # `uv tool list` indents the entry points under each tool; the tools
    # themselves are the unindented `name version` lines.
    return [Suggestion(item.value.split()[0]) for item in out if not item.value.startswith("-")]


@provider("brew.installed")
def _brew_installed(ctx: SourceContext) -> list[Suggestion]:
    return _run(ctx, ["brew", "list", "--formula"], scope="global", ttl_ms=60_000,
                timeout_ms=2000, max_items=500)


@provider("k8s.resources")
def _k8s_resources(ctx: SourceContext) -> list[Suggestion]:
    """Resource kinds the cluster knows, so `kubectl get <TAB>` is useful."""
    return _run(ctx, ["kubectl", "api-resources", "--no-headers", "-o", "name"],
                scope="global", ttl_ms=300_000, timeout_ms=2000, max_items=500)


@provider("k8s.pods")
def _k8s_pods(ctx: SourceContext) -> list[Suggestion]:
    out = _run(ctx, ["kubectl", "get", "pods", "--no-headers",
                     "-o", "custom-columns=:metadata.name,:status.phase"],
               scope="global", ttl_ms=5000, timeout_ms=2000)
    pods = []
    for item in out:
        name, _, phase = item.value.partition(" ")
        pods.append(Suggestion(name, phase.strip()))
    return pods


@provider("make.targets")
def _make_targets(ctx: SourceContext) -> list[Suggestion]:
    """Targets of the local Makefile.

    Parsed rather than asked of `make`: `make -qp` runs the makefile's
    shell assignments, which is not something a TAB press should do.
    """
    targets: list[Suggestion] = []
    seen: set[str] = set()
    for name in ("Makefile", "makefile", "GNUmakefile"):
        path = os.path.join(ctx.cwd, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    match = _MAKE_TARGET.match(line)
                    if match is None:
                        continue
                    for target in match.group(1).split():
                        if target not in seen and not target.startswith("."):
                            seen.add(target)
                            targets.append(Suggestion(target))
        except OSError:
            continue
        break
    return targets


_MAKE_TARGET = re.compile(r"^([A-Za-z0-9._%/$(){} -]+):(?!=)")


@provider("ssh.hosts")
def _ssh_hosts(ctx: SourceContext) -> list[Suggestion]:
    """Hosts named in ~/.ssh/config, plus its Include files."""
    hosts: list[Suggestion] = []
    seen: set[str] = set()
    for path in _ssh_config_files():
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    parts = line.strip().split()
                    if len(parts) < 2 or parts[0].lower() != "host":
                        continue
                    for name in parts[1:]:
                        # Patterns are not connectable destinations.
                        if any(ch in name for ch in "*?!") or name in seen:
                            continue
                        seen.add(name)
                        hosts.append(Suggestion(name, os.path.basename(path)))
        except OSError:
            continue
    return hosts


def _ssh_config_files() -> list[str]:
    base = os.path.expanduser("~/.ssh/config")
    files = [base]
    try:
        with open(base, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                parts = line.strip().split()
                if len(parts) >= 2 and parts[0].lower() == "include":
                    for pattern in parts[1:]:
                        files += sorted(glob.glob(os.path.expanduser(
                            pattern if os.path.isabs(pattern)
                            else os.path.join("~/.ssh", pattern))))
    except OSError:
        pass
    return files


# --- zem itself -----------------------------------------------------------

@provider("zem.commands")
def _zem_commands(ctx: SourceContext) -> list[Suggestion]:
    from zem.utils.executables import get_system_commands

    return [Suggestion(name) for name in get_system_commands()]


@provider("zem.aliases")
def _zem_aliases(ctx: SourceContext) -> list[Suggestion]:
    shell = ctx.shell
    if shell is None:
        return []
    return [Suggestion(name, value) for name, value in sorted(shell.context.aliases.items())]


@provider("zem.variables")
def _zem_variables(ctx: SourceContext) -> list[Suggestion]:
    shell = ctx.shell
    if shell is None:
        return []
    return [
        Suggestion(name, "exported" if shell.context.is_exported(name) else "shell")
        for name in sorted(shell.context.variables)
        if name != "?"
    ]


@provider("zem.themes")
def _zem_themes(ctx: SourceContext) -> list[Suggestion]:
    from zem.config.settings import AppConfig
    from zem.utils.themes import ThemeManager

    config = getattr(ctx.shell, "config", None) or AppConfig()
    manager = ThemeManager(config)
    return [
        Suggestion(name, str(data.get("data", {}).get("type", "")))
        for name, data in sorted(manager.list_themes().items())
    ]


@provider("zem.config_keys")
def _zem_config_keys(ctx: SourceContext) -> list[Suggestion]:
    """Dotted keys of the *live* config, with their current values.

    Reading the live config (rather than a snapshot taken at startup) is
    what makes a key written by `config set` show up straight away.
    """
    from zem.config.settings import AppConfig

    config = getattr(ctx.shell, "config", None) or AppConfig()
    return _flatten(config.model_dump())


def _flatten(data: dict, prefix: str = "") -> list[Suggestion]:
    out: list[Suggestion] = []
    for key, value in data.items():
        full = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict) and key != "plugins":
            out.extend(_flatten(value, full))
        else:
            out.append(Suggestion(full, str(value)[:40]))
    return out


def _package_json(ctx: SourceContext) -> dict:
    """package.json of the current directory, or an empty dict."""
    try:
        with open(os.path.join(ctx.cwd, "package.json"), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}
