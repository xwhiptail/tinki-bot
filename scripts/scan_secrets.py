#!/usr/bin/env python3
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

DIRECT_SECRET_PATTERNS = [
    ("GitHub fine-grained PAT", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("GitHub classic token", re.compile(r"\bghp_[A-Za-z0-9]{20,}\b")),
    ("OpenAI key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z\-_]{20,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("Private key block", re.compile(r"-----BEGIN (RSA|OPENSSH|EC|DSA) PRIVATE KEY-----")),
]

ASSIGNMENT_RE = re.compile(
    r"^\s*(?:export\s+)?"
    r"(?P<name>OPENAI_API_KEY|DISCORD|GIPHY|GITHUB_TOKEN|AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY)"
    r"\s*=\s*"
    r"(?P<value>.+?)"
    r"\s*$"
)

SAFE_VALUE_HINTS = {
    "",
    "''",
    '""',
}

SAFE_SUBSTRINGS = (
    "example",
    "your-",
    "your_",
    "changeme",
    "replace-me",
    "<",
    ">",
)

TEXT_EXTENSIONS = {
    ".py",
    ".sh",
    ".ps1",
    ".md",
    ".txt",
    ".yml",
    ".yaml",
    ".json",
    ".toml",
    ".ini",
    ".cfg",
    ".env",
    ".example",
    ".service",
}


def run_git(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def tracked_files() -> list[Path]:
    return [REPO_ROOT / rel for rel in run_git("ls-files")]


def staged_files() -> list[Path]:
    return [REPO_ROOT / rel for rel in run_git("diff", "--cached", "--name-only", "--diff-filter=ACMR")]


def should_read(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.parts and ".git" in path.parts:
        return False
    if path.suffix.lower() in TEXT_EXTENSIONS:
        return True
    return path.name in {".env", ".env.example", ".gitignore"}


def normalize_value(raw: str) -> str:
    value = raw.split("#", 1)[0].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value.strip()


def looks_safe_template(value: str) -> bool:
    lowered = value.lower()
    if value in SAFE_VALUE_HINTS:
        return True
    return any(hint in lowered for hint in SAFE_SUBSTRINGS)


def scan_file(path: Path) -> list[str]:
    findings: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return findings

    rel = path.relative_to(REPO_ROOT)
    for lineno, line in enumerate(text.splitlines(), start=1):
        for label, pattern in DIRECT_SECRET_PATTERNS:
            if pattern.search(line):
                findings.append(f"{rel}:{lineno}: possible {label}")

        match = ASSIGNMENT_RE.match(line)
        if not match:
            continue
        value = normalize_value(match.group("value"))
        if value and not looks_safe_template(value):
            findings.append(f"{rel}:{lineno}: possible hard-coded {match.group('name')}")
    return findings


def all_files() -> list[Path]:
    files: list[Path] = []
    for root, dirs, names in os.walk(REPO_ROOT):
        if ".git" in dirs:
            dirs.remove(".git")
        if ".venv" in dirs:
            dirs.remove(".venv")
        if "venv" in dirs:
            dirs.remove("venv")
        for name in names:
            files.append(Path(root) / name)
    return files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan repo files for likely secrets.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--staged", action="store_true", help="Scan staged files only.")
    group.add_argument("--all-files", action="store_true", help="Scan all files under the repo root.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.staged:
        candidates = staged_files()
    elif args.all_files:
        candidates = all_files()
    else:
        candidates = tracked_files()

    findings: list[str] = []
    for path in candidates:
        if should_read(path):
            findings.extend(scan_file(path))

    if findings:
        print("Secret scan found potential issues:", file=sys.stderr)
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        return 1

    print("Secret scan passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
