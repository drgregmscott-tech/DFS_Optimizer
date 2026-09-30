"""Score the DNP model on 2026 wk1-3 pre-lock production files (research). Usage: python dnp_2026_check.py <scratch_dir>"""
import io, json, os, subprocess, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
import dnp_frame, dnp_model
R = dnp_frame.R; SP = sys.argv[1]
FILES = [(1, "main", "cefc761", "13Sep2026"), (2, "main", "7e57cfe", "20Sep2026"), (3, "main", "84fbb02", "27Sep2026"),
         (3, "early", "0dba72d", "27Sep2026"), (3, "afternoon", "2c01488", "27Sep2026")]
seen = []
for wk, sub, sha, dt in FILES:
    txt = subprocess.run(["git", "-C", R, "show", f"{sha}:output/final_projections_dk_dk_classic_wk{wk}_{sub}_{dt}.csv"], capture_output=True, text=True, encoding="utf-8", check=True).stdout
    d = pd.read_csv(io.StringIO(txt), dtype={"player_id": str}); d["season"], d["week"] = 2026, wk
    d.to_csv(os.path.join(SP, f"proj_2026_wk{wk}_{sub}.csv"), index=False)
dnp_frame.main(seasons=[2026], proj_glob=os.path.join(SP, "proj_2026_*.csv"), out_name="dnp_frame_2026.parquet")
o = pd.read_parquet(os.path.join(dnp_frame.D, "qb_depth/dnp_frame_2026.parquet"))
# production status is applied in the file (Out -> 0); use file injury status as designation where nflverse lacks it
U = o[(o.final_projection > 5) & ~o.desig.isin(["Out", "Doubtful"]) & o.status.isin(["ACT", "INA"])].copy()
m = json.load(open(os.path.join(dnp_frame.D, "qb_depth/dnp_model_candidate_2026-09-29.json")))
F = dnp_model.feats(U)[m["cols"]].values
U["p"] = dnp_model.pred_logit((np.array(m["b"]), np.array(m["mu"]), np.array(m["sd"])), F)
U["y"] = U.zero_off
print("2026 wk1-3 production proj>5, not Out/Doubtful:", len(U), "zero-snap", int(U.y.sum()), "AUC %.3f" % dnp_model.auc(U.y.values.astype(float), U.p.values))
print(U[U.y | (U.p >= .1)].sort_values("p", ascending=False)[["week", "player_name", "position", "team", "salary", "final_projection", "proj_rank", "snap_l3", "desig", "status", "p", "y", "offense_pct"]].round(2).to_string(index=False))
