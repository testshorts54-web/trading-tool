"""Fixture tests for the regime rules on synthetic series (no network)."""
import unittest, datetime as dt, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tt.regime import equities as req, crypto as rcr, combine
import sense

TODAY = dt.date(2026, 10, 31)

def ser(vals, last=dt.date(2026, 10, 30), step=1):
    ds = [last - dt.timedelta(days=step * i) for i in range(len(vals))][::-1]
    return dict(dates=ds, closes=list(vals), source="fixture", asof=ds[-1].isoformat())

def up(n=400, g=0.001): return [100 * (1 + g) ** i for i in range(n)]
def down(n=400, g=0.001): return [100 * (1 - g) ** i for i in range(n)]

def snap(eq, ivol=15.0):
    S = {s: ser(eq) for s in ["SPY", "QQQ", "IWM", "RSP", "TLT", "HYG", "UUP", "GLD", "USO"]}
    S["^VIX"] = ser([ivol] * 300); S["T10Y2Y"] = ser([0.5] * 300)
    S["BTC-USD"] = ser(eq, dt.date(2026, 10, 30)); S["ETH-USD"] = ser(eq)
    return S

class Regime(unittest.TestCase):
    def test_uptrend_is_risk_on(self):
        S = snap(up()); S["IWM"] = ser(up(g=0.002)); S["RSP"] = ser(up(g=0.002)); S["HYG"] = ser(up(g=0.002))
        lab = combine.label(req.rules(S, TODAY), 7)
        self.assertEqual(lab["label"], "risk-on"); self.assertEqual(combine.crypto_label(rcr.rules(S, TODAY))["label"], "risk-on")
    def test_downtrend_high_vix_is_risk_off(self):
        S = snap(down(g=0.002), ivol=32); S["BTC-USD"] = ser(down(g=0.004)); S["IWM"] = ser(down(g=0.004))
        R = req.rules(S, TODAY)
        self.assertEqual(combine.label(R, 7)["label"], "risk-off")
        self.assertEqual(next(r for r in R if r["id"] == "E4")["score"], -1)
        self.assertEqual(combine.crypto_label(rcr.rules(S, TODAY))["label"], "risk-off")
    def test_stale_and_missing_are_unknown_never_guessed(self):
        S = snap(up()); S["SPY"] = ser(up(), last=dt.date(2026, 10, 1)); S["QQQ"] = dict(error="HTTP 503")
        R = {r["id"]: r for r in req.rules(S, TODAY)}
        self.assertEqual(R["E1"]["status"], "unknown"); self.assertIn("stale", R["E1"]["reason"])
        self.assertIn("fetch failed", R["E2"]["reason"]); self.assertIsNone(R["E2"]["score"])
        self.assertEqual(combine.label(list(R.values()), 7)["label"], "unknown")
    def test_every_ok_row_has_source_and_date(self):
        for r in req.rules(snap(up()), TODAY) + rcr.rules(snap(up()), TODAY):
            if r["status"] == "ok": self.assertTrue(r["source"] and r["data_date"] and r["rule"], r["id"])
    def test_changes_vs_history(self):
        S = snap(up()); R = sense.build(S, TODAY); R["changes"] = None
        hist = [dict(run_date="2026-10-30", overall="neutral", crypto="risk-on", scores={"E1": -1})]
        ch = sense.changes(R, hist)[0]
        self.assertIn("overall label neutral -> risk-on", ch); self.assertIn("E1 SPY trend: -1 -> 1", ch)
        self.assertEqual(sense.changes(R, []), ["first run (no earlier history)"])

if __name__ == "__main__": unittest.main()
