"""
nflverse_fetch.py
==================

Minimal, dependency-light replacement for nfl_data_py's data-pull functions.

Why this exists (see SESSION_LOG.md, Session 1.1):
  nfl_data_py is deprecated upstream (nflverse now recommends nflreadpy) and,
  more importantly, its import_weekly_data() / import_schedules() functions
  point at a GitHub release path ("player_stats") that nflverse retired on
  2025-08-01 in favor of a renamed release ("stats_player"). That means
  nfl_data_py 404s on any 2025+ season data and will not be fixed upstream.

  Rather than depend on nfl_data_py (dead) or nflreadpy (new, Polars-based,
  would require converting this whole pandas pipeline), we read nflverse's
  published parquet files directly. nflverse-data releases are stable,
  public, and require no API key.

If nflverse renames a release again in the future, this is the one file
that needs to change — update the URL_TEMPLATES dict below.
"""

import pandas as pd

BASE_URL = "https://github.com/nflverse/nflverse-data/releases/download"

URL_TEMPLATES = {
    # weekly player stats, one row per player per game
    "weekly_stats": f"{BASE_URL}/stats_player/stats_player_week_{{season}}.parquet",
    # season schedule / results, one row per game
    # NOTE: the release tag is "schedules" but the asset file itself is
    # named "games.parquet", not "schedules.parquet" (verified against the
    # live release on 2026-07-21 — see SESSION_LOG.md, Session 1.2).
    "schedules": f"{BASE_URL}/schedules/games.parquet",
    # weekly rosters (team, position, status per player per week)
    "weekly_rosters": f"{BASE_URL}/weekly_rosters/roster_weekly_{{season}}.parquet",
    # TEAM-level weekly stats, one row per team per game (Session 10.4).
    # Carries the defensive counting stats (def_sacks, def_interceptions,
    # fumble_recovery_opp, def_safeties, def_tds), the blocked-kick columns
    # (fg_blocked / pat_blocked / pt_blocked) and per-team offensive EPA --
    # everything the DST model needs. ~126 KB per season, which is why
    # Session 10.4 uses it instead of the play-by-play release: pbp is ~20 MB
    # per season and the only thing it was wanted for was EPA, which is here.
    "team_stats": f"{BASE_URL}/stats_team/stats_team_week_{{season}}.parquet",
}


def _read_parquet(url: str) -> pd.DataFrame:
    try:
        return pd.read_parquet(url, engine="pyarrow")
    except Exception as e:
        raise RuntimeError(
            f"Failed to fetch nflverse data from {url}. "
            f"If this is a 404, nflverse may have renamed/moved the release — "
            f"check https://github.com/nflverse/nflverse-data/releases and "
            f"update URL_TEMPLATES in this file. Original error: {e}"
        ) from e


def import_weekly_data(years: list[int]) -> pd.DataFrame:
    """Pull weekly player stats for the given seasons.

    Equivalent in purpose to nfl_data_py.import_weekly_data(years), but reads
    the current ("stats_player") nflverse release directly. Note the schema
    differs slightly from the old nfl_data_py output — notably the team
    column is named 'team', not 'recent_team'.
    """
    frames = [_read_parquet(URL_TEMPLATES["weekly_stats"].format(season=y)) for y in years]
    return pd.concat(frames, ignore_index=True)


def import_schedules(years: list[int] | None = None) -> pd.DataFrame:
    """Pull the full nflverse schedule table, optionally filtered to given seasons."""
    df = _read_parquet(URL_TEMPLATES["schedules"])
    if years:
        df = df[df["season"].isin(years)]
    return df


def import_team_stats(years: list[int]) -> pd.DataFrame:
    """Pull weekly TEAM stats for the given seasons (Session 10.4).

    NOTE the team-code wrinkle this release has relative to `schedules`:
    stats_team uses the CURRENT franchise abbreviation retroactively (LV, LAC,
    LA) while games.parquet uses the ERA-CORRECT one (OAK, SD, STL). Anything
    joining the two must normalise first -- see fit_dst_model.py's decision
    #12, which exists because that mismatch silently dropped 13% of a fit
    panel via an inner join.
    """
    frames = [_read_parquet(URL_TEMPLATES["team_stats"].format(season=y)) for y in years]
    return pd.concat(frames, ignore_index=True)


def import_weekly_rosters(years: list[int]) -> pd.DataFrame:
    """Pull weekly roster/status data for the given seasons."""
    frames = [_read_parquet(URL_TEMPLATES["weekly_rosters"].format(season=y)) for y in years]
    return pd.concat(frames, ignore_index=True)


if __name__ == "__main__":
    # Smoke test: pull one prior-season week and print shape + columns.
    df = import_weekly_data([2025])
    print(f"Pulled {len(df)} rows, {len(df.columns)} columns for 2025 weekly stats.")
    print(f"Weeks present: {sorted(df['week'].unique().tolist())}")
    print(f"Season types: {df['season_type'].unique().tolist()}")
