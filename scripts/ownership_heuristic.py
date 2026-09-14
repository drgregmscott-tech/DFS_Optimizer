"""
ownership_heuristic.py
=======================

Session 4.1 -- Chalk Score Heuristic.
Updated Session 11.0 -- Feature Expansion (2026-07-28).

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
gut-check on direction, not precision."

SESSION 11.0 CHANGES (2026-07-28)
----------------------------------
Two new features added, one weight table updated. No existing feature
removed, no existing output column changed -- purely additive.

New features:
  - raw_projection_percentile: final_projection as a standalone feature,
    percentile-ranked within position group. This is distinct from value
    (pts/$1K): a player can have a great raw projection AND poor value (very
    expensive), or great value AND a modest raw projection (cheap role
    player). Both signals predict ownership independently. Research finding:
    salary and projected points together explain ~20-25% of ownership
    variance vs ~8% for salary alone.

  - over_under_percentile: the game-level over/under (already present in
    final_projections_*.csv from Session 3.3's addendum) as a separate
    feature. This captures "shootout game" signal that implied_total alone
    misses. A team with a 26 implied total in a 52 O/U game (expected
    shootout) is a meaningfully different ownership driver than a team with
    26 in a 40 O/U game (expected defensive game with one dominant offense).
    Percentile-ranked across the full pool, same as implied_total.

Updated blend weights (all 5 are UNFIT starting guesses, flagged for
Session 11.1 regression retuning once real ownership data exists):

  Old (4-feature):  value 0.45 | salary_tier 0.20 | vegas 0.25 | name 0+ 
  New (5-feature):  value 0.35 | projection 0.15 | salary_tier 0.15
                    | vegas 0.20 | over_under 0.15 | name 0+

Rationale for direction of weight changes:
  - value dropped 0.45 -> 0.35: raw projection is now a separate feature,
    so value doesn't need to carry both the "good player" signal AND the
    "efficient play" signal alone.
  - salary_tier dropped 0.20 -> 0.15: value + raw projection together
    already carry most of the salary-driven signal.
  - vegas held 0.25 -> 0.20: redistributed partially to over_under.
  - over_under 0.0 -> 0.15: new. Game totals are a real, published
    predictor of ownership documented in the research gathered 2026-07-28.
  - projection 0.0 -> 0.15: new. Raw ceiling is a distinct ownership
    driver from value efficiency.

ALL FIVE WEIGHTS ARE RETUNING TARGETS for Session 11.1 once
ownership_actual_log.csv has 4-6 weeks of real data.

Design decisions from Session 4.1 (unchanged):

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

3. Vegas implied total -- the public bets game totals (overs) heavily,
   and a team/game projected to score a lot draws more attention to every
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

New design decisions from Session 11.0:

6. raw_projection_percentile -- final_projection as a standalone feature,
   distinct from value. Percentile-ranked within position_group (same
   grouping as value, decision #1) so QB/WR/RB/TE/DST are compared
   within their own pools. Zero-projection players (bye/inactive) rank at
   or near the bottom of their group, which is correct. This is a
   SEPARATE signal from value: a $9,800 WR projected for 18 points has
   lower value than a $5,000 WR projected for 12 points, but the $9,800
   WR will be owned far more heavily on name/projection ceiling alone.
   Value alone would undersell the expensive stud and oversell the cheap
   punt in ownership terms. This feature corrects that.

7. over_under_percentile -- game-level over/under (O/U) as a separate
   signal from implied_total. Percentile-ranked across the full pool (not
   position-grouped), same approach as vegas_percentile (decision #3).
   Bye-week players carry over_under == 0.0 (build_projections.py's
   sentinel fill), correctly ranking them at the bottom.

   Why separate from implied_total: both signals are real. implied_total
   tells you "this team is expected to score a lot" (directly drives
   skill-position ownership). over_under tells you "this is expected to
   be a high-scoring game overall" (drives all-position ownership in the
   game, including the losing team's skill positions and the winning
   team's DST opponent). A team with implied_total 27 in a 52 O/U game
   has a very different DFS ownership profile than the same team in a 38
   O/U game, even with identical point spreads.

8. PARTICIPATION-CONFIDENCE DAMPENING (Session 15.3) -- value_percentile
   (decision #1) is a ratio, final_projection divided by salary, and
   ratios break down at the bottom of the salary range: ANY nonzero
   projection, however thin the basis for it, produces a huge ratio
   against a tiny salary denominator. Confirmed on a real Week 1 2026
   Showdown slate: a Seattle WR with ZERO career NFL participation
   (games_played == 0, participation_effective == 0.0), priced at DK
   Showdown's $200 floor and projected for 1.4 points, produced
   value_percentile == 100 -- the single highest value ranking in the
   whole 61-player pool -- and an outright TIED chalk_score (76.25) with
   the slate's best real, established player (a $10,600+ WR projected for
   19-28 points). A real fullback with an actual small role (11 games
   played, participation_effective == 0.8) ranked BELOW several
   zero-participation players for the opposite reason: his genuinely
   small real role produces a smaller raw_projection_percentile than the
   noisier baseline projection given to totally unproven players.

   `participation_effective` (Session 15.2) already exists in
   final_projections_*.csv specifically to answer "how much real evidence
   exists that this player sees the field" -- 0.0 for a confirmed
   zero-history bench/inactive-risk player, 1.0 for an established
   full-season role, already corrected upward for confirmed depth-chart
   #1 starters even in their first game
   (apply_confirmed_starter_override(), Session 15.2), so a genuine
   rookie starter is not wrongly dampened here.

   Applied as a multiplier on the WHOLE blended chalk_score (all five
   inputs plus the name-recognition bonus), not a single sub-feature --
   every input is, to some degree, built from a projection whose
   reliability depends on this same participation signal. A floor (not a
   hard zero) is used deliberately: a real, if small, chance exists that
   an unproven player sees the field and becomes a differentiation play,
   and estimated_ownership_pct already has its own explicit-zero
   mechanism (decision #5) for the genuinely-impossible case
   (final_projection == 0, confirmed no game). PARTICIPATION_CONFIDENCE_
   FLOOR is an UNFIT starting guess, same status as the blend weights and
   softmax temperature -- retuning target for Session 11.1.

   Only applied where the signal exists: DST/K have no participation_
   effective concept at all (NaN in final_projections_*.csv -- a defense
   or kicker has no "bench" the way a skill-position player does), so
   they get a confidence multiplier of 1.0 (unchanged), not a spurious
   dampening from a signal that was never computed for them. A
   projections file missing the column entirely (older schema) degrades
   the same way -- multiplier 1.0 for everyone, with a stderr note -- so
   this is additive, not a hard schema requirement.

9. THE TRUE-WEEK-1 CASE (Session 15.3, found via a real live run):
   decision #8 as first shipped could not tell "this ONE player has no
   track record, relative to established teammates" (its intended case)
   apart from "NO player in the pool has current-season history yet,
   because the season's actual first game hasn't been played" (a
   completely different, degenerate case) -- both show
   participation_effective == 0.0. In the true-Week-1 case that number is
   uninformative for every skill player, proven veteran and rookie alike,
   because statline_model.py's cold-start path (its own decision #14) has
   no current-season data for ANYONE yet. Decision #8 dampened every real
   skill player regardless, while DST/K -- which never had a
   participation_effective concept to dampen -- kept full strength.
   Confirmed real on an actual NE/SEA season-opener Showdown slate: the
   Seahawks defense reached 98.7% estimated Captain ownership, ahead of
   every real skill player in the game.

   Fixed by checking whether the pool has ANY real signal to act on
   before applying decision #8 at all: if not one player anywhere shows
   participation_effective > 0, the dampening is skipped entirely (every
   player gets confidence 1.0, same treatment DST/K already get) rather
   than uniformly deflating the whole skill-position pool against
   positions that were never subject to it. This is a property of the
   data, not a week-number check -- the moment even one real player in
   the pool has accumulated true in-season history, decision #8's
   original per-player dampening resumes automatically.

10. THE STRUCTURAL MIN-SALARY RATIO BLOWUP (Session 15.3, real root cause
    of a real complaint -- several $200 Showdown players marked chalk that
    had no real business being there). Decision #8/#9 address WHO gets
    dampened and when; this addresses a completely separate mechanism that
    exists independent of participation, week, or season, and that
    decision #9's fix (correctly) stopped masking: value_percentile
    (decision #1) is points divided by salary, and salary_tier_score
    (decision #2) is a percentile rank of salary itself. Both derive
    directly from raw salary, and both break down the same way for any
    player priced at or near a slate's minimum -- a $200 salary makes even
    a thin, low-confidence projection divide out to a value ratio bigger
    than a real $10,000+ star's, and separately ranks as an extreme-tier
    salary_tier_score purely for being at the price floor, regardless of
    whether that price reflects a real role. Confirmed on a real live
    slate: a Seattle WR with zero career snaps outranked the slate's best
    real, established receiver on BOTH features, tied its overall
    chalk_score exactly, well before decision #8/#9 (participation) ever
    entered the picture -- this is a salary-math problem, not a
    participation problem.

    Fixed with a floor (VALUE_SALARY_FLOOR) on the salary figure these two
    features use -- NOT on the real `salary` column, which stays untouched
    everywhere else (display, the optimizer's own cap-space math). Below
    the floor, small real salary differences ($200 vs $300) don't reflect
    a real difference in expected role, so they shouldn't drive one in
    either feature. A no-op for Classic QB/RB/WR/TE (their real minimums
    already sit above the floor); a small, appropriate nudge for Classic's
    cheapest DST tier (already visibly elevated before this fix); the main
    correction for Showdown's much lower $200 floor.

5. estimated_ownership_pct -- added Session 4.1 as a follow-up to
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
   evenly three ways, flagged as a simplification Session 11.2 can
   replace once real logged FLEX usage exists (see Phase 11 in
   ROADMAP.md).

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
   flagged as the clearest first target for Session 11.1 retuning once
   real ownership numbers exist to fit against.

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
from ingest_salaries import SITE_CONFIGS  # noqa: E402 -- shared defense-position labels / site config

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUT_DIR = REPO_ROOT / "output"

NAME_RECOGNITION_PATH = DATA_DIR / "name_recognition_flags.csv"

# ---------------------------------------------------------------------------
# Blend weights -- SESSION 11.0 UPDATE
# All five weights are UNFIT starting guesses, not calibrated to real
# ownership data. Flagged as retuning targets for Session 11.1 once
# ownership_actual_log.csv has 4-6 weeks of real data.
#
# Tracking the old weights here for diff visibility:
#   OLD (4-feature, Session 4.1): VALUE 0.45 | SALARY_TIER 0.20 | VEGAS 0.25
#   NEW (5-feature, Session 11.0): see below
# ---------------------------------------------------------------------------
VALUE_WEIGHT = 0.35           # pts/$1K value, percentile within position group
PROJECTION_WEIGHT = 0.15      # raw projected points, percentile within position group (NEW Session 11.0)
SALARY_TIER_WEIGHT = 0.15     # U-shaped salary tier score
VEGAS_WEIGHT = 0.20           # implied team total, percentile across full pool
OVER_UNDER_WEIGHT = 0.15      # game over/under, percentile across full pool (NEW Session 11.0)
MAX_NAME_RECOGNITION_BONUS = 20  # sanity ceiling on any single flag_weight row

# Decision #8 (Session 15.3): floor on the participation-confidence
# multiplier applied to the WHOLE blended chalk_score -- see that decision
# in the module docstring. A confirmed zero-participation player's
# chalk_score is scaled to this fraction of what the raw 5-feature blend
# would otherwise produce (1.0 = no dampening, at participation_effective
# == 1.0). UNFIT starting guess, same status as the blend weights and
# softmax temperature below -- retuning target for Session 11.1 once real
# logged ownership data exists to fit it against.
PARTICIPATION_CONFIDENCE_FLOOR = 0.35

# Decision #10 (Session 15.3): floor on the salary figure used to compute
# value_percentile AND salary_tier_score -- see that decision in the
# module docstring. Both features derive from raw salary; both break down
# the same way for any player priced at or near a slate's minimum, since
# that's a structural property of the ratio/percentile math, independent
# of participation, week, or season. UNFIT starting guess, same status as
# the other constants above -- validated against a real live slate tonight
# (Session 15.3) but not fit to real logged ownership data. A no-op for
# Classic QB/RB/WR/TE (their real minimum salaries already sit well above
# this), a small nudge for Classic's cheapest DST tier, and the main
# correction for Showdown's much lower $200 floor.
VALUE_SALARY_FLOOR = 2400

MIN_GROUP_SIZE_FOR_RELIABLE_PERCENTILE = 5  # below this, warn -- see ROADMAP.md "Known Testing Artifact"

# Decision #5 (see module docstring): estimated_ownership_pct constants.
# Standard NFL DFS FLEX eligibility, same on both sites.
FLEX_ELIGIBLE_POSITIONS = {"RB", "WR", "TE"}

# Softmax temperature controlling how concentrated estimated_ownership_pct
# is within a position group -- lower = more winner-take-most, higher = flatter.
# UNFIT starting guess. Clearest first target for Session 11.1 retuning.
# Session 4.1 value preserved unchanged -- temperature is fit separately
# from the blend weights, so the Session 11.0 feature expansion doesn't
# change the right starting point here. Will be re-evaluated in 11.1.
OWNERSHIP_SOFTMAX_TEMPERATURE = 15.0

# Session (this change) -- first REAL fit against real ownership data, not
# just an unfit guess. Grid-searched per position group (T in [4..25])
# against real DK contest %Drafted from the Week 1 2026 main and early
# slates combined (499 matched real players across both), minimizing MAE
# between real ownership and this module's own softmax-implied estimate.
# RB got the clearest, most material win (T=11 vs the global 15: MAE 2.73
# vs 2.88, ~5% better); QB/WR/TE only moved the optimum a little (14/17/17)
# for a much smaller MAE gain. DST is deliberately NOT included here --
# there are only 32 possible DST values and far fewer real rows per slate
# to fit against, too thin a sample to trust a DST-specific number yet; it
# keeps using OWNERSHIP_SOFTMAX_TEMPERATURE above.
#
# IMPORTANT CAVEAT, flagged same as every other unfit constant in this file:
# this is fit against exactly TWO slates. That is enough to correct the
# original guess in the right direction and by a defensible amount, but
# nowhere near enough to trust a sharper fit (e.g. per-position-AND-per-
# salary-tier) without risking overfitting to these two specific slates'
# noise. Re-fit this dict again once more weeks of real contest ownership
# data are available -- do not hand-tune it further from vibes alone.
#
# This fit ALSO does not fully close the "top chalk plays are under-owned"
# gap documented from the same real data (e.g. a genuine ~47-50%-owned
# workhorse RB still lands around 25-35% here even at RB's own better-
# fit T=11) -- a single softmax temperature per position cannot
# simultaneously match the extreme top of the ownership distribution and
# the broad middle; closing that gap further needs a different mechanism
# (e.g. an explicit top-of-slate boost, or additional real features), not
# just a sharper single temperature, and shouldn't be attempted on two
# slates' worth of data.
OWNERSHIP_SOFTMAX_TEMPERATURE_BY_POSITION = {
    "QB": 14.0,
    "RB": 11.0,
    "WR": 17.0,
    "TE": 17.0,
}


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
    required = {
        "player_id", "player_name", "position", "salary",
        "final_projection", "implied_total", "over_under",
    }
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(
            f"{path} is missing expected columns: {sorted(missing)}. "
            f"build_projections.py's output schema may have changed -- "
            f"update this script's load_final_projections() to match. "
            f"Note: 'over_under' was added to final_projections_*.csv in "
            f"Session 3.3's addendum. If this column is missing, regenerate "
            f"the projections file with the current build_projections.py."
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


def compute_chalk_scores(df: pd.DataFrame, site: str, group_col: str = None) -> pd.DataFrame:
    """Session 13.3b: `group_col` lets a caller supply an alternate grouping
    column instead of the default classic `position_group` (built via
    build_position_group()) -- added so Showdown pools can group by
    roster_role (CPT/MVP vs FLEX, see build_showdown_role_group()) instead,
    since Showdown has no position-based roster slots for percentile-ranking
    to be meaningful against. Classic behavior is unchanged when group_col
    is omitted -- same code path, same default column, byte-identical
    output to every prior session's classic run."""
    df = df.copy()
    if group_col is None:
        df["position_group"] = build_position_group(df, site)
        group_col = "position_group"

    group_counts = df.groupby(group_col).size()
    thin_groups = group_counts[group_counts < MIN_GROUP_SIZE_FOR_RELIABLE_PERCENTILE]
    if not thin_groups.empty:
        print(
            f"WARNING: value_percentile/salary_tier_score/raw_projection_percentile "
            f"are less meaningful for thin '{group_col}' groups (same distortion "
            f"ROADMAP.md's 'Known Testing Artifact' note already flags "
            f"for this project's current test pool) -- group sizes: "
            f"{thin_groups.to_dict()}",
            file=sys.stderr,
        )

    # Decision #10 (Session 15.3, see module docstring): a floor on the
    # salary figure used below for value AND salary_tier -- NOT on the raw
    # `salary` column itself, which stays untouched for every other use
    # (display, the optimizer's actual cap-space math). Only these two
    # derived, ranking-only features use it.
    effective_salary = df["salary"].clip(lower=VALUE_SALARY_FLOOR)

    # Decision #1: value = projected points per $1K salary, percentile-
    # ranked within group_col so groups with structurally different raw
    # value ranges are comparable.
    # Defensive guard: a salary <= 0 would make this divide 0/0 -> NaN,
    # which propagates to a NaN chalk_score and hard-stops
    # build_projections.py's add_ownership_columns. A non-positive salary
    # yields value 0.0 (correctly the worst value), not NaN.
    safe_salary = effective_salary.where(effective_salary > 0)
    df["value"] = (df["final_projection"] / (safe_salary / 1000.0)).fillna(0.0)
    df["value_percentile"] = df.groupby(group_col)["value"].rank(pct=True) * 100

    # Decision #6 (Session 11.0): raw projected points, percentile-ranked
    # within group_col. Distinct from value -- captures "expected
    # ceiling" signal that value efficiency misses.
    df["raw_projection_percentile"] = (
        df.groupby(group_col)["final_projection"].rank(pct=True) * 100
    )

    # Decision #2: salary tier, U-shaped -- both ends of a group's salary
    # range score high, the middle scores low. Uses effective_salary (see
    # decision #10) for the same reason value does: below the floor, real
    # salary differences (e.g. $200 vs $300) don't reflect a real
    # difference in expected role, so they shouldn't drive a real
    # difference in how "cheap-tier chalk" this feature says a player is.
    salary_pct = df.assign(_eff_salary=effective_salary).groupby(group_col)["_eff_salary"].rank(pct=True)
    df["salary_tier_score"] = (salary_pct - 0.5).abs() * 2 * 100

    # Decision #3: vegas implied total, percentile-ranked across the WHOLE
    # pool (not position-grouped) -- a team's high implied total raises
    # attention on every position in that game alike. Bye-week players
    # carry implied_total == 0.0 (build_projections.py sentinel fill),
    # which correctly ranks them at the bottom here too.
    df["vegas_percentile"] = df["implied_total"].rank(pct=True) * 100

    # Decision #7 (Session 11.0): game over/under, percentile-ranked
    # across the full pool. Separate from implied_total -- captures
    # "shootout game" signal. Bye-week players carry over_under == 0.0,
    # correctly ranking at the bottom.
    df["over_under_percentile"] = df["over_under"].rank(pct=True) * 100

    # Decision #4: manual name-recognition flag, additive, shared across
    # sites, 0 for anyone not on the list.
    flags = load_name_recognition_flags()
    df = df.merge(flags, on="player_id", how="left")
    # Coerce flag_weight to numeric -- guards against object dtype when the
    # CSV is absent (empty-frame return) or header-only. See Session 10.3a
    # note in the original docstring for full reasoning.
    df["flag_weight"] = pd.to_numeric(df["flag_weight"], errors="coerce").fillna(0.0)
    n_flagged = (df["flag_weight"] > 0).sum()
    print(
        f"{n_flagged} player(s) received a name-recognition bonus "
        f"from {NAME_RECOGNITION_PATH.name}."
    )

    # Decision #8 (see module docstring): participation-confidence
    # dampening. `participation_confidence` scales from
    # PARTICIPATION_CONFIDENCE_FLOOR (no real evidence this player sees
    # the field) up to 1.0 (established full-season role). Only applied
    # where the signal exists -- DST/K have no participation_effective
    # concept and get 1.0 (unchanged), same as a projections file that
    # predates this column entirely.
    #
    # Decision #9 (Session 15.3, found via a real live run): a GENUINE
    # Week 1 -- the season's actual first slate, before any 2026 game has
    # been played -- gives EVERY skill player participation_effective ==
    # 0.0, established veteran or true rookie alike (statline_model.py
    # decision #14's cold-start path has no current-season history for
    # ANYONE to distinguish them by yet). Decision #8 as first shipped
    # could not tell that degenerate case apart from its intended one (a
    # normal week where SOME players are established and others aren't),
    # so it dampened every real skill player by the same amount while
    # leaving DST/K -- which never had a participation concept to dampen
    # in the first place -- untouched. Confirmed real on the actual NE/SEA
    # season-opener Showdown slate: the Seahawks defense reached 98.7%
    # estimated Captain ownership, ahead of every real player in the game,
    # for exactly this reason.
    #
    # Fixed by checking whether the pool has ANY real signal to act on at
    # all: if not one player anywhere shows participation_effective > 0,
    # there is nothing genuine to differentiate by, and the dampening is
    # skipped entirely (every player gets 1.0, matching how DST/K are
    # already treated) rather than uniformly deflating the whole skill
    # position pool relative to positions that were never subject to it.
    # The moment even one real player in the pool has accumulated true
    # in-season history (participation_effective > 0), this reverts to
    # decision #8's original per-player behavior automatically -- no
    # season-awareness or week-number logic needed, this is a property of
    # the data itself.
    if "participation_effective" in df.columns:
        participation = pd.to_numeric(df["participation_effective"], errors="coerce")
        # Session (this change) -- decision #9 originally required literally
        # EVERY player to be at 0.0 before skipping dampening, which only
        # catches a fully-degenerate all-zero slate. That's narrower than
        # the real failure mode: statline_model.py's participation window
        # can produce a MINORITY of the pool sitting at a nonzero-but-not-1.0
        # value from a boundary/lookback artifact (e.g. the Week 1 season-
        # rollover case apply_confirmed_starter_override() now corrects at
        # the source for clean, confirmed starters -- see that function's
        # clean_starter_partial block) while most of the pool is still a
        # genuine 0.0. Requiring a real MAJORITY of the pool to have signal
        # before trusting it at all is a coarser backstop for whatever this
        # threshold doesn't already catch upstream -- kept even after that
        # fix as cheap insurance, since it's scoped narrowly (depth_rank==1
        # only) and won't cover every possible degenerate-window artifact.
        MIN_REAL_SIGNAL_SHARE = 0.5
        share_real_signal = (participation.fillna(0) > 0).mean()
        has_real_signal = share_real_signal >= MIN_REAL_SIGNAL_SHARE
        if has_real_signal:
            df["participation_confidence"] = (
                PARTICIPATION_CONFIDENCE_FLOOR
                + (1 - PARTICIPATION_CONFIDENCE_FLOOR) * participation
            ).fillna(1.0)
        else:
            print(
                f"NOTE: only {share_real_signal:.1%} of skill-position players "
                "in this slate have participation_effective > 0.0 (below the "
                f"{MIN_REAL_SIGNAL_SHARE:.0%} threshold) -- a true Week 1/"
                "no-history slate, not a mix of established and unproven "
                "players. Decision #8's dampening (decision #9) is skipped "
                "entirely this run so real players aren't uniformly punished "
                "relative to DST/K, which have no participation concept at "
                "all.",
                file=sys.stderr,
            )
            df["participation_confidence"] = 1.0
    else:
        print(
            "NOTE: 'participation_effective' not found in this projections "
            "file -- chalk_score's participation-confidence dampening "
            "(decision #8) is skipped; every player gets a 1.0 (unchanged) "
            "multiplier.",
            file=sys.stderr,
        )
        df["participation_confidence"] = 1.0

    # 5-feature blend (Session 11.0). Weights are UNFIT starting guesses;
    # retuning target for Session 11.1.
    base_blend = (
        VALUE_WEIGHT        * df["value_percentile"]
        + PROJECTION_WEIGHT * df["raw_projection_percentile"]
        + SALARY_TIER_WEIGHT * df["salary_tier_score"]
        + VEGAS_WEIGHT      * df["vegas_percentile"]
        + OVER_UNDER_WEIGHT * df["over_under_percentile"]
    )

    # Real-data bug found while investigating "chalkiest plays get no pivot
    # suggestions" (pivot_finder.py): the weights above sum to 1.0, so
    # base_blend is already 0-100 on its own -- but the several best players
    # in a group are all percentile-ranked near 100 across every feature
    # (that's what makes them the best plays), leaving almost no headroom.
    # The OLD code then added flag_weight (0-20) flat and clipped to 100.
    # On a real slate this collapsed multiple genuinely-different star RBs
    # (base_blend ~99.6, ~93.5, ~91.4) to an IDENTICAL chalk_score of
    # exactly 100 the instant each got even a modest name-recognition bonus
    # -- which then produced identical estimated_ownership_pct for all of
    # them (see compute_estimated_ownership() below), so the single biggest
    # chalk play could never find a "less owned" alternative even though
    # one obviously existed.
    #
    # Fixed by scaling flag_weight into the REMAINING headroom instead of
    # adding it flat: a player already at 99.6 has only 0.4 points of
    # headroom left, so even a large name-recognition bonus can only close
    # a fraction of that tiny gap, rather than flattening him and his
    # nearest rivals to the same ceiling. This preserves flag_weight's
    # documented intent ("a modest nudge, not a dominant factor," decision
    # #4 above) instead of letting it silently become a dominant,
    # tie-creating factor exactly at the top of the distribution, where
    # ownership differentiation matters most.
    headroom = 100 - base_blend
    boosted_blend = base_blend + df["flag_weight"] * (headroom / 100.0)

    df["chalk_score"] = (boosted_blend * df["participation_confidence"]).clip(lower=0, upper=100)

    return df


