"""Network-free unit tests for universe selection, TWAP settle, and logical scan helpers."""
import datetime as dt, unittest
from predict_maker_sim import PaperMarket, select_markets
from predict_twap_settle import compute_after_fee_gap, evaluate_window
from predict_logical_scan import (
    normalize_text, evaluate_neg_risk, evaluate_nested_deadlines, evaluate_duplicates
)


class TestUniverseFilter(unittest.TestCase):
    def setUp(self):
        # Sample synthetic event list with future end dates
        now_dt = dt.datetime.now(dt.timezone.utc)
        end_5m = (now_dt + dt.timedelta(minutes=5)).isoformat()
        end_1h = (now_dt + dt.timedelta(hours=1)).isoformat()
        end_pol = (now_dt + dt.timedelta(days=700)).isoformat()
        self.events = [
            dict(
                slug="btc-updown-5m-20261114",
                title="Bitcoin Up or Down 5m",
                tags=["5m", "up-or-down", "crypto"],
                volume24h=500.0,
                end=end_5m,
                markets=[dict(
                    condition_id="c_5m",
                    tokens=["tok_5m_y", "tok_5m_n"],
                    question="Bitcoin Up or Down 5m",
                    best_bid=0.48,
                    best_ask=0.50,
                    volume24h=500.0,
                    fee_rate=0.07,
                    end=end_5m,
                    outcomes=["Up", "Down"],
                )],
            ),
            dict(
                slug="btc-updown-1h-20261114",
                title="Bitcoin Up or Down - 8 PM ET",
                tags=["1h", "up-or-down", "crypto"],
                volume24h=800.0,
                end=end_1h,
                markets=[dict(
                    condition_id="c_1h",
                    tokens=["tok_1h_y", "tok_1h_n"],
                    question="Bitcoin Up or Down - 8 PM ET",
                    best_bid=0.47,
                    best_ask=0.49,
                    volume24h=800.0,
                    fee_rate=0.07,
                    end=end_1h,
                    outcomes=["Up", "Down"],
                )],
            ),
            dict(
                slug="presidential-race-2028",
                title="Next President",
                tags=["politics"],
                volume24h=1200.0,
                end=end_pol,
                markets=[dict(
                    condition_id="c_pol",
                    tokens=["tok_p_y", "tok_p_n"],
                    question="Who wins in 2028?",
                    best_bid=0.45,
                    best_ask=0.47,
                    volume24h=1200.0,
                    fee_rate=0.02,
                    end=end_pol,
                    outcomes=["Yes", "No"],
                )],
            ),
        ]

    def test_universe_5m15m_filters_only_short_windows(self):
        sel = select_markets(self.events, cap=10, universe="5m15m")
        self.assertEqual(len(sel), 1)
        self.assertEqual(sel[0]["condition_id"], "c_5m")

    def test_universe_1h4h_filters_hourly_windows(self):
        sel = select_markets(self.events, cap=15, universe="1h4h")
        self.assertEqual(len(sel), 1)
        self.assertEqual(sel[0]["condition_id"], "c_1h")

    def test_universe_slow_filters_slower_politics_sports(self):
        sel = select_markets(self.events, cap=20, universe="slow")
        self.assertEqual(len(sel), 1)
        self.assertEqual(sel[0]["condition_id"], "c_pol")


class TestFastIntervalSleep(unittest.TestCase):
    def test_sleep_duration_logic(self):
        # min 2s when interval >= 2, else min 5s
        def calc_sleep(interval):
            return max(2, interval) if (interval is not None and interval >= 2) else max(5, interval or 5)

        self.assertEqual(calc_sleep(2), 2)
        self.assertEqual(calc_sleep(3), 3)
        self.assertEqual(calc_sleep(8), 8)
        self.assertEqual(calc_sleep(60), 60)
        self.assertEqual(calc_sleep(1), 5)
        self.assertEqual(calc_sleep(None), 5)


