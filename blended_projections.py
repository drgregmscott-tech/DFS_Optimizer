"""
Blended NFL DFS Projection Model
==================================

Combines four signals into a single fantasy point projection per player:
  1. Season baseline  - per-game rate stats x efficiency (nflverse historical data)
  2. Recent form       - recency-weighted average of last N games
  3. Matchup factor    - opponent's fantasy points allowed to that position vs league avg
  4. Vegas factor       - team implied total vs their season-average implied total

Formula:
  final_projection = (0.5 * recent_form + 0.5 * season_baseline)
                      * matchup_factor
                      * vegas_factor

Data sources:
  - nfl_data_py (wraps nflverse GitHub data releases) — free, no API key
  - Vegas lines — plug in any odds API (The Odds API has a free tier: 500 req/month)

Requirements:
  pip install nfl_data_py pandas numpy --break-system-packages

Usage:
  python blended_projections.py --season 2026 --week 3
"""

import argparse
import numpy as np
import pandas as pd

try:
    import nfl_data_py as nfl
except ImportError:
    raise SystemExit("Run: pip install nfl_data_py pandas numpy --break-system-packages")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

RECENCY_WEIGHTS = [0.35, 0.25, 0.20, 0.12, 0.08]  # most recent game first, last 5 games
FANTASY_SCORING = {
    "pass_yds": 0.04, "pass_td": 4, "pass_int": -2,
    "rush_yds": 0.1, "rush_td": 6,
    "rec": 1,  # PPR — set to 0 for standard, 0.5 for half-PPR
    "rec_yds": 0.1, "rec_td": 6,
    "fumble_lost": -2,
}
POSITIONS = ["QB", "RB", "WR", "TE"]


# ---------------------------------------------------------------------------
# Step 1: Pull historical weekly data from nflverse
# ---------------------------------------------------------------------------

def load_weekly_data(season: int) -> pd.DataFrame:
    """Pull weekly player stats for the season so far."""
    df = nfl.import_weekly_data([season])
    df = df[df["position"].isin(POSITIONS)]
    return df


def compute_fantasy_points(df: pd.DataFrame) -> pd.Series:
    """Compute PPR fantasy points per row from raw stats, if not already present."""
    if "fantasy_points_ppr" in df.columns:
        return df["fantasy_points_ppr"]
    pts = (
        df.get("passing_yards", 0) * FANTASY_SCORING["pass_yds"]
        + df.get("passing_tds", 0) * FANTASY_SCORING["pass_td"]
        + df.get("interceptions", 0) * FANTASY_SCORING["pass_int"]
        + df.get("rushing_yards", 0) * FANTASY_SCORING["rush_yds"]
        + df.get("rushing_tds", 0) * FANTASY_SCORING["rush_td"]
        + df.get("receptions", 0) * FANTASY_SCORING["rec"]
        + df.get("receiving_yards", 0) * FANTASY_SCORING["rec_yds"]
        + df.get("receiving_tds", 0) * FANTASY_SCORING["rec_td"]
    )
    return pts


# ---------------------------------------------------------------------------
# Step 2: Season baseline (per-game average, all games so far)
# ---------------------------------------------------------------------------

def season_baseline(weekly: pd.DataFrame) -> pd.DataFrame:
    weekly["fantasy_points"] = compute_fantasy_points(weekly)
    baseline = (
        weekly.groupby(["player_id", "player_name", "position", "recent_team"])
        .agg(season_avg=("fantasy_points", "mean"), games_played=("fantasy_points", "count"))
        .reset_index()
    )
    return baseline


# ---------------------------------------------------------------------------
# Step 3: Recent form (recency-weighted average of last 5 games)
# ---------------------------------------------------------------------------

