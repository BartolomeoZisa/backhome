import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import combine_legs as cl  # noqa: E402


def leg(i, mode, a, b, dep, arr, price, **kw):
    d = {"id": i, "mode": mode, "from": a, "to": b, "dep": dep, "arr": arr, "price": price,
         "currency": "EUR", "operator": "X", "number": "", "source": "test"}
    d.update(kw)
    return d


def cfg(**over):
    c = {"currency": "EUR", "origin": ["AAA"], "destination": ["ZZZ"],
         "outbound_window": ["2026-12-17", "2026-12-23"], "return_window": ["2027-01-04", "2027-01-09"],
         "max_total": 250, "budget_scope": "round_trip"}
    c.update(over)
    path = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(c, path)
    path.close()
    return cl.load_config(path.name)


def build(legs, c):
    f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    for l in legs:
        f.write(json.dumps(l) + "\n")
    f.close()
    return cl.load_legs([f.name], c)


class CombineTests(unittest.TestCase):
    def test_buffer_and_separate_ticket_flag(self):
        c = cfg()
        legs, _ = build([
            leg("b", "bus", "AAA", "HUB", "2026-12-18T06:00", "2026-12-18T08:00", 10),
            leg("ok", "flight", "HUB", "ZZZ", "2026-12-18T11:00", "2026-12-18T13:00", 50),    # 180 min gap
            leg("tight", "flight", "HUB", "ZZZ", "2026-12-18T09:00", "2026-12-18T11:00", 40),  # 60 min gap
        ], c)
        res = cl.find_itineraries(legs, c, "outbound")
        self.assertEqual([r["total"] for r in res], [60.0])
        self.assertTrue(res[0]["separate_tickets"])

    def test_no_overnight_and_min_start_hour(self):
        c = cfg(no_overnight=True, min_start_hour=5)
        legs, _ = build([
            leg("night", "flight", "AAA", "ZZZ", "2026-12-18T22:00", "2026-12-19T00:30", 40),
            leg("early", "flight", "AAA", "ZZZ", "2026-12-18T04:00", "2026-12-18T06:00", 40),
            leg("day", "flight", "AAA", "ZZZ", "2026-12-18T09:00", "2026-12-18T11:00", 90),
        ], c)
        self.assertEqual([r["legs"][0]["id"] for r in cl.find_itineraries(legs, c, "outbound")], ["day"])
        c2 = cfg(no_overnight=False)   # opt-in rule: the default imposes no such preference
        legs2, _ = build([leg("night", "flight", "AAA", "ZZZ", "2026-12-18T22:00", "2026-12-19T00:30", 40)], c2)
        self.assertEqual(len(cl.find_itineraries(legs2, c2, "outbound")), 1)

    def test_preferences_are_opt_in_by_default(self):
        c = cfg()
        self.assertFalse(c["no_overnight"])
        self.assertEqual(c["min_start_hour"], 0)
        legs, _ = build([leg("night", "flight", "AAA", "ZZZ", "2026-12-18T22:00", "2026-12-19T00:30", 40),
                         leg("early", "flight", "AAA", "ZZZ", "2026-12-18T03:00", "2026-12-18T05:00", 40)], c)
        self.assertEqual(len(cl.find_itineraries(legs, c, "outbound")), 2)

    def test_window_filter(self):
        c = cfg()
        legs, _ = build([leg("late", "flight", "AAA", "ZZZ", "2026-12-24T09:00", "2026-12-24T11:00", 40)], c)
        self.assertEqual(cl.find_itineraries(legs, c, "outbound"), [])

    def test_last_mile_weekday_override_and_missing_date(self):
        c = cfg(last_mile={"outbound": {"ZZZ": {"latest_arrival": "17:00", "weekday_latest_arrival": {"Sun": "12:00"},
                                                 "date_latest_arrival": {"2026-12-22": "10:00"}}}})
        legs, _ = build([
            leg("sat", "flight", "AAA", "ZZZ", "2026-12-19T13:00", "2026-12-19T16:00", 50),   # Sat, <=17:00 ok
            leg("sun", "flight", "AAA", "ZZZ", "2026-12-20T13:00", "2026-12-20T16:00", 50),   # Sun, >12:00 fails
            leg("tue", "flight", "AAA", "ZZZ", "2026-12-22T08:00", "2026-12-22T11:00", 50),   # date override 10:00 fails
        ], c)
        self.assertEqual([r["legs"][0]["id"] for r in cl.find_itineraries(legs, c, "outbound")], ["sat"])
        c2 = cfg(last_mile={"outbound": {"ZZZ": {}}})
        res = cl.find_itineraries(build([leg("x", "flight", "AAA", "ZZZ", "2026-12-19T09:00", "2026-12-19T11:00", 5)], c2)[0], c2, "outbound")
        self.assertIn("NOT checked", res[0]["notes"][0])   # empty rule = not checked, said honestly
        c3 = cfg(last_mile={"return": {"ZZZ": {"date_earliest_departure": {"2027-01-05": "10:00"}}}})
        legs3, _ = build([leg("r", "flight", "ZZZ", "AAA", "2027-01-06T12:00", "2027-01-06T14:00", 30)], c3)
        self.assertEqual(cl.find_itineraries(legs3, c3, "return"), [])   # no rule for that date -> infeasible

    def test_return_earliest_departure(self):
        c = cfg(last_mile={"return": {"ZZZ": {"earliest_departure": "10:00"}}})
        legs, _ = build([
            leg("early", "flight", "ZZZ", "AAA", "2027-01-05T08:00", "2027-01-05T10:00", 30),
            leg("fine", "flight", "ZZZ", "AAA", "2027-01-05T11:00", "2027-01-05T13:00", 30),
        ], c)
        self.assertEqual([r["legs"][0]["id"] for r in cl.find_itineraries(legs, c, "return")], ["fine"])

    def test_unknown_price_dropped_not_zero(self):
        c = cfg()
        legs, dropped = build([leg("n", "flight", "AAA", "ZZZ", "2026-12-18T09:00", "2026-12-18T11:00", None, source="p")], c)
        self.assertEqual(legs, [])
        self.assertEqual(dropped["p"], 1)

    def test_discount_percent_cap_and_scope(self):
        rule = {"name": "r", "percent": 50, "cap": 100, "modes": ["flight"], "between": [["ZZZ"], ["MID"]],
                "valid_from": "2026-12-01", "valid_to": "2027-01-10"}
        c = cfg(discounts=[rule])
        legs, _ = build([
            leg("a", "flight", "MID", "ZZZ", "2026-12-18T09:00", "2026-12-18T11:00", 300),   # capped: -100
            leg("b", "flight", "MID", "ZZZ", "2026-12-18T12:00", "2026-12-18T14:00", 80),    # -40
            leg("c", "bus", "MID", "ZZZ", "2026-12-18T12:00", "2026-12-18T14:00", 80),       # wrong mode
            leg("d", "flight", "AAA", "ZZZ", "2026-12-18T12:00", "2026-12-18T14:00", 80),    # wrong pair
            leg("e", "flight", "MID", "ZZZ", "2027-02-01T12:00", "2027-02-01T14:00", 80),    # out of validity
        ], c)
        prices = {l["id"]: l["price"] for l in legs}
        self.assertEqual(prices, {"a": 200.0, "b": 40.0, "c": 80.0, "d": 80.0, "e": 80.0})
        self.assertIn("ASSUMED", [l for l in legs if l["id"] == "a"][0]["discount"])

    def test_equivalent_node_extra_transfer(self):
        c = cfg(equivalent_nodes=[["CITY", "APT", 60]])
        legs, _ = build([
            leg("bus", "bus", "AAA", "CITY", "2026-12-18T06:00", "2026-12-18T08:00", 10),
            leg("f1", "flight", "APT", "ZZZ", "2026-12-18T10:45", "2026-12-18T13:00", 50),   # 165 < 150+60
            leg("f2", "flight", "APT", "ZZZ", "2026-12-18T11:30", "2026-12-18T14:00", 55),   # 210 >= 210
        ], c)
        self.assertEqual([r["legs"][1]["id"] for r in cl.find_itineraries(legs, c, "outbound")], ["f2"])

    def test_stopover_nights_and_pairs_budget(self):
        c = cfg(stopovers={"nodes": ["HOME"], "min_nights": 1, "max_nights": 3},
                outbound_window=["2026-12-17", "2026-12-23"], return_window=["2027-01-04", "2027-01-09"], max_total=200)
        legs, _ = build([
            leg("o1", "bus", "AAA", "HOME", "2026-12-17T07:00", "2026-12-17T20:00", 60),
            leg("o2", "flight", "HOME", "ZZZ", "2026-12-19T10:00", "2026-12-19T12:00", 70),   # 2 nights
            leg("o3", "flight", "HOME", "ZZZ", "2026-12-17T21:00", "2026-12-17T23:00", 10),   # 0 nights: excluded
            leg("r1", "flight", "ZZZ", "HOME", "2027-01-07T10:00", "2027-01-07T12:00", 40),
            leg("r2", "bus", "HOME", "AAA", "2027-01-09T07:00", "2027-01-09T20:00", 60),      # 2 nights
            leg("r3", "bus", "HOME", "AAA", "2027-01-12T07:00", "2027-01-12T20:00", 5),       # outside window
        ], c)
        outs = cl.find_stopovers(legs, c, "outbound")
        rets = cl.find_stopovers(legs, c, "return")
        self.assertEqual([(o["total"], o["stopover"]["nights"]) for o in outs], [(130.0, 2)])
        self.assertEqual([(r["total"], r["stopover"]["nights"]) for r in rets], [(100.0, 2)])
        pairs = cl.pair_round_trips(outs, rets, c)
        self.assertEqual(pairs, [])                      # 230 > 200
        c["max_total"] = 250
        self.assertEqual(cl.pair_round_trips(outs, rets, c)[0]["total"], 230.0)

    def test_through_leg_not_flagged_separate_when_single_record(self):
        c = cfg()
        legs, _ = build([leg("t", "bus", "AAA", "ZZZ", "2026-12-18T09:00", "2026-12-18T20:00", 80, through=True)], c)
        res = cl.find_itineraries(legs, c, "outbound")
        self.assertFalse(res[0]["separate_tickets"])

    def test_mixed_currency_rejected(self):
        c = cfg()
        with self.assertRaises(ValueError):
            build([leg("a", "bus", "AAA", "ZZZ", "2026-12-18T09:00", "2026-12-18T20:00", 80),
                   leg("b", "bus", "AAA", "ZZZ", "2026-12-18T10:00", "2026-12-18T21:00", 80, currency="USD")], c)

    def test_cli_end_to_end(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "legs.jsonl").write_text("\n".join(json.dumps(l) for l in [
            leg("o", "flight", "AAA", "ZZZ", "2026-12-18T09:00", "2026-12-18T11:00", 90),
            leg("r", "flight", "ZZZ", "AAA", "2027-01-05T09:00", "2027-01-05T11:00", 80)]))
        cfgp = tmp / "config.json"
        cfgp.write_text(json.dumps({"origin": ["AAA"], "destination": ["ZZZ"], "outbound_window": ["2026-12-17", "2026-12-23"],
                                    "return_window": ["2027-01-04", "2027-01-09"], "max_total": 200}))
        self.assertEqual(cl.main(["--config", str(cfgp), "--legs", str(tmp / "legs.jsonl"), "--out", str(tmp / "o")]), 0)
        data = json.loads((tmp / "o.json").read_text())
        self.assertEqual(data["pairs"][0]["total"], 170.0)
        self.assertIn("unverified", (tmp / "o.md").read_text())


if __name__ == "__main__":
    unittest.main()
