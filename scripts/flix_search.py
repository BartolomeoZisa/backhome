#!/usr/bin/env python3
"""Search FlixBus (public search API) and write normalised legs.

Examples
  python3 scripts/flix_search.py --from "Berlin" --from-code BER-BUS \
      --to "Prague" --to-code PRG-BUS --dates 2026-12-17..2026-12-19 \
      --out local/runs/<run>/legs/flix.jsonl --raw-dir local/runs/<run>/raw/flix
  python3 scripts/flix_search.py --lookup "Prague airport"      # list matching city/station ids

The API is the one the public website uses. Prices are taken as `total_with_platform_fee`
when present (more honest than the headline price). Be polite: one request at a time with a pause.
Use --direct-only to keep single-ride results; multi-ride (changes) results are kept as one
`through` record on a single FlixBus ticket.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _common import http_get_json, now_iso, parse_dates, write_jsonl  # noqa: E402

BASE = "https://global.api.flixbus.com"


def lookup(query: str, lang: str = "en", country: str = "de") -> list[dict]:
    qs = urllib.parse.urlencode({"q": query, "lang": lang, "country": country,
                                 "flixbus_cities_only": "false", "stations": "false", "popularity": "true"})
    data, _, err = http_get_json(f"{BASE}/search/autocomplete/cities?{qs}")
    if err or not isinstance(data, list):
        raise SystemExit(f"lookup failed: {err}")
    return [{"id": c.get("id"), "name": c.get("name"), "country": c.get("country")} for c in data]


def search_url(from_id: str, to_id: str, date_iso: str, currency: str, locale: str, after_midnight: bool) -> str:
    y, m, d = date_iso.split("-")
    qs = urllib.parse.urlencode({
        "from_city_id": from_id, "to_city_id": to_id, "departure_date": f"{d}.{m}.{y}",
        "products": '{"adult":1}', "currency": currency, "locale": locale,
        "search_by": "cities", "include_after_midnight_rides": 1 if after_midnight else 0})
    return f"{BASE}/search/service/v4/search?{qs}"


def legs_from_response(raw: dict, *, from_code: str, to_code: str, currency: str, url: str,
                       accessed: str, direct_only: bool = False) -> list[dict]:
    """Convert one search response into normalised legs (only 'available' results)."""
    stations = {s.get("id"): s.get("name") for s in (raw.get("stations") or {}).values()} \
        if isinstance(raw.get("stations"), dict) else {}
    legs = []
    for trip in raw.get("trips", []):
        results = trip.get("results")
        if not isinstance(results, dict):
            continue
        for rid, r in results.items():
            if r.get("status") != "available":
                continue
            rides = r.get("legs") or []
            if direct_only and len(rides) > 1:
                continue
            price_obj = r.get("price") or {}
            price = price_obj.get("total_with_platform_fee", price_obj.get("total"))
            dep, arr = r["departure"]["date"][:16], r["arrival"]["date"][:16]
            via = ""
            if len(rides) > 1:
                names = [stations.get((x.get("arrival") or {}).get("station_id")) or "?" for x in rides[:-1]]
                via = " via " + ", ".join(names)
            dep_name = stations.get(r["departure"].get("station_id")) or from_code
            arr_name = stations.get(r["arrival"].get("station_id")) or to_code
            legs.append({
                "id": f"flix:{rid}", "mode": "bus", "from": from_code, "to": to_code,
                "dep": dep, "arr": arr, "price": price, "currency": currency,
                "operator": "FlixBus", "number": "", "through": len(rides) > 1,
                "label": f"{dep_name} -> {arr_name}{via}", "url": url, "accessed": accessed,
                "source": "flixbus-search-api",
                "notes": "price includes platform fee" if "total_with_platform_fee" in price_obj else "platform fee may be extra",
            })
    return legs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lookup", help="print city/station ids matching this text and exit")
    ap.add_argument("--from", dest="frm", help="origin name (resolved by autocomplete) or use --from-id")
    ap.add_argument("--to", help="destination name or use --to-id")
    ap.add_argument("--from-id")
    ap.add_argument("--to-id")
    ap.add_argument("--from-code", help="node code written to legs (default: from name)")
    ap.add_argument("--to-code")
    ap.add_argument("--dates", help="e.g. 2026-12-17..2026-12-23 or comma list")
    ap.add_argument("--currency", default="EUR")
    ap.add_argument("--locale", default="en")
    ap.add_argument("--direct-only", action="store_true")
    ap.add_argument("--no-after-midnight", action="store_true", help="exclude rides just after midnight")
    ap.add_argument("--pause", type=float, default=1.0, help="seconds between requests")
    ap.add_argument("--out", help="legs .jsonl (appended)")
    ap.add_argument("--raw-dir", help="save raw responses here as evidence")
    a = ap.parse_args(argv)

    if a.lookup:
        for c in lookup(a.lookup):
            print(f"{c['id']}\t{c['name']}\t{c['country']}")
        return 0
    if not (a.dates and a.out and (a.frm or a.from_id) and (a.to or a.to_id)):
        ap.error("need --from/--from-id, --to/--to-id, --dates and --out (or --lookup)")

    from_id = a.from_id or lookup(a.frm, a.locale)[0]["id"]
    to_id = a.to_id or lookup(a.to, a.locale)[0]["id"]
    from_code, to_code = a.from_code or a.frm or from_id, a.to_code or a.to or to_id
    total = 0
    for date in parse_dates(a.dates):
        url = search_url(from_id, to_id, date, a.currency, a.locale, not a.no_after_midnight)
        raw, accessed, err = http_get_json(url)
        if err or not isinstance(raw, dict):
            print(f"{date}: FAILED ({err}); not treated as 'no service'", file=sys.stderr)
        else:
            if a.raw_dir:
                p = pathlib.Path(a.raw_dir)
                p.mkdir(parents=True, exist_ok=True)
                (p / f"{from_code}-{to_code}-{date}.json").write_text(json.dumps(raw))
            legs = legs_from_response(raw, from_code=from_code, to_code=to_code, currency=a.currency,
                                      url=url, accessed=accessed, direct_only=a.direct_only)
            total += write_jsonl(a.out, legs)
            print(f"{date}: {len(legs)} legs")
        time.sleep(a.pause)
    print(f"wrote {total} legs to {a.out} at {now_iso()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
