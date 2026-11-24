import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import _common  # noqa: E402
import flix_search  # noqa: E402
import ryanair_fares  # noqa: E402


class CommonTests(unittest.TestCase):
    def test_parse_dates(self):
        self.assertEqual(_common.parse_dates("2026-12-30..2027-01-02"),
                         ["2026-12-30", "2026-12-31", "2027-01-01", "2027-01-02"])
        self.assertEqual(_common.parse_dates("2026-12-17, 2026-12-20"), ["2026-12-17", "2026-12-20"])
        with self.assertRaises(ValueError):
            _common.parse_dates("2026-12-20..2026-12-17")


class FlixTests(unittest.TestCase):
    RAW = {"stations": {"s1": {"id": "s1", "name": "Origin ZOB"}, "s2": {"id": "s2", "name": "Mid Hbf"},
                        "s3": {"id": "s3", "name": "Dest Airport"}},
           "trips": [{"results": {
               "r1": {"status": "available", "departure": {"date": "2026-12-18T08:20:00+01:00", "station_id": "s1"},
                      "arrival": {"date": "2026-12-18T09:40:00+01:00", "station_id": "s3"},
                      "price": {"total": 9.99, "total_with_platform_fee": 10.98}, "legs": [{}]},
               "r2": {"status": "sold_out", "departure": {"date": "2026-12-18T10:00:00+01:00"},
                      "arrival": {"date": "2026-12-18T12:00:00+01:00"}, "price": {"total": 5}, "legs": [{}]},
               "r3": {"status": "available", "departure": {"date": "2026-12-18T01:00:00+01:00", "station_id": "s1"},
                      "arrival": {"date": "2026-12-18T13:00:00+01:00", "station_id": "s3"},
                      "price": {"total": 40.0}, "legs": [{"arrival": {"station_id": "s2"}}, {}]}}}]}

    def test_available_only_fee_included_and_through(self):
        legs = flix_search.legs_from_response(self.RAW, from_code="A", to_code="B", currency="EUR", url="u", accessed="t")
        self.assertEqual({l["id"] for l in legs}, {"flix:r1", "flix:r3"})
        r1 = next(l for l in legs if l["id"] == "flix:r1")
        self.assertEqual((r1["price"], r1["dep"], r1["arr"], r1["through"]), (10.98, "2026-12-18T08:20", "2026-12-18T09:40", False))
        r3 = next(l for l in legs if l["id"] == "flix:r3")
        self.assertTrue(r3["through"])
        self.assertIn("Mid Hbf", r3["label"])
        direct = flix_search.legs_from_response(self.RAW, from_code="A", to_code="B", currency="EUR", url="u", accessed="t", direct_only=True)
        self.assertEqual([l["id"] for l in direct], ["flix:r1"])

    def test_search_url_date_format(self):
        url = flix_search.search_url("f", "t", "2026-12-07", "EUR", "en", True)
        self.assertIn("departure_date=07.12.2026", url)
        self.assertIn("include_after_midnight_rides=1", url)


class RyanairTests(unittest.TestCase):
    def test_timetable_and_after_midnight(self):
        tt = {"days": [{"day": 18, "flights": [{"number": "123", "departureTime": "22:30", "arrivalTime": "00:40"}]},
                       {"day": 25, "flights": [{"number": "9", "departureTime": "09:00", "arrivalTime": "10:00"}]}]}
        fl = ryanair_fares.flights_in_timetable(tt, 2026, 12, {"2026-12-18"})
        self.assertEqual(len(fl), 1)
        leg = ryanair_fares.to_leg("AAA", "BBB", fl[0], 42.5, "EUR", "u", "t")
        self.assertEqual((leg["dep"], leg["arr"], leg["price"]), ("2026-12-18T22:30", "2026-12-19T00:40", 42.5))
        self.assertIn("not a checkout quote", leg["notes"])
        none_price = ryanair_fares.to_leg("AAA", "BBB", fl[0], None, "EUR", "u", "t")
        self.assertIsNone(none_price["price"])   # unknown stays unknown


if __name__ == "__main__":
    unittest.main()
