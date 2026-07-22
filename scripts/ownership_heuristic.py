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

Usage:
    python3 scripts/ownership_heuristic.py --site dk --week 10

Outputs:
    output/chalk_scores_{site}_{week}.csv
    Required columns per the roadmap card: player_id, chalk_score.
    player_name/position/salary/final_projection are carried through too
    -- purely additive, makes the output spot-checkable without a join
    back to final_projections_*.csv.
"""

import argparse
import sys
from pathlib import Path

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


def build_chalk_scores(site: str, week: int) -> pd.DataFrame:
    projections = load_final_projections(site, week)
    scored = compute_chalk_scores(projections, site)
    out_cols = ["player_id", "player_name", "position", "salary", "final_projection", "chalk_score"]
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
    n_out_of_range = ((result["chalk_score"] < 0) | (result["chalk_score"] > 100)).sum()
    print(f"Wrote {len(result)} players to {out_path}")
    print(f"  Nulls in any column: {n_null} (should be 0)")
    print(f"  chalk_score out of [0,100] range: {n_out_of_range} (should be 0)")
