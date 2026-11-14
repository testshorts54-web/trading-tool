#!/usr/bin/env python3
"""Paper-only prediction-market scan (P4). Public read-only data: Polymarket Gamma events + CLOB books (GET), spot from the
Binance.US public websocket (flow core/exchange.py approach) with trading-tool venue quotes as fallback. No keys, no
login, no orders, no AI calls, no notifications. Signals append to out/predict/signals.jsonl; summary to stdout.
  python3 predict_scan.py --once                       one scan
  python3 predict_scan.py --interval 300               loop (min 60s), writes out/predict/heartbeat for predict_watchdog.sh
  add --log --equity E                                 also log new flagged leads as paper rows (trade-journal/paper-trades.csv)
Signals: dutch_book (neg-risk set below $1 after taker fees, top-of-book depth), crypto_spot (strike market priced far
from a deliberately wide-vol model of live spot), large_move (1h move on a liquid market; info only, never logged).
Cross-venue gaps: UNKNOWN (no second venue; Kalshi API/data terms restrict this use, see README)."""
import sys, json, os, time, argparse, datetime as dt
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).parent))
from tt import predict as P, journal
from tt.sources import venues

OUT = Path(__file__).parent / "out" / "predict"
MIN_DISCOUNT_PCT, MIN_SETS, MIN_PROFIT_USD = 1.0, 10, 1.0     # dutch book: gap after fees, depth, $ at depth
SIGMA, P_OBVIOUS, MIN_EDGE, MAX_DAYS = 1.0, 0.99, 0.02, 30    # crypto: 100% annual vol (well above BTC/ETH realized), ...
MOVE, MIN_LIQ, MAX_SPREAD = 0.10, 10_000, 0.05                # large move: 10 pts in 1h, $10k liquidity, <= 5c spread
REFIRE_S = 6 * 3600                                           # same signal key is re-appended at most every 6h
CROSS_VENUE = "UNKNOWN: no second venue enabled (Kalshi Developer Agreement limits API data to members' own trading)"

def now(): return dt.datetime.now(dt.timezone.utc)

def spot_ws(bases, timeout=8):
    """One bookTicker snapshot per base from the Binance.US public stream (read-only; nothing is sent)."""
    from websockets.sync.client import connect
    url = "wss://stream.binance.us:9443/stream?streams=" + "/".join(f"{b.lower()}usdt@bookTicker" for b in bases)
    out, end = {}, time.time() + timeout
    with connect(url, open_timeout=timeout) as ws:
        while len(out) < len(bases) and time.time() < end:
            d = json.loads(ws.recv(timeout=max(0.1, end - time.time()))).get("data", {})
            b, a = P._f(d.get("b")), P._f(d.get("a"))
            if str(d.get("s", "")).endswith("USDT") and b and a and 0 < b <= a:
                out[d["s"][:-4]] = dict(mid=(a + b) / 2, source="binance.us websocket bookTicker (USDT)")
    return out

def spot(bases):
    out, notes = {}, []
    try: out = spot_ws(sorted(bases))
    except Exception as e: notes.append(f"websocket: {str(e)[:120]}")
    for b in sorted(set(bases) - set(out)):   # fallback: REST quotes, skipped when venues disagree > 50 bps
        qs, errs = venues.quotes(b); live = [q for q in qs.values() if q]; s = venues.sanity(qs)
        if live and not (s and s["flag"]): out[b] = dict(mid=s["median_mid"] if s else live[0].mid, source=f"REST median of {len(live)} venues")
        else: notes.append(f"{b}: spot UNKNOWN ({'venues disagree' if s else '; '.join(errs)[:100]})")
    return out, notes

def url(ev): return f"https://polymarket.com/event/{ev['slug']}"

