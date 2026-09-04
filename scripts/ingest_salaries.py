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
NOT yet verified against a real current-season FD CLASSIC download (no FD
equivalent of DK's Madden Stream exists to test against right now). If a
real FD file's columns don't match SITE_CONFIGS["fd"], the script fails
loudly with expected-vs-actual columns rather than silently misparsing --
fix SITE_CONFIGS here.

===============================================================================
Session 13.2 -- Showdown / Single-Game Salary Ingest
===============================================================================
Adds --format {classic,showdown} (default "classic"). Backward compatible
for existing consumers -- every column classic mode produced before this
session is unchanged -- but NOT byte-for-byte identical: a new
`slate_format` column ("classic"/"showdown") is now stamped on every row
regardless of format, same precedent as Phase 11's `slate_type` column.
Confirmed via a real regression run (Session 13.2): classic mode with
--format omitted produces the exact same match results, row count, and
pre-existing columns against a real classic file as before this session's
changes -- only the one additive column differs.

REAL DATA USED THIS SESSION (both sites -- user-supplied live Thursday
08/06/2026 CAR@ARI preseason Showdown/Single-Game exports, not synthetic):
this replaced two assumptions in the original roadmap card that measured
FALSE against real files:

  1. The card's premise "both sites' Showdown exports list each player
     TWICE" is only true for DK. FD's real Single Game export is ONE ROW
     PER PLAYER, carrying both a "Salary" (FLEX-priced) column and an
     "MVP 1.5x Salary" column on the same row -- there is no second row.
  2. DK's Position column retains the player's TRUE position (QB/RB/WR/
     TE/K/DST) on BOTH the CPT and FLEX row -- it is NOT overwritten to
     "CPT"/"FLEX" the way the Roster Position column is. This means the
     EXISTING (name, team, position) matching pipeline works completely
     unchanged for DK Showdown; no fallback matching strategy was needed.

Because of #1, this script NORMALIZES both sites' OUTPUT to two rows per
player (one FLEX-priced, one CPT/MVP-priced), regardless of the raw input
shape -- this matches the output contract the roadmap card itself specifies
("same shape as classic output plus a roster_role ... column distinguishing
the two rows per player") and keeps Sessions 13.3/13.4 site-agnostic, the
same way this script already normalizes classic DK/FD differences today.

RESOLVED DURING THIS SESSION (was an open question, confirmed before
close-out, not deferred to 13.4): user-supplied screenshots of a LIVE FD
Single Game roster builder (same CAR@ARI slate) confirm FD's MVP slot
DOES cost 1.5x salary -- same mechanic as DK's CPT, not the "same as
FLEX" rule ROADMAP.md's Phase 13 intro had previously stated. Verified
directly against the live cap math, not just inferred from the export
file: MVP $12,000 + 5 FLEX x $8,000 = $52,000 of the $60,000 cap, leaving
exactly $8,000 remaining -- matches the live "Salary Remaining" readout
exactly. **ROADMAP.md's Phase 13 "confirmed rule" for FD was WRONG and
needs correcting** when ROADMAP.md is updated to close this session.
Session 13.4 can treat both sites' cap math as identical (1.5x salary AND
1.5x points for the captain-equivalent slot) -- no further verification
needed there.

DK Showdown roster: 1 CPT + 5 FLEX (6 total), captain scores 1.5x AND costs
1.5x the FLEX salary (MEASURED: real file's CPT salary / FLEX salary =
11400 / 7600 = 1.5 exactly). FD Single Game roster: 1 MVP + 4 FLEX (5
total), MVP scores 1.5x (salary question above still open). Both sites:
exactly 2 teams, minimum 1 player per team (Phase 13 intro's confirmed
rules) -- this script validates the ingested pool has exactly 2 teams when
--format showdown and fails loudly otherwise.

Showdown usage:
  python scripts/ingest_salaries.py \
      --site dk --format showdown \
      --raw data/raw_salaries/DKSalaries_showdown.csv \
      --season 2025 --slate-id showdown_car_ari_wk1

  python scripts/ingest_salaries.py \
      --site fd --format showdown \
      --raw data/raw_salaries/FDSalaries_showdown.csv \
      --season 2025 --slate-id showdown_car_ari_wk1

Showdown output adds two columns beyond classic's player_id/match_method/
match_confidence: `roster_role` (raw site role label -- "CPT"/"FLEX" for
DK, "MVP"/"FLEX" for FD) and `slate_format` ("classic" or "showdown",
stamped on every row so downstream scripts can branch on one column
instead of re-deriving it). The SAME player_id appears on both of a
player's two rows -- that IS the CPT/FLEX or MVP/FLEX link; no separate
linking table is needed, same principle as how classic DST rows already
share a synthetic "DST_{team}" id instead of a real player_id.
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
        # Session 13.2 -- Showdown/Captain Mode. Nested here (not a
        # restructure of the flat keys above into SITE_CONFIGS[site][format])
        # on purpose: 9 other scripts already read SITE_CONFIGS[site][key]
        # flat, assuming classic. Nesting only the showdown-specific delta
        # keeps every existing consumer byte-identical and untouched.
        "showdown": {
            "roster_position_col": "Roster Position",   # MEASURED real file: carries "CPT"/"FLEX" per row
            "captain_role_value": "CPT",
            "flex_role_value": "FLEX",
            # MEASURED against real 08/06/2026 CAR@ARI file: every CPT row
            # salary (11400) / its paired FLEX row salary (7600) = 1.5
            # exactly. Real per-row salaries are captured as-is; this is
            # only used for a soft validation warning, not to compute salary.
            "captain_salary_multiplier": 1.5,
            "captain_score_multiplier": 1.5,   # confirmed, ROADMAP.md Phase 13 intro + Session 13.1 kicker validation
            "roster_slots": ["CPT", "FLEX", "FLEX", "FLEX", "FLEX", "FLEX"],
            "salary_cap": 50000,   # unchanged from classic, per Phase 13 intro
            "n_teams": 2,
            "min_per_team": 1,
            # DK's real Showdown export already lists each player TWICE
            # (one CPT row, one FLEX row) -- MEASURED, no expansion needed.
            "row_shape": "two_rows_per_player",
        },
    },
    "fd": {
        "label": "FanDuel",
        # CONFIRMED against a real FD Classic Week 1 2026 export (site work,
        # 2026-08-11): Id, Position, First Name, Nickname, Last Name, FPPG,
        # Played, Salary, Game, Team, Opponent, Injury Indicator, Injury
        # Details, Tier. Real position values for defenses are "D" (see
        # defense_position_values below and optimizer.py's canonicalization
        # of it) -- everything else here matched the previously-documented
        # guess exactly.
        "required_columns": {"Position", "Team", "Salary"},
        "name_col": None,   # derived from First Name/Last Name/Nickname
        "team_col": "Team",
        "position_col": "Position",
        "salary_col": "Salary",
        # Session 7.3 addition -- same purpose as dk's site_id_col above.
        # CONFIRMED against the same real export above -- "Id" is the
        # literal first column.
        "site_id_col": "Id",
        # FD names the season-average PPG column "FPPG" (not "AvgPointsPerGame"
        # like DK). CONFIRMED against the same real export above.
        "avg_ppg_col": "FPPG",
        "defense_position_values": {"D", "DEF"},
        "team_abbrev_overrides": {},
        "salary_cap": 60000,
        "roster_slots": ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DEF"],
        "scoring": "half_ppr",   # 0.5 pt/reception
        # Session 13.2 -- Single Game. See dk's "showdown" key above for why
        # this is nested rather than a full SITE_CONFIGS restructure.
        "showdown": {
            # MEASURED real file: FD does NOT duplicate rows like DK --
            # ONE row per player, carrying both a base "Salary" column and
            # an "MVP 1.5x Salary" column on that same row. roster_position_col
            # is NOT role-distinguishing here (every row reads literally
            # "MVP - 1.5X Points/AnyFLEX" since one row covers both
            # eligibilities) -- kept as a raw passthrough only, not used
            # to derive roster_role the way DK's is.
            "roster_position_col": "Roster Position",
            "mvp_salary_col": "MVP 1.5x Salary",   # MEASURED real column name/casing
            "captain_role_value": "MVP",
            "flex_role_value": "FLEX",
            # CONFIRMED, not just measured from the export -- user-supplied
            # screenshots of a LIVE FD roster builder verified the 1.5x
            # salary deduction actually happens against the real $60,000
            # cap (see module docstring). ROADMAP.md's Phase 13 "confirmed
            # rule" that FD's MVP costs the SAME salary as FLEX was WRONG;
            # corrected here and in ROADMAP.md at session close-out.
            "captain_salary_multiplier": 1.5,   # CONFIRMED against a live FD roster builder, same mechanic as DK's CPT
            "captain_score_multiplier": 1.5,   # confirmed, ROADMAP.md Phase 13 intro + Session 13.1 kicker validation
            # Bug fix (found live, Sep 2026): this read ["MVP","FLEX","FLEX",
            # "FLEX","FLEX"] -- 5 total roster spots. A real FD Single Game
            # contest has 1 MVP + 5 FLEX = 6 total (confirmed against a live
            # FD Showdown contest, Sep 2026). The 5-slot version was carried
            # over from early development and never re-verified against a
            # real 6-man FD Showdown contest -- see DK's own "showdown"
            # block above, which already had the correct 1+5=6 shape.
            "roster_slots": ["MVP", "FLEX", "FLEX", "FLEX", "FLEX", "FLEX"],
            "salary_cap": 60000,   # unchanged from classic, per Phase 13 intro
            "n_teams": 2,
            "min_per_team": 1,
            "row_shape": "one_row_per_player",   # MEASURED -- contradicts the roadmap card's speculative "both sites list twice" premise
        },
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


def _prepare_dk_showdown(df: pd.DataFrame, site: str) -> pd.DataFrame:
    """DK's real Showdown export already has 2 rows/player (row_shape =
    two_rows_per_player, MEASURED) -- no expansion needed. Just validate
    the shape assumption holds and tag `roster_role` from the real
    Roster Position column values."""
    cfg = SITE_CONFIGS[site]["showdown"]
    col = cfg["roster_position_col"]
    if col not in df.columns:
        raise SystemExit(
            f"--format showdown was requested for site=dk but the raw file "
            f"has no '{col}' column (found: {sorted(df.columns)}). This "
            f"doesn't look like a real DK Showdown export -- check the "
            f"downloaded file, or omit --format showdown for a classic file."
        )
    df = df.copy()
    df["roster_role"] = df[col]
    known_roles = {cfg["captain_role_value"], cfg["flex_role_value"]}
    unknown = set(df["roster_role"].unique()) - known_roles
    if unknown:
        raise SystemExit(
            f"DK Showdown file's '{col}' column has unexpected value(s) "
            f"{sorted(unknown)} -- expected only {sorted(known_roles)}. "
            f"DK may have changed its export format; update "
            f"SITE_CONFIGS['dk']['showdown'] to match."
        )
    return df


def _prepare_fd_showdown(df: pd.DataFrame, site: str) -> pd.DataFrame:
    """FD's real Single Game export is ONE row/player (row_shape =
    one_row_per_player, MEASURED -- contradicts the roadmap card's
    speculative "both sites list twice" premise). Expand into 2 output
    rows (FLEX-priced + MVP-priced) so downstream sessions see the same
    two-rows-per-player shape as DK, per this script's own output
    contract."""
    cfg = SITE_CONFIGS[site]["showdown"]
    mvp_col = cfg["mvp_salary_col"]
    if mvp_col not in df.columns:
        raise SystemExit(
            f"--format showdown was requested for site=fd but the raw file "
            f"has no '{mvp_col}' column (found: {sorted(df.columns)}). This "
            f"doesn't look like a real FD Single Game export -- check the "
            f"downloaded file, or omit --format showdown for a classic file."
        )
    salary_col = SITE_CONFIGS[site]["salary_col"]

    flex_rows = df.copy()
    flex_rows["roster_role"] = cfg["flex_role_value"]
    # salary_col already holds the FLEX-priced value -- nothing to change.

    mvp_rows = df.copy()
    mvp_rows["roster_role"] = cfg["captain_role_value"]
    mvp_rows[salary_col] = mvp_rows[mvp_col]   # overwrite Salary with the MVP-priced value for this synthesized row

    # NOTE: both synthesized rows carry the SAME raw site_id_col value
    # (FD's real file only has one "Id" per player -- there's no second id
    # to give the MVP row). This is faithful to reality, not a bug, but a
    # future session building an FD upload-template feature (the DK
    # equivalent already exists per site_id_col's module docstring note)
    # needs to know FD's own upload format likely expects one id per
    # player + a separate role designation, not two distinct ids like DK.
    return pd.concat([flex_rows, mvp_rows], ignore_index=True)


def _validate_showdown_pool(df: pd.DataFrame, site: str) -> None:
    """Fail loud (not silently) if the ingested pool doesn't look like a
    real single-game slate -- per Phase 13's confirmed rule of exactly 2
    teams. Also soft-warns (does not crash) on DK's captain salary
    multiplier deviating from the measured 1.5x, since real differentiated
    pricing might round slightly differently than the flat test-slate
    pricing this was measured against."""
    cfg = SITE_CONFIGS[site]["showdown"]
    n_teams = df["normalized_team"].nunique()
    expected = cfg["n_teams"]
    if n_teams != expected:
        raise SystemExit(
            f"--format showdown expects exactly {expected} teams in the "
            f"pool (Phase 13's confirmed single-game rule) but found "
            f"{n_teams}: {sorted(df['normalized_team'].unique())}. Check "
            f"this is really a Showdown/Single-Game export, not classic."
        )

    if site == "dk":
        mult = cfg["captain_salary_multiplier"]
        pairs = df.dropna(subset=["player_id"]).groupby("player_id")
        bad = []
        for pid, g in pairs:
            if set(g["roster_role"]) != {cfg["captain_role_value"], cfg["flex_role_value"]}:
                continue  # incomplete pair -- covered by the unmatched/role-count check in main()
            cpt_sal = g.loc[g["roster_role"] == cfg["captain_role_value"], "salary"].iloc[0]
            flex_sal = g.loc[g["roster_role"] == cfg["flex_role_value"], "salary"].iloc[0]
            # Tolerance 0.05 (not 0.01): real file matched the multiplier
            # EXACTLY (11400/7600=1.5), but salaries independently rounded
            # to the nearest $100 (both real exports and this project's own
            # synthetic generator round that way) can drift a ratio by a
            # few percent at the low end of the salary range without any
            # actual bug -- confirmed by testing this check against
            # generate_synthetic_slate.py's own showdown output.
            if flex_sal and abs(cpt_sal / flex_sal - mult) > 0.05:
                bad.append((pid, cpt_sal, flex_sal))
        if bad:
            print(f"  WARNING: {len(bad)} player(s) have a CPT/FLEX salary "
                  f"ratio != {mult} (expected from the measured rule) -- "
                  f"first few: {bad[:5]}")


def load_raw_salary_csv(path: Path, site: str, fmt: str = "classic") -> pd.DataFrame:
    if site == "dk":
        df = _load_dk_raw(path)
    elif site == "fd":
        df = _load_fd_raw(path)
    else:
        raise SystemExit(f"Unknown site '{site}' -- expected 'dk' or 'fd'.")

    cfg = SITE_CONFIGS[site]

    if fmt == "showdown":
        if site == "dk":
            df = _prepare_dk_showdown(df, site)
        else:
            df = _prepare_fd_showdown(df, site)

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
    df["slate_format"] = fmt
    return df


# ---------------------------------------------------------------------------
# Step 2: Build the player reference table from Session 1.2's weekly_stats
# ---------------------------------------------------------------------------

def build_player_reference(weekly_stats_path: Path,
                           weekly_rosters_path: Path | None = None) -> pd.DataFrame:
    """Decision #X (Session 13.5-pause Bug Fix B): `weekly_rosters_path` is
    new. Before this fix, the whole matching universe came from
    weekly_stats -- players with >=1 logged snap that season. A true
    rookie or anyone with zero snaps has no row there at all, so
    name_mapping.csv (which can only redirect an existing row, never
    manufacture a new one) could never resolve them, and build_projections
    .py's `players[players["player_id"].notna()]` gate silently dropped
    them downstream. The cold-start salary-anchor blend (Session 10.0-
    10.2) already exists specifically for zero-history players -- it just
    never got a chance to run, because this gate filtered them out first.
    Confirmed real via a real DK preseason ingest this session: Carson
    Beck (2026 draft prospect, ARI's real starting QB per the salary file)
    and 43 others, 34.9% unmatched.

    weekly_rosters' player-identifier column is `gsis_id`, not `player_id`
    -- CONFIRMED the same ID scheme/values as weekly_stats' `player_id`
    (verified against real 2025 data this session: Patrick Mahomes'
    gsis_id and player_id are both '00-0033873'; ingest_historical.py's
    Session 1.2 ROSTER_KEY comment independently confirms the same thing).
    No crosswalk file needed -- gsis_id IS player_id, just a differently-
    named column.
    """
    # Decision #Y (Session 15.3): weekly_stats_path can now be GENUINELY
    # ABSENT -- not just present-but-missing-some-players (this function's
    # original Bug Fix B case above), but the file itself not existing at
    # all. That's the normal state before a season's first game -- the
    # same real condition statline_model.py's load_history() (decision
    # #19) and projections_matchup.py's load_weekly_data() (decision #1)
    # already handle. When it happens, fall through to building the WHOLE
    # reference table from weekly_rosters_path instead of just using it to
    # patch in a few missing rookies -- a roster snapshot needs no games
    # played to exist, unlike weekly stats. If weekly_rosters_path is ALSO
    # missing or not supplied, there is genuinely no source to build a
    # reference table from, and this still fails loud: silently returning
    # an empty table would mean every caller (status_check.py included)
    # matches zero players against real data without ever saying so.
    if Path(weekly_stats_path).exists():
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
    else:
        if weekly_rosters_path is None or not Path(weekly_rosters_path).exists():
            raise SystemExit(
                f"build_player_reference: neither {weekly_stats_path} nor a usable "
                f"weekly_rosters_path exists -- no source to build a player_id "
                f"reference table from at all. Run scripts/ingest_historical.py "
                f"--season <season> first."
            )
        print(
            f"NOTE: {weekly_stats_path} not found -- treating this as a season "
            f"with no games played yet (same condition statline_model.py's "
            f"load_history() and projections_matchup.py's load_weekly_data() "
            f"already handle). Building the player_id reference table entirely "
            f"from {weekly_rosters_path} instead."
        )
        most_recent = pd.DataFrame(columns=[
            "player_id", "player_display_name", "position", "team",
            "normalized_name", "normalized_team",
        ])

    if weekly_rosters_path is not None and Path(weekly_rosters_path).exists():
        rosters = pd.read_parquet(weekly_rosters_path)
        rosters = rosters.dropna(subset=["gsis_id", "full_name", "position", "team"])
        rosters = rosters.sort_values(["gsis_id", "week"])
        roster_recent = (
            rosters.groupby("gsis_id")
            .tail(1)[["gsis_id", "full_name", "position", "team"]]
            .rename(columns={"gsis_id": "player_id", "full_name": "player_display_name"})
        )
        # Only ADD players weekly_stats doesn't already cover -- a player
        # with real stat history keeps using their weekly_stats row. A
        # roster snapshot can lag an in-season move; weekly_stats reflects
        # where they actually played, which is the more reliable signal
        # when both exist. When weekly_stats was absent entirely (above),
        # `most_recent` starts empty, so every roster player lands here --
        # this is the SAME union logic, just with nothing to compare against.
        new_players = roster_recent[~roster_recent["player_id"].isin(most_recent["player_id"])].copy()
        if len(new_players):
            new_players["normalized_name"] = new_players["player_display_name"].map(normalize_name)
            new_players["normalized_team"] = new_players["team"].map(
                lambda t: BASE_TEAM_ABBREV_MAP.get(str(t).strip().upper(), str(t).strip().upper())
            )
            print(f"build_player_reference: added {len(new_players)} roster-only player(s) "
                  f"with no weekly_stats row (true rookies / zero-snap players, or the "
                  f"entire reference table when weekly_stats itself is absent -- Session "
                  f"15.3) from {weekly_rosters_path}.")
            most_recent = pd.concat([most_recent, new_players], ignore_index=True)
    elif weekly_rosters_path is not None:
        print(f"NOTE: {weekly_rosters_path} not found -- skipping roster-only player "
              f"union (Bug Fix B). Rookies/zero-snap players will still be dropped. "
              f"Run: python3 scripts/ingest_historical.py --season <season>",
              file=sys.stderr)

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
    parser.add_argument("--format", default="classic", choices=["classic", "showdown"],
                         help="Session 13.2 -- 'showdown' for DK Captain Mode / FD Single "
                              "Game exports. Default 'classic' preserves all pre-13.2 "
                              "columns/behavior (adds one new slate_format column only).")
    parser.add_argument("--raw", required=True, help="Path to raw salary CSV")
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--slate-id", required=True, help="e.g. classic_wk1")
    parser.add_argument("--weekly-stats", default=None,
                         help="Override path to weekly_stats parquet (default: data/weekly_stats_{season}.parquet)")
    parser.add_argument("--weekly-rosters", default=None,
                         help="Override path to weekly_rosters parquet, used to catch true "
                              "rookies/zero-snap players missing from weekly_stats (Bug Fix "
                              "B). Default: data/weekly_rosters_{season+1}.parquet -- the "
                              "CURRENT season's roster, not --season's (which is last "
                              "completed season, for stats lookback). Pass --weekly-rosters "
                              "'' explicitly to disable this (pre-fix behavior).")
    parser.add_argument("--name-mapping", default="data/name_mapping.csv")
    parser.add_argument("--out-dir", default="data")
    parser.add_argument("--log-dir", default="logs")
    args = parser.parse_args()

    raw_path = Path(args.raw)
    weekly_stats_path = Path(args.weekly_stats) if args.weekly_stats else Path(
        f"data/weekly_stats_{args.season}.parquet"
    )
    if args.weekly_rosters == "":
        weekly_rosters_path = None
    elif args.weekly_rosters:
        weekly_rosters_path = Path(args.weekly_rosters)
    else:
        # NOT args.season -- this project's established convention (see
        # DFS_Weekly_Process.md / Handoff_13.5_Pause_BugFixes.md) is that
        # --season is always "last completed season" (2025), used for
        # stats-LOOKBACK. Bug Fix B's whole point is catching a CURRENT-
        # season rookie (e.g. a 2026 draft prospect) who has no games in
        # any completed season at all -- defaulting this to weekly_rosters_
        # {args.season}.parquet would silently point at last year's roster,
        # which never has this year's rookies on it, and the fix would look
        # broken for a reason that's easy to miss. current season = last
        # completed season + 1, matching that same established convention.
        weekly_rosters_path = Path(f"data/weekly_rosters_{args.season + 1}.parquet")
    name_mapping_path = Path(args.name_mapping)
    out_path = Path(args.out_dir) / f"salaries_{args.site}_{args.slate_id}.csv"
    unmatched_path = Path(args.log_dir) / f"unmatched_salaries_{args.site}_{args.slate_id}.csv"

    salaries = load_raw_salary_csv(raw_path, args.site, args.format)
    reference = build_player_reference(weekly_stats_path, weekly_rosters_path)
    name_mapping = load_name_mapping(name_mapping_path, args.site)

    matched = match_players(salaries, reference, name_mapping, args.site)

    if args.format == "showdown":
        _validate_showdown_pool(matched, args.site)
        # Confirm CPT/FLEX (or MVP/FLEX) linking worked: every matched
        # player_id should have exactly one row per expected role.
        cfg = SITE_CONFIGS[args.site]["showdown"]
        expected_roles = {cfg["captain_role_value"], cfg["flex_role_value"]}
        role_counts = matched.dropna(subset=["player_id"]).groupby("player_id")["roster_role"].apply(set)
        incomplete = role_counts[role_counts != expected_roles]
        if len(incomplete):
            print(f"  WARNING: {len(incomplete)} matched player(s) don't have both "
                  f"{sorted(expected_roles)} rows linked to the same player_id -- "
                  f"first few: {incomplete.head().to_dict()}")

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