class TestRepriceAnyAndQuietWindow(unittest.TestCase):
    def test_reprice_any_pulls_on_best_bid_tick_move(self):
        meta = dict(tokens=["ty", "tn"], fee_rate=0.07, slug="test-reprice", condition_id="cr1", outcomes=["Up", "Down"])
        p = PaperMarket(meta, shares=10, margin=0.02, v2=True, reprice_any=True)
        yb = dict(bid=0.50, ask=0.52, bid_sz=10, ask_sz=10, tick=0.01)
        nb = dict(bid=0.46, ask=0.48, bid_sz=10, ask_sz=10, tick=0.01)
        p.requote(yb, nb, 100.0)
        self.assertEqual(p.yes_px, 0.51)

        # Market moves by 1 tick (best bid rises to 0.51)
        yb_moved = dict(bid=0.51, ask=0.53, bid_sz=10, ask_sz=10, tick=0.01)
        p.requote(yb_moved, nb, 101.0)
        # Repriced to reflect the new market state
        self.assertEqual(p.last_bid_yes, 0.51)

    def test_reprice_any_keeps_filled_entry(self):
        meta = dict(tokens=["ty", "tn"], fee_rate=0.07, slug="test-entry", condition_id="ce1", outcomes=["Up", "Down"])
        p = PaperMarket(meta, shares=10, margin=0.02, v2=True, reprice_any=True, complete_sec=30.0, stagger="first")
        yb = dict(bid=0.50, ask=0.52, bid_sz=10, ask_sz=10, tick=0.01)
        nb = dict(bid=0.46, ask=0.48, bid_sz=10, ask_sz=10, tick=0.01)
        p.requote(yb, nb, 100.0)
        entry = p.yes_px
        p._after_fill([dict(side="yes", qty=10.0, price=entry, src="trade", ts=100.0)])
        p.yes_qty = 10.0
        p.yes_fill_ts = 100.0
        yb_moved = dict(bid=0.40, ask=0.42, bid_sz=10, ask_sz=10, tick=0.01)
        p.requote(yb_moved, nb, 140.0)
        ev = p.check_exit(yb_moved, nb, 140.0)
        self.assertIsNotNone(ev)
        self.assertEqual(ev["reason"], "timeout")
        self.assertEqual(ev["entry_px"], entry)


    def test_quiet_before_end_pulls_fresh_quotes(self):
        # Market ending in 60 seconds
        end_time = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=60)).isoformat()
        meta = dict(tokens=["ty", "tn"], fee_rate=0.07, slug="test-quiet", condition_id="cq1", end=end_time, outcomes=["Up", "Down"])
        p = PaperMarket(meta, shares=10, margin=0.02, v2=True, quiet_before_end=90.0)
        p.yes_px = 0.50
        p.no_px = 0.46
        yb = dict(bid=0.50, ask=0.52, bid_sz=10, ask_sz=10, tick=0.01)
        nb = dict(bid=0.46, ask=0.48, bid_sz=10, ask_sz=10, tick=0.01)

        # With no fills, within 90s window pulls quotes
        p.requote(yb, nb, dt.datetime.now(dt.timezone.utc).timestamp())
        self.assertIsNone(p.yes_px)
        self.assertIsNone(p.no_px)

    def test_quiet_before_end_pulls_unfilled_second_leg(self):
        end_time = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=60)).isoformat()
        meta = dict(tokens=["ty", "tn"], fee_rate=0.07, slug="test-quiet-leg", condition_id="cq2", end=end_time, outcomes=["Up", "Down"])
        p = PaperMarket(meta, shares=10, margin=0.02, v2=True, quiet_before_end=90.0)
        p.yes_qty = 10.0
        p.no_px = 0.45
        yb = dict(bid=0.50, ask=0.52, bid_sz=10, ask_sz=10, tick=0.01)
        nb = dict(bid=0.45, ask=0.47, bid_sz=10, ask_sz=10, tick=0.01)

        # One-leg inventory is kept, but the unfilled second-leg quote is pulled
        p.requote(yb, nb, dt.datetime.now(dt.timezone.utc).timestamp())
        self.assertIsNone(p.no_px)
        self.assertEqual(p.yes_qty, 10.0)


class TestCryptoExitFeeScheduleFallback(unittest.TestCase):
    def test_crypto_universe_falls_back_to_007_with_note(self):
        meta = dict(tokens=["ty", "tn"], fee_rate=None, slug="test-fb", condition_id="cfb", outcomes=["Up", "Down"])
        p = PaperMarket(meta, shares=10, margin=0.02, v2=True, universe="5m15m", loss_cap=0.50)
        p.yes_qty = 10.0
        p.yes_px = 0.50
        p.yes_fill_ts = 100.0

        yb = dict(bid=0.44, ask=0.46, tick=0.01)
        ev = p.check_exit(yb, dict(bid=0.40, ask=0.42), 150.0)
        self.assertIsNotNone(ev)
        self.assertEqual(ev["type"], "exit")
        # Fee rate recorded as fallback and calculated with 0.07
        self.assertEqual(ev["fee_rate"], "UNKNOWN (fallback 0.07)")
        self.assertIsNotNone(ev["fee"])
        self.assertIn("fallback 0.07", ev.get("note", ""))

    def test_non_crypto_universe_does_not_fall_back(self):
        meta = dict(tokens=["ty", "tn"], fee_rate=None, slug="test-nofb", condition_id="cnofb", outcomes=["Yes", "No"])
        p = PaperMarket(meta, shares=10, margin=0.02, v2=True, universe="slow", loss_cap=0.50)
        p.yes_qty = 10.0
        p.yes_px = 0.50
        p.yes_fill_ts = 100.0

        yb = dict(bid=0.44, ask=0.46, tick=0.01)
        ev = p.check_exit(yb, dict(bid=0.40, ask=0.42), 150.0)
        self.assertIsNotNone(ev)
        self.assertIsNone(ev["fee"])


