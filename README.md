# Backhome

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE) ![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg) ![Dependencies: none](https://img.shields.io/badge/dependencies-none-brightgreen.svg)

### The cheapest flight is not the cheapest way home.

Flight search stops at the airport. Home doesn't. Backhome points an AI agent at the **whole door-to-door trip**, last bus included, and hands you a short list to book yourself.

I was about to pay **~€500**, after Rome2Rio, Skyscanner, Google Flights and days of comparing dates by hand. The agent found a plan for **around €250** all-in: coach to a budget airport, a low-cost flight, a cheap last leg. *(Snapshot prices, separate tickets, bags extra, not booked yet.)*

## Try it

```sh
git clone https://github.com/BartolomeoZisa/backhome && cd backhome && python3 scripts/init_local.py
```

Open the folder in an agent that reads `AGENTS.md` (Claude Code, Codex, Cursor…) and say:

> Read AGENTS.md, fill in local/trip.md with me, then find the best way home.

No dependencies. Your trip stays in `local/`, which git ignores.

## What it does

- **Chains** coach, flights and trains into complete journeys: transfer buffers, last-bus rules, budget, free-night stopovers, resident/student fares.
- **Flags** separate tickets, thin connections, assumed discounts and unverified prices. Missing data is never "no service".
- **Never books, pays or bypasses a CAPTCHA.** You buy.

Try the combiner on made-up data: `python3 scripts/combine_legs.py --config examples/demo/config.json --legs examples/demo/legs.jsonl --out /tmp/demo`

## Contribute

Write a **provider**: a small script that turns one operator's public data into the leg format (`scripts/README.md`). Rail, ferries, other airlines, other countries.

MIT licensed.
