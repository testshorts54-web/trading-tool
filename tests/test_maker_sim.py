"""Unit tests for the paper maker-complement simulator. No network."""
import unittest
from tt import predict as P
from predict_maker_sim import (
    maker_quotes, fill_from_trade, fill_from_book, mark_pnl, tick_floor,
    estimate_rebate, rebate_share_of, PaperMarket, PaperRebateMarket, summarize
)


class Quotes(unittest.TestCase):
    def test_shades_to_margin_and_does_not_cross(self):
        # yes 0.54/0.55, no 0.45/0.46, margin 2c -> 0.53+0.45=0.98
        q = maker_quotes(0.54, 0.55, 0.45, 0.46, margin=0.02, tick=0.01)
        self.assertEqual(q, (0.53, 0.45))
        self.assertLessEqual(q[0] + q[1], 0.98)
        self.assertLess(q[0], 0.55)
        self.assertLess(q[1], 0.46)

    def test_uses_inside_ask_when_already_under_target(self):
        # wide book, caps already sum to 0.90
        q = maker_quotes(0.40, 0.50, 0.40, 0.50, margin=0.02, tick=0.01)
        self.assertEqual(q, (0.49, 0.49))

    def test_none_when_missing_or_invalid(self):
        self.assertIsNone(maker_quotes(None, 0.5, 0.4, 0.5))
        self.assertIsNone(maker_quotes(0.50, 0.51, 0.49, 0.50, margin=0.0, tick=0.01))
        # 20c margin still quotes, shaded to 0.40+0.40
        self.assertEqual(maker_quotes(0.50, 0.51, 0.49, 0.50, margin=0.20, tick=0.01), (0.4, 0.4))


class Fills(unittest.TestCase):
    def test_sell_at_or_through_hits_bid_buy_does_not(self):
        self.assertEqual(fill_from_trade(0.54, 0.54, "SELL", 8, 10), 8)
        self.assertEqual(fill_from_trade(0.54, 0.53, "SELL", 20, 10), 10)
        self.assertEqual(fill_from_trade(0.54, 0.55, "SELL", 8, 10), 0)
        self.assertEqual(fill_from_trade(0.54, 0.54, "BUY", 8, 10), 0)

    def test_book_ask_at_or_through(self):
        self.assertEqual(fill_from_book(0.54, 0.54, 5, 10), 5)
        self.assertEqual(fill_from_book(0.54, 0.53, None, 10), 10)
        self.assertEqual(fill_from_book(0.54, 0.55, 5, 10), 0)


class PnL(unittest.TestCase):
    def test_pair_locks_edge_one_leg_marks_to_mid(self):
        pair = mark_pnl(10, 0.53, 10, 0.45, 0.60, 0.40)
        self.assertEqual(pair["paired"], 10)
        self.assertEqual(pair["one_leg"], 0)
        self.assertAlmostEqual(pair["locked"], 0.20)  # 10 * (1-0.98)
        self.assertAlmostEqual(pair["total"], 0.20)
        one = mark_pnl(10, 0.53, 0, 0.0, 0.50, 0.50)
        self.assertEqual(one["paired"], 0)
        self.assertEqual(one["one_leg"], 10)
        self.assertAlmostEqual(one["marked"], -0.30)  # 10 * (0.50-0.53)
        self.assertAlmostEqual(one["total"], -0.30)

    def test_tick_floor(self):
        self.assertAlmostEqual(tick_floor(0.549, 0.01), 0.54)
        self.assertAlmostEqual(tick_floor(0.55, 0.01), 0.55)


class ComplementTaker(unittest.TestCase):
    def test_fees_eat_a_raw_gap(self):
        # 0.49+0.49=0.98 raw, crypto 0.07 fee each at ~50c is 0.0175 -> cost 1.015, not flagged
        r = P.complement_taker(0.49, 0.49, 0.07, 0.07, yes_size=100, no_size=100)
        self.assertFalse(r["flagged"])
        self.assertGreater(r["cost"], 1)
        # geopolitics / fee 0 with a 3c gap and depth
        r = P.complement_taker(0.48, 0.49, 0.0, 0.0, yes_size=50, no_size=50)
        self.assertTrue(r["flagged"])
        self.assertAlmostEqual(r["cost"], 0.97)
        self.assertIsNone(P.complement_taker(0.48, 0.49, None, 0.0))


