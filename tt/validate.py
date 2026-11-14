"""Part B validation: does an idea's written rule have an edge after costs, out of sample, versus chance?
Uses btlib.trades (simulator) and btlib.stats (min-sample guard) from /workspace/backtest. Research only."""
import sys, math, random, statistics as st
from statistics import NormalDist
sys.path.insert(0, "/workspace/backtest")
from btlib import trades as T, stats as S
from tt import config as C, indicators as ind
from tt.ideas import scanners

def exits(idea, bars):
    atr = ind.atr_s([b["high"] for b in bars], [b["low"] for b in bars], [b["close"] for b in bars], 14)
    (sk, sv), = idea.stop.items()
    stop_fn = (lambda f, i: None if atr[i] is None else f - sv * atr[i]) if sk == "atr" else (lambda f, i: f * (1 - sv / 100))
    tgt_fn = None
    if idea.target:
        (tk, tv), = idea.target.items()
        tgt_fn = (lambda f, s, i: f + tv * (f - s)) if tk == "R" else (lambda f, s, i: f * (1 + tv / 100))
    return stop_fn, tgt_fn, atr

def dsr(r, n_trials, trial_sr_var=None):
    """Deflated Sharpe probability on per-trade returns (Bailey & Lopez de Prado 2014, formula as btlib.evals.dsr).
    Without the trial Sharpes, their variance is approximated by the SR estimator variance 1/(n-1)."""
    n = len(r)
    if n < 3 or n_trials < 2: return None
    m, s = st.mean(r), st.stdev(r)
    if s == 0: return None
    sr = m / s; sk = sum(((x - m) / s) ** 3 for x in r) / n; ku = sum(((x - m) / s) ** 4 for x in r) / n
    v = trial_sr_var if trial_sr_var is not None else 1 / (n - 1); g = 0.5772156649; N = NormalDist()
    sr0 = math.sqrt(v) * ((1 - g) * N.inv_cdf(1 - 1 / n_trials) + g * N.inv_cdf(1 - 1 / (n_trials * math.e)))
    den = 1 - sk * sr + (ku - 1) / 4 * sr ** 2
    return N.cdf((sr - sr0) * math.sqrt(n - 1) / math.sqrt(den)) if den > 0 else None

def _mean(t): return st.mean([x["ret"] for x in t]) if t else None

def null_test(bars, sig, stop_fn, tgt_fn, hold, cost, start, actual_mean, draws=C.NULL_DRAWS, seed=C.NULL_SEED):
    """Random-entry null: same exits and cost, entries drawn at random with the same signal frequency.
    p = share of draws whose mean trade return >= the real one (one-sided)."""
    elig = range(start, len(bars) - 1); p = sum(sig[i] for i in elig) / max(len(elig), 1)
    if actual_mean is None or p == 0: return None
    rng = random.Random(seed); ge, means = 0, []
    for _ in range(draws):
        s = [i >= start and rng.random() < p for i in range(len(bars))]
        m = _mean(T.simulate(bars, s, stop_fn, tgt_fn, hold, cost, start)["trades"])
        if m is None: continue
        means.append(m); ge += m >= actual_mean
    return dict(p_value=(ge + 1) / (len(means) + 1), draws=len(means), null_mean=st.mean(means) if means else None, signal_freq=p)

