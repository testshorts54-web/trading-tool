#!/usr/bin/env python3
"""One-shot paper-only logical scan for Polymarket prediction markets.

Checks:
1) negRisk YES basket (complete executable sets vs hidden-Other/incomplete sets,
   plus optional NO-basket convert sketch).
2) Strike-ladder and nested-deadline monotonicity.
3) Duplicate same-event listings.

No orders, no live keys, standard library only.
Outputs to predict_paper/logical-<timestamp>/{summary.json, signals.jsonl}.
"""
from __future__ import annotations
import argparse, datetime as dt, json, math, re, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tt import predict as P
from tt.http import get

# Import strike_arb from arb-carry-study if available
try:
    sys.path.insert(0, "/workspace/arb-carry-study")
    from predict_extra import strike_arb
except Exception:
    strike_arb = None

OUT_ROOT = Path(__file__).parent / "predict_paper"
CLOB_BOOK = "https://clob.polymarket.com/book"


def now():
    return dt.datetime.now(dt.timezone.utc)


def normalize_text(text):
    """Normalize text for duplicate question matching."""
    t = (text or "").lower().replace(",", "")
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def parse_top_book(token_id):
    """Fetch best bid and ask with sizes for a token."""
    if not token_id:
        return None
    try:
        raw = json.loads(get(f"{CLOB_BOOK}?token_id={token_id}", timeout=10, retries=1))
        parsed_bids = [(P._f(b.get("price")), P._f(b.get("size"))) for b in raw.get("bids") or [] if P._f(b.get("price")) and P._f(b.get("size"))]
        parsed_asks = [(P._f(a.get("price")), P._f(a.get("size"))) for a in raw.get("asks") or [] if P._f(a.get("price")) and P._f(a.get("size"))]
        best_bid = max(parsed_bids, key=lambda x: x[0]) if parsed_bids else (None, 0.0)
        best_ask = min(parsed_asks, key=lambda x: x[0]) if parsed_asks else (None, 0.0)
        return dict(bid=best_bid[0], bid_sz=best_bid[1], ask=best_ask[0], ask_sz=best_ask[1])
    except Exception:
        return None


def evaluate_neg_risk(ev, book_parser=parse_top_book):
    """Check negRisk YES basket and incomplete sets."""
    signals = []
    if not ev.get("neg_risk"):
        return signals
    ms = ev.get("markets") or []
    if len(ms) < 2:
        return signals

    incomplete = ev.get("augmented", False) or any(
        m.get("other") or any(w in (m.get("title") or "").lower() for w in P.PLACEHOLDER)
        for m in ms
    )

    if incomplete:
        signals.append(dict(
            type="neg_risk_incomplete",
            event=ev.get("title"),
            slug=ev.get("slug"),
            markets_count=len(ms),
            flagged=False,
            note="hidden-Other / incomplete — not a locked basket",
        ))
        # Optional NO-basket convert sketch: sum of NO asks vs n-1 after fees
        no_costs = []
        for m in ms:
            toks = m.get("tokens") or []
            if len(toks) >= 2:
                top = book_parser(toks[1]) if book_parser else None
                if top and top.get("ask") is not None:
                    fee = P.fee_per_share(top["ask"], m.get("fee_rate"))
                    no_costs.append(top["ask"] + (fee if fee is not None else 0.0))
        if len(no_costs) == len(ms):
            signals.append(dict(
                type="no_basket_convert_sketch",
                event=ev.get("title"),
                slug=ev.get("slug"),
                n_legs=len(ms),
                sum_no_asks=round(sum(no_costs), 4),
                payout_target=len(ms) - 1,
                flagged=False,
                note="NO-basket convert sketch (informational only; never flagged as locked if set is incomplete)",
            ))
        return signals

    # Complete set: evaluate YES basket after taker fees
    tops = []
    for m in ms:
        toks = m.get("tokens") or []
        top = book_parser(toks[0]) if (toks and book_parser) else None
        tops.append(top)
    rates = [m.get("fee_rate") for m in ms]

    if any(t is None or t.get("ask") is None for t in tops) or any(r is None for r in rates):
        signals.append(dict(
            type="neg_risk_basket",
            event=ev.get("title"),
            slug=ev.get("slug"),
            flagged=False,
            reasons=["a leg has no ask in the CLOB book or fee rate UNKNOWN"],
        ))
        return signals

    adj = [t["ask"] + P.fee_per_share(t["ask"], r) for t, r in zip(tops, rates)]
    cost = sum(adj)
    disc = (1.0 - cost) * 100.0
    sets = min(t["ask_sz"] for t in tops)
    profit = sets * (1.0 - cost)
    why = []
    if disc < 1.0:
        why.append("gap < 1.0% after fees")
    if sets < 10:
        why.append(f"top-of-book depth {sets:.0f} < 10 sets")
    if profit < 1.0:
        why.append(f"profit ${profit:.2f} at depth < $1.00")

    signals.append(dict(
        type="neg_risk_basket",
        event=ev.get("title"),
        slug=ev.get("slug"),
        flagged=not why,
        cost=round(cost, 4),
        gross_sum=round(sum(t["ask"] for t in tops), 4),
        discount_pct=round(disc, 2),
        depth_sets=sets,
        profit_usd_at_depth=round(profit, 2),
        reasons=why or ["complete executable set after taker fees"],
    ))
    return signals


