"""
derive_actual_results.py
=========================

Companion to Session 9.1 (log_results.py). Builds a real, site-exact
actual-fantasy-points CSV directly from real official box-score stats
(nflverse weekly_stats), instead of from a site's own contest-results
export -- for FanDuel, which unlike DraftKings does not publish a
copy-pasteable post-lock results/ownership page at all (the standing
gap this script exists to close, flagged repeatedly across ROADMAP.md's
"Known Deferred Validations" section).

WHY THIS IS LEGITIMATE, NOT AN ESTIMATE
-----------------------------------------
This does NOT convert or infer FD's points from DK's points, and does NOT
touch ownership at all -- see the "What this does NOT do" section below.
It independently computes FD's real fantasy points from the same real,
official per-play stat line every site scores off of, using
`scoring_rules.py`'s already-measured-exact site scoring tables (Session
10.3a/10.4, verified byte-for-byte against nflverse's own precomputed
column and against real RotoGuru-graded actuals). A player's real
receptions/yards/TDs for a real game is one fact; DK and FD each apply
their own, already-confirmed-correct scoring formula to that same fact.
This script computes FD's side of that directly from the stat line, the
same way `statline_model.py` projects both sites from one shared stat-line
model -- it never looks at DK's number at all.

WHAT THIS DOES NOT DO
-----------------------
Does NOT touch ownership. FD's real ownership percentages are a genuinely
different, unobservable-from-here quantity (which real humans drafted which
players in a real FD contest) -- there is no way to derive that from real
box-score stats, from DK's ownership, or from anything else this pipeline
has access to. ROADMAP.md's ownership-logging section is explicit that
fabricating/estimating unobserved ownership is out of bounds ("log what's
available... do not fabricate or estimate entries for contest types that
can't be observed"). If FD ever starts publishing real post-lock ownership,
log it through `log_ownership.py` like DK; until then, FD stays absent from
`ownership_actual_log.csv`, which is the documented, correct state, not a
gap this script tries to paper over.

USAGE
-----
    python scripts/derive_actual_results.py \\
        --site fd --season 2026 --week 1 \\
        --slate-id fd_classic_wk1_main_13Sep2026 \\
        --output data/results_raw_fd_2026_wk1_main.csv

Then feed the output straight into log_results.py exactly like a real
contest-results export:

    python scripts/log_results.py log --site fd --season 2026 --week 1 \\
        --slate-id fd_classic_wk1_main_13Sep2026 --slate-type regular_season \\
        --input data/results_raw_fd_2026_wk1_main.csv \\
        --source "Derived from real nflverse box-score stats (scoring_rules.py, site-exact), 2026-09-14"

Player names in the output are copied VERBATIM from this slate's own
final_projections_{site}_{slate_id}.csv, not from nflverse's own display
name -- guarantees an exact string match through log_results.py's
normalize_name() lookup rather than depending on it.

SCOPE
-----
Skill positions (QB/RB/WR/TE/K) via `scoring_rules.score_statline()`.
DST via `fit_dst_model.build_panel()` (real per-team-week components,
already used to fit and validate the DST model) + `scoring_rules.score_dst()`.
A reference player with no real stat-line row this week (inactive, DNP,
zero snaps) is scored 0.0, not dropped -- a real, meaningful zero, not a
missing value.

VALIDATION
----------
`--cross-check-dk PATH` optionally re-derives DK's own points the same way
and compares them against a real DK contest-results-derived raw CSV (the
`player_name, actual_fpts` shape `log_results.py` itself consumes) as a
sanity check on this whole derivation path before trusting the FD numbers
built the same way.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUT_DIR = REPO_ROOT / "output"
SCRIPTS_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(SCRIPTS_DIR))
import scoring_rules  # noqa: E402
from ingest_salaries import normalize_name, SITE_CONFIGS  # noqa: E402
from fit_dst_model import load_team_stats, load_games, canonical_team  # noqa: E402


def load_reference(site: str, slate_id: str) -> pd.DataFrame:
    proj_path = OUTPUT_DIR / f"final_projections_{site}_{slate_id}.csv"
    if not proj_path.exists():
        raise SystemExit(f"No projection file found at {proj_path}.")
    ref = pd.read_csv(proj_path, dtype={"player_id": str})
    missing = {"player_id", "player_name", "position", "team"} - set(ref.columns)
    if missing:
        raise SystemExit(f"{proj_path} missing columns {sorted(missing)}.")
    return ref


def derive_skill_actuals(season: int, week: int, site: str) -> pd.DataFrame:
    """Returns player_id -> actual_fpts for QB/RB/WR/TE/K, this site's rules."""
    weekly_path = DATA_DIR / f"weekly_stats_{season}.parquet"
    if not weekly_path.exists():
        raise SystemExit(
            f"{weekly_path} not found -- run "
            f"`python scripts/ingest_historical.py --season {season}` first."
        )
    w = pd.read_parquet(weekly_path)
    w = w[(w["season_type"] == "REG") & (w["week"] == week)]
    w = w[w["position"].isin(["QB", "RB", "WR", "TE", "K"])].copy()
    if w.empty:
        raise SystemExit(
            f"No real REG week={week} season={season} skill-position rows in "
            f"{weekly_path}. Has this week's data been ingested "
            f"(ingest_historical.py) since the games finished?"
        )
    statline = scoring_rules.statline_from_nflverse(w)
    pts = scoring_rules.score_statline(statline, site)
    return pd.DataFrame({"player_id": w["player_id"].to_numpy(),
                         "actual_fpts": pts})


