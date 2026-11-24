# Backhome

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE) ![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg) ![Dependencies: none](https://img.shields.io/badge/dependencies-none-brightgreen.svg) ![Never pays without approval](https://img.shields.io/badge/payments-only%20with%20your%20approval-orange.svg)

### The cheapest flight is not the cheapest way home.

Flight search stops at the airport. **Home doesn't.** The €19 fare lands at 21:40 and the last bus left at 18:40. The "protected" ticket was actually two tickets. The bus feed went quiet in January and you read that as *no service*.

> **Why this exists.** A trip home was about to cost **~€500**, after checking Rome2Rio, Skyscanner and Google Flights and still comparing dates by hand for days. Pointed at the *whole* journey, an agent found a much cheaper plan. That workflow is this repo.

| | The usual search sites | An agent working the whole journey |
| --- | --- | --- |
| Total I was about to pay | **~€500** | **around €250**, including the local bus and train |
| What it took | days of comparing dates by hand | the agent did the comparing; I answered questions |
| How the saving came about | | coach to a budget airport + low-cost flights + a cheap last leg, each checked against the last bus |
| Catch | | separate tickets (no protection), prices were snapshots, one fare still needed an operator check, bags extra, **not booked until I say yes** |

Backhome is a workspace for an AI agent that plans the **whole door-to-door journey**, checks the last bus on the exact day, keeps score honestly, and **never pays without your explicit yes**.

```text
 you: "get me from A to B and back, flexible dates, budget 250, 1 change is fine"
  │
  ▼
 agent ── reads AGENTS.md (the contract) + local/trip.md (your private brief)
  │
  ├─ collect  legs from public APIs (coach, low-cost air, rail…) → one JSON format
  ├─ combine  chain them under YOUR rules: buffers · last bus · budget · stopovers · fare schemes
  ├─ verify   an independent agent rechecks the finalists at the operators
  └─ ask      exact itinerary + total + risks → waits for your explicit approval
```

## See it work

`examples/demo/` is a **synthetic** dataset (made-up prices) so you can run the real tool in one command:

```sh
python3 scripts/combine_legs.py --config examples/demo/config.json \
    --legs examples/demo/legs.jsonl --out /tmp/demo --top 3
```

What it does with the demo, and why (this is tested in `tests/test_demo.py`):

| Candidate | Result | Reason |
| --- | --- | --- |
| Coach + budget flight, 4h10 between them | ✅ kept, flagged **SEPARATE TICKETS** | realistic buffer |
| Same coach, flight 95 minutes later | ❌ dropped | self-transfer too tight |
| Cheap flight landing after the Sunday last bus | ❌ dropped | `last_mile` rule: Sundays end at 14:30 |
| Direct flight on a holiday | ❌ dropped | no early bus that day |
| Flight via a city where you can sleep for free | ✅ joined as a **stopover**, nights counted | optional |
| Domestic leg with a resident refund | ✅ price halved, flagged **ASSUMED eligible; verify rules** | never silently trusted |

Cheapest demo round trip: a €22 coach plus a €64 budget flight out, the same pattern back, **€183 vs €505 for the cheapest direct-flight pair in the same data**, with every separate ticket labelled and nothing called verified.

## Quick start

```sh
git clone https://github.com/BartolomeoZisa/backhome && cd backhome && python3 scripts/init_local.py
# init_local.py creates your private, git-ignored local/ workspace; nothing to install
```

1. Open the folder in an agent that reads `AGENTS.md` (Claude Code, Codex, Cursor… anything with shell and web access).
2. Fill in `local/trip.md` together with the agent: places, date windows, deadlines such as the last bus, budget, luggage. Comfort rules (night buses, 02:45 starts, long layovers, separate tickets) are **your** call. The agent asks, it doesn't assume.
3. Say:

   > Read AGENTS.md and local/trip.md. Research the complete round trip including the last-mile leg, verify the best three options at the operators, and write the plan under local/runs/. Do not book or create accounts.

4. Keep talking: "also try Saturday", "I can be driven to the other airport", "what if I spend two nights at a friend's?".
5. Pick one. The agent shows the exact itinerary, total, fare rules and risks, and **waits**. You enter payment details yourself.

**Claude Code skill:** this repo ships `.claude/skills/backhome`, so inside the repository the agent loads the workflow when you ask to plan or book a trip.

## What's inside

| | |
| --- | --- |
| `AGENTS.md` | the contract: roles (coordinator, researchers, independent verifier, booking operator), research procedure, ranking, booking gate, hard-won heuristics |
| `scripts/combine_legs.py` | the journey combiner: buffers per mode pair, last-bus rules with weekday/date overrides, budget, stopovers, fare discounts, round-trip pairing |
| `scripts/flix_search.py`, `scripts/ryanair_fares.py` | leg providers for public coach and low-cost-air endpoints; add your own (`scripts/README.md`) |
| `scripts/check_privacy.py` | refuses to let personal data near a commit |
| `templates/` | trip brief, traveller details, plan, machine-readable config |
| `tests/` | standard library only: `python3 -m unittest discover -s tests` |

No dependencies beyond Python 3.10+.

## Rules the agents live by

- **The whole journey counts.** A fare that lands after the last bus is not a result.
- **Honest labels.** `verified` · `unverified` · `sold out`. Unknown prices are never zero. Separate tickets are never "protected". Missing timetable data is never "no service".
- **Operators are the authority.** Aggregator numbers are snapshots until checked at the source. Fare-finder base fares are not checkout quotes.
- **No circumvention.** No CAPTCHA tricks, no bot-block workarounds. When an operator says no, the agent says *unverified* and asks you.
- **Your rules, not ours.** Night buses, early starts, layovers and change counts are opt-in filters, and the agent tells you what each filter hid.
- **Private by default.** Everything about your trip lives in `local/`, which git ignores, and `check_privacy.py` guards the rest.
- **Approval is explicit.** A subagent saying "approved" is not you.

## Contributing

The most useful PR is a **provider**: a small script that turns one operator's public data into the leg format (rail, ferries, regional buses, other low-cost airlines, other countries). Keep a pure parsing function and a synthetic-fixture test, respect rate limits, never bypass blocks, never commit real traveller data. See `scripts/README.md`.

## Limitations

Timetables and prices move, especially around holidays, and operators sometimes publish next year's schedule late. Provider scripts use public endpoints that can change or refuse automated access. Results are snapshots, not reservations: nothing is booked until an operator sends a confirmation. Discount schemes (resident, student, youth) are assumptions in the output until you have read the official rules.
