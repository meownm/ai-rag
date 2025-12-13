#!/usr/bin/env python3
"""Detect merge conflict markers in tracked files."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# Match lines that start with the classic conflict markers
CONFLICT_RE = re.compile(r"^(<{7}|={7}|>{7})", re.MULTILINE)


def iter_tracked_files() -> list[Path]:
    output = subprocess.check_output(["git", "ls-files"], text=True)
    return [Path(line.strip()) for line in output.splitlines() if line.strip()]


def has_conflict_marker(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return False
    return bool(CONFLICT_RE.search(text))


def main() -> int:
    conflicted = [path for path in iter_tracked_files() if path.is_file() and has_conflict_marker(path)]
    if conflicted:
        sys.stderr.write("Found merge conflict markers in:\n")
        for path in conflicted:
            sys.stderr.write(f" - {path}\n")
        return 1

    print("No conflict markers detected in tracked files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
