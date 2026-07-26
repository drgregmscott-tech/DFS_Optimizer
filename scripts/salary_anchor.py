"""
salary_anchor.py
================

Session 10.2 -- Salary-Anchor Baseline Curve (the CONSUMER).

Deliberately separate from fit_salary_anchor.py. The fitter is a
once-in-a-while offline job with binning/isotonic machinery; this is the
small, stable thing build_projections.py imports on every single run. Keeping
them apart means the production path never imports the fitting code, and the
artifact's read contract is defined in exactly one place.

Numbered decisions:

  1. FLAT EXTRAPOLATION PAST BOTH ENDS. Below the lowest fitted knot the
     anchor returns the lowest knot's value; above the highest, the highest.
     A curve knows nothing outside the salary range it was fit on, and the
     two alternatives are both worse: linear extrapolation off the top knot
     invents points nobody has evidence for (and the top knot is the
     thinnest, noisiest bin), while returning NaN would silently drop the
     anchor for exactly the expensive players it matters most for. Flat is
     the honest answer -- "the market's information runs out here."

  2. MISSING ARTIFACT IS A HARD ERROR WITH THE FIX COMMAND, not a silent
     no-anchor fallback. The anchor is only ever loaded because a caller
     explicitly asked for it (weight > 0); quietly returning zeros would
     make a backtest report "the anchor didn't help" when the truth is "the
     anchor never ran." Same fail-loud principle as the rest of this
     project.

  3. UNKNOWN POSITION IS A HARD ERROR. final_projections carries only
     QB/RB/WR/TE plus the site's defense label, and the artifact is fit on
     exactly that set. A position arriving here that the artifact has no
     curve for means the two are out of sync -- silently leaving those
     players un-anchored would distort the very comparison this session
     exists to make.

  4. COLD-START WEIGHT SCHEDULE (empirical-Bayes shrinkage). The ROADMAP's
     Phase 10 design calls for blend weights that are dynamic on data
     sufficiency: at zero games of usage history a projection should be
     essentially salary + market, and the usage component should take over
     as games accumulate. That is implemented here as:

         w_eff = w_floor + (1 - w_floor) * K / (K + games_played)

     At games_played = 0 this is 1.0 (pure anchor -- the only real signal
     available), decaying toward w_floor as history accumulates. K is the
     half-weight point: at games_played = K the shrinkage term is 0.5.

     K's default (4.0) is an ARBITRARY starting value chosen here, not
     user-confirmed and not fit -- flagged per this project's convention.
     Fitting it is Session 10.3/10.5 work, once there is a sigma and a
     tradeoff curve to fit it against.

     NOT implemented here, deliberately: the design's "suppress the salary
     anchor's weight when a role change is flagged" (a stale price is
     exactly the value spot we want to beat). No role-change flag exists in
     this pipeline yet -- that arrives with the Session 10.3 stat-line
     rewrite. Named here so it is a known gap, not an oversight.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

# Decision #4 -- arbitrary starting value, not user-confirmed, not fit.
DEFAULT_COLD_START_K = 4.0

_CACHE = {}


def anchor_path(site: str) -> Path:
    return DATA_DIR / f"salary_anchor_{site}.json"


def load_anchor(site: str, path: Path | None = None) -> dict:
    """Load (and memoize) the fitted artifact. Decision #2: hard error with
    the exact fix command if it isn't there."""
    p = Path(path) if path else anchor_path(site)
    key = str(p)
    if key in _CACHE:
        return _CACHE[key]
    if not p.exists():
        raise SystemExit(
            f"Salary anchor requested but {p} does not exist.\n"
            f"Fit it first:\n"
            f"    python3 scripts/fit_salary_anchor.py --site {site}\n"
            f"(Not falling back to a no-op anchor -- that would report "
            f"'the anchor didn't help' when the anchor never ran.)"
        )
    artifact = json.loads(p.read_text())
    ver = artifact.get("schema_version")
    if ver not in (1, 2):
        raise SystemExit(
            f"{p.name} has schema_version={ver}, expected 1 or 2. "
            f"Refit with the current fit_salary_anchor.py."
        )
    if ver == 1:
        # v1 curves were fit before fit_salary_anchor.py's decision #8, so
        # their knot span stops at the mean of the top/bottom bin rather than
        # the observed salary range. Every player priced past that collapses
        # onto one anchor value -- for the expensive end, that is the region
        # that matters most. Readable, but not measurable-quality.
        print(f"NOTE: {p.name} is schema_version 1 -- fit BEFORE the endpoint-knot "
              f"fix, so expensive players collapse onto a single anchor. Refit "
              f"(fit_salary_anchor.py --site {site}) before trusting a measurement.")
    if artifact.get("site") != site:
        raise SystemExit(
            f"{p.name} was fit for site='{artifact.get('site')}' but is being "
            f"loaded for site='{site}'. Refusing to cross-apply a DK curve to "
            f"FD prices (or vice versa) -- the two sites price and score "
            f"differently, which is the whole reason this is fit per site."
        )
    _CACHE[key] = artifact
    return artifact


