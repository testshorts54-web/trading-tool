"""Per-bar series ported from flow core/indicators.py and the IC function from datascientist/analyzer.py."""
import unittest, math, datetime as dt
from pathlib import Path
from tt import indicators as ind
from tt.sources import crypto
from tt.regime import crypto as rcr
FX = Path(__file__).parent / "fixtures"

class Series(unittest.TestCase):
    def test_sma_ema_wilder(self):
        self.assertEqual(ind.sma_s([1, 2, 3, 4], 2), [None, 1.5, 2.5, 3.5])
        self.assertEqual(ind.ema_s([1, 2, 3, 4], 3)[2:], [2.0, 3.0])
        self.assertEqual(ind.wilder_s([2, 4, 4], 2), [None, 3.0, 3.5])
        self.assertEqual(ind.rsi_s(list(range(1, 10)), 2)[-1], 100.0)
    def test_atr_and_true_range(self):
        self.assertEqual(ind.true_range([10, 12], [9, 11], [9.5, 11.5]), [1, 2.5])
    def test_adx_trend_vs_chop(self):
        n = 120; up = [100 + i for i in range(n)]
        adx, pdi, mdi = ind.adx_s([x + 1 for x in up], [x - 1 for x in up], up, 14)
        self.assertGreater(adx[-1], 50); self.assertGreater(pdi[-1], mdi[-1]); self.assertIsNone(adx[20])
        ch = [100 + (1 if i % 2 else -1) for i in range(n)]
        self.assertLess(ind.adx_s([x + 1 for x in ch], [x - 1 for x in ch], ch, 14)[0][-1], 20)
    def test_short_history_is_none_not_fallback(self):
        self.assertIsNone(ind.hurst([1.0, 2.0] * 5)); self.assertEqual(ind.adx_s([1] * 5, [1] * 5, [1] * 5)[0], [None] * 5)
        sq, mom = ind.ttm_squeeze_s([2] * 10, [1] * 10, [1.5] * 10, 20); self.assertEqual(sq, [None] * 10)
    def test_hurst_random_walk_vs_mean_reverting(self):
        import random; rng = random.Random(7); w = [0.0]
        for _ in range(400): w.append(w[-1] + rng.gauss(0, 1))
        self.assertTrue(0.3 < ind.hurst(w) < 0.7)
        x = [0.0]
        for _ in range(400): x.append(0.2 * x[-1] + rng.gauss(0, 1))   # stationary, mean-reverting
        self.assertLess(ind.hurst(x), 0.2)
    def test_bb_width_and_squeeze_on_flat_then_wide(self):
        c = [100 + 0.01 * (i % 2) for i in range(40)]; h = [x + 1 for x in c]; l = [x - 1 for x in c]
        self.assertLess(ind.bb_width_s(c, 20)[-1], 0.1); self.assertTrue(ind.ttm_squeeze_s(h, l, c, 20)[0][-1])
    def test_spearman_ic(self):
        x = list(range(40)); self.assertAlmostEqual(ind.spearman_ic(x, [v * 2 for v in x]), 1.0)
        self.assertAlmostEqual(ind.spearman_ic(x, [-v for v in x]), -1.0)
        self.assertIsNone(ind.spearman_ic(x[:20], x[:20])); self.assertIsNone(ind.spearman_ic(x, [1] * 40))
        self.assertEqual(ind.rank([3, 1, 3]), [2.5, 1.0, 2.5])

class CryptoInfoRows(unittest.TestCase):
    def test_trend_row_on_fixture_and_unknowns(self):
        b = crypto.load_hourly_fixture(FX / "BTCUSDT_1h.json")
        d = [dt.datetime.fromtimestamp(x["ts"] / 1000, dt.timezone.utc).date() for x in b]
        s = dict(dates=d, closes=[x["close"] for x in b], highs=[x["high"] for x in b], lows=[x["low"] for x in b],
                 source="fixture", asof=d[-1].isoformat())
        r = rcr.trend_rows(s, d[-1])[0]
        self.assertEqual(r["status"], "ok"); self.assertFalse(r["scored"]); self.assertIn("ADX", r["value"])
        self.assertEqual(rcr.trend_rows(dict(error="down"), d[-1])[0]["status"], "unknown")
        rows = rcr.perp_rows(dict(error="HL down"), dict(error="KR down")) + rcr.sentiment_rows(dict(error="x"), dict(error="y")) + [rcr.venue_row(dict(error="z"))]
        self.assertTrue(all(x["status"] == "unknown" and not x["scored"] for x in rows))
        self.assertEqual([x["id"] for x in rows], ["C4", "C5", "C6", "C7", "C8"])

if __name__ == "__main__": unittest.main()
