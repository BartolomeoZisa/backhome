#!/usr/bin/env python3
"""Check private-file safeguards without displaying private file contents.

    python3 scripts/check_privacy.py            # checks the repository
    python3 scripts/check_privacy.py --strict   # also require the local/ files to exist

Checks: required tracked files exist; private paths are git-ignored; nothing under local/ is
tracked; tracked/untracked-but-not-ignored text files do not contain obvious personal data
(absolute home-directory paths, e-mail addresses). It only reports file names and line numbers.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    "AGENTS.md",
    ".gitignore",
    "templates/trip.example.md",
    "templates/traveller.example.md",
    "templates/config.example.json",
    "templates/plan.md",
)
LOCAL_FILES = ("local/trip.md", "local/traveller.md", "local/config.json")
PRIVATE_PATHS = (
    "local/trip.md",
    "local/traveller.md",
    "local/config.json",
    "local/runs/example.md",
    "local/browser-profile/example",
    ".env",
)
# Patterns that suggest personal data inside files that could be committed.
LEAK_PATTERNS = {
    "absolute home path": re.compile(r"/(?:home|Users)/[A-Za-z0-9._-]+/"),
    "e-mail address": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
}
ALLOWED_EMAILS = ("noreply@", "example.com", "example.org", "users.noreply.github.com")
TEXT_SUFFIXES = {".md", ".py", ".json", ".txt", ".toml", ".yml", ".yaml", ".cfg", ".ini", ""}


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)


def committable_files() -> list[str]:
    """Tracked files plus untracked files that git would not ignore."""
    result = git("ls-files", "--cached", "--others", "--exclude-standard")
    return [f for f in result.stdout.splitlines() if f]


def scan_for_leaks(errors: list[str]) -> None:
    for rel in committable_files():
        path = ROOT / rel
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES or path.stat().st_size > 1_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for name, pattern in LEAK_PATTERNS.items():
                for match in pattern.finditer(line):
                    if name == "e-mail address" and any(a in match.group(0) for a in ALLOWED_EMAILS):
                        continue
                    errors.append(f"possible {name} in committable file {rel}:{lineno}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--strict", action="store_true", help="fail if the local/ files do not exist yet")
    args = parser.parse_args()
    errors: list[str] = []
    notes: list[str] = []

    for relative_path in REQUIRED_FILES:
        if not (ROOT / relative_path).is_file():
            errors.append(f"missing required file: {relative_path}")
    for relative_path in LOCAL_FILES:
        if not (ROOT / relative_path).is_file():
            (errors if args.strict else notes).append(f"missing {relative_path} (run scripts/init_local.py)")

    if not (ROOT / ".git").exists():
        errors.append("not a Git repository; cannot verify ignore rules")
    else:
        for relative_path in PRIVATE_PATHS:
            if git("check-ignore", "--quiet", "--", relative_path).returncode != 0:
                errors.append(f"not git-ignored: {relative_path}")
        tracked_private = git("ls-files", "--", "local")
        if tracked_private.returncode != 0:
            errors.append("could not inspect tracked private paths")
        elif tracked_private.stdout.strip():
            errors.append("one or more paths under local/ are tracked")
        scan_for_leaks(errors)

    for note in notes:
        print(f"NOTE: {note}")
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print("OK: required files exist, private local paths are git-ignored, no obvious personal data in committable files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
