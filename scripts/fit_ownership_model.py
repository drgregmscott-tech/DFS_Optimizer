"""
fit_ownership_model.py
=======================

Fits the layered ownership model (see ownership_model.py) against the real
post-lock DK ownership in data/ownership_actual_log.csv and writes
data/ownership_model_dk.json.

    python scripts/fit_ownership_model.py            # fit + leave-one-week-out report + write artifact
    python scripts/fit_ownership_model.py --no-write # report only

Uses every DK classic regular-season slate in the log whose
output/final_projections_dk_{slate_id}.csv still exists. Players in a slate's
projection file with a positive projection but no logged ownership count as
0% owned (they were never drafted). Exposure is recomputed per slate from the
projection file (deterministic seed), so results are reproducible.

Honest limits, printed with the report: the effective sample is a handful of
weeks, so the fit is a small ridge regression on 7 features, and it is scored
leave-one-week-out (train on the other weeks, predict this one). Refit every
week; expect coefficients to move.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ownership_model as om  # noqa: E402
import ownership_heuristic as oh  # noqa: E402
import build_projections as bp  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
OUTPUT_DIR = REPO_ROOT / "output"
RIDGE = 1.0
CHALK_THRESHOLD = 20.0


def load_training_frame(site: str = "dk") -> pd.DataFrame:
    log = pd.read_csv(DATA_DIR / "ownership_actual_log.csv", dtype={"player_id": str})
    log = log[(log["site"] == site) & (log["slate_format"] == "classic")
              & (log["slate_type"] == "regular_season")]
    frames = []
    for slate_id, g in log.groupby("slate_id"):
        path = OUTPUT_DIR / f"final_projections_{site}_{slate_id}.csv"
        if not path.exists():
            print(f"  skip {slate_id}: {path.name} missing")
            continue
        df = pd.read_csv(path, dtype={"player_id": str, "site_player_id": str})
        # Recompute the pure heuristic on the file as it stands now (post OUT
        # zeroing), i.e. exactly what the runtime layer sees as its l_est input.
        df = df.drop(columns=["chalk_score", "estimated_ownership_pct",
                              "estimated_ownership_pct_heuristic"], errors="ignore")
        df = bp.add_ownership_columns(df, site, layered=False)
        df = df[df["final_projection"] > 0].copy()
        own = g.drop_duplicates("player_id").set_index("player_id")["actual_ownership_pct"]
        df["own"] = df["player_id"].map(own).fillna(0.0)
        df["position_group"] = np.where(df["position"].isin(list(om.DEFENSE_LABELS)), "DST", df["position"])
        exposure = om.optimizer_exposure(df, site)
        feats = om.build_features(df, exposure)
        df = pd.concat([df, feats], axis=1)
        df["slate_id"] = slate_id
        df["week"] = int(g["week"].iloc[0])
        print(f"  {slate_id}: {len(df)} players, week {df['week'].iloc[0]}")
        frames.append(df)
    if not frames:
        raise SystemExit("no usable slates -- log ownership first (log_ownership.py)")
    return pd.concat(frames, ignore_index=True)


def fit(train: pd.DataFrame, ridge: float = RIDGE) -> dict:
    X = train[om.FEATURES].to_numpy(float)
    y = om._logit(train["own"].to_numpy(float))
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1.0
    Z = (X - mu) / sd
    A = np.column_stack([np.ones(len(Z)), Z])
    pen = np.eye(A.shape[1]) * ridge
    pen[0, 0] = 0.0
    beta = np.linalg.solve(A.T @ A + pen, A.T @ y)
    coefs = beta[1:] / sd
    intercept = beta[0] - float(np.sum(coefs * mu))
    out = {"intercept": float(intercept)}
    out.update({n: float(c) for n, c in zip(om.FEATURES, coefs)})
    return {"coefs": out, "cap": om.OWNERSHIP_CAP_PCT}


def score(df: pd.DataFrame, pred: pd.Series, label: str) -> dict:
    chalk = df["own"] >= CHALK_THRESHOLD
    err = pred - df["own"]
    res = dict(label=label,
               corr=round(float(np.corrcoef(pred, df["own"])[0, 1]), 3),
               mae=round(float(err.abs().mean()), 2),
               chalk_n=int(chalk.sum()),
               chalk_mae=round(float(err[chalk].abs().mean()), 1),
               chalk_bias=round(float(err[chalk].mean()), 1))
    return res


def predict_slates(df: pd.DataFrame, artifact: dict, budgets: dict) -> pd.Series:
    out = pd.Series(0.0, index=df.index)
    for _, g in df.groupby("slate_id"):
        feats = g[om.FEATURES]
        out.loc[g.index] = om.predict(g, feats, artifact, budgets)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="dk")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--ridge", type=float, default=RIDGE)
    args = ap.parse_args()

    print("Building training frame (this runs the optimizer 60x per slate)...")
    df = load_training_frame(args.site)
    budgets = oh.compute_position_slot_budgets(args.site)
    weeks = sorted(df["week"].unique())
    print(f"\nSlates: {df['slate_id'].nunique()}, weeks: {weeks}, rows: {len(df)}")

    print(f"\nLeave-one-week-out (chalk = real ownership >= {CHALK_THRESHOLD:.0f}%):")
    heur = df["estimated_ownership_pct"]
    for w in weeks:
        test = df[df["week"] == w]
        train = df[df["week"] != w]
        art = fit(train, args.ridge)
        pred = predict_slates(test, art, budgets)
        for r in (score(test, heur.loc[test.index], f"week {w} heuristic (as built)"),
                  score(test, pred, f"week {w} layered model (trained on other weeks)")):
            print("  ", r)

    art = fit(df, args.ridge)
    in_sample = score(df, predict_slates(df, art, budgets), "in-sample, all weeks")
    print("\n  ", in_sample)
    print("\nCoefficients (logit scale, cap %.0f%%):" % om.OWNERSHIP_CAP_PCT)
    for k, v in art["coefs"].items():
        print(f"   {k:10s} {v:+.4f}")

    if not args.no_write:
        art.update({
            "version": 1,
            "site": args.site,
            "fit_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "weeks": [int(w) for w in weeks],
            "slates": sorted(df["slate_id"].unique().tolist()),
            "n_rows": int(len(df)),
            "ridge": args.ridge,
            "features": om.FEATURES,
            "exposure_lineups": om.EXPOSURE_LINEUPS,
            "exposure_randomization_pct": om.EXPOSURE_RANDOMIZATION_PCT,
            "in_sample": in_sample,
        })
        path = om.artifact_path(args.site)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(art, f, indent=2)
        print(f"\nWrote {path}")


if __name__ == "__main__":
    main()
