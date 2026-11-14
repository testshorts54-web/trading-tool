"""optimize.py: search space comes from the rule's own numbers and apply() rewrites only those."""
import unittest
from tt.ideas.schema import Idea
import optimize as O

class Space(unittest.TestCase):
    def test_space_and_apply(self):
        i = Idea(id="x", symbol="BTC-USD", asset="crypto", entry=[["close", ">", "hh_50"], ["dow", "==", 6], ["ret_1", "<", -0.1]],
                 stop={"atr": 3}, time_exit_bars=20)
        sp = O.space(i)
        self.assertEqual(sp, {"e02_n": ("int", 50), "e22_v": ("float", -0.1), "stop": ("float", 3.0), "time_exit": ("int", 20)})
        j = O.apply(i, {"e02_n": 30, "e22_v": -0.2, "stop": 2.0, "time_exit": 9})
        self.assertEqual(j.entry, [["close", ">", "hh_30"], ["dow", "==", 6], ["ret_1", "<", -0.2]])
        self.assertEqual((j.stop, j.time_exit_bars, i.entry[0][2]), ({"atr": 2.0}, 9, "hh_50"))

if __name__ == "__main__": unittest.main()
