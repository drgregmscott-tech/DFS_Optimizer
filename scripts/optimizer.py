"""
optimizer.py
============

Session 3.1 -- Single Lineup Optimizer.

For a given site (DK/FD) and slate, reads that site's
`final_projections_{site}_{slate_id}.csv` (Session 2.4, extended in Session 3.1
to include DST/DEF -- see build_projections.py's module docstring, decision
#5) and solves for the single salary-cap-legal lineup that maximizes total
projected points, using each site's own cap/roster rules from
`ingest_salaries.py`'s `SITE_CONFIGS` (Session 1.3) rather than hardcoding
DK's numbers and assuming FD follows.

Design decisions (cleared with the same "flag, don't silently assume"
pattern as every prior session):

1. Solver: PuLP (already pinned in requirements.txt for exactly this
   phase, per Session 1.1's card). Uses PuLP's bundled CBC solver --
   no separate install needed. This is an integer LINEAR program, so
   CBC's branch-and-bound finds a certified GLOBAL optimum for a problem
   this size (9 slots, ~90 players) essentially instantly -- there is no
   approximation/heuristic risk here, which is what makes the roadmap's
   second validation checkbox ("no single-player swap would increase
   points without breaking a constraint") mathematically guaranteed by
   construction, not just something to eyeball.

2. FLEX eligibility = {RB, WR, TE}. This is standard classic-contest DFS
   rule on both DK and FD, but it is NOT present anywhere in
   `SITE_CONFIGS` (Session 1.3 only stores the roster_slots list itself,
   e.g. [...,"TE","FLEX","DST"], not which positions can fill FLEX).
   Hardcoded here as `FLEX_ELIGIBLE_POSITIONS` rather than silently
   assumed inline, flagged as a convention this project has never
   explicitly confirmed with the user -- if a future site/format allows
   QB in flex (superflex) this constant is the one place to change.

3. Constraint formulation: rather than one binary decision variable per
   (player, specific slot) -- which would need arbitrary tie-breaking
   between e.g. "RB slot 1" and "RB slot 2" for two interchangeable RBs
   -- this uses one binary variable per PLAYER (selected or not), with
   aggregate count constraints per position:
   - non-flex-eligible positions (QB, DST/DEF): exact count required.
   - flex-eligible positions (RB, WR, TE): each >= its own fixed
     minimum, and the RB+WR+TE pool together == fixed minimums + FLEX
     count. This is the standard DFS-optimizer ILP formulation and is
     equivalent to true per-slot assignment for any single-lineup
     problem, but avoids a meaningless symmetry the solver would
     otherwise have to break arbitrarily (which specific RB fills
     "RB1" vs "RB2" doesn't matter -- only which 2 RBs are selected
     does). Human-readable slot labels (RB1/RB2/FLEX/etc) are assigned
     AFTER solving, cosmetically, for the output file's `roster_slot`
     column -- this labeling never affects the optimization itself.

4. Zero-projection players (bye-week skill players and defenses --
   Session 2.4's decision #4b / this session's decision #5 in
   build_projections.py) are NOT filtered out of the player pool before
   optimizing. They're left in deliberately: the ILP will naturally
   never select a 0.0-projection player over a positive-projection
   alternative at the same or lower salary (there's no cap benefit to
   spending money on a locked $0), so filtering them out first would be
   redundant, not incorrect -- but leaving them in doubles as a live
   correctness check: if a bye-week player ever DOES get selected,
   something upstream (or in this file's constraints) is broken, since
   that should be mathematically impossible while any legal alternative
   exists at the same slot.

Usage:
    python3 optimizer.py --site dk --slate-id classic_wk10
    python3 optimizer.py --site fd --slate-id classic_wk10

Outputs:
    output/lineup_single_{site}_{slate_id}.csv
    One row per roster slot: roster_slot, player_name, position, team,
    salary, projection. Also prints total salary used, cap remaining,
    and total projected points to stdout.
"""

import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pulp

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest_salaries import SITE_CONFIGS  # noqa: E402 -- Session 1.3's single source of truth for cap/roster/scoring per site

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "output"

# See decision #2 above -- not present in SITE_CONFIGS, hardcoded here as
# the one place to change if a future site/format needs a different rule
# (e.g. superflex allowing QB in FLEX).
FLEX_ELIGIBLE_POSITIONS = {"RB", "WR", "TE"}
FLEX_SLOT_LABEL = "FLEX"

# ---------------------------------------------------------------------------
# Session 3.2 -- Multi-Lineup Generation + Exposure Limits
# ---------------------------------------------------------------------------
# Extends (does not replace) the single-lineup ILP above. Re-solves the same
# formulation repeatedly -- one legal, optimal-given-current-constraints
# lineup per iteration -- rather than any heuristic top-N or random shuffle.
# See decisions #5-8 below (continuing the numbering from the module
# docstring's Session 3.1 decisions).
#
# 5. Exposure cap enforcement is a HARD constraint (locking a player out of
#    the candidate pool entirely once they hit the cap), not a soft penalty
#    in the objective. A soft penalty could still let a player exceed the
#    cap if no better lineup exists without them -- the roadmap's validation
#    checkbox ("confirm no player exceeds the exposure cap set") asks for a
#    guarantee, not a probability, matching this project's general
#    "structural guarantee, not eyeballing" pattern (see Session 3.1's
#    decision #1 re: certified ILP optimum).
#
# 6. Exposure cap rounding: floor(max_exposure_pct * n_lineups), floored at
#    a MINIMUM of 1 rather than allowed to hit 0. A literal floor could
#    round to 0 for a small n_lineups/max_exposure_pct combination (e.g.
#    5% cap * 10 lineups = 0.5 -> floor 0), which would silently forbid a
#    player from ever being selected -- indistinguishable from a ban, not
#    what "no more than X%" implies. `max(1, floor(...))` used instead.
#
# 7. Lineup diversity is enforced with a HARD minimum-swap constraint
#    between every pair of lineups (each new lineup must differ from every
#    previously generated lineup in at least `uniqueness` players),
#    not a soft/randomized approach (e.g. adding noise to projections each
#    iteration). This keeps uniqueness auditable and guaranteed rather than
#    probabilistic. Known tradeoff, flagged rather than hidden: this
#    project's real-data test pool is thin (see ROADMAP.md's "Known Testing
#    Artifact" note -- only 4 non-zero-projection QBs in the 91-player DK
#    Madden Stream test pool), so a strict uniqueness floor can make later
#    lineups infeasible well before `n_lineups` is reached. Handled by
#    progressively relaxing `uniqueness` (by 1 each time a solve goes
#    infeasible) rather than crashing or silently stopping -- every
#    relaxation is printed to stderr, and if it's relaxed all the way to 0
#    and still infeasible, generation stops early with a clear count of how
#    many lineups were actually produced. This is a property of the small
#    test pool, not the algorithm -- expected to resolve itself against a
#    real, full-size slate the same way the "top 10" distortion did
#    (ROADMAP.md, same note).
#
#    Naming/default note (user addendum, 2026-07-22): this parameter was
#    originally implemented as `min_unique_swaps` with a default of 3.
#    Renamed to `uniqueness` (--uniqueness) to match standard DFS-optimizer
#    terminology, and the default changed to 1 to match the standard
#    convention -- both user-confirmed, not independently decided. The
#    mechanic itself (hard per-pair minimum-swap constraint, with automatic
#    relaxation on infeasibility) is unchanged.
#
# 8. Default exposure cap: 40% (`DEFAULT_MAX_EXPOSURE_PCT = 0.40`), matching
#    the example figure in the roadmap card itself. Kept the SAME for both
#    DK and FD by default rather than site-specific -- exposure is a
#    portfolio-construction choice (how much you're willing to bet on one
#    player being right) that doesn't have an obvious reason to differ by
#    site's salary cap or roster rules the way, say, chalk_score (Session
#    4.1, salary-tier-dependent) would. `--max-exposure` is exposed as a
#    CLI flag either way, so a future session or a live run can override
#    per-site without a code change if real usage shows a reason to.
DEFAULT_N_LINEUPS = 20
DEFAULT_MAX_EXPOSURE_PCT = 0.40
DEFAULT_UNIQUENESS = 1

# Session 7.3 -- Salary Floor (decision #28). 0 means "no floor," identical
# to every prior session's behavior (the ILP's own <= salary_cap constraint
# is the only salary constraint). A value > 0 (e.g. 95) adds a companion
# >= constraint at that %% of the site's cap, so a lineup can't leave more
# money on the table than the user wants -- most useful in regular-season
# slates where a thin, cheap-heavy lineup is rarely optimal anyway, but
# previously nothing stopped the solver from returning one if the
# objective happened to prefer it.
DEFAULT_MIN_SALARY_PCT = 0.0

# Session 15 (Pre-Season Hardening) -- decision #A2. Real Week 1 2026 data
# (a real DK slate, Colts QBs) showed a genuine current starter (Daniel
# Jones, back from a late-2025 injury, 13 real starts before that) ranked
# BELOW his own team's QB3 (Riley Leonard, 5 relevant games, one fluky
# season-ending garbage-time outing) -- traced to statline_model.py's
# participation signal, which cannot tell "missed the last month hurt, full
# workload now" from "is a permanent backup" (that gap is named explicitly
# in statline_model.py's own decision #9). Rather than build a second,
# unproven heuristic to guess which case a low-participation player is in,
# this is a hard floor: below threshold, out of the pool, full stop. The
# `--lock` flag (already existed, decisions #22/#23) is the deliberate
# human override for a case like Jones, where you know the real-world
# context the model can't see. ON by default -- a safety net that has to be
# remembered every slate isn't much of one. QB is strict (the position is
# structurally closest to winner-take-all: one real starter almost every
# week); RB/TE are moderate (real committees still show up on the field
# most weeks, so this only catches players who are genuinely inactive more
# often than not); WR is unrestricted by default (deep, egalitarian
# rotations make a low participation reading far less diagnostic there).
# User-confirmed defaults, 2026-08-14 -- not fit to data, a considered
# judgment call the same way SALARY_TOLERANCE_PCT_OF_CAP and other
# starting heuristics in this project were. First retuning target once
# real-season roster-decision outcomes exist to check it against.
DEFAULT_PARTICIPATION_FLOORS = "QB:0.6,RB:0.4,TE:0.4"

# ---------------------------------------------------------------------------
# Session 3.2 (addendum) -- Projection randomization
# ---------------------------------------------------------------------------
# User-requested addition after Session 3.2 shipped: an optional knob that
# lets the optimizer select against a randomized version of each player's
# projection, rather than always the exact `final_projection` value, as a
# second (complementary, not replacement -- user-confirmed) diversity lever
# alongside decision #7's hard swap constraint. Continuing the numbering:
#
# 9. Distribution: NORMAL (Gaussian), centered on the real `final_projection`,
#    with standard deviation = `randomization_pct` of that same real value
#    (e.g. pct=10 -> std_dev = 0.10 * final_projection). Chosen over a hard
#    uniform +/-X% bound after a quick industry check (FantasyCruncher PRO's
#    published approach, and the open-source `dfs-with-r/coach` optimizer,
#    both draw from a normal/log-normal distribution scaled off the
#    projection rather than a flat uniform window) -- this matches how real
#    DFS tools model projection uncertainty, and was the user's own stated
#    preference. Values are clipped at a floor of 0.0 (no negative fantasy
#    points) -- flagged, not hidden, that this clip makes the *realized*
#    distribution slightly right-skewed for low-projection players whose
#    std dev is large relative to their mean (mostly punt-salary players).
#
# 10. OFF by default (`randomization_pct=0`) -- reproduces every prior
#     session's exact deterministic behavior unchanged unless explicitly
#     requested via `--randomization-pct`, matching this project's "never
#     silently change existing behavior" pattern.
#
# 11. Randomization touches ONLY the ILP's objective (which players look
#     attractive enough to select) -- never salary, position, or the
#     `projection` value written to the output CSV. Every output row always
#     reports the player's REAL `final_projection`, not the noisy draw used
#     to pick them, so total-points figures in the output stay real,
#     auditable numbers rather than whatever noise got drawn that iteration.
#
# 12. Independent draw per lineup (user-confirmed): in multi-lineup mode, a
#     fresh random draw is taken for every lineup in the batch, not one
#     draw reused across the whole batch -- this is what actually makes
#     randomization function as a diversity lever lineup-to-lineup, used
#     TOGETHER WITH (not instead of) decision #7's hard swap constraint,
#     per explicit user direction.
#
# 13. Reproducibility: optional `--seed` flag seeds the RNG so a specific
#     run can be exactly replayed (used by this addendum's own validation
#     run, and useful for debugging a specific generated lineup later).
#     Omitted by default -- normal usage is genuinely random every run.
#
# 14. (Session 10.5, decision #3) SIGMA-MODE RANDOMIZATION is additive, not
#     a reinterpretation of pct-mode. `randomization_mode="pct"` (default)
#     is byte-identical to every prior session in every way. When
#     `randomization_mode="sigma"` is chosen, the per-player std_dev is
#     `pct/100 * sigma` rather than `pct/100 * final_projection`. Everything
#     else is unchanged: same clipping, same one-draw-per-lineup, same seed.
#     The entry-count scale (0 at n=1, linear to 1.0 at
#     DEFAULT_SIGMA_RAND_FULL_LINEUPS) is FLAGGED ARBITRARY -- no data
#     behind this schedule; first retuning target after the sweep.
#     Sigma-mode requires sigma in the pool (same pre-solve guard as lambda).
DEFAULT_RANDOMIZATION_PCT = 0.0
# Session 10.5 decision #3: n_lineups at which sigma-mode randomization
# reaches full scale. Linear ramp from 0 at n=1. FLAGGED ARBITRARY.
DEFAULT_SIGMA_RAND_FULL_LINEUPS = 20


# ---------------------------------------------------------------------------
# Session 3.3 -- Stacking Rules
# ---------------------------------------------------------------------------
# Continuing the numbering from Session 3.2's addendum decisions (#9-13).
#
# 14. Four independent stack modes, chosen via --stack-mode:
#     - "qb": QB + N teammates from --stack-positions. Covers Standard/
#       Double/Triple stacks and QB+RB depending on --stack-size and
#       --stack-positions -- these are all the same mechanism, just
#       different N/eligible-positions. Optionally extended with
#       --bring-back (an opponent player added on top).
#     - "game": Game Stack/Shootout -- no QB required, just a minimum
#       combined player count from both teams in one game, with at least
#       one player from each side.
#     - "mini": Mini-Stack -- either same-team RB+DST correlation, or two
#       opposing pass-catchers in one game, via --mini-stack-type.
#     - "none" (default): no stacking: existing Session 3.1/3.2 behavior
#       unchanged, byte-for-byte.
#
# 15. Enforcement is a HARD ILP constraint, same pattern as every other
#     constraint in this file (exposure, uniqueness, roster/salary) --
#     user-confirmed: "if stacking is enabled it is mandatory for every
#     lineup generated ... if disabled, no stacking is required." Not a
#     soft bonus added to the objective -- a soft bonus could still produce
#     an unstacked lineup if it scored higher, which isn't what "mandatory"
#     means.
#
# 16. Team/game selection: AUTO by default (highest Vegas implied_total for
#     QB/mini-stack team selection, highest over_under for game-stack),
#     with --stack-team/--stack-game as an explicit pin -- user-confirmed:
#     "both -- auto by default, with a CLI override available." Auto-
#     selection is restricted up front to teams/games that actually have
#     viable (non-zero-projection) players at every required role --
#     avoids wasting a solve attempt on a team whose QB or partner is a
#     confirmed bye/zero (decision #4b in build_projections.py).
#
# 17. Multi-lineup diversification: when auto-selecting (no explicit pin),
#     the batch ROTATES across a candidate pool of the top
#     --stack-candidate-pool teams/games by default, rather than repeating
#     one team/game across all N lineups. An explicit --stack-team/
#     --stack-game PINS the whole batch to that one target and
#     diversification does not apply, regardless of --stack-diversify --
#     user-confirmed: "most often this will be [diversify] ... but the
#     user needs to be able to say 'I want 20 stacked lineups from this
#     game only.'" --stack-diversify {auto,on,off} can force diversify on
#     or off explicitly when auto-selecting (it has no effect when a team/
#     game is pinned; a printed note flags this if the combination is
#     given, rather than silently ignoring the flag).
#
# 18. Stack partner positions default to {WR, TE, RB} (user-confirmed:
#     "any pass-catcher" -- RB included since some offenses use a
#     pass-catching RB as the correlated piece, e.g. a QB+RB checkdown
#     stack). Configurable via --stack-positions (comma-separated).
#
# 19. Bring-back pool is QB/RB/WR/TE from the opponent -- excludes the
#     opponent's DST/DEF deliberately: a shootout benefits the opponent's
#     SKILL players, not their defense, whose output is inversely
#     correlated with their own offense giving up a lot of points in a
#     shootout.
#
# 20. validate_stack() mirrors validate_lineup()'s existing pattern -- an
#     automated structural assertion that the requested stack actually
#     landed in the final lineup, not just trusted from the solver's
#     constraints (same "guarantee, not eyeballing" pattern as every other
#     validation in this file). Directly answers the roadmap's first
#     Session 3.3 validation checkbox.
#
# 21. An impossible stack request (a team/game with no legal partner at the
#     required position/count within the current candidate pool) raises a
#     RuntimeError from add_stack_constraints() BEFORE the solver even
#     runs, with a specific reason -- "fails loudly, not silently" (the
#     roadmap's second Session 3.3 validation checkbox), and cheaper than
#     waiting for an ILP infeasibility. A request that's only infeasible
#     for subtler reasons (e.g. legal partners exist but salary cap can't
#     fit all of them) still falls through to the solver and raises via
#     the existing "Solver did not find an optimal solution" path in
#     solve_lineup() -- both paths fail loudly, neither silently drops the
#     stack requirement.
DEFENSE_POSITION_LABELS = {"DST", "D", "DEF"}  # both sites' labels (Session 1.3's log)
STACK_ELIGIBLE_QB_PARTNER_POSITIONS = {"WR", "TE", "RB"}

DEFAULT_STACK_MODE = "none"
DEFAULT_STACK_SIZE = 1
# Session 7.3, decision #31: tightened from "WR,TE,RB" -- RB production
# doesn't correlate with the QB's own passing stats the way WR/TE does
# (rushing yards/TDs are a largely separate pool from passing yards/TDs),
# so defaulting to include it muddied what a QB stack is theoretically
# supposed to capture. Still fully supported as an opt-in via
# --stack-positions (STACK_ELIGIBLE_QB_PARTNER_POSITIONS unchanged) --
# only the DEFAULT changed, not what's allowed.
DEFAULT_STACK_POSITIONS = "WR,TE"
DEFAULT_GAME_STACK_MIN_PLAYERS = 4
DEFAULT_STACK_CANDIDATE_POOL = 5
DEFAULT_STACK_DIVERSIFY = "auto"  # auto | on | off -- see decision #17


def parse_stack_positions(raw: str) -> set:
    positions = {p.strip().upper() for p in raw.split(",") if p.strip()}
    invalid = positions - STACK_ELIGIBLE_QB_PARTNER_POSITIONS
    if invalid:
        raise SystemExit(
            f"--stack-positions has invalid position(s) {sorted(invalid)} -- "
            f"only {sorted(STACK_ELIGIBLE_QB_PARTNER_POSITIONS)} are eligible "
            f"QB-stack partners (decision #18)."
        )
    return positions


def parse_flex_positions(raw: str) -> set:
    """Session 7.3 -- FLEX Eligibility Restriction (decision #29). Validates
    a user-supplied subset of FLEX_ELIGIBLE_POSITIONS (RB/WR/TE) -- e.g.
    'WR,RB' to exclude TE from FLEX entirely. Empty/whitespace-only entries
    are ignored the same way --stack-positions handles them."""
    positions = {p.strip().upper() for p in raw.split(",") if p.strip()}
    invalid = positions - FLEX_ELIGIBLE_POSITIONS
    if invalid:
        raise SystemExit(
            f"--flex-positions has invalid position(s) {sorted(invalid)} -- "
            f"only {sorted(FLEX_ELIGIBLE_POSITIONS)} are FLEX-eligible at all."
        )
    if not positions:
        raise SystemExit("--flex-positions was given but resolved to an empty set.")
    return positions


def parse_team_pair(raw: str, flag_name: str) -> tuple:
    parts = [p.strip().upper() for p in raw.split("-")]
    if len(parts) != 2:
        raise SystemExit(f"{flag_name} must be TEAM-TEAM (e.g. KC-BUF), got: {raw!r}")
    return tuple(parts)


def parse_team_list(raw: str, flag_name: str) -> list:
    """Session 7.3 addition (decision #32) -- lets --stack-team pin MORE
    THAN ONE team (e.g. 'KC,SEA'), reusing the existing candidate-rotation
    machinery (originally built for auto-select diversification, decision
    #17) to rotate the batch across exactly the teams the user picked,
    instead of only ever pinning to one. A single team (no comma) still
    works exactly as before."""
    teams = [t.strip().upper() for t in raw.split(",") if t.strip()]
    if not teams:
        raise SystemExit(f"{flag_name} resolved to an empty team list: {raw!r}")
    return teams


def parse_game_list(raw: str, flag_name: str) -> list:
    """Same idea as parse_team_list, for --stack-game: comma-separates
    multiple TEAM-TEAM pairs (e.g. 'KC-BUF,SEA-ARI')."""
    pairs = [p.strip() for p in raw.split(",") if p.strip()]
    if not pairs:
        raise SystemExit(f"{flag_name} resolved to an empty game list: {raw!r}")
    return [parse_team_pair(p, flag_name) for p in pairs]


