"""Daily external series for entry rules, cached on disk (GET only, no keys; research only).
Hosts are allowlisted: anything else raises before any network call. Each loader returns {date: float}.
  funding_<SYM>  Binance USD-M perp funding, daily mean of the 8h rates (data.binance.vision monthly zips, from 2020-01)
  mvrv, realized_cap, mcap, hashrate   BTC from Coin Metrics community API (from 2010; realized_cap = mcap / mvrv)
  stables        DefiLlama total stablecoin supply USD (from 2017-11)
  btcd           BTC dominance PROXY: BTC cap / (BTC + 8 large coins + stablecoins); no BNB/SOL/TRX (CM community lacks them)
Names may add a trailing ".sma_N" (rolling mean over N days of that series), e.g. "btcd.sma_50"."""
import io, csv, json, time, zipfile, hashlib, datetime as dt
from pathlib import Path
from urllib.parse import urlparse
from tt.http import get

ALLOWED_HOSTS = {"data.binance.vision", "community-api.coinmetrics.io", "stablecoins.llama.fi"}
CACHE = Path(__file__).resolve().parents[2] / "out" / "cache" / "series"
CM = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
DOM_COINS = ("eth", "xrp", "ada", "doge", "ltc", "bch", "link", "xlm")   # CM community caps 2017-12..now (bnb stops 2019-04)

def fetch(url, max_age_days=None):
    """Cached GET. max_age_days=None caches forever (closed months); else refetch when older."""
    if urlparse(url).scheme != "https" or urlparse(url).hostname not in ALLOWED_HOSTS: raise ValueError(f"refused: host not allowlisted: {url}")
    p = CACHE / hashlib.sha1(url.encode()).hexdigest()[:16]
    if p.exists() and (max_age_days is None or time.time() - p.stat().st_mtime < max_age_days * 86400): return p.read_bytes()
    b = get(url); CACHE.mkdir(parents=True, exist_ok=True); p.write_bytes(b); return b

def _day(ms): return dt.datetime.fromtimestamp(int(ms) / 1000, dt.timezone.utc).date()

def funding(sym="BTCUSDT", start=dt.date(2020, 1, 1)):
    today, m, rows = dt.date.today(), start, {}
    while (m.year, m.month) < (today.year, today.month):   # closed months only; the current month has no zip yet
        try: z = fetch(f"https://data.binance.vision/data/futures/um/monthly/fundingRate/{sym}/{sym}-fundingRate-{m:%Y-%m}.zip")
        except RuntimeError: z = None   # month not published (before listing)
        if z:
            with zipfile.ZipFile(io.BytesIO(z)) as f:
                for r in csv.DictReader(io.TextIOWrapper(f.open(f.namelist()[0]))): rows.setdefault(_day(r["calc_time"]), []).append(float(r["last_funding_rate"]))
        m = (m.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return {d: sum(v) / len(v) for d, v in sorted(rows.items())}

def coinmetrics(assets, metrics, start="2010-01-01"):
    """-> {(asset, metric): {date: float}}; follows next_page_url (community API pages)."""
    out, url = {}, f"{CM}?assets={','.join(assets)}&metrics={','.join(metrics)}&frequency=1d&start_time={start}&page_size=10000&ignore_unsupported_errors=true"
    while url:
        d = json.loads(fetch(url, max_age_days=1))
        for r in d["data"]:
            for m in metrics:
                if r.get(m) is not None: out.setdefault((r["asset"], m), {})[dt.date.fromisoformat(r["time"][:10])] = float(r[m])
        url = d.get("next_page_url")
    return out

def stables():
    return {_day(int(x["date"]) * 1000): float(x["totalCirculatingUSD"]["peggedUSD"]) for x in json.loads(fetch("https://stablecoins.llama.fi/stablecoincharts/all", max_age_days=1))
            if x.get("totalCirculatingUSD", {}).get("peggedUSD") is not None}

def btc_dominance():
    cm = coinmetrics(("btc",) + DOM_COINS, ["CapMrktCurUSD"], "2017-12-01"); st = stables()
    caps = [cm.get((a, "CapMrktCurUSD"), {}) for a in ("btc",) + DOM_COINS]
    return {d: caps[0][d] / (sum(c[d] for c in caps) + st[d]) for d in sorted(caps[0]) if d in st and all(d in c for c in caps)}

def _btc(metric):
    if metric == "realized_cap":
        c = coinmetrics(["btc"], ["CapMrktCurUSD", "CapMVRVCur"]); m, v = c[("btc", "CapMrktCurUSD")], c[("btc", "CapMVRVCur")]
        return {d: m[d] / v[d] for d in m if v.get(d)}
    key = {"mvrv": "CapMVRVCur", "mcap": "CapMrktCurUSD", "hashrate": "HashRate"}[metric]
    return coinmetrics(["btc"], [key])[("btc", key)]

def sma(s, n):
    ks = sorted(s); v = [s[k] for k in ks]
    return {ks[i]: sum(v[i - n + 1:i + 1]) / n for i in range(n - 1, len(v))}

def load(name):
    base, _, op = name.partition(".")
    s = (funding(base.split("_", 1)[1]) if base.startswith("funding_") else stables() if base == "stables"
         else btc_dominance() if base == "btcd" else _btc(base))
    return sma(s, int(op.split("_")[1])) if op else s
