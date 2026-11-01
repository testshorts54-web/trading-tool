"""Spot best bid/ask per venue (ported from flow core/venue_quotes.py; async httpx -> sync urllib GET).
Each venue fails on its own; a missing listing is None, never a made-up quote."""
import json
from dataclasses import dataclass
from tt.http import get

@dataclass
class Quote:
    venue: str; symbol: str; bid: float; ask: float; last: float = None; source_id: str = None; quote_ccy: str = "USD"
    @property
    def mid(self): return (self.bid + self.ask) / 2
    @property
    def spread_bps(self): return (self.ask - self.bid) / self.mid * 1e4 if self.mid > 0 else None

def _num(x):
    try: return float(x)
    except (TypeError, ValueError): return None

def _ok(q): return q if q.bid and q.ask and q.ask >= q.bid > 0 else None

def binance_us(base):
    d = json.loads(get(f"https://api.binance.us/api/v3/ticker/bookTicker?symbol={base}USDT", retries=0))
    return _ok(Quote("binance.us", f"{base}/USDT", _num(d.get("bidPrice")), _num(d.get("askPrice")), None, f"binance.us:bookTicker:{base}USDT", "USDT"))

def coinbase(base):
    try: d = json.loads(get(f"https://api.exchange.coinbase.com/products/{base}-USD/ticker", retries=0))
    except RuntimeError as e:
        if "404" in str(e): return None   # not listed
        raise
    return _ok(Quote("coinbase", f"{base}/USD", _num(d.get("bid")), _num(d.get("ask")), _num(d.get("price")), f"coinbase:ticker:{base}-USD"))

KRAKEN_ALIAS = {"XBT": "BTC", "XDG": "DOGE"}

def kraken_pair(base, pairs):
    """Find the Kraken pair key for base/USD from AssetPairs result (wsname like 'XBT/USD')."""
    for k, v in pairs.items():
        ws = v.get("wsname", "")
        if "/" not in ws: continue
        b, q = ws.split("/")
        if KRAKEN_ALIAS.get(b, b) == base and q == "USD": return k
    return None

def kraken(base, pairs=None):
    pairs = pairs or json.loads(get("https://api.kraken.com/0/public/AssetPairs", retries=0)).get("result", {})
    k = kraken_pair(base, pairs)
    if not k: return None
    t = json.loads(get(f"https://api.kraken.com/0/public/Ticker?pair={k}", retries=0)).get("result", {})
    if not t: return None
    d = next(iter(t.values()))
    return _ok(Quote("kraken", f"{base}/USD", _num(d["b"][0]), _num(d["a"][0]), _num(d["c"][0]), f"kraken:Ticker:{k}"))

def quotes(base):
    """{venue: Quote|None} plus errors list."""
    out, errs = {}, []
    for name, fn in (("binance.us", binance_us), ("coinbase", coinbase), ("kraken", kraken)):
        try: out[name] = fn(base)
        except Exception as e: out[name] = None; errs.append(f"{name}: {str(e)[:120]}")
    return out, errs

def sanity(qs, max_dev_bps=50):
    """Venue spread sanity: each mid vs the median mid. Info only (no trade suggestion)."""
    q = [x for x in qs.values() if x]
    if len(q) < 2: return None
    mids = sorted(x.mid for x in q); med = mids[len(mids) // 2] if len(mids) % 2 else (mids[len(mids) // 2 - 1] + mids[len(mids) // 2]) / 2
    dev = {x.venue: (x.mid / med - 1) * 1e4 for x in q}
    return dict(median_mid=med, dev_bps=dev, max_abs_dev_bps=max(abs(v) for v in dev.values()),
                flag=max(abs(v) for v in dev.values()) > max_dev_bps, spreads_bps={x.venue: x.spread_bps for x in q})

class IdenticalSourceError(ValueError): pass

def spot_spread_check(a, b, fee_pct_per_side=0.10):
    """Cross-venue spread using executable prices: buy at the lower ask, sell at the other venue's bid, minus fees
    on both sides (flow's spot_arbitrage_check). Raises on same venue/source, missing quote or currency mismatch.
    Ignores transfer time, withdrawal fees and depth: a positive net spread is a flag to check, not a sure profit."""
    if a is None or b is None or not (a.bid and a.ask and b.bid and b.ask): raise ValueError("quote unavailable")
    if a.venue == b.venue or (a.source_id and a.source_id == b.source_id): raise IdenticalSourceError("same venue or same data source")
    if a.quote_ccy != b.quote_ccy: raise ValueError(f"quote currency mismatch {a.quote_ccy} vs {b.quote_ccy}")
    buy, sell = (a, b) if a.ask <= b.ask else (b, a)
    gross = (sell.bid - buy.ask) / buy.ask * 100; net = gross - 2 * fee_pct_per_side
    return dict(buy_venue=buy.venue, sell_venue=sell.venue, price_basis="ask/bid", gross_spread_pct=gross,
                net_spread_pct=net, positive_after_fees=net > 0)
