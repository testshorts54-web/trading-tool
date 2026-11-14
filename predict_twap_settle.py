#!/usr/bin/env python3
"""Paper-only TWAP settlement and post-window analysis.

Reads twap_log ledger entries from a 5m/15m or 1h/4h maker sim run,
fetches public Gamma event metadata and resolution payouts, and writes
predict_paper/<run>/twap_settle.json and twap_settle.jsonl.
Public GET only. No keys, no signing, no live trading.
"""
from __future__ import annotations
import argparse, json, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tt import predict as P
from tt.http import get

GAMMA_EVENTS = "https://gamma-api.polymarket.com/events"
DATA_RES = "https://data-api.polymarket.com/v2/resolutions"


def fetch_gamma_event(slug):
    """Fetch public event metadata by slug."""
    try:
        raw = json.loads(get(f"{GAMMA_EVENTS}?slug={slug}", timeout=15, retries=1))
        if isinstance(raw, list) and raw:
            return raw[0]
        if isinstance(raw, dict):
            return raw
    except Exception:
        pass
    return None


def fetch_resolution_payouts(condition_id):
    """Fetch resolution payouts from public Data API v2."""
    try:
        raw = json.loads(get(f"{DATA_RES}?condition={condition_id}", timeout=15, retries=1))
        rows = raw if isinstance(raw, list) else (raw.get("data") if isinstance(raw, dict) else [])
        for r in rows or []:
            if str(r.get("status") or "").lower() != "resolved":
                continue
            p = r.get("payouts") or r.get("payout") or r.get("payout_numerators")
            if isinstance(p, list) and len(p) >= 2:
                a, b = float(p[0]), float(p[1])
                if a > 1 or b > 1:
                    a, b = a / 1e6, b / 1e6
                return [a, b]
    except Exception:
        pass
    return None


def compute_after_fee_gap(winner, last_ask, last_bid, last_mid, fee_rate=0.07):
    """Calculate gap vs $1 for buying the winner: ask+fee if logged, else mid as mark only."""
    rate = fee_rate if isinstance(fee_rate, (int, float)) else 0.07
    if winner == "Up":
        if last_ask is not None:
            fee = P.fee_per_share(last_ask, rate)
            cost = last_ask + (fee if fee is not None else 0.0)
            return dict(winner=winner, cost=round(cost, 4), gap=round(1.0 - cost, 4),
                        basis="ask", executable=True)
        if last_mid is not None:
            fee = P.fee_per_share(last_mid, rate)
            cost = last_mid + (fee if fee is not None else 0.0)
            return dict(winner=winner, cost=round(cost, 4), gap=round(1.0 - cost, 4),
                        basis="mid not executable", executable=False)
    elif winner == "Down":
        # Down ask is approximated from YES bid when only YES quotes were logged
        down_ask = (1.0 - last_bid) if last_bid is not None else None
        if down_ask is not None:
            fee = P.fee_per_share(down_ask, rate)
            cost = down_ask + (fee if fee is not None else 0.0)
            return dict(winner=winner, cost=round(cost, 4), gap=round(1.0 - cost, 4),
                        basis="ask", executable=True)
        if last_mid is not None:
            down_mid = 1.0 - last_mid
            fee = P.fee_per_share(down_mid, rate)
            cost = down_mid + (fee if fee is not None else 0.0)
            return dict(winner=winner, cost=round(cost, 4), gap=round(1.0 - cost, 4),
                        basis="mid not executable", executable=False)
    return dict(winner=winner, cost=None, gap=None, basis="UNKNOWN", executable=False)


