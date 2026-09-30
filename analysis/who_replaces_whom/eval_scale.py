"""LOSO shrink factor k on the real-pipeline delta (on = off + k*delta), fit on the other seasons' rebuilt weeks."""
import numpy as np, pandas as pd, runpy, io, contextlib
with contextlib.redirect_stdout(io.StringIO()): g = runpy.run_path("eval_hist.py")
x = g["act_x"].copy(); x["e"] = x.act - x.off
for nm, sub in [("all affected", x), ("base>=8 only", x[x.off >= 8]), ("wk<=17", x[x.week <= 17])]:
    out = []
    for s in sorted(sub.season.unique()):
        tr, te = sub[sub.season != s], sub[sub.season == s]
        k = (tr.e * tr.wrw_delta_pts).sum() / (tr.wrw_delta_pts ** 2).sum()
        out.append(te.assign(k=k, p=te.off + k * te.wrw_delta_pts))
    o = pd.concat(out); e0, e1 = o.act - o.off, o.act - o.p
    better = sum(np.sqrt(((d.act-d.p)**2).mean()) < np.sqrt(((d.act-d.off)**2).mean()) for _, d in o.groupby("season"))
    print(f"{nm:14s} n={len(o)} k(LOSO) {o.k.min():.2f}-{o.k.max():.2f} | off RMSE {np.sqrt((e0**2).mean()):.3f} MAE {e0.abs().mean():.3f} bias {e0.mean():+.2f}"
          f" | shrunk RMSE {np.sqrt((e1**2).mean()):.3f} MAE {e1.abs().mean():.3f} bias {e1.mean():+.2f} | seasons better {better}/{o.season.nunique()}")
