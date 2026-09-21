"""Refine: re-score the top candidates from best_single.py with a game-script (margin) factor,
many more sims, and split results by who wins. usage: python refine_single.py <projections_csv> [top_n]"""
import sys, pickle
from pathlib import Path
import numpy as np, pandas as pd
R = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(R / "scripts")); sys.path.insert(0, str(Path(__file__).parent))
import best_single as bs, showdown_field as sf

CSV = sys.argv[1]; TOP = int(sys.argv[2]) if len(sys.argv) > 2 else 60
PK = Path(__file__).parent / "cands.pkl"
P = bs.load_pool(CSV)
if PK.exists():
    cands = pickle.load(open(PK, "rb"))
else:
    cands = bs.candidates(P)
    pickle.dump(cands, open(PK, "wb"))
prev = pd.read_csv(Path(__file__).parent / "best_single_results.csv", index_col=0)
keep = prev.index[:TOP].tolist()
cands = [cands[i] for i in keep]

fl = P[P.roster_role == "FLEX"].reset_index(drop=True)
cpt_own = fl.player_id.map(P[P.roster_role == "CPT"].set_index("player_id").estimated_ownership_pct).values
fields = {"model-own": sf.simulate_field(fl.salary.values, fl.team.values, cpt_own, fl.estimated_ownership_pct.values, n=15000, seed=1)}
h = P[P.roster_role == "CPT"].set_index("player_id").estimated_ownership_pct_heuristic
fields["old-own"] = sf.simulate_field(fl.salary.values, fl.team.values, fl.player_id.map(h).values, fl.estimated_ownership_pct_heuristic.values, n=15000, seed=1)

idx = {pid: i for i, pid in enumerate(fl.player_id)}
m = len(fl); teams = fl.team.unique().tolist(); tix = fl.team.map({t: i for i, t in enumerate(teams)}).values; opp = 1 - tix
la = teams.index("LA")
pos = fl.position.values; isk = pos == "K"; isd = np.isin(pos, ["DST", "D", "DEF"])
proj = fl.final_projection.values; sig = fl.sigma.values
W = np.zeros((m, len(cands)))
for j, c in enumerate(cands):
    for r in c.itertuples():
        W[idx[r.player_id], j] = 1.5 if r.roster_role == "CPT" else 1.0
sign = np.where(tix == la, 1.0, -1.0)   # +1 for LA players, -1 for NYG

# scenario: (a game/total factor, b own-offense factor, lam = projection swing per 1 SD of game margin, dst_rho, dst_mult)
SC = {"base": (0.20, 0.45, 0.10, -0.5, 1.0), "shootout": (0.40, 0.35, 0.10, -0.5, 1.0),
      "big-script": (0.15, 0.40, 0.20, -0.5, 1.0), "quiet-DST": (0.20, 0.45, 0.10, 0.0, 0.6)}
N = 6000
res = {}   # (scenario, field) -> (p10 all, p10 | LA wins, p10 | NYG wins)
for sname, (a, b, lam, drho, dmult) in SC.items():
    for fname, (fc, ff) in fields.items():
        rng = np.random.default_rng(99)
        hit = np.zeros((N, len(cands)), bool); margin = np.zeros(N)
        for s in range(N):
            G = rng.normal(); M = rng.normal(); T = rng.normal(size=2); e = rng.normal(size=m)
            z = a * G + b * T[tix] + np.sqrt(max(1e-6, 1 - a * a - b * b)) * e
            z = np.where(isk, 0.45 * T[tix] + np.sqrt(1 - 0.2025) * e, z)
            z = np.where(isd, drho * T[opp] + np.sqrt(1 - drho ** 2) * e, z)
            mean = proj * (1 + lam * M * sign)              # game-script swing: winner's players up, loser's down
            mean = np.where(isd, proj * (1 + lam * M * sign), mean)
            pts = np.maximum(0.0, mean + sig * np.where(isd, dmult, 1.0) * z)
            field = np.sort(1.5 * pts[fc] + pts[ff].sum(axis=1))
            hit[s] = (np.searchsorted(field, pts @ W) / len(field)) >= 0.90
            margin[s] = M
        res[(sname, fname)] = (hit.mean(0), hit[margin > 0.5].mean(0), hit[margin < -0.5].mean(0))
allp = np.vstack([v[0] for v in res.values()]); lawin = np.vstack([v[1] for v in res.values()]); nywin = np.vstack([v[2] for v in res.values()])
df = pd.DataFrame({"avg": allp.mean(0) * 100, "worst": allp.min(0) * 100, "if_LA_wins": lawin.mean(0) * 100, "if_NYG_wins": nywin.mean(0) * 100})
df["desc"] = [bs.describe(P, c) for c in cands]
nm = P.set_index(bs.ROWKEY)
df["proj"] = [float((nm.loc[c[bs.ROWKEY], "final_projection"].values * np.where(c.roster_role == "CPT", 1.5, 1.0)).sum()) for c in cands]
df["salary"] = [int((nm.loc[c[bs.ROWKEY], "salary"]).sum()) for c in cands]
df["min_side"] = df[["if_LA_wins", "if_NYG_wins"]].min(axis=1)
pd.set_option("display.width", 250, "display.max_colwidth", 100)
print("\nTOP 12 by average P(top10%):"); print(df.sort_values("avg", ascending=False).head(12).round(1).to_string())
print("\nTOP 8 by robustness (worst scenario):"); print(df.sort_values("worst", ascending=False).head(8).round(1).to_string())
print("\nTOP 8 by 'works whoever wins' (min of LA-wins / NYG-wins):"); print(df.sort_values("min_side", ascending=False).head(8).round(1).to_string())
df.to_csv(Path(__file__).parent / "refine_results.csv")
