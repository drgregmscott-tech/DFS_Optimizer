"""
sigma_recalibration.py
======================

Session 10.4b -- Sigma Dispersion Recalibration (CONSUMER).

The production-path half of this session. Deliberately separate from
`fit_sigma_recalibration.py` so the projection build never imports fitting
machinery -- the same split as Session 10.2's `salary_anchor` /
`fit_salary_anchor` and Session 10.4's `dst_model` / `fit_dst_model`.

WHAT THIS CORRECTS, AND HOW IT WAS FOUND

Session 10.5's pre-test (`probe_sigma_quality.py`, probe B3) measured, for
the first time, whether the stat-line engine's per-player sigma actually
separates a safe player from a volatile one. Two things came out, and they
point in opposite directions:

  - It DOES rank correctly. Spearman(projected sigma, |error|) = +0.31 to
    +0.45 at every skill position. The signal is real.
  - It is massively OVER-DISPERSED. Across sigma quintiles, projected sigma
    spans 4.5x (QB) to 9.9x (RB) while realized residual SD spans only
    1.4x to 2.4x. The realized/projected ratio falls monotonically from
    ~2.1-2.7 in the lowest quintile to ~0.58-0.69 in the highest, at EVERY
    position:

        pos   projected sigma q1->q5     realized sd q1->q5    ratio q1->q5
        QB     3.63 -> 16.40 (4.5x)      7.41 -> 10.53 (1.4x)  2.04 -> 0.64
        RB     1.80 -> 17.88 (9.9x)      4.84 -> 10.42 (2.2x)  2.69 -> 0.58
        WR     2.04 -> 17.18 (8.4x)      4.53 -> 10.01 (2.2x)  2.22 -> 0.58
        TE     1.53 -> 11.46 (7.5x)      3.26 ->  7.92 (2.4x)  2.13 -> 0.69

    (2018-2021 DK, 65 weeks, 15,968 player-weeks, in-sample -- see the
    provenance note in the artifact.)

The LEVEL was already fine (probe B1: calibration 0.92-1.07 per position),
which is exactly why Session 10.3a's capability gate passed and why this was
never caught: the two halves of the distortion cancel in the average.

WHY IT HAD TO BE FIXED BEFORE SESSION 10.5 RATHER THAN AFTER

Session 10.5's objective is `sum(mu) - lambda*sum(sigma^2)`, so the
over-dispersion gets SQUARED -- in variance units the model's spread is too
wide by roughly 10x (QB, TE) to 20x (RB). And because the distortion is
NON-LINEAR in sigma while lambda is a single scalar, no value of lambda can
undo it: the optimizer's implied risk aversion ends up player-dependent, so
every lambda traces a strictly interior curve and none reaches the true
mean-variance frontier. Sweeping lambda harder does not help; it moves along
the wrong curve.

It also compounds with probe A1: sigma is ~97% collinear with the mean
(sig_R^2 0.968-0.984), so an over-dispersion nearly aligned with projection
size would make a positive lambda act largely as "shade down expensive
players" -- a salary/value tilt wearing risk-management clothing, which is
the same shape as the artifact Session 10.2 caught.

Nothing consumed `sigma` at the time this was written -- carrying it through
the optimizer is Session 10.5's own first task -- so this was the cheapest
moment in the project's life to correct its scale.

THE MODEL

Per position, a power transform fit on the relationship between projected
sigma and realized dispersion:

    sigma' = a * clip(sigma, lo, hi) ** b

  - `b` < 1 compresses the spread; the measured relationship is close to
    sigma' ~ sigma^(1/3), i.e. the real dispersion spread is nearer the cube
    root of the model's.
  - `a` and `b` both come from one log-log regression of within-bin realized
    dispersion on within-bin mean sigma, so the LEVEL is not a separately
    tuned knob -- it falls out of the same fit, and the resulting overall
    calibration is a VALIDATION rather than a fitted parameter.
  - The transform is MONOTONE, so it cannot destroy the ranking signal probe
    B3 measured. A validation run showing an unchanged Spearman is therefore
    NOT evidence the fix worked -- it is guaranteed by construction. The
    test is the ratio column flattening toward 1.0.

Numbered decisions:

  1. FIT ON WITHIN-BIN RESIDUAL SD, NOT RMSE -- the mean bias is removed
     inside each bin before dispersion is measured. This is not cosmetic.
     The Session 10.5 objective decomposes a lineup as
     E[sum] = sum(mu) + sum(bias) and Var[sum] = sum(resid_var); a bias
     belongs in the MEAN term and must not be laundered into the variance
     term. Probe B1 separately recorded a real per-position mean bias (RB
     +1.08, WR +0.85, TE +0.77, QB -0.63) -- that is a projection-accuracy
     issue for a future card, explicitly NOT corrected here.

  2. SITE-KEYED, NOT SITE-AGNOSTIC. Unlike `statline_variance.json`
     (decision #1 of the fitter: a stat line is real football), sigma is
     denominated in FANTASY POINTS, and DK's full PPR and FD's half PPR are
     genuinely different units. The artifact is therefore keyed by site and
     a missing site is a HARD ERROR, never a silent fallback to DK's curve.
     FD has no real data to fit against -- the same standing gap as every
     other FD item -- so FD is BLOCKED here in the same way the FD salary
     anchor is, rather than assumed to transfer.

  3. NO EXTRAPOLATION OF THE POWER LAW. A power law fit over an observed
     sigma range says nothing outside it, and the tails are where an
     unbounded `sigma ** b` misbehaves worst. The INPUT sigma is clipped to
     the fit's observed range before transforming, so the curve is never
     evaluated where it was not fit. The clipped fraction is reported at
     apply time rather than silently absorbed.

  4. ZERO STAYS ZERO. `build_projections_statline.py` sets sigma = 0.0 for
     confirmed-no-game rows (its decision #7). Those are not low-variance
     players, they are absent players, and a power transform would map 0 to
     0 anyway -- but it is asserted rather than relied upon, because a
     positive projection with zero sigma is the one shape that would make
     the Session 10.5 objective treat a player as risk-free.

  5. PROVENANCE IS APPENDED TO `sigma_source`, never overwritten:
     `statline_mc` becomes `statline_mc+recal_10_4b`. Session 10.4's bug #4
     was an arm axis added without being added to a label; a recalibrated
     sigma that reports itself as raw is the same failure one layer down.

  6. `statline_p10` / `statline_p90` ARE NOT TOUCHED. They describe the
     simulator's own distribution and are not consumed by the objective.
     Rescaling them would make probe B2's coverage check circular -- it
     would then be grading the recalibration against itself instead of
     measuring the simulator's shape. Consequence, stated so it is not
     mistaken for a null result: B2 is UNCHANGED by this session, by design.
     The right-tail thinness B2 measured (RB/WR/TE ~0.19-0.21 above p90
     against a 0.10 target) is a separate, still-open finding.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
ARTIFACT_PATH = DATA_DIR / "sigma_recalibration.json"

SCHEMA_VERSION = 1

# Both sites' defense labels, matching optimizer.py's own set.
DEFENSE_LABELS = {"DST", "D", "DEF"}

PROVENANCE_SUFFIX = "+recal_10_4b"


def normalize_position(pos) -> str:
    p = str(pos).upper().strip()
    return "DST" if p in DEFENSE_LABELS else p


def load(site: str, path: Path = None) -> dict:
    """Decision #2: a missing artifact or a missing site is a hard error.

    There is no silent fallback and no cross-site reuse. A recalibration
    that quietly did nothing would be indistinguishable, in every downstream
    number, from one that worked.
    """
    path = Path(path) if path else ARTIFACT_PATH
    if not path.exists():
        raise RuntimeError(
            f"{path.name} not found -- run fit_sigma_recalibration.py "
            f"--site {site} first (Session 10.4b)."
        )
    blob = json.loads(path.read_text())
    if blob.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError(
            f"{path.name} has schema_version {blob.get('schema_version')}, "
            f"this consumer expects {SCHEMA_VERSION}."
        )
    if blob.get("site") != site:
        raise RuntimeError(
            f"{path.name} was fit for site '{blob.get('site')}', not '{site}'. "
            f"Decision #2: sigma is in fantasy points and DK's full PPR is not "
            f"FD's half PPR, so this artifact does NOT transfer between sites. "
            f"FD has no real data to fit against -- the same standing gap as "
            f"every other FD item in this project."
        )
    return blob


def describe(artifact: dict) -> str:
    """One line naming the fit, for a run banner. Session 10.4's bug #4:
    an axis that changes results and is not in any label is how a run comes
    to assert it is something it is not."""
    pos = artifact.get("positions", {})
    bits = ", ".join(
        f"{p}: b={v['b']:.3f}" + ("*" if v.get("b_clamped") else "")
        for p, v in sorted(pos.items())
    )
    return (f"sigma recal 10.4b (site={artifact.get('site')}, "
            f"fit {artifact.get('seasons')}, n={artifact.get('n_rows')}) [{bits}]")


def apply_recalibration(df: pd.DataFrame, site: str, artifact: dict = None,
                        path: Path = None, verbose: bool = True) -> pd.DataFrame:
    """Returns a COPY of `df` with `sigma` recalibrated and `sigma_source`
    annotated (decision #5). Never mutates the input.

    Requires `sigma` and `position` columns. Rows whose position has no
    fitted entry are left untouched and counted -- a position the fitter
    could not fit is a real gap, and silently applying another position's
    curve to it would be worse than leaving it raw.
    """
    if artifact is None:
        artifact = load(site, path=path)
    for col in ("sigma", "position"):
        if col not in df.columns:
            raise RuntimeError(
                f"apply_recalibration() needs a '{col}' column; this frame has "
                f"{sorted(df.columns)[:12]}..."
            )

    out = df.copy()
    positions = artifact["positions"]
    pos_norm = out["position"].map(normalize_position)
    sigma = pd.to_numeric(out["sigma"], errors="coerce").fillna(0.0).to_numpy(float)
    new_sigma = sigma.copy()

    n_clipped = 0
    n_applied = 0
    unfitted = set()

    for pos, params in positions.items():
        # Decision #4: only strictly-positive sigma is transformed. Zero is
        # an absent player, not a risk-free one.
        mask = (pos_norm == pos).to_numpy() & (sigma > 0)
        if not mask.any():
            continue
        lo, hi = params["sigma_fit_range"]
        raw = sigma[mask]
        clipped = np.clip(raw, lo, hi)          # decision #3
        n_clipped += int((clipped != raw).sum())
        new_sigma[mask] = params["a"] * np.power(clipped, params["b"])
        n_applied += int(mask.sum())

    for pos in set(pos_norm[sigma > 0]) - set(positions):
        unfitted.add(pos)

    out["sigma"] = np.round(new_sigma, 4)

    if "sigma_source" in out.columns:
        touched = (sigma > 0) & pos_norm.isin(positions).to_numpy()
        out.loc[touched, "sigma_source"] = (
            out.loc[touched, "sigma_source"].astype(str) + PROVENANCE_SUFFIX
        )

    # Decision #4, asserted rather than assumed.
    if "final_projection" in out.columns:
        bad = int(((pd.to_numeric(out["final_projection"], errors="coerce") > 0)
                   & (out["sigma"] <= 0)).sum())
        if bad:
            raise RuntimeError(
                f"{bad} player(s) have a positive projection and sigma <= 0 "
                f"AFTER recalibration. Under a variance penalty those are free "
                f"points, so this fails loud rather than shipping the pool."
            )

    if verbose:
        print(f"  Sigma recalibration applied to {n_applied} player(s). "
              f"{n_clipped} clipped to the fitted sigma range (decision #3).")
        if unfitted:
            print(f"  NOTE: position(s) {sorted(unfitted)} have no fitted curve "
                  f"and keep their RAW sigma -- not silently borrowed from "
                  f"another position.")
    return out
