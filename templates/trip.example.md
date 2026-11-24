# Trip requirements template

Copy this file to `local/trip.md` (`python3 scripts/init_local.py` does it for you). Do not put real requirements in this tracked template.
Machine-readable settings for the scripts live in `local/config.json` (copy of `templates/config.example.json`); keep the two consistent.

## Journey

- Origin / home base: `<city>`
- Final destination (the real door, not just an airport): `<town/address area>`
- Likely gateways at the destination end: `<airports/stations>`
- Likely gateways at the origin end: `<airports/stations/coach terminals>`
- Allowed modes: `<plane / train / bus / ferry / car lift>`
- Gateways where the traveller can be driven (no ground constraint): `<none or list>`

## Dates

- Outbound window: `<YYYY-MM-DD>` through `<YYYY-MM-DD>`
- Return window: `<YYYY-MM-DD>` through `<YYYY-MM-DD>`, or one-way
- Timezone/local-time convention: times are local to each place
- Date flexibility: `<fixed / flexible within windows>`

## Hard constraints

- Latest arrival / earliest departure at each destination gateway, and what they proxy (e.g. "last bus at 18:40"): `<times and locations>`
- Required final surface leg: `<details>`
- Passenger count: `<number>`
- Baggage: `<hand luggage only / quantity and size>`
- Maximum budget and currency; does it apply per direction or to the whole round trip; are local ground legs included? `<amount, scope>`
- Maximum journey duration: `<duration or unspecified>`
- Maximum number of changes: `<number>`
- Overnight travel (night bus, 02:00 starts, airport sleeping): `<avoid / acceptable>`

## Priorities

- `<e.g. "the return matters more than the outbound", cheapest vs fastest vs safest>`

## Optional routes and stopovers

- Allowed cities: `<cities>`
- Allowed directions: `<outbound/return/either>`
- Minimum and maximum stopover duration: `<duration>`
- Free accommodation available at: `<city or none>`

## Entitlements and discounts

- Residency/student/youth/senior/disability status that may unlock fares or refunds: `<status, or none>`
- Official scheme(s) to check: `<name/URL, or none>` (record eligibility as an assumption until read in the official rules)

## Booking status

Research only until the user explicitly approves an exact itinerary and final total.

## Open questions

- `<question>`
