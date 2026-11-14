"""Prediction-market math (P4 groundwork; ported from flow prediction/kelly.py, dutch_book.py, polymarket.py).
Not wired into the pipeline yet. Fixes vs flow: fees are in the price, bankroll must be given (no $10k default),
missing prices stay None (flow used 0.50), dutch-book uses executable asks across an event's sub-markets with
real end dates and depth, and nothing is called risk-free or guaranteed. Read-only; no order code."""
import json, math, re, datetime as dt
from statistics import NormalDist
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
                           title=m.get("groupItemTitle") or m.get("question"), tokens=_j(m.get("clobTokenIds")) or [],
                           fee_rate=_f((m.get("feeSchedule") or {}).get("rate")), liquidity=_f(m.get("liquidityNum")),
                           d1h=_f(m.get("oneHourPriceChange")), other=bool(m.get("negRiskOther")),
                           condition_id=m.get("conditionId"), volume24h=_f(m.get("volume24hr"))))
        out.append(dict(title=e.get("title"), slug=e.get("slug"), neg_risk=bool(e.get("negRisk")), end=e.get("endDate"),
                        volume24h=_f(e.get("volume24hr")), augmented=bool(e.get("negRiskAugmented")),
                        tags=[t.get("slug") for t in e.get("tags") or []], markets=ms))
    return out

def fetch_events(limit=40, tag=None):
    # Gamma returns 406 for limit>50 (observed 2026-11-14); page with offset instead.
    try:
        page, offset, rows, seen = 50, 0, [], set()
        while len(rows) < limit:
            n = min(page, limit - len(rows))
            url = (f"https://gamma-api.polymarket.com/events?limit={n}&order=volume24hr&ascending=false&closed=false"
                   + (f"&offset={offset}" if offset else "") + (f"&tag_slug={tag}" if tag else ""))
            d = json.loads(get(url))
            if not d: break
            for ev in parse_events(d):
                key = ev.get("slug") or ev.get("title")
                if key in seen: continue
                seen.add(key); rows.append(ev)
            if len(d) < n: break
            offset += len(d)
        return dict(events=rows[:limit], source="Polymarket Gamma API /events", asof=dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"))
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
    inc = ev.get("augmented", False) or any(m.get("other") or any(w in (m["title"] or "").lower() for w in PLACEHOLDER) for m in ms)
    return dutch_book(px, min_discount_pct, fee, ev.get("end"), today, execu, None, inc)

# ---- P4 scan helpers (predict_scan.py). Fee formula: docs.polymarket.com/trading/fees, fee = C * rate * p * (1-p), taker only.
def fee_per_share(p, rate):
    """Taker fee per share at price p; None (UNKNOWN) when the market publishes no rate."""
    return None if rate is None or p is None else rate * p * (1 - p)

def book_top(token_id):
    """Best ask and its size from the public CLOB book (GET). None when the book has no asks."""
    b = json.loads(get(f"https://clob.polymarket.com/book?token_id={token_id}", retries=1))
    asks = [(_f(a.get("price")), _f(a.get("size"))) for a in b.get("asks") or []]
    asks = [a for a in asks if a[0] and a[1]]
    return min(asks) if asks else None   # shortcut: top level only, no walk down the book; upgrade if sizes matter

def size_binary(cost, equity, max_qty=None):
    """Paper size for a contract set costing `cost` that can go to 0: max loss = notional, so the 1% risk cap binds
    before the 10% position cap. Capped by visible depth when given."""
    from tt.config import MAX_POSITION_PCT, MAX_RISK_PER_TRADE_PCT
    if not cost or cost <= 0 or not equity or equity <= 0: raise ValueError("cost and paper equity must be > 0")
    budget = min(MAX_POSITION_PCT, MAX_RISK_PER_TRADE_PCT) * equity
    qty = math.floor(budget / cost); binding = "1% risk"
    if max_qty is not None and math.floor(max_qty) < qty: qty, binding = math.floor(max_qty), "book depth"
    return dict(qty=qty, notional=qty * cost, pct_of_equity=qty * cost / equity, risk_usd=qty * cost,
                risk_pct=qty * cost / equity, binding=binding)

COINS = {"bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL", "xrp": "XRP", "dogecoin": "DOGE"}
_Q = re.compile(r"price of (bitcoin|ethereum|solana|xrp|dogecoin) be (above|greater than|below|less than) \$([\d,]+(?:\.\d+)?) on", re.I)

def parse_crypto_q(q):
    """'Will the price of Bitcoin be above $70,000 on November 1?' -> (BTC, 'above', 70000). Ranges, 'reach'/'dip'
    (path-dependent) and anything else -> None."""
    m = _Q.search(q or "")
    if not m or " between " in q.lower(): return None
    return COINS[m.group(1).lower()], ("above" if m.group(2).lower() in ("above", "greater than") else "below"), float(m.group(3).replace(",", ""))

def model_p_yes(spot, strike, side, years, sigma):
    """Driftless lognormal P(S_T > K) (or < K). An assumption, not a forecast; sigma is set high on purpose."""
    if spot <= 0 or strike <= 0 or years <= 0 or sigma <= 0: return None
    v = sigma * years ** 0.5; d2 = (math.log(spot / strike) - v * v / 2) / v
    p = NormalDist().cdf(d2)
    return p if side == "above" else 1 - p


def complement_taker(yes_ask, no_ask, yes_rate, no_rate, min_discount_pct=1.0,
                     yes_size=None, no_size=None, min_sets=10, min_profit_usd=1.0):
    """Taker cost of buying both complementary outcomes at the ask, plus taker fees.
    Returns None if a price or rate is missing (UNKNOWN). Flagged when the after-fee
    cost is at least min_discount_pct below $1 with enough top-of-book depth."""
    if any(x is None for x in (yes_ask, no_ask, yes_rate, no_rate)):
        return None
    cost = yes_ask + no_ask + fee_per_share(yes_ask, yes_rate) + fee_per_share(no_ask, no_rate)
    disc = (1 - cost) * 100
    sets = None if yes_size is None or no_size is None else min(yes_size, no_size)
    profit = None if sets is None else sets * (1 - cost)
    why = [w for w, bad in (
        (f"gap < {min_discount_pct}% after fees", disc < min_discount_pct),
        (f"top-of-book depth {sets:.0f} < {min_sets} sets", sets is not None and sets < min_sets),
        (f"${profit:.2f} at depth < ${min_profit_usd}", profit is not None and profit < min_profit_usd),
    ) if bad]
    return dict(sum_of_asks=yes_ask + no_ask, cost=cost, discount_pct=disc,
                depth_sets=sets, profit_usd_at_depth=profit,
                flagged=not why, reasons=why or ["check resolution rules (void/ties) before trusting the pair"])
