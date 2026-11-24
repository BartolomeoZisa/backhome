"""The README quotes the synthetic demo; keep it honest by testing what it claims."""
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import combine_legs as cl  # noqa: E402

DEMO = ROOT / "examples" / "demo"


class DemoTests(unittest.TestCase):
    def setUp(self):
        out = pathlib.Path(tempfile.mkdtemp()) / "c"
        cl.main(["--config", str(DEMO / "config.json"), "--legs", str(DEMO / "legs.jsonl"), "--out", str(out), "--pairs", "5"])
        self.data = json.loads(out.with_suffix(".json").read_text())

    def ids(self, key):
        return {tuple(l["id"] for l in it["legs"]) for it in self.data["results"][key]}

    def test_rejections_the_readme_describes(self):
        outbound = self.ids("Outbound")
        self.assertIn(("o2", "o3"), outbound)          # coach + budget flight, 4h10 buffer
        self.assertNotIn(("o4", "o5"), outbound)       # 95-minute self-transfer
        self.assertNotIn(("o10", "o11"), outbound)     # lands after the Sunday last-bus limit
        self.assertNotIn(("r1",), self.ids("Return"))  # holiday: earliest departure 13:00
        self.assertNotIn(("r7", "r4"), self.ids("Return with stopover"))  # departs before the 10:00 rule

    def test_cheapest_round_trip_and_discount(self):
        best = self.data["pairs"][0]
        self.assertEqual(best["total"], 183.0)
        stop = self.data["results"]["Outbound with stopover"][0]
        self.assertEqual(stop["total"], 130.0)         # 95 + 70 halved by the assumed refund
        self.assertTrue(stop["discounted"])


if __name__ == "__main__":
    unittest.main()
