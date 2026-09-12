"""Finding, validating and caching hint specs."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Iterable, Optional

from zem.hints.spec import HintSpec, SpecError, parse_spec

log = logging.getLogger(__name__)

#: Colon-separated extra directories, searched between the bundled specs and
#: the user's own. Mirrors `ZEM_CONFIG_PATH` in spirit.
ENV_PATH = "ZEM_HINTS_PATH"

DEFAULT_USER_DIR = "~/.zem/hints"


class HintRegistry:
    """Every spec Zem knows about, keyed by command name.

    Directories are searched bundled-first, so a user's `~/.zem/hints/git.json`
    replaces the one we ship. Replacement, not merging: a half-merged tree
    of subcommands is impossible to reason about when something goes wrong.
    """

    def __init__(self, config=None, *, user_dir: Optional[str] = None,
                 extra_dirs: Iterable[str] = ()):
        self._bundled_dir = Path(__file__).parent / "data"
        if user_dir is None:
            user_dir = getattr(getattr(config, "hints", None), "user_dir", DEFAULT_USER_DIR)
        self._user_dir = Path(user_dir).expanduser()
        self._extra_dirs = [Path(p).expanduser() for p in extra_dirs]
        self._specs: Optional[dict[str, HintSpec]] = None
        self._errors: dict[str, list[str]] = {}

    def spec_dirs(self) -> list[tuple[Path, str]]:
        """Directories to scan, weakest first, each with its origin label."""
        dirs: list[tuple[Path, str]] = [(self._bundled_dir, "bundled")]
        for raw in os.environ.get(ENV_PATH, "").split(os.pathsep):
            if raw.strip():
                dirs.append((Path(raw.strip()).expanduser(), "user"))
        dirs += [(path, "plugin") for path in self._extra_dirs]
        dirs.append((self._user_dir, "user"))
        return dirs

    def load(self, force: bool = False) -> dict[str, HintSpec]:
        """Load every spec. Lazy: the shell's startup time is not free."""
        if self._specs is not None and not force:
            return self._specs

        specs: dict[str, HintSpec] = {}
        errors: dict[str, list[str]] = {}
        for directory, origin in self.spec_dirs():
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.json")):
                spec = self._read(path, origin, errors)
                if spec is None:
                    continue
                for name in spec.names():
                    specs[name] = spec

        self._specs, self._errors = specs, errors
        return specs

    def _read(self, path: Path, origin: str, errors: dict) -> Optional[HintSpec]:
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError as exc:
            errors[str(path)] = [f"invalid JSON: {exc}"]
            log.warning("hint spec %s: invalid JSON: %s", path, exc)
            return None
        except OSError as exc:
            errors[str(path)] = [f"cannot read: {exc}"]
            return None

        try:
            spec = parse_spec(data)
        except SpecError as exc:
            messages = exc.args[0] if isinstance(exc.args[0], list) else [str(exc)]
            errors[str(path)] = messages
            log.warning("hint spec %s is invalid: %s", path, "; ".join(messages))
            return None

        spec.origin = origin  # type: ignore[assignment]
        spec.source_path = str(path)
        return spec

    def get(self, command: str) -> Optional[HintSpec]:
        return self.load().get(command)

    def errors(self) -> dict[str, list[str]]:
        """Files that failed to load, as `path -> messages`."""
        self.load()
        return dict(self._errors)

    def reload(self) -> dict[str, HintSpec]:
        return self.load(force=True)
