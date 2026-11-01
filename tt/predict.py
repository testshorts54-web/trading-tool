"""Prediction-market math (P4 groundwork; ported from flow prediction/kelly.py, dutch_book.py, polymarket.py).
Not wired into the pipeline yet. Fixes vs flow: fees are in the price, bankroll must be given (no $10k default),
missing prices stay None (flow used 0.50), dutch-book uses executable asks across an event's sub-markets with
real end dates and depth, and nothing is called risk-free or guaranteed. Read-only; no order code."""
import json, datetime as dt
from tt.http import get
from tt.config import MAX_RISK_PER_TRADE_PCT

def kelly(price, p, bankroll, fee=0.0, fraction=1.0, cap_pct=MAX_RISK_PER_TRADE_PCT):
    """Binary YES share at `price` paying 1. Effective cost c = price*(1+fee). EV/share = p - c; full Kelly f* = (p-c)/(1-c).
    Stake = bankroll * min(fraction*f*, cap_pct). No edge -> 0."""
    if not (0 < price < 1) or not (0 <= p <= 1) or bankroll is None or bankroll <= 0: raise ValueError("bad inputs")
    c = price * (1 + fee)
    full = max((p - c) / (1 - c), 0.0) if c < 1 else 0.0
    frac = full * fraction; stake_pct = min(frac, cap_pct)
    return dict(cost=c, ev_per_share=p - c, roi_pct=(p - c) / c * 100, full_kelly=full, fractional_kelly=frac,
                stake=bankroll * stake_pct, capped=frac > cap_pct)

def _j(x):
    if isinstance(x, str):
        try: return json.loads(x)
        except ValueError: return None
    return x

def _f(x):
    try: return float(x)
    except (TypeError, ValueError): return None

def parse_events(events):
    """Gamma /events JSON -> list of events with sub-markets; JSON-string fields decoded; missing price -> None."""
    out = []
    for e in events:
        ms = []
        for m in e.get("markets", []) or []:
            if m.get("closed") or m.get("active") is False: continue
            outs, px = _j(m.get("outcomes")) or [], [_f(x) for x in (_j(m.get("outcomePrices")) or [])]
            ms.append(dict(question=m.get("question"), outcomes=outs, prices=px + [None] * (len(outs) - len(px)),
                           best_ask=_f(m.get("bestAsk")), best_bid=_f(m.get("bestBid")), end=m.get("endDate") or e.get("endDate"),
                           title=m.get("groupItemTitle") or m.get("question")))
        out.append(dict(title=e.get("title"), slug=e.get("slug"), neg_risk=bool(e.get("negRisk")), end=e.get("endDate"),
                        volume24h=_f(e.get("volume24hr")), markets=ms))
    return out

def fetch_events(limit=40):
    try:
        d = json.loads(get(f"https://gamma-api.polymarket.com/events?limit={limit}&order=volume24hr&ascending=false&closed=false"))
        return dict(events=parse_events(d), source="Polymarket Gamma API /events", asof=dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"))
    except Exception as e: return dict(error=f"Polymarket: {str(e)[:160]}")

PLACEHOLDER = ("other", "another", "field", "none of", "tbd", "someone else")

def dutch_book(prices, min_discount_pct=1.0, fee=0.0, end=None, today=None, executable=True, depth=None, incomplete=False):
    """Cost of buying one YES of every outcome = sum(prices)*(1+fee). Flag when that is below 1 by >= min_discount_pct
    and there are >= 3 outcomes. Returns None if any price is missing. APR only when a real end date is given.
    The flag is a lead to check (resolution rules, fills, depth), not a sure profit."""
    if len(prices) < 3 or any(p is None for p in prices): return None
    cost = sum(prices) * (1 + fee); disc = (1 - cost) * 100
    days = None
    if end:
        try: days = (dt.date.fromisoformat(str(end)[:10]) - (today or dt.date.today())).days
        except ValueError: days = None
    roi = (1 / cost - 1) * 100 if cost > 0 else None
    return dict(sum_of_prices=sum(prices), cost=cost, discount_pct=disc, roi_pct=roi, days_to_end=days,
                apr_pct=None if roi is None or not days or days <= 0 else roi * 365 / days,
                executable=executable, depth_sets=depth, incomplete_set=incomplete,
                flagged=disc >= min_discount_pct and executable and not incomplete)

def event_dutch_book(ev, fee=0.0, min_discount_pct=1.0, today=None):
    """Across an event's sub-markets: YES best ask if present, else YES mid (then executable=False).
    A neg-risk 'other'/placeholder outcome means the set may be incomplete -> never flagged."""
    ms = ev["markets"]; px, execu = [], True
    for m in ms:
        if m["best_ask"] is not None: px.append(m["best_ask"])
        else: px.append(m["prices"][0] if m["prices"] else None); execu = False
    inc = any(any(w in (m["title"] or "").lower() for w in PLACEHOLDER) for m in ms)
    return dutch_book(px, min_discount_pct, fee, ev.get("end"), today, execu, None, inc)
