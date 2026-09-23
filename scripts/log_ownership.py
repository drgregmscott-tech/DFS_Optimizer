"""
log_ownership.py
================

Session 9.3 -- Actual Ownership Logging.
Extended (this fix) to support Showdown ownership logging.

Logs real post-lock DFS ownership percentages alongside this pipeline's
pre-lock estimates, building the dataset Sessions 11.1 and 11.2 will fit
ownership model parameters against.

Schema originally defined in Session 11.0 (see ROADMAP.md's Session 9.3
card and SESSION_LOG.md's Session 11.0 entry), extended by this fix with
two additive columns -- roster_role and slate_format -- so Showdown
ownership (Captain/MVP vs. FLEX are separate real ownership quantities for
the same player) can be logged at all. See DECISIONS #6/#7 below. This
extension was flagged as the concrete next step back in Session 13.3b and
Session 15.3 and is not a speculative redesign.

USAGE
-----

Log ownership from a specific contest/slate (classic example):

    python scripts/log_ownership.py \\
        --site dk \\
        --season 2026 \\
        --week 1 \\
        --slate-id dk_classic_wk1_091326 \\
        --slate-type regular_season \\
        --contest-type single_entry_gpp \\
        --field-size 150000 \\
        --input data/ownership_raw_dk_2026_wk1.csv

Showdown example (raw CSV needs an extra roster_role column -- see
"RAW INPUT CSV SHAPE" below):

    python scripts/log_ownership.py \\
        --site dk \\
        --season 2026 \\
        --week 2 \\
        --slate-id dk_showdown_wk2_091826 \\
        --slate-type regular_season \\
        --contest-type single_entry_gpp \\
        --field-size 20000 \\
        --input data/ownership_raw_dk_showdown_2026_wk2.csv

--slate-id must match the --slate-id used when
final_projections_{site}_{slate_id}.csv was built for this slate (i.e. the
same value passed to build_projections_statline.py). It is NOT the same
thing as --week -- a site can have more than one slate_id in the same
week (e.g. a classic main slate and a Showdown slate), and each needs its
own --slate-id to find the right reference file (decision #6).

The script matches players to the pipeline's player_id (and, for
Showdown, roster_role) via that slate's own final_projections file, which
already carries the pipeline's pre-lock estimated_ownership_pct alongside
each player -- no separate join needed. It then appends all rows to
data/ownership_actual_log.csv.

For the Millionaire Maker and similar large-field GPPs, DraftKings posts
ownership percentages on the contest results page after lock. FanDuel does
the same on their My Contests page. Copy player names (and, for Showdown,
roster role) and percentages into a CSV manually -- there is no stable API
for this.

RAW INPUT CSV SHAPE
--------------------
Classic slates -- two columns:
    player_name, actual_ownership_pct

Showdown slates -- three columns:
    player_name, roster_role, actual_ownership_pct

roster_role must be exactly one of the site's real role labels
(DK: "CPT"/"FLEX", FD: "MVP"/"FLEX") for every row -- DK's and FD's own
Showdown contest-results pages report Captain/MVP ownership and FLEX
ownership as separate line items for the same player, since a real DFS
player can (and often does) roster the same player in either slot at very
different rates. One raw row per (player, roster_role) pair.

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
slate_id                  -- this slate's own slate_id (added 2026-09-14,
                              decision #8 -- see below; distinguishes e.g.
                              a week's main/early/afternoon classic slates,
                              which previously collided as false duplicates)
slate_type                -- regular_season | preseason | madden_sim
contest_id                -- platform's own contest identifier (optional,
                              "" if unavailable)
contest_type              -- cash | single_entry_gpp | 3max_gpp | unknown
field_size                -- number of entries in the contest (integer)
player_id                 -- nflverse player_id (matched via name lookup)
player_name               -- as it appears in the raw ownership source
roster_role               -- "" for classic. "CPT"/"FLEX" (DK) or
                              "MVP"/"FLEX" (FD) for Showdown -- same raw
                              site role labels final_projections_*.csv
                              carries (decision #6).
slate_format               -- classic | showdown
actual_ownership_pct      -- real post-lock ownership percentage (0-100)
estimated_ownership_pct_at_lock -- pipeline's pre-lock estimate, read
                              directly off this slate's own
                              final_projections_{site}_{slate_id}.csv
source                    -- human-readable description of where the actual
                              ownership data came from (e.g.
                              "DK Millionaire Maker results page 2026-09-14")
logged_at                 -- ISO timestamp when this row was appended

MATCHING
--------
Players are matched by normalized name (and, for Showdown, roster_role)
against final_projections_{site}_{slate_id}.csv (which carries player_id,
roster_role, slate_format, and estimated_ownership_pct straight from the
salary/projection pipeline). The same normalize_name() function used
throughout this pipeline is used here, so existing name_mapping.csv
overrides apply.

Unmatched players (names that don't resolve to a player_id) are logged to
data/ownership_unmatched_{site}_{slate_id}.csv rather than dropped
silently -- same fail-loud pattern as ingest_salaries.py. They do NOT enter
the main log.

DECISIONS
---------

1. APPEND, NOT OVERWRITE. ownership_actual_log.csv grows weekly. Running
   this script twice for the same (site, season, week, contest_id) detects
   the duplicate by checking existing rows and raises a clear error rather
   than silently doubling the data. If contest_id is "" (not available),
   the duplicate check uses (site, season, week, slate_type, contest_type,
   slate_format) instead -- slate_format added by decision #7 below, so
   logging a classic slate and a Showdown slate for the same site/week/
   slate_type/contest_type no longer collide as a false duplicate.

2. [SUPERSEDED by decision #6.] Originally: estimated ownership captured
   at log time from a separate chalk_scores_{site}_{week}.csv file. That
   file is not part of the live production pipeline (build_projections_
   statline.py writes ownership columns straight into final_projections),
   so this script no longer depends on it at all -- see decision #6.

3. PLAYER_ID IS THE JOIN KEY for Sessions 11.1/11.2. Name matching here
   uses normalize_name() + this slate's own final_projections file (which
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

6. ROSTER_ROLE + SLATE_FORMAT ADDED; REFERENCE SOURCE SWITCHED TO
   final_projections_{site}_{slate_id}.csv, KEYED BY --slate-id NOT
   --week. Two real, separate problems, fixed together because the second
   was found while fixing the first:
     (a) A Showdown pool has TWO reference rows per player (one CPT/MVP,
         one FLEX) with the SAME normalized name -- Session 13.3b
         established these are genuinely different real-world ownership
         quantities (e.g. a real Joe Burrow: ~4% CPT vs. ~20% FLEX on the
         validated slate). Without a roster_role column, this script had
         no way to log which one a given real number referred to, so it
         could not log Showdown ownership at all -- the gap flagged in
         Session 13.3b and re-flagged in Session 15.3.
     (b) While wiring that fix, this script's file lookup was found to
         be pointed at a filename the live pipeline hasn't written since
         Session 13.2: it looked for final_projections_{site}_{week}.csv
         (and, failing that, chalk_scores_{site}_{week}.csv), but
         build_projections_statline.py has written
         final_projections_{site}_{slate_id}.csv (slate_id, not week --
         see DFS_Weekly_Process.md's "Output filenames use --slate-id"
         note) since Showdown support shipped. That means this script's
         reference lookup could never have found a real file for any
         real slate whose slate_id isn't literally the week number as a
         string -- a pre-existing bug, not something this fix introduced,
         caught before the first real end-to-end run rather than during
         one, because Session 9.3's real end-to-end run never actually
         happened (see SESSION_LOG.md).
   Fix: this script now takes a required --slate-id, reads player_id,
   player_name, position, roster_role, slate_format, and
   estimated_ownership_pct all from ONE file
   (final_projections_{site}_{slate_id}.csv), and drops the separate
   chalk_scores join entirely -- the same fix already applied to
   pivot_finder.py (Session 13.5b) for the identical reason (two files
   that could independently go stale vs. one source of truth).

8. SLATE_ID ADDED TO THE LOG SCHEMA AND TO THE FALLBACK DUPLICATE KEY --
   REAL BUG, FOUND LOGGING A REAL MULTI-SLATE WEEK (2026-09-14). The
   original fallback duplicate key (site, season, week, slate_type,
   contest_type, slate_format) was built for "one classic slate per
   site per week" -- it has no way to tell a week's main/early/afternoon
   classic slates apart, since all three share every field in that key.
   Logging the real Week 1 DK early slate right after the real main
   slate raised a false "duplicate detected" error, even though the two
   are genuinely different slates with genuinely different real
   ownership. Fix: slate_id is now a first-class log column (backfilled
   for pre-fix rows -- see the migration note in SESSION_LOG.md's
   2026-09-14 entry) and is included in the fallback duplicate key
   alongside the existing fields, so main/early/afternoon (or any two
   same-week classic slates) log independently and correctly.
   slate_format is kept in the key too, redundantly with slate_id, since
   it costs nothing and keeps the key's intent readable on its own.

7. SHOWDOWN RAW INPUT CSV NEEDS ITS OWN roster_role COLUMN, VALIDATED
   AGAINST SITE_CONFIGS. DK's and FD's real Showdown/Single-Game contest
   results report Captain/MVP ownership and FLEX ownership as separate
   line items for the same player. load_raw_ownership() requires a third
   "roster_role" column whenever the target slate's slate_format is
   "showdown" (detected from final_projections_{site}_{slate_id}.csv, not
   guessed), and fails loud if any value isn't exactly this site's real
   captain_role_value/flex_role_value from SITE_CONFIGS (e.g. "CPT"/
   "FLEX" for DK). Classic slates are unaffected -- no roster_role column
   required, matching behavior unchanged from before this fix.
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
    "site", "season", "week", "slate_id", "slate_type", "contest_id", "contest_type",
    "field_size", "player_id", "player_name", "roster_role", "slate_format",
    "actual_ownership_pct", "estimated_ownership_pct_at_lock", "source",
    "logged_at",
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
                    slate_id: str, slate_type: str, contest_type: str,
                    contest_id: str, slate_format: str) -> None:
    """Raise if this (site, season, week, contest) combination is already logged.

    Decision #1 (extended by decisions #7 and #8): duplicate detection. Uses
    contest_id when present; falls back to (site, season, week, slate_id,
    slate_type, contest_type, slate_format) when contest_id is empty --
    slate_id (decision #8) is what actually distinguishes same-week classic
    slates (main/early/afternoon); slate_format (decision #7) is kept too so
    a classic slate and a Showdown slate in the same site/week/slate_type/
    contest_type also can't collide.
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
            (existing["slate_id"] == slate_id) &
            (existing["slate_type"] == slate_type) &
            (existing["contest_type"] == contest_type) &
            (existing["slate_format"] == slate_format)
        )
        key_desc = (f"site={site}, season={season}, week={week}, "
                    f"slate_id={slate_id}, slate_type={slate_type}, "
                    f"contest_type={contest_type}, slate_format={slate_format}")

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

def load_raw_ownership(path: Path, slate_format: str, site: str) -> pd.DataFrame:
    """Load the manually-prepared ownership CSV.

    Classic: two required columns -- player_name, actual_ownership_pct.
    Showdown: three required columns -- player_name, roster_role,
    actual_ownership_pct (decision #7).

    Ownership values may be expressed as "23.4%" or "23.4" -- both accepted.
    Extra columns are silently ignored.
    """
    df = pd.read_csv(path)
    required = {"player_name", "actual_ownership_pct"}
    if slate_format == "showdown":
        required.add("roster_role")
    missing = required - set(df.columns)
    if missing:
        shape = ("player_name, roster_role, actual_ownership_pct"
                  if slate_format == "showdown"
                  else "player_name, actual_ownership_pct")
        raise SystemExit(
            f"Raw ownership CSV at {path} is missing column(s) {sorted(missing)}. "
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
                f"row of a Showdown ownership CSV must be labeled "
                f"'{cfg['captain_role_value']}' or '{cfg['flex_role_value']}' "
                f"(decision #7)."
            )
    else:
        df["roster_role"] = ""

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
    # 2026-09-23: DK's results export lists a player once per roster slot
    # they were drafted into (position row + FLEX row). Week 2 was logged
    # with only the first row, silently dropping all FLEX ownership (slate
    # totals ~797% instead of ~897%). Real ownership sums to 100 * roster
    # slots minus unmatched/DST-only noise, so a classic slate far below
    # that means rows were dropped -- fail loudly rather than log it.
    if slate_format == "classic":
        n_slots = len(SITE_CONFIGS[site]["roster_slots"])
        total = float(df["actual_ownership_pct"].sum())
        if total < 0.93 * n_slots * 100:
            raise SystemExit(
                f"Raw ownership CSV at {path} sums to {total:.0f}% but a "
                f"classic {site} slate should total ~{n_slots * 100}%. Sum "
                f"each player's %Drafted across ALL of his rows in the DK "
                f"export (position row + FLEX row), don't keep only the first."
            )
    return df[["player_name", "roster_role", "actual_ownership_pct"]].copy()


# ---------------------------------------------------------------------------
# Player matching
# ---------------------------------------------------------------------------

def build_reference(site: str, slate_id: str) -> pd.DataFrame:
    """Build a normalized-name (+ roster_role) -> player_id lookup.

    Decision #6: reads directly off final_projections_{site}_{slate_id}.csv
    -- the single real source of truth for a slate's player pool,
    roster_role, slate_format, and pre-lock estimated_ownership_pct --
    rather than a separate chalk_scores_{site}_{week}.csv file (not part of
    the live pipeline) keyed by the wrong identifier (week, not slate_id).

    Returns a DataFrame with columns:
      normalized_name, player_id, player_name, position, roster_role,
      slate_format, estimated_ownership_pct
    """
    proj_path = OUTPUT_DIR / f"final_projections_{site}_{slate_id}.csv"
    if not proj_path.exists():
        raise SystemExit(
            f"No projection file found at {proj_path}. Run "
            f"build_projections_statline.py for this site/slate before "
            f"logging ownership -- double check --slate-id matches the "
            f"slate you're logging (the same value passed to "
            f"build_projections_statline.py's own --slate-id, not the "
            f"week number)."
        )

    ref = pd.read_csv(proj_path, dtype={"player_id": str, "site_player_id": str})
    print(f"Loaded {len(ref)} player reference rows from {proj_path.name}.")

    missing_cols = ({"player_id", "player_name", "position", "roster_role",
                     "slate_format", "estimated_ownership_pct"} - set(ref.columns))
    if missing_cols:
        raise SystemExit(
            f"{proj_path} is missing expected column(s): {sorted(missing_cols)}. "
            f"Was this file built by an older version of the pipeline? "
            f"Re-run build_projections_statline.py for this slate."
        )

    ref = ref.dropna(subset=["player_id"])
    ref["normalized_name"] = ref["player_name"].map(normalize_name)
    # roster_role is None/NaN for classic rows (matches
    # build_projections_statline.py's own out["roster_role"] = None
    # convention) -- normalize to "" so nothing downstream has to
    # special-case NaN.
    ref["roster_role"] = ref["roster_role"].fillna("")
    return ref[["normalized_name", "player_id", "player_name", "position",
                "roster_role", "slate_format", "estimated_ownership_pct"]].copy()


def match_ownership_rows(raw: pd.DataFrame, ref: pd.DataFrame,
                         site: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Match raw ownership rows to player_id (+ roster_role) via normalized name.

    Returns (matched_df, unmatched_df).

    Decision #6: a Showdown pool has TWO reference rows per player (one
    CPT/MVP, one FLEX) with the SAME normalized name. For a showdown slate,
    each raw row is first filtered to candidates sharing its own
    roster_role before the name match runs, so a raw CPT row can only match
    the CPT reference row, never the FLEX one. Classic slates are
    unaffected -- one reference row per player, roster_role plays no role
    in the match (every candidate's roster_role is "").

    DST/DEF rows are matched by team abbreviation embedded in the player name
    (e.g. "Kansas City Chiefs D/ST" -> team "KC") rather than normalized name,
    since defense names vary widely across platforms.
    """
    slate_format = ref["slate_format"].iloc[0] if not ref.empty else "classic"
    defense_values = SITE_CONFIGS[site]["defense_position_values"]

    matched_rows, unmatched_rows = [], []

    for _, row in raw.iterrows():
        raw_name = str(row["player_name"]).strip()
        actual_pct = row["actual_ownership_pct"]
        raw_role = row["roster_role"] if slate_format == "showdown" else ""
        norm = normalize_name(raw_name)

        candidates = ref[ref["roster_role"] == raw_role] if slate_format == "showdown" else ref
        ref_skill = candidates[~candidates["position"].str.upper().isin(defense_values)]
        ref_dst = candidates[candidates["position"].str.upper().isin(defense_values)]

        # Try skill-player exact normalized match first
        skill_hit = ref_skill[ref_skill["normalized_name"] == norm]
        if len(skill_hit) == 1:
            hit = skill_hit.iloc[0]
            matched_rows.append({
                "raw_name": raw_name,
                "player_id": hit["player_id"],
                "player_name": hit["player_name"],
                "roster_role": hit["roster_role"],
                "estimated_ownership_pct": hit["estimated_ownership_pct"],
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
                "roster_role": dst_match["roster_role"],
                "estimated_ownership_pct": dst_match["estimated_ownership_pct"],
                "actual_ownership_pct": actual_pct,
            })
            continue

        # No match
        unmatched_rows.append({
            "raw_name": raw_name,
            "normalized_name": norm,
            "roster_role": raw_role,
            "actual_ownership_pct": actual_pct,
            "reason": "no exact name match in final_projections for this "
                      "roster_role; not a recognized DST format",
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
                    "player_name": dst_row["player_name"],
                    "roster_role": dst_row["roster_role"],
                    "estimated_ownership_pct": dst_row["estimated_ownership_pct"]}
    return None


# ---------------------------------------------------------------------------
# Main logging function
# ---------------------------------------------------------------------------

def log_ownership(
    site: str,
    season: int,
    week: int,
    slate_id: str,
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
    if not slate_id.strip():
        raise SystemExit(
            "--slate-id is required (decision #6) -- it must match the "
            "--slate-id used when final_projections_{site}_{slate_id}.csv "
            "was built for this slate. It is NOT the same thing as --week."
        )

    if slate_type in ("preseason", "madden_sim"):
        print(
            f"NOTE: slate_type={slate_type!r}. These rows are logged for pipeline "
            f"validation only and are EXCLUDED from Sessions 11.1 and 11.2 model fits. "
            f"Only regular_season rows count toward the 4-6 week data gate."
        )

    # --- Build name->player_id reference (also tells us slate_format) ---
    ref = build_reference(site, slate_id)
    slate_format = ref["slate_format"].iloc[0] if not ref.empty else "classic"
    print(f"Detected slate_format={slate_format!r} from slate_id={slate_id!r}.")

    # --- Load existing log and check for duplicates ---
    existing = load_log()
    check_duplicate(existing, site, season, week, slate_id, slate_type,
                    contest_type, contest_id, slate_format)

    # --- Load raw ownership input (shape depends on slate_format) ---
    raw = load_raw_ownership(raw_path, slate_format, site)
    print(f"Loaded {len(raw)} raw ownership rows from {raw_path.name}.")

    # --- Match players ---
    matched, unmatched = match_ownership_rows(raw, ref, site)

    n_total = len(raw)
    n_matched = len(matched)
    n_unmatched = len(unmatched)
    match_pct = 100.0 * n_matched / n_total if n_total else 0.0
    print(f"Matched {n_matched}/{n_total} players ({match_pct:.1f}%).")

    # --- Write unmatched log ---
    if n_unmatched > 0:
        unmatched_path = DATA_DIR / f"ownership_unmatched_{site}_{slate_id}.csv"
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
            "Check that the raw ownership file uses player names (and, for "
            "Showdown, roster_role values) consistent with this slate's "
            "final_projections file."
        )

    # --- Build log rows ---
    logged_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    new_rows = []
    for _, m in matched.iterrows():
        new_rows.append({
            "site": site,
            "season": season,
            "week": week,
            "slate_id": slate_id,
            "slate_type": slate_type,
            "contest_id": contest_id,
            "contest_type": contest_type,
            "field_size": field_size,
            "player_id": m["player_id"],
            "player_name": m["player_name"],
            "roster_role": m["roster_role"],
            "slate_format": slate_format,
            "actual_ownership_pct": m["actual_ownership_pct"],
            "estimated_ownership_pct_at_lock": m["estimated_ownership_pct"],
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
    print(f"  site={site}, season={season}, week={week}, slate_id={slate_id}, "
          f"slate_format={slate_format}, slate_type={slate_type}, "
          f"contest_type={contest_type}")
    print(f"  field_size={field_size:,}, contest_id={contest_id!r}")
    print(f"  source: {source}")

    est_present = new_df["estimated_ownership_pct_at_lock"].notna().sum()
    if est_present < len(new_df):
        print(
            f"  WARNING: estimated_ownership_pct_at_lock is NaN for "
            f"{len(new_df) - est_present} player(s) -- not present in "
            f"final_projections_{site}_{slate_id}.csv's own "
            f"estimated_ownership_pct column.",
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
    by_slate = (
        log.groupby(["site", "season", "week", "slate_format", "slate_type",
                     "contest_type"])
        .agg(n_players=("player_id", "count"),
             mean_actual=("actual_ownership_pct", "mean"),
             mean_est=("estimated_ownership_pct_at_lock", "mean"))
        .reset_index()
    )
    print(by_slate.to_string(index=False))


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
        "--slate-id", required=True,
        help=(
            "The slate_id used when final_projections_{site}_{slate_id}.csv "
            "was built for this slate (the same value passed to "
            "build_projections_statline.py's own --slate-id). NOT the week "
            "number -- a site can have more than one slate_id in the same "
            "week (e.g. classic + Showdown)."
        ),
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
            "Path to the raw ownership CSV. Classic: player_name, "
            "actual_ownership_pct. Showdown: player_name, roster_role, "
            "actual_ownership_pct. Ownership values may be '23.4' or '23.4%%'."
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
                f"Input file not found: {args.input}. Create the raw "
                f"ownership CSV (see --input's help for the expected "
                f"columns) from the contest results page before running."
            )
        log_ownership(
            site=args.site,
            season=args.season,
            week=args.week,
            slate_id=args.slate_id,
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
