#!/usr/bin/env python3
"""Optuna parameter search for one ideas.json rule (paper-only research; places nothing, no LLM calls).
  python3 optimize.py <idea_id> [--trials 50] [--oos-from 2023-01-01] [--draws 100]
Search: tunes the numbers already in the rule (metric lookbacks like hh_50, numeric thresholds, stop, target, time exit)
within 0.5x-2x of the written value. Objective = t-stat of pooled stress-cost trade returns on IN-SAMPLE bars only (bars
before --oos-from are all the search ever sees; < 30 IS trades scores -inf). Study lives in out/optuna/optuna.db (sqlite),
so reruns add trials to the same study. The best params are then screened ONCE with screen_batch.screen on full data with
variants = total trials in the study, so the DSR gate gets stricter the more you search. Writes out/optuna/<id>-<date>.json."""
import sys, re, json, math, copy, argparse, datetime as dt, statistics as st
from dataclasses import replace
from pathlib import Path
import optuna
ROOT = Path(__file__).parent; sys.path.insert(0, str(ROOT))
import screen_batch as SB
from screen_batch import T, C, V, schema, scanners, extras, history, WARM

def space(idea):
    """-> {param_name: (kind, written_value)} for every number in the rule."""
    p = {}
    for i, c in enumerate(idea.entry):
        for j in (0, 2):
            x = c[j]
            if isinstance(x, str) and (m := re.search(r"_(\d+)$", x)):
                if int(m.group(1)) >= 2: p[f"e{i}{j}_n"] = ("int", int(m.group(1)))   # ret_1 etc. stay as written
            elif isinstance(x, (int, float)) and not isinstance(x, bool) and x != 0 and not (isinstance(c[0], str) and c[0] in ("dow", "dom", "month")):
                p[f"e{i}{j}_v"] = ("float", float(x))
    (k, v), = idea.stop.items(); p["stop"] = ("float", float(v))
    if idea.target: (k, v), = idea.target.items(); p["target"] = ("float", float(v))
    if idea.time_exit_bars: p["time_exit"] = ("int", int(idea.time_exit_bars))
    return p

def apply(idea, params):
    e = copy.deepcopy(idea.entry)
    for k, v in params.items():
        if k[0] == "e":
            i, j = int(k[1]), int(k[2]); x = e[i][j]
            e[i][j] = re.sub(r"_\d+$", f"_{v}", x) if k.endswith("_n") else v
    s = {next(iter(idea.stop)): params.get("stop", next(iter(idea.stop.values())))}
    t = {next(iter(idea.target)): params["target"]} if idea.target else None
    return replace(idea, entry=e, stop=s, target=t, time_exit_bars=params.get("time_exit", idea.time_exit_bars))

def suggest(trial, sp):
    out = {}
    for k, (kind, v) in sp.items():
        lo, hi = sorted((v * 0.5, v * 2))
        out[k] = trial.suggest_int(k, max(2, math.floor(lo)), max(3, math.ceil(hi))) if kind == "int" else trial.suggest_float(k, lo, hi)
    return out

def is_bars(idea, oos_from):
    coins = SB.all_coins() if idea.coins == ["ALL"] else (idea.coins or [idea.symbol])
    out = {}
    for sym in coins:
        h = history.load(sym, idea.asset)
        if "error" in h: continue
        b = [x for x in h["bars"] if x["date"] < oos_from]   # the search never sees OOS bars
        if len(b) >= WARM + 30: out[sym] = b
    return out

def is_score(idea, bars_by):
    """t-stat of pooled IS trade returns at stress cost; -inf below the 30-trade minimum."""
    cost = C.COST_BPS[idea.asset][1] / 1e4; r = []
    for b in bars_by.values():
        sig = scanners.evaluate(b, idea.entry, extras.build(b, idea.entry, lambda s, a: dict(bars=[x for x in history.load(s, a).get("bars", []) if x["date"] <= b[-1]["date"]]), idea.asset))
        sf, tf, _ = V.exits(idea, b)
        r += [t["ret"] for t in T.simulate(b, sig, sf, tf, idea.time_exit_bars, cost, WARM)["trades"]]
    if len(r) < C.MIN_TRADES or st.pstdev(r) == 0: return float("-inf"), len(r)
    return st.mean(r) / st.stdev(r) * math.sqrt(len(r)), len(r)

def main(argv=None):
    a = argparse.ArgumentParser(); a.add_argument("idea"); a.add_argument("--trials", type=int, default=50)
    a.add_argument("--oos-from", default="2023-01-01"); a.add_argument("--draws", type=int, default=100); a.add_argument("--seed", type=int, default=42)
    x = a.parse_args(argv); idea = schema.load(ROOT / "ideas.json")[x.idea]; oos = dt.date.fromisoformat(x.oos_from)
    out = ROOT / "out" / "optuna"; out.mkdir(parents=True, exist_ok=True)
    sp = space(idea); bars_by = is_bars(idea, oos)
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(study_name=f"{idea.id}|oos{x.oos_from}", storage=f"sqlite:///{out / 'optuna.db'}", direction="maximize",
                                load_if_exists=True, sampler=optuna.samplers.TPESampler(seed=x.seed))
    def obj(trial):
        s, n = is_score(apply(idea, suggest(trial, sp)), bars_by); trial.set_user_attr("n_is", n)
        return s if s != float("-inf") else -1e9
    study.optimize(obj, n_trials=x.trials)
    n_trials = len(study.trials); best = apply(idea, study.best_params)
    written_is = is_score(idea, bars_by)
    tuned = replace(best, variants=idea.variants + n_trials)   # every trial counts as a variant for DSR
    keep = lambda r: {k: r.get(k) for k in ("verdict", "reasons", "n_IS", "n_OOS", "IS_mean_stress", "oos_mean_stress", "oos_median_stress", "oos_net_return", "null_p", "dsr")}
    res = dict(idea=idea.id, date=dt.date.today().isoformat(), oos_from=x.oos_from, trials_in_study=n_trials, trials_this_run=x.trials,
               space={k: v[1] for k, v in sp.items()}, best_params=study.best_params, best_is_tstat=study.best_value,
               written_is_tstat=written_is[0], tuned_rule=dict(entry=best.entry, stop=best.stop, target=best.target, time_exit_bars=best.time_exit_bars),
               written_oos=keep(SB.screen((idea, oos, x.draws))), tuned_oos_once=keep(SB.screen((tuned, oos, x.draws))),
               note=f"tuned verdict uses variants = {tuned.variants} (trials in study + written variants) for DSR; a screen is not proof")
    p = out / f"{idea.id}-{res['date']}.json"; p.write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(dict(trials=n_trials, best=study.best_params, written=res["written_oos"]["verdict"], tuned=res["tuned_oos_once"]["verdict"],
                          tuned_reasons=res["tuned_oos_once"]["reasons"]), default=str)); print(p)

if __name__ == "__main__":
    main()
