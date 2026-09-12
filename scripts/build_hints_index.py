#!/usr/bin/env python3
"""Regenerate `registry/index.json` from the specs in `registry/hints/`.

Run after adding or editing a spec in the registry:

    uv run python scripts/build_hints_index.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "registry"
HINTS = REGISTRY / "hints"


def main() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    from zem.hints.spec import parse_spec

    entries = []
    for path in sorted(HINTS.glob("*.json")):
        raw = path.read_bytes()
        try:
            spec = parse_spec(json.loads(raw))
        except Exception as exc:  # noqa: BLE001 - report and fail the build
            print(f"{path.name}: {exc}", file=sys.stderr)
            return 1
        entries.append({
            "name": path.stem,
            "command": spec.command,
            "aliases": spec.aliases,
            "description": spec.description,
            "subcommands": len(spec.subcommands),
            "size": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        })

    index = {"schema_version": 1, "hints": entries}
    (REGISTRY / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {REGISTRY / 'index.json'} with {len(entries)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
