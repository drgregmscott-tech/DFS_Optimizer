"""V3 of the live (pre-lock) chalk-anchor + pivot test. v2 found the
ownership-driven pivot layer added ZERO value on top of the
worst_top25_realstack anchor across all 6 slates (pivot never beat the
anchor) -- but v2's best_alt_per_slot() swapped for ANY alternative with
lower estimated_ownership_pct than the CURRENT slot's own player, even a
marginal edge (e.g. 18% vs. 22%). That is not what Greg's cited DFS Army
finding actually describes: their criterion was an ABSOLUTE threshold --
winning lineups typically carried >= 2 RB/WR/TE players under 10% ownership,
not "somewhat lower than whoever they're next to." This version tests that
literal criterion instead of the relative one, on top of the SAME
already-validated worst_top25_realstack anchor v2 used, before concluding
the live pivot layer itself doesn't work.

usage: python analysis/classic_diag/pivot_off_chalk_live_v3.py [n_sims] [field_n] [n_candidates] [own_threshold_pct]
"""
import itertools
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import replay_validation as rv
import best_lineup_classic as blc
from pivot_off_chalk_live import enumerate_pivots, score_masks

N_SIMS = int(sys.argv[1]) if len(sys.argv) > 1 else 800
FIELD_N = int(sys.argv[2]) if len(sys.argv) > 2 else 6000
N_CAND = int(sys.argv[3]) if len(sys.argv) > 3 else 80
OWN_THRESHOLD = float(sys.argv[4]) if len(sys.argv) > 4 else 10.0
SWAPPABLE_POS = {"RB", "WR", "TE"}


def best_alt_per_slot_absolute(P, mask, own_threshold):
    """DFS Army's literal criterion: a genuine leverage candidate is under
    own_threshold% estimated ownership outright -- NOT just lower than the
    anchor's own player at that slot (v2's relative version). Among
    same-position players under the threshold, not already in the mask,
    picks the single best-projected one per slot -- same "best of the
    eligible pool" shape as every prior version, only the eligibility rule
    changed."""
    alts = {}
    for i in mask:
        pos = P.position.iloc[i]
        if pos not in SWAPPABLE_POS:
            continue
        pool = P[(P.position == pos) & (~P.index.isin(mask)) & (P["own"] < own_threshold)].copy()
        pool = pool.sort_values("final_projection", ascending=False)
        if len(pool):
            alts[i] = pool.index[0]
    return alts


def main():
    rows = []
    for lab, (f, sid) in rv.SLATES.items():
        t0 = time.time()
        fpts_map, real_own_map, real_points, mine = rv.load_real(f)

        try:
            out, masks, P = blc.score(
                "dk", sid, n_candidates=N_CAND, field_n=FIELD_N, n_sims=N_SIMS, seed=3,
                return_detail=True,
            )
        except Exception as exc:
            print(f"{lab}: candidate pool build failed ({type(exc).__name__}: {exc})", file=sys.stderr)
            continue
        P["k"] = P.player_name.map(rv.norm)

        real_stack_mask = out["is_real_stack"].to_numpy()
        worst25_pool = out["worst_top25"].to_numpy()
        v = np.where(real_stack_mask, worst25_pool, -np.inf)
        anchor_idx = int(v.argmax())
        mask = masks[anchor_idx]

        anchor_ks = [P["k"].iloc[i] for i in mask]
        g_anchor = rv.grade(anchor_ks, fpts_map, real_points)
        anchor_total_own = float(P["own"].iloc[mask].sum())
        n_anchor_sub10 = int((P["own"].iloc[mask] < OWN_THRESHOLD).sum())

        _, field = blc.build_pool_and_field("dk", sid, field_n=FIELD_N, seed=3)

        alts = best_alt_per_slot_absolute(P, mask, OWN_THRESHOLD)
        combos = list(enumerate_pivots(P, mask, alts))
        all_masks = [mask] + [c[0] for c in combos]
        for m in all_masks:
            assert len(set(m.tolist())) == len(m), f"{lab}: duplicate player in a candidate mask -- roster-legality bug"
        avg25, worst25 = score_masks(P, field, all_masks, N_SIMS, seed=3)

        best_idx = int(worst25.argmax())
        best_mask = all_masks[best_idx]
        best_ks = [P["k"].iloc[i] for i in best_mask]
        g_best = rv.grade(best_ks, fpts_map, real_points)
        best_total_own = float(P["own"].iloc[best_mask].sum())
        n_best_sub10 = int((P["own"].iloc[best_mask] < OWN_THRESHOLD).sum())
        is_anchor = (best_idx == 0)

        row = dict(slate=lab, n_swappable_alts=len(alts), n_pivots=len(combos),
                   anchor_cash=g_anchor["cash"], anchor_pct=g_anchor["pct"],
                   anchor_total_own=anchor_total_own, anchor_n_sub10=n_anchor_sub10,
                   best_cash=g_best["cash"], best_pct=g_best["pct"],
                   best_worst25=worst25[best_idx], best_is_anchor=is_anchor,
                   best_total_own=best_total_own, best_n_sub10=n_best_sub10,
                   runtime_s=round(time.time() - t0))
        if mine:
            row["arm1_cash"] = mine["cash"]
            row["arm1_pct"] = mine["pct"]
        rows.append(row)
        if not is_anchor:
            _, out_names, in_names = combos[best_idx - 1]
            print(f"{lab}: pivot swap chosen -- OUT {out_names} / IN {in_names}")
        print(f"{lab}: done in {row['runtime_s']}s ({len(alts)} slots had a sub-{OWN_THRESHOLD:.0f}% alt, "
              f"{len(combos)} legal pivots) -- "
              f"anchor pct={g_anchor['pct']:.3f} cash={g_anchor['cash']} "
              f"(total_own={anchor_total_own:.0f}%, {n_anchor_sub10} already sub-{OWN_THRESHOLD:.0f}%) | "
              f"best pct={g_best['pct']:.3f} cash={g_best['cash']} (worst25={worst25[best_idx]:.3f}, "
              f"total_own={best_total_own:.0f}%, {n_best_sub10} sub-{OWN_THRESHOLD:.0f}%) "
              f"{'[= anchor]' if is_anchor else '[PIVOT]'}")

    out_df = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print("\n" + out_df.to_string(index=False))
    print(f"\nlive anchor (worst_top25_realstack pick): {out_df.anchor_cash.sum()}/{len(out_df)} cash, "
          f"mean pctile {out_df.anchor_pct.mean():.3f}")
    print(f"live best (anchor or absolute-threshold pivot): {out_df.best_cash.sum()}/{len(out_df)} cash, "
          f"mean pctile {out_df.best_pct.mean():.3f}, mean total_own {out_df.best_total_own.mean():.0f}%")
    print(f"pivot beat anchor on {(~out_df.best_is_anchor).sum()}/{len(out_df)} slates")
    print("\ncompare to v2 (relative-threshold pivot, same anchor): 3/6 cash, mean pctile 0.703, pivot beat anchor 0/6")
    print("compare to pivot_off_chalk.py's REAL-ownership anchor+pivot (upper bound, ground truth): 4/6 cash, mean pctile 0.819")

    out_df.to_csv("analysis/classic_diag/pivot_off_chalk_live_v3_results.csv", index=False)


if __name__ == "__main__":
    main()
