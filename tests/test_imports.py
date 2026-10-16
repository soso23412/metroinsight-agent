import platform
import subprocess
import sys
from pathlib import Path

import metro_agent


def test_standard_library_platform_is_not_shadowed():
    assert platform.system()
    assert "legacy" not in platform.__file__
    assert hasattr(metro_agent, "__version__")


def test_cli_works_outside_project(tmp_path: Path):
    result = subprocess.run(
        [sys.executable, "-m", "metro_agent", "--version"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == metro_agent.__version__
