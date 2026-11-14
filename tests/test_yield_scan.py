"""Offline tests for the paper-only yield scan (no network)."""
import unittest
from pathlib import Path
from unittest import mock
import yield_scan as Y
from tt.sources import yields as llama

FX = Path(__file__).parent / "fixtures" / "llama_yields_sample.json"

class Allowlist(unittest.TestCase):
    def test_refuses_before_network(self):
        self.assertEqual(llama.ALLOWED_HOSTS, {"yields.llama.fi"})
        for bad in ("https://evil.example/yields.llama.fi/pools", "http://yields.llama.fi/pools",
                    "https://api.llama.fi/pools"):
            with self.assertRaises(ValueError):
                llama.fetch(bad)

class PickAndFlag(unittest.TestCase):
    def setUp(self):
        import json
        self.pools = json.loads(FX.read_text())["data"]

    def test_prefers_core_market_over_meta(self):
        spec = dict(project="aave-v3", chain="Ethereum", symbol="USDC")
        p = Y.pick(self.pools, spec)
        self.assertIsNone(p.get("poolMeta"))
        self.assertAlmostEqual(p["apy"], 3.8)
        self.assertGreater(p["tvlUsd"], 100_000_000)

    def test_meta_substring(self):
        p = Y.pick(self.pools, dict(project="sky-lending", chain="Ethereum", symbol="STUSDS", meta="Expert"))
        self.assertIn("Expert", p["poolMeta"])
        row = Y.attach(dict(id="x", risk="high", us_access="n", reason="r", category="c",
                            project="sky-lending", chain="Ethereum", symbol="STUSDS", meta="Expert"), p)
        self.assertFalse(row["flag_high"])  # 13.05 < 15
        high = dict(p, apy=24.0)
        self.assertTrue(Y.attach(dict(id="y", risk="high", us_access="n", reason="r", category="c",
                                      project="pendle-v2", chain="Ethereum", symbol="X"), high)["flag_high"])

    def test_missing_pool(self):
        self.assertIsNone(Y.pick(self.pools, dict(project="nope", chain="Ethereum", symbol="USDC")))

    def test_score_skips_blocked_high_thin_and_eth(self):
        base = dict(found=True, flag_high=False, apy=4.0, apy_base=4.0, apy_reward=0, risk="low",
                    us_access="yes", category="CEX earn (US)", id="a", tvl=None)
        self.assertIsNotNone(Y.score(base))
        self.assertIsNone(Y.score(dict(base, us_access="no — restricted")))
        self.assertIsNone(Y.score(dict(base, flag_high=True, apy=40)))
        self.assertIsNone(Y.score(dict(base, category="ETH staking")))
        self.assertIsNone(Y.score(dict(base, risk="high", apy=13.0)))
        self.assertIsNone(Y.score(dict(base, risk="med", tvl=16_000_000, apy=5.11)))
        fat = dict(base, risk="med", tvl=130_000_000, apy=4.5, apy_base=4.5)
        self.assertLess(Y.score(fat), Y.score(base))

if __name__ == "__main__":
    unittest.main()
