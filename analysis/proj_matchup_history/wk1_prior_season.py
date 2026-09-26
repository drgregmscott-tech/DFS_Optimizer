"""Production wk1 uses the WHOLE prior season's matchup factor (g=17, weight .81 at k=4).
History regen had empty wk1 factors. Emulate prior-season factor on wk1 baseline rows
(engine + S*(mf-1)), k in {4,16,64}; within slate x pos Spearman / top-N vs a0."""
import sys, numpy as np, pandas as pd
from pathlib import Path
from scipy.stats import spearmanr
REPO = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO / "scripts"))
import projections_matchup as pm
DER = REPO / "data/fc_history/derived"
f = pd.read_parquet(DER / "matchup_history/frame.parquet"); f = f[f.week == 1]
TOPN = {"QB": 6, "RB": 12, "WR": 18, "TE": 6}
res = []
for s, g in f.groupby("season"):
    b = pd.concat([pd.read_csv(DER / f"ourproj/proj_{s}_wk1.csv", dtype={"player_id": str})])
    S = (b.proj_pass_yd*.04+b.proj_pass_td*4+b.proj_rush_yd*.1+b.proj_rush_td*6+b.proj_rec_yd*.1+b.proj_rec_td*6)
    b = b.assign(S=S)[["player_id", "S", "opponent"]]
    g = g.merge(b, on="player_id")
    w = pd.read_parquet(REPO / f"data/weekly_stats_{s-1}.parquet")
    w = w[(w.season_type == "REG") & w.position.isin(pm.POSITIONS)].copy(); w["fantasy_points"] = w.fantasy_points_ppr
    for k in (4, 16, 64):
        pm.SHRINKAGE_K_GAMES = k
        m = pm.matchup_factors(w).set_index(["team", "position"]).matchup_factor
        mf = pd.Series([m.get((o, p), 1.0) for o, p in zip(g.opponent, g.position)], index=g.index)
        g[f"k{k}"] = g.fin_a0 + g.S * (mf - 1)
    for p, c in g.groupby("position"):
        for v in ["fin_a0", "k4", "k16", "k64"]:
            res.append(dict(season=s, pos=p, v=v, sp=spearmanr(c[v], c.score)[0], top=c.nlargest(TOPN[p], v).score.mean()))
r = pd.DataFrame(res).pivot_table(index=["season", "pos"], columns="v", values=["sp", "top"])
for v in ["k4", "k16", "k64"]:
    d = r["sp"][v] - r["sp"]["fin_a0"]; t = r["top"][v] - r["top"]["fin_a0"]
    print(v, f"sp d={d.mean():+.4f} per-season", d.groupby(level=0).mean().round(3).to_dict(), f"top d={t.mean():+.3f}", t.groupby(level=0).mean().round(2).to_dict())
