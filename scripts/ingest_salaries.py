"""
ingest_salaries.py
===================

Session 1.3 -- Salary Data Ingestion (revised to support DraftKings AND
FanDuel -- see SESSION_LOG.md's Session 1.3 revision entry for why this
changed after the original DK-only version shipped).

Ingests a manually-downloaded DraftKings or FanDuel NFL "Classic" salary
export CSV, normalizes player names/teams, and matches each row to the
nflverse player_id used everywhere else in this pipeline (see
nflverse_fetch.py / data/weekly_stats_{season}.parquet from Sessions 1.1-1.2).

Site is selected with --site {dk,fd}. Everything downstream of the raw-file
parser (normalization, matching, override table, output) is shared logic --
only column names, defense-position labels, and team-abbreviation quirks
differ by site.

DraftKings file-shape note (found in Session 1.3 revision, real data):
  DK's "Export to CSV" button on the player pool gives a clean standalone
  table: Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,
  TeamAbbrev,AvgPointsPerGame.
  DK's "DKEntries.csv" bulk lineup-upload template (downloaded from the
  "Entries" screen) is a DIFFERENT shape: your contest entries on the left
  columns, and that SAME player-pool table embedded starting several
  columns to the right, preceded by blank cells. Both are real files users
  will have on hand, so this script detects and handles either shape for
  site="dk" -- see _load_dk_raw().

Why matching isn't a plain merge:
  - Site names don't always match nflverse's `player_display_name` exactly
    (suffixes like "Jr."/"II", punctuation, occasional site typos).
  - Site team abbreviations don't always match nflverse's scheme
    (e.g. DK's "LAR" vs nflverse's "LA", "JAC" vs "JAX").
  - Team defenses (DK: "DST" position, FD: "D"/"DEF" position) aren't
    players and have no nflverse player_id at all -- handled as a separate
    case, not a failure.

Matching strategy (in order, first hit wins):
  1. Manual override table (data/name_mapping.csv) -- always checked first,
     so a mismatch fixed once by hand stays fixed every future week, per
     site (a DK override doesn't automatically apply to FD or vice versa,
     since the two sites' raw name/team text can differ).
  2. Team defenses -- matched to a synthetic "DST_{team}" id, not to a
     player_id, since nflverse's player-level data has no defense rows.
  3. Automatic match on (normalized_name, normalized_team, position).
  4. Fallback match on (normalized_name, position) only, for players who
     were traded/signed after their last game in weekly_stats -- flagged
     as a lower-confidence match (team_mismatch) so it can be eyeballed.
  5. No match -- logged to logs/unmatched_salaries_{site}_{slate_id}.csv,
     never silently dropped from the main output (kept with player_id = null).

Usage:
  python scripts/ingest_salaries.py \
      --site dk \
      --raw data/raw_salaries/DKSalaries.csv \
      --season 2025 \
      --slate-id classic_wk1

  python scripts/ingest_salaries.py \
      --site fd \
      --raw data/raw_salaries/FDSalaries.csv \
      --season 2025 \
      --slate-id classic_wk1

Outputs:
  data/salaries_{site}_{slate_id}.csv
      Every row from the export plus: player_id, match_method, match_confidence
  logs/unmatched_salaries_{site}_{slate_id}.csv
      Only the rows that failed to match (empty file with header if none) --
      this is the file to check before trusting a week's salary data.

Adding a new manual override:
  Append a row to data/name_mapping.csv:
      site,source_name,source_team,source_position,player_id,notes
      dk,Gabe Davis,BUF,WR,00-0036973,example only
  It's consulted before any automatic matching, so it always wins. Overrides
  are scoped to `site` -- the same player may need separate rows for dk and
  fd if their raw name/team text differs between the two exports.

CAVEAT (see SESSION_LOG.md): the FD column layout and FD-specific team
abbreviation handling below are based on documented FanDuel export format,
NOT yet verified against a real current-season FD download (no FD
equivalent of DK's Madden Stream exists to test against right now). If a
real FD file's columns don't match SITE_CONFIGS["fd"], the script fails
loudly with expected-vs-actual columns rather than silently misparsing --
fix SITE_CONFIGS here.
"""

