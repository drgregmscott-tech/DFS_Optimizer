"""
statlite.py
============

Session 10.4 -- the handful of statistical functions this project needs from
SciPy, implemented on numpy + the standard library so SciPy is not a
dependency.

Why this exists
---------------
Session 10.4's fitter and measurement script originally imported SciPy for
four things: a negative-binomial log-pmf, a bounded 1-D minimiser, Spearman
correlation, and a paired t-test. Running them on the real Windows
environment turned up the obvious problem -- SciPy was not installed, and the
project's dependency set is pandas / numpy / PuLP / pyarrow.

SciPy does publish Python 3.14 wheels (since 1.16.1, July 2025), so
`pip install scipy` would have worked. It was not taken, for three reasons:

  1. The production path does not need it. `dst_model.py` -- which is what
     `build_projections.py` actually calls -- uses only `numpy.random`. Adding
     SciPy would have put a compiled dependency into the environment for the
     sake of two offline scripts, and the GitHub Actions refresh workflow
     installs from the same requirements.
  2. It is four functions, and small ones. The NB log-pmf and the Student-t
     survival function are textbook; Spearman is Pearson on ranks; the paired
     t-test is arithmetic plus that survival function.
  3. The usual objection to hand-rolling statistics -- that new code is
     probably subtly wrong -- is answerable here rather than merely assertable.
     `verify_against_scipy()` at the bottom of this file checks every function
     against SciPy across a grid of real inputs. It was run before this
     shipped (results in the Session 10.4 log) and can be re-run by anyone who
     has SciPy available. It is not imported by anything on the normal path.

The estimators are UNCHANGED, not approximated. `fit_nb_dispersion` is still
a maximum-likelihood fit, not a method-of-moments shortcut -- swapping the
estimator would have quietly moved every fitted dispersion in the shipped
model, which is exactly the kind of silent change this project's
schema-stability principle exists to prevent.
"""

import math

import numpy as np

__all__ = [
    "nbinom_logpmf", "minimize_scalar_bounded", "spearmanr", "ttest_rel",
    "student_t_sf", "verify_against_scipy",
]

_LGAMMA = np.frompyfunc(math.lgamma, 1, 1)


def _gammaln(x):
    """Vectorized log-gamma. numpy has no gammaln; math.lgamma does, and
    frompyfunc lifts it over an array. Returns float64, not object."""
    # frompyfunc returns a 0-d object scalar for scalar input, so np.asarray
    # is applied to the RESULT as well -- not just the argument.
    return np.asarray(_LGAMMA(np.asarray(x, dtype=float)), dtype=float)


# ---------------------------------------------------------------------------
# Negative binomial
# ---------------------------------------------------------------------------

