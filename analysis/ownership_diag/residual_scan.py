"""Task A: failure map + candidate-feature residual scan + incremental LOWO."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
from math import erfc, sqrt
def spearmanr(x, y):
    x=pd.Series(x).rank().to_numpy(); y=pd.Series(y).rank().to_numpy()
    r=np.corrcoef(x,y)[0,1]; z=abs(r)*sqrt(len(x)-1)
    return r, erfc(z/sqrt(2))

sys.path.insert(0, r"C:\Users\gmsco\Desktop\DFS_Optimizer\scripts")
sys.path.insert(0, str(Path(__file__).parent))
import ownership_model as om, fit_ownership_model as fom, ownership_heuristic as oh
from features import SCR, CANDIDATES

d = pd.read_pickle(SCR / "diag_frame.pkl")
B = oh.compute_position_slot_budgets("dk")
M = (d.own > 5) | (d.lowo > 5)


def metrics(own, p):
    m = (own > 5) | (p > 5); e = p - own; c = own >= 20
    return dict(corr_m=round(np.corrcoef(p[m], own[m])[0, 1], 3), mae_m=round(e[m].abs().mean(), 2),
                chalk_bias=round(e[c].mean(), 1), chalk_mae=round(e[c].abs().mean(), 1),
                chalk_ge10=f"{int(((p >= 10) & c).sum())}/{int(c.sum())}",
                miss12=int((e < -12).sum()), cheap_miss=int(((e < -12) & (d.loc[own.index, 'salary'] <= 5500)).sum()),
                over12=int((e > 12).sum()))


# ---------- failure map ----------
fm = d[(d.err.abs() > 10)].copy()
fm["dir"] = np.where(fm.err < 0, "UNDER", "OVER")
cols = ["slate_id", "player_name", "position", "salary", "sal_chg", "dk_avg", "final_projection", "prev_fpts",
        "vacated", "imp", "rank_gap", "own", "lowo", "err"]
fm = fm.sort_values("err")[["dir"] + cols]
fm["slate_id"] = fm.slate_id.str.replace("dk_classic_", "").str[:13]
fm.round(1).to_csv(Path(__file__).parent / "failure_map.csv", index=False)
print("failure map n:", fm.dir.value_counts().to_dict())
comp = []
for f in CANDIDATES + ["salary", "final_projection", "exposure", "heur"]:
    comp.append(dict(feature=f, under_med=d.loc[d.err < -10, f].median(), over_med=d.loc[d.err > 10, f].median(),
                     ok_med=d.loc[M & (d.err.abs() <= 10), f].median()))
comp = pd.DataFrame(comp).round(2); print(comp.to_string())
comp.to_csv(Path(__file__).parent / "failure_medians.csv", index=False)

# ---------- residual rank-correlation per week (meaningful cut) ----------
rows = []
for f in CANDIDATES:
    r = {"feature": f}
    for w in (1, 2):
        g = d[M & (d.week == w)].dropna(subset=[f])
        if g[f].nunique() < 3:
            r[f"rho_w{w}"] = np.nan; r[f"p_w{w}"] = np.nan; continue
        rho, p = spearmanr(g[f], g.resid)
        r[f"rho_w{w}"], r[f"p_w{w}"] = rho, p
    g = d[M].dropna(subset=[f]); rho, p = spearmanr(g[f], g.resid)
    r["rho_pool"], r["p_pool"], r["n"] = rho, p, len(g)
    rows.append(r)
rs = pd.DataFrame(rows)
rs["p_bonf"] = (rs.p_pool * len(CANDIDATES)).clip(upper=1)
rs["same_sign"] = np.sign(rs.rho_w1) == np.sign(rs.rho_w2)
rs = rs.sort_values("p_pool"); print(rs.round(3).to_string())
rs.round(4).to_csv(Path(__file__).parent / "residual_scan.csv", index=False)


# ---------- incremental LOWO (add one feature to layered model) ----------
def lowo(feats, df=d, ridge=1.0):
    pred = pd.Series(0.0, index=df.index); old = om.FEATURES
    for w in (1, 2):
        tr, te = df[df.week != w], df[df.week == w]
        om.FEATURES = feats
        try:
            art = fom.fit(tr, ridge); pred.loc[te.index] = fom.predict_slates(te, art, B)
        finally:
            om.FEATURES = old
    return pred


base = lowo(list(om.FEATURES))
print("base", metrics(d.own, base))
inc = [dict(feature="(base)", **metrics(d.own, base))]
for f in CANDIDATES:
    if f in ("prev_opps",):  # wk2-only, can't train on wk1 -> skip in LOWO
        continue
    d[f + "_z"] = d[f].fillna(0.0)
    p = lowo(list(om.FEATURES) + [f + "_z"])
    inc.append(dict(feature=f, **metrics(d.own, p)))
inc = pd.DataFrame(inc); print(inc.to_string())
inc.to_csv(Path(__file__).parent / "incremental_lowo.csv", index=False)
