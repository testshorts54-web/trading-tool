#!/usr/bin/env python3
"""Part B: idea -> validation -> risk check -> paper log. Paper only; never places orders.
  python3 pipeline.py collect                         list ideas + today's watch notes (scanner hits, volume flags, funding)
  python3 pipeline.py validate <id>                   backtest the written rule; writes out/validations/<id>.json
  python3 pipeline.py risk <id> --entry P --equity E  size and check a paper entry (needs a PASS validation)
  python3 pipeline.py log  <id> --entry P --equity E  risk check, then append a paper row to trade-journal/paper-trades.csv"""
import sys, json, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from tt import validate, risk, journal, indicators as ind
from tt.ideas import schema, scanners
from tt.sources import history, perps

ROOT = Path(__file__).parent; OUT = ROOT / "out"; IDEAS = ROOT / "ideas.json"
VOLUME = Path("/workspace/volume-tracker/volume_state.json")
WATCH = [("SPY", "equity"), ("QQQ", "equity"), ("IWM", "equity"), ("BTC-USD", "crypto"), ("ETH-USD", "crypto")]

def collect(ideas):
    notes, gaps = [], []
    for i in ideas.values():
        hits, g = scanners.scan(sorted(set(WATCH) | {(i.symbol, i.asset)}), i.entry, history.load); gaps += g
        notes += [f"scanner {i.id}: entry rule true on {h['symbol']} ({h['date']})" for h in hits]
    if VOLUME.exists():
        v = json.loads(VOLUME.read_text())
        notes += [f"volume-tracker {s}: {', '.join(t['flags'])} (asof {t.get('asof')})" for s, t in v.get("tickers", {}).items() if t.get("flags")]
    else: gaps.append("volume-tracker state not found")
    hl = perps.hyperliquid()
    if "error" in hl: gaps.append(hl["error"])
    else: notes += [f"funding {k}: {d['funding_apr_pct']:+.1f}% APR (Hyperliquid) - extreme" for k, d in hl["data"].items()
                    if d["funding_apr_pct"] is not None and abs(d["funding_apr_pct"]) >= 30]
    return dict(ideas=[dict(id=i.id, symbol=i.symbol, problems=i.problems()) for i in ideas.values()], watch_notes=notes, gaps=gaps,
                note="watch notes are leads only; an idea needs a written entry/stop/exit in ideas.json before validation")

def main(argv=None):
    a = argparse.ArgumentParser(); a.add_argument("cmd", choices=["collect", "validate", "risk", "log"]); a.add_argument("id", nargs="?")
    a.add_argument("--entry", type=float); a.add_argument("--equity", type=float); a.add_argument("--ideas", default=str(IDEAS))
    a.add_argument("--journal", default=str(journal.PAPER_CSV)); a.add_argument("--out", default=str(OUT))
    x = a.parse_args(argv); ideas = schema.load(x.ideas); out = Path(x.out)
    if x.cmd == "collect": print(json.dumps(collect(ideas), indent=1)); return
    idea = ideas[x.id]; vp = out / "validations" / f"{idea.id}.json"
    if x.cmd == "validate":
        h = history.load(idea.symbol, idea.asset)
        r = dict(idea=idea.id, verdict="INSUFFICIENT", reasons=[h["error"]]) if "error" in h else validate.run(idea, h)
        vp.parent.mkdir(parents=True, exist_ok=True); vp.write_text(json.dumps(r, indent=1, default=str)); print(json.dumps(r, indent=1, default=str)); return
    v = json.loads(vp.read_text()) if vp.exists() else {}
    h = history.load(idea.symbol, idea.asset); atr = None
    if "error" not in h:
        b = h["bars"]; atr = ind.atr_s([y["high"] for y in b], [y["low"] for y in b], [y["close"] for y in b], 14)[-1]
    r = risk.check(idea, x.entry, x.equity, v.get("verdict"), atr, risk.latest_regime(out), out / "risk_state.json")
    print(json.dumps(r, indent=1, default=str))
    if x.cmd == "log":
        if r["approved"]: print("logged:", journal.log(idea, r, v["verdict"], x.journal))
        else: print("not logged: risk check rejected")

if __name__ == "__main__":
    main()
