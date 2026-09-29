"""A. Projection head-to-head: OURS vs FC vs actual DK points (no FC data in this file).
Input: data/fc_history/derived/model_vs_fc/frame.parquet (build.py). Output: proj_h2h_out.txt next to this script
(aggregates only) and data/fc_history/derived/model_vs_fc/proj_*.csv.
Cuts: SKILL rows where max(fc, ours) > 8 ("relevant"); ACTIVE = also both > 0 (removes inactive zero-outs,
isolating skill from inactive/news knowledge). DST: all rows.
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
from scipy import stats

R = Path(__file__).resolve().parents[2]
OUT = R / "data/fc_history/derived/model_vs_fc"
LOG = open(OUT / "proj_h2h_out.txt", "w")
def P(*a):
    s = " ".join(str(x) for x in a); print(s); LOG.write(s + "\n")
rng = np.random.default_rng(11)

J = pd.read_parquet(OUT / "frame.parquet")
J = J[J.act.notna() & J.fc.notna() & J.ours.notna()].copy()
J["cell"] = J.slate.astype(str) + "_" + J.pos
J["mx"] = J[["fc", "ours"]].max(axis=1)
SK = J[(J.pos != "DST") & (J.mx > 8)].copy()
ACT = SK[(SK.fc > 0) & (SK.ours > 0)].copy()
DST = J[J.pos == "DST"].copy()


def within_spear(d, c):
    g = pd.DataFrame({"c": d.cell.values, "x": d.groupby("cell")[c].rank().values, "y": d.groupby("cell").act.rank().values})
    gm = g.groupby("c")
    g["xd"] = g.x - gm.x.transform("mean"); g["yd"] = g.y - gm.y.transform("mean")
    a = g.assign(xy=g.xd * g.yd, xx=g.xd ** 2, yy=g.yd ** 2).groupby("c")[["xy", "xx", "yy"]].sum()
    n = gm.size(); r = a.xy / np.sqrt(a.xx * a.yy)
    return r[(n >= 5) & (a.xx > 0) & (a.yy > 0)].mean()


def topn(d, c, n, value=False):
    key = d[c] / d.salary * 1000 if value else d[c]
    rk = key.groupby(d.cell).rank(ascending=False, method="first")
    sel = d[rk <= n]
    tgt = sel.act / sel.salary * 1000 if value else sel.act
    return tgt.groupby(sel.cell).mean().mean()


def exclusive(d, n):
    """mean actual of players in ours-topN not in fc-topN, and vice versa (per cell, pooled)."""
    ro = d.ours.groupby(d.cell).rank(ascending=False, method="first") <= n
    rf = d.fc.groupby(d.cell).rank(ascending=False, method="first") <= n
    return d.act[ro & ~rf].mean(), d.act[rf & ~ro].mean(), int((ro & ~rf).sum())


def met(d, c):
    e = d[c] - d.act
    return dict(n=len(d), bias=e.mean(), MAE=e.abs().mean(), RMSE=np.sqrt((e ** 2).mean()),
                corr=d[c].corr(d.act), spear_slate=within_spear(d, c),
                slope=np.polyfit(d[c], d.act, 1)[0] if d[c].std() > 0 else np.nan,
                top10=topn(d, c, 10), top20=topn(d, c, 20), val10=topn(d, c, 10, True))


def table(d, by, title):
    rows = []
    for k, g in (d.groupby(by, observed=True) if by else [("all", d)]):
        if len(g) < 20:
            continue
        for c, lab in [("fc", "FC"), ("ours", "OURS")]:
            m = met(g, c); m.update(slice=k, model=lab); rows.append(m)
    t = pd.DataFrame(rows).set_index(["slice", "model"])
    P(f"\n== {title}"); P(t.round(3).to_string()); return t


def boot(d, keys=("MAE", "RMSE", "spear_slate", "top10", "top20", "val10"), B=300, by_slate=True):
    obs = {k: met(d, "fc")[k] - met(d, "ours")[k] for k in keys}
    per = {s: g for s, g in d.groupby("slate")}; sl = list(per)
    res = {k: [] for k in keys}
    for i in range(B):
        if by_slate:
            g = pd.concat([per[s].assign(cell=per[s].cell + f"#{j}") for j, s in enumerate(rng.choice(sl, len(sl)))])
        else:  # 2026: resample players within slate-position cells
            idx = np.concatenate([rng.choice(ix, len(ix)) for ix in d.groupby("cell").indices.values()])
            g = d.iloc[idx]
        mf, mo = met(g, "fc"), met(g, "ours")
        for k in keys:
            res[k].append(mf[k] - mo[k])
    return {k: (obs[k], *np.nanpercentile(res[k], [2.5, 97.5])) for k in keys}


def show_boot(d, label, by_slate=True):
    b = boot(d, by_slate=by_slate, B=150)
    P(f"  {label:34s} " + " | ".join(f"{k} {v[0]:+.2f} [{v[1]:+.2f},{v[2]:+.2f}]" for k, v in b.items()))
    return b


for reg, lab in [("hist", "HISTORY 2021-25 (ours = regenerated, NO props/injuries/depth/weather -> handicapped)"),
                 ("prod2026", "2026 wk1-2 MAIN (ours = real pre-lock production file; FAIR test, 2 slates)")]:
    s, a, dd = SK[SK.regime == reg], ACT[ACT.regime == reg], DST[DST.regime == reg]
    P("\n" + "#" * 110 + f"\n# {lab}\n# relevant skill rows {len(s)}, active {len(a)}, DST {len(dd)}, slates {s.slate.nunique()}")
    table(s, None, "skill, relevant (max>8) -- includes inactive knowledge")
    table(a, None, "skill, ACTIVE (both>0) -- pure projection skill")
    table(a, "pos", "by position (ACTIVE)")
    table(dd, None, "DST (all)")
    table(a, "tier", "by salary band (ACTIVE skill)")
    table(a[a.pos.isin(["WR", "TE"])], "tier", "WR+TE by salary band (ACTIVE)")
    if reg == "hist":
        table(a, "season", "by season (ACTIVE)")
    P("\n  top-N exclusive picks (ACTIVE): mean actual of ours-only picks vs FC-only picks")
    for p in ["QB", "RB", "WR", "TE"]:
        for n in (10, 20):
            o, f, k = exclusive(a[a.pos == p], n); P(f"    {p} top{n}: ours-only {o:.2f} vs FC-only {f:.2f} (n ours-only {k})")
    o, f, k = exclusive(dd, 5); P(f"    DST top5: ours-only {o:.2f} vs FC-only {f:.2f} (n {k})")
    P(f"\n  FC minus OURS, 95% CI ({'slate-cluster bootstrap' if reg == 'hist' else 'player bootstrap within slate-pos (only 2 slates)'}); "
      "negative MAE/RMSE = FC better; positive spear/top = FC better")
    bs = reg == "hist"
    show_boot(s, "skill relevant", bs); show_boot(a, "skill ACTIVE", bs)
    for p in ["QB", "RB", "WR", "TE"]:
        show_boot(a[a.pos == p], f"{p} ACTIVE", bs)
    for t in a.tier.cat.categories:
        show_boot(a[a.tier == t], f"band {t} ACTIVE", bs)
        show_boot(a[(a.tier == t) & a.pos.isin(["WR", "TE"])], f"WR+TE {t} ACTIVE", bs)
    show_boot(dd, "DST", bs)

# inactive knowledge: who zeros scratches
P("\n== Inactive knowledge (skill, max>8): rows where one model is 0")
for reg in ["hist", "prod2026"]:
    s = SK[SK.regime == reg]
    P(f"  {reg}: FC=0 & ours>8: n={((s.fc == 0) & (s.ours > 8)).sum()} mean act {s[(s.fc == 0) & (s.ours > 8)].act.mean():.2f} | "
      f"ours=0 & FC>8: n={((s.ours == 0) & (s.fc > 8)).sum()} mean act {s[(s.ours == 0) & (s.fc > 8)].act.mean():.2f}")
SK.to_parquet(OUT / "proj_skill_rows.parquet")
LOG.close()
