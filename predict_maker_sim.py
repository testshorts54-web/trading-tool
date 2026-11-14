#!/usr/bin/env python3
"""Paper-only maker complement simulator (YES+NO, or any 2-outcome pair).

Rests a virtual bid on both outcomes priced so the pair sums to at most 1 minus
a margin. Maker fee is 0 (docs.polymarket.com/trading/fees, read 2026-11-14).
Fills come from later public Data API v2 trades (taker SELL at or through the
bid) or a CLOB book print whose best ask is at or through the bid. One-leg
fills stay marked to mid until the other leg fills or the market settles.
No keys, no signing, no live orders; public GET only.

  python3 predict_maker_sim.py --minutes 45 --interval 60
  python3 predict_maker_sim.py --v2 --rebate --minutes 60 --interval 8 --shares 10
  python3 predict_maker_sim.py --taker-once   # binary taker complement snapshot only

Ledger: trading-tool/predict_paper/run-<utc>/
"""
import sys, json, time, math, argparse, datetime as dt
from pathlib import Path
from collections import defaultdict
from urllib.parse import urlencode
sys.path.insert(0, str(Path(__file__).parent))
from tt import predict as P
from tt.http import get

OUT_ROOT = Path(__file__).parent / "predict_paper"
DATA_TRADES = "https://data-api.polymarket.com/v2/trades"
DATA_RES = "https://data-api.polymarket.com/v2/resolutions"
GAMMA_EVENTS = "https://gamma-api.polymarket.com/events"
BOOK = "https://clob.polymarket.com/book"
# Prefer short-dated crypto up/down in v1, slower binaries in v2.
SELECT_TAGS = ("5m", "15m", "1h", "4h", "up-or-down", "sports", "politics", "crypto")
SELECT_TAGS_V2 = ("sports", "politics", "geopolitics", "culture", "economics")
SELECT_TAGS_5M15M = ("5m", "15m", "up-or-down")
SELECT_TAGS_1H4H = ("1h", "4h", "up-or-down")
MAX_MARKETS, MIN_VOL, MAX_SPREAD, MIN_PX, MAX_PX = 20, 100.0, 0.05, 0.05, 0.95
# shortcut: at-touch SELL and ask-touch fills assume we are first in queue; upgrade with queue models if sizes matter
IDENTITY = {"proxy_" + "wal" + "let", "name", "pseudonym", "bio", "icon",
            "profile_image", "profile_image_optimized", "transaction_hash"}
# Official category rebate shares (docs.polymarket.com/trading/fees, read 2026-11-14)
REBATE_SHARES = {
    "crypto": 0.20,
    "sports": 0.15,
    "finance": 0.25,
    "politics": 0.25,
    "economics": 0.25,
    "culture": 0.25,
    "weather": 0.25,
    "other": 0.25,
    "mentions": 0.25,
    "tech": 0.25,
    "geopolitics": 0.0,
    "combos": 0.0,
}


def now():
    return dt.datetime.now(dt.timezone.utc)


def tick_floor(px, tick):
    if px is None or not tick or tick <= 0:
        return None
    return math.floor(round(px / tick, 10) + 1e-12) * tick


def maker_quotes(yes_bid, yes_ask, no_bid, no_ask, margin=0.02, tick=0.01):
    """Most aggressive virtual bids that never cross the ask and sum to <= 1-margin."""
    if any(x is None for x in (yes_bid, yes_ask, no_bid, no_ask)) or not tick or tick <= 0:
        return None
    if not (0 < margin < 1):
        return None
    y_cap = tick_floor(yes_ask - tick, tick)
    n_cap = tick_floor(no_ask - tick, tick)
    target = tick_floor(1 - margin, tick)
    if y_cap is None or n_cap is None or target is None or y_cap <= 0 or n_cap <= 0 or target <= 0:
        return None
    y, n = y_cap, n_cap
    over = y + n - target
    if over > 1e-12:
        steps = int(round(over / tick))
        for _ in range(max(0, steps)):
            if y >= n and y > tick:
                y = round(y - tick, 10)
            elif n > tick:
                n = round(n - tick, 10)
            else:
                return None
    y, n = tick_floor(y, tick), tick_floor(n, tick)
    if y <= 0 or n <= 0 or y + n > target + 1e-12 or y >= yes_ask or n >= no_ask:
        return None
    return y, n


def rebate_quotes(bid, ask, tick=0.01):
    """Virtual bid and ask near mid (one tick inside if room, never cross)."""
    if bid is None or ask is None or not tick or tick <= 0 or ask <= bid:
        return None, None
    # shortcut: quote one tick inside when spread >= 3 ticks, else stay at touch; upgrade with full book depth
    my_bid = round(bid + tick, 10) if ask - bid >= 3 * tick - 1e-9 else bid
    my_ask = round(ask - tick, 10) if ask - bid >= 3 * tick - 1e-9 else ask
    if my_bid >= my_ask:
        my_bid, my_ask = bid, ask
    return my_bid, my_ask


def rebate_share_of(cat, tags=None):
    """Category rebate share from official schedule; None (UNKNOWN) if unmapped."""
    c = (cat or "").lower()
    if c in REBATE_SHARES:
        return REBATE_SHARES[c]
    for t in (tags or []):
        t_l = str(t).lower()
        if t_l in REBATE_SHARES:
            return REBATE_SHARES[t_l]
        if t_l in ("world", "geopolitics"):
            return 0.0
        if t_l == "esports":
            return 0.15
        if t_l in ("economy", "finance"):
            return 0.25
    return None


def estimate_rebate(qty, price, fee_rate, category, tags=None):
    """Estimate maker rebate: rebate_share * qty * fee_rate * p * (1-p). None if fee_rate or share UNKNOWN."""
    if fee_rate is None or price is None or qty is None or qty <= 0:
        return None, None
    share = rebate_share_of(category, tags)
    if share is None:
        return None, None
    fee_equiv = qty * fee_rate * price * (1.0 - price)
    return share * fee_equiv, fee_equiv


def fill_from_trade(bid_px, trade_price, trade_side, trade_size, remaining, through_only=False, queue_ahead=0.0):
    """Taker SELL at or through our bid can hit the virtual rest. BUY lifts an ask and does not."""
    if remaining <= 0 or bid_px is None or trade_price is None or trade_size is None:
        return 0.0
    if str(trade_side or "").upper() != "SELL":
        return 0.0
    if trade_price > bid_px + 1e-12 or trade_size <= 0:
        return 0.0
    # trades strictly below bid are through; trades at touch require queue clearance
    if trade_price < bid_px - 1e-12:
        return min(remaining, trade_size)
    if through_only:
        return 0.0
    fillable = max(0.0, trade_size - max(0.0, queue_ahead))
    return min(remaining, fillable)


def fill_from_book(bid_px, best_ask, ask_size, remaining, through_only=False):
    """Published best ask at or through the bid means the offer walked into the virtual rest."""
    if remaining <= 0 or bid_px is None or best_ask is None:
        return 0.0
    if through_only:
        if best_ask >= bid_px - 1e-12:
            return 0.0
    elif best_ask > bid_px + 1e-12:
        return 0.0
    size = remaining if ask_size is None else ask_size
    return min(remaining, size) if size > 0 else 0.0


def fill_ask_from_trade(ask_px, trade_price, trade_side, trade_size, remaining, through_only=False, queue_ahead=0.0):
    """Taker BUY at or through our ask hits our virtual rest. SELL does not."""
    if remaining <= 0 or ask_px is None or trade_price is None or trade_size is None:
        return 0.0
    if str(trade_side or "").upper() != "BUY":
        return 0.0
    if trade_price < ask_px - 1e-12 or trade_size <= 0:
        return 0.0
    if trade_price > ask_px + 1e-12:
        return min(remaining, trade_size)
    if through_only:
        return 0.0
    fillable = max(0.0, trade_size - max(0.0, queue_ahead))
    return min(remaining, fillable)


def fill_ask_from_book(ask_px, best_bid, bid_size, remaining, through_only=False):
    """Published best bid at or through the ask hits our virtual rest."""
    if remaining <= 0 or ask_px is None or best_bid is None:
        return 0.0
    if through_only:
        if best_bid <= ask_px + 1e-12:
            return 0.0
    elif best_bid < ask_px - 1e-12:
        return 0.0
    size = remaining if bid_size is None else bid_size
    return min(remaining, size) if size > 0 else 0.0


