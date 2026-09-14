"""
log_results.py
===============

Session 9.1 -- Actual-vs-Projected Logging.

Logs real post-game fantasy point outcomes alongside this pipeline's
pre-lock final_projection, building the dataset Session 9.2 (projection
weight retuning) will eventually fit against reality. Mirrors
log_ownership.py's established pattern (Session 9.3) -- same slate-id-keyed
reference lookup, same append/duplicate-detection/unmatched-log shape --
deliberately reusing that pattern rather than inventing a new one.

USAGE
-----

    python scripts/log_results.py \\
        --site dk \\
        --season 2026 \\
        --week 1 \\
        --slate-id dk_classic_wk1_main_13Sep2026 \\
        --slate-type regular_season \\
        --input data/results_raw_dk_2026_wk1.csv \\
        --source "DK contest results export 2026-09-14"

--slate-id must match the --slate-id used when
final_projections_{site}_{slate_id}.csv was built for this slate (the same
value passed to build_projections_statline.py) -- NOT the week number, same
rule as log_ownership.py, for the same reason (a site can have more than
one slate_id active in the same week).

--season/--week here are the REAL NFL season/week (e.g. 2026/1), not the
stats-lookback sentinel (2025/23 for Week 1 of any 2026 slate type) that
build_projections_statline.py itself is called with -- same distinction
log_ownership.py already draws in current_slate.json's own field notes.

RAW INPUT CSV SHAPE
--------------------
Two columns: player_name, actual_fpts

One row per real player who appeared in the slate's actual results (DST
included, one row per team defense). If a site's raw export lists a player
more than once (e.g. DraftKings' contest-results export splits ownership,
but not points, across a player's primary position and FLEX rows), dedupe
to one row per player before handing the file to this script -- actual_fpts
is a single real-world quantity, unlike ownership.

SLATE_TYPE VALUES
-----------------
  regular_season   -- NFL regular season slate (weeks 1-18). ONLY these
                      rows count toward Session 9.2's retuning.
  preseason        -- Preseason Week 1-3. Log for pipeline validation only.
  madden_sim       -- DK Madden Sim slate. Log only for confirming the
                      script runs end-to-end.

OUTPUT SCHEMA (data/projection_error_log.csv)
-----------------------------------------------
site                -- dk | fd
season               -- real NFL season, e.g. 2026
week                 -- real NFL week number
slate_id             -- this slate's own slate_id
slate_type           -- regular_season | preseason | madden_sim
player_id            -- nflverse player_id (matched via name lookup)
player_name          -- as it appears in final_projections (canonical)
position             -- from final_projections
final_projection      -- this pipeline's own pre-lock projection for this
                         player/slate
actual_fpts          -- real post-game fantasy points scored, in this
                         site's own scoring (DK full-PPR, FD half-PPR --
                         never expected to match across sites for the same
                         player)
error                -- actual_fpts - final_projection (positive =
                         pipeline under-projected)
abs_error            -- abs(error)
source               -- human-readable description of where actual_fpts
                         came from
logged_at            -- ISO timestamp when this row was appended

MATCHING
--------
Players are matched by normalized name against
final_projections_{site}_{slate_id}.csv, reusing normalize_name() and the
same DST-by-team-substring matching log_ownership.py already established
(imported from that module rather than re-implemented, to avoid two copies
of the same matching logic silently drifting apart).

Unmatched players are written to
data/results_unmatched_{site}_{slate_id}.csv rather than dropped silently
-- same fail-loud pattern as log_ownership.py / ingest_salaries.py.

DECISIONS
---------

1. APPEND, NOT OVERWRITE, SAME DUPLICATE-DETECTION SHAPE AS
   log_ownership.py. Running this script twice for the same
   (site, season, week, slate_id) is a hard error -- remove the existing
   rows by hand first if a real re-log is intended.

2. NO PER-CONTEST FIELDS (contest_id/contest_type/field_size). Unlike
   ownership, which is genuinely different across contests played the same
   week (chalk in an MME vs. a 3-max), a player's real fantasy points are
   one fact about the slate, not about which contest you entered -- so this
   log is keyed on (site, season, week, slate_id), one row per player per
   slate, independent of how many contests were logged for ownership.

3. FINAL_PROJECTION READ AT LOG TIME, NOT SNAPSHOTTED PRE-LOCK. Reads
   directly from output/final_projections_{site}_{slate_id}.csv as it
   exists on disk when this script runs. Since that file is not regenerated
   after lock (the pipeline has no reason to touch it post-game), the value
   read here is the same one that was live at lock time for any slate that
   hasn't been rebuilt since -- but this script does not independently
   verify that, so re-running build_projections_statline.py for an old
   slate_id before logging its results would silently log the wrong
   projection. Not currently guarded against; flag if this becomes a real
   problem.
"""

