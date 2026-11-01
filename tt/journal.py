"""Append an approved idea as a paper row to trade-journal/paper-trades.csv (append-only; never edits rows,
never touches the real trades file)."""
import csv, datetime as dt
from pathlib import Path
PAPER_CSV = Path("/workspace/trade-journal/paper-trades.csv")
HEADER = ["date", "source", "symbol", "direction", "thesis", "entry", "exit_rule", "status", "result"]

def exit_rule(r):
    parts = [f"stop {r['stop']:.4g}"]
    if r["target"]: parts.append(f"target {r['target']:.4g}")
    if r["time_exit_bars"]: parts.append(f"time exit {r['time_exit_bars']} bars")
    return "; ".join(parts) + f"; size {r['size']['qty']} ({r['size']['pct_of_equity']:.1%} of paper equity, risk {r['size']['risk_pct']:.2%})"

def log(idea, risk, verdict, path=PAPER_CSV, today=None):
    if not risk.get("approved"): raise ValueError("risk check not approved; nothing logged")
    p = Path(path)
    if not p.exists(): p.write_text(",".join(HEADER) + "\n")
    with open(p) as f: hdr = next(csv.reader(f))
    if hdr != HEADER: raise ValueError(f"unexpected header in {p}: {hdr}")
    row = [(today or dt.date.today()).isoformat(), f"trading-tool:{idea.source}", idea.symbol, idea.side,
           f"{idea.thesis} [validation {verdict}; idea {idea.id}]", f"{risk['entry']:.4g}", exit_rule(risk), "paper-open", ""]
    with open(p, "a", newline="") as f: csv.writer(f).writerow(row)
    return row
