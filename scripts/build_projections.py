"""
build_projections.py
=====================

Session 2.4 -- Full Blend Pipeline.

For a given site (DK/FD), season, and target week, merges the outputs of
Sessions 2.1-2.3 plus that site's salary file into one clean weekly
projections table: `final_projections_{site}_{week}.csv`.

final_projection = (0.5 * season_avg + 0.5 * recent_form) * matchup_factor * vegas_factor

This session's card left three real design gaps unresolved. All three were
cleared with the user before building (same pattern as Session 2.1's
lookahead-bias guard / Session 2.2's per-team-week summing):

  1. vegas_factor isn't defined anywhere upstream. vegas_odds.py (2.3)
     outputs `implied_total`, a raw point total, not a normalized
     multiplier. Checked for an industry-standard "vegas factor" -- didn't
     find one; DFS literature (FantasyLabs "Vegas Score", Stokastic, etc.)
     uses the raw implied_total itself as a model input, not a ratio.
     Decision (this session): define vegas_factor the same way 2.2 already
     defined matchup_factor -- a team's implied_total divided by the
     league-average implied_total across teams actually playing that
     target week. Keeps both multipliers on the same "1.0 = league
     average" scale, which is what lets them multiply together cleanly in
     the blend formula below.

  2. No prior session's output tells you a player's WEEK-N OPPONENT.
     baseline_recent_form has no team column at all. matchup_factors is
     indexed by team, not by "who is this player about to face." And
     vegas_implied_totals_{week}.csv is known (Session 2.3's log) to mix
     multiple weeks of games together, with `--week` only labeling the
     filename. Decision (this session): pull in `schedules_{season}.parquet`
     (a real Session 1.2 output, just not listed on this card's Inputs --
     same kind of drift Session 1.2 itself flagged when it added schedules/
     rosters outputs beyond the roadmap's original file list) to build a
     team -> week-N-opponent map. That map does double duty:
       a. gives the opponent team to look up in matchup_factors (a player's
          matchup is against their OPPONENT's defense, not their own team)
       b. filters vegas_implied_totals_{week}.csv down to exactly that
          week's (team, opponent) pairs, which resolves the multi-week
          mixing problem without guessing off `commence_time` alone.

  3. Missing-data handling. Roadmap validation demands "no nulls, no
     unexpectedly missing players." Decision (user-confirmed): a player
     missing matchup_factor or vegas_factor (bye week, unscheduled game,
     line not posted yet) gets a neutral 1.0 rather than being dropped.
     Extending that same neutral philosophy to a gap Session 2.1 explicitly
     deferred to this session: a player with no season_avg/recent_form yet
     (rookie debut, 0 games played before the target week -- 2.1 left this
     as NaN on purpose, for exactly this session to decide) gets 0.0 for
     both rather than being dropped, since "we have no evidence this
     player will score fantasy points yet" is a legitimate real answer,
     not a bug.

  4. Salary-file team drift in backtests (found + fixed during Session
     2.4's addendum, real-data re-run). A player's team in the salary
     file reflects whenever that file was downloaded (e.g. today), not
     necessarily their team as of the TARGET week -- fine for live
     production (current salary file + current week always agree), but
     silently wrong for backtesting a past week with a live snapshot.
     Quantified example: Joe Flacco's salary-file team (CLE) doesn't
     match his real week-10-2025 team (CIN) -- 5 of 85 skill players in
     one real DK pool were affected. Decision (user-confirmed, "Option
     A"): auto-correct using weekly_stats_{season}.parquet, no flag
     required -- if the target week has already been played, trust real
     data over the salary snapshot. Two distinct sub-cases, found only
     after building this and checking all 5 real examples:
       a. Player has a real row for the target week (played, just for a
          DIFFERENT team than the salary file shows -- an in-season
          trade). Correctable: use their real team for that week.
       b. Player has NO real row for the target week at all -- turned out
          to be all 5 of the real examples found, including Flacco (his
          team, CIN, had a bye that week -- he has no team to "correct"
          to, because he didn't play). Not correctable by picking a team:
          forcing in the salary file's team here would compute a
          plausible-LOOKING but factually wrong matchup/vegas factor (as
          it did for Flacco before this fix).

          IMPORTANT, caught as a follow-up bug: neutralizing
          matchup_factor/vegas_factor to 1.0 alone was NOT enough -- that
          still left a real, positive final_projection (Flacco showed
          ~20.04, driven by his season_avg/recent_form, with only the
          matchup/vegas multipliers neutralized). But for an ALREADY-
          PLAYED week, "no real row" isn't uncertainty, it's hindsight: we
          know for a fact this player scored zero real fantasy points
          that week. So final_projection is forced to 0.0 outright for
          these players, not just neutrally-factored. This is distinct
          from decision #3's rookie/no-history case and from a live run
          with an uncertain-status player (target week hasn't happened
          yet) -- in a live run, we genuinely don't know a player's status
          and a normal non-zero projection is correct (that's what Session
          5.1's injury-status work is for); zeroing every uncertain player
          in a live run would defeat the pipeline's purpose. The
          `no_real_game_this_week` flag is only ever set True when the
          target week has already been played, so this zero-out never
          fires during live usage.
     If the target week hasn't happened yet (a real live/current run),
     weekly_stats has no rows for it at all by definition, so both
     sub-cases are skipped entirely and the salary file's team is used
     as-is -- live production is never affected.

  5. DST/DEF projections (added Session 3.1, decision cleared with the user
     before building -- same pattern as decisions #1-#4 above). Team
     defenses were excluded entirely through Session 2.4 because
     weekly_stats has no defense-level rows, so there's no real
     season_avg/recent_form/matchup_factor to blend the way skill
     positions get blended. But Session 3.1 (single-lineup optimizer)
     needs a full legal 9-slot roster for both sites, and both site
     rosters require one DST/DEF slot -- an optimizer with zero defense
     rows in the player pool can never produce a legal lineup. Decision
     (user-confirmed, "Option A" from Session 3.1's clarifying question):
     add a REAL projection now rather than a flat placeholder, built from
     the only two genuinely real signals available for a defense:
       a. `AvgPointsPerGame` -- a real season average DraftKings/FanDuel
          computes and includes directly in the salary export for EVERY
          player, including defenses. Never used anywhere upstream before
          this (skill-position season_avg/recent_form instead come from
          weekly_stats via Sessions 2.1), but for defenses it's the only
          real historical scoring signal that exists in this pipeline.
          Used as-is for both `season_avg` and `recent_form` -- there's no
          week-by-week defense data available to distinguish "recent" from
          "season," so both columns carry the same real number rather than
          fabricating a fake split. Flagged as a known simplification, not
          silently hidden.
       b. Vegas, inverted. A defense's fantasy output (sacks, turnovers,
          points allowed, defensive/return TDs) correlates with how POORLY
          the opposing OFFENSE is expected to do, not the defense's own
          team's implied_total (which reflects their own offense). So
          `vegas_factor` for a DST/DEF is `league_avg_implied_total /
          opponent_implied_total` -- the inverse of the skill-position
          convention in decision #1 above, and using the OPPONENT's number,
          not the defense's own team's number.
     No `matchup_factor` exists for defenses at all (Session 2.2's
     matchup_factors_{site}_{season}_{week}.csv only covers QB/RB/WR/TE) --
     held at a flat neutral 1.0, flagged as a known gap a future session
     could close (e.g. real defensive DVOA/points-allowed-by-position data)
     rather than silently building a fake one now.
     Bye-week handling matches decision #4b's philosophy exactly: a
     defense whose team has no row in vegas_implied_totals_{week}.csv (no
     game that week -- confirmed this is how a bye shows up post-Session
     2.3's fix, not an error) gets `final_projection` forced to 0.0, not a
     neutrally-factored guess, since a bye defense scores zero real
     fantasy points, full stop -- exactly the same real-outcome-over-
     plausible-guess logic already applied to skill players in decision #4b.
     This DST/DEF projection needs no `schedules_{season}.parquet` lookup
     at all (unlike decision #2's skill-position opponent map) --
     vegas_implied_totals_{week}.csv already carries each team's real
     opponent for the week directly in its own `opponent` column (a fix
     from Session 2.3's addendum), so defense projections have one fewer
     upstream file dependency than skill-position projections.

  6. Session 3.3 addendum -- opponent/implied_total/over_under exposed in
     the output. Session 3.3 (Stacking Rules) needs each player's week-N
     opponent and each team's Vegas implied total to auto-select and
     validate QB/game/bring-back/mini-stacks in optimizer.py. Both values
     are already computed internally (decision #2's opponent_map, and
     build_vegas_factors()'s merge) but were never written to the output
     CSV -- optimizer.py would otherwise have to re-derive the same
     schedule/vegas lookups a second time, in a different file, with a
     real risk of drifting out of sync with this file's own logic.
     Decision: add `opponent`, `implied_total` (the player's own team's),
     and `over_under` (that game's total, for game-stack selection) as
     three additional output columns, for both skill players and DST/DEF
     rows. Purely additive -- no existing column's values change, so every
     prior session's validation still holds unchanged. For a bye-week/
     no-real-game player, these are left null, consistent with
     matchup_factor/vegas_factor being neutral-filled but the player
     having no real game to point an opponent/total at.

Site-awareness: this script does not recompute fantasy points itself --
by the time projections reach this stage, DK vs FD is already baked into
the season_avg/recent_form/matchup_factor inputs (site-specific from 2.1/
2.2) and reflected in which players/salaries are in the salary file (2.1
different cap/roster/scoring per SITE_CONFIGS in ingest_salaries.py).
Only the *shared* vegas_implied_totals_{week}.csv input is site-agnostic,
per Session 2.3.

Team defenses (DK "DST" / FD "D"/"DEF") were excluded from this pipeline
through Session 2.4 -- weekly_stats has no defense-level rows, so 2.1/2.2
never produced a season_avg/recent_form/matchup_factor for them the way
skill positions get one. Session 3.1 adds a real (if simplified)
projection for them -- see decision #5 above -- since the optimizer needs
a full 9-slot roster including DST/DEF for both sites.

  7. Session 7.3 addition (user-confirmed): `chalk_score` and
     `estimated_ownership_pct` (Session 4.1's ownership_heuristic.py) are
     now baked directly into this file's own output, instead of requiring
     a separate `chalk_scores_{site}_{week}.csv` file the frontend had to
     upload a second time. `add_ownership_columns()` below imports and
     calls ownership_heuristic.py's own `compute_chalk_scores()`/
     `compute_estimated_ownership()` UNCHANGED, on this exact run's
     in-memory DataFrame (not a re-read of the just-written CSV) -- no
     second implementation of the ownership math to drift out of sync,
     and no risk of the two files disagreeing within a single run.
     ownership_heuristic.py's own standalone CLI is untouched and still
     produces `chalk_scores_{site}_{week}.csv` exactly as before -- this
     is purely an additional consumer of its compute functions, not a
     replacement. Downstream readers of `final_projections_{site}_{week}.csv`
     that don't know about the two new columns are unaffected (extra
     columns, nothing existing changed or removed).

Usage:
    python3 build_projections.py --site dk --season 2025 --week 10 \
        --slate-id classic_wk10
    python3 build_projections.py --site fd --season 2025 --week 10 \
        --slate-id classic_wk10
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest_salaries import SITE_CONFIGS  # noqa: E402 -- Session 1.3's single source of truth for per-site defense-position labels (decision #5)
from ownership_heuristic import compute_chalk_scores, compute_estimated_ownership  # noqa: E402 -- Session 7.3 decision #7: bake ownership into final_projections directly, see add_ownership_columns() below

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUT_DIR = REPO_ROOT / "output"

POSITIONS = ["QB", "RB", "WR", "TE"]

# Blend weights -- user-confirmed 0.5/0.5 on season_avg/recent_form, with
# matchup_factor and vegas_factor applied as multipliers on top. Logged
# here explicitly (per the roadmap card's handoff-notes instruction) so
# Session 9.2's future retuning has a clear starting point to diff against.
BASELINE_WEIGHT = 0.5
RECENT_FORM_WEIGHT = 0.5

# ---------------------------------------------------------------------------
# Step 0: Load the three projection-component inputs + salary file
# ---------------------------------------------------------------------------

def load_baseline_recent_form(site: str, season: int, week: int) -> pd.DataFrame:
    path = OUTPUT_DIR / f"baseline_recent_form_{site}_{season}_{week}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run projections_baseline.py --site {site} "
            f"--season {season} --week {week} first (Session 2.1)."
        )
    return pd.read_csv(path, dtype={"player_id": str})


def load_matchup_factors(site: str, season: int, week: int) -> pd.DataFrame:
    path = OUTPUT_DIR / f"matchup_factors_{site}_{season}_{week}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run projections_matchup.py --site {site} "
            f"--season {season} --week {week} first (Session 2.2)."
        )
    return pd.read_csv(path)


def load_vegas_implied_totals(week: int) -> pd.DataFrame:
    path = OUTPUT_DIR / f"vegas_implied_totals_{week}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run vegas_odds.py --week {week} first "
            f"(Session 2.3)."
        )
    return pd.read_csv(path)


def load_salaries(site: str, slate_id: str) -> pd.DataFrame:
    path = DATA_DIR / f"salaries_{site}_{slate_id}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run ingest_salaries.py --site {site} "
            f"--slate-id {slate_id} first (Session 1.3)."
        )
    # Session 7.3 addition -- site_id_col (ingest_salaries.py's
    # SITE_CONFIGS) is the site's OWN player ID (DK's "ID", FD's "Id"),
    # different from this pipeline's nflverse player_id. Read as str
    # explicitly, same reasoning as player_id below -- an all-numeric
    # column with no NaNs would read fine as int64, but one bye/inactive
    # row with a blank ID anywhere would upcast the whole column to
    # float64 and every ID would come out "43636569.0".
    site_id_col = SITE_CONFIGS[site]["site_id_col"]
    df = pd.read_csv(path, dtype={"player_id": str, site_id_col: str})
    required = {"player_id", "name", "salary", "normalized_team", "position_upper", site_id_col}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(
            f"{path} is missing expected columns: {sorted(missing)}. "
            f"ingest_salaries.py's output schema may have changed -- update "
            f"this script's load_salaries() to match."
        )
    return df


def load_schedule(season: int) -> pd.DataFrame:
    """Team -> week-N-opponent comes from schedules_{season}.parquet
    (Session 1.2 output). Not on this card's original Inputs list -- added
    this session because nothing else upstream carries opponent info for a
    future week. See module docstring, decision #2.
    """
    path = DATA_DIR / f"schedules_{season}.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. This is a Session 1.2 output -- run "
            f"ingest_historical.py --season {season} if it's missing. "
            f"(Added as a new input this session -- see build_projections.py's "
            f"module docstring, decision #2.)"
        )
    df = pd.read_parquet(path)

    # Defensive column-name handling -- nflverse schema gotchas have bitten
    # every prior session that touched a new release (1.1: recent_team ->
    # team, 1.2: schedules asset filename, 1.2: gsis_id vs player_id).
    # Fail loudly with what's actually present rather than KeyError deep
    # in the merge logic below.
    season_type_col = "season_type" if "season_type" in df.columns else (
        "game_type" if "game_type" in df.columns else None
    )
    if season_type_col is None or not {"week", "home_team", "away_team"}.issubset(df.columns):
        raise SystemExit(
            f"{path} doesn't have the expected columns (need week, "
            f"home_team, away_team, and season_type or game_type). Columns "
            f"actually present: {sorted(df.columns)}. Update load_schedule() "
            f"to match the real schema."
        )
    df = df[df[season_type_col] == "REG"]
    return df[["week", "home_team", "away_team"]].copy()


# ---------------------------------------------------------------------------
# Step 1: Team -> week-N-opponent map
# ---------------------------------------------------------------------------

def load_real_team_for_week(season: int, week: int):
    """Decision #4 (see module docstring). Returns (week_was_played, team_lookup):
    - week_was_played: False if weekly_stats has no rows for this week at
      all (target week hasn't happened yet -- a live/current run, not an
      error). When False, the caller applies no correction whatsoever.
    - team_lookup: player_id -> real team, ONLY for players who have an
      actual row that week (i.e. actually played). A player_id's absence
      from this lookup, when week_was_played is True, means "this player
      has no real game that week" (bye, inactive, hadn't debuted yet) --
      the caller must NOT fall back to the salary file's team for these,
      since that produces a plausible-looking but wrong matchup (this is
      exactly how the Flacco case was found).
    """
    path = DATA_DIR / f"weekly_stats_{season}.parquet"
    if not path.exists():
        print(
            f"NOTE: {path} not found -- skipping salary-file team-drift "
            f"correction (decision #4). Fine for a live/current-week run; "
            f"if this IS a backtest of a past week, get this file for a "
            f"more accurate matchup/vegas lookup.",
            file=sys.stderr,
        )
        return False, pd.Series(dtype=object)

    df = pd.read_parquet(path)
    season_type_col = "season_type" if "season_type" in df.columns else "game_type"
    wk = df[(df[season_type_col] == "REG") & (df["week"] == week)]
    if wk.empty:
        # Target week hasn't been played yet -- expected for a live run, not
        # an error. No correction applied at all.
        return False, pd.Series(dtype=object)
    return True, wk.drop_duplicates(subset=["player_id"]).set_index("player_id")["team"]


def build_opponent_map(schedule: pd.DataFrame, week: int) -> dict:
    wk = schedule[schedule["week"] == week]
    opp_map = {}
    for row in wk.itertuples():
        opp_map[row.home_team] = row.away_team
        opp_map[row.away_team] = row.home_team
    return opp_map


# ---------------------------------------------------------------------------
# Step 2: vegas_factor -- normalized to league average, same convention as
# matchup_factor (Session 2.2). Filtered to exactly this week's games using
# the opponent map, which resolves the multi-week-mixing issue flagged in
# Session 2.3's log (vegas_implied_totals_{week}.csv contains every
# currently-listed upcoming game, not just one week).
# ---------------------------------------------------------------------------

def build_vegas_factors(vegas: pd.DataFrame, opponent_map: dict) -> pd.DataFrame:
    vegas = vegas.copy()
    vegas["expected_opponent"] = vegas["team"].map(opponent_map)
    this_week = vegas[vegas["opponent"] == vegas["expected_opponent"]].copy()
    this_week = this_week.drop_duplicates(subset=["team"])

    if this_week.empty:
        print(
            "WARNING: no vegas_implied_totals rows matched this week's "
            "schedule via (team, opponent) pairing -- every player will "
            "get a neutral vegas_factor of 1.0. Check that "
            "vegas_odds.py has been re-run close enough to this week for "
            "lines to be posted.",
            file=sys.stderr,
        )
        return pd.DataFrame(columns=["team", "vegas_factor", "opponent", "implied_total", "over_under"])

    league_avg = this_week["implied_total"].mean()
    this_week["vegas_factor"] = this_week["implied_total"] / league_avg
    # Session 3.3 addendum (decision #6): keep opponent/implied_total/
    # over_under alongside vegas_factor so build_final_projections() can
    # pass them straight through to the output CSV without a second lookup.
    keep_cols = ["team", "vegas_factor", "opponent", "implied_total"]
    if "over_under" in this_week.columns:
        keep_cols.append("over_under")
    return this_week[keep_cols]


# ---------------------------------------------------------------------------
# Step 2b: DST/DEF projections (Session 3.1, decision #5 -- see module
# docstring). Deliberately separate from the skill-position path above: no
# baseline_recent_form/matchup_factor inputs exist for defenses at all, and
# this needs the OPPONENT's implied_total (not the defense's own team's),
# which is the opposite convention from build_vegas_factors() above.
# ---------------------------------------------------------------------------

def build_dst_projections(salaries: pd.DataFrame, vegas: pd.DataFrame, site: str) -> pd.DataFrame:
    defense_values = SITE_CONFIGS[site]["defense_position_values"]
    site_id_col = SITE_CONFIGS[site]["site_id_col"]
    dst = salaries[salaries["position_upper"].isin(defense_values)].copy()
    dst = dst[dst["player_id"].notna()]
    dst = dst.rename(columns={
        "normalized_team": "team",
        "position_upper": "position",
        "name": "player_name",
        site_id_col: "site_player_id",
    })[["player_id", "player_name", "position", "team", "salary", "site_player_id", "AvgPointsPerGame"]]

    # Decision #5a: AvgPointsPerGame is the only real historical scoring
    # signal available for a defense -- used for both season_avg and
    # recent_form (no real week-by-week split exists to tell them apart).
    dst["season_avg"] = dst["AvgPointsPerGame"].fillna(0.0)
    dst["recent_form"] = dst["season_avg"]
    dst = dst.drop(columns=["AvgPointsPerGame"])

    # Decision #5: no defensive matchup_factor exists anywhere upstream --
    # held flat neutral, flagged as a known gap rather than fabricated.
    dst["matchup_factor"] = 1.0

    # Decision #5b: vegas_factor uses the OPPONENT's implied_total (how
    # well the offense the defense is FACING is expected to do), inverted
    # relative to league average -- opposite of build_vegas_factors()'s
    # convention for skill positions, which uses the player's own team.
    implied_by_team = vegas.drop_duplicates(subset=["team"]).set_index("team")["implied_total"]
    league_avg = vegas["implied_total"].mean()
    opponent_by_team = vegas.drop_duplicates(subset=["team"]).set_index("team")["opponent"]
    over_under_by_team = None
    if "over_under" in vegas.columns:
        over_under_by_team = vegas.drop_duplicates(subset=["team"]).set_index("team")["over_under"]

    has_game = dst["team"].isin(opponent_by_team.index)
    n_bye = (~has_game).sum()

    # Session 3.3 addendum (decision #6): opponent/implied_total/over_under
    # for defenses too -- a defense's OWN implied_total (not the opponent's)
    # is what a mini-stack (e.g. RB+DST same team) would care about.
    dst["opponent"] = dst["team"].map(opponent_by_team).where(has_game)
    dst["implied_total"] = dst["team"].map(implied_by_team).where(has_game)
    if over_under_by_team is not None:
        dst["over_under"] = dst["team"].map(over_under_by_team).where(has_game)
    else:
        dst["over_under"] = None

    opp_implied = dst["team"].map(opponent_by_team).map(implied_by_team)
    dst["vegas_factor"] = league_avg / opp_implied
    dst["vegas_factor"] = dst["vegas_factor"].where(has_game, 1.0)  # neutral, informational only

    dst["final_projection"] = (dst["season_avg"] * dst["vegas_factor"]).clip(lower=0.0)
    # Decision #5 bye handling, same philosophy as decision #4b: no real
    # game that week (bye) -> confirmed zero real fantasy points, not a
    # neutrally-factored guess.
    dst.loc[~has_game, "final_projection"] = 0.0

    print(f"{n_bye} defense(s) had no game this week (bye) -- final_projection forced to 0.0 "
          f"(decision #5, same philosophy as decision #4b).")

    # Same sentinel-fill treatment as the skill-position path (decision #6) --
    # keeps "no nulls in any column" true even for bye-week defenses.
    dst["opponent"] = dst["opponent"].fillna("BYE_OR_UNKNOWN")
    dst["implied_total"] = dst["implied_total"].fillna(0.0)
    dst["over_under"] = dst["over_under"].fillna(0.0)

    return dst[[
        "player_id", "player_name", "position", "team", "salary",
        "season_avg", "recent_form", "matchup_factor", "vegas_factor",
        "final_projection", "opponent", "implied_total", "over_under",
    ]]


# ---------------------------------------------------------------------------
# Step 3: Build the blended output
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Step 3: Ownership estimates (Session 7.3, decision #7)
# ---------------------------------------------------------------------------

def add_ownership_columns(df: pd.DataFrame, site: str) -> pd.DataFrame:
    """Bakes ownership_heuristic.py's chalk_score/estimated_ownership_pct
    into this file's own output (see module docstring, decision #7).
    Reuses its compute functions unchanged, run on THIS exact DataFrame
    (skill players + DST/DEF, already merged) -- not a re-read from disk."""
    scored = compute_chalk_scores(df, site)
    scored = compute_estimated_ownership(scored, site)
    ownership_cols = scored[["player_id", "chalk_score", "estimated_ownership_pct"]]
    merged = df.merge(ownership_cols, on="player_id", how="left")
    n_missing = merged["chalk_score"].isna().sum()
    if n_missing:
        raise SystemExit(
            f"add_ownership_columns: {n_missing} player(s) got no chalk_score/"
            f"estimated_ownership_pct after merge -- should be impossible since "
            f"ownership_heuristic.py computed scores from this exact same "
            f"DataFrame. Likely a player_id dtype/duplicate mismatch -- "
            f"investigate before shipping."
        )
    return merged


def build_final_projections(site: str, season: int, week: int, slate_id: str) -> pd.DataFrame:
    baseline = load_baseline_recent_form(site, season, week)
    matchup = load_matchup_factors(site, season, week)
    vegas = load_vegas_implied_totals(week)
    salaries = load_salaries(site, slate_id)
    schedule = load_schedule(season)

    opponent_map = build_opponent_map(schedule, week)
    vegas_factors = build_vegas_factors(vegas, opponent_map)

    # Player pool = salary file, restricted to real players at a projected
    # position (excludes DST/D/DEF -- see module docstring).
    players = salaries[salaries["position_upper"].isin(POSITIONS)].copy()
    players = players[players["player_id"].notna()]
    players = players.rename(columns={
        "normalized_team": "team",
        "position_upper": "position",
        "salary": "salary",
    })
    site_id_col = SITE_CONFIGS[site]["site_id_col"]
    players = players[["player_id", "name", "position", "team", "salary", site_id_col]].rename(
        columns={"name": "player_name", site_id_col: "site_player_id"}
    )

    # Decision #4 (see module docstring): auto-correct team drift when the
    # target week has already been played. No-op for a live/current run.
    week_was_played, real_team_this_week = load_real_team_for_week(season, week)
    players["no_real_game_this_week"] = False
    if week_was_played:
        corrected = players["player_id"].map(real_team_this_week)
        played_mask = corrected.notna()
        n_corrected = (played_mask & (corrected != players["team"])).sum()
        players.loc[played_mask, "team"] = corrected[played_mask]
        # Sub-case b: no real row this week at all (bye, inactive, hadn't
        # debuted) -- do NOT trust the salary file's team for these; flag
        # them so matchup_factor/vegas_factor fall back to neutral 1.0
        # below instead of a plausible-but-wrong specific value.
        players["no_real_game_this_week"] = ~played_mask
        n_no_game = players["no_real_game_this_week"].sum()
        print(f"{n_corrected} player(s) had their team corrected from the salary file's "
              f"snapshot to their real week-{week} team (decision #4a, in-season trade).")
        print(f"{n_no_game} player(s) had no real game at all in week {week} (bye/inactive/"
              f"not yet debuted) -- matchup_factor/vegas_factor forced to neutral 1.0 rather "
              f"than trusting the salary file's team (decision #4b).")

    df = players.merge(baseline[["player_id", "season_avg", "recent_form", "games_played"]],
                        on="player_id", how="left")

    # Decision #3 (rookie/no-history gap Session 2.1 explicitly deferred here):
    # no games played yet before this week -> 0.0, not dropped.
    n_no_history = df["season_avg"].isna().sum()
    df["season_avg"] = df["season_avg"].fillna(0.0)
    df["recent_form"] = df["recent_form"].fillna(0.0)
    df["games_played"] = df["games_played"].fillna(0).astype(int)

    df["opponent"] = df["team"].map(opponent_map)
    df.loc[df["no_real_game_this_week"], "opponent"] = None

    matchup_lookup = matchup.set_index(["team", "position"])["matchup_factor"]
    df["matchup_factor"] = df.apply(
        lambda r: matchup_lookup.get((r["opponent"], r["position"])), axis=1
    )
    n_no_matchup = df["matchup_factor"].isna().sum()
    df["matchup_factor"] = df["matchup_factor"].fillna(1.0)  # user-confirmed neutral fill

    # Session 3.3 addendum (decision #6): merge in implied_total/over_under
    # alongside vegas_factor -- same merge key (team), no extra lookup.
    merge_cols = ["team", "vegas_factor", "implied_total"]
    if "over_under" in vegas_factors.columns:
        merge_cols.append("over_under")
    df = df.merge(vegas_factors[merge_cols], on="team", how="left")
    df.loc[df["no_real_game_this_week"], "vegas_factor"] = None  # stale salary team, not a real game
    df.loc[df["no_real_game_this_week"], "implied_total"] = None
    if "over_under" in df.columns:
        df.loc[df["no_real_game_this_week"], "over_under"] = None
    n_no_vegas = df["vegas_factor"].isna().sum()
    df["vegas_factor"] = df["vegas_factor"].fillna(1.0)  # user-confirmed neutral fill

    df["final_projection"] = (
        (BASELINE_WEIGHT * df["season_avg"] + RECENT_FORM_WEIGHT * df["recent_form"])
        * df["matchup_factor"]
        * df["vegas_factor"]
    ).clip(lower=0.0)  # roadmap validation requires no negative projections

    # Decision #4b, corrected: neutral matchup/vegas factors alone weren't
    # enough -- that still left a real, positive final_projection for a
    # player we know via HINDSIGHT did not play that week at all (bye,
    # injury, inactive). This is different from the live-run case (target
    # week hasn't happened yet), where an uncertain player correctly still
    # gets a normal non-zero projection -- we just don't know their status
    # yet, and zeroing every uncertain player would break live usefulness
    # (that's what Session 5.1's injury-status work is for). But for an
    # already-played week, "no real row" is a confirmed fact, not
    # uncertainty: the player scored zero real fantasy points, so
    # final_projection should say zero, not a neutrally-factored guess.
    df.loc[df["no_real_game_this_week"], "final_projection"] = 0.0

    print(f"{n_no_history} player(s) had no season_avg/recent_form yet (0.0 fallback, "
          f"expected for rookies/midseason signings).")
    print(f"{n_no_matchup} player(s) had no matchup_factor found for (opponent, position) "
          f"(1.0 neutral fallback -- check opponent map / bye weeks).")
    print(f"{n_no_vegas} player(s) had no vegas_factor found for their team "
          f"(1.0 neutral fallback -- check line posting / bye weeks).")

    # Session 3.3 addendum (decision #6, continued): fill remaining nulls in
    # the three new columns with sentinels rather than leaving real NaN --
    # keeps the roadmap's existing "no nulls in any column" invariant intact
    # (previously true by construction; adding nullable columns would
    # otherwise silently break it). "BYE_OR_UNKNOWN" / 0.0 signal "this
    # player's week-N context isn't trustworthy" -- consistent with
    # final_projection already being forced to 0.0 for the same rows
    # (decision #4b), so optimizer.py's stacking logic in Session 3.3 will
    # never pick these players anyway (0-projection players are never
    # selected -- decision #4 in optimizer.py's own docstring).
    if "over_under" not in df.columns:
        df["over_under"] = None
    df["opponent"] = df["opponent"].fillna("BYE_OR_UNKNOWN")
    df["implied_total"] = df["implied_total"].fillna(0.0)
    df["over_under"] = df["over_under"].fillna(0.0)

    out_cols = [
        "player_id", "player_name", "position", "team", "salary", "site_player_id",
        "season_avg", "recent_form", "matchup_factor", "vegas_factor",
        "final_projection", "opponent", "implied_total", "over_under",
    ]
    skill_out = df[out_cols]

    # Decision #5 (see module docstring): add DST/DEF rows, needed for the
    # optimizer to fill a legal 9-slot roster for either site. Uses the raw
    # `vegas` frame directly (not `vegas_factors`, which is already
    # restricted/renamed for the skill-position convention above).
    dst_out = build_dst_projections(salaries, vegas, site)

    out = pd.concat([skill_out, dst_out], ignore_index=True)

    # Session 7.3, decision #7: chalk_score/estimated_ownership_pct baked
    # in here -- must run AFTER the skill+DST concat above (ownership needs
    # the full pool, including defenses, to compute real roster-slot
    # budgets/percentiles) but BEFORE the final sort below (a merge can
    # reorder rows, and the ascending-by-final_projection sort is this
    # function's real, validated output order).
    out = add_ownership_columns(out, site)

    out = out.sort_values("final_projection", ascending=False).reset_index(drop=True)

    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", choices=["dk", "fd"], required=True)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--slate-id", required=True, help="e.g. classic_wk10, matches ingest_salaries.py's --slate-id")
    args = parser.parse_args()

    result = build_final_projections(args.site, args.season, args.week, args.slate_id)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"final_projections_{args.site}_{args.week}.csv"
    result.to_csv(out_path, index=False)

    n_null = result.isna().any(axis=1).sum()
    n_neg = (result["final_projection"] < 0).sum()
    n_chalk_out_of_range = ((result["chalk_score"] < 0) | (result["chalk_score"] > 100)).sum()
    n_own_out_of_range = ((result["estimated_ownership_pct"] < 0) | (result["estimated_ownership_pct"] > 100)).sum()
    print(f"Wrote {len(result)} players to {out_path}")
    print(f"  Nulls in any column: {n_null} (should be 0)")
    print(f"  Negative final_projection: {n_neg} (should be 0)")
    print(f"  chalk_score out of [0,100] range: {n_chalk_out_of_range} (should be 0)")
    print(f"  estimated_ownership_pct out of [0,100] range: {n_own_out_of_range} (should be 0)")
