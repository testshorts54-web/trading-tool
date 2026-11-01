"""FRED public CSV (same endpoint as crown-monitor/fetch_fred.py; no key)."""
import datetime as dt
from tt.http import get

def series(sid, days=420):
    start = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={start}"
    try:
        lines = get(url, ua=False).decode().strip().splitlines()[1:]
        pts = [(dt.date.fromisoformat(a), float(b)) for a, b in (l.split(",") for l in lines) if b not in ("", ".")]
        if not pts: raise RuntimeError("no values")
        return dict(dates=[p[0] for p in pts], closes=[p[1] for p in pts],
                    source=f"FRED public CSV [{sid}]", asof=pts[-1][0].isoformat())
    except Exception as e:
        return dict(error=f"FRED {sid}: {e}")