def derive_dst_actuals(season: int, week: int, site: str) -> pd.DataFrame:
    """Returns team (abbrev) -> actual_fpts, this site's DST rules.

    A deliberately lighter single-week version of fit_dst_model.build_panel()
    -- that function expects a FULL season's worth of team_stats to match a
    full season's worth of scheduled games (it fails loud on exactly this
    mismatch, decision #12), which is the correct behavior when fitting a
    model across a season but the wrong shape here: mid-season, team_stats_
    {season}.parquet only has real rows for weeks already played, while
    games.parquet already lists the full published schedule including
    not-yet-played weeks. This function joins only the single requested
    week, so "future week has no stats yet" is expected, not an error --
    no priors are computed here either, since a REALIZED game only needs
    this week's own real components, not history.
    """
    team = load_team_stats([season])
    team = team[team["week"] == week].copy()
    if team.empty:
        raise SystemExit(
            f"No real team_stats_{season}.parquet rows for week={week}. "
            f"Run `python scripts/ingest_historical.py --season {season}` "
            f"after this week's games finish."
        )
    games = load_games([season])
    games = games[games["week"] == week].copy()

    # team_stats already carries its own canonical opponent_team column
    # (load_team_stats canonicalizes it) -- sched supplies only opp_score,
    # which team_stats doesn't have, so it deliberately carries no
    # opponent_team column of its own to avoid a duplicate-column collision
    # on merge.
    rows = []
    for g in games.itertuples():
        for me, opp_score in (
            (g.home_team, g.away_score),
            (g.away_team, g.home_score),
        ):
            rows.append({"team": me, "opp_score": opp_score})
    sched = pd.DataFrame(rows)

    off_cols = ["fg_blocked", "pat_blocked", "pt_blocked", "def_tds"]
    off = team[["team"] + off_cols].copy()
    off.columns = ["opponent_team"] + ["o_" + c for c in off_cols]

    d = team.merge(sched, on=["team"], how="inner")
    d = d.merge(off, on="opponent_team", how="left")

    for c in [c for c in d.columns if c.startswith("o_")] + [
            "def_sacks", "def_interceptions", "fumble_recovery_opp",
            "def_safeties", "def_tds", "special_teams_tds"]:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0.0)

    d["points_allowed"] = (d["opp_score"] - 7.0 * d["o_def_tds"]).clip(lower=0.0)
    d["blocked_kick"] = d["o_fg_blocked"] + d["o_pat_blocked"] + d["o_pt_blocked"]

    components = pd.DataFrame({
        "points_allowed": d["points_allowed"],
        "sack": d["def_sacks"],
        "interception": d["def_interceptions"],
        "fumble_recovery": d["fumble_recovery_opp"],
        "safety": d["def_safeties"],
        "def_td": d["def_tds"],
        "st_td": d["special_teams_tds"],
        "blocked_kick": d["blocked_kick"],
        # Not computed here -- Session 10.4 decision #10 already documents
        # this as one of the small unscoreable-from-nflverse components
        # (blocked-kick/two-point-return edge cases), absorbed into the
        # DST model's fitted residual rather than reconstructed. Left at 0.
        "two_pt_return": 0.0,
    })
    pts = scoring_rules.score_dst(components, site)
    return pd.DataFrame({"team": d["team"].to_numpy(), "actual_fpts": pts})


