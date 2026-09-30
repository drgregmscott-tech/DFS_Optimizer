"""Step 1: where does v2 linear (LOSO) miss cheap WR/TE vs realized and vs FC Own? No FC data in this file.
Outputs go to data/fc_history/derived/cheap_wrte/ (git-ignored)."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ownership_v2"))
from common import ALL, R, Model  # noqa
OUT = R / "data/fc_history/derived/cheap_wrte"; OUT.mkdir(parents=True, exist_ok=True)
H = pd.read_parquet(R / "data/fc_history/derived/ownership_v2/hist.parquet")
H = H.reset_index(drop=True)
# extra raw quantities for residual scanning (all pre-lock, already in frame)
p = np.zeros(len(H))
for s in sorted(H.season.unique()):
    te = (H.season == s).to_numpy()
    p[te] = Model(ALL).fit(H[~te], "own").predict(H[te])
H["v2"] = p
H[["slate_id", "player_id", "v2"]].to_parquet(OUT / "v2_loso.parquet")
cw = H.pos.isin(["WR", "TE"]) & (H.salary < 5500) & (H.own > 0)
C = H[cw].copy()
C["res"] = C.own - C.v2; C["fres"] = C.fc_own - C.v2
print("cheap WR/TE rows", len(C), "corr v2", np.corrcoef(C.v2, C.own)[0,1])
m3 = C.season <= 2023
print("2021-23 corr v2 %.3f  FC %.3f" % (np.corrcoef(C.v2[m3], C.own[m3])[0,1], np.corrcoef(C.fc_own[m3], C.own[m3])[0,1]))
print("mean own %.2f v2 %.2f  (bias by real-own bucket)" % (C.own.mean(), C.v2.mean()))
C["bk"] = pd.cut(C.own, [0, 2, 5, 10, 20, 100])
print(C.groupby("bk", observed=True).agg(n=("own","size"), own=("own","mean"), v2=("v2","mean"), fc=("fc_own","mean")).round(2))
# residual correlation scan with every numeric column
num = [c for c in C.columns if C[c].dtype.kind in "fi" and c not in ("res","fres","own","fc_own","v2","act","ours_own_model")]
sc = pd.DataFrame({"corr_res_real": [C.res.corr(C[c]) for c in num],
                   "corr_res_fc(21-23)": [C.fres[m3].corr(C[c][m3]) for c in num]}, index=num)
print(sc.reindex(sc.corr_res_real.abs().sort_values(ascending=False).index).head(25).round(3))
print("corr res with realized points (act):", round(C.res.corr(C.act), 3))
C.sort_values("res", ascending=False).head(40)[["season","week","player","pos","team","salary","proj","own","fc_own","v2","vacated","my_share","p3_usage","team_total","act"]].to_csv(OUT/"top_under.csv", index=False)
C.sort_values("res").head(40)[["season","week","player","pos","team","salary","proj","own","fc_own","v2","vacated","my_share","p3_usage","team_total","act"]].to_csv(OUT/"top_over.csv", index=False)
print(C.sort_values("res", ascending=False).head(30)[["season","week","player","team","salary","proj","own","fc_own","v2","vacated","my_share","p3_usage","team_total"]].round(2).to_string())
C.drop(columns="bk").to_parquet(OUT / "cheap_frame.parquet")
