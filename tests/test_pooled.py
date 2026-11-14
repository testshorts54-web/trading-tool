"""Pooled multi-symbol validation: per-symbol rows add up to the pooled trade counts; too few pooled trades -> INSUFFICIENT."""
import unittest, datetime as dt
from unittest import mock
import screen_batch
from tests.test_part_b import idea, bars_with_edge

class Pooled(unittest.TestCase):
    def run_screen(self, syms, n, oos=dt.date(2004, 1, 1)):
        bars = bars_with_edge(n)
        with mock.patch.object(screen_batch.history, "load", lambda s, a: dict(bars=bars, source="fixture")):
            return screen_batch.screen((idea(coins=syms), oos, 20))

    def test_per_symbol_sums_to_pooled(self):
        r = self.run_screen(["A", "B"], 2400)
        self.assertEqual(len(r["per_symbol"]), 2)
        self.assertEqual(sum(p["n_IS"] for p in r["per_symbol"]), r["n_IS"])
        self.assertEqual(sum(p["n_OOS"] for p in r["per_symbol"]), r["n_OOS"])
        self.assertIn(r["verdict"], ("PASS", "FAIL"))

    def test_min_trades(self):
        r = self.run_screen(["A"], 260, dt.date(2000, 8, 1))
        self.assertEqual(r["verdict"], "INSUFFICIENT")

if __name__ == "__main__":
    unittest.main()
