#!/usr/bin/env python3
"""Cheap batch screen of ideas.json rules on one coin or a pooled basket (paper-only research; places nothing).
  python3 screen_batch.py [--ids a,b] [--oos-from 2023-01-01] [--draws 100] [--out out/screens/DATE]
Per idea: coins = idea.coins (list of symbols; "ALL" = every local crypto CSV) or [idea.symbol]. Same simulator, exits,
costs (base/stress per side), 30-trade minimum, random-entry null and DSR as pipeline.py validate, but trades are pooled
across the basket and the IS/OOS split is a fixed date. Also writes an OOS daily-return series per idea (equal weight over
open positions, cash when flat) and its correlation with other ideas and with BTC buy-and-hold.
Verdict: INSUFFICIENT (< 30 pooled trades IS or OOS), PASS (stress OOS mean > 0, null p < 0.05, DSR >= 0.95 if variants > 1), else FAIL.
A PASS here is a cheap screen, not proof (survivorship bias, daily fills, no signal-based exits)."""
import sys, json, math, random, argparse, datetime as dt, statistics as st
from pathlib import Path
from multiprocessing import Pool
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, "/workspace/backtest")
from btlib import trades as T, stats as S
from tt import config as C, validate as V
from tt.ideas import schema, scanners, extras
from tt.sources import history
ROOT = Path(__file__).parent; WARM = 200

def all_coins():
    return sorted({p.name[:-7] for d in history.CRYPTO_DIRS for p in d.glob("*-USD_1d.csv")})

def daily(bars, trades):
    """date -> return of the open position that day (fills include cost)."""
    out = {}
    for t in trades:
        j, k = t["entry_bar"], t["exit_bar"]
        for m in range(j, k + 1):
            a = t["entry"] if m == j else bars[m - 1]["close"]; b = t["exit"] if m == k else bars[m]["close"]
            out[bars[m]["date"]] = b / a - 1
    return out

def screen(args):
    idea, oos_from, draws = args
    coins = all_coins() if idea.coins == ["ALL"] else (idea.coins or [idea.symbol])
    per, gaps = [], []
    for sym in coins:
        h = history.load(sym, idea.asset)
        if "error" in h or len(h["bars"]) < WARM + 30: gaps.append(sym); continue
        b = h["bars"]; sig = scanners.evaluate(b, idea.entry, extras.build(b, idea.entry, history.load, idea.asset))
        sf, tf, _ = V.exits(idea, b)
        split = next((i for i, x in enumerate(b) if x["date"] >= oos_from), len(b))
        per.append(dict(sym=sym, bars=b, sig=sig, sf=sf, tf=tf, split=split))
    base_bp, stress_bp = C.COST_BPS[idea.asset]; res = {}
    for name, bp in (("base", base_bp), ("stress", stress_bp)):
        IS, OOS, dl = [], [], {}
        for p in per:
            tr = T.simulate(p["bars"], p["sig"], p["sf"], p["tf"], idea.time_exit_bars, bp / 1e4, WARM)["trades"]
            p[name] = tr; IS += [t for t in tr if t["entry_bar"] < p["split"]]; OOS += [t for t in tr if t["entry_bar"] >= p["split"]]
            for d, r in daily(p["bars"], tr).items(): dl.setdefault(d, []).append(r)
        res[name] = dict(IS=S.trade_metrics([t["ret"] for t in IS]), OOS=S.trade_metrics([t["ret"] for t in OOS]),
                         n_IS=len(IS), n_OOS=len(OOS), oos_mean=st.mean([t["ret"] for t in OOS]) if OOS else None,
                         oos_median=st.median([t["ret"] for t in OOS]) if OOS else None,
                         daily={d: st.mean(v) for d, v in dl.items()})
    s = res["stress"]; out = dict(idea=idea.id, coins=len(per), missing=gaps, oos_from=str(oos_from), thesis=idea.thesis, source=idea.source,
        n_IS=s["n_IS"], n_OOS=s["n_OOS"], oos_mean_stress=s["oos_mean"], oos_mean_base=res["base"]["oos_mean"], oos_median_stress=s["oos_median"],
        IS_mean_stress=s["IS"].get("mean_ret"), oos_win_pct=s["OOS"].get("win_rate_pct"))
    m = lambda r: st.mean(r) if r else None
    out["per_symbol"] = [dict(sym=p["sym"], n_IS=sum(t["entry_bar"] < p["split"] for t in p["stress"]), n_OOS=sum(t["entry_bar"] >= p["split"] for t in p["stress"]),
        IS_mean_stress=m([t["ret"] for t in p["stress"] if t["entry_bar"] < p["split"]]), OOS_mean_stress=m([t["ret"] for t in p["stress"] if t["entry_bar"] >= p["split"]]))
        for p in per]
    oos_coins = [p for p in per if any(t["entry_bar"] >= p["split"] for t in p["stress"])]
    out["breadth_pos_oos"] = (sum(st.mean([t["ret"] for t in p["stress"] if t["entry_bar"] >= p["split"]]) > 0 for p in oos_coins), len(oos_coins))
    btc = {x["date"]: x for x in history.load("BTC-USD", "crypto")["bars"]}
    days = sorted(d for d in btc if d >= oos_from); dly = s["daily"]
    eq = math.prod(1 + dly.get(d, 0) for d in days); bh = btc[days[-1]]["close"] / btc[days[0]]["open"]; yrs = len(days) / 365
    out.update(oos_net_return=eq - 1, oos_cagr=eq ** (1 / yrs) - 1, btc_hold_oos=bh - 1, btc_hold_cagr=bh ** (1 / yrs) - 1,
               exposure_pct=100 * sum(d in dly for d in days) / len(days))
    out["_daily_oos"] = {str(d): dly.get(d, 0.0) for d in days}
    if s["IS"]["insufficient_data"] or s["OOS"]["insufficient_data"]:
        out["verdict"] = "INSUFFICIENT"; out["reasons"] = [f"IS {s['n_IS']} / OOS {s['n_OOS']} pooled trades, need {C.MIN_TRADES} each"]; return out
    allr = [t["ret"] for p in per for t in p["stress"]]; actual = st.mean(allr); why = []
    if s["oos_mean"] is None or s["oos_mean"] <= 0: why.append(f"OOS mean at stress cost {s['oos_mean']:.4f} <= 0")
    else:   # null only when it can matter (it is the slow part)
        rng = random.Random(C.NULL_SEED); ge = n = 0
        for _ in range(draws):
            rs = []
            for p in per:
                el = range(WARM, len(p["bars"]) - 1); q = sum(p["sig"][i] for i in el) / max(len(el), 1)
                if q == 0: continue
                sg = [i >= WARM and rng.random() < q for i in range(len(p["bars"]))]
                rs += [t["ret"] for t in T.simulate(p["bars"], sg, p["sf"], p["tf"], idea.time_exit_bars, stress_bp / 1e4, WARM)["trades"]]
            if rs: n += 1; ge += st.mean(rs) >= actual
        out["null_p"] = (ge + 1) / (n + 1)
        if out["null_p"] >= 0.05: why.append(f"random-entry null p = {out['null_p']:.3f} (need < 0.05)")
    out["dsr"] = V.dsr(allr, idea.variants) if idea.variants > 1 else None
    if idea.variants > 1 and not why and (out["dsr"] is None or out["dsr"] < 0.95): why.append(f"DSR {out['dsr']} over {idea.variants} variants")
    out["verdict"] = "FAIL" if why else "PASS"; out["reasons"] = why or ["stress OOS mean > 0, beats random entry"]
    return out

