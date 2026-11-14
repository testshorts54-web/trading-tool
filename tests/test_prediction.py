"""Kelly + dutch-book tests ported from flow (test_kelly.py, test_arbitrage.py::test_dutch_book_math), plus the fixes."""
import unittest, datetime as dt
from tt import predict as P

class Kelly(unittest.TestCase):
    def test_full_kelly_matches_formula(self):
        a = P.kelly(0.40, 0.60, 10_000, fraction=1.0, cap_pct=1.0)
        self.assertAlmostEqual(a["full_kelly"], 1 / 3, places=4); self.assertAlmostEqual(a["ev_per_share"], 0.20)
        self.assertAlmostEqual(a["roi_pct"], 50.0); self.assertAlmostEqual(a["stake"], 3333.33, places=2); self.assertFalse(a["capped"])
    def test_fractional_kelly_and_cap(self):
        a = P.kelly(0.40, 0.60, 10_000, fraction=0.25, cap_pct=0.05)
        self.assertAlmostEqual(a["fractional_kelly"], 1 / 12, places=4); self.assertAlmostEqual(a["stake"], 500.0); self.assertTrue(a["capped"])
    def test_default_cap_is_one_percent_and_bankroll_required(self):
        self.assertAlmostEqual(P.kelly(0.40, 0.60, 10_000)["stake"], 100.0)
        with self.assertRaises(ValueError): P.kelly(0.40, 0.60, None)
    def test_no_bet_without_edge_and_fees_count(self):
        for p in (0.50, 0.30): self.assertEqual(P.kelly(0.50, p, 1000)["stake"], 0.0)
        self.assertEqual(P.kelly(0.50, 0.505, 1000, fee=0.02)["full_kelly"], 0.0)   # edge eaten by fee

class Dutch(unittest.TestCase):
    def test_flags_cheap_not_fair(self):
        a = P.dutch_book([0.30, 0.30, 0.35]); b = P.dutch_book([0.40, 0.30, 0.30])
        self.assertTrue(a["flagged"]); self.assertFalse(b["flagged"])
        self.assertAlmostEqual(a["sum_of_prices"], 0.95); self.assertAlmostEqual(a["discount_pct"], 5.0)
        self.assertAlmostEqual(a["roi_pct"], (1 / 0.95 - 1) * 100, places=2)
    def test_fixes(self):
        self.assertIsNone(P.dutch_book([0.3, None, 0.3]))                                  # missing price: no 0.50 fill
        self.assertFalse(P.dutch_book([0.30, 0.30, 0.35], fee=0.06)["flagged"])           # fees remove the gap
        a = P.dutch_book([0.30, 0.30, 0.35], end="2026-12-30", today=dt.date(2026, 10, 31))
        self.assertEqual(a["days_to_end"], 60); self.assertAlmostEqual(a["apr_pct"], a["roi_pct"] * 365 / 60)
        self.assertIsNone(P.dutch_book([0.30, 0.30, 0.35])["apr_pct"])                    # no end date -> no APR
    def test_event_parse_and_incomplete_set(self):
        ev = {"title": "Who wins", "endDate": "2026-12-30T00:00:00Z", "negRisk": True, "markets": [
            {"question": "A?", "groupItemTitle": "A", "outcomes": '["Yes","No"]', "outcomePrices": '["0.30","0.70"]', "bestAsk": "0.31"},
            {"question": "B?", "groupItemTitle": "B", "outcomes": '["Yes","No"]', "outcomePrices": '["0.30","0.70"]', "bestAsk": "0.31"},
            {"question": "C?", "groupItemTitle": "C", "outcomes": '["Yes","No"]', "outcomePrices": "[]"}]}
        e = P.parse_events([ev])[0]
        self.assertEqual(e["markets"][2]["prices"], [None, None])
        self.assertIsNone(P.event_dutch_book(e))                                            # C has no price at all
        ev["markets"][2].update(groupItemTitle="Other", outcomePrices='["0.20","0.80"]', bestAsk="0.21")
        r = P.event_dutch_book(P.parse_events([ev])[0], today=dt.date(2026, 10, 31))
        self.assertTrue(r["incomplete_set"]); self.assertFalse(r["flagged"]); self.assertTrue(r["executable"])
    def test_no_risk_free_wording(self):
        import inspect
        src = inspect.getsource(P).lower().replace("nothing is called risk-free or guaranteed", "")
        self.assertNotIn("risk-free", src); self.assertNotIn("guaranteed", src)

class Scan(unittest.TestCase):
    def test_fee_unknown_and_formula(self):
        self.assertIsNone(P.fee_per_share(0.5, None)); self.assertAlmostEqual(P.fee_per_share(0.5, 0.07), 0.0175)
    def test_crypto_parse_and_model(self):
        self.assertEqual(P.parse_crypto_q("Will the price of Bitcoin be above $70,000 on November 1?"), ("BTC", "above", 70000.0))
        self.assertEqual(P.parse_crypto_q("Will the price of Ethereum be less than $1,900 on November 1?")[1], "below")
        for q in ("Will Bitcoin reach $150,000 in October?", "Will the price of Bitcoin be between $70,000 and $72,000 on November 1?"):
            self.assertIsNone(P.parse_crypto_q(q))
        hi = P.model_p_yes(80000, 70000, "above", 14 / 8760, 1.0); self.assertGreater(hi, 0.99)
        self.assertAlmostEqual(P.model_p_yes(80000, 70000, "below", 14 / 8760, 1.0), 1 - hi); self.assertIsNone(P.model_p_yes(1, 1, "above", 0, 1))
    def test_size_binary_one_pct_and_depth(self):
        a = P.size_binary(0.95, 10_000); self.assertEqual(a["qty"], 105); self.assertLessEqual(a["risk_pct"], 0.01); self.assertEqual(a["binding"], "1% risk")
        self.assertEqual(P.size_binary(0.95, 10_000, 50)["binding"], "book depth")
        with self.assertRaises(ValueError): P.size_binary(0.95, None)
    def test_augmented_event_never_flagged(self):
        ms = [dict(best_ask=0.2, prices=[0.2], title=t, other=False) for t in "ABC"]
        self.assertTrue(P.event_dutch_book(dict(markets=ms, end=None))["flagged"])
        self.assertFalse(P.event_dutch_book(dict(markets=ms, end=None, augmented=True))["flagged"])

if __name__ == "__main__": unittest.main()
