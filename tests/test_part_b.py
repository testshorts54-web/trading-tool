"""Idea schema, scanner rules, risk rule table, and the end-to-end paper flow: idea -> validate -> risk -> paper row."""
import unittest, tempfile, csv, json, datetime as dt
from pathlib import Path
from tt.ideas.schema import Idea
from tt.ideas import scanners
from tt import validate, risk, journal, config as C

def idea(**kw):
    d = dict(id="t", symbol="X", asset="equity", entry=[["ret_1", "<", -0.015]], stop={"pct": 5}, target={"pct": 2}, time_exit_bars=3, thesis="dip rebound")
    d.update(kw); return Idea(**d)

def bars_with_edge(n=2400):
    """Flat-ish drift; every 10th bar drops 2% and the next bar rallies 2.5% intrabar: the dip rule has a real edge."""
    out, p = [], 100.0
    for i in range(n):
        if i % 10 == 9: o, c = p, p * 0.98
        elif i % 10 == 0 and i: o, c = p, p * 1.025
        else: o, c = p, p * 1.0003
        out.append(dict(date=dt.date(2000, 1, 1) + dt.timedelta(i), open=o, high=max(o, c) * 1.001, low=min(o, c) * 0.999, close=c)); p = c
    return out

class Schema(unittest.TestCase):
    def test_written_exit_required(self):
        self.assertEqual(idea().problems(), [])
        self.assertTrue(idea(target=None, time_exit_bars=None).problems())
        self.assertTrue(idea(stop={}).problems()); self.assertTrue(idea(side="short").problems())
        self.assertTrue(idea(entry=[["rsi_2", "~", 3]]).problems())

class Scanner(unittest.TestCase):
    B = [dict(open=c, high=c, low=c, close=c) for c in (1, 2, 3, 2, 5)]
    def test_ops_missing_empty_any(self):
        self.assertEqual(scanners.evaluate(self.B, [["close", ">", 2]]), [False, False, True, False, True])
        self.assertEqual(scanners.evaluate(self.B, [["close", ">", "sma_2"]]), [False, True, True, False, True])  # sma_2 missing on bar 0 -> False
        self.assertEqual(scanners.evaluate(self.B, []), [False] * 5)
        self.assertEqual(scanners.evaluate(self.B, {"any": [[["close", "==", 1]], [["close", ">=", 5]]]}), [True, False, False, False, True])
        with self.assertRaises(KeyError): scanners.evaluate(self.B, [["bogus_3", ">", 1]])

class Risk(unittest.TestCase):
    def chk(self, **kw):
        a = dict(idea=idea(), entry=100.0, equity=100_000, verdict="PASS", regime=dict(run_date="d", overall="neutral", crypto="neutral"))
        a.update(kw); return risk.check(**a)
    def test_rule_table(self):
        r = self.chk(); self.assertTrue(r["approved"])
        self.assertEqual(r["size"]["qty"], 100); self.assertEqual(r["size"]["binding"], "position cap")   # 10% cap binds at a 5% stop
        r = self.chk(idea=idea(stop={"pct": 20}))                                                         # wide stop: 1% risk binds
        self.assertEqual(r["size"]["qty"], 50); self.assertAlmostEqual(r["size"]["risk_pct"], 0.01)
        self.assertFalse(self.chk(verdict="FAIL")["approved"]); self.assertFalse(self.chk(verdict=None)["approved"])
        self.assertFalse(self.chk(idea=idea(target=None, time_exit_bars=None))["approved"])
        self.assertFalse(self.chk(idea=idea(stop={"atr": 2}), atr=None)["approved"])
        w = self.chk(regime=dict(run_date="d", overall="risk-off", crypto="risk-on"))
        self.assertTrue(w["approved"]); self.assertTrue(any("risk-off" in x for x in w["warnings"]))
        self.assertFalse(self.chk(regime=dict(run_date="d", overall="risk-off", crypto="x"), block_on_risk_off=True)["approved"])
    def test_breaker_persists(self):
        with tempfile.TemporaryDirectory() as d:
            sp, day = Path(d) / "s.json", dt.date(2026, 10, 30)
            self.assertTrue(self.chk(state_path=sp, today=day)["approved"])
            self.assertTrue(self.chk(state_path=sp, today=day, equity=97_000)["approved"])
            self.assertFalse(self.chk(state_path=sp, today=day, equity=95_900)["approved"])
            self.assertTrue(self.chk(state_path=sp, today=day + dt.timedelta(1), equity=95_900)["approved"])  # new day, new baseline

class EndToEnd(unittest.TestCase):
    def test_idea_to_paper_row(self):
        i = idea(); v = validate.run(i, dict(bars=bars_with_edge(), source="synthetic"), draws=200)
        self.assertEqual(v["verdict"], "PASS", v.get("reasons")); self.assertLess(v["null"]["p_value"], 0.05)
        r = risk.check(i, 100.0, 50_000, v["verdict"], regime=dict(run_date="d", overall="neutral", crypto="neutral"))
        self.assertTrue(r["approved"])
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "paper.csv"; journal.log(i, r, v["verdict"], p, dt.date(2026, 10, 31))
            rows = list(csv.DictReader(open(p)))
            self.assertEqual(len(rows), 1); self.assertEqual(rows[0]["status"], "paper-open"); self.assertIn("validation PASS", rows[0]["thesis"])
            with self.assertRaises(ValueError): journal.log(i, dict(approved=False), "FAIL", p)
            self.assertEqual(len(list(csv.DictReader(open(p)))), 1)
    def test_too_few_trades_is_insufficient(self):
        v = validate.run(idea(), dict(bars=bars_with_edge(600)), draws=10)
        self.assertEqual(v["verdict"], "INSUFFICIENT"); self.assertIn("insufficient data", v["reasons"][0])
    def test_stress_costs_and_header(self):
        self.assertEqual(C.COST_BPS, {"equity": (10, 20), "crypto": (25, 90)})
        self.assertEqual(journal.HEADER, next(csv.reader(open(journal.PAPER_CSV))))

if __name__ == "__main__": unittest.main()
