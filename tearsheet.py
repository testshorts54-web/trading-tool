#!/usr/bin/env python3
"""QuantStats HTML tearsheet vs BTC buy-and-hold, OOS window only (paper-only research; places nothing).
  python3 tearsheet.py <idea_id> [--oos-from 2023-01-01]     # screened rule: EW daily returns of open positions (stress cost), cash when flat
  python3 tearsheet.py --btc-filter 100 [--oos-from ...]      # baseline: hold BTC while yesterday's close > SMA_N, else cash (stress cost per switch)
-> out/tearsheets/<name>-<date>.html. Daily bars, crypto 365 periods/year. Benchmark passed as a series (no download)."""
import sys, argparse, datetime as dt
from pathlib import Path
import pandas as pd
import quantstats as qs
ROOT = Path(__file__).parent; sys.path.insert(0, str(ROOT))
import screen_batch as SB
from screen_batch import C, schema, scanners, history

def btc_filter(n, oos):
    b = history.load("BTC-USD", "crypto")["bars"]; sma = scanners.series(b, f"sma_{n}"); cost = C.COST_BPS["crypto"][1] / 1e4; out, prev = {}, False
    for i in range(1, len(b)):
        on = sma[i - 1] is not None and b[i - 1]["close"] > sma[i - 1]   # decided on yesterday's close, no look-ahead
        r = (b[i]["close"] / b[i - 1]["close"] - 1 if on else 0.0) - (cost if on != prev else 0.0); prev = on
        if b[i]["date"] >= oos: out[b[i]["date"]] = r
    return out

def main(argv=None):
    a = argparse.ArgumentParser(); a.add_argument("idea", nargs="?"); a.add_argument("--btc-filter", type=int)
    a.add_argument("--oos-from", default="2023-01-01"); x = a.parse_args(argv); oos = dt.date.fromisoformat(x.oos_from)
    if x.btc_filter: name, d = f"btc-sma{x.btc_filter}-filter", btc_filter(x.btc_filter, oos)
    elif x.idea: name, d = x.idea, {dt.date.fromisoformat(k): v for k, v in SB.screen((schema.load(ROOT / "ideas.json")[x.idea], oos, 0))["_daily_oos"].items()}
    else: a.error("give an idea id or --btc-filter N")
    bh = {b["date"]: b["close"] for b in history.load("BTC-USD", "crypto")["bars"]}
    idx = pd.to_datetime(sorted(d)); ret = pd.Series([d[k] for k in sorted(d)], idx, name=name)
    bench = pd.Series([bh[k] / bh[k - dt.timedelta(1)] - 1 for k in sorted(d)], idx, name="BTC hold")
    out = ROOT / "out" / "tearsheets"; out.mkdir(parents=True, exist_ok=True); p = out / f"{name}-{dt.date.today()}.html"
    qs.reports.html(ret, bench, output=str(p), title=f"{name} vs BTC hold, OOS from {x.oos_from} (paper research, not proof)", periods_per_year=365)
    p.write_text(p.read_text().replace('<link rel="shortcut icon" href="https://qtpylib.io/favicon.ico" type="image/x-icon">', ""))  # no remote fetch when opened
    print(p)

if __name__ == "__main__":
    main()
