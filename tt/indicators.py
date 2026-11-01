"""Pure indicator functions on a list of closes (oldest first). Return None when history is too short."""
import math, datetime as dt

def sma(v, n):
    return sum(v[-n:]) / n if len(v) >= n else None

def rsi(v, n=14):
    """Wilder RSI."""
    if len(v) < n + 1: return None
    d = [b - a for a, b in zip(v[:-1], v[1:])]
    g = sum(max(x, 0) for x in d[:n]) / n; l = sum(max(-x, 0) for x in d[:n]) / n
    for x in d[n:]:
        g = (g * (n - 1) + max(x, 0)) / n; l = (l * (n - 1) + max(-x, 0)) / n
    return 100.0 if l == 0 else 100 - 100 / (1 + g / l)

def ret_days(dates, v, days):
    """Return from the last close on/before (last date - days calendar days) to the last close."""
    if not v: return None
    target = dates[-1] - dt.timedelta(days=days)
    base = [c for d, c in zip(dates, v) if d <= target]
    return v[-1] / base[-1] - 1 if base else None

def drawdown(v, n=252):
    """Last close vs max close of the last n observations."""
    if len(v) < n: return None
    return v[-1] / max(v[-n:]) - 1

def realized_vol(v, n=20, periods=252):
    if len(v) < n + 1: return None
    r = [math.log(b / a) for a, b in zip(v[-n - 1:-1], v[-n:])]
    m = sum(r) / n
    return math.sqrt(sum((x - m) ** 2 for x in r) / (n - 1) * periods)

def percentile_rank(v, n=252):
    if len(v) < n: return None
    w = v[-n:]; return sum(1 for x in w if x <= w[-1]) / n

def ratio(a, b):
    """Align two {date: close} dicts -> (dates, ratio values)."""
    ds = sorted(set(a) & set(b))
    return ds, [a[d] / b[d] for d in ds]

# ---- Per-bar series (one value per bar, None during warm-up). Subset ported from flow core/indicators.py
# (EMA, ATR, Bollinger width, Keltner/TTM squeeze, ADX, Hurst) rewritten without numpy; flow's fallbacks
# (Hurst 0.5, squeeze 0, VWAP z 0) are replaced by None.
def sma_s(x, n):
    out, s = [None] * len(x), 0.0
    for i, v in enumerate(x):
        s += v
        if i >= n: s -= x[i - n]
        if i >= n - 1: out[i] = s / n
    return out

def ema_s(x, n):
    """EMA seeded with the SMA of the first n values (as flow)."""
    out = [None] * len(x)
    if len(x) < n: return out
    a, e = 2 / (n + 1), sum(x[:n]) / n; out[n - 1] = e
    for i in range(n, len(x)): e = a * x[i] + (1 - a) * e; out[i] = e
    return out

def wilder_s(x, n):
    """Wilder smoothing, alpha=1/n, seeded with the first value; None until n values seen
    (= pandas ewm(alpha=1/n, adjust=False, min_periods=n), as /workspace/backtest/backtest.py)."""
    out, e = [None] * len(x), None
    for i, v in enumerate(x):
        e = v if e is None else e + (v - e) / n
        if i >= n - 1: out[i] = e
    return out

def rsi_s(c, n=14):
    """Wilder RSI series matching backtest.py rsi() (first diff seeds the averages)."""
    d = [b - a for a, b in zip(c[:-1], c[1:])]
    up, dn = wilder_s([max(x, 0) for x in d], n), wilder_s([max(-x, 0) for x in d], n)
    return [None] + [None if u is None else (100.0 if w == 0 else 100 - 100 / (1 + u / w)) for u, w in zip(up, dn)]

def true_range(h, l, c):
    return [h[0] - l[0]] + [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(c))]

def atr_s(h, l, c, n=14):
    """Wilder ATR (as backtest.py atr())."""
    return wilder_s(true_range(h, l, c), n)

def std_s(x, n):
    """Population std over a rolling window (flow's Bollinger used np.std, ddof=0)."""
    m = sma_s(x, n)
    return [None if m[i] is None else math.sqrt(max(sum((v - m[i]) ** 2 for v in x[i - n + 1:i + 1]) / n, 0)) for i in range(len(x))]

def bb_width_s(c, n=20, k=2.0):
    """Bollinger bandwidth in percent: (upper - lower) / middle * 100."""
    m, s = sma_s(c, n), std_s(c, n)
    return [None if m[i] is None or m[i] <= 0 else 2 * k * s[i] / m[i] * 100 for i in range(len(c))]

