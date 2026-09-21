"""Build the showdown ownership dataset: one row per (slate, player, role) with
heuristic estimate, optimizer-exposure features (separately for CPT / FLEX rows),
and real logged ownership + points."""
import sys, warnings
from pathlib import Path
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
R = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(R / "scripts"))
import optimizer

SLATES = ["dk_showdown_wk1_Den_KC_14Sep2026", "dk_showdown_wk2_Ind_KC_20Sep2026"]

def exposure(pool, noise, n=60, seed=7):
    rng = np.random.default_rng(seed)
    pool = pool[pool.final_projection > 0].copy()
    prev, cnt = [], {}
    for _ in range(n):
        opt = optimizer.randomize_showdown_projections(pool, noise, rng)
        sel = optimizer.solve_showdown_lineup(pool, "dk", previous_player_sets=prev, uniqueness=1,
                                               optimization_projection=opt)
        prev.append(set(sel.player_id))
        for k in sel[optimizer.ROW_KEY_COL]:
            cnt[k] = cnt.get(k, 0) + 1
    return pd.Series(cnt, dtype=float) / n * 100

def build(slate, noises=(15, 30, 50)):
    pool = optimizer.load_showdown_pool("dk", slate)
    for nz in noises:
        pool[f"exp{nz}"] = pool[optimizer.ROW_KEY_COL].map(exposure(pool, nz)).fillna(0.0)
    log = pd.read_csv(R / "data/ownership_actual_log.csv")
    log = log[log.slate_id == slate][["player_id", "roster_role", "actual_ownership_pct"]]
    pool = pool.merge(log, on=["player_id", "roster_role"], how="left")
    pool["own"] = pool.actual_ownership_pct.fillna(0.0)  # logged table is truncated at ~0.02%
    pool["slate"] = slate
    return pool

if __name__ == "__main__":
    out = pd.concat([build(s) for s in SLATES])
    out.to_csv(R / "analysis/showdown_own/dataset.csv", index=False)
    print(out.shape)
