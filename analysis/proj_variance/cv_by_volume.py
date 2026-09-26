"""Measured yards-ratio CV by volume bucket (research; public nflverse only)."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "scripts")
import fit_statline_variance as f
df = f.load_history(list(range(2018, 2026)))
for pos, comps in f.COMPONENTS.items():
    for name, vs, ys, ts in comps:
        d = df[(df.position == pos) & (df[vs] > 0)]
        own = d.groupby(["player_id", "season"]).agg(y=(ys, "sum"), v=(vs, "sum"), n=(ys, "size"))
        own = own[own.n >= 6]; own["rate"] = own.y / own.v
        m = d.merge(own[["rate"]], left_on=["player_id", "season"], right_index=True)
        ratio = m[ys] / (m[vs] * m.rate).replace(0, np.nan)
        ok = ratio.notna() & (ratio > 0) & (ratio < 6)
        m = m[ok]; r = ratio[ok]
        b = pd.qcut(m[vs], 5, duplicates="drop")
        print(pos, name, "all cv %.3f volw cv %.3f" % (r.std(), np.sqrt(np.average((r - 1) ** 2, weights=m[vs]))),
              r.groupby(b, observed=True).std().round(3).to_dict())
