"""6.5k+ skill-only salary pull (fit only on 6.5k+). LOSO 2021-25, 2026 held out. Direction split. FC-derived, local."""
import io, contextlib, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
with contextlib.redirect_stdout(io.StringIO()):
    import allweeks as A
P = A.Pi; LAM = A.LAM
for lab, cond in [("6.5k+", lambda d: d.salary >= 6500), ("6k+", lambda d: d.salary >= 6000), ("7k+", lambda d: d.salary >= 7000)]:
    rows = []
    for s in [2021, 2022, 2023, 2024, 2025, 2026]:
        tr = P[(P.season != s) & (P.season <= 2025) & cond(P)]; te = P[P.season == s].copy()
        a, w = A.fit(tr); m = cond(te)
        te["F"] = te.E; te.loc[m, "F"] = (te.E + a + w * te.d)[m].clip(lower=0)
        g = te[m]; sk = te.season * 100 + te.week
        top = lambda c: te.assign(sk=sk).groupby("sk").apply(lambda x: x.nlargest(24, c).act.mean()).mean()
        up, dn = g[g.F > g.E], g[g.F < g.E]
        rows.append(dict(season=s, a=a, w=w, n=len(g), mae0=(g.E - g.act).abs().mean(), mae1=(g.F - g.act).abs().mean(),
                         bias0=(g.E - g.act).mean(), bias1=(g.F - g.act).mean(), n_up=len(up), up_err0=(up.E - up.act).mean(),
                         up_err1=(up.F - up.act).mean(), n_dn=len(dn), dn_err0=(dn.E - dn.act).mean(), dn_err1=(dn.F - dn.act).mean(),
                         top24_0=top("E"), top24_1=top("F"),
                         rb=(lambda x: (x.F - x.act).abs().mean() - (x.E - x.act).abs().mean())(g[g.position == "RB"]),
                         wr=(lambda x: (x.F - x.act).abs().mean() - (x.E - x.act).abs().mean())(g[g.position == "WR"]),
                         te=(lambda x: (x.F - x.act).abs().mean() - (x.E - x.act).abs().mean())(g[g.position == "TE"])))
    D = pd.DataFrame(rows); pd.set_option("display.width", 250)
    print(f"== {lab} only ==  (up/dn = players the pull raises/lowers; err = mean proj - actual)")
    print(D.round(3).to_string(index=False))
    tr = P[(P.season <= 2025) & cond(P)]; print("final fit 2021-25 (a,w):", np.round(A.fit(tr), 3))
