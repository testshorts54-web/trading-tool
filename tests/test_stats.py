"""Ported from flow backend/tests/test_stats.py (pytest -> unittest); min sample now explicit / 30 by default."""
import sys, math, unittest
sys.path.insert(0, "/workspace/backtest")
from btlib import stats

class Stats(unittest.TestCase):
    def test_win_rate(self):
        self.assertAlmostEqual(stats.win_rate_pct([0.02, -0.01, 0.03, 0.0]), 50.0); self.assertIsNone(stats.win_rate_pct([]))
    def test_profit_factor(self):
        self.assertAlmostEqual(stats.profit_factor([0.03, -0.01, 0.01, -0.02]), 0.04 / 0.03)
        self.assertTrue(math.isinf(stats.profit_factor([0.01, 0.02])))
        self.assertIsNone(stats.profit_factor([])); self.assertIsNone(stats.profit_factor([0.0, 0.0]))
    def test_sharpe_per_trade_sample_std(self):
        r = [0.01, 0.02, -0.01, 0.03]; m = sum(r) / 4; sd = math.sqrt(sum((x - m) ** 2 for x in r) / 3)
        self.assertAlmostEqual(stats.sharpe_ratio(r), m / sd)
        self.assertAlmostEqual(stats.sharpe_ratio(r, periods_per_year=365), m / sd * math.sqrt(365))
        self.assertIsNone(stats.sharpe_ratio([0.01])); self.assertIsNone(stats.sharpe_ratio([0.01] * 3))
    def test_insufficient_data_reports_no_metrics(self):
        out = stats.trade_metrics([0.05, 0.04] * 14)          # 28 < default 30
        self.assertEqual(out["status"], "INSUFFICIENT_DATA"); self.assertEqual(out["trade_count"], 28)
        for k in ("win_rate_pct", "profit_factor", "sharpe_ratio", "mean_ret"): self.assertIsNone(out[k])
        self.assertIn("Insufficient data", out["message"])
    def test_trade_metrics_json_safe_for_no_losses(self):
        out = stats.trade_metrics([0.01, 0.02, 0.03], min_trades=3)
        self.assertEqual(out["status"], "OK"); self.assertEqual(out["win_rate_pct"], 100.0)
        self.assertIsNone(out["profit_factor"]); self.assertEqual(out["profit_factor_note"], "undefined: no losing trades")

if __name__ == "__main__": unittest.main()
