"""Rebuild history pools' estimated_ownership_pct: (a) shipped v2 form (linear softmax, ALL feats + DST model), leave-one-season-out
on the current hist.parquet; (b) ORACLE = real SE field ownership (FC-derived, local only). Writes pools_v2/ and pools_oracle/.
2026 pools copied unchanged into both. Prints per-season corr vs real field on our pool rows."""
import sys, os, shutil
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent; REPO = HERE.parents[1]
V2 = REPO / "analysis" / "ownership_v2"; sys.path.insert(0, str(V2))
from common import ALL, Model  # noqa
from build import OUT  # noqa
from part3_dst import dst_feats, F_DST_OPT  # noqa
POOLS = REPO / "analysis" / "pool_randomization" / "builds" / "pools"; META = REPO / "analysis" / "lineup_replay" / "hist_meta"
H = pd.read_parquet(OUT / "hist.parquet")
pred = pd.Series(np.nan, index=H.index)
for s in sorted(H.season.unique()):
    te = H.season == s; tr = H[~te]
    sk = Model(ALL).fit(tr, "own"); pred[te] = sk.predict(H[te])
    Dtr = dst_feats(tr); Dte = dst_feats(H[te])
    d = Model(F_DST_OPT, l2=3.0, pos_inter=False).fit(Dtr, "own"); pred[Dte.index] = d.predict(Dte)
H["v2"] = pred
V = H.set_index(["slate_id", "player_id"]).v2
rows = []
for d in ("pools_v2", "pools_oracle"):
    (HERE / d).mkdir(exist_ok=True)
for p in sorted(POOLS.glob("final_projections_dk_*.csv")):
    sid = p.name[len("final_projections_dk_"):-4]
    if not sid.startswith("hist_"):
        for d in ("pools_v2", "pools_oracle"): shutil.copy(p, HERE / d / p.name)
        continue
    tag = sid[5:]; hs = f"h{tag[1:5]}_{tag[6:8]}"
    x = pd.read_csv(p, dtype={"player_id": str}); M = np.load(META / f"{tag}.npz")
    real = pd.Series(dict(zip(M["fp_ids"], M["own"])))
    fid = x.player_name.map(lambda n: int(str(n).split("#")[-1]))
    x_real = fid.map(real).fillna(0.0)
    v = pd.Series([V.get((hs, pid), np.nan) for pid in x.player_id], index=x.index).fillna(0.0)
    for col, d in ((v, "pools_v2"), (x_real, "pools_oracle")):
        y = x.copy(); y["estimated_ownership_pct"] = col * 900.0 / col.sum(); y.to_csv(HERE / d / p.name, index=False)
    k = (x_real > 0.5) | (v > 0.5) | (x.estimated_ownership_pct > 0.5)
    rows.append(dict(season=tag[1:5], tag=tag, v2=np.corrcoef(v[k], x_real[k])[0, 1], old=np.corrcoef(x.estimated_ownership_pct[k], x_real[k])[0, 1],
                     v2_cover=v.sum(), real_cover=x_real.sum()))
R = pd.DataFrame(rows); R.to_csv(HERE / "own_corr_by_slate.csv", index=False)
print(R.groupby("season")[["v2", "old", "v2_cover", "real_cover"]].mean().round(3)); print("ALL", R[["v2", "old"]].mean().round(3).to_dict())
