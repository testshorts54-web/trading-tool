"""Offline tests for public-data parsers: venue spread check (ported from flow test_arbitrage.py), Kraken pairs,
Hyperliquid parsing and its POST allowlist, stablecoin change, hourly candle fixtures."""
import unittest
from pathlib import Path
from tt import http
from tt.sources import venues as V, perps, sentiment, crypto, series
FX = Path(__file__).parent / "fixtures"

def q(venue, bid, ask, source_id=None, ccy="USD"): return V.Quote(venue, "BTC/USD", bid, ask, None, source_id or f"{venue}:ticker", ccy)

class Venues(unittest.TestCase):
    def test_spread_uses_ask_bid_and_subtracts_fees(self):
        o = V.spot_spread_check(q("kraken", 99, 100), q("coinbase", 101, 102), 0.10)
        self.assertEqual(o["price_basis"], "ask/bid"); self.assertAlmostEqual(o["gross_spread_pct"], 1.0)
        self.assertAlmostEqual(o["net_spread_pct"], 0.8); self.assertTrue(o["positive_after_fees"])
    def test_fees_can_kill_it(self):
        o = V.spot_spread_check(q("kraken", 99.9, 100), q("coinbase", 100.1, 100.2), 0.10)
        self.assertAlmostEqual(o["gross_spread_pct"], 0.1); self.assertFalse(o["positive_after_fees"])
    def test_rejects_same_source_missing_and_ccy(self):
        with self.assertRaises(V.IdenticalSourceError): V.spot_spread_check(q("kraken", 99, 100), q("kraken", 101, 102))
        with self.assertRaises(V.IdenticalSourceError): V.spot_spread_check(q("a", 99, 100, "x"), q("b", 99, 100, "x"))
        with self.assertRaises(ValueError): V.spot_spread_check(None, q("coinbase", 101, 102))
        with self.assertRaises(ValueError): V.spot_spread_check(q("kraken", 99, 100), q("binance.us", 101, 102, ccy="USDT"))
    def test_kraken_pair_and_sanity(self):
        pairs = {"XXBTZUSD": {"wsname": "XBT/USD"}, "XXBTZEUR": {"wsname": "XBT/EUR"}, "XDGUSD": {"wsname": "XDG/USD"}}
        self.assertEqual(V.kraken_pair("BTC", pairs), "XXBTZUSD"); self.assertEqual(V.kraken_pair("DOGE", pairs), "XDGUSD")
        self.assertIsNone(V.kraken_pair("SOL", pairs))
        s = V.sanity({"a": q("a", 99, 101), "b": q("b", 100, 102), "c": None})
        self.assertAlmostEqual(s["median_mid"], 100.5); self.assertFalse(s["flag"])
        self.assertIsNone(V.sanity({"a": q("a", 99, 101), "b": None}))

class Perps(unittest.TestCase):
    def test_parse_hl(self):
        d = [{"universe": [{"name": "BTC"}, {"name": "OLD", "isDelisted": True}, {"name": "ETH"}]},
             [{"markPx": "100", "funding": "0.00001", "openInterest": "10", "oraclePx": "99"}, {}, {"markPx": "5"}]]
        o = perps.parse_hl(d)
        self.assertAlmostEqual(o["BTC"]["funding_apr_pct"], 0.00001 * 24 * 365 * 100); self.assertAlmostEqual(o["BTC"]["oi_usd"], 1000)
        self.assertIsNone(o["ETH"]["funding_apr_pct"]); self.assertNotIn("OLD", o)
        self.assertIsNone(perps.funding_spread(o["ETH"], {"funding_apr_pct": 5}))
        self.assertAlmostEqual(perps.funding_spread({"funding_apr_pct": 10}, {"funding_apr_pct": 4}), 6)
    def test_post_allowlist_refuses_before_network(self):
        with self.assertRaises(ValueError): http.hl_info({"type": "metaAndAssetCtxs"}, url="https://api.hyperliquid.xyz/other")
        for bad in ({"type": "order"}, {"type": "clearinghouseState", "user": "0x0"}, "metaAndAssetCtxs"):
            with self.assertRaises(ValueError): http.hl_info(bad)

class Series(unittest.TestCase):
    def test_get_allowlist_refuses_before_network(self):
        self.assertEqual(series.ALLOWED_HOSTS, {"data.binance.vision", "community-api.coinmetrics.io", "stablecoins.llama.fi"})
        for bad in ("https://fapi.binance.com/fapi/v1/fundingRate", "http://stablecoins.llama.fi/x", "https://evil.example/community-api.coinmetrics.io"):
            with self.assertRaises(ValueError): series.fetch(bad)
    def test_sma_and_ext_lag(self):
        import datetime as dt
        from unittest import mock
        from tt.ideas import extras
        d0 = dt.date(2024, 1, 1); s = {d0 + dt.timedelta(i): float(i) for i in range(5)}
        self.assertEqual(series.sma(s, 2)[d0 + dt.timedelta(1)], 0.5)
        bars = [dict(date=d0 + dt.timedelta(i)) for i in range(3)]
        with mock.patch.object(series, "load", return_value=s):
            self.assertEqual(extras.build(bars, [["ext:mvrv", ">", 1]], None)["ext:mvrv"], [None, 0.0, 1.0])   # bar D sees D-1

class Misc(unittest.TestCase):
    def test_stablecoin_change(self):
        data = [{"date": str(1700000000 + 86400 * i), "totalCirculatingUSD": {"peggedUSD": 100 + i}} for i in range(40)]
        v, ch, _ = sentiment.stablecoin_change(data, 30)
        self.assertEqual(v, 139); self.assertAlmostEqual(ch, (139 / 109 - 1) * 100)
        self.assertIsNone(sentiment.stablecoin_change(data[:20], 30))
    def test_hourly_fixtures_load(self):
        fs = sorted(FX.glob("*_1h.json")); self.assertEqual(len(fs), 9)
        b = crypto.load_hourly_fixture(FX / "BTCUSDT_1h.json")
        self.assertGreater(len(b), 300); self.assertTrue(all(x["low"] <= x["close"] <= x["high"] for x in b))

if __name__ == "__main__": unittest.main()
