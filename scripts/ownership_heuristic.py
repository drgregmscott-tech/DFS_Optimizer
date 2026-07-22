"""
ownership_heuristic.py
=======================

Session 4.1 -- Chalk Score Heuristic.

For a given site (DK/FD) and week, reads that week's
final_projections_{site}_{week}.csv (Session 2.4/3.3's output) and produces
a 0-100 "chalk_score" per player -- a heuristic estimate of how likely the
field is to roster that player. Used downstream by Session 4.2's
cash-to-GPP pivot logic (pivots matter most on high-chalk players).

This is explicitly a HEURISTIC, not a real ownership model -- no real
DK/FD ownership percentages exist anywhere in this pipeline (same class of
gap as FD's real salary data -- see ROADMAP.md's FanDuel validation gap
note). The roadmap card's own validation step says as much: check relative
order against actual published ownership "if available, or intuition as a
gut-check on direction, not precision." Four inputs are combined below,
each cleared as a design decision this session left open (same pattern as
build_projections.py's decisions #1-#6):

1. Value (points per $1K salary) -- the single strongest real driver of
   DFS ownership: cheap-for-their-projection players get rostered a lot
   because they free up cap space for stars elsewhere, and elite/expensive
   players with the best raw projection get rostered because they're the
   "obvious" play. Computed as final_projection / (salary / 1000).
   Value isn't comparable across positions (a QB's raw value number runs
   structurally higher than a WR's, a WR's higher than a DST's), so it's
   converted to a PERCENTILE RANK within (site, position_group) before
   use -- same "convert to a comparable scale before blending" approach
   Session 2.4 already used for matchup_factor/vegas_factor (decision #1
   there). position_group folds DK's/FD's differently-labeled defense
   rows (DST vs D/DEF) into one "DST" bucket for this ranking, via
   SITE_CONFIGS[site]["defense_position_values"] -- otherwise DK (only
   ever has "DST") vs FD (only ever has "D"/"DEF") would each rank
   against a pool of one position label, not against each other,
   defeating the point of a percentile.

2. Salary tier -- modeled as a U-shape, not linear: real DFS chalk
   clusters at BOTH ends of a position's salary range (min-priced "punt"
   plays that free up cap room, AND the single most-expensive "clearly
   the best player" studs), and is thinnest in the middle, where genuine
   differentiated decisions live. Computed as
   100 * abs(salary_percentile_within_position_group - 0.5) * 2, so both
   tails approach 100 and the middle approaches 0.

3. Vegas total -- the public bets game totals (overs) heavily, and a
   team/game projected to score a lot draws more attention to every
   player in it, independent of that player's own value. Computed as a
   straight percentile rank of `implied_total` across every row in this
   site/week's pool (not position-grouped -- a shootout raises attention
   on that game's QB AND its WRs AND the DST facing the bad defense
   alike).

4. Manual name-recognition flag list -- real DFS ownership is also driven
   by simple fame/media narrative, independent of value or matchup (e.g.
   a slumping star still gets rostered heavily on name alone). No
   upstream data source captures this, so it's a small manually-curated
   CSV (data/name_recognition_flags.csv: player_id, player_name,
   flag_weight [0-20], notes) applied as a flat ADDITIVE bonus, not a
   percentile -- unlike inputs 1-3, this isn't meant to rank the whole
   pool, just nudge specific known names up. Decision: SHARED across
   sites, not site-specific -- a player's real-world name recognition
   doesn't change between DK and FD, only their price/value does (which
   inputs 1-2 already capture per-site). Missing file, or a player not on
   it, -> 0 bonus, never an error -- this list is expected to start empty
   or thin and grow over time (flag as a handoff note each session that
   touches it, per the roadmap card's own instruction).

Blend (weights are a starting heuristic, not fit to any real ownership
data -- flagged as a good target for a future session's retuning once
real published ownership numbers are available to check against, same
spirit as build_projections.py's BASELINE_WEIGHT/RECENT_FORM_WEIGHT):

    chalk_score = clip(
        0.45 * value_percentile
      + 0.20 * salary_tier_score
      + 0.25 * vegas_percentile
      + name_recognition_bonus,
      0, 100
    )

name_recognition_bonus is added AFTER the 0-100 weighted blend (not folded
into the weights), then the whole thing is clipped to [0, 100] -- so a
flag_weight on an already-high-scoring player saturates at 100 rather than
pushing the number off-scale.

A player with final_projection == 0.0 (bye/no-real-game, per
build_projections.py's decision #4b, or a legitimate 0-projection edge
case) gets value_percentile computed normally -- 0 value ranks at or near
the bottom of its position group, which is correct (nobody chalks a
bye-week player) -- rather than being dropped or special-cased.

5. estimated_ownership_pct -- added same session as a follow-up to
   chalk_score, after the user asked directly: chalk_score alone is a
   RELATIVE ranking (0-100 scale, no real-world anchor) and was never
   meant to be read as a percentage. This adds an actual 0-100 percentage
   ESTIMATE, still not real data (none exists yet), but anchored to one
   genuinely real, non-fabricated fact instead of an arbitrary curve:
   roster-slot math. Every single lineup on a site fills exactly N slots
   of a given position (e.g. DK fills exactly 2 "hard" RB slots plus a
   share of 1 FLEX slot every single time), so across a large, rational
   field, TOTAL ownership summed across every eligible player at that
   position should land close to N * 100 percentage points -- this is a
   structural constraint on the real world, not an empirical guess.
   compute_position_slot_budgets() derives this "budget" per
   position_group straight from SITE_CONFIGS[site]["roster_slots"].
   FLEX (RB/WR/TE-eligible on both sites) has no real per-position
   usage-rate data available yet (does the field actually play RB in
   FLEX more often than WR? almost certainly yes in practice, but no real
   number exists in this pipeline) -- decision: split FLEX's budget
   evenly three ways, flagged as a simplification a future session can
   replace once real logged FLEX usage exists (see the new Phase 9
   "Actual Ownership Logging" / "Ownership Estimate Retuning" cards added
   to ROADMAP.md this session).

   Within each position_group, chalk_score is converted to a share of
   that group's budget via a softmax: weight = exp(chalk_score /
   OWNERSHIP_SOFTMAX_TEMPERATURE), normalized to sum to 1 within the
   group, then multiplied by the group's budget. Softmax (rather than a
   flat percentile-to-percentage rescale) was chosen because real
   ownership is known to be concentrated, not flat -- a few true chalk
   plays take a large share, most of the field's cheap depth pieces take
   a sliver. OWNERSHIP_SOFTMAX_TEMPERATURE controls how concentrated:
   lower = more winner-take-most. Like the blend weights above, this
   constant is an UNFIT starting guess, not calibrated to real data --
   flagged as the clearest first target for the new Phase 9 retuning
   session once real ownership numbers exist to fit against.

   Bye/no-real-game players (final_projection == 0) get an explicit 0
   weight -- not just a low one -- so their share of the group's budget
   gets fully redistributed to real players rather than leaving a
   phantom floor value the way chalk_score's blend does (chalk_score
   still assigns these players a nonzero score from the salary/vegas
   components alone; estimated_ownership_pct deliberately does not,
   since "how much of the real ownership budget should a player with a
   confirmed zero projection get" has an unambiguous real-world answer:
   none). If EVERY player in a position group has final_projection == 0
   (all-bye edge case), there's no nonzero signal to weight by, so that
   group's budget falls back to an even split across its players, with a
   stderr warning -- flagged as a backtest-fixture artifact that a real
   live slate's salary file should never actually trigger (it only ever
   contains players who are genuinely playing that slate).

Usage:
    python3 scripts/ownership_heuristic.py --site dk --week 10

Outputs:
    output/chalk_scores_{site}_{week}.csv
    Required columns per the roadmap card: player_id, chalk_score.
    estimated_ownership_pct (decision #5) and
    player_name/position/salary/final_projection are carried through too
    -- purely additive, makes the output spot-checkable without a join
    back to final_projections_*.csv.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest_salaries import SITE_CONFIGS  # noqa: E402 -- shared defense-position labels / site config, same import pattern as build_projections.py

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUT_DIR = REPO_ROOT / "output"

NAME_RECOGNITION_PATH = DATA_DIR / "name_recognition_flags.csv"

# Blend weights -- user-confirmed pattern of logging tunable constants
# explicitly (see build_projections.py's BASELINE_WEIGHT/RECENT_FORM_WEIGHT)
# so a future retuning session has a clear starting point to diff against.
VALUE_WEIGHT = 0.45
SALARY_TIER_WEIGHT = 0.20
VEGAS_WEIGHT = 0.25
MAX_NAME_RECOGNITION_BONUS = 20  # sanity ceiling on any single flag_weight row

MIN_GROUP_SIZE_FOR_RELIABLE_PERCENTILE = 5  # below this, warn -- see ROADMAP.md's "Known Testing Artifact" note on thin pools

# Decision #5 (see module docstring): estimated_ownership_pct constants.
# Standard NFL DFS FLEX eligibility, same on both sites -- used to split a
# roster's FLEX slot budget across the three positions that can fill it.
FLEX_ELIGIBLE_POSITIONS = {"RB", "WR", "TE"}

# Softmax temperature controlling how concentrated estimated_ownership_pct
# is within a position group -- lower = more winner-take-most (a few true
# mega-chalk plays take most of the group's budget), higher = flatter.
# UNFIT starting guess, not calibrated to any real ownership data -- the
# clearest first target for the new Phase 9 retuning session once real
# ownership numbers exist to fit against (see ROADMAP.md).
OWNERSHIP_SOFTMAX_TEMPERATURE = 15.0


# ---------------------------------------------------------------------------
# Step 0: Load inputs
# ---------------------------------------------------------------------------

def load_final_projections(site: str, week: int) -> pd.DataFrame:
    path = OUTPUT_DIR / f"final_projections_{site}_{week}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run build_projections.py --site {site} "
            f"--week {week} first (Session 2.4/3.3)."
        )
    df = pd.read_csv(path, dtype={"player_id": str})
    required = {"player_id", "player_name", "position", "salary", "final_projection", "implied_total"}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(
            f"{path} is missing expected columns: {sorted(missing)}. "
            f"build_projections.py's output schema may have changed -- "
            f"update this script's load_final_projections() to match."
        )
    return df


def load_name_recognition_flags() -> pd.DataFrame:
    """Decision #4 (see module docstring): shared across sites, additive
    bonus, missing file or missing player -> 0, never an error -- this
    list is expected to start thin and grow over time."""
    cols = ["player_id", "player_name", "flag_weight", "notes"]
    if not NAME_RECOGNITION_PATH.exists():
        print(
            f"NOTE: {NAME_RECOGNITION_PATH} not found -- every player gets "
            f"a 0 name-recognition bonus. Create this file to start "
            f"flagging known high-name-recognition players (see this "
            f"script's module docstring for the expected columns).",
            file=sys.stderr,
        )
        return pd.DataFrame(columns=["player_id", "flag_weight"])

    df = pd.read_csv(NAME_RECOGNITION_PATH, dtype={"player_id": str})
    missing = set(cols[:3]) - set(df.columns)
    if missing:
        raise SystemExit(
            f"{NAME_RECOGNITION_PATH} is missing expected columns: {sorted(missing)}."
        )
    out_of_range = df[(df["flag_weight"] < 0) | (df["flag_weight"] > MAX_NAME_RECOGNITION_BONUS)]
    if not out_of_range.empty:
        raise SystemExit(
            f"{NAME_RECOGNITION_PATH} has flag_weight values outside "
            f"0-{MAX_NAME_RECOGNITION_BONUS} for: "
            f"{out_of_range['player_name'].tolist()}. Fix these rows -- "
            f"flag_weight is meant to be a modest nudge, not a dominant "
            f"factor in the blend."
        )
    return df[["player_id", "flag_weight"]].drop_duplicates(subset=["player_id"])


# ---------------------------------------------------------------------------
# Step 1: Chalk score
# ---------------------------------------------------------------------------

def build_position_group(df: pd.DataFrame, site: str) -> pd.Series:
    """Folds site-specific defense position labels (DK 'DST', FD 'D'/'DEF')
    into one 'DST' bucket for percentile grouping -- see module docstring
    decision #1."""
    defense_values = SITE_CONFIGS[site]["defense_position_values"]
    return df["position"].where(~df["position"].isin(defense_values), "DST")


