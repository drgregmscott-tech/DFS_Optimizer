"""Redo the 2026 wk1-2 'production FIX' slice of analysis/proj_fc_accuracy/compare.py with the player pool taken from the
PRE-LOCK production commits (wk1 cefc761, wk2 7e57cfe) instead of HEAD (HEAD wk1 main was rebuilt post-lock, 89 vs 40 zeros).
FIX values: wk1 from the guarded rebuild file (argv[1]); wk2 from analysis/proj_recheck/guarded_accuracy_frame.csv (HEAD==7e57cfe for wk2).
No FC data in this file. Output printed + appended to data/fc_history/derived/proj_lineup_level/redo_2026.txt
"""
import io, os, subprocess, sys, glob
import numpy as np, pandas as pd

R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DER = os.path.join(R, "data/fc_history/derived")
TOPN = {"QB": 5, "RB": 10, "WR": 15, "TE": 5}

def gshow(c, f):
    s = subprocess.run(["git", "show", f"{c}:output/{f}"], cwd=R, capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return pd.read_csv(io.StringIO(s), dtype={"player_id": str})

fc = pd.read_csv(os.path.join(DER, "fc_master_mapped.csv"), low_memory=False, dtype={"player_id": str})
fc = fc[(fc.site == "dk") & (fc.slate_kind == "classic") & (fc.season == 2026) & fc.player_id.notna()].drop_duplicates(["week", "player_id"])
ours = pd.concat([pd.read_csv(f, dtype={"player_id": str}) for f in glob.glob(os.path.join(DER, "ourproj/proj_2026_*.csv"))])
G = pd.read_csv(os.path.join(R, "analysis/proj_recheck/guarded_accuracy_frame.csv"), dtype={"player_id": str})
G = G[G["sub"] == "main"].drop_duplicates(["week", "player_id"])
fix1 = pd.read_csv(sys.argv[1], dtype={"player_id": str})
rows = []
for wk, c, f in [(1, "cefc761", "final_projections_dk_dk_classic_wk1_main_13Sep2026.csv"), (2, "7e57cfe", "final_projections_dk_dk_classic_wk2_main_20Sep2026.csv")]:
    for pool in ["prelock", "HEAD"]:
        o = gshow(c if pool == "prelock" else "HEAD", f)
        dead = set(o.loc[(o.final_projection <= 0) | (o.get("injury_status") == "OUT"), "player_id"])
        m = o[~o.player_id.isin(dead)][["player_id", "final_projection"]].rename(columns={"final_projection": "OLD"})
        fx = fix1[["player_id", "final_projection"]] if wk == 1 else G[G.week == 2][["player_id", "FIX"]].rename(columns={"FIX": "final_projection"})
        m = m.merge(fx.rename(columns={"final_projection": "FIX"}), on="player_id")
        m = m.merge(fc[fc.week == wk][["player_id", "pos", "fc_proj", "score"]], on="player_id")
        m = m.merge(ours[ours.week == wk][["player_id", "final_projection"]].rename(columns={"final_projection": "ours"}), on="player_id")
        rows.append(m.assign(week=wk, pool=pool))
D = pd.concat(rows).rename(columns={"fc_proj": "fc", "score": "act"}).dropna(subset=["fc", "act"])
D = D[D.pos.isin(TOPN)]
D = D[D[["fc", "ours", "FIX"]].max(axis=1) > 8]
out = []
for pool, d in D.groupby("pool"):
    for src in ["fc", "FIX", "OLD", "ours"]:
        e = d[src] - d.act
        sp, tn = [], []
        for (w, p), g in d.groupby(["week", "pos"]):
            if len(g) >= 5: sp.append(g[src].rank().corr(g.act.rank()))
            tn.append(g.nlargest(TOPN[p], src).act.mean())
        out.append(dict(pool=pool, src=src, n=len(d), bias=e.mean(), MAE=e.abs().mean(), RMSE=np.sqrt((e ** 2).mean()), spear_w=np.nanmean(sp), topN=np.mean(tn)))
T = pd.DataFrame(out).set_index(["pool", "src"]).round(3)
print(T.to_string())
ex = D[D.pool == "prelock"].merge(D[D.pool == "HEAD"][["player_id", "week"]], how="left", indicator=True)
ex = ex[ex._merge == "left_only"]
print("rows in prelock pool but dropped by HEAD pool:", len(ex), "mean act", round(ex.act.mean(), 2), "mean FIX", round(ex.FIX.mean(), 2), "mean fc", round(ex.fc.mean(), 2))
with open(os.path.join(DER, "proj_lineup_level/redo_2026.txt"), "w") as fh:
    fh.write(T.to_string() + f"\nprelock-only rows {len(ex)} mean act {ex.act.mean():.2f} FIX {ex.FIX.mean():.2f} fc {ex.fc.mean():.2f}\n")
