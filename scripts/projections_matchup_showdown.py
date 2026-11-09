"""
projections_matchup_showdown.py
================================

Sibling to projections_matchup.py, built for one specific gap that script
doesn't cover: showdown captain/FLEX decisions need finer-grained
defense-vs-position detail than one aggregate "points allowed to WR" number.
A defense that's brutal on a true WR1 but soft on WR2/3 (or vice versa)
reads identically in the aggregate -- exactly the distinction a showdown
build has to make, since CPT/FLEX decisions are inherently about ONE
specific player's role on the slate, not "the WR position" as a group.

Depth-tier/split definitions:
  - WR:  WR1 (the team's #1 target-earner WR that GAME, by that week's own
         targets) vs WR2_3 (every other WR on that team that game).
  - TE:  TE1 (the team's #1 target-earner TE that game) vs TE2_3 (every
         other TE on that team that game).
  - RB:  NOT a depth split (most teams only have one real every-down back
         most weeks, so a RB1/RB2 split would mostly be noise) -- instead
         split by STAT TYPE: rushing points allowed vs receiving points
         allowed to the position. A run-funnel defense and a
         pass-funnel-at-the-RB defense look identical in one blended RB
         number but are very different for a pass-catching-back FLEX/CPT
         call.

Depth tier is determined from each historical game's OWN targets that
game (not a season-long "WR1/WR2" label) -- a team's actual #1 target earner
can rotate week to week (injury, matchup-driven gameplan), and this is
retroactively knowable for every past game in the sample, so there's no
reason to use a coarser season-long proxy.

Everything else here is a direct carry-over from projections_matchup.py,
same reasoning, duplicated rather than imported -- that file keeps its own
self-contained loader rather than importing siblings (see its own
load_weekly_data() docstring), and this script follows the same project
convention:
  - Site-aware scoring (DK full PPR off fantasy_points_ppr; FD half PPR).
    The rush/receiving SPLIT needed here can't come from that single
    pre-combined column (it fuses pass+rush+rec for the player-game), so
    this script reconstructs the two components from their own raw box-
    score fields using the same standard-scoring formula nflverse's own
    fantasy_points is built from (yards*0.1, TD*6, fumble lost*-2, plus
    the site's reception value on the receiving half only) -- this
    reconstruction is ONLY used for the rushing/receiving split; nothing
    about the existing aggregate matchup_factor file is touched.
  - REG season only, same lookahead-bias guard (week N uses weeks 1..N-1
    of that season only).
  - Empirical-Bayes shrinkage toward the neutral 1.0 prior, same
    SHRINKAGE_K_GAMES=4.0 constant as projections_matchup.py (reused
    rather than re-guessed -- these splits have an even smaller per-
    bucket sample than the aggregate version, so if anything this k is
    an UNDER-correction; retune together if/when either gets fit against
    real logged results).

QB and DST are intentionally out of scope -- the per-position depth-tier
question doesn't apply to either (one QB, one DST per team), and the
existing matchup_factors_{site}_{season}_{week}.csv aggregate file already
covers them. cheat_sheet_showdown.py reads both files: this one for
WR/TE/RB tier detail, the existing aggregate file for QB (DST's own
matchup_factor already lives in final_projections, same as the classic
cheat sheet).

Usage:
  python3 scripts/projections_matchup_showdown.py --site dk --season 2026 --week 9
  python3 scripts/projections_matchup_showdown.py --site fd --season 2026 --week 9

Output:
  output/matchup_factors_showdown_{site}_{season}_{week}.csv
  columns: team, position, tier, pts_allowed_avg, games, matchup_factor
  tier values: WR1, WR2_3, TE1, TE2_3, RB_rush, RB_rec
"""

import argparse
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUT_DIR = REPO_ROOT / "output"

SITE_SCORING = {"dk": "full_ppr", "fd": "half_ppr"}

# Same constant, same reasoning, as projections_matchup.py -- see module
# docstring for why it's reused as-is rather than re-guessed for the
# smaller per-tier sample.
SHRINKAGE_K_GAMES = 4.0

RAW_COLUMNS = [
    "player_id", "player_name", "position", "team", "opponent_team", "week",
    "season_type", "targets", "receptions", "receiving_yards", "receiving_tds",
    "receiving_fumbles_lost", "rushing_yards", "rushing_tds", "rushing_fumbles_lost",
]


def load_weekly_data(season: int, week: int) -> pd.DataFrame:
    """Identical lookahead-bias guard + REG-only filter as
    projections_matchup.py's load_weekly_data() -- see that file's
    docstring for the full reasoning (same empty-season-is-normal
    handling for a season with no games played yet)."""
    path = DATA_DIR / f"weekly_stats_{season}.parquet"
    if not path.exists():
        print(
            f"NOTE: {path} not found -- treating season {season} as having "
            f"no games played yet. Every team/tier will get a neutral "
            f"matchup_factor (1.0) once this (empty) result reaches the "
            f"showdown cheat sheet's own fillna fallback."
        )
        return pd.DataFrame(columns=RAW_COLUMNS)
    df = pd.read_parquet(path, engine="pyarrow")
    df = df[df["position"].isin(["WR", "TE", "RB"])]
    df = df[df["season_type"] == "REG"]
    df = df[df["week"] < week]
    return df.copy()


