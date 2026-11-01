#!/usr/bin/env python3
"""Part A: market regime readout from free public daily data. Read-only; not financial advice.
Usage: python3 sense.py [--json]   -> out/YYYY-MM-DD.md, out/YYYY-MM-DD.json, out/history.json"""
import sys, json, datetime as dt
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).parent))
from tt.sources import equities, crypto, fred, perps, sentiment, venues
from tt.regime import equities as req, crypto as rcr, combine

OUT = Path(__file__).parent / "out"
ETF = ["SPY", "QQQ", "IWM", "RSP", "TLT", "HYG", "UUP", "GLD", "USO"]   # UUP = dollar proxy, GLD gold, USO oil

def _venues(base):
    try:
        qs, errs = venues.quotes(base); s = venues.sanity(qs)
        return dict(sanity=s, errors=errs, source="venue public tickers: " + ", ".join(k for k, q in qs.items() if q),
                    asof=dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"))
    except Exception as e: return dict(error=f"venues: {str(e)[:160]}")

def fetch():
    jobs = {s: (equities.daily, s, s) for s in ETF}
    jobs["^VIX"] = (equities.daily, "^VIX", None)
    jobs["BTC-USD"] = (crypto.daily, "BTC-USD"); jobs["ETH-USD"] = (crypto.daily, "ETH-USD")
    jobs["T10Y2Y"] = (fred.series, "T10Y2Y")
    jobs["HL"] = (perps.hyperliquid,); jobs["KRF"] = (perps.kraken_funding, "BTC")
    jobs["FNG"] = (sentiment.fear_greed,); jobs["STABLES"] = (sentiment.stablecoins,); jobs["VENUES"] = (_venues, "BTC")
    with ThreadPoolExecutor(6) as ex:
        fut = {k: ex.submit(f, *a) for k, (f, *a) in jobs.items()}
        S = {k: f.result() for k, f in fut.items()}
    if "error" in S["^VIX"]:                      # fallback: FRED VIXCLS
        alt = fred.series("VIXCLS", 420)
        if "error" not in alt: S["^VIX"] = alt
        else: S["^VIX"]["error"] += "; " + alt["error"]
    return S

def build(S, today):
    eq = req.rules(S, today); cr = rcr.rules(S, today); g = lambda k: S.get(k) or dict(error="not fetched")
    cr += (rcr.trend_rows(S.get("BTC-USD"), today) + rcr.perp_rows(g("HL"), g("KRF")) +
           rcr.sentiment_rows(g("FNG"), g("STABLES")) + [rcr.venue_row(g("VENUES"))])
    return dict(run_date=today.isoformat(),
                generated=dt.datetime.now(ZoneInfo("America/New_York")).isoformat(timespec="seconds"),
                overall=combine.label(eq, min_known=7), crypto=combine.crypto_label(cr), rules=eq + cr,
                gaps=[f"{k}: {v['error']}" for k, v in S.items() if "error" in v],
                note="Read-only research readout. Not financial advice. Rules and thresholds are fixed and printed; nothing is estimated.")

def changes(R, hist):
    prev = [h for h in hist if h["run_date"] < R["run_date"]]
    if not prev: return ["first run (no earlier history)"]
    p = prev[-1]; out = []
    for k in ("overall", "crypto"):
        if p[k] != R[k]["label"]: out.append(f"{k} label {p[k]} -> {R[k]['label']}")
    for r in R["rules"]:
        old = p["scores"].get(r["id"], "absent"); new = r["score"] if r["status"] == "ok" else "unknown"
        if r["scored"] and old != new: out.append(f"{r['id']} {r['name']}: {old} -> {new}")
    return [f"vs {p['run_date']}: " + ("; ".join(out) if out else "no label or rule-score changes")]

def md(R):
    o, c = R["overall"], R["crypto"]
    L = [f"# Market regime readout {R['run_date']}", f"_Generated {R['generated']} (ET). {R['note']}_", "",
         f"**Overall (cross-asset): {o['label'].upper()}** ({o['why']})  ",
         f"**Crypto: {c['label'].upper()}** ({c['why']})", "", "**Changed since last run:** " + " ".join(R["changes"]), "",
         "| ID | Indicator | Value | Rule triggered | Score | Source | Data date |", "|---|---|---|---|---|---|---|"]
    for r in R["rules"]:
        sc = "info" if not r["scored"] else ("unknown" if r["status"] != "ok" else f"{r['score']:+d}")
        val = r["value"] if r["status"] == "ok" else f"UNKNOWN: {r['reason']}"
        L.append(f"| {r['id']} | {r['name']} | {val} | {r['rule'] if r['status']=='ok' else '-'} | {sc} | {r['source'] or '-'} | {r['data_date'] or '-'} |")
    L += ["", "**Gaps:** " + ("; ".join(R["gaps"]) if R["gaps"] else "none")]
    return "\n".join(L) + "\n"

def main():
    today = dt.datetime.now(ZoneInfo("America/New_York")).date()
    R = build(fetch(), today)
    OUT.mkdir(exist_ok=True); hp = OUT / "history.json"
    hist = json.loads(hp.read_text()) if hp.exists() else []
    R["changes"] = changes(R, hist)
    hist = [h for h in hist if h["run_date"] != R["run_date"]] + [dict(
        run_date=R["run_date"], overall=R["overall"]["label"], crypto=R["crypto"]["label"],
        scores={r["id"]: (r["score"] if r["status"] == "ok" else "unknown") for r in R["rules"] if r["scored"]})]
    hp.write_text(json.dumps(hist[-120:], indent=1))
    (OUT / f"{R['run_date']}.json").write_text(json.dumps(R, indent=1, default=str))
    (OUT / f"{R['run_date']}.md").write_text(md(R))
    print(json.dumps(R, indent=1, default=str) if "--json" in sys.argv else md(R))

if __name__ == "__main__":
    main()
