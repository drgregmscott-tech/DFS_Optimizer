"""On vs off rebuild compare (2026 slates): affected RBs vs actuals, byte-identity of unaffected rows."""
import sys; from pathlib import Path; import numpy as np, pandas as pd
D = Path(__file__).parent; R = D.parents[1]
E = pd.read_csv(R/"data/projection_error_log.csv"); E = E[E.site=="dk"].groupby(["week","player_id"]).actual_fpts.mean()
for sid, wk in [("dk_classic_wk2_main_20Sep2026",2),("dk_classic_wk3_main_27Sep2026",3),("dk_classic_wk3_afternoon_27Sep2026",3)]:
    for kind in ("buildtime","final_projections_dk"):
        on = pd.read_csv(D/f"rebuild26/builds/on/{kind}_{sid}.csv"); off = pd.read_csv(D/f"rebuild26/builds/off/{kind}_{sid}.csv")
        m = on.merge(off, on="player_id", suffixes=("","_off"))
        aff = m.wrw_delta_pts > 0
        cols = [c for c in off.columns if c in on.columns and c not in ("player_id","wrw_delta_pts","wrw_vacated_car")]
        diffrows = set()
        for c in cols:
            a, b = m[c], m[c+"_off"]
            ne = ~((a == b) | (a.isna() & b.isna()))
            diffrows |= set(m.player_id[ne])
        un = set(m.player_id[~aff])
        print(f"{sid} {kind}: rows {len(m)}, affected {aff.sum()}, unaffected rows with ANY diff: {len(diffrows & un)}",
              sorted(m.set_index('player_id').loc[list(diffrows & un),'player_name'])[:10] if diffrows & un else "")
    b = m[aff].copy()
    b["act"] = [E.get((wk,p), np.nan) for p in b.player_id]
    b["val_on"] = b.final_projection/b.salary*1000; b["val_off"] = b.final_projection_off/b.salary*1000
    print(b[["player_name","team","salary","wrw_delta_pts","final_projection_off","final_projection","val_off","val_on","act"]].round(2).to_string(index=False))
