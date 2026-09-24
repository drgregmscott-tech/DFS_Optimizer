"""Stacked-exposure prototype (uncommitted research). Builds per-slate
exposure from QB-stacked optimizer lineups on noisy projections, mirroring
ownership_model.optimizer_exposure (60 lineups, 25% noise, uniqueness 1).

Stack target per lineup: solve unstacked on the noisy draw, take that
lineup's QB team, then re-solve with stack_mode="qb" on that team (so the
field-like 'best QB this draw' decides the stack). Fallback on an
impossible stack: keep the unstacked lineup.

Usage: python stacked_exposure.py  -> writes <scratch>/sexp.pkl
  dict[(slate_id, setting)] = DataFrame(player_id, exp, qb_team_count)
"""
import sys, time, pickle
from pathlib import Path
import numpy as np, pandas as pd

REPO = Path(r"C:\Users\gmsco\Desktop\DFS_Optimizer")
sys.path.insert(0, str(REPO / "scripts"))
import optimizer  # noqa
import ownership_model as om  # noqa
from ingest_salaries import SITE_CONFIGS  # noqa

SCR = Path(r"C:\Users\gmsco\AppData\Local\Temp\claude\C--Users-gmsco-Desktop-DFS-Optimizer\36a97c4a-433e-4ff9-b857-c9a23bb65822\scratchpad")

# Pre-specified settings (fixed before looking at results).
SETTINGS = {
    "qb1": dict(stack_size=1, stack_positions={"WR", "TE"}, bring_back=False),
    "qb2": dict(stack_size=2, stack_positions={"WR", "TE", "RB"}, bring_back=False),
    "qb1bb": dict(stack_size=1, stack_positions={"WR", "TE"}, bring_back=True),
}


def stacked_exposure(df, setting, n=om.EXPOSURE_LINEUPS, pct=om.EXPOSURE_RANDOMIZATION_PCT, seed=om.EXPOSURE_SEED):
    cfg = SITE_CONFIGS["dk"]
    fixed, flex = optimizer.parse_roster_requirements(cfg["roster_slots"])
    p = df.copy()
    for c in ("final_projection", "salary", "sigma"):
        p[c] = pd.to_numeric(p[c], errors="coerce").fillna(0.0)
    p = p[p.final_projection > 0].copy()
    rng = np.random.default_rng(seed)
    counts, qbt, prev, fb = {}, {}, [], 0
    kw = SETTINGS[setting]
    for _ in range(n):
        opt = optimizer.randomize_projections(p, pct, rng)
        base = optimizer.solve_lineup(p, cfg["salary_cap"], fixed, flex, previous_lineups=prev,
                                      uniqueness=1, optimization_projection=opt, stack_mode="none")
        team = base.loc[base.position == "QB", "team"].iloc[0]
        try:
            sel = optimizer.solve_lineup(p, cfg["salary_cap"], fixed, flex, previous_lineups=prev,
                                         uniqueness=1, optimization_projection=opt, stack_mode="qb",
                                         target_team=team, **kw)
        except Exception:
            sel, fb = base, fb + 1
        ids = set(sel.player_id)
        prev.append(ids)
        for pid in ids:
            counts[pid] = counts.get(pid, 0) + 1
        t = sel.loc[sel.position == "QB", "team"].iloc[0]
        qbt[t] = qbt.get(t, 0) + 1
    return pd.Series(counts) / n * 100, pd.Series(qbt) / n, fb


if __name__ == "__main__":
    d = pd.read_pickle(SCR / "d_ffc.pkl")
    out = {}
    for sid, g in d.groupby("slate_id"):
        for s in SETTINGS:
            t0 = time.time()
            e, q, fb = stacked_exposure(g, s)
            out[(sid, s)] = (e, q)
            print(sid, s, f"{time.time()-t0:.0f}s fallbacks={fb}", flush=True)
    pickle.dump(out, open(SCR / "sexp.pkl", "wb"))
