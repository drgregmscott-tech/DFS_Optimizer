"""Q3 follow-up: does a DST-specific Vegas input fix DST discrimination?
DST-only residual layer on the live model's logit (offset), features:
  l_opprank = log rank (within slate DSTs) of opponent implied total (1 = lowest opp total)
  spread    = own implied - opponent implied (positive = favourite)
  l_dprojrank = log rank of our DST projection within slate
Fit LOSO on 2021-25 history (live base as offset), then fit on all history and apply to 2026 (live FFC route)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run  # noqa: E402

h, r = run.load_hist(), run.load_2026()
lb, lf = run.om.load_artifact("dk"), run.om.load_artifact("dk", "_ffc")


def dfeat(d):
    d = d.copy()
    # team implied from SKILL rows (DST rows' implied_total convention differs between FC history and 2026)
    it = pd.to_numeric(d.implied_total, errors="coerce")
    sk = d[d.position != "DST"].assign(it=it).groupby(["slate_id", "team"]).it.median()
    key = lambda t: list(zip(d.slate_id, t))  # noqa: E731
    own_imp = pd.Series(sk.reindex(key(d.team)).to_numpy(), index=d.index)
    opp = d.opponent.astype(str).str.replace("@", "").str.replace("vs", "").str.strip()
    d["opp_imp"] = pd.Series(sk.reindex(key(opp)).to_numpy(), index=d.index)
    d["spread"] = own_imp - d.opp_imp
    isd = (d.position == "DST") & (d.final_projection > 0)
    d["opp_imp"] = d.opp_imp.where(isd)
    d["opp_imp"] = d.opp_imp.fillna(d.opp_imp.groupby(d.slate_id).transform("median")).fillna(22)
    d["spread"] = d.spread.where(isd).fillna(0)
    d["l_opprank"] = np.where(isd, np.log(d.opp_imp.where(isd).groupby(d.slate_id).rank(method="min").fillna(1)), 0.0)
    d["l_dprojrank"] = np.where(isd, np.log(d.final_projection.where(isd).groupby(d.slate_id).rank(ascending=False, method="min").fillna(1)), 0.0)
    d["spread"] = np.where(isd, d.spread, 0.0)
    return d


h, r = dfeat(h), dfeat(r)
dd_=h[h.position=="DST"]; print("hist DST raw implied vs skill-derived own/opp corr", np.corrcoef(pd.to_numeric(dd_.implied_total), dd_.opp_imp.fillna(22))[0,1].round(3), dd_.opp_imp.notna().mean())
print("vegas coverage DST hist", h[h.position == "DST"].implied_total.notna().mean().round(3),
      "2026", r[r.position == "DST"].implied_total.notna().mean().round(3))
F = ["l_opprank", "spread", "l_dprojrank"]
dh = h[h.position == "DST"]
print("hist DST corr(real own, feature):", {f: round(np.corrcoef(dh[f], dh.own)[0, 1], 3) for f in F + ["final_projection"]})
dr = r[r.position == "DST"]
print("2026 DST corr(real own, feature):", {f: round(np.corrcoef(dr[f], dr.own)[0, 1], 3) for f in F + ["final_projection"]})


def dst_metrics(d, p):
    x = d.assign(p=p)[d.position == "DST"]
    g = x.groupby("slate_id")
    top = g.apply(lambda z: z.loc[z.own.idxmax(), "p"] - z.own.max()).mean()
    hit = g.apply(lambda z: z.p.idxmax() == z.own.idxmax()).mean()
    top3 = g.apply(lambda z: len(set(z.nlargest(3, "p").index) & set(z.nlargest(3, "own").index))).mean()
    c = x[x.own >= 10]
    return (f"mae {np.abs(x.p - x.own).mean():.2f} corr {np.corrcoef(x.p, x.own)[0, 1]:.3f} top {top:+.1f} "
            f"b10+ {(c.p - c.own).mean():+.1f} top1hit {hit:.2f} top3ov {top3:.2f}")


for feats in (F, ["l_opprank"], ["spread"]):
    print("\n### features", feats)
    for s in range(2021, 2026):
        te, tr = h.season == s, (h.season != s) & (h.position == "DST")
        res = run.fit_offset(h[tr], feats, run.linpred(h[tr], lb))
        base = run.predict(h[te], lb)
        new = run.predict(h[te], run.with_residual(lb, res))
        print(s, "base", dst_metrics(h[te], base), "|| new", dst_metrics(h[te], new),
              {k: round(v, 2) for k, v in res.items()})
    tr = h.position == "DST"
    res = run.fit_offset(h[tr], feats, run.linpred(h[tr], lb))
    m = run.hasf(r)
    for w in (1, 2, 3):
        te = r.week == w
        rr = r[te]
        base = run.predict(rr, lb)
        new = run.predict(rr, run.with_residual(lb, res))
        mm = m[te]
        base[mm] = run.predict(rr[mm], lf)
        new[mm] = run.predict(rr[mm], run.with_residual(lf, res))
        print(f"2026 wk{w}", "base", dst_metrics(rr, base), "|| new", dst_metrics(rr, new))
    print("hist-fit coefs", {k: round(v, 3) for k, v in res.items()})
