"""
status_check.py
================

Session 5.1 -- Injury/Active Status Pull.

Pulls each NFL team's current injury/active status from ESPN, matches
players to the nflverse player_id used everywhere else in this pipeline,
and (via a second subcommand) enforces "OUT excludes from optimizer input"
by reusing build_projections.py's existing zero-out convention -- with NO
changes needed to optimizer.py or build_projections.py.

Site-agnostic (per this card's Roadmap entry): a player's injury status is
the same fact regardless of DK vs FD, so both subcommands operate on
whichever site's final_projections file you point `apply` at.

---------------------------------------------------------------------------
Decision #1 -- which ESPN endpoint, and why the other two real options
were rejected (checked live, 2026-07-22, before choosing):

  a. site.api.espn.com/apis/site/v2/sports/football/nfl/injuries
     (league-wide "injuries" feed) -- REJECTED. This is really a news/
     transactions feed: a real pull returned >9MB for the whole league,
     and almost every entry's own `status` field reads "Active" (a
     roster-news blurb, not a game-day designation). Wrong data shape.

  b. sports.core.api.espn.com/v2/.../teams/{id}/injuries (per-team,
     "core" API) -- REJECTED. Returns EVERY injury-report entry for the
     whole season as bare {"$ref": ...} links (one real team returned 66
     of them, paginated 25/page) -- each is a HISTORICAL status change,
     not just the current one, and each needs a second fetch for the
     actual status/date, plus a THIRD fetch to resolve the athlete's own
     name (the detail record only links an athlete $ref, no name
     embedded). 3 round trips per entry x dozens of entries x 32 teams,
     for data that's mostly stale.

  c. site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{id}/roster
     -- USED HERE. Confirmed live (team 12/KC, 2026-07-22): each of the
     91 real players on the roster carries its OWN `injuries` array
     inline (0 or 1 entries in every case observed), right alongside
     `fullName`/`position`/`id` -- no extra fetches needed at all. 87/91
     had an empty array (no current injury -- see decision #2 for why
     that means ACTIVE); 4 had a single real entry, e.g.
     `{"status": "Questionable", "date": "2026-07-15T19:39Z"}` for
     Patrick Mahomes. ONE call per team, 32 calls for the whole league.

Endpoint last verified working: 2026-07-22. This is an unofficial/
undocumented ESPN endpoint (same caveat as every other ESPN URL in this
class of tool) -- if a future pull 404s or comes back with an unexpected
shape, that's ESPN reorganizing again, not a logic bug; update
ESPN_ROSTER_URL_TEMPLATE / parse_roster_injuries() to match whatever they
changed it to, same "fix it ourselves" posture as nflverse_fetch.py takes
toward nflverse's own release-path changes.

---------------------------------------------------------------------------
Decision #2 -- status mapping. ESPN's raw `injuries[].status` strings are
collapsed to this project's OUT / DOUBTFUL / QUESTIONABLE / ACTIVE scheme
via STATUS_MAP. A player with an EMPTY `injuries` array -> ACTIVE
(confirmed the right read on real data: 87 of 91 real KC players had zero
entries and are simply not currently limited/injured -- there's no
separate "Active" entry to look for, absence of an entry IS the active
signal). Any raw status string NOT in STATUS_MAP fails loudly (collected
and printed, non-fatal per-player but a nonzero final exit code) rather
than silently defaulting to ACTIVE or OUT -- guessing wrong in either
direction here is exactly the kind of silent guess this project has
avoided everywhere else (see build_projections.py's decision #3).

---------------------------------------------------------------------------
Decision #3 -- player matching reuses ingest_salaries.py's
normalize_name() / normalize_team() / build_player_reference() (Session
1.3) rather than inventing a second scheme -- same (normalized_name,
normalized_team) join key targeting the same nflverse player_id. ESPN's
own team abbreviations (confirmed live) already collide with two of
ingest_salaries.py's existing BASE_TEAM_ABBREV_MAP entries -- ESPN's "LAR"
-> nflverse's "LA", ESPN's "WSH" -> nflverse's "WAS" -- so
normalize_team(raw, site="dk") is reused as-is (DK's own
team_abbrev_overrides table is empty, so this only ever applies the
shared BASE_TEAM_ABBREV_MAP) instead of adding a third abbreviation table
for one more data source. Matching is two-tier, same fail-loud spirit as
ingest_salaries.py's own tiers: (1) exact (normalized_name,
normalized_team), (2) name-only fallback ONLY if it resolves to a single
unique player_id across the whole reference (catches an in-season trade
between the player's nflverse team and their current ESPN team). Anything
left over is logged, never silently dropped.

Only QB/RB/WR/TE/FB are pulled from each roster (FB folds into RB, same
POSITION_EQUIVALENTS convention ingest_salaries.py already uses) --
matches this pipeline's own skill-position universe
(build_projections.py's POSITIONS list); other positions can't appear in
a DFS pool at all, so pulling/matching them would just be noise.

---------------------------------------------------------------------------
Decision #4 -- two subcommands:

  `pull`   -- hits ESPN, matches to player_id, writes this session's
              roadmap-specified output:
              output/player_status_{week}_{timestamp}.csv

  `apply`  -- the actual "OUT excludes from optimizer input" enforcement
              (this card's second validation checkbox). Reads a `pull`
              output file plus an existing
              final_projections_{site}_{week}.csv (Session 2.4) and, for
              every OUT player, forces final_projection to 0.0 --
              deliberately reusing the EXACT SAME zero-out convention
              build_projections.py's decision #4b already established
              for a confirmed-no-game player, rather than inventing a
              second "this player doesn't count" mechanism elsewhere in
              the pipeline. optimizer.py already never selects a
              0.0-projection player over a legal positive-projection
              alternative (Session 3.1's own decision #4) -- so zeroing
              here is sufficient, structural exclusion. This is exactly
              what makes OUT-exclusion work with ZERO changes to
              optimizer.py or build_projections.py, matching this
              session's roadmap card, which lists only this one file
              under "Files touched."

              QUESTIONABLE/DOUBTFUL are flagged via a new
              `injury_status` column added to the output file and left
              otherwise unchanged (final_projection untouched) --
              "flags but doesn't exclude," per the card. Purely additive
              column, same pattern Session 3.3's addendum used for
              opponent/implied_total/over_under -- optimizer.py's own
              `required` column check is a subset check, so this new
              column doesn't break it.

              By default OVERWRITES output/final_projections_{site}_
              {week}.csv in place -- the exact filename optimizer.py
              reads, which has no path override of its own. `--out` can
              redirect elsewhere for a dry run before committing to the
              overwrite.

---------------------------------------------------------------------------
Decision #5 -- KNOWN GAP, same shape as this project's other "can't
validate for real until the season exists yet" notes (see ROADMAP.md's
Vegas-lines-only-currently-listed and FD-salary-format gaps). Pulled live
2026-07-22 (off-season / pre-training-camp): every real non-"empty-array"
status seen across a sampled roster was "Questionable," and every one of
those was tied to a long-term injury recovery (e.g. Mahomes' ACL) or a
personal/legal situation -- NOT a game-week designation, because there is
no NFL game being played yet to designate anyone in/out FOR. A real
OUT/DOUBTFUL *game-day* designation -- the kind that actually needs to
zero a player out of a SPECIFIC week's slate -- first becomes possible
once real practice-report windows exist ahead of a real game: Preseason
Week 1 (Aug 13-15, 2026), the same first-real-data checkpoint as this
project's other deferred-validation gaps (see ROADMAP.md's "Known
Deferred Validations" section -- this note belongs there too). This
session's `pull`/`apply` logic is validated for MECHANISM on real (if not
yet game-relevant) ESPN data -- endpoint shape, matching, zero-out
plumbing all confirmed working end-to-end -- but re-validate against a
real OUT/DOUBTFUL game-day designation once one actually exists.

Usage:
    python3 scripts/status_check.py pull --season 2025 --week 10
    python3 scripts/status_check.py pull --season 2025 --week 10 \
        --teams KC,BUF,DAL

    python3 scripts/status_check.py apply --site dk --week 10 \
        --status-file output/player_status_10_20260722_140000.csv
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest_salaries import (  # noqa: E402 -- Session 1.3's single source of truth for name/team normalization
    normalize_name,
    normalize_team,
    build_player_reference,
    POSITION_EQUIVALENTS,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUT_DIR = REPO_ROOT / "output"
LOG_DIR = REPO_ROOT / "logs"

# ---------------------------------------------------------------------------
# ESPN team id map (decision #1) -- confirmed live via
# site.api.espn.com/apis/site/v2/sports/football/nfl/teams, 2026-07-22.
# Keyed by ESPN's OWN abbreviation (see decision #3 re: LAR/WSH quirks) so
# --teams can be given in either ESPN's or nflverse's spelling.
# ---------------------------------------------------------------------------
ESPN_TEAM_IDS = {
    "ARI": "22", "ATL": "1", "BAL": "33", "BUF": "2", "CAR": "29",
    "CHI": "3", "CIN": "4", "CLE": "5", "DAL": "6", "DEN": "7",
    "DET": "8", "GB": "9", "HOU": "34", "IND": "11", "JAX": "30",
    "KC": "12", "LV": "13", "LAC": "24", "LAR": "14", "MIA": "15",
    "MIN": "16", "NE": "17", "NO": "18", "NYG": "19", "NYJ": "20",
    "PHI": "21", "PIT": "23", "SF": "25", "SEA": "26", "TB": "27",
    "TEN": "10", "WSH": "28",
}
# nflverse-spelling aliases so --teams LA / --teams WAS also work.
_TEAM_ALIASES = {"LA": "LAR", "WAS": "WSH"}

ESPN_ROSTER_URL_TEMPLATE = (
    "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team_id}/roster"
)

ESPN_RELEVANT_POSITIONS = {"QB", "RB", "WR", "TE", "FB"}

# Decision #2 -- raw ESPN injuries[].status string -> this project's
# OUT/DOUBTFUL/QUESTIONABLE/ACTIVE scheme. Extend this map (don't guess)
# if a future pull surfaces a raw string not listed here -- see
# parse_roster_injuries()'s fail-loud handling below.
STATUS_MAP = {
    "out": "OUT",
    "injured reserve": "OUT",
    "ir": "OUT",
    "physically unable to perform": "OUT",
    "pup": "OUT",
    "suspended": "OUT",
    "reserve/suspended": "OUT",
    "doubtful": "DOUBTFUL",
    "questionable": "QUESTIONABLE",
    "day-to-day": "QUESTIONABLE",
    "active": "ACTIVE",
    "probable": "ACTIVE",  # legacy designation, ESPN rarely uses it now
}


def resolve_team_ids(teams_arg: str | None) -> dict:
    """Returns {espn_abbrev: espn_team_id} for the requested teams (all 32
    if --teams wasn't given). Accepts either ESPN's or nflverse's spelling
    for LA/LAR and WAS/WSH (decision #3)."""
    if not teams_arg:
        return dict(ESPN_TEAM_IDS)
    requested = [t.strip().upper() for t in teams_arg.split(",") if t.strip()]
    out = {}
    for t in requested:
        espn_abbrev = _TEAM_ALIASES.get(t, t)
        if espn_abbrev not in ESPN_TEAM_IDS:
            raise SystemExit(
                f"Unknown team '{t}' in --teams. Expected one of "
                f"{sorted(ESPN_TEAM_IDS)} (or 'LA'/'WAS', nflverse's "
                f"spelling for LAR/WSH)."
            )
        out[espn_abbrev] = ESPN_TEAM_IDS[espn_abbrev]
    return out


# ---------------------------------------------------------------------------
# Step 1: Pull + parse one team's roster (decision #1c)
# ---------------------------------------------------------------------------

def fetch_team_roster(team_id: str) -> dict:
    url = ESPN_ROSTER_URL_TEMPLATE.format(team_id=team_id)
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json()


def parse_roster_injuries(espn_abbrev: str, roster_json: dict, unmapped_statuses: set) -> list[dict]:
    """Extracts one row per fantasy-relevant player on this team's roster
    (decision #3's ESPN_RELEVANT_POSITIONS filter), with status collapsed
    via STATUS_MAP (decision #2). A player with an empty `injuries` array
    -> ACTIVE, raw_status=None. A raw status string not in STATUS_MAP is
    added to `unmapped_statuses` (caller fails loudly on these) and that
    player is skipped from the output entirely rather than guessed at.
    """
    rows = []
    team_nflverse = normalize_team(espn_abbrev, "dk")  # decision #3 -- reuses the shared base map

    for group in roster_json.get("athletes", []):
        for p in group.get("items", []):
            pos = (p.get("position") or {}).get("abbreviation", "")
            if pos not in ESPN_RELEVANT_POSITIONS:
                continue

            injuries = p.get("injuries") or []
            if not injuries:
                status, raw_status, last_updated = "ACTIVE", None, None
            else:
                # Most recent entry by date, in case a player somehow
                # carries more than one (not seen on real data, but not
                # assumed impossible either).
                latest = sorted(injuries, key=lambda i: i.get("date", ""))[-1]
                raw_status = latest.get("status", "")
                last_updated = latest.get("date")
                mapped = STATUS_MAP.get(raw_status.strip().lower())
                if mapped is None:
                    unmapped_statuses.add(raw_status)
                    continue
                status = mapped

            rows.append({
                "espn_id": p.get("id"),
                "player_name": p.get("fullName", ""),
                "espn_position": pos,
                "team": team_nflverse,
                "status": status,
                "raw_status": raw_status,
                "last_updated": last_updated,
            })
    return rows


# ---------------------------------------------------------------------------
# Step 2: Match to nflverse player_id (decision #3)
# ---------------------------------------------------------------------------

def match_to_player_id(pulled: pd.DataFrame, reference: pd.DataFrame) -> pd.DataFrame:
    pulled = pulled.copy()
    pulled["normalized_name"] = pulled["player_name"].map(normalize_name)
    pulled["normalized_team"] = pulled["team"]  # already normalized in parse_roster_injuries
    pulled["player_id"] = None
    pulled["match_method"] = None

    # Tier 1: exact (normalized_name, normalized_team), position-equivalence
    # aware (FB folds into RB) -- same convention as ingest_salaries.py.
    ref_by_name_team = {}
    for row in reference.itertuples():
        ref_by_name_team.setdefault((row.normalized_name, row.normalized_team), []).append(
            (row.position, row.player_id)
        )
    for idx, row in pulled.iterrows():
        equiv = POSITION_EQUIVALENTS.get(row["espn_position"], {row["espn_position"]})
        candidates = ref_by_name_team.get((row["normalized_name"], row["normalized_team"]), [])
        hits = [pid for pos, pid in candidates if pos in equiv]
        if len(hits) == 1:
            pulled.at[idx, "player_id"] = hits[0]
            pulled.at[idx, "match_method"] = "auto_exact"

    # Tier 2: name-only fallback, ONLY if it uniquely resolves across the
    # whole reference (catches a trade between the player's nflverse team
    # and their CURRENT ESPN team) -- same "unique-or-skip" discipline as
    # ingest_salaries.py's own final tier.
    ref_by_name = {}
    for row in reference.itertuples():
        ref_by_name.setdefault(row.normalized_name, []).append(row.player_id)
    unresolved = pulled["player_id"].isna()
    for idx, row in pulled[unresolved].iterrows():
        unique_ids = set(ref_by_name.get(row["normalized_name"], []))
        if len(unique_ids) == 1:
            pulled.at[idx, "player_id"] = next(iter(unique_ids))
            pulled.at[idx, "match_method"] = "auto_fallback_name_only"

    return pulled


# ---------------------------------------------------------------------------
# `pull` subcommand
# ---------------------------------------------------------------------------

def run_pull(season: int, week: int, teams_arg: str | None, weekly_stats_override: str | None):
    team_ids = resolve_team_ids(teams_arg)
    weekly_stats_path = Path(weekly_stats_override) if weekly_stats_override else (
        DATA_DIR / f"weekly_stats_{season}.parquet"
    )
    if not weekly_stats_path.exists():
        raise SystemExit(
            f"{weekly_stats_path} not found -- this is a Session 1.2 output, "
            f"needed to build the player_id reference table (decision #3). "
            f"Run ingest_historical.py --season {season} first."
        )
    reference = build_player_reference(weekly_stats_path)

    all_rows = []
    unmapped_statuses = set()
    failed_teams = []
    for espn_abbrev, team_id in team_ids.items():
        try:
            roster_json = fetch_team_roster(team_id)
        except requests.RequestException as e:
            failed_teams.append((espn_abbrev, str(e)))
            print(f"WARNING: failed to pull roster for {espn_abbrev} (team id {team_id}): {e}",
                  file=sys.stderr)
            continue
        all_rows.extend(parse_roster_injuries(espn_abbrev, roster_json, unmapped_statuses))

    if not all_rows:
        raise SystemExit("No rows pulled from ESPN at all -- check network/endpoint before trusting any output.")

    pulled = pd.DataFrame(all_rows)
    matched = match_to_player_id(pulled, reference)

    unmatched = matched[matched["player_id"].isna()]
    final = matched[matched["player_id"].notna()][
        ["player_id", "player_name", "team", "espn_position", "status", "raw_status", "last_updated", "match_method"]
    ].rename(columns={"espn_position": "position"})

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"player_status_{week}_{timestamp}.csv"
    final.to_csv(out_path, index=False)

    unmatched_path = LOG_DIR / f"unmatched_status_{week}_{timestamp}.csv"
    unmatched.drop(columns=["player_id"]).to_csv(unmatched_path, index=False)

    n_out = (final["status"] == "OUT").sum()
    n_doubtful = (final["status"] == "DOUBTFUL").sum()
    n_questionable = (final["status"] == "QUESTIONABLE").sum()
    n_active = (final["status"] == "ACTIVE").sum()

    print(f"Pulled {len(pulled)} fantasy-relevant player(s) across {len(team_ids)} team(s) "
          f"({len(failed_teams)} team(s) failed to fetch: {[t for t, _ in failed_teams]}).")
    print(f"Matched: {len(final)} ({len(final) / len(pulled):.1%}). Unmatched: {len(unmatched)} -> {unmatched_path}")
    print(f"Status breakdown -- OUT: {n_out}, DOUBTFUL: {n_doubtful}, QUESTIONABLE: {n_questionable}, ACTIVE: {n_active}")
    print(f"Wrote {out_path}")

    if unmapped_statuses:
        print(f"ERROR: {len(unmapped_statuses)} unrecognized raw ESPN status string(s) skipped "
              f"(not written to output, not silently guessed -- decision #2): {sorted(unmapped_statuses)}. "
              f"Add these to STATUS_MAP in this file, then re-run.", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# `apply` subcommand -- decision #4's actual OUT-exclusion enforcement
# ---------------------------------------------------------------------------

def run_apply(site: str, week: int, status_file: str, projections_file: str | None, out_file: str | None):
    proj_path = Path(projections_file) if projections_file else (OUTPUT_DIR / f"final_projections_{site}_{week}.csv")
    if not proj_path.exists():
        raise SystemExit(
            f"{proj_path} not found. Run build_projections.py --site {site} "
            f"--week {week} first (Session 2.4)."
        )
    status_path = Path(status_file)
    if not status_path.exists():
        raise SystemExit(f"{status_path} not found -- run `status_check.py pull` first.")

    projections = pd.read_csv(proj_path, dtype={"player_id": str})
    status = pd.read_csv(status_path, dtype={"player_id": str})
    required_status_cols = {"player_id", "status"}
    missing = required_status_cols - set(status.columns)
    if missing:
        raise SystemExit(f"{status_path} is missing expected columns: {sorted(missing)}.")

    merged = projections.merge(status[["player_id", "status"]], on="player_id", how="left")
    # A player in the current slate but absent from the ESPN pull (e.g. a
    # team that failed to fetch, decision #4's partial-pull case) is
    # treated as ACTIVE -- the same "no evidence of a problem" default
    # used inside parse_roster_injuries() for an empty injuries array,
    # applied consistently here rather than silently zeroing on an
    # unrelated fetch failure.
    merged["injury_status"] = merged["status"].fillna("ACTIVE")
    merged = merged.drop(columns=["status"])

    out_mask = merged["injury_status"] == "OUT"
    n_out = out_mask.sum()
    n_already_zero = (out_mask & (merged["final_projection"] == 0.0)).sum()
    merged.loc[out_mask, "final_projection"] = 0.0

    n_doubtful = (merged["injury_status"] == "DOUBTFUL").sum()
    n_questionable = (merged["injury_status"] == "QUESTIONABLE").sum()

    out_path = Path(out_file) if out_file else proj_path
    merged.to_csv(out_path, index=False)

    # Structural re-check (this project's "guarantee, not eyeballing"
    # pattern -- see optimizer.py's validate_lineup()/validate_stack()).
    reloaded = pd.read_csv(out_path, dtype={"player_id": str})
    still_nonzero_out = reloaded[(reloaded["injury_status"] == "OUT") & (reloaded["final_projection"] != 0.0)]
    assert still_nonzero_out.empty, (
        f"APPLY VALIDATION FAILED: {len(still_nonzero_out)} OUT player(s) still have a nonzero "
        f"final_projection after writing {out_path} -- {still_nonzero_out['player_name'].tolist()}"
    )

    print(f"Applied {status_path.name} to {proj_path.name}.")
    print(f"  OUT: {n_out} player(s) -- final_projection forced to 0.0 "
          f"({n_already_zero} were already 0.0 from a bye/no-real-game, unaffected).")
    print(f"  DOUBTFUL: {n_doubtful}, QUESTIONABLE: {n_questionable} -- flagged via `injury_status`, "
          f"final_projection left unchanged.")
    print(f"  Wrote {out_path}" + (" (overwrote the file optimizer.py reads)" if out_path == proj_path else ""))
    print("  Validation: PASS -- every OUT player's final_projection confirmed 0.0 on reload.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p_pull = sub.add_parser("pull", help="Pull current status from ESPN, match to player_id, write player_status CSV.")
    p_pull.add_argument("--season", type=int, required=True)
    p_pull.add_argument("--week", type=int, required=True, help="Used only in the output filename (matches vegas_odds.py's convention).")
    p_pull.add_argument("--teams", default=None, help="Comma-separated team abbreviations to restrict the pull (default: all 32).")
    p_pull.add_argument("--weekly-stats", default=None, help="Override path to weekly_stats parquet (default: data/weekly_stats_{season}.parquet).")

    p_apply = sub.add_parser("apply", help="Zero OUT players' final_projection; flag DOUBTFUL/QUESTIONABLE.")
    p_apply.add_argument("--site", choices=["dk", "fd"], required=True)
    p_apply.add_argument("--week", type=int, required=True)
    p_apply.add_argument("--status-file", required=True, help="Path to a player_status_*.csv from `pull`.")
    p_apply.add_argument("--projections-file", default=None, help="Override path (default: output/final_projections_{site}_{week}.csv).")
    p_apply.add_argument("--out", default=None, help="Override output path (default: overwrite --projections-file in place).")

    args = parser.parse_args()

    if args.command == "pull":
        run_pull(args.season, args.week, args.teams, args.weekly_stats)
    elif args.command == "apply":
        run_apply(args.site, args.week, args.status_file, args.projections_file, args.out)


if __name__ == "__main__":
    main()
