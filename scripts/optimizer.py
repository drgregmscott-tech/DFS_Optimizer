"""
optimizer.py
============

Session 3.1 -- Single Lineup Optimizer.

For a given site (DK/FD) and week, reads that site's
`final_projections_{site}_{week}.csv` (Session 2.4, extended in Session 3.1
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
    python3 optimizer.py --site dk --week 10
    python3 optimizer.py --site fd --week 10

Outputs:
    output/lineup_single_{site}_{week}.csv
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
DEFAULT_RANDOMIZATION_PCT = 0.0


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
DEFAULT_STACK_POSITIONS = "WR,TE,RB"
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


def parse_team_pair(raw: str, flag_name: str) -> tuple:
    parts = [p.strip().upper() for p in raw.split("-")]
    if len(parts) != 2:
        raise SystemExit(f"{flag_name} must be TEAM-TEAM (e.g. KC-BUF), got: {raw!r}")
    return tuple(parts)


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


def rank_candidate_games(players: pd.DataFrame) -> list:
    """Ranks distinct real games (excludes bye-week/unknown rows -- see
    build_projections.py decision #6's BYE_OR_UNKNOWN sentinel) by
    over_under (desc). Returns a list of (team_a, team_b) tuples, deduped
    so each real game appears once regardless of which side's row it came
    from.

    Requires BOTH sides to actually have players present in the current
    pool -- not just that the game exists in Vegas data (a real, thin test
    pool can have a team's real Vegas opponent entirely absent from the
    salary file; found via real-data testing -- see SESSION_LOG.md)."""
    real = players[(players["opponent"] != "BYE_OR_UNKNOWN") & (players["opponent"].notna())]
    if "over_under" not in real.columns or real.empty:
        return []
    teams_in_pool = set(players["team"].unique())
    pairs = real[["team", "opponent", "over_under"]].drop_duplicates()
    pairs = pairs[pairs["opponent"].isin(teams_in_pool)]  # both sides must have real pool players
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

def load_final_projections(site: str, week: int) -> pd.DataFrame:
    path = OUTPUT_DIR / f"final_projections_{site}_{week}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run build_projections.py --site {site} "
            f"--week {week} first (Session 2.4, extended in Session 3.1 "
            f"for DST/DEF -- decision #5)."
        )
    df = pd.read_csv(path, dtype={"player_id": str})
    required = {
        "player_id", "player_name", "position", "team", "salary", "final_projection",
        # Session 3.3 addition (build_projections.py decision #6) -- needed
        # for stack team/game auto-selection and bring-back/game-stack
        # constraints below. A final_projections file generated before this
        # addendum won't have these -- re-run build_projections.py.
        "opponent", "implied_total",
    }
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(
            f"{path} is missing expected columns: {sorted(missing)}. "
            f"build_projections.py's output schema may have changed (or this "
            f"file predates Session 3.3's opponent/implied_total addition -- "
            f"re-run build_projections.py) -- update this script's "
            f"load_final_projections() to match."
        )
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
                           rng: np.random.Generator) -> pd.Series:
    """Returns a pd.Series indexed by player_id: the real `final_projection`
    unchanged if `randomization_pct <= 0` (decision #10), otherwise one
    independent normal draw per player with mean = real final_projection and
    std_dev = randomization_pct% of that same value (decision #9), clipped
    at 0.0. This Series is meant to be passed to `solve_lineup`'s
    `optimization_projection` param -- it never modifies `players` itself,
    so the real final_projection stays intact for output/display (decision
    #11)."""
    base = players.set_index("player_id")["final_projection"]
    if randomization_pct <= 0:
        return base
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
                  mini_stack_type: str = None) -> pd.DataFrame:
    """`previous_lineups`/`uniqueness` are Session 3.2 additions (see
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

    prob += pulp.lpSum(x[pid] * proj[pid] for pid in x), "total_projected_points"

    # Salary cap.
    prob += pulp.lpSum(x[pid] * salary[pid] for pid in x) <= salary_cap, "salary_cap"

    # Total roster size.
    total_slots = sum(fixed_counts.values()) + flex_count
    prob += pulp.lpSum(x[pid] for pid in x) == total_slots, "total_roster_size"

    by_position = {
        pos: players.loc[players["position"] == pos, "player_id"].tolist()
        for pos in set(position)
    }

    for pos, required in fixed_counts.items():
        pool = by_position.get(pos, [])
        if pos in FLEX_ELIGIBLE_POSITIONS:
            # Own minimum, can exceed via FLEX -- exact total enforced below.
            prob += pulp.lpSum(x[pid] for pid in pool) >= required, f"min_{pos}"
        else:
            # QB / DST-DEF -- no FLEX eligibility, exact count.
            prob += pulp.lpSum(x[pid] for pid in pool) == required, f"exact_{pos}"

    flex_pool = [pid for pos in FLEX_ELIGIBLE_POSITIONS for pid in by_position.get(pos, [])]
    flex_fixed_total = sum(c for pos, c in fixed_counts.items() if pos in FLEX_ELIGIBLE_POSITIONS)
    prob += (
        pulp.lpSum(x[pid] for pid in flex_pool) == flex_fixed_total + flex_count,
        "rb_wr_te_pool_total",
    )

    # Session 3.2 -- uniqueness constraints (decision #7). Only players
    # still present in this solve's pool are counted; a previously-used
    # player who has since been exposure-locked-out (decision #5, handled
    # by the caller filtering the pool before this function runs) simply
    # isn't in `x`, so referencing them here would be a KeyError -- filter
    # to the ones that are.
    if previous_lineups:
        for i, prev_ids in enumerate(previous_lineups):
            relevant = [pid for pid in prev_ids if pid in x]
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
            "player_name": row.player_name,
            "position": row.position,
            "team": row.team,
            "salary": row.salary,
            "projection": row.final_projection,
            # Session 3.3 addition -- needed by validate_stack() for
            # bring-back checks, and generally useful in the output CSV to
            # see who a selected player was facing.
            "opponent": row.opponent,
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
                              stack_positions: set, stack_team: str, stack_game: tuple,
                              mini_stack_type: str, candidate_pool_size: int,
                              diversify_requested: str, bring_back: bool = False) -> tuple:
    """Decision #16/#17. Returns (candidates, diversify_active, pin_note):
    - candidates: list of {"target_team":..., "target_game":...} dicts --
      one entry if pinned or not diversifying, up to candidate_pool_size
      entries (ranked best-first) if diversifying.
    - diversify_active: whether the caller should rotate across
      `candidates` per lineup. Always False when a team/game is pinned,
      regardless of --stack-diversify (decision #17).
    - pin_note: a string to print if --stack-diversify on was combined with
      an explicit pin (has no effect, but flagged rather than silently
      ignored), else None."""
    pinned = bool(stack_team or stack_game)
    pin_note = None

    if stack_mode == "qb" or (stack_mode == "mini" and mini_stack_type == "rb-dst"):
        partner_positions = stack_positions if stack_mode == "qb" else {"RB"}
        require_opp = bool(stack_mode == "qb" and bring_back)
        if stack_team:
            candidates = [{"target_team": stack_team, "target_game": None}]
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
        if stack_game:
            candidates = [{"target_team": None, "target_game": stack_game}]
        else:
            ranked = rank_candidate_games(players_all)
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

    if pinned and diversify_requested == "on":
        pin_note = (
            "--stack-diversify on was set together with an explicit "
            "--stack-team/--stack-game pin -- diversify has no effect once "
            "the team/game is pinned (decision #17); using the pinned "
            "target for every lineup."
        )
    diversify_active = (not pinned) and (diversify_requested != "off")
    return candidates, diversify_active, pin_note


def _stack_label(cand: dict) -> str:
    if cand.get("target_team"):
        return f"team:{cand['target_team']}"
    if cand.get("target_game"):
        return f"game:{cand['target_game'][0]}-{cand['target_game'][1]}"
    return ""


def build_single_lineup(site: str, week: int, randomization_pct: float = DEFAULT_RANDOMIZATION_PCT,
                         rng: np.random.Generator = None,
                         stack_mode: str = DEFAULT_STACK_MODE, stack_size: int = DEFAULT_STACK_SIZE,
                         stack_positions: set = None, bring_back: bool = False,
                         stack_team: str = None, stack_game: tuple = None,
                         game_stack_min_players: int = DEFAULT_GAME_STACK_MIN_PLAYERS,
                         mini_stack_type: str = None,
                         candidate_pool_size: int = DEFAULT_STACK_CANDIDATE_POOL) -> pd.DataFrame:
    config = SITE_CONFIGS[site]
    players = load_final_projections(site, week)
    fixed_counts, flex_count = parse_roster_requirements(config["roster_slots"])

    optimization_projection = None
    if randomization_pct > 0:
        rng = rng if rng is not None else np.random.default_rng()
        optimization_projection = randomize_projections(players, randomization_pct, rng)

    # Session 3.3 -- single-lineup mode always uses the single BEST
    # candidate (no diversification concept for one lineup) unless pinned.
    target_team = target_game = None
    if stack_mode != "none":
        candidates, _, pin_note = resolve_stack_candidates(
            players, stack_mode, stack_positions, stack_team, stack_game,
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
    )
    lineup = assign_roster_slots(selected, fixed_counts)
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

def build_multi_lineup(site: str, week: int, n_lineups: int = DEFAULT_N_LINEUPS,
                        max_exposure_pct: float = DEFAULT_MAX_EXPOSURE_PCT,
                        uniqueness: int = DEFAULT_UNIQUENESS,
                        randomization_pct: float = DEFAULT_RANDOMIZATION_PCT,
                        seed: int = None,
                        stack_mode: str = DEFAULT_STACK_MODE, stack_size: int = DEFAULT_STACK_SIZE,
                        stack_positions: set = None, bring_back: bool = False,
                        stack_team: str = None, stack_game: tuple = None,
                        game_stack_min_players: int = DEFAULT_GAME_STACK_MIN_PLAYERS,
                        mini_stack_type: str = None,
                        candidate_pool_size: int = DEFAULT_STACK_CANDIDATE_POOL,
                        stack_diversify: str = DEFAULT_STACK_DIVERSIFY) -> tuple:
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
    (no `stack_team`/`stack_game` pin) and `stack_diversify` allows it
    (decision #17), the batch ROTATES through up to `candidate_pool_size`
    candidate teams/games (best-first by implied_total/over_under) instead
    of repeating one target for all `n_lineups`. For each lineup, if the
    current rotation candidate turns out infeasible (e.g. its players got
    exposure-locked-out earlier in the batch), the remaining candidates are
    tried before falling back to uniqueness relaxation -- a stacking
    infeasibility and a diversity infeasibility are handled as separate,
    independently-retried problems rather than one giving up for the other."""
    config = SITE_CONFIGS[site]
    players_all = load_final_projections(site, week)
    fixed_counts, flex_count = parse_roster_requirements(config["roster_slots"])
    rng = np.random.default_rng(seed) if randomization_pct > 0 else None

    exposure_cap = max(1, math.floor(max_exposure_pct * n_lineups))

    candidates = [{"target_team": None, "target_game": None}]
    diversify_active = False
    if stack_mode != "none":
        candidates, diversify_active, pin_note = resolve_stack_candidates(
            players_all, stack_mode, stack_positions, stack_team, stack_game,
            mini_stack_type, candidate_pool_size, stack_diversify,
            bring_back=bring_back,
        )
        if pin_note:
            print(pin_note, file=sys.stderr)
        if diversify_active:
            print(
                f"Stacking: diversifying across {len(candidates)} candidate "
                f"{'team' if stack_mode in ('qb',) or (stack_mode == 'mini' and mini_stack_type == 'rb-dst') else 'game'}(s) "
                f"across the batch (decision #17): "
                f"{[_stack_label(c) for c in candidates]}",
            )
        else:
            print(f"Stacking: every lineup uses {_stack_label(candidates[0])}.")

    exposure_count = {pid: 0 for pid in players_all["player_id"]}
    previous_lineups = []
    all_lineup_frames = []
    current_uniqueness = uniqueness
    n_generated = 0

    while n_generated < n_lineups:
        locked_out = {pid for pid, cnt in exposure_count.items() if cnt >= exposure_cap}
        pool = players_all[~players_all["player_id"].isin(locked_out)]

        # Decision #12 -- independent draw per lineup, not one draw reused
        # for the whole batch.
        optimization_projection = None
        if randomization_pct > 0:
            optimization_projection = randomize_projections(pool, randomization_pct, rng)

        # Decision #17 -- rotation order for this lineup: if diversifying,
        # start at a different candidate each lineup (round-robin) so a
        # batch of e.g. 5 candidates x 20 lineups cycles through evenly,
        # rather than exhausting candidate[0] before ever trying candidate[1].
        if diversify_active:
            start = n_generated % len(candidates)
            try_order = candidates[start:] + candidates[:start]
        else:
            try_order = [candidates[0]]

        selected = None
        chosen_cand = None
        stack_infeasible_reason = None
        for cand in try_order:
            try:
                selected = solve_lineup(
                    pool, config["salary_cap"], fixed_counts, flex_count,
                    previous_lineups=previous_lineups,
                    uniqueness=current_uniqueness,
                    optimization_projection=optimization_projection,
                    stack_mode=stack_mode, stack_size=stack_size,
                    stack_positions=stack_positions, bring_back=bring_back,
                    target_team=cand["target_team"], target_game=cand["target_game"],
                    game_stack_min_players=game_stack_min_players,
                    mini_stack_type=mini_stack_type,
                )
                chosen_cand = cand
                break
            except RuntimeError as e:
                stack_infeasible_reason = e
                continue

        if selected is None:
            if current_uniqueness > 0:
                print(
                    f"WARNING: lineup {n_generated + 1}/{n_lineups} infeasible with "
                    f"uniqueness={current_uniqueness} across all "
                    f"{len(try_order)} candidate(s) tried (pool too thin -- see "
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

        lineup = assign_roster_slots(selected, fixed_counts)
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", choices=["dk", "fd"], required=True)
    parser.add_argument("--week", type=int, required=True)
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
        help="Pin the stack to this team (e.g. KC) instead of auto-selecting by "
             "Vegas implied total (decision #16). Used with --stack-mode qb or "
             "--stack-mode mini --mini-stack-type rb-dst.",
    )
    parser.add_argument(
        "--stack-game", default=None,
        help="Pin the stack to this exact game, TEAM-TEAM (e.g. KC-BUF), instead "
             "of auto-selecting by over_under (decision #16). Used with "
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
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    config = SITE_CONFIGS[args.site]

    stack_positions = parse_stack_positions(args.stack_positions) if args.stack_mode == "qb" else None
    stack_game = parse_team_pair(args.stack_game, "--stack-game") if args.stack_game else None
    if args.stack_mode == "mini" and not args.mini_stack_type:
        parser.error("--stack-mode mini requires --mini-stack-type {rb-dst,opposing-pass-catchers}")
    stack_kwargs = dict(
        stack_mode=args.stack_mode, stack_size=args.stack_size,
        stack_positions=stack_positions, bring_back=args.bring_back,
        stack_team=args.stack_team, stack_game=stack_game,
        game_stack_min_players=args.game_stack_min_players,
        mini_stack_type=args.mini_stack_type,
        candidate_pool_size=args.stack_candidate_pool,
    )

    if args.n_lineups:
        lineups, exposure_count, n_generated = build_multi_lineup(
            args.site, args.week, n_lineups=args.n_lineups,
            max_exposure_pct=args.max_exposure,
            uniqueness=args.uniqueness,
            randomization_pct=args.randomization_pct,
            seed=args.seed,
            stack_diversify=args.stack_diversify,
            **stack_kwargs,
        )
        out_path = OUTPUT_DIR / f"lineups_multi_{args.site}_{args.week}.csv"
        lineups.to_csv(out_path, index=False)

        exposure_cap = max(1, math.floor(args.max_exposure * args.n_lineups))
        top_exposure = sorted(exposure_count.items(), key=lambda kv: kv[1], reverse=True)[:10]

        print(f"[{config['label']}] Generated {n_generated}/{args.n_lineups} lineups "
              f"for week {args.week} (exposure cap: {exposure_cap}/{args.n_lineups} "
              f"lineups = {args.max_exposure:.0%}"
              + (f", randomization: {args.randomization_pct:.0f}%)" if args.randomization_pct > 0 else ", randomization: off)"))
        print("Top exposure (player_id: times used):")
        for pid, cnt in top_exposure:
            if cnt > 0:
                print(f"  {pid}: {cnt}/{n_generated}")
        print(f"Wrote {out_path}")
    else:
        lineup = build_single_lineup(
            args.site, args.week,
            randomization_pct=args.randomization_pct,
            rng=np.random.default_rng(args.seed) if args.randomization_pct > 0 else None,
            **stack_kwargs,
        )
        out_path = OUTPUT_DIR / f"lineup_single_{args.site}_{args.week}.csv"
        lineup.to_csv(out_path, index=False)

        total_salary = lineup["salary"].sum()
        total_points = lineup["projection"].sum()
        print(f"[{config['label']}] Optimal single lineup for week {args.week}"
              + (f" (randomization: {args.randomization_pct:.0f}%):" if args.randomization_pct > 0 else ":"))
        print(lineup.to_string(index=False))
        print(f"Total salary: {total_salary} / {config['salary_cap']} "
              f"({config['salary_cap'] - total_salary} remaining)")
        print(f"Total projected points: {total_points:.2f}")
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
