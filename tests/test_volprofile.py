import unittest
from tt.volprofile import volume_profile, position

def bar(p, v): return dict(high=p + 1, low=p, close=p + 0.5, volume=v)   # typical price = p + 0.5 (bin centre)

class VP(unittest.TestCase):
    def setUp(self):
        vols = [1, 1, 2, 5, 20, 40, 20, 5, 4, 2]                            # bin p gets vols[p]; range 0..10, width 1
        self.c = [bar(p, v) for p, v in enumerate(vols)] * 12               # 120 candles, last close 9.5
        self.p = volume_profile(self.c, bins=10, lookback=0)
    def test_poc_and_value_area(self):
        p = self.p
        self.assertAlmostEqual(p["poc"], 5.5)
        self.assertEqual((p["val"], p["vah"]), (4.0, 7.0))                 # bins 4-6 = 80%; no 2-bin range reaches 70%
        self.assertAlmostEqual(p["va_volume_pct"], 0.8)
    def test_nodes_and_position(self):
        self.assertEqual(self.p["hvn"], [(4.0, 7.0)])                      # >= 1.5x mean bin volume
        self.assertEqual(self.p["lvn"], [(0.0, 4.0), (7.0, 10.0)])         # <= 0.5x mean bin volume
        q = position(self.p)
        self.assertEqual((q["vs_value_area"], q["vs_poc"], q["nearest_lvn"], q["nearest_lvn_dist_pct"]), ("above", "above", (7.0, 10.0), 0.0))
        q = position(dict(self.p, last=5.0))
        self.assertEqual((q["vs_value_area"], q["vs_poc"], q["nearest_lvn"]), ("inside", "below", (0.0, 4.0)))
        self.assertAlmostEqual(q["nearest_lvn_dist_pct"], 0.2)
    def test_unknown_on_short_missing_or_zero(self):
        self.assertIsNone(volume_profile([], bins=10))
        self.assertIsNone(volume_profile(self.c[:50], bins=10, min_candles=100))
        bad = list(self.c); bad[-1] = dict(bad[-1], volume=None)
        self.assertIsNone(volume_profile(bad, bins=10, lookback=0))
        self.assertIsNone(volume_profile([bar(1, 0)] * 200, bins=10))

if __name__ == "__main__": unittest.main()
