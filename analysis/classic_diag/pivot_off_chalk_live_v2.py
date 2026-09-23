"""V2 of the live (pre-lock) chalk-anchor + pivot test. Found via
pivot_off_chalk_live.py's own results, 2026-09-23: fixing the anchor from a
pure-ownership-max solve to a quality-first single deterministic solve
improved things (2/6 -> still 2/6 cash, but mean pctile 0.585 -> 0.610, and
total lineup ownership landed in a much saner range vs. the DFS Army 126%
winning-lineup norm) -- but the ownership-driven PIVOT layer added zero value
on all 6 slates (worst_top25 never preferred a swap over the anchor), and the
single-deterministic-solve anchor itself still trailed the already-validated,
fully ownership-independent `worst_top25_realstack` method (3/6 cash, 0.703
mean pctile -- see replay_selection_criteria.py) built from a POOL of 80+
Monte-Carlo-scored candidates, not one direct solve.

This version combines the two already-separately-proven pieces instead of
inventing a third: the anchor is now the `worst_top25_realstack` pick itself
(the strongest ownership-independent, already-validated single-lineup
method), and the SAME ownership-driven same-position-swap pivot layer from
pivot_off_chalk_live.py is applied on top of THAT anchor, scored the same
way. This directly tests DFS Army's two-step framing ("build the lineup you
think can win first [[here: the validated worst_top25_realstack pick]], then
find 2-3 places to get away from the field [[here: live-ownership pivots]]")
using only pieces already independently proven on real data, rather than
inventing new anchor-construction logic a third time.

usage: python analysis/classic_diag/pivot_off_chalk_live_v2.py [n_sims] [field_n] [n_candidates]
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
from pivot_off_chalk_live import best_alt_per_slot, enumerate_pivots, score_masks

N_SIMS = int(sys.argv[1]) if len(sys.argv) > 1 else 800
FIELD_N = int(sys.argv[2]) if len(sys.argv) > 2 else 6000
N_CAND = int(sys.argv[3]) if len(sys.argv) > 3 else 80


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
        anchor_worst25_pool_score = float(worst25_pool[anchor_idx])

        # Rebuild field deterministically (same seed=3 build_pool_and_field
        # used inside blc.score() above) so the pivot combos below are
        # scored against the identical simulated field the anchor's own
        # worst_top25 (above) was measured against.
        _, field = blc.build_pool_and_field("dk", sid, field_n=FIELD_N, seed=3)

        alts = best_alt_per_slot(P, mask)
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
        is_anchor = (best_idx == 0)

        row = dict(slate=lab, n_pool=len(masks), n_real_stack=int(real_stack_mask.sum()),
                   n_pivots=len(combos),
                   anchor_cash=g_anchor["cash"], anchor_pct=g_anchor["pct"],
                   anchor_worst25_repro=worst25[0], anchor_worst25_pool=anchor_worst25_pool_score,
                   anchor_total_own=anchor_total_own,
                   best_cash=g_best["cash"], best_pct=g_best["pct"],
                   best_worst25=worst25[best_idx], best_is_anchor=is_anchor,
                   best_total_own=best_total_own,
                   runtime_s=round(time.time() - t0))
        if mine:
            row["arm1_cash"] = mine["cash"]
            row["arm1_pct"] = mine["pct"]
        rows.append(row)
        if not is_anchor:
            _, out_names, in_names = combos[best_idx - 1]
            print(f"{lab}: pivot swap chosen -- OUT {out_names} / IN {in_names}")
        print(f"{lab}: done in {row['runtime_s']}s ({len(combos)} legal pivots, "
              f"anchor pool-score worst25={anchor_worst25_pool_score:.3f} vs. field-rebuild worst25={worst25[0]:.3f}) -- "
              f"anchor pct={g_anchor['pct']:.3f} cash={g_anchor['cash']} (total_own={anchor_total_own:.0f}%) | "
              f"best pct={g_best['pct']:.3f} cash={g_best['cash']} (worst25={worst25[best_idx]:.3f}, "
              f"total_own={best_total_own:.0f}%) "
              f"{'[= anchor]' if is_anchor else '[PIVOT]'}")

    out_df = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print("\n" + out_df.to_string(index=False))
    print(f"\nlive anchor (worst_top25_realstack pick): {out_df.anchor_cash.sum()}/{len(out_df)} cash, "
          f"mean pctile {out_df.anchor_pct.mean():.3f}, mean total_own {out_df.anchor_total_own.mean():.0f}%")
    print(f"live best (anchor or pivot): {out_df.best_cash.sum()}/{len(out_df)} cash, "
          f"mean pctile {out_df.best_pct.mean():.3f}, mean total_own {out_df.best_total_own.mean():.0f}%")
    print(f"pivot beat anchor on {(~out_df.best_is_anchor).sum()}/{len(out_df)} slates")
    print("\ncompare to worst_top25_realstack alone (no live-ownership pivot layer): 3/6 cash, mean pctile 0.703")
    print("compare to pivot_off_chalk.py's REAL-ownership anchor+pivot (upper bound, uses ground truth): 4/6 cash, mean pctile 0.819")
    print("compare to v1 live attempt (quality-first single-solve anchor, buggy ownership-max anchor before that): 2/6 cash, 0.610 / 2/6 cash, 0.585")

    out_df.to_csv("analysis/classic_diag/pivot_off_chalk_live_v2_results.csv", index=False)


if __name__ == "__main__":
    main()