def ttm_squeeze_s(h, l, c, n=20, bb_k=2.0, kc_k=1.5):
    """(squeeze_on, momentum) per bar. Squeeze on = Bollinger(n, 2) inside Keltner(EMA n +/- 1.5 x Wilder ATR n).
    Momentum = close - ((highest high + lowest low)/2 + SMA n)/2 over n bars (flow's definition)."""
    m, s, e = sma_s(c, n), std_s(c, n), ema_s(c, n)
    tr = true_range(h, l, c); atr = [None] * len(c)
    if len(c) >= n:
        a = sum(tr[:n]) / n; atr[n - 1] = a
        for i in range(n, len(c)): a = (a * (n - 1) + tr[i]) / n; atr[i] = a
    sq, mom = [None] * len(c), [None] * len(c)
    for i in range(n - 1, len(c)):
        if None in (m[i], s[i], e[i], atr[i]): continue
        sq[i] = (m[i] + bb_k * s[i] < e[i] + kc_k * atr[i]) and (m[i] - bb_k * s[i] > e[i] - kc_k * atr[i])
        mom[i] = c[i] - ((max(h[i - n + 1:i + 1]) + min(l[i - n + 1:i + 1])) / 2 + m[i]) / 2
    return sq, mom

def adx_s(h, l, c, n=14):
    """(ADX, +DI, -DI) per bar; Wilder sums as flow; ADX seeded with the mean DX of bars n..2n-1."""
    N = len(c); adx, pdi, mdi = [None] * N, [None] * N, [None] * N
    if N <= n: return adx, pdi, mdi
    tr = true_range(h, l, c); up, dn = [0.0] * N, [0.0] * N
    for i in range(1, N):
        u, d = h[i] - h[i - 1], l[i - 1] - l[i]
        if u > d and u > 0: up[i] = u
        if d > u and d > 0: dn[i] = d
    a, p, m = sum(tr[1:n + 1]), sum(up[1:n + 1]), sum(dn[1:n + 1]); dx = [None] * N
    for i in range(n, N):
        if i > n: a, p, m = a - a / n + tr[i], p - p / n + up[i], m - m / n + dn[i]
        if a > 0:
            pdi[i], mdi[i] = 100 * p / a, 100 * m / a
            dx[i] = 100 * abs(pdi[i] - mdi[i]) / (pdi[i] + mdi[i]) if pdi[i] + mdi[i] > 0 else 0.0
    if N >= 2 * n and None not in dx[n:2 * n]:
        x = sum(dx[n:2 * n]) / n; adx[2 * n - 1] = x
        for i in range(2 * n, N):
            if dx[i] is None: break
            x = (x * (n - 1) + dx[i]) / n; adx[i] = x
    return adx, pdi, mdi

def hurst(v, max_lags=20):
    """Hurst exponent from the slope of log std(lagged differences) vs log lag (flow's method).
    None (not 0.5) when there are fewer than 2 x max_lags points or a zero-variance lag."""
    if len(v) < max_lags * 2: return None
    xs, ys = [], []
    for lag in range(2, min(max_lags, len(v) // 2)):
        d = [b - a for a, b in zip(v[:-lag], v[lag:])]; m = sum(d) / len(d)
        sd = math.sqrt(sum((x - m) ** 2 for x in d) / len(d))
        if sd <= 0: return None
        xs.append(math.log(lag)); ys.append(math.log(sd))
    if len(xs) < 2: return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    h = sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / sum((a - mx) ** 2 for a in xs)
    return min(max(h, 0.01), 0.99)   # clamped as flow

def rank(v):
    """Average ranks (ties share the mean rank), 1-based."""
    o = sorted(range(len(v)), key=lambda i: v[i]); r = [0.0] * len(v); i = 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]: j += 1
        for k in range(i, j + 1): r[o[k]] = (i + j) / 2 + 1
        i = j + 1
    return r

def spearman_ic(signal, fwd, min_n=30):
    """Spearman rank correlation between a signal and forward returns over pairs where both exist.
    Ported from flow datascientist/analyzer.compute_spearman_ic, which returned 0.0 below 10 pairs and mixed
    ddof; here: None below min_n pairs or zero variance, Pearson on average ranks."""
    p = [(a, b) for a, b in zip(signal, fwd) if a is not None and b is not None]
    if len(p) < min_n: return None
    ra, rb = rank([a for a, _ in p]), rank([b for _, b in p]); n = len(p); m = (n + 1) / 2
    sa = math.sqrt(sum((x - m) ** 2 for x in ra)); sb = math.sqrt(sum((x - m) ** 2 for x in rb))
    if sa == 0 or sb == 0: return None
    return sum((x - m) * (y - m) for x, y in zip(ra, rb)) / (sa * sb)
