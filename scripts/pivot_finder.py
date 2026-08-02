"""
pivot_finder.py
================

Session 4.2 -- Cash-to-GPP Pivot Logic.

For a given site (DK/FD) and slate_id, reads that site's single optimal
cash lineup (`lineup_single_{site}_{slate_id}.csv`, Session 3.1) alongside
`final_projections_{site}_{slate_id}.csv` (Session 2.4/3.3, which now carries
`chalk_score`/`estimated_ownership_pct` natively -- see decision #0 below),
and for every player in the cash lineup, generates a ranked list of "pivot"
candidates -- same-position, similarly-PROJECTED players who are LESS
owned than the cash play, for use building differentiated GPP lineups off
the same cash-lineup starting point.

Design decisions (same "flag, don't silently assume" pattern as every prior
session's file):

0. Input fix (this session, found while re-validating on real data): this
   script originally joined `chalk_scores_{site}_{slate_id}.csv` (Session 4.1's
   standalone CLI output) onto `final_projections_{site}_{slate_id}.csv` by
   `player_id` to get `estimated_ownership_pct`. Since then, the frontend's
   Item 6 change added `add_ownership_columns()` to `build_projections.py`,
   which now bakes `chalk_score`/`estimated_ownership_pct` directly into
   `final_projections_{site}_{slate_id}.csv` at write time -- the weekly SOP
   (`DFS_Weekly_Process.md`) never runs `ownership_heuristic.py`'s
   standalone CLI as a separate pipeline step any more. The old merge
   therefore joined two DataFrames that both already had
   `estimated_ownership_pct`, silently producing `..._x`/`..._y` suffixed
   columns instead of the expected single column, and crashing downstream
   with an opaque `KeyError` rather than failing loudly with a clear
   message. Fixed by reading `estimated_ownership_pct`/`chalk_score`
   straight off `final_projections`, removing the `chalk_scores` merge
   entirely (see `load_final_projections()`/`build_candidate_pool()`).
   `chalk_scores_{site}_{slate_id}.csv` and its standalone CLI are untouched
   and still work if wanted for other purposes -- this script just no
   longer depends on them.

0b. Filename convention fix (this session, found while running against a
    real slate with a non-numeric slate_id): this script originally took
    `--week` and built every filename as `{site}_{week}.csv`. That
    predates the slate-management rework (see ROADMAP.md/SESSION_LOG.md),
    which moved EVERY other script (`build_projections.py`, `optimizer.py`)
    to name output by `--slate-id` (an arbitrary string like
    `synthetic_08022026`), not by NFL week number. This script's own
    earlier real-data validation (Madden Sim data) didn't catch the gap
    because that test happened to use "10" as both a week number AND a
    literal slate_id, so the mismatch was invisible until a real
    non-numeric slate_id was used. Fixed by taking `--slate-id` throughout,
    matching `build_projections.py`/`optimizer.py` exactly -- this script
    no longer has any concept of "week" as a CLI input at all.

1. Ownership signal: `estimated_ownership_pct`, NOT `chalk_score`. Session
   4.1's addendum left this as an explicit open decision for this session
   (see ROADMAP.md/SESSION_LOG.md's Session 4.1 ADDENDUM handoff note) --
   `chalk_score` is a pure rank with no real-world anchor, while
   `estimated_ownership_pct` is anchored to real roster-slot budget math.
   User-confirmed answer for this session: use `estimated_ownership_pct`.
   One consequence: the roadmap card's own validation checkbox says "has a
   lower chalk_score than the player it replaces" -- since this session
   uses `estimated_ownership_pct` instead, that checkbox is validated
   against `estimated_ownership_pct` instead of `chalk_score`, not both;
   `chalk_score` is left out of this file's join/output entirely.

2. Join key: `lineup_single_{site}_{slate_id}.csv` (Session 3.1's optimizer
   output) does NOT carry `player_id` -- `assign_roster_slots()` in
   optimizer.py only ever wrote `player_name, position, team, salary,
   projection, opponent`, never `player_id`. Rather than change Session
   3.1/3.2/3.3's already-validated output schema retroactively (this
   project's standing pattern is to flag a gap, not silently touch a
   prior session's validated file), this script instead joins the cash
   lineup to `chalk_scores`/`final_projections` on the normalized triple
   (player_name, position, team), reusing `ingest_salaries.py`'s own
   `normalize_name()`/`normalize_team()` helpers (the same normalization
   already used to join site salary exports against nflverse data in
   Session 1.3) rather than inventing a second, separately-drifting
   normalization scheme. Fails loudly (SystemExit) if a cash-lineup
   player can't be matched to exactly one row in either input file --
   a silent fallback (e.g. skipping the player) would produce an
   incomplete, misleadingly-quiet pivot_suggestions file.

3. Eligibility basis (REVISED this session -- see NFL_pivot_ui_handoff.md
   Finding 1): candidates are now filtered by similarity in
   `final_projection`, NOT salary. This was originally a salary-tolerance
   filter (`SALARY_TOLERANCE_PCT_OF_CAP`, % of that site's cap). NHL's
   Session 4.2 port of this same script found, against real NHL slates,
   that salary is a weak proxy for "similar projected output" at every
   tolerance tried: loose tolerances let through technically-legal but
   useless swaps (a big pay-cut to a clearly worse player), while tight
   tolerances left real cash-lineup players with zero eligible candidates
   -- a structural wall, since salary also prices in matchup, role
   certainty, and market perception, not just points. That reasoning is
   about DFS pricing in general, not NHL-specific, so it applies here too.

   New filter: `PROJECTION_TOLERANCE_PCT_OF_CASH_PROJECTION` (default
   25.0, tested against this session's real Madden Sim week-10 data for
   both DK and FD -- see SESSION_LOG.md for the 15/25/35% comparison this
   value was chosen from, same test-multiple-values-against-real-data
   approach NHL used; NOT copied from NHL's own fitted 25% without a
   separate NFL-specific check, per the handoff doc's explicit caution).
   Symmetric -- a candidate can project a bit higher OR lower than the
   cash player, off the cash player's own `final_projection`. Salary is
   demoted to an INFORMATIONAL output column (`salary_diff`,
   `salary_diff_pct`) -- still shown, no longer a gate. Explicitly
   flagged as an unfit-to-full-season starting heuristic (Madden Sim data
   only) -- a retuning target once real regular-season usage exists, same
   spirit as `OWNERSHIP_SOFTMAX_TEMPERATURE`.

4. Eligibility filters for a pivot candidate (all must hold):
   - Same `position` label as the cash player (site-specific label used
     as-is -- DK's "DST" or FD's "DEF" -- since candidate and cash player
     always come from the same site's file, no cross-site DST/DEF folding
     is needed here, unlike Session 4.1's `position_group`).
   - `final_projection` within `PROJECTION_TOLERANCE_PCT_OF_CASH_PROJECTION`
     of the cash player's own `final_projection` (decision #3 -- both
     directions; a pivot can project a bit higher OR lower).
   - `estimated_ownership_pct` strictly LESS than the cash player's own --
     a "pivot" that isn't less owned isn't leverage, it's just a
     different player.
   - `final_projection > 0` -- a bye/no-real-game player (Session 2.4
     decision #4b) is never a usable pivot suggestion regardless of how
     low its (correctly zeroed) ownership is.
   - Not the cash player themselves, and not any OTHER player already
     rostered elsewhere in the same cash lineup (e.g. a FLEX-eligible
     player already filling a different slot) -- suggesting a swap into a
     player who's already in the lineup is not a real pivot.
   - The swap must keep the FULL lineup's total salary under that site's
     cap (decision #5 below) -- an over-cap "suggestion" isn't usable, so
     it's filtered out entirely rather than surfaced with a warning flag.
     This is now the ONLY place salary acts as a gate -- a legality
     guarantee, not a similarity filter (unchanged from before this
     session, per the handoff doc's explicit instruction to leave it).

5. Full-lineup salary cap re-check (roadmap card's second validation
   checkbox): for every candidate, this script computes what the ENTIRE
   9-player lineup's total salary would be after swapping the cash player
   out for the candidate (cash lineup's total salary - cash player's
   salary + candidate's salary), and hard-filters out any candidate whose
   post-swap total would exceed `SITE_CONFIGS[site]["salary_cap"]hey`.
   This is stricter than just checking the single swapped salary is
   "close enough" (decision #3) -- decision #3's tolerance is about
   whether the swap is a sensible like-for-like price tier, decision #5
   is the hard legality guarantee, same "structural guarantee, not
   eyeballing" pattern as optimizer.py's own salary_cap constraint.

6. Leverage score (0-100 scale, matching `chalk_score`/
   `estimated_ownership_pct`'s existing 0-100 convention): combines HOW
   MUCH LESS owned the candidate is with HOW MUCH PROJECTION is kept,
   so a deep-punt pivot that saves ownership but tanks your points doesn't
   outrank a near-equal-projection, meaningfully-less-owned pivot.

       ownership_edge_pts   = cash_player.estimated_ownership_pct
                               - candidate.estimated_ownership_pct
       projection_retention = min(candidate.final_projection
                                   / cash_player.final_projection, 1.0)
       leverage_score = clip(ownership_edge_pts * projection_retention, 0, 100)

   `projection_retention` is capped at 1.0 (not left uncapped) specifically
   to keep `leverage_score` on the same bounded 0-100 scale as every other
   score in this project -- a candidate that projects HIGHER than the cash
   player still gets full (100%) retention credit, not a score inflated
   above 100. That "outprojects the cash player" case is real and worth
   surfacing on its own, so it's flagged as a separate boolean column
   (`outprojects_cash_player`) in the output rather than folded into the
   score. This blend is an explicit starting heuristic, unfit to any real
   leverage/finish-rate data (none exists in this pipeline yet) -- flagged
   as a future retuning target, same as every other heuristic blend in
   this project (chalk_score's weights, ownership softmax temperature).

7. Top-N cutoff: `TOP_N_PIVOTS` (default 3, matching the roadmap card's
   "top 2-3 ranked pivot candidates"), ranked by `leverage_score`
   descending. If fewer than `TOP_N_PIVOTS` eligible candidates exist for
   a given cash player (thin pool -- see ROADMAP.md's "Known Testing
   Artifact" note), all eligible candidates are returned and this is
   noted, not treated as an error. A cash player with ZERO eligible
   candidates under the projection-band filter (decision #3) is likewise
   accepted as legitimate information -- "this player has no real
   same-tier alternative on this slate" -- rather than a signal to widen
   the tolerance until something appears (same resolution NHL reached
   after testing; a WARNING is printed to stderr but the tolerance is not
   auto-relaxed).

Usage:
    python3 pivot_finder.py --site dk --slate-id classic_wk10
    python3 pivot_finder.py --site fd --slate-id classic_wk10

Outputs:
    output/pivot_suggestions_{site}_{slate_id}.csv
    One row per (cash_player, pivot_candidate) pair. See OUTPUT_COLUMNS
    below for the full schema.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest_salaries import SITE_CONFIGS, normalize_name, normalize_team  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "output"

# Decision #3 -- % of the cash player's OWN final_projection, symmetric.
# Chosen from a real-data 15/25/35% comparison against Madden Sim week 10
# (both sites) -- see SESSION_LOG.md. Flagged as unfit to full-season data.
PROJECTION_TOLERANCE_PCT_OF_CASH_PROJECTION = 25.0

# Decision #7.
TOP_N_PIVOTS = 3

OUTPUT_COLUMNS = [
    "cash_player_name", "cash_position", "cash_team", "cash_salary",
    "cash_final_projection", "cash_estimated_ownership_pct",
    "pivot_rank",
    "pivot_player_name", "pivot_team", "pivot_salary",
    "pivot_final_projection", "pivot_estimated_ownership_pct",
    "salary_diff", "salary_diff_pct", "projection_diff", "projection_diff_pct",
    "ownership_edge_pts",
    "outprojects_cash_player", "leverage_score",
    "lineup_salary_after_swap", "site_salary_cap",
]


# ---------------------------------------------------------------------------
# Step 0: Load inputs
# ---------------------------------------------------------------------------

def load_lineup_single(site: str, slate_id: str) -> pd.DataFrame:
    path = OUTPUT_DIR / f"lineup_single_{site}_{slate_id}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run optimizer.py --site {site} --slate-id {slate_id} "
            f"first (Session 3.1)."
        )
    df = pd.read_csv(path)
    required = {"roster_slot", "player_name", "position", "team", "salary", "projection"}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(
            f"{path} is missing expected columns: {sorted(missing)}. "
            f"optimizer.py's output schema may have changed -- update this "
            f"script's load_lineup_single() to match."
        )
    return df


def load_final_projections(site: str, slate_id: str) -> pd.DataFrame:
    path = OUTPUT_DIR / f"final_projections_{site}_{slate_id}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run build_projections.py --site {site} "
            f"--slate-id {slate_id} first (Session 2.4/3.3)."
        )
    df = pd.read_csv(path, dtype={"player_id": str})
    required = {
        "player_id", "player_name", "position", "team", "salary",
        "final_projection", "estimated_ownership_pct",
    }
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(
            f"{path} is missing expected columns: {sorted(missing)}. "
            f"Note: build_projections.py's add_ownership_columns() bakes "
            f"chalk_score/estimated_ownership_pct into this file directly "
            f"-- if those columns are missing, re-run build_projections.py "
            f"--site {site} --slate-id {slate_id} rather than looking for a "
            f"separate chalk_scores file. Update this script's "
            f"load_final_projections() if the schema has changed further."
        )
    return df


# ---------------------------------------------------------------------------
# Step 1: Join cash lineup + final_projections (decision #2)
# ---------------------------------------------------------------------------

def _join_key(df: pd.DataFrame, site: str, name_col: str, team_col: str,
              position_col: str) -> pd.Series:
    return (
        df[name_col].apply(normalize_name) + "|"
        + df[position_col].astype(str).str.strip().str.upper() + "|"
        + df[team_col].apply(lambda t: normalize_team(t, site))
    )


def build_candidate_pool(site: str, slate_id: str) -> pd.DataFrame:
    """As of this session's Finding-3 fix, `final_projections_{site}_
    {slate_id}.csv` already carries `chalk_score`/`estimated_ownership_pct`
    natively -- `build_projections.py`'s `add_ownership_columns()` (added
    for the frontend's automatic-ownership feature) bakes these in at
    write time. There is no longer a separate join to a standalone
    `chalk_scores_{site}_{slate_id}.csv` file -- that file's own standalone
    CLI still exists and still works if wanted for other purposes, but
    this script no longer depends on it, removing one more file that can
    silently go stale relative to final_projections (this was the exact
    failure mode found this session: merging two DataFrames that both
    already had `estimated_ownership_pct` produced `..._x`/`..._y`
    suffixed columns instead of a clean single column, crashing
    downstream with a KeyError rather than failing loudly with a clear
    message)."""
    return load_final_projections(site, slate_id)


def attach_cash_lineup_context(lineup: pd.DataFrame, pool: pd.DataFrame,
                                site: str, slate_id: str) -> pd.DataFrame:
    """Decision #2 -- joins each cash-lineup row to its matching row in
    `pool` (final_projections + estimated_ownership_pct) via the
    normalized (player_name, position, team) triple, since lineup_single
    has no player_id. Fails loudly on any zero- or multi-match."""
    lineup = lineup.copy()
    pool = pool.copy()
    lineup["_key"] = _join_key(lineup, site, "player_name", "team", "position")
    pool["_key"] = _join_key(pool, site, "player_name", "team", "position")

    match_counts = pool.groupby("_key").size()
    enriched_rows = []
    for _, row in lineup.iterrows():
        n_matches = match_counts.get(row["_key"], 0)
        if n_matches != 1:
            raise SystemExit(
                f"Cash lineup player {row['player_name']!r} ({row['position']}, "
                f"{row['team']}) matched {n_matches} row(s) in "
                f"final_projections/chalk_scores by normalized "
                f"(name, position, team) -- expected exactly 1 (decision #2). "
                f"Check for a name/team mismatch between lineup_single_"
                f"{site}_{slate_id}.csv and final_projections_{site}_{slate_id}.csv "
                f"(e.g. files generated from different weeks/runs)."
            )
        match = pool.loc[pool["_key"] == row["_key"]].iloc[0]
        enriched_rows.append({
            "player_id": match["player_id"],
            "cash_player_name": row["player_name"],
            "cash_position": row["position"],
            "cash_team": row["team"],
            "cash_salary": row["salary"],
            "cash_final_projection": match["final_projection"],
            "cash_estimated_ownership_pct": match["estimated_ownership_pct"],
        })
    return pd.DataFrame(enriched_rows)


# ---------------------------------------------------------------------------
# Step 2: Find + rank pivot candidates per cash-lineup player
# ---------------------------------------------------------------------------

def find_pivots_for_player(cash_row: pd.Series, pool: pd.DataFrame,
                            rostered_player_ids: set, site: str,
                            lineup_total_salary: float,
                            projection_tolerance_pct: float,
                            top_n: int) -> pd.DataFrame:
    cap = SITE_CONFIGS[site]["salary_cap"]
    # Decision #3 -- tolerance is a % of the cash player's OWN
    # final_projection, symmetric, NOT a % of the site's salary cap.
    tolerance_pts = (projection_tolerance_pct / 100.0) * cash_row["cash_final_projection"]

    candidates = pool[
        (pool["position"] == cash_row["cash_position"])
        & (pool["player_id"] != cash_row["player_id"])
        & (~pool["player_id"].isin(rostered_player_ids))
        & (pool["final_projection"] > 0)  # decision #4 -- never suggest a bye/zero player
        & (pool["estimated_ownership_pct"] < cash_row["cash_estimated_ownership_pct"])
        & ((pool["final_projection"] - cash_row["cash_final_projection"]).abs() <= tolerance_pts)
    ].copy()

    if candidates.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    # Decision #5 -- hard full-lineup salary cap re-check.
    candidates["lineup_salary_after_swap"] = (
        lineup_total_salary - cash_row["cash_salary"] + candidates["salary"]
    )
    candidates = candidates[candidates["lineup_salary_after_swap"] <= cap]
    if candidates.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    # Decision #6 -- leverage score.
    candidates["ownership_edge_pts"] = (
        cash_row["cash_estimated_ownership_pct"] - candidates["estimated_ownership_pct"]
    )
    projection_retention = (
        candidates["final_projection"] / cash_row["cash_final_projection"]
    ).clip(upper=1.0)
    candidates["outprojects_cash_player"] = (
        candidates["final_projection"] > cash_row["cash_final_projection"]
    )
    candidates["leverage_score"] = (
        candidates["ownership_edge_pts"] * projection_retention
    ).clip(lower=0, upper=100)

    # Salary is informational-only output now (decision #3) -- no longer
    # a gate. Reported both in dollars and as a % of the site's cap, since
    # a raw dollar diff doesn't travel between DK's $50K and FD's $60K cap.
    candidates["salary_diff"] = candidates["salary"] - cash_row["cash_salary"]
    candidates["salary_diff_pct"] = (candidates["salary_diff"] / cap) * 100.0
    candidates["projection_diff"] = candidates["final_projection"] - cash_row["cash_final_projection"]
    candidates["projection_diff_pct"] = (
        candidates["projection_diff"] / cash_row["cash_final_projection"]
    ) * 100.0

    candidates = candidates.sort_values("leverage_score", ascending=False).head(top_n)
    candidates = candidates.reset_index(drop=True)
    candidates.insert(0, "pivot_rank", candidates.index + 1)

    out = pd.DataFrame({
        "cash_player_name": cash_row["cash_player_name"],
        "cash_position": cash_row["cash_position"],
        "cash_team": cash_row["cash_team"],
        "cash_salary": cash_row["cash_salary"],
        "cash_final_projection": cash_row["cash_final_projection"],
        "cash_estimated_ownership_pct": cash_row["cash_estimated_ownership_pct"],
        "pivot_rank": candidates["pivot_rank"],
        "pivot_player_name": candidates["player_name"].values,
        "pivot_team": candidates["team"].values,
        "pivot_salary": candidates["salary"].values,
        "pivot_final_projection": candidates["final_projection"].values,
        "pivot_estimated_ownership_pct": candidates["estimated_ownership_pct"].values,
        "salary_diff": candidates["salary_diff"].values,
        "salary_diff_pct": candidates["salary_diff_pct"].values,
        "projection_diff": candidates["projection_diff"].values,
        "projection_diff_pct": candidates["projection_diff_pct"].values,
        "ownership_edge_pts": candidates["ownership_edge_pts"].values,
        "outprojects_cash_player": candidates["outprojects_cash_player"].values,
        "leverage_score": candidates["leverage_score"].values,
        "lineup_salary_after_swap": candidates["lineup_salary_after_swap"].values,
        "site_salary_cap": cap,
    })
    return out


# ---------------------------------------------------------------------------
# Step 3: Validation assertions (roadmap's two checkboxes -- automated)
# ---------------------------------------------------------------------------

def validate_pivot_suggestions(suggestions: pd.DataFrame, site: str,
                                projection_tolerance_pct: float):
    if suggestions.empty:
        return
    cap = SITE_CONFIGS[site]["salary_cap"]

    # Position is enforced structurally in find_pivots_for_player() (the
    # `pool["position"] == cash_row["cash_position"]` filter) -- there is
    # no separate "pivot_position" output column since it's always
    # identical to cash_position by construction. Re-assert that
    # construction guarantee here rather than re-deriving it.
    tolerance_pts = (projection_tolerance_pct / 100.0) * suggestions["cash_final_projection"]
    assert (suggestions["projection_diff"].abs() <= tolerance_pts + 1e-6).all(), (
        "VALIDATION FAILED: a suggested pivot's projection_diff exceeds "
        "the configured projection tolerance (decision #3)."
    )
    assert (suggestions["pivot_estimated_ownership_pct"]
            < suggestions["cash_estimated_ownership_pct"]).all(), (
        "VALIDATION FAILED: a suggested pivot does not have a lower "
        "estimated_ownership_pct than the cash player it replaces "
        "(decision #1 -- this session validates against "
        "estimated_ownership_pct, not chalk_score)."
    )
    assert (suggestions["lineup_salary_after_swap"] <= suggestions["site_salary_cap"]).all(), (
        "VALIDATION FAILED: a suggested pivot's full-lineup salary after "
        "the swap exceeds that site's salary cap (decision #5)."
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_pivot_suggestions(site: str, slate_id: str,
                             projection_tolerance_pct: float = PROJECTION_TOLERANCE_PCT_OF_CASH_PROJECTION,
                             top_n: int = TOP_N_PIVOTS) -> pd.DataFrame:
    lineup = load_lineup_single(site, slate_id)
    pool = build_candidate_pool(site, slate_id)
    cash_context = attach_cash_lineup_context(lineup, pool, site, slate_id)

    lineup_total_salary = lineup["salary"].sum()
    rostered_player_ids = set(cash_context["player_id"])

    all_suggestions = []
    for _, cash_row in cash_context.iterrows():
        result = find_pivots_for_player(
            cash_row, pool, rostered_player_ids, site,
            lineup_total_salary, projection_tolerance_pct, top_n,
        )
        if result.empty:
            # Decision #7 -- an empty result is accepted as legitimate
            # information ("no real same-tier alternative on this slate"),
            # not a signal to widen the tolerance until something appears.
            print(
                f"WARNING: no eligible pivot candidates found for "
                f"{cash_row['cash_player_name']} ({cash_row['cash_position']}, "
                f"{cash_row['cash_team']}) within {projection_tolerance_pct:.0f}% "
                f"of cash-player projection tolerance -- thin pool (see "
                f"ROADMAP.md's 'Known Testing Artifact' note) or a "
                f"genuinely unique play with no same-tier, lower-owned "
                f"alternative in range. This is left as-is, not widened.",
                file=sys.stderr,
            )
        elif len(result) < top_n:
            print(
                f"NOTE: only {len(result)}/{top_n} pivot candidates found for "
                f"{cash_row['cash_player_name']} ({cash_row['cash_position']}).",
                file=sys.stderr,
            )
        all_suggestions.append(result)

    out = pd.concat(all_suggestions, ignore_index=True) if all_suggestions else pd.DataFrame(columns=OUTPUT_COLUMNS)
    return out[OUTPUT_COLUMNS] if not out.empty else out


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", choices=["dk", "fd"], required=True)
    parser.add_argument("--slate-id", type=str, required=True)
    parser.add_argument(
        "--projection-tolerance-pct", type=float,
        default=PROJECTION_TOLERANCE_PCT_OF_CASH_PROJECTION,
        help=f"Projection tolerance for a pivot candidate, as a symmetric "
             f"percentage of the cash player's own final_projection "
             f"(decision #3, default "
             f"{PROJECTION_TOLERANCE_PCT_OF_CASH_PROJECTION:.0f}%%).",
    )
    parser.add_argument(
        "--top-n", type=int, default=TOP_N_PIVOTS,
        help=f"Max ranked pivot candidates per cash-lineup player "
             f"(decision #7, default {TOP_N_PIVOTS}).",
    )
    args = parser.parse_args()

    config = SITE_CONFIGS[args.site]
    suggestions = build_pivot_suggestions(
        args.site, args.slate_id,
        projection_tolerance_pct=args.projection_tolerance_pct,
        top_n=args.top_n,
    )
    validate_pivot_suggestions(suggestions, args.site, args.projection_tolerance_pct)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"pivot_suggestions_{args.site}_{args.slate_id}.csv"
    suggestions.to_csv(out_path, index=False)

    n_cash_players = suggestions["cash_player_name"].nunique() if not suggestions.empty else 0
    print(f"[{config['label']}] Wrote {len(suggestions)} pivot suggestion row(s) "
          f"covering {n_cash_players} cash-lineup player(s) to {out_path}")
    print(f"  Projection tolerance: {args.projection_tolerance_pct:.0f}% of "
          f"cash player's own final_projection (symmetric, decision #3)")
    if not suggestions.empty:
        print(f"  leverage_score range: {suggestions['leverage_score'].min():.1f} "
              f"- {suggestions['leverage_score'].max():.1f}")
