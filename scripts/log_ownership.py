"""
log_ownership.py
================

Session 9.3 -- Actual Ownership Logging.

Logs real post-lock DFS ownership percentages alongside this pipeline's
pre-lock estimates, building the dataset Sessions 11.1 and 11.2 will fit
ownership model parameters against.

Schema defined in Session 11.0 (see ROADMAP.md's Session 9.3 card and
SESSION_LOG.md's Session 11.0 entry). That schema is fixed before the
first real ownership number is logged -- contest_type, field_size, and
slate_type cannot be retrofitted from old data and are required for
Sessions 11.1 and 11.3.

USAGE
-----

Log ownership from a specific contest/week:

    python scripts/log_ownership.py \\
        --site dk \\
        --season 2026 \\
        --week 1 \\
        --slate-type regular_season \\
        --contest-type single_entry_gpp \\
        --field-size 150000 \\
        --input data/ownership_raw_dk_2026_wk1.csv

The raw input is a two-column CSV (player_name, actual_ownership_pct)
manually copied from the DK/FD contest results page. The script matches
players to the pipeline's player_id via the most recent final_projections
file for that site/week, joins in the pre-lock estimated_ownership_pct
from chalk_scores_{site}_{week}.csv, and appends all rows to
data/ownership_actual_log.csv.

For the Millionaire Maker and similar large-field GPPs, DraftKings posts
ownership percentages on the contest results page after lock. FanDuel does
the same on their My Contests page. Copy player names and percentages into
a two-column CSV manually -- there is no stable API for this.

SLATE_TYPE VALUES
-----------------
  regular_season   -- NFL regular season slate (weeks 1-18). ONLY these
                      rows count toward Sessions 11.1 and 11.2's data gate.
  preseason        -- Preseason Week 1-3. Log for pipeline validation only.
                      Excluded from all model fits (field skewed toward
                      hardcore grinders, player pool unrepresentative).
  madden_sim       -- DK Madden Sim slate. Log only for confirming the
                      script runs end-to-end. Excluded from all fits.

CONTEST_TYPE VALUES
-------------------
  cash               -- Double-ups, 50/50s, head-to-head.
  single_entry_gpp   -- Large-field GPPs with one entry per user (e.g.
                        DK Millionaire Maker). Highest-quality ownership data.
  3max_gpp           -- GPPs allowing up to 3 entries.

If contest_type can't be determined from the source, pass "unknown". These
rows are logged but excluded from per-type stratification fits (Session 11.3).

OUTPUT SCHEMA (data/ownership_actual_log.csv)
---------------------------------------------
site                      -- dk | fd
season                    -- e.g. 2026
week                      -- NFL week number
slate_type                -- regular_season | preseason | madden_sim
contest_id                -- platform's own contest identifier (optional,
                              "" if unavailable)
contest_type              -- cash | single_entry_gpp | 3max_gpp | unknown
field_size                -- number of entries in the contest (integer)
player_id                 -- nflverse player_id (matched via name lookup)
player_name               -- as it appears in the raw ownership source
actual_ownership_pct      -- real post-lock ownership percentage (0-100)
estimated_ownership_pct_at_lock -- pipeline's pre-lock estimate from
                              chalk_scores_{site}_{week}.csv
source                    -- human-readable description of where the actual
                              ownership data came from (e.g.
                              "DK Millionaire Maker results page 2026-09-14")
logged_at                 -- ISO timestamp when this row was appended

MATCHING
--------
Players are matched by normalized name against final_projections_{site}_{week}.csv
(which carries player_id from the salary ingestion step). The same
normalize_name() function used throughout this pipeline is used here, so
existing name_mapping.csv overrides apply.

Unmatched players (names that don't resolve to a player_id) are logged to
data/ownership_unmatched_{site}_{season}_wk{week}.csv rather than dropped
silently -- same fail-loud pattern as ingest_salaries.py. They do NOT enter
the main log.

DECISIONS
---------

1. APPEND, NOT OVERWRITE. ownership_actual_log.csv grows weekly. Running
   this script twice for the same (site, season, week, contest_id) detects
   the duplicate by checking existing rows and raises a clear error rather
   than silently doubling the data. If contest_id is "" (not available),
   the duplicate check uses (site, season, week, slate_type, contest_type)
   instead.

2. ESTIMATED OWNERSHIP IS CAPTURED AT LOG TIME from the chalk_scores file.
   The chalk_scores file for a given week is overwritten on every projection
   rebuild -- after lock, it reflects the final pre-lock state, which is
   what we want. Logging immediately after lock is the correct workflow.
   If chalk_scores_{site}_{week}.csv doesn't exist, estimated_ownership_pct
   is recorded as NaN with a warning rather than blocking the log -- real
   actuals are more important than the estimate column.

3. PLAYER_ID IS THE JOIN KEY for Sessions 11.1/11.2. Name matching here
   uses normalize_name() + the most recent final_projections file (which
   already has player_id matched). DST/DEF rows match on team name since
   defenses have a synthetic player_id format.

4. SLATE_TYPE IS REQUIRED AND VALIDATED. It is not inferred from the week
   number -- preseason weeks 1-3 and regular-season week 1 both start at
   "week 1," and Madden Sim slates can run any time. The caller must pass
   the correct type explicitly.

5. THIS SCRIPT WRITES TO DATA/, NOT OUTPUT/. ownership_actual_log.csv is
   a growing dataset that must persist across weeks and be committed to the
   repo -- it is not a per-run output that gets regenerated. Same treatment
   as name_mapping.csv, salary_anchor_dk.json, etc.
"""