def compute_chalk_scores(df: pd.DataFrame, site: str) -> pd.DataFrame:
    df = df.copy()
    df["position_group"] = build_position_group(df, site)

    group_counts = df.groupby("position_group").size()
    thin_groups = group_counts[group_counts < MIN_GROUP_SIZE_FOR_RELIABLE_PERCENTILE]
    if not thin_groups.empty:
        print(
            f"WARNING: value_percentile/salary_tier_score are less "
            f"meaningful for thin position groups (same distortion "
            f"ROADMAP.md's 'Known Testing Artifact' note already flags "
            f"for this project's current test pool) -- group sizes: "
            f"{thin_groups.to_dict()}",
            file=sys.stderr,
        )

    # Decision #1: value = projected points per $1K salary, percentile-
    # ranked within position_group so positions with structurally
    # different raw value ranges are comparable.
    df["value"] = df["final_projection"] / (df["salary"] / 1000.0)
    df["value_percentile"] = df.groupby("position_group")["value"].rank(pct=True) * 100

    # Decision #2: salary tier, U-shaped -- both ends of a position
    # group's salary range score high, the middle scores low.
    salary_pct = df.groupby("position_group")["salary"].rank(pct=True)
    df["salary_tier_score"] = (salary_pct - 0.5).abs() * 2 * 100

    # Decision #3: vegas total, percentile-ranked across the WHOLE pool
    # (not position-grouped) -- a shootout raises attention on every
    # position in that game alike. Bye-week players carry implied_total
    # == 0.0 (build_projections.py's sentinel fill), which correctly
    # ranks them at the bottom here too.
    df["vegas_percentile"] = df["implied_total"].rank(pct=True) * 100

    # Decision #4: manual name-recognition flag, additive, shared across
    # sites, 0 for anyone not on the list.
    flags = load_name_recognition_flags()
    df = df.merge(flags, on="player_id", how="left")
    df["flag_weight"] = df["flag_weight"].fillna(0.0)
    n_flagged = (df["flag_weight"] > 0).sum()
    print(f"{n_flagged} player(s) received a name-recognition bonus from {NAME_RECOGNITION_PATH.name}.")

    df["chalk_score"] = (
        VALUE_WEIGHT * df["value_percentile"]
        + SALARY_TIER_WEIGHT * df["salary_tier_score"]
        + VEGAS_WEIGHT * df["vegas_percentile"]
        + df["flag_weight"]
    ).clip(lower=0, upper=100)

    return df



