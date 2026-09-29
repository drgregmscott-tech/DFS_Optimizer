"""Spot checks: cheap-DST rows (Jets wk1, Titans/Vikings wk3), FFC-unlisted chalk, floor victims on wk3.
Uses the same LOWO fits as evaluate.py."""
import pandas as pd
from evaluate import load, fit_pred, FEATS_ALL, floor

df = load()
out = []
for w in [1, 2, 3]:
    te, tr = df[df.week == w].copy(), df[df.week != w]
    for name, f in FEATS_ALL.items():
        te[name], _ = fit_pred(tr, te, f)
    te["floor45"] = floor(te, te["ffc"], 0.45, True)
    out.append(te)
d = pd.concat(out)
cols = ["week", "slate_id", "player_name", "position_group", "salary", "final_projection", "ffc_own_pct", "own", "est_live", "ffc", "ffc+dst_min", "ffc_soft_nolisted", "floor45"]
d["slate"] = d.slate_id.str.extract(r"wk\d_(\w+?)_")
cols[1] = "slate"
pd.set_option("display.width", 250)
print("DST with real >= 10%:")
print(d[(d.position_group == "DST") & (d.own >= 10)][cols].round(1).sort_values(["week", "slate", "salary"]).to_string(index=False))
print("\nFFC-unlisted non-DST with real >= 10%:")
print(d[(d.position_group != "DST") & (d.own >= 10) & d.ffc_own_pct.isna()][cols].round(1).sort_values(["week", "own"]).to_string(index=False))
print("\nwk3 players the floor moved by >= 3pt:")
x = d[(d.week == 3) & ((d.floor45 - d.ffc).abs() >= 3)]
print(x[cols].round(1).to_string(index=False))
