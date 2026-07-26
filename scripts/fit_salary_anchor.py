"""
fit_salary_anchor.py
====================

Session 10.2 -- Salary-Anchor Baseline Curve (the FITTER).

Fits the empirical points-vs-salary relationship, per site per position,
from the real historical data the Session 10.0 bootstrap materialized, and
writes it out as a small, inspectable artifact:

    data/salary_anchor_{site}.json

The curve is the MARKET'S OWN FORECAST. DK and FD price every player every
week, with real money and real incentives behind that price. The fitted
E[fantasy points | salary, position] is therefore a genuine, free,
independent projection component -- and, unlike our usage-based model, it
is available for a player with ZERO games of history (the cold-start case
Session 10.1's harness had to skip week 1 over).

Numbered decisions:

  1. SUBTRACT, DON'T DIVIDE (the 4for4-style baseline; the ROADMAP's own
     framing for this card). The classic "value" metric, points per $1,000
     of salary, structurally over-favors cheap players: a $3,000 player
     needs only 9 points to beat a $9,000 player's 27. Fitting a baseline
     curve and looking at points ABOVE that baseline removes the structural
     tilt, because the baseline itself already rises with salary. This
     script emits the baseline; `points_above_anchor` (the subtract form)
     is emitted downstream by build_projections.py when the anchor is on.

     Note this fights the ILP's own behavior in a useful way rather than a
     conflicting one: the optimizer already handles the price tradeoff
     natively via the salary-cap constraint, so points-per-dollar stays
     DISPLAY-ONLY in this project and never drives selection (ROADMAP,
     Phase 10 design intro). The anchor is about the PROJECTION, not the
     selection rule.

  2. FIT SOURCE = data/rotoguru_actuals_{site}_{season}.csv, not the 155
     matched salary files. The actuals file already carries every field the
     fit needs (season, week, gid, rotoguru_position, salary,
     actual_points) in ONE file per season, so the fit needs no 155-way
     join and no second copy of the matching logic. The matched salary
     files exist to feed the pipeline; this fit only needs (position,
     salary) -> points, which is exactly the actuals file's shape.

     Consequence, stated rather than hidden: rows the salary files DROP for
     being unpurchasable (N/A or $0 salary -- Session 10.0 decision #5,
     Session 10.1 bug #2) are retained in the actuals file. This script
     drops them too, for the same reason: a $0 price carries no market
     information, which is the only thing being fit here.

  3. ISOTONIC (MONOTONE) FIT ON BINNED MEANS, NOT A PARAMETRIC CURVE.
     The relationship is genuinely non-linear -- it flattens hard at the
     salary minimum (a floor of near-zero-usage bodies all priced at the
     same $3,000-ish minimum) and is close to linear above it. Rather than
     assume a functional form (linear, log, quadratic) and be wrong at the
     ends, the fit is:

       (a) bin salary into quantile bins with a minimum row count per bin,
       (b) take the count-weighted mean actual points per bin,
       (c) run a weighted pool-adjacent-violators (PAVA) isotonic
           regression over those bin means, so the result is guaranteed
           NON-DECREASING in salary,
       (d) store the result as a piecewise-linear knot table.

     Monotonicity is not cosmetic: it is the ROADMAP's own validation line
     for this card ("sanity-checked shape -- monotonic-ish, sensible
     endpoints"), and a non-monotone anchor would let the blend actively
     reward a lower price for the same player, which is nonsense.

     PAVA is implemented here in ~15 lines rather than pulling in
     scikit-learn -- this project's requirements.txt is deliberately thin
     (pandas/numpy/pulp), and a new dependency for one function that is
     this small and this well-specified is not worth the install surface.

  4. ZERO-POINT ROWS ARE KEPT BY DEFAULT (unconditional expectation).
     A slate's player pool contains players who were listed, priced, and
     then did not play (late scratch, healthy inactive) as well as players
     who played and scored ~0. The actuals data cannot tell those two
     apart. Keeping them makes the fit E[points | salary] UNCONDITIONALLY,
     which is the correct object for a projection component in THIS
     pipeline, because ruling players out is a separate, already-built
     stage (Session 5.1's status_check.py zeroes OUT players before the
     optimizer ever sees them). Fitting the played-only conditional here
     and then also zeroing OUT players downstream would double-count the
     availability discount.

     The played-only conditional is still FIT AND STORED, as a diagnostic
     (`played_only` per position), because the gap between the two curves
     is itself informative -- it is roughly the market's implied
     availability discount by price tier. `--exclude-zero-points` swaps
     which one is primary.

  5. POOLED ACROSS SEASONS, WITH AN EXPLICIT ERA-DRIFT DIAGNOSTIC.
     Salary scales drift (cap structure, scoring tweaks, pricing-model
     changes at the site). Pooling 2014-2021 gets far more rows per bin
     than any single season, which matters most exactly where the data is
     thinnest (the high-salary tail). But pooling ACROSS a real drift would
     bias the curve silently -- the failure mode this project has been
     bitten by three times now.

     So the fit is pooled, AND a per-season diagnostic is computed: each
     season is scored against the pooled curve, and the mean signed
     residual per season is reported. A season whose players systematically
     out- or under-perform the pooled curve is drift, and it is printed
     loudly and stored in the artifact. `--seasons` restricts the fit if
     the drift turns out to matter.

  6. FULL-WEEK POOL, NOT SUNDAY-MAIN-SLATE-ONLY. RotoGuru's pool is the
     whole Thu-Mon week (Session 10.0), and Session 10.1's harness filters
     to the Sunday main slate for LINEUP purposes. This fit deliberately
     does NOT apply that filter: the relationship between what a site
     charges for a player and what that player scores has no reason to
     differ by day of week, and the unfiltered pool is ~25% more rows.
     Flagged rather than assumed -- if a future session finds a real
     day-of-week effect, this is the line to revisit.

  8. ENDPOINT KNOTS AT THE OBSERVED SALARY RANGE (added after the first real
     measurement run -- a defect found by real data, not review).

     The first version of this fitter used each bin's MEAN salary as that
     knot's x-coordinate. Correct for the interior, wrong at the ends: it
     makes the fitted curve's domain [mean of lowest bin, mean of highest
     bin], which is far narrower than the observed salary range. With
     salary_anchor.py's flat extrapolation (its decision #1), every player
     priced above the top bin's MEAN collapsed onto a single anchor value.

     Measured on the real 8-season DK fit: the QB curve's top knot sat at
     $8,050 while real QB salaries reach $10,100, so Josh Allen anchored at
     exactly the top-knot value 22.14. Kamara and Jonathan Taylor BOTH
     anchored at exactly 21.06, the RB top knot, despite different prices.
     The curve was blind precisely among the expensive players who anchor
     every lineup -- the most consequential region there is.

     Fix: after the isotonic fit, append ONE endpoint knot at the observed
     salary MAX, extending the curve by the LOCAL SLOPE of the top three
     fitted knots (least-squares, so one flat isotonic block can't produce a
     zero or absurd slope), monotone and capped at TOP_EXTENSION_MAX_RATIO x
     the last fitted knot so a steep final segment can't invent points
     nobody has evidence for.

     TOP ONLY -- the bottom stays flat, deliberately, and this is a
     correction to the first version of this fix. Extending a linear slope
     DOWNWARD below the lowest bin undershoots badly: on the real 8-season
     DK data it drove a $3,000 QB, a $2,500 RB and a $2,400 TE to an anchor
     of exactly 0.00 points, worse than the flat value it replaced and
     flatly contradicted by their own bins (3.33 / 2.02 / 1.95).

     The reason is that a linear model is simply wrong at the bottom: the
     curve FLATTENS at the salary floor, where sites pile hundreds of
     near-zero-usage bodies onto the same minimum price. That is not an
     assumption -- it is what the isotonic step measured, pooling RB
     $3,407-$4,000 and TE $2,743-$3,000 into single flat blocks. So flat
     extrapolation below the lowest knot IS the fitted shape there, not a
     fallback from having no better idea. Only the expensive end, where the
     curve is still climbing and quantile bins are widest, needed extending.

     The fit also now reports FLAT-EXTRAPOLATION EXPOSURE per position: what
     share of real players fall outside the fitted knot span. That is the
     diagnostic whose absence let this defect through the first time, so it
     is printed unconditionally, not behind --report.

  9. A CURVE THAT CANNOT REACH THE EXPENSIVE END IS A HARD ERROR, NOT A
     WARNING. Found by the real FD fit, and it exposed a hole in this
     script's own guard.

     The row-count guard in fit_position() (`n < min_bin_rows * 2`) counts
     ROWS, not BINS -- so FD, with one season of data, passed it twice while
     producing a 4-knot QB curve and a 3-knot defense curve. Row count is
     the wrong test: what matters is whether the fitted span reaches the
     prices that decide lineups.

     Two guards now, and both stop the fit rather than warning past it:

       (a) MIN_KNOTS -- fewer knots than this and the "curve" is a couple of
           line segments. Arbitrary value, flagged, not user-confirmed.

       (b) THE TOP-EXTENSION CAP BINDING IS FATAL. This one is not
           arbitrary, and it is the better signal of the two. If decision
           #8's extension runs into TOP_EXTENSION_MAX_RATIO, the top bin's
           mean is so far below the real salary maximum that the local slope
           would have to be extrapolated further than there is any evidence
           for. Measured on the real FD data: WR's top bin mean was $7,045
           against a $10,200 maximum -- a $3,155 gap -- and QB/RB/WR/TE all
           pinned at exactly 1.350. A truncated top is precisely the defect
           decision #8 exists to remove, so shipping one silently would undo
           that fix.

     `--allow-truncated-top` overrides (b) for deliberate exploration. It
     prints what it is suppressing, and a curve fit under it must never be
     used for a measurement.

  7. KICKERS AND ANYTHING ELSE NON-ROSTERABLE ARE DROPPED, NOT ERRORED.
     RotoGuru's pool includes PK, which no Classic NFL roster on either
     site has a slot for. Dropped with a count. Anything that is neither a
     known roster position NOR a known-droppable one is a hard error -- an
     unrecognized position label means the source format changed, and this
     project does not silently proceed past that.

Usage:
    python3 scripts/fit_salary_anchor.py --site dk
    python3 scripts/fit_salary_anchor.py --site dk --seasons 2018 2019 2020 2021
    python3 scripts/fit_salary_anchor.py --site dk --report
    python3 scripts/fit_salary_anchor.py --site fd

Output:
    data/salary_anchor_{site}.json   (read by scripts/salary_anchor.py)
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
SCRIPTS_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(SCRIPTS_DIR))
from ingest_salaries import SITE_CONFIGS  # noqa: E402

# Skill positions the pipeline projects. The site's own defense label is
# appended at runtime (DK "DST" / FD "D") so the artifact's position keys
# match final_projections_{site}_{week}.csv's `position` column exactly.
SKILL_POSITIONS = ["QB", "RB", "WR", "TE"]

# Positions that legitimately appear in RotoGuru's pool but have no roster
# slot in an NFL Classic contest on either site. Dropped with a count
# (decision #7); anything NOT in this set and NOT a roster position is a
# hard error.
DROPPABLE_POSITIONS = {"PK", "K"}

# Binning defaults (decision #3). Both are arbitrary starting values chosen
# here, NOT user-confirmed -- flagged per this project's convention. They
# trade resolution against per-bin noise; N_BINS is a target, MIN_BIN_ROWS
# is the hard floor that adjacent bins get merged to satisfy.
N_BINS_DEFAULT = 24
MIN_BIN_ROWS_DEFAULT = 200

# Era-drift warning threshold (decision #5): a season whose mean signed
# residual against the pooled curve exceeds this many fantasy points is
# printed as a loud warning. Arbitrary starting value, not user-confirmed.
DRIFT_WARN_POINTS = 1.5

# Decision #8: guard on the top-end slope extension. The top bin is the
# thinnest and noisiest, so its local slope is the least trustworthy number
# in the fit; this caps how far the extension can run. Arbitrary starting
# value, not user-confirmed.
TOP_EXTENSION_MAX_RATIO = 1.35

# Decision #8: warn when this share of a position's players fall outside the
# fitted knot span (i.e. are flat-extrapolated). Arbitrary, not fit.
FLAT_EXPOSURE_WARN_PCT = 5.0

# Decision #9(a): minimum knots for something to count as a fitted curve
# rather than a couple of line segments. Arbitrary, not user-confirmed.
# Reference points from real fits: DK 8-season produces 13-17 knots per
# position; FD's single season produced 3-7.
MIN_KNOTS = 6


# ---------------------------------------------------------------------------
# Weighted isotonic regression (PAVA) -- decision #3
# ---------------------------------------------------------------------------

def isotonic_pava(y: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Weighted pool-adjacent-violators. Returns the non-decreasing
    sequence minimizing sum(w * (y - yhat)^2). Inputs must already be
    sorted by x ascending."""
    y = np.asarray(y, dtype=float)
    w = np.asarray(w, dtype=float)
    if len(y) == 0:
        return y
    # Each active block: (weighted mean value, total weight, block length)
    vals, wts, lens = [], [], []
    for yi, wi in zip(y, w):
        vals.append(float(yi))
        wts.append(float(wi))
        lens.append(1)
        # Pool backwards while the monotone constraint is violated.
        while len(vals) > 1 and vals[-2] > vals[-1]:
            v2, w2, l2 = vals.pop(), wts.pop(), lens.pop()
            v1, w1, l1 = vals.pop(), wts.pop(), lens.pop()
            tw = w1 + w2
            vals.append((v1 * w1 + v2 * w2) / tw if tw > 0 else (v1 + v2) / 2.0)
            wts.append(tw)
            lens.append(l1 + l2)
    out = []
    for v, l in zip(vals, lens):
        out.extend([v] * l)
    return np.asarray(out, dtype=float)


