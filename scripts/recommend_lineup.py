"""
recommend_lineup.py
====================

Week 3+ live lineup recommender -- ships the ONE piece of the 2026-09-22/23
lineup-system investigation that's actually validated end-to-end for live
(pre-lock) use: `worst_top25_realstack`, the strongest ownership-INDEPENDENT
selection rule tested against 6 real logged SE3max slates (3/6 cash, mean
percentile 0.703 -- see HANDOFF_week3_lineup_system.md).

TRACK-RECORD CORRECTION (2026-09-23 ownership/projection review): the
3/6, 0.703 figure was measured on the ORIGINAL (pre-projection-fix)
projections. Re-scored on projections rebuilt with the reconcile_team_shares
fix (leak-free, same 6 slates, same scoring harness -- reproduced the old
numbers exactly before trusting the new ones; see
analysis/classic_diag/pivot_rerun_corrected_ownership.py) this rule cashes
1/6 with mean percentile 0.583 (95% interval 0.47-0.73), identical across
3 seeds. With n=6 that is not proof it is worse than any alternative --
the alternatives tested are statistically indistinguishable -- but it means
"3/6, 0.703" should NOT be read as a demonstrated edge. Treat this script's
output as a reasonable, ownership-free, stack-aware pick, not a validated
cashing method. Whether the projection fix or noise caused the drop is under
review (analysis/proj_recheck/).

WHY THIS RULE AND NOT THE STRONGER ONE: the chalk-anchor + ownership-driven
pivot method tested stronger on paper (4/6 cash, 0.819) but ONLY using real
post-lock ownership data, which doesn't exist before a slate locks. Three
separate attempts to substitute the model's own estimated_ownership_pct for
that real signal (analysis/classic_diag/pivot_off_chalk_live.py, _v2, _v3)
each showed the live-ownership pivot layer adding ZERO value over the plain
anchor across all 6 slates, regardless of anchor construction or pivot
eligibility threshold -- a consistent result, not a one-off. Greg's own call
(2026-09-23): ship the proven, ownership-independent piece now for Week 3,
keep the ownership-driven pivot/leverage layer OFF until projection/
ownership model accuracy improves enough to earn it back. Do not add a pivot
step to this script without a new real-data validation matching the rigor
of the tests above -- see HANDOFF_week3_lineup_system.md for the full
investigation trail before changing this.

WHAT IT DOES: builds a real, live candidate pool (unconstrained noise solves
+ QB-stack-forced solves, best_lineup_classic.candidates()) against the
current final_projections_{site}_{slate_id}.csv, scores every candidate
against a simulated field across 4 correlated Monte Carlo scenarios
(best_lineup_classic.SCENARIOS), and picks the single lineup with the best
WORST-CASE probability of finishing top-25% of the field (the real SE3max
cash line), restricted to candidates with a real QB + >=1 same-team WR/TE
structure (is_real_stack) -- exactly the already-validated
worst_top25_realstack rule, no new construction logic here.

Reuses analysis/classic_diag/best_lineup_classic.py's score() directly
rather than re-implementing it -- that file is the validated source of
truth for this Monte Carlo machinery (see
analysis/classic_diag/replay_selection_criteria.py, which is what produced
the 3/6/0.703 number this script is shipping). Importing across the
scripts/ <-> analysis/classic_diag/ boundary is a deliberate choice to avoid
a second, silently-drifting copy of ~300 lines of validated scenario/field
simulation code -- not an oversight.

PERFORMANCE: 15-220s per slate at the defaults (n_candidates=80,
field_n=6000, n_sims=800 -- same as every real test this session), same
order of magnitude as pivot_finder.py's existing batch step. Intended to run
as a scheduled/dispatched batch step (see refresh_data.yml), writing a
static CSV for the frontend to read -- NOT triggered live per click.

UNLIKE pivot_finder.py, this script has NO dependency on a lineup already
being built (lineups_multi_*.csv / lineup_single_*.csv) -- it only needs
final_projections_{site}_{slate_id}.csv, so it can run the moment that file
is fresh, independent of whether "Build Lineups" has ever been clicked for
this slate.

Usage:
    python3 scripts/recommend_lineup.py --site dk --slate-id classic_wk3
    python3 scripts/recommend_lineup.py --site dk --slate-id classic_wk3 \
        --n-candidates 80 --field-n 6000 --n-sims 800 --seed 3

Output:
    output/recommended_lineup_{site}_{slate_id}.csv
    One row per rostered player, for up to TOP_N ranked lineups stacked
    together (same per-player schema as lineup_single_{site}_{slate_id}.csv
    / lineups_multi_{site}_{slate_id}.csv -- roster_slot, player_id,
    player_name, position, team, salary, projection, value, opponent,
    site_player_id, sigma, sigma_source), PLUS lineup-level provenance
    columns repeated on every row of a given lineup so a downstream reader
    can verify what produced it without cross-referencing anything else:
    method, recommendation_rank, worst_top25_score, avg_top25_score,
    score_gap_from_best, n_candidates_in_pool, n_real_stack_in_pool,
    generated_at_utc.

    2026-09-23 addition -- TOP_N=3, not just the #1 pick. Greg's own framing
    for why: NOT "3 options to submit" (he plays single-entry -- see
    HANDOFF_week3_lineup_system.md) and NOT "pick whichever feels right"
    (his own real submitted lineups, graded against the same 6 logged
    slates every method here was tested against, scored 0/6 cash, 0.367
    mean percentile -- worse than every systematic method tested, including
    this one at 3/6, 0.703, so free-form deviation from the model has no
    supporting evidence). The actual point is MARGIN/CONFIDENCE: since the
    full candidate pool is already scored for the #1 pick, showing #2/#3
    and their score_gap_from_best is nearly free and tells you whether the
    #1 pick is well-separated from the field (a real, confident edge) or a
    close call against near-identical alternatives (little separation) --
    information worth having either way, independent of whether you ever
    deviate. rank 1 is still THE recommendation; 2/3 are context, not a menu.
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "output"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "analysis" / "classic_diag"))
sys.path.insert(0, str(REPO_ROOT / "analysis" / "showdown_own"))
import optimizer  # noqa: E402
import best_lineup_classic as blc  # noqa: E402
import best_single as bs  # noqa: E402
from ingest_salaries import SITE_CONFIGS  # noqa: E402

METHOD_TAG = "worst_top25_realstack_v1"
METHOD_TAG_SHOWDOWN = "worst_top10_showdown_v1"
TOP_N = 3


def recommend_lineup(site: str, slate_id: str, n_candidates: int = 80,
                      field_n: int = 6000, n_sims: int = 800, seed: int = 3,
                      top_n: int = TOP_N):
    """Returns a DataFrame of up to `top_n` ranked lineups stacked together
    (see module docstring's Output section) -- rank 1 is THE recommendation;
    2/3 are margin/confidence context, not alternate options to pick from.
    Dispatches to the classic or Showdown implementation below based on the
    slate's own `slate_format`."""
    proj_path = OUTPUT_DIR / f"final_projections_{site}_{slate_id}.csv"
    is_showdown = False
    if proj_path.exists():
        probe = pd.read_csv(proj_path, usecols=lambda c: c == "slate_format", nrows=1000)
        is_showdown = optimizer.is_showdown_pool(probe)
    if is_showdown:
        return _recommend_showdown(site, slate_id, n_candidates=n_candidates,
                                   field_n=field_n, n_sims=n_sims, seed=seed, top_n=top_n)
    return _recommend_classic(site, slate_id, n_candidates=n_candidates,
                              field_n=field_n, n_sims=n_sims, seed=seed, top_n=top_n)


def _recommend_classic(site: str, slate_id: str, n_candidates: int, field_n: int,
                       n_sims: int, seed: int, top_n: int):
    out, masks, P = blc.score(
        site, slate_id, n_candidates=n_candidates, field_n=field_n,
        n_sims=n_sims, seed=seed, return_detail=True,
    )

    real_stack_mask = out["is_real_stack"].to_numpy()
    n_real_stack = int(real_stack_mask.sum())
    if n_real_stack == 0:
        # Fails loudly rather than silently falling back to an unstacked
        # pick -- an unstacked, single-bust-vulnerable candidate is the
        # EXACT failure mode replay_selection_criteria.py's investigation
        # started from (see that file's own docstring). A real slate with
        # zero real-stack candidates in an 80+-candidate pool would be a
        # genuine anomaly worth a human looking at, not something to paper
        # over automatically.
        raise SystemExit(
            f"recommend_lineup: NO candidate in the {len(masks)}-lineup pool "
            f"for {site}/{slate_id} has a real QB+teammate stack "
            f"(is_real_stack) -- refusing to fall back to an unstacked pick. "
            f"Check final_projections_{site}_{slate_id}.csv and the "
            f"candidate-generation step (best_lineup_classic.candidates())."
        )

    worst25 = out["worst_top25"].to_numpy()
    v = np.where(real_stack_mask, worst25, -np.inf)
    # candidates() already dedupes the pool by frozenset(player_id) (see its
    # own docstring), so every ranked lineup below is a genuinely distinct
    # roster -- no risk of rank 2/3 silently repeating rank 1.
    ranked_idx = np.argsort(v)[::-1][:min(top_n, n_real_stack)]
    best_score = float(worst25[ranked_idx[0]])

    config = SITE_CONFIGS[site]
    fixed_counts, _flex_count = optimizer.parse_roster_requirements(config["roster_slots"])
    now = datetime.now(timezone.utc).isoformat()

    lineups = []
    for rank, idx in enumerate(ranked_idx, start=1):
        idx = int(idx)
        selected = P.iloc[masks[idx]].reset_index(drop=True)
        lineup = optimizer.assign_roster_slots(selected, fixed_counts)
        optimizer.validate_lineup(lineup, config["salary_cap"], config["roster_slots"])

        lineup["method"] = METHOD_TAG
        lineup["recommendation_rank"] = rank
        lineup["worst_top25_score"] = float(worst25[idx])
        lineup["avg_top25_score"] = float(out["avg_top25"].iloc[idx])
        lineup["score_gap_from_best"] = float(worst25[idx]) - best_score  # 0.0 for rank 1
        lineup["n_candidates_in_pool"] = len(masks)
        lineup["n_real_stack_in_pool"] = n_real_stack
        lineup["generated_at_utc"] = now
        lineups.append(lineup)

    return pd.concat(lineups, ignore_index=True)


def _recommend_showdown(site: str, slate_id: str, n_candidates: int, field_n: int,
                        n_sims: int, seed: int, top_n: int):
    """2026-09-23 addition. Uses analysis/showdown_own/best_single.score()
    (generalized the same session -- see that file's `candidates()`
    docstring) instead of best_lineup_classic.score(): a Showdown pool has
    two rows per player_id (CPT/FLEX), which the classic solver can't
    handle at all (see git history for the crash this replaced).

    Ranks by `worst_top10` (worst-case P(top-10%) across 4 correlated
    scenarios), NOT `worst_top25`/`is_real_stack` -- those are classic/
    SE3max-cash-line concepts with no Showdown analogue. Every real logged
    Showdown slate (data/ownership_actual_log.csv) is a real
    `single_entry_gpp` contest, so a GPP ceiling metric is the right target,
    and `worst_top10` specifically is what analysis/showdown_own/
    replay_showdown.py's real-data test (the 2 real Showdown slates with
    both real ownership and real logged results) found tied-or-best against
    every other rule tested, on both the realistic and idealized arms --
    see that file and best_single.score()'s own docstring for the numbers.

    No `is_real_stack`-equivalent restriction is applied: unlike classic,
    every Showdown candidate already structurally includes >=1 player from
    each team by construction (optimizer.solve_showdown_lineup()'s
    decision #41, min_per_team=1) -- there's no unstacked-candidate failure
    mode analogous to classic's to guard against here, and the replay found
    no evidence a further structural restriction was needed."""
    out, masks, P = bs.score(
        site, slate_id, n_candidates=n_candidates, n_forced=max(15, n_candidates // 4),
        field_n=field_n, n_sims=n_sims, seed=seed, return_detail=True,
    )

    worst10 = out["worst_top10"].to_numpy()
    ranked_idx = np.argsort(worst10)[::-1][:min(top_n, len(masks))]
    best_score = float(worst10[ranked_idx[0]])

    now = datetime.now(timezone.utc).isoformat()
    lineups = []
    for rank, idx in enumerate(ranked_idx, start=1):
        idx = int(idx)
        selected = P.iloc[masks[idx]].reset_index(drop=True)
        lineup = optimizer.assign_showdown_roster_slots(selected, site)
        optimizer.validate_showdown_lineup(lineup, site)

        lineup["method"] = METHOD_TAG_SHOWDOWN
        lineup["recommendation_rank"] = rank
        # Same column names as the classic branch (worst_top25_score/
        # avg_top25_score) so the output schema/frontend don't need to know
        # which contest format a given slate is -- populated with the
        # Showdown-appropriate P(top-10%) metric instead of P(top-25%),
        # per this function's own docstring. METHOD_TAG_SHOWDOWN in the
        # `method` column is what actually distinguishes the two.
        lineup["worst_top25_score"] = float(worst10[idx])
        lineup["avg_top25_score"] = float(out["avg_top10"].iloc[idx])
        lineup["score_gap_from_best"] = float(worst10[idx]) - best_score
        lineup["n_candidates_in_pool"] = len(masks)
        lineup["n_real_stack_in_pool"] = len(masks)  # no stack restriction for showdown; see docstring
        lineup["generated_at_utc"] = now
        lineups.append(lineup)

    return pd.concat(lineups, ignore_index=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", choices=["dk", "fd"], required=True)
    parser.add_argument("--slate-id", type=str, required=True)
    parser.add_argument("--n-candidates", type=int, default=80)
    parser.add_argument("--field-n", type=int, default=6000)
    parser.add_argument("--n-sims", type=int, default=800)
    parser.add_argument("--seed", type=int, default=3)
    parser.add_argument("--top-n", type=int, default=TOP_N)
    args = parser.parse_args()

    lineups = recommend_lineup(
        args.site, args.slate_id,
        n_candidates=args.n_candidates, field_n=args.field_n,
        n_sims=args.n_sims, seed=args.seed, top_n=args.top_n,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"recommended_lineup_{args.site}_{args.slate_id}.csv"
    lineups.to_csv(out_path, index=False)

    n_ranks = lineups["recommendation_rank"].nunique()
    print(f"[{args.site}] {args.slate_id}: wrote {n_ranks} ranked lineup(s) ({len(lineups)} rows) to {out_path}")
    for rank, g in lineups.groupby("recommendation_rank"):
        total_salary = int(g["salary"].sum())
        total_proj = float(g["projection"].sum())
        print(f"\n  --- rank {rank}{' (THE recommendation)' if rank == 1 else ' (context only)'} --- "
              f"worst_top25={g['worst_top25_score'].iloc[0]:.3f} "
              f"avg_top25={g['avg_top25_score'].iloc[0]:.3f} "
              f"gap_from_best={g['score_gap_from_best'].iloc[0]:.3f} "
              f"salary={total_salary}/{SITE_CONFIGS[args.site]['salary_cap']} projection={total_proj:.1f}")
        print(g[["roster_slot", "player_name", "team", "position", "salary", "projection"]].to_string(index=False))


if __name__ == "__main__":
    main()
