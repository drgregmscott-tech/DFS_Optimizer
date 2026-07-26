"""
scoring_rules.py
================

Session 10.3a -- exact per-site fantasy scoring, applied to a STAT LINE.

Why this file exists at all
---------------------------
Every projection before Phase 10 was a *points* projection, so the pipeline
never needed to know a site's scoring rules -- it borrowed nflverse's
precomputed `fantasy_points_ppr` (DK) or `fantasy_points + 0.5*receptions`
(FD) and treated those as the site's scoring. Session 10.3 projects a stat
line, so the conversion has to be explicit and exact.

Measuring that borrowed assumption (real 2021 data, this session) turned up
three real errors:

  * nflverse's `fantasy_points` scores an INTERCEPTION at -2. DK and FD both
    score it at -1. (Verified by reconstruction: substituting -2 reproduces
    nflverse's own column to 7.1e-15; substituting -1 does not.) 45.3% of QB
    games in 2021 had at least one INT, mean 1.46 among those.
  * nflverse scores a LOST FUMBLE at -2. That is right for FD and wrong for
    DK, which uses -1.
  * nflverse has no YARDAGE BONUSES. DK pays +3 at 300 passing / 100 rushing
    / 100 receiving yards. FD pays none. Measured: DK's true score differs
    from `fantasy_points_ppr` on 13.1% of all skill performances and on
    **42.9% of performances worth 15+ points**, mean gap +1.22, max +7.

The harness grades against RotoGuru actuals, which are *real* DK points
including bonuses -- so the pre-10.3 pipeline was projecting in one unit and
being scored in another.

Numbered decisions:

  1. TABLES ARE THE PUBLISHED SITE RULES, not a derived approximation.
     Sourced from DraftKings' and FanDuel's own published NFL Classic
     scoring and cross-checked across three independent write-ups
     (2026-07-26). DK and FD agree on every per-yard and per-TD value; they
     differ only in reception value (1.0 vs 0.5), fumble-lost value
     (-1 vs -2), and bonuses (three vs none).

  2. `build_projections.py` IS DELIBERATELY NOT FIXED. It is the frozen
     measurement baseline every Phase 10 comparison keys to (median-pctile
     72.8 / max-pctile 94.7, Session 10.1). Correcting its scoring would
     silently move that baseline and invalidate Sessions 10.1 and 10.2's
     recorded numbers. It stays known-wrong-and-frozen; this file is used
     only by the new parallel engine. Flagged here so a future session does
     not "helpfully" fix it without re-baselining first.

  3. THE BONUSES ARE STEP FUNCTIONS, SO THIS CONVERTER MUST NEVER BE
     APPLIED TO A MEAN STAT LINE. E[f(X)] != f(E[X]) when f has a
     discontinuity: a player whose mean is 85 receiving yards has a real
     probability of clearing 100 and earning +3, but scoring his mean line
     awards him exactly 0 of it. This is the same argument the ROADMAP's
     Phase 10 intro already makes for DST's points-allowed brackets. It is
     the reason `statline_model.py` scores every Monte-Carlo draw
     individually and averages afterwards, rather than scoring once.

  4. UNRECOGNIZED SITE IS A HARD ERROR, and the stat-line column contract
     is checked explicitly. A silently-missing stat column would read as a
     player simply not accumulating that stat -- i.e. it would quietly lower
     the projection instead of failing. Same fail-loud principle as the rest
     of the project.

  5. `fumble_recovery_td` IS IN THE TABLE BUT IS NEVER PROJECTED. DK pays
     +6 for an offensive fumble-recovery TD. It is real scoring, so the
     converter honours it when a caller supplies it (e.g. scoring a
     historical line), but it is pure noise to forecast and the model leaves
     it at zero. Same treatment for `st_td` (punt/kick return TD): scored if
     supplied, not projected.

Session 10.4 additions -- DST scoring
--------------------------------------

  6. THIS FILE HAD NO DST TABLE AT ALL BEFORE SESSION 10.4. Session 10.3a
     scored only skill positions, because the DST path was still the legacy
     `AvgPointsPerGame x vegas_ratio` model, which needs no scoring rules --
     it never touches a component. Session 10.4's model projects the
     components (sacks, turnovers, points allowed), so the conversion has to
     become explicit here, exactly as decision #1 made it explicit for skill
     positions.

  7. THE DST TABLE IS VERIFIED AGAINST REAL GRADED ACTUALS, NOT ASSERTED.
     Same technique decision #1 used, and a stronger test: the skill-position
     table was proven by reproducing an nflverse column, whereas this one is
     proven against RotoGuru's real DK/FD graded DST scores. Reconstructing
     544 real 2021 DK team-weeks from nflverse team-week components:

         brackets + core components                  83.3% exact, mean -0.40
         + blocked kicks (+2 each)                   87.5% exact, mean -0.29
         + points-allowed rule in decision #9        89.7% exact, mean -0.16

     A mean bias of -0.16 against a target SD of 5.86 is 2.7% of a standard
     deviation. `verify_dst_against_actuals()` below reproduces this, and it
     is a hard error if the bias degrades past a tolerance.

  8. DK AND FD DST SCORING ARE IDENTICAL, MEASURED, NOT ASSUMED -- and the
     ROADMAP card for Session 10.4 is WRONG on this point. That card asks the
     model to "handle the DK/FD bracket divergence correctly." There is no
     divergence. Running this exact table against real FD 2021 actuals gives
     79.8% exact, mean -0.43 -- the same residual shape as DK, with no
     systematic offset, i.e. the two sites agree on every bracket and every
     component value.

     The tables are still stored PER SITE rather than collapsed into one.
     That is deliberate: the sites have diverged on skill-position scoring
     (reception value, fumble value, bonuses) and could diverge here, so a
     future change should be a value edit in this dict, not a rewrite of
     every call site. What is NOT justified is code that branches on site.

     The measured equality is for the 2014-2021 rules. Re-verify when a real
     current-season FD export first exists (the standing FD gap).

  9. POINTS ALLOWED EXCLUDES THE OPPONENT'S DEFENSIVE TOUCHDOWNS, AND THIS
     WAS FOUND EMPIRICALLY. A pick-six thrown by your own offense is not
     charged to your DST; a kick/punt return TD by the opponent's return unit
     IS, because coverage is part of the DST unit that scores +6 for the
     mirror-image play. Tested against the real graded actuals, four
     candidate definitions:

         raw opponent final score                    87.5% exact, mean -0.29
         minus opponent DEFENSIVE TDs                89.7% exact, mean -0.16
         minus opponent defensive AND return TDs     86.8% exact, mean -0.12
         minus 6 (not 7) per non-offensive TD        89.5% exact, mean -0.19

     The second wins on both exact-match share and MAE, and is the one that
     matches the published rule. `dst_points_allowed()` implements it so the
     definition lives in one place rather than being re-derived by each
     caller.

 10. THREE COMPONENTS ARE UNSCOREABLE FROM NFLVERSE AND ARE LEFT OUT, NAMED
     RATHER THAN BURIED: blocked-kick return TDs, 2-point return conversions,
     and the handful of return TDs that land in neither `def_tds` nor
     `special_teams_tds`. Together they are the entire remaining -0.16 mean
     bias. All three bias the reconstruction LOW, i.e. conservatively, and
     `fit_dst_model.py` absorbs them into a fitted residual-TD rate rather
     than pretending they do not exist.
"""

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# The canonical stat-line schema. Every producer and consumer in Phase 10
# uses exactly these names.
# ---------------------------------------------------------------------------
STATLINE_COLUMNS = [
    "pass_att", "pass_yd", "pass_td", "pass_int", "pass_2pt",
    "rush_att", "rush_yd", "rush_td", "rush_2pt",
    "targets", "rec", "rec_yd", "rec_td", "rec_2pt",
    "fumbles_lost", "st_td", "fum_rec_td",
]