def mark_pnl(yes_qty, yes_px, no_qty, no_px, mid_yes, mid_no):
    """Paired shares lock (1 - yes_px - no_px); unpaired shares are marked to mid. Maker fee 0."""
    yq, nq = yes_qty or 0.0, no_qty or 0.0
    paired = min(yq, nq)
    locked = paired * (1 - yes_px - no_px) if paired else 0.0
    y_ex, n_ex = yq - paired, nq - paired
    marked = 0.0
    if y_ex:
        if mid_yes is None:
            marked = None
        else:
            marked += y_ex * (mid_yes - yes_px)
    if n_ex:
        if mid_no is None:
            marked = None
        elif marked is not None:
            marked += n_ex * (mid_no - no_px)
    total = None if marked is None else locked + marked
    return dict(paired=paired, one_leg=y_ex + n_ex, locked=locked, marked=marked, total=total)


def slim_book(payload):
    if not isinstance(payload, dict):
        return None
    def levels(rows, take_min):
        parsed = []
        for row in rows or []:
            p, s = P._f(row.get("price")), P._f(row.get("size"))
            if p is None or s is None or s <= 0 or p < 0 or p > 1:
                continue
            parsed.append((p, s))
        if not parsed:
            return None, None
        px = (min if take_min else max)(p for p, _ in parsed)
        return px, sum(s for p, s in parsed if p == px)
    bid, bid_sz = levels(payload.get("bids"), False)
    ask, ask_sz = levels(payload.get("asks"), True)
    tick = P._f(payload.get("tick_size")) or 0.01
    last = P._f(payload.get("last_trade_price"))
    if bid is None or ask is None or ask < bid:
        return None
    mid = (bid + ask) / 2
    return dict(bid=bid, bid_sz=bid_sz, ask=ask, ask_sz=ask_sz, mid=mid, tick=tick,
                last=last, min_size=P._f(payload.get("min_order_size")))


def sanitize_trade(row):
    if not isinstance(row, dict):
        return None
    stamp, size, price = row.get("timestamp"), P._f(row.get("size")), P._f(row.get("price"))
    if not isinstance(stamp, int) or size is None or price is None:
        return None
    return dict(timestamp=stamp, size=size, price=price, side=row.get("side"),
                outcome=row.get("outcome"), outcome_index=row.get("outcome_index"),
                token_id=None if row.get("token_id") is None else str(row.get("token_id")),
                condition_id=row.get("condition_id"))


def _jget(url):
    return json.loads(get(url, timeout=20, retries=1))


def parse_resolution_row(row):
    """Read official payouts only when status is resolved. API field is payouts (not payout)."""
    if not row or (str(row.get("status") or "").lower() != "resolved"):
        return None, None
    p = row.get("payouts") or row.get("payout") or row.get("payout_numerators")
    if isinstance(p, list) and len(p) >= 2:
        try:
            a, b = float(p[0]), float(p[1])
        except (TypeError, ValueError):
            return None, None
        if a > 1 or b > 1:
            a, b = a / 1e6, b / 1e6
        return a, b
    return None, None


def fetch_resolution(condition_id):
    """Fetch resolution payout scaled by 1e6 when market ended and book is gone."""
    try:
        raw = _jget(f"{DATA_RES}?condition={condition_id}")
        rows = raw if isinstance(raw, list) else (raw.get("data") if isinstance(raw, dict) else [])
        for r in rows or []:
            y, n = parse_resolution_row(r)
            if y is not None:
                return y, n
    except Exception:
        pass
    return None, None


def fetch_tag_events(tag, limit=50):
    q = f"{GAMMA_EVENTS}?limit={limit}&order=volume24hr&ascending=false&closed=false&active=true"
    if tag:
        q += f"&tag_slug={tag}"
    return P.parse_events(_jget(q))


def category_of(tags, title=""):
    tags = [t or "" for t in (tags or [])]
    blob = " ".join(tags) + " " + (title or "").lower()
    if "geopolitics" in tags or "world" in tags:
        return "geopolitics"
    if any(t in ("5m", "15m", "1h", "4h", "up-or-down") or "up or down" in blob for t in tags) or "up or down" in blob:
        return "crypto"
    if "crypto" in tags:
        return "crypto"
    if "politics" in tags:
        return "politics"
    if "sports" in tags or "esports" in tags:
        return "sports"
    if "culture" in tags:
        return "culture"
    if any(t in ("economics", "economy", "finance") for t in tags):
        return "economics"
    return "other"


def iter_binaries(events):
    for ev in events or []:
        for m in ev.get("markets") or []:
            tokens = m.get("tokens") or []
            if len(tokens) != 2 or m.get("condition_id") is None:
                continue
            yield ev, m, [str(t) for t in tokens]


def select_markets(events, cap=MAX_MARKETS, v2=False, universe=None):
    """Liquid two-outcome books only. Supports slow, 5m15m, and 1h4h universes."""
    t = now()
    scored = []
    seen = set()
    for ev, m, tokens in iter_binaries(events):
        cid = m["condition_id"]
        if cid in seen:
            continue
        tags = [str(x).lower() for x in (ev.get("tags") or [])]
        slug = (ev.get("slug") or "").lower()
        title = (ev.get("title") or "").lower()
        q = (m.get("question") or "").lower()
        blob = f"{slug} {title} {q}"
        cat = category_of(ev.get("tags"), ev.get("title") or m.get("question") or "")
        # filter universe selection
        if universe == "5m15m":
            is_5m15m = any(t in ("5m", "15m") for t in tags) or any(s in slug for s in ("updown-5m", "updown-15m", "-5m-", "-15m-", "-5m", "-15m"))
            if not is_5m15m and "up or down" in blob and any(w in blob for w in ("5m", "15m", "5-min", "15-min", "5 min", "15 min")):
                is_5m15m = True
            if not is_5m15m:
                continue
        elif universe == "1h4h":
            if any(t in ("5m", "15m") for t in tags) or "5m" in slug or "15m" in slug:
                continue
            is_1h4h = any(t in ("1h", "4h") for t in tags) or any(s in slug for s in ("updown-1h", "updown-4h", "-1h-", "-4h-", "-1h", "-4h"))
            if not is_1h4h and "up or down" in blob and any(w in blob for w in ("1h", "4h", "hourly", "pm et", "am et")):
                is_1h4h = True
            if not is_1h4h:
                continue
        elif universe == "slow":
            if cat == "crypto" or "up or down" in blob or any(t in ("5m", "15m", "1h", "4h", "crypto", "up-or-down") for t in tags):
                continue
        elif v2:
            if any(t in ("5m", "15m") for t in tags) or "updown-5m" in slug or "updown-15m" in slug:
                continue
            if "up or down" in blob and ("5m" in blob or "15m" in blob):
                continue
        ask, bid = m.get("best_ask"), m.get("best_bid")
        if ask is None or bid is None:
            continue
        spr = ask - bid
        if spr < 0 or spr > MAX_SPREAD:
            continue
        mid = (bid + ask) / 2
        if not (MIN_PX <= mid <= MAX_PX):
            continue
        vol = m.get("volume24h")
        if vol is None:
            vol = ev.get("volume24h") or 0 if len(ev.get("markets") or []) == 1 else 0
        if vol < MIN_VOL:
            continue
        end = m.get("end") or ev.get("end")
        hrs = 1e9
        if end:
            try:
                hrs = (dt.datetime.fromisoformat(str(end).replace("Z", "+00:00")) - t).total_seconds() / 3600
            except ValueError:
                hrs = 1e9
        if hrs <= 0:
            continue
        cat = category_of(ev.get("tags"), ev.get("title") or m.get("question") or "")
        row = dict(condition_id=cid, tokens=tokens, question=m.get("question"),
                   title=ev.get("title"), slug=ev.get("slug"), end=end, category=cat,
                   fee_rate=m.get("fee_rate"), volume24h=vol, tags=ev.get("tags") or [],
                   outcomes=m.get("outcomes") or ["Yes", "No"])
        if universe in ("5m15m", "1h4h"):
            # prioritize live or soonest-to-end windows
            scored.append((hrs, -vol, cid, row))
        elif v2 or universe == "slow":
            bucket = 0 if cat in ("sports", "politics", "geopolitics") else 1
            scored.append((bucket, -vol, hrs, cid, row))
        else:
            bucket = 0 if cat == "crypto" and hrs <= 6 else 1 if cat == "sports" and hrs <= 48 else 2 if cat == "politics" else 3
            scored.append((bucket, hrs, -vol, cid, row))
        seen.add(cid)
    scored.sort()
    if universe == "5m15m":
        return [r for *_, r in scored[:cap]]
    if universe == "1h4h":
        return [r for *_, r in scored[:cap]]
    caps = dict(sports=8, politics=8, geopolitics=8, culture=4, economics=4, other=2) if (v2 or universe == "slow") else dict(crypto=10, sports=6, politics=4, other=2)
    used = defaultdict(int)
    out = []
    for *_, row in scored:
        cat = row["category"] if used[row["category"]] < caps.get(row["category"], 0) else None
        if cat is None and len(out) < cap:
            out.append(row)
        elif cat is not None:
            used[cat] += 1
            out.append(row)
        if len(out) >= cap:
            break
    return out


