"""
fit_sigma_recalibration.py
==========================

Session 10.4b -- Sigma Dispersion Recalibration (FITTER).

Writes `data/sigma_recalibration.json`. Deliberately separate from the
consumer (`sigma_recalibration.py`) so the production projection path never
imports fitting machinery -- same split as Session 10.2's
`salary_anchor`/`fit_salary_anchor` and Session 10.4's
`dst_model`/`fit_dst_model`.

Read `sigma_recalibration.py`'s module docstring for WHAT is being corrected
and WHY it had to happen before Session 10.5. This file documents HOW.

It also OWNS the row-collection routine (`collect_rows`), which
`probe_sigma_quality.py` imports rather than duplicating. That direction is
deliberate: the probe is an explicit throwaway, and a production artifact
must not depend on a script the project intends to delete. When the probe
goes, nothing here breaks.

THE FIT

Per position, over a set of real player-weeks:

  1. Bin players into quantiles of PROJECTED sigma (deciles by default).
  2. In each bin, measure realized dispersion as the residual SD of
     (actual - projection) AROUND THAT BIN'S OWN MEAN ERROR -- decision #1
     of the consumer: bias belongs in the mean term, not the variance term.
  3. Regress log(realized dispersion) on log(mean projected sigma) across
     bins, unweighted (quantile bins carry near-equal n by construction).
     Slope = `b`, exp(intercept) = `a`.

That single regression yields BOTH parameters, so the level is not a
separately tuned knob. The resulting overall calibration is then a
validation, not a fitted quantity -- and it is printed as such.

Numbered decisions (continuing the consumer's numbering):

  7. HOLDOUT BY DEFAULT. `--fit-seasons` defaults to 2014-2017, leaving
     2018-2021 free for measurement. This is the same discipline Session
     10.3a learned the hard way: fitting `statline_variance.json` on the
     season then measured inflated the effect roughly THREEFOLD and would
     have gone into the log as a finding. The script prints a loud warning
     if a fit window overlaps the standard 2018-2021 measurement window,
     mirroring `fit_dst_model.py`'s own guard.

  8. GUARDS COUNT BINS, NOT ROWS. Session 10.2 fixed exactly this hole in
     `fit_salary_anchor.py` -- it counted ROWS and let a 3-knot curve
     through twice. A position needs enough ROWS, enough ROWS PER BIN, and
     enough USABLE BINS, and all three are hard errors. A curve fit on four
     points is not a curve.

  9. `b` IS CLAMPED TO [0, 1], LOUDLY, AND THE RAW VALUE IS STORED. b > 1
     would mean the model is UNDER-dispersed, contradicting the measurement
     this session exists to correct; b < 0 would mean sigma is
     anti-informative, contradicting probe B3's +0.31 to +0.45 Spearman.
     Either is a signal to investigate, not to ship -- but silently
     clamping would hide it, so `b_raw` and `b_clamped` both go in the
     artifact and a warning is printed.

 10. DST IS FIT LIKE EVERY OTHER POSITION, AND A NEAR-ZERO `b` IS THE
     EXPECTED, CORRECT OUTCOME -- not a failure. Three independent probe
     results agree that DST sigma carries no per-player discrimination:
     it is nearly constant (slope 0.055 on projection, resid/sigma 0.021),
     lambda ~= 0.14 is needed to flip 5% of DST pairs against a useful grid
     topping out near 0.055, and Spearman(sigma, |error|) = +0.076. A fitted
     b near 0 simply encodes that, collapsing DST sigma toward a constant at
     the right LEVEL (probe B1 measured 0.930 against Session 10.4's
     recorded 0.931). This is a mild amendment to Session 10.4's record,
     which established that DST sigma varies with the opponent but never
     tested whether that variation predicts which defense actually busts.

 11. WEEK 1 IS SKIPPED unless `--volume-prior`, mirroring the harness and
     the probe exactly. The default arm here is the current reference
     configuration: stat-line engine, distributional DST, volume prior OFF.

 12. COLLECTION AND FITTING ARE SEPARABLE. `--rows` fits from a previously
     collected frame instead of rebuilding projections, and `--rows-out`
     names the frame written by a collection run. The rebuild is the
     expensive part and is completely independent of the fit, so iterating
     on bin counts or guards costs seconds rather than an hour.

Usage:
    python scripts/fit_sigma_recalibration.py --site dk
    python scripts/fit_sigma_recalibration.py --site dk --fit-seasons 2014 2015 2016 2017
    python scripts/fit_sigma_recalibration.py --site dk --rows output/sigma_rows_fit_dk.csv
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUT_DIR = REPO_ROOT / "output"
SCRIPTS_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(SCRIPTS_DIR))
from ingest_salaries import normalize_team  # noqa: E402
from sigma_recalibration import (  # noqa: E402
    ARTIFACT_PATH, SCHEMA_VERSION, normalize_position,
)

POSITIONS = ["QB", "RB", "WR", "TE", "DST"]

DEFAULT_FIT_SEASONS = [2014, 2015, 2016, 2017]      # decision #7
MEASUREMENT_SEASONS = {2018, 2019, 2020, 2021}      # decision #7

# Decision #8. All three are hard errors, none is a soft warning.
DEFAULT_N_BINS = 10
MIN_ROWS_PER_POSITION = 400
MIN_ROWS_PER_BIN = 50
MIN_USABLE_BINS = 6


# ---------------------------------------------------------------------------
# Collection -- owned here, imported by probe_sigma_quality.py
# ---------------------------------------------------------------------------

def collect_week(site: str, season: int, week: int, games, statline: dict,
                 dst_model_mode: str, prior: dict) -> pd.DataFrame:
    """Reproduces the backtest harness's per-week setup and returns the
    optimizer-visible pool joined to real graded actuals.

    Calls the harness's own functions rather than reimplementing them -- the
    harness's decision #4, and this project's repeated lesson that only real
    runs through the real functions catch the real bugs.

    Stated loudly: this OVERWRITES `output/final_projections_{site}_{week}.csv`
    exactly the way the harness does. The harness regenerates it per week, so
    nothing is lost, but do not run this concurrently with a backtest.
    """
    import backtest_harness as bh

    slate_id = f"rotoguru_{season}_wk{week}"
    salary_path = DATA_DIR / f"salaries_{site}_{slate_id}.csv"
    if not salary_path.exists():
        raise RuntimeError(f"missing {salary_path.name} (run batch_match_rotoguru.py)")

    bh.ensure_per_season_schedule(season)
    bh.build_vegas_file(games, site, season, week)
    proj_path = bh.run_projection_pipeline(
        site, season, week, slate_id, anchor=None, engine="statline",
        statline=statline, dst_model_mode=dst_model_mode, prior=prior,
    )

    proj = pd.read_csv(proj_path, dtype={"player_id": str, "site_player_id": str})
    for col in ("sigma", "statline_p10", "statline_p90"):
        if col not in proj.columns:
            raise RuntimeError(
                f"{proj_path.name} has no '{col}' column -- this requires the "
                f"stat-line engine's output schema (Session 10.3a)."
            )

    main_teams = bh.sunday_main_slate_teams(games, season, week)
    main_teams_norm = {normalize_team(t, site) for t in main_teams}
    pool = proj[proj["team"].isin(main_teams_norm)].copy()
    pool = pool[pool["final_projection"] > 0].copy()
    if len(pool) < 20:
        raise RuntimeError(f"main-slate pool too small ({len(pool)} players)")

    actuals = bh.load_actuals(site, season)
    pts = actuals[actuals["week"] == week].set_index("gid")["actual_points"]

    pool["position"] = pool["position"].map(normalize_position)
    pool["actual_points"] = pool["site_player_id"].map(pts)
    pool["joined"] = pool["actual_points"].notna()
    pool["season"] = season
    pool["week"] = week

    keep = ["season", "week", "player_id", "site_player_id", "player_name",
            "position", "team", "salary", "final_projection", "sigma",
            "statline_p10", "statline_p90", "sigma_source", "actual_points",
            "joined"]
    return pool[[c for c in keep if c in pool.columns]]


def collect_rows(site: str, seasons: list, weeks: list = None,
                 all_weeks: bool = True, statline: dict = None,
                 dst_model_mode: str = "distributional",
                 prior: dict = None) -> pd.DataFrame:
    """Per-week isolation (the harness's decision #5): a week that cannot be
    built is recorded and the run continues, but is never silently dropped."""
    import backtest_harness as bh

    statline = statline or {"sims": 4000, "seed": 20103}
    prior = prior or {"on": False, "floor": None, "k": None, "role_change": True}

    games = bh.load_games()
    frames, errors = [], []
    week1_ok = bool(prior and prior["on"])  # decision #11

    for season in seasons:
        wk_list = weeks if weeks else (list(range(1, 19)) if all_weeks else [10])
        for week in wk_list:
            if week == 1 and not week1_ok:
                print(f"  {season} wk{week:<2d} SKIP  (week 1 needs --volume-prior)")
                continue
            try:
                df = collect_week(site, season, week, games, statline,
                                  dst_model_mode, prior)
            except Exception as e:  # noqa: BLE001
                errors.append((season, week, f"{type(e).__name__}: {e}"))
                print(f"  {season} wk{week:<2d} ERROR {str(e)[:110]}")
                continue
            frames.append(df)
            print(f"  {season} wk{week:<2d} OK    {len(df):4d} pool players, "
                  f"{df['joined'].mean()*100:5.1f}% joined to actuals")

    if errors:
        print(f"\n  {len(errors)} week(s) errored and are excluded. First three:")
        for s, w, m in errors[:3]:
            print(f"    {s} wk{w}: {m[:150]}")
        print("  (Seasons before 2021 have 17 weeks -- a wk18 miss there is "
              "expected, not a fault.)")
    if not frames:
        raise SystemExit("No weeks collected -- nothing to fit.")
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# The fit
# ---------------------------------------------------------------------------

def fit_position(g: pd.DataFrame, pos: str, n_bins: int) -> dict:
    """One position's power curve. Raises on any guard failure (decision #8)."""
    g = g[g["sigma"] > 0].copy()
    if len(g) < MIN_ROWS_PER_POSITION:
        raise RuntimeError(
            f"{pos}: only {len(g)} usable rows, need >= {MIN_ROWS_PER_POSITION}."
        )

    try:
        g["_bin"] = pd.qcut(g["sigma"], n_bins, labels=False, duplicates="drop")
    except ValueError as e:
        raise RuntimeError(f"{pos}: could not bin sigma into {n_bins} quantiles ({e}).")

    bins = []
    for bi, gb in g.groupby("_bin"):
        if len(gb) < MIN_ROWS_PER_BIN:
            continue
        err = (gb["actual_points"] - gb["final_projection"]).to_numpy(float)
        # Decision #1: dispersion AROUND THIS BIN'S OWN MEAN ERROR.
        resid_sd = float(err.std(ddof=1))
        mean_sigma = float(gb["sigma"].mean())
        if resid_sd <= 0 or mean_sigma <= 0:
            continue
        bins.append({"bin": int(bi), "n": int(len(gb)),
                     "mean_sigma": round(mean_sigma, 4),
                     "mean_error": round(float(err.mean()), 4),
                     "resid_sd": round(resid_sd, 4)})

    # Decision #8 -- BINS, not rows.
    if len(bins) < MIN_USABLE_BINS:
        raise RuntimeError(
            f"{pos}: only {len(bins)} usable bin(s) after the >= "
            f"{MIN_ROWS_PER_BIN} rows-per-bin filter, need >= "
            f"{MIN_USABLE_BINS}. A curve fit on that few points is not a curve."
        )

    x = np.log(np.array([b["mean_sigma"] for b in bins], float))
    y = np.log(np.array([b["resid_sd"] for b in bins], float))
    b_raw, log_a = np.polyfit(x, y, 1)
    resid = y - (log_a + b_raw * x)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - float((resid ** 2).sum()) / ss_tot if ss_tot > 0 else float("nan")

    # Decision #9 -- clamp loudly, keep the raw value.
    b = float(min(1.0, max(0.0, b_raw)))
    clamped = abs(b - b_raw) > 1e-12
    if clamped:
        print(f"  WARNING {pos}: fitted b = {b_raw:.4f} is outside [0, 1] and was "
              f"clamped to {b:.4f}. b>1 means the model is UNDER-dispersed and "
              f"b<0 means sigma is anti-informative -- both contradict the "
              f"measurement this session exists to correct. Investigate before "
              f"trusting this position.")

    a = float(np.exp(log_a))
    sigmas = g["sigma"].to_numpy(float)
    lo, hi = float(sigmas.min()), float(sigmas.max())
    clipped_sigmas = np.clip(sigmas, lo, hi)
    err_all = (g["actual_points"] - g["final_projection"]).to_numpy(float)
    overall_sd = float(err_all.std(ddof=1))
    calib_before = overall_sd / float(sigmas.mean())

    # Decision #13 -- IF b WAS CLAMPED, `a` MUST BE REFIT.
    #
    # `a` and `b` come from one joint regression, so the intercept is only
    # meaningful at the slope it was fit with. Clamping the slope and keeping
    # the intercept silently breaks the LEVEL -- caught by this session's own
    # fixture test, where a clamped DST slope left calibration at 0.672
    # against a level that had been correct at 0.957. The level is the one
    # thing probe B1 says was already right, so breaking it while fixing the
    # spread would be a straight regression.
    #
    # Refit ONLY on clamp, never otherwise. When b is untouched, `a` stays as
    # fitted so `calibration_after` remains a genuine, independent validation
    # rather than a tautology -- if the level were always forced to 1.0 the
    # check would be incapable of failing and would tell us nothing.
    a_refit = False
    if clamped:
        denom = float(np.power(clipped_sigmas, b).mean())
        if denom > 0:
            a = overall_sd / denom
            a_refit = True
            print(f"          {pos}: `a` refit to {a:.4f} to hold the level at "
                  f"the clamped slope (decision #13).")

    new_sigma = a * np.power(clipped_sigmas, b)
    calib_after = overall_sd / float(new_sigma.mean())

    return {
        "a": round(a, 6),
        "b": round(b, 6),
        "b_raw": round(float(b_raw), 6),
        "b_clamped": bool(clamped),
        "a_refit_on_clamp": bool(a_refit),
        "loglog_r2": round(float(r2), 4),
        "sigma_fit_range": [round(lo, 4), round(hi, 4)],   # decision #3
        "n_rows": int(len(g)),
        "n_bins": len(bins),
        "calibration_before": round(float(calib_before), 4),
        "calibration_after": round(float(calib_after), 4),
        "bins": bins,
    }


def fit(site: str, rows: pd.DataFrame, seasons: list, n_bins: int) -> dict:
    rows = rows[rows["joined"].astype(bool)].copy()
    rows["position"] = rows["position"].map(normalize_position)

    positions, failures = {}, []
    print(f"\n{'pos':5s} {'n':>6s} {'bins':>5s} {'a':>9s} {'b':>8s} "
          f"{'b_raw':>8s} {'r2':>7s} {'calib_b4':>9s} {'calib_af':>9s}")
    for pos in POSITIONS:
        g = rows[rows["position"] == pos]
        try:
            entry = fit_position(g, pos, n_bins)
        except RuntimeError as e:
            failures.append(str(e))
            print(f"{pos:5s} SKIPPED -- {e}")
            continue
        positions[pos] = entry
        print(f"{pos:5s} {entry['n_rows']:>6d} {entry['n_bins']:>5d} "
              f"{entry['a']:>9.4f} {entry['b']:>8.4f} {entry['b_raw']:>8.4f} "
              f"{entry['loglog_r2']:>7.3f} {entry['calibration_before']:>9.3f} "
              f"{entry['calibration_after']:>9.3f}")

    if not positions:
        raise SystemExit(
            "No position could be fit. Nothing written -- a partial or empty "
            "artifact is worse than none, because a later run would load it "
            "and silently do nothing.\n  " + "\n  ".join(failures)
        )
    if failures:
        print(f"\n  NOTE: {len(failures)} position(s) could not be fit and are "
              f"ABSENT from the artifact. The consumer leaves those positions' "
              f"sigma RAW and says so -- it does not borrow another position's "
              f"curve (consumer decision #2's reasoning, one level down).")

    return {
        "schema_version": SCHEMA_VERSION,
        "fit_date": date.today().isoformat(),
        "site": site,
        "seasons": sorted(int(s) for s in seasons),
        "n_rows": int(len(rows)),
        "n_bins_requested": n_bins,
        "guards": {
            "min_rows_per_position": MIN_ROWS_PER_POSITION,
            "min_rows_per_bin": MIN_ROWS_PER_BIN,
            "min_usable_bins": MIN_USABLE_BINS,
        },
        "notes": (
            "Session 10.4b. Corrects the OVER-DISPERSION of the stat-line "
            "engine's per-player sigma measured by probe_sigma_quality.py's "
            "probe B3. Fit on within-bin residual SD with the bin's own mean "
            "bias removed (consumer decision #1) -- the per-position MEAN bias "
            "is a separate, uncorrected finding. Site-keyed: sigma is in "
            "fantasy points and does not transfer between DK and FD."
        ),
        "positions": positions,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(
        description="Session 10.4b -- fit the per-position sigma dispersion curve.")
    p.add_argument("--site", choices=["dk", "fd"], default="dk")
    p.add_argument("--fit-seasons", type=int, nargs="+", default=DEFAULT_FIT_SEASONS,
                   help="Default 2014-2017 (decision #7 -- holdout).")
    p.add_argument("--week", type=int, nargs="+", default=None)
    p.add_argument("--n-bins", type=int, default=DEFAULT_N_BINS)
    p.add_argument("--dst-model", choices=["legacy", "distributional"],
                   default="distributional")
    p.add_argument("--statline-sims", type=int, default=4000)
    p.add_argument("--statline-seed", type=int, default=20103)
    p.add_argument("--volume-prior", action="store_true")
    p.add_argument("--volume-prior-floor", type=float, default=None)
    p.add_argument("--volume-prior-k", type=float, default=None)
    p.add_argument("--no-role-change", action="store_true")
    p.add_argument("--rows", default=None,
                   help="Fit from a previously collected frame (decision #12).")
    p.add_argument("--rows-out", default=None,
                   help="Where a collection run writes its frame. Defaults to "
                        "output/sigma_rows_fit_{site}.csv")
    p.add_argument("--out", default=None)
    args = p.parse_args()

    # Decision #7 -- the same guard fit_dst_model.py carries.
    overlap = sorted(set(args.fit_seasons) & MEASUREMENT_SEASONS)
    if overlap:
        print(f"\n  WARNING: fit window includes {overlap}, which is inside the "
              f"standard 2018-2021 MEASUREMENT window.\n  Session 10.3a measured "
              f"that exact leak inflating an effect roughly threefold. Any "
              f"validation\n  run against those seasons afterwards is in-sample "
              f"and is not evidence.\n")

    if args.rows:
        rows = pd.read_csv(args.rows, dtype={"player_id": str, "site_player_id": str})
        print(f"Fitting from {args.rows}: {len(rows)} player-weeks.")
        seasons = sorted(rows["season"].unique().tolist())
    else:
        statline = {"sims": args.statline_sims, "seed": args.statline_seed}
        prior = {"on": args.volume_prior, "floor": args.volume_prior_floor,
                 "k": args.volume_prior_k, "role_change": not args.no_role_change}
        print("Collecting (this rebuilds projections per week -- the slow part):")
        rows = collect_rows(args.site, args.fit_seasons, weeks=args.week,
                            all_weeks=True, statline=statline,
                            dst_model_mode=args.dst_model, prior=prior)
        rows_out = Path(args.rows_out) if args.rows_out else (
            OUTPUT_DIR / f"sigma_rows_fit_{args.site}.csv")
        rows_out.parent.mkdir(parents=True, exist_ok=True)
        rows.to_csv(rows_out, index=False)
        print(f"\nWrote {rows_out} ({len(rows)} player-weeks). "
              f"Re-fit without rebuilding via --rows {rows_out}.")
        seasons = args.fit_seasons

    artifact = fit(args.site, rows, seasons, args.n_bins)

    out_path = Path(args.out) if args.out else ARTIFACT_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=1))
    print(f"\nWrote {out_path} (schema_version {SCHEMA_VERSION}).")
    print("\n  'calib_b4' / 'calib_af' are a VALIDATION, not fitted knobs: the")
    print("  level was already right (probe B1) and the transform must not")
    print("  break it. Both columns should sit near 1.0.")
    print("  The real test is the probe re-run -- probe B3's ratio column")
    print("  flattening toward 1.0 across quintiles. An unchanged Spearman is")
    print("  NOT evidence: the transform is monotone, so that is guaranteed.")


if __name__ == "__main__":
    main()
