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
    One row per rostered player (same per-player schema as
    lineup_single_{site}_{slate_id}.csv / lineups_multi_{site}_{slate_id}.csv
    -- roster_slot, player_id, player_name, position, team, salary,
    projection, value, opponent, site_player_id, sigma, sigma_source --
    so it's a drop-in input for pivot_finder.py too if ever wanted), PLUS
    lineup-level provenance columns repeated on every row so a downstream
    reader (or a human staring at the raw CSV) can verify what actually
    produced this pick without cross-referencing anything else:
    method, worst_top25_score, avg_top25_score, n_candidates_in_pool,
    n_real_stack_in_pool, generated_at_utc.
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "output"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "analysis" / "classic_diag"))
import optimizer  # noqa: E402
import best_lineup_classic as blc  # noqa: E402
from ingest_salaries import SITE_CONFIGS  # noqa: E402

METHOD_TAG = "worst_top25_realstack_v1"


def recommend_lineup(site: str, slate_id: str, n_candidates: int = 80,
                      field_n: int = 6000, n_sims: int = 800, seed: int = 3):
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
    win_idx = int(v.argmax())
    win_mask = masks[win_idx]

    config = SITE_CONFIGS[site]
    fixed_counts, _flex_count = optimizer.parse_roster_requirements(config["roster_slots"])
    selected = P.iloc[win_mask].reset_index(drop=True)
    lineup = optimizer.assign_roster_slots(selected, fixed_counts)

    optimizer.validate_lineup(lineup, config["salary_cap"], config["roster_slots"])

    lineup["method"] = METHOD_TAG
    lineup["worst_top25_score"] = float(worst25[win_idx])
    lineup["avg_top25_score"] = float(out["avg_top25"].iloc[win_idx])
    lineup["n_candidates_in_pool"] = len(masks)
    lineup["n_real_stack_in_pool"] = n_real_stack
    lineup["generated_at_utc"] = datetime.now(timezone.utc).isoformat()

    return lineup


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", choices=["dk", "fd"], required=True)
    parser.add_argument("--slate-id", type=str, required=True)
    parser.add_argument("--n-candidates", type=int, default=80)
    parser.add_argument("--field-n", type=int, default=6000)
    parser.add_argument("--n-sims", type=int, default=800)
    parser.add_argument("--seed", type=int, default=3)
    args = parser.parse_args()

    lineup = recommend_lineup(
        args.site, args.slate_id,
        n_candidates=args.n_candidates, field_n=args.field_n,
        n_sims=args.n_sims, seed=args.seed,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"recommended_lineup_{args.site}_{args.slate_id}.csv"
    lineup.to_csv(out_path, index=False)

    total_salary = int(lineup["salary"].sum())
    total_proj = float(lineup["projection"].sum())
    print(f"[{args.site}] {args.slate_id}: wrote {len(lineup)}-player recommended lineup to {out_path}")
    print(f"  method={METHOD_TAG} worst_top25={lineup['worst_top25_score'].iloc[0]:.3f} "
          f"avg_top25={lineup['avg_top25_score'].iloc[0]:.3f} "
          f"pool={lineup['n_candidates_in_pool'].iloc[0]} "
          f"real_stack_in_pool={lineup['n_real_stack_in_pool'].iloc[0]}")
    print(f"  salary={total_salary}/{SITE_CONFIGS[args.site]['salary_cap']} projection={total_proj:.1f}")
    print(lineup[["roster_slot", "player_name", "team", "position", "salary", "projection"]].to_string(index=False))


if __name__ == "__main__":
    main()