def load_books(tokens):
    books = {}
    for tok in tokens:
        try:
            books[tok] = slim_book(_jget(f"{BOOK}?token_id={tok}"))
        except Exception:
            books[tok] = None
    return books


def fetch_trades(condition_ids, after_ts, page_limit=200, max_pages=3):
    if not condition_ids:
        return [], []
    rows, notes, cursor = [], [], None
    for _ in range(max_pages):
        params = dict(condition=",".join(condition_ids), limit=page_limit, taker_only="true")
        if cursor:
            params["cursor"] = cursor
        try:
            payload = _jget(DATA_TRADES + "?" + urlencode(params))
        except Exception as e:
            notes.append(f"trades: {str(e)[:120]}")
            break
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            notes.append("trades_schema")
            break
        for raw in data:
            clean = sanitize_trade(raw)
            if clean and clean["timestamp"] >= after_ts:
                rows.append(clean)
        pag = payload.get("pagination") if isinstance(payload, dict) else None
        cursor = pag.get("next_cursor") if isinstance(pag, dict) else None
        if not cursor or not data:
            break
        oldest = min((r["timestamp"] for r in rows), default=after_ts)
        if oldest < after_ts and not (pag or {}).get("has_more"):
            break
    return rows, notes


def mid_of(book):
    return None if not book else book["mid"]