def derive_for_slate(site: str, season: int, week: int, slate_id: str) -> pd.DataFrame:
    ref = load_reference(site, slate_id)
    defense_values = SITE_CONFIGS[site]["defense_position_values"]
    is_dst = ref["position"].str.upper().isin(defense_values)

    skill_ref = ref[~is_dst].copy()
    dst_ref = ref[is_dst].copy()

    skill_pts = derive_skill_actuals(season, week, site)
    skill_out = skill_ref.merge(skill_pts, on="player_id", how="left")
    n_no_stats = skill_out["actual_fpts"].isna().sum()
    skill_out["actual_fpts"] = skill_out["actual_fpts"].fillna(0.0)
    if n_no_stats:
        print(f"NOTE: {n_no_stats} skill-position player(s) in the pool had no "
              f"real stat-line row this week (inactive/DNP/zero snaps) -- "
              f"scored 0.0, not dropped.")

    if not dst_ref.empty:
        dst_pts = derive_dst_actuals(season, week, site)
        # Decision #12 (fit_dst_model.py): games.parquet/team_stats use
        # nflverse's canonical abbreviations (e.g. "LA" not "LAR"), which
        # don't always match the site salary export's own abbreviation --
        # canonicalize the reference side before joining, same fix already
        # applied throughout fit_dst_model.py.
        dst_ref = dst_ref.copy()
        dst_ref["_canonical_team"] = canonical_team(dst_ref["team"])
        dst_out = dst_ref.merge(
            dst_pts, left_on="_canonical_team", right_on="team",
            how="left", suffixes=("", "_panel"),
        )
        n_dst_missing = dst_out["actual_fpts"].isna().sum()
        if n_dst_missing:
            missing_teams = dst_out.loc[dst_out["actual_fpts"].isna(), "team"].tolist()
            raise SystemExit(
                f"{n_dst_missing} DST row(s) in the pool had no matching real "
                f"team-week in build_panel([{season}]) for week={week}: "
                f"{missing_teams}. A real DST should never be missing -- check "
                f"team abbreviations line up between final_projections and "
                f"games.parquet/team_stats."
            )
        out = pd.concat([skill_out, dst_out], ignore_index=True)
    else:
        out = skill_out

    return out[["player_name", "actual_fpts"]].copy()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Derive real actual fantasy points for a slate directly from real "
            "nflverse box-score stats, using scoring_rules.py's site-exact "
            "scoring. Does NOT touch ownership -- see module docstring."
        )
    )
    parser.add_argument("--site", choices=["dk", "fd"], required=True)
    parser.add_argument("--season", type=int, required=True,
                        help="Real NFL season (e.g. 2026).")
    parser.add_argument("--week", type=int, required=True,
                        help="Real NFL week number.")
    parser.add_argument("--slate-id", required=True,
                        help="Matches final_projections_{site}_{slate_id}.csv.")
    parser.add_argument("--output", type=Path, required=True,
                        help="Where to write the player_name,actual_fpts CSV.")
    parser.add_argument(
        "--cross-check-dk", type=Path, default=None,
        help=(
            "Optional: path to a real DK player_name,actual_fpts CSV (e.g. "
            "data/results_raw_dk_2026_wk1.csv) to sanity-check this script's "
            "derivation path by re-deriving DK's own points from real stats "
            "and comparing. Only meaningful with --site dk."
        ),
    )
    args = parser.parse_args()

    out = derive_for_slate(args.site, args.season, args.week, args.slate_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False)
    print(f"Wrote {len(out)} rows to {args.output}.")
    print(out.sort_values("actual_fpts", ascending=False).head(10).to_string(index=False))

    if args.cross_check_dk:
        real = pd.read_csv(args.cross_check_dk)
        real["normalized_name"] = real["player_name"].map(normalize_name)
        derived = out.copy()
        derived["normalized_name"] = derived["player_name"].map(normalize_name)
        cmp = real.merge(derived, on="normalized_name", suffixes=("_real", "_derived"))
        diff = cmp["actual_fpts_derived"] - cmp["actual_fpts_real"]
        print(f"\nCross-check vs {args.cross_check_dk}: {len(cmp)}/{len(real)} "
              f"players matched. Max abs diff: {diff.abs().max():.3f}, "
              f"mean diff: {diff.mean():+.4f}.")
        bad = cmp[diff.abs() > 0.05]
        if not bad.empty:
            print(f"WARNING: {len(bad)} player(s) differ by >0.05 pts:")
            print(bad[["player_name_real", "actual_fpts_real", "actual_fpts_derived"]]
                  .to_string(index=False))
        else:
            print("All matched players reproduce the real site export exactly "
                  "(within float rounding). Derivation path confirmed.")


if __name__ == "__main__":
    main()
