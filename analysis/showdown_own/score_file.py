"""Score a lineup file for P(top 10%) with the scenario machinery from refine_single.py.
usage: python score_file.py <projections_csv> <lineups_csv> [n_sims]"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
R = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(R / "scripts")); sys.path.insert(0, str(Path(__file__).parent))
import best_single as bs, showdown_field as sf

CSV, LU = sys.argv[1], sys.argv[2]
N = int(sys.argv[3]) if len(sys.argv) > 3 else 6000
P = bs.load_pool(CSV)
L = pd.read_csv(LU, dtype={"player_id": str})
cands = []
for lid, g in L.groupby("lineup_id"):
    c = g[["player_id", "roster_role"]].copy(); c[bs.ROWKEY] = c.player_id + "::" + c.roster_role; cands.append((lid, c))
fl = P[P.roster_role == "FLEX"].reset_index(drop=True)
cpt_own = fl.player_id.map(P[P.roster_role == "CPT"].set_index("player_id").estimated_ownership_pct).values
fields = {"model-own": sf.simulate_field(fl.salary.values, fl.team.values, cpt_own, fl.estimated_ownership_pct.values, n=15000, seed=1)}
if "estimated_ownership_pct_heuristic" in P.columns:
    h = P[P.roster_role == "CPT"].set_index("player_id").estimated_ownership_pct_heuristic
    fields["old-own"] = sf.simulate_field(fl.salary.values, fl.team.values, fl.player_id.map(h).values, fl.estimated_ownership_pct_heuristic.values, n=15000, seed=1)
idx = {pid: i for i, pid in enumerate(fl.player_id)}
m = len(fl); teams = fl.team.unique().tolist(); tix = fl.team.map({t: i for i, t in enumerate(teams)}).values; opp = 1 - tix
la = teams.index("LA"); sign = np.where(tix == la, 1.0, -1.0)
pos = fl.position.values; isk = pos == "K"; isd = np.isin(pos, ["DST", "D", "DEF"])
proj = fl.final_projection.values; sig = fl.sigma.values
W = np.zeros((m, len(cands)))
for j, (lid, c) in enumerate(cands):
    for r in c.itertuples():
        W[idx[r.player_id], j] = 1.5 if r.roster_role == "CPT" else 1.0
SC = {"base": (0.20, 0.45, 0.10, -0.5, 1.0), "shootout": (0.40, 0.35, 0.10, -0.5, 1.0),
      "big-script": (0.15, 0.40, 0.20, -0.5, 1.0), "quiet-DST": (0.20, 0.45, 0.10, 0.0, 0.6)}
res = {}
for sname, (a, b, lam, drho, dmult) in SC.items():
    for fname, (fc, ff) in fields.items():
        rng = np.random.default_rng(99)
        hit = np.zeros((N, len(cands)), bool); top1 = np.zeros((N, len(cands)), bool); margin = np.zeros(N)
        for s in range(N):
            G = rng.normal(); M = rng.normal(); T = rng.normal(size=2); e = rng.normal(size=m)
            z = a * G + b * T[tix] + np.sqrt(max(1e-6, 1 - a * a - b * b)) * e
            z = np.where(isk, 0.45 * T[tix] + np.sqrt(1 - 0.2025) * e, z)
            z = np.where(isd, drho * T[opp] + np.sqrt(1 - drho ** 2) * e, z)
            mean = proj * (1 + lam * M * sign)
            pts = np.maximum(0.0, mean + sig * np.where(isd, dmult, 1.0) * z)
            field = np.sort(1.5 * pts[fc] + pts[ff].sum(axis=1))
            pc = np.searchsorted(field, pts @ W) / len(field)
            hit[s] = pc >= 0.90; top1[s] = pc >= 0.99; margin[s] = M
        res[(sname, fname)] = (hit.mean(0), hit[margin > 0.5].mean(0), hit[margin < -0.5].mean(0), top1.mean(0))
allp = np.vstack([v[0] for v in res.values()])
df = pd.DataFrame({"lineup": [l for l, _ in cands], "avg_top10": allp.mean(0) * 100, "worst": allp.min(0) * 100,
                   "LA_out": np.vstack([v[1] for v in res.values()]).mean(0) * 100,
                   "NYG_out": np.vstack([v[2] for v in res.values()]).mean(0) * 100,
                   "top1": np.vstack([v[3] for v in res.values()]).mean(0) * 100})
nm = P.set_index(bs.ROWKEY)
df["desc"] = [bs.describe(P, c) for _, c in cands]
df["proj"] = [float(nm.loc[c[bs.ROWKEY], "final_projection"].values.sum()) for _, c in cands]  # CPT rows already carry the 1.5x
df["salary"] = [int(nm.loc[c[bs.ROWKEY], "salary"].sum()) for _, c in cands]
own = P.set_index(bs.ROWKEY).estimated_ownership_pct
df["own_sum"] = [float(own.loc[c[bs.ROWKEY]].sum()) for _, c in cands]
pd.set_option("display.width", 250, "display.max_colwidth", 100)
print(df.sort_values("avg_top10", ascending=False).round(1).to_string(index=False))