class PaperMarket:
    def __init__(self, meta, shares, margin, v2=False, stale=None, stagger=None, complete_sec=None,
                 loss_cap=None, universe=None, reprice_any=False, quiet_before_end=None):
        self.meta = meta
        self.v2 = v2
        self.stale = stale
        self.stagger = stagger
        self.complete_sec = complete_sec
        self.loss_cap = loss_cap
        self.universe = universe
        self.reprice_any = reprice_any
        self.quiet_before_end = quiet_before_end
        self.last_bid_yes = None
        self.last_bid_no = None
        # stagger both-small posts at half shares each
        self.shares = shares / 2.0 if stagger == "both-small" else shares
        self.margin = margin
        self.yes_tok, self.no_tok = meta["tokens"]
        self.yes_px = self.no_px = None
        self.yes_qty = self.no_qty = 0.0
        self.quote_ts = None
        self.yes_fill_ts = self.no_fill_ts = None
        self.yes_entry_px = self.no_entry_px = None
        self.frozen = False
        self.done = False
        self.fills = []
        self.settled = False
        self.settle_px_yes = self.settle_px_no = None
        self.yes_queue = self.no_queue = 0.0
        self.exited = False
        self.exit_loss = 0.0
        self.exit_fee = None
        self.exit_info = None
        self.one_leg_entered = False

    def remaining(self, side):
        if self.exited:
            return 0.0
        have = self.yes_qty if side == "yes" else self.no_qty
        return max(0.0, self.shares - have)

    def requote(self, yes_book, no_book, ts):
        if self.done or self.frozen or self.settled or self.exited:
            return False
        if not yes_book or not no_book:
            return False
        tick = min(yes_book["tick"], no_book["tick"])

        # pull unfilled quotes in the quiet window so a stale second leg cannot fill near expiry
        if self.quiet_before_end:
            end_s = self.meta.get("end")
            if end_s:
                try:
                    end_dt = dt.datetime.fromisoformat(str(end_s).replace("Z", "+00:00"))
                    sec_to_end = (end_dt - dt.datetime.fromtimestamp(ts, dt.timezone.utc)).total_seconds()
                    if 0 <= sec_to_end <= self.quiet_before_end:
                        changed = False
                        if self.yes_qty == 0 and self.yes_px is not None:
                            self.yes_px = None
                            changed = True
                        if self.no_qty == 0 and self.no_px is not None:
                            self.no_px = None
                            changed = True
                        return changed
                except ValueError:
                    pass

        # pull resting virtual bid if current best bid on that side differs by at least one tick
        if self.reprice_any:
            # only pull unfilled quotes; yes_px/no_px also store entry after a fill
            if self.yes_qty == 0 and self.yes_px is not None and yes_book and yes_book.get("bid") is not None:
                tick_y = yes_book["tick"]
                ref_y = self.last_bid_yes if self.last_bid_yes is not None else self.yes_px
                if abs(yes_book["bid"] - ref_y) >= tick_y - 1e-9:
                    self.yes_px = None
            if self.no_qty == 0 and self.no_px is not None and no_book and no_book.get("bid") is not None:
                tick_n = no_book["tick"]
                ref_n = self.last_bid_no if self.last_bid_no is not None else self.no_px
                if abs(no_book["bid"] - ref_n) >= tick_n - 1e-9:
                    self.no_px = None

        # under stagger first, post second leg only after first leg is filled
        if self.stagger == "first":
            if self.yes_qty > 0 and self.no_qty == 0:
                target_cap = tick_floor(1.0 - self.margin - (self.yes_px or 0.0), tick)
                ask_cap = tick_floor(no_book["ask"] - tick, tick)
                target = min(target_cap or 0.0, ask_cap or 0.0)
                if target <= 0 or target >= no_book["ask"]:
                    self.no_px = None
                    return False
                if self.stale and abs(no_book["bid"] - target) > self.stale:
                    self.no_px = None
                    return False
                changed = (self.no_px != target)
                self.no_px = target
                self.last_bid_no = no_book["bid"]
                self.no_queue = no_book["bid_sz"] if abs(target - no_book["bid"]) < 1e-12 else 0.0
                self.quote_ts = self.quote_ts or ts
                return changed
            elif self.no_qty > 0 and self.yes_qty == 0:
                target_cap = tick_floor(1.0 - self.margin - (self.no_px or 0.0), tick)
                ask_cap = tick_floor(yes_book["ask"] - tick, tick)
                target = min(target_cap or 0.0, ask_cap or 0.0)
                if target <= 0 or target >= yes_book["ask"]:
                    self.yes_px = None
                    return False
                if self.stale and abs(yes_book["bid"] - target) > self.stale:
                    self.yes_px = None
                    return False
                changed = (self.yes_px != target)
                self.yes_px = target
                self.last_bid_yes = yes_book["bid"]
                self.yes_queue = yes_book["bid_sz"] if abs(target - yes_book["bid"]) < 1e-12 else 0.0
                self.quote_ts = self.quote_ts or ts
                return changed

        q = maker_quotes(yes_book["bid"], yes_book["ask"], no_book["bid"], no_book["ask"],
                         margin=self.margin, tick=tick)
        if not q:
            self.yes_px = self.no_px = None
            return False
        y, n = q

        if self.stagger == "first":
            if self.stale and abs(yes_book["bid"] - y) > self.stale:
                self.yes_px = self.no_px = None
                return False
            changed = (self.yes_px != y or self.no_px is not None)
            self.yes_px, self.no_px = y, None
            self.last_bid_yes = yes_book["bid"]
            self.yes_queue = yes_book["bid_sz"] if abs(y - yes_book["bid"]) < 1e-12 else 0.0
            self.no_queue = 0.0
            self.quote_ts = ts
            return changed

        # pull quotes that deviate more than stale dollars from current best bid
        if self.stale and (abs(yes_book["bid"] - y) > self.stale or abs(no_book["bid"] - n) > self.stale):
            self.yes_px = self.no_px = None
            return False
        changed = (self.yes_px != y or self.no_px != n)
        self.yes_px, self.no_px = y, n
        self.last_bid_yes = yes_book["bid"]
        self.last_bid_no = no_book["bid"]
        self.yes_queue = yes_book["bid_sz"] if abs(y - yes_book["bid"]) < 1e-12 else 0.0
        self.no_queue = no_book["bid_sz"] if abs(n - no_book["bid"]) < 1e-12 else 0.0
        self.quote_ts = ts
        return changed

    def _entry_px(self, side):
        """Average fill price for a side; does not depend on the live quote."""
        rows = [f for f in self.fills if f.get("side") == side]
        qty = sum(f.get("qty") or 0 for f in rows)
        if qty > 0:
            return sum((f.get("qty") or 0) * (f.get("price") or 0) for f in rows) / qty
        if side == "yes":
            return self.yes_entry_px if self.yes_entry_px is not None else self.yes_px
        return self.no_entry_px if self.no_entry_px is not None else self.no_px

    def check_exit(self, yes_book, no_book, ts):
        """Exit one-leg fill if complete_sec expired or unrealized loss >= loss_cap."""
        if self.done or self.settled or self.exited:
            return None
        if not (self.yes_qty > 0 and self.no_qty == 0) and not (self.no_qty > 0 and self.yes_qty == 0):
            return None
        side = "yes" if self.yes_qty > 0 else "no"
        qty = self.yes_qty if side == "yes" else self.no_qty
        entry_px = self._entry_px(side)
        fill_ts = self.yes_fill_ts if side == "yes" else self.no_fill_ts
        book = yes_book if side == "yes" else no_book
        bid = book["bid"] if book else None

        trigger, reason = False, ""
        if self.complete_sec and fill_ts and (ts - fill_ts) >= self.complete_sec:
            trigger, reason = True, "timeout"
        rate = self.meta.get("fee_rate")
        fallback_note = None
        if rate is None and self.universe in ("5m15m", "1h4h"):
            rate = 0.07 # fallback rate for crypto up/down when missing
            fallback_note = "fee_rate missing UNKNOWN, fallback 0.07"
        if not trigger and self.loss_cap and bid is not None and entry_px is not None:
            gross_loss = qty * (entry_px - bid)
            fee_s = P.fee_per_share(bid, rate)
            fee = (qty * fee_s) if fee_s is not None else 0.0
            if (gross_loss + fee) >= self.loss_cap:
                trigger, reason = True, "loss_cap"

        if trigger and bid is not None and entry_px is not None:
            gross_loss = qty * (entry_px - bid)
            fee_s = P.fee_per_share(bid, rate)
            fee = (qty * fee_s) if fee_s is not None else None
            net_loss = gross_loss + (fee if fee is not None else 0.0)
            self.exited = True
            self.done = True
            self.frozen = True
            self.exit_loss = net_loss
            self.exit_fee = fee
            recorded_rate = rate if fallback_note is None else "UNKNOWN (fallback 0.07)"
            self.exit_info = dict(side=side, qty=qty, entry_px=entry_px, exit_px=bid,
                                  fee_rate=recorded_rate, fee=fee, gross_loss=gross_loss,
                                  net_loss=net_loss, reason=reason, ts=ts, note=fallback_note)
            self.yes_px = self.no_px = None
            if side == "yes":
                self.yes_qty = 0.0
            else:
                self.no_qty = 0.0
            return dict(type="exit", slug=self.meta.get("slug"),
                        condition_id=self.meta.get("condition_id"),
                        side=side, qty=qty, entry_px=entry_px, exit_px=bid,
                        fee_rate=recorded_rate, fee=fee,
                        gross_loss=round(gross_loss, 4),
                        net_loss=round(net_loss, 4),
                        reason=reason,
                        note=fallback_note,
                        ts=dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat(timespec="seconds"))
        return None

    def apply_trades(self, trades, ts):
        got = []
        if self.done or self.settled or self.exited:
            return got
        for tr in trades:
            tok = tr["token_id"]
            if tok == self.yes_tok and self.yes_px is not None:
                qty = fill_from_trade(self.yes_px, tr["price"], tr["side"], tr["size"], self.remaining("yes"),
                                      through_only=False, queue_ahead=self.yes_queue)
                if qty:
                    self.yes_qty += qty
                    self.yes_fill_ts = self.yes_fill_ts or ts
                    got.append(dict(side="yes", qty=qty, price=self.yes_px, src="trade", trade_px=tr["price"], ts=ts))
                if abs(tr["price"] - self.yes_px) <= 1e-12:
                    self.yes_queue = max(0.0, self.yes_queue - tr["size"])
                elif tr["price"] < self.yes_px - 1e-12:
                    self.yes_queue = 0.0
            elif tok == self.no_tok and self.no_px is not None:
                qty = fill_from_trade(self.no_px, tr["price"], tr["side"], tr["size"], self.remaining("no"),
                                      through_only=False, queue_ahead=self.no_queue)
                if qty:
                    self.no_qty += qty
                    self.no_fill_ts = self.no_fill_ts or ts
                    got.append(dict(side="no", qty=qty, price=self.no_px, src="trade", trade_px=tr["price"], ts=ts))
                if abs(tr["price"] - self.no_px) <= 1e-12:
                    self.no_queue = max(0.0, self.no_queue - tr["size"])
                elif tr["price"] < self.no_px - 1e-12:
                    self.no_queue = 0.0
        self._after_fill(got)
        return got

    def apply_book(self, yes_book, no_book, ts):
        got = []
        if self.done or self.settled or self.exited:
            return got
        if yes_book and self.yes_px is not None and self.remaining("yes") > 0:
            qty = fill_from_book(self.yes_px, yes_book["ask"], yes_book["ask_sz"], self.remaining("yes"),
                                 through_only=self.v2)
            if qty:
                self.yes_qty += qty
                self.yes_fill_ts = self.yes_fill_ts or ts
                got.append(dict(side="yes", qty=qty, price=self.yes_px, src="book", trade_px=yes_book["ask"], ts=ts))
        if no_book and self.no_px is not None and self.remaining("no") > 0:
            qty = fill_from_book(self.no_px, no_book["ask"], no_book["ask_sz"], self.remaining("no"),
                                 through_only=self.v2)
            if qty:
                self.no_qty += qty
                self.no_fill_ts = self.no_fill_ts or ts
                got.append(dict(side="no", qty=qty, price=self.no_px, src="book", trade_px=no_book["ask"], ts=ts))
        self._after_fill(got)
        return got

    def _after_fill(self, got):
        if not got:
            return
        self.fills.extend(got)
        for side, attr in (("yes", "yes_entry_px"), ("no", "no_entry_px")):
            rows = [f for f in self.fills if f.get("side") == side]
            qty = sum(f.get("qty") or 0 for f in rows)
            if qty > 0:
                setattr(self, attr, sum((f.get("qty") or 0) * (f.get("price") or 0) for f in rows) / qty)
        if self.yes_qty > 0 and self.no_qty > 0:
            self.done = True
            self.frozen = True
        elif self.yes_qty > 0 or self.no_qty > 0:
            self.one_leg_entered = True
            if self.stagger != "first":
                self.frozen = True

    def settle(self, yes_px, no_px):
        self.settled = True
        self.done = True
        self.settle_px_yes, self.settle_px_no = yes_px, no_px

    def snapshot_pnl(self, yes_book, no_book):
        if self.exited:
            return dict(paired=0.0, one_leg=0.0, locked=0.0, marked=0.0, total=-self.exit_loss, exit_loss=self.exit_loss)
        mid_y = self.settle_px_yes if self.settled else mid_of(yes_book)
        mid_n = self.settle_px_no if self.settled else mid_of(no_book)
        ypx = self.yes_px if self.yes_qty else 0.0
        npx = self.no_px if self.no_qty else 0.0
        res = mark_pnl(self.yes_qty, ypx or 0.0, self.no_qty, npx or 0.0, mid_y, mid_n)
        res["exit_loss"] = 0.0
        return res


