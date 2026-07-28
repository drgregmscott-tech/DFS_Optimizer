"""
probe_sigma_quality.py
======================

Session 10.5 PRE-TEST. Throwaway measurement script, same status as Session
10.3b's `probe_statline_priors.py`: it writes no artifact any production path
reads, nothing imports it, and it can be deleted the moment it stops being
useful. It exists to answer two questions on REAL data BEFORE the lambda
objective is built, because twice in Phase 10 a cheap pre-test has changed
what got built (10.2's points-level blend, 10.3a's re-scope to a capability
gate).

It answers:

  PROBE A -- CAN LAMBDA MOVE ANYTHING AT ALL?
    If sigma is close to a deterministic function of the projection --
    `sigma ~= a + b*mu` -- then `sum(mu) - lambda*sum(sigma^2)` is very
    nearly a monotone rescale of `sum(mu)`, the ILP's argmax does not move
    for a wide band of lambda, and then jumps discontinuously once it does.
    That is EXACTLY Session 10.2's failure mode (a level shift an ILP barely
    notices), and it is not hypothetical here: the pre-10.4 DST sigma was
    literally `3.25 + 0.39 * projection`.

    Rather than answer this with an R^2 alone, the probe computes the exact
    quantity that governs it. For two players i, j at the same position with
    mu_i > mu_j, the penalized objective reverses their order at

        lambda* = (mu_i - mu_j) / (var_i - var_j)

    That ratio is positive only when the higher-mean player is also the
    higher-variance one (a floor-seeking flip, lambda > 0) and negative when
    the higher-mean player is the SAFER one (an upside-seeking flip,
    lambda < 0). Collecting the distribution of lambda* over every
    within-position pair in every week gives, directly from the data:

      - whether any lambda in a sane range reorders anything, and
      - the coarse grid the card asks for, DERIVED rather than guessed.

    This is a NECESSARY condition, not a sufficient one: a reordering that
    the salary cap or roster constraints never let matter still shows up
    here. Reported as "pairs reordered", never as "lineups changed".

  PROBE B -- IS SIGMA ANY GOOD? (never measured for skill players)
    Session 10.4 measured DST sigma calibration at 0.931 (realized RMSE /
    mean projected sigma, 1.00 ideal). There is NO equivalent figure
    anywhere for skill players. Session 10.3a's capability gate was
    "delivers a validated mean and sigma"; what was validated was that a
    sigma EXISTS and is idiosyncratic by construction, not that it is the
    right SIZE. A lambda objective fed a miscalibrated sigma will have
    lambda silently absorb the miscalibration, and if the miscalibration
    differs BY POSITION the objective will systematically distort slot
    allocation -- which is the failure mode Session 10.4 already flagged
    for the DST slot on size grounds alone.

    Three separate numbers, because they fail differently:

      1. LEVEL      -- realized RMSE / mean projected sigma, per position.
                       Reported both raw and with the mean bias removed,
                       since RMSE^2 = bias^2 + residual variance and a
                       biased MEAN would otherwise be misread as an
                       understated SIGMA.
      2. SHAPE      -- empirical coverage of the simulator's own
                       `statline_p10`/`statline_p90` columns. Target 0.80
                       between them. Reported as below-p10 / above-p90
                       separately, because fantasy scoring is right-skewed
                       and a symmetric miss and a skew miss are different
                       problems.
      3. DISCRIMINATION -- the one that actually matters for this card.
                       Bucket players by projected-sigma quintile and
                       compare each bucket's realized residual SD to its
                       mean projected sigma. A sigma that is right ON
                       AVERAGE but does not separate a safe player from a
                       volatile one is noise to the objective, and lambda
                       fitted on it would be fitting noise. This is the
                       analogue of Session 10.4's "genuinely varying with
                       the opponent" check.

Numbered decisions:

  1. RUNS THE REAL PIPELINE, IN-PROCESS WHERE POSSIBLE. Imports
     `backtest_harness` and calls its own `run_projection_pipeline`,
     `sunday_main_slate_teams`, `build_vegas_file` and `load_actuals`
     rather than reimplementing the week setup. Same reasoning as the
     harness's decision #4: measuring a reimplementation measures the
     reimplementation. Consequence, stated loudly: this OVERWRITES
     `output/final_projections_{site}_{week}.csv` exactly the way the
     harness does. The harness regenerates it per week, so nothing is lost,
     but do not run this concurrently with a backtest.

  2. MEASURES THE POOL THE OPTIMIZER ACTUALLY SEES, not the raw projection
     file: Sunday-main-slate filter plus `final_projection > 0`, identical
     to the harness. Sigma quality on players who can never be selected is
     not the question being asked.

  3. NON-JOINING PLAYERS ARE DROPPED FROM CALIBRATION, NOT SCORED AS ZERO.
     The harness scores a missing actual as 0.0, which is correct for a
     lineup total (an unrostered/inactive player really did contribute
     nothing) and WRONG for a calibration statistic, where it is missing
     data masquerading as a 30-point miss. Per-position join rates are
     printed so the drop is visible rather than silent.

  4. ARTIFACT PROVENANCE IS PRINTED AND IN-SAMPLE OVERLAP IS FLAGGED,
     per Session 10.3b's handoff note ("read the ARTIFACTS block; if
     anything says << IN-SAMPLE, refit before believing the numbers"). An
     in-sample variance artifact will look better calibrated than it is,
     which is precisely the leak Session 10.3a caught and recorded as its
     transferable lesson.

  5. THE PER-PLAYER-WEEK FRAME IS CACHED to
     `output/probe_sigma_rows_{site}.csv`. The projection rebuild is the
     expensive part and is completely independent of the analysis, so
     `--reuse` re-runs every statistic in seconds while iterating on the
     questions.

  6. WEEK 1 IS SKIPPED unless `--volume-prior`, mirroring the harness
     exactly (Session 10.3b made week 1 buildable only on that arm). The
     default configuration here is the current reference arm: stat-line
     engine, distributional DST, volume prior OFF -- the 77.9 / 97.3 pair.

Usage:
    python3 scripts/probe_sigma_quality.py --site dk --season 2021 --all-weeks
    python3 scripts/probe_sigma_quality.py --site dk --season 2018 2019 2020 2021 --all-weeks
    python3 scripts/probe_sigma_quality.py --site dk --season 2021 --reuse
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUT_DIR = REPO_ROOT / "output"
SCRIPTS_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(SCRIPTS_DIR))
# Session 10.4b: `collect_rows` now lives in fit_sigma_recalibration.py and is
# imported rather than duplicated. The direction is deliberate -- this probe is
# an explicit throwaway, and a production artifact must not depend on a script
# the project intends to delete. When this file goes, nothing there breaks.
from fit_sigma_recalibration import collect_rows  # noqa: E402  -- decision #1
import sigma_recalibration  # noqa: E402

# Positions reported separately. DST is included deliberately: Session 10.4
# flagged that a DST's sigma (~6.2) is nearly its whole mean (~6.9), so it is
# the slot most exposed to any lambda penalty, and it is the ONE position
# whose sigma has a published calibration (0.931) to check this probe's own
# machinery against.
POSITIONS = ["QB", "RB", "WR", "TE", "DST"]
DEFENSE_LABELS = {"DST", "D", "DEF"}

# Probe A grid, in the units of the variance form (points per point^2).
# Deliberately wide and coarse -- the POINT of probe A is that the useful
# range comes out of the data, not out of this list.
LAMBDA_SCAN = [-0.20, -0.10, -0.05, -0.02, -0.01, 0.01, 0.02, 0.05, 0.10, 0.20]


# ---------------------------------------------------------------------------
# Artifact provenance (decision #4)
# ---------------------------------------------------------------------------

def _artifact_seasons(path: Path):
    if not path.exists():
        return None, f"{path.name} NOT FOUND"
    try:
        blob = json.loads(path.read_text())
    except Exception as e:  # noqa: BLE001 -- provenance must never abort the run
        return None, f"{path.name} unreadable ({type(e).__name__})"
    for key in ("seasons", "fit_seasons", "fit_window"):
        if key in blob and blob[key]:
            try:
                return sorted(int(s) for s in blob[key]), None
            except (TypeError, ValueError):
                return None, f"{path.name} '{key}' present but not a season list"
    return None, f"{path.name} carries no season provenance key"


def print_artifacts_block(measure_seasons: list) -> None:
    print("\n" + "=" * 78)
    print("ARTIFACTS (decision #4 -- read this before believing any number below)")
    print("=" * 78)
    measured = set(measure_seasons)
    any_leak = False
    for path in (DATA_DIR / "statline_variance.json", DATA_DIR / "dst_model.json"):
        seasons, problem = _artifact_seasons(path)
        if problem:
            print(f"  {path.name:26s} {problem}  <<< PROVENANCE UNKNOWN")
            any_leak = True
            continue
        overlap = sorted(measured & set(seasons))
        tag = ""
        if overlap:
            tag = f"  <<< IN-SAMPLE on {overlap}"
            any_leak = True
        print(f"  {path.name:26s} fit on {seasons}{tag}")
    if any_leak:
        print("\n  WARNING: at least one artifact was fit on a season being measured"
              "\n  here, or its provenance could not be read. An in-sample variance"
              "\n  artifact looks better calibrated than it is -- that is Session"
              "\n  10.3a's recorded leak. Refit to a holdout window before treating"
              "\n  Probe B's calibration numbers as evidence.")
    else:
        print("\n  Clean: no measured season appears in any artifact's fit window.")
    print("=" * 78 + "\n")


# ---------------------------------------------------------------------------
# Collection: one row per (season, week, player), pool-filtered and joined
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# PROBE A -- can lambda move anything?
# ---------------------------------------------------------------------------

def flip_lambdas(mu: np.ndarray, var: np.ndarray) -> np.ndarray:
    """All pairwise reversal thresholds within one (week, position) group.

    For every pair with mu_i > mu_j, returns (mu_i - mu_j) / (var_i - var_j).
    Positive values are floor-seeking flips (the better player is also the
    riskier one, so a lambda ABOVE the value demotes him); negative values
    are upside-seeking flips (the better player is the safer one, so a
    lambda BELOW the value demotes him). Pairs with equal variance can never
    flip at any finite lambda and are dropped.
    """
    n = len(mu)
    if n < 2:
        return np.empty(0)
    dmu = mu[:, None] - mu[None, :]
    dvar = var[:, None] - var[None, :]
    iu = np.triu_indices(n, k=1)
    dmu = dmu[iu]
    dvar = dvar[iu]
    # Orient every pair so the mean difference is positive.
    flip = dmu < 0
    dmu = np.where(flip, -dmu, dmu)
    dvar = np.where(flip, -dvar, dvar)
    ok = (np.abs(dvar) > 1e-9) & (dmu > 1e-9)
    return dmu[ok] / dvar[ok]


def probe_a(df: pd.DataFrame) -> None:
    print("\n" + "=" * 78)
    print("PROBE A -- CAN LAMBDA REORDER ANYTHING? (necessary condition only)")
    print("=" * 78)

    d = df.copy()
    d["var"] = d["sigma"] ** 2

    # --- A1: how collinear is sigma with the projection? -------------------
    print("\nA1. sigma vs projection, and variance vs projection, within position.")
    print("    A high R^2 means lambda is close to a monotone rescale of the mean")
    print("    and cannot reorder much -- Session 10.2's failure mode.\n")
    print(f"    {'pos':4s} {'n':>6s} {'sig_a':>7s} {'sig_b':>7s} {'sig_R2':>7s} "
          f"{'resid_sd':>9s} {'resid/sig':>10s} {'var_R2':>7s}")
    for pos in POSITIONS:
        g = d[d["position"] == pos]
        if len(g) < 30:
            print(f"    {pos:4s} {len(g):>6d}   (too few rows)")
            continue
        mu = g["final_projection"].to_numpy(float)
        sg = g["sigma"].to_numpy(float)
        vr = g["var"].to_numpy(float)
        b, a = np.polyfit(mu, sg, 1)
        resid = sg - (a + b * mu)
        ss_tot = float(((sg - sg.mean()) ** 2).sum())
        r2 = 1.0 - float((resid ** 2).sum()) / ss_tot if ss_tot > 0 else float("nan")
        bv, av = np.polyfit(mu, vr, 1)
        rv = vr - (av + bv * mu)
        ssv = float(((vr - vr.mean()) ** 2).sum())
        r2v = 1.0 - float((rv ** 2).sum()) / ssv if ssv > 0 else float("nan")
        rsd = float(resid.std(ddof=1))
        print(f"    {pos:4s} {len(g):>6d} {a:>7.3f} {b:>7.3f} {r2:>7.3f} "
              f"{rsd:>9.3f} {rsd / sg.mean():>10.3f} {r2v:>7.3f}")
    print("\n    Reading it: sig_R2 above ~0.95 with resid/sig below ~0.05 means")
    print("    sigma carries almost no information the projection does not, and")
    print("    this card needs re-scoping before it is built.")

    # --- Compute every within-(week, position) reversal threshold ONCE ------
    flips = {}
    for pos in POSITIONS:
        g = d[d["position"] == pos]
        vals = [flip_lambdas(wk["final_projection"].to_numpy(float),
                             wk["var"].to_numpy(float))
                for _, wk in g.groupby(["season", "week"], sort=False)]
        flips[pos] = np.concatenate(vals) if vals else np.empty(0)

    # --- A2: the exact reversal thresholds ---------------------------------
    print("\nA2. Pairwise reversal thresholds lambda* = dmu / dvar, within")
    print("    position, within week. This is the exact quantity that decides")
    print("    whether a given lambda changes the ordering of any two players.\n")
    print(f"    {'pos':4s} {'pairs':>9s} {'floor%':>7s} | "
          f"{'floor-seeking lambda>0':>32s} | {'upside-seeking lambda<0':>32s}")
    print(f"    {'':4s} {'':>9s} {'':>7s} | {'p01':>10s} {'p05':>10s} {'p25':>10s} | "
          f"{'p01':>10s} {'p05':>10s} {'p25':>10s}")

    def _q(arr, pct, sign=1.0):
        if arr.size == 0:
            return f"{'--':>10s}"
        return f"{sign * float(np.percentile(arr, pct)):10.4f}"

    pos_all, neg_all = [], []
    for pos in POSITIONS:
        v = flips[pos]
        if v.size == 0:
            continue
        pv = np.sort(v[v > 0])
        nv = np.sort(-v[v < 0])          # magnitudes, so percentiles read small-first
        pos_all.append(pv)
        neg_all.append(nv)
        share_floor = pv.size / v.size
        print(f"    {pos:4s} {v.size:>9d} {share_floor:>7.3f} | "
              f"{_q(pv,1)} {_q(pv,5)} {_q(pv,25)} | "
              f"{_q(nv,1,-1)} {_q(nv,5,-1)} {_q(nv,25,-1)}")

    pv_all = np.concatenate(pos_all) if pos_all else np.empty(0)
    nv_all = np.concatenate(neg_all) if neg_all else np.empty(0)

    print("\n    'floor%' is the share of pairs where the higher-projected player")
    print("    is ALSO the riskier one -- those are the pairs a positive lambda can")
    print("    act on. p01 is the lambda at which the first 1% of pairs have")
    print("    reversed: a lambda materially below it is a guaranteed no-op, and a")
    print("    lambda far above p25 has scrambled the position ordering wholesale.")

    # --- A3: the derived coarse grid --------------------------------------
    if pv_all.size and nv_all.size:
        print("\nA3. DERIVED COARSE GRID (this is the deliverable, not a guess).")
        print("    Grid points placed at the lambda reversing 1/2/5/10/25% of")
        print("    same-position pairs, in each direction, plus 0.\n")
        floor_grid = [round(float(np.percentile(pv_all, q)), 4)
                      for q in (1, 2, 5, 10, 25)]
        upside_grid = [-round(float(np.percentile(nv_all, q)), 4)
                       for q in (1, 2, 5, 10, 25)]
        print(f"    floor-seeking  (cash):  {floor_grid}")
        print(f"    upside-seeking (GPP):   {upside_grid}")
        print(f"    full sweep grid:        {sorted(set(upside_grid + [0.0] + floor_grid))}")

    # --- A4: share of pairs reordered at a fixed scan grid ----------------
    print("\nA4. Share of same-position pairs reordered, at a fixed scan grid.")
    print("    A column of 0.000 means lambda is inert at that value.\n")
    print("    " + f"{'lambda':>8s}" + "".join(f"{p:>8s}" for p in POSITIONS))
    for lam in LAMBDA_SCAN:
        cells = []
        for pos in POSITIONS:
            v = flips[pos]
            if v.size == 0:
                cells.append(f"{'--':>8s}")
                continue
            if lam > 0:
                frac = float(((v > 0) & (v <= lam)).mean())
            else:
                frac = float(((v < 0) & (v >= lam)).mean())
            cells.append(f"{frac:>8.3f}")
        print(f"    {lam:>8.3f}" + "".join(cells))


# ---------------------------------------------------------------------------
# PROBE B -- is sigma any good?
# ---------------------------------------------------------------------------

def _spearman(a, b) -> float:
    """Spearman rho WITHOUT SciPy -- Pearson correlation on ranks.

    `pd.Series.corr(method="spearman")` silently imports `scipy.stats`, which
    this project deliberately does not have: Session 10.4 removed a SciPy
    dependency rather than installing one (`statlite.py` exists for exactly
    this reason). Ranks are taken with pandas' default 'average' tie handling,
    which is the correct tie correction for Spearman, so this is not an
    approximation -- it is the same statistic by its own definition.
    """
    ra = pd.Series(a).rank().to_numpy(float)
    rb = pd.Series(b).rank().to_numpy(float)
    if ra.size < 3 or ra.std() == 0 or rb.std() == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def probe_b(df: pd.DataFrame) -> None:
    print("\n" + "=" * 78)
    print("PROBE B -- SIGMA QUALITY (never measured for skill players)")
    print("=" * 78)

    print("\nB0. Join rate to real graded actuals, per position. Decision #3:")
    print("    non-joins are DROPPED from every statistic below, not scored 0.\n")
    print(f"    {'pos':4s} {'pool':>7s} {'joined':>7s} {'rate':>7s}")
    for pos in POSITIONS:
        g = df[df["position"] == pos]
        if not len(g):
            continue
        print(f"    {pos:4s} {len(g):>7d} {int(g['joined'].sum()):>7d} "
              f"{g['joined'].mean()*100:>6.1f}%")

    d = df[df["joined"]].copy()
    d["err"] = d["actual_points"] - d["final_projection"]

    # --- B1: level --------------------------------------------------------
    print("\nB1. LEVEL. calib = realized spread / mean projected sigma (1.00 ideal).")
    print("    'raw' uses RMSE; 'debias' removes the mean bias first, because")
    print("    RMSE^2 = bias^2 + resid_var and a biased MEAN would otherwise read")
    print("    as an understated SIGMA.\n")
    print(f"    {'pos':4s} {'n':>6s} {'proj':>7s} {'actual':>7s} {'bias':>7s} "
          f"{'RMSE':>7s} {'resid_sd':>9s} {'mean_sig':>9s} {'calib_raw':>10s} "
          f"{'calib_deb':>10s}")
    for pos in POSITIONS:
        g = d[d["position"] == pos]
        if len(g) < 30:
            continue
        err = g["err"].to_numpy(float)
        sg = g["sigma"].to_numpy(float)
        rmse = float(np.sqrt((err ** 2).mean()))
        bias = float(err.mean())
        rsd = float(err.std(ddof=1))
        ms = float(sg.mean())
        print(f"    {pos:4s} {len(g):>6d} {g['final_projection'].mean():>7.2f} "
              f"{g['actual_points'].mean():>7.2f} {bias:>7.2f} {rmse:>7.2f} "
              f"{rsd:>9.2f} {ms:>9.2f} {rmse/ms if ms else float('nan'):>10.3f} "
              f"{rsd/ms if ms else float('nan'):>10.3f}")
    print("\n    Cross-check: DST calib_raw should land near Session 10.4's")
    print("    recorded 0.931. If it does not, this probe -- not the model --")
    print("    is what to distrust first.")

    # --- B2: shape --------------------------------------------------------
    print("\nB2. SHAPE. Empirical coverage of the simulator's own p10/p90.")
    print("    Target: 0.10 below, 0.80 inside, 0.10 above. A right-skewed miss")
    print("    (too few above p90) is a different problem from a scale miss.\n")
    print(f"    {'pos':4s} {'n':>6s} {'<p10':>8s} {'inside':>8s} {'>p90':>8s}")
    for pos in POSITIONS:
        g = d[d["position"] == pos]
        if len(g) < 30 or g["statline_p90"].max() <= 0:
            continue
        a = g["actual_points"].to_numpy(float)
        lo = g["statline_p10"].to_numpy(float)
        hi = g["statline_p90"].to_numpy(float)
        below = float((a < lo).mean())
        above = float((a > hi).mean())
        print(f"    {pos:4s} {len(g):>6d} {below:>8.3f} {1-below-above:>8.3f} "
              f"{above:>8.3f}")
    print("\n    DST rows report 0.000/0.000 by construction -- the stat-line")
    print("    builder writes statline_p10/p90 = 0.0 for defenses. Not a finding.")

    # --- B3: discrimination ----------------------------------------------
    print("\nB3. DISCRIMINATION -- THE ONE THAT DECIDES THIS CARD.")
    print("    Players bucketed into projected-sigma quintiles WITHIN position.")
    print("    If realized resid_sd rises across buckets roughly in step with")
    print("    mean projected sigma, sigma separates safe from volatile players")
    print("    and lambda has real information to act on. If it is flat, sigma")
    print("    is right on average and useless per player, and lambda would be")
    print("    fitting noise.\n")
    print(f"    {'pos':4s} {'q':>2s} {'n':>6s} {'mean_sig':>9s} {'resid_sd':>9s} "
          f"{'ratio':>7s}")
    for pos in POSITIONS:
        g = d[d["position"] == pos].copy()
        if len(g) < 250:
            continue
        try:
            g["q"] = pd.qcut(g["sigma"], 5, labels=False, duplicates="drop")
        except ValueError:
            continue
        for qi, gq in g.groupby("q"):
            ms = float(gq["sigma"].mean())
            rsd = float(gq["err"].std(ddof=1))
            print(f"    {pos:4s} {int(qi)+1:>2d} {len(gq):>6d} {ms:>9.2f} "
                  f"{rsd:>9.2f} {rsd/ms if ms else float('nan'):>7.3f}")
        # Spearman between projected sigma and |error| is the same question
        # without the bucketing choice.
        rho = _spearman(g["sigma"], g["err"].abs())
        print(f"    {pos:4s}    Spearman(projected sigma, |error|) = {rho:+.3f}")
    print("\n    A Spearman near 0 is the kill signal: the model's sigma would")
    print("    carry no per-player information about who actually busts.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(
        description="Session 10.5 pre-test: sigma collinearity + calibration.")
    p.add_argument("--site", choices=["dk", "fd"], default="dk")
    p.add_argument("--season", type=int, nargs="+", default=[2021])
    p.add_argument("--week", type=int, nargs="+", default=None)
    p.add_argument("--all-weeks", action="store_true")
    p.add_argument("--dst-model", choices=["legacy", "distributional"],
                   default="distributional",
                   help="Default distributional -- the current reference arm.")
    p.add_argument("--statline-sims", type=int, default=4000)
    p.add_argument("--statline-seed", type=int, default=20103)
    p.add_argument("--volume-prior", action="store_true",
                   help="OFF by default (Session 10.3b). Turning it on also "
                        "makes week 1 collectable.")
    p.add_argument("--volume-prior-floor", type=float, default=None)
    p.add_argument("--volume-prior-k", type=float, default=None)
    p.add_argument("--no-role-change", action="store_true")
    p.add_argument("--apply-recalibration", action="store_true",
                   help="Session 10.4b VALIDATION MODE. Applies the fitted "
                        "per-position dispersion curve from "
                        "data/sigma_recalibration.json to the sigma column "
                        "before analysing. Because the transform is a pure "
                        "per-player function of sigma, doing it here is exactly "
                        "equivalent to rebuilding with "
                        "--sigma-recalibration, and costs seconds against the "
                        "cached frame instead of an hour of rebuilds. NOTE the "
                        "wiring itself is then still unvalidated -- that needs "
                        "one real build.")
    p.add_argument("--reuse", action="store_true",
                   help="Skip collection and re-analyse the cached row frame "
                        "(decision #5).")
    args = p.parse_args()

    cache = OUTPUT_DIR / f"probe_sigma_rows_{args.site}.csv"

    print_artifacts_block(args.season)

    if args.reuse:
        if not cache.exists():
            raise SystemExit(f"--reuse given but {cache} does not exist.")
        rows = pd.read_csv(cache, dtype={"player_id": str, "site_player_id": str})
        print(f"Reusing cached frame: {len(rows)} player-weeks from {cache.name}\n")
    else:
        statline = {"sims": args.statline_sims, "seed": args.statline_seed}
        prior = {"on": args.volume_prior, "floor": args.volume_prior_floor,
                 "k": args.volume_prior_k, "role_change": not args.no_role_change}
        print("Collecting (this rebuilds projections per week -- the slow part):")
        rows = collect_rows(args.site, args.season, weeks=args.week,
                            all_weeks=args.all_weeks, statline=statline,
                            dst_model_mode=args.dst_model, prior=prior)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        rows.to_csv(cache, index=False)
        print(f"\nWrote {cache} ({len(rows)} player-weeks). Re-run with --reuse "
              f"to re-analyse without rebuilding.")

    if args.apply_recalibration:
        art = sigma_recalibration.load(args.site)
        print(f"\nAPPLYING {sigma_recalibration.describe(art)}")
        rows = sigma_recalibration.apply_recalibration(rows, args.site,
                                                       artifact=art)
        print("  Validation reading: B3's ratio column should flatten toward")
        print("  1.0 across quintiles -- THAT is the test. B1 must stay near")
        print("  1.0 (the level was already right and must not break). B3's")
        print("  Spearman is unchanged BY CONSTRUCTION -- the transform is")
        print("  monotone -- so it is not evidence of anything. B2 is also")
        print("  unchanged by design: statline_p10/p90 are deliberately not")
        print("  rescaled (consumer decision #6), so B2 still grades the")
        print("  SIMULATOR's shape rather than this correction.")

    n_wk = rows.groupby(["season", "week"]).ngroups
    print(f"\nAnalysing {len(rows)} player-weeks across {n_wk} week(s), "
          f"seasons {sorted(rows['season'].unique().tolist())}.")

    bad_sigma = int(((rows["final_projection"] > 0) & (rows["sigma"] <= 0)).sum())
    if bad_sigma:
        print(f"\n  WARNING: {bad_sigma} pool player(s) have a positive projection "
              f"and sigma <= 0.\n  Under a variance penalty those are free points -- "
              f"the objective must reject\n  this pool rather than silently treat "
              f"them as risk-free.")

    probe_a(rows)
    probe_b(rows)

    print("\n" + "=" * 78)
    print("Nothing was written that any production path reads. This script is a")
    print("throwaway (decision #0) -- delete it when it stops being useful.")
    print("=" * 78)


if __name__ == "__main__":
    main()