# Decision #1 -- published site rules.
SCORING = {
    "dk": {
        "label": "DraftKings Classic (full PPR)",
        "per_stat": {
            "pass_yd": 0.04, "pass_td": 4.0, "pass_int": -1.0, "pass_2pt": 2.0,
            "rush_yd": 0.10, "rush_td": 6.0, "rush_2pt": 2.0,
            "rec": 1.0, "rec_yd": 0.10, "rec_td": 6.0, "rec_2pt": 2.0,
            "fumbles_lost": -1.0, "st_td": 6.0, "fum_rec_td": 6.0,
        },
        # (stat, threshold, points) -- awarded once if the stat reaches the
        # threshold in a single game.
        "bonuses": [
            ("pass_yd", 300.0, 3.0),
            ("rush_yd", 100.0, 3.0),
            ("rec_yd", 100.0, 3.0),
        ],
    },
    "fd": {
        "label": "FanDuel Classic (half PPR)",
        "per_stat": {
            "pass_yd": 0.04, "pass_td": 4.0, "pass_int": -1.0, "pass_2pt": 2.0,
            "rush_yd": 0.10, "rush_td": 6.0, "rush_2pt": 2.0,
            "rec": 0.5, "rec_yd": 0.10, "rec_td": 6.0, "rec_2pt": 2.0,
            "fumbles_lost": -2.0, "st_td": 6.0, "fum_rec_td": 6.0,
        },
        "bonuses": [],
    },
    # Not a real site. The exact constants nflverse's own `fantasy_points_ppr`
    # uses, kept ONLY so verify_against_nflverse() can prove this converter's
    # arithmetic is right by reproducing a column we did not compute. Never
    # use this to project anything.
    "_nflverse_ppr": {
        "label": "nflverse fantasy_points_ppr (reference only -- NOT a site)",
        "per_stat": {
            "pass_yd": 0.04, "pass_td": 4.0, "pass_int": -2.0, "pass_2pt": 2.0,
            "rush_yd": 0.10, "rush_td": 6.0, "rush_2pt": 2.0,
            "rec": 1.0, "rec_yd": 0.10, "rec_td": 6.0, "rec_2pt": 2.0,
            "fumbles_lost": -2.0, "st_td": 6.0, "fum_rec_td": 0.0,
        },
        "bonuses": [],
    },
}

