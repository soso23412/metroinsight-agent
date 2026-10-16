"""Check the tracked publishable surface; never read ignored private source data."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PARTS = {".venv", "legacy", "MediaCrawler", "browser_data", "wheels", ".cache"}
FORBIDDEN_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".xlsx", ".xls", ".docx", ".rar"}
SECRET = re.compile(
    r"sk-[A-Za-z0-9_-]{20,}|github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"
)


def main() -> int:
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    failures = []
    checked = 0
    for name in filter(None, names):
        path = ROOT / name
        relative = Path(name)
        if (
            set(relative.parts) & FORBIDDEN_PARTS
            or relative.suffix in FORBIDDEN_SUFFIXES
            or (relative.name.startswith(".env") and relative.name != ".env.example")
        ):
            failures.append((name, "private_file_type"))
            continue
        if path.stat().st_size > 2_000_000:
            failures.append((name, "unexpected_large_file"))
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        # Print filenames only, never matching values.
        if SECRET.search(text):
            failures.append((name, "possible_secret"))
        checked += 1
    for name, reason in failures:
        print(f"FAIL: {name}: {reason}")
    print(f"Checked {checked} tracked text files; findings={len(failures)}")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