# ---------------------------------------------------------------------------
# Step 2: Estimated ownership % (decision #5)
# ---------------------------------------------------------------------------

def compute_position_slot_budgets(site: str) -> dict:
    """Each position_group's total 'ownership budget,' in percentage
    points summed across every eligible player in that group -- anchored
    to real roster-slot math (see module docstring decision #5), not a
    guess. FLEX's budget is split evenly across RB/WR/TE (no real
    per-position FLEX usage-rate data exists yet -- retuning target for
    Session 11.2)."""
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

    # Internal consistency check -- total budget across all groups should
    # equal exactly len(roster_slots) * 100.
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


def compute_showdown_role_budgets(site: str) -> dict:
    """Session 13.3b: Showdown's equivalent of decision #5's roster-slot
    budget math, keyed by roster_role (CPT_MVP vs FLEX) instead of
    position. Showdown's real roster construction
    (SITE_CONFIGS[site]['showdown']['roster_slots'] -- Session 13.2,
    confirmed against real DK/FD exports and live roster builders) is
    exactly 1 CPT/MVP slot + N FLEX slots, with ANY position eligible in
    either -- so classic's position-based FLEX_ELIGIBLE_POSITIONS 3-way
    split has no meaning here; the FLEX budget stays as ONE undivided
    group instead. Still real roster-slot math, not a guess -- same
    anchor principle as compute_position_slot_budgets(), just regrouped
    for a pool structure that has no position-based slots at all."""
    slots = SITE_CONFIGS[site]["showdown"]["roster_slots"]
    n_flex = slots.count("FLEX")
    n_captain = len(slots) - n_flex
    return {"FLEX": n_flex * 100.0, "CPT_MVP": n_captain * 100.0}


