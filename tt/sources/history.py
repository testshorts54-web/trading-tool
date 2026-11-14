"""Long daily OHLC history for validation. Local CSVs first (reuses /workspace/backtest/data[2] and
/workspace/crypto-strategies/data), then a public fallback (yfinance for equities, Coinbase for crypto).
Returns dict(bars=[{date, open, high, low, close[, volume]}], source, asof) or dict(error=...)."""
import csv, datetime as dt
from pathlib import Path
EQ_DIRS = [Path("/workspace/backtest/data"), Path("/workspace/backtest/data2")]
CRYPTO_DIR = Path("/workspace/crypto-strategies/data")
CRYPTO_DIRS = [CRYPTO_DIR, Path("/workspace/crypto-strategies/alts/data")]   # alts: Coinbase daily, 62 alts incl. delisted

def read_csv(path):
    bars = []
    for r in csv.DictReader(open(path)):
        try: b = dict(date=dt.date.fromisoformat(r["date"][:10]), **{k: float(r[k]) for k in ("open", "high", "low", "close")})
        except (KeyError, ValueError): continue
        try: b["volume"] = float(r["volume"])
        except (KeyError, TypeError, ValueError): pass
        bars.append(b)
    return bars

def _yf(sym):
    import yfinance as yf
    df = yf.Ticker(sym).history(period="max", interval="1d", auto_adjust=True).dropna(subset=["Close"])
    return [dict(date=d.date(), open=float(o), high=float(h), low=float(l), close=float(c), volume=float(v))
            for d, o, h, l, c, v in zip(df.index, df["Open"], df["High"], df["Low"], df["Close"], df["Volume"])
            if d.date() < dt.date.today()]   # drop today's still-open partial bar

def load(symbol, asset):
    cands = [d / f"{symbol}_1d.csv" for d in CRYPTO_DIRS] if asset == "crypto" else [d / f"{symbol}.csv" for d in EQ_DIRS]
    for p in cands:
        if p.exists():
            b = read_csv(p)
            if len(b) > 50: return dict(bars=b, source=f"local CSV {p}", asof=b[-1]["date"].isoformat())
    try:
        if asset == "crypto":
            from tt.sources.crypto import _coinbase
            d, c, o = _coinbase(symbol, days=3000)
            b = [dict(date=x, open=o["opens"][i], high=o["highs"][i], low=o["lows"][i], close=c[i]) for i, x in enumerate(d)]
            src = f"Coinbase Exchange public candles [{symbol}]"
        else:
            b = _yf(symbol); src = f"Yahoo Finance via yfinance (adjusted OHLC) [{symbol}]"
        if len(b) < 50: raise RuntimeError(f"only {len(b)} bars")
        return dict(bars=b, source=src, asof=b[-1]["date"].isoformat())
    except Exception as e:
        return dict(error=f"no history for {symbol}: {str(e)[:160]}")
