"""
fit_projection_stack.py
========================

Fits projection_stack.py's per-position linear stack from
data/projection_stack_training_dk.csv (clean, pre-game engine projections for
2020-21 weeks 2-17 + actual DK points + last-4-game usage features) and writes
data/projection_stack_dk.json.

    python scripts/fit_projection_stack.py                  # fit + leave-one-season-out report + write
    python scripts/fit_projection_stack.py --no-write

The training rows must be built WITHOUT look-ahead: each week's engine build
saw only stats from earlier weeks (see WK2_POSTMORTEM.md's correction note).
To extend the training set, append rows with the same columns from future
pre-game ENGINE-ONLY builds (props blended in would change the input
distribution the stack was fit on).
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import projection_stack as ps  # noqa: E402

TRAIN = ps.DATA_DIR / "projection_stack_training_dk.csv"


# Usage features used per position (others get coefficient 0). QBs have no
# receiving usage (their tiny target-share values produced wild coefficients
# with no out-of-sample gain), so the QB stack is salary + engine only.
POS_USAGE = {
    "QB": [],
    "RB": list(ps.USAGE_COLS),
    "WR": list(ps.USAGE_COLS),
    "TE": list(ps.USAGE_COLS),
}
RIDGE = 5.0


def design(d: pd.DataFrame, pos: str = None) -> np.ndarray:
    cols = [np.ones(len(d)), d["salary"].to_numpy(float) / 1000.0, d["engine_projection"].to_numpy(float)]
    use = ps.USAGE_COLS if pos is None else POS_USAGE[pos]
    cols += [d[c].fillna(0.0).to_numpy(float) for c in use]
    return np.column_stack(cols)


def ridge_solve(X, y, lam=RIDGE):
    """OLS with a small ridge penalty on standardized non-intercept columns."""
    mu, sd = X[:, 1:].mean(0), X[:, 1:].std(0)
    sd[sd == 0] = 1.0
    Z = np.column_stack([np.ones(len(X)), (X[:, 1:] - mu) / sd])
    pen = np.eye(Z.shape[1]) * lam
    pen[0, 0] = 0.0
    beta = np.linalg.solve(Z.T @ Z + pen, Z.T @ y)
    coefs = beta[1:] / sd
    return np.concatenate([[beta[0] - float(np.sum(coefs * mu))], coefs])


def fit_pos(d: pd.DataFrame, pos: str):
    return ridge_solve(design(d, pos), d["actual_points"].to_numpy(float))


def r2(y, p):
    return 1.0 - float(((y - p) ** 2).mean() / y.var())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args()
    T = pd.read_csv(TRAIN)
    print(f"Training rows: {len(T)} ({T['season'].nunique()} seasons, {T.groupby(['season','week']).ngroups} weeks)")

    seasons = sorted(T["season"].unique())
    print("\nLeave-one-season-out R2 (engine calibrated alone | engine+salary | full stack):")
    for pos in ps.POSITIONS:
        d = T[T["position"] == pos]
        line = []
        for hold in seasons:
            tr, te = d[d["season"] != hold], d[d["season"] == hold]
            y = te["actual_points"].to_numpy(float)
            b_full = fit_pos(tr, pos)
            p_full = design(te, pos) @ b_full
            # engine alone / engine+salary using the same design with columns masked
            def sub(cols):
                Xtr = design(tr, pos)[:, cols]; Xte = design(te, pos)[:, cols]
                b = np.linalg.lstsq(Xtr, tr["actual_points"].to_numpy(float), rcond=None)[0]
                return Xte @ b
            line.append(f"hold {hold}: {r2(y, sub([0, 2])):.3f} | {r2(y, sub([0, 1, 2])):.3f} | {r2(y, p_full):.3f}")
        print(f"  {pos}: " + "   ".join(line))

    art = {"version": 1, "site": "dk", "fit_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "n_rows": int(len(T)), "seasons": [int(s) for s in seasons], "features": ps.FEATURES,
           "usage_fill": {c: float(T[c].mean()) for c in ps.USAGE_COLS}, "positions": {}}
    for pos in ps.POSITIONS:
        d = T[T["position"] == pos]
        b = fit_pos(d, pos)
        names = ["sal", "proj"] + POS_USAGE[pos]
        coefs = {f: 0.0 for f in ps.FEATURES}
        coefs.update({f: float(v) for f, v in zip(names, b[1:])})
        art["positions"][pos] = {"intercept": float(b[0]), "coefs": coefs, "n": int(len(d))}
        print(f"\n{pos} (n={len(d)}): intercept {b[0]:+.3f}  " + "  ".join(f"{f} {v:+.3f}" for f, v in zip(names, b[1:])))
    if not args.no_write:
        with open(ps.artifact_path("dk"), "w", encoding="utf-8") as f:
            json.dump(art, f, indent=2)
        print(f"\nWrote {ps.artifact_path('dk')}")


if __name__ == "__main__":
    main()