import argparse
import csv
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUT_DIR = REPO_ROOT / "output"
SCRIPTS_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(SCRIPTS_DIR))
from ingest_salaries import normalize_name, SITE_CONFIGS  # noqa: E402

LOG_PATH = DATA_DIR / "ownership_actual_log.csv"

LOG_COLUMNS = [
    "site", "season", "week", "slate_type", "contest_id", "contest_type",
    "field_size", "player_id", "player_name", "actual_ownership_pct",
    "estimated_ownership_pct_at_lock", "source", "logged_at",
]

VALID_SLATE_TYPES = {"regular_season", "preseason", "madden_sim"}
VALID_CONTEST_TYPES = {"cash", "single_entry_gpp", "3max_gpp", "unknown"}


# ---------------------------------------------------------------------------
# Log file management
# ---------------------------------------------------------------------------

def load_log() -> pd.DataFrame:
    """Load existing log, or return an empty DataFrame with the right schema."""
    if not LOG_PATH.exists():
        return pd.DataFrame(columns=LOG_COLUMNS)
    df = pd.read_csv(LOG_PATH, dtype={"season": int, "week": int,
                                       "field_size": int, "player_id": str})
    missing = set(LOG_COLUMNS) - set(df.columns)
    if missing:
        raise SystemExit(
            f"{LOG_PATH} is missing expected columns: {sorted(missing)}. "
            f"Has the schema changed? Expected: {LOG_COLUMNS}."
        )
    return df


def check_duplicate(existing: pd.DataFrame, site: str, season: int, week: int,
                    slate_type: str, contest_type: str, contest_id: str) -> None:
    """Raise if this (site, season, week, contest) combination is already logged.

    Decision #1: duplicate detection. Uses contest_id when present; falls back
    to (site, season, week, slate_type, contest_type) when contest_id is empty.
    """
    if existing.empty:
        return
    if contest_id:
        mask = (
            (existing["site"] == site) &
            (existing["season"] == season) &
            (existing["week"] == week) &
            (existing["contest_id"] == contest_id)
        )
        key_desc = f"site={site}, season={season}, week={week}, contest_id={contest_id!r}"
    else:
        mask = (
            (existing["site"] == site) &
            (existing["season"] == season) &
            (existing["week"] == week) &
            (existing["slate_type"] == slate_type) &
            (existing["contest_type"] == contest_type)
        )
        key_desc = (f"site={site}, season={season}, week={week}, "
                    f"slate_type={slate_type}, contest_type={contest_type}")

    if mask.any():
        n = int(mask.sum())
        raise SystemExit(
            f"Duplicate detected: {n} row(s) already in {LOG_PATH} for "
            f"{key_desc}. If you want to re-log this contest, manually "
            f"remove the existing rows from the CSV first. This error "
            f"prevents silently doubling the data (decision #1)."
        )


# ---------------------------------------------------------------------------
# Raw ownership input parsing
# ---------------------------------------------------------------------------