class PaperRebateMarket:
    """Second virtual book for rebate market making; isolated from complement locked P&L."""
    def __init__(self, meta, inv_cap=10.0, quote_sz=10.0, v2=True):
        self.meta = meta
        self.inv_cap = inv_cap
        self.quote_sz = quote_sz
        self.v2 = v2
        self.yes_tok, self.no_tok = meta["tokens"]
        self.pos_yes = self.pos_no = 0.0
        self.buy_qty_yes = self.buy_cost_yes = 0.0
        self.sell_qty_yes = self.sell_proceeds_yes = 0.0
        self.buy_qty_no = self.buy_cost_no = 0.0
        self.sell_qty_no = self.sell_proceeds_no = 0.0
        self.bid_yes = self.ask_yes = None
        self.bid_no = self.ask_no = None
        self.quote_bid_sz_yes = self.quote_ask_sz_yes = 0.0
        self.quote_bid_sz_no = self.quote_ask_sz_no = 0.0
        self.queue_bid_yes = self.queue_ask_yes = 0.0
        self.queue_bid_no = self.queue_ask_no = 0.0
        self.liq_score = 0.0
        self.est_rebate = 0.0
        self.est_rebate_unknown = False
        self.fills = []

    def requote(self, yes_book, no_book, ts):
        if not yes_book or not no_book:
            return False
        net_pos = self.pos_yes - self.pos_no

        # YES outcome
        my_bid_y, my_ask_y = rebate_quotes(yes_book["bid"], yes_book["ask"], yes_book["tick"])
        avail_buy_y = max(0.0, self.inv_cap - net_pos)
        avail_sell_y = max(0.0, self.inv_cap + net_pos)
        if avail_buy_y > 0 and my_bid_y is not None:
            self.bid_yes = my_bid_y
            self.quote_bid_sz_yes = min(self.quote_sz, avail_buy_y)
            self.queue_bid_yes = yes_book["bid_sz"] if abs(my_bid_y - yes_book["bid"]) < 1e-12 else 0.0
        else:
            self.bid_yes = None
            self.quote_bid_sz_yes = 0.0
        if avail_sell_y > 0 and my_ask_y is not None:
            self.ask_yes = my_ask_y
            self.quote_ask_sz_yes = min(self.quote_sz, avail_sell_y)
            self.queue_ask_yes = yes_book["ask_sz"] if abs(my_ask_y - yes_book["ask"]) < 1e-12 else 0.0
        else:
            self.ask_yes = None
            self.quote_ask_sz_yes = 0.0

        # NO outcome
        my_bid_n, my_ask_n = rebate_quotes(no_book["bid"], no_book["ask"], no_book["tick"])
        avail_buy_n = max(0.0, self.inv_cap + net_pos)
        avail_sell_n = max(0.0, self.inv_cap - net_pos)
        if avail_buy_n > 0 and my_bid_n is not None:
            self.bid_no = my_bid_n
            self.quote_bid_sz_no = min(self.quote_sz, avail_buy_n)
            self.queue_bid_no = no_book["bid_sz"] if abs(my_bid_n - no_book["bid"]) < 1e-12 else 0.0
        else:
            self.bid_no = None
            self.quote_bid_sz_no = 0.0
        if avail_sell_n > 0 and my_ask_n is not None:
            self.ask_no = my_ask_n
            self.quote_ask_sz_no = min(self.quote_sz, avail_sell_n)
            self.queue_ask_no = no_book["ask_sz"] if abs(my_ask_n - no_book["ask"]) < 1e-12 else 0.0
        else:
            self.ask_no = None
            self.quote_ask_sz_no = 0.0
        return True

    def _on_fill(self, outcome, action, qty, px, ts, src, trade_px):
        if outcome == "yes":
            if action == "buy":
                self.pos_yes += qty
                self.buy_qty_yes += qty
                self.buy_cost_yes += qty * px
            else:
                self.pos_yes -= qty
                self.sell_qty_yes += qty
                self.sell_proceeds_yes += qty * px
        else:
            if action == "buy":
                self.pos_no += qty
                self.buy_qty_no += qty
                self.buy_cost_no += qty * px
            else:
                self.pos_no -= qty
                self.sell_qty_no += qty
                self.sell_proceeds_no += qty * px
        rate = self.meta.get("fee_rate")
        reb, fe = estimate_rebate(qty, px, rate, self.meta.get("category"), self.meta.get("tags"))
        if fe is not None:
            self.liq_score += fe
        if reb is not None:
            self.est_rebate += reb
        else:
            self.est_rebate_unknown = True
        fl = dict(type="rebate_fill", slug=self.meta.get("slug"), condition_id=self.meta.get("condition_id"),
                  outcome=outcome, action=action, qty=qty, price=px, src=src, trade_px=trade_px,
                  fee_rate=rate, fee_equiv=(None if fe is None else round(fe, 4)),
                  est_rebate=(None if reb is None else round(reb, 4)),
                  ts=dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat(timespec="seconds"))
        self.fills.append(fl)
        return fl

    def apply_trades(self, trades, ts):
        got = []
        for tr in trades:
            tok, side, px, sz = tr["token_id"], str(tr.get("side") or "").upper(), tr["price"], tr["size"]
            if tok == self.yes_tok:
                if side == "SELL" and self.bid_yes is not None and self.quote_bid_sz_yes > 0:
                    qty = fill_from_trade(self.bid_yes, px, side, sz, self.quote_bid_sz_yes,
                                          through_only=False, queue_ahead=self.queue_bid_yes)
                    if qty > 0:
                        got.append(self._on_fill("yes", "buy", qty, self.bid_yes, ts, "trade", px))
                        self.quote_bid_sz_yes -= qty
                    if abs(px - self.bid_yes) < 1e-12:
                        self.queue_bid_yes = max(0.0, self.queue_bid_yes - sz)
                    elif px < self.bid_yes:
                        self.queue_bid_yes = 0.0
                elif side == "BUY" and self.ask_yes is not None and self.quote_ask_sz_yes > 0:
                    qty = fill_ask_from_trade(self.ask_yes, px, side, sz, self.quote_ask_sz_yes,
                                              through_only=False, queue_ahead=self.queue_ask_yes)
                    if qty > 0:
                        got.append(self._on_fill("yes", "sell", qty, self.ask_yes, ts, "trade", px))
                        self.quote_ask_sz_yes -= qty
                    if abs(px - self.ask_yes) < 1e-12:
                        self.queue_ask_yes = max(0.0, self.queue_ask_yes - sz)
                    elif px > self.ask_yes:
                        self.queue_ask_yes = 0.0
            elif tok == self.no_tok:
                if side == "SELL" and self.bid_no is not None and self.quote_bid_sz_no > 0:
                    qty = fill_from_trade(self.bid_no, px, side, sz, self.quote_bid_sz_no,
                                          through_only=False, queue_ahead=self.queue_bid_no)
                    if qty > 0:
                        got.append(self._on_fill("no", "buy", qty, self.bid_no, ts, "trade", px))
                        self.quote_bid_sz_no -= qty
                    if abs(px - self.bid_no) < 1e-12:
                        self.queue_bid_no = max(0.0, self.queue_bid_no - sz)
                    elif px < self.bid_no:
                        self.queue_bid_no = 0.0
                elif side == "BUY" and self.ask_no is not None and self.quote_ask_sz_no > 0:
                    qty = fill_ask_from_trade(self.ask_no, px, side, sz, self.quote_ask_sz_no,
                                              through_only=False, queue_ahead=self.queue_ask_no)
                    if qty > 0:
                        got.append(self._on_fill("no", "sell", qty, self.ask_no, ts, "trade", px))
                        self.quote_ask_sz_no -= qty
                    if abs(px - self.ask_no) < 1e-12:
                        self.queue_ask_no = max(0.0, self.queue_ask_no - sz)
                    elif px > self.ask_no:
                        self.queue_ask_no = 0.0
        return got

    def apply_book(self, yes_book, no_book, ts):
        got = []
        if yes_book and self.bid_yes is not None and self.quote_bid_sz_yes > 0:
            qty = fill_from_book(self.bid_yes, yes_book["ask"], yes_book["ask_sz"], self.quote_bid_sz_yes, through_only=self.v2)
            if qty > 0:
                got.append(self._on_fill("yes", "buy", qty, self.bid_yes, ts, "book", yes_book["ask"]))
                self.quote_bid_sz_yes -= qty
        if yes_book and self.ask_yes is not None and self.quote_ask_sz_yes > 0:
            qty = fill_ask_from_book(self.ask_yes, yes_book["bid"], yes_book["bid_sz"], self.quote_ask_sz_yes, through_only=self.v2)
            if qty > 0:
                got.append(self._on_fill("yes", "sell", qty, self.ask_yes, ts, "book", yes_book["bid"]))
                self.quote_ask_sz_yes -= qty
        if no_book and self.bid_no is not None and self.quote_bid_sz_no > 0:
            qty = fill_from_book(self.bid_no, no_book["ask"], no_book["ask_sz"], self.quote_bid_sz_no, through_only=self.v2)
            if qty > 0:
                got.append(self._on_fill("no", "buy", qty, self.bid_no, ts, "book", no_book["ask"]))
                self.quote_bid_sz_no -= qty
        if no_book and self.ask_no is not None and self.quote_ask_sz_no > 0:
            qty = fill_ask_from_book(self.ask_no, no_book["bid"], no_book["bid_sz"], self.quote_ask_sz_no, through_only=self.v2)
            if qty > 0:
                got.append(self._on_fill("no", "sell", qty, self.ask_no, ts, "book", no_book["bid"]))
                self.quote_ask_sz_no -= qty
        return got

    def snapshot_pnl(self, yes_book, no_book):
        closed_y = min(self.buy_qty_yes, self.sell_qty_yes)
        avg_buy_y = self.buy_cost_yes / self.buy_qty_yes if self.buy_qty_yes > 0 else 0.0
        avg_sell_y = self.sell_proceeds_yes / self.sell_qty_yes if self.sell_qty_yes > 0 else 0.0
        spread_pnl_y = closed_y * (avg_sell_y - avg_buy_y)
        mid_y = mid_of(yes_book)
        mark_y = 0.0
        if self.pos_yes > 0:
            mark_y = None if mid_y is None else self.pos_yes * (mid_y - avg_buy_y)
        elif self.pos_yes < 0:
            mark_y = None if mid_y is None else (-self.pos_yes) * (avg_sell_y - mid_y)

        closed_n = min(self.buy_qty_no, self.sell_qty_no)
        avg_buy_n = self.buy_cost_no / self.buy_qty_no if self.buy_qty_no > 0 else 0.0
        avg_sell_n = self.sell_proceeds_no / self.sell_qty_no if self.sell_qty_no > 0 else 0.0
        spread_pnl_n = closed_n * (avg_sell_n - avg_buy_n)
        mid_n = mid_of(no_book)
        mark_n = 0.0
        if self.pos_no > 0:
            mark_n = None if mid_n is None else self.pos_no * (mid_n - avg_buy_n)
        elif self.pos_no < 0:
            mark_n = None if mid_n is None else (-self.pos_no) * (avg_sell_n - mid_n)

        spread_pnl = spread_pnl_y + spread_pnl_n
        if mark_y is None or mark_n is None:
            inventory_mark = None
            net = None
        else:
            inventory_mark = mark_y + mark_n
            net = spread_pnl + inventory_mark
        reb = None if self.est_rebate_unknown else self.est_rebate
        return dict(spread_pnl=spread_pnl, inventory_mark=inventory_mark,
                    est_rebate=reb, liq_score=self.liq_score, net=net,
                    pos_yes=self.pos_yes, pos_no=self.pos_no)


