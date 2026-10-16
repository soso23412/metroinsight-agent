"""Verify v0.2.0 package surfaces, including built-from-sdist browser resources."""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path

from metro_agent import __version__


def main() -> int:
    stem = f"metroinsight_agent-{__version__}"
    wheel = Path("dist") / f"{stem}-py3-none-any.whl"
    sdist = Path("dist") / f"{stem}.tar.gz"
    with zipfile.ZipFile(wheel) as archive:
        wheel_names = archive.namelist()
    with tarfile.open(sdist) as archive:
        source_names = archive.getnames()
    for names in (wheel_names, source_names):
        for name in names:
            parts = set(Path(name).parts)
            if parts & {"legacy", "MediaCrawler", ".venv", ".cache", "browser_data", "artifacts"}:
                raise ValueError("private_directory_in_distribution")
            if Path(name).suffix in {".db", ".sqlite3", ".xlsx", ".docx", ".rar"}:
                raise ValueError("private_data_type_in_distribution")
            if Path(name).name.startswith(".env") and Path(name).name != ".env.example":
                raise ValueError("environment_file_in_distribution")
    required = {
        "metro_agent/api/web/index.html",
        "metro_agent/api/web/app.js",
        "metro_agent/resources/demo.json",
        "metro_agent/resources/contracts.json",
    }
    if not required <= set(wheel_names):
        raise ValueError("missing_runtime_resource")
    print(
        f"{__version__}: wheel={len(wheel_names)} entries, sdist={len(source_names)} entries; public surface and runtime resources verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
