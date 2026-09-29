"""Fit final candidates on all 2021-25 realized ownership and save coefficients only (no FC rows)."""
import json, sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from common import ALL, GROUPS, Model
from build import OUT
from part3_dst import dst_feats, F_DST_OPT
H = pd.read_parquet(OUT / "hist.parquet")
m = Model(ALL).fit(H, "own")
json.dump({"kind": "ownership_v2_softmax_linear", "fit": "realized DK SE own 2021-25 (86 slates), not wired",
           "features": ALL, "pos_interaction_order": GROUPS, "mu": m.mu.tolist(), "sd": m.sd.tolist(),
           "b": m.b.tolist(), "budgets": m.budgets, "cap": 75.0},
          open(Path(__file__).parent / "ownership_v2_linear.candidate-2026-09-29.json", "w"), indent=1)
D = dst_feats(H)
d = Model(F_DST_OPT, l2=3.0, pos_inter=False).fit(D, "own")
json.dump({"kind": "ownership_v2_dst_softmax", "features": F_DST_OPT, "mu": d.mu.tolist(), "sd": d.sd.tolist(),
           "b": d.b.tolist(), "budget": 100.0},
          open(Path(__file__).parent / "ownership_v2_dst.candidate-2026-09-29.json", "w"), indent=1)
print("saved")