import argparse
import csv
import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Team abbreviation normalization
# ---------------------------------------------------------------------------
# Maps common site-specific / legacy abbreviations to nflverse's canonical
# set (as seen in data/weekly_stats_{season}.parquet's `team` column).
# Base map applies to both sites; site-specific overrides/additions go in
# SITE_CONFIGS[site]["team_abbrev_overrides"].
BASE_TEAM_ABBREV_MAP = {
    "LAR": "LA",   # nflverse uses LA for the Rams
    "LVR": "LV",
    "OAK": "LV",   # legacy Raiders abbrev, in case of old exports
    "SD": "LAC",   # legacy Chargers abbrev
    "STL": "LA",   # legacy Rams abbrev
    "WSH": "WAS",
    "JAC": "JAX",
    "NOS": "NO",
    "NOR": "NO",   # found via real RotoGuru data (Session: RotoGuru ingest) --
                   # "NOS" was already here but RotoGuru uses "nor". Left
                   # unmapped, NOR silently (a) demoted every New Orleans skill
                   # player from an exact match to the medium-confidence
                   # auto_fallback_team_mismatch stage, and (b) produced a
                   # DST row with normalized_team="NOR", which can never match
                   # the Vegas file's "NO" -- so build_dst_projections() would
                   # treat NO as a bye and force final_projection to 0.0 every
                   # single week, with no error. Purely additive: no site
                   # export currently sends "NOR", so no existing behavior
                   # changes.
    "GNB": "GB",
    "SFO": "SF",
    "TAM": "TB",
    "NWE": "NE",
    "KAN": "KC",
}

SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}

# Some sites don't have a dedicated position for certain real NFL positions
# and fold them into an adjacent one. Used in matching so a site's Position
# label doesn't cause an otherwise-correct match to be missed. Found via
# real DK data in Session 1.3's revision (Alec Ingold listed as DK "RB",
# nflverse position "FB").
POSITION_EQUIVALENTS = {
    "RB": {"RB", "FB"},
}


# ---------------------------------------------------------------------------
# Site configuration
# ---------------------------------------------------------------------------
# salary_cap / roster_slots / scoring are metadata only (not used by THIS
# script) -- carried here so Session 3.1 (optimizer) and Session 2.x
# (projections) have one place to read site rules from instead of
# re-discovering them later. See SESSION_LOG.md Session 1.3 revision entry.
SITE_CONFIGS = {
    "dk": {
        "label": "DraftKings",
        "required_columns": {"Name", "Position", "TeamAbbrev", "Salary"},
        "name_col": "Name",
        "team_col": "TeamAbbrev",
        "position_col": "Position",
        "salary_col": "Salary",
        # Session 7.3 addition -- DK's own numeric player ID (the "ID"
        # column in both a standalone DK salary export and the embedded
        # player-pool table in DKEntries.csv -- see that file's own
        # "Position,Name + ID,Name,ID,..." header). Different from this
        # pipeline's own nflverse player_id; needed for the "Download
        # Lineups" DK-import feature, which has to write DK's ID (or
        # "Name (ID)"), never just a name (DK's own bulk-upload
        # instructions explicitly reject name-only).
        "site_id_col": "ID",
        # The column name for a defense's season average fantasy points in
        # the raw salary export. Used by build_projections.py's legacy DST
        # path (decision #5a). DK names this column "AvgPointsPerGame";
        # FD names it "FPPG". Keeping this in SITE_CONFIGS (the single
        # source of truth for site-specific column names) rather than
        # hardcoding in build_projections.py -- same discipline as site_id_col.
        "avg_ppg_col": "AvgPointsPerGame",
        "defense_position_values": {"DST"},
        "team_abbrev_overrides": {},
        "salary_cap": 50000,
        "roster_slots": ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"],
        "scoring": "full_ppr",   # 1 pt/reception
    },
    "fd": {
        "label": "FanDuel",
        # UNVERIFIED against a real current FD export -- standard documented
        # FD Classic column layout: Id, Position, First Name, Nickname,
        # Last Name, FPPG, Played, Salary, Game, Team, Opponent,
        # Injury Indicator, Injury Details
        "required_columns": {"Position", "Team", "Salary"},
        "name_col": None,   # derived from First Name/Last Name/Nickname
        "team_col": "Team",
        "position_col": "Position",
        "salary_col": "Salary",
        # Session 7.3 addition -- same purpose as dk's site_id_col above.
        # UNVERIFIED, same caveat as required_columns above -- FD's own
        # entry-upload template/column name hasn't been confirmed against
        # a real export yet.
        "site_id_col": "Id",
        # FD names the season-average PPG column "FPPG" (not "AvgPointsPerGame"
        # like DK). UNVERIFIED against a real FD export -- confirmed from FD's
        # documented column layout (see module docstring), same status as
        # required_columns and site_id_col above. Fix here when a real FD
        # export confirms or corrects this.
        "avg_ppg_col": "FPPG",
        "defense_position_values": {"D", "DEF"},
        "team_abbrev_overrides": {},
        "salary_cap": 60000,
        "roster_slots": ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DEF"],
        "scoring": "half_ppr",   # 0.5 pt/reception
    },
}


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def normalize_name(name: str) -> str:
    """Lowercase, strip punctuation and generational suffixes, collapse whitespace."""
    if not isinstance(name, str):
        return ""
    name = name.lower().strip()
    name = name.replace(".", "").replace("'", "").replace("-", " ")
    tokens = [t for t in name.split() if t not in SUFFIXES]
    return " ".join(tokens)