# ---------------------------------------------------------------------------
# Step 2: Estimated ownership % (decision #5)
# ---------------------------------------------------------------------------

def compute_position_slot_budgets(site: str) -> dict:
    """Each position_group's total 'ownership budget,' in percentage
    points summed across every eligible player in that group -- anchored
    to real roster-slot math (see module docstring decision #5), not a
    guess. FLEX's budget is split evenly across RB/WR/TE (no real
    per-position FLEX usage-rate data exists yet)."""
    slots = SITE_CONFIGS[site]["roster_slots"]
    defense_values = SITE_CONFIGS[site]["defense_position_values"]
    budgets: dict = {}

    hard_slots = [s for s in slots if s != "FLEX"]
    for s in hard_slots:
        group = "DST" if s in defense_values else s
        budgets[group] = budgets.get(group, 0.0) + 100.0

    n_flex = slots.count("FLEX")
    if n_flex:
        flex_share = (n_flex * 100.0) / len(FLEX_ELIGIBLE_POSITIONS)
        for group in FLEX_ELIGIBLE_POSITIONS:
            budgets[group] = budgets.get(group, 0.0) + flex_share

    # Internal consistency check, informational only -- total budget
    # across all groups should equal exactly len(roster_slots) * 100,
    # since every slot (hard or FLEX) contributes exactly 100 percentage
    # points somewhere. Not a data-quality check (no real data involved
    # yet), just confirms the budget math itself didn't drift.
    expected_total = len(slots) * 100.0
    actual_total = sum(budgets.values())
    if abs(actual_total - expected_total) > 0.01:
        raise SystemExit(
            f"compute_position_slot_budgets({site!r}) internal check failed: "
            f"budgets sum to {actual_total}, expected {expected_total} "
            f"(len(roster_slots) * 100). This is a bug in this function, "
            f"not a data problem -- check SITE_CONFIGS['{site}']['roster_slots']."
        )
    return budgets