class LedgerRow(unittest.TestCase):
    def test_fill_row_does_not_clash_on_ts(self):
        fl = dict(side="yes", qty=3.0, price=0.53, src="trade", trade_px=0.53, ts=123.0)
        row = dict(type="fill", ts="2026-11-14T18:00:00+00:00", slug="x",
                   side=fl["side"], qty=fl["qty"], price=fl["price"], src=fl["src"],
                   trade_px=fl.get("trade_px"), fill_unix=fl.get("ts"))
        self.assertEqual(row["ts"], "2026-11-14T18:00:00+00:00")
        self.assertEqual(row["fill_unix"], 123.0)


class TestThroughAndQueue(unittest.TestCase):
    def test_through_vs_at_touch_book(self):
        # v1 allows at-touch book prints; v2 through_only allows only prints strictly below
        self.assertEqual(fill_from_book(0.54, 0.54, 5, 10, through_only=False), 5)
        self.assertEqual(fill_from_book(0.54, 0.54, 5, 10, through_only=True), 0.0)
        self.assertEqual(fill_from_book(0.54, 0.53, 5, 10, through_only=True), 5)

    def test_through_vs_at_touch_trade(self):
        # trades through bid always fill; trades at touch fill only without through_only
        self.assertEqual(fill_from_trade(0.54, 0.54, "SELL", 8, 10, through_only=False), 8)
        self.assertEqual(fill_from_trade(0.54, 0.54, "SELL", 8, 10, through_only=True), 0.0)
        self.assertEqual(fill_from_trade(0.54, 0.53, "SELL", 8, 10, through_only=True), 8)

    def test_queue_ahead(self):
        # trade at touch only fills excess beyond queue_ahead
        self.assertEqual(fill_from_trade(0.54, 0.54, "SELL", 8, 10, queue_ahead=0.0), 8)
        self.assertEqual(fill_from_trade(0.54, 0.54, "SELL", 8, 10, queue_ahead=5.0), 3)
        self.assertEqual(fill_from_trade(0.54, 0.54, "SELL", 8, 10, queue_ahead=8.0), 0)
        self.assertEqual(fill_from_trade(0.54, 0.54, "SELL", 8, 10, queue_ahead=12.0), 0)
        # through trade bypasses queue_ahead
        self.assertEqual(fill_from_trade(0.54, 0.53, "SELL", 8, 10, queue_ahead=12.0), 8)


class TestStalePull(unittest.TestCase):
    def test_stale_bid_pulled_no_stale_fill(self):
        meta = dict(tokens=["tok_y", "tok_n"], fee_rate=0.05, slug="test-stale", condition_id="c1", outcomes=["Yes", "No"])
        p = PaperMarket(meta, shares=10, margin=0.02, v2=True, stale=0.03)
        yb = dict(bid=0.50, ask=0.52, bid_sz=10, ask_sz=10, tick=0.01)
        nb = dict(bid=0.46, ask=0.48, bid_sz=10, ask_sz=10, tick=0.01)
        self.assertTrue(p.requote(yb, nb, 100.0))
        self.assertIsNotNone(p.yes_px)
        # book moves away by more than 3c (bid jumps to 0.56)
        yb_moved = dict(bid=0.56, ask=0.58, bid_sz=10, ask_sz=10, tick=0.01)
        p.requote(yb_moved, nb, 101.0)
        # stale quote pulled: resting bid is None
        self.assertIsNone(p.yes_px)
        # subsequent trade at old price does not fill
        fills = p.apply_trades([dict(token_id="tok_y", price=0.50, side="SELL", size=10)], 101.0)
        self.assertEqual(len(fills), 0)