def load_raw_ownership(path: Path) -> pd.DataFrame:
    """Load the manually-prepared two-column ownership CSV.

    Expected columns: player_name, actual_ownership_pct.
    Ownership values may be expressed as "23.4%" or "23.4" -- both accepted.
    Extra columns are silently ignored.
    """
    df = pd.read_csv(path)
    if "player_name" not in df.columns or "actual_ownership_pct" not in df.columns:
        raise SystemExit(
            f"Raw ownership CSV at {path} must have columns 'player_name' and "
            f"'actual_ownership_pct'. Columns found: {sorted(df.columns)}."
        )
    # Strip trailing "%" if present
    df["actual_ownership_pct"] = (
        df["actual_ownership_pct"]
        .astype(str)
        .str.rstrip("%")
        .pipe(pd.to_numeric, errors="coerce")
    )
    bad = df["actual_ownership_pct"].isna()
    if bad.any():
        bad_names = df.loc[bad, "player_name"].tolist()
        raise SystemExit(
            f"Could not parse actual_ownership_pct for {len(bad_names)} player(s): "
            f"{bad_names[:5]}{'...' if len(bad_names) > 5 else ''}. "
            f"Values must be numeric (e.g. '23.4' or '23.4%')."
        )
    out_of_range = (df["actual_ownership_pct"] < 0) | (df["actual_ownership_pct"] > 100)
    if out_of_range.any():
        raise SystemExit(
            f"{int(out_of_range.sum())} ownership value(s) are outside [0, 100]. "
            f"Check the source data."
        )
    return df[["player_name", "actual_ownership_pct"]].copy()


# ---------------------------------------------------------------------------
# Player matching
# ---------------------------------------------------------------------------

def build_name_to_player_id(site: str, season: int, week: int) -> pd.DataFrame:
    """Build a normalized-name -> player_id lookup from final_projections.

    Falls back to chalk_scores if final_projections doesn't exist for the
    target week. Returns a DataFrame with columns:
      normalized_name, player_id, player_name (canonical), position
    """
    proj_path = OUTPUT_DIR / f"final_projections_{site}_{week}.csv"
    chalk_path = OUTPUT_DIR / f"chalk_scores_{site}_{week}.csv"

    if proj_path.exists():
        ref = pd.read_csv(proj_path, dtype={"player_id": str,
                                             "site_player_id": str})
        source = proj_path.name
    elif chalk_path.exists():
        ref = pd.read_csv(chalk_path, dtype={"player_id": str})
        source = chalk_path.name
    else:
        raise SystemExit(
            f"No projection file found for site={site}, week={week}. "
            f"Looked for:\n  {proj_path}\n  {chalk_path}\n"
            f"Run build_projections.py (or ownership_heuristic.py) for this "
            f"site/week before logging ownership."
        )

    print(f"Loaded {len(ref)} player reference rows from {source}.")
    ref = ref.dropna(subset=["player_id"])
    ref["normalized_name"] = ref["player_name"].map(normalize_name)
    return ref[["normalized_name", "player_id", "player_name", "position"]].copy()


def load_chalk_estimates(site: str, week: int) -> pd.Series:
    """Load estimated_ownership_pct from chalk_scores_{site}_{week}.csv.

    Returns a Series indexed by player_id. Returns an empty Series with a
    warning if the file doesn't exist (decision #2).
    """
    chalk_path = OUTPUT_DIR / f"chalk_scores_{site}_{week}.csv"
    if not chalk_path.exists():
        print(
            f"WARNING: {chalk_path} not found. estimated_ownership_pct_at_lock "
            f"will be NaN for all players this run. Log immediately after lock "
            f"before the chalk_scores file is regenerated for a future week.",
            file=sys.stderr,
        )
        return pd.Series(dtype=float)
    chalk = pd.read_csv(chalk_path, dtype={"player_id": str})
    return chalk.set_index("player_id")["estimated_ownership_pct"]


