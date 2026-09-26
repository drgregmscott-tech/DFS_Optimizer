"""wk1 price-weight-floor arms (prodw50/prodw75) vs base/prod: player-level + lineup (research only; no FC data inside)."""
import os, sys, glob, numpy as np, pandas as pd
R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")); OUT = os.path.join(R, "data/fc_history/derived/proj_early_season")
sys.path.insert(0, os.path.join(R, "analysis/proj_lineup_level")); from lineup_eval import solve_k
X = pd.read_parquet(os.path.join(OUT, "players.parquet")); X = X[X.week == 1]
for a in ["prodw50", "prodw75"]:
    o = pd.concat([pd.read_csv(f, dtype={"player_id": str}, usecols=["season", "week", "player_id", "final_projection"]) for f in glob.glob(os.path.join(OUT, a, "proj_*.csv"))])
    X = X.merge(o.rename(columns={"final_projection": a}), on=["season", "week", "player_id"], how="left")
A = {"base": "final_projection", "prod": "final_projection_prod", "prodw50": "prodw50", "prodw75": "prodw75", "fc": "fc"}
V = X[X.played & ((X.fc >= 5) | (X.final_projection >= 5))]
P = lambda f: pd.DataFrame({k: V.groupby("season").apply(lambda h: f(h[c], h.act)) for k, c in A.items()}).round(3)
print("wk1 within-slate Spearman by season\n", P(lambda p, a: p.corr(a, method="spearman")))
print("wk1 MAE by season\n", P(lambda p, a: (p - a).abs().mean()))
print("wk1 top-24 by proj per slate: mean actual\n", pd.DataFrame({k: V.groupby("season").apply(lambda h: h.nlargest(24, c).act.mean()) for k, c in A.items()}).round(2))
# lineups (skill only + DST from base arm lineups not available here -> use DST at FC proj for all arms, identical across arms)
L = pd.read_csv(os.path.join(OUT, "lineups_early.csv"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import lineup_early as le
Y = le.load(); Y = Y[Y.week == 1]
for a in ["prodw50", "prodw75"]:
    o = pd.concat([pd.read_csv(f, dtype={"player_id": str}, usecols=["season", "week", "player_id", "final_projection"]) for f in glob.glob(os.path.join(OUT, a, "proj_*.csv"))])
    Y = Y.merge(o.rename(columns={"final_projection": a}), on=["season", "week", "player_id"], how="left")
    Y[a] = Y[a].fillna(Y.final_projection).clip(lower=0)
rows = []
for s, g in Y.groupby("slate"):
    g = g.reset_index(drop=True); sal, pos, act = g.salary.values.astype(float), g.pos.values, g.act.values
    for k, c in {"base": "final_projection", "prod": "final_projection_prod", "prodw50": "prodw50", "prodw75": "prodw75"}.items():
        for b in [0, 0.35]:
            ob = (1 - b) * g[c].values + b * g.fc.values
            Ls = solve_k(sal, pos, ob, 5)
            rows.append(dict(slate=s, v=f"{k}{'_b35' if b else ''}", r0=act[Ls[0]].sum(), bo5=max(act[L].sum() for L in Ls)))
T = pd.DataFrame(rows)
for m in ["r0", "bo5"]:
    print(f"\nwk1 lineup {m} by slate"); print(T.pivot(index="slate", columns="v", values=m).round(1).to_string())
