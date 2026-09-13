"""Ready-made prompt styles, and the sample data that previews them."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

BUNDLED_DIR = Path(__file__).parent / "presets"
USER_DIR = "~/.zem/prompts"


@dataclass
class Preset:
    """One named prompt configuration."""

    name: str
    description: str = ""
    format: str = ""
    right_format: str = ""
    modules: dict = field(default_factory=dict)
    origin: str = "bundled"

    def as_config(self) -> dict:
        return {
            "format": self.format,
            "right_format": self.right_format,
            "modules": self.modules,
        }


def load_presets(user_dir: str = USER_DIR) -> dict:
    """Every preset, bundled first so a user's own replaces it by name."""
    presets: dict = {}
    for directory, origin in ((BUNDLED_DIR, "bundled"), (Path(user_dir).expanduser(), "user")):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            if path.name.startswith("."):
                continue
            preset = _read(path, origin)
            if preset is not None:
                presets[preset.name] = preset
    return presets


def _read(path: Path, origin: str) -> Optional[Preset]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("prompt preset %s: %s", path, exc)
        return None
    if not isinstance(data, dict) or "format" not in data:
        log.warning("prompt preset %s: not a preset", path)
        return None
    return Preset(
        name=str(data.get("name") or path.stem),
        description=str(data.get("description", "")),
        format=str(data["format"]),
        right_format=str(data.get("right_format", "")),
        modules=data.get("modules") or {},
        origin=origin,
    )


#: What each module shows in a preview, so a preset can be seen from
#: anywhere -- outside a repository, with no virtualenv, on a first run.
SAMPLE_VARIABLES: dict = {
    "venv": {"name": ".venv"},
    "exit_code": {"code": "0"},
    "path": {"path": "~ project"},
    "git": {"branch": "main", "status": "*"},
    "symbol": {"symbol": "#"},
    "duration": {"duration": "1.2s"},
    "time": {"time": "09:41:00"},
    "user": {"user": "you"},
    "host": {"host": "laptop"},
    "jobs": {"count": "2"},
}
