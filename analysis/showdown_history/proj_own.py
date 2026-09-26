"""Player-level projection-quality and ownership analyses (LOSO). Prints aggregate tables only.
Run: python analysis/showdown_history/proj_own.py > data/fc_history/derived/showdown/proj_own_out.txt"""
import warnings
from pathlib import Path
import numpy as np, pandas as pd
from numpy.linalg import solve
warnings.filterwarnings("ignore")
R = Path(__file__).resolve().parents[2]; D = R / "data/fc_history/derived/showdown"
df = pd.read_parquet(D / "players.parquet")
pd.set_option("display.width", 220); pd.set_option("display.max_columns", 30)


def rmse(a, b): return float(np.sqrt(np.mean((a - b) ** 2)))


df["tier"] = pd.cut(df.sal, [-1, 1000, 3000, 5000, 7000, 9000, 20000], labels=["<=1k", "1-3k", "3-5k", "5-7k", "7-9k", "9k+"])
df["prank"] = df.groupby("slate").proj.rank(ascending=False, method="first")
print("=== PROJECTION: FC Proj vs actual (rows with proj>0) ===")
p = df[df.proj > 0].copy()
z = df[df.proj <= 0]
print("rows", len(p), "of", len(df), "; proj==0 rows mean act", round(z.act.mean(), 2), "max", z.act.max(),
      "share of proj0 with act>=10:", round((z.act >= 10).mean(), 3), "proj0 with flex_own>=5:", int((z.flex_own >= 5).sum()))
t = p.groupby("pos").apply(lambda x: pd.Series(dict(n=len(x), proj=x.proj.mean(), act=x.act.mean(), bias=(x.act - x.proj).mean(),
    corr=np.corrcoef(x.proj, x.act)[0, 1], corr_sal=np.corrcoef(x.sal, x.act)[0, 1], sd_act=x.act.std(), rmse=rmse(x.act, x.proj))))
print(t.round(2))
print(p.groupby("tier").apply(lambda x: pd.Series(dict(n=len(x), proj=x.proj.mean(), act=x.act.mean(), bias=(x.act - x.proj).mean()))).round(2))
print("by year:")
print(p.groupby("year").apply(lambda x: pd.Series(dict(n=len(x), bias=(x.act - x.proj).mean(), corr=np.corrcoef(x.proj, x.act)[0, 1]))).round(3))
print("proj-rank within slate (1=top) bias:")
p["prk"] = pd.cut(p.prank, [0, 1, 3, 6, 10, 40])
print(p.groupby("prk").apply(lambda x: pd.Series(dict(n=len(x), proj=x.proj.mean(), act=x.act.mean(), bias=(x.act - x.proj).mean(),
                                                    se=(x.act - x.proj).std() / np.sqrt(len(x))))).round(2))
print("top-proj skill players (QB/RB/WR/TE, prank<=6) bias by year:")
print(p[(p.prank <= 6) & p.pos.isin(["QB", "RB", "WR", "TE"])].groupby("year").apply(lambda x: pd.Series(dict(n=len(x), bias=(x.act - x.proj).mean(), se=(x.act - x.proj).std() / np.sqrt(len(x))))).round(2))
print("calibration deciles:")
p["dec"] = pd.qcut(p.proj, 10, duplicates="drop")
print(p.groupby("dec").apply(lambda x: pd.Series(dict(n=len(x), proj=x.proj.mean(), act=x.act.mean(), sd=x.act.std()))).round(2))


def design(x, kind):
    cols = {"proj": [x.proj], "sal": [x.sal / 1000], "both": [x.proj, x.sal / 1000], "both_vegas": [x.proj, x.sal / 1000, x.tv]}[kind]
    return np.c_[np.ones(len(x)), np.column_stack(cols)]


res = []
for kind in ("raw", "proj", "sal", "both", "both_vegas"):
    pred = pd.Series(np.nan, index=p.index)
    for s in p.slate.unique():
        tr, te = p[p.slate != s], p[p.slate == s]
        for pos in p.pos.unique():
            a, b = tr[tr.pos == pos], te[te.pos == pos]
            if len(b) == 0:
                continue
            if kind == "raw":
                pred[b.index] = b.proj
                continue
            W = np.sqrt(np.where(a.year == 2025, 2.0, 1.0))[:, None]
            beta = np.linalg.lstsq(design(a, kind) * W, a.act.to_numpy() * W[:, 0], rcond=None)[0]
            pred[b.index] = design(b, kind) @ beta
    p["pred_" + kind] = pred
    for grp, x in [("ALL", p), ("2025", p[p.year == 2025])] + [(q, p[p.pos == q]) for q in ["QB", "RB", "WR", "TE", "K", "DST"]]:
        wsc = x.groupby("slate").apply(lambda y: y[["pred_" + kind, "act"]].corr(method="spearman").iloc[0, 1]).mean()
        res.append(dict(model=kind, grp=grp, rmse=rmse(x.act, x["pred_" + kind]), within_slate_spearman=wsc))
