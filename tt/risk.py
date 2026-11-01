"""Pre-trade risk check for a PAPER entry (rewrite of flow brain/risk.py with Kennedy's limits).
Inputs are an idea, a planned entry price and a paper equity figure; no account data is read.
Rules: validated (verdict PASS) - written exit - stop below entry - size = min(10% position cap, 1% risk / stop
distance) - regime gate from Part A (risk-off warns, or blocks if configured) - daily drawdown breaker (persisted)."""
import json, math, datetime as dt
from pathlib import Path
from tt import config as C

def stop_price(idea, entry, atr=None):
    (k, v), = idea.stop.items()
    if k == "pct": return entry * (1 - v / 100)
    return None if atr is None else entry - v * atr

def target_price(idea, entry, stop):
    if not idea.target: return None
    (k, v), = idea.target.items()
    return entry + v * (entry - stop) if k == "R" else entry * (1 + v / 100)

def latest_regime(out_dir):
    fs = sorted(Path(out_dir).glob("20*.json"))
    if not fs: return None
    R = json.loads(fs[-1].read_text())
    return dict(run_date=R["run_date"], overall=R["overall"]["label"], crypto=R["crypto"]["label"])

def breaker(state_path, equity, today, limit=C.DAILY_DD_BREAKER_PCT):
    """Day-start paper equity is stored on first check each day; trips when equity <= start x (1 - limit)."""
    p = Path(state_path); s = json.loads(p.read_text()) if p.exists() else {}
    if s.get("day") != today.isoformat(): s = dict(day=today.isoformat(), start_equity=equity); p.write_text(json.dumps(s))
    dd = equity / s["start_equity"] - 1
    return dict(day_start_equity=s["start_equity"], day_change=dd, tripped=dd <= -limit)

def check(idea, entry, equity, verdict=None, atr=None, regime=None, state_path=None, today=None,
          block_on_risk_off=C.BLOCK_ON_RISK_OFF):
    today = today or dt.date.today(); rej, warn = [], []
    if verdict != "PASS": rej.append(f"not validated: verdict {verdict}")
    rej += idea.problems()
    if not entry or entry <= 0 or not equity or equity <= 0: rej.append("entry price and paper equity must be > 0")
    stop = stop_price(idea, entry, atr) if entry else None
    if stop is None: rej.append("stop cannot be computed (missing ATR?)")
    elif stop >= entry: rej.append(f"stop {stop:.4f} is not below entry {entry:.4f}")
    tgt = target_price(idea, entry, stop) if stop and stop < entry else None
    if regime:
        lab = regime["crypto"] if idea.asset == "crypto" else regime["overall"]
        if lab == "risk-off": (rej if block_on_risk_off else warn).append(f"regime {lab} on {regime['run_date']}")
        if lab == "unknown": warn.append("regime unknown")
    else: warn.append("no Part A readout found (regime gate skipped)")
    br = breaker(state_path, equity, today) if state_path and equity and equity > 0 else None
    if br and br["tripped"]: rej.append(f"daily drawdown breaker: {br['day_change']:.1%} <= -{C.DAILY_DD_BREAKER_PCT:.0%}")
    size = None
    if not rej or (stop and stop < entry and entry > 0 and equity > 0):
        dist = entry - stop
        qty = min(C.MAX_POSITION_PCT * equity / entry, C.MAX_RISK_PER_TRADE_PCT * equity / dist)
        qty = math.floor(qty) if idea.asset == "equity" else math.floor(qty * 1e6) / 1e6
        if qty <= 0: rej.append("position rounds to zero")
        size = dict(qty=qty, notional=qty * entry, pct_of_equity=qty * entry / equity, risk_usd=qty * dist,
                    risk_pct=qty * dist / equity, binding="position cap" if C.MAX_POSITION_PCT * equity / entry <= C.MAX_RISK_PER_TRADE_PCT * equity / dist else "1% risk")
    return dict(idea=idea.id, approved=not rej, rejections=rej, warnings=warn, entry=entry, stop=stop, target=tgt,
                reward_risk=None if tgt is None or stop is None else (tgt - entry) / (entry - stop), time_exit_bars=idea.time_exit_bars,
                size=size, breaker=br, paper_only=C.PAPER_ONLY)
