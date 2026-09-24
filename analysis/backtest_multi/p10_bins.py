"""Below-p10 rate by position x projection bin: MC statline_p10 vs calibrated p10 (LOSO c).
python analysis/backtest_multi/p10_bins.py"""
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
t["bin"] = pd.cut(t.final_projection, [0, 3, 6, 10, 15, 20, 25, 60])
g = t.groupby(["position", "bin"], observed=True).apply(lambda x: pd.Series({
    "n": len(x), "below_mc": (x.actual_points < x.statline_p10).mean(), "below_cal": (x.actual_points < x.p10n).mean(),
    "p10_mc": x.statline_p10.mean(), "p10_cal": x.p10n.mean(), "emp_q10": x.actual_points.quantile(0.10)}))
print(g.round(3).to_string())
