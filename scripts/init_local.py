#!/usr/bin/env python3
"""Create the private local/ workspace from the tracked templates (never overwrites).

    python3 scripts/init_local.py

Creates (if missing): local/trip.md, local/traveller.md, local/config.json, local/runs/.
Everything under local/ is git-ignored. Fill the files in; never put payment-card numbers,
CVVs, passwords or identity-document scans in them.
"""

from __future__ import annotations

import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parents[1]
COPIES = {
    "templates/trip.example.md": "local/trip.md",
    "templates/traveller.example.md": "local/traveller.md",
    "templates/config.example.json": "local/config.json",
}


def main() -> int:
    (ROOT / "local/runs").mkdir(parents=True, exist_ok=True)
    for src, dst in COPIES.items():
        target = ROOT / dst
        if target.exists():
            print(f"kept    {dst} (already exists)")
            continue
        shutil.copyfile(ROOT / src, target)
        print(f"created {dst}")
    print("Next: edit local/trip.md and local/config.json, then run scripts/check_privacy.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