def _tag_wr_te_depth(weekly: pd.DataFrame) -> pd.DataFrame:
    """WR1/TE1 vs WR2_3/TE2_3, ranked by THAT game's own targets within
    the player's own team+game+position -- see module docstring. method
    "first" breaks exact target ties deterministically (by row order)
    rather than producing duplicate rank-1s that would double-count a
    team's "WR1" bucket for a single game."""
    w = weekly[weekly["position"].isin(["WR", "TE"])].copy()
    w["_depth_rank"] = w.groupby(["team", "week", "position"])["targets"] \
        .rank(ascending=False, method="first")
    w["tier"] = w["position"] + w["_depth_rank"].apply(
        lambda r: "1" if r == 1 else "2_3"
    )
    return w


def _site_aware_receiving_points(df: pd.DataFrame, site: str) -> pd.Series:
    """Receiving-only component of standard fantasy scoring, reconstructed
    from raw box-score fields -- see module docstring for why this can't
    just read the pre-combined fantasy_points_ppr column. Reception value
    is the one site-aware piece (DK full PPR = 1.0/rec, FD half PPR =
    0.5/rec); yardage/TD/fumble values are scoring-system standard and not
    site-specific."""
    rec_value = 1.0 if SITE_SCORING[site] == "full_ppr" else 0.5
    return (
        df["receptions"] * rec_value
        + df["receiving_yards"] * 0.1
        + df["receiving_tds"] * 6
        - df["receiving_fumbles_lost"] * 2
    )


def _rushing_points(df: pd.DataFrame) -> pd.Series:
    """Rushing-only component -- not site-aware (PPR only affects
    receptions)."""
    return (
        df["rushing_yards"] * 0.1
        + df["rushing_tds"] * 6
        - df["rushing_fumbles_lost"] * 2
    )


def _shrink(allowed: pd.DataFrame) -> pd.DataFrame:
    """Same shrinkage formula as projections_matchup.py's matchup_factors()
    -- league_avg computed within each tier's own bucket (a WR1 bucket and
    a WR2_3 bucket each get their own league-average baseline, since the
    two are structurally different point levels, not one shared average)."""
    league_avg = allowed.groupby("tier")["pts_allowed_avg"].transform("mean")
    raw_factor = allowed["pts_allowed_avg"] / league_avg
    k = SHRINKAGE_K_GAMES
    allowed["matchup_factor"] = (
        (allowed["games"] * raw_factor + k * 1.0) / (allowed["games"] + k)
    )
    return allowed


def _points_allowed_by_tier(weekly_tagged: pd.DataFrame, points_col: str) -> pd.DataFrame:
    per_team_week = (
        weekly_tagged.groupby(["team", "week", "tier"])[points_col]
        .sum()
        .reset_index()
    )
    grouped = per_team_week.groupby(["team", "tier"])[points_col]
    allowed = (
        grouped.mean().reset_index()
        .rename(columns={points_col: "pts_allowed_avg"})
    )
    allowed["games"] = grouped.size().to_numpy()
    return allowed


def build_matchup_factors_showdown(site: str, season: int, week: int) -> pd.DataFrame:
    weekly = load_weekly_data(season, week)
    weekly = weekly.rename(columns={"opponent_team": "opponent"})
    # Defense-vs-position is keyed by the OPPONENT the offensive player
    # faced that game, same convention as projections_matchup.py (a
    # team's matchup_factor describes what IT allows, computed from what
    # opposing offensive players scored against it).
    weekly = weekly.rename(columns={"team": "offense_team", "opponent": "team"})

    wr_te = _tag_wr_te_depth(weekly)
    wr_te["fantasy_points"] = _site_aware_receiving_points(wr_te, site)
    wr_te_allowed = _points_allowed_by_tier(wr_te, "fantasy_points")

    rb = weekly[weekly["position"] == "RB"].copy()
    rb_rows = []
    if not rb.empty:
        rb_rush = rb.copy()
        rb_rush["tier"] = "RB_rush"
        rb_rush["fantasy_points"] = _rushing_points(rb_rush)
        rb_rec = rb.copy()
        rb_rec["tier"] = "RB_rec"
        rb_rec["fantasy_points"] = _site_aware_receiving_points(rb_rec, site)
        rb_rows = [rb_rush, rb_rec]
    rb_allowed = (
        _points_allowed_by_tier(pd.concat(rb_rows), "fantasy_points")
        if rb_rows else pd.DataFrame(columns=["team", "tier", "pts_allowed_avg", "games"])
    )

    allowed = pd.concat([wr_te_allowed, rb_allowed], ignore_index=True)
    if allowed.empty:
        return pd.DataFrame(columns=["team", "position", "tier", "pts_allowed_avg", "games", "matchup_factor"])

    allowed = _shrink(allowed)
    allowed["position"] = allowed["tier"].map({
        "WR1": "WR", "WR2_3": "WR", "TE1": "TE", "TE2_3": "TE",
        "RB_rush": "RB", "RB_rec": "RB",
    })
    return allowed[["team", "position", "tier", "pts_allowed_avg", "games", "matchup_factor"]] \
        .sort_values(["position", "tier", "matchup_factor"], ascending=[True, True, False]) \
        .reset_index(drop=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", choices=["dk", "fd"], required=True)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    args = parser.parse_args()

    result = build_matchup_factors_showdown(args.site, args.season, args.week)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"matchup_factors_showdown_{args.site}_{args.season}_{args.week}.csv"
    result.to_csv(out_path, index=False)

    print(f"Wrote {len(result)} team/tier rows to {out_path}")
    if not result.empty:
        for tier in result["tier"].unique():
            tier_avg = result.loc[result["tier"] == tier, "matchup_factor"].mean()
            n_teams = (result["tier"] == tier).sum()
            print(f"  {tier}: {n_teams} teams, mean matchup_factor = {tier_avg:.4f}")
