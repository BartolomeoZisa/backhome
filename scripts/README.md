# Scripts

All scripts use only the Python 3.10+ standard library. Run them from the repository root. Anything they write for a trip goes under `local/runs/<run>/` (git-ignored).

| Script | What it does |
| --- | --- |
| `init_local.py` | Creates `local/trip.md`, `local/traveller.md`, `local/config.json` and `local/runs/` from the templates (never overwrites). |
| `check_privacy.py` | Confirms private paths are git-ignored, nothing under `local/` is tracked, and no committable file contains obvious personal data (home paths, e-mail addresses). Run it before every commit. |
| `flix_search.py` | FlixBus public search API → normalised legs (`--lookup` finds city/station ids). |
| `ryanair_fares.py` | Ryanair public timetable + fare finder → normalised legs (base fares, not checkout quotes). |
| `combine_legs.py` | Chains legs from any provider into complete journeys, applies your constraints, ranks them, pairs round trips. |

Tests: `python3 -m unittest discover -s tests`.

## Workflow

```sh
python3 scripts/init_local.py                  # once
# edit local/trip.md (human-readable) and local/config.json (for combine_legs.py)

RUN=local/runs/$(date +%Y%m%dT%H%M%S)

# 1. collect legs (one request at a time; raw responses kept as evidence)
python3 scripts/flix_search.py --from "Berlin" --from-code BER-BUS --to "Prague" --to-code PRG-BUS \
    --dates 2026-12-17..2026-12-23 --out $RUN/legs/flix.jsonl --raw-dir $RUN/raw/flix
python3 scripts/ryanair_fares.py --from PRG --to FAO --dates 2026-12-17..2026-12-23 \
    --out $RUN/legs/ryanair.jsonl --raw-dir $RUN/raw/ryanair

# 2. combine and rank
python3 scripts/combine_legs.py --config local/config.json --legs $RUN/legs/*.jsonl \
    --out $RUN/combined --top 3 --pairs 10
```

`combined.md` is the readable result, `combined.json` has every candidate.

## Leg format (JSON Lines)

One object per line; every provider script writes this, and you can write it by hand or from a browser capture.

```json
{"id": "ryanair:FR272:2026-12-18", "mode": "flight", "from": "DUB", "to": "STN",
 "dep": "2026-12-18T06:45", "arr": "2026-12-18T08:05", "price": 19.99, "currency": "EUR",
 "operator": "Ryanair", "number": "FR272", "through": false, "label": "FR272 DUB->STN",
 "url": "<request url>", "accessed": "2026-11-24T22:13:06+01:00", "source": "ryanair-farfnd",
 "notes": "base fare, bags/seat excluded; not a checkout quote"}
```

- `from` / `to` are node codes: IATA codes, or labels of your choice (`--from-code`). A bus station in a city and that city's airport are different nodes; connect them in the config with `equivalent_nodes` and an extra transfer time.
- `dep` / `arr` are local wall-clock times, `price` is `null` when unknown (such legs are dropped and counted, never treated as zero), `through: true` means one ticket already covers several segments (for example a coach with a change).

## What `combine_legs.py` applies

Configured in `local/config.json` (see `templates/config.example.json`):

- `max_legs` (1 = direct only, 2 = one change), minimum transfer buffers per mode pair, `max_layover_hours`.
- Comfort preferences, **all off by default** (ask the traveller): `no_overnight` (drop journeys that end on another calendar day), `min_start_hour` (drop earlier departures), `max_layover_hours`.
- `last_mile`: latest arrival (outbound) or earliest departure (return) at the destination gateway, with weekday and date overrides; an exact date with no rule is treated as infeasible. Gateways listed in `no_constraint_nodes` (you will be driven) skip the rule. A gateway with no rule is flagged "last mile NOT checked".
- `discounts`: percent and cap for fares between two airport sets, valid in a date range. Applied as an assumption and flagged in the output; always verify eligibility and claim rules in the official scheme.
- `stopovers`: free overnight stays; joins two same-day chains with a number of nights in a range.
- `max_total` with `budget_scope` `round_trip` or `per_direction`.

Every multi-leg row is flagged **SEPARATE TICKETS (no protection)**, thin connection margins are flagged, and output prices stay **unverified** until the independent verifier has checked them at the operator.

## Adding a provider

Write a script that fetches one operator's public data and emits legs in the format above (see `flix_search.py` as the model: one function that builds the request URL, one pure function that converts a response to legs, so the conversion can be unit-tested with a small synthetic fixture). Rules:

- Use public endpoints that the operator's own website uses; do not bypass blocks, CAPTCHAs, logins or availability checks. If the operator refuses, report it and mark the data `unverified`.
- Sleep between requests and save raw responses plus the access timestamp.
- Keep the prices honest: say what is included or excluded in `notes`.
- Put a test next to the others in `tests/`. Never commit real traveller data or trip-specific captures.

Browser-only sources (Google Flights, airline sites) can feed the same format by writing the captured rows as legs; keep the browser profile under `local/browser-profile/`.
