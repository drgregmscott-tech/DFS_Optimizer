"""Build ownership-variant pools: same projections, only estimated_ownership_pct swapped. DO NOT COMMIT (FC/contest-derived).
Sources: old (layered, DFS_OWNERSHIP_V2=0), v2 (shipped: current coef + vac bump), v2tp (truepool coef + vac bump),
v2novac (current coef, vac off), oracle (realized contest ownership). usage: python make_pools.py <variant>"""
import os, sys, re
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent; REPO = HERE.parents[1]
V = sys.argv[1]
env = {"old": {"DFS_OWNERSHIP_V2": "0"}, "v2": {}, "v2tp": {"DFS_OWN_V2_COEF": "truepool"},
       "v2novac": {"DFS_OWN_VAC_BUMP": "0"}, "oracle": {}}[V]
os.environ.update(env)
sys.path.insert(0, str(REPO / "scripts")); sys.path.insert(0, str(REPO / "analysis" / "ownership_lever"))
sys.path.insert(0, str(REPO / "analysis" / "lambda_reverify")); sys.path.insert(0, str(REPO / "analysis" / "lineup_replay"))
from sweep import POOLS, S26, HIST  # lambda_reverify
import ownership_model, ingest_salaries  # noqa
from build_projections import add_ownership_columns
OUT = HERE / "pools"; OUT.mkdir(exist_ok=True)

def sw(sid):
    if sid.startswith("hist_"):
        m = re.match(r"hist_h(\d{4})w(\d\d)", sid); return int(m[1]), int(m[2])
    m = re.search(r"wk(\d+)_", sid); return 2026, int(m[1])

rows = []
for sid in S26 + HIST:
    df = pd.read_csv(POOLS / f"final_projections_dk_{sid}.csv", dtype={"player_id": str})
    orig = df["estimated_ownership_pct"].copy()
    if V == "oracle":
        from own_real import real_own
        new = real_own(sid, df)
    else:
        drop = [c for c in df.columns if c in ("chalk_score", "estimated_ownership_pct", "estimated_ownership_pct_heuristic",
                "est_own_live_old", "est_own_v2_only", "own_vacated", "own_vac_bump")]
        base = df.drop(columns=drop).copy()
        s, w = sw(sid)
        try:
            out = add_ownership_columns(base, "dk", layered=True, season=s, week=w)
            m = out.set_index("player_id")["estimated_ownership_pct"]
            new = df["player_id"].map(m).fillna(0.0).values
            if "estimated_ownership_pct_heuristic" in out.columns:
                h = df["player_id"].map(out.set_index("player_id")["estimated_ownership_pct_heuristic"])
                print("heur corr vs pool", float(np.corrcoef(h.fillna(0), df.estimated_ownership_pct_heuristic.fillna(0))[0, 1]))
        except Exception as e:
            print(sid, "FAIL", repr(e)); new = orig.values
    df["estimated_ownership_pct"] = np.asarray(new, float)
    df.to_csv(OUT / f"{V}__final_projections_dk_{sid}.csv", index=False)
    rows.append((sid, V, float(np.corrcoef(orig, df.estimated_ownership_pct)[0, 1]), float(np.abs(orig - df.estimated_ownership_pct).max())))
    print(rows[-1], flush=True)
pd.DataFrame(rows, columns=["sid", "var", "corr_vs_poolcol", "maxdiff_vs_poolcol"]).to_csv(HERE / f"make_{V}.csv", index=False)
