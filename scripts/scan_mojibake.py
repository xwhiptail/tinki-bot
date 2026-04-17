#!/usr/bin/env python3
"""Scan the repo for mojibake — UTF-8 bytes misread as latin-1/cp1252.

Run standalone:   python scripts/scan_mojibake.py
Exits 0 if clean, 1 if mojibake found.
"""
import os
import sys
from pathlib import Path

# Mojibake patterns: each (bad_sequence, correct_char_description)
# Written as Unicode escapes so the file itself never contains the bad bytes.
MOJIBAKE_PATTERNS: list[tuple[str, str]] = [
    ("\u00e2\u0080\u0099", "right single quote \u2019"),
    ("\u00e2\u0080\u009c", "left double quote \u201c"),
    ("\u00e2\u0080\u009d", "right double quote \u201d"),
    ("\u00e2\u0080\u0094", "em dash \u2014"),
    ("\u00e2\u0080\u0093", "en dash \u2013"),
    ("\u00e2\u0080\u0098", "left single quote \u2018"),
    ("\u00e2\u0080\u00a6", "ellipsis \u2026"),
    ("\u00c3\u00a9", "\u00e9"),
    ("\u00c3\u00a0", "\u00e0"),
    ("\u00c3\u00a8", "\u00e8"),
    ("\u00c2\u00a0", "non-breaking space"),
]

SKIP_DIRS = {".git", "__pycache__", ".venv", "myenv", "node_modules", ".mypy_cache"}
SCAN_EXTS = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml"}
# Skip this file itself — it deliberately contains the bad sequences as string literals
THIS_FILE = Path(__file__).resolve()


def scan(root: str = ".") -> list[tuple[str, int, str, str]]:
    hits = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for filename in files:
            if not any(filename.endswith(ext) for ext in SCAN_EXTS):
                continue
            path = Path(dirpath) / filename
            if path.resolve() == THIS_FILE:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                hits.append((str(path), 0, "FILE", "not valid UTF-8"))
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                for bad, label in MOJIBAKE_PATTERNS:
                    if bad in line:
                        hits.append((str(path), lineno, label, line.strip()[:120]))
                        break
    return hits


def main() -> int:
    hits = scan()
    if not hits:
        print("No mojibake found.")
        return 0
    for path, lineno, label, snippet in hits:
        line = f"{path}:{lineno} [{label}]: {snippet}"
        print(line.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))
    print(f"\n{len(hits)} mojibake hit(s) found.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
