"""
projections_baseline.py
========================

Session 2.1 — Season Baseline + Recent Form.

For a given site (DK/FD), season, and target week, computes two per-player
signals from nflverse weekly stats:
  1. season_avg   - mean fantasy points/game over all REG-season games BEFORE
                     the target week
  2. recent_form  - recency-weighted average of the last 5 such games
                     (weights from RECENCY_WEIGHTS, renormalized if <5 games)

Site-aware scoring:
  - DK is full PPR  -> use nflverse's precomputed `fantasy_points_ppr` as-is.
  - FD is half PPR  -> nflverse has no half-PPR column, so it's derived as
                        `fantasy_points + 0.5 * receptions` (equivalently
                        `fantasy_points_ppr - 0.5 * receptions`; both are
                        exact, verified against this season's data to
                        float-precision noise only).

Two design decisions not spelled out on the roadmap card, made explicitly
here (see SESSION_LOG for the fuller reasoning):

  - REG season only. POST weeks (19-22 in nflverse's numbering) are excluded
    from both season_avg and recent_form. Mixing playoff performance into a
    regular-season baseline would pull in different opponents/roster context
    than the regular season slate this projection is for.

  - Lookahead-bias guard: baseline and recent-form for week N only use weeks
    1..N-1. The old blended_projections.py computed averages over the WHOLE
    season file regardless of the target week, which silently leaks the
    outcome being projected into its own inputs. --week is not just an
    output-filename label here; it's a hard cutoff on the input data.

Usage:
  python3 projections_baseline.py --site dk --season 2025 --week 10
  python3 projections_baseline.py --site fd --season 2025 --week 10
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUT_DIR = REPO_ROOT / "output"

RECENCY_WEIGHTS = [0.35, 0.25, 0.20, 0.12, 0.08]  # most recent game first, last 5 games
POSITIONS = ["QB", "RB", "WR", "TE"]

SITE_SCORING = {
    "dk": "full_ppr",
    "fd": "half_ppr",
}


# ---------------------------------------------------------------------------
# Step 0: Load + filter
# ---------------------------------------------------------------------------

def load_weekly_data(season: int, week: int) -> pd.DataFrame:
    """Load weekly stats for the season, restricted to REG-season games
    strictly before the target week (lookahead-bias guard)."""
    path = DATA_DIR / f"weekly_stats_{season}.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run scripts/ingest_historical.py --season {season} first "
            f"(Session 1.2)."
        )
    df = pd.read_parquet(path, engine="pyarrow")
    df = df[df["position"].isin(POSITIONS)]
    df = df[df["season_type"] == "REG"]
    df = df[df["week"] < week]
    return df.copy()


# ---------------------------------------------------------------------------
# Step 1: Site-aware fantasy points
# ---------------------------------------------------------------------------

def compute_fantasy_points(df: pd.DataFrame, site: str) -> pd.Series:
    """Per-row fantasy points for the given site's scoring rule.

    DK = full PPR -> nflverse's fantasy_points_ppr, used directly.
    FD = half PPR -> not a native nflverse column; derived as
         fantasy_points + 0.5 * receptions.
    """
    scoring = SITE_SCORING[site]
    if scoring == "full_ppr":
        return df["fantasy_points_ppr"]
    if scoring == "half_ppr":
        return df["fantasy_points"] + 0.5 * df["receptions"]
    raise ValueError(f"Unknown scoring rule: {scoring}")


# ---------------------------------------------------------------------------
# Step 2: Season baseline (mean fantasy points/game, weeks before target week)
# ---------------------------------------------------------------------------

def season_baseline(weekly: pd.DataFrame) -> pd.DataFrame:
    """Season-to-date average, across ALL of a player's REG games before the
    target week -- regardless of which team they were on for each game.

    Bug fix #1 (found during Session 2.4's first real validation run):
    originally grouped by player_id+player_name+position+TEAM, which
    silently split any player who changed teams mid-season (trade, waiver
    claim, re-signing) into multiple rows with different season_avg values
    under the same player_id -- e.g. Joe Flacco (Browns -> Bengals in 2025)
    produced two rows, both under the same player_id. 7 of 532 players were
    affected. This output has never had a team column, so grouping by team
    here was never right in the first place.

    Bug fix #2 (found immediately after fix #1, same real-data re-run):
    dropping `team` from the groupby wasn't enough -- `player_name` in
    nflverse's raw weekly data is ALSO occasionally inconsistent for the
    same player_id across different weeks (e.g. player_id 00-0039394 shows
    as "Cas.Washington" in some weeks and "C.Washington" in others, likely
    a same-team-same-surname disambiguation quirk upstream). Grouping by
    player_name reproduced the identical duplicate-row bug through a
    different key. 2 more players were affected (Washington, A./Ar. Smith).
    Fixed by grouping on `player_id` alone -- the only field guaranteed
    stable per player -- and attaching each player's MOST RECENT
    player_name/position (by week) after the fact, same "most recent"
    pattern already used in ingest_salaries.py's build_player_reference()
    for exactly this kind of week-to-week inconsistency.
    """
    baseline = (
        weekly.groupby("player_id")
        .agg(season_avg=("fantasy_points", "mean"), games_played=("fantasy_points", "count"))
        .reset_index()
    )
    most_recent_identity = (
        weekly.sort_values("week")
        .groupby("player_id")[["player_name", "position"]]
        .last()
        .reset_index()
    )
    return baseline.merge(most_recent_identity, on="player_id", how="left")


# ---------------------------------------------------------------------------
# Step 3: Recent form (recency-weighted average of last 5 games)
# ---------------------------------------------------------------------------

def recent_form(weekly: pd.DataFrame) -> pd.DataFrame:
    weekly = weekly.sort_values(["player_id", "week"])
    results = []
    for pid, group in weekly.groupby("player_id"):
        last_n = group.tail(len(RECENCY_WEIGHTS)).sort_values("week", ascending=False)
        if last_n.empty:
            continue
        weights = np.array(RECENCY_WEIGHTS[: len(last_n)])
        weights = weights / weights.sum()  # renormalize if fewer than 5 games
        weighted_avg = np.dot(last_n["fantasy_points"].values, weights)
        results.append({"player_id": pid, "recent_form": weighted_avg})
    return pd.DataFrame(results, columns=["player_id", "recent_form"])


# ---------------------------------------------------------------------------
# Step 4: Build output
# ---------------------------------------------------------------------------

def build_baseline_recent_form(site: str, season: int, week: int) -> pd.DataFrame:
    weekly = load_weekly_data(season, week)
    weekly["fantasy_points"] = compute_fantasy_points(weekly, site)

    baseline = season_baseline(weekly)
    recent = recent_form(weekly)

    df = baseline.merge(recent, on="player_id", how="left")
    # A player with 0 games played before this week (rookie debut, first
    # career game, etc.) has no history at all -- season_avg/recent_form
    # are legitimately NaN, not a bug. Leave them as NaN rather than
    # silently filling with 0, so downstream steps can decide how to
    # handle a totally unknown player explicitly.
    df["recent_form"] = df["recent_form"].fillna(df["season_avg"])

    return df[["player_id", "player_name", "position", "season_avg", "recent_form", "games_played"]] \
        .sort_values("season_avg", ascending=False, na_position="last") \
        .reset_index(drop=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", choices=["dk", "fd"], required=True)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    args = parser.parse_args()

    result = build_baseline_recent_form(args.site, args.season, args.week)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"baseline_recent_form_{args.site}_{args.season}_{args.week}.csv"
    result.to_csv(out_path, index=False)

    print(f"Wrote {len(result)} players to {out_path}")
    print(f"({result['games_played'].eq(0).sum() if 'games_played' in result else 0} players "
          f"had 0 games played before week {args.week} -- NaN baseline, expected for early weeks)")
