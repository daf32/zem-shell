"""Version is sourced from package metadata and exposed via `zem --version`."""

import re
import subprocess
import sys

import zem


def test_dunder_version_is_pep440():
    # Either the installed metadata version or the documented fallback.
    pep440 = r"^\d+(\.\d+)*([abc]|rc)?\d*(\.post\d+)?(\.dev\d+)?(\+\w+)?$"
    assert re.match(pep440, zem.__version__)


def test_cli_version_flag_prints_version():
    result = subprocess.run(
        [sys.executable, "-m", "zem.main", "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"zem {zem.__version__}"
