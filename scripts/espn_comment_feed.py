"""
espn_comment_feed.py
=====================

Collection-only capture of ESPN's league-wide injuries/news feed's free-text
`shortComment`/`longComment` fields -- WK7_POSTMORTEM_ACTION_ITEMS.md's "ESPN
injury-feed comment text as a role/usage signal" item.

Scoped 2026-10-28 (discussed with owner before building): the comment text
does NOT live on the per-team roster endpoint `status_check.py` already
pulls (confirmed live -- that endpoint's `injuries[]` entries carry only
`status`/`date`). It lives on the separate league-wide
`.../apis/site/v2/sports/football/nfl/injuries` feed -- the exact endpoint
`status_check.py`'s own decision #1 evaluated and REJECTED for OUT/
DOUBTFUL/etc. status purposes (an 8-9MB news feed, mostly routine recap
text: confirmed live 2026-10-28, 616/800 sampled entries were
`status: "Active"`, i.e. a weekly box-score blurb, not a game-day
designation). This script pulls that feed for its text fields ONLY --
it is entirely separate from, and does not touch, `status_check.py`'s
OUT-exclusion pipeline.

Deliberately NOT wired into projections. Two concrete reasons, both found
live during scoping:
  1. Confirmed this endpoint has no historical lookback -- `dates`/`week`/
     `season` query params are silently ignored, every call just returns
     today's current snapshot. There is no way to backfill what it said in
     a past week, so the only way to ever get evidence on whether this text
     predicts anything is to start accumulating dated snapshots now and
     check prospectively in a few weeks.
  2. A related, testable proxy (teammate snap-share volatility as a
     "healthy player's role changed" signal) was checked against 108 real
     zero-signal projection misses (Wk2-7 2026) and came back as pure noise
     -- 67.6% of misses had a teammate with a >=15pt snap-share drop that
     week, vs. 71.7% in an unrelated control sample. That's the closest
     comparable test available and it says "plausible-looking usage
     volatility, unvalidated, is not itself a signal" -- a reason for
     caution, not a reason to skip validation on this feed too.

This script's ONLY job: fetch the feed, keep the fields relevant to this
investigation (name/team/status/comment text/date), best-effort match each
row to this pipeline's nflverse player_id (reusing ingest_salaries.py's
existing normalize_name/normalize_team/build_player_reference -- same
two-tier exact-then-unique-name-fallback matching status_check.py uses, so
a future session can join these snapshots to real outcomes without
re-deriving the join), and write a timestamped CSV. No classification, no
scoring, no role-change detection logic here by design -- that is the
explicitly deferred next step, only worth building once there are enough
real prospective snapshots to validate against.

Usage:
    python3 scripts/espn_comment_feed.py pull --season 2026
    python3 scripts/espn_comment_feed.py pull --season 2026 --week 8
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest_salaries import (  # noqa: E402 -- same matching convention as status_check.py
    normalize_name,
    normalize_team,
    build_player_reference,
    POSITION_EQUIVALENTS,
)
from status_check import ESPN_TEAM_IDS  # noqa: E402 -- reuse the existing espn_abbrev -> team_id map

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUT_DIR = REPO_ROOT / "output"

ESPN_INJURIES_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries"

# Reverse of status_check.py's ESPN_TEAM_IDS (espn_abbrev -> id) so a team
# entry's bare numeric `id` in this feed can be mapped back to an abbrev for
# normalize_team(). This feed's team objects only carry {id, displayName,
# injuries} -- no abbreviation of their own.
_ESPN_ID_TO_ABBREV = {v: k for k, v in ESPN_TEAM_IDS.items()}

ESPN_RELEVANT_POSITIONS = {"QB", "RB", "WR", "TE", "FB"}


def fetch_feed() -> dict:
    resp = requests.get(ESPN_INJURIES_URL, timeout=30)
    resp.raise_for_status()
    return resp.json()


def flatten_feed(data: dict) -> pd.DataFrame:
    """One row per (team, athlete) entry with a comment field. Position is
    not given directly on this feed's athlete object (unlike the per-team
    roster endpoint status_check.py uses) -- matching below is name+team
    only, same fallback tier ingest_salaries.py's own final tier uses when
    position isn't available to disambiguate."""
    rows = []
    for team in data.get("injuries", []):
        espn_id = str(team.get("id", ""))
        espn_abbrev = _ESPN_ID_TO_ABBREV.get(espn_id)
        for e in team.get("injuries", []):
            athlete = e.get("athlete") or {}
            rows.append({
                "espn_athlete_id": athlete.get("id"),
                "player_name": athlete.get("displayName", ""),
                "espn_team_name": team.get("displayName", ""),
                "espn_team_abbrev": espn_abbrev,
                "status": e.get("status", ""),
                "short_comment": e.get("shortComment", ""),
                "long_comment": e.get("longComment", ""),
                "comment_date": e.get("date"),
            })
    return pd.DataFrame(rows)