# ---------------------------------------------------------------------------
# Session 12 -- Team / Game Exposure Caps (decisions #36-38)
# ---------------------------------------------------------------------------
# 36. Two independent MAXIMUM constraints, additive to (not a replacement
#     for) the existing stacking MINIMUMs above -- a game stack's "at least
#     4 combined" and a game cap's "at most 3 combined" can be requested at
#     the same time; if they contradict, that surfaces the same way every
#     other constraint conflict does in this file: the solver returns
#     non-Optimal and solve_lineup() raises its existing generic RuntimeError
#     (no special-cased pre-check for this interaction, same reasoning as
#     decision #24's note that lock-vs-stack conflicts aren't pre-checked
#     either -- only STRUCTURAL infeasibility, independent of what else was
#     requested, gets a dedicated upfront check).
# 37. Multiple simultaneous caps are supported for both flags (e.g.
#     "KC:2,DEN:1" or "KC-DEN:4,SEA-ARI:3"), matching this file's existing
#     comma-list convention (decision #32's parse_team_list/parse_game_list).
# 38. A cap on a team/game with an unknown label (typo, or that team has a
#     bye and simply isn't in this slate's pool) is NOT a hard error -- it's
#     a real possibility (byes) as well as a likely typo, so it prints a
#     non-fatal NOTE (same pattern as an unmatched --exclude id) rather than
#     stopping the run. The constraint itself is still added -- with no
#     matching players, the resulting `<= cap` constraint is simply always
#     satisfied, a harmless no-op.
def parse_participation_floors(raw: str, flag_name: str) -> dict:
    """Parses '--participation-floors QB:0.6,RB:0.4,TE:0.4' into
    {'QB': 0.6, 'RB': 0.4, 'TE': 0.4}. A position simply absent from the
    string has no floor (0.0 -- unrestricted), matching WR's own default.
    Same parse shape as parse_team_cap_list() below, kept as a separate
    function rather than a generalized one because the value here is a
    0.0-1.0 participation share, not an integer roster-slot count, and the
    error messages should say so specifically rather than genericize."""
    floors = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if ":" not in entry:
            raise SystemExit(
                f"{flag_name} entries must be POSITION:FLOOR (e.g. QB:0.6), "
                f"got: {entry!r}"
            )
        pos, _, floor_raw = entry.partition(":")
        pos = pos.strip().upper()
        try:
            floor = float(floor_raw.strip())
        except ValueError:
            raise SystemExit(f"{flag_name} entry {entry!r} has a non-numeric floor.")
        if not (0.0 <= floor <= 1.0):
            raise SystemExit(
                f"{flag_name} entry {entry!r} -- floor must be between 0.0 "
                f"and 1.0 (it's a share of games played, not a percentage)."
            )
        if pos in floors:
            raise SystemExit(f"{flag_name} lists position {pos} more than once.")
        floors[pos] = floor
    return floors


def apply_participation_floor(players: pd.DataFrame, participation_floors: dict,
                              locked_player_ids: set) -> pd.DataFrame:
    """Session 15, decision #A2. Shared by build_single_lineup() and
    build_multi_lineup() -- same filter, same exemptions, one place to
    fix it. Excludes any player whose position has a configured floor AND
    whose participation_effective is below it, UNLESS locked (decision
    #22/#23's existing override) or exempt (no games-played history at
    all, or a confirmed no-game week this slate -- see
    build_projections_statline.py's AUDIT_COLUMNS comment for why those
    read as NaN rather than 0.0). A position absent from
    participation_floors, or an empty participation_floors dict entirely
    (e.g. --participation-floors ''), is a no-op -- identical behavior to
    today, same convention as --min-projection at 0.0."""
    if not participation_floors:
        return players
    if "participation_effective" not in players.columns:
        print(
            "NOTE: --participation-floors was requested but this pool's "
            "final_projections file has no participation_effective column "
            "(built before this fix, or built without --volume-prior) -- "
            "floor skipped for this build. Re-run build_projections_"
            "statline.py --volume-prior to enable it.",
            file=sys.stderr,
        )
        return players

    pos = players["position"].astype(str)
    floor = pos.map(participation_floors).fillna(0.0)
    part = pd.to_numeric(players["participation_effective"], errors="coerce")
    below_floor = players[
        part.notna() & (part < floor) & (floor > 0.0)
        & (~players["player_id"].isin(locked_player_ids))
    ]
    if len(below_floor):
        print(
            f"Pool filter: excluding {len(below_floor)} player(s) below "
            f"their position's --participation-floors threshold "
            f"(decision #A2): " + ", ".join(
                f"{r.player_name} ({r.position}, participation "
                f"{r.participation_effective:.2f} < {participation_floors.get(r.position, 0.0):.2f})"
                for r in below_floor.itertuples()
            ),
            file=sys.stderr,
        )
    return players[
        ~(part.notna() & (part < floor) & (floor > 0.0))
        | players["player_id"].isin(locked_player_ids)
    ].copy()


# ---------------------------------------------------------------------------
# Session 16 -- Thumbs Up/Down Projection Nudge (decisions #48-51)
# ---------------------------------------------------------------------------
# 48. A fixed, symmetric multiplier used ONLY as (or to center) the ILP
#     objective -- the exact same seam randomize_projections() already
#     established for --randomization-pct (decision #11): players
#     [\"final_projection\"] itself is NEVER touched, so a flagged player's
#     real, pipeline-calculated projection is always what's reported in
#     the output CSV and every downstream total (lineup_value, Total
#     projected points, etc.) -- never an inflated/deflated number. sigma
#     (the variance figure driving GPP scoring) is also left untouched: a
#     thumbs vote is a belief about the mean outcome, not new statistical
#     confidence about its spread.
# 49. Applied here, inside optimizer.py, at the same point randomization's
#     own draw is built -- well downstream of the real pipeline
#     (build_projections_statline.py) and the ownership model
#     (ownership_heuristic.py), which have both already finished by the
#     time this file ever runs. That means the user's personal opinion
#     never contaminates the ownership model's field-consensus estimate
#     (already computed and merged into final_projections before this
#     file runs) or the real actual-vs-projected accuracy log this
#     project is waiting on for Session 9.1/11.1. Deliberately NOT wired
#     into --min-projection/--participation-floors (both still filter on
#     the real number, same as every build before this session) -- a
#     thumbs vote nudges the solver's preference among already-eligible
#     players, it does not override a floor that exists to keep a
#     genuinely bad play out of consideration, matching this session's own
#     decision to skip a minimum-exposure floor for the same reason.
# 50. THUMBS_UP_MULTIPLIER / THUMBS_DOWN_MULTIPLIER are FLAGGED ARBITRARY,
#     same status as this project's other hand-picked, not-yet-fit
#     constants -- but not a blind guess: chosen from a real probe against
#     the live Week 1 FD Classic pool. A 10% boost moved three real fringe
#     players (RB/WR/TE, all previously 0/20 in a real 20-lineup batch at
#     40% max exposure) into a real, meaningfully-sized fraction of
#     lineups (5-25%) without maxing out the exposure cap the way 15%+
#     did for two of the three. Because the exposure cap (decision #5/#6,
#     unchanged here) is always the hard ceiling, this multiplier can
#     never functionally reproduce --lock (100%, every lineup) regardless
#     of its size -- it can only ever push a player up toward whatever cap
#     is already active.
# 51. A player_id in both --thumbs-up and --thumbs-down is a hard CLI
#     error, same "not a silent precedence rule" convention as decision
#     #25's --lock/--exclude overlap check. An id not found in the current
#     pool is a non-fatal NOTE (same as an unmatched --exclude id) --
#     ignored, since a since-scratched or renamed player shouldn't hard-
#     fail an otherwise-valid build.
THUMBS_UP_MULTIPLIER = 1.10
THUMBS_DOWN_MULTIPLIER = 0.90


def compute_thumbs_projection(players: pd.DataFrame, thumbs_up_ids: set,
                               thumbs_down_ids: set):
    """Returns None if no player is flagged -- callers use that to mean
    'no override, behave exactly as before this session' (same convention
    as optimization_projection=None already means for solve_lineup()).
    When non-None: a pd.Series indexed by player_id, equal to
    players['final_projection'] for every player EXCEPT those flagged,
    whose value is multiplied by THUMBS_UP_MULTIPLIER/THUMBS_DOWN_
    MULTIPLIER (decisions #48-51 above). Classic-pool version -- player_id
    is unique here. See compute_thumbs_projection_showdown() for the
    Showdown counterpart (player_id collides across CPT/FLEX rows)."""
    thumbs_up_ids = thumbs_up_ids or set()
    thumbs_down_ids = thumbs_down_ids or set()
    if not thumbs_up_ids and not thumbs_down_ids:
        return None

    base = players.set_index("player_id")["final_projection"]
    missing = (thumbs_up_ids | thumbs_down_ids) - set(base.index)
    if missing:
        print(
            f"NOTE: --thumbs-up/--thumbs-down player_id(s) {sorted(missing)} "
            f"not found in this pool -- ignored.", file=sys.stderr,
        )

    adjusted = base.copy()
    up = [pid for pid in thumbs_up_ids if pid in adjusted.index]
    down = [pid for pid in thumbs_down_ids if pid in adjusted.index]
    if up:
        adjusted.loc[up] = adjusted.loc[up] * THUMBS_UP_MULTIPLIER
    if down:
        adjusted.loc[down] = adjusted.loc[down] * THUMBS_DOWN_MULTIPLIER
    print(
        f"Projection adjustment for THIS SOLVE only (decisions #48-49) -- "
        f"the output still reports each player's real projection: {len(up)} "
        f"player(s) boosted {THUMBS_UP_MULTIPLIER:.0%}, {len(down)} "
        f"player(s) reduced to {THUMBS_DOWN_MULTIPLIER:.0%} of real "
        f"projection for solving purposes."
    )
    return adjusted


def parse_team_cap_list(raw: str, flag_name: str) -> dict:
    """Parses '--max-team-players KC:2,DEN:1' into {'KC': 2, 'DEN': 1}."""
    caps = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if ":" not in entry:
            raise SystemExit(
                f"{flag_name} entries must be TEAM:N (e.g. KC:2), got: {entry!r}"
            )
        team, _, n_raw = entry.partition(":")
        team = team.strip().upper()
        try:
            n = int(n_raw.strip())
        except ValueError:
            raise SystemExit(f"{flag_name} entry {entry!r} has a non-integer cap.")
        if n < 0:
            raise SystemExit(f"{flag_name} entry {entry!r} -- cap cannot be negative.")
        if team in caps:
            raise SystemExit(f"{flag_name} lists team {team} more than once.")
        caps[team] = n
    if not caps:
        raise SystemExit(f"{flag_name} resolved to an empty cap list: {raw!r}")
    return caps


def parse_game_cap_list(raw: str, flag_name: str) -> dict:
    """Parses '--max-game-players KC-DEN:4,SEA-ARI:3' into
    {frozenset({'KC','DEN'}): 4, frozenset({'SEA','ARI'}): 3}. Keyed by
    frozenset (not the ordered tuple parse_team_pair returns) so KC-DEN
    and DEN-KC are treated as the same game."""
    caps = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if ":" not in entry:
            raise SystemExit(
                f"{flag_name} entries must be TEAM-TEAM:N (e.g. KC-DEN:4), "
                f"got: {entry!r}"
            )
        pair_raw, _, n_raw = entry.partition(":")
        team_a, team_b = parse_team_pair(pair_raw.strip(), flag_name)
        try:
            n = int(n_raw.strip())
        except ValueError:
            raise SystemExit(f"{flag_name} entry {entry!r} has a non-integer cap.")
        if n < 0:
            raise SystemExit(f"{flag_name} entry {entry!r} -- cap cannot be negative.")
        key = frozenset({team_a, team_b})
        if key in caps:
            raise SystemExit(f"{flag_name} lists game {team_a}-{team_b} more than once.")
        caps[key] = n
    if not caps:
        raise SystemExit(f"{flag_name} resolved to an empty cap list: {raw!r}")
    return caps


# ---------------------------------------------------------------------------
# Session 16 -- Per-Player Exposure Override (decisions #52-55)
# ---------------------------------------------------------------------------
# 52. --player-exposure PID:PCT,PID:PCT (PCT is a 0.0-1.0 fraction, the
#     same convention --max-exposure itself already uses -- NOT a 0-100
#     integer like --max-team-players' counts above, since this is a
#     share of lineups, not a roster-slot count). A player named here uses
#     HIS OWN cap for the whole batch instead of --max-exposure's shared
#     default; every other player is unaffected.
# 53. Showdown: capped by real player_id, which already (pre-existing,
#     unchanged) tracks a player's Captain and FLEX rows as ONE combined
#     exposure count. Decision #52's override follows that same existing
#     convention automatically -- one cap per person, covering both roles,
#     not a separate cap per role.
# 54. A player who is BOTH locked AND given an explicit override is a hard
#     error, checked in validate_exposure_cap_feasibility() below (same
#     spot the other exposure-cap structural conflicts are already
#     checked) -- a lock already means "100% of lineups", so a lower
#     override on the same id can never be satisfiable.
# 55. An id not found in the current pool is a non-fatal NOTE, same as an
#     unmatched --exclude id -- checked in the same place as decision #54.
def parse_player_exposure_list(raw: str, flag_name: str) -> dict:
    """Parses '--player-exposure 00-0012345:0.5,00-0067890:0.3' into
    {'00-0012345': 0.5, '00-0067890': 0.3}. Same comma-list shape as
    parse_team_cap_list() above, but a 0.0-1.0 fraction (matching
    --max-exposure's own convention), not an integer count."""
    caps = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if ":" not in entry:
            raise SystemExit(
                f"{flag_name} entries must be PLAYER_ID:PCT (e.g. "
                f"00-0012345:0.5), got: {entry!r}"
            )
        pid, _, pct_raw = entry.partition(":")
        pid = pid.strip()
        try:
            pct = float(pct_raw.strip())
        except ValueError:
            raise SystemExit(f"{flag_name} entry {entry!r} has a non-numeric percentage.")
        if not (0.0 < pct <= 1.0):
            raise SystemExit(
                f"{flag_name} entry {entry!r} -- percentage must be greater "
                f"than 0.0 and at most 1.0 (it's a fraction of lineups, e.g. "
                f"0.5 for 50%%, not a 0-100 integer)."
            )
        if pid in caps:
            raise SystemExit(f"{flag_name} lists player_id {pid} more than once.")
        caps[pid] = pct
    if not caps:
        raise SystemExit(f"{flag_name} resolved to an empty list: {raw!r}")
    return caps


# ---------------------------------------------------------------------------
# Session 7.2 -- Lock / Exclude (UI-Optimizer Integration)
# ---------------------------------------------------------------------------
# Continuing the numbering from Session 3.3's stacking decisions (#14-21).
#
# 22. Two independent mechanisms, by player_id (not player_name -- names can
#     collide; player_id is this project's existing stable key throughout
#     build_projections.py/ingest_salaries.py):
#     - EXCLUDE: the player is removed from the candidate pool entirely,
#       before the solver ever sees them (same "not in the pool" pattern as
#       an exposure-locked-out player, decision #5) -- done once, by the
#       caller (build_single_lineup/build_multi_lineup), not inside
#       solve_lineup() itself, since it never needs to vary per-solve within
#       a single run.
#     - LOCK: the player is forced into every generated lineup via a hard
#       ILP constraint (x[pid] == 1), same "hard constraint, not a soft
#       nudge" pattern as every other rule in this file. Implemented inside
#       solve_lineup() itself (not pre-filtered) because it must still
#       participate in salary-cap/position-count constraints alongside every
#       other decision variable.
#
# 23. Locked players are exempt from BOTH the exposure cap's lock-out check
#     (decision #5/#6 -- a lock is an explicit, stronger override of "no
#     more than X%", not a conflicting rule to reconcile) AND from the
#     uniqueness swap count (decision #7) -- a locked player appears in
#     every lineup by definition, so counting them as an available "swap"
#     would inflate how many different players two lineups actually need,
#     making a uniqueness target infeasible for reasons unrelated to the
#     real pool being thin.
#
# 24. validate_lock_feasibility() mirrors add_stack_constraints()'s decision
#     #21 pattern: fails loudly with a specific, structural reason (too many
#     locked players at an exact-count position, locked RB/WR/TE overflowing
#     available FLEX-inclusive slots, locked salaries alone exceeding the
#     cap, or more locked players than roster slots exist at all) BEFORE the
#     solver ever runs, rather than surfacing as an opaque "did not find an
#     optimal solution." A lock that's only infeasible for subtler reasons
#     (e.g. conflicts with a simultaneous stack requirement) still falls
#     through to the solver's own infeasibility path -- both fail loudly,
#     neither silently drops the lock.
#
# 25. --lock and --exclude on the same player_id is a hard CLI error (fails
#     at argument-parsing time, not a silent "exclude wins"/"lock wins"
#     precedence rule).
#
# 26. player_id is now carried through assign_roster_slots() into the output
#     CSV (previously dropped after the solve). Needed so a UI can
#     round-trip "lock this specific player" from a rendered lineup without
#     a separate name-based lookup.
def parse_id_list(raw: str) -> set:
    return {p.strip() for p in raw.split(",") if p.strip()} if raw else set()


def validate_lock_feasibility(players: pd.DataFrame, locked_player_ids: set,
                               fixed_counts: dict, flex_count: int, salary_cap: int):
    """Decision #24 -- structural pre-check for a lock request, independent
    of which OTHER players end up selected. Does not check interaction with
    stacking or exposure -- those still fail loudly via their own existing
    paths (decision #21, solve_lineup's own RuntimeError) if a conflict
    exists there instead."""
    if not locked_player_ids:
        return
    locked = players[players["player_id"].isin(locked_player_ids)]
    unknown = locked_player_ids - set(locked["player_id"])
    if unknown:
        raise RuntimeError(
            f"Cannot lock player_id(s) {sorted(unknown)} -- not found in "
            f"the current candidate pool (already excluded, or an invalid "
            f"player_id)."
        )

    total_slots = sum(fixed_counts.values()) + flex_count
    if len(locked) > total_slots:
        raise RuntimeError(
            f"Cannot lock {len(locked)} player(s) -- only {total_slots} "
            f"roster slot(s) exist."
        )

    for pos, required in fixed_counts.items():
        if pos in FLEX_ELIGIBLE_POSITIONS:
            continue
        n_locked_here = int((locked["position"] == pos).sum())
        if n_locked_here > required:
            raise RuntimeError(
                f"Cannot lock {n_locked_here} {pos}(s) -- exactly {required} "
                f"{pos} slot(s) exist in this roster."
            )

    flex_locked = int(locked["position"].isin(FLEX_ELIGIBLE_POSITIONS).sum())
    flex_fixed_total = sum(c for pos, c in fixed_counts.items() if pos in FLEX_ELIGIBLE_POSITIONS)
    flex_capacity = flex_fixed_total + flex_count
    if flex_locked > flex_capacity:
        raise RuntimeError(
            f"Cannot lock {flex_locked} RB/WR/TE player(s) -- only "
            f"{flex_capacity} RB/WR/TE slot(s) (including FLEX) exist."
        )

    locked_salary = int(locked["salary"].sum())
    if locked_salary > salary_cap:
        raise RuntimeError(
            f"Locked players alone cost {locked_salary}, exceeding the "
            f"{salary_cap} salary cap -- cannot build a legal lineup."
        )


def validate_exposure_cap_feasibility(players: pd.DataFrame, locked_player_ids: set,
                                       max_team_players: dict = None,
                                       max_game_players: dict = None,
                                       player_exposure: dict = None):
    """Decision #36's structural pre-check, same pattern and same scope
    limitation as validate_lock_feasibility's decision #24: only checks
    whether the LOCKED players themselves already violate a cap (in which
    case no legal lineup can ever exist, regardless of what else is
    requested) -- does not check interaction with stacking minimums or
    with each other. If a locked player fills a team's cap of 1, every
    OTHER player from that team is implicitly excluded by the cap
    constraint itself once added (decision #36) -- no separate mechanism
    needed for that half of the requested behavior.

    Session 16 (decisions #54-55): --player-exposure gets its own two
    checks here, run regardless of whether any locks were requested at
    all (unlike the team/game checks below, which only matter once a lock
    exists) -- an unknown player_id is a non-fatal NOTE, and a player who
    is BOTH locked and given an explicit override is a hard error, since a
    lock already means 100% of lineups and a lower cap on the same id can
    never be satisfied."""
    if player_exposure:
        unknown = set(player_exposure) - set(players["player_id"])
        if unknown:
            print(
                f"NOTE: --player-exposure references player_id(s) not "
                f"found in this pool: {sorted(unknown)} -- ignored.",
                file=sys.stderr,
            )
        if locked_player_ids:
            conflict = locked_player_ids & set(player_exposure)
            if conflict:
                raise RuntimeError(
                    f"player_id(s) {sorted(conflict)} are both --lock'd "
                    f"and given a --player-exposure override -- a lock "
                    f"already means 100% of lineups, so a lower cap on "
                    f"the same id can never be satisfied (decision #54). "
                    f"Remove one or the other."
                )

    if not locked_player_ids:
        return
    locked = players[players["player_id"].isin(locked_player_ids)]

    if max_team_players:
        for team, cap in max_team_players.items():
            n_locked_here = int((locked["team"] == team).sum())
            if n_locked_here > cap:
                raise RuntimeError(
                    f"Cannot satisfy --max-team-players {team}:{cap} -- "
                    f"{n_locked_here} locked player(s) are already on {team}, "
                    f"exceeding that cap by itself."
                )

    if max_game_players:
        for game_key, cap in max_game_players.items():
            n_locked_here = int(locked["team"].isin(game_key).sum())
            if n_locked_here > cap:
                raise RuntimeError(
                    f"Cannot satisfy --max-game-players {'-'.join(sorted(game_key))}:"
                    f"{cap} -- {n_locked_here} locked player(s) are already in that "
                    f"game, exceeding that cap by itself."
                )


# ---------------------------------------------------------------------------
# Candidate ranking for auto-selection (decision #16)
# ---------------------------------------------------------------------------

def rank_candidate_teams(players: pd.DataFrame, partner_positions: set,
                          require_opponent_viable: bool = False) -> list:
    """Ranks teams by implied_total (desc), restricted to teams that have
    at least one viable (non-zero-projection) QB AND at least one viable
    partner at an eligible position -- a team failing either check can
    never satisfy a QB stack, so it's excluded from the candidate pool up
    front rather than only discovered after a wasted solve attempt.

    `require_opponent_viable` (added after real-data testing surfaced a
    gap -- see SESSION_LOG.md): when True (used for --bring-back), also
    requires the team's real opponent to have at least one player present
    in the CURRENT SALARY POOL. This matters for thin pools (e.g. a
    partial-slate test file) where a team's real Vegas opponent may not
    have any players in the pool at all -- auto-selecting that team would
    otherwise pick a candidate that's guaranteed to fail the bring-back
    constraint, rather than skipping it up front the same way a missing
    QB/partner already gets skipped."""
    has_qb = set(players.loc[
        (players["position"] == "QB") & (players["final_projection"] > 0), "team"
    ])
    has_partner = set(players.loc[
        players["position"].isin(partner_positions) & (players["final_projection"] > 0), "team"
    ])
    viable = has_qb & has_partner

    if require_opponent_viable:
        teams_in_pool = set(players["team"].unique())
        opponent_by_team = players.drop_duplicates("team").set_index("team")["opponent"]
        viable = {
            t for t in viable
            if opponent_by_team.get(t) not in (None, "BYE_OR_UNKNOWN")
            and opponent_by_team.get(t) in teams_in_pool
        }

    totals = (
        players[players["team"].isin(viable) & (players["implied_total"] > 0)]
        .drop_duplicates("team")
        .set_index("team")["implied_total"]
        .sort_values(ascending=False)
    )
    return totals.index.tolist()


