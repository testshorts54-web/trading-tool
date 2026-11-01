"""Perp funding / open interest / premium (ported from flow intelligence/derivatives.py, minus its arbitrary
'cushion' and cash-and-carry advice) plus a Kraken-vs-Hyperliquid funding spread (rewrite of flow
brain/cross_exchange.py, which used a third-party exchange library + Gate.io). Public market data only."""
import json, datetime as dt
from tt.http import get, hl_info

def _f(x):
    try: return float(x)
    except (TypeError, ValueError): return None

def parse_hl(data, coins=("BTC", "ETH")):
    """metaAndAssetCtxs -> {coin: dict(funding_1h, funding_apr_pct, oi_usd, premium_pct, mark)}. Missing -> None."""
    uni, ctx = data[0].get("universe", []), data[1]; out = {}
    for u, c in zip(uni, ctx):
        n = u.get("name")
        if n not in coins or u.get("isDelisted"): continue
        mark, fr, oi, orc = _f(c.get("markPx")), _f(c.get("funding")), _f(c.get("openInterest")), _f(c.get("oraclePx"))
        out[n] = dict(mark=mark, funding_1h=fr, funding_apr_pct=None if fr is None else fr * 24 * 365 * 100,
                      oi_usd=None if None in (oi, mark) else oi * mark,
                      premium_pct=None if None in (mark, orc) or not orc else (mark / orc - 1) * 100)
    return out

def hyperliquid(coins=("BTC", "ETH")):
    try: return dict(data=parse_hl(hl_info({"type": "metaAndAssetCtxs"}), coins), source="Hyperliquid public info API (metaAndAssetCtxs)",
                     asof=dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"))
    except Exception as e: return dict(error=f"Hyperliquid: {str(e)[:160]}")

KRAKEN_PERP = {"BTC": "PF_XBTUSD", "ETH": "PF_ETHUSD"}

def kraken_funding(coin="BTC"):
    """Latest Kraken Futures hourly relative funding rate (as crypto-strategies uses)."""
    try:
        d = json.loads(get(f"https://futures.kraken.com/derivatives/api/v4/historicalfundingrates?symbol={KRAKEN_PERP[coin]}"))
        r = d["rates"][-1]; fr = _f(r.get("relativeFundingRate"))
        return dict(funding_1h=fr, funding_apr_pct=None if fr is None else fr * 24 * 365 * 100, asof=r.get("timestamp"),
                    source=f"Kraken Futures historicalfundingrates [{KRAKEN_PERP[coin]}]")
    except Exception as e: return dict(error=f"Kraken funding {coin}: {str(e)[:160]}")

def funding_spread(hl, kr):
    """APR spread Hyperliquid minus Kraken (percentage points). None if either side is missing. Info only."""
    a, b = (hl or {}).get("funding_apr_pct"), (kr or {}).get("funding_apr_pct")
    return None if a is None or b is None else a - b