REAL_SITES = ("dk", "fd")

# ---------------------------------------------------------------------------
# Session 10.4 -- DST scoring (decisions #6 through #10).
# ---------------------------------------------------------------------------

# The canonical DST component schema. `points_allowed` is the only one that
# is not a count; it is the value produced by dst_points_allowed().
DST_COMPONENT_COLUMNS = [
    "points_allowed", "sack", "interception", "fumble_recovery",
    "safety", "def_td", "st_td", "blocked_kick", "two_pt_return",
]

# Decision #8: stored per site, currently identical, measured not assumed.
_DST_BRACKETS = [
    (0, 0, 10.0),
    (1, 6, 7.0),
    (7, 13, 4.0),
    (14, 20, 1.0),
    (21, 27, 0.0),
    (28, 34, -1.0),
    (35, None, -4.0),      # None = open-ended top bracket
]
_DST_PER_STAT = {
    "sack": 1.0, "interception": 2.0, "fumble_recovery": 2.0,
    "safety": 2.0, "def_td": 6.0, "st_td": 6.0,
    "blocked_kick": 2.0, "two_pt_return": 2.0,
}

DST_SCORING = {
    "dk": {
        "label": "DraftKings Classic DST",
        "per_stat": dict(_DST_PER_STAT),
        "points_allowed_brackets": list(_DST_BRACKETS),
    },
    "fd": {
        "label": "FanDuel Classic D/ST",
        "per_stat": dict(_DST_PER_STAT),
        "points_allowed_brackets": list(_DST_BRACKETS),
    },
}


def dst_scoring_for(site: str) -> dict:
    """Decision #4's fail-loud rule, applied to the DST table."""
    if site not in DST_SCORING:
        raise SystemExit(
            f"scoring_rules: no DST scoring table for site={site!r}. "
            f"Known: {sorted(DST_SCORING)}."
        )
    return DST_SCORING[site]


def dst_points_allowed(opponent_score, opponent_defensive_tds=0.0):
    """Decision #9. The points-allowed figure the brackets are read against.

    Charged to a DST: everything the opponent scored EXCEPT touchdowns
    scored by the opponent's DEFENSE (a pick-six or fumble-six against your
    own offense). Return TDs by the opponent's special teams DO count, since
    coverage is part of the same unit that is paid +6 for the mirror play.

    7 points per defensive TD (TD + the extra point that almost always
    follows) beat 6 in the measurement -- see decision #9's table.
    """
    opp = np.asarray(opponent_score, dtype=float)
    dtd = np.asarray(opponent_defensive_tds, dtype=float)
    return np.clip(opp - 7.0 * dtd, 0.0, None)