import argparse
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
from log_ownership import _match_dst  # noqa: E402

LOG_PATH = DATA_DIR / "projection_error_log.csv"

LOG_COLUMNS = [
    "site", "season", "week", "slate_id", "slate_type", "player_id",
    "player_name", "position", "final_projection", "actual_fpts", "error",
    "abs_error", "source", "logged_at",
]

VALID_SLATE_TYPES = {"regular_season", "preseason", "madden_sim"}


# ---------------------------------------------------------------------------
# Log file management
# ---------------------------------------------------------------------------

def load_log() -> pd.DataFrame:
    """Load existing log, or return an empty DataFrame with the right schema."""
    if not LOG_PATH.exists():
        return pd.DataFrame(columns=LOG_COLUMNS)
    df = pd.read_csv(LOG_PATH, dtype={"season": int, "week": int, "player_id": str})
    missing = set(LOG_COLUMNS) - set(df.columns)
    if missing:
        raise SystemExit(
            f"{LOG_PATH} is missing expected columns: {sorted(missing)}. "
            f"Has the schema changed? Expected: {LOG_COLUMNS}."
        )
    return df


def check_duplicate(existing: pd.DataFrame, site: str, season: int, week: int,
                    slate_id: str) -> None:
    """Raise if this (site, season, week, slate_id) combination is already logged."""
    if existing.empty:
        return
    mask = (
        (existing["site"] == site) &
        (existing["season"] == season) &
        (existing["week"] == week) &
        (existing["slate_id"] == slate_id)
    )
    if mask.any():
        n = int(mask.sum())
        raise SystemExit(
            f"Duplicate detected: {n} row(s) already in {LOG_PATH} for "
            f"site={site}, season={season}, week={week}, slate_id={slate_id!r}. "
            f"If you want to re-log this slate, manually remove the existing "
            f"rows from the CSV first. This error prevents silently doubling "
            f"the data (decision #1)."
        )


# ---------------------------------------------------------------------------
# Raw actual-results input parsing
# ---------------------------------------------------------------------------

def load_raw_results(path: Path) -> pd.DataFrame:
    """Load the manually-prepared actual-results CSV.

    Required columns: player_name, actual_fpts.
    """
    df = pd.read_csv(path)
    required = {"player_name", "actual_fpts"}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(
            f"Raw results CSV at {path} is missing column(s) {sorted(missing)}. "
            f"Columns found: {sorted(df.columns)}. "
            f"Expected shape: player_name, actual_fpts."
        )

    df["actual_fpts"] = pd.to_numeric(df["actual_fpts"], errors="coerce")
    bad = df["actual_fpts"].isna()
    if bad.any():
        bad_names = df.loc[bad, "player_name"].tolist()
        raise SystemExit(
            f"Could not parse actual_fpts for {len(bad_names)} player(s): "
            f"{bad_names[:5]}{'...' if len(bad_names) > 5 else ''}. "
            f"Values must be numeric."
        )

    dupe_names = df["player_name"][df["player_name"].duplicated()].unique()
    if len(dupe_names) > 0:
        raise SystemExit(
            f"Raw results CSV at {path} has {len(dupe_names)} duplicate "
            f"player_name row(s): {list(dupe_names)[:5]}"
            f"{'...' if len(dupe_names) > 5 else ''}. Dedupe to one row per "
            f"player before running this script -- actual_fpts is a single "
            f"real-world quantity per player per slate, unlike ownership."
        )

    return df[["player_name", "actual_fpts"]].copy()


