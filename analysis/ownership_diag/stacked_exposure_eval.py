"""LOWO evaluation of stacked-exposure / team features on top of the
base+pub_val and +FFC baselines. Reads <scratch>/d_ffc.pkl and sexp.pkl."""
import sys, pickle
from pathlib import Path
import numpy as np, pandas as pd

REPO = Path(r"C:\Users\gmsco\Desktop\DFS_Optimizer")
sys.path.insert(0, str(REPO / "scripts"))
import ownership_model as om  # noqa
import fit_ownership_model as fom  # noqa
import ownership_heuristic as oh  # noqa

SCR = Path(r"C:\Users\gmsco\AppData\Local\Temp\claude\C--Users-gmsco-Desktop-DFS-Optimizer\36a97c4a-433e-4ff9-b857-c9a23bb65822\scratchpad")
OUT = Path(__file__).resolve().parent
B = oh.compute_position_slot_budgets("dk")
d = pd.read_pickle(SCR / "d_ffc.pkl").reset_index(drop=True)
sx = pickle.load(open(SCR / "sexp.pkl", "rb"))

# ---- features ------------------------------------------------------------
for s in ("qb1", "qb2", "qb1bb"):
    d[f"sexp_{s}"] = 0.0
d["team_qb_share"] = 0.0
for (sid, s), (e, q) in sx.items():
    m = d.slate_id == sid
    d.loc[m, f"sexp_{s}"] = d.loc[m, "player_id"].map(e).fillna(0.0)
    if s == "qb1":
        d.loc[m, "team_qb_share"] = d.loc[m, "team"].map(q).fillna(0.0)
for s in ("qb1", "qb2", "qb1bb"):
    d[f"l_sexp_{s}"] = om._logit(d[f"sexp_{s}"])


def teammate(col):
    mean, mx = np.zeros(len(d)), np.zeros(len(d))
    for (sid, t), g in d.groupby(["slate_id", "team"]):
        for i in g.index:
            o = g[(g.position != g.at[i, "position"]) & ~g.position.isin(list(om.DEFENSE_LABELS))][col]
            mean[d.index.get_loc(i)] = o.mean() if len(o) else 0.0
            mx[d.index.get_loc(i)] = o.max() if len(o) else 0.0
    return mean, mx


for col, tag in (("exposure", "u"), ("sexp_qb1", "s")):
    a, b = teammate(col)
    d[f"tm_mean_{tag}"], d[f"tm_max_{tag}"] = a / 10.0, b / 10.0
ts = d.drop_duplicates(["slate_id", "team"])
d["team_it_rank"] = d.groupby("slate_id").implied_total.rank(pct=True, method="dense")
d["game_ou_rank"] = d.groupby("slate_id").over_under.rank(pct=True, method="dense")

BASE = list(om.FEATURES)
FFC = BASE + list(om.FFC_FEATURES)
ADD = {
    "none": [],
    "sexp_qb1": ["l_sexp_qb1"], "sexp_qb2": ["l_sexp_qb2"], "sexp_qb1bb": ["l_sexp_qb1bb"],
    "qb_share": ["team_qb_share"],
    "tm_unstk": ["tm_mean_u", "tm_max_u"], "tm_stk": ["tm_mean_s", "tm_max_s"],
    "env": ["team_it_rank", "game_ou_rank"],
    "combo": ["l_sexp_qb1", "team_qb_share", "tm_mean_s", "tm_max_s", "team_it_rank", "game_ou_rank"],
}


def lowo(feats):
    p = pd.Series(0.0, index=d.index)
    for w in (1, 2):
        art = fom.fit(d[d.week != w], feats=feats)
        art["features"] = feats
        te = d[d.week == w]
        p.loc[te.index] = fom.predict_slates(te, art, B)
    return p


def met(g, c):
    m = (g.own > 5) | (g[c] > 5); e = g[c] - g.own; ch = g.own >= 20
    mm = g[m]
    return dict(corr=mm[c].corr(mm.own), mae=e[m].abs().mean(), chalk_bias=e[ch].mean(),
                chalk_hit=int((ch & (g[c] >= 10)).sum()), chalk_n=int(ch.sum()),
                miss12=int((m & (e.abs() > 12)).sum()), cheap_miss12=int((m & (e.abs() > 12) & (g.salary <= 4500)).sum()))