def match_ownership_rows(raw: pd.DataFrame, ref: pd.DataFrame,
                         site: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Match raw ownership rows to player_id via normalized name.

    Returns (matched_df, unmatched_df).

    DST/DEF rows are matched by team abbreviation embedded in the player name
    (e.g. "Kansas City Chiefs D/ST" -> team "KC") rather than normalized name,
    since defense names vary widely across platforms.
    """
    defense_values = SITE_CONFIGS[site]["defense_position_values"]
    ref_skill = ref[~ref["position"].str.upper().isin(defense_values)].copy()
    ref_dst = ref[ref["position"].str.upper().isin(defense_values)].copy()

    matched_rows, unmatched_rows = [], []

    for _, row in raw.iterrows():
        raw_name = str(row["player_name"]).strip()
        actual_pct = row["actual_ownership_pct"]
        norm = normalize_name(raw_name)

        # Try skill-player exact normalized match first
        skill_hit = ref_skill[ref_skill["normalized_name"] == norm]
        if len(skill_hit) == 1:
            matched_rows.append({
                "raw_name": raw_name,
                "player_id": skill_hit.iloc[0]["player_id"],
                "player_name": skill_hit.iloc[0]["player_name"],
                "actual_ownership_pct": actual_pct,
            })
            continue

        # Try DST match: look for a team abbreviation in the raw name
        dst_match = _match_dst(raw_name, ref_dst, site)
        if dst_match is not None:
            matched_rows.append({
                "raw_name": raw_name,
                "player_id": dst_match["player_id"],
                "player_name": dst_match["player_name"],
                "actual_ownership_pct": actual_pct,
            })
            continue

        # No match
        unmatched_rows.append({
            "raw_name": raw_name,
            "normalized_name": norm,
            "actual_ownership_pct": actual_pct,
            "reason": "no exact name match in final_projections; not a recognized DST format",
        })

    return pd.DataFrame(matched_rows), pd.DataFrame(unmatched_rows)


def _match_dst(raw_name: str, ref_dst: pd.DataFrame, site: str) -> dict | None:
    """Try to match a raw ownership name to a DST row.

    DK format: "Kansas City Chiefs D/ST", "New England Patriots D/ST"
    FD format:  "Kansas City Chiefs",     "New England Patriots"

    Matches by checking whether any DST row's player_name appears as a
    substring of the raw_name (case-insensitive), which handles both formats.
    Falls back to team abbreviation matching via normalize_name on the
    team portion.
    """
    if ref_dst.empty:
        return None

    raw_lower = raw_name.lower()
    # Remove common DST suffixes before checking
    raw_stripped = re.sub(r"\s*(d/st|dst|defense|def)\s*$", "", raw_lower).strip()

    for _, dst_row in ref_dst.iterrows():
        canonical = str(dst_row["player_name"]).lower()
        canonical_stripped = re.sub(
            r"\s*(d/st|dst|defense|def)\s*$", "", canonical
        ).strip()
        # Match if either the stripped raw name matches the stripped canonical,
        # or the raw name contains the canonical as a substring
        if raw_stripped == canonical_stripped or canonical_stripped in raw_lower:
            return {"player_id": dst_row["player_id"],
                    "player_name": dst_row["player_name"]}
    return None


# ---------------------------------------------------------------------------
# Main logging function
# ---------------------------------------------------------------------------

def log_ownership(
    site: str,
    season: int,
    week: int,
    slate_type: str,
    contest_type: str,
    field_size: int,
    raw_path: Path,
    source: str,
    contest_id: str = "",
) -> None:
    """Core logging function. Append ownership rows to ownership_actual_log.csv."""

    # --- Validate arguments ---
    if slate_type not in VALID_SLATE_TYPES:
        raise SystemExit(
            f"Invalid --slate-type {slate_type!r}. "
            f"Valid values: {sorted(VALID_SLATE_TYPES)}."
        )
    if contest_type not in VALID_CONTEST_TYPES:
        raise SystemExit(
            f"Invalid --contest-type {contest_type!r}. "
            f"Valid values: {sorted(VALID_CONTEST_TYPES)}."
        )
    if field_size < 1:
        raise SystemExit(f"--field-size must be >= 1, got {field_size}.")

    if slate_type in ("preseason", "madden_sim"):
        print(
            f"NOTE: slate_type={slate_type!r}. These rows are logged for pipeline "
            f"validation only and are EXCLUDED from Sessions 11.1 and 11.2 model fits. "
            f"Only regular_season rows count toward the 4-6 week data gate."
        )

    # --- Load existing log and check for duplicates ---
    existing = load_log()
    check_duplicate(existing, site, season, week, slate_type, contest_type, contest_id)

    # --- Load raw ownership input ---
    raw = load_raw_ownership(raw_path)
    print(f"Loaded {len(raw)} raw ownership rows from {raw_path.name}.")

    # --- Build name->player_id reference ---
    ref = build_name_to_player_id(site, season, week)

    # --- Match players ---
    matched, unmatched = match_ownership_rows(raw, ref, site)

    n_total = len(raw)
    n_matched = len(matched)
    n_unmatched = len(unmatched)
    match_pct = 100.0 * n_matched / n_total if n_total else 0.0
    print(f"Matched {n_matched}/{n_total} players ({match_pct:.1f}%).")

    # --- Write unmatched log ---
    if n_unmatched > 0:
        unmatched_path = (DATA_DIR /
                          f"ownership_unmatched_{site}_{season}_wk{week}.csv")
        unmatched.to_csv(unmatched_path, index=False)
        print(
            f"WARNING: {n_unmatched} player(s) could not be matched to a "
            f"player_id and are NOT in the ownership log. "
            f"See {unmatched_path} for details. "
            f"Add overrides to data/name_mapping.csv and re-run if needed.",
            file=sys.stderr,
        )

    if n_matched == 0:
        raise SystemExit(
            "No players matched. The log was not updated. "
            "Check that the raw ownership file uses player names consistent "
            "with the pipeline's salary data for this site/week."
        )

    # --- Load estimated ownership (decision #2) ---
    estimates = load_chalk_estimates(site, week)

    # --- Build log rows ---
    logged_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    new_rows = []
    for _, m in matched.iterrows():
        pid = m["player_id"]
        est = float(estimates.get(pid, float("nan")))
        new_rows.append({
            "site": site,
            "season": season,
            "week": week,
            "slate_type": slate_type,
            "contest_id": contest_id,
            "contest_type": contest_type,
            "field_size": field_size,
            "player_id": pid,
            "player_name": m["player_name"],
            "actual_ownership_pct": m["actual_ownership_pct"],
            "estimated_ownership_pct_at_lock": est,
            "source": source,
            "logged_at": logged_at,
        })

    new_df = pd.DataFrame(new_rows, columns=LOG_COLUMNS)

    # --- Append to log ---
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    combined = pd.concat([existing, new_df], ignore_index=True)
    combined.to_csv(LOG_PATH, index=False)

    # --- Summary ---
    print(f"\nLogged {len(new_rows)} rows to {LOG_PATH}.")
    print(f"  site={site}, season={season}, week={week}, "
          f"slate_type={slate_type}, contest_type={contest_type}")
    print(f"  field_size={field_size:,}, contest_id={contest_id!r}")
    print(f"  source: {source}")

    est_present = new_df["estimated_ownership_pct_at_lock"].notna().sum()
    if est_present < len(new_df):
        print(
            f"  WARNING: estimated_ownership_pct_at_lock is NaN for "
            f"{len(new_df) - est_present} player(s). "
            f"(chalk_scores_{site}_{week}.csv missing or player not in it.)",
            file=sys.stderr,
        )

    total_regular = len(
        combined[combined["slate_type"] == "regular_season"]
    )
    total_pre = len(combined[combined["slate_type"] == "preseason"])
    total_sim = len(combined[combined["slate_type"] == "madden_sim"])
    total_weeks_regular = (
        combined[combined["slate_type"] == "regular_season"]
        .drop_duplicates(subset=["site", "season", "week"])
        .shape[0]
    )
    print(
        f"\nLog totals: {len(combined)} rows total "
        f"({total_regular} regular_season across {total_weeks_regular} week(s), "
        f"{total_pre} preseason, {total_sim} madden_sim)."
    )
    if total_weeks_regular < 4:
        print(
            f"  DATA GATE: {total_weeks_regular}/4 regular-season weeks logged. "
            f"Session 11.1 requires 4-6 weeks of regular_season data before "
            f"fitting ownership model parameters."
        )
    elif total_weeks_regular < 6:
        print(
            f"  DATA GATE: {total_weeks_regular} regular-season week(s) logged. "
            f"Session 11.1 can proceed (minimum 4 weeks met). "
            f"More data (6+ weeks) will improve the fit."
        )
    else:
        print(
            f"  DATA GATE: {total_weeks_regular} regular-season week(s) logged. "
            f"Session 11.1 is well-supported."
        )


# ---------------------------------------------------------------------------
# Query helper
# ---------------------------------------------------------------------------

def print_summary(site: str | None = None) -> None:
    """Print a summary of what's in the log (no modification)."""
    if not LOG_PATH.exists():
        print(f"No log file found at {LOG_PATH}. Nothing has been logged yet.")
        return
    log = pd.read_csv(LOG_PATH, dtype={"season": int, "week": int})
    if site:
        log = log[log["site"] == site]
    if log.empty:
        print(f"Log exists but is empty{' for site=' + site if site else ''}.")
        return
    print(f"\nOwnership log summary ({LOG_PATH}):")
    print(f"  Total rows: {len(log)}")
    for stype in VALID_SLATE_TYPES:
        sub = log[log["slate_type"] == stype]
        if sub.empty:
            continue
        weeks = sub.drop_duplicates(["site", "season", "week"]).shape[0]
        print(f"  {stype}: {len(sub)} rows, {weeks} distinct week(s)")
        if stype == "regular_season" and weeks < 6:
            print(f"    -> {weeks}/6 weeks toward Session 11.1 data gate")
    print()
    by_week = (
        log.groupby(["site", "season", "week", "slate_type", "contest_type"])
        .agg(n_players=("player_id", "count"),
             mean_actual=("actual_ownership_pct", "mean"),
             mean_est=("estimated_ownership_pct_at_lock", "mean"))
        .reset_index()
    )
    print(by_week.to_string(index=False))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Log real post-lock DFS ownership percentages alongside pipeline "
            "estimates. Appends to data/ownership_actual_log.csv."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- log subcommand ---
    log_parser = subparsers.add_parser(
        "log",
        help="Append ownership rows for a specific contest.",
    )
    log_parser.add_argument("--site", choices=["dk", "fd"], required=True)
    log_parser.add_argument(
        "--season", type=int, required=True,
        help="NFL season year (e.g. 2026).",
    )
    log_parser.add_argument(
        "--week", type=int, required=True,
        help="NFL week number (1-18 for regular season).",
    )
    log_parser.add_argument(
        "--slate-type",
        choices=sorted(VALID_SLATE_TYPES),
        required=True,
        help=(
            "regular_season: counts toward 11.1 data gate. "
            "preseason/madden_sim: pipeline validation only, excluded from fits."
        ),
    )
    log_parser.add_argument(
        "--contest-type",
        choices=sorted(VALID_CONTEST_TYPES),
        required=True,
        help="cash | single_entry_gpp | 3max_gpp | unknown.",
    )
    log_parser.add_argument(
        "--field-size", type=int, required=True,
        help="Number of entries in the contest.",
    )
    log_parser.add_argument(
        "--input", type=Path, required=True,
        help=(
            "Path to a two-column CSV: player_name, actual_ownership_pct. "
            "Ownership values may be '23.4' or '23.4%%'."
        ),
    )
    log_parser.add_argument(
        "--source", required=True,
        help=(
            "Human-readable description of where the ownership data came from "
            "(e.g. 'DK Millionaire Maker results page 2026-09-14')."
        ),
    )
    log_parser.add_argument(
        "--contest-id", default="",
        help=(
            "Platform's own contest identifier, if available. Used for "
            "duplicate detection. Leave empty if unavailable."
        ),
    )

    # --- summary subcommand ---
    summary_parser = subparsers.add_parser(
        "summary",
        help="Print a summary of what has been logged so far.",
    )
    summary_parser.add_argument(
        "--site", choices=["dk", "fd"], default=None,
        help="Filter summary to one site.",
    )

    args = parser.parse_args()

    if args.command == "log":
        if not args.input.exists():
            raise SystemExit(
                f"Input file not found: {args.input}. "
                f"Create a two-column CSV (player_name, actual_ownership_pct) "
                f"from the contest results page before running."
            )
        log_ownership(
            site=args.site,
            season=args.season,
            week=args.week,
            slate_type=args.slate_type,
            contest_type=args.contest_type,
            field_size=args.field_size,
            raw_path=args.input,
            source=args.source,
            contest_id=args.contest_id,
        )
    elif args.command == "summary":
        print_summary(site=args.site)


if __name__ == "__main__":
    main()