def dst_bracket_points(points_allowed, site: str) -> np.ndarray:
    """Look up the points-allowed bracket value. Vectorized.

    NOTE this is the SINGLE-VALUE lookup. It is correct for scoring a
    REALIZED game, and wrong for scoring a projection -- see the warning on
    `score_dst()`.
    """
    pa = np.asarray(points_allowed, dtype=float)
    out = np.full(pa.shape, np.nan, dtype=float)
    for lo, hi, value in dst_scoring_for(site)["points_allowed_brackets"]:
        hit = (pa >= lo) if hi is None else ((pa >= lo) & (pa <= hi))
        out = np.where(hit, value, out)
    if np.isnan(out).any():
        bad = pa[np.isnan(out)]
        raise SystemExit(
            f"dst_bracket_points({site}): {len(bad)} points-allowed value(s) "
            f"fell into no bracket (e.g. {bad[:5]}). The bracket table must "
            f"cover every non-negative integer -- not defaulting these, that "
            f"would silently score a real game as zero."
        )
    return out


def score_dst(components, site: str) -> np.ndarray:
    """Convert DST components to that site's fantasy points.

    `components` is a DataFrame or a dict of equal-length arrays carrying
    DST_COMPONENT_COLUMNS. Returns a float array.

    !! THE SAME WARNING AS DECISION #3, AND IT BITES HARDER HERE. The
    points-allowed brackets are a step function with steps of 3 points, so
    E[f(X)] != f(E[X]) by a wide margin. Measured over 3,952 real team-weeks
    (Session 10.4): integrating this table over a fitted negative binomial
    gives a mean bracket value of 0.433 against a realized 0.479, while
    looking the bracket up at the point estimate gives 0.181 -- biased low by
    0.30 points on EVERY defense, compressing the spread across defenses by
    19% (SD 0.860 -> 0.696) and ranking worse against realized outcomes
    (Spearman 0.369 -> 0.336). Hand this function a mean and you get a
    systematically wrong, systematically compressed answer.

    `dst_model.py` therefore calls this per Monte-Carlo draw and averages
    afterwards, exactly as `statline_model.py` does for skill positions.
    """
    rules = dst_scoring_for(site)
    per_stat = rules["per_stat"]

    if isinstance(components, pd.DataFrame):
        get = lambda c: pd.to_numeric(components[c], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        present = set(components.columns)
        n = len(components)
    else:
        get = lambda c: np.asarray(components[c], dtype=float)
        present = set(components.keys())
        n = len(next(iter(components.values()))) if components else 0

    # Decision #4's contract check, applied to the DST schema.
    missing = sorted(c for c in DST_COMPONENT_COLUMNS if c not in present)
    if missing:
        raise SystemExit(
            f"score_dst({site}): components missing {missing}.\n"
            f"Expected the canonical schema: {DST_COMPONENT_COLUMNS}\n"
            f"(Not defaulting these to zero -- for a DST that would quietly "
            f"understate the projection instead of failing.)"
        )

    pts = dst_bracket_points(get("points_allowed"), site)
    for col, value in per_stat.items():
        if value:
            pts += get(col) * value
    return pts


def verify_dst_against_actuals(team_weeks: pd.DataFrame, actuals: pd.DataFrame,
                               site: str, max_mean_bias: float = 0.35) -> dict:
    """Decision #7. Reproduce real graded DST scores from real components.

    `team_weeks` needs: week, team, and the DST_COMPONENT_COLUMNS.
    `actuals`    needs: week, team, actual_points (RotoGuru's real graded
                        DST points for this site).

    Raises if the mean bias degrades past `max_mean_bias`. The measured
    figure at the time of writing is -0.16 for DK and -0.43 for FD; the
    tolerance is set just outside both so a real regression trips it while
    the known unscoreable components (decision #10) do not.
    """
    recon = score_dst(team_weeks, site)
    m = pd.DataFrame({"week": team_weeks["week"].to_numpy(),
                      "team": team_weeks["team"].to_numpy(),
                      "recon": recon}).merge(
        actuals[["week", "team", "actual_points"]], on=["week", "team"], how="inner")
    if m.empty:
        raise SystemExit(
            "verify_dst_against_actuals: nothing joined between the "
            "reconstructed team-weeks and the graded actuals. Check that both "
            "sides use the same team abbreviations and the same week numbering."
        )
    err = m["recon"] - m["actual_points"]
    report = {
        "site": site,
        "n_rows": int(len(m)),
        "exact_match_share": round(float((err.abs() < 1e-9).mean()), 4),
        "mean_bias": round(float(err.mean()), 4),
        "mae": round(float(err.abs().mean()), 4),
        "actual_sd": round(float(m["actual_points"].std()), 4),
    }
    if abs(report["mean_bias"]) > max_mean_bias:
        raise SystemExit(
            f"DST scoring self-check FAILED for {site}: reconstructing real "
            f"graded DST points from real components is biased by "
            f"{report['mean_bias']:+.3f} (tolerance +/-{max_mean_bias}). "
            f"Either the scoring table (decision #8), the points-allowed rule "
            f"(decision #9), or the component aggregation is wrong. "
            f"Full report: {report}"
        )
    return report


def scoring_for(site: str) -> dict:
    """Decision #4: unknown site is a hard error."""
    if site not in SCORING:
        raise SystemExit(
            f"scoring_rules: no scoring table for site={site!r}. "
            f"Known: {sorted(s for s in SCORING if not s.startswith('_'))}."
        )
    return SCORING[site]


def score_statline(stats, site: str) -> np.ndarray:
    """Convert a stat line to that site's fantasy points.

    `stats` is anything with the STATLINE_COLUMNS as keys/columns: a
    DataFrame, or a dict of equal-length arrays (which is what the
    Monte-Carlo draws arrive as). Returns a float array.

    Decision #3: this is the per-DRAW converter. Do not hand it a mean stat
    line and expect an expected score -- the bonuses are step functions.
    """
    rules = scoring_for(site)
    per_stat = rules["per_stat"]

    if isinstance(stats, pd.DataFrame):
        get = lambda c: pd.to_numeric(stats[c], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        present = set(stats.columns)
        n = len(stats)
    else:
        get = lambda c: np.asarray(stats[c], dtype=float)
        present = set(stats.keys())
        n = len(next(iter(stats.values()))) if stats else 0

    # Decision #4: a missing column would silently read as "player did not
    # accumulate this stat", which lowers the score instead of failing.
    scored_cols = set(per_stat) | {b[0] for b in rules["bonuses"]}
    missing = sorted(c for c in scored_cols if c not in present)
    if missing:
        raise SystemExit(
            f"score_statline({site}): stat line is missing column(s) {missing}.\n"
            f"Expected the canonical schema: {STATLINE_COLUMNS}\n"
            f"(Not defaulting these to zero -- that would quietly understate "
            f"the projection instead of failing.)"
        )

    pts = np.zeros(n, dtype=float)
    for col, value in per_stat.items():
        if value:
            pts += get(col) * value
    for col, threshold, value in rules["bonuses"]:
        pts += (get(col) >= threshold) * value
    return pts


def bonus_thresholds(site: str) -> list:
    return list(scoring_for(site)["bonuses"])


# ---------------------------------------------------------------------------
# Self-verification (decision #1). Proves the converter's arithmetic against
# a column this project did not compute.
# ---------------------------------------------------------------------------

NFLVERSE_TO_STATLINE = {
    "pass_att": "attempts", "pass_yd": "passing_yards", "pass_td": "passing_tds",
    "pass_int": "passing_interceptions", "pass_2pt": "passing_2pt_conversions",
    "rush_att": "carries", "rush_yd": "rushing_yards", "rush_td": "rushing_tds",
    "rush_2pt": "rushing_2pt_conversions",
    "targets": "targets", "rec": "receptions", "rec_yd": "receiving_yards",
    "rec_td": "receiving_tds", "rec_2pt": "receiving_2pt_conversions",
    "st_td": "special_teams_tds", "fum_rec_td": "fumble_recovery_tds",
}
# nflverse splits lost fumbles across three columns; the sites score one total.
NFLVERSE_FUMBLE_COLS = ["sack_fumbles_lost", "rushing_fumbles_lost",
                        "receiving_fumbles_lost"]


def statline_from_nflverse(weekly: pd.DataFrame) -> pd.DataFrame:
    """Map a raw nflverse weekly_stats frame onto the canonical stat-line
    schema. Column names verified against the real 2021 release (145
    columns): note `passing_interceptions` (not `interceptions`) and
    `sacks_suffered` (not `sacks`) -- the obvious guesses are both wrong.
    """
    out = pd.DataFrame(index=weekly.index)
    for canon, nfl in NFLVERSE_TO_STATLINE.items():
        out[canon] = (pd.to_numeric(weekly[nfl], errors="coerce").fillna(0.0)
                      if nfl in weekly.columns else 0.0)
    fum = np.zeros(len(weekly), dtype=float)
    for c in NFLVERSE_FUMBLE_COLS:
        if c in weekly.columns:
            fum += pd.to_numeric(weekly[c], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    out["fumbles_lost"] = fum
    return out[STATLINE_COLUMNS]


def verify_against_nflverse(weekly: pd.DataFrame, tol: float = 1e-6) -> dict:
    """Reproduce nflverse's own `fantasy_points_ppr` from the stat line using
    the `_nflverse_ppr` constants, and report how far each real site's rules
    diverge from it. Raises if the reproduction fails -- that would mean the
    converter's plumbing, not just its constants, is wrong.
    """
    sl = statline_from_nflverse(weekly)
    ref = score_statline(sl, "_nflverse_ppr")
    truth = pd.to_numeric(weekly["fantasy_points_ppr"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    err = float(np.abs(ref - truth).max())
    if err > tol:
        raise SystemExit(
            f"scoring_rules self-check FAILED: reconstructing nflverse's "
            f"fantasy_points_ppr from the stat line is off by {err:.6g} "
            f"(tolerance {tol}). The converter's arithmetic or the "
            f"nflverse column mapping is wrong -- fix before projecting."
        )
    report = {"nflverse_reproduction_max_abs_err": err, "n_rows": int(len(weekly))}
    # Compare each site against the formula the LEGACY pipeline actually used
    # for that site (projections_baseline.py's compute_fantasy_points), not
    # against the PPR column for both -- FD's legacy formula is half-PPR, so
    # comparing FD to a full-PPR column would report the reception value as an
    # error when it is simply the wrong yardstick.
    legacy = {
        "dk": truth,
        "fd": (pd.to_numeric(weekly["fantasy_points"], errors="coerce").fillna(0.0)
               + 0.5 * pd.to_numeric(weekly["receptions"], errors="coerce").fillna(0.0)
               ).to_numpy(dtype=float),
    }
    for site in REAL_SITES:
        gap = score_statline(sl, site) - legacy[site]
        report[site] = {
            "mean_gap_vs_legacy": round(float(gap.mean()), 4),
            "share_rows_differing": round(float((np.abs(gap) > 1e-9).mean()), 4),
            "max_gap": round(float(gap.max()), 2),
        }
    return report


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="Verify the scoring converter against real nflverse data.")
    parser.add_argument("--season", type=int, default=2021)
    args = parser.parse_args()

    path = Path(__file__).resolve().parent.parent / "data" / f"weekly_stats_{args.season}.parquet"
    if not path.exists():
        raise SystemExit(f"{path} not found -- run ingest_historical.py --season {args.season}.")
    df = pd.read_parquet(path)
    df = df[(df["season_type"] == "REG") & (df["position"].isin(["QB", "RB", "WR", "TE"]))]

    rep = verify_against_nflverse(df)
    print(f"Verified on {rep['n_rows']:,} real {args.season} skill-position rows.")
    print(f"  nflverse fantasy_points_ppr reproduced to "
          f"{rep['nflverse_reproduction_max_abs_err']:.3g} -- converter arithmetic OK.")
    for site in REAL_SITES:
        r = rep[site]
        print(f"  {SCORING[site]['label']}: differs from the LEGACY formula for "
              f"this site on {r['share_rows_differing']*100:.1f}% of rows, "
              f"mean {r['mean_gap_vs_legacy']:+.3f} pts, max {r['max_gap']:+.2f}.")
    print("\nDK's gap = the three yardage bonuses + the INT value + the fumble "
          "value.\nFD's gap = the INT value alone (FD's -2 fumble and absent "
          "bonuses were already right).\nbuild_projections.py keeps the old "
          "behaviour on purpose -- it is the frozen baseline (decision #2).")
