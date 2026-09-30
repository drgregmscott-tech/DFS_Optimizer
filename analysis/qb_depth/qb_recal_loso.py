"""LOSO test of QB recalibration candidates (research; no FC data inside)."""
import os
import numpy as np, pandas as pd
from scipy.stats import spearmanr
R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
X = pd.read_parquet(os.path.join(R, "data/fc_history/derived/qb_depth/qb_frame.parquet"))
X = X[(X.season <= 2025) & (X.week >= 3)].copy()
X["q"] = X.q_final_projection
X["tr_rpts"] = X.tr_rpts.fillna(X.q_rush)  # rookies: our own rush projection
X["q_rush_sh"] = X.q_rush / X.q.clip(lower=1)
# training pool: pre-lock QB1 of team (production guard) who played (injury-out handled by status feed live)
TR = X[X.qb1 & X.played & (X.attempts + X.carries >= 5)]
EV = X[X.started & X.fc.notna()]
MODELS = {
    "lin": ["q"],
    "lin+it": ["q", "implied_total"],
    "lin+it+sp": ["q", "implied_total", "spread"],
    "lin+it+sp+rush": ["q", "implied_total", "spread", "tr_rpts"],
    "lin+it+sp+qrush": ["q", "implied_total", "spread", "q_rush"],
    "lin+sal": ["q", "salary"],
    "full": ["q", "implied_total", "spread", "q_rush", "salary"],
}
def fit(T, cols):
    A = np.c_[np.ones(len(T)), T[cols].values]; return np.linalg.lstsq(A, T.act.values, rcond=None)[0]
def pred(b, D, cols): return np.c_[np.ones(len(D)), D[cols].values] @ b
res = {}
E = EV.copy()
for name, cols in MODELS.items():
    E[name] = np.nan
    for s in sorted(X.season.unique()):
        b = fit(TR[TR.season != s].dropna(subset=cols), cols)
        k = E.season == s
        E.loc[k, name] = pred(b, E[k], cols)
    print(name, "full-fit coefs", fit(TR.dropna(subset=cols), cols).round(3))
def mae(g, p): return (g[p] - g.act).abs().mean()
cols = ["q"] + list(MODELS) + ["fc"]
print("\nMAE on wk3+ actual starters (held-out season):")
print("season n " + " ".join(f"{c:>15s}" for c in cols))
for s, g in E.groupby("season"):
    print(s, len(g), " ".join(f"{mae(g,c):15.3f}" for c in cols))
print("all", len(E), " ".join(f"{mae(E,c):15.3f}" for c in cols))
print("\ngain vs ours by season (+ = better):")
for c in list(MODELS):
    print(f"{c:18s}", " ".join(f"{mae(g,'q')-mae(g,c):+.3f}" for _, g in E.groupby("season")))
E["tier"] = pd.cut(E.sal_rank, [0, 3, 6, 10, 16, 99], labels=["QB1-3", "QB4-6", "QB7-10", "QB11-16", "QB17+"])
print("\nby tier: ours / lin+it+sp+qrush / full / FC  MAE (bias)")
for t, g in E.groupby("tier", observed=True):
    print(t, len(g), " ".join(f"{mae(g,c):.2f}({(g[c]-g.act).mean():+.1f})" for c in ["q", "lin+it+sp+qrush", "full", "fc"]))
print("\nwithin-slate spearman / top1-by-proj mean act:")
for c in ["q", "lin", "lin+it+sp+qrush", "full", "fc"]:
    sp = np.mean([spearmanr(h[c], h.act)[0] for _, h in E.groupby(["season", "week"])])
    t3 = np.mean([h.nlargest(3, c).act.mean() for _, h in E.groupby(["season", "week"])])
    print(f"{c:18s} sp {sp:.3f} top3 act {t3:.2f}")
# all QB pool rows incl backups (does recal hurt backups?) — apply to all qb rows with fc (played, fc>=5 or q>=5)
P = X[X.played & ((X.fc >= 5) | (X.q >= 5)) & X.fc.notna()].copy()
for name in ["lin+it+sp+qrush", "full"]:
    cols_ = MODELS[name]; P[name] = np.nan
    for s in sorted(X.season.unique()):
        b = fit(TR[TR.season != s].dropna(subset=cols_), cols_); k = P.season == s
        P.loc[k, name] = pred(b, P[k].fillna({"tr_rpts": 0}), cols_)
print("\nprojection_v2-style pool (played, fc>=5|q>=5), n", len(P))
for s, g in P.groupby("season"):
    print(s, len(g), " ".join(f"{mae(g,c):.3f}" for c in ["q", "lin+it+sp+qrush", "full", "fc"]))
print("all", " ".join(f"{mae(P,c):.3f}" for c in ["q", "lin+it+sp+qrush", "full", "fc"]))
E.to_parquet(os.path.join(R, "data/fc_history/derived/qb_depth/qb_recal_eval.parquet"))
