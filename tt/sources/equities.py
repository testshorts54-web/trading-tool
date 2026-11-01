"""Daily closes for US ETFs/indices. Primary: yfinance (Yahoo, dividend-adjusted). Fallback: Stooq CSV
(reuses volume-tracker/track.py fetch_stooq). Returns dict(dates, closes, source, asof) or dict(error=...)."""
import sys, datetime as dt
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")

def _drop_partial(dates, closes):
    now = dt.datetime.now(ET)
    if dates and dates[-1] == now.date() and (now.hour, now.minute) < (16, 30):
        return dates[:-1], closes[:-1]   # today's bar is intraday, not a close
    return dates, closes

def _yf(sym):
    import yfinance as yf
    df = yf.Ticker(sym).history(period="2y", interval="1d", auto_adjust=True)
    df = df.dropna(subset=["Close"])
    if df.empty: raise RuntimeError("empty yfinance frame")
    return [d.date() for d in df.index], [float(x) for x in df["Close"]]

def _stooq(sym):
    sys.path.insert(0, "/workspace/volume-tracker")
    from track import fetch_stooq
    df = fetch_stooq(sym)
    return [d.date() for d in df.index], [float(x) for x in df["Close"]]

def daily(sym, stooq_sym=None):
    errs = []
    for name, fn, s in (("Yahoo Finance via yfinance (adjusted close)", _yf, sym),
                        ("Stooq CSV", _stooq, stooq_sym)):
        if not s: continue
        try:
            d, c = _drop_partial(*fn(s))
            if len(c) < 2: raise RuntimeError("too few rows")
            return dict(dates=d, closes=c, source=f"{name} [{s}]", asof=d[-1].isoformat())
        except Exception as e:
            errs.append(f"{name}: {e}")
    return dict(error="; ".join(errs))
