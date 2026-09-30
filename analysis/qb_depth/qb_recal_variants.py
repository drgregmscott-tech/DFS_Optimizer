"""Gated (proj>=8) LOSO QB recal variants on known starters, vs production-equivalent and FC (research; no FC data)."""
import os
import numpy as np, pandas as pd
R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
X = pd.read_parquet(os.path.join(R, "data/fc_history/derived/qb_depth/qb_recal_eval.parquet"))
G = X.q >= 8
TR = X[G & X.played & (X.attempts + X.carries >= 5)]
V = {"lin": ["q"], "lin+it": ["q", "implied_total"], "lin+it+sp": ["q", "implied_total", "spread"],
     "cand(it+sp+rush)": ["q", "implied_total", "spread", "q_rush"], "prodbase+it+sp+rush": ["prod", "implied_total", "spread", "q_rush"],
     "it+sp+rush,no q": ["implied_total", "spread", "q_rush"], "+salary": ["q", "implied_total", "spread", "q_rush", "salary"]}
K = X[G & X.started & X.fc.notna()].copy()
mae = lambda g, c: (g[c] - g.act).abs().mean()
for n, cols in V.items():
    K[n] = np.nan
    for s in sorted(X.season.unique()):
        T = TR[TR.season != s]; A = np.c_[np.ones(len(T)), T[cols].values]; b = np.linalg.lstsq(A, T.act.values, rcond=None)[0]
        k = K.season == s; K.loc[k, n] = np.c_[np.ones(k.sum()), K.loc[k, cols].values] @ b
print("known starters wk3+, held-out MAE gain vs prod by season 2021..2025 | all MAE | wk3-6 MAE (prod %.3f FC %.3f)" % (mae(K[K.week<=6], "prod"), mae(K[K.week<=6], "fc")))
for n in V:
    print(f"{n:22s}", " ".join(f"{mae(g,'prod')-mae(g,n):+.3f}" for _, g in K.groupby("season")), f"| {mae(K,n):.3f} | {mae(K[K.week<=6],n):.3f}")
print(f"{'prod':22s}", f"| {mae(K,'prod'):.3f};  FC | {mae(K,'fc'):.3f}")