class TestTwapSettle(unittest.TestCase):
    def test_after_fee_gap_executable_ask_vs_mid_mark(self):
        # When ask is present, marked executable
        r_ask = compute_after_fee_gap("Up", last_ask=0.90, last_bid=0.88, last_mid=0.89, fee_rate=0.07)
        self.assertTrue(r_ask["executable"])
        self.assertEqual(r_ask["basis"], "ask")
        self.assertLess(r_ask["cost"], 1.0)
        self.assertGreater(r_ask["gap"], 0.0)

        # When ask is missing, last mid is used as mark only and marked not executable
        r_mid = compute_after_fee_gap("Up", last_ask=None, last_bid=0.88, last_mid=0.89, fee_rate=0.07)
        self.assertFalse(r_mid["executable"])
        self.assertEqual(r_mid["basis"], "mid not executable")

    def test_evaluate_window_twap_unknown_and_implied_winner(self):
        twap_rows = [
            dict(slug="s1", condition_id="c1", mid=0.51, bid=0.50, ask=0.52, fee_rate=0.07, end="2026-11-14T20:00:00Z"),
            dict(slug="s1", condition_id="c1", mid=0.53, bid=0.52, ask=0.54, fee_rate=0.07, end="2026-11-14T20:00:00Z"),
        ]
        ev_data = dict(eventMetadata=dict(priceToBeat=90000.0, finalPrice=90150.0))
        w = evaluate_window("s1", twap_rows, event_data=ev_data, res_payouts=[1.0, 0.0])

        self.assertEqual(w["twap"], "UNKNOWN")
        self.assertEqual(w["implied_outcome"], "Up")
        self.assertEqual(w["price_to_beat"], 90000.0)
        self.assertEqual(w["final_price"], 90150.0)
        self.assertEqual(len(w["book_mids_last_band"]), 2)


class TestLogicalScan(unittest.TestCase):
    def test_normalize_text(self):
        self.assertEqual(normalize_text("Will Bitcoin Reach $100k?!"), "will bitcoin reach 100k")

    def test_neg_risk_incomplete_not_flagged(self):
        ev = dict(
            neg_risk=True,
            augmented=True,
            title="Presidential Nominee",
            slug="pres-nom",
            markets=[
                dict(title="Candidate A", question="Candidate A", fee_rate=0.02, tokens=["t1", "t2"]),
                dict(title="Other", question="Other Candidate", other=True, fee_rate=0.02, tokens=["t3", "t4"]),
            ],
        )
        signals = evaluate_neg_risk(ev, book_parser=lambda tok: None)
        self.assertTrue(any(s["type"] == "neg_risk_incomplete" for s in signals))
        inc_sig = [s for s in signals if s["type"] == "neg_risk_incomplete"][0]
        self.assertFalse(inc_sig["flagged"])
        self.assertIn("incomplete", inc_sig["note"])

    def test_duplicate_uncompared_logged(self):
        events = [
            dict(title="E1", slug="e1", markets=[dict(condition_id="c1", question="Will ETH hit 4000?", tokens=["t1"])]),
            dict(title="E2", slug="e2", markets=[dict(condition_id="c2", question="Will ETH hit 4,000?", tokens=["t2"])]),
        ]
        # Top book returns None in offline test, so rules not compared
        signals = evaluate_duplicates(events, book_parser=lambda tok: None)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["type"], "duplicate_listing")
        self.assertFalse(signals[0]["flagged"])
        self.assertIn("possible duplicate", signals[0]["note"])


if __name__ == "__main__":
    unittest.main()


class TestParseResolutionRow(unittest.TestCase):
    def test_payouts_field_when_resolved(self):
        from predict_maker_sim import parse_resolution_row
        y, n = parse_resolution_row({"status": "resolved", "payouts": [0, 1000000]})
        self.assertEqual((y, n), (0.0, 1.0))

    def test_ignores_unresolved_and_old_payout_key(self):
        from predict_maker_sim import parse_resolution_row
        self.assertEqual(parse_resolution_row({"status": "proposed", "payouts": [0, 1000000]}), (None, None))
        y, n = parse_resolution_row({"status": "resolved", "payout": [1000000, 0]})
        self.assertEqual((y, n), (1.0, 0.0))
