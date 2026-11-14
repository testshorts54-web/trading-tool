"""BTC/ETH daily OHLC (UTC days); merges flow core/historical.py (Coinbase candles) into one crypto-candle source. Primary: Coinbase Exchange public candles (as crypto-strategies/fetch_data.py).
Fallback: yfinance. Today's UTC candle is incomplete and is dropped."""
import json, datetime as dt
from tt.http import get

def _coinbase(product, days=420):
    rows, end = {}, dt.datetime.now(dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    t = end - dt.timedelta(days=days)
    while t < end:
        e = min(t + dt.timedelta(days=299), end)
        url = (f"https://api.exchange.coinbase.com/products/{product}/candles?granularity=86400"
               f"&start={t.isoformat()}&end={e.isoformat()}")
        for r in json.loads(get(url)):        # [time, low, high, open, close, volume]
            rows[r[0]] = [float(x) for x in r[1:5]]   # low, high, open, close
        t = e
    today = end.date()
    ks = [k for k in sorted(rows) if dt.datetime.fromtimestamp(k, dt.timezone.utc).date() < today]
    ohlc = dict(opens=[rows[k][2] for k in ks], highs=[rows[k][1] for k in ks], lows=[rows[k][0] for k in ks])
    return [dt.datetime.fromtimestamp(k, dt.timezone.utc).date() for k in ks], [rows[k][3] for k in ks], ohlc

def _yf(product):
    import yfinance as yf
    df = yf.Ticker(product).history(period="2y", interval="1d").dropna(subset=["Close"])
    today = dt.datetime.now(dt.timezone.utc).date()
    df = df[[d.date() < today for d in df.index]]
    ohlc = dict(opens=[float(x) for x in df["Open"]], highs=[float(x) for x in df["High"]], lows=[float(x) for x in df["Low"]])
    return [d.date() for d in df.index], [float(x) for x in df["Close"]], ohlc

def daily(product):
    errs = []
    for name, fn in (("Coinbase Exchange public candles", _coinbase), ("Yahoo Finance via yfinance", _yf)):
        try:
            d, c, ohlc = fn(product)
            if len(c) < 2: raise RuntimeError("too few rows")
            return dict(dates=d, closes=c, **ohlc, source=f"{name} [{product}]", asof=d[-1].isoformat())
        except Exception as e:
            errs.append(f"{name}: {e}")
    return dict(error="; ".join(errs))

def load_hourly_fixture(path):
    """flow's cached 1h candles: JSON list of {timestamp(ms), open, high, low, close, volume}. Test fixtures only."""
    rows = json.loads(open(path).read())
    return [dict(ts=int(r["timestamp"]), **{k: float(r[k]) for k in ("open", "high", "low", "close", "volume")}) for r in rows]

def binance_klines(base, interval="1h", limit=720):
    """Binance public spot klines for {base}USDT (data-api.binance.vision, market data only; as Crypto Scout
    crypto-tracker/compare/market.py). Same candle dicts as load_hourly_fixture. The still-open candle is dropped."""
    if not 1 <= limit <= 1000: raise ValueError("limit must be 1..1000 (one request)")
    url = f"https://data-api.binance.vision/api/v3/klines?symbol={base.upper()}USDT&interval={interval}&limit={limit + 1}"
    now_ms = dt.datetime.now(dt.timezone.utc).timestamp() * 1000
    rows = [r for r in json.loads(get(url)) if r[6] < now_ms]          # r[6] = close time (ms)
    return dict(candles=[dict(ts=int(r[0]), **{k: float(r[i]) for i, k in enumerate(("open", "high", "low", "close", "volume"), 1)})
                         for r in rows[-limit:]], source=f"Binance public klines {base.upper()}USDT {interval} (data-api.binance.vision)")
