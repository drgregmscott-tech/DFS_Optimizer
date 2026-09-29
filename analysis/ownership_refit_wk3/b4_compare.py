"""B4 comparison: build-time vs status-applied (refreshed) ownership vs production pre-lock file vs real."""
from pathlib import Path

import numpy as np
import pandas as pd

H = Path(__file__).resolve().parent
log = pd.read_csv(H.parent.parent / "data/ownership_actual_log.csv", dtype={"player_id": str})
for s in ["main", "early", "afternoon"]:
    sid = f"dk_classic_wk3_{s}_27Sep2026"
    b = pd.read_csv(H / f"b4/buildtime_{s}.csv", dtype={"player_id": str}).drop_duplicates("player_id").set_index("player_id")
    a = pd.read_csv(H / f"b4/applied_{s}.csv", dtype={"player_id": str}).drop_duplicates("player_id").set_index("player_id")
    p = pd.read_csv(H / f"rebuilds/final_projections_dk_{sid}.csv", dtype={"player_id": str}).drop_duplicates("player_id").set_index("player_id")
    real = log[log.slate_id == sid].drop_duplicates("player_id").set_index("player_id")["actual_ownership_pct"]
    d = pd.DataFrame({"name": b.player_name, "pos": b.position, "build": b.estimated_ownership_pct,
                      "applied": a.estimated_ownership_pct.reindex(b.index),
                      "prod": p.estimated_ownership_pct.reindex(b.index),
                      "out": a.final_projection.reindex(b.index).eq(0) & b.final_projection.gt(0)})
    d["real"] = real.reindex(d.index).fillna(0)
    live = ~d.out
    ch = live & (d.real >= 20)
    print(f"\n{s}: players zeroed by apply {int(d.out.sum())}; build-time ownership parked on them "
          f"{d.loc[d.out, 'build'].sum():.0f}pt of 900; real ownership on them {d.loc[d.out, 'real'].sum():.1f}")
    for c in ["build", "applied", "prod"]:
        e = (d[c] - d.real)
        print(f"  {c:8s} chalk(real>=20, n={int(ch.sum())}) bias {e[ch].mean():+.1f} mae {e[ch].abs().mean():.1f} | "
              f"corr(live rows) {np.corrcoef(d.loc[live, c].fillna(0), d.loc[live, 'real'])[0, 1]:.3f}")
    print(d[live].nlargest(10, "applied")[["name", "pos", "build", "applied", "prod", "real"]].round(1).to_string())
    print(f"  applied vs prod: max |diff| {(d.applied - d['prod']).abs().max():.1f}, "
          f"corr {np.corrcoef(d.loc[live, 'applied'].fillna(0), d.loc[live, 'prod'].fillna(0))[0, 1]:.3f}")
    print("  biggest build->applied moves among live players:")
    mv = (d.applied - d.build)[live]
    print(d.loc[mv.abs().nlargest(5).index, ["name", "pos", "build", "applied", "real"]].round(1).to_string())
