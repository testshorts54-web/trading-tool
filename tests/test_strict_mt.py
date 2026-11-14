"""Stricter multiple-testing count: ideas in batch + distinct pooled symbol-sets tried."""
import unittest, tempfile, json
from pathlib import Path
import pipeline
from tests.test_part_b import idea

class StrictMT(unittest.TestCase):
    def test_counts_ideas_and_symbol_sets(self):
        with tempfile.TemporaryDirectory() as d:
            reg = Path(d) / "mt.json"; ideas = {f"i{k}": None for k in range(5)}
            self.assertEqual(pipeline.strict_variants(idea(), ideas, ["B", "A"], reg), 6)
            self.assertEqual(pipeline.strict_variants(idea(), ideas, ["A", "B"], reg), 6)   # same set, order ignored
            self.assertEqual(pipeline.strict_variants(idea(), ideas, ["A", "C"], reg), 7)
            self.assertEqual(len(json.loads(reg.read_text())), 2)

    def test_never_below_declared(self):
        with tempfile.TemporaryDirectory() as d:
            i = idea(); i.variants = 99
            self.assertEqual(pipeline.strict_variants(i, {"x": None}, ["A"], Path(d) / "mt.json"), 99)

if __name__ == "__main__":
    unittest.main()