def recent_form(weekly: pd.DataFrame) -> pd.DataFrame:
    weekly = weekly.sort_values(["player_id", "week"])
    results = []
    for pid, group in weekly.groupby("player_id"):
        last_n = group.tail(len(RECENCY_WEIGHTS)).sort_values("week", ascending=False)
        weights = RECENCY_WEIGHTS[: len(last_n)]
        weights = np.array(weights) / sum(weights)  # renormalize if fewer than 5 games
        weighted_avg = np.dot(last_n["fantasy_points"].values, weights)
        results.append({"player_id": pid, "recent_form": weighted_avg})
    return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# Step 4: Matchup factor (opponent fantasy points allowed to position vs league avg)
# ---------------------------------------------------------------------------

def matchup_factors(weekly: pd.DataFrame) -> pd.DataFrame:
    """
    For each team+position, sum fantasy points allowed to opposing players.
    Then express as a ratio vs league-average points allowed to that position.
    """
    allowed = (
        weekly.groupby(["opponent_team", "position"])["fantasy_points"]
        .mean()
        .reset_index()
        .rename(columns={"opponent_team": "team", "fantasy_points": "pts_allowed_avg"})
    )
    league_avg = allowed.groupby("position")["pts_allowed_avg"].transform("mean")
    allowed["matchup_factor"] = allowed["pts_allowed_avg"] / league_avg
    return allowed[["team", "position", "matchup_factor"]]


# ---------------------------------------------------------------------------
# Step 5: Vegas factor (implied team total vs team's season-average implied total)
# ---------------------------------------------------------------------------

def vegas_factor_placeholder(team: str, current_implied_total: float,
                              season_avg_implied_total: float) -> float:
    """
    Plug in real odds data here (e.g. from The Odds API - free tier available).
    implied_total = over_under/2 +/- spread/2 depending on favorite/underdog.
    For now this is a placeholder function to wire in your odds source.
    """
    if season_avg_implied_total == 0:
        return 1.0
    return current_implied_total / season_avg_implied_total


# ---------------------------------------------------------------------------
# Step 6: Blend everything together
# ---------------------------------------------------------------------------

def build_projections(season: int, current_week_opponents: dict,
                       vegas_totals: dict = None) -> pd.DataFrame:
    """
    current_week_opponents: {player_id: opponent_team} for the upcoming slate
    vegas_totals: {team: implied_total} for the upcoming slate (optional)
    """
    weekly = load_weekly_data(season)
    weekly["fantasy_points"] = compute_fantasy_points(weekly)

    baseline = season_baseline(weekly)
    recent = recent_form(weekly)
    matchups = matchup_factors(weekly)

    df = baseline.merge(recent, on="player_id", how="left")
    df["recent_form"] = df["recent_form"].fillna(df["season_avg"])

    df["opponent_team"] = df["player_id"].map(current_week_opponents)
    df = df.merge(matchups, left_on=["opponent_team", "position"],
                  right_on=["team", "position"], how="left")
    df["matchup_factor"] = df["matchup_factor"].fillna(1.0)

    # Vegas factor — wire in real data via vegas_totals dict {team: implied_total}
    team_season_avg = weekly.groupby("recent_team")["fantasy_points"].transform("mean")
    df["vegas_factor"] = 1.0  # default neutral; overwrite below if vegas_totals provided
    if vegas_totals:
        df["vegas_factor"] = df["recent_team"].map(
            lambda t: vegas_totals.get(t, 1.0) / (vegas_totals.get(t, 1.0) or 1.0)
        )

    df["final_projection"] = (
        (0.5 * df["recent_form"] + 0.5 * df["season_avg"])
        * df["matchup_factor"]
        * df["vegas_factor"]
    )

    return df[["player_id", "player_name", "position", "recent_team", "season_avg",
               "recent_form", "matchup_factor", "vegas_factor", "final_projection"]] \
        .sort_values("final_projection", ascending=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    args = parser.parse_args()

    # NOTE: current_week_opponents needs to come from the upcoming week's schedule.
    # nfl.import_schedules([args.season]) gives you home/away matchups — build the
    # {player_id: opponent_team} dict from each player's team + that week's schedule.
    print("Wire in current_week_opponents (from schedule) and vegas_totals (from odds API),")
    print("then call build_projections(season, current_week_opponents, vegas_totals)")