def evaluate_strike_ladder(markets, book_parser=parse_top_book):
    """Check strike-ladder monotonicity across markets with same asset, side, and deadline."""
    signals = []
    if not strike_arb:
        return signals

    grouped = defaultdict(list)
    for m in markets:
        parsed = P.parse_crypto_q(m.get("question"))
        end = m.get("end")
        if parsed and end and m.get("tokens"):
            coin, side, k = parsed
            grouped[(coin, side, end)].append((k, m))

    for (coin, side, end), k_list in grouped.items():
        if len(k_list) < 2:
            continue
        k_list.sort(key=lambda x: x[0])
        for i in range(len(k_list) - 1):
            lo_k, lo_m = k_list[i]
            hi_k, hi_m = k_list[i + 1]
            lo_book = book_parser(lo_m["tokens"][0]) if book_parser else None
            hi_book = book_parser(hi_m["tokens"][0]) if book_parser else None
            if not lo_book or not hi_book:
                continue
            lo_dict = dict(strike=lo_k, side=side, ask=lo_book.get("ask"), ask_sz=lo_book.get("ask_sz"),
                           bid=lo_book.get("bid"), bid_sz=lo_book.get("bid_sz"), fee_rate=lo_m.get("fee_rate"))
            hi_dict = dict(strike=hi_k, side=side, ask=hi_book.get("ask"), ask_sz=hi_book.get("ask_sz"),
                           bid=hi_book.get("bid"), bid_sz=hi_book.get("bid_sz"), fee_rate=hi_m.get("fee_rate"))
            try:
                res = strike_arb(lo_dict, hi_dict)
                if res and (res.get("flagged") or (res.get("edge") and res["edge"] > 0)):
                    signals.append(dict(
                        type="strike_monotonicity",
                        coin=coin,
                        side=side,
                        end=end,
                        lo_strike=lo_k,
                        hi_strike=hi_k,
                        **res,
                    ))
            except Exception:
                pass
    return signals


def evaluate_nested_deadlines(events, book_parser=parse_top_book):
    """Check same-event or same-claim nested deadlines: earlier date must not price above later date."""
    signals = []
    for ev in events:
        ms = ev.get("markets") or []
        if len(ms) < 2:
            continue
        # pair markets that have end timestamps
        dated = []
        for m in ms:
            end = m.get("end")
            toks = m.get("tokens") or []
            if end and toks:
                try:
                    dt_end = dt.datetime.fromisoformat(str(end).replace("Z", "+00:00"))
                    dated.append((dt_end, m))
                except ValueError:
                    pass
        if len(dated) < 2:
            continue
        dated.sort(key=lambda x: x[0])
        for i in range(len(dated) - 1):
            t1, m1 = dated[i]
            t2, m2 = dated[i + 1]
            if t1 >= t2:
                continue
            b1 = book_parser(m1["tokens"][0]) if book_parser else None
            b2 = book_parser(m2["tokens"][0]) if book_parser else None
            if not b1 or not b2 or b1.get("bid") is None or b2.get("ask") is None:
                continue
            r1, r2 = m1.get("fee_rate"), m2.get("fee_rate")
            proceeds = b1["bid"] - (P.fee_per_share(b1["bid"], r1) if r1 is not None else 0.0)
            cost = b2["ask"] + (P.fee_per_share(b2["ask"], r2) if r2 is not None else 0.0)
            edge = proceeds - cost
            sz = min(b1.get("bid_sz", 0.0), b2.get("ask_sz", 0.0))
            if edge >= 0.01 and sz >= 10:
                signals.append(dict(
                    type="nested_deadline_monotonicity",
                    event=ev.get("title"),
                    slug=ev.get("slug"),
                    t1=t1.isoformat(),
                    t2=t2.isoformat(),
                    m1_question=m1.get("question"),
                    m2_question=m2.get("question"),
                    sell_bid=b1["bid"],
                    buy_ask=b2["ask"],
                    edge=round(edge, 4),
                    depth=sz,
                    flagged=True,
                    note="earlier deadline priced above later deadline after taker fees",
                ))
    return signals


