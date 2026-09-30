"""Oracle ownership: copy of analysis/ownership_lever/sweep.py real_own (read-only reuse)."""
import sys
from pathlib import Path
import numpy as np
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "analysis" / "lineup_replay"))

def real_own(sid, df):
    if sid.startswith("hist_"):
        M = np.load(REPO / "analysis" / "lineup_replay" / "hist_meta" / f"{sid[5:]}.npz")
        d = dict(zip(M["fp_ids"], M["own"]))
        return df.player_name.map(lambda n: d.get(int(str(n).split("#")[-1]), 0.0)).astype(float)
    import grade as G
    lab = {v[0]: k for k, v in G.SL.items()}[sid]
    C = G.contest(*G.SL[lab][1]["se"])
    return df.player_name.map(lambda n: C["own"].get(G.norm(n), 0.0)).astype(float)
