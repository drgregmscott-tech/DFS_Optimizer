"""Final QB recal candidate evaluation (research; no FC data inside).
Candidate: for QBs with pre-recal projection >= 8 (projected starters), wk3+ DK classic:
  new = a + b*proj + c*implied_total + d*spread + e*proj_rush_pts ; spread = O/U/2 - implied (+ = underdog)
Baseline "prod" = what production would output now: q, plus the wk7+ QB salary blend (early_season_blend_config.json).
Writes derived/qb_depth/qb_recal_candidate_<date>.json (FC-fit -> git-ignored)."""
import json, os
import numpy as np, pandas as pd
from scipy.stats import spearmanr
R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
D = os.path.join(R, "data/fc_history/derived")
X = pd.read_parquet(os.path.join(D, "qb_depth/qb_frame.parquet"))
X = X[(X.season <= 2025) & (X.week >= 3)].copy()
X["q"] = X.q_final_projection
cfg = json.load(open(os.path.join(D, "projection_v2/early_season_blend_config.json")))
m, b0 = cfg["sal_line"]["QB"]; pa = cfg["weeks"]["7+"]["QB"]
S = m * X.salary / 1000 + b0
X["prod"] = np.where(X.week >= 7, (X.q + pa["a"] + pa["w"] * (S - X.q)).clip(lower=0), X.q)
COLS = ["q", "implied_total", "spread", "q_rush"]
G = X.q >= 8
TR = X[G & X.played & (X.attempts + X.carries >= 5)]
def fit(T):
    A = np.c_[np.ones(len(T)), T[COLS].values]; return np.linalg.lstsq(A, T.act.values, rcond=None)[0]
def pred(b, D_): return np.c_[np.ones(len(D_)), D_[COLS].values] @ b
X["cand"] = X.q
for s in sorted(X.season.unique()):
    k = G & (X.season == s); X.loc[k, "cand"] = pred(fit(TR[TR.season != s]), X[k])
bfull = fit(TR); print("full-fit coefs [a, b_proj, c_implied, d_spread, e_rushpts]:", bfull.round(4))
# per-season coefficient stability
for s in sorted(X.season.unique()):
    print("  fit on", s, "only:", fit(TR[TR.season == s]).round(3))
E = X[X.started & X.fc.notna()].copy()
mae = lambda g, c: (g[c] - g.act).abs().mean()
print("\nHeld-out MAE, wk3+ actual starters | ours(q) | prod(q+wk7 blend) | cand | FC")
for s, g in E.groupby("season"):
    print(s, len(g), " ".join(f"{mae(g,c):.3f}" for c in ["q", "prod", "cand", "fc"]))
print("all", len(E), " ".join(f"{mae(E,c):.3f}" for c in ["q", "prod", "cand", "fc"]))
for lab, g in [("wk3-6", E[E.week <= 6]), ("wk7+", E[E.week >= 7])]:
    print(lab, len(g), " ".join(f"{mae(g,c):.3f}" for c in ["q", "prod", "cand", "fc"]))
# slate-clustered bootstrap
rng = np.random.default_rng(0); sl = E.groupby(["season", "week"])
keys = list(sl.groups); per = {k: (g.cand.sub(g.act).abs().sum(), g["prod"].sub(g.act).abs().sum(), g.fc.sub(g.act).abs().sum(), len(g)) for k, g in sl}
arr = np.array([per[k] for k in keys]); bs = []
for _ in range(2000):
    a = arr[rng.integers(0, len(arr), len(arr))]; bs.append(((a[:, 1] - a[:, 0]) / a[:, 3].sum()).sum() * 1 if False else (a[:, 1].sum() - a[:, 0].sum()) / a[:, 3].sum())
bs2 = [];
for _ in range(2000):
    a = arr[rng.integers(0, len(arr), len(arr))]; bs2.append((a[:, 2].sum() - a[:, 0].sum()) / a[:, 3].sum())
print("gain cand vs prod MAE %.3f [%.3f, %.3f]; cand vs FC %.3f [%.3f, %.3f]" % (np.mean(bs), *np.percentile(bs, [2.5, 97.5]), np.mean(bs2), *np.percentile(bs2, [2.5, 97.5])))
E["tier"] = pd.cut(E.sal_rank, [0, 3, 6, 10, 16, 99], labels=["QB1-3", "QB4-6", "QB7-10", "QB11-16", "QB17+"])
print("\nBy tier: MAE(bias) prod | cand | FC ; calib slope prod/cand/FC")
for t, g in E.groupby("tier", observed=True):
    sl_ = [np.polyfit(g[c], g.act, 1)[0] for c in ["prod", "cand", "fc"]]
    print(t, len(g), " | ".join(f"{mae(g,c):.2f}({(g[c]-g.act).mean():+.1f})" for c in ["prod", "cand", "fc"]), " slope " + "/".join(f"{x:.2f}" for x in sl_))
print("overall slope prod/cand/FC", "/".join(f"{np.polyfit(E[c], E.act, 1)[0]:.2f}" for c in ["prod", "cand", "fc"]),
      " proj SD", "/".join(f"{E[c].std():.2f}" for c in ["prod", "cand", "fc"]))
print("\nWithin-slate (starters) Spearman / top-3 by proj mean actual / RMSE")
for c in ["prod", "cand", "fc"]:
    sp = np.mean([spearmanr(h[c], h.act)[0] for _, h in E.groupby(["season", "week"])])
    t3 = np.mean([h.nlargest(3, c).act.mean() for _, h in E.groupby(["season", "week"])])
    print(f"{c:5s} sp {sp:.3f} top3 {t3:.2f} rmse {np.sqrt(((E[c]-E.act)**2).mean()):.2f}")
json.dump({"_note": "QB wk3+ recal (analysis/qb_depth). new = a + b*proj + c*implied_total + d*spread + e*proj_rush_pts for QB with proj>=8, "
                    "DK classic, weeks>=3; replaces the QB part of the early-season salary blend for those weeks. FC-history fit (FC actuals) -> do not commit.",
           "gate_min_proj": 8.0, "min_week": 3, "coef": dict(zip(["a", "b_proj", "c_implied", "d_spread", "e_rush_pts"], bfull.round(5).tolist()))},
          open(os.path.join(D, "qb_depth/qb_recal_candidate_2026-09-29.json"), "w"), indent=1)
X.to_parquet(os.path.join(D, "qb_depth/qb_recal_eval.parquet"))
