"""Shared helpers: freshness check, per-asset metrics, rule rows."""
import datetime as dt
from tt import indicators as ind
from tt.config import MAX_AGE_DAYS

def problem(s, kind, today, need=1):
    """Return a reason string if series s is missing, stale or too short, else None."""
    if s is None: return "not fetched"
    if "error" in s: return f"fetch failed: {s['error'][:160]}"
    age = (today - s["dates"][-1]).days
    if age > MAX_AGE_DAYS[kind]: return f"stale: last data {s['asof']} is {age} days old (limit {MAX_AGE_DAYS[kind]})"
    if len(s["closes"]) < need: return f"too little history: {len(s['closes'])} rows, need {need}"
    return None

def metrics(s, periods=252):
    d, v = s["dates"], s["closes"]
    m = dict(close=v[-1], sma50=ind.sma(v, 50), sma100=ind.sma(v, 100), sma200=ind.sma(v, 200), rsi14=ind.rsi(v),
             ret_1m=ind.ret_days(d, v, 30), ret_3m=ind.ret_days(d, v, 91), ret_6m=ind.ret_days(d, v, 182),
             dd_1y=ind.drawdown(v, periods), vol20=ind.realized_vol(v, 20, periods))
    return m

def trend_score(m):
    c, a, b = m["close"], m["sma50"], m["sma200"]
    if a is None or b is None: return None, "need 200 closes"
    if c > b and a > b: return 1, "close > SMA200 and SMA50 > SMA200 -> uptrend (+1)"
    if c < b and a < b: return -1, "close < SMA200 and SMA50 < SMA200 -> downtrend (-1)"
    return 0, "mixed (close and SMA50 on different sides of SMA200) -> 0"

def band(x, hi, lo, unit="", fmt="{:+.1%}"):
    """+1 if x > hi, -1 if x < lo, else 0, with the rule text."""
    if x is None: return None, "value unavailable"
    f = lambda y: fmt.format(y) + unit
    if x > hi: return 1, f"{f(x)} > {f(hi)} (+1)"
    if x < lo: return -1, f"{f(x)} < {f(lo)} (-1)"
    return 0, f"{f(lo)} <= {f(x)} <= {f(hi)} (0)"

def row(rid, name, scored, value=None, score=None, rule="", src=None, unknown=None):
    """unknown: reason string -> score None, status unknown. src: list of series dicts."""
    src = [s for s in (src or []) if s and "error" not in s]
    r = dict(id=rid, name=name, scored=scored, value=value, score=None if unknown else score,
             rule=rule, status="unknown" if unknown else "ok", reason=unknown,
             source="; ".join(s["source"] for s in src) or None,
             data_date=min((s["asof"] for s in src), default=None))
    if not unknown and scored and score is None:
        r["status"], r["reason"] = "unknown", rule
    return r
