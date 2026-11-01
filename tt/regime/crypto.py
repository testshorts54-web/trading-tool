"""Crypto regime: BTC vs its 100-day average and the slope of that average. ETH shown for confirmation."""
from tt.regime.common import problem, metrics, row
from tt import indicators as ind

def pct(x): return "n/a" if x is None else f"{x:+.1%}"

def rules(S, today):
    R = []
    for rid, sym in (("C1", "BTC-USD"), ("C2", "ETH-USD")):
        s = S.get(sym); p = problem(s, "crypto", today, 252)
        if p: R.append(row(rid, f"{sym} vs 100-day average", rid == "C1", unknown=p, src=[s])); continue
        m = metrics(s, 365); v = s["closes"]
        slope = m["sma100"] / ind.sma(v[:-20], 100) - 1
        above, rising = m["close"] > m["sma100"], slope > 0
        sc = 1 if above and rising else (-1 if not above and not rising else 0)
        val = (f"close {m['close']:,.0f} vs SMA100 {m['sma100']:,.0f} ({m['close']/m['sma100']-1:+.1%}); SMA100 20d slope {pct(slope)}; "
               f"RSI14 {m['rsi14']:.1f}; 1m {pct(m['ret_1m'])}, 3m {pct(m['ret_3m'])}, 6m {pct(m['ret_6m'])}; DD from 1y high {pct(m['dd_1y'])}")
        R.append(row(rid, f"{sym} vs 100-day average", rid == "C1", val, sc,
                     f"above SMA100 and SMA100 rising -> +1; below and falling -> -1; else 0 => {sc:+d}" + ("" if rid == "C1" else " (info only)"), [s]))
    return R

# ---- Info rows (unscored). Rewrite of flow analysis/regime.py: same inputs (ADX/DI, BB width, TTM squeeze, Hurst)
# but shown as plain values with fixed, printed thresholds; flow's hardcoded confidence % and fallbacks are gone.
def trend_rows(s, today, sym="BTC-USD", rid="C3"):
    p = problem(s, "crypto", today, 120)
    if not p and not s.get("highs"): p = "no high/low data in this source"
    name = f"{sym} trend structure (ADX14, BB20 width, TTM squeeze, Hurst 100d)"
    if p: return [row(rid, name, False, unknown=p, src=[s])]
    h, l, c = s["highs"], s["lows"], s["closes"]
    adx, pdi, mdi = (x[-1] for x in ind.adx_s(h, l, c, 14))
    bw = ind.bb_width_s(c, 20); bw_rank = sum(1 for x in bw[-120:] if x is not None and x <= bw[-1]) / 120
    sq, mom = ind.ttm_squeeze_s(h, l, c, 20); hu = ind.hurst(c[-100:], 20)
    state = "n/a" if adx is None else ("trending" if adx >= 25 else ("no trend" if adx < 20 else "weak trend"))
    val = (f"ADX {adx:.1f} ({state}), +DI {pdi:.1f} / -DI {mdi:.1f}; BB width {bw[-1]:.1f}% (120d pct rank {bw_rank:.0%}); "
           f"TTM squeeze {'ON' if sq[-1] else 'off'}, momentum {mom[-1]:+,.0f}; Hurst {'n/a' if hu is None else f'{hu:.2f}'}")
    return [row(rid, name, False, val, None, "info: ADX >= 25 trending, < 20 no trend; Hurst > 0.5 persistent, < 0.5 mean-reverting", [s])]

def perp_rows(hl, kr):
    R = []
    if "error" in hl: R.append(row("C4", "BTC/ETH perp funding, OI, premium (Hyperliquid)", False, unknown=hl["error"]))
    else:
        parts = [f"{k}: funding {v['funding_apr_pct']:+.1f}% APR, OI ${v['oi_usd']/1e9:.2f}B, mark vs oracle {v['premium_pct']:+.3f}%"
                 for k, v in hl["data"].items() if None not in (v["funding_apr_pct"], v["oi_usd"], v["premium_pct"])]
        R.append(row("C4", "BTC/ETH perp funding, OI, premium (Hyperliquid)", False, "; ".join(parts) or None, None,
                     "info: funding APR = hourly rate x 24 x 365", [hl], None if parts else "no BTC/ETH contexts returned"))
    from tt.sources.perps import funding_spread
    if "error" in kr or "error" in hl:
        R.append(row("C5", "BTC funding spread Hyperliquid - Kraken", False, unknown=kr.get("error") or hl.get("error")))
    else:
        sp = funding_spread(hl["data"].get("BTC"), kr)
        R.append(row("C5", "BTC funding spread Hyperliquid - Kraken", False,
                     None if sp is None else f"HL {hl['data']['BTC']['funding_apr_pct']:+.1f}% vs Kraken {kr['funding_apr_pct']:+.1f}% APR -> spread {sp:+.1f} pp",
                     None, "info only; a spread is not a trade (fees, margin, basis risk)", [hl, kr], None if sp is not None else "missing rate"))
    return R

def sentiment_rows(fng, st):
    R = [row("C6", "Crypto Fear & Greed", False, unknown=fng["error"]) if "error" in fng else
         row("C6", "Crypto Fear & Greed", False, f"{fng['value']} ({fng['label']})", None, "info: 0-24 extreme fear ... 75-100 extreme greed", [fng])]
    R.append(row("C7", "Stablecoin supply, 30d change", False, unknown=st["error"]) if "error" in st else
             row("C7", "Stablecoin supply, 30d change", False, f"${st['total_usd']/1e9:,.1f}B, {st['change_pct']:+.2f}% over {st['days']}d",
                 None, "info: rising supply = more dry powder on-chain", [st]))
    return R

def venue_row(v):
    if "error" in v: return row("C8", "BTC spot venue sanity (Coinbase/Kraken/Binance.US)", False, unknown=v["error"])
    s = v["sanity"]
    if s is None: return row("C8", "BTC spot venue sanity (Coinbase/Kraken/Binance.US)", False, unknown="fewer than 2 venues quoted; " + "; ".join(v["errors"]))
    val = ", ".join(f"{k} {d:+.1f}bp (spread {s['spreads_bps'][k]:.1f}bp)" for k, d in s["dev_bps"].items())
    return row("C8", "BTC spot venue sanity (Coinbase/Kraken/Binance.US)", False, f"mids vs median {s['median_mid']:,.0f}: {val}", None,
               f"info: flag if any venue mid is > 50bp from the median => {'FLAG' if s['flag'] else 'ok'}", [v])