# ---------------------------------------------------------------------------
# Player matching
# ---------------------------------------------------------------------------

def build_reference(site: str, slate_id: str) -> pd.DataFrame:
    """Build a normalized-name -> player_id/position/final_projection lookup.

    Reads directly off final_projections_{site}_{slate_id}.csv, the same
    single source of truth log_ownership.py's build_reference() uses.
    """
    proj_path = OUTPUT_DIR / f"final_projections_{site}_{slate_id}.csv"
    if not proj_path.exists():
        raise SystemExit(
            f"No projection file found at {proj_path}. Run "
            f"build_projections_statline.py for this site/slate before "
            f"logging results -- double check --slate-id matches the slate "
            f"you're logging."
        )

    ref = pd.read_csv(proj_path, dtype={"player_id": str, "site_player_id": str})
    print(f"Loaded {len(ref)} player reference rows from {proj_path.name}.")

    missing_cols = ({"player_id", "player_name", "position",
                     "final_projection"} - set(ref.columns))
    if missing_cols:
        raise SystemExit(
            f"{proj_path} is missing expected column(s): {sorted(missing_cols)}. "
            f"Was this file built by an older version of the pipeline? "
            f"Re-run build_projections_statline.py for this slate."
        )

    ref = ref.dropna(subset=["player_id"])
    ref["normalized_name"] = ref["player_name"].map(normalize_name)
    # Classic slates carry one reference row per player. If a Showdown
    # reference file is ever passed here it has two (CPT/FLEX) rows per
    # player with identical final_projection scaling aside -- collapse to
    # one, since actual_fpts (unlike ownership) is not role-split.
    ref = ref.drop_duplicates(subset=["normalized_name"], keep="first")
    return ref[["normalized_name", "player_id", "player_name", "position",
                "final_projection"]].copy()