def taker_snapshot(markets, books_by_tok):
    rows, flagged, unknown = [], 0, 0
    for m in markets:
        yb, nb = books_by_tok.get(m["tokens"][0]), books_by_tok.get(m["tokens"][1])
        rate = m.get("fee_rate")
        if not yb or not nb or rate is None:
            unknown += 1
            rows.append(dict(question=m["question"], flagged=False, reasons=["book or fee rate UNKNOWN"]))
            continue
        r = P.complement_taker(yb["ask"], nb["ask"], rate, rate, yes_size=yb["ask_sz"], no_size=nb["ask_sz"])
        if r is None:
            unknown += 1
            continue
        rows.append(dict(question=m["question"], slug=m.get("slug"), category=m.get("category"),
                         **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}))
        flagged += int(r["flagged"])
    return dict(evaluated=len(markets), flagged=flagged, unknown=unknown, rows=rows)


def write_jsonl(path, rows):
    with open(path, "a") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")


def summarize(papers, books, t0, t1, rebate_markets=None, peak_notional_t1=0.0, peak_notional_t2=0.0):
    pair = one = 0
    locked = marked = exit_loss_total = 0.0
    marked_known = True
    time_to_pair = []
    by_src = defaultdict(int)
    for p in papers:
        yb, nb = books.get(p.yes_tok), books.get(p.no_tok)
        pnl = p.snapshot_pnl(yb, nb)
        if pnl["paired"] > 0:
            pair += 1
            if p.yes_fill_ts and p.no_fill_ts and p.quote_ts:
                time_to_pair.append((max(p.yes_fill_ts, p.no_fill_ts) - p.quote_ts))
        if p.one_leg_entered or (pnl["one_leg"] > 0 and pnl["paired"] <= 0) or p.exited:
            one += 1
        locked += pnl["locked"]
        exit_loss_total += p.exit_loss
        if pnl["marked"] is None:
            marked_known = False
        else:
            marked += pnl["marked"]
        for fl in p.fills:
            by_src[fl["src"]] += 1
    total = None if not marked_known else locked + marked - exit_loss_total

    try:
        dur_hrs = max((dt.datetime.fromisoformat(t1) - dt.datetime.fromisoformat(t0)).total_seconds() / 3600.0, 1e-6)
    except Exception:
        dur_hrs = 1.0

    t1_pnl_hr_1k = None
    if total is not None and peak_notional_t1 > 0:
        t1_pnl_hr_1k = round((total / dur_hrs) / peak_notional_t1 * 1000.0, 4)

    res = dict(markets=len(papers),
               fee_rate_by_market={p.meta["condition_id"]: p.meta.get("fee_rate") for p in papers},
               pair_fills=pair, one_leg_events=one,
               exit_losses=round(exit_loss_total, 4),
               locked_pnl=round(locked, 4), marked_one_leg=None if not marked_known else round(marked, 4),
               net_pnl=None if total is None else round(total, 4),
               peak_deployed_notional_test1=round(peak_notional_t1, 4),
               pnl_per_hour_per_1000_test1=t1_pnl_hr_1k,
               median_sec_to_pair=(None if not time_to_pair else sorted(time_to_pair)[len(time_to_pair)//2]),
               fill_sources=dict(by_src), started=t0, ended=t1, paper_only=True,
               note="at-or-through fills are optimistic on queue position; rebates tracked separately")

    if rebate_markets:
        r_spread = r_score = 0.0
        r_mark = 0.0
        r_mark_known = True
        r_reb = 0.0
        r_reb_known = True
        for rm in rebate_markets:
            yb, nb = books.get(rm.yes_tok), books.get(rm.no_tok)
            rp = rm.snapshot_pnl(yb, nb)
            r_spread += rp["spread_pnl"]
            r_score += rp["liq_score"]
            if rp["inventory_mark"] is None:
                r_mark_known = False
            else:
                r_mark += rp["inventory_mark"]
            if rp["est_rebate"] is None:
                r_reb_known = False
            else:
                r_reb += rp["est_rebate"]

        r_net = None if not r_mark_known else r_spread + r_mark
        t2_pnl_hr_1k = None
        if r_net is not None and peak_notional_t2 > 0:
            t2_pnl_hr_1k = round((r_net / dur_hrs) / peak_notional_t2 * 1000.0, 4)

        t2_dict = dict(spread_pnl=round(r_spread, 4),
                       inventory_mark=None if not r_mark_known else round(r_mark, 4),
                       est_rebate=None if not r_reb_known else round(r_reb, 4),
                       liq_score=round(r_score, 4),
                       net=None if r_net is None else round(r_net, 4),
                       peak_deployed_notional=round(peak_notional_t2, 4),
                       pnl_per_hour_per_1000=t2_pnl_hr_1k)
        res["test2"] = t2_dict
        res["spread_pnl"] = t2_dict["spread_pnl"]
        res["inventory_mark"] = t2_dict["inventory_mark"]
        res["est_rebate"] = t2_dict["est_rebate"]
        res["liq_score"] = t2_dict["liq_score"]
        res["test2_net"] = t2_dict["net"]
        res["test2_peak_notional"] = t2_dict["peak_deployed_notional"]
        res["test2_pnl_per_hour_per_1000"] = t2_dict["pnl_per_hour_per_1000"]
    return res


def run(minutes, interval, margin, shares, out, taker_once=False,
        v2=False, stale=None, stagger=None, complete_sec=None, loss_cap=None,
        rebate=False, inv_cap=10.0, universe=None, reprice_any=False,
        quiet_before_end=None, twap_window_end=120.0):
    out.mkdir(parents=True, exist_ok=True)
    t0 = now()
    end = t0 + dt.timedelta(minutes=minutes)
    start_ts = int(t0.timestamp())
    evs, gaps = {}, []
    if universe == "5m15m":
        tags_to_fetch = SELECT_TAGS_5M15M
        refresh_tags = SELECT_TAGS_5M15M
        univ_cap = 10
    elif universe == "1h4h":
        tags_to_fetch = SELECT_TAGS_1H4H
        refresh_tags = SELECT_TAGS_1H4H
        univ_cap = 15
    elif v2 or universe == "slow":
        tags_to_fetch = SELECT_TAGS_V2
        refresh_tags = ("sports", "politics", "geopolitics")
        univ_cap = MAX_MARKETS
    else:
        tags_to_fetch = SELECT_TAGS
        refresh_tags = ("5m", "15m", "1h", "4h", "up-or-down", "sports")
        univ_cap = MAX_MARKETS

    for tag in tags_to_fetch:
        try:
            for e in fetch_tag_events(tag):
                evs[e.get("slug") or e.get("title")] = e
        except Exception as e:
            gaps.append(f"events {tag}: {str(e)[:120]}")
    chosen = select_markets(list(evs.values()), cap=univ_cap, v2=v2, universe=universe)
    books = {}
    for m in chosen:
        books.update(load_books(m["tokens"]))
    taker = taker_snapshot(chosen, books)
    (out / "taker_complement.json").write_text(json.dumps(taker, indent=1, default=str))
    meta = dict(ts=t0.isoformat(timespec="seconds"), minutes=minutes, interval=interval, margin=margin,
                shares=shares, universe=universe, reprice_any=reprice_any,
                quiet_before_end=quiet_before_end, twap_window_end=twap_window_end,
                selected=[{k: m[k] for k in ("condition_id","question","slug","category","end","fee_rate","volume24h")} for m in chosen],
                taker_complement=dict(evaluated=taker["evaluated"], flagged=taker["flagged"], unknown=taker["unknown"]),
                gaps=gaps, paper_only=True, v2=v2, rebate=rebate,
                fees="maker 0; taker C*rate*p*(1-p) from each market feeSchedule; official category rates at docs.polymarket.com/trading/fees (sports 0.05, not the post's 0.03; geopolitics 0)")
    (out / "run.json").write_text(json.dumps(meta, indent=1, default=str))
    if taker_once:
        print(json.dumps(dict(taker_complement=dict(evaluated=taker["evaluated"], flagged=taker["flagged"], unknown=taker["unknown"]),
                              selected=len(chosen), out=str(out)), indent=1))
        return taker

    papers = {m["condition_id"]: PaperMarket(m, shares, margin, v2=v2, stale=stale, stagger=stagger,
                                             complete_sec=complete_sec, loss_cap=loss_cap,
                                             universe=universe, reprice_any=reprice_any,
                                             quiet_before_end=quiet_before_end) for m in chosen}
    rebate_papers = {m["condition_id"]: PaperRebateMarket(m, inv_cap=inv_cap, quote_sz=shares, v2=v2) for m in chosen} if rebate else {}

    ledger = out / "ledger.jsonl"
    write_jsonl(ledger, [dict(type="select", ts=t0.isoformat(timespec="seconds"), n=len(chosen),
                              slugs=[m["slug"] for m in chosen],
                              fee_rates={m["condition_id"]: m.get("fee_rate") for m in chosen})])
    last_trade_floor = start_ts
    poll_i = 0
    peak_notional_t1 = 0.0
    peak_notional_t2 = 0.0
    last_refresh = None
    refresh_every = dt.timedelta(seconds=30)

    while True:
        ts = now()
        poll_i += 1
        # refresh on a 30s clock (not every few 2s polls) to limit Gamma traffic
        if last_refresh is None or (ts - last_refresh) >= refresh_every:
            last_refresh = ts
            try:
                fresh = {}
                for tag in refresh_tags:
                    for e in fetch_tag_events(tag, 30):
                        fresh[e.get("slug") or e.get("title")] = e
                # drop ended markets with no fills so the trade batch stays on live books
                for cid, p in list(papers.items()):
                    end_s = p.meta.get("end")
                    ended = False
                    if end_s:
                        try:
                            ended = now() >= dt.datetime.fromisoformat(str(end_s).replace("Z", "+00:00"))
                        except ValueError:
                            ended = False
                    if ended and p.yes_qty == 0 and p.no_qty == 0 and not p.settled and not p.exited:
                        p.settle(None, None)
                live = sum(1 for p in papers.values() if not p.settled and not p.exited)
                for m in select_markets(list(fresh.values()), cap=univ_cap, v2=v2, universe=universe):
                    if m["condition_id"] in papers or live >= univ_cap:
                        continue
                    books.update(load_books(m["tokens"]))
                    papers[m["condition_id"]] = PaperMarket(m, shares, margin, v2=v2, stale=stale, stagger=stagger,
                                                            complete_sec=complete_sec, loss_cap=loss_cap,
                                                            universe=universe, reprice_any=reprice_any,
                                                            quiet_before_end=quiet_before_end)
                    if rebate:
                        rebate_papers[m["condition_id"]] = PaperRebateMarket(m, inv_cap=inv_cap, quote_sz=shares, v2=v2)
                    live += 1
                    write_jsonl(ledger, [dict(type="add", ts=ts.isoformat(timespec="seconds"),
                                              slug=m["slug"], question=m["question"],
                                              condition_id=m["condition_id"], fee_rate=m.get("fee_rate"))])
            except Exception as e:
                gaps.append(f"refresh: {str(e)[:120]}")

        active = [p for p in papers.values() if not p.settled and not p.exited]
        cids = [p.meta["condition_id"] for p in active]
        trades, notes = fetch_trades(cids[:20], last_trade_floor)
        gaps.extend(notes)
        if trades:
            last_trade_floor = max(last_trade_floor, max(tr["timestamp"] for tr in trades))
        by_cid = defaultdict(list)
        for tr in trades:
            by_cid[tr["condition_id"]].append(tr)

        events = []
        need = []
        for p in active:
            need.extend(p.meta["tokens"])
        books.update(load_books(need))

        # log twap_log row per market when within twap_window_end of expiry
        for p in active:
            end_s = p.meta.get("end")
            if end_s:
                try:
                    end_dt = dt.datetime.fromisoformat(str(end_s).replace("Z", "+00:00"))
                    sec_to_end = (end_dt - ts).total_seconds()
                    if 0 <= sec_to_end <= twap_window_end:
                        yb = books.get(p.yes_tok)
                        f_rate = p.meta.get("fee_rate")
                        fallback_note = None
                        if f_rate is None and universe in ("5m15m", "1h4h"):
                            f_rate = 0.07
                            fallback_note = "fallback 0.07"
                        events.append(dict(type="twap_log", ts=ts.isoformat(timespec="seconds"),
                                           slug=p.meta.get("slug"), condition_id=p.meta.get("condition_id"),
                                           end=end_s, sec_to_end=round(sec_to_end, 1),
                                           mid=yb.get("mid") if yb else None,
                                           bid=yb.get("bid") if yb else None,
                                           ask=yb.get("ask") if yb else None,
                                           fee_rate=f_rate if fallback_note is None else "UNKNOWN (fallback 0.07)",
                                           note=fallback_note))
                except Exception:
                    pass

        for p in active:
            try:
                yb, nb = books.get(p.yes_tok), books.get(p.no_tok)
                # settle if book collapsed to 0/1 after market end
                if yb and nb and ((yb["mid"] <= 0.01 and nb["mid"] >= 0.99) or (yb["mid"] >= 0.99 and nb["mid"] <= 0.01)):
                    end_s = p.meta.get("end")
                    ended = False
                    if end_s:
                        try:
                            ended = now() >= dt.datetime.fromisoformat(str(end_s).replace("Z", "+00:00"))
                        except ValueError:
                            ended = False
                    if ended:
                        p.settle(1.0 if yb["mid"] >= 0.99 else 0.0, 1.0 if nb["mid"] >= 0.99 else 0.0)
                        events.append(dict(type="settle", ts=ts.isoformat(timespec="seconds"), slug=p.meta.get("slug"),
                                           condition_id=p.meta.get("condition_id"), question=p.meta.get("question"),
                                           yes=p.settle_px_yes, no=p.settle_px_no, pnl=p.snapshot_pnl(yb, nb)))
                        continue

                if not p.frozen and not p.done and not p.exited:
                    changed = p.requote(yb, nb, ts.timestamp())
                    if changed:
                        events.append(dict(type="quote", ts=ts.isoformat(timespec="seconds"), slug=p.meta.get("slug"),
                                           condition_id=p.meta.get("condition_id"), question=p.meta.get("question"),
                                           yes=p.yes_px, no=p.no_px, sum=round((p.yes_px or 0)+(p.no_px or 0), 4)))

                fills = p.apply_trades(by_cid.get(p.meta["condition_id"], []), ts.timestamp())
                if p.stagger == "first" and p.yes_qty > 0 and p.no_qty == 0 and p.no_px is None and not p.done and not p.exited:
                    p.requote(yb, nb, ts.timestamp())
                if p.remaining("yes") or p.remaining("no"):
                    fills += p.apply_book(yb, nb, ts.timestamp())
                for fl in fills:
                    events.append(dict(type="fill", ts=ts.isoformat(timespec="seconds"), slug=p.meta.get("slug"),
                                       condition_id=p.meta.get("condition_id"), question=p.meta.get("question"),
                                       side=fl["side"], qty=fl["qty"], price=fl["price"], src=fl["src"],
                                       trade_px=fl.get("trade_px"), fill_unix=fl.get("ts")))

                exit_ev = p.check_exit(yb, nb, ts.timestamp())
                if exit_ev:
                    events.append(exit_ev)

                pnl = p.snapshot_pnl(yb, nb)
                if p.yes_qty or p.no_qty or p.exited:
                    events.append(dict(type="mark", ts=ts.isoformat(timespec="seconds"), slug=p.meta.get("slug"),
                                       condition_id=p.meta.get("condition_id"), question=p.meta.get("question"),
                                       yes_qty=p.yes_qty, no_qty=p.no_qty,
                                       **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in pnl.items()}))
            except Exception as e:
                gaps.append(f"market {p.meta.get('slug')}: {type(e).__name__}: {str(e)[:120]}")

        # Test 2 rebate market-making tick
        if rebate:
            for cid, rm in rebate_papers.items():
                try:
                    yb, nb = books.get(rm.yes_tok), books.get(rm.no_tok)
                    rm.requote(yb, nb, ts.timestamp())
                    r_fills = rm.apply_trades(by_cid.get(cid, []), ts.timestamp())
                    r_fills += rm.apply_book(yb, nb, ts.timestamp())
                    events.extend(r_fills)
                except Exception as e:
                    gaps.append(f"rebate {rm.meta.get('slug')}: {type(e).__name__}: {str(e)[:120]}")

        # track peak deployed notional across both tests
        cur_t1 = 0.0
        for p in papers.values():
            if not p.settled and not p.exited:
                cur_t1 += p.yes_qty * (p.yes_px or 0.0) + p.no_qty * (p.no_px or 0.0)
                if p.yes_px and p.remaining("yes") > 0:
                    cur_t1 += p.remaining("yes") * p.yes_px
                if p.no_px and p.remaining("no") > 0:
                    cur_t1 += p.remaining("no") * p.no_px
        peak_notional_t1 = max(peak_notional_t1, cur_t1)

        if rebate:
            # shortcut: deployed notional is open inventory mark plus reserved quote bids; upgrade with margin hair-cuts if margin applies
            cur_t2 = 0.0
            for rm in rebate_papers.values():
                yb, nb = books.get(rm.yes_tok), books.get(rm.no_tok)
                my = mid_of(yb) or (rm.buy_cost_yes / rm.buy_qty_yes if rm.buy_qty_yes else 0.5)
                mn = mid_of(nb) or (rm.buy_cost_no / rm.buy_qty_no if rm.buy_qty_no else 0.5)
                cur_t2 += abs(rm.pos_yes) * my + abs(rm.pos_no) * mn
                cur_t2 += rm.quote_bid_sz_yes * (rm.bid_yes or 0.0) + rm.quote_bid_sz_no * (rm.bid_no or 0.0)
            peak_notional_t2 = max(peak_notional_t2, cur_t2)

        if events:
            write_jsonl(ledger, events)
        if now() >= end:
            break
        # interval sleep: min 2s when interval >= 2, else min 5s
        sleep_sec = max(2, interval) if (interval is not None and interval >= 2) else max(5, interval or 5)
        time.sleep(sleep_sec)

    t1 = now()
    # final books + resolution check + summary
    need = [tok for p in papers.values() for tok in p.meta["tokens"]]
    books.update(load_books(need))
    for cid, p in papers.items():
        if not p.settled and not p.exited:
            yb, nb = books.get(p.yes_tok), books.get(p.no_tok)
            end_s = p.meta.get("end")
            ended = False
            if end_s:
                try:
                    ended = now() >= dt.datetime.fromisoformat(str(end_s).replace("Z", "+00:00"))
                except ValueError:
                    ended = False
            if ended and (not yb or not nb or (yb.get("bid") is None and yb.get("ask") is None)):
                ry, rn = fetch_resolution(cid)
                if ry is not None and rn is not None:
                    p.settle(ry, rn)

    reb_list = list(rebate_papers.values()) if rebate else None
    summary = summarize(list(papers.values()), books, t0.isoformat(timespec="seconds"),
                        t1.isoformat(timespec="seconds"), rebate_markets=reb_list,
                        peak_notional_t1=peak_notional_t1, peak_notional_t2=peak_notional_t2)
    summary["gaps"] = gaps[:30]
    summary["markets_quoted"] = sum(1 for p in papers.values() if p.quote_ts)
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    write_jsonl(ledger, [dict(type="summary", **summary)])
    print(json.dumps(summary, indent=1, default=str), flush=True)
    return summary


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--minutes", type=float, default=45)
    a.add_argument("--interval", type=int, default=None)
    a.add_argument("--margin", type=float, default=0.02)
    a.add_argument("--shares", type=float, default=10)
    a.add_argument("--out", default="")
    a.add_argument("--taker-once", action="store_true")
    a.add_argument("--v2", action="store_true")
    a.add_argument("--stale", type=float, default=None)
    a.add_argument("--stagger", choices=["first", "both-small"], default=None)
    a.add_argument("--complete-sec", type=float, default=None)
    a.add_argument("--loss-cap", type=float, default=None)
    a.add_argument("--rebate", action="store_true")
    a.add_argument("--inv-cap", type=float, default=10.0)
    a.add_argument("--universe", choices=["slow", "5m15m", "1h4h"], default=None)
    a.add_argument("--reprice-any", action="store_true")
    a.add_argument("--quiet-before-end", type=float, default=None)
    a.add_argument("--twap-window-end", type=float, default=120.0)
    x = a.parse_args()

    # set v2 defaults when --v2 is turned on
    if x.v2:
        interval = 8 if x.interval is None else x.interval
        stale = 0.03 if x.stale is None else x.stale
        stagger = "first" if x.stagger is None else x.stagger
        complete_sec = 300.0 if x.complete_sec is None else x.complete_sec
        loss_cap = 0.50 if x.loss_cap is None else x.loss_cap
    else:
        interval = 60 if x.interval is None else x.interval
        stale = x.stale
        stagger = x.stagger
        complete_sec = x.complete_sec
        loss_cap = x.loss_cap

    if not (0 < x.margin < 1) or x.shares <= 0 or x.minutes <= 0:
        a.error("margin in (0,1), shares and minutes > 0")
    stamp = now().strftime("%Y%m%dT%H%M%SZ")
    out = Path(x.out) if x.out else OUT_ROOT / f"run-{stamp}"
    run(x.minutes if not x.taker_once else 0.01, interval, x.margin, x.shares, out,
        taker_once=x.taker_once, v2=x.v2, stale=stale, stagger=stagger,
        complete_sec=complete_sec, loss_cap=loss_cap, rebate=x.rebate, inv_cap=x.inv_cap,
        universe=x.universe, reprice_any=x.reprice_any, quiet_before_end=x.quiet_before_end,
        twap_window_end=x.twap_window_end)


if __name__ == "__main__":
    main()