def evaluate_window(slug, twap_rows, event_data=None, res_payouts=None):
    """Evaluate one window record using twap_log rows and event/resolution metadata."""
    mids = [r["mid"] for r in twap_rows if r.get("mid") is not None]
    last_row = twap_rows[-1] if twap_rows else {}
    last_mid = last_row.get("mid")
    last_bid = last_row.get("bid")
    last_ask = last_row.get("ask")
    fee_rate_raw = last_row.get("fee_rate")
    fee_rate = 0.07 if (fee_rate_raw is None or isinstance(fee_rate_raw, str)) else fee_rate_raw
    end_s = last_row.get("end")
    cid = last_row.get("condition_id")

    # Gamma eventMetadata
    meta = (event_data or {}).get("eventMetadata") or {}
    price_to_beat = P._f(meta.get("priceToBeat")) if meta else None
    final_price = P._f(meta.get("finalPrice")) if meta else None

    # Implied winner
    implied = "UNKNOWN"
    if final_price is not None and price_to_beat is not None:
        if final_price > price_to_beat:
            implied = "Up"
        elif final_price < price_to_beat:
            implied = "Down"
        else:
            implied = "Tie"
    elif res_payouts and len(res_payouts) >= 2:
        if res_payouts[0] > res_payouts[1]:
            implied = "Up"
        elif res_payouts[1] > res_payouts[0]:
            implied = "Down"

    gap_info = compute_after_fee_gap(implied, last_ask, last_bid, last_mid, fee_rate)

    return dict(
        slug=slug,
        condition_id=cid,
        end=end_s,
        twap="UNKNOWN",  # public unauthenticated GET does not provide live PolyBolt stream
        twap_note="Chainlink live TWAP requires authenticated ws; Gamma publishes later",
        price_to_beat=price_to_beat,
        final_price=final_price,
        resolution_payouts=res_payouts,
        implied_outcome=implied,
        twap_log_samples=len(twap_rows),
        book_mids_last_band=[round(m, 4) for m in mids],
        last_mid=round(last_mid, 4) if last_mid is not None else None,
        last_bid=round(last_bid, 4) if last_bid is not None else None,
        last_ask=round(last_ask, 4) if last_ask is not None else None,
        fee_rate=fee_rate,
        after_fee_gap=gap_info["gap"],
        after_fee_cost=gap_info["cost"],
        after_fee_basis=gap_info["basis"],
        executable=gap_info["executable"],
    )


def settle_run(run_dir):
    """Process a finished run directory and write settle reports."""
    path = Path(run_dir)
    ledger_path = path / "ledger.jsonl"
    if not ledger_path.exists():
        raise FileNotFoundError(f"ledger not found: {ledger_path}")

    by_slug = defaultdict(list)
    with open(ledger_path) as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("type") == "twap_log" and row.get("slug"):
                by_slug[row["slug"]].append(row)

    windows = []
    for slug, rows in by_slug.items():
        ev = fetch_gamma_event(slug)
        cid = rows[-1].get("condition_id") if rows else None
        payouts = fetch_resolution_payouts(cid) if cid else None
        w = evaluate_window(slug, rows, event_data=ev, res_payouts=payouts)
        windows.append(w)

    out_json = path / "twap_settle.json"
    out_jsonl = path / "twap_settle.jsonl"
    out_json.write_text(json.dumps(windows, indent=2, default=str) + "\n")
    with open(out_jsonl, "w") as f:
        for w in windows:
            f.write(json.dumps(w, default=str) + "\n")

    summary = dict(run_dir=str(run_dir), windows_evaluated=len(windows),
                   resolved_count=sum(1 for w in windows if w["implied_outcome"] != "UNKNOWN"),
                   out_json=str(out_json), out_jsonl=str(out_jsonl))
    return summary


def main():
    a = argparse.ArgumentParser(description="TWAP settlement evaluator")
    a.add_argument("run_dir", nargs="?", default="", help="Path to run directory")
    a.add_argument("--run", default="", help="Path to run directory")
    x = a.parse_args()

    target = x.run or x.run_dir
    if not target:
        # default to most recent run
        runs = sorted(Path("predict_paper").glob("run-*"))
        if not runs:
            sys.exit("No run directory provided and none found in predict_paper/")
        target = str(runs[-1])

    res = settle_run(target)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
