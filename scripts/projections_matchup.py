"""
projections_matchup.py
=======================

Session 2.2 — Matchup Factor.

For a given site (DK/FD), season, and target week, computes a per
team+position "matchup_factor": how many fantasy points that team has
allowed to opposing players at that position so far this season, expressed
as a ratio vs the league-average points allowed to that position.

  matchup_factor > 1.0  -> plays MORE fantasy points to that position than
                            league average (a "good" matchup to attack)
  matchup_factor < 1.0  -> plays FEWER fantasy points to that position than
                            league average (a "tough" matchup)
  matchup_factor == 1.0 -> exactly league average (or a position/team combo
                            with no data yet, see fillna note below)

Site-aware scoring (same rule as Session 2.1's projections_baseline.py):
  - DK is full PPR  -> use nflverse's precomputed `fantasy_points_ppr` as-is.
  - FD is half PPR  -> derived as `fantasy_points + 0.5 * receptions`.

Two design decisions carried over from Session 2.1, applied identically here
(see that session's docstring / SESSION_LOG for the fuller reasoning):

  - REG season only. POST weeks are excluded.
  - Lookahead-bias guard: matchup factors for week N only use weeks 1..N-1.
    A defense's week-N matchup factor must not include week N's own game,
    or it leaks the outcome being projected into its own input.

Usage:
  python3 projections_matchup.py --site dk --season 2025 --week 10
  python3 projections_matchup.py --site fd --season 2025 --week 10
"""

import argparse
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUT_DIR = REPO_ROOT / "output"

POSITIONS = ["QB", "RB", "WR", "TE"]

SITE_SCORING = {
    "dk": "full_ppr",
    "fd": "half_ppr",
}


# ---------------------------------------------------------------------------
# Step 0: Load + filter (identical guard logic to projections_baseline.py)
# ---------------------------------------------------------------------------

def load_weekly_data(season: int, week: int) -> pd.DataFrame:
    """Load weekly stats for the season, restricted to REG-season games
    strictly before the target week (lookahead-bias guard).

    Decision #1 (Session 15.3): a season whose weekly_stats_{season}.
    parquet doesn't exist AT ALL is the normal state before that season's
    first game, not a config mistake -- ingest_historical.py's own
    ingest_weekly_stats() deliberately never writes a placeholder file for
    a season with no games played yet (see that function's docstring).
    This module's own matchup_factor documentation at the top of this file
    already anticipated the correct outcome for this case ("matchup_factor
    == 1.0 -> exactly league average ... or a position/team combo with no
    data yet"): an empty result here, rather than a crash, lets that
    already-intended neutral fallback (build_projections.py's
    matchup_lookup.get(...).fillna(1.0), applied to every player once this
    file is loaded downstream) actually take effect for a genuine week 1,
    instead of stopping the whole matchup-factor build before it starts.

    Same real condition, and same fix shape, as statline_model.py's
    load_history() (decision #19) -- this script keeps its own
    self-contained data loader rather than importing that one, so it needs
    the identical guard applied here separately.
    """
    path = DATA_DIR / f"weekly_stats_{season}.parquet"
    if not path.exists():
        print(
            f"NOTE: {path} not found -- treating season {season} as having "
            f"no games played yet. Every team/position will get a neutral "
            f"matchup_factor once this (empty) result reaches "
            f"build_projections.py's own fillna(1.0) fallback. If season "
            f"{season} should already have real data, double-check: run "
            f"scripts/ingest_historical.py --season {season} to confirm."
        )
        return pd.DataFrame(columns=[
            "opponent_team", "position", "week", "season_type",
            "fantasy_points_ppr", "fantasy_points", "receptions",
        ])
    df = pd.read_parquet(path, engine="pyarrow")
    df = df[df["position"].isin(POSITIONS)]
    df = df[df["season_type"] == "REG"]
    df = df[df["week"] < week]
    return df.copy()


# ---------------------------------------------------------------------------
# Step 1: Site-aware fantasy points (identical to projections_baseline.py)
# ---------------------------------------------------------------------------

def compute_fantasy_points(df: pd.DataFrame, site: str) -> pd.Series:
    """Per-row fantasy points for the given site's scoring rule.

    DK = full PPR -> nflverse's fantasy_points_ppr, used directly.
    FD = half PPR -> derived as fantasy_points + 0.5 * receptions.
    """
    scoring = SITE_SCORING[site]
    if scoring == "full_ppr":
        return df["fantasy_points_ppr"]
    if scoring == "half_ppr":
        return df["fantasy_points"] + 0.5 * df["receptions"]
    raise ValueError(f"Unknown scoring rule: {scoring}")


# ---------------------------------------------------------------------------
# Step 2: Points allowed by team+position, normalized to league average
# ---------------------------------------------------------------------------

def matchup_factors(weekly: pd.DataFrame) -> pd.DataFrame:
    """
    For each opponent_team+position, average fantasy points scored AGAINST
    that team by players at that position (i.e. points that team "allows").
    Express as a ratio vs the league-average points allowed to that
    position across all teams.

    Averaging is done per game, not per player: a team's points-allowed to
    a position in a given week is the SUM of that position's fantasy
    points across all opposing players that week (e.g. all opposing WRs'
    points added together), not any one player's individual total. The
    team+position matchup_factor is then the mean of those weekly sums
    across the team's games so far this season.
    """
    per_team_week = (
        weekly.groupby(["opponent_team", "position", "week"])["fantasy_points"]
        .sum()
        .reset_index()
    )
    allowed = (
        per_team_week.groupby(["opponent_team", "position"])["fantasy_points"]
        .mean()
        .reset_index()
        .rename(columns={"opponent_team": "team", "fantasy_points": "pts_allowed_avg"})
    )
    league_avg = allowed.groupby("position")["pts_allowed_avg"].transform("mean")
    allowed["matchup_factor"] = allowed["pts_allowed_avg"] / league_avg
    return allowed[["team", "position", "matchup_factor"]]


# ---------------------------------------------------------------------------
# Step 3: Build output
# ---------------------------------------------------------------------------

def build_matchup_factors(site: str, season: int, week: int) -> pd.DataFrame:
    weekly = load_weekly_data(season, week)
    weekly["fantasy_points"] = compute_fantasy_points(weekly, site)

    result = matchup_factors(weekly)

    return result.sort_values(["position", "matchup_factor"], ascending=[True, False]) \
        .reset_index(drop=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", choices=["dk", "fd"], required=True)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    args = parser.parse_args()

    result = build_matchup_factors(args.site, args.season, args.week)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"matchup_factors_{args.site}_{args.season}_{args.week}.csv"
    result.to_csv(out_path, index=False)

    print(f"Wrote {len(result)} team/position rows to {out_path}")
    for pos in POSITIONS:
        pos_avg = result.loc[result["position"] == pos, "matchup_factor"].mean()
        print(f"  {pos}: league-average-weighted mean matchup_factor = {pos_avg:.4f} "
              f"(should be ~1.0 -- unweighted mean of a ratio-to-mean isn't exactly 1.0 "
              f"unless every team has the same game count; see validation notes)")
