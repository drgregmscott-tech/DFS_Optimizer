"""Score the real-pipeline history rebuilds: affected RBs (wrw_delta_pts>0), off = final - delta, on = final."""
from pathlib import Path; import numpy as np, pandas as pd
D = Path(__file__).resolve().parent; R = D.parents[1]
A = pd.concat([pd.read_csv(p) for p in sorted((D/"hist_builds/on").glob("proj_*.csv"))], ignore_index=True)
S = pd.concat([pd.read_parquet(R/f"data/weekly_stats_{y}.parquet") for y in range(2021, 2026)])
S = S[S.season_type == "REG"].fillna(0)
S["dk"] = S.fantasy_points_ppr + 3*(S.rushing_yards>=100) + 3*(S.receiving_yards>=100) + 3*(S.passing_yards>=300)
act = S.set_index(["season","week","player_id"]).dk
P = pd.read_csv(R/"analysis/inactives/status_panel_2016_2025.csv").set_index(["season","week","gsis_id"]).inactive
A["act"] = [act.get((s,w,p), np.nan) for s,w,p in zip(A.season,A.week,A.player_id)]
A["inactive"] = [bool(P.get((s,w,p), np.isnan(a))) for s,w,p,a in zip(A.season,A.week,A.player_id,A.act)]
A["act"] = A.act.fillna(0.0)
x = A[A.wrw_delta_pts > 0].copy(); x["off"] = x.final_projection - x.wrw_delta_pts; x["on"] = x.final_projection
def sc(d, nm):
    r = []
    for h in ("off","on"):
        e = d.act - d[h]; r.append(f"{h}: MAE {e.abs().mean():.2f} RMSE {np.sqrt((e**2).mean()):.2f} bias {e.mean():+.2f}")
    print(f"{nm:38s} n={len(d):4d} | " + " | ".join(r))
act_x = x[~x.inactive]
print(f"{A[['season','week']].drop_duplicates().shape[0]} weeks rebuilt, {len(x)} affected RB rows ({x.inactive.sum()} inactive at T-90)")
sc(act_x, "affected RBs, active")
sc(x, "affected RBs, incl T-90 inactive as 0")
sc(act_x[act_x.wrw_delta_pts >= 2], "active, delta >= 2")
sc(act_x[act_x.wrw_delta_pts < 2], "active, delta < 2")
sc(act_x[act_x.off >= 8], "active, base proj >= 8")
for s, g in act_x.groupby("season"): sc(g, f"  season {s}")
print("unaffected rows:", (A.wrw_delta_pts == 0).sum())
print(act_x.sort_values("wrw_delta_pts", ascending=False).head(15)[["season","week","player_name","team","salary","off","wrw_delta_pts","on","act"]].round(1).to_string(index=False))
