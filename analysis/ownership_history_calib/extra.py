"""Follow-ups: real-shape facts from history (projection-free), DST-only metrics for the DST power,
mid x1.15, real top-player distribution (is a 60-65 cap structurally safe?)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run  # noqa: E402

h, r = run.load_hist(), run.load_2026()
lb, lf = run.om.load_artifact("dk"), run.om.load_artifact("dk", "_ffc")
ph = run.predict(h, lb)
p26 = run.predict(r, lb)
m = run.hasf(r)
p26[m] = run.predict(r[m], lf)

print("=== real top player per slate (history 2021-25 vs 2026) ===")
for lab, d in (("hist", h), ("2026", r)):
    mx = d.groupby("slate_id").own.max()
    print(lab, f"n={len(mx)} mean {mx.mean():.1f} p90 {mx.quantile(.9):.1f} max {mx.max():.1f} "
          f"share>60 {(mx > 60).mean():.3f} >65 {(mx > 65).mean():.3f}")
    print("   by season:", d.groupby("season").apply(lambda x: round(x.groupby('slate_id').own.max().mean(), 1)).to_dict())

print("\n=== real shape per slate (history by season, 2026): n10-20, n20+, tier totals non-DST, DST top ===")
for lab, d in list(h.groupby("season")) + [("2026", r)]:
    g = d.groupby("slate_id")
    nd = d[d.position != "DST"]
    t = pd.cut(nd.salary, [0, 5499, 6999, 99999], labels=["lo", "mid", "hi"])
    ts = nd.groupby([nd.slate_id, t], observed=False).own.sum().groupby(level=1, observed=False).mean()
    dd = d[d.position == "DST"]
    print(lab, f"n10-20 {g.own.apply(lambda x: ((x >= 10) & (x < 20)).sum()).mean():.1f} "
          f"n20+ {g.own.apply(lambda x: (x >= 20).sum()).mean():.1f} tiers " +
          " ".join(f"{k}:{v:.0f}" for k, v in ts.items()) +
          f" | DST top {dd.groupby('slate_id').own.max().mean():.1f} top2 "
          f"{dd.groupby('slate_id').own.apply(lambda x: x.nlargest(2).sum()).mean():.1f}")

print("\n=== DST-only metrics per fold: MAE, top-DST bias, rank corr (dst_t power) ===")
for lab, d, p in (("hist-liveBase", h, ph), ("2026-live", r, p26)):
    fold = d.season if lab.startswith("hist") else d.week
    for t in (1.0, 1.25, 1.5):
        pc = run.calib(d, p, dst_t=t)
        dd = d.assign(p=pc)[d.position == "DST"]
        out = []
        for k, x in dd.groupby(fold.loc[dd.index]):
            top = x.groupby("slate_id").apply(lambda z: z.loc[z.own.idxmax(), "p"] - z.own.max()).mean()
            # DST >= 10% real: bias
            c = x[x.own >= 10]
            out.append(f"{k}: mae {np.abs(x.p - x.own).mean():.2f} top {top:+.1f} b10+ {(c.p - c.own).mean():+.1f}")
        print(lab, f"t={t}", " | ".join(out))
    dd = d.assign(p=p)[d.position == "DST"].copy()
    dd["pq"] = dd.groupby("slate_id").salary.rank(pct=True)
    print(lab, "DST by salary quartile-in-slate (real/pred):",
          dd.groupby(pd.cut(dd.pq, [0, .25, .5, .75, 1])).apply(lambda x: f"{x.own.mean():.1f}/{x.p.mean():.1f}").to_dict())
    dd["orank"] = dd.groupby("slate_id").own.rank(ascending=False, method="first").clip(upper=5)
    print(lab, "DST by real-own rank (real/pred):",
          dd.groupby("orank").apply(lambda x: f"{x.own.mean():.1f}/{x.p.mean():.1f}").to_dict())
    mn = dd[dd.min_dst == 1]
    print(lab, f"min-price DST real {mn.own.mean():.1f} pred {mn.p.mean():.1f} n={len(mn)}; share of slates where min DST is real top-3 "
          f"{(mn.orank <= 3).mean():.2f}")

print("\n=== mid x1.15 (2026 live, per week) ===")
for kw in ({"mid": 1.15}, {"mid": 1.15, "cap": 65}, {"dst_t": 1.25, "cap": 65}):
    pc = run.calib(r, p26, **kw)
    b = [run.metrics(r[r.week == w], p26[r.week == w]) for w in (1, 2, 3)]
    x = [run.metrics(r[r.week == w], pc[r.week == w]) for w in (1, 2, 3)]
    print(kw, " ".join(f"{k}:" + "/".join(f"{xx[k] - bb[k]:+.3f}" for xx, bb in zip(x, b))
                       for k in ("corr", "mae", "chalk_bias", "chalk_mae", "sub10_mae", "top10", "tier_abs")))
    ph2 = run.calib(h, ph, **kw)
    bh = [run.metrics(h[h.season == s], ph[h.season == s]) for s in range(2021, 2026)]
    xh = [run.metrics(h[h.season == s], ph2[h.season == s]) for s in range(2021, 2026)]
    print("   hist", " ".join(f"{k}:" + "/".join(f"{xx[k] - bb[k]:+.3f}" for xx, bb in zip(xh, bh))
                            for k in ("corr", "mae", "chalk_bias", "chalk_mae", "sub10_mae", "tier_abs")))

print("\n=== cheap WR/TE: does the field know something? (history, live base) ===")
d = h.assign(p=ph)
cw = d[d.cheap & d.position.isin(["WR", "TE"]) & (d.own >= 2)]
for s, x in cw.groupby("season"):
    print(s, f"n={len(x)} corr(pred-real, FP) {np.corrcoef(x.p - x.own, x.fpts)[0, 1]:+.3f} "
          f"corr(real, FP) {np.corrcoef(x.own, x.fpts)[0, 1]:+.3f} corr(pred, FP) {np.corrcoef(x.p, x.fpts)[0, 1]:+.3f} "
          f"corr(ourproj, FP) {np.corrcoef(x.final_projection, x.fpts)[0, 1]:+.3f}")
x = r.assign(p=p26)
x = x[x.cheap & x.position.isin(["WR", "TE"]) & (x.own >= 2) & x.fpts.notna()]
print("2026", f"n={len(x)} corr(pred-real, FP) {np.corrcoef(x.p - x.own, x.fpts)[0, 1]:+.3f} corr(real, FP) "
      f"{np.corrcoef(x.own, x.fpts)[0, 1]:+.3f} corr(pred, FP) {np.corrcoef(x.p, x.fpts)[0, 1]:+.3f} "
      f"corr(proj, FP) {np.corrcoef(x.final_projection, x.fpts)[0, 1]:+.3f}")