class TestStagger(unittest.TestCase):
    def test_second_leg_only_after_first_fill(self):
        meta = dict(tokens=["tok_y", "tok_n"], fee_rate=0.05, slug="test-stagger", condition_id="c2", outcomes=["Yes", "No"])
        p = PaperMarket(meta, shares=10, margin=0.02, v2=True, stagger="first")
        yb = dict(bid=0.50, ask=0.52, bid_sz=10, ask_sz=10, tick=0.01)
        nb = dict(bid=0.46, ask=0.48, bid_sz=10, ask_sz=10, tick=0.01)
        p.requote(yb, nb, 100.0)
        # initially only first leg (YES) is quoted
        self.assertIsNotNone(p.yes_px)
        self.assertIsNone(p.no_px)
        # trade on second leg does not fill
        fills_n = p.apply_trades([dict(token_id="tok_n", price=0.46, side="SELL", size=5)], 101.0)
        self.assertEqual(len(fills_n), 0)
        self.assertEqual(p.no_qty, 0.0)
        # first leg fills
        fills_y = p.apply_trades([dict(token_id="tok_y", price=p.yes_px, side="SELL", size=10)], 102.0)
        self.assertEqual(len(fills_y), 1)
        self.assertEqual(p.yes_qty, 10.0)
        # second leg is now quoted and satisfies 1-margin constraint
        p.requote(yb, nb, 103.0)
        self.assertIsNotNone(p.no_px)
        self.assertLessEqual(p.yes_px + p.no_px, 1.0 - 0.02 + 1e-9)
        # trade on second leg now fills to complete the pair
        fills_n2 = p.apply_trades([dict(token_id="tok_n", price=p.no_px, side="SELL", size=10)], 104.0)
        self.assertEqual(len(fills_n2), 1)
        self.assertEqual(p.no_qty, 10.0)
        self.assertTrue(p.done)


class TestOneLegExit(unittest.TestCase):
    def test_loss_cap_exit_at_bid_plus_fee(self):
        meta = dict(tokens=["tok_y", "tok_n"], fee_rate=0.05, slug="test-loss-cap", condition_id="c3", outcomes=["Yes", "No"])
        p = PaperMarket(meta, shares=10, margin=0.02, v2=True, complete_sec=300, loss_cap=0.50)
        p.yes_qty = 10.0
        p.yes_px = 0.50
        p.yes_fill_ts = 100.0
        # book bid drops to 0.44: gross loss = 10*(0.50-0.44)=0.60; fee=10*0.05*0.44*(1-0.44)=0.1232
        yb = dict(bid=0.44, ask=0.46, tick=0.01)
        ev = p.check_exit(yb, dict(bid=0.40, ask=0.42), 150.0)
        self.assertIsNotNone(ev)
        self.assertEqual(ev["type"], "exit")
        self.assertEqual(ev["reason"], "loss_cap")
        self.assertEqual(ev["exit_px"], 0.44)
        self.assertAlmostEqual(ev["gross_loss"], 0.60)
        self.assertAlmostEqual(ev["fee"], 0.1232)
        self.assertAlmostEqual(ev["net_loss"], 0.7232)
        self.assertTrue(p.exited)
        self.assertEqual(p.yes_qty, 0.0)

    def test_complete_sec_timeout_exit(self):
        meta = dict(tokens=["tok_y", "tok_n"], fee_rate=0.05, slug="test-timeout", condition_id="c4", outcomes=["Yes", "No"])
        p = PaperMarket(meta, shares=10, margin=0.02, v2=True, complete_sec=300, loss_cap=5.0)
        p.yes_qty = 10.0
        p.yes_px = 0.50
        p.yes_fill_ts = 100.0
        # 305s later, exit triggers on timeout
        yb = dict(bid=0.49, ask=0.51, tick=0.01)
        ev = p.check_exit(yb, dict(bid=0.40, ask=0.42), 405.0)
        self.assertIsNotNone(ev)
        self.assertEqual(ev["reason"], "timeout")
        self.assertEqual(ev["exit_px"], 0.49)

    def test_exit_fee_unknown_when_rate_missing(self):
        meta = dict(tokens=["tok_y", "tok_n"], fee_rate=None, slug="test-unknown-fee", condition_id="c5", outcomes=["Yes", "No"])
        p = PaperMarket(meta, shares=10, margin=0.02, v2=True, loss_cap=0.50)
        p.yes_qty = 10.0
        p.yes_px = 0.50
        p.yes_fill_ts = 100.0
        yb = dict(bid=0.44, ask=0.46, tick=0.01)
        ev = p.check_exit(yb, dict(bid=0.40, ask=0.42), 150.0)
        self.assertIsNone(ev["fee"])
        self.assertAlmostEqual(ev["net_loss"], 0.60)


