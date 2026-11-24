"""Shared helpers for the backhome scripts (standard library only).

Normalised leg record (one JSON object per line, "JSON Lines"):

    id        unique string
    mode      "flight" | "bus" | "train" | "ferry"
    from, to  node codes, e.g. IATA airport codes or labels you chose ("PRAGUE-BUS")
    dep, arr  local wall-clock times, "YYYY-MM-DDTHH:MM" (no timezone; local to each end)
    price     number in `currency`, or null when unknown (never treated as zero)
    currency  ISO code
    operator  free text
    number    flight/service number, may be empty
    label     short human description
    url       the request URL or page the data came from
    accessed  ISO timestamp with offset, when the data was fetched
    source    which script/API produced it
    notes     caveats (e.g. "base fare, bags excluded")
    through   true when the record already bundles several segments on one ticket
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import time
import urllib.error
import urllib.request
from typing import Iterable, Iterator

USER_AGENT = "Mozilla/5.0 (compatible; backhome-research/1.0)"


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def parse_dates(spec: str) -> list[str]:
    """'2026-12-17..2026-12-19' or '2026-12-17,2026-12-20' -> list of ISO dates."""
    out: list[str] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if ".." in part:
            a, b = (dt.date.fromisoformat(x) for x in part.split(".."))
            if b < a:
                raise ValueError(f"empty date range: {part}")
            d = a
            while d <= b:
                out.append(d.isoformat())
                d += dt.timedelta(days=1)
        else:
            out.append(dt.date.fromisoformat(part).isoformat())
    return out


def http_get_json(url: str, *, retries: int = 3, timeout: int = 30, pause: float = 2.0):
    """GET a URL and parse JSON. Returns (data_or_None, accessed_iso, error_or_None).

    Politeness is the caller's job (sleep between calls). A 4xx/5xx or non-JSON reply is
    reported, never bypassed: if an operator blocks automated access, mark the data
    unverified and ask the user (see AGENTS.md).
    """
    last_error = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", "replace")
            return json.loads(body), now_iso(), None
        except urllib.error.HTTPError as exc:  # blocked / not found: do not hammer
            return None, now_iso(), f"HTTP {exc.code}"
        except Exception as exc:  # network hiccup or bad JSON: retry a few times
            last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(pause * (attempt + 1))
    return None, now_iso(), last_error


def write_jsonl(path: str | pathlib.Path, legs: Iterable[dict], append: bool = True) -> int:
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with p.open("a" if append else "w", encoding="utf-8") as fh:
        for leg in legs:
            fh.write(json.dumps(leg, ensure_ascii=False) + "\n")
            n += 1
    return n


def read_jsonl(paths: Iterable[str | pathlib.Path]) -> Iterator[dict]:
    for path in paths:
        with pathlib.Path(path).open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield json.loads(line)


def local_minute(iso: str) -> str:
    """Trim an ISO timestamp (with or without offset) to local 'YYYY-MM-DDTHH:MM'."""
    return iso[:16]