def corr(a, b):
    ma, mb = st.mean(a), st.mean(b); va = sum((x - ma) ** 2 for x in a); vb = sum((y - mb) ** 2 for y in b)
    return None if va == 0 or vb == 0 else sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb)

def main(argv=None):
    a = argparse.ArgumentParser(); a.add_argument("--ideas", default=str(ROOT / "ideas.json")); a.add_argument("--ids")
    a.add_argument("--oos-from", default="2023-01-01"); a.add_argument("--draws", type=int, default=100)
    a.add_argument("--out", default=str(ROOT / "out" / "screens" / dt.date.today().isoformat())); a.add_argument("--procs", type=int, default=6)
    x = a.parse_args(argv); ideas = schema.load(x.ideas); oos = dt.date.fromisoformat(x.oos_from)
    sel = [i for k, i in ideas.items() if (x.ids is None and i.asset == "crypto") or (x.ids and k in x.ids.split(","))]
    with Pool(x.procs) as pool: rows = pool.map(screen, [(i, oos, x.draws) for i in sel])
    out = Path(x.out); out.mkdir(parents=True, exist_ok=True)
    btc = {x2["date"]: x2["close"] for x2 in history.load("BTC-USD", "crypto")["bars"]}
    days = list(rows[0]["_daily_oos"]) if rows else []
    btc_r = [btc[dt.date.fromisoformat(d)] / btc[dt.date.fromisoformat(d) - dt.timedelta(1)] - 1 for d in days]
    for r in rows: r["corr_btc"] = corr([r["_daily_oos"][d] for d in days], btc_r)
    surv = [r for r in rows if r["verdict"] == "PASS" or (r["verdict"] != "INSUFFICIENT" and (r["oos_mean_stress"] or 0) > 0)]
    cm = {r["idea"]: {q["idea"]: corr([r["_daily_oos"][d] for d in days], [q["_daily_oos"][d] for d in days]) for q in surv} for r in surv}
    lines = ["| rule | coins | trades IS/OOS | verdict | OOS mean / median per trade (stress) | OOS net (EW open pos.) | BTC hold OOS | exposure | corr BTC |", "|---|---|---|---|---|---|---|---|---|"]
    f = lambda v, p=1: "n/a" if v is None else f"{100 * v:+.{p}f}%"
    for r in sorted(rows, key=lambda r: (r["verdict"] != "PASS", -(r["oos_mean_stress"] or -9))):
        lines.append(f"| {r['idea']} | {r['coins']} | {r['n_IS']}/{r['n_OOS']} | {r['verdict']} | {f(r['oos_mean_stress'], 2)} / {f(r['oos_median_stress'], 2)} | {f(r['oos_net_return'])} | {f(r['btc_hold_oos'])} | {r['exposure_pct']:.0f}% | {r['corr_btc'] if r['corr_btc'] is None else round(r['corr_btc'], 2)} |")
    (out / "summary.md").write_text(f"# Batch screen {dt.date.today()} (OOS from {x.oos_from}, stress {C.COST_BPS['crypto'][1]} bp/side; paper-only, a screen is not proof)\n\n" + "\n".join(lines)
        + "\n\nCorrelation of OOS daily returns among rules with positive stress OOS mean:\n\n```\n" + json.dumps({k: {kk: (None if vv is None else round(vv, 2)) for kk, vv in v.items()} for k, v in cm.items()}, indent=1) + "\n```\n")
    (out / "results.json").write_text(json.dumps([{k: v for k, v in r.items() if k != "_daily_oos"} for r in rows], indent=1, default=str))
    print(out / "summary.md")

if __name__ == "__main__":
    main()