def run(idea, hist, min_trades=C.MIN_TRADES, warmup=200, draws=C.NULL_DRAWS, extra=None):
    probs = idea.problems()
    if probs: return dict(idea=idea.id, verdict="REJECTED", reasons=probs)
    bars = hist["bars"]
    if len(bars) < warmup + 2 * min_trades: return dict(idea=idea.id, verdict="INSUFFICIENT", reasons=[f"only {len(bars)} bars"], source=hist.get("source"))
    miss = scanners.missing_inputs(bars, idea.entry, extra)
    if miss:   # a metric with no data would silently give 0 trades; fail loudly instead
        raise ValueError(f"idea {idea.id} ({idea.symbol}): rule metric(s) with no data: " + ", ".join(
            f"{m} (needs field {'volume' if 'volr_' in m else 'OHLC/series'}: missing or all zero/None)" for m in miss) + f"; source {hist.get('source')}")
    sig = scanners.evaluate(bars, idea.entry, extra); stop_fn, tgt_fn, _ = exits(idea, bars)
    split = warmup + int((len(bars) - warmup) * (1 - C.OOS_FRACTION))
    base_bp, stress_bp = C.COST_BPS[idea.asset]; out = dict(idea=idea.id, symbol=idea.symbol, source=hist.get("source"),
        data_from=str(bars[warmup]["date"]), data_to=str(bars[-1]["date"]), oos_from=str(bars[split]["date"]),
        costs_bps_per_side=dict(base=base_bp, stress=stress_bp), min_trades=min_trades)
    res = {}
    for name, bp in (("base", base_bp), ("stress", stress_bp)):
        sim = T.simulate(bars, sig, stop_fn, tgt_fn, idea.time_exit_bars, bp / 1e4, warmup)
        tr = sim["trades"]; ist = [t for t in tr if t["entry_bar"] < split]; oos = [t for t in tr if t["entry_bar"] >= split]
        res[name] = dict(trades=tr, IS=S.trade_metrics([t["ret"] for t in ist], min_trades), OOS=S.trade_metrics([t["ret"] for t in oos], min_trades),
                         mean_R_all=st.mean([t["R"] for t in tr]) if tr else None, open_at_end=sim["open_at_end"])
    out["results"] = {k: {kk: vv for kk, vv in v.items() if kk != "trades"} for k, v in res.items()}
    out["trade_count"] = len(res["stress"]["trades"])
    c = [b["close"] for b in bars]
    out["benchmark_buy_hold"] = dict(IS=c[split - 1] / c[warmup] - 1, OOS=c[-1] / c[split] - 1, note="info only; price return of the symbol")
    stt = res["stress"]
    if stt["IS"]["insufficient_data"] or stt["OOS"]["insufficient_data"]:
        out["verdict"] = "INSUFFICIENT"
        out["reasons"] = [f"insufficient data: IS {stt['IS']['trade_count']} / OOS {stt['OOS']['trade_count']} trades at stress cost, need {min_trades} each"]
        return out
    oos_tr = [t for t in stt["trades"] if t["entry_bar"] >= split]
    out["null"] = null_test(bars, sig, stop_fn, tgt_fn, idea.time_exit_bars, stress_bp / 1e4, warmup, _mean(stt["trades"]), draws)
    out["dsr"] = dsr([t["ret"] for t in stt["trades"]], idea.variants) if idea.variants > 1 else None
    first = idea.entry[0][0]; h = idea.time_exit_bars or 5
    try:
        sv = scanners.series(bars, first, extra=extra) if isinstance(first, str) else None
        fwd = [c[i + h] / c[i] - 1 if i + h < len(c) else None for i in range(len(c))]
        idx = range(warmup, len(c), h)
        out["ic"] = dict(metric=first, horizon_bars=h, spearman=ind.spearman_ic([sv[i] for i in idx], [fwd[i] for i in idx]) if sv else None,
                         note="non-overlapping samples; None below 30 points; info only")
    except KeyError: out["ic"] = None
    why = []
    if stt["OOS"]["mean_ret"] is None or stt["OOS"]["mean_ret"] <= 0: why.append(f"OOS mean trade return at stress cost {stt['OOS']['mean_ret']} <= 0")
    if out["null"] is None or out["null"]["p_value"] >= 0.05: why.append(f"random-entry null p = {out['null'] and round(out['null']['p_value'], 3)} (need < 0.05)")
    if idea.variants > 1 and (out["dsr"] is None or out["dsr"] < 0.95): why.append(f"DSR {out['dsr'] and round(out['dsr'], 3)} over {idea.variants} variants (need >= 0.95)")
    out["verdict"] = "FAIL" if why else "PASS"
    out["reasons"] = why or ["OOS mean > 0 at stress cost, beats random entry (p < 0.05)" + (", DSR >= 0.95" if idea.variants > 1 else "")]
    return out
