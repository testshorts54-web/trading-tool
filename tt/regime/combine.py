"""Rule-based labels. Fewer known scored rules than the minimum -> 'unknown' (never guessed)."""
def label(rows, min_known, on=3, off=-3):
    sc = [r for r in rows if r["scored"]]
    known = [r for r in sc if r["status"] == "ok" and r["score"] is not None]
    if len(known) < min_known:
        return dict(label="unknown", score=None, known=len(known), total=len(sc),
                    why=f"only {len(known)}/{len(sc)} scored rules have fresh data (need {min_known})")
    s = sum(r["score"] for r in known)
    lab = "risk-on" if s >= on else ("risk-off" if s <= off else "neutral")
    return dict(label=lab, score=s, known=len(known), total=len(sc),
                why=f"sum of scores {s:+d} over {len(known)}/{len(sc)} rules; >= {on:+d} risk-on, <= {off:+d} risk-off, else neutral")

def crypto_label(rows):
    c1 = next((r for r in rows if r["id"] == "C1"), None)
    if not c1 or c1["status"] != "ok":
        return dict(label="unknown", score=None, why=f"BTC rule unavailable: {c1 and c1['reason']}")
    lab = {1: "risk-on", 0: "neutral", -1: "risk-off"}[c1["score"]]
    return dict(label=lab, score=c1["score"], why="from BTC vs rising/falling SMA100 (rule C1); ETH (C2) shown for confirmation only")