def nbinom_logpmf(k, r, p):
    """log P(X = k) for the negative binomial, SciPy's (n, p) parameterization.

        log C(k+r-1, k) + r*log(p) + k*log(1-p)

    with the binomial coefficient written in log-gammas so non-integer r
    works -- which it must, since r is a fitted continuous dispersion.
    """
    k = np.asarray(k, dtype=float)
    r = np.asarray(r, dtype=float)
    p = np.clip(np.asarray(p, dtype=float), 1e-300, 1.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = (_gammaln(k + r) - _gammaln(r) - _gammaln(k + 1.0)
               + r * np.log(p) + k * np.log1p(-p))
    return np.where(k < 0, -np.inf, out)


# ---------------------------------------------------------------------------
# Bounded 1-D minimisation
# ---------------------------------------------------------------------------

_GOLDEN_INV = (math.sqrt(5.0) - 1.0) / 2.0


def minimize_scalar_bounded(func, bounds, xatol=1e-6, maxiter=500):
    """Golden-section search on a bounded interval.

    Stands in for `scipy.optimize.minimize_scalar(method="bounded")`. SciPy
    uses Brent's method, which converges faster; on the smooth unimodal
    negative log-likelihoods here both land on the same minimiser well inside
    the tolerance that matters (verified below), and golden-section cannot
    fail the way an unguarded parabolic step can.

    Returns an object with an `.x` attribute, matching the SciPy call site.
    """
    lo, hi = float(bounds[0]), float(bounds[1])
    if hi < lo:
        lo, hi = hi, lo
    c = hi - _GOLDEN_INV * (hi - lo)
    d = lo + _GOLDEN_INV * (hi - lo)
    fc, fd = func(c), func(d)
    for _ in range(maxiter):
        if abs(hi - lo) < xatol:
            break
        if fc < fd:
            hi, d, fd = d, c, fc
            c = hi - _GOLDEN_INV * (hi - lo)
            fc = func(c)
        else:
            lo, c, fc = c, d, fd
            d = lo + _GOLDEN_INV * (hi - lo)
            fd = func(d)

    class _Result:
        pass

    res = _Result()
    res.x = (lo + hi) / 2.0
    res.fun = func(res.x)
    return res


# ---------------------------------------------------------------------------
# Student-t survival function (needed for the paired t-test's p-value)
# ---------------------------------------------------------------------------

def _betacf(a, b, x, itmax=300, eps=3e-16):
    """Continued-fraction expansion for the incomplete beta function
    (Lentz's algorithm). Standard formulation."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1e-300:
        d = 1e-300
    d = 1.0 / d
    h = d
    for m in range(1, itmax + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-300:
            d = 1e-300
        c = 1.0 + aa / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-300:
            d = 1e-300
        c = 1.0 + aa / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def _betainc(a, b, x):
    """Regularized incomplete beta I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
             + a * math.log(x) + b * math.log1p(-x))
    front = math.exp(lbeta)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + b * math.log1p(-x) + a * math.log(x)
    ) * _betacf(b, a, 1.0 - x) / b


def student_t_sf(t, df):
    """P(T > t) for Student's t with `df` degrees of freedom."""
    t = float(t)
    df = float(df)
    if df <= 0:
        return float("nan")
    x = df / (df + t * t)
    tail = 0.5 * _betainc(df / 2.0, 0.5, x)
    return tail if t > 0 else 1.0 - tail


# ---------------------------------------------------------------------------
# Correlation and the paired t-test
# ---------------------------------------------------------------------------

class _Result:
    def __init__(self, statistic, pvalue=None):
        self.statistic = statistic
        self.pvalue = pvalue