# ---------------------------------------------------------------------------
# Load + normalize the fit source (decisions #2, #7)
# ---------------------------------------------------------------------------

def defense_label(site: str) -> str:
    """The site's own defense position label, matching what
    ingest_rotoguru.py emits and what final_projections carries in its
    `position` column (DK 'DST', FD 'D')."""
    return sorted(SITE_CONFIGS[site]["defense_position_values"])[0]


def target_positions(site: str) -> list:
    return SKILL_POSITIONS + [defense_label(site)]


def load_fit_frame(site: str, seasons: list | None) -> pd.DataFrame:
    """Load and normalize every rotoguru_actuals_{site}_{season}.csv into a
    single (season, week, position, salary, actual_points) frame."""
    paths = sorted(DATA_DIR.glob(f"rotoguru_actuals_{site}_*.csv"))
    if not paths:
        raise SystemExit(
            f"No rotoguru_actuals_{site}_*.csv found in {DATA_DIR}.\n"
            f"Run Session 10.0's bootstrap first, e.g.:\n"
            f"  python3 scripts/ingest_rotoguru.py --site {site} --season 2021"
        )

    frames = []
    for p in paths:
        df = pd.read_csv(p, dtype={"gid": str})
        missing = {"season", "week", "gid", "rotoguru_position", "salary",
                   "actual_points"} - set(df.columns)
        if missing:
            raise SystemExit(
                f"{p.name} is missing expected column(s) {sorted(missing)}. "
                f"The actuals schema changed -- not proceeding on a guess."
            )
        frames.append(df)
    raw = pd.concat(frames, ignore_index=True)

    if seasons:
        raw = raw[raw["season"].isin(seasons)].copy()
        if raw.empty:
            raise SystemExit(
                f"No rows for site={site} seasons={seasons}. Available: "
                f"{sorted(pd.concat(frames)['season'].unique().tolist())}"
            )

    dlabel = defense_label(site)
    pos = raw["rotoguru_position"].astype(str).str.strip().str.upper()
    pos = pos.where(pos != "DEF", dlabel)
    raw["position"] = pos

    known = set(target_positions(site))
    unknown = sorted(set(pos.unique()) - known - DROPPABLE_POSITIONS)
    if unknown:
        raise SystemExit(
            f"Unrecognized position label(s) in the actuals data: {unknown}.\n"
            f"Expected roster positions {sorted(known)} or known-droppable "
            f"{sorted(DROPPABLE_POSITIONS)}. An unrecognized label means the "
            f"source format changed -- fix the mapping rather than letting "
            f"those rows be silently miscategorized."
        )

    n_before = len(raw)
    n_droppable = int(raw["position"].isin(DROPPABLE_POSITIONS).sum())
    raw = raw[raw["position"].isin(known)].copy()

    # Decision #2: unpurchasable rows carry no market signal.
    raw["salary"] = pd.to_numeric(raw["salary"], errors="coerce")
    n_unpurchasable = int((raw["salary"].isna() | (raw["salary"] <= 0)).sum())
    raw = raw[raw["salary"].notna() & (raw["salary"] > 0)].copy()

    raw["actual_points"] = pd.to_numeric(raw["actual_points"], errors="coerce")
    n_bad_points = int(raw["actual_points"].isna().sum())
    if n_bad_points:
        raise SystemExit(
            f"{n_bad_points} row(s) have an unparseable actual_points value. "
            f"Points are the fit target -- not zero-filling them."
        )

    print(f"Fit source: {len(paths)} actuals file(s), seasons "
          f"{sorted(raw['season'].unique().tolist())}")
    print(f"  {n_before} raw rows -> {len(raw)} usable "
          f"({n_droppable} non-roster positions dropped, "
          f"{n_unpurchasable} unpurchasable salaries dropped).")
    return raw