def evaluate_duplicates(events, book_parser=parse_top_book):
    """Check duplicate same-event listings with different condition_ids."""
    signals = []
    by_q = defaultdict(list)
    for ev in events:
        for m in ev.get("markets") or []:
            cid = m.get("condition_id")
            q = m.get("question")
            if cid and q and m.get("tokens"):
                norm = normalize_text(q)
                by_q[norm].append((ev, m))

    seen_pairs = set()
    for norm, items in by_q.items():
        if len(items) < 2:
            continue
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                ev1, m1 = items[i]
                ev2, m2 = items[j]
                cid1, cid2 = m1["condition_id"], m2["condition_id"]
                if cid1 == cid2:
                    continue
                pair_key = tuple(sorted([cid1, cid2]))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                b1 = book_parser(m1["tokens"][0]) if book_parser else None
                b2 = book_parser(m2["tokens"][0]) if book_parser else None
                r1, r2 = m1.get("fee_rate"), m2.get("fee_rate")

                ask1 = b1.get("ask") if b1 else None
                ask2 = b2.get("ask") if b2 else None
                bid1 = b1.get("bid") if b1 else None
                bid2 = b2.get("bid") if b2 else None

                ask_sum = (ask1 + ask2) if (ask1 is not None and ask2 is not None) else None

                # Check if complement or monotonicity rule is violated after fees
                flagged = False
                note = "possible duplicate, rules not compared"
                edge = None

                if ask1 is not None and bid2 is not None:
                    # Selling 2 at bid and buying 1 at ask
                    fee_buy = P.fee_per_share(ask1, r1) if r1 is not None else 0.0
                    fee_sell = P.fee_per_share(bid2, r2) if r2 is not None else 0.0
                    gap = (bid2 - fee_sell) - (ask1 + fee_buy)
                    if gap >= 0.01:
                        flagged = True
                        note = "duplicate price gap violates monotonicity after taker fees"
                        edge = round(gap, 4)

                if not flagged and ask2 is not None and bid1 is not None:
                    fee_buy = P.fee_per_share(ask2, r2) if r2 is not None else 0.0
                    fee_sell = P.fee_per_share(bid1, r1) if r1 is not None else 0.0
                    gap = (bid1 - fee_sell) - (ask2 + fee_buy)
                    if gap >= 0.01:
                        flagged = True
                        note = "duplicate price gap violates monotonicity after taker fees"
                        edge = round(gap, 4)

                signals.append(dict(
                    type="duplicate_listing",
                    question=m1.get("question"),
                    cid1=cid1,
                    cid2=cid2,
                    slug1=ev1.get("slug"),
                    slug2=ev2.get("slug"),
                    ask1=ask1,
                    ask2=ask2,
                    ask_sum=round(ask_sum, 4) if ask_sum is not None else None,
                    edge=edge,
                    flagged=flagged,
                    note=note,
                ))
    return signals


def run_logical_scan(limit=60, out_dir=None):
    """Run one-shot logical scan over public Polymarket Gamma events and CLOB books."""
    t0 = now()
    stamp = t0.strftime("%Y%m%dT%H%M%SZ")
    out = Path(out_dir) if out_dir else OUT_ROOT / f"logical-{stamp}"
    out.mkdir(parents=True, exist_ok=True)

    fetched = P.fetch_events(limit=limit)
    events = fetched.get("events") or []

    all_markets = [m for ev in events for m in ev.get("markets") or []]

    signals = []
    # 1. negRisk YES basket
    for ev in events:
        signals.extend(evaluate_neg_risk(ev))

    # 2. strike-ladder and nested deadlines
    signals.extend(evaluate_strike_ladder(all_markets))
    signals.extend(evaluate_nested_deadlines(events))

    # 3. duplicate listings
    signals.extend(evaluate_duplicates(events))

    signals_path = out / "signals.jsonl"
    with open(signals_path, "w") as f:
        for s in signals:
            f.write(json.dumps(s, default=str) + "\n")

    summary = dict(
        scan="logical_scan",
        timestamp=t0.isoformat(timespec="seconds"),
        events_scanned=len(events),
        markets_scanned=len(all_markets),
        signals_total=len(signals),
        signals_flagged=sum(1 for s in signals if s.get("flagged")),
        neg_risk_signals=sum(1 for s in signals if "neg_risk" in s.get("type", "")),
        strike_signals=sum(1 for s in signals if s.get("type") == "strike_monotonicity"),
        nested_deadline_signals=sum(1 for s in signals if s.get("type") == "nested_deadline_monotonicity"),
        duplicate_signals=sum(1 for s in signals if s.get("type") == "duplicate_listing"),
        out_dir=str(out),
    )
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    return summary


def main():
    a = argparse.ArgumentParser(description="Paper-only logical scan")
    a.add_argument("--once", action="store_true", default=True, help="Run once")
    a.add_argument("--limit", type=int, default=60, help="Max events to page")
    a.add_argument("--out", default="", help="Output directory")
    x = a.parse_args()

    res = run_logical_scan(limit=x.limit, out_dir=x.out)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
