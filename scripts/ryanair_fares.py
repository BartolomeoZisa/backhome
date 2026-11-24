#!/usr/bin/env python3
"""Ryanair public timetable + fare-finder -> normalised legs.

Example
  python3 scripts/ryanair_fares.py --from FMM --to CTA --dates 2026-12-17..2026-12-23 \
      --out local/runs/<run>/legs/ryanair.jsonl --raw-dir local/runs/<run>/raw/ryanair

What it is: the per-flight lowest *base* fare shown by Ryanair's public fare finder, plus the
public schedule. It is NOT a checkout quote: bags, seats and payment fees are excluded, and the
booking/availability API may refuse automated requests (HTTP 409/403). Never bypass that; label
the fare "fare-finder snapshot, unverified at checkout" in the plan.
A route that does not exist returns no timetable; that is reported, not guessed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
import time
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _common import http_get_json, now_iso, parse_dates, write_jsonl  # noqa: E402

API = "https://services-api.ryanair.com"


def timetable_url(a: str, b: str, year: int, month: int) -> str:
    return f"{API}/timtbl/3/schedules/{a}/{b}/years/{year}/months/{month}"


def fare_url(a: str, b: str, date: str, dep_time: str, currency: str, market: str) -> str:
    qs = urllib.parse.urlencode({
        "departureAirportIataCode": a, "arrivalAirportIataCode": b,
        "outboundDepartureDateFrom": date, "outboundDepartureDateTo": date,
        "outboundDepartureTimeFrom": dep_time, "outboundDepartureTimeTo": dep_time,
        "currency": currency, "market": market})
    return f"{API}/farfnd/v4/oneWayFares?{qs}"


def flights_in_timetable(tt: dict, year: int, month: int, wanted: set[str]) -> list[dict]:
    out = []
    for day in (tt or {}).get("days", []):
        date = f"{year}-{month:02d}-{int(day['day']):02d}"
        if date in wanted:
            for fl in day.get("flights", []):
                out.append({"date": date, "number": f"FR{fl['number']}",
                            "dep": fl["departureTime"], "arr": fl["arrivalTime"]})
    return out


def to_leg(frm: str, to: str, fl: dict, price, currency: str, url: str, accessed: str) -> dict:
    dep = f"{fl['date']}T{fl['dep']}"
    arr_dt = dt.datetime.fromisoformat(f"{fl['date']}T{fl['arr']}")
    if arr_dt <= dt.datetime.fromisoformat(dep):  # lands after midnight (times are local wall-clock)
        arr_dt += dt.timedelta(days=1)
    return {"id": f"ryanair:{fl['number']}:{fl['date']}", "mode": "flight", "from": frm, "to": to,
            "dep": dep, "arr": arr_dt.isoformat(timespec="minutes"), "price": price, "currency": currency,
            "operator": "Ryanair", "number": fl["number"], "through": False,
            "label": f"{fl['number']} {frm}->{to}", "url": url, "accessed": accessed,
            "source": "ryanair-farfnd", "notes": "base fare, bags/seat excluded; not a checkout quote"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="frm", required=True, help="IATA code")
    ap.add_argument("--to", required=True, help="IATA code")
    ap.add_argument("--dates", required=True)
    ap.add_argument("--currency", default="EUR")
    ap.add_argument("--market", default="en-gb")
    ap.add_argument("--pause", type=float, default=0.5)
    ap.add_argument("--out", required=True)
    ap.add_argument("--raw-dir")
    a = ap.parse_args(argv)

    dates = parse_dates(a.dates)
    wanted = set(dates)
    months = sorted({(int(d[:4]), int(d[5:7])) for d in dates})
    total = 0
    for year, month in months:
        turl = timetable_url(a.frm, a.to, year, month)
        tt, _, err = http_get_json(turl)
        if err or not isinstance(tt, dict) or "days" not in tt:
            print(f"{a.frm}->{a.to} {year}-{month:02d}: no timetable ({err or 'empty'}); route may not exist", file=sys.stderr)
            continue
        if a.raw_dir:
            p = pathlib.Path(a.raw_dir)
            p.mkdir(parents=True, exist_ok=True)
            (p / f"tt-{a.frm}-{a.to}-{year}-{month:02d}.json").write_text(json.dumps(tt))
        legs = []
        for fl in flights_in_timetable(tt, year, month, wanted):
            furl = fare_url(a.frm, a.to, fl["date"], fl["dep"], a.currency, a.market)
            fares, accessed, ferr = http_get_json(furl)
            price = None
            if isinstance(fares, dict) and fares.get("fares"):
                price = fares["fares"][0]["outbound"]["price"]["value"]
            elif ferr:
                print(f"  {fl['number']} {fl['date']}: fare lookup failed ({ferr}); price left null", file=sys.stderr)
            legs.append(to_leg(a.frm, a.to, fl, price, a.currency, furl, accessed))
            time.sleep(a.pause)
        total += write_jsonl(a.out, legs)
        print(f"{a.frm}->{a.to} {year}-{month:02d}: {len(legs)} flights")
    print(f"wrote {total} legs to {a.out} at {now_iso()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
