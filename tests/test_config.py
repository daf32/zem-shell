"""Tests for config-file bootstrap in axonix.config.settings."""

import json
import subprocess
import sys


def test_first_run_creates_valid_config(tmp_path):
    """Importing settings with a missing AXONIX_CONFIG_PATH must create a
    valid JSON file instead of crashing on the half-written empty file.

    Runs in a subprocess because `_ensure_config_file` fires at import time
    and the module is already imported in the test process.
    """
    cfg = tmp_path / "nested" / "config.json"
    code = (
        "from axonix.config.settings import AppConfig; "
        "print(AppConfig().active_theme)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        env={"AXONIX_CONFIG_PATH": str(cfg), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "default"
    assert json.loads(cfg.read_text())["active_theme"] == "default"
