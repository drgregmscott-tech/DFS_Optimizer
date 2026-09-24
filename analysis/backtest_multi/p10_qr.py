"""Item 2 (revised): p10 as a per-position linear 10% quantile regression of
actual DK points on the build's own outputs, p10 = max(0, X @ beta), fit as an
LP (scipy HiGHS). Folds: leave-one-season-out and fit 2014-17 / test 2018-21.
Reports pinball-10 loss vs the MC statline_p10 (week-bootstrap CI), coverage
by position x projection bin, and the all-season production coefficients.

  python analysis/backtest_multi/p10_qr.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linprog

sys.path.insert(0, str(Path(__file__).resolve().parent))
import followups as fu  # noqa: E402

TAU = 0.10
MODELS = {"QR_final": ["final_projection"], "QR_final_sigma": ["final_projection", "sigma"]}


def qr_fit(X, y, tau=TAU):
    n, k = X.shape
    c = np.r_[np.zeros(k), tau * np.ones(n), (1 - tau) * np.ones(n)]
    A = np.hstack([X, np.eye(n), -np.eye(n)]) if n < 3000 else None
    from scipy.sparse import hstack, identity, csr_matrix
    A = hstack([csr_matrix(X), identity(n), -identity(n)]).tocsr()
    bounds = [(None, None)] * k + [(0, None)] * (2 * n)
    r = linprog(c, A_eq=A, b_eq=y, bounds=bounds, method="highs")
    if r.status != 0:
        raise RuntimeError(r.message)
    return r.x[:k]


def design(d, cols):
    return np.column_stack([np.ones(len(d))] + [d[c].to_numpy(float) for c in cols])


def pin(y, q):
    u = y - q
    return np.maximum(TAU * u, (TAU - 1) * u)


def fit_all(train, cols):
    return {p: qr_fit(design(g, cols), g["actual_points"].to_numpy(float)) for p, g in train.groupby("position")}


def predict(d, betas, cols):
    out = pd.Series(0.0, index=d.index)
    for p, g in d.groupby("position"):
        out[g.index] = np.clip(design(g, cols) @ betas[p], 0, None)
    return out


def ci(d, col):
    w = d.groupby(["season", "week"])[col].agg(["sum", "size"])
    rng = np.random.default_rng(7)
    idx = rng.integers(0, len(w), (2000, len(w)))
    bs = w["sum"].to_numpy()[idx].sum(1) / w["size"].to_numpy()[idx].sum(1)
    return w["sum"].sum() / w["size"].sum(), np.percentile(bs, 2.5), np.percentile(bs, 97.5)


def main():
    d = fu.load("baseline", "played")
    d = d[d["position"].isin(fu.SKILL) & d["sigma"].gt(0)].copy()
    # subsample-free: n per position-fold is 4k-14k rows, fine for HiGHS
    lines = [f"baseline played skill n={len(d)}"]
    for name, cols in MODELS.items():
        parts = []
        for s in fu.SEASONS:
            b = fit_all(d[d["season"] != s], cols)
            t = d[d["season"] == s].copy()
            t["p10n"] = predict(t, b, cols)
            parts.append(t)
        t = pd.concat(parts)
        t["dl"] = pin(t["actual_points"], t["p10n"]) - pin(t["actual_points"], t["statline_p10"])
        t["below"] = t["actual_points"] < t["p10n"]
        lines.append(f"\n==== {name} (LOSO) ====")
        for lab, g in [("skill", t)] + [(p, t[t["position"] == p]) for p in fu.SKILL]:
            m, lo, hi = ci(g, "dl")
            r, rlo, rhi = ci(g, "below")
            by = g.groupby("season")["dl"].mean()
            lines.append(f"  {lab:5s} n={len(g):5d} dPinball10={m:+.4f} [{lo:+.4f},{hi:+.4f}] improved {int((by < 0).sum())}/8 "
                         f"seasons; below {r:.3f} [{rlo:.3f},{rhi:.3f}] (MC {(g['actual_points'] < g['statline_p10']).mean():.3f})")
        t["bin"] = pd.cut(t["final_projection"], [0, 3, 6, 10, 15, 20, 25, 60])
        gb = t.groupby(["position", "bin"], observed=True).apply(lambda x: pd.Series({
            "n": len(x), "below_mc": (x["actual_points"] < x["statline_p10"]).mean(),
            "below_new": x["below"].mean(), "p10_mc": x["statline_p10"].mean(), "p10_new": x["p10n"].mean(),
            "emp_q10": x["actual_points"].quantile(0.1)}))
        lines.append(gb.round(3).to_string())
        # fixed split
        b = fit_all(d[d["season"] <= 2017], cols)
        t2 = d[d["season"] >= 2018].copy()
        t2["p10n"] = predict(t2, b, cols)
        t2["dl"] = pin(t2["actual_points"], t2["p10n"]) - pin(t2["actual_points"], t2["statline_p10"])
        m, lo, hi = ci(t2, "dl")
        lines.append(f"  fit14-17/test18-21 skill n={len(t2)} dPinball10={m:+.4f} [{lo:+.4f},{hi:+.4f}] "
                     f"below {(t2['actual_points'] < t2['p10n']).mean():.3f}; by pos below " + ", ".join(
                         f"{p}:{(g['actual_points'] < g['p10n']).mean():.3f}" for p, g in t2.groupby("position")))
        ball = fit_all(d, cols)
        lines.append("  production coefficients (all 8 seasons) [const, " + ", ".join(cols) + "]: " + "; ".join(
            f"{p}: " + ", ".join(f"{v:+.4f}" for v in bb) for p, bb in sorted(ball.items())))
        lines.append("  fit14-17 coefficients: " + "; ".join(
            f"{p}: " + ", ".join(f"{v:+.4f}" for v in bb) for p, bb in sorted(b.items())))
    fu.write("followups_p10_qr", lines)


if __name__ == "__main__":
    main()