def rank_candidate_games(players: pd.DataFrame, require_qb_viable: bool = False) -> list:
    """Ranks distinct real games (excludes bye-week/unknown rows -- see
    build_projections.py decision #6's BYE_OR_UNKNOWN sentinel) by
    over_under (desc). Returns a list of (team_a, team_b) tuples, deduped
    so each real game appears once regardless of which side's row it came
    from.

    Requires BOTH sides to actually have players present in the current
    pool -- not just that the game exists in Vegas data (a real, thin test
    pool can have a team's real Vegas opponent entirely absent from the
    salary file; found via real-data testing -- see SESSION_LOG.md).

    `require_qb_viable` (Session 7.3, decision #30 -- Game Stack now
    requires a QB from one of the two teams, see add_stack_constraints):
    when True, also requires at least one side to have a viable
    (non-zero-projection) QB, same up-front filtering rank_candidate_teams()
    already does for QB stacks -- a candidate game with no QB on either
    side can never satisfy the constraint, so it's excluded before a
    wasted solve attempt rather than only discovered after one. Defaults
    to False because this function is ALSO used for the opposing-pass-
    catchers mini-stack, which has no QB requirement at all -- filtering
    QB-less games out there would wrongly shrink a perfectly valid
    candidate pool."""
    real = players[(players["opponent"] != "BYE_OR_UNKNOWN") & (players["opponent"].notna())]
    if "over_under" not in real.columns or real.empty:
        return []
    teams_in_pool = set(players["team"].unique())
    pairs = real[["team", "opponent", "over_under"]].drop_duplicates()
    pairs = pairs[pairs["opponent"].isin(teams_in_pool)]  # both sides must have real pool players
    if require_qb_viable:
        has_qb = set(players.loc[
            (players["position"] == "QB") & (players["final_projection"] > 0), "team"
        ])
        pairs = pairs[pairs["team"].isin(has_qb) | pairs["opponent"].isin(has_qb)]
    seen = set()
    games = []
    for row in pairs.sort_values("over_under", ascending=False).itertuples():
        key = frozenset((row.team, row.opponent))
        if key in seen:
            continue
        seen.add(key)
        games.append((row.team, row.opponent))
    return games


# ---------------------------------------------------------------------------
# Constraint builder (decision #15) + post-solve validator (decision #20)
# ---------------------------------------------------------------------------

def add_stack_constraints(prob, x: dict, players: pd.DataFrame, stack_mode: str,
                           stack_size: int = DEFAULT_STACK_SIZE,
                           stack_positions: set = None, bring_back: bool = False,
                           target_team: str = None, target_game: tuple = None,
                           game_stack_min_players: int = DEFAULT_GAME_STACK_MIN_PLAYERS,
                           mini_stack_type: str = None):
    """Adds hard ILP constraints (decision #15) for the requested stack.
    Only players present in `x` are referenced -- if the caller has already
    filtered the pool (e.g. exposure lock-outs, Session 3.2), a locked-out
    player simply contributes nothing rather than raising a KeyError, same
    defensive pattern as the existing uniqueness constraints below."""
    if stack_mode == "none":
        return

    def team_pool(team, positions):
        return [
            pid for pid in players.loc[
                (players["team"] == team) & (players["position"].isin(positions)), "player_id"
            ]
            if pid in x
        ]

    if stack_mode == "qb":
        qb_pool = team_pool(target_team, {"QB"})
        partner_pool = team_pool(target_team, stack_positions)
        if not qb_pool or len(partner_pool) < stack_size:
            raise RuntimeError(
                f"Stack request impossible (decision #21): {target_team} has "
                f"{len(qb_pool)} available QB(s) and {len(partner_pool)} "
                f"available partner(s) at {sorted(stack_positions)} in the "
                f"current candidate pool, need 1 QB + {stack_size} partner(s)."
            )
        prob += pulp.lpSum(x[pid] for pid in qb_pool) == 1, f"stack_qb_{target_team}"
        prob += pulp.lpSum(x[pid] for pid in partner_pool) >= stack_size, f"stack_partners_{target_team}"

        if bring_back:
            opp_rows = players.loc[players["team"] == target_team, "opponent"]
            opp_team = opp_rows.iloc[0] if len(opp_rows) else None
            if not opp_team or opp_team == "BYE_OR_UNKNOWN":
                raise RuntimeError(
                    f"--bring-back requested but {target_team} has no real "
                    f"opponent this week (bye/unknown) -- decision #21."
                )
            bringback_pool = team_pool(opp_team, {"QB", "RB", "WR", "TE"})  # decision #19 -- no DST
            if not bringback_pool:
                raise RuntimeError(
                    f"--bring-back requested but {opp_team} has no viable "
                    f"skill-position players in the current candidate pool."
                )
            prob += pulp.lpSum(x[pid] for pid in bringback_pool) >= 1, f"bring_back_{opp_team}"

    elif stack_mode == "game":
        team_a, team_b = target_game
        skill_and_def = {"QB", "RB", "WR", "TE", *DEFENSE_POSITION_LABELS}
        pool_a = team_pool(team_a, skill_and_def)
        pool_b = team_pool(team_b, skill_and_def)
        if not pool_a or not pool_b:
            raise RuntimeError(
                f"Game stack {team_a}/{team_b} impossible (decision #21): "
                f"one side has no available players in the current "
                f"candidate pool (a={len(pool_a)}, b={len(pool_b)})."
            )
        # Session 7.3, decision #30: a game stack now requires a QB from
        # ONE of the two teams (the lineup's single QB slot must land in
        # this game) -- without this, "≥1 each side + ≥N total" could be
        # satisfied entirely by uncorrelated skill players who happen to
        # be in the same game, which doesn't capture the shootout
        # correlation the strategy is supposed to be about. Deliberately
        # doesn't pin WHICH side's QB -- that's what QB Stack (+ bring-
        # back) is for, when you have a specific team's QB in mind rather
        # than "I like this game environment, not sure which side pops."
        qb_pool = team_pool(team_a, {"QB"}) + team_pool(team_b, {"QB"})
        if not qb_pool:
            raise RuntimeError(
                f"Game stack {team_a}/{team_b} impossible (decision #30): "
                f"neither side has a viable QB in the current candidate pool."
            )
        prob += pulp.lpSum(x[pid] for pid in qb_pool) == 1, f"game_stack_{team_a}_{team_b}_qb"
        prob += pulp.lpSum(x[pid] for pid in pool_a) >= 1, f"game_stack_{team_a}_min1"
        prob += pulp.lpSum(x[pid] for pid in pool_b) >= 1, f"game_stack_{team_b}_min1"
        prob += (
            pulp.lpSum(x[pid] for pid in pool_a + pool_b) >= game_stack_min_players,
            f"game_stack_{team_a}_{team_b}_total",
        )

    elif stack_mode == "mini":
        if mini_stack_type == "rb-dst":
            rb_pool = team_pool(target_team, {"RB"})
            dst_pool = team_pool(target_team, DEFENSE_POSITION_LABELS)
            if not rb_pool or not dst_pool:
                raise RuntimeError(
                    f"Mini-stack (RB+DST) impossible (decision #21): "
                    f"{target_team} has {len(rb_pool)} RB(s) and "
                    f"{len(dst_pool)} DST/DEF in the current candidate pool."
                )
            prob += pulp.lpSum(x[pid] for pid in rb_pool) >= 1, f"mini_rb_{target_team}"
            # DST/DEF is already exactly 1 for the whole lineup (fixed_counts) --
            # pinning this team's DST pool to == 1 forces THAT specific DST,
            # same pinning technique as the QB constraint above.
            prob += pulp.lpSum(x[pid] for pid in dst_pool) == 1, f"mini_dst_{target_team}"
        elif mini_stack_type == "opposing-pass-catchers":
            team_a, team_b = target_game
            pool_a = team_pool(team_a, {"WR", "TE"})
            pool_b = team_pool(team_b, {"WR", "TE"})
            if not pool_a or not pool_b:
                raise RuntimeError(
                    f"Mini-stack (opposing pass-catchers) impossible "
                    f"(decision #21): {team_a}/{team_b} missing a viable "
                    f"WR/TE on one side in the current candidate pool."
                )
            prob += pulp.lpSum(x[pid] for pid in pool_a) >= 1, f"mini_oppcatch_{team_a}"
            prob += pulp.lpSum(x[pid] for pid in pool_b) >= 1, f"mini_oppcatch_{team_b}"
        else:
            raise ValueError(f"Unknown --mini-stack-type: {mini_stack_type}")
    else:
        raise ValueError(f"Unknown --stack-mode: {stack_mode}")


def add_exposure_cap_constraints(prob, x: dict, players: pd.DataFrame,
                                  max_team_players: dict = None,
                                  max_game_players: dict = None):
    """Decision #36 -- hard `<= cap` ILP constraints, additive alongside
    whatever add_stack_constraints() already added. No-op (returns
    immediately, identical to every prior session's behavior) unless at
    least one cap was actually requested."""
    if not max_team_players and not max_game_players:
        return

    def team_pool(team):
        return [
            pid for pid in players.loc[players["team"] == team, "player_id"]
            if pid in x
        ]

    if max_team_players:
        for team, cap in max_team_players.items():
            pool = team_pool(team)
            if pool:
                prob += pulp.lpSum(x[pid] for pid in pool) <= cap, f"max_team_{team}"

    if max_game_players:
        for game_key, cap in max_game_players.items():
            pool = [pid for team in game_key for pid in team_pool(team)]
            if pool:
                label = "_".join(sorted(game_key))
                prob += pulp.lpSum(x[pid] for pid in pool) <= cap, f"max_game_{label}"


def validate_stack(lineup: pd.DataFrame, stack_mode: str,
                    stack_size: int = DEFAULT_STACK_SIZE, stack_positions: set = None,
                    bring_back: bool = False, target_team: str = None,
                    target_game: tuple = None,
                    game_stack_min_players: int = DEFAULT_GAME_STACK_MIN_PLAYERS,
                    mini_stack_type: str = None):
    """Decision #20 -- mirrors validate_lineup()'s pattern: an automated,
    structural re-check that the requested stack actually landed in the
    final lineup. `lineup` must include the `opponent` column (assign_
    roster_slots() carries it through as of this session)."""
    if stack_mode == "none":
        return

    if stack_mode == "qb":
        qb_rows = lineup[(lineup["team"] == target_team) & (lineup["position"] == "QB")]
        assert len(qb_rows) == 1, (
            f"STACK VALIDATION FAILED: expected exactly 1 {target_team} QB, found {len(qb_rows)}"
        )
        partner_rows = lineup[(lineup["team"] == target_team) & (lineup["position"].isin(stack_positions))]
        assert len(partner_rows) >= stack_size, (
            f"STACK VALIDATION FAILED: expected >= {stack_size} {target_team} "
            f"partner(s) at {sorted(stack_positions)}, found {len(partner_rows)}"
        )
        if bring_back:
            opp_team = lineup.loc[lineup["team"] == target_team, "opponent"].iloc[0]
            bringback_rows = lineup[lineup["team"] == opp_team]
            assert len(bringback_rows) >= 1, (
                f"STACK VALIDATION FAILED: --bring-back requested but no "
                f"{opp_team} player found in lineup"
            )

    elif stack_mode == "game":
        team_a, team_b = target_game
        n_a = (lineup["team"] == team_a).sum()
        n_b = (lineup["team"] == team_b).sum()
        n_qb = ((lineup["team"].isin([team_a, team_b])) & (lineup["position"] == "QB")).sum()
        assert n_qb == 1, (
            f"STACK VALIDATION FAILED: game stack {team_a}/{team_b} -- "
            f"lineup's QB isn't from either team (decision #30)"
        )
        assert n_a >= 1 and n_b >= 1, (
            f"STACK VALIDATION FAILED: game stack {team_a}/{team_b} missing "
            f"a player from one side (a={n_a}, b={n_b})"
        )
        assert n_a + n_b >= game_stack_min_players, (
            f"STACK VALIDATION FAILED: game stack {team_a}/{team_b} has "
            f"{n_a + n_b} combined players, need >= {game_stack_min_players}"
        )

    elif stack_mode == "mini":
        if mini_stack_type == "rb-dst":
            rb_rows = lineup[(lineup["team"] == target_team) & (lineup["position"] == "RB")]
            dst_rows = lineup[(lineup["team"] == target_team) & (lineup["position"].isin(DEFENSE_POSITION_LABELS))]
            assert len(rb_rows) >= 1 and len(dst_rows) == 1, (
                f"STACK VALIDATION FAILED: mini-stack (RB+DST) for "
                f"{target_team} -- found {len(rb_rows)} RB(s), {len(dst_rows)} DST/DEF"
            )
        elif mini_stack_type == "opposing-pass-catchers":
            team_a, team_b = target_game
            a_catch = lineup[(lineup["team"] == team_a) & (lineup["position"].isin({"WR", "TE"}))]
            b_catch = lineup[(lineup["team"] == team_b) & (lineup["position"].isin({"WR", "TE"}))]
            assert len(a_catch) >= 1 and len(b_catch) >= 1, (
                f"STACK VALIDATION FAILED: mini-stack (opposing pass-catchers) "
                f"{team_a}/{team_b} missing a WR/TE on one side"
            )


# ---------------------------------------------------------------------------
# Step 0: Load projections
# ---------------------------------------------------------------------------

def load_final_projections(site: str, slate_id: str) -> pd.DataFrame:
    path = OUTPUT_DIR / f"final_projections_{site}_{slate_id}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run build_projections.py --site {site} "
            f"--slate-id {slate_id} first (Session 2.4, extended in Session 3.1 "
            f"for DST/DEF -- decision #5)."
        )
    # Session 7.3 fix -- site_player_id MUST be read as str, not left to
    # pandas' default inference. A numeric-looking column with even ONE
    # missing value anywhere gets inferred as float64, not int64 -- which
    # silently corrupts EVERY id in the column into "43636560.0" once
    # written back out (found via a real user's download: every DK ID had
    # a spurious ".0" suffix, which DraftKings' own bulk-upload rejects
    # outright, same as a missing ID).
    df = pd.read_csv(path, dtype={"player_id": str, "site_player_id": str})
    required = {
        "player_id", "player_name", "position", "team", "salary", "final_projection",
        # Session 3.3 addition (build_projections.py decision #6) -- needed
        # for stack team/game auto-selection and bring-back/game-stack
        # constraints below. A final_projections file generated before this
        # addendum won't have these -- re-run build_projections.py.
        "opponent", "implied_total",
    }
    # Session 10.5 (decision #1): `sigma` is NOT in `required`. Legacy
    # final_projections files built by build_projections.py (the live
    # production path) carry no sigma column and must still load cleanly.
    # The stat-line path (build_projections_statline.py) does emit sigma;
    # a non-zero --lambda on a sigma-less file is a hard error raised at
    # solve time, not here. sigma_source is carried through for provenance
    # only -- never used in any constraint or objective.
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(
            f"{path} is missing expected columns: {sorted(missing)}. "
            f"build_projections.py's output schema may have changed (or this "
            f"file predates Session 3.3's opponent/implied_total addition -- "
            f"re-run build_projections.py) -- update this script's "
            f"load_final_projections() to match."
        )

    # Found via a real FD roster build going fully infeasible even at
    # uniqueness=0, no stack, no salary floor, with a healthy real pool
    # (92 QB / 150 RB / 170 TE / 299 WR / 24 DST). Root cause: FD's real
    # raw export labels a defense row's position "D" (confirmed against a
    # real FD Week 1 2026 export), but SITE_CONFIGS["fd"]["roster_slots"]
    # names FD's defense slot "DEF". ingest_salaries.py already recognizes
    # "D" as a defense via defense_position_values (assigns it a DST_{team}
    # player_id), but never remaps the position LABEL itself to match the
    # roster slot name. parse_roster_requirements() builds fixed_counts
    # straight from roster_slots (so {"DEF": 1} for FD), and solve_lineup()
    # keys its player pool by the literal position string in this
    # DataFrame -- "D" != "DEF" meant the DEF slot's required player pool
    # was silently EMPTY on every FD build, an infeasible constraint (sum
    # of zero players must equal 1) with no error naming the real cause,
    # just "no legal lineup exists." DK never hit this: its roster slot
    # name ("DST") and its raw position label ("DST") already happened to
    # be the same string. Canonicalizing here, once, at load time, means
    # every downstream consumer (the ILP's by_position dict, stacking's
    # DST/mini-stack lookups, FLEX-eligibility checks) sees one consistent
    # label without needing its own fix.
    site_roster_slots = SITE_CONFIGS[site]["roster_slots"]
    canonical_def = next(
        (s for s in site_roster_slots if s in DEFENSE_POSITION_LABELS), None)
    if canonical_def:
        is_def = df["position"].astype(str).str.upper().isin(DEFENSE_POSITION_LABELS)
        df.loc[is_def, "position"] = canonical_def

    return df


# ---------------------------------------------------------------------------
# Step 1: Parse a site's roster_slots list into position requirements
# ---------------------------------------------------------------------------

def parse_roster_requirements(roster_slots: list) -> tuple:
    """Returns (fixed_counts, flex_count) where fixed_counts is
    {position: required_count} for every non-FLEX slot (e.g.
    {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "DST": 1}) and flex_count is the
    number of FLEX slots (normally 1)."""
    fixed_counts = {}
    flex_count = 0
    for slot in roster_slots:
        if slot == FLEX_SLOT_LABEL:
            flex_count += 1
        else:
            fixed_counts[slot] = fixed_counts.get(slot, 0) + 1
    return fixed_counts, flex_count


# ---------------------------------------------------------------------------
# Session 3.2 (addendum): projection randomization -- see decisions #9-13
# ---------------------------------------------------------------------------

def randomize_projections(players: pd.DataFrame, randomization_pct: float,
                           rng: np.random.Generator,
                           mode: str = "pct",
                           n_lineups: int = 1,
                           base_override: pd.Series = None) -> pd.Series:
    """Returns a pd.Series indexed by player_id for use as the ILP objective.

    Session 3.2 (decisions #9-13): `mode="pct"` (default) draws from
    N(final_projection, pct/100 * final_projection), clipped at 0. This is
    the only mode that existed before Session 10.5 and is byte-identical.

    Session 10.5 (decision #14): `mode="sigma"` scales the std_dev on the
    pool's per-player sigma instead of the projection:
        std_dev = pct/100 * sigma * entry_scale
    where entry_scale ramps linearly 0 (n_lineups=1) -> 1.0 (n_lineups >=
    DEFAULT_SIGMA_RAND_FULL_LINEUPS). FLAGGED ARBITRARY: the ramp has no
    data behind it (decision #14). Hard error if sigma is absent or all-zero.

    Session 16 addition: `base_override` (decisions #48-49), when
    supplied, replaces players['final_projection'] as the CENTER of the
    noise draw -- e.g. compute_thumbs_projection()'s output, so a
    thumbs-up player's randomized draws land around his boosted number,
    not his real one. Reindexed to `players` here (the caller may pass a
    Series computed against a larger pool, e.g. before an exposure
    lock-out filter) so it always aligns with this call's own salary/sigma
    Series below. None (default) is every prior session's behavior,
    unchanged.

    Neither mode modifies `players` itself; output always reports the real
    final_projection (decision #11).
    """
    base = (
        base_override.reindex(players["player_id"].values)
        if base_override is not None
        else players.set_index("player_id")["final_projection"]
    )
    if randomization_pct <= 0:
        return base

    if mode == "sigma":
        if "sigma" not in players.columns:
            raise RuntimeError(
                "randomization_mode='sigma' requires a 'sigma' column in the "
                "pool -- build projections with build_projections_statline.py "
                "--sigma-recalibration (Session 10.5)."
            )
        sigma_s = players.set_index("player_id")["sigma"]
        if int((sigma_s > 0).sum()) == 0:
            raise RuntimeError(
                "randomization_mode='sigma' requested but every player has "
                "sigma=0. Use build_projections_statline.py --sigma-recalibration."
            )
        # Entry-count scale: 0 at n=1, linear ramp to 1.0. FLAGGED ARBITRARY.
        entry_scale = min(1.0, max(0.0, (n_lineups - 1) /
                                   max(1, DEFAULT_SIGMA_RAND_FULL_LINEUPS - 1)))
        std_dev = sigma_s * (randomization_pct / 100.0) * entry_scale
    else:
        std_dev = base * (randomization_pct / 100.0)

    noisy = rng.normal(loc=base.to_numpy(), scale=std_dev.to_numpy())
    return pd.Series(noisy, index=base.index).clip(lower=0.0)


# ---------------------------------------------------------------------------
# Step 2: Build and solve the ILP
# ---------------------------------------------------------------------------