def normalize_team(team: str, site: str) -> str:
    if not isinstance(team, str):
        return ""
    team = team.strip().upper()
    overrides = SITE_CONFIGS[site]["team_abbrev_overrides"]
    if team in overrides:
        return overrides[team]
    return BASE_TEAM_ABBREV_MAP.get(team, team)


# ---------------------------------------------------------------------------
# Step 1: Load raw site export
# ---------------------------------------------------------------------------

def _load_dk_raw(path: Path) -> pd.DataFrame:
    """Handle both DK file shapes: a clean standalone salary export, and
    the DKEntries.csv bulk-upload template with the player pool embedded
    to the right of the entries table."""
    try:
        df = pd.read_csv(path)
        if SITE_CONFIGS["dk"]["required_columns"].issubset(set(df.columns)):
            return df
    except pd.errors.ParserError:
        pass  # fall through to the embedded-table extraction below

    # Fallback: scan for the embedded player-pool table (DKEntries.csv shape)
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    header_idx, col_offset = None, None
    for i, row in enumerate(rows):
        if "Position" in row and "Name + ID" in row and "Salary" in row:
            header_idx = i
            col_offset = row.index("Position")
            break

    if header_idx is None:
        raise SystemExit(
            f"Could not find a DraftKings player-pool table in {path}. "
            f"Expected either a standalone export with columns "
            f"{sorted(SITE_CONFIGS['dk']['required_columns'])}, or a "
            f"DKEntries.csv-style file with an embedded 'Position,...,Salary,...' "
            f"table. Neither pattern was found -- check the file wasn't "
            f"truncated or re-saved with different column names."
        )

    n_cols = 9  # Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame
    header = rows[header_idx][col_offset:col_offset + n_cols]
    data_rows = [
        row[col_offset:col_offset + n_cols]
        for row in rows[header_idx + 1:]
        if len(row) >= col_offset + n_cols and row[col_offset]
    ]
    return pd.DataFrame(data_rows, columns=header)


