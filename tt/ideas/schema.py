"""Idea record (rewrite of flow brain/thesis.py). Every idea must carry a written exit before it can be validated:
a stop plus a target and/or a time exit. Long only for now (the simulator is long only)."""
import json
from dataclasses import dataclass, field, asdict
OPS = (">", ">=", "<", "<=", "==")

@dataclass
class Idea:
    id: str; symbol: str; asset: str              # asset: equity | crypto
    entry: list                                    # ANDed conditions: [["rsi_2","<",10],["close",">","sma_200"]]
    stop: dict                                     # {"atr": 2.0} (x ATR14 at signal) or {"pct": 5}
    target: dict = None                            # {"R": 1.5} or {"pct": 8} or None
    time_exit_bars: int = None
    side: str = "long"
    thesis: str = ""; source: str = "manual"
    variants: int = 1                              # how many versions were tried before this one (for DSR)

    def problems(self):
        p = []
        if self.asset not in ("equity", "crypto"): p.append(f"asset must be equity or crypto, got {self.asset!r}")
        if self.side != "long": p.append(f"side {self.side!r} unsupported (long only)")
        if not self.entry: p.append("no entry conditions")
        for c in self.entry or []:
            if not (isinstance(c, (list, tuple)) and len(c) == 3 and c[1] in OPS): p.append(f"bad entry condition {c!r}")
        if not isinstance(self.stop, dict) or len(self.stop) != 1 or next(iter(self.stop)) not in ("atr", "pct") \
                or not next(iter(self.stop.values()), 0) > 0: p.append("needs a written stop: {'atr': x} or {'pct': x}")
        if self.target is not None and (not isinstance(self.target, dict) or next(iter(self.target), None) not in ("R", "pct")):
            p.append("target must be {'R': x} or {'pct': x}")
        if self.target is None and not self.time_exit_bars: p.append("needs a written exit besides the stop: target and/or time_exit_bars")
        return p

    def to_dict(self): return asdict(self)

def load(path):
    """JSON list of idea dicts -> {id: Idea}."""
    return {d["id"]: Idea(**d) for d in json.loads(open(path).read())}