r = pd.DataFrame(res).pivot(index="grp", columns="model", values=["rmse", "within_slate_spearman"])
print("LOSO (fit per pos, 2025 weighted 2x):")
print(r.round(3))
sl = p.slate.unique(); rng = np.random.default_rng(0)


def boot(col_a, col_b, x=p):
    e = x.assign(d=(x.act - x[col_a]) ** 2 - (x.act - x[col_b]) ** 2).groupby("slate").d.agg(["sum", "count"])
    dd = []
    for _ in range(2000):
        b = e.loc[rng.choice(e.index, len(e))]
        dd.append(b["sum"].sum() / b["count"].sum())
    return np.round(np.percentile(dd, [5, 50, 95]), 3)


print("MSE(recal proj) - MSE(proj+sal) boot 90% CI:", boot("pred_proj", "pred_both"))
print("MSE(raw) - MSE(recal proj) CI:", boot("proj", "pred_proj"))
print("MSE(sal) - MSE(recal proj) CI:", boot("pred_sal", "pred_proj"))
print("same, 2025 only: recal-vs-both", boot("pred_proj", "pred_both", p[p.year == 2025]), "raw-vs-recal", boot("proj", "pred_proj", p[p.year == 2025]))
for kind in ("proj", "both"):
    coef = {}
    for pos in p.pos.unique():
        a = p[p.pos == pos]
        coef[pos] = np.linalg.lstsq(design(a, kind), a.act.to_numpy(), rcond=None)[0].round(3).tolist()
    print(f"full-sample act ~ 1 + {kind}:", coef)
p["res"] = p.act - p.proj
print("residual by pos x fav:")
print(p.pivot_table(index="pos", columns="fav", values="res", aggfunc="mean").round(2))
print("share act > FC ceiling by pos:", p.groupby("pos").apply(lambda x: (x.act > x.ceil).mean()).round(3).to_dict())
print("share act < FC floor by pos:", p.groupby("pos").apply(lambda x: (x.act < x.floor).mean()).round(3).to_dict())

print("\n=== OWNERSHIP ===")
g = df.copy()
g["cpt_share"] = g.cpt_own / g.groupby("slate").cpt_own.transform("sum") * 100
ns = g.slate.nunique()
print("CPT own by pos (share of CPT slots, avg per slate):", (g.groupby("pos").cpt_share.sum() / ns).round(1).to_dict())
print("FLEX own by pos (sum per slate):", (g.groupby("pos").flex_own.sum() / ns).round(1).to_dict())
mx = g.groupby("slate").apply(lambda x: pd.Series(dict(max_cpt=x.cpt_own.max(), top3_cpt=x.cpt_own.nlargest(3).sum(), max_flex=x.flex_own.max(),
     top_proj_cpt_own=x.loc[x.proj.idxmax(), "cpt_own"], chalk_cpt_pos=x.loc[x.cpt_own.idxmax(), "pos"], year=x.year.iloc[0],
     chalk_is_topproj=x.cpt_own.idxmax() == x.proj.idxmax())))
print("chalk concentration by year:")
print(mx.groupby("year")[["max_cpt", "top3_cpt", "max_flex", "top_proj_cpt_own"]].mean().round(1))
print("chalk CPT position counts:", mx.chalk_cpt_pos.value_counts().to_dict(), " chalk CPT == top-proj player share:", round(mx.chalk_is_topproj.mean(), 2))
print("cpt/flex own ratio by pos (players with flex_own>=5):", g[g.flex_own >= 5].assign(r=lambda x: x.cpt_own / x.flex_own).groupby("pos").r.median().round(3).to_dict())
print("K/DST mean own:", g[g.pos.isin(["K", "DST"])].groupby("pos")[["flex_own", "cpt_own"]].mean().round(2).to_dict())
print("cheap (sal<=1000) own by proj band:")
c = g[g.sal <= 1000]
print(c.groupby(pd.cut(c.proj, [-1, 0, 2, 5, 50]))[["flex_own", "cpt_own"]].agg(["mean", "count"]).round(2))
g["dstcheap"] = (g.groupby(["slate", "pos"]).sal.rank(method="first") == 1)
print("DST cheap(True) vs expensive:", g[g.pos == "DST"].groupby("dstcheap")[["flex_own", "cpt_own", "act", "proj", "sal"]].mean().round(2).to_dict())
print("K fav vs dog:", g[g.pos == "K"].groupby("fav")[["flex_own", "cpt_own", "act", "proj"]].mean().round(2).to_dict())
# per-pos: CPT ownership share vs actual CPT-worthiness (share of slates where the top 1.5x-score player is that pos) -> in sim hindsight

g["pshare"] = g.proj / g.groupby("slate").proj.transform("max"); g["salk"] = g.sal / 1000
g["val"] = g.proj / np.maximum(g.salk, 0.2); g["lprank"] = np.log(g.prank)
for q in ["QB", "RB", "WR", "TE", "K", "DST"]:
    g["is" + q] = (g.pos == q).astype(float)