def _load_fd_raw(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = SITE_CONFIGS["fd"]["required_columns"] - set(df.columns)
    if missing:
        raise SystemExit(
            f"Raw FanDuel salary CSV at {path} is missing expected columns: "
            f"{sorted(missing)}. Columns actually present: {sorted(df.columns)}. "
            f"FD's real export format hasn't been verified yet (see module "
            f"docstring) -- update SITE_CONFIGS['fd'] in this script to match "
            f"what you actually got, rather than guessing."
        )
    return df


def load_raw_salary_csv(path: Path, site: str) -> pd.DataFrame:
    if site == "dk":
        df = _load_dk_raw(path)
    elif site == "fd":
        df = _load_fd_raw(path)
    else:
        raise SystemExit(f"Unknown site '{site}' -- expected 'dk' or 'fd'.")

    cfg = SITE_CONFIGS[site]

    # Derive a single `name` column
    if cfg["name_col"]:
        df["name"] = df[cfg["name_col"]]
    else:
        # FD: prefer Nickname (FD's usual display name), fall back to First+Last
        if "Nickname" in df.columns and df["Nickname"].notna().any():
            df["name"] = df["Nickname"].fillna(
                df.get("First Name", "").astype(str) + " " + df.get("Last Name", "").astype(str)
            )
        else:
            df["name"] = (
                df.get("First Name", "").astype(str) + " " + df.get("Last Name", "").astype(str)
            )

    df["site"] = site
    df["salary"] = pd.to_numeric(df[cfg["salary_col"]], errors="coerce")
    df["normalized_name"] = df["name"].map(normalize_name)
    df["normalized_team"] = df[cfg["team_col"]].map(lambda t: normalize_team(t, site))
    df["position_upper"] = df[cfg["position_col"]].astype(str).str.upper()
    return df


# ---------------------------------------------------------------------------
# Step 2: Build the player reference table from Session 1.2's weekly_stats
# ---------------------------------------------------------------------------

def build_player_reference(weekly_stats_path: Path) -> pd.DataFrame:
    weekly = pd.read_parquet(weekly_stats_path)
    name_col = "player_display_name" if "player_display_name" in weekly.columns else "player_name"

    weekly = weekly.dropna(subset=["player_id", name_col, "position", "team"])
    weekly = weekly.sort_values(["player_id", "week"])

    # Most recent team per player (handles in-season trades: site salary
    # data reflects a player's CURRENT team, weekly_stats has all teams
    # they've played for this season).
    most_recent = (
        weekly.groupby("player_id")
        .tail(1)[["player_id", name_col, "position", "team"]]
        .rename(columns={name_col: "player_display_name"})
    )
    most_recent["normalized_name"] = most_recent["player_display_name"].map(normalize_name)
    most_recent["normalized_team"] = most_recent["team"].map(
        lambda t: BASE_TEAM_ABBREV_MAP.get(str(t).strip().upper(), str(t).strip().upper())
    )
    return most_recent


# ---------------------------------------------------------------------------
# Step 3: Manual override table
# ---------------------------------------------------------------------------

def load_name_mapping(path: Path, site: str) -> pd.DataFrame:
    cols = ["site", "source_name", "source_team", "source_position", "player_id", "notes"]
    if not path.exists():
        return pd.DataFrame(columns=cols)
    df = pd.read_csv(path)
    missing = set(cols[:5]) - set(df.columns)
    if missing:
        raise SystemExit(f"{path} is missing expected columns: {sorted(missing)}")
    df = df[df["site"] == site].copy()
    df["normalized_name"] = df["source_name"].map(normalize_name)
    df["normalized_team"] = df["source_team"].map(lambda t: normalize_team(t, site))
    return df


# ---------------------------------------------------------------------------
# Step 4: Match
# ---------------------------------------------------------------------------

def match_players(salaries: pd.DataFrame, reference: pd.DataFrame,
                   name_mapping: pd.DataFrame, site: str) -> pd.DataFrame:
    salaries = salaries.copy()
    salaries["player_id"] = None
    salaries["match_method"] = None
    salaries["match_confidence"] = None

    # --- 1. Manual overrides (highest priority) ---
    # A mapping row carries an explicit player_id, so the (name, team,
    # position) ambiguity it exists to resolve is ALREADY resolved -- the ID
    # pins the exact player. Requiring team to match on top of that can only
    # cause MISSES, never prevent a bad match: a name-variant row written
    # with one team (e.g. Robby Anderson -> Robbie Chosen, source_team CAR)
    # would then fire only in that player's CAR weeks and silently fail to
    # resolve his NYJ/ARI/WAS weeks, which is exactly the multi-team miss
    # found on real data (113 unmatched -> only 110 after mapping).
    #
    # So overrides are keyed by NAME, team-agnostic by default. A row MAY
    # still supply source_team to narrow -- kept for the rare case of two
    # different real players sharing a normalized name, where team is the
    # disambiguator -- but a blank/NaN source_team means "any team". Because
    # each row names an explicit player_id, name-only can't silently pick
    # the wrong same-named player the way an inferred match could.
    name_only_lookup = {}       # normalized_name -> player_id
    name_team_lookup = {}       # (normalized_name, normalized_team) -> player_id
    for row in name_mapping.itertuples():
        team = getattr(row, "normalized_team", "")
        if isinstance(team, str) and team.strip():
            name_team_lookup[(row.normalized_name, team)] = row.player_id
        else:
            name_only_lookup[row.normalized_name] = row.player_id

    for idx, row in salaries.iterrows():
        pid = name_team_lookup.get((row["normalized_name"], row["normalized_team"]))
        if pid is None:
            pid = name_only_lookup.get(row["normalized_name"])
        if pid is not None:
            salaries.at[idx, "player_id"] = pid
            salaries.at[idx, "match_method"] = "manual_override"
            salaries.at[idx, "match_confidence"] = "high"

    # --- 2. Team defenses: no nflverse player_id, not a failure ---
    defense_values = SITE_CONFIGS[site]["defense_position_values"]
    is_def = salaries["position_upper"].isin(defense_values)
    unresolved = salaries["player_id"].isna()
    def_mask = is_def & unresolved
    salaries.loc[def_mask, "player_id"] = "DST_" + salaries.loc[def_mask, "normalized_team"]
    salaries.loc[def_mask, "match_method"] = "team_defense"
    salaries.loc[def_mask, "match_confidence"] = "high"

    # --- 3. Automatic match on (name, team, position-or-equivalent) ---
    ref_by_name_team = {}
    for row in reference.itertuples():
        ref_by_name_team.setdefault((row.normalized_name, row.normalized_team), []).append(
            (row.position, row.player_id)
        )
    unresolved = salaries["player_id"].isna()
    for idx, row in salaries[unresolved].iterrows():
        candidates = ref_by_name_team.get((row["normalized_name"], row["normalized_team"]), [])
        equiv_positions = POSITION_EQUIVALENTS.get(row["position_upper"], {row["position_upper"]})
        hits = [pid for pos, pid in candidates if pos in equiv_positions]
        if len(hits) == 1:
            salaries.at[idx, "player_id"] = hits[0]
            salaries.at[idx, "match_method"] = "auto_exact"
            salaries.at[idx, "match_confidence"] = "high"

    # --- 4. Fallback: (name, position-or-equivalent) only -- catches trades/signings ---
    ref_by_name_pos = {}
    for row in reference.itertuples():
        ref_by_name_pos.setdefault(row.normalized_name, []).append((row.position, row.player_id))

    unresolved = salaries["player_id"].isna()
    for idx, row in salaries[unresolved].iterrows():
        equiv_positions = POSITION_EQUIVALENTS.get(row["position_upper"], {row["position_upper"]})
        candidates = ref_by_name_pos.get(row["normalized_name"], [])
        hits = list({pid for pos, pid in candidates if pos in equiv_positions})
        if len(hits) == 1:
            salaries.at[idx, "player_id"] = hits[0]
            salaries.at[idx, "match_method"] = "auto_fallback_team_mismatch"
            salaries.at[idx, "match_confidence"] = "medium"
        elif len(hits) > 1:
            salaries.at[idx, "match_method"] = "ambiguous_multiple_candidates"
            salaries.at[idx, "match_confidence"] = "low"

    # --- 5. Last resort: name-only, ANY position -- catches site position
    # mislabels nflverse doesn't share (e.g. a blocking TE listed as "RB").
    # Only applied when the name uniquely resolves across the whole
    # reference table, so it can't silently pick the wrong same-named player.
    unresolved = salaries["player_id"].isna()
    for idx, row in salaries[unresolved].iterrows():
        candidates = ref_by_name_pos.get(row["normalized_name"], [])
        unique_ids = {pid for _, pid in candidates}
        if len(unique_ids) == 1:
            salaries.at[idx, "player_id"] = next(iter(unique_ids))
            salaries.at[idx, "match_method"] = "auto_fallback_name_only_position_mismatch"
            salaries.at[idx, "match_confidence"] = "low"

    return salaries


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", required=True, choices=["dk", "fd"])
    parser.add_argument("--raw", required=True, help="Path to raw salary CSV")
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--slate-id", required=True, help="e.g. classic_wk1")
    parser.add_argument("--weekly-stats", default=None,
                         help="Override path to weekly_stats parquet (default: data/weekly_stats_{season}.parquet)")
    parser.add_argument("--name-mapping", default="data/name_mapping.csv")
    parser.add_argument("--out-dir", default="data")
    parser.add_argument("--log-dir", default="logs")
    args = parser.parse_args()

    raw_path = Path(args.raw)
    weekly_stats_path = Path(args.weekly_stats) if args.weekly_stats else Path(
        f"data/weekly_stats_{args.season}.parquet"
    )
    name_mapping_path = Path(args.name_mapping)
    out_path = Path(args.out_dir) / f"salaries_{args.site}_{args.slate_id}.csv"
    unmatched_path = Path(args.log_dir) / f"unmatched_salaries_{args.site}_{args.slate_id}.csv"

    salaries = load_raw_salary_csv(raw_path, args.site)
    reference = build_player_reference(weekly_stats_path)
    name_mapping = load_name_mapping(name_mapping_path, args.site)

    matched = match_players(salaries, reference, name_mapping, args.site)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    unmatched_path.parent.mkdir(parents=True, exist_ok=True)
    matched.to_csv(out_path, index=False)

    unmatched = matched[matched["player_id"].isna()]
    unmatched.to_csv(unmatched_path, index=False)

    total = len(matched)
    n_matched = total - len(unmatched)
    print(f"[{SITE_CONFIGS[args.site]['label']}] Ingested {total} rows from {raw_path.name}")
    print(f"  Matched:   {n_matched} ({n_matched / total:.1%})")
    print(f"  Unmatched: {len(unmatched)} ({len(unmatched) / total:.1%}) -> {unmatched_path}")
    if len(unmatched):
        print("  Unmatched players (add these to data/name_mapping.csv once you've "
              "found the correct player_id):")
        for name in unmatched["name"].tolist():
            print(f"    - {name}")
    print(f"Wrote {out_path}")

    if len(unmatched):
        sys.exit(1)


if __name__ == "__main__":
    main()
