"""Declarative entry rules (rewrite of flow scanner/rules.py). A rule is a list of [left, op, right] conditions,
ANDed; {"any": [rules...]} ORs rules. left/right are metric names or numbers. Metric names:
close, open, high, low, sma_N, ema_N, rsi_N, atr_N, ret_N (N-bar return), hh_N/ll_N (highest/lowest close of the
prior N bars, today excluded), dd_N (close vs highest close of the last N bars, incl. today, minus 1), rv_N (stdev of
daily returns over N), volr_N (volume / mean volume of the prior N bars; needs a volume column), bbwp_N (percentile
0..1 of today's 20-bar Bollinger width within the last N bars), dow (Mon=0), dom (day of month), month, plus any extra
series passed in (e.g. "BTC-USD:sma_100" cross-asset series from tt/ideas/extras.py).
A missing metric makes the condition False; an empty rule is False."""
import operator, re
from tt import indicators as ind
OPF = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le, "==": operator.eq}

def series(bars, name, cache=None, extra=None):
    cache = cache if cache is not None else {}
    if name in cache: return cache[name]
    if extra and name in extra: return extra[name]
    c = [b["close"] for b in bars]
    m = re.fullmatch(r"(sma|ema|rsi|atr|ret|hh|ll|dd|rv|volr|bbwp)_(\d+)", name)
    if name in ("close", "open", "high", "low"): s = [b[name] for b in bars]
    elif name in ("dow", "dom", "month"):
        s = [(b["date"].weekday() if name == "dow" else b["date"].day if name == "dom" else b["date"].month) for b in bars]
    elif not m: raise KeyError(f"unknown metric {name!r}")
    elif m.group(1) in ("hh", "ll", "dd", "rv", "volr", "bbwp"): s = _window(bars, c, m.group(1), int(m.group(2)))
    else:
        k, n = m.group(1), int(m.group(2))
        if k == "sma": s = ind.sma_s(c, n)
        elif k == "ema": s = ind.ema_s(c, n)
        elif k == "rsi": s = ind.rsi_s(c, n)
        elif k == "atr": s = ind.atr_s([b["high"] for b in bars], [b["low"] for b in bars], c, n)
        else: s = [None] * n + [c[i] / c[i - n] - 1 for i in range(n, len(c))]
    cache[name] = s; return s

def _window(bars, c, k, n):
    N = len(c); s = [None] * N
    if k == "volr":
        v = [b.get("volume") for b in bars]
        for i in range(n, N):
            w = v[i - n:i]
            if v[i] is not None and None not in w and sum(w) > 0: s[i] = v[i] / (sum(w) / n)
        return s
    if k == "bbwp":
        w = ind.bb_width_s(c, 20)
        for i in range(n - 1, N):
            x = [y for y in w[i - n + 1:i + 1] if y is not None]
            if w[i] is not None and len(x) == n: s[i] = sum(y <= w[i] for y in x) / n
        return s
    if k == "rv":
        r = [None] + [c[i] / c[i - 1] - 1 for i in range(1, N)]
        for i in range(n, N):
            x = r[i - n + 1:i + 1]; mu = sum(x) / n; s[i] = (sum((y - mu) ** 2 for y in x) / (n - 1)) ** 0.5
        return s
    for i in range(n, N):
        if k == "hh": s[i] = max(c[i - n:i])
        elif k == "ll": s[i] = min(c[i - n:i])
        else: s[i] = c[i] / max(c[i - n + 1:i + 1]) - 1
    return s

def _val(bars, x, i, cache, extra):
    return float(x) if isinstance(x, (int, float)) else series(bars, x, cache, extra)[i]

def missing_inputs(bars, rule, extra=None):
    """Metric names in a rule whose series is entirely None (e.g. volr_N when volume is missing or all zero)."""
    if isinstance(rule, dict): return sorted({n for r in rule.get("any", []) for n in missing_inputs(bars, r, extra)})
    cache = {}
    return sorted({x for c in rule or [] for x in (c[0], c[2]) if isinstance(x, str) and all(v is None for v in series(bars, x, cache, extra))})

def evaluate(bars, rule, extra=None):
    """-> list of bools, one per bar."""
    cache = {}
    if isinstance(rule, dict) and "any" in rule:
        subs = [evaluate(bars, r, extra) for r in rule["any"]]
        return [any(s[i] for s in subs) for i in range(len(bars))] if subs else [False] * len(bars)
    if not rule: return [False] * len(bars)
    out = []
    for i in range(len(bars)):
        ok = True
        for l, op, r in rule:
            a, b = _val(bars, l, i, cache, extra), _val(bars, r, i, cache, extra)
            if a is None or b is None or not OPF[op](a, b): ok = False; break
        out.append(ok)
    return out

def scan(watch, rule, loader):
    """Today's hits: symbols whose rule is True on the latest bar. loader(sym) -> history dict."""
    from tt.ideas import extras
    hits, gaps = [], []
    for sym, asset in watch:
        h = loader(sym, asset)
        if "error" in h: gaps.append(h["error"]); continue
        b = h["bars"][-400:]
        if evaluate(b, rule, extras.build(b, rule, loader, asset))[-1]: hits.append(dict(symbol=sym, asset=asset, date=h["asof"]))
    return hits, gaps
