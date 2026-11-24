# Sample handoff (synthetic demo: made-up prices, links and operators)

What the agent leaves you with at the end. You book each ticket yourself on the operator's site.

**Option: cheapest round trip from the demo data, total EUR 183** (see `combined.md` for the alternatives)

## Outbound, Fri 18 Dec 2026

| # | Leg | Local time | Price | Book at |
| --- | --- | --- | --- | --- |
| 1 | Coach, Berlin → Prague airport (ExampleBus) | 05:30 → 10:10 | 22 | `https://example.com/coach` |
| 2 | Flight BJ442, Prague → Faro (BudgetJet) | 14:20 → 16:55 | 64 | `https://example.com/budgetjet` |

Last mile: lands 16:55, inside the Friday limit (18:00) set in `config.json`. In a real run this line cites the operator's timetable for that exact date and when it was checked.

## Return, Fri 8 Jan 2027

| # | Leg | Local time | Price | Book at |
| --- | --- | --- | --- | --- |
| 3 | Flight BJ443, Faro → Prague (BudgetJet) | 10:30 → 15:00 | 72 | `https://example.com/budgetjet` |
| 4 | Coach, Prague airport → Berlin (ExampleBus) | 18:30 → 23:05 | 25 | `https://example.com/coach` |

Leaves Faro after the 10:00 earliest-departure rule. 22 + 64 + 72 + 25 = **183**.

## Read before you buy

- **Four separate tickets, no protection.** Coach to flight has 4h10 of slack outbound and 3h30 back. A real handoff also says what a miss costs: the next departure and its price.
- **Prices are snapshots.** Recheck the total at each operator's own site; fare-finder base prices are not checkout prices.
- **Bags, seats and payment fees are not included.**
- **Still unverified here:** everything. A real handoff lists which legs an independent check confirmed at the operator, and which did not.
