"""Isolates whether Arm 3's SELECTION RULE (rank candidates by average
simulated P(top-10%)) is the weak link, independent of candidate generation
or field simulation -- flagged as the priority open question in
HANDOFF_classic_construction_replay.md section 3 after Arm 3's replay showed
real but inconsistent gains (2/6 cash, better on 4/6 slates, worse on 2/6,
and didn't improve with a bigger candidate pool).

Method: generate ONE candidate pool + scenario-score table per slate via
best_lineup_classic.score(..., return_detail=True) -- the exact same call
replay_arm3.py's pick_top() makes internally -- then pick from that SAME pool
by five different rules and grade each against real results:
  (a) avg_top10   -- the existing Arm 3 rule (average P(top-10%) across scenarios)
  (b) raw_proj    -- highest total projected points in the pool (no simulation at all)
  (c) worst_top10 -- highest worst-case P(top-10%) across scenarios (the
      robustness metric the code already computes but never uses for selection)
  (d) avg_top25   -- average P(top-25%), added 2026-09-22: (a)/(c) target a GPP-style
      ceiling (top-10%) that was never actually the SE3max cash line (top-25%,
      CASH_PCT=0.25 elsewhere in this codebase) -- this rule targets the real line
  (e) worst_top25 -- worst-case P(top-25%) across scenarios
Holding candidate generation and field simulation fixed isolates the ranking
RULE as the only thing that varies between (a)-(e).

Stack-restricted follow-up (added 2026-09-22): raw_proj AND avg_top25 both
independently picked the IDENTICAL unstacked, single-bust-vulnerable candidate
on wk2_early (an 8.5th-percentile disaster vs. 65.8th for the stack-respecting
avg_top10 pick on the same slate) -- confirming the failure is in the
CANDIDATE POOL (an unstacked solve can look artificially good under a
limited-sample Monte Carlo, on any percentile-based metric), not the ranking
rule alone. A first cut (`*_stackonly`, restricting to `is_stack_forced` --
candidates from the explicit stack-generation loop) fixed that but cost
wk2_main (cash->miss), because origin-based tagging excluded a legitimately
good, apparently-correlated wk2_main candidate that happened to come from the
unconstrained noise loop. A structure-based attempt (`*_realstack`, QB + >=1
same-team WR/TE, regardless of generation origin) was tried and TESTED WORSE
than origin-tagging (2-3/6 cash vs. 4/6) -- ">=1 teammate" turned out to be
too weak a bar: 60-90 of ~120 candidates in every pool passed it anyway
(good players cluster on good offenses even in unconstrained noise solves),
so it barely filtered anything and let back in weakly-correlated candidates.
The real explanation for why origin-tagging worked: that loop doesn't just
add "a" correlation, it enforces the exact VALIDATED structure (stack_size=2
AND bring_back=True). **`*_validated` variants (added 2026-09-22)** restrict
argmax to `is_validated_stack` (best_lineup_classic.has_real_stack(...,
min_teammates=2, min_bringback=1)) -- checked on the roster itself but
matching the full validated structure, not just "any" correlation. Should
match or beat origin-tagging's 4/6 while also being generation-source-blind
(so it can rescue a genuinely well-structured noise-loop candidate like
wk2_main's, which neither prior attempt managed).

usage: python analysis/classic_diag/replay_selection_criteria.py [n_candidates] [field_n] [n_sims]
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
            print(f"{lab}: failed ({type(exc).__name__}: {exc})", file=sys.stderr)
            continue

        proj = P.final_projection.to_numpy(float)
        raw_proj = np.array([proj[m].sum() for m in masks])
        real_stack_mask = out["is_real_stack"].to_numpy()
        validated_mask = out["is_validated_stack"].to_numpy()
        stack_forced_mask = out["is_stack_forced"].to_numpy()
        n_real_stack = int(real_stack_mask.sum())
        n_validated = int(validated_mask.sum())
        n_stack_forced = int(stack_forced_mask.sum())

        # floor_sum: sum of each roster's own already-computed statline_p10
        # (a calibrated floor estimate, not a new model) across its 9 slots.
        # Added 2026-09-22 in response to HANDOFF_dfs_army_variables.md's V4
        # ("FLEX should be a real target-volume player, because DK is
        # full-PPR and target-hogs carry more floor") -- rather than proxy
        # that with proj_targets/proj_rec on the FLEX slot alone, this tests
        # the more direct and already-available claim: does explicitly
        # selecting for LINEUP-WIDE floor (not mean projection) pick a
        # better SE3max candidate? statline_p10 already reflects each
        # player's own volume/role (a target hog's p10 is higher relative
        # to its mean than a boom/bust player's), so this subsumes V4's
        # target-share idea rather than duplicating it as a separate test.
        floor_sum = np.array([P.statline_p10.to_numpy(float)[m].sum() for m in masks])

        def argmax_restricted(values, mask):
            v = np.where(mask, values, -np.inf)
            return int(v.argmax())

        picks = {
            "avg_top10": int(out["avg_top10"].to_numpy().argmax()),
            "raw_proj": int(raw_proj.argmax()),
            "worst_top10": int(out["worst_top10"].to_numpy().argmax()),
            "avg_top25": int(out["avg_top25"].to_numpy().argmax()),
            "worst_top25": int(out["worst_top25"].to_numpy().argmax()),
            "raw_proj_realstack": argmax_restricted(raw_proj, real_stack_mask),
            "avg_top25_realstack": argmax_restricted(out["avg_top25"].to_numpy(), real_stack_mask),
            "worst_top25_realstack": argmax_restricted(out["worst_top25"].to_numpy(), real_stack_mask),
            "raw_proj_validated": argmax_restricted(raw_proj, validated_mask),
            "avg_top25_validated": argmax_restricted(out["avg_top25"].to_numpy(), validated_mask),
            "worst_top25_validated": argmax_restricted(out["worst_top25"].to_numpy(), validated_mask),
            "floor_sum": int(floor_sum.argmax()),
            "floor_sum_validated": argmax_restricted(floor_sum, validated_mask),
            # *_stackonly: reconstructs the ORIGINAL origin-based restriction
            # (HANDOFF_week3_lineup_system.md section 3) against the CURRENT
            # candidate pool/scenario code, to check whether the old "4/6,
            # 0.709" result reproduces here or was an artifact of code since
            # superseded. is_stack_forced was already being computed and
            # returned by candidates()/score() (see best_lineup_classic.py)
            # but not used as a selection mask since *_realstack/*_validated
            # replaced it -- this just re-adds the mask, no new computation.
            "worst_top25_stackonly": argmax_restricted(out["worst_top25"].to_numpy(), stack_forced_mask),
            "avg_top25_stackonly": argmax_restricted(out["avg_top25"].to_numpy(), stack_forced_mask),
        }

        row = dict(slate=lab, n_pool=len(masks), n_real_stack=n_real_stack, n_validated=n_validated,
                   runtime_s=round(time.time() - t0))
        for rule, idx in picks.items():
            names = P.player_name.iloc[masks[idx]].tolist()
            ks = [rv.norm(n) for n in names]
            g = rv.grade(ks, fpts_map, real_points)
            row[f"{rule}_cash"] = g["cash"]
            row[f"{rule}_pct"] = g["pct"]
            row[f"{rule}_avg_top10"] = out["avg_top10"].iloc[idx]
            row[f"{rule}_worst_top10"] = out["worst_top10"].iloc[idx]
            row[f"{rule}_avg_top25"] = out["avg_top25"].iloc[idx]
            row[f"{rule}_worst_top25"] = out["worst_top25"].iloc[idx]
            row[f"{rule}_raw_proj"] = raw_proj[idx]
            row[f"{rule}_same_lineup_as_avg_top10"] = (idx == picks["avg_top10"])
        if mine:
            row["arm1_cash"] = mine["cash"]
            row["arm1_pct"] = mine["pct"]
        rows.append(row)
        print(f"{lab}: done in {row['runtime_s']}s ({n_real_stack}/{len(masks)} real-stack, "
              f"{n_validated}/{len(masks)} validated-stack) -- "
              f"avg_top10 pct={row['avg_top10_pct']:.3f} cash={row['avg_top10_cash']} | "
              f"avg_top25 pct={row['avg_top25_pct']:.3f} cash={row['avg_top25_cash']} | "
              f"avg_top25_realstack pct={row['avg_top25_realstack_pct']:.3f} cash={row['avg_top25_realstack_cash']} | "
              f"avg_top25_validated pct={row['avg_top25_validated_pct']:.3f} cash={row['avg_top25_validated_cash']} | "
              f"worst_top25_validated pct={row['worst_top25_validated_pct']:.3f} cash={row['worst_top25_validated_cash']}")

    out_df = pd.DataFrame(rows)
    pd.set_option("display.width", 240)
    print("\n" + out_df.to_string(index=False))

    for rule in ("avg_top10", "raw_proj", "worst_top10", "avg_top25", "worst_top25",
                 "raw_proj_realstack", "avg_top25_realstack", "worst_top25_realstack",
                 "raw_proj_validated", "avg_top25_validated", "worst_top25_validated",
                 "floor_sum", "floor_sum_validated",
                 "worst_top25_stackonly", "avg_top25_stackonly"):
        cashes = out_df[f"{rule}_cash"].sum()
        mean_pct = out_df[f"{rule}_pct"].mean()
        n_same = out_df[f"{rule}_same_lineup_as_avg_top10"].sum()
        print(f"\n{rule}: {cashes}/{len(out_df)} cash, mean pctile {mean_pct:.3f}, "
              f"identical to avg_top10's pick on {n_same}/{len(out_df)} slates")

    out_df.to_csv("analysis/classic_diag/replay_selection_criteria_results.csv", index=False)


if __name__ == "__main__":
    main()
