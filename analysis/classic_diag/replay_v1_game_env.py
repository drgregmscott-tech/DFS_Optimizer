"""Tests HANDOFF_dfs_army_variables.md's V1: Greg's DFS Army rule that QB/stack
selection should target the best GAME ENVIRONMENT (implied team total), not just
the best-projected QB. `best_lineup_classic.candidates()` already forces stacks
onto the `top_teams` best teams -- historically ranked by QB `final_projection`.
This script generates a SECOND candidate pool per slate ranking those teams by
`implied_total` instead, and compares the two pools under the winning selection
rule found in replay_selection_criteria.py (`worst_top25_realstack`: worst-case
P(top-25%) across scenarios, restricted to candidates with a real QB+teammate+
bring-back structure on the roster -- 3/6 cash, mean pctile 0.703, the best of
11 rules tested there).

Caveat established before running this: QB final_projection and implied_total
are already strongly rank-correlated (~0.83-0.93 across the 6 logged slates), so
this is a test of a real but likely modest reordering of which teams get
stack-forced, not an independent-from-scratch signal.

usage: python analysis/classic_diag/replay_v1_game_env.py [n_candidates] [field_n] [n_sims]
"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import replay_validation as rv
import best_lineup_classic as blc

N_CAND = int(sys.argv[1]) if len(sys.argv) > 1 else 80
FIELD_N = int(sys.argv[2]) if len(sys.argv) > 2 else 6000
N_SIMS = int(sys.argv[3]) if len(sys.argv) > 3 else 800


def pick_and_grade(out, masks, P, fpts_map, real_points, label):
    real_stack_mask = out["is_real_stack"].to_numpy()
    v = np.where(real_stack_mask, out["worst_top25"].to_numpy(), -np.inf)
    idx = int(v.argmax())
    names = P.player_name.iloc[masks[idx]].tolist()
    ks = [rv.norm(n) for n in names]
    g = rv.grade(ks, fpts_map, real_points)
    return dict(cash=g["cash"], pct=g["pct"], n_pool=len(masks),
                n_real_stack=int(real_stack_mask.sum()))


def main():
    rows = []
    for lab, (f, sid) in rv.SLATES.items():
        t0 = time.time()
        fpts_map, real_own_map, real_points, mine = rv.load_real(f)
        row = dict(slate=lab)
        for key in ("proj", "implied_total"):
            try:
                out, masks, P = blc.score(
                    "dk", sid, n_candidates=N_CAND, field_n=FIELD_N, n_sims=N_SIMS, seed=3,
                    return_detail=True, team_rank_key=key,
                )
            except Exception as exc:
                print(f"{lab}/{key}: failed ({type(exc).__name__}: {exc})", file=sys.stderr)
                continue
            g = pick_and_grade(out, masks, P, fpts_map, real_points, key)
            row[f"{key}_cash"] = g["cash"]
            row[f"{key}_pct"] = g["pct"]
            row[f"{key}_n_pool"] = g["n_pool"]
            row[f"{key}_n_real_stack"] = g["n_real_stack"]
        row["runtime_s"] = round(time.time() - t0)
        if mine:
            row["arm1_cash"] = mine["cash"]
            row["arm1_pct"] = mine["pct"]
        rows.append(row)
        print(f"{lab}: done in {row['runtime_s']}s -- "
              f"proj pct={row.get('proj_pct'):.3f} cash={row.get('proj_cash')} | "
              f"implied_total pct={row.get('implied_total_pct'):.3f} cash={row.get('implied_total_cash')}")

    out_df = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print("\n" + out_df.to_string(index=False))

    for key in ("proj", "implied_total"):
        cashes = out_df[f"{key}_cash"].sum()
        mean_pct = out_df[f"{key}_pct"].mean()
        print(f"\n{key}: {cashes}/{len(out_df)} cash, mean pctile {mean_pct:.3f}")

    out_df.to_csv("analysis/classic_diag/replay_v1_game_env_results.csv", index=False)


if __name__ == "__main__":
    main()