def _rankdata(a):
    """Ranks with ties averaged -- the same convention Spearman requires."""
    a = np.asarray(a, dtype=float)
    order = a.argsort(kind="mergesort")
    ranks = np.empty(len(a), dtype=float)
    ranks[order] = np.arange(1, len(a) + 1, dtype=float)
    # Average the ranks within each group of tied values.
    srt = a[order]
    i = 0
    while i < len(srt):
        j = i
        while j + 1 < len(srt) and srt[j + 1] == srt[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = ranks[order[i:j + 1]].mean()
        i = j + 1
    return ranks


def spearmanr(x, y):
    """Spearman rank correlation. Pearson on tie-averaged ranks."""
    rx, ry = _rankdata(x), _rankdata(y)
    if rx.std() == 0 or ry.std() == 0:
        return _Result(float("nan"))
    return _Result(float(np.corrcoef(rx, ry)[0, 1]))


def ttest_rel(a, b):
    """Two-sided paired t-test."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    d = a - b
    n = len(d)
    if n < 2:
        return _Result(float("nan"), float("nan"))
    sd = d.std(ddof=1)
    if sd == 0:
        return _Result(0.0, 1.0)
    t = float(d.mean() / (sd / math.sqrt(n)))
    p = 2.0 * student_t_sf(abs(t), n - 1)
    return _Result(t, float(min(max(p, 0.0), 1.0)))


# ---------------------------------------------------------------------------
# Self-verification against SciPy (decision: prove, do not assert)
# ---------------------------------------------------------------------------

def verify_against_scipy(verbose: bool = True) -> dict:
    """Check every function here against SciPy. Requires SciPy, so it is
    never called on the normal path -- it is the evidence that this module is
    a drop-in replacement rather than an approximation of one.
    """
    try:
        from scipy import optimize as sp_opt, stats as sp_stats
    except ImportError:
        raise SystemExit(
            "verify_against_scipy needs SciPy installed. That is the point: "
            "this check exists to be run in an environment that HAS SciPy, so "
            "the environments that do not can rely on the result."
        )
    rng = np.random.default_rng(4)
    report = {}

    k = np.arange(0, 60)
    worst = 0.0
    for r in (0.5, 1.0, 6.4, 20.0, 100.0):
        for mu in (0.5, 2.0, 6.0, 23.0, 45.0):
            p = r / (r + mu)
            worst = max(worst, float(np.abs(
                nbinom_logpmf(k, r, p) - sp_stats.nbinom.logpmf(k, r, p)).max()))
    report["nbinom_logpmf_max_abs_err"] = worst

    worst_t = 0.0
    for df in (1, 2, 5, 16, 64, 300):
        for t in (0.0, 0.3, 1.0, 1.96, 3.5, 8.0):
            worst_t = max(worst_t, abs(student_t_sf(t, df) - sp_stats.t.sf(t, df)))
    report["student_t_sf_max_abs_err"] = worst_t

    worst_s, worst_tt, worst_p, worst_min = 0.0, 0.0, 0.0, 0.0
    for _ in range(40):
        n = int(rng.integers(8, 200))
        x = rng.normal(size=n)
        y = 0.4 * x + rng.normal(size=n)
        y[rng.integers(0, n, size=max(1, n // 10))] = 0.0   # force ties
        worst_s = max(worst_s, abs(spearmanr(x, y).statistic
                                   - sp_stats.spearmanr(x, y).statistic))
        mine, theirs = ttest_rel(x, y), sp_stats.ttest_rel(x, y)
        worst_tt = max(worst_tt, abs(mine.statistic - theirs.statistic))
        worst_p = max(worst_p, abs(mine.pvalue - theirs.pvalue))

        # UNIMODAL test functions only. An earlier version of this check used
        # a multimodal one and reported a 0.87 discrepancy -- which was the
        # test being wrong, not the minimiser: golden-section and Brent can
        # legitimately settle in different local minima, and neither is
        # incorrect. Every real call site here minimises a smooth unimodal
        # negative log-likelihood, so that is what gets verified.
        c = rng.uniform(-1, 3)
        f = lambda v, c=c: (v - c) ** 2 + 0.1 * abs(v - c)
        worst_min = max(worst_min, abs(
            minimize_scalar_bounded(f, (-2.0, 8.0)).x
            - sp_opt.minimize_scalar(f, bounds=(-2.0, 8.0), method="bounded").x))
    report["spearmanr_max_abs_err"] = worst_s
    report["ttest_rel_statistic_max_abs_err"] = worst_tt
    report["ttest_rel_pvalue_max_abs_err"] = worst_p
    report["minimize_scalar_max_abs_err"] = worst_min

    # The real call site: an NB dispersion MLE on realistic counts. This is
    # the number that actually ships inside dst_model.json, so it is checked
    # end to end rather than only component by component.
    worst_r = 0.0
    for true_r, mu_level in ((6.4, 23.0), (8.5, 2.4), (16.0, 0.8), (40.0, 12.0)):
        mu = np.full(1500, mu_level)
        y = rng.negative_binomial(true_r, true_r / (true_r + mu))

        def nll_mine(log_r, y=y, mu=mu):
            r = math.exp(log_r)
            return -float(nbinom_logpmf(y, r, r / (r + mu)).sum())

        def nll_scipy(log_r, y=y, mu=mu):
            r = math.exp(log_r)
            return -float(sp_stats.nbinom.logpmf(y, r, r / (r + mu)).sum())

        mine = math.exp(minimize_scalar_bounded(nll_mine, (-2.0, 8.0)).x)
        theirs = math.exp(sp_opt.minimize_scalar(
            nll_scipy, bounds=(-2.0, 8.0), method="bounded").x)
        worst_r = max(worst_r, abs(mine - theirs) / theirs)
    report["nb_dispersion_mle_max_rel_err"] = worst_r

    if verbose:
        print("statlite vs SciPy -- max absolute error across the grid:")
        for key, value in report.items():
            print(f"  {key:38s} {value:.3e}")
    return report


if __name__ == "__main__":
    verify_against_scipy()
