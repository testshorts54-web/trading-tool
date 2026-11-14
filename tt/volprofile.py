"""Volume profile on OHLCV candles (dicts with high, low, close, volume; oldest first).
Each candle's whole volume goes to the bin holding its typical price (H+L+C)/3 (simpler than spreading over the
high-low range; fine on 1h candles). Returns None when volume is missing/zero or there are too few candles."""

def volume_profile(candles, bins=50, lookback=720, min_candles=100, va_pct=0.70):
    c = candles[-lookback:] if lookback else list(candles)
    if len(c) < min_candles or bins < 1: return None
    if any(x.get("volume") is None or x["volume"] < 0 for x in c): return None
    tot = sum(x["volume"] for x in c)
    if tot <= 0: return None
    lo, hi = min(x["low"] for x in c), max(x["high"] for x in c)
    w = (hi - lo) / bins or 1.0                       # flat price: everything lands in bin 0
    vol = [0.0] * bins
    for x in c:
        tp = (x["high"] + x["low"] + x["close"]) / 3
        vol[min(int((tp - lo) / w), bins - 1)] += x["volume"]
    poc = max(range(bins), key=lambda i: vol[i])      # ties -> lowest bin
    # value area: smallest contiguous [i, j] containing POC with >= va_pct of volume (ties -> more volume)
    pre = [0.0]
    for v in vol: pre.append(pre[-1] + v)
    best = None
    for i in range(poc + 1):
        for j in range(poc, bins):
            s = pre[j + 1] - pre[i]
            if s >= va_pct * tot - 1e-12:
                k = (j - i, -s)
                if best is None or k < best[0]: best = (k, i, j)
                break                                  # widening j further only grows the range
    _, i, j = best
    mean = tot / bins; edge = lambda k: lo + k * w
    def zones(test):
        out, k = [], 0
        while k < bins:
            if test(vol[k]):
                s = k
                while k + 1 < bins and test(vol[k + 1]): k += 1
                out.append((edge(s), edge(k + 1)))
            k += 1
        return out
    return dict(poc=edge(poc) + w / 2, poc_range=(edge(poc), edge(poc + 1)), val=edge(i), vah=edge(j + 1),
                va_volume_pct=(pre[j + 1] - pre[i]) / tot, hvn=zones(lambda v: v >= 1.5 * mean),
                lvn=zones(lambda v: v <= 0.5 * mean), low=lo, high=hi, bin_width=w, candles=len(c), last=c[-1]["close"])

def position(p):
    """Last close vs value area and nearest low-volume node (by distance to the zone; 0 if inside it)."""
    px = p["last"]
    where = "above" if px > p["vah"] else "below" if px < p["val"] else "inside"
    dist = lambda z: 0.0 if z[0] <= px <= z[1] else min(abs(px - z[0]), abs(px - z[1]))
    near = min(p["lvn"], key=dist) if p["lvn"] else None
    return dict(price=px, vs_value_area=where, vs_poc="above" if px > p["poc"] else "below" if px < p["poc"] else "at",
                nearest_lvn=near, nearest_lvn_dist_pct=dist(near) / px if near else None)