def match_results_rows(raw: pd.DataFrame, ref: pd.DataFrame,
                       site: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Match raw actual-results rows to player_id via normalized name.

    Returns (matched_df, unmatched_df). DST rows matched by team-substring,
    same helper log_ownership.py uses for the identical problem.
    """
    defense_values = SITE_CONFIGS[site]["defense_position_values"]
    ref_skill = ref[~ref["position"].str.upper().isin(defense_values)]
    ref_dst = ref[ref["position"].str.upper().isin(defense_values)]

    matched_rows, unmatched_rows = [], []

    for _, row in raw.iterrows():
        raw_name = str(row["player_name"]).strip()
        actual_fpts = row["actual_fpts"]
        norm = normalize_name(raw_name)

        skill_hit = ref_skill[ref_skill["normalized_name"] == norm]
        if len(skill_hit) == 1:
            hit = skill_hit.iloc[0]
            matched_rows.append({
                "player_id": hit["player_id"],
                "player_name": hit["player_name"],
                "position": hit["position"],
                "final_projection": hit["final_projection"],
                "actual_fpts": actual_fpts,
            })
            continue

        # _match_dst() expects estimated_ownership_pct/roster_role keys --
        # build a compatible frame for the shared helper rather than
        # re-implementing DST substring matching here.
        dst_ref = ref_dst.assign(estimated_ownership_pct=ref_dst["final_projection"],
                                  roster_role="")
        dst_match = _match_dst(raw_name, dst_ref, site)
        if dst_match is not None:
            matched_rows.append({
                "player_id": dst_match["player_id"],
                "player_name": dst_match["player_name"],
                "position": "DST",
                "final_projection": dst_match["estimated_ownership_pct"],
                "actual_fpts": actual_fpts,
            })
            continue

        unmatched_rows.append({
            "raw_name": raw_name,
            "normalized_name": norm,
            "actual_fpts": actual_fpts,
            "reason": "no exact name match in final_projections; not a "
                      "recognized DST format",
        })

    return pd.DataFrame(matched_rows), pd.DataFrame(unmatched_rows)


# ---------------------------------------------------------------------------
# Main logging function
# ---------------------------------------------------------------------------

def log_results(
    site: str,
    season: int,
    week: int,
    slate_id: str,
    slate_type: str,
    raw_path: Path,
    source: str,
) -> None:
    """Core logging function. Append result rows to projection_error_log.csv."""

    if slate_type not in VALID_SLATE_TYPES:
        raise SystemExit(
            f"Invalid --slate-type {slate_type!r}. "
            f"Valid values: {sorted(VALID_SLATE_TYPES)}."
        )
    if not slate_id.strip():
        raise SystemExit(
            "--slate-id is required -- it must match the --slate-id used "
            "when final_projections_{site}_{slate_id}.csv was built for "
            "this slate. It is NOT the same thing as --week."
        )

    if slate_type in ("preseason", "madden_sim"):
        print(
            f"NOTE: slate_type={slate_type!r}. These rows are logged for pipeline "
            f"validation only and are EXCLUDED from Session 9.2's retuning. "
            f"Only regular_season rows count."
        )

    ref = build_reference(site, slate_id)

    existing = load_log()
    check_duplicate(existing, site, season, week, slate_id)

    raw = load_raw_results(raw_path)
    print(f"Loaded {len(raw)} raw result rows from {raw_path.name}.")

    matched, unmatched = match_results_rows(raw, ref, site)

    n_total = len(raw)
    n_matched = len(matched)
    n_unmatched = len(unmatched)
    match_pct = 100.0 * n_matched / n_total if n_total else 0.0
    print(f"Matched {n_matched}/{n_total} players ({match_pct:.1f}%).")

    if n_unmatched > 0:
        unmatched_path = DATA_DIR / f"results_unmatched_{site}_{slate_id}.csv"
        unmatched.to_csv(unmatched_path, index=False)
        print(
            f"WARNING: {n_unmatched} player(s) could not be matched to a "
            f"player_id and are NOT in the results log. "
            f"See {unmatched_path} for details. "
            f"Add overrides to data/name_mapping.csv and re-run if needed.",
            file=sys.stderr,
        )

    if n_matched == 0:
        raise SystemExit(
            "No players matched. The log was not updated. "
            "Check that the raw results file uses player names consistent "
            "with this slate's final_projections file."
        )

    logged_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    new_rows = []
    for _, m in matched.iterrows():
        error = m["actual_fpts"] - m["final_projection"]
        new_rows.append({
            "site": site,
            "season": season,
            "week": week,
            "slate_id": slate_id,
            "slate_type": slate_type,
            "player_id": m["player_id"],
            "player_name": m["player_name"],
            "position": m["position"],
            "final_projection": m["final_projection"],
            "actual_fpts": m["actual_fpts"],
            "error": error,
            "abs_error": abs(error),
            "source": source,
            "logged_at": logged_at,
        })

    new_df = pd.DataFrame(new_rows, columns=LOG_COLUMNS)

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    combined = pd.concat([existing, new_df], ignore_index=True)
    combined.to_csv(LOG_PATH, index=False)

    print(f"\nLogged {len(new_rows)} rows to {LOG_PATH}.")
    print(f"  site={site}, season={season}, week={week}, slate_id={slate_id}, "
          f"slate_type={slate_type}")
    print(f"  source: {source}")
    print(f"  mean error: {new_df['error'].mean():.2f}, "
          f"mean abs error: {new_df['abs_error'].mean():.2f}")

    total_regular = len(combined[combined["slate_type"] == "regular_season"])
    total_weeks_regular = (
        combined[combined["slate_type"] == "regular_season"]
        .drop_duplicates(subset=["site", "season", "week"])
        .shape[0]
    )
    print(
        f"\nLog totals: {len(combined)} rows total "
        f"({total_regular} regular_season across {total_weeks_regular} week(s))."
    )
    if total_weeks_regular < 4:
        print(
            f"  DATA GATE: {total_weeks_regular}/4 regular-season weeks logged. "
            f"Session 9.2 requires 4+ weeks of regular_season data before "
            f"retuning projection weights."
        )
    else:
        print(
            f"  DATA GATE: {total_weeks_regular} regular-season week(s) logged. "
            f"Session 9.2 can proceed (minimum 4 weeks met)."
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
    print(f"\nProjection error log summary ({LOG_PATH}):")
    print(f"  Total rows: {len(log)}")
    for stype in VALID_SLATE_TYPES:
        sub = log[log["slate_type"] == stype]
        if sub.empty:
            continue
        weeks = sub.drop_duplicates(["site", "season", "week"]).shape[0]
        print(f"  {stype}: {len(sub)} rows, {weeks} distinct week(s)")
        if stype == "regular_season" and weeks < 4:
            print(f"    -> {weeks}/4 weeks toward Session 9.2 data gate")
    print()
    by_slate = (
        log.groupby(["site", "season", "week", "slate_id", "slate_type"])
        .agg(n_players=("player_id", "count"),
             mean_error=("error", "mean"),
             mean_abs_error=("abs_error", "mean"))
        .reset_index()
    )
    print(by_slate.to_string(index=False))
    print()
    by_pos = (
        log[log["slate_type"] == "regular_season"]
        .groupby(["site", "position"])
        .agg(n=("player_id", "count"),
             mean_error=("error", "mean"),
             mean_abs_error=("abs_error", "mean"))
        .reset_index()
    )
    if not by_pos.empty:
        print("By site/position (regular_season only):")
        print(by_pos.to_string(index=False))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Log real post-game actual fantasy points alongside pipeline "
            "projections. Appends to data/projection_error_log.csv."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    log_parser = subparsers.add_parser(
        "log",
        help="Append result rows for a specific slate.",
    )
    log_parser.add_argument("--site", choices=["dk", "fd"], required=True)
    log_parser.add_argument(
        "--season", type=int, required=True,
        help="Real NFL season year (e.g. 2026).",
    )
    log_parser.add_argument(
        "--week", type=int, required=True,
        help="Real NFL week number (1-18 for regular season).",
    )
    log_parser.add_argument(
        "--slate-id", required=True,
        help=(
            "The slate_id used when final_projections_{site}_{slate_id}.csv "
            "was built for this slate. NOT the week number."
        ),
    )
    log_parser.add_argument(
        "--slate-type",
        choices=sorted(VALID_SLATE_TYPES),
        required=True,
        help=(
            "regular_season: counts toward Session 9.2's data gate. "
            "preseason/madden_sim: pipeline validation only, excluded."
        ),
    )
    log_parser.add_argument(
        "--input", type=Path, required=True,
        help="Path to the raw results CSV: player_name, actual_fpts.",
    )
    log_parser.add_argument(
        "--source", required=True,
        help=(
            "Human-readable description of where actual_fpts came from "
            "(e.g. 'DK contest results export 2026-09-14')."
        ),
    )

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
                f"Input file not found: {args.input}. Create the raw "
                f"results CSV (player_name, actual_fpts) before running."
            )
        log_results(
            site=args.site,
            season=args.season,
            week=args.week,
            slate_id=args.slate_id,
            slate_type=args.slate_type,
            raw_path=args.input,
            source=args.source,
        )
    elif args.command == "summary":
        print_summary(site=args.site)


if __name__ == "__main__":
    main()
