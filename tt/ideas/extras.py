"""Cross-asset series for entry rules: a metric written "SYM:metric" (e.g. "BTC-USD:sma_100", "BTC-USD:ret_20") is
computed on SYM's own history and aligned to the traded bars by date (None where SYM has no bar that day).
"ext:NAME" (e.g. "ext:mvrv", "ext:btcd.sma_50", "ext:funding_BTCUSDT") is a daily series from tt/sources/series.py,
lagged one day (bar D sees the value for D-1) so a rule never uses a value published after its close."""
import datetime as dt
from tt.ideas import scanners

def names(rule):
    if isinstance(rule, dict): return {n for r in rule.get("any", []) for n in names(r)}
    return {x for c in rule or [] for x in (c[0], c[2]) if isinstance(x, str) and ":" in x}

def build(bars, rule, loader, asset="crypto"):
    out, cache = {}, {}
    for n in sorted(names(rule)):
        sym, metric = n.split(":", 1)
        if sym == "ext":
            from tt.sources import series
            if n not in cache: cache[n] = series.load(metric)
            out[n] = [cache[n].get(b["date"] - dt.timedelta(1)) for b in bars]; continue
        if sym not in cache: cache[sym] = loader(sym, asset)
        h = cache[sym]
        if "error" in h: out[n] = [None] * len(bars); continue
        by = dict(zip((b["date"] for b in h["bars"]), scanners.series(h["bars"], metric)))
        out[n] = [by.get(b["date"]) for b in bars]
    return out
