"""Regression check for the ownership v2 switch (scripts/ownership_v2.py).

    python scripts/test_ownership_v2_switch.py output/final_projections_dk_dk_classic_wk3_main_27Sep2026.csv 3

Asserts, on one DK classic final_projections file (ownership recomputed from scratch):
  1. switch OFF (DFS_OWNERSHIP_V2=0): no v2 columns are added;
  2. switch ON: est_own_live_old equals the OFF estimated_ownership_pct exactly (old path preserved);
  3. ON: no NaN, 0 for zero-projection players, <= 75 cap, each QB/RB/WR/TE/DST group sums to its
     artifact budget; chalk_score / heuristic unchanged vs OFF;
  4. re-running on the ON output (status_check apply refresh) gives no _x/_y duplicate columns.
Byte-identity of OFF against the pre-v2 code was checked separately on 2026-09-29 (wk3 main, build
and status-apply refresh paths).
"""
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_projections as bp  # noqa: E402
import ownership_v2  # noqa: E402

path, week = sys.argv[1], int(sys.argv[2])
season = int(sys.argv[3]) if len(sys.argv) > 3 else None
raw = pd.read_csv(path, dtype={"player_id": str, "site_player_id": str})
base = raw.drop(columns=[c for c in raw.columns if c in ("chalk_score", "estimated_ownership_pct")
                         or c.startswith("estimated_ownership_pct_heuristic") or c.startswith("est_own_")
                         or c in ("own_vacated", "own_vac_bump")])


def run(flag):
    os.environ["DFS_OWNERSHIP_V2"] = flag
    return bp.add_ownership_columns(base, "dk", season=season, week=week)


off, on = run("0"), run("1")
assert not {"est_own_live_old", "est_own_v2_only", "own_vac_bump"} & set(off.columns), "OFF added v2 columns"
assert np.array_equal(on["est_own_live_old"].to_numpy(), off["estimated_ownership_pct"].to_numpy()), \
    "ON est_own_live_old != OFF estimated_ownership_pct"
assert on["chalk_score"].equals(off["chalk_score"]), "chalk_score changed"
assert on["estimated_ownership_pct_heuristic"].equals(off["estimated_ownership_pct_heuristic"]), "heuristic changed"
e = on["estimated_ownership_pct"]
assert e.notna().all(), "NaN ownership"
assert (e[pd.to_numeric(on["final_projection"]) <= 0] == 0).all(), "ownership on zero-projection player"
assert e.max() <= 75.0 + 1e-9, "cap exceeded"
lin, dst = ownership_v2.load_artifacts("dk")
budgets = dict(lin["budgets"], DST=float(dst["budget"]))
sums = on.groupby(on["position"].replace({"D": "DST", "DEF": "DST"}))["estimated_ownership_pct"].sum()
for g, b in budgets.items():
    assert abs(sums.get(g, 0.0) - b) < 1e-6, f"{g} sums {sums.get(g)} != budget {b}"
os.environ["DFS_OWNERSHIP_V2"] = "1"
again = bp.add_ownership_columns(on.drop(columns=["chalk_score", "estimated_ownership_pct"]), "dk",
                                 season=season, week=week)
assert not [c for c in again.columns if c.endswith(("_x", "_y"))], "refresh produced _x/_y columns"
print("OK", {k: round(v, 1) for k, v in sums.items()})