def compute_estimated_ownership(df: pd.DataFrame, site: str) -> pd.DataFrame:
    """Decision #5 (see module docstring): converts chalk_score's relative
    ranking into an ESTIMATED ownership percentage, anchored to real
    roster-slot math, not to any real ownership data (none exists yet)."""
    df = df.copy()
    budgets = compute_position_slot_budgets(site)

    # Bye/no-real-game players (final_projection == 0) get an explicit 0
    # weight so their share of the group's budget is fully redistributed
    # to real players -- see module docstring decision #5.
    has_signal = df["final_projection"] > 0
    df["_weight"] = 0.0
    df.loc[has_signal, "_weight"] = np.exp(df.loc[has_signal, "chalk_score"] / OWNERSHIP_SOFTMAX_TEMPERATURE)

    group_weight_sum = df.groupby("position_group")["_weight"].transform("sum")
    group_size = df.groupby("position_group")["position_group"].transform("count")

    all_zero = group_weight_sum == 0
    if all_zero.any():
        affected = sorted(df.loc[all_zero, "position_group"].unique().tolist())
        print(
            f"WARNING: position group(s) {affected} have final_projection "
            f"== 0 for EVERY player this week -- estimated_ownership_pct "
            f"falls back to an even split of that group's budget, since "
            f"there's no nonzero signal to weight by. A real live slate's "
            f"salary file should never hit this path (it only ever "
            f"contains players who are genuinely playing) -- this is a "
            f"backtest-fixture artifact, not expected in production.",
            file=sys.stderr,
        )

    denom = group_weight_sum.replace(0, np.nan)
    df["_group_share"] = df["_weight"] / denom
    df.loc[all_zero, "_group_share"] = 1.0 / group_size[all_zero]

    df["_group_budget"] = df["position_group"].map(budgets)
    df["estimated_ownership_pct"] = (df["_group_share"] * df["_group_budget"]).clip(lower=0, upper=100)

    group_totals = df.groupby("position_group")["estimated_ownership_pct"].sum()
    print("estimated_ownership_pct summed per position group (should equal that group's roster-slot budget):")
    for group, total in group_totals.sort_index().items():
        print(f"  {group}: {total:.1f}% (budget: {budgets.get(group, float('nan')):.1f}%)")

    return df.drop(columns=["_weight", "_group_share", "_group_budget"])