class TestRebateEstimateFormula(unittest.TestCase):
    def test_rebate_calculation_and_schedule(self):
        # crypto: share 0.20, fee_rate 0.07 -> fee_equiv = 10*0.07*0.25=0.175, est_rebate=0.035
        reb, fe = estimate_rebate(10, 0.50, 0.07, "crypto")
        self.assertAlmostEqual(fe, 0.175)
        self.assertAlmostEqual(reb, 0.035)

        # sports: share 0.15, fee_rate 0.05 -> fee_equiv = 10*0.05*0.25=0.125, est_rebate=0.01875
        reb_s, fe_s = estimate_rebate(10, 0.50, 0.05, "sports")
        self.assertAlmostEqual(fe_s, 0.125)
        self.assertAlmostEqual(reb_s, 0.01875)

        # politics: share 0.25, fee_rate 0.04 -> fee_equiv = 10*0.04*0.25=0.10, est_rebate=0.025
        reb_p, fe_p = estimate_rebate(10, 0.50, 0.04, "politics")
        self.assertAlmostEqual(fe_p, 0.10)
        self.assertAlmostEqual(reb_p, 0.025)

        # geopolitics: share 0.0 -> est_rebate 0.0
        reb_g, fe_g = estimate_rebate(10, 0.50, 0.0, "geopolitics")
        self.assertAlmostEqual(reb_g, 0.0)

        # missing rate or unknown category returns None (UNKNOWN)
        self.assertEqual(estimate_rebate(10, 0.50, None, "politics"), (None, None))
        self.assertEqual(estimate_rebate(10, 0.50, 0.05, "unmapped_cat"), (None, None))


class TestRebatePnLIsolation(unittest.TestCase):
    def test_rebate_columns_not_added_to_locked_pnl(self):
        meta = dict(tokens=["tok_y", "tok_n"], fee_rate=0.05, slug="test-iso", condition_id="c6", outcomes=["Yes", "No"], category="sports")
        p = PaperMarket(meta, shares=10, margin=0.02)
        p.yes_qty = 10.0
        p.yes_px = 0.53
        p.no_qty = 10.0
        p.no_px = 0.45
        # locked complement P&L = 10 * (1 - 0.98) = 0.20

        rm = PaperRebateMarket(meta, inv_cap=10.0)
        rm._on_fill("yes", "buy", 10.0, 0.40, 100.0, "trade", 0.40)
        rm._on_fill("yes", "sell", 10.0, 0.43, 101.0, "trade", 0.43)
        # rebate captured round-trip spread = 10 * (0.43 - 0.40) = 0.30

        books = {
            "tok_y": dict(bid=0.41, ask=0.43, tick=0.01, mid=0.42, bid_sz=10, ask_sz=10),
            "tok_n": dict(bid=0.55, ask=0.57, tick=0.01, mid=0.56, bid_sz=10, ask_sz=10),
        }
        summary = summarize([p], books, "2026-11-14T10:00:00", "2026-11-14T11:00:00", rebate_markets=[rm])

        # locked_pnl must be strictly 0.20 and must NOT include spread_pnl, est_rebate, or liq_score
        self.assertAlmostEqual(summary["locked_pnl"], 0.20)
        self.assertAlmostEqual(summary["spread_pnl"], 0.30)
        self.assertGreater(summary["liq_score"], 0.0)
        self.assertGreater(summary["est_rebate"], 0.0)
        self.assertNotEqual(summary["locked_pnl"], summary["locked_pnl"] + summary["spread_pnl"])


if __name__ == "__main__":
    unittest.main()
