"""Evaluate FC-history refits of the DK classic ownership model.

Inputs: data/fc_history/derived/fc_own_features_single_entry.parquet (FC, git-ignored)
        analysis/ownership_fc_refit/cache_2026.parquet (real 2026 wk1-2, our logs)
Nothing here is written unless --write is passed (then only NEW artifact files).
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import ownership_model as om  # noqa: E402
import ownership_heuristic as oh  # noqa: E402
import fit_ownership_model as fom  # noqa: E402

BUDGETS = oh.compute_position_slot_budgets("dk")
BASE = ["l_est", "l_exp", "sal", "top1sal", "cv", "dart", "lo_proj"]
EXTRA = ["vegas_pts", "l_salrank", "l_valrank", "l_projrank"]


def add_extras(df):
    df = df.copy()
    df["position_group"] = np.where(df["position"].isin(list(om.DEFENSE_LABELS)), "DST", df["position"])
    df["vegas_pts"] = pd.to_numeric(df["vegas_pts"], errors="coerce")
    df["vegas_pts"] = df["vegas_pts"].fillna(df.groupby("slate_id")["vegas_pts"].transform("median")).fillna(22.0)
    for c in ("sal_rank", "val_rank", "proj_rank"):
        df["l_" + c.replace("_", "")] = np.log(df[c].clip(lower=1))
    return df


def fit(train, feats, ridge=1.0, offset=None):
    """fom.fit, optionally with a fixed offset (base-layer linear predictor)."""
    if offset is None:
        return fom.fit(train, ridge, feats)
    X = train[feats].to_numpy(float)
    y = om._logit(train["own"].to_numpy(float)) - offset
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1.0
    A = np.column_stack([np.ones(len(X)), (X - mu) / sd])
    pen = np.eye(A.shape[1]) * ridge
    pen[0, 0] = 0
    b = np.linalg.solve(A.T @ A + pen, A.T @ y)
    co = b[1:] / sd
    out = {"intercept": float(b[0] - np.sum(co * mu))}
    out.update({n: float(c) for n, c in zip(feats, co)})
    return {"coefs": out, "cap": om.OWNERSHIP_CAP_PCT, "features": list(feats)}


def linpred(df, art):
    z = np.full(len(df), art["coefs"]["intercept"])
    for f in art["features"]:
        z = z + art["coefs"][f] * df[f].to_numpy(float)
    return z


def combine(a, b):
    """Sum two linear layers into one artifact."""
    co = dict(a["coefs"])
    co["intercept"] += b["coefs"]["intercept"]
    for f in b["features"]:
        co[f] = co.get(f, 0.0) + b["coefs"][f]
    feats = list(dict.fromkeys(a["features"] + b["features"]))
    return {"coefs": co, "cap": om.OWNERSHIP_CAP_PCT, "features": feats}


def predict(df, art):
    out = pd.Series(0.0, index=df.index)
    for _, g in df.groupby("slate_id"):
        out.loc[g.index] = om.predict(g, g, art, BUDGETS)
    return out


def metrics(df, pred):
    y = df["own"].to_numpy(float)
    p = pred.to_numpy(float)
    r = {"n": len(y), "slates": df["slate_id"].nunique(),
         "corr": np.corrcoef(p, y)[0, 1], "mae": np.abs(p - y).mean()}
    for t in (10, 20):
        real, hit = y >= t, p >= t
        r[f"catch{t}"] = (real & hit).sum() / max(real.sum(), 1)
        r[f"prec{t}"] = (real & hit).sum() / max(hit.sum(), 1)
        r[f"n{t}"] = int(real.sum())
    tier = (y >= 10) & (y < 20)
    r["t1020_catch"] = (tier & (p >= 10)).sum() / max(tier.sum(), 1)
    r["t1020_mae"] = np.abs(p - y)[tier].mean()
    r["t1020_bias"] = (p - y)[tier].mean()
    ch = y >= 20
    r["chalk_bias"] = (p - y)[ch].mean()
    return r


def fmt(label, r):
    return (f"{label:44s} n={r['n']:5d} corr {r['corr']:.3f} mae {r['mae']:.2f} | "
            f"10+ catch {r['catch10']:.2f} prec {r['prec10']:.2f} (n{r['n10']}) | "
            f"20+ catch {r['catch20']:.2f} prec {r['prec20']:.2f} (n{r['n20']}) | "
            f"10-20 catch {r['t1020_catch']:.2f} mae {r['t1020_mae']:.1f} bias {r['t1020_bias']:+.1f} | "
            f"chalk bias {r['chalk_bias']:+.1f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    h = add_extras(pd.read_parquet(REPO / "data/fc_history/derived/fc_own_features_single_entry.parquet"))
    h26 = h[h["season"] == 2026]
    h = h[h["season"] <= 2025]  # 2026 FC SE == our real contests (corr .999): exclude
    r = add_extras(pd.read_parquet(REPO / "analysis/ownership_fc_refit/cache_2026.parquet"))
    r["ffc_listed"] = r["ffc_listed"].fillna(0)
    print(f"history: {h['slate_id'].nunique()} slates, {len(h)} rows; 2026 real: {r['slate_id'].nunique()} slates, {len(r)} rows")
    print("pred sums per slate (sanity, must be ~900):")

    sets = {"H-base (prod feats - pub_val)": BASE, "H-extra (+vegas, ranks)": BASE + EXTRA}

    # ---- 1. LOSO / LOWO on history
    print("\n=== History, leave-one-season-out (pooled over held-out seasons) ===")
    for name, feats in sets.items():
        preds = pd.Series(0.0, index=h.index)
        for s in sorted(h["season"].unique()):
            te = h["season"] == s
            preds[te] = predict(h[te], fit(h[~te], feats))
        print(fmt(name, metrics(h, preds)))
        per = [metrics(h[h.season == s], preds[h.season == s])["corr"] for s in sorted(h.season.unique())]
        print("   per-season corr:", np.round(per, 3))
        ins = predict(h, fit(h, feats))
        print(fmt("   same-sample " + name, metrics(h, ins)))
    print("\n=== History, leave-one-week-out (week number across seasons) ===")
    for name, feats in sets.items():
        preds = pd.Series(0.0, index=h.index)
        for w in sorted(h["week"].unique()):
            te = h["week"] == w
            preds[te] = predict(h[te], fit(h[~te], feats))
        print(fmt(name, metrics(h, preds)))
    # production artifacts applied to history (pub_val=0 -> intercept shift; FYI only)
    hh = h.copy()
    hh["pub_val"] = 0.0
    prod = om.load_artifact("dk")
    print(fmt("prod base artifact on history (pub_val=0!)", metrics(hh, predict(hh, prod))))

    # ---- 2. Independent test: real 2026 wk1-2
    print("\n=== Real 2026 wk1-2 (6 slates, 2 weeks, overlapping players) ===")
    prod_ffc = om.load_artifact("dk", "_ffc")
    has_ffc = r.groupby("slate_id")["ffc_listed"].transform("sum") >= om.MIN_FFC_LISTED
    print(f"slates with FFC table: {sorted(r.loc[has_ffc, 'slate_id'].unique())}")

    def prod_route(df, base_art, ffc_art):
        p = predict(df, base_art)
        m = df.groupby("slate_id")["ffc_listed"].transform("sum") >= om.MIN_FFC_LISTED
        if m.any():
            p[m] = predict(df[m], ffc_art)
        return p

    res = {}
    res["prod artifacts (IN-SAMPLE, fit on these)"] = prod_route(r, prod, prod_ffc)
    # production recipe, leave-one-week-out on 2026 -- the honest current baseline
    lowo = pd.Series(0.0, index=r.index)
    for w in (1, 2):
        te, tr = r.week == w, r.week != w
        b = fit(r[tr], om.FEATURES)
        f_tr = r[tr & (r.groupby("slate_id")["ffc_listed"].transform("sum") >= om.MIN_FFC_LISTED)]
        fa = fit(f_tr, om.FEATURES + om.FFC_FEATURES) if len(f_tr) else b
        lowo[te] = prod_route(r[te], b, fa)
    res["prod recipe, LOWO on 2026 (baseline)"] = lowo

    hist_arts = {n: fit(h, f) for n, f in sets.items()}
    for n, a in hist_arts.items():
        res[f"{n}, fit 2021-25 only"] = predict(r, a)
    # layered: history base as fixed offset, pub_val (+FFC) layer fit on the OTHER 2026 week
    for n, a in hist_arts.items():
        lay = pd.Series(0.0, index=r.index)
        for w in (1, 2):
            te, tr = r.week == w, r.week != w
            off = linpred(r[tr], a)
            l1 = combine(a, fit(r[tr], ["pub_val"], offset=off))
            ftr = tr & (r.groupby("slate_id")["ffc_listed"].transform("sum") >= om.MIN_FFC_LISTED)
            l2 = combine(a, fit(r[ftr], ["pub_val"] + om.FFC_FEATURES, offset=linpred(r[ftr], a))) if ftr.any() else l1
            lay[te] = prod_route(r[te], l1, l2)
        res[f"{n} + 2026 pub_val/FFC layer, LOWO"] = lay
    for k, p in res.items():
        print(fmt(k, metrics(r, p)))
        for w in (1, 2):
            m = metrics(r[r.week == w], p[r.week == w])
            print(f"     wk{w}: corr {m['corr']:.3f} mae {m['mae']:.2f} catch10 {m['catch10']:.2f} "
                  f"prec10 {m['prec10']:.2f} catch20 {m['catch20']:.2f} 10-20 catch {m['t1020_catch']:.2f}")
    print("\npred sum per slate (should be ~900):",
          res["H-extra (+vegas, ranks), fit 2021-25 only"].groupby(r["slate_id"]).sum().round(0).to_dict())
    print("real sum per slate:", r.groupby("slate_id")["own"].sum().round(0).to_dict())
    # FC 2026 SE as a cross-check of the history models on FC's own projections
    for n, a in hist_arts.items():
        print(fmt(f"[FC-proj 2026 SE] {n}", metrics(h26, predict(h26, a))))
    for n, a in hist_arts.items():
        print(f"\n{n} coefficients:", {k: round(v, 3) for k, v in a["coefs"].items()})

    if args.write:
        return hist_arts, r
    return None


if __name__ == "__main__":
    main()
