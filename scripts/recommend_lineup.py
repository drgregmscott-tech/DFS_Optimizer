"""
recommend_lineup.py
====================

Week 3+ live lineup recommender -- ships the ONE piece of the 2026-09-22/23
lineup-system investigation that's actually validated end-to-end for live
(pre-lock) use: `worst_top25_realstack`, the strongest ownership-INDEPENDENT
selection rule tested against 6 real logged SE3max slates (3/6 cash, mean
percentile 0.703 -- see HANDOFF_week3_lineup_system.md).

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
import optimizer  # noqa: E402
import best_lineup_classic as blc  # noqa: E402
from ingest_salaries import SITE_CONFIGS  # noqa: E402

METHOD_TAG = "worst_top25_realstack_v1"
TOP_N = 3


def recommend_lineup(site: str, slate_id: str, n_candidates: int = 80,
                      field_n: int = 6000, n_sims: int = 800, seed: int = 3,
                      top_n: int = TOP_N):
    """Returns a DataFrame of up to `top_n` ranked lineups stacked together
    (see module docstring's Output section) -- rank 1 is THE recommendation
    (identical selection to every prior version of this function); 2/3 are
    margin/confidence context, not alternate options to pick from.

    2026-09-23 fix: Showdown slates are refused here, not silently crashed
    into. `best_lineup_classic.candidates()` (via `optimizer.build_single_
    lineup()`) assumes one row per player_id -- a Showdown pool has TWO
    (CPT and FLEX price/points variants of the same player_id), which made
    `proj[pid]` return a pandas Series instead of a scalar and PuLP raise an
    opaque `TypeError: must be real number, not Series` deep inside the
    solver. That was never a "small bug": this script's only shipped method,
    `worst_top25_realstack`, was validated exclusively against CLASSIC
    slates (see HANDOFF_week3_lineup_system.md) -- "is_real_stack" (a QB +
    same-team WR/TE) and the "top25" SE3max cash-line threshold are both
    classic-roster concepts that don't have a validated Showdown analogue.
    `analysis/showdown_own/best_single.py` already has SEPARATE Showdown
    candidate-generation/scoring machinery (a different selection metric,
    never validated against real logged Showdown results the way this
    script's classic rule was, and its own candidate generator is hardcoded
    to one old 2-team slate's team abbreviations) -- wiring it in here needs
    its own real-data validation pass, not a same-session patch, per this
    module's own stated discipline for adding new selection logic (see the
    docstring's "Do not add a pivot step... without a new real-data
    validation" note). Failing loud with an explanation is more useful than
    either crashing or silently shipping an unvalidated rule."""
    proj_path = OUTPUT_DIR / f"final_projections_{site}_{slate_id}.csv"
    if proj_path.exists():
        probe = pd.read_csv(proj_path, usecols=lambda c: c == "slate_format", nrows=1000)
        if optimizer.is_showdown_pool(probe):
            raise SystemExit(
                f"recommend_lineup: {site}/{slate_id} is a Showdown/Single-Game "
                f"slate. This script's only shipped method (worst_top25_realstack) "
                f"was validated for classic slates only -- see this function's own "
                f"docstring for why Showdown isn't a same-session patch. No "
                f"recommended_lineup file will be written for this slate; classic "
                f"slates are unaffected."
            )
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