def dutch(ev):
    ms = ev["markets"]
    if not ev["neg_risk"] or len(ms) < 3 or any(m["best_ask"] is None for m in ms) or sum(m["best_ask"] for m in ms) >= 1: return None
    tops = [P.book_top(m["tokens"][0]) if m["tokens"] else None for m in ms]
    rates = [m["fee_rate"] for m in ms]
    base = dict(type="dutch_book", event=ev["title"], slug=ev["slug"], url=url(ev), side="buy YES on every outcome",
                fees=dict(model="taker rate*p*(1-p) per leg (market feeSchedule)", rates=sorted(set(rates), key=str)))
    if any(t is None for t in tops): return dict(base, flagged=False, reasons=["a leg has no ask in the CLOB book"])
    if any(r is None for r in rates): return dict(base, flagged=False, reasons=["fee rate UNKNOWN on a leg"])
    adj = [p + P.fee_per_share(p, r) for (p, _), r in zip(tops, rates)]
    d = P.event_dutch_book(dict(ev, markets=[dict(m, best_ask=a) for m, a in zip(ms, adj)]), min_discount_pct=MIN_DISCOUNT_PCT)
    sets = min(sz for _, sz in tops); profit = sets * (1 - d["cost"])
    why = [w for w, bad in (("incomplete set (Other/placeholder/augmented)", d["incomplete_set"]), (f"gap < {MIN_DISCOUNT_PCT}% after fees", d["discount_pct"] < MIN_DISCOUNT_PCT),
                            (f"top-of-book depth {sets:.0f} < {MIN_SETS} sets", sets < MIN_SETS), (f"${profit:.2f} at depth < ${MIN_PROFIT_USD}", profit < MIN_PROFIT_USD)) if bad]
    return dict(base, flagged=not why, reasons=why or ["check resolution rules (void/ties) before trusting the set"], cost=round(d["cost"], 4),
                gross_sum_asks=round(sum(p for p, _ in tops), 4), discount_pct=round(d["discount_pct"], 2), apr_pct=d["apr_pct"] and round(d["apr_pct"], 1),
                liquidity=dict(depth_sets=sets, profit_usd_at_depth=round(profit, 2), basis="best ask level only"), end=ev["end"])

def crypto(ev, m, sp, t):
    q = P.parse_crypto_q(m["question"]); end = m["end"]
    if not q or not end or len(m["tokens"]) < 2: return None
    coin, side, k = q; yrs = (dt.datetime.fromisoformat(end.replace("Z", "+00:00")) - t).total_seconds() / (365 * 86400)
    if not 0 < yrs <= MAX_DAYS / 365: return None
    if coin not in sp: return dict(type="crypto_spot", market=m["question"], url=url(ev), flagged=False, reasons=[f"{coin} spot UNKNOWN"])
    p = P.model_p_yes(sp[coin]["mid"], k, side, yrs, SIGMA)
    if P_OBVIOUS > p > 1 - P_OBVIOUS: return None
    buy_yes = p >= P_OBVIOUS; top = P.book_top(m["tokens"][0 if buy_yes else 1]); p_side = p if buy_yes else 1 - p
    base = dict(type="crypto_spot", market=m["question"], url=url(ev), slug=ev["slug"], side="YES" if buy_yes else "NO",
                spot=round(sp[coin]["mid"], 6), spot_source=sp[coin]["source"], strike=k, hours_to_end=round(yrs * 8760, 1),
                model=dict(p_side=round(p_side, 4), sigma_annual=SIGMA, kind="driftless lognormal; assumption, not a forecast"),
                fees=dict(model="taker rate*p*(1-p)", rate=m["fee_rate"]),
                basis_risk="resolves on the source in the market rules (e.g. Binance BTCUSDT 1m close), not this spot feed")
    if top is None: return dict(base, flagged=False, reasons=["no ask in the CLOB book"])
    if m["fee_rate"] is None: return dict(base, flagged=False, reasons=["fee rate UNKNOWN"], ask=top[0])
    cost = top[0] + P.fee_per_share(top[0], m["fee_rate"]); edge = p_side - cost
    why = [w for w, bad in ((f"model edge {edge:+.3f} < {MIN_EDGE}", edge < MIN_EDGE), (f"ask size {top[1]:.0f} < {MIN_SETS}", top[1] < MIN_SETS)) if bad]
    return dict(base, flagged=not why, reasons=why, ask=top[0], cost=round(cost, 4), model_edge=round(edge, 4), liquidity=dict(ask_size=top[1], basis="best ask level only"))

def move(ev, m):
    if m["d1h"] is None or abs(m["d1h"]) < MOVE: return None
    if m["prices"] and m["prices"][0] is not None and not 0.03 < m["prices"][0] < 0.97: return None   # settling (e.g. game over), not news
    spr = None if m["best_ask"] is None or m["best_bid"] is None else m["best_ask"] - m["best_bid"]
    ok = (m["liquidity"] or 0) >= MIN_LIQ and spr is not None and spr <= MAX_SPREAD
    return dict(type="large_move", market=m["question"], url=url(ev), slug=ev["slug"], move_1h=m["d1h"], yes_mid=m["prices"][0] if m["prices"] else None,
                flagged=ok, reasons=[] if ok else ["thin: liquidity < $10k or spread > 5c or UNKNOWN"], fees=dict(rate=m["fee_rate"], note="info only; no edge claimed"),
                liquidity=dict(liquidity_usd=m["liquidity"], spread=spr and round(spr, 4)))

