#!/usr/bin/env python3
"""Fail if a change edits a CHANGELOG section that is already released.

A branch written before someone else's release, then rebased onto it, has
its CHANGELOG hunk land inside the section that release just closed — so
the entry describes a version that never contained it, and the new
`[Unreleased]` ships empty. It has happened twice; a machine should catch
it rather than a reader.

    python scripts/check_changelog.py [base-ref]
"""

from __future__ import annotations

import re
import subprocess
import sys

CHANGELOG = "CHANGELOG.md"
VERSION_HEADING = re.compile(r"^## \[\d")


def released_line_numbers(text: str) -> set:
    """Line numbers (1-based) that belong to an already-released section."""
    released: set = set()
    inside = False
    for number, line in enumerate(text.splitlines(), start=1):
        if line.startswith("## ["):
            inside = bool(VERSION_HEADING.match(line))
        if inside:
            released.add(number)
    return released


def changed_line_numbers(base: str) -> set:
    """Lines this branch adds to the changelog, by their new line number."""
    diff = subprocess.run(
        ["git", "diff", "--unified=0", f"{base}...HEAD", "--", CHANGELOG],
        capture_output=True, text=True, check=False,
    ).stdout

    changed: set = set()
    line_number = 0
    for line in diff.splitlines():
        header = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
        if header:
            line_number = int(header.group(1))
            continue
        if line.startswith("+") and not line.startswith("+++"):
            changed.add(line_number)
            line_number += 1
    return changed


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
    # Read the committed file, not the working tree: the line numbers come
    # from a diff of commits, and mixing the two compares different files.
    committed = subprocess.run(
        ["git", "show", f"HEAD:{CHANGELOG}"],
        capture_output=True, text=True, check=False,
    )
    if committed.returncode != 0:
        print(f"{CHANGELOG}: not in HEAD", file=sys.stderr)
        return 1
    text = committed.stdout

    offenders = sorted(changed_line_numbers(base) & released_line_numbers(text))
    if not offenders:
        return 0

    lines = text.splitlines()
    print(
        f"{CHANGELOG}: this change writes into an already-released section.\n"
        "Move the entry up into '## [Unreleased]' — most likely the branch was\n"
        "rebased across a release and the hunk landed below the new heading.\n",
        file=sys.stderr,
    )
    for number in offenders[:10]:
        print(f"  line {number}: {lines[number - 1]}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