def match_to_player_id(flat: pd.DataFrame, reference: pd.DataFrame) -> pd.DataFrame:
    """Name-only fallback match (unique-or-skip), same discipline as
    status_check.py's own tier 2. No position filter here since this feed
    doesn't give one -- a name collision across positions on the same team
    is rare enough to leave unresolved rather than guess."""
    flat = flat.copy()
    flat["normalized_name"] = flat["player_name"].map(normalize_name)
    flat["normalized_team"] = flat["espn_team_abbrev"].map(
        lambda t: normalize_team(t, "dk") if pd.notna(t) else None
    )
    flat["player_id"] = None
    flat["match_method"] = None

    ref_by_name_team = {}
    for row in reference.itertuples():
        ref_by_name_team.setdefault((row.normalized_name, row.normalized_team), []).append(row.player_id)
    for idx, row in flat.iterrows():
        key = (row["normalized_name"], row["normalized_team"])
        hits = set(ref_by_name_team.get(key, []))
        if len(hits) == 1:
            flat.at[idx, "player_id"] = next(iter(hits))
            flat.at[idx, "match_method"] = "exact_name_team"

    ref_by_name = {}
    for row in reference.itertuples():
        ref_by_name.setdefault(row.normalized_name, []).append(row.player_id)
    unresolved = flat["player_id"].isna()
    for idx, row in flat[unresolved].iterrows():
        unique_ids = set(ref_by_name.get(row["normalized_name"], []))
        if len(unique_ids) == 1:
            flat.at[idx, "player_id"] = next(iter(unique_ids))
            flat.at[idx, "match_method"] = "fallback_name_only"

    return flat


def run_pull(season: int, week: int | None):
    weekly_stats_path = DATA_DIR / f"weekly_stats_{season}.parquet"
    weekly_rosters_path = DATA_DIR / f"weekly_rosters_{season}.parquet"
    reference = build_player_reference(weekly_stats_path, weekly_rosters_path)
    reference = reference[reference["position"].isin(
        ESPN_RELEVANT_POSITIONS | {"K", "PK"}
    )] if "position" in reference.columns else reference

    data = fetch_feed()
    flat = flatten_feed(data)
    if flat.empty:
        raise SystemExit("No rows parsed from the ESPN injuries feed -- check the endpoint before trusting this.")

    matched = match_to_player_id(flat, reference)
    n_matched = matched["player_id"].notna().sum()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    week_tag = f"wk{week}_" if week is not None else ""
    out_path = OUTPUT_DIR / f"espn_comment_feed_{week_tag}{timestamp}.csv"
    matched.drop(columns=["normalized_name", "normalized_team"]).to_csv(out_path, index=False)

    status_counts = matched["status"].value_counts().to_dict()
    print(f"Pulled {len(matched)} comment-feed entries across {data.get('injuries', []).__len__()} team(s).")
    print(f"Matched to player_id: {n_matched} ({n_matched / len(matched):.1%}).")
    print(f"Status breakdown: {status_counts}")
    print(f"Wrote {out_path}")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p_pull = sub.add_parser(
        "pull",
        help="Pull ESPN's league-wide injuries/comment feed and save a timestamped snapshot. Collection only -- "
             "does not touch final_projections or any live build.",
    )
    p_pull.add_argument("--season", type=int, required=True)
    p_pull.add_argument("--week", type=int, default=None, help="Optional -- used only to tag the output filename.")

    args = parser.parse_args()
    if args.command == "pull":
        run_pull(args.season, args.week)


if __name__ == "__main__":
    main()
