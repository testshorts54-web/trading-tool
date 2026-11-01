"""Crypto sentiment and liquidity (ported from flow intelligence/macro.py): Fear & Greed (alternative.me) and
total stablecoin supply (DefiLlama). flow defaulted missing F&G to 50 and labelled 7-day flows; here a missing
value is an error and the change is over 30 days, shown as info."""
import json, datetime as dt
from tt.http import get

def fear_greed():
    try:
        d = json.loads(get("https://api.alternative.me/fng/?limit=1"))["data"][0]
        day = dt.datetime.fromtimestamp(int(d["timestamp"]), dt.timezone.utc).date()
        return dict(value=int(d["value"]), label=d.get("value_classification"), asof=day.isoformat(),
                    source="alternative.me Fear & Greed index")
    except Exception as e: return dict(error=f"Fear & Greed: {str(e)[:160]}")

def stablecoin_change(data, days=30):
    """data = DefiLlama stablecoincharts/all list (daily). Returns (latest_usd, change_pct, asof) or None."""
    pts = [(int(x["date"]), float(x["totalCirculatingUSD"]["peggedUSD"])) for x in data
           if x.get("totalCirculatingUSD", {}).get("peggedUSD") is not None]
    if len(pts) <= days: return None
    (t1, v1), (_, v0) = pts[-1], pts[-1 - days]
    return v1, (v1 / v0 - 1) * 100 if v0 else None, dt.datetime.fromtimestamp(t1, dt.timezone.utc).date().isoformat()

def stablecoins(days=30):
    try:
        r = stablecoin_change(json.loads(get("https://stablecoins.llama.fi/stablecoincharts/all")), days)
        if r is None: raise RuntimeError("too little history")
        return dict(total_usd=r[0], change_pct=r[1], days=days, asof=r[2], source="DefiLlama stablecoincharts/all (peggedUSD)")
    except Exception as e: return dict(error=f"Stablecoins: {str(e)[:160]}")