def anchor_points(artifact: dict, positions, salaries) -> np.ndarray:
    """Vectorized E[points | salary, position] from the fitted curve.

    Decision #1: flat extrapolation past both ends.
    Decision #3: an unmapped position is a hard error.
    """
    positions = pd.Series(positions).astype(str).to_numpy()
    salaries = pd.to_numeric(pd.Series(salaries), errors="coerce").to_numpy(dtype=float)

    curves = artifact["positions"]
    unknown = sorted(set(positions) - set(curves.keys()))
    if unknown:
        raise SystemExit(
            f"Salary anchor has no fitted curve for position(s) {unknown} "
            f"(artifact has {sorted(curves.keys())}).\n"
            f"The projections file and the anchor artifact are out of sync -- "
            f"refit with fit_salary_anchor.py --site {artifact['site']}, or "
            f"check why an unexpected position reached the projections file."
        )

    out = np.full(len(positions), np.nan, dtype=float)
    for pos, curve in curves.items():
        mask = positions == pos
        if not mask.any():
            continue
        kx = np.array([k[0] for k in curve["knots"]], dtype=float)
        ky = np.array([k[1] for k in curve["knots"]], dtype=float)
        out[mask] = np.interp(salaries[mask], kx, ky,
                              left=float(ky[0]), right=float(ky[-1]))

    # A NaN salary can't be anchored; treat as no market signal rather than
    # letting NaN propagate into final_projection (the Session 10.1 bug #2
    # class of failure).
    out = np.where(np.isnan(salaries), 0.0, out)
    return out


def effective_weight(weight_floor: float, games_played, cold_start: bool,
                     k: float = DEFAULT_COLD_START_K) -> np.ndarray:
    """Per-player anchor weight. Decision #4.

    cold_start=False -> a flat `weight_floor` for everyone (the simple,
    directly-measurable unit; this is what the ROADMAP's validation line
    for this card compares against the Session 10.1 baseline).

    cold_start=True  -> shrinkage schedule on games_played.
    """
    gp = pd.to_numeric(pd.Series(games_played), errors="coerce").fillna(0.0).to_numpy(dtype=float)
    if not cold_start:
        return np.full(len(gp), float(weight_floor), dtype=float)
    if k <= 0:
        raise SystemExit("--salary-anchor-k must be > 0 (it is the half-weight "
                         "point of the shrinkage schedule).")
    w = weight_floor + (1.0 - weight_floor) * (k / (k + gp))
    return np.clip(w, 0.0, 1.0)


def blend(model_projection, anchor, weight) -> np.ndarray:
    """final = (1 - w) * model + w * anchor, clipped at 0."""
    m = pd.to_numeric(pd.Series(model_projection), errors="coerce").fillna(0.0).to_numpy(dtype=float)
    a = pd.to_numeric(pd.Series(anchor), errors="coerce").fillna(0.0).to_numpy(dtype=float)
    w = np.asarray(weight, dtype=float)
    return np.clip((1.0 - w) * m + w * a, 0.0, None)