def solve_lineup(players: pd.DataFrame, salary_cap: int, fixed_counts: dict,
                  flex_count: int, previous_lineups: list = None,
                  uniqueness: int = 0,
                  optimization_projection: pd.Series = None,
                  stack_mode: str = DEFAULT_STACK_MODE, stack_size: int = DEFAULT_STACK_SIZE,
                  stack_positions: set = None, bring_back: bool = False,
                  target_team: str = None, target_game: tuple = None,
                  game_stack_min_players: int = DEFAULT_GAME_STACK_MIN_PLAYERS,
                  mini_stack_type: str = None,
                  locked_player_ids: set = None,
                  min_salary: int = 0,
                  min_total_ownership: float = 0.0,
                  flex_positions: set = None,
                  lam: float = 0.0,
                  max_team_players: dict = None,
                  max_game_players: dict = None) -> pd.DataFrame:
    """`lam` is a Session 10.5 addition (decision #2): the lambda
    coefficient on the variance penalty `sum(mu) - lam*sum(sigma^2)`.
    Defaults to 0.0 -- byte-identical to every prior session's behavior.
    Positive values penalize variance (floor-seeking, cash games); negative
    values reward it (upside-seeking, GPPs -- probe A3 showed the negative
    direction has little to act on: ~96% of same-position pairs are
    floor-seeking by construction). The penalty uses the REAL per-player
    sigma^2 always -- never the randomized draw -- so risk preference is
    stable across a portfolio even when projections are noisy.
    Hard error if lam != 0.0 and the pool has no sigma or all-zero sigma:
    a non-zero lambda on a sigma-less pool is silent nonsense, not a no-op.

    `min_salary` is a Session 7.3 addition (decision #28): 0 (default)
    adds no floor, identical to every prior session's behavior. A value > 0
    adds a companion `>= min_salary` constraint alongside the existing
    `<= salary_cap` one.

    `flex_positions` is a Session 7.3 addition (decision #29): defaults to
    None, meaning "every FLEX_ELIGIBLE_POSITIONS position can fill FLEX"
    (identical to every prior session's behavior). When a strict subset is
    supplied (e.g. {"RB", "WR"} to exclude TE from FLEX), positions left
    OUT of the subset get an exact `== required` constraint instead of the
    normal `>= required` one, so the solver can never place a "leftover"
    player from an excluded position into FLEX. The positions left IN the
    subset are unchanged (still `>= required`, free to absorb the FLEX
    slot) -- since the roster-size and total-flex-pool constraints below
    are unaffected, pinning the excluded positions to exact counts is
    sufficient on its own to force the extra slot into an allowed position.

    `previous_lineups`/`uniqueness` are Session 3.2 additions (see
    decision #7 above) -- default to None/0, which reproduces Session 3.1's
    exact single-lineup behavior unchanged. When provided, `previous_lineups`
    is a list of sets of player_id, and the solve adds one constraint per
    previous lineup requiring the new lineup to swap out at least
    `uniqueness` of that lineup's players.

    `optimization_projection` is a Session 3.2-addendum addition (decisions
    #9-13): an optional pd.Series indexed by player_id used AS THE ILP
    OBJECTIVE in place of `players["final_projection"]` -- e.g. a randomized
    draw from `randomize_projections()`. Defaults to None, which uses the
    real final_projection unchanged (identical to every prior session's
    behavior). Only the objective is affected -- salary/position constraints
    and the returned DataFrame's own `final_projection` column (used for
    display downstream) are untouched either way."""
    prob = pulp.LpProblem("dfs_lineup", pulp.LpMaximize)

    # One binary variable per player -- see decision #3 above.
    x = {
        pid: pulp.LpVariable(f"x_{pid}", cat="Binary")
        for pid in players["player_id"]
    }

    proj = optimization_projection if optimization_projection is not None else (
        players.set_index("player_id")["final_projection"]
    )
    salary = players.set_index("player_id")["salary"]
    position = players.set_index("player_id")["position"]

    # Session 10.5 (decision #2): mean-variance objective.
    # Precompute sigma^2 per player from the REAL sigma column (not the
    # randomized draw). getattr default 0.0 keeps this backward-compatible
    # with legacy pools that predate Session 10.3a.
    #
    # Bug fix (Session 13.4, found via Greg's real-data Showdown run and
    # backported here since classic has the IDENTICAL latent exposure):
    # build_projections.py's `sigma` column can be PRESENT but only
    # PARTIALLY populated -- Session 13.1's kicker model writes real sigma
    # for kicker rows, but skill/DST rows never get a sigma value merged
    # back in (dst_out's sigma is computed then dropped before the final
    # concat, never re-merged -- see build_projections.py's `_dst_extra`).
    # A `sigma` column that's NaN for most rows previously crashed PuLP
    # ("Cannot multiply variables with NaN/inf values") building the
    # objective below -- for ANY lam, including the default lam=0.0, since
    # 0 * NaN is NaN, not 0 (this is a real LP coefficient being built, not
    # a Python float that could short-circuit). `.fillna(0.0)` is the
    # correct fix, not a workaround -- a row with no real sigma should
    # never have contributed a variance penalty, identical to how this
    # exact fallback already behaves when the column is absent entirely.
    real_sigma = players.set_index("player_id")["sigma"].fillna(0.0) if "sigma" in players.columns else (
        players.set_index("player_id")["final_projection"] * 0.0
    )
    var = (real_sigma ** 2)

    if lam != 0.0:
        # Hard error here, not at solve time, so the message is clear and
        # not swallowed by the try/except in build_multi_lineup's candidate
        # loop (decision #35's precedent for pre-solve guards).
        n_nonzero_sigma = int((real_sigma > 0).sum())
        if n_nonzero_sigma == 0:
            raise RuntimeError(
                f"lam={lam} was requested but every player in this pool has "
                f"sigma=0. This pool was built by build_projections.py (the "
                f"legacy path, which emits no sigma) or by "
                f"build_projections_statline.py WITHOUT --sigma-recalibration. "
                f"Either use lam=0 (the default) or build projections with "
                f"build_projections_statline.py and --sigma-recalibration so "
                f"the pool carries real per-player sigma values."
            )

    prob += (
        pulp.lpSum(x[pid] * proj[pid] for pid in x)
        - lam * pulp.lpSum(x[pid] * var[pid] for pid in x)
    ), "mean_variance_objective"

    # Salary cap.
    prob += pulp.lpSum(x[pid] * salary[pid] for pid in x) <= salary_cap, "salary_cap"

    # Session 7.3 -- salary floor (decision #28). No-op unless a floor was
    # actually requested.
    if min_salary > 0:
        prob += pulp.lpSum(x[pid] * salary[pid] for pid in x) >= min_salary, "min_salary_floor"

    # Decision #35 (this session) -- minimum total lineup ownership, same
    # pattern as decision #28's salary floor: no-op unless requested, and
    # a simple ">=" companion constraint alongside the existing objective
    # rather than a second objective. Lets a normal run explore anywhere
    # from 0 (no floor, existing behavior) up to a very high floor, which
    # -- since points-maximization is still the objective -- converges
    # toward "the highest-owned lineup that's still as good as possible
    # given that floor" as the floor approaches the max achievable total,
    # letting a "super chalk" build and the true optimal be compared
    # directly on the same objective rather than needing a second, separate
    # ownership-only solve mode.
    if min_total_ownership > 0:
        if "estimated_ownership_pct" not in players.columns:
            raise RuntimeError(
                "--min-total-ownership was requested but this pool's "
                "final_projections file has no estimated_ownership_pct "
                "column -- re-run build_projections.py for this "
                "site/week first."
            )
        ownership = players.set_index("player_id")["estimated_ownership_pct"].fillna(0)
        prob += (
            pulp.lpSum(x[pid] * ownership[pid] for pid in x) >= min_total_ownership,
            "min_total_ownership_floor",
        )

    # Total roster size.
    total_slots = sum(fixed_counts.values()) + flex_count
    prob += pulp.lpSum(x[pid] for pid in x) == total_slots, "total_roster_size"

    by_position = {
        pos: players.loc[players["position"] == pos, "player_id"].tolist()
        for pos in set(position)
    }

    # Session 7.3 -- FLEX eligibility restriction (decision #29). Defaults
    # to every FLEX_ELIGIBLE_POSITIONS position, reproducing every prior
    # session's behavior unchanged.
    flex_positions = flex_positions if flex_positions is not None else set(FLEX_ELIGIBLE_POSITIONS)

    for pos, required in fixed_counts.items():
        pool = by_position.get(pos, [])
        if pos in FLEX_ELIGIBLE_POSITIONS:
            if pos in flex_positions:
                # Own minimum, can exceed via FLEX -- exact total enforced below.
                prob += pulp.lpSum(x[pid] for pid in pool) >= required, f"min_{pos}"
            else:
                # Excluded from FLEX this run -- pinned to its exact fixed
                # count, same treatment as a non-FLEX-eligible position.
                prob += pulp.lpSum(x[pid] for pid in pool) == required, f"exact_{pos}_no_flex"
        else:
            # QB / DST-DEF -- no FLEX eligibility, exact count.
            prob += pulp.lpSum(x[pid] for pid in pool) == required, f"exact_{pos}"

    flex_pool = [pid for pos in FLEX_ELIGIBLE_POSITIONS for pid in by_position.get(pos, [])]
    flex_fixed_total = sum(c for pos, c in fixed_counts.items() if pos in FLEX_ELIGIBLE_POSITIONS)
    prob += (
        pulp.lpSum(x[pid] for pid in flex_pool) == flex_fixed_total + flex_count,
        "rb_wr_te_pool_total",
    )

    # Session 7.2 -- lock constraints (decision #22). Excluded players are
    # never in `players` at all by this point (filtered by the caller), so
    # only locking needs handling here. Missing/infeasible locks are caught
    # earlier by validate_lock_feasibility(); this is a final defensive
    # check in case a locked player fell out of the pool mid-batch (e.g. a
    # caller bug), rather than a silent KeyError.
    locked_player_ids = locked_player_ids or set()
    missing_locks = locked_player_ids - set(x)
    if missing_locks:
        raise RuntimeError(
            f"Cannot lock player_id(s) {sorted(missing_locks)} -- not present "
            f"in this solve's candidate pool."
        )
    for pid in locked_player_ids:
        prob += x[pid] == 1, f"locked_{pid}"

    # Session 3.2 -- uniqueness constraints (decision #7). Only players
    # still present in this solve's pool are counted; a previously-used
    # player who has since been exposure-locked-out (decision #5, handled
    # by the caller filtering the pool before this function runs) simply
    # isn't in `x`, so referencing them here would be a KeyError -- filter
    # to the ones that are. Locked players (decision #23) are also excluded
    # from this count -- they appear in every lineup by definition, so
    # counting them as an available "swap" would inflate how many different
    # players two lineups actually need to satisfy `uniqueness`.
    if previous_lineups:
        for i, prev_ids in enumerate(previous_lineups):
            relevant = [pid for pid in prev_ids if pid in x and pid not in locked_player_ids]
            if not relevant:
                continue
            prob += (
                pulp.lpSum(x[pid] for pid in relevant) <= len(relevant) - uniqueness,
                f"uniqueness_vs_lineup_{i}",
            )

    # Session 3.3 -- stacking constraints (decision #15). Raises RuntimeError
    # up front (decision #21) if the requested stack has no viable players
    # in the current pool, before wasting a solve attempt.
    add_stack_constraints(
        prob, x, players, stack_mode, stack_size=stack_size,
        stack_positions=stack_positions, bring_back=bring_back,
        target_team=target_team, target_game=target_game,
        game_stack_min_players=game_stack_min_players,
        mini_stack_type=mini_stack_type,
    )

    # Session 12 -- team/game exposure caps (decision #36). No-op unless
    # requested, same as every other optional constraint above.
    add_exposure_cap_constraints(
        prob, x, players,
        max_team_players=max_team_players, max_game_players=max_game_players,
    )

    status = prob.solve(pulp.PULP_CBC_CMD(msg=False))
    if pulp.LpStatus[status] != "Optimal":
        raise RuntimeError(
            f"Solver did not find an optimal solution (status: "
            f"{pulp.LpStatus[status]}). Check that enough players exist "
            f"at every required position within the salary cap."
        )

    selected_ids = [pid for pid in x if x[pid].value() == 1]
    return players[players["player_id"].isin(selected_ids)].copy()


# ---------------------------------------------------------------------------
# Step 3: Assign human-readable roster_slot labels (cosmetic, post-solve)
# ---------------------------------------------------------------------------

def _clean_site_id(value):
    """Defense in depth for the .0-suffix bug fixed in load_final_projections()
    above: even with that fix, a final_projections file WRITTEN before the
    fix could already have "43636560.0" baked into it as literal text (not
    just a read-time dtype issue) -- this strips a trailing ".0" from
    anything that looks like it, so an already-corrupted file self-heals
    on the next lineup build rather than needing a full pipeline re-run."""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return None
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s


def assign_roster_slots(selected: pd.DataFrame, fixed_counts: dict) -> pd.DataFrame:
    remaining = selected.copy()
    rows = []

    # Non-flex-eligible fixed positions first (QB, DST/DEF) -- always an
    # exact match, no ambiguity possible.
    for pos, count in fixed_counts.items():
        if pos in FLEX_ELIGIBLE_POSITIONS:
            continue
        pool = remaining[remaining["position"] == pos]
        for i, row in enumerate(pool.itertuples(), start=1):
            label = pos if count == 1 else f"{pos}{i}"
            rows.append((label, row))
        remaining = remaining.drop(pool.index)

    # Flex-eligible positions -- fill each position's own fixed slots
    # first (highest projection first, arbitrary but deterministic tie-
    # break -- doesn't affect optimality, already solved), whatever's left
    # over across the whole RB/WR/TE pool becomes FLEX.
    leftover = []
    for pos in ["RB", "WR", "TE"]:
        count = fixed_counts.get(pos, 0)
        pool = remaining[remaining["position"] == pos].sort_values(
            "final_projection", ascending=False
        )
        fixed_players = pool.iloc[:count]
        leftover.append(pool.iloc[count:])
        for i, row in enumerate(fixed_players.itertuples(), start=1):
            label = pos if count == 1 else f"{pos}{i}"
            rows.append((label, row))
        remaining = remaining.drop(pool.index)

    leftover_df = pd.concat(leftover) if leftover else remaining.iloc[0:0]
    for row in leftover_df.itertuples():
        rows.append((FLEX_SLOT_LABEL, row))

    out = pd.DataFrame([
        {
            "roster_slot": label,
            # Session 7.2 addition (decision #26) -- carries the stable
            # player_id through to output so a UI can round-trip "lock this
            # exact player" without a separate name-based lookup.
            "player_id": row.player_id,
            "player_name": row.player_name,
            "position": row.position,
            "team": row.team,
            "salary": row.salary,
            "projection": row.final_projection,
            # Session 8 (this session) addition -- points per $1,000 salary,
            # the standard DFS "value" metric. Guarded against salary=0 (a
            # locked $0 player would otherwise divide by zero); rounded to
            # 2dp for readability, matching how projection/salary are
            # already displayed.
            "value": round(row.final_projection / (row.salary / 1000), 2) if row.salary else 0.0,
            # Session 3.3 addition -- needed by validate_stack() for
            # bring-back checks, and generally useful in the output CSV to
            # see who a selected player was facing.
            "opponent": row.opponent,
            # Session 7.3 addition -- the site's OWN player ID (DK's "ID",
            # FD's "Id"), needed for the "Download Lineups" DK/FD-import
            # feature -- their bulk-upload template requires this exact ID
            # (or "Name (ID)"), never just a name. getattr() default keeps
            # this backward-compatible with a final_projections file built
            # before build_projections.py carried site_player_id through.
            "site_player_id": _clean_site_id(getattr(row, "site_player_id", None)),
            # Session 10.5 (decision #1): sigma and sigma_source carried
            # through from the projection file so solve_lineup() can read
            # them from the returned DataFrame. sigma defaults to 0.0 for
            # files built before Session 10.3a (all legacy files); the
            # non-zero-lambda guard in solve_lineup() catches that case.
            # sigma_source is for provenance only -- never used in any
            # constraint or objective.
            "sigma": float(getattr(row, "sigma", 0.0) or 0.0),
            "sigma_source": getattr(row, "sigma_source", "") or "",
        }
        for label, row in rows
    ])
    return out


# ---------------------------------------------------------------------------
# Step 4: Validation assertions (roadmap's first checkbox -- automated,
# not manual eyeballing)
# ---------------------------------------------------------------------------