def scan(state, equity=None, log=False, out=OUT):
    t = now(); ts = t.isoformat(timespec="seconds"); gaps = []; evs = {}
    for tag in (None, "crypto"):
        r = P.fetch_events(100, tag)
        if "error" in r: gaps.append(r["error"])
        else: evs.update({e["slug"]: e for e in r["events"]})
    pairs = [(e, m) for e in evs.values() for m in e["markets"]]
    coins = {q[0] for _, m in pairs if (q := P.parse_crypto_q(m["question"]))}
    sp, notes = spot(coins) if coins else ({}, []); gaps += notes
    sigs = []
    for e in evs.values():
        try: sigs.append(dutch(e))
        except Exception as x: gaps.append(f"dutch {e['slug']}: {str(x)[:100]}")
    for e, m in pairs:
        try: sigs += [crypto(e, m, sp, t), move(e, m)]
        except Exception as x: gaps.append(f"market {m['question'][:40]}: {str(x)[:100]}")
    sigs = [dict(s, ts=ts) for s in sigs if s]
    big = {}   # one large_move per event (largest), so a live game does not produce 20 rows
    for s in sigs:
        if s["type"] == "large_move" and abs(s["move_1h"]) > abs(big.get(s["slug"], {}).get("move_1h", 0)): big[s["slug"]] = s
    sigs = [s for s in sigs if s["type"] != "large_move"] + list(big.values())
    counts = {}
    for s in sigs: c = counts.setdefault(s["type"], dict(evaluated=0, flagged=0)); c["evaluated"] += 1; c["flagged"] += s["flagged"]
    new = []
    for s in (s for s in sigs if s["flagged"]):
        key = f"{s['type']}:{s.get('slug')}:{s.get('market', '')}:{s.get('side', '')}"
        if t.timestamp() - state.setdefault("fired", {}).get(key, 0) >= REFIRE_S:
            state["fired"][key] = t.timestamp(); new.append(s)
            if log and s["type"] != "large_move" and key not in state.setdefault("logged", []): s["paper"] = paper(s, equity); state["logged"].append(key)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "signals.jsonl", "a") as f:
        for s in new: f.write(json.dumps(s, default=str) + "\n")
    return dict(ts=ts, events=len(evs), markets=len(pairs), counts=counts, new_appended=len(new), cross_venue=CROSS_VENUE,
                spot={k: dict(mid=round(v["mid"], 6), source=v["source"]) for k, v in sp.items()}, gaps=gaps[:20], paper_only=True)

def paper(s, equity):
    """Size with the 1%-risk / 10%-position caps (P.size_binary) and append one paper row via the existing journal."""
    size = P.size_binary(s["cost"], equity, s["liquidity"].get("depth_sets") or s["liquidity"].get("ask_size"))
    if size["qty"] <= 0: return "not logged: size rounds to zero"
    idea = SimpleNamespace(id=s["type"], source="predict_scan", symbol=f"PM:{s['slug']}"[:60], side="long",
                           thesis=f"{s['type']} {s['side']}: cost {s['cost']} vs payout 1 at resolution; {'; '.join(s['reasons'])}; {s['url']}")
    r = dict(approved=True, entry=s["cost"], stop=0.0, target=1.0, time_exit_bars=None, size=size)   # binary: worst case 0, best case 1
    return journal.log(idea, r, "not backtested (pricing lead)")

def main():
    a = argparse.ArgumentParser(); a.add_argument("--once", action="store_true"); a.add_argument("--interval", type=int, default=300)
    a.add_argument("--log", action="store_true"); a.add_argument("--equity", type=float); a.add_argument("--out", default=str(OUT))
    a.add_argument("--logical", action="store_true")
    x = a.parse_args()
    if x.logical:
        from predict_logical_scan import run_logical_scan
        res = run_logical_scan(out_dir=x.out if x.out != str(OUT) else None)
        print(json.dumps(res, indent=1), flush=True)
        return
    out = Path(x.out); out.mkdir(parents=True, exist_ok=True)
    if x.log and not (x.equity and x.equity > 0): a.error("--log needs --equity > 0 (paper equity; no default)")
    sp = out / "state.json"; state = json.loads(sp.read_text()) if sp.exists() else {}
    while True:
        print(json.dumps(scan(state, x.equity, x.log, out), indent=1), flush=True)
        tmp = sp.with_suffix(".tmp"); tmp.write_text(json.dumps(state)); os.replace(tmp, sp)
        (out / "heartbeat").touch()
        if x.once: return
        time.sleep(max(60, x.interval))

if __name__ == "__main__":
    main()
