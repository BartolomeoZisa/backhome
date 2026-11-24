#!/usr/bin/env python3
"""Join separately researched legs into complete journeys and rank them.

Input : one or more legs .jsonl files (see scripts/_common.py for the record format) and a
        JSON config (copy templates/config.example.json to local/config.json).
Output: <out>.md (readable tables) and <out>.json (everything).

What it does
  * chains up to `max_legs` legs from origin to destination (and back) with realistic minimum
    transfer buffers per mode pair; every chain of more than one leg is flagged SEPARATE TICKETS;
  * optional rules (all off unless configured): no overnight travel, earliest start hour, latest arrival / earliest departure at the destination
    gateway (your last-mile check), budget, resident/student fare discounts;
  * optional stopovers (e.g. a free night at a friend's/own home) joining two same-day chains;
  * optional round-trip pairing under a total budget.
It never invents data: legs with an unknown price are dropped and counted, and nothing is
"verified" - prices are whatever the provider scripts captured, with their access timestamps.

Usage
  python3 scripts/combine_legs.py --config local/config.json \
      --legs local/runs/<run>/legs/*.jsonl --out local/runs/<run>/combined [--top 3] [--pairs 10]
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import itertools
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _common import read_jsonl  # noqa: E402

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DEFAULT_BUFFERS = {"bus>flight": 150, "train>flight": 150, "flight>bus": 120, "flight>train": 90,
                   "flight>flight": 180, "bus>bus": 45, "train>train": 30, "bus>train": 45,
                   "train>bus": 45, "default": 90}


# ---------- loading ----------
def parse_dt(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s[:16])


def load_config(path: str | pathlib.Path) -> dict:
    cfg = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    cfg.setdefault("max_legs", 2)
    # Preferences are opt-in: the defaults below impose no personal taste. Ask the traveller
    # (AGENTS.md) and set them in local/config.json only when they are wanted.
    cfg.setdefault("max_layover_hours", 24)   # longest wait between two legs
    cfg.setdefault("min_start_hour", 0)       # 0 = no earliest start; e.g. 5 drops 02:45 departures
    cfg.setdefault("no_overnight", False)     # True = a journey must start and end on the same calendar day
    cfg.setdefault("thin_margin_min", 30)
    cfg.setdefault("budget_scope", "round_trip")  # or "per_direction"
    cfg["buffers_min"] = {**DEFAULT_BUFFERS, **cfg.get("buffers_min", {})}
    for key in ("origin", "destination"):
        if not cfg.get(key):
            raise ValueError(f"config needs a non-empty list '{key}'")
    for key in ("outbound_window", "return_window"):
        if key not in cfg or len(cfg[key]) != 2:
            raise ValueError(f"config needs '{key}': [first_date, last_date]")
    return cfg


def load_legs(paths, cfg: dict) -> tuple[list[dict], collections.Counter]:
    """Read legs, parse times, drop unpriced ones (counted) and apply configured discounts."""
    dropped: collections.Counter = collections.Counter()
    legs, currencies = [], set()
    for rec in read_jsonl(paths):
        if rec.get("price") is None:
            dropped[rec.get("source", "?")] += 1  # unknown price is never treated as zero
            continue
        leg = dict(rec)
        leg["dep_dt"], leg["arr_dt"] = parse_dt(rec["dep"]), parse_dt(rec["arr"])
        if leg["arr_dt"] < leg["dep_dt"]:
            dropped["arrival-before-departure"] += 1
            continue
        leg["price"] = float(rec["price"])
        currencies.add(rec.get("currency", cfg.get("currency", "EUR")))
        legs.append(leg)
    if len(currencies) > 1:
        raise ValueError(f"mixed currencies {sorted(currencies)}; convert before combining")
    return apply_discounts(legs, cfg.get("discounts", [])), dropped


def apply_discounts(legs: list[dict], rules: list[dict]) -> list[dict]:
    out = []
    for leg in legs:
        leg = dict(leg)
        for rule in rules:
            a, b = set(rule["between"][0]), set(rule["between"][1])
            modes = rule.get("modes", ["flight"])
            day = leg["dep_dt"].date().isoformat()
            if leg["mode"] not in modes:
                continue
            if not ((leg["from"] in a and leg["to"] in b) or (leg["from"] in b and leg["to"] in a)):
                continue
            if day < rule.get("valid_from", "0000-01-01") or day > rule.get("valid_to", "9999-12-31"):
                continue
            cut = min(leg["price"] * rule["percent"] / 100.0, rule.get("cap", float("inf")))
            leg["price_original"] = leg["price"]
            leg["price"] = round(leg["price"] - cut, 2)
            leg["discount"] = f"{rule.get('name', 'discount')}: -{cut:.2f} (ASSUMED eligible; verify rules)"
            break
        out.append(leg)
    return out


# ---------- chain search ----------
def connections(cfg: dict) -> dict[str, list[tuple[str, int]]]:
    """node -> [(node, extra_transfer_minutes)], always includes itself with 0."""
    conn: dict[str, list[tuple[str, int]]] = collections.defaultdict(list)
    for node in set(cfg["origin"]) | set(cfg["destination"]):
        conn[node].append((node, 0))
    for a, b, extra in cfg.get("equivalent_nodes", []):
        conn[a].append((b, int(extra)))
        conn[b].append((a, int(extra)))
    return conn


def _conn_for(conn, node):
    return conn[node] if node in conn else [(node, 0)]


def buffer_needed(cfg: dict, a: dict, b: dict) -> int:
    key = f"{a['mode']}>{b['mode']}"
    return cfg["buffers_min"].get(key, cfg["buffers_min"]["default"])


def find_chains(legs: list[dict], cfg: dict, starts: set[str], ends: set[str], window: tuple[str, str],
                *, max_legs: int | None = None, apply_rules: bool = True) -> list[dict]:
    """All chains from `starts` to `ends` whose first leg departs inside `window` (dates, inclusive)."""
    max_legs = max_legs or cfg["max_legs"]
    by_from: dict[str, list[dict]] = collections.defaultdict(list)
    for leg in legs:
        by_from[leg["from"]].append(leg)
    conn = connections(cfg)
    results = []

    def extend(chain, visited):
        last = chain[-1]
        if last["to"] in ends:
            results.append(chain)
        if len(chain) >= max_legs:
            return
        for node, extra in _conn_for(conn, last["to"]):
            for nxt in by_from.get(node, []):
                if nxt["to"] in visited:
                    continue
                gap = (nxt["dep_dt"] - last["arr_dt"]).total_seconds() / 60
                need = buffer_needed(cfg, last, nxt) + extra
                if need <= gap <= cfg["max_layover_hours"] * 60:
                    extend(chain + [nxt], visited | {nxt["to"]})

    for start in starts:
        for leg in by_from.get(start, []):
            day = leg["dep_dt"].date().isoformat()
            if window[0] <= day <= window[1]:
                extend([leg], {leg["from"], leg["to"]})
    return [make_itinerary(c, cfg) for c in results if not apply_rules or _basic_ok(c, cfg)]


def _basic_ok(chain: list[dict], cfg: dict) -> bool:
    s, e = chain[0]["dep_dt"], chain[-1]["arr_dt"]
    if cfg["no_overnight"] and s.date() != e.date():
        return False
    return s.hour >= cfg["min_start_hour"]


def make_itinerary(chain: list[dict], cfg: dict) -> dict:
    buffers = []
    for a, b in zip(chain, chain[1:]):
        gap = int((b["dep_dt"] - a["arr_dt"]).total_seconds() / 60)
        buffers.append({"at": a["to"], "minutes": gap, "needed": buffer_needed(cfg, a, b),
                        "thin": gap < buffer_needed(cfg, a, b) + cfg["thin_margin_min"]})
    start, end = chain[0]["dep_dt"], chain[-1]["arr_dt"]
    return {"legs": chain, "total": round(sum(l["price"] for l in chain), 2), "start": start, "end": end,
            "hours": round((end - start).total_seconds() / 3600, 1), "buffers": buffers,
            "separate_tickets": len(chain) > 1 and not all(l.get("through") for l in chain),
            "discounted": any("discount" in l for l in chain), "notes": []}


# ---------- last mile ----------
def _hhmm(s: str) -> float:
    h, m = s.split(":")
    return int(h) + int(m) / 60


def last_mile_check(it: dict, direction: str, cfg: dict) -> tuple[bool, str]:
    """Check the gateway-side time rule. Returns (ok, note)."""
    gateway = it["legs"][-1]["to"] if direction == "outbound" else it["legs"][0]["from"]
    if gateway in cfg.get("no_constraint_nodes", []):
        return True, f"{gateway}: no ground constraint (configured)"
    rule = cfg.get("last_mile", {}).get(direction, {}).get(gateway)
    if not rule:
        return True, f"{gateway}: last mile NOT checked (no rule configured)"
    when = it["end"] if direction == "outbound" else it["start"]
    day = when.date().isoformat()
    key = "latest_arrival" if direction == "outbound" else "earliest_departure"
    limit = (rule.get(f"date_{key}", {}).get(day)
             or rule.get(f"weekday_{key}", {}).get(WEEKDAYS[when.weekday()])
             or rule.get(key))
    if limit is None:
        return False, f"{gateway}: no service/limit defined for {day} (treated as infeasible)"
    hh = when.hour + when.minute / 60
    ok = hh <= _hhmm(limit) if direction == "outbound" else hh >= _hhmm(limit)
    word = "arrival by" if direction == "outbound" else "departure from"
    return ok, f"{gateway}: {word} {limit} on {day} {'OK' if ok else 'FAILS'}"


def find_itineraries(legs, cfg, direction: str) -> list[dict]:
    origin, dest = set(cfg["origin"]), set(cfg["destination"])
    starts, ends = (origin, dest) if direction == "outbound" else (dest, origin)
    window = tuple(cfg["outbound_window"] if direction == "outbound" else cfg["return_window"])
    out = []
    for it in find_chains(legs, cfg, starts, ends, window):
        ok, note = last_mile_check(it, direction, cfg)
        it["notes"].append(note)
        it["direction"] = direction
        if ok:
            out.append(it)
    return rank(out, cfg, direction)


def find_stopovers(legs, cfg, direction: str) -> list[dict]:
    """Join origin->S and S->destination (or reverse) with a free overnight stay at S."""
    so = cfg.get("stopovers")
    if not so:
        return []
    origin, dest = set(cfg["origin"]), set(cfg["destination"])
    starts, ends = (origin, dest) if direction == "outbound" else (dest, origin)
    window = tuple(cfg["outbound_window"] if direction == "outbound" else cfg["return_window"])
    out = []
    for node in so["nodes"]:
        firsts = find_chains(legs, cfg, starts, {node}, window)
        seconds = find_chains(legs, cfg, {node}, ends, window)
        for a, b in itertools.product(firsts, seconds):
            nights = (b["start"].date() - a["end"].date()).days
            if not so.get("min_nights", 1) <= nights <= so.get("max_nights", 7):
                continue
            if so.get("end_within_window", True) and b["end"].date().isoformat() > window[1]:
                continue
            joined = make_itinerary(a["legs"] + b["legs"], {**cfg, "no_overnight": False})
            joined["buffers"] = a["buffers"] + b["buffers"]
            joined["stopover"] = {"node": node, "nights": nights}
            joined["separate_tickets"] = True
            ok, note = last_mile_check(joined, direction, cfg)
            joined["notes"] = [f"stay {nights} night(s) at {node}", note]
            joined["direction"] = direction
            if ok:
                out.append(joined)
    return rank(out, cfg, direction)


def rank(its: list[dict], cfg: dict, direction: str) -> list[dict]:
    limit = cfg.get("max_total")
    if limit is not None and cfg["budget_scope"] == "per_direction":
        its = [i for i in its if i["total"] <= limit]
    return sorted(its, key=lambda i: (i["total"], i["hours"]))


def pair_round_trips(out_its: list[dict], ret_its: list[dict], cfg: dict, top: int = 10) -> list[dict]:
    limit = cfg.get("max_total")
    best: dict[tuple, dict] = {}
    for o in out_its:
        for r in ret_its:
            total = round(o["total"] + r["total"], 2)
            if limit is not None and total > limit:
                continue
            key = (o["start"].date(), r["start"].date(), o.get("stopover", {}).get("nights"), r.get("stopover", {}).get("nights"))
            if key not in best or total < best[key]["total"]:
                best[key] = {"total": total, "outbound": o, "return": r}
    return sorted(best.values(), key=lambda p: p["total"])[:top]


# ---------- rendering ----------
def describe(it: dict) -> str:
    parts = [f"{l['mode']} {l['from']}>{l['to']} {l['dep_dt']:%a %d.%m %H:%M}->{l['arr_dt']:%d.%m %H:%M} "
             f"{l['price']:.0f} ({' '.join(x for x in [(l.get('operator') or '')[:14], l.get('number') or ''] if x)})"
             for l in it["legs"]]
    return " ; ".join(parts)


def flags(it: dict) -> str:
    f = []
    if it["separate_tickets"]:
        f.append("SEPARATE TICKETS (no protection)")
    if any(b["thin"] for b in it["buffers"]):
        f.append("thin connection margin")
    if it["discounted"]:
        f.append("discount assumed: " + "; ".join(l["discount"] for l in it["legs"] if "discount" in l))
    return "; ".join(f + it["notes"])


def render_markdown(cfg, results, pairs, dropped, top) -> str:
    cur = cfg.get("currency", "EUR")
    lines = ["# Combined journeys (auto-generated)", "",
             "Prices are provider snapshots with access timestamps in the legs files: **unverified** until an",
             "independent check at the operator. Multi-leg rows are separate tickets unless stated.", ""]
    if dropped:
        lines += [f"Legs dropped for unknown price (never treated as zero): {dict(dropped)}", ""]
    for name, its in results.items():
        lines += [f"## {name} ({len(its)} candidates, cheapest {top} per start date)", "",
                  f"| Total {cur} | Hours | Legs | Flags |", "|---|---|---|---|"]
        by_day = collections.defaultdict(list)
        for it in its:
            by_day[it["start"].date().isoformat()].append(it)
        for day in sorted(by_day):
            lines.append(f"| **{day}** | | | |")
            for it in by_day[day][:top]:
                lines.append(f"| {it['total']:.0f} | {it['hours']} | {describe(it)} | {flags(it)} |")
        lines.append("")
    if pairs:
        lines += ["## Cheapest round trips", "", f"| Total {cur} | Outbound | Return |", "|---|---|---|"]
        for p in pairs:
            lines.append(f"| {p['total']:.0f} | {describe(p['outbound'])} | {describe(p['return'])} |")
        lines.append("")
    return "\n".join(lines)


def _jsonable(obj):
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items() if k not in ("dep_dt", "arr_dt")}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(x) for x in obj]
    if isinstance(obj, (dt.datetime, dt.date)):
        return obj.isoformat()
    return obj


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True)
    ap.add_argument("--legs", nargs="+", required=True, help=".jsonl files")
    ap.add_argument("--out", required=True, help="output path prefix (writes .md and .json)")
    ap.add_argument("--top", type=int, default=3, help="rows per start date in the tables")
    ap.add_argument("--pairs", type=int, default=10, help="how many round-trip pairs to list (0 = none)")
    a = ap.parse_args(argv)

    cfg = load_config(a.config)
    legs, dropped = load_legs(a.legs, cfg)
    results = {"Outbound": find_itineraries(legs, cfg, "outbound"),
               "Return": find_itineraries(legs, cfg, "return")}
    if cfg.get("stopovers"):
        results["Outbound with stopover"] = find_stopovers(legs, cfg, "outbound")
        results["Return with stopover"] = find_stopovers(legs, cfg, "return")
    pairs = []
    if a.pairs:
        outs = results["Outbound"] + results.get("Outbound with stopover", [])
        rets = results["Return"] + results.get("Return with stopover", [])
        pairs = pair_round_trips(outs, rets, cfg, a.pairs)
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".md").write_text(render_markdown(cfg, results, pairs, dropped, a.top), encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps(_jsonable({"results": results, "pairs": pairs,
                                                             "dropped_unpriced": dict(dropped)}), indent=1))
    for name, its in results.items():
        print(f"{name}: {len(its)} candidates" + (f", cheapest {its[0]['total']:.0f}" if its else ""))
    print(f"round trips: {len(pairs)}; wrote {out.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
