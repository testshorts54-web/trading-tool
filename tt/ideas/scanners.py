"""Declarative entry rules (rewrite of flow scanner/rules.py). A rule is a list of [left, op, right] conditions,
ANDed; {"any": [rules...]} ORs rules. left/right are metric names or numbers. Metric names:
close, open, high, low, sma_N, ema_N, rsi_N, atr_N, ret_N (N-bar return), plus any extra series passed in.
A missing metric makes the condition False; an empty rule is False."""
import operator, re
from tt import indicators as ind
OPF = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le, "==": operator.eq}

def series(bars, name, cache=None, extra=None):
    cache = cache if cache is not None else {}
    if name in cache: return cache[name]
    if extra and name in extra: return extra[name]
    c = [b["close"] for b in bars]
    m = re.fullmatch(r"(sma|ema|rsi|atr|ret)_(\d+)", name)
    if name in ("close", "open", "high", "low"): s = [b[name] for b in bars]
    elif not m: raise KeyError(f"unknown metric {name!r}")
    else:
        k, n = m.group(1), int(m.group(2))
        if k == "sma": s = ind.sma_s(c, n)
        elif k == "ema": s = ind.ema_s(c, n)
        elif k == "rsi": s = ind.rsi_s(c, n)
        elif k == "atr": s = ind.atr_s([b["high"] for b in bars], [b["low"] for b in bars], c, n)
        else: s = [None] * n + [c[i] / c[i - n] - 1 for i in range(n, len(c))]
    cache[name] = s; return s

def _val(bars, x, i, cache, extra):
    return float(x) if isinstance(x, (int, float)) else series(bars, x, cache, extra)[i]

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
    hits, gaps = [], []
    for sym, asset in watch:
        h = loader(sym, asset)
        if "error" in h: gaps.append(h["error"]); continue
        if evaluate(h["bars"][-400:], rule)[-1]: hits.append(dict(symbol=sym, asset=asset, date=h["asof"]))
    return hits, gaps
