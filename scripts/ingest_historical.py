"""
ingest_historical.py
=====================

Session 1.2 — Historical Data Ingestion.

Pulls weekly player stats, schedules, and weekly rosters for the given
season(s) and writes them to local parquet files under /data.

NOTE (see SESSION_LOG.md, Session 1.1): the roadmap card for this session
originally specified pulling this data via `nfl_data_py`. That package is
deprecated and 404s on 2025+ season data, so this script instead pulls via
`scripts/nflverse_fetch.py`, which reads nflverse's parquet releases
directly. Functionally equivalent, no API key required.

Schema note: the resulting weekly-stats dataframe uses `team` (not
`recent_team`) as the team column, has 145 columns, and already includes an
`opponent_team` column — no need to derive it from the schedule separately.

Usage:
  python3 scripts/ingest_historical.py --season 2025
  python3 scripts/ingest_historical.py --season 2025 2024   # multiple seasons
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from nflverse_fetch import (import_weekly_data, import_schedules,
                            import_weekly_rosters, import_team_stats)

DATA_DIR = Path(__file__).parent.parent / "data"

# Natural key used to de-duplicate weekly stats rows. One row should exist
# per player, per game, per season/season-type.
WEEKLY_STATS_KEY = ["player_id", "season", "week", "season_type", "game_id"]
# NOTE: the weekly_rosters release does not have a "player_id" column — its
# player identifier column is named "gsis_id" (same ID scheme/values as
# weekly_stats' "player_id", just a different column name). Verified against
# the live release on 2026-07-21 — see SESSION_LOG.md, Session 1.2.
ROSTER_KEY = ["gsis_id", "season", "week"]
# Session 10.4 -- one row per team per game.
TEAM_STATS_KEY = ["team", "season", "week", "season_type", "game_id"]


def ingest_weekly_stats(seasons: list[int]) -> list[Path]:
    """Session 13.5-pause Bug Fix: pulls each season INDEPENDENTLY now, not
    as one combined `import_weekly_data(seasons)` batch. nflverse only
    publishes stats_player_week_{season}.parquet once that season's games
    have actually been played -- a season requested before its own kickoff
    (e.g. --season 2025 2026 run before any 2026 game has happened) 404s.
    The old combined-batch call meant that one missing season aborted the
    ENTIRE call, silently skipping 2025's refresh too even though 2025 was
    perfectly available -- confirmed real, not hypothetical, this session.
    A 404 for a specific season is expected/recoverable (that season just
    hasn't started) and is reported as a clear note, not a crash; any OTHER
    error still raises, since silently swallowing a genuine problem (e.g. a
    real nflverse release rename) would be the "silent fallback" failure
    mode this project explicitly avoids elsewhere.
    """
    paths = []
    for season in seasons:
        try:
            df = import_weekly_data([season])
        except RuntimeError as e:
            if "404" in str(e):
                print(f"  NOTE: no weekly stats available yet for season {season} "
                      f"(season hasn't started / no games played yet) -- skipping. "
                      f"Re-run once games begin.")
                continue
            raise
        before = len(df)
        df = df.drop_duplicates(subset=WEEKLY_STATS_KEY)
        dropped = before - len(df)
        if dropped:
            print(f"  Dropped {dropped} duplicate rows on key {WEEKLY_STATS_KEY}")

        out_path = DATA_DIR / f"weekly_stats_{season}.parquet"
        df.to_parquet(out_path, engine="pyarrow", index=False)
        paths.append(out_path)
        print(f"  Wrote {out_path} ({len(df)} rows, {len(df.columns)} cols)")
    return paths


def ingest_schedules(seasons: list[int]) -> Path:
    df = import_schedules(seasons)
    before = len(df)
    df = df.drop_duplicates(subset=["game_id"])
    dropped = before - len(df)
    if dropped:
        print(f"  Dropped {dropped} duplicate rows on key ['game_id']")

    out_path = DATA_DIR / f"schedules_{'_'.join(map(str, seasons))}.parquet"
    df.to_parquet(out_path, engine="pyarrow", index=False)
    print(f"  Wrote {out_path} ({len(df)} rows, {len(df.columns)} cols)")
    return out_path


def ingest_weekly_rosters(seasons: list[int]) -> Path:
    df = import_weekly_rosters(seasons)
    before = len(df)
    df = df.drop_duplicates(subset=ROSTER_KEY)
    dropped = before - len(df)
    if dropped:
        print(f"  Dropped {dropped} duplicate rows on key {ROSTER_KEY}")

    paths = []
    for season in seasons:
        season_df = df[df["season"] == season]
        out_path = DATA_DIR / f"weekly_rosters_{season}.parquet"
        season_df.to_parquet(out_path, engine="pyarrow", index=False)
        paths.append(out_path)
        print(f"  Wrote {out_path} ({len(season_df)} rows, {len(season_df.columns)} cols)")
    return paths


def ingest_team_stats(seasons: list[int]) -> list:
    """Session 10.4 -- team-week stats, needed by the DST model.

    Session 13.5-pause Bug Fix: same per-season independence fix as
    ingest_weekly_stats() above, same reasoning -- stats_team_week_
    {season}.parquet also 404s until that season's games have actually
    been played.
    """
    paths = []
    for season in seasons:
        try:
            df = import_team_stats([season])
        except RuntimeError as e:
            if "404" in str(e):
                print(f"  NOTE: no team stats available yet for season {season} "
                      f"(season hasn't started / no games played yet) -- skipping. "
                      f"Re-run once games begin.")
                continue
            raise
        before = len(df)
        df = df.drop_duplicates(subset=TEAM_STATS_KEY)
        dropped = before - len(df)
        if dropped:
            print(f"  Dropped {dropped} duplicate rows on key {TEAM_STATS_KEY}")

        out_path = DATA_DIR / f"team_stats_{season}.parquet"
        df.to_parquet(out_path, engine="pyarrow", index=False)
        paths.append(out_path)
        print(f"  Wrote {out_path} ({len(df)} rows, {len(df.columns)} cols)")
    return paths


def ingest_games(seasons: list[int]) -> Path:
    """Session 10.4 -- the schedules release under the plain name
    `games.parquet`, which is what the DST model and the backtest harness
    both look for. The existing ingest_schedules() writes a season-suffixed
    filename; this writes the unsuffixed full table alongside it rather than
    changing that convention, since several scripts already key on it."""
    df = import_schedules(None).drop_duplicates(subset=["game_id"])
    out_path = DATA_DIR / "games.parquet"
    df.to_parquet(out_path, engine="pyarrow", index=False)
    print(f"  Wrote {out_path} ({len(df)} rows, {len(df.columns)} cols)")
    return out_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, nargs="+", required=True,
                         help="One or more seasons to pull, e.g. --season 2025 2024")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Ingesting weekly stats for seasons {args.season}...")
    ingest_weekly_stats(args.season)

    print(f"\nIngesting schedules for seasons {args.season}...")
    ingest_schedules(args.season)

    print(f"\nIngesting weekly rosters for seasons {args.season}...")
    ingest_weekly_rosters(args.season)

    # Session 10.4 -- both needed by the DST model (dst_model.py) and by
    # fit_dst_model.py.
    print(f"\nIngesting team stats for seasons {args.season}...")
    ingest_team_stats(args.season)

    print("\nIngesting the full games table (games.parquet)...")
    ingest_games(args.season)

    print("\nDone.")


if __name__ == "__main__":
    main()
