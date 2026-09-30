"""2026 wk1-3: model fit on ALL 2016-25 (2026 fully out of sample), delta added on top of our LIVE production projection
(data/projection_error_log.csv, DK, one row per player-week = mean over slates). Friday-known OUT definition."""
import sys; from pathlib import Path; import numpy as np, pandas as pd
D = Path(__file__).parent; sys.path.insert(0, str(D))
from evaluate import predict
R = D.parents[1]
for flag in ("fri", "inactive"):
    m = pd.read_pickle(D/f"model_{flag}.pkl")
    F = pd.read_parquet(D/"frame.parquet"); F = F[(F.flag == flag) & (F.season == 2026)].reset_index(drop=True)
    for h in ("cell", "cell_rb", "flat", "prop"): F[f"d_{h}"] = predict(m, F, h)
    E = pd.read_csv(R/"data/projection_error_log.csv"); E = E[E.site == "dk"]
    E = E.groupby(["week", "player_id"]).agg(prod=("final_projection", "mean"), act_log=("actual_fpts", "mean"), name=("player_name", "first")).reset_index()
    X = F.merge(E, on=["week", "player_id"])
    print(f"\n===== 2026 wk1-3, OUT={flag}: {len(F)} teammate rows, {len(X)} with a live DK projection =====")
    for nm, msk in [("all", np.ones(len(X), bool)), ("RB1 OUT -> RBs", ((X.outpos_car=="RB")&(X.V_car>=.3)&(X.pos=="RB")).to_numpy()),
                    ("cell gain >= 1.5", (X.d_cell >= 1.5).to_numpy())]:
        rows = []
        for h in ("none", "flat", "prop", "cell", "cell_rb"):
            p = X["prod"] + (0 if h == "none" else X[f"d_{h}"]); e = (X.act_log - p)[msk]
            rows.append({"method": h, "n": int(msk.sum()), "MAE": np.abs(e).mean(), "RMSE": np.sqrt((e**2).mean()), "bias": e.mean()})
        print("--", nm); print(pd.DataFrame(rows).round(2).to_string(index=False))
    show = X[X.d_cell >= 1.0].sort_values("d_cell", ascending=False)
    print(show[["week","team","name","pos","sh_car","sh_tgt","V_car","V_tgt","rk_car","prod","d_cell","act_log"]].round(2).to_string(index=False))
