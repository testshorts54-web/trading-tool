import unittest, datetime as dt
from tt import indicators as ind

class Ind(unittest.TestCase):
    def test_sma(self):
        self.assertEqual(ind.sma([1, 2, 3, 4], 2), 3.5); self.assertIsNone(ind.sma([1], 2))
    def test_rsi_extremes_and_known(self):
        self.assertEqual(ind.rsi(list(range(1, 30))), 100.0)
        self.assertAlmostEqual(ind.rsi([1, 2] * 20, 14), 51.5, delta=1.5)   # alternating moves, ends on an up day: just above 50
        self.assertIsNone(ind.rsi([1] * 10))
    def test_ret_days(self):
        d0 = dt.date(2026, 1, 1); ds = [d0 + dt.timedelta(i) for i in range(100)]; v = [100 + i for i in range(100)]
        self.assertAlmostEqual(ind.ret_days(ds, v, 30), 199 / 169 - 1)
        self.assertIsNone(ind.ret_days(ds[:10], v[:10], 30))
    def test_drawdown_vol_ratio(self):
        self.assertAlmostEqual(ind.drawdown([10, 20, 15], 3), -0.25)
        self.assertAlmostEqual(ind.realized_vol([100] * 30), 0.0)
        ds, r = ind.ratio({1: 2.0, 2: 4.0, 3: 1.0}, {2: 2.0, 3: 1.0, 4: 9.0})
        self.assertEqual((ds, r), ([2, 3], [2.0, 1.0]))

if __name__ == "__main__": unittest.main()