def build_chalk_scores(site: str, week: int) -> pd.DataFrame:
    projections = load_final_projections(site, week)
    scored = compute_chalk_scores(projections, site)
    scored = compute_estimated_ownership(scored, site)
    out_cols = [
        "player_id", "player_name", "position", "salary", "final_projection",
        "chalk_score", "estimated_ownership_pct",
    ]
    out = scored[out_cols].sort_values("chalk_score", ascending=False).reset_index(drop=True)
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", choices=["dk", "fd"], required=True)
    parser.add_argument("--week", type=int, required=True)
    args = parser.parse_args()

    result = build_chalk_scores(args.site, args.week)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"chalk_scores_{args.site}_{args.week}.csv"
    result.to_csv(out_path, index=False)

    n_null = result.isna().any(axis=1).sum()
    n_chalk_out_of_range = ((result["chalk_score"] < 0) | (result["chalk_score"] > 100)).sum()
    n_own_out_of_range = ((result["estimated_ownership_pct"] < 0) | (result["estimated_ownership_pct"] > 100)).sum()
    print(f"Wrote {len(result)} players to {out_path}")
    print(f"  Nulls in any column: {n_null} (should be 0)")
    print(f"  chalk_score out of [0,100] range: {n_chalk_out_of_range} (should be 0)")
    print(f"  estimated_ownership_pct out of [0,100] range: {n_own_out_of_range} (should be 0)")