def build_showdown_role_group(df: pd.DataFrame) -> pd.Series:
    """Session 13.3b: folds DK's 'CPT' / FD's 'MVP' roster_role values
    into one 'CPT_MVP' bucket, mirroring build_position_group()'s
    DST-label-folding pattern -- both sites' captain-equivalent slot
    shares the same 1.5x salary/scoring mechanic (Session 13.2/13.1), so
    they belong in the same ownership group for percentile-ranking
    purposes, exactly like DK's 'DST' and FD's 'D'/'DEF' do today."""
    return df["roster_role"].map({"CPT": "CPT_MVP", "MVP": "CPT_MVP", "FLEX": "FLEX"})


def compute_estimated_ownership(df: pd.DataFrame, site: str, group_col: str = None,
                                 budgets: dict = None) -> pd.DataFrame:
    """Decision #5 (see module docstring): converts chalk_score's relative
    ranking into an ESTIMATED ownership percentage, anchored to real
    roster-slot math, not to any real ownership data (none exists yet).
    Temperature and FLEX split are retuning targets for Session 11.1/11.2.

    Session 13.3b: `group_col`/`budgets` let a caller supply Showdown's
    roster_role grouping + compute_showdown_role_budgets() instead of the
    classic position_group/compute_position_slot_budgets() default.
    Classic behavior is unchanged when both are omitted."""
    df = df.copy()
    if group_col is None:
        group_col = "position_group"
    if budgets is None:
        budgets = compute_position_slot_budgets(site)

    # Bye/no-real-game players (final_projection == 0) get an explicit 0
    # weight so their share of the group's budget is fully redistributed
    # to real players -- see module docstring decision #5.
    #
    # Session (this change) -- per-position temperature (see
    # OWNERSHIP_SOFTMAX_TEMPERATURE_BY_POSITION's own comment for the real
    # fit this came from) when `group_col` is the classic position_group
    # (QB/RB/WR/TE/DST); Showdown's role-group grouping (CPT_MVP/FLEX) has
    # no per-position real ownership fit behind it yet, so it keeps the
    # single global constant unchanged.
    if group_col == "position_group":
        temperature = df[group_col].map(OWNERSHIP_SOFTMAX_TEMPERATURE_BY_POSITION) \
                                    .fillna(OWNERSHIP_SOFTMAX_TEMPERATURE)
    else:
        temperature = OWNERSHIP_SOFTMAX_TEMPERATURE
    has_signal = df["final_projection"] > 0
    df["_weight"] = 0.0
    df.loc[has_signal, "_weight"] = np.exp(
        df.loc[has_signal, "chalk_score"] / temperature
    )

    group_weight_sum = df.groupby(group_col)["_weight"].transform("sum")
    group_size = df.groupby(group_col)[group_col].transform("count")

    all_zero = group_weight_sum == 0
    if all_zero.any():
        affected = sorted(df.loc[all_zero, group_col].unique().tolist())
        print(
            f"WARNING: '{group_col}' group(s) {affected} have final_projection "
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

    df["_group_budget"] = df[group_col].map(budgets)
    df["estimated_ownership_pct"] = (
        df["_group_share"] * df["_group_budget"]
    ).clip(lower=0, upper=100)

    group_totals = df.groupby(group_col)["estimated_ownership_pct"].sum()
    print(
        f"estimated_ownership_pct summed per '{group_col}' group "
        "(should equal that group's roster-slot budget):"
    )
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
    n_chalk_out_of_range = (
        (result["chalk_score"] < 0) | (result["chalk_score"] > 100)
    ).sum()
    n_own_out_of_range = (
        (result["estimated_ownership_pct"] < 0)
        | (result["estimated_ownership_pct"] > 100)
    ).sum()
    print(f"Wrote {len(result)} players to {out_path}")
    print(f"  Nulls in any column:                     {n_null} (should be 0)")
    print(f"  chalk_score out of [0,100] range:        {n_chalk_out_of_range} (should be 0)")
    print(f"  estimated_ownership_pct out of [0,100]:  {n_own_out_of_range} (should be 0)")
