"""Evaluate an ownership refit on FC history using OUR reconstructed projection,
plus a projection-free shape/calibration check (step 3).

Inputs (FC-derived, git-ignored): data/fc_history/derived/fc_own_features_ourproj.parquet,
  data/fc_history/derived/fc_own_features_single_entry.parquet (FC-proj features, for comparison)
Our data: analysis/ownership_fc_refit/cache_2026.parquet (real 2026 wk1-2, production projections)
Writes nothing unless --write (then only NEW artifact names).
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "analysis/ownership_fc_refit"))
import ownership_model as om  # noqa: E402
from evaluate import BASE, EXTRA, add_extras, fit, predict, metrics, fmt, linpred, combine  # noqa: E402

DER = REPO / "data/fc_history/derived"


def loso(h, feats):
    p = pd.Series(0.0, index=h.index)
    for s in sorted(h.season.unique()):
        te = h.season == s
        p[te] = predict(h[te], fit(h[~te], feats))
    return p


def shape(df, col, label):
    g = df.assign(v=df[col])
    tiers = pd.cut(g.salary, [0, 3999, 5499, 6999, 99999], labels=["<4k", "4-5.5k", "5.5-7k", "7k+"])
    per = g.groupby("slate_id")
    n_sl = g.slate_id.nunique()
    tier_sum = g.groupby(tiers, observed=False)["v"].sum() / n_sl
    pos_sum = g.groupby("position")["v"].sum() / n_sl
    c20 = per["v"].apply(lambda x: (x >= 20).sum()).mean()
    c10 = per["v"].apply(lambda x: (x >= 10).sum()).mean()
    c1020 = per["v"].apply(lambda x: ((x >= 10) & (x < 20)).sum()).mean()
    top = per["v"].max().mean()
    tot = per["v"].sum().mean()
    print(f"{label:38s} tot {tot:5.0f} | n20+ {c20:4.1f} n10-20 {c1020:4.1f} n10+ {c10:4.1f} top {top:4.1f} | "
          + " ".join(f"{k}:{v:4.0f}" for k, v in tier_sum.items()) + " | "
          + " ".join(f"{k}:{v:4.0f}" for k, v in pos_sum.items()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    H = add_extras(pd.read_parquet(DER / "fc_own_features_ourproj.parquet"))
    F = add_extras(pd.read_parquet(DER / "fc_own_features_single_entry.parquet"))
    h, h26 = H[H.season <= 2025].copy(), H[H.season == 2026].copy()
    f = F[F.season <= 2025]
    print(f"history(ourproj): {h.slate_id.nunique()} slates {len(h)} rows; own kept/slate "
          f"{h.groupby('slate_id').own.sum().mean():.0f} of {h.groupby('slate_id').own_total_all.first().mean():.0f}")

    # ---- key question: projection-ownership correlation, same players/weeks
    j = h.merge(f[["slate_id", "player_id", "final_projection"]].rename(columns={"final_projection": "fcp"}),
                on=["slate_id", "player_id"])
    print("\n=== corr(projection, ownership), identical rows ===")
    for lab, m in [("all incl DST", j), ("skill only", j[j.position != "DST"])]:
        c_o = m.final_projection.corr(m.own)
        c_f = m.fcp.corr(m.own)
        per = m.groupby("season").apply(lambda x: (round(x.final_projection.corr(x.own), 3), round(x.fcp.corr(x.own), 3)))
        print(f"{lab:14s} n={len(m)} ours {c_o:.3f}  FC {c_f:.3f}  ours~FC {m.final_projection.corr(m.fcp):.3f}  per-season(ours,FC) {per.to_dict()}")
        wm = m.groupby("slate_id").apply(lambda x: pd.Series({"o": x.final_projection.corr(x.own), "f": x.fcp.corr(x.own)})).mean()
        print(f"{'':14s} mean within-slate corr: ours {wm.o:.3f} FC {wm.f:.3f}")
    r26 = add_extras(pd.read_parquet(REPO / "analysis/ownership_fc_refit/cache_2026.parquet"))
    print(f"2026 real (production proj): corr(proj, own) = {r26.final_projection.corr(r26.own):.3f} n={len(r26)}; "
          f"skill {r26[r26.position != 'DST'].final_projection.corr(r26[r26.position != 'DST'].own):.3f}")
    print(f"2026 FC-main wk1-2 (reconstructed ourproj): corr = {h26.final_projection.corr(h26.own):.3f} n={len(h26)}")
    r26m = r26.merge(h26[["week", "player_id", "final_projection"]].rename(columns={"final_projection": "recon"}),
                     on=["week", "player_id"])
    r26m = r26m[r26m.slate_id.str.contains("main")] if r26m.slate_id.str.contains("main").any() else r26m
    print(f"2026 same players, main: prod proj~own {r26m.final_projection.corr(r26m.own):.3f}, recon~own "
          f"{r26m.recon.corr(r26m.own):.3f}, prod~recon {r26m.final_projection.corr(r26m.recon):.3f} n={len(r26m)}")

    # ---- history LOSO
    sets = {"OP-base": BASE, "OP-extra": BASE + EXTRA}
    print("\n=== History LOSO (ourproj features) ===")
    lo = {}
    for n, fe in sets.items():
        lo[n] = loso(h, fe)
        print(fmt(n + " LOSO", metrics(h, lo[n])))
        print("   per-season corr:", [round(metrics(h[h.season == s], lo[n][h.season == s])["corr"], 3) for s in sorted(h.season.unique())])
    hp = h.copy()
    hp["pub_val"] = 0.0
    prod = om.load_artifact("dk")
    ph = predict(hp, prod)
    print(fmt("prod artifact on history (pub_val=0)", metrics(h, ph)))
    fl = loso(f, BASE)
    print(fmt("FC-proj base LOSO (prev agent, own rows)", metrics(f, fl)))

    # ---- independent 2026
    print("\n=== Real 2026 wk1-2 (independent of history fit) ===")
    r = r26.copy()
    r["ffc_listed"] = r["ffc_listed"].fillna(0)
    prod_ffc = om.load_artifact("dk", "_ffc")
    hasf = lambda df: df.groupby("slate_id")["ffc_listed"].transform("sum") >= om.MIN_FFC_LISTED  # noqa: E731

    def route(df, b, fa):
        p = predict(df, b)
        m = hasf(df)
        if m.any():
            p[m] = predict(df[m], fa)
        return p
    res = {"prod artifacts (in-sample on 2026)": route(r, prod, prod_ffc)}
    low = pd.Series(0.0, index=r.index)
    for w in (1, 2):
        te, tr = r.week == w, r.week != w
        b = fit(r[tr], om.FEATURES)
        ft = r[tr & hasf(r)]
        low[te] = route(r[te], b, fit(ft, om.FEATURES + om.FFC_FEATURES) if len(ft) else b)
    res["prod recipe LOWO on 2026 (honest baseline)"] = low
    arts = {n: fit(h, fe) for n, fe in sets.items()}
    for n, art in arts.items():
        res[f"{n} fit 2021-25 only"] = predict(r, art)
        lay = pd.Series(0.0, index=r.index)
        for w in (1, 2):
            te, tr = r.week == w, r.week != w
            l1 = combine(art, fit(r[tr], ["pub_val"], offset=linpred(r[tr], art)))
            ftr = tr & hasf(r)
            l2 = combine(art, fit(r[ftr], ["pub_val"] + om.FFC_FEATURES, offset=linpred(r[ftr], art))) if ftr.any() else l1
            lay[te] = route(r[te], l1, l2)
        res[f"{n} + 2026 pub_val/FFC layer LOWO"] = lay
    for k, p in res.items():
        print(fmt(k, metrics(r, p)))
        for w in (1, 2):
            m = metrics(r[r.week == w], p[r.week == w])
            print(f"     wk{w}: corr {m['corr']:.3f} mae {m['mae']:.2f} c10 {m['catch10']:.2f} p10 {m['prec10']:.2f} "
                  f"c20 {m['catch20']:.2f} p20 {m['prec20']:.2f} 10-20 c {m['t1020_catch']:.2f} chalk {m['chalk_bias']:+.1f}")
    print("\n=== 2026 FC main wk1-2, reconstructed ourproj features (2 slates) ===")
    h26p = h26.copy()
    h26p["pub_val"] = 0.0
    print(fmt("prod artifact (pub_val=0)", metrics(h26, predict(h26p, prod))))
    for n, art in arts.items():
        print(fmt(f"{n} fit 2021-25", metrics(h26, predict(h26, art))))

    # ---- step 3 shape
    print("\n=== Shape (per-slate averages): tot | chalk counts | salary tiers | positions ===")
    shape(h, "own", "FC history REAL (2021-25)")
    shape(h.assign(p=lo["OP-base"]), "p", "OP-base LOSO pred on history")
    shape(h.assign(p=ph), "p", "prod artifact on history (pub_val=0)")
    shape(r, "own", "2026 REAL (6 slates)")
    shape(r.assign(p=res["prod artifacts (in-sample on 2026)"]), "p", "prod artifacts on 2026")
    shape(r.assign(p=res["OP-base fit 2021-25 only"]), "p", "OP-base on 2026")
    mains = r[r.slate_id.str.contains("main")]
    shape(mains, "own", "2026 REAL main only")
    shape(mains.assign(p=res["prod artifacts (in-sample on 2026)"][mains.index]), "p", "prod on 2026 main")
    print("\nOP-base coefs:", {k: round(v, 3) for k, v in arts["OP-base"]["coefs"].items()})
    print("prod coefs   :", {k: round(v, 3) for k, v in prod["coefs"].items()})
    if a.write:
        out = REPO / "data/ownership_model_dk_fchist_ourproj.json"
        assert not out.exists()
        json.dump(arts["OP-base"], open(out, "w"), indent=2)
        print("wrote", out)


if __name__ == "__main__":
    main()
