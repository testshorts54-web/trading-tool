"""Trade simulator: next-bar fill, intrabar stop, gaps, per-side cost, time exit; reproduces backtest.py RSI2 on SPY."""
import sys, csv, unittest
from pathlib import Path
sys.path.insert(0, "/workspace/backtest")
from btlib import trades as T
from tt import indicators as ind
FX = Path(__file__).parent / "fixtures"

def B(*rows): return [dict(open=o, high=h, low=l, close=c) for o, h, l, c in rows]
STOP5 = lambda f, i: f * 0.95
TGT10 = lambda f, s, i: f * 1.10

class Sim(unittest.TestCase):
    def run1(self, bars, sig=None, **kw):
        sig = sig or [True] + [False] * (len(bars) - 1)
        return T.simulate(bars, sig, kw.pop("stop", STOP5), kw.pop("tgt", TGT10), kw.pop("hold", 5), kw.pop("cost", 0.0), **kw)
    def test_fill_next_open_with_cost(self):
        bars = B((100, 100, 100, 100), (102, 103, 101, 102), (102, 103, 101, 102), (102, 103, 101, 102))
        t = self.run1(bars, hold=2, cost=0.001)["trades"][0]
        self.assertEqual(t["entry_bar"], 1); self.assertAlmostEqual(t["entry"], 102 * 1.001)
        self.assertEqual((t["reason"], t["exit_bar"]), ("time", 2)); self.assertAlmostEqual(t["exit"], 102 * 0.999)
    def test_intrabar_stop_and_stop_first(self):
        bars = B((100, 100, 100, 100), (100, 100.5, 99, 100), (100, 111, 94, 100))
        t = self.run1(bars)["trades"][0]
        self.assertEqual(t["reason"], "stop"); self.assertAlmostEqual(t["exit"], 95); self.assertAlmostEqual(t["R"], -1)
    def test_gaps_fill_at_open(self):
        down = self.run1(B((100,) * 4, (100, 101, 99, 100), (90, 91, 89, 90)))["trades"][0]
        self.assertEqual((down["reason"], down["exit"]), ("stop_gap", 90))
        up = self.run1(B((100,) * 4, (100, 101, 99, 100), (115, 116, 114, 115)))["trades"][0]
        self.assertEqual((up["reason"], up["exit"]), ("target_gap", 115))
    def test_open_at_end_not_counted_and_needs_exit(self):
        r = self.run1(B((100,) * 4, (100, 101, 99, 100)), hold=9)
        self.assertEqual(r["trades"], []); self.assertEqual(r["open_at_end"]["entry_bar"], 1)
        with self.assertRaises(ValueError): T.simulate(B((100,) * 4) * 3, [True] * 3, STOP5, None, None)
    def test_reproduces_backtest_rsi2_spy(self):
        rows = [dict(date=r["date"], **{k: float(r[k]) for k in ("open", "high", "low", "close")}) for r in csv.DictReader(open(FX / "SPY_daily.csv"))]
        c, h, l = ([r[k] for r in rows] for k in ("close", "high", "low"))
        r2, s200, atr = ind.rsi_s(c, 2), ind.sma_s(c, 200), ind.atr_s(h, l, c, 14)
        sig = [s200[i] is not None and c[i] > s200[i] and r2[i] is not None and r2[i] < 10 for i in range(len(c))]
        mine = T.simulate(rows, sig, lambda f, i: f - 2 * atr[i], lambda f, s, i: f + 1.5 * (f - s), 7, 0.0005, 200)["trades"]
        ref = list(csv.DictReader(open(FX / "rsi2_spy_trades_backtest.csv")))
        self.assertEqual(len(mine), len(ref))
        for a, b in zip(mine, ref):
            self.assertEqual((rows[a["entry_bar"]]["date"], rows[a["exit_bar"]]["date"], a["reason"]), (b["entry_date"], b["exit_date"], b["reason"]))
            self.assertAlmostEqual(a["R"], float(b["R"]), places=6)

if __name__ == "__main__": unittest.main()