# ---------------------------------------------------------------------------
# Fit one position (decision #3)
# ---------------------------------------------------------------------------

def fit_position(df: pd.DataFrame, n_bins: int, min_bin_rows: int) -> dict:
    """Bin -> weighted bin means -> isotonic -> piecewise-linear knots."""
    d = df.sort_values("salary").reset_index(drop=True)
    n = len(d)
    if n < min_bin_rows * 2:
        raise SystemExit(
            f"Only {n} rows available -- too few to fit a credible curve "
            f"(need at least {min_bin_rows * 2} at the current "
            f"--min-bin-rows). Widen --seasons or lower --min-bin-rows "
            f"deliberately rather than shipping a curve fit on noise."
        )

    # Quantile bins on salary, then merge any bin under the row floor into
    # its neighbour. Duplicate salary values (very common at the salary
    # minimum) mean qcut can produce fewer bins than asked -- that's fine
    # and expected, not an error.
    try:
        d["_bin"] = pd.qcut(d["salary"], q=min(n_bins, n // min_bin_rows),
                            duplicates="drop", labels=False)
    except ValueError:
        d["_bin"] = 0

    grouped = d.groupby("_bin").agg(
        salary_mean=("salary", "mean"),
        salary_min=("salary", "min"),
        salary_max=("salary", "max"),
        points_mean=("actual_points", "mean"),
        rows=("actual_points", "size"),
    ).sort_values("salary_mean").reset_index(drop=True)

    # Merge undersized bins forward (rare after qcut, but a hard floor
    # beats an assumption).
    merged = []
    carry = None
    for r in grouped.itertuples():
        cur = {"salary_mean": r.salary_mean, "points_sum": r.points_mean * r.rows,
               "rows": r.rows, "salary_min": r.salary_min, "salary_max": r.salary_max}
        if carry is not None:
            tot = carry["rows"] + cur["rows"]
            cur = {
                "salary_mean": (carry["salary_mean"] * carry["rows"]
                                + cur["salary_mean"] * cur["rows"]) / tot,
                "points_sum": carry["points_sum"] + cur["points_sum"],
                "rows": tot,
                "salary_min": min(carry["salary_min"], cur["salary_min"]),
                "salary_max": max(carry["salary_max"], cur["salary_max"]),
            }
            carry = None
        if cur["rows"] < min_bin_rows:
            carry = cur
            continue
        merged.append(cur)
    if carry is not None:
        if merged:
            last = merged[-1]
            tot = last["rows"] + carry["rows"]
            merged[-1] = {
                "salary_mean": (last["salary_mean"] * last["rows"]
                                + carry["salary_mean"] * carry["rows"]) / tot,
                "points_sum": last["points_sum"] + carry["points_sum"],
                "rows": tot,
                "salary_min": min(last["salary_min"], carry["salary_min"]),
                "salary_max": max(last["salary_max"], carry["salary_max"]),
            }
        else:
            merged.append(carry)

    xs = np.array([m["salary_mean"] for m in merged], dtype=float)
    ys = np.array([m["points_sum"] / m["rows"] for m in merged], dtype=float)
    ws = np.array([m["rows"] for m in merged], dtype=float)

    ys_iso = isotonic_pava(ys, ws)

    # Decision #8: extend the TOP end to the observed salary max.
    raw_means = [round(float(v), 4) for v in ys]
    bin_rows = [int(v) for v in ws]
    xs, ys_iso, synthetic = _add_top_endpoint_knot(
        xs, ys_iso, float(d["salary"].max())
    )
    # Keep the audit arrays aligned with the knot list -- the synthetic knot
    # has no bin behind it, so it gets an explicit None rather than silently
    # borrowing its neighbour's numbers (which is exactly how the first
    # version of this fix produced a misaligned report).
    for is_syn in synthetic[len(raw_means):]:
        raw_means.append(None)
        bin_rows.append(None)

    knots = [[round(float(x), 1), round(float(y), 4)] for x, y in zip(xs, ys_iso)]
    return {
        "n": int(n),
        "n_bins": len(knots),
        "salary_min": float(d["salary"].min()),
        "salary_max": float(d["salary"].max()),
        "points_mean": round(float(d["actual_points"].mean()), 4),
        "knots": knots,
        "knot_is_extrapolated": synthetic,   # True = synthetic top endpoint
        "raw_bin_means": raw_means,          # pre-isotonic, for audit; None = synthetic
        "bin_rows": bin_rows,
    }


def _local_slope(xs: np.ndarray, ys: np.ndarray, at_top: bool, n: int = 3) -> float:
    """Least-squares slope over the n knots nearest the requested end.
    Least-squares rather than a two-point difference specifically because
    isotonic pooling creates FLAT blocks -- a two-point slope landing inside
    one would come out 0 and the extension would be a no-op."""
    if len(xs) < 2:
        return 0.0
    k = min(n, len(xs))
    sx, sy = (xs[-k:], ys[-k:]) if at_top else (xs[:k], ys[:k])
    if np.ptp(sx) <= 0:
        return 0.0
    slope = float(np.polyfit(sx, sy, 1)[0])
    return max(slope, 0.0)   # monotone curve -> never extend downward


def _add_top_endpoint_knot(xs: np.ndarray, ys: np.ndarray,
                           sal_max: float) -> tuple:
    """Decision #8. Append ONE knot at the observed salary max so the curve
    spans the expensive prices it will actually be asked about. The bottom
    stays flat on purpose -- see decision #8 for why a downward linear
    extension is the wrong model there.

    Returns (xs, ys, is_extrapolated) so the report can label the synthetic
    knot instead of misaligning it against the real bins' raw means.
    """
    xs = list(map(float, xs))
    ys = list(map(float, ys))
    synthetic = [False] * len(xs)

    if sal_max > xs[-1] + 1.0:
        slope = _local_slope(np.array(xs), np.array(ys), at_top=True)
        y_hi = ys[-1] + slope * (sal_max - xs[-1])
        y_hi = max(y_hi, ys[-1])                              # monotone
        y_hi = min(y_hi, ys[-1] * TOP_EXTENSION_MAX_RATIO)    # noisy-tail cap
        xs.append(sal_max)
        ys.append(y_hi)
        synthetic.append(True)

    return (np.array(xs, dtype=float), np.array(ys, dtype=float), synthetic)


def flat_exposure(df: pd.DataFrame, knots: list) -> tuple:
    """Share of real players (%) priced BELOW and ABOVE the fitted knot span,
    reported separately. Decision #8's diagnostic.

    The two ends are not equally worrying and must not be summed into one
    number. Below the span, flat means "held at the cheapest fitted value",
    and the curve genuinely IS flat down there (that is what the isotonic
    step measured), so exposure is expected and benign. Above the span, flat
    means expensive players collapse onto a single value -- which is the
    defect decision #8 exists to fix, in the region that decides lineups.
    """
    lo, hi = knots[0][0], knots[-1][0]
    sal = df["salary"].to_numpy(dtype=float)
    if len(sal) == 0:
        return 0.0, 0.0
    return (float((sal < lo).mean() * 100.0), float((sal > hi).mean() * 100.0))


def interp_knots(knots: list, salaries: np.ndarray) -> np.ndarray:
    """Piecewise-linear evaluation with FLAT extrapolation past both ends
    (see salary_anchor.py -- same rule, duplicated here only so the fitter
    can score its own residuals without importing the consumer)."""
    kx = np.array([k[0] for k in knots], dtype=float)
    ky = np.array([k[1] for k in knots], dtype=float)
    return np.interp(np.asarray(salaries, dtype=float), kx, ky,
                     left=float(ky[0]), right=float(ky[-1]))


# ---------------------------------------------------------------------------
# Era-drift diagnostic (decision #5)
# ---------------------------------------------------------------------------

def season_drift(df: pd.DataFrame, fits: dict) -> dict:
    """Mean signed residual (actual - anchor) per season, pooled over
    positions. A systematically non-zero season is era drift."""
    out = {}
    for season, sub in df.groupby("season"):
        resid = []
        for pos, psub in sub.groupby("position"):
            if pos not in fits:
                continue
            pred = interp_knots(fits[pos]["knots"], psub["salary"].to_numpy())
            resid.append(psub["actual_points"].to_numpy() - pred)
        if resid:
            allr = np.concatenate(resid)
            out[int(season)] = {
                "n": int(len(allr)),
                "mean_residual": round(float(allr.mean()), 4),
                "mean_salary": round(float(sub["salary"].mean()), 1),
                "mean_points": round(float(sub["actual_points"].mean()), 4),
            }
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Fit the points-vs-salary baseline curve (Session 10.2).")
    ap.add_argument("--site", choices=["dk", "fd"], required=True)
    ap.add_argument("--seasons", type=int, nargs="+", default=None,
                    help="Restrict the fit to these seasons (default: all available)")
    ap.add_argument("--n-bins", type=int, default=N_BINS_DEFAULT)
    ap.add_argument("--min-bin-rows", type=int, default=MIN_BIN_ROWS_DEFAULT)
    ap.add_argument("--exclude-zero-points", action="store_true",
                    help="Fit the PLAYED-ONLY conditional as the primary curve "
                         "instead of the unconditional one (decision #4)")
    ap.add_argument("--allow-truncated-top", action="store_true",
                    help="Ship a curve whose top-endpoint extension hit the cap "
                         "(decision #9b). For exploration only -- such a curve "
                         "must NOT be used for a measurement.")
    ap.add_argument("--report", action="store_true",
                    help="Print the fitted curve, bin counts, and drift table")
    ap.add_argument("--out", default=None,
                    help="Override output path (default data/salary_anchor_{site}.json)")
    args = ap.parse_args()

    df = load_fit_frame(args.site, args.seasons)

    primary = df[df["actual_points"] > 0].copy() if args.exclude_zero_points else df
    conditional = df[df["actual_points"] > 0].copy()

    fits, played_only = {}, {}
    for pos in target_positions(args.site):
        sub = primary[primary["position"] == pos]
        if sub.empty:
            print(f"  WARNING: no rows at all for position {pos} -- skipped. "
                  f"The anchor will not apply to {pos} players.")
            continue
        fits[pos] = fit_position(sub, args.n_bins, args.min_bin_rows)
        csub = conditional[conditional["position"] == pos]
        if len(csub) >= args.min_bin_rows * 2:
            po = fit_position(csub, args.n_bins, args.min_bin_rows)
            played_only[pos] = {"n": po["n"], "knots": po["knots"],
                                "points_mean": po["points_mean"]}

    # Decision #9: both guards run BEFORE the artifact is written, so a
    # curve that fails them never reaches disk to be picked up by a later run.
    thin = {pos: len(f["knots"]) for pos, f in fits.items()
            if len(f["knots"]) < MIN_KNOTS}
    if thin:
        raise SystemExit(
            f"Refusing to write a curve: position(s) {sorted(thin)} produced "
            f"fewer than {MIN_KNOTS} knots ({thin}).\n"
            f"That is a couple of line segments, not a fitted curve. The "
            f"row-count guard alone does not catch this -- a thin season can "
            f"have plenty of rows and still bin into almost nothing.\n"
            f"Widen --seasons (more data), or lower --min-bin-rows to buy more "
            f"bins at the cost of per-bin noise. Do not proceed to a "
            f"measurement on this fit."
        )

    truncated = {}
    for pos, f in fits.items():
        syn = f.get("knot_is_extrapolated", [])
        if not (syn and syn[-1]):
            continue
        ky = [k[1] for k in f["knots"]]
        if ky[-2] and abs(ky[-1] / ky[-2] - TOP_EXTENSION_MAX_RATIO) < 0.005:
            truncated[pos] = round(f["knots"][-1][0] - f["knots"][-2][0], 0)
    if truncated and not args.allow_truncated_top:
        raise SystemExit(
            f"Refusing to write a curve: the top-endpoint extension is CAPPED "
            f"at position(s) {sorted(truncated)}.\n"
            f"  (salary gap the extension had to span, per position: {truncated})\n"
            f"The top bin's mean sits so far below the real salary maximum that "
            f"the extension\nwould have to run further than the data supports, so "
            f"it is being truncated -- which\nleaves expensive players compressed "
            f"onto a near-flat top. That is exactly the defect\ndecision #8 exists "
            f"to remove, and it is the region that decides lineups.\n"
            f"Fix it with more data (--seasons) or more bins at the top (--n-bins "
            f"/ lower\n--min-bin-rows). Use --allow-truncated-top only for "
            f"exploration, never for a measurement."
        )
    if truncated and args.allow_truncated_top:
        print(f"\n  !! --allow-truncated-top: shipping a curve with a CAPPED top "
              f"extension at {sorted(truncated)}.\n     Expensive players are "
              f"compressed. Do NOT use this curve for a measurement.")

    drift = season_drift(df, fits)

    artifact = {
        "schema_version": 2,   # 2 = decision #8 endpoint knots present
        "site": args.site,
        "site_label": SITE_CONFIGS[args.site]["label"],
        "scoring": SITE_CONFIGS[args.site]["scoring"],
        "fitted_on": date.today().isoformat(),
        "fit_source": "rotoguru_actuals_{site}_{season}.csv (Session 10.0 bootstrap)",
        "seasons": sorted(int(s) for s in df["season"].unique()),
        "n_rows": int(len(df)),
        "primary_curve": "played_only" if args.exclude_zero_points else "unconditional",
        "params": {"n_bins": args.n_bins, "min_bin_rows": args.min_bin_rows},
        "positions": fits,
        "played_only_diagnostic": played_only,
        "season_drift": drift,
        "caveats": [
            "BOOTSTRAP DATA: RotoGuru tops out at 2021; this project's current-state "
            "weekly_stats is 2025. This curve is fit on a real but OLDER market. "
            "Refit from live salary exports once enough real weeks accumulate "
            "(Session 10.0 handoff: archive every real export from Preseason Week 1 on).",
            "Zero-point rows are retained by default, so the curve is the "
            "UNCONDITIONAL E[points|salary] -- availability is handled separately "
            "by status_check.py (decision #4).",
            "Full-week Thu-Mon pool, not Sunday-main-slate-filtered (decision #6).",
        ],
    }

    out_path = Path(args.out) if args.out else DATA_DIR / f"salary_anchor_{args.site}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=2))

    # --- Summary + validation-relevant sanity checks -----------------------
    print(f"\nWrote {out_path}")
    print(f"  Positions fitted: {sorted(fits.keys())}")
    exposure_flagged = []
    for pos, f in fits.items():
        kx = [k[0] for k in f["knots"]]
        ky = [k[1] for k in f["knots"]]
        nondec = all(ky[i] <= ky[i + 1] + 1e-9 for i in range(len(ky) - 1))
        exp_lo, exp_hi = flat_exposure(primary[primary["position"] == pos], f["knots"])
        f["flat_exposure_below_pct"] = round(exp_lo, 2)
        f["flat_exposure_above_pct"] = round(exp_hi, 2)
        if exp_hi > FLAT_EXPOSURE_WARN_PCT:
            exposure_flagged.append((pos, exp_hi))
        print(f"  {pos:>3}: n={f['n']:>6}  bins={f['n_bins']:>2}  "
              f"salary ${f['salary_min']:.0f}-${f['salary_max']:.0f}  "
              f"anchor ${kx[0]:.0f}->{ky[0]:.2f}pts .. ${kx[-1]:.0f}->{ky[-1]:.2f}pts  "
              f"monotone={'YES' if nondec else 'NO (BUG)'}  "
              f"flat below {exp_lo:4.1f}% / above {exp_hi:4.1f}%")
        if not nondec:
            raise SystemExit(
                f"Isotonic fit for {pos} came out non-monotone -- that is a bug "
                f"in isotonic_pava(), not a data property. Not shipping this curve."
            )

    if args.report:
        print("\n--- Fitted curve (knots: salary -> anchor points) ---")
        for pos, f in fits.items():
            print(f"\n  {pos}  (n={f['n']})")
            print(f"    {'salary':>8} {'anchor':>8} {'raw bin':>8} {'rows':>7}")
            for (x, y), raw_y, rows in zip(f["knots"], f["raw_bin_means"], f["bin_rows"]):
                if raw_y is None:
                    print(f"    {x:>8.0f} {y:>8.2f} {'--':>8} {'--':>7}   "
                          f"<- extrapolated top endpoint (decision #8)")
                else:
                    print(f"    {x:>8.0f} {y:>8.2f} {raw_y:>8.2f} {rows:>7}")

        print("\n--- Decision #1 illustration: points per $1,000 by price tier ---")
        print("    (falling left-to-right is the cheap-player bias that dividing bakes in)")
        for pos, f in fits.items():
            kx = [k[0] for k in f["knots"]]
            ky = [k[1] for k in f["knots"]]
            lo_ppd = ky[0] / (kx[0] / 1000.0)
            hi_ppd = ky[-1] / (kx[-1] / 1000.0)
            print(f"    {pos:>3}: cheapest bin {lo_ppd:5.2f} pts/$1K   "
                  f"priciest bin {hi_ppd:5.2f} pts/$1K")

    # Decision #8: this is the diagnostic whose absence hid the top-knot
    # collapse on the first pass. Printed always, not behind --report.
    if exposure_flagged:
        print(f"\n  WARNING: EXPENSIVE-END flat exposure above "
              f"{FLAT_EXPOSURE_WARN_PCT}% at: "
              f"{', '.join(f'{p} ({e:.1f}%)' for p, e in exposure_flagged)}.")
        print(f"  Those players all collapse onto ONE anchor value, so the curve "
              f"cannot tell apart the\n  very players who decide a lineup. Add "
              f"bins at the top (--n-bins) or lower\n  --min-bin-rows before "
              f"trusting a measurement from this curve.")
    else:
        print(f"\n  Expensive-end flat exposure is under "
              f"{FLAT_EXPOSURE_WARN_PCT}% at every position -- the fitted span "
              f"reaches the prices that decide lineups.")
    print(f"  (Cheap-end flat exposure is expected and benign: the curve really "
          f"is flat at the\n   salary floor, which is what the isotonic step "
          f"measured. See decision #8.)")

    # Decision #8: the top extension's cap nearly bound on the real DK data
    # (RB 1.32x, TE 1.33x against a 1.35 limit). Report the ratio so a future
    # session can see whether the guard is truncating rather than guessing.
    print("\n--- Top-endpoint extension (decision #8) ---")
    capped = []
    for pos, f in fits.items():
        syn = f.get("knot_is_extrapolated", [])
        if not (syn and syn[-1]):
            print(f"    {pos:>3}: no extension needed (top bin mean == salary max)")
            continue
        ky = [k[1] for k in f["knots"]]
        ratio = ky[-1] / ky[-2] if ky[-2] else float("inf")
        at_cap = abs(ratio - TOP_EXTENSION_MAX_RATIO) < 0.005
        if at_cap:
            capped.append(pos)
        print(f"    {pos:>3}: ${f['knots'][-2][0]:.0f}->{ky[-2]:.2f} extended to "
              f"${f['knots'][-1][0]:.0f}->{ky[-1]:.2f}  ratio {ratio:.3f} "
              f"(cap {TOP_EXTENSION_MAX_RATIO}){'  <-- AT CAP' if at_cap else ''}")
    if capped:
        print(f"\n  WARNING: the extension cap is BINDING at {capped}. The local "
              f"slope wants to run\n  further than the guard allows, so the top of "
              f"those curves is truncated, not fitted.\n  Raise "
              f"TOP_EXTENSION_MAX_RATIO deliberately, or add bins at the top "
              f"(--n-bins) so the\n  fitted span reaches higher on its own -- do "
              f"not just accept the truncation silently.")

    print("\n--- Era-drift diagnostic (decision #5) ---")
    print("    mean signed residual (actual - anchor); ~0 = the pooled curve fits "
          "that season")
    flagged = []
    for season, d in sorted(drift.items()):
        flag = ""
        if abs(d["mean_residual"]) > DRIFT_WARN_POINTS:
            flag = "  <-- DRIFT"
            flagged.append(season)
        print(f"    {season}: n={d['n']:>6}  resid {d['mean_residual']:+6.2f}  "
              f"(mean salary ${d['mean_salary']:.0f}, mean pts {d['mean_points']:.2f}){flag}")
    if flagged:
        print(f"\n  WARNING: season(s) {flagged} deviate from the pooled curve by more "
              f"than {DRIFT_WARN_POINTS} pts on average.\n"
              f"  That is real era drift, not noise. Consider refitting with "
              f"--seasons restricted to the recent, stable window, and record the "
              f"choice in SESSION_LOG.md rather than pooling over it silently.")
    else:
        print(f"\n  No season deviates by more than {DRIFT_WARN_POINTS} pts -- pooling "
              f"across these seasons is supported by the data.")

    print("\nNext: measure it. The curve is INERT until build_projections.py is run "
          "with --salary-anchor-weight > 0 (default 0.0 = off, production unchanged).")
    print("  python3 scripts/backtest_harness.py --site {s} --season 2021 --all-weeks "
          "--num-lineups 20 --salary-anchor-weight 0.25".format(s=args.site))


if __name__ == "__main__":
    main()
