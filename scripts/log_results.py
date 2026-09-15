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
Classic slates -- two columns: player_name, actual_fpts

One row per real player who appeared in the slate's actual results (DST
included, one row per team defense). If a site's raw export lists a player
more than once (e.g. DraftKings' contest-results export splits ownership,
but not points, across a player's primary position and FLEX rows), dedupe
to one row per player before handing the file to this script -- actual_fpts
is a single real-world quantity per player on a classic slate, unlike
ownership.

Showdown slates -- three columns: player_name, roster_role, actual_fpts.
Unlike classic, actual_fpts is genuinely role-split here: DK/FD apply a
1.5x scoring multiplier to whichever player was drafted as Captain/MVP, so
the SAME real player has two different real actual_fpts values depending
on role (e.g. a real Bo Nix: 7.44 FLEX vs 11.16 CPT, exactly 1.5x, both
values found directly in DK's own contest-results export). One row per
(player, roster_role) pair -- do NOT dedupe these, they are not duplicates.
roster_role must be exactly this site's real role labels (DK: "CPT"/"FLEX",
FD: "MVP"/"FLEX"), same convention log_ownership.py already established.

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
roster_role          -- "" for classic. "CPT"/"FLEX" (DK) or "MVP"/"FLEX"
                         (FD) for Showdown -- same raw site role labels
                         final_projections_*.csv already carries. Added
                         2026-09-15 for Showdown support; pre-existing
                         classic rows backfilled to "" on migration.
slate_format          -- classic | showdown. Added alongside roster_role.
final_projection      -- this pipeline's own pre-lock projection for this
                         player/slate/role (Showdown: already carries the
                         1.5x Captain/MVP scaling where applicable)
actual_fpts          -- real post-game fantasy points scored, in this
                         site's own scoring (DK full-PPR, FD half-PPR --
                         never expected to match across sites for the same
                         player), and for Showdown, in this specific role
                         (Captain/MVP actual_fpts is 1.5x the FLEX value
                         for the same real performance -- not a second,
                         independent real quantity, but still logged
                         separately since it's compared against that
                         role's own, separately-scaled final_projection)
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

4. SHOWDOWN SUPPORT ADDED 2026-09-15, SAME GAP LOG_OWNERSHIP.PY ALREADY
   CLOSED (its decision #6/#7). This script's original build_reference()
   collapsed a Showdown reference's two rows per player (CPT/FLEX) down to
   one via drop_duplicates(subset=["normalized_name"]) -- silently correct
   for classic (no real dupes), silently WRONG for Showdown (it would have
   matched a real Captain-role actual_fpts against a FLEX-priced
   final_projection, or vice versa, roughly half the time depending on
   row order). Never caught earlier because Session 9.1's real runs were
   all classic slates; found when a real DK Showdown results export
   (Week 1, DEN@KC) was logged for the first time. Fixed the same way
   log_ownership.py already solved this: roster_role/slate_format added to
   both this script's reference lookup and its output schema, raw-input
   parsing requires a roster_role column for Showdown (validated against
   SITE_CONFIGS's real role labels), and matching filters candidates by
   roster_role before matching name -- so a raw CPT row can only match the
   CPT reference row. `data/projection_error_log.csv`'s existing rows (all
   classic, logged before this fix) were migrated in place: roster_role=""
   and slate_format="classic" backfilled, no rows changed or lost.
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
    "player_name", "position", "roster_role", "slate_format",
    "final_projection", "actual_fpts", "error",
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

def load_raw_results(path: Path, slate_format: str, site: str) -> pd.DataFrame:
    """Load the manually-prepared actual-results CSV.

    Classic: two required columns -- player_name, actual_fpts.
    Showdown: three required columns -- player_name, roster_role,
    actual_fpts (decision #4). actual_fpts is role-split for Showdown
    (Captain/MVP is real-scored at 1.5x FLEX), so duplicate (player_name)
    rows are EXPECTED there, not an error -- only exact (player_name,
    roster_role) duplicates are rejected.
    """
    df = pd.read_csv(path)
    required = {"player_name", "actual_fpts"}
    if slate_format == "showdown":
        required.add("roster_role")
    missing = required - set(df.columns)
    if missing:
        shape = ("player_name, roster_role, actual_fpts"
                  if slate_format == "showdown"
                  else "player_name, actual_fpts")
        raise SystemExit(
            f"Raw results CSV at {path} is missing column(s) {sorted(missing)}. "
            f"Columns found: {sorted(df.columns)}. "
            f"Expected shape for a {slate_format} slate: {shape}."
        )

    if slate_format == "showdown":
        cfg = SITE_CONFIGS[site]["showdown"]
        valid_roles = {cfg["captain_role_value"], cfg["flex_role_value"]}
        df["roster_role"] = df["roster_role"].astype(str).str.strip()
        bad_roles = ~df["roster_role"].isin(valid_roles)
        if bad_roles.any():
            bad_vals = sorted(df.loc[bad_roles, "roster_role"].unique())
            raise SystemExit(
                f"{int(bad_roles.sum())} row(s) have a roster_role not in "
                f"{sorted(valid_roles)} for site={site}: {bad_vals}. Every "
                f"row of a Showdown results CSV must be labeled "
                f"'{cfg['captain_role_value']}' or '{cfg['flex_role_value']}' "
                f"(decision #4)."
            )
    else:
        df["roster_role"] = ""

    df["actual_fpts"] = pd.to_numeric(df["actual_fpts"], errors="coerce")
    bad = df["actual_fpts"].isna()
    if bad.any():
        bad_names = df.loc[bad, "player_name"].tolist()
        raise SystemExit(
            f"Could not parse actual_fpts for {len(bad_names)} player(s): "
            f"{bad_names[:5]}{'...' if len(bad_names) > 5 else ''}. "
            f"Values must be numeric."
        )

    dupe_key = ["player_name", "roster_role"]
    dupes = df[dupe_key][df.duplicated(dupe_key)]
    if len(dupes) > 0:
        dupe_names = dupes["player_name"].unique()
        raise SystemExit(
            f"Raw results CSV at {path} has {len(dupe_names)} duplicate "
            f"(player_name, roster_role) row(s): {list(dupe_names)[:5]}"
            f"{'...' if len(dupe_names) > 5 else ''}. Dedupe before running "
            f"this script -- actual_fpts is a single real-world quantity per "
            f"player per role per slate, unlike ownership."
        )

    return df[["player_name", "roster_role", "actual_fpts"]].copy()


# ---------------------------------------------------------------------------
# Player matching
# ---------------------------------------------------------------------------

def build_reference(site: str, slate_id: str) -> pd.DataFrame:
    """Build a normalized-name(+roster_role) -> player_id/position/
    final_projection lookup.

    Reads directly off final_projections_{site}_{slate_id}.csv, the same
    single source of truth log_ownership.py's build_reference() uses.

    Decision #4: a Showdown reference has TWO rows per player (CPT/FLEX)
    with the same normalized name but different (1.5x-scaled) final_
    projection -- both are kept, distinguished by roster_role, mirroring
    log_ownership.py's own build_reference() exactly. Classic keeps its
    original drop_duplicates safety net (roster_role is "" for every row
    there, so it's a no-op unless something is genuinely duplicated).
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

    missing_cols = ({"player_id", "player_name", "position", "roster_role",
                     "slate_format", "final_projection"} - set(ref.columns))
    if missing_cols:
        raise SystemExit(
            f"{proj_path} is missing expected column(s): {sorted(missing_cols)}. "
            f"Was this file built by an older version of the pipeline? "
            f"Re-run build_projections_statline.py for this slate."
        )

    ref = ref.dropna(subset=["player_id"])
    ref["normalized_name"] = ref["player_name"].map(normalize_name)
    ref["roster_role"] = ref["roster_role"].fillna("")
    slate_format = ref["slate_format"].iloc[0] if not ref.empty else "classic"
    if slate_format != "showdown":
        ref = ref.drop_duplicates(subset=["normalized_name"], keep="first")
    return ref[["normalized_name", "player_id", "player_name", "position",
                "roster_role", "slate_format", "final_projection"]].copy()


def match_results_rows(raw: pd.DataFrame, ref: pd.DataFrame,
                       site: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Match raw actual-results rows to player_id via normalized name
    (+ roster_role for Showdown). Returns (matched_df, unmatched_df).

    Decision #4: for a Showdown slate, each raw row is first filtered to
    candidates sharing its own roster_role before the name match runs --
    same pattern log_ownership.py's match_ownership_rows() already
    established -- so a raw CPT row can only match the CPT reference row,
    never FLEX. Classic is unaffected (every candidate's roster_role is "").
    DST rows matched by team-substring, same helper log_ownership.py uses.
    """
    slate_format = ref["slate_format"].iloc[0] if not ref.empty else "classic"
    defense_values = SITE_CONFIGS[site]["defense_position_values"]

    matched_rows, unmatched_rows = [], []

    for _, row in raw.iterrows():
        raw_name = str(row["player_name"]).strip()
        actual_fpts = row["actual_fpts"]
        raw_role = row["roster_role"] if slate_format == "showdown" else ""
        norm = normalize_name(raw_name)

        candidates = ref[ref["roster_role"] == raw_role] if slate_format == "showdown" else ref
        ref_skill = candidates[~candidates["position"].str.upper().isin(defense_values)]
        ref_dst = candidates[candidates["position"].str.upper().isin(defense_values)]

        skill_hit = ref_skill[ref_skill["normalized_name"] == norm]
        if len(skill_hit) == 1:
            hit = skill_hit.iloc[0]
            matched_rows.append({
                "player_id": hit["player_id"],
                "player_name": hit["player_name"],
                "position": hit["position"],
                "roster_role": hit["roster_role"],
                "final_projection": hit["final_projection"],
                "actual_fpts": actual_fpts,
            })
            continue

        # _match_dst() expects an estimated_ownership_pct key -- build a
        # compatible frame for the shared helper rather than re-implementing
        # DST substring matching here. roster_role is real (already
        # filtered above), not hardcoded.
        dst_ref = ref_dst.assign(estimated_ownership_pct=ref_dst["final_projection"])
        dst_match = _match_dst(raw_name, dst_ref, site)
        if dst_match is not None:
            matched_rows.append({
                "player_id": dst_match["player_id"],
                "player_name": dst_match["player_name"],
                "position": "DST",
                "roster_role": dst_match["roster_role"],
                "final_projection": dst_match["estimated_ownership_pct"],
                "actual_fpts": actual_fpts,
            })
            continue

        unmatched_rows.append({
            "raw_name": raw_name,
            "normalized_name": norm,
            "roster_role": raw_role,
            "actual_fpts": actual_fpts,
            "reason": "no exact name match in final_projections for this "
                      "roster_role; not a recognized DST format",
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
    slate_format = ref["slate_format"].iloc[0] if not ref.empty else "classic"
    print(f"Detected slate_format={slate_format!r} from slate_id={slate_id!r}.")

    existing = load_log()
    check_duplicate(existing, site, season, week, slate_id)

    raw = load_raw_results(raw_path, slate_format, site)
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
            "roster_role": m["roster_role"],
            "slate_format": slate_format,
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
        help=(
            "Path to the raw results CSV. Classic: player_name, "
            "actual_fpts. Showdown: player_name, roster_role, actual_fpts."
        ),
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
                f"results CSV before running (see --input's help for the "
                f"expected columns)."
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
