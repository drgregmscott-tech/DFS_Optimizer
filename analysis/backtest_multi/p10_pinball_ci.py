"""LOSO pinball-10 delta (calibrated p10 minus shipped statline_p10), week-bootstrap CI.
python analysis/backtest_multi/p10_pinball_ci.py"""
import numpy as np, pandas as pd, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import followups as fu
d = fu.load("baseline", "played"); d = d[d.position.isin(fu.SKILL) & d.sigma.gt(0)].copy()
parts = []
for s in fu.SEASONS:
    c = fu.fit_c(d[d.season != s], "sigma", False)
    t = d[d.season == s].copy(); t["p10n"] = fu.p10_candidates(t, c, "sigma"); parts.append(t)
t = pd.concat(parts)
def pin(y, q): u = y - q; return np.maximum(0.1 * u, -0.9 * u)
t["dl"] = pin(t.actual_points, t.p10n) - pin(t.actual_points, t.statline_p10)
for lab, g in [("skill", t)] + [(p, t[t.position == p]) for p in fu.SKILL]:
    w = g.groupby(["season", "week"])["dl"].agg(["sum", "size"])
    rng = np.random.default_rng(7); idx = rng.integers(0, len(w), (2000, len(w)))
    bs = w["sum"].to_numpy()[idx].sum(1) / w["size"].to_numpy()[idx].sum(1)
    by = g.groupby("season")["dl"].mean()
    print(f"{lab:5s} n={len(g):5d} dPinball10={g.dl.mean():+.4f} [{np.percentile(bs,2.5):+.4f},{np.percentile(bs,97.5):+.4f}] "
          f"seasons improved {int((by<0).sum())}/8")