def validate_lineup(lineup: pd.DataFrame, salary_cap: int, roster_slots: list):
    total_salary = lineup["salary"].sum()
    assert total_salary <= salary_cap, (
        f"VALIDATION FAILED: lineup salary {total_salary} exceeds cap {salary_cap}"
    )
    assert len(lineup) == len(roster_slots), (
        f"VALIDATION FAILED: lineup has {len(lineup)} players, roster needs {len(roster_slots)}"
    )
    fixed_counts, flex_count = parse_roster_requirements(roster_slots)
    for pos, required in fixed_counts.items():
        if pos in FLEX_ELIGIBLE_POSITIONS:
            actual = (lineup["position"] == pos).sum()
            assert actual >= required, (
                f"VALIDATION FAILED: only {actual} {pos}(s) in lineup, need >= {required}"
            )
        else:
            actual = (lineup["position"] == pos).sum()
            assert actual == required, (
                f"VALIDATION FAILED: {actual} {pos}(s) in lineup, need exactly {required}"
            )
    flex_total_actual = lineup["position"].isin(FLEX_ELIGIBLE_POSITIONS).sum()
    flex_total_required = sum(c for pos, c in fixed_counts.items() if pos in FLEX_ELIGIBLE_POSITIONS) + flex_count
    assert flex_total_actual == flex_total_required, (
        f"VALIDATION FAILED: RB+WR+TE total {flex_total_actual}, need exactly {flex_total_required}"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def resolve_stack_candidates(players_all: pd.DataFrame, stack_mode: str,
                              stack_positions: set, stack_teams: list, stack_games: list,
                              mini_stack_type: str, candidate_pool_size: int,
                              diversify_requested: str, bring_back: bool = False) -> tuple:
    """Decision #16/#17, extended by decision #32. Returns (candidates,
    diversify_active, pin_note):
    - candidates: list of {"target_team":..., "target_game":...} dicts --
      one entry if a single team/game is pinned or not diversifying, one
      entry per pinned team/game if the user explicitly picked more than
      one (decision #32), or up to candidate_pool_size entries (ranked
      best-first) if auto-selecting with diversification.
    - diversify_active: whether the caller should rotate across
      `candidates` per lineup. False for a single pin (unchanged
      behavior); TRUE whenever more than one candidate is in play,
      whether that's from auto-ranking or the user explicitly picking
      multiple teams/games -- picking more than one IS the request to
      rotate across them, regardless of --stack-diversify.
    - pin_note: a string to print if --stack-diversify on was combined
      with a SINGLE explicit pin (has no effect there -- nothing to
      rotate across), else None."""
    pinned = bool(stack_teams or stack_games)
    pin_note = None

    if stack_mode == "qb" or (stack_mode == "mini" and mini_stack_type == "rb-dst"):
        partner_positions = stack_positions if stack_mode == "qb" else {"RB"}
        require_opp = bool(stack_mode == "qb" and bring_back)
        if stack_teams:
            candidates = [{"target_team": t, "target_game": None} for t in stack_teams]
        else:
            ranked = rank_candidate_teams(players_all, partner_positions,
                                           require_opponent_viable=require_opp)
            if not ranked:
                raise RuntimeError(
                    "No team has both a viable QB/RB and a viable stack "
                    "partner/DST this week" +
                    (" with a real, in-pool opponent for --bring-back" if require_opp else "") +
                    " -- cannot auto-select a stack team."
                )
            candidates = [{"target_team": t, "target_game": None} for t in ranked[:candidate_pool_size]]
    elif stack_mode == "game" or (stack_mode == "mini" and mini_stack_type == "opposing-pass-catchers"):
        if stack_games:
            candidates = [{"target_team": None, "target_game": g} for g in stack_games]
        else:
            ranked = rank_candidate_games(players_all, require_qb_viable=(stack_mode == "game"))
            if not ranked:
                raise RuntimeError("No real games found this week to auto-select a game/mini-stack from.")
            candidates = [{"target_team": None, "target_game": g} for g in ranked[:candidate_pool_size]]
    elif stack_mode == "mini":
        raise SystemExit(
            f"--stack-mode mini requires --mini-stack-type "
            f"{{rb-dst,opposing-pass-catchers}} (got: {mini_stack_type!r})."
        )
    else:
        candidates = [{"target_team": None, "target_game": None}]

    if pinned and len(candidates) == 1 and diversify_requested == "on":
        pin_note = (
            "--stack-diversify on was set together with a single explicit "
            "--stack-team/--stack-game pin -- diversify has nothing to "
            "rotate across with just one target; pass more than one "
            "(comma-separated) to actually diversify across your own picks "
            "(decision #32)."
        )
    diversify_active = ((not pinned) and (diversify_requested != "off")) or (pinned and len(candidates) > 1)
    return candidates, diversify_active, pin_note


def _stack_label(cand: dict) -> str:
    if cand.get("target_team"):
        return f"team:{cand['target_team']}"
    if cand.get("target_game"):
        return f"game:{cand['target_game'][0]}-{cand['target_game'][1]}"
    return ""


def _print_control_summary(locked_player_ids: set, excluded_player_ids: set,
                            thumbs_up_ids: set = None, thumbs_down_ids: set = None,
                            player_exposure: dict = None):
    """Session 16 -- one shared printer for main()'s per-player-control
    summary line(s), used at all four build call sites (classic/Showdown x
    single/multi) so the four don't drift out of sync with each other the
    way four hand-duplicated print statements could."""
    if locked_player_ids or excluded_player_ids:
        print(f"Locked: {sorted(locked_player_ids) or 'none'} | Excluded: {sorted(excluded_player_ids) or 'none'}")
    if thumbs_up_ids or thumbs_down_ids:
        print(f"Thumbs up: {sorted(thumbs_up_ids or []) or 'none'} | Thumbs down: {sorted(thumbs_down_ids or []) or 'none'}")
    if player_exposure:
        overrides = ", ".join(f"{pid}:{pct:.0%}" for pid, pct in sorted(player_exposure.items()))
        print(f"Player exposure overrides: {overrides}")


def build_single_lineup(site: str, slate_id: str, randomization_pct: float = DEFAULT_RANDOMIZATION_PCT,
                         rng: np.random.Generator = None,
                         randomization_mode: str = "pct",
                         stack_mode: str = DEFAULT_STACK_MODE, stack_size: int = DEFAULT_STACK_SIZE,
                         stack_positions: set = None, bring_back: bool = False,
                         lam: float = 0.0,
                         stack_teams: list = None, stack_games: list = None,
                         game_stack_min_players: int = DEFAULT_GAME_STACK_MIN_PLAYERS,
                         mini_stack_type: str = None,
                         candidate_pool_size: int = DEFAULT_STACK_CANDIDATE_POOL,
                         locked_player_ids: set = None,
                         excluded_player_ids: set = None,
                         min_salary: int = 0,
                         min_projection: float = 0.0,
                         min_total_ownership: float = 0.0,
                         flex_positions: set = None,
                         max_team_players: dict = None,
                         max_game_players: dict = None,
                         participation_floors: dict = None,
                         thumbs_up_ids: set = None,
                         thumbs_down_ids: set = None) -> pd.DataFrame:
    config = SITE_CONFIGS[site]
    players = load_final_projections(site, slate_id)
    fixed_counts, flex_count = parse_roster_requirements(config["roster_slots"])

    # Session 7.2 -- exclude (decision #22): filtered once, up front, so the
    # solver never sees these players at all.
    locked_player_ids = locked_player_ids or set()
    excluded_player_ids = excluded_player_ids or set()
    if excluded_player_ids:
        missing_excl = excluded_player_ids - set(players["player_id"])
        if missing_excl:
            print(
                f"NOTE: --exclude player_id(s) {sorted(missing_excl)} not "
                f"found in this pool -- ignored.", file=sys.stderr,
            )
        players = players[~players["player_id"].isin(excluded_player_ids)].copy()

    # Decision #34 -- see build_multi_lineup() for full rationale. Same
    # filter, same lock exemption, applied here for single-lineup mode too.
    if min_projection > 0:
        below_floor = players[
            (players["final_projection"] < min_projection)
            & (~players["player_id"].isin(locked_player_ids))
        ]
        if len(below_floor):
            print(
                f"Pool filter: excluding {len(below_floor)} player(s) below "
                f"--min-projection {min_projection} (decision #34): "
                f"{sorted(below_floor['player_name'].tolist())}",
                file=sys.stderr,
            )
        players = players[
            (players["final_projection"] >= min_projection)
            | (players["player_id"].isin(locked_player_ids))
        ].copy()

    # Session 15, decision #A2 -- see apply_participation_floor()'s own
    # docstring for the full rationale. Applied after --min-projection/
    # --exclude, same "narrow the pool down in independent passes" pattern.
    players = apply_participation_floor(players, participation_floors or {}, locked_player_ids)

    # Decision #35 -- validated once, upfront, here -- NOT left to
    # solve_lineup()'s own check. solve_lineup() is called inside a
    # try/except RuntimeError loop when stacking (see build_multi_lineup),
    # and a missing-column error raised from inside that loop would get
    # silently swallowed and misreported as "stacking infeasible" instead
    # of the actual problem. Failing loudly here, before any solving
    # starts, keeps this project's established "never silently guess or
    # misreport" convention intact.
    if min_total_ownership > 0 and "estimated_ownership_pct" not in players.columns:
        raise SystemExit(
            "--min-total-ownership was requested but this pool's "
            "final_projections file has no estimated_ownership_pct "
            "column -- re-run build_projections.py for this site/week first."
        )

    validate_lock_feasibility(players, locked_player_ids, fixed_counts, flex_count, config["salary_cap"])
    validate_exposure_cap_feasibility(
        players, locked_player_ids,
        max_team_players=max_team_players, max_game_players=max_game_players,
    )

    # Session 16 (decisions #48-49) -- computed once, used either directly
    # as the objective or as randomization's center, exactly like
    # build_multi_lineup() below.
    thumbs_projection = compute_thumbs_projection(players, thumbs_up_ids, thumbs_down_ids)

    optimization_projection = None
    if randomization_pct > 0:
        rng = rng if rng is not None else np.random.default_rng()
        # n_lineups=1: entry_scale=0 in sigma-mode (off for single-entry, decision #14).
        optimization_projection = randomize_projections(
            players, randomization_pct, rng, mode=randomization_mode, n_lineups=1,
            base_override=thumbs_projection,
        )
    elif thumbs_projection is not None:
        optimization_projection = thumbs_projection

    # Session 3.3 -- single-lineup mode always uses the single BEST
    # candidate (no diversification concept for one lineup) unless pinned.
    target_team = target_game = None
    if stack_mode != "none":
        candidates, _, pin_note = resolve_stack_candidates(
            players, stack_mode, stack_positions, stack_teams, stack_games,
            mini_stack_type, candidate_pool_size, diversify_requested="off",
            bring_back=bring_back,
        )
        if pin_note:
            print(pin_note, file=sys.stderr)
        target_team = candidates[0]["target_team"]
        target_game = candidates[0]["target_game"]

    selected = solve_lineup(
        players, config["salary_cap"], fixed_counts, flex_count,
        optimization_projection=optimization_projection,
        stack_mode=stack_mode, stack_size=stack_size, stack_positions=stack_positions,
        bring_back=bring_back, target_team=target_team, target_game=target_game,
        game_stack_min_players=game_stack_min_players, mini_stack_type=mini_stack_type,
        locked_player_ids=locked_player_ids,
        min_salary=min_salary, min_total_ownership=min_total_ownership,
        flex_positions=flex_positions, lam=lam,
        max_team_players=max_team_players, max_game_players=max_game_players,
    )
    if locked_player_ids:
        missing = locked_player_ids - set(selected["player_id"])
        assert not missing, (
            f"LOCK VALIDATION FAILED: player_id(s) {sorted(missing)} requested "
            f"locked but not present in the solved lineup"
        )
    lineup = assign_roster_slots(selected, fixed_counts)
    # Session 10.5 (decision #1): sigma_total = sum of all nine players'
    # recalibrated sigma values. Stored in attrs so it survives the
    # validate/return chain without widening the per-player DataFrame schema.
    # Zero when the projection file predates Session 10.3a (legacy path).
    lineup.attrs["sigma_total"] = round(float(lineup["sigma"].sum()), 4)
    validate_lineup(lineup, config["salary_cap"], config["roster_slots"])
    validate_stack(
        lineup, stack_mode, stack_size=stack_size, stack_positions=stack_positions,
        bring_back=bring_back, target_team=target_team, target_game=target_game,
        game_stack_min_players=game_stack_min_players, mini_stack_type=mini_stack_type,
    )

    zero_proj_selected = lineup[lineup["projection"] == 0.0]
    if len(zero_proj_selected):
        print(
            f"WARNING: {len(zero_proj_selected)} zero-projection player(s) selected "
            f"({', '.join(zero_proj_selected['player_name'])}) -- per decision #4 above "
            f"this should be mathematically impossible unless there is no legal "
            f"alternative at that slot/salary. Investigate before trusting this lineup.",
            file=sys.stderr,
        )

    return lineup


# ---------------------------------------------------------------------------
# Session 3.2 -- Multi-lineup generation with exposure caps
# ---------------------------------------------------------------------------

def build_multi_lineup(site: str, slate_id: str, n_lineups: int = DEFAULT_N_LINEUPS,
                        max_exposure_pct: float = DEFAULT_MAX_EXPOSURE_PCT,
                        lam: float = 0.0,
                        uniqueness: int = DEFAULT_UNIQUENESS,
                        randomization_pct: float = DEFAULT_RANDOMIZATION_PCT,
                        randomization_mode: str = "pct",
                        seed: int = None,
                        stack_mode: str = DEFAULT_STACK_MODE, stack_size: int = DEFAULT_STACK_SIZE,
                        stack_positions: set = None, bring_back: bool = False,
                        stack_teams: list = None, stack_games: list = None,
                        game_stack_min_players: int = DEFAULT_GAME_STACK_MIN_PLAYERS,
                        mini_stack_type: str = None,
                        candidate_pool_size: int = DEFAULT_STACK_CANDIDATE_POOL,
                        stack_diversify: str = DEFAULT_STACK_DIVERSIFY,
                        locked_player_ids: set = None,
                        excluded_player_ids: set = None,
                        min_salary: int = 0,
                        min_projection: float = 0.0,
                        min_total_ownership: float = 0.0,
                        flex_positions: set = None,
                        max_team_players: dict = None,
                        max_game_players: dict = None,
                        participation_floors: dict = None,
                        thumbs_up_ids: set = None,
                        thumbs_down_ids: set = None,
                        player_exposure: dict = None) -> tuple:
    """Generates up to `n_lineups` distinct, salary-cap-legal lineups, none
    of which use any single player in more than `max_exposure_pct` of the
    total requested lineups (decisions #5/#6 above). Returns
    (all_lineups_df, exposure_counts, n_generated) -- `n_generated` can be
    less than `n_lineups` if the pool is too thin to keep satisfying both
    the exposure caps and uniqueness requirement (decision #7); this is
    reported, never silently truncated without a printed reason.

    `randomization_pct`/`seed` are the Session 3.2-addendum projection-
    randomization params (decisions #9-13): if `randomization_pct > 0`, a
    FRESH normal draw is taken independently for EVERY lineup in the batch
    (decision #12) and used only as that lineup's ILP objective -- real
    `final_projection` values, exposure accounting, and the swap-uniqueness
    constraint (decision #7) are all unaffected and still apply.

    Session 3.3 stacking params: if `stack_mode != "none"`, every lineup in
    the batch is mandatorily stacked (decision #15). When auto-selecting
    (no `stack_teams`/`stack_games` pin) and `stack_diversify` allows it
    (decision #17), the batch ROTATES through up to `candidate_pool_size`
    candidate teams/games (best-first by implied_total/over_under) instead
    of repeating one target for all `n_lineups`. For each lineup, if the
    current rotation candidate turns out infeasible (e.g. its players got
    exposure-locked-out earlier in the batch), the remaining candidates are
    tried before falling back to uniqueness relaxation -- a stacking
    infeasibility and a diversity infeasibility are handled as separate,
    independently-retried problems rather than one giving up for the other.

    Session 7.2 params (decisions #22-25): `excluded_player_ids` are removed
    from the pool once, up front, for the whole batch. `locked_player_ids`
    are forced into EVERY lineup in the batch via a hard constraint, are
    exempt from the exposure lock-out check below (a lock is an explicit
    override, not a conflicting rule -- decision #23), and are exempt from
    the uniqueness swap count inside solve_lineup() for the same reason.

    Session 16 params: `thumbs_up_ids`/`thumbs_down_ids` (decisions #48-51)
    nudge the ILP objective only, computed once below and reused for every
    lineup in the batch -- players_all['final_projection'] itself, and
    therefore the real output, are never touched (see
    compute_thumbs_projection()). `player_exposure` (decisions #52-55)
    gives named players their own exposure cap instead of
    `max_exposure_pct`'s shared default -- everyone else is unaffected."""
    config = SITE_CONFIGS[site]
    players_all = load_final_projections(site, slate_id)
    fixed_counts, flex_count = parse_roster_requirements(config["roster_slots"])
    rng = np.random.default_rng(seed) if randomization_pct > 0 else None

    locked_player_ids = locked_player_ids or set()
    excluded_player_ids = excluded_player_ids or set()
    if excluded_player_ids:
        missing_excl = excluded_player_ids - set(players_all["player_id"])
        if missing_excl:
            print(
                f"NOTE: --exclude player_id(s) {sorted(missing_excl)} not "
                f"found in this pool -- ignored.", file=sys.stderr,
            )
        players_all = players_all[~players_all["player_id"].isin(excluded_player_ids)].copy()

    # Decision #34: pool-level minimum-projection filter. This is a
    # distinct step from optimization itself -- the same "filter pools:
    # remove injured or bad-matchup players" step every commercial DFS
    # optimizer runs before it ever solves anything. Without it, a deeply
    # constrained batch (exposure caps exhausting every viable player at a
    # position, or a stack target whose real QB happens to be a near-zero
    # player) can mathematically pull in a technically-legal but
    # practically insane player -- e.g. a $4,000 player projected at 1.44
    # points -- simply because nothing better was AVAILABLE at that point,
    # never because it was actually a good pick. This keeps such players
    # out of consideration from the start instead. Locked players
    # (decision #23) are EXEMPT -- an explicit lock is a deliberate
    # override and should never be silently dropped by a floor the user
    # didn't intend to apply to that specific pick.
    if min_projection > 0:
        below_floor = players_all[
            (players_all["final_projection"] < min_projection)
            & (~players_all["player_id"].isin(locked_player_ids))
        ]
        if len(below_floor):
            print(
                f"Pool filter: excluding {len(below_floor)} player(s) below "
                f"--min-projection {min_projection} (decision #34): "
                f"{sorted(below_floor['player_name'].tolist())}",
                file=sys.stderr,
            )
        players_all = players_all[
            (players_all["final_projection"] >= min_projection)
            | (players_all["player_id"].isin(locked_player_ids))
        ].copy()

    # Session 15, decision #A2 -- see apply_participation_floor()'s own
    # docstring. Applied after --min-projection/--exclude, before the
    # lock-feasibility check below, so a lock that only "works" because a
    # thin-participation player would otherwise have been filtered out
    # still gets validated against the REAL final pool.
    players_all = apply_participation_floor(players_all, participation_floors or {}, locked_player_ids)

    # Decision #35 -- validated once, upfront, here -- NOT left to
    # solve_lineup()'s own check, which sits inside a try/except
    # RuntimeError loop when stacking (below). A missing-column error
    # raised from inside that loop would get silently swallowed and
    # misreported as "stacking infeasible" for all N lineups instead of
    # the actual problem. Failing loudly here, before the batch starts,
    # keeps this project's established "never silently guess or
    # misreport" convention intact.
    if min_total_ownership > 0 and "estimated_ownership_pct" not in players_all.columns:
        raise SystemExit(
            "--min-total-ownership was requested but this pool's "
            "final_projections file has no estimated_ownership_pct "
            "column -- re-run build_projections.py for this site/week first."
        )

    validate_lock_feasibility(players_all, locked_player_ids, fixed_counts, flex_count, config["salary_cap"])
    validate_exposure_cap_feasibility(
        players_all, locked_player_ids,
        max_team_players=max_team_players, max_game_players=max_game_players,
        player_exposure=player_exposure,
    )

    # Session 16 (decisions #52-55): a per-player cap dict instead of one
    # shared scalar. A player_id absent from `player_exposure` falls back
    # to `max_exposure_pct`, identical to every build before this session.
    player_exposure = player_exposure or {}
    exposure_cap_by_pid = {
        pid: max(1, math.floor(player_exposure.get(pid, max_exposure_pct) * n_lineups))
        for pid in players_all["player_id"]
    }

    candidates = [{"target_team": None, "target_game": None}]
    diversify_active = False
    if stack_mode != "none":
        candidates, diversify_active, pin_note = resolve_stack_candidates(
            players_all, stack_mode, stack_positions, stack_teams, stack_games,
            mini_stack_type, candidate_pool_size, stack_diversify,
            bring_back=bring_back,
        )
        if pin_note:
            print(pin_note, file=sys.stderr)
        if diversify_active:
            print(
                f"Stacking: evaluating {len(candidates)} candidate "
                f"{'team' if stack_mode in ('qb',) or (stack_mode == 'mini' and mini_stack_type == 'rb-dst') else 'game'}(s) "
                f"for every lineup, keeping whichever scores highest each "
                f"time (decision #33): "
                f"{[_stack_label(c) for c in candidates]}",
            )
        else:
            print(f"Stacking: every lineup uses {_stack_label(candidates[0])}.")

    exposure_count = {pid: 0 for pid in players_all["player_id"]}
    previous_lineups = []
    all_lineup_frames = []
    current_uniqueness = uniqueness
    n_generated = 0

    # Session 16 (decisions #48-49) -- computed once against the full pool,
    # reused for every lineup in the batch (a thumbs vote is fixed for the
    # whole build, unlike randomization's fresh per-lineup draw below).
    thumbs_projection = compute_thumbs_projection(players_all, thumbs_up_ids, thumbs_down_ids)

    while n_generated < n_lineups:
        locked_out = {
            pid for pid, cnt in exposure_count.items()
            if cnt >= exposure_cap_by_pid[pid] and pid not in locked_player_ids
        }
        pool = players_all[~players_all["player_id"].isin(locked_out)]

        # Decision #12 -- independent draw per lineup, not one draw reused
        # for the whole batch.
        optimization_projection = None
        if randomization_pct > 0:
            optimization_projection = randomize_projections(
                pool, randomization_pct, rng, mode=randomization_mode, n_lineups=n_lineups,
                base_override=thumbs_projection,
            )
        elif thumbs_projection is not None:
            optimization_projection = thumbs_projection

        # Decision #33 (supersedes decision #17's rotation schedule) --
        # TRUE GREEDY SELECTION. A lineup optimizer's job is to return the
        # best legal lineup possible at every step, full stop -- never a
        # lineup picked because it was "this index's turn" in a rotation.
        # So: solve against EVERY currently-viable stack candidate for this
        # lineup slot, and keep whichever one actually produces the
        # highest-scoring legal lineup -- even if that means the same
        # team/game gets picked repeatedly across several lineups in a row,
        # until its players hit their exposure cap or a uniqueness
        # constraint forces a swap. Diversification across teams/games now
        # emerges naturally from exposure caps and uniqueness depleting the
        # best option over time, not from a forced schedule that could
        # (and did -- see SESSION_LOG.md) hand out a worse candidate purely
        # because of where n_generated landed in the rotation.
        selected = None
        chosen_cand = None
        stack_infeasible_reason = None
        best_score = None
        for cand in candidates:
            try:
                candidate_selected = solve_lineup(
                    pool, config["salary_cap"], fixed_counts, flex_count,
                    previous_lineups=previous_lineups,
                    uniqueness=current_uniqueness,
                    optimization_projection=optimization_projection,
                    stack_mode=stack_mode, stack_size=stack_size,
                    stack_positions=stack_positions, bring_back=bring_back,
                    target_team=cand["target_team"], target_game=cand["target_game"],
                    game_stack_min_players=game_stack_min_players,
                    mini_stack_type=mini_stack_type,
                    locked_player_ids=locked_player_ids,
                    min_salary=min_salary, min_total_ownership=min_total_ownership,
                    flex_positions=flex_positions, lam=lam,
                    max_team_players=max_team_players, max_game_players=max_game_players,
                )
            except RuntimeError as e:
                stack_infeasible_reason = e
                continue
            # Score every candidate on the SAME values solve_lineup() just
            # optimized against -- real final_projection, or this lineup's
            # own randomized draw if randomization_pct > 0 (decision #12
            # still applies: one draw per lineup, shared across every
            # candidate tried for that lineup, so this comparison stays
            # apples-to-apples rather than mixing noisy and real scores).
            if optimization_projection is not None:
                candidate_score = optimization_projection.reindex(
                    candidate_selected["player_id"]
                ).sum()
            else:
                candidate_score = candidate_selected["final_projection"].sum()
            if best_score is None or candidate_score > best_score:
                best_score = candidate_score
                selected = candidate_selected
                chosen_cand = cand

        if selected is None:
            if current_uniqueness > 0:
                print(
                    f"WARNING: lineup {n_generated + 1}/{n_lineups} infeasible with "
                    f"uniqueness={current_uniqueness} across all "
                    f"{len(candidates)} candidate(s) tried (pool too thin -- see "
                    f"decision #7; last reason: {stack_infeasible_reason}). "
                    f"Relaxing to {current_uniqueness - 1} and retrying.",
                    file=sys.stderr,
                )
                current_uniqueness -= 1
                continue
            print(
                f"WARNING: stopping early at {n_generated} of {n_lineups} requested "
                f"lineups -- no further legal lineup exists even with uniqueness "
                f"fully relaxed to 0 and every stack candidate tried (exposure caps "
                f"still enforced, decision #5). Last reason: {stack_infeasible_reason}. "
                f"See ROADMAP.md's 'Known Testing Artifact' note if this is the "
                f"small real-data test pool.",
                file=sys.stderr,
            )
            break

        if locked_player_ids:
            missing = locked_player_ids - set(selected["player_id"])
            assert not missing, (
                f"LOCK VALIDATION FAILED: player_id(s) {sorted(missing)} requested "
                f"locked but not present in lineup {n_generated + 1}"
            )
        lineup = assign_roster_slots(selected, fixed_counts)
        # Session 10.5 (decision #1): sigma_total on each lineup frame,
        # same as the single-lineup path.
        lineup.attrs["sigma_total"] = round(float(lineup["sigma"].sum()), 4)
        validate_lineup(lineup, config["salary_cap"], config["roster_slots"])
        validate_stack(
            lineup, stack_mode, stack_size=stack_size, stack_positions=stack_positions,
            bring_back=bring_back, target_team=chosen_cand["target_team"],
            target_game=chosen_cand["target_game"],
            game_stack_min_players=game_stack_min_players, mini_stack_type=mini_stack_type,
        )
        lineup.insert(0, "lineup_id", n_generated + 1)
        lineup["stack_target"] = _stack_label(chosen_cand) if stack_mode != "none" else ""
        all_lineup_frames.append(lineup)

        for pid in selected["player_id"]:
            exposure_count[pid] += 1
        previous_lineups.append(set(selected["player_id"]))
        n_generated += 1
        current_uniqueness = uniqueness  # reset relaxation for the next lineup

    if not all_lineup_frames:
        raise RuntimeError(
            "No lineups could be generated at all -- check pool size vs. roster "
            "requirements, exposure_cap (decision #6), and stack feasibility "
            "(decision #21) if stacking was requested."
        )

    all_lineups = pd.concat(all_lineup_frames, ignore_index=True)
    return all_lineups, exposure_count, n_generated


# ---------------------------------------------------------------------------
# Session 13.4 -- Optimizer ILP for Showdown Roster Construction
# ---------------------------------------------------------------------------
# Showdown/Single-Game pools (Session 13.2 ingest, Session 13.3/13.3b
# projections+ownership) have a structurally different shape than every
# classic pool this file has handled so far: each real player appears
# TWICE -- once as a FLEX-priced row, once as a CPT (DK) / MVP (FD) row at
# 1.5x salary AND 1.5x projection (`roster_role` column distinguishes the
# two, `player_id` is the SAME for both rows). The entire classic ILP above
# assumes one row == one player == one decision variable
# (`x = {pid: ... for pid in players["player_id"]}` at the top of
# solve_lineup() -- a dict comprehension, which would silently COLLAPSE a
# Showdown pool's two rows per player_id down to one, dropping half the
# pool's rows without even an error). Rather than retrofit that assumption
# out of the classic path (high risk of subtly changing classic's
# already-validated behavior for zero benefit -- classic pools will never
# have duplicate player_ids), this section adds a PARALLEL, self-contained
# solve path keyed on `_row_key` (`f"{player_id}::{roster_role}"`, unique
# per row) instead of `player_id`. Every classic function above is
# untouched.
#
# Decisions (continuing this file's numbering, #39+):
#
# 39. Decision variables are per ROW (`_row_key`), not per player. Three
#     ILP constraints replace classic's position-count machinery entirely,
#     since Showdown has no position-based roster slots at all -- any
#     position is eligible in either the 1 CPT/MVP slot or the N FLEX
#     slots (SITE_CONFIGS[site]["showdown"]["roster_slots"], Session 13.2):
#       - exactly 1 row with roster_role == captain_role_value selected
#       - exactly N rows with roster_role == "FLEX" selected
#       - total selected == roster size (6 DK / 5 FD)
#
# 40. Mutual exclusivity (NEW constraint type, doesn't exist in the classic
#     solver): for every player_id, at most 1 of their 2 rows (CPT + FLEX)
#     may be selected -- a real player can only occupy one of the six/five
#     real roster spots, priced one way or the other, never both.
#
# 41. Minimum 1 player per team (NEW constraint type): both teams in the
#     2-team pool must have >= `min_per_team` (1) selected player, reusing
#     `SITE_CONFIGS[site]["showdown"]["min_per_team"]` rather than a guess.
#     Summing selected rows by team is equivalent to summing selected
#     DISTINCT PLAYERS by team here specifically because decision #40's
#     mutual-exclusivity constraint already guarantees at most one row per
#     player is ever selected.
#
# 42. Salary: DK's captain-priced row already carries its real 1.5x salary
#     from the raw export (Session 13.2's ingest, confirmed against a real
#     08/06/2026 CAR@ARI file); FD's synthesized MVP row does the same
#     (`_prepare_fd_showdown`, same session). The existing single
#     `<= salary_cap` sum-of-selected-salaries constraint therefore needs
#     no special-casing for the captain multiplier -- it's already baked
#     into the per-row salary value, exactly as the roadmap card's Build
#     section anticipated.
#
# 43. Locking a player (`--lock`) locks them into the lineup in EITHER
#     role (`sum(both rows) == 1`), not a specific one -- the solver picks
#     whichever role (CPT or FLEX) is actually optimal given everything
#     else, same "structural guarantee, letting the solver decide what it
#     does best" philosophy as every other constraint in this file. A
#     role-specific lock (e.g. "must be captain") is not built this
#     session -- flagged as a possible follow-up if real usage wants it,
#     not guessed at without a stated need.
#
# 44. Uniqueness (multi-lineup diversity, decision #7's Showdown
#     counterpart) counts DISTINCT PLAYERS between two lineups, not rows/
#     roles -- a player who was CPT in lineup 1 and is FLEX in lineup 2 is
#     still "the same player" for diversity purposes; counting roles as
#     different would understate how repetitive two lineups actually are
#     to a real end user filling out two entries.
#
# 45. Stacking (Session 3.3's --stack-mode) is EXPLICITLY NOT SUPPORTED
#     for Showdown this session -- main() raises a clear parser.error()
#     rather than silently ignoring the flag or half-applying classic's
#     team-pool logic to a 2-team pool it was never built for. The
#     roadmap card flagged this as a real decision to make, not a given:
#     Showdown stacking (e.g. "at least N combined from this 2-team game")
#     is well-established real DFS strategy and the opponent-lookup logic
#     really would be simpler with only one possible opponent, but
#     correctly reinterpreting classic's 4 stack modes (qb/game/mini +
#     bring-back) against a positionless, CPT/FLEX-role pool is a
#     substantial, separately-testable piece of work in its own right --
#     bolting it on inside this already-highest-risk session risked
#     shipping either path half-validated. DEFERRED to a dedicated
#     follow-up (see SESSION_LOG.md/ROADMAP.md), not silently dropped.
#     `--max-game-players` is similarly rejected for Showdown (the
#     roadmap card's own note: game caps are meaningless when only one
#     game exists in the pool) -- `--max-team-players` carries over
#     unchanged and IS supported (decision below). `--flex-positions` and
#     `--min-total-ownership` are also rejected for Showdown this session
#     -- the former has no meaning (no position-restricted roster slots to
#     restrict further), the latter would need Showdown's own role-grouped
#     ownership budget threaded through a min-ownership floor, which is a
#     real feature but not built/validated this session -- same "decide,
#     don't half-work" discipline as stacking.
#
# 46. `--max-team-players` (Session 12's team exposure cap) DOES carry over
#     to Showdown unchanged -- it's a simple `<= cap` sum over a team's
#     selected rows, no reinterpretation needed, and team-level exposure
#     control is exactly as meaningful in a 2-team pool as a full slate.
DEFAULT_SHOWDOWN_N_LINEUPS = DEFAULT_N_LINEUPS
ROW_KEY_COL = "_row_key"


def is_showdown_pool(df: pd.DataFrame) -> bool:
    """Session 13.4 -- detects a Showdown/Single-Game final_projections
    file via the `slate_format` column Session 13.3 stamps on every row
    ("showdown" or "classic"). Mirrors build_projections.py's own
    is_showdown_slate() detection pattern (module docstring decision #0
    there) rather than requiring a separate always-remember-to-set CLI
    flag."""
    return (
        "slate_format" in df.columns
        and bool(len(df))
        and df["slate_format"].astype(str).eq("showdown").any()
    )


def load_showdown_pool(site: str, slate_id: str) -> pd.DataFrame:
    """Loads and validates a Showdown pool via the existing
    load_final_projections() (unchanged), then adds this section's
    `_row_key` (decision #39) and fails loudly (not silently) on any
    schema mismatch -- same "flag, don't silently assume" discipline as
    every other loader in this file."""
    df = load_final_projections(site, slate_id)
    if not is_showdown_pool(df):
        raise SystemExit(
            f"load_showdown_pool: final_projections_{site}_{slate_id}.csv "
            f"has no slate_format='showdown' rows -- this doesn't look like "
            f"a Showdown/Single-Game pool. Use the classic solve path "
            f"instead (omit --format showdown, or let --format auto detect "
            f"it), or re-run build_projections.py against a Showdown salary "
            f"file (Session 13.2/13.3) if one was expected."
        )
    cfg = SITE_CONFIGS[site]["showdown"]
    captain_role = cfg["captain_role_value"]
    flex_role = cfg["flex_role_value"]
    if "roster_role" not in df.columns:
        raise SystemExit(
            f"final_projections_{site}_{slate_id}.csv has slate_format="
            f"'showdown' but no roster_role column -- re-run "
            f"build_projections.py (Session 13.3)."
        )
    known_roles = {captain_role, flex_role}
    unknown = set(df["roster_role"].dropna().unique()) - known_roles
    if unknown:
        raise SystemExit(
            f"final_projections_{site}_{slate_id}.csv has unexpected "
            f"roster_role value(s) {sorted(unknown)} -- expected only "
            f"{sorted(known_roles)}."
        )
    role_counts = df["roster_role"].value_counts()
    n_cpt, n_flex = role_counts.get(captain_role, 0), role_counts.get(flex_role, 0)
    if n_cpt != n_flex:
        raise SystemExit(
            f"final_projections_{site}_{slate_id}.csv has an unbalanced "
            f"Showdown pool: {n_cpt} {captain_role} row(s) vs {n_flex} "
            f"{flex_role} row(s) -- every player should have exactly one "
            f"of each (Session 13.2/13.3 ingest contract)."
        )
    df = df.copy()
    df[ROW_KEY_COL] = df["player_id"].astype(str) + "::" + df["roster_role"].astype(str)
    return df


def compute_thumbs_projection_showdown(players: pd.DataFrame, thumbs_up_ids: set,
                                        thumbs_down_ids: set):
    """Row-keyed counterpart to compute_thumbs_projection() (decisions
    #48-51) -- player_id collides across a Showdown pool's CPT/FLEX rows,
    so this indexes by ROW_KEY_COL instead. thumbs_up_ids/thumbs_down_ids
    are still real player_id values (decision #53): a flagged player's
    multiplier applies to BOTH his CPT and FLEX row -- same existing
    convention the per-player exposure cap already follows. Returns None
    if no player is flagged, same convention as the classic version."""
    thumbs_up_ids = thumbs_up_ids or set()
    thumbs_down_ids = thumbs_down_ids or set()
    if not thumbs_up_ids and not thumbs_down_ids:
        return None

    missing = (thumbs_up_ids | thumbs_down_ids) - set(players["player_id"])
    if missing:
        print(
            f"NOTE: --thumbs-up/--thumbs-down player_id(s) {sorted(missing)} "
            f"not found in this pool -- ignored.", file=sys.stderr,
        )

    indexed = players.set_index(ROW_KEY_COL)
    adjusted = indexed["final_projection"].copy()
    up_rks = indexed.index[indexed["player_id"].isin(thumbs_up_ids)]
    down_rks = indexed.index[indexed["player_id"].isin(thumbs_down_ids)]
    if len(up_rks):
        adjusted.loc[up_rks] = adjusted.loc[up_rks] * THUMBS_UP_MULTIPLIER
    if len(down_rks):
        adjusted.loc[down_rks] = adjusted.loc[down_rks] * THUMBS_DOWN_MULTIPLIER
    print(
        f"Projection adjustment for THIS SOLVE only (decisions #48-49, "
        f"#53) -- the output still reports each player's real projection: "
        f"{len(up_rks)} row(s) (CPT+FLEX combined) boosted "
        f"{THUMBS_UP_MULTIPLIER:.0%}, {len(down_rks)} row(s) reduced to "
        f"{THUMBS_DOWN_MULTIPLIER:.0%} of real projection for solving "
        f"purposes."
    )
    return adjusted


def randomize_showdown_projections(players: pd.DataFrame, randomization_pct: float,
                                    rng: np.random.Generator, mode: str = "pct",
                                    n_lineups: int = 1,
                                    base_override: pd.Series = None) -> pd.Series:
    """Row-keyed counterpart to randomize_projections() (decisions #9-14) --
    that function indexes by player_id, which collides for a Showdown pool
    (2 rows share the same player_id). Identical distribution/clipping/
    sigma-mode logic, indexed by `_row_key` instead. `base_override`
    (Session 16, decisions #48-49) works the same way as the classic
    version -- see that function's docstring."""
    base = (
        base_override.reindex(players[ROW_KEY_COL].values)
        if base_override is not None
        else players.set_index(ROW_KEY_COL)["final_projection"]
    )
    if randomization_pct <= 0:
        return base

    if mode == "sigma":
        if "sigma" not in players.columns:
            raise RuntimeError(
                "randomization_mode='sigma' requires a 'sigma' column in "
                "the pool -- build projections with "
                "build_projections_statline.py --sigma-recalibration "
                "(Session 10.5)."
            )
        sigma_s = players.set_index(ROW_KEY_COL)["sigma"]
        if int((sigma_s > 0).sum()) == 0:
            raise RuntimeError(
                "randomization_mode='sigma' requested but every row has "
                "sigma=0. Use build_projections_statline.py "
                "--sigma-recalibration."
            )
        entry_scale = min(1.0, max(0.0, (n_lineups - 1) /
                                   max(1, DEFAULT_SIGMA_RAND_FULL_LINEUPS - 1)))
        std_dev = sigma_s * (randomization_pct / 100.0) * entry_scale
    else:
        std_dev = base * (randomization_pct / 100.0)

    noisy = rng.normal(loc=base.to_numpy(), scale=std_dev.to_numpy())
    return pd.Series(noisy, index=base.index).clip(lower=0.0)


def solve_showdown_lineup(players: pd.DataFrame, site: str,
                           previous_player_sets: list = None,
                           uniqueness: int = 0,
                           optimization_projection: pd.Series = None,
                           locked_player_ids: set = None,
                           min_salary: int = 0,
                           lam: float = 0.0,
                           max_team_players: dict = None,
                           min_team_players: dict = None) -> pd.DataFrame:
    """Session 13.4 core ILP -- see decisions #39-46 above. `players` must
    already carry `_row_key` (load_showdown_pool()). Returns the selected
    rows (one per filled roster spot -- exactly 1 captain-role row + N
    flex-role rows)."""
    cfg = SITE_CONFIGS[site]["showdown"]
    salary_cap = cfg["salary_cap"]
    captain_role = cfg["captain_role_value"]
    flex_role = cfg["flex_role_value"]
    roster_slots = cfg["roster_slots"]
    captain_count = sum(1 for s in roster_slots if s == captain_role)
    flex_count = sum(1 for s in roster_slots if s == flex_role)
    total_slots = len(roster_slots)
    min_per_team = cfg["min_per_team"]

    prob = pulp.LpProblem("dfs_showdown_lineup", pulp.LpMaximize)

    row_keys = players[ROW_KEY_COL].tolist()
    x = {rk: pulp.LpVariable(f"x_{rk}", cat="Binary") for rk in row_keys}

    indexed = players.set_index(ROW_KEY_COL)
    proj = optimization_projection if optimization_projection is not None else indexed["final_projection"]
    salary = indexed["salary"]
    team = indexed["team"]
    role = indexed["roster_role"]

    # Bug fix (found via Greg's real-data run, Session 13.4): build_projections.py
    # (the legacy path) leaves a `sigma` column PRESENT but only PARTIALLY
    # populated -- Session 13.1's kicker model writes real sigma values for
    # kicker rows, but skill/DST rows never get a sigma column merged back in
    # (dst_out's sigma is computed then dropped before the final concat --
    # see build_projections.py's `_dst_extra`, never re-merged). The result is
    # a `sigma` column that EXISTS but is NaN for most rows, not absent. PuLP
    # raises "Cannot multiply variables with NaN/inf values" building the
    # objective the moment ANY coefficient is NaN -- this happens regardless
    # of lam's value (0 * NaN is NaN, not 0; there's no short-circuit,
    # this is building a real LP coefficient, not evaluating a Python float).
    # `.fillna(0.0)` is the correct fix, not a workaround: it's the exact
    # same "missing sigma = 0.0" fallback this file already uses when the
    # column is absent entirely (getattr(row, "sigma", 0.0) in
    # assign_showdown_roster_slots) -- a row with no real sigma should
    # never have contributed a variance penalty, present-but-NaN or
    # absent-column should behave identically.
    real_sigma = indexed["sigma"].fillna(0.0) if "sigma" in players.columns else pd.Series(0.0, index=indexed.index)
    var = real_sigma ** 2

    if lam != 0.0:
        if int((real_sigma > 0).sum()) == 0:
            raise RuntimeError(
                f"lam={lam} was requested but every row in this Showdown "
                f"pool has sigma=0. Either use lam=0 (the default) or build "
                f"projections with build_projections_statline.py "
                f"--sigma-recalibration so the pool carries real per-row "
                f"sigma values."
            )

    prob += (
        pulp.lpSum(x[rk] * proj[rk] for rk in x)
        - lam * pulp.lpSum(x[rk] * var[rk] for rk in x)
    ), "mean_variance_objective"

    prob += pulp.lpSum(x[rk] * salary[rk] for rk in x) <= salary_cap, "salary_cap"
    if min_salary > 0:
        prob += pulp.lpSum(x[rk] * salary[rk] for rk in x) >= min_salary, "min_salary_floor"

    # Decision #39 -- role slot counts + total roster size.
    captain_rows = [rk for rk in row_keys if role[rk] == captain_role]
    flex_rows = [rk for rk in row_keys if role[rk] == flex_role]
    prob += pulp.lpSum(x[rk] for rk in captain_rows) == captain_count, "captain_slot_count"
    prob += pulp.lpSum(x[rk] for rk in flex_rows) == flex_count, "flex_slot_count"
    prob += pulp.lpSum(x[rk] for rk in x) == total_slots, "total_roster_size"

    # Decision #40 -- CPT/FLEX mutual exclusivity per underlying player.
    for player_id, group in players.groupby("player_id"):
        rks = [rk for rk in group[ROW_KEY_COL] if rk in x]
        if len(rks) > 1:
            prob += pulp.lpSum(x[rk] for rk in rks) <= 1, f"mutex_{player_id}"

    # Decision #41 -- minimum 1 player per team.
    for t in players["team"].dropna().unique():
        rks = [rk for rk in row_keys if team[rk] == t]
        if rks:
            prob += pulp.lpSum(x[rk] for rk in rks) >= min_per_team, f"min_per_team_{t}"

    # Decision #43 -- locks (either role).
    locked_player_ids = locked_player_ids or set()
    known_pids = set(players["player_id"])
    missing_locks = locked_player_ids - known_pids
    if missing_locks:
        raise RuntimeError(
            f"Cannot lock player_id(s) {sorted(missing_locks)} -- not "
            f"present in this solve's candidate pool."
        )
    for locked_pid in locked_player_ids:
        rks = [rk for rk in players.loc[players["player_id"] == locked_pid, ROW_KEY_COL] if rk in x]
        prob += pulp.lpSum(x[rk] for rk in rks) == 1, f"locked_{locked_pid}"

    # Decision #44 -- uniqueness vs. previous lineups, counted by player,
    # not row/role. `previous_player_sets` is a list of sets of player_id
    # (NOT row_key) -- see build_multi_showdown_lineup().
    if previous_player_sets:
        for i, prev_pids in enumerate(previous_player_sets):
            relevant_pids = [p for p in prev_pids if p in known_pids and p not in locked_player_ids]
            if not relevant_pids:
                continue
            relevant_rks = [
                rk for p in relevant_pids
                for rk in players.loc[players["player_id"] == p, ROW_KEY_COL]
                if rk in x
            ]
            prob += (
                pulp.lpSum(x[rk] for rk in relevant_rks) <= len(relevant_pids) - uniqueness,
                f"uniqueness_vs_lineup_{i}",
            )

    # Decision #46 -- team exposure caps (max_game_players is rejected for
    # Showdown up front in main(), decision #45 -- never reaches here).
    if max_team_players:
        for t, cap in max_team_players.items():
            rks = [rk for rk in row_keys if team[rk] == t]
            if rks:
                prob += pulp.lpSum(x[rk] for rk in rks) <= cap, f"max_team_{t}"

    # Decision #47 (this session's addendum, user-requested) -- MINIMUM
    # team count, the mirror of decision #46's maximum. This is the
    # "one-sided lineup" lever the user actually wanted in place of full
    # stacking (decision #45): "force 4/5/6 players from the same team"
    # is exactly `--min-team-players TEAM:N`. Reuses decision #41's
    # min-1-per-team mechanism (a plain `>= N` sum constraint) rather than
    # introducing a new constraint type -- min_per_team=1 is just this
    # same mechanism's default floor for every team; a user-supplied
    # min_team_players entry overrides that floor to something higher for
    # the specific team(s) named. Structural feasibility (can this team's
    # floor and the other team's own min_per_team floor both fit in
    # total_slots?) is pre-checked in main() before the solver ever runs
    # (same "fail loud, with a specific reason, before wasting a solve"
    # discipline as decision #21/#24 in the classic path), so an
    # impossible combination surfaces clearly rather than as an opaque
    # solver infeasibility.
    if min_team_players:
        for t, floor in min_team_players.items():
            rks = [rk for rk in row_keys if team[rk] == t]
            if rks:
                prob += pulp.lpSum(x[rk] for rk in rks) >= floor, f"min_team_{t}"

    status = prob.solve(pulp.PULP_CBC_CMD(msg=False))
    if pulp.LpStatus[status] != "Optimal":
        raise RuntimeError(
            f"Solver did not find an optimal solution for this Showdown "
            f"lineup (status: {pulp.LpStatus[status]}). Check salary cap, "
            f"the min-1-per-team requirement, and lock/exposure settings."
        )

    selected_keys = [rk for rk in x if x[rk].value() == 1]
    return players[players[ROW_KEY_COL].isin(selected_keys)].copy()


def assign_showdown_roster_slots(selected: pd.DataFrame, site: str) -> pd.DataFrame:
    """Cosmetic post-solve labeling, mirroring assign_roster_slots()'s
    pattern: the captain-role row gets its site's own label (CPT/MVP), and
    FLEX rows are numbered FLEX1..FLEXN by descending projection (arbitrary
    deterministic tie-break, same as classic -- doesn't affect optimality,
    already solved). `roster_role` is carried through into the output
    (unlike classic's `assign_roster_slots()`, which has no equivalent
    column to carry) -- pivot_finder.py's Session 13.4 fix needs it to
    join a Showdown cash lineup back to its pool row unambiguously (a
    player has 2 pool rows in Showdown; player_name/position/team alone no
    longer uniquely identifies one)."""
    cfg = SITE_CONFIGS[site]["showdown"]
    captain_role = cfg["captain_role_value"]
    flex_role = cfg["flex_role_value"]

    captain_rows = selected[selected["roster_role"] == captain_role]
    flex_rows = selected[selected["roster_role"] == flex_role].sort_values(
        "final_projection", ascending=False
    )

    rows = [(captain_role, row) for row in captain_rows.itertuples()]
    rows += [
        (f"{flex_role}{i}", row)
        for i, row in enumerate(flex_rows.itertuples(), start=1)
    ]

    out = pd.DataFrame([
        {
            "roster_slot": label,
            "player_id": row.player_id,
            "player_name": row.player_name,
            "position": row.position,
            "team": row.team,
            "roster_role": row.roster_role,
            "salary": row.salary,
            "projection": row.final_projection,
            "value": round(row.final_projection / (row.salary / 1000), 2) if row.salary else 0.0,
            "opponent": row.opponent,
            "site_player_id": _clean_site_id(getattr(row, "site_player_id", None)),
            "sigma": float(getattr(row, "sigma", 0.0) or 0.0),
            "sigma_source": getattr(row, "sigma_source", "") or "",
        }
        for label, row in rows
    ])
    return out


def validate_showdown_lineup(lineup: pd.DataFrame, site: str):
    """Session 13.4's counterpart to validate_lineup() -- an automated
    structural assertion, not eyeballing, matching this file's standing
    "guarantee, not eyeballing" discipline. Directly answers the roadmap
    card's first Showdown validation checkbox."""
    cfg = SITE_CONFIGS[site]["showdown"]
    salary_cap = cfg["salary_cap"]
    roster_slots = cfg["roster_slots"]
    captain_role = cfg["captain_role_value"]
    flex_role = cfg["flex_role_value"]
    min_per_team = cfg["min_per_team"]

    total_salary = lineup["salary"].sum()
    assert total_salary <= salary_cap, (
        f"VALIDATION FAILED: Showdown lineup salary {total_salary} exceeds cap {salary_cap}"
    )
    assert len(lineup) == len(roster_slots), (
        f"VALIDATION FAILED: Showdown lineup has {len(lineup)} players, roster needs {len(roster_slots)}"
    )
    n_captain = int((lineup["roster_role"] == captain_role).sum())
    n_flex = int((lineup["roster_role"] == flex_role).sum())
    expected_captain = sum(1 for s in roster_slots if s == captain_role)
    expected_flex = sum(1 for s in roster_slots if s == flex_role)
    assert n_captain == expected_captain, (
        f"VALIDATION FAILED: {n_captain} {captain_role} slot(s) filled, need exactly {expected_captain}"
    )
    assert n_flex == expected_flex, (
        f"VALIDATION FAILED: {n_flex} {flex_role} slot(s) filled, need exactly {expected_flex}"
    )
    assert lineup["player_id"].is_unique, (
        "VALIDATION FAILED: the same underlying player was selected in more "
        "than one roster slot (decision #40's CPT/FLEX mutual exclusivity "
        "was violated)"
    )
    n_teams_in_lineup = lineup["team"].nunique()
    assert n_teams_in_lineup == cfg["n_teams"], (
        f"VALIDATION FAILED: lineup has players from {n_teams_in_lineup} "
        f"team(s), need exactly {cfg['n_teams']}"
    )
    team_counts = lineup["team"].value_counts()
    assert (team_counts >= min_per_team).all(), (
        f"VALIDATION FAILED: a team has fewer than {min_per_team} player(s) "
        f"in lineup (decision #41): {team_counts.to_dict()}"
    )


def validate_min_team_players_feasibility(site: str, min_team_players: dict):
    """Decision #47's structural pre-check -- same "fail loud, before
    wasting a solve" discipline as classic's validate_lock_feasibility()/
    validate_exposure_cap_feasibility(). Two failure modes:
    1. A single team's floor exceeds what's structurally possible (total
       slots minus the OTHER team's own required min_per_team floor).
    2. Floors for both teams in a 2-team pool sum to more than total_slots
       (can't have >= 4 from team A AND >= 4 from team B in a 6-slot
       lineup)."""
    if not min_team_players:
        return
    cfg = SITE_CONFIGS[site]["showdown"]
    total_slots = len(cfg["roster_slots"])
    min_per_team = cfg["min_per_team"]

    for t, floor in min_team_players.items():
        max_possible_one_sided = total_slots - min_per_team
        if floor > max_possible_one_sided:
            raise SystemExit(
                f"--min-team-players {t}:{floor} is impossible -- a "
                f"{total_slots}-slot Showdown lineup must leave at least "
                f"{min_per_team} slot(s) for the other team (decision #41), "
                f"so {t} can have at most {max_possible_one_sided}."
            )

    if len(min_team_players) > 1 and sum(min_team_players.values()) > total_slots:
        raise SystemExit(
            f"--min-team-players floors {min_team_players} sum to more than "
            f"the {total_slots} total roster slots -- cannot satisfy both "
            f"at once."
        )


def build_single_showdown_lineup(site: str, slate_id: str,
                                  randomization_pct: float = DEFAULT_RANDOMIZATION_PCT,
                                  rng: np.random.Generator = None,
                                  randomization_mode: str = "pct",
                                  lam: float = 0.0,
                                  locked_player_ids: set = None,
                                  excluded_player_ids: set = None,
                                  min_salary: int = 0,
                                  max_team_players: dict = None,
                                  min_team_players: dict = None,
                                  thumbs_up_ids: set = None,
                                  thumbs_down_ids: set = None) -> pd.DataFrame:
    players = load_showdown_pool(site, slate_id)
    validate_min_team_players_feasibility(site, min_team_players)
    locked_player_ids = locked_player_ids or set()
    excluded_player_ids = excluded_player_ids or set()

    if excluded_player_ids:
        missing_excl = excluded_player_ids - set(players["player_id"])
        if missing_excl:
            print(
                f"NOTE: --exclude player_id(s) {sorted(missing_excl)} not "
                f"found in this pool -- ignored.", file=sys.stderr,
            )
        players = players[~players["player_id"].isin(excluded_player_ids)].copy()

    # Session 16 (decisions #48-49, #53).
    thumbs_projection = compute_thumbs_projection_showdown(players, thumbs_up_ids, thumbs_down_ids)

    optimization_projection = None
    if randomization_pct > 0:
        rng = rng if rng is not None else np.random.default_rng()
        optimization_projection = randomize_showdown_projections(
            players, randomization_pct, rng, mode=randomization_mode, n_lineups=1,
            base_override=thumbs_projection,
        )
    elif thumbs_projection is not None:
        optimization_projection = thumbs_projection

    selected = solve_showdown_lineup(
        players, site,
        optimization_projection=optimization_projection,
        locked_player_ids=locked_player_ids,
        min_salary=min_salary, lam=lam,
        max_team_players=max_team_players,
        min_team_players=min_team_players,
    )
    if locked_player_ids:
        missing = locked_player_ids - set(selected["player_id"])
        assert not missing, (
            f"LOCK VALIDATION FAILED: player_id(s) {sorted(missing)} "
            f"requested locked but not present in the solved lineup"
        )

    lineup = assign_showdown_roster_slots(selected, site)
    lineup.attrs["sigma_total"] = round(float(lineup["sigma"].sum()), 4)
    validate_showdown_lineup(lineup, site)

    zero_proj_selected = lineup[lineup["projection"] == 0.0]
    if len(zero_proj_selected):
        print(
            f"WARNING: {len(zero_proj_selected)} zero-projection player(s) "
            f"selected ({', '.join(zero_proj_selected['player_name'])}) -- "
            f"same decision #4 concern as classic: investigate before "
            f"trusting this lineup.", file=sys.stderr,
        )

    return lineup


def build_multi_showdown_lineup(site: str, slate_id: str,
                                 n_lineups: int = DEFAULT_SHOWDOWN_N_LINEUPS,
                                 max_exposure_pct: float = DEFAULT_MAX_EXPOSURE_PCT,
                                 uniqueness: int = DEFAULT_UNIQUENESS,
                                 randomization_pct: float = DEFAULT_RANDOMIZATION_PCT,
                                 randomization_mode: str = "pct",
                                 seed: int = None,
                                 lam: float = 0.0,
                                 locked_player_ids: set = None,
                                 excluded_player_ids: set = None,
                                 min_salary: int = 0,
                                 max_team_players: dict = None,
                                 min_team_players: dict = None,
                                 thumbs_up_ids: set = None,
                                 thumbs_down_ids: set = None,
                                 player_exposure: dict = None) -> tuple:
    """Showdown counterpart to build_multi_lineup() -- same exposure-cap /
    uniqueness-relaxation loop (decisions #5-7), no stacking rotation
    (decision #45 -- not supported for Showdown this session). Session 16
    params (thumbs_up_ids/thumbs_down_ids/player_exposure) mirror
    build_multi_lineup()'s own -- see that function's docstring and
    decisions #48-55 above."""
    players_all = load_showdown_pool(site, slate_id)
    validate_min_team_players_feasibility(site, min_team_players)

    rng = np.random.default_rng(seed) if randomization_pct > 0 else None
    locked_player_ids = locked_player_ids or set()
    excluded_player_ids = excluded_player_ids or set()
    if excluded_player_ids:
        missing_excl = excluded_player_ids - set(players_all["player_id"])
        if missing_excl:
            print(
                f"NOTE: --exclude player_id(s) {sorted(missing_excl)} not "
                f"found in this pool -- ignored.", file=sys.stderr,
            )
        players_all = players_all[~players_all["player_id"].isin(excluded_player_ids)].copy()

    # Session 16 side-effect, worth flagging explicitly: build_multi_
    # showdown_lineup() never called validate_exposure_cap_feasibility()
    # before this session -- a locked player who already busts
    # --max-team-players on a Showdown slate previously only surfaced as
    # an opaque solver infeasibility. Needed here regardless for the new
    # --player-exposure checks (decisions #54-55), and extending it to the
    # pre-existing --max-team-players/lock conflict too is a pure
    # improvement (same upfront, specific error classic already had) --
    # not a behavior change for any build that doesn't hit that conflict.
    validate_exposure_cap_feasibility(
        players_all, locked_player_ids,
        max_team_players=max_team_players, player_exposure=player_exposure,
    )

    # Session 16 (decisions #52-55) -- per-player cap dict, same shape and
    # same fallback-to-shared-default as build_multi_lineup() above. A
    # showdown player_id is shared by his CPT and FLEX rows (decision #53)
    # so one cap here already covers both roles, unchanged pre-existing
    # behavior.
    player_exposure = player_exposure or {}
    exposure_cap_by_pid = {
        pid: max(1, math.floor(player_exposure.get(pid, max_exposure_pct) * n_lineups))
        for pid in players_all["player_id"].unique()
    }
    exposure_count = {pid: 0 for pid in players_all["player_id"].unique()}
    previous_player_sets = []
    all_lineup_frames = []
    current_uniqueness = uniqueness
    n_generated = 0

    # Session 16 (decisions #48-49, #53).
    thumbs_projection = compute_thumbs_projection_showdown(players_all, thumbs_up_ids, thumbs_down_ids)

    while n_generated < n_lineups:
        locked_out = {
            pid for pid, cnt in exposure_count.items()
            if cnt >= exposure_cap_by_pid[pid] and pid not in locked_player_ids
        }
        pool = players_all[~players_all["player_id"].isin(locked_out)]

        optimization_projection = None
        if randomization_pct > 0:
            optimization_projection = randomize_showdown_projections(
                pool, randomization_pct, rng, mode=randomization_mode, n_lineups=n_lineups,
                base_override=thumbs_projection,
            )
        elif thumbs_projection is not None:
            optimization_projection = thumbs_projection

        try:
            selected = solve_showdown_lineup(
                pool, site,
                previous_player_sets=previous_player_sets,
                uniqueness=current_uniqueness,
                optimization_projection=optimization_projection,
                locked_player_ids=locked_player_ids,
                min_salary=min_salary, lam=lam,
                max_team_players=max_team_players,
                min_team_players=min_team_players,
            )
        except RuntimeError as e:
            if current_uniqueness > 0:
                print(
                    f"WARNING: Showdown lineup {n_generated + 1}/{n_lineups} "
                    f"infeasible with uniqueness={current_uniqueness} (pool "
                    f"too thin -- last reason: {e}). Relaxing to "
                    f"{current_uniqueness - 1} and retrying.", file=sys.stderr,
                )
                current_uniqueness -= 1
                continue
            print(
                f"WARNING: stopping early at {n_generated} of {n_lineups} "
                f"requested Showdown lineups -- no further legal lineup "
                f"exists even with uniqueness fully relaxed to 0. Last "
                f"reason: {e}", file=sys.stderr,
            )
            break

        if locked_player_ids:
            missing = locked_player_ids - set(selected["player_id"])
            assert not missing, (
                f"LOCK VALIDATION FAILED: player_id(s) {sorted(missing)} "
                f"requested locked but not present in lineup {n_generated + 1}"
            )
        lineup = assign_showdown_roster_slots(selected, site)
        lineup.attrs["sigma_total"] = round(float(lineup["sigma"].sum()), 4)
        validate_showdown_lineup(lineup, site)
        lineup.insert(0, "lineup_id", n_generated + 1)
        all_lineup_frames.append(lineup)

        for pid in selected["player_id"]:
            exposure_count[pid] += 1
        previous_player_sets.append(set(selected["player_id"]))
        n_generated += 1
        current_uniqueness = uniqueness

    if not all_lineup_frames:
        raise RuntimeError(
            "No Showdown lineups could be generated at all -- check pool "
            "size vs. the 6/5-slot roster + min-1-per-team requirement, "
            "exposure_cap, and lock settings."
        )

    all_lineups = pd.concat(all_lineup_frames, ignore_index=True)
    return all_lineups, exposure_count, n_generated


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("--site", choices=["dk", "fd"], required=True)
    parser.add_argument("--slate-id", required=True,
        help="e.g. classic_wk10 or madden_07312026 -- matches build_projections.py's "
             "--slate-id and names the input/output files.")
    # Session 13.4 -- Showdown/Single-Game support.
    parser.add_argument(
        "--format", choices=["auto", "classic", "showdown"], default="auto",
        help="'auto' (default) detects Showdown vs. classic from the "
             "loaded final_projections file's slate_format column (Session "
             "13.2/13.3) -- normal runs never need to set this. 'classic'/"
             "'showdown' force that solve path and fail loudly up front if "
             "the file doesn't actually match (catches an accidental "
             "wrong-file run before wasting a solve attempt).",
    )
    parser.add_argument(
        "--n-lineups", type=int, default=None,
        help="If set, generate this many lineups with exposure caps (Session "
             "3.2) instead of a single optimal lineup (Session 3.1).",
    )
    parser.add_argument(
        "--max-exposure", type=float, default=DEFAULT_MAX_EXPOSURE_PCT,
        help=f"Max fraction of lineups any one player may appear in "
             f"(default {DEFAULT_MAX_EXPOSURE_PCT:.0%}%). Only used with --n-lineups.",
    )
    parser.add_argument(
        "--uniqueness", type=int, default=DEFAULT_UNIQUENESS,
        help=f"Minimum number of different players required between any two "
             f"generated lineups (default {DEFAULT_UNIQUENESS}). Only used "
             f"with --n-lineups.",
    )
    parser.add_argument(
        "--randomization-pct", type=float, default=DEFAULT_RANDOMIZATION_PCT,
        help="Optional projection randomization (Session 3.2 addendum, decisions "
             "#9-13): 0 (default) uses each player's real final_projection "
             "unchanged. A value > 0 (typically 1-40) draws each player's "
             "projection from a normal distribution centered on their real "
             "final_projection with std_dev = that %% of the real value, "
             "clipped at 0, used only for that solve's objective -- output "
             "always reports the real projection. Works in both single- and "
             "multi-lineup modes; in multi-lineup mode each lineup gets its "
             "own independent draw.",
    )
    parser.add_argument(
        "--randomization-mode", dest="randomization_mode",
        choices=["pct", "sigma"], default="pct",
        help="Session 10.5 (decision #14): randomization std_dev scale. "
             "'pct' (default) -- pct%% of each player's real final_projection "
             "(every prior session's behavior, unchanged). "
             "'sigma' -- pct%% of each player's real per-player sigma, with "
             "an entry-count ramp (off at n=1, full at "
             f"{DEFAULT_SIGMA_RAND_FULL_LINEUPS}+ lineups, FLAGGED ARBITRARY). "
             "Requires --sigma-recalibration in the projection build. "
             "Use with --n-lineups; --randomization-pct sets the overall scale.",
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="Optional RNG seed for --randomization-pct, for reproducible runs. "
             "Omitted by default (genuinely random each run).",
    )
    # Session 3.3 -- Stacking Rules (decisions #14-21).
    parser.add_argument(
        "--stack-mode", choices=["none", "qb", "game", "mini"], default=DEFAULT_STACK_MODE,
        help="Stacking mode (default 'none' -- no stacking, existing behavior "
             "unchanged). 'qb': QB + N teammates (Standard/Double/Triple/QB+RB, "
             "optionally with --bring-back). 'game': Game Stack/Shootout, no QB "
             "required. 'mini': same-team RB+DST or opposing pass-catchers, via "
             "--mini-stack-type. Mandatory on every generated lineup when set "
             "(decision #15).",
    )
    parser.add_argument(
        "--stack-size", type=int, default=DEFAULT_STACK_SIZE,
        help=f"Number of QB-stack partners required (default {DEFAULT_STACK_SIZE} "
             f"= Standard stack; 2 = Double; 3 = Triple). Only used with "
             f"--stack-mode qb.",
    )
    parser.add_argument(
        "--stack-positions", default=DEFAULT_STACK_POSITIONS,
        help=f"Comma-separated eligible QB-stack partner positions (default "
             f"'{DEFAULT_STACK_POSITIONS}' -- any pass-catcher, decision #18). "
             f"E.g. --stack-positions RB for a QB+RB checkdown stack specifically. "
             f"Only used with --stack-mode qb.",
    )
    parser.add_argument(
        "--bring-back", action="store_true",
        help="Add-on to --stack-mode qb: require >=1 player from the stacked "
             "QB's opponent (decision #19 -- QB/RB/WR/TE only, never the "
             "opponent's DST/DEF).",
    )
    parser.add_argument(
        "--stack-team", default=None,
        help="Pin the stack to this team (e.g. KC), or a comma-separated list "
             "of teams (e.g. KC,SEA) to rotate the batch across exactly those "
             "teams instead of auto-selecting by Vegas implied total (decision "
             "#16, extended by #32). Used with --stack-mode qb or --stack-mode "
             "mini --mini-stack-type rb-dst.",
    )
    parser.add_argument(
        "--stack-game", default=None,
        help="Pin the stack to this exact game, TEAM-TEAM (e.g. KC-BUF), or a "
             "comma-separated list of games (e.g. KC-BUF,SEA-ARI) to rotate "
             "the batch across exactly those games instead of auto-selecting "
             "by over_under (decision #16, extended by #32). Used with "
             "--stack-mode game or --stack-mode mini --mini-stack-type "
             "opposing-pass-catchers.",
    )
    parser.add_argument(
        "--game-stack-min-players", type=int, default=DEFAULT_GAME_STACK_MIN_PLAYERS,
        help=f"Minimum combined players from both teams in a game stack "
             f"(default {DEFAULT_GAME_STACK_MIN_PLAYERS}). Only used with "
             f"--stack-mode game.",
    )
    parser.add_argument(
        "--mini-stack-type", choices=["rb-dst", "opposing-pass-catchers"], default=None,
        help="Required when --stack-mode mini: 'rb-dst' (same-team RB + that "
             "team's own DST/DEF) or 'opposing-pass-catchers' (a WR/TE from "
             "each side of one game).",
    )
    parser.add_argument(
        "--stack-candidate-pool", type=int, default=DEFAULT_STACK_CANDIDATE_POOL,
        help=f"When auto-selecting and diversifying (decision #17), how many "
             f"top teams/games (by implied_total/over_under) are eligible for "
             f"rotation across the batch (default {DEFAULT_STACK_CANDIDATE_POOL}).",
    )
    parser.add_argument(
        "--stack-diversify", choices=["auto", "on", "off"], default=DEFAULT_STACK_DIVERSIFY,
        help="Controls multi-lineup stack rotation (decision #17). 'auto' "
             "(default): diversify across candidates when auto-selecting, "
             "single target when pinned. 'on'/'off' force rotation on or off "
             "when auto-selecting -- has no effect when --stack-team/"
             "--stack-game is pinned (that always uses one target).",
    )
    # Session 7.2 -- Lock / Exclude (decisions #22-25).
    parser.add_argument(
        "--lock", default=None,
        help="Comma-separated player_id(s) to force into every generated "
             "lineup (decision #22). Fails loudly before solving if the "
             "request is structurally impossible (decision #24).",
    )
    parser.add_argument(
        "--exclude", default=None,
        help="Comma-separated player_id(s) to remove from the candidate pool "
             "entirely (decision #22).",
    )
    # Session 7.3 -- Salary Floor / FLEX Eligibility Restriction (decisions #28-29).
    parser.add_argument(
        "--min-salary-pct", type=float, default=DEFAULT_MIN_SALARY_PCT,
        help=f"Minimum %% of that site's salary cap the lineup must use "
             f"(default {DEFAULT_MIN_SALARY_PCT:.0f} -- no floor, existing "
             f"behavior unchanged). E.g. 95 requires spending at least 95%% "
             f"of the cap. A %% (not a flat dollar amount) so it travels "
             f"between DK's $50K and FD's $60K cap unchanged, same pattern "
             f"as pivot_finder.py's salary tolerance decision.",
    )
    parser.add_argument(
        "--flex-positions", default=None,
        help="Comma-separated subset of RB,WR,TE allowed to fill the FLEX "
             "slot (default: unset, meaning all three -- existing behavior "
             "unchanged). E.g. --flex-positions WR,RB excludes TE from "
             "FLEX entirely (each position still gets its own normal fixed "
             "slot(s) either way -- this only restricts the one extra FLEX "
             "seat).",
    )
    # Session 7.2b -- UI-Optimizer Integration (real-solver dispatch path).
    parser.add_argument(
        "--request-id", default=None,
        help="Decision #27: when set, output is written to "
             "output/ui_requests/{request-id}.csv INSTEAD OF the canonical "
             "lineup_single_{site}_{slate_id}.csv / lineups_multi_{site}_{slate_id}.csv "
             "path. Exists so an ad-hoc/interactive run (e.g. a UI 'try these "
             "settings' request dispatched via GitHub Actions) can never "
             "silently overwrite the canonical output file that live "
             "automation and other consumers read from. Omit for a normal, "
             "canonical run -- default behavior is unchanged.",
    )
    parser.add_argument(
        "--min-total-ownership", type=float, default=0.0,
        help="Requires the lineup's summed estimated_ownership_pct across "
             "all 9 players to be at least this much (default 0.0 -- no "
             "floor, existing behavior unchanged; same units as the UI's "
             "'Total Own' stat, e.g. 57.5). Same pattern as "
             "--min-salary-pct (decision #28): a floor alongside the "
             "existing points-maximization objective, not a second "
             "objective. Setting this very high (near the max achievable "
             "for the slate) converges toward the single highest-owned "
             "legal lineup -- a 'super chalk' reference build you can "
             "directly compare against the unrestricted optimal.",
    )
    # Session 8 (this session) -- Pool-level value filter (decision #34).
    parser.add_argument(
        "--min-projection", type=float, default=0.0,
        help="Excludes any player projected below this many points from "
             "the candidate pool entirely, before optimization runs "
             "(default 0.0 -- no floor, existing behavior unchanged). "
             "This is the 'filter pools: remove injured or bad-matchup "
             "players' step every commercial DFS optimizer runs as a "
             "separate pass from the optimization itself -- without it, a "
             "deeply exposure/uniqueness-constrained batch or a forced "
             "stack target can mathematically pull in a technically-legal "
             "but practically unusable player (e.g. a $4,000 player "
             "projected at 1.44 points) simply because nothing better was "
             "available at that step, not because it was ever a good "
             "pick. Locked players (decision #22) are always exempt.",
    )
    # Session 15 (Pre-Season Hardening) -- participation floor.
    parser.add_argument(
        "--participation-floors", default=DEFAULT_PARTICIPATION_FLOORS,
        help="Comma-separated POSITION:FLOOR pairs (e.g. 'QB:0.6,RB:0.4,"
             "TE:0.4'). A player whose participation_effective (share of "
             "his team's last 5 played games he actually appeared in, "
             "post role-change-correction) falls below his position's "
             "floor is excluded from the candidate pool entirely, before "
             "optimization runs -- same pattern and same pass as "
             "--min-projection (decision #34), but on games-played "
             "evidence instead of point projection, since a low-sample "
             "fluke game can inflate a real backup's projection past a "
             "point floor without ever giving him real volume. Locked "
             "players (decision #22) are always exempt -- use --lock for "
             "a known exception (e.g. a starter you know is back from "
             "injury at full workload, whose recent-games history hasn't "
             "caught up yet). A position not listed has no floor. Players "
             "with no games-played history at all (true rookies, first "
             "career game) or a confirmed no-game week (bye/OUT) are "
             "always exempt -- this floor only applies where there IS "
             "real history to judge. Defaults to "
             f"{DEFAULT_PARTICIPATION_FLOORS!r} -- ON by default, not opt-"
             "in. Pass an empty string ('') to disable entirely.",
    )
    # Session 10.5 (decision #2) -- lambda variance penalty.
    parser.add_argument(
        "--lambda", dest="lam", type=float, default=0.0,
        help="Session 10.5: lambda coefficient in the mean-variance objective "
             "sum(mu) - lambda*sum(sigma^2). Default 0.0 = pure-mean maximization "
             "(every prior session's behavior, unchanged). Positive values "
             "penalize variance (floor-seeking, cash games); negative values "
             "reward it (upside-seeking, GPPs). Requires a projection file built "
             "by build_projections_statline.py --sigma-recalibration: fails loud "
             "if the pool has no per-player sigma. The derived coarse grid from "
             "probe A3 (2018-2021 DK, 65 weeks): floor-seeking cash "
             "[0.039, 0.063, 0.104, 0.139, 0.188]; upside-seeking GPP "
             "[-0.003, -0.005, -0.014, -0.030, -0.095]. These are derived "
             "from the data -- not guessed -- and are the input to Session "
             "10.5's backtest sweep. FLAGGED ARBITRARY: no lambda has been "
             "validated by a backtest sweep yet; 0.0 is the only defensible "
             "production default until that sweep runs.",
    )
    # Session 12 -- Team / Game Exposure Caps (decisions #36-38).
    parser.add_argument(
        "--max-team-players", default=None,
        help="Comma-separated TEAM:N caps on the max number of players "
             "from that team allowed in the lineup (e.g. 'KC:2,DEN:1'). "
             "Applies to every generated lineup (decision #36), same as "
             "stacking. Additive alongside any stacking minimums requested "
             "-- a contradictory combination surfaces as normal solver "
             "infeasibility, not a special-cased error.",
    )
    parser.add_argument(
        "--max-game-players", default=None,
        help="Comma-separated TEAM-TEAM:N caps on the max COMBINED players "
             "from both teams in that game (e.g. 'KC-DEN:4,SEA-ARI:3'). "
             "Applies to every generated lineup (decision #36), same as "
             "stacking.",
    )
    # Session 13.4 addendum (decision #47, user-requested) -- Showdown-only
    # "one-sided lineup" lever, the mirror of --max-team-players.
    parser.add_argument(
        "--min-team-players", default=None,
        help="Showdown ONLY: comma-separated TEAM:N floors on the minimum "
             "number of players from that team required in the lineup "
             "(e.g. 'KC:5' to force a lopsided KC-heavy build, up to "
             "roster_size - min_per_team since the other team must still "
             "have >= 1 player). This is the lever for 'make the lineup "
             "one-sided' without full stacking support (decision #45's "
             "deferral) -- fails loudly up front (not a solver "
             "infeasibility) if the requested floor(s) are structurally "
             "impossible.",
    )
    # Session 16 -- Per-Player Exposure Override + Thumbs Up/Down (decisions
    # #48-55).
    parser.add_argument(
        "--player-exposure", default=None,
        help="Comma-separated PLAYER_ID:PCT caps (e.g. "
             "'00-0012345:0.5,00-0067890:0.3') giving named players their "
             "OWN max-exposure ceiling instead of --max-exposure's shared "
             "default -- everyone else is unaffected. PCT is a 0.0-1.0 "
             "fraction, same convention as --max-exposure itself (decision "
             "#52). Only used with --n-lineups -- exposure has no meaning "
             "for a single lineup. On Showdown, one cap covers both a "
             "player's Captain and FLEX rows (decision #53), matching how "
             "--max-exposure already behaves there.",
    )
    parser.add_argument(
        "--thumbs-up", default=None,
        help=f"Comma-separated player_id(s) whose final_projection is "
             f"boosted to {THUMBS_UP_MULTIPLIER:.0%}% of its real value for "
             f"this build (decision #48). Works in single- or multi-"
             f"lineup mode, classic or Showdown.",
    )
    parser.add_argument(
        "--thumbs-down", default=None,
        help=f"Comma-separated player_id(s) whose final_projection is "
             f"reduced to {THUMBS_DOWN_MULTIPLIER:.0%}% of its real value "
             f"for this build (decision #48). Works in single- or multi-"
             f"lineup mode, classic or Showdown.",
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    config = SITE_CONFIGS[args.site]

    # Session 13.4 -- Showdown/Single-Game format detection (decision #45).
    # Loaded once here for detection; build_single_lineup()/build_multi_lineup()
    # (classic) and build_single_showdown_lineup()/build_multi_showdown_lineup()
    # (Showdown) each reload it themselves -- an extra read of a small
    # final_projections file is cheap and keeps every function's own
    # loading/validation self-contained rather than threading a pre-loaded
    # DataFrame through every call site.
    _format_probe = load_final_projections(args.site, args.slate_id)
    _detected_showdown = is_showdown_pool(_format_probe)
    if args.format == "classic" and _detected_showdown:
        parser.error(
            f"--format classic was requested but final_projections_"
            f"{args.site}_{args.slate_id}.csv is a Showdown pool "
            f"(slate_format='showdown')."
        )
    if args.format == "showdown" and not _detected_showdown:
        parser.error(
            f"--format showdown was requested but final_projections_"
            f"{args.site}_{args.slate_id}.csv is not a Showdown pool."
        )
    showdown_mode = _detected_showdown if args.format == "auto" else (args.format == "showdown")

    if showdown_mode:
        # Decision #45 -- explicitly rejected for Showdown this session,
        # not silently ignored or half-applied.
        if args.stack_mode != "none":
            parser.error(
                "--stack-mode is not supported for Showdown slates yet "
                "(Session 13.4 deferred this -- see ROADMAP.md/"
                "SESSION_LOG.md). Omit --stack-mode (or leave it at "
                "'none') for a Showdown run."
            )
        if args.max_game_players:
            parser.error(
                "--max-game-players has no meaning on a Showdown slate "
                "(only one game exists in a 2-team pool by definition) -- "
                "use --max-team-players instead, or omit."
            )
        if args.flex_positions:
            parser.error(
                "--flex-positions has no meaning on a Showdown slate -- "
                "any position is eligible in both the CPT/MVP slot and "
                "every FLEX slot."
            )
        if args.min_total_ownership:
            parser.error(
                "--min-total-ownership is not supported for Showdown "
                "slates yet (Session 13.4 scope is the core ILP only -- "
                "see ROADMAP.md/SESSION_LOG.md)."
            )
        if args.min_projection:
            parser.error(
                "--min-projection is not supported for Showdown slates yet "
                "(Session 13.4 scope is the core ILP only -- see "
                "ROADMAP.md/SESSION_LOG.md)."
            )
    elif args.min_team_players:
        parser.error(
            "--min-team-players only applies to Showdown slates -- classic "
            "slates already have full stacking support via --stack-mode "
            "(e.g. --stack-mode game for a shootout-style build)."
        )

    stack_positions = parse_stack_positions(args.stack_positions) if args.stack_mode == "qb" else None
    stack_teams = parse_team_list(args.stack_team, "--stack-team") if args.stack_team else None
    stack_games = parse_game_list(args.stack_game, "--stack-game") if args.stack_game else None
    if args.stack_mode == "mini" and not args.mini_stack_type:
        parser.error("--stack-mode mini requires --mini-stack-type {rb-dst,opposing-pass-catchers}")

    locked_player_ids = parse_id_list(args.lock)
    excluded_player_ids = parse_id_list(args.exclude)
    overlap = locked_player_ids & excluded_player_ids
    if overlap:
        parser.error(
            f"player_id(s) {sorted(overlap)} cannot be both --lock and "
            f"--exclude (decision #25)."
        )

    # Session 16 -- decisions #48-51. Same "hard CLI error, not a silent
    # precedence rule" pattern as the --lock/--exclude overlap check above.
    thumbs_up_ids = parse_id_list(args.thumbs_up)
    thumbs_down_ids = parse_id_list(args.thumbs_down)
    thumbs_overlap = thumbs_up_ids & thumbs_down_ids
    if thumbs_overlap:
        parser.error(
            f"player_id(s) {sorted(thumbs_overlap)} cannot be both "
            f"--thumbs-up and --thumbs-down (decision #51)."
        )

    # Session 16 -- decisions #52-55. Unknown-id and lock-conflict checks
    # happen inside validate_exposure_cap_feasibility() below (both build
    # paths already call it), not here -- same split as --max-team-players'
    # own checks (structural feasibility inside the build function; only
    # this session's CLI-level parsing happens here).
    player_exposure = (
        parse_player_exposure_list(args.player_exposure, "--player-exposure")
        if args.player_exposure else None
    )
    if player_exposure and not args.n_lineups:
        print(
            "NOTE: --player-exposure was set but --n-lineups was not -- "
            "exposure has no meaning for a single lineup, ignored for "
            "this build.", file=sys.stderr,
        )

    # Session 7.3 -- decisions #28-29.
    flex_positions = parse_flex_positions(args.flex_positions) if args.flex_positions else None
    if not 0 <= args.min_salary_pct <= 100:
        parser.error("--min-salary-pct must be between 0 and 100.")
    min_salary = int(round((args.min_salary_pct / 100.0) * config["salary_cap"]))

    stack_kwargs = dict(
        stack_mode=args.stack_mode, stack_size=args.stack_size,
        stack_positions=stack_positions, bring_back=args.bring_back,
        stack_teams=stack_teams, stack_games=stack_games,
        game_stack_min_players=args.game_stack_min_players,
        mini_stack_type=args.mini_stack_type,
        candidate_pool_size=args.stack_candidate_pool,
    )

    # Session 12 -- decisions #36-38.
    max_team_players = (
        parse_team_cap_list(args.max_team_players, "--max-team-players")
        if args.max_team_players else None
    )
    max_game_players = (
        parse_game_cap_list(args.max_game_players, "--max-game-players")
        if args.max_game_players else None
    )
    if max_team_players or max_game_players:
        pool_teams = set(load_final_projections(args.site, args.slate_id)["team"])
        if max_team_players:
            unknown_teams = set(max_team_players) - pool_teams
            if unknown_teams:
                print(
                    f"NOTE: --max-team-players references team(s) not in "
                    f"this slate's pool: {sorted(unknown_teams)} (typo, or "
                    f"a bye) -- that cap will be a no-op (decision #38).",
                    file=sys.stderr,
                )
        if max_game_players:
            for game_key in max_game_players:
                missing = game_key - pool_teams
                if missing:
                    print(
                        f"NOTE: --max-game-players references team(s) not "
                        f"in this slate's pool: {sorted(missing)} (typo, "
                        f"or a bye) -- that cap will be a no-op "
                        f"(decision #38).", file=sys.stderr,
                    )

    # Session 15 -- participation floor. Scoped to classic slates only for
    # now (Showdown's role/position model -- one player can occupy CPT or
    # FLEX, any position eligible anywhere -- doesn't map onto a QB/RB/TE
    # position-keyed floor the same way; out of scope for this pass, same
    # "classic first" boundary Session 13.4 drew for other features).
    # Unlike --min-projection/--min-total-ownership's Showdown guards
    # (which error because the USER explicitly asked for something
    # unsupported), this one defaults ON -- erroring on every Showdown
    # build because of a default the user never touched would be a much
    # worse outcome than quietly not applying it. A NOTE either way, never
    # silent.
    if showdown_mode:
        if args.participation_floors and args.participation_floors != DEFAULT_PARTICIPATION_FLOORS:
            print(
                "NOTE: --participation-floors is not supported for "
                "Showdown slates yet -- ignored for this build.",
                file=sys.stderr,
            )
        participation_floors = {}
    else:
        participation_floors = (
            parse_participation_floors(args.participation_floors, "--participation-floors")
            if args.participation_floors else {}
        )

    # Decision #47 -- Showdown-only min-team-players floor.
    min_team_players = (
        parse_team_cap_list(args.min_team_players, "--min-team-players")
        if args.min_team_players else None
    )
    if min_team_players:
        validate_min_team_players_feasibility(args.site, min_team_players)
        pool_teams = set(load_final_projections(args.site, args.slate_id)["team"])
        unknown_teams = set(min_team_players) - pool_teams
        if unknown_teams:
            parser.error(
                f"--min-team-players references team(s) not in this "
                f"Showdown pool: {sorted(unknown_teams)} -- a Showdown "
                f"pool only has 2 teams, so (unlike --max-team-players) an "
                f"unknown team here can never be satisfied and isn't "
                f"treated as a harmless no-op."
            )

    if showdown_mode:
        if args.n_lineups:
            lineups, exposure_count, n_generated = build_multi_showdown_lineup(
                args.site, args.slate_id, n_lineups=args.n_lineups,
                max_exposure_pct=args.max_exposure, uniqueness=args.uniqueness,
                randomization_pct=args.randomization_pct,
                randomization_mode=args.randomization_mode,
                seed=args.seed, lam=args.lam,
                locked_player_ids=locked_player_ids,
                excluded_player_ids=excluded_player_ids,
                min_salary=min_salary, max_team_players=max_team_players,
                min_team_players=min_team_players,
                thumbs_up_ids=thumbs_up_ids, thumbs_down_ids=thumbs_down_ids,
                player_exposure=player_exposure,
            )
            if args.request_id:
                out_path = OUTPUT_DIR / "ui_requests" / f"{args.request_id}.csv"
                out_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                out_path = OUTPUT_DIR / f"lineups_multi_{args.site}_{args.slate_id}.csv"
            lineups.to_csv(out_path, index=False)

            exposure_cap = max(1, math.floor(args.max_exposure * args.n_lineups))
            override_note = f", {len(player_exposure)} player(s) using a custom cap" if player_exposure else ""
            top_exposure = sorted(exposure_count.items(), key=lambda kv: kv[1], reverse=True)[:10]
            print(f"[{config['label']}] Generated {n_generated}/{args.n_lineups} Showdown "
                  f"lineup(s) for slate {args.slate_id} (exposure cap: "
                  f"{exposure_cap}/{args.n_lineups} lineups = {args.max_exposure:.0%}{override_note})")
            _print_control_summary(locked_player_ids, excluded_player_ids,
                                    thumbs_up_ids, thumbs_down_ids, player_exposure)
            print("Top exposure (player_id: times used):")
            for pid, cnt in top_exposure:
                if cnt > 0:
                    print(f"  {pid}: {cnt}/{n_generated}")
            summary = lineups.groupby("lineup_id").agg(
                total_salary=("salary", "sum"), total_projection=("projection", "sum")
            )
            summary["lineup_value"] = (
                summary["total_projection"] / (summary["total_salary"] / 1000)
            ).round(2)
            summary["total_projection"] = summary["total_projection"].round(2)
            print("Per-lineup summary (lineup_id: salary used, total projection, value):")
            print(summary.to_string())
            print(f"Wrote {out_path}")
        else:
            lineup = build_single_showdown_lineup(
                args.site, args.slate_id,
                randomization_pct=args.randomization_pct,
                randomization_mode=args.randomization_mode,
                rng=np.random.default_rng(args.seed) if args.randomization_pct > 0 else None,
                locked_player_ids=locked_player_ids,
                excluded_player_ids=excluded_player_ids,
                min_salary=min_salary, lam=args.lam,
                max_team_players=max_team_players,
                min_team_players=min_team_players,
                thumbs_up_ids=thumbs_up_ids, thumbs_down_ids=thumbs_down_ids,
            )
            if args.request_id:
                out_path = OUTPUT_DIR / "ui_requests" / f"{args.request_id}.csv"
                out_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                out_path = OUTPUT_DIR / f"lineup_single_{args.site}_{args.slate_id}.csv"
            lineup.to_csv(out_path, index=False)

            showdown_cap = SITE_CONFIGS[args.site]["showdown"]["salary_cap"]
            total_salary = lineup["salary"].sum()
            total_points = lineup["projection"].sum()
            lineup_value = round(total_points / (total_salary / 1000), 2) if total_salary else 0.0
            print(f"[{config['label']}] Optimal single Showdown lineup for slate {args.slate_id}:")
            _print_control_summary(locked_player_ids, excluded_player_ids, thumbs_up_ids, thumbs_down_ids)
            print(lineup.to_string(index=False))
            print(f"Total salary: {total_salary} / {showdown_cap} ({showdown_cap - total_salary} remaining)")
            print(f"Total projected points: {total_points:.2f}")
            print(f"Lineup value: {lineup_value} pts/$1000")
            print(f"Wrote {out_path}")
        return

    if args.n_lineups:
        lineups, exposure_count, n_generated = build_multi_lineup(
            args.site, args.slate_id, n_lineups=args.n_lineups,
            max_exposure_pct=args.max_exposure,
            uniqueness=args.uniqueness,
            randomization_pct=args.randomization_pct,
            randomization_mode=args.randomization_mode,
            seed=args.seed,
            stack_diversify=args.stack_diversify,
            locked_player_ids=locked_player_ids,
            excluded_player_ids=excluded_player_ids,
            min_salary=min_salary, min_projection=args.min_projection,
            min_total_ownership=args.min_total_ownership,
            flex_positions=flex_positions,
            lam=args.lam,
            max_team_players=max_team_players, max_game_players=max_game_players,
            participation_floors=participation_floors,
            thumbs_up_ids=thumbs_up_ids, thumbs_down_ids=thumbs_down_ids,
            player_exposure=player_exposure,
            **stack_kwargs,
        )
        if args.request_id:
            out_path = OUTPUT_DIR / "ui_requests" / f"{args.request_id}.csv"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            lineups.to_csv(out_path, index=False)
            # Session 15 (Pre-Season Hardening), decision #B2 -- REAL BUG,
            # found while tracing why pivot suggestions never generate for
            # a real UI-built batch, not assumed. Every real "Build
            # Lineups" click in the deployed UI goes through
            # optimizer_api.js's dispatch, which always supplies a
            # request_id (a fresh UUID every click) -- so this branch, not
            # the `else` below, is what ACTUALLY runs for every real slate.
            # Before this fix, the only file written was the request_id-
            # keyed one above, used solely for the UI's poll-and-download
            # round trip -- output/lineups_multi_{site}_{slate_id}.csv (the
            # deterministic, slate-keyed name refresh_data.yml's pivot gate
            # and pivot_finder.py's load_lineup_players() both look for)
            # was NEVER written by a real UI build, only by a manual CLI
            # run with no --request-id, which real usage never does either.
            # Fixed by ALSO writing the slate-keyed copy here -- "most
            # recent batch wins" is the correct semantics for a pivot
            # source (pivots should reflect what you most recently built,
            # not some earlier historical batch), and this is a pure
            # addition: the request_id file and the UI's poll/download
            # behavior are completely unchanged.
            slate_path = OUTPUT_DIR / f"lineups_multi_{args.site}_{args.slate_id}.csv"
            lineups.to_csv(slate_path, index=False)
            out_path = slate_path  # for the "Wrote {out_path}" log line below
        else:
            out_path = OUTPUT_DIR / f"lineups_multi_{args.site}_{args.slate_id}.csv"
            lineups.to_csv(out_path, index=False)

        exposure_cap = max(1, math.floor(args.max_exposure * args.n_lineups))
        override_note = f", {len(player_exposure)} player(s) using a custom cap" if player_exposure else ""
        top_exposure = sorted(exposure_count.items(), key=lambda kv: kv[1], reverse=True)[:10]

        print(f"[{config['label']}] Generated {n_generated}/{args.n_lineups} lineups "
              f"for slate {args.slate_id} (exposure cap: {exposure_cap}/{args.n_lineups} "
              f"lineups = {args.max_exposure:.0%}{override_note}"
              + (f", randomization: {args.randomization_pct:.0f}%)" if args.randomization_pct > 0 else ", randomization: off)"))
        _print_control_summary(locked_player_ids, excluded_player_ids,
                                thumbs_up_ids, thumbs_down_ids, player_exposure)
        print("Top exposure (player_id: times used):")
        for pid, cnt in top_exposure:
            if cnt > 0:
                print(f"  {pid}: {cnt}/{n_generated}")
        # Session 8 (this session) addition -- per-lineup value summary, so
        # a batch can be scanned at a glance for anything that looks off
        # (unusually low total salary used, or a lineup_value well below
        # the rest of the batch) without opening the CSV.
        summary = lineups.groupby("lineup_id").agg(
            total_salary=("salary", "sum"), total_projection=("projection", "sum")
        )
        summary["lineup_value"] = (
            summary["total_projection"] / (summary["total_salary"] / 1000)
        ).round(2)
        summary["total_projection"] = summary["total_projection"].round(2)
        print("Per-lineup summary (lineup_id: salary used, total projection, value):")
        print(summary.to_string())
        print(f"Wrote {out_path}")
    else:
        lineup = build_single_lineup(
            args.site, args.slate_id,
            randomization_pct=args.randomization_pct,
            randomization_mode=args.randomization_mode,
            rng=np.random.default_rng(args.seed) if args.randomization_pct > 0 else None,
            locked_player_ids=locked_player_ids,
            excluded_player_ids=excluded_player_ids,
            min_salary=min_salary, min_projection=args.min_projection,
            min_total_ownership=args.min_total_ownership,
            flex_positions=flex_positions,
            lam=args.lam,
            max_team_players=max_team_players, max_game_players=max_game_players,
            participation_floors=participation_floors,
            thumbs_up_ids=thumbs_up_ids, thumbs_down_ids=thumbs_down_ids,
            **stack_kwargs,
        )
        if args.request_id:
            out_path = OUTPUT_DIR / "ui_requests" / f"{args.request_id}.csv"
            out_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            out_path = OUTPUT_DIR / f"lineup_single_{args.site}_{args.slate_id}.csv"
        lineup.to_csv(out_path, index=False)

        total_salary = lineup["salary"].sum()
        total_points = lineup["projection"].sum()
        lineup_value = round(total_points / (total_salary / 1000), 2) if total_salary else 0.0
        print(f"[{config['label']}] Optimal single lineup for slate {args.slate_id}"
              + (f" (randomization: {args.randomization_pct:.0f}%):" if args.randomization_pct > 0 else ":"))
        _print_control_summary(locked_player_ids, excluded_player_ids, thumbs_up_ids, thumbs_down_ids)
        print(lineup.to_string(index=False))
        print(f"Total salary: {total_salary} / {config['salary_cap']} "
              f"({config['salary_cap'] - total_salary} remaining)")
        print(f"Total projected points: {total_points:.2f}")
        print(f"Lineup value: {lineup_value} pts/$1000")
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    # Session 7.2c hotfix (real live testing this session): RuntimeError is
    # this file's consistent signal for "the requested settings/pool
    # combination is infeasible" (decisions #21/#24, solver infeasibility,
    # "no lineups could be generated") -- never an internal bug (verified:
    # every raise RuntimeError(...) site in this file is one of those
    # cases). A full Python traceback for that case reads as "the system is
    # broken" to someone who just picked an incompatible combination of
    # controls (e.g. --bring-back against a pool whose real opponents
    # aren't present) -- print just the clean message instead. Any OTHER
    # exception type still gets its full traceback unchanged, since that
    # DOES mean something unexpected broke and needs real debugging.
    try:
        main()
    except RuntimeError as e:
        print(f"\nCould not generate a lineup with the current settings: {e}", file=sys.stderr)
        sys.exit(1)