g["isMin"] = (g.sal <= 1000).astype(float); g["proj0"] = (g.proj <= 0).astype(float)
FEATS = {"projonly": ["pshare", "lprank"],
         "full": ["pshare", "lprank", "salk", "val", "isQB", "isRB", "isTE", "isK", "isDST", "isMin", "proj0", "fav", "spread", "total"]}


def lg(o, cap):
    x = np.clip(o / cap, 0.003, 0.997); return np.log(x / (1 - x))


def ridge(X, y, lam=1.0):
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Z = np.c_[np.ones(len(X)), (X - mu) / sd]; P = np.eye(Z.shape[1]) * lam; P[0, 0] = 0
    w = solve(Z.T @ Z + P, Z.T @ y)
    return (lambda Xn: np.c_[np.ones(len(Xn)), (Xn - mu) / sd] @ w), w


def waterfill(r, b, cap):
    out = np.zeros(len(r)); free = r > 0; rem = b
    for _ in range(30):
        tt = r[free].sum()
        if tt <= 0:
            break
        tr = np.where(free, r / tt * rem, 0.0); over = free & (tr > cap)
        if not over.any():
            return np.where(free, tr, out)
        out = np.where(over, cap, out); rem -= cap * over.sum(); free &= ~over
    return out


try:
    prod = pd.read_parquet(D / "prod_own_pred.parquet")
except Exception:
    prod = None
out = []
for role, cap, bud, th in (("cpt_own", 60, 100, 8), ("flex_own", 75, 500, 20)):
    for fname, fl in FEATS.items():
        pred = pd.Series(np.nan, index=g.index)
        for s in g.slate.unique():
            tr, te = g[g.slate != s], g[g.slate == s]
            wt = np.where(tr.year == 2025, 2, 1)
            f, _ = ridge(np.repeat(tr[fl].to_numpy(float), wt, 0), np.repeat(lg(tr[role].to_numpy(), cap), wt))
            raw = cap / (1 + np.exp(-f(te[fl].to_numpy(float))))
            pred[te.index] = waterfill(raw, bud, cap)
        g[f"pred_{role}_{fname}"] = pred
    if prod is not None:
        rr = "CPT" if role == "cpt_own" else "FLEX"
        pp = prod[prod.roster_role == rr]
        g[f"pred_{role}_prod"] = np.nan
        for s, x in g.groupby("slate"):
            q = pp[pp.slate == s].pred.to_numpy()
            if len(q) == len(x):
                g.loc[x.index, f"pred_{role}_prod"] = q
    for m in [c for c in g.columns if c.startswith(f"pred_{role}_")]:
        for yr, x in [("ALL", g), ("2025", g[g.year == 2025])]:
            x = x[x[m].notna()]
            a, pr = x[role].to_numpy(), x[m].to_numpy(); ch = a >= th
            out.append(dict(role=role, model=m.split("_")[-1], yr=yr, n_slates=x.slate.nunique(), corr=np.corrcoef(a, pr)[0, 1], mae=np.abs(a - pr).mean(),
                            chalk_n=int(ch.sum()), chalk_mae=np.abs(a - pr)[ch].mean(), chalk_bias=(pr - a)[ch].mean(),
                            top1_hit=x.groupby("slate").apply(lambda y: y[role].idxmax() == y[m].idxmax()).mean()))
print(pd.DataFrame(out).round(3).to_string())
for role in ("cpt_own", "flex_own"):
    for m in ("full", "prod"):
        c = f"pred_{role}_{m}"
        if c not in g:
            continue
        print(role, m, "bias (pred-actual) by pos:", g.groupby("pos").apply(lambda x: (x[c] - x[role]).mean()).round(2).to_dict())
        print(role, m, "bias by salary tier:", g.groupby("tier").apply(lambda x: (x[c] - x[role]).mean()).round(2).to_dict())
        bands = [-1, 2, 5, 10, 20, 35, 100]
        print(role, m, "count actual band:", pd.cut(g[role], bands).value_counts().sort_index().values.tolist(),
              "pred band:", pd.cut(g[c], bands).value_counts().sort_index().values.tolist(), "bands", bands)
for role, cap in (("cpt_own", 60), ("flex_own", 75)):
    fl = FEATS["full"]
    _, w = ridge(g[fl].to_numpy(float), lg(g[role].to_numpy(), cap))
    print(role, "std coefs (full, all data):", dict(zip(fl, w[1:].round(2))))
pp = g[g.proj > 0]; r0 = []; r1 = []
for s in pp.slate.unique():
    tr, te = pp[pp.slate != s], pp[pp.slate == s]
    for cols, lst in ((["proj"], r0), (["proj", "flex_own"], r1)):
        b = np.linalg.lstsq(np.c_[np.ones(len(tr)), tr[cols]], tr.act, rcond=None)[0]
        lst.append(((te.act - np.c_[np.ones(len(te)), te[cols]] @ b) ** 2).sum())
print("LOSO SSE act~proj vs act~proj+flex_own:", round(sum(r0)), round(sum(r1)))
g.to_parquet(D / "players_with_preds.parquet")