def eta2(g_all, c, nperm=1000, rng=np.random.default_rng(0)):
    """share of within-slate residual variance explained by team (meaningful cut)."""
    g = g_all[(g_all.own > 5) | (g_all[c] > 5)].copy()
    r = g[c] - g.own
    r = r - r.groupby(g.slate_id).transform("mean")
    def e2(teams):
        return (r.groupby([g.slate_id, teams]).transform("mean") ** 2).sum() / (r ** 2).sum()
    obs = e2(g.team.values)
    perm = []
    for _ in range(nperm):
        t = g.groupby("slate_id").team.transform(lambda x: rng.permutation(x.values))
        perm.append(e2(t.values))
    perm = np.array(perm)
    return obs, perm.mean(), (perm >= obs).mean()


rows, preds = [], {}
for bname, bf in (("base", BASE), ("ffc", FFC)):
    for a, extra in ADD.items():
        c = f"p_{bname}_{a}"
        d[c] = lowo(bf + extra)
        preds[c] = (bname, a)
        r = dict(baseline=bname, add=a, slate="POOLED", **met(d, c))
        r["eta2"], r["eta2_perm"], r["eta2_p"] = eta2(d, c)
        rows.append(r)
        for sid, g in d.groupby("slate_id"):
            rows.append(dict(baseline=bname, add=a, slate=sid[11:25], **met(g, c)))
        for w, g in d.groupby("week"):
            rows.append(dict(baseline=bname, add=a, slate=f"week{w}", **met(g, c)))
R = pd.DataFrame(rows)

# paired deltas + bootstrap (players resampled within slate; ignores within-week correlation)
rng = np.random.default_rng(1)
idx_by_slate = [g.index.values for _, g in d.groupby("slate_id")]
boot = [np.concatenate([rng.choice(ix, len(ix)) for ix in idx_by_slate]) for _ in range(300)]
summ = []
for c, (bname, a) in preds.items():
    if a == "none":
        continue
    b0 = f"p_{bname}_none"
    P = R[(R.baseline == bname)]
    ps = P[P["add"] == a].set_index("slate"); p0 = P[P["add"] == "none"].set_index("slate")
    sl = [s for s in ps.index if s.startswith("wk")]
    dc = (ps.loc[sl, "corr"] - p0.loc[sl, "corr"]); dm = (ps.loc[sl, "mae"] - p0.loc[sl, "mae"])
    bd = []
    for ix in boot:
        g = d.loc[ix]
        bd.append(met(g, c)["corr"] - met(g, b0)["corr"])
    lo, hi = np.percentile(bd, [2.5, 97.5])
    summ.append(dict(baseline=bname, add=a,
                     d_corr=ps.at["POOLED", "corr"] - p0.at["POOLED", "corr"], ci_lo=lo, ci_hi=hi,
                     d_mae=ps.at["POOLED", "mae"] - p0.at["POOLED", "mae"],
                     slates_corr_up=int((dc > 0).sum()), slates_mae_down=int((dm < 0).sum()),
                     wk1_dcorr=ps.at["week1", "corr"] - p0.at["week1", "corr"],
                     wk2_dcorr=ps.at["week2", "corr"] - p0.at["week2", "corr"],
                     wk1_dmae=ps.at["week1", "mae"] - p0.at["week1", "mae"],
                     wk2_dmae=ps.at["week2", "mae"] - p0.at["week2", "mae"]))
S = pd.DataFrame(summ)
R.to_csv(OUT / "stacked_exposure_results.csv", index=False, float_format="%.4f")
S.to_csv(OUT / "stacked_exposure_deltas.csv", index=False, float_format="%.4f")
pd.set_option("display.width", 250)
print(R[R.slate == "POOLED"].round(3).to_string(index=False))
print(S.round(3).to_string(index=False))
print("feature corr with l_exp:", d[["l_exp", "l_sexp_qb1", "l_sexp_qb2", "l_sexp_qb1bb"]].corr().round(2).iloc[0].to_dict())
