"""Tests HANDOFF_dfs_army_variables.md's V3a: Greg's DFS Army rule that DST
should be the cheapest viable play (defense upside is capped, so pay up
elsewhere) rather than whatever the solver's raw point-maximization prefers.

Generates a SECOND candidate pool per slate with `best_lineup_classic.score(...,
cheapest_dst_only=True)` -- restricts OUR OWN candidate generation to the single
cheapest-salary DST via excluded_player_ids (the real opposing field is left
alone; it played whatever DSTs it actually did) -- and compares to the default
(DST chosen freely by the solver) under the winning selection rule found in
replay_selection_criteria.py (`worst_top25_realstack`).

usage: python analysis/classic_diag/replay_v3a_cheap_dst.py [n_candidates] [field_n] [n_sims]
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


def pick_and_grade(out, masks, P, fpts_map, real_points):
    real_stack_mask = out["is_real_stack"].to_numpy()
    v = np.where(real_stack_mask, out["worst_top25"].to_numpy(), -np.inf)
    idx = int(v.argmax())
    names = P.player_name.iloc[masks[idx]].tolist()
    ks = [rv.norm(n) for n in names]
    g = rv.grade(ks, fpts_map, real_points)
    dst_name = [n for n, p in zip(names, P.position.iloc[masks[idx]]) if p == "DST"]
    return dict(cash=g["cash"], pct=g["pct"], n_pool=len(masks),
                n_real_stack=int(real_stack_mask.sum()), dst=dst_name[0] if dst_name else None)


def main():
    rows = []
    for lab, (f, sid) in rv.SLATES.items():
        t0 = time.time()
        fpts_map, real_own_map, real_points, mine = rv.load_real(f)
        row = dict(slate=lab)
        for key, kwargs in (("default", {}), ("cheap_dst", {"cheapest_dst_only": True}),
                            ("cheap_viable_dst", {"cheapest_viable_dst_only": True})):
            try:
                out, masks, P = blc.score(
                    "dk", sid, n_candidates=N_CAND, field_n=FIELD_N, n_sims=N_SIMS, seed=3,
                    return_detail=True, **kwargs,
                )
            except Exception as exc:
                print(f"{lab}/{key}: failed ({type(exc).__name__}: {exc})", file=sys.stderr)
                continue
            g = pick_and_grade(out, masks, P, fpts_map, real_points)
            row[f"{key}_cash"] = g["cash"]
            row[f"{key}_pct"] = g["pct"]
            row[f"{key}_n_pool"] = g["n_pool"]
            row[f"{key}_dst"] = g["dst"]
        row["runtime_s"] = round(time.time() - t0)
        if mine:
            row["arm1_cash"] = mine["cash"]
            row["arm1_pct"] = mine["pct"]
        rows.append(row)
        print(f"{lab}: done in {row['runtime_s']}s -- "
              f"default pct={row.get('default_pct'):.3f} cash={row.get('default_cash')} dst={row.get('default_dst')} | "
              f"cheap_dst pct={row.get('cheap_dst_pct'):.3f} cash={row.get('cheap_dst_cash')} dst={row.get('cheap_dst_dst')} | "
              f"cheap_viable_dst pct={row.get('cheap_viable_dst_pct'):.3f} cash={row.get('cheap_viable_dst_cash')} dst={row.get('cheap_viable_dst_dst')}")

    out_df = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print("\n" + out_df.to_string(index=False))

    for key in ("default", "cheap_dst", "cheap_viable_dst"):
        cashes = out_df[f"{key}_cash"].sum()
        mean_pct = out_df[f"{key}_pct"].mean()
        print(f"\n{key}: {cashes}/{len(out_df)} cash, mean pctile {mean_pct:.3f}")

    out_df.to_csv("analysis/classic_diag/replay_v3a_cheap_dst_results.csv", index=False)


if __name__ == "__main__":
    main()
