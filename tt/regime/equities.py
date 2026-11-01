"""Cross-asset (equities/macro) regime rules. Every threshold is written in the rule text."""
from tt import indicators as ind
from tt.regime.common import problem, metrics, trend_score, band, row

def pct(x): return "n/a" if x is None else f"{x:+.1%}"
def num(x, n=2): return "n/a" if x is None else f"{x:.{n}f}"

def _trend_row(rid, sym, S, today, scored):
    s = S.get(sym); p = problem(s, "equity", today, 200)
    if p: return row(rid, f"{sym} trend", scored, unknown=p, src=[s])
    m = metrics(s); sc, rule = trend_score(m)
    val = (f"close {num(m['close'])}, SMA50 {num(m['sma50'])}, SMA200 {num(m['sma200'])}, RSI14 {num(m['rsi14'],1)}, "
           f"1m {pct(m['ret_1m'])}, 3m {pct(m['ret_3m'])}, 6m {pct(m['ret_6m'])}")
    return row(rid, f"{sym} trend", scored, val, sc, rule, [s])

def _ratio_row(rid, a, b, S, today, name):
    sa, sb = S.get(a), S.get(b)
    p = problem(sa, "equity", today, 130) or problem(sb, "equity", today, 130)
    if p: return row(rid, name, True, unknown=p, src=[sa, sb])
    d, v = ind.ratio(dict(zip(sa["dates"], sa["closes"])), dict(zip(sb["dates"], sb["closes"])))
    r3 = ind.ret_days(d, v, 91); sma50 = ind.sma(v, 50)
    sc, rule = band(r3, 0.01, -0.01)
    val = f"{a}/{b} 3m change {pct(r3)}; ratio {v[-1]:.4f} vs its SMA50 {num(sma50,4)}"
    return row(rid, name, True, val, sc, f"3m change of {a}/{b}: " + rule, [sa, sb])

def rules(S, today):
    R = [_trend_row("E1", "SPY", S, today, True), _trend_row("E2", "QQQ", S, today, True)]
    s = S.get("SPY"); p = problem(s, "equity", today, 252)
    if p:
        R += [row("E3", "SPY momentum (3m)", True, unknown=p, src=[s]), row("E8", "SPY drawdown from 1y high", True, unknown=p, src=[s])]
        spy = None
    else:
        spy = metrics(s)
        sc, rule = band(spy["ret_3m"], 0.02, -0.02)
        R.append(row("E3", "SPY momentum (3m)", True, f"3m {pct(spy['ret_3m'])}, RSI14 {num(spy['rsi14'],1)}", sc, "SPY 3m return: " + rule, [s]))
        dd = spy["dd_1y"]
        sc = 1 if dd > -0.05 else (-1 if dd < -0.10 else 0)
        R.append(row("E8", "SPY drawdown from 1y high", True, pct(dd), sc,
                     "> -5% -> +1; -10%..-5% -> 0; < -10% -> -1", [s]))
    v = S.get("^VIX"); p = problem(v, "equity", today, 252)
    if p: R.append(row("E4", "Volatility (VIX)", True, unknown=p, src=[v]))
    else:
        x = v["closes"][-1]; pr = ind.percentile_rank(v["closes"])
        sc = 1 if x < 18 else (-1 if x > 25 else 0)
        rv = spy["vol20"] if spy else None
        R.append(row("E4", "Volatility (VIX)", True, f"VIX {x:.2f} (1y pct rank {pr:.0%}); SPY 20d realized vol {pct(rv) if rv else 'n/a'}",
                     sc, "VIX < 18 -> +1; 18-25 -> 0; > 25 -> -1", [v]))
    R.append(_ratio_row("E5", "RSP", "SPY", S, today, "Breadth: equal-weight vs cap-weight"))
    R.append(_ratio_row("E6", "IWM", "SPY", S, today, "Breadth: small caps vs large caps"))
    R.append(_ratio_row("E7", "HYG", "TLT", S, today, "Credit risk appetite: high yield vs Treasuries"))
    b, s = S.get("BTC-USD"), S.get("SPY")
    p = problem(b, "crypto", today, 182) or problem(s, "equity", today, 130)
    if p: R.append(row("E9", "Crypto vs equities (3m)", True, unknown=p, src=[b, s]))
    else:
        rb, rs = ind.ret_days(b["dates"], b["closes"], 91), ind.ret_days(s["dates"], s["closes"], 91)
        sc, rule = band(rb - rs, 0.05, -0.05, " pts", "{:+.1%}")
        R.append(row("E9", "Crypto vs equities (3m)", True, f"BTC 3m {pct(rb)} vs SPY 3m {pct(rs)}", sc, "BTC minus SPY 3m return: " + rule, [b, s]))
    R.sort(key=lambda r: r["id"])
    # info rows (not scored)
    for i, sym in enumerate(["IWM", "RSP", "TLT", "HYG", "UUP", "GLD", "USO"], 1):
        R.append(_trend_row(f"I{i}", sym, S, today, False))
    f = S.get("T10Y2Y"); p = problem(f, "fred", today, 1)
    if p: R.append(row("I8", "Yield curve 10y-2y", False, unknown=p, src=[f]))
    else:
        x = f["closes"][-1]
        old = [c for d, c in zip(f["dates"], f["closes"]) if (f["dates"][-1] - d).days >= 91]
        R.append(row("I8", "Yield curve 10y-2y", False, f"{x:+.2f} pp (3m ago {old[-1]:+.2f})" if old else f"{x:+.2f} pp",
                     None, "info only: inverted (<0) is a long-lead recession signal, not a timing signal", [f]))
    return R
