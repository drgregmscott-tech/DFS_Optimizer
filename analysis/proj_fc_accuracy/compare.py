"""FC projection vs OUR projection accuracy (research only; contains no FC data).

Inputs (gitignored, FC-derived):  data/fc_history/derived/fc_master_mapped.csv,
  data/fc_history/derived/ourproj/proj_*.csv (regenerated leak-controlled projections, run_ourproj.py),
  analysis/proj_recheck/guarded_accuracy_frame.csv (2026 wk1-2 guarded production rebuild: OLD / FIX).
Outputs: data/fc_history/derived/proj_fc_accuracy/*.csv + report.txt (gitignored).
"""
import glob, os, sys
import numpy as np, pandas as pd
from scipy import stats

R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(R, "data/fc_history/derived/proj_fc_accuracy")
os.makedirs(OUT, exist_ok=True)
CUT = os.environ.get("CUT", "max8")  # max8 | active (both>0 and max>8: removes FC inactive zero-outs)
LOG = open(os.path.join(OUT, f"report_{CUT}.txt"), "w")
def P(*a):
    s = " ".join(str(x) for x in a); print(s); LOG.write(s + "\n")
rng = np.random.default_rng(7)
TOPN = {"QB": 5, "RB": 10, "WR": 15, "TE": 5, "DST": 5}

# ---------------- load ----------------
fc = pd.read_csv(os.path.join(R, "data/fc_history/derived/fc_master_mapped.csv"), low_memory=False)
fc = fc[(fc.site == "dk") & (fc.slate_kind == "classic") & fc.player_id.notna()]
fc = fc.drop_duplicates(["season", "week", "player_id"])
fc = fc[["season", "week", "player_id", "player", "pos", "salary", "fc_proj", "floor", "ceiling", "stdv", "score"]]
ours = pd.concat([pd.read_csv(f) for f in glob.glob(os.path.join(R, "data/fc_history/derived/ourproj/proj_*.csv"))])
ours = ours[["season", "week", "player_id", "position", "final_projection", "sigma", "statline_p10", "statline_p90"]]
ours = ours.drop_duplicates(["season", "week", "player_id"])
J = fc.merge(ours, on=["season", "week", "player_id"], how="inner")
J = J.rename(columns={"final_projection": "ours", "fc_proj": "fc", "score": "act"})
J = J[J.pos.isin(["QB", "RB", "WR", "TE", "DST"])].dropna(subset=["fc", "ours", "act"])
J["cell"] = J.season.astype(str) + "_" + J.week.astype(str) + "_" + J.pos
J["slate"] = J.season * 100 + J.week
P(f"joined rows {len(J)} (fc dk rows {len(fc)}, ours {len(ours)}); pos mismatch {(J.pos!=J.position).sum()}")
J["tier"] = pd.cut(J.salary, [0, 4000, 5500, 7000, 99999], labels=["<4k", "4-5.5k", "5.5-7k", "7k+"])

# ---------------- metrics ----------------
def _cellcorr(d, x):
    y = d.act
    g = pd.DataFrame({"c": d.cell.values, "x": x.values, "y": y.values})
    gm = g.groupby("c")
    g["xd"] = g.x - gm.x.transform("mean"); g["yd"] = g.y - gm.y.transform("mean")
    a = g.assign(xy=g.xd * g.yd, xx=g.xd ** 2, yy=g.yd ** 2).groupby("c")[["xy", "xx", "yy"]].sum()
    n = gm.size()
    r = a.xy / np.sqrt(a.xx * a.yy)
    return r[(n >= 5) & (a.xx > 0) & (a.yy > 0)].mean()

def within(d, col, fn):
    if fn is stats.spearmanr:
        dd = d.assign(act=d.groupby("cell").act.rank())
        return _cellcorr(dd, dd.groupby("cell")[col].rank())
    return _cellcorr(d, d[col])

def topn(d, col, valcol=False):
    key = d[col] / d.salary if valcol else d[col]
    r = key.groupby(d.cell).rank(ascending=False, method="first")
    lim = d.pos.map(TOPN)
    return d.act[r <= lim].groupby(d.cell[r <= lim]).mean().mean()

def metrics(d, col):
    e = d[col] - d.act
    slope = np.polyfit(d[col], d.act, 1)[0] if d[col].std() > 0 else np.nan
    return dict(n=len(d), bias=e.mean(), MAE=e.abs().mean(), RMSE=np.sqrt((e**2).mean()),
                pear_w=within(d, col, stats.pearsonr), spear_w=within(d, col, stats.spearmanr),
                slope=slope, topN=topn(d, col), valN=topn(d, col, True))

def compare(d, label, cols=("fc", "ours")):
    rows = []
    for c in cols:
        m = metrics(d, c); m.update(slice=label, src=c); rows.append(m)
    return rows

def show(rows, title):
    t = pd.DataFrame(rows).set_index(["slice", "src"])
    P("\n== " + title); P(t.round(3).to_string()); return t

J["mx"] = J[["fc", "ours"]].max(axis=1)
M = J[J.mx > 8]
if CUT == "active": M = M[(M.fc > 0) & (M.ours > 0)]
P("CUT =", CUT)
SK = M[M.pos != "DST"]
all_tabs = []
rows = compare(SK, "skill_all_proj>8") + compare(J[(J.pos != "DST") & (J.fc > 0) & (J.ours > 0)], "skill_both>0") \
     + compare(J[J.pos != "DST"], "skill_everything")
all_tabs.append(show(rows, "Overall (meaningful = max(fc,ours)>8)"))
rows = []
for p in ["QB", "RB", "WR", "TE"]: rows += compare(M[M.pos == p], p)
rows += compare(J[J.pos == "DST"], "DST_all")
all_tabs.append(show(rows, "By position (proj>8; DST all)"))
rows = []
for t in SK.tier.cat.categories: rows += compare(SK[SK.tier == t], str(t))
all_tabs.append(show(rows, "By salary tier (skill, proj>8)"))
rows = []
for s in sorted(SK.season.unique()): rows += compare(SK[SK.season == s], str(s))
all_tabs.append(show(rows, "By season (skill, proj>8)"))
# robustness: drop FC anomalies (proj>40)
rows = compare(SK[SK.fc <= 40], "skill_fc<=40")
all_tabs.append(show(rows, "Robustness"))
P(f"FC proj>40 rows (anomalies?) in skill cut: {(SK.fc>40).sum()}; FC==0 & ours>8: {((J.fc==0)&(J.ours>8)&(J.pos!='DST')).sum()} "
  f"(mean act {J[(J.fc==0)&(J.ours>8)&(J.pos!='DST')].act.mean():.2f}); ours==0 & fc>8: {((J.ours==0)&(J.fc>8)).sum()}")

# ---------------- bootstrap FC-ours deltas, by slate ----------------
def boot_delta(d, key, B=400):
    slates = d.slate.unique()
    per = {s: g for s, g in d.groupby("slate")}
    obs = metrics(d, "fc")[key] - metrics(d, "ours")[key]
    bs = []
    for _ in range(B):
        g = pd.concat([per[s].assign(cell=per[s].cell + f"#{i}") for i, s in enumerate(rng.choice(slates, len(slates)))])
        bs.append(metrics(g, "fc")[key] - metrics(g, "ours")[key])
    return obs, np.percentile(bs, [2.5, 97.5])
P("\n== FC minus OURS, slate-bootstrap 95% CI (skill proj>8)")
for k in ["MAE", "RMSE", "spear_w", "topN"]:
    o, ci = boot_delta(SK, k, 200); P(f"  {k}: {o:+.3f}  [{ci[0]:+.3f}, {ci[1]:+.3f}]")

# ---------------- blends, LOSO ----------------
def zs(d, c):
    g = d.groupby("cell")[c]; return (d[c] - g.transform("mean")) / g.transform("std").replace(0, np.nan)
def rk(d, c): return d.groupby("cell")[c].rank(pct=True)
SK = SK.copy(); SK["zf"], SK["zo"] = zs(SK, "fc"), zs(SK, "ours"); SK["rf"], SK["ro"] = rk(SK, "fc"), rk(SK, "ours")
W = np.round(np.arange(0, 1.0001, 0.05), 2)
def blend(d, w, kind):
    if kind == "raw": return w * d.fc + (1 - w) * d.ours
    if kind == "z": return w * d.zf.fillna(0) + (1 - w) * d.zo.fillna(0)
    return w * d.rf + (1 - w) * d.ro
obj = {"raw": "RMSE", "z": "spear_w", "rank": "spear_w"}
P("\n== Blends: w*FC+(1-w)*ours, w chosen leave-one-season-out")
blend_rows = []
seasons = sorted(SK.season.unique())
for kind in ["raw", "z", "rank"]:
    for s in seasons:
        tr, te = SK[SK.season != s], SK[SK.season == s]
        sc = []
        for w in W:
            m = metrics(tr.assign(b=blend(tr, w, kind)), "b")
            sc.append(m[obj[kind]] * (1 if obj[kind] in ("RMSE",) else -1))
        wb = W[int(np.argmin(sc))]
        mb = metrics(te.assign(b=blend(te, wb, kind)), "b"); mo = metrics(te, "ours"); mf = metrics(te, "fc")
        blend_rows.append(dict(kind=kind, held=s, w=wb, RMSE_b=mb["RMSE"], RMSE_o=mo["RMSE"], RMSE_f=mf["RMSE"],
                               sp_b=mb["spear_w"], sp_o=mo["spear_w"], sp_f=mf["spear_w"],
                               top_b=mb["topN"], top_o=mo["topN"], top_f=mf["topN"]))
BT = pd.DataFrame(blend_rows); P(BT.round(3).to_string())
BT.to_csv(os.path.join(OUT, f"blend_loso_{CUT}.csv"), index=False)
# pooled curve
curve = []
for w in W:
    for kind in ["raw", "z"]:
        m = metrics(SK.assign(b=blend(SK, w, kind)), "b"); m.update(w=w, kind=kind); curve.append(m)
C = pd.DataFrame(curve); C.to_csv(os.path.join(OUT, f"blend_curve_{CUT}.csv"), index=False)
P("\n pooled raw-blend curve:"); P(C[C.kind == "raw"][["w", "bias", "RMSE", "spear_w", "topN", "slope"]].iloc[::2].round(3).to_string(index=False))
P(" pooled z-blend curve:"); P(C[C.kind == "z"][["w", "spear_w", "topN"]].iloc[::2].round(3).to_string(index=False))
# bootstrap of blend at w=.5 vs ours / vs fc
def boot_b(d, w, B=200):
    per = {s: g for s, g in d.groupby("slate")}; sl = list(per)
    out = []
    for _ in range(B):
        g = pd.concat([per[s].assign(cell=per[s].cell + f"#{i}") for i, s in enumerate(rng.choice(sl, len(sl)))])
        mb = metrics(g.assign(b=blend(g, w, "raw")), "b"); mo = metrics(g, "ours"); mf = metrics(g, "fc")
        out.append([mb["RMSE"] - mo["RMSE"], mb["spear_w"] - mo["spear_w"], mb["topN"] - mo["topN"],
                    mb["RMSE"] - mf["RMSE"], mb["spear_w"] - mf["spear_w"], mb["topN"] - mf["topN"]])
    return np.percentile(np.array(out), [2.5, 50, 97.5], axis=0)
wmed = float(BT[BT.kind == "raw"].w.median())
ci = boot_b(SK, wmed)
P(f"\n raw blend w={wmed}: delta vs OURS  RMSE/spear/topN 2.5,50,97.5 pct:\n{np.round(ci[:, :3], 3)}\n delta vs FC:\n{np.round(ci[:, 3:], 3)}")

# ---------------- spread / stretch ----------------
P("\n== Spread: sd of proj within cell / sd act; slope act~proj (demeaned within cell)")
for c in ["fc", "ours"]:
    dm = SK[c] - SK.groupby("cell")[c].transform("mean"); da = SK.act - SK.groupby("cell").act.transform("mean")
    P(f"  {c}: proj sd {SK[c].std():.2f} act sd {SK.act.std():.2f}; within-cell slope {np.polyfit(dm, da, 1)[0]:.3f}; pooled slope {np.polyfit(SK[c], SK.act, 1)[0]:.3f}")
for p in ["QB", "RB", "WR", "TE"]:
    g = SK[SK.pos == p]; P(f"  {p}: slope fc {np.polyfit(g.fc, g.act, 1)[0]:.3f} ours {np.polyfit(g.ours, g.act, 1)[0]:.3f}")

# ---------------- intervals ----------------
P("\n== Interval calibration (skill proj>8): FC floor-ceiling & mean+-1.2816*stdv vs our p10-p90 & mean+-1.2816*sigma")
S = SK.dropna(subset=["statline_p10", "statline_p90", "sigma"])
def cov(lo, hi, a): return f"inside {((a >= lo) & (a <= hi)).mean():.3f} below {(a < lo).mean():.3f} above {(a > hi).mean():.3f} width {(hi - lo).mean():.1f}"
P("  FC floor/ceiling      ", cov(S.floor, S.ceiling, S.act))
P("  FC proj+-1.28*stdv    ", cov(S.fc - 1.2816 * S.stdv, S.fc + 1.2816 * S.stdv, S.act))
P("  OURS p10/p90          ", cov(S.statline_p10, S.statline_p90, S.act))
P("  OURS proj+-1.28*sigma ", cov(S.ours - 1.2816 * S.sigma, S.ours + 1.2816 * S.sigma, S.act))
P(f"  corr(|err|, spread): FC stdv {stats.spearmanr(S.stdv, (S.fc-S.act).abs())[0]:.3f}, FC ceil-floor {stats.spearmanr(S.ceiling-S.floor,(S.fc-S.act).abs())[0]:.3f}, "
  f"ours sigma {stats.spearmanr(S.sigma, (S.ours-S.act).abs())[0]:.3f}")
for p in ["QB", "RB", "WR", "TE"]:
    g = S[S.pos == p]
    P(f"  {p}: FC fl/ce {((g.act>=g.floor)&(g.act<=g.ceiling)).mean():.2f} >ceil {(g.act>g.ceiling).mean():.2f} | OURS p10-90 {((g.act>=g.statline_p10)&(g.act<=g.statline_p90)).mean():.2f} >p90 {(g.act>g.statline_p90).mean():.2f}")

pd.concat(all_tabs).to_csv(os.path.join(OUT, f"metrics_{CUT}.csv"))

# ---------------- 2026 production check ----------------
P("\n== 2026 wk1-2 PRODUCTION (guarded rebuild FIX, and OLD pre-guard) vs FC, main slate, same players")
G = pd.read_csv(os.path.join(R, "analysis/proj_recheck/guarded_accuracy_frame.csv"))
G = G[G["sub"] == "main"].drop_duplicates(["week", "player_id"])
f26 = J[J.season == 2026][["week", "player_id", "fc", "ours", "act", "pos", "salary", "cell", "slate"]]
H = f26.merge(G[["week", "player_id", "OLD", "FIX"]], on=["week", "player_id"])
P(f"  rows {len(H)}; act check vs guarded frame skipped (FC score used)")
H = H[H[["fc", "ours", "FIX"]].max(axis=1) > 8]
if CUT == "active": H = H[(H.fc > 0) & (H.FIX > 0)]
for p in [None, "QB", "RB", "WR", "TE"]:
    d = H[H.pos != "DST"] if p is None else H[H.pos == p]
    rows = compare(d, p or "skill", cols=("fc", "FIX", "OLD", "ours"))
    t = pd.DataFrame(rows).set_index(["slice", "src"]); P(t[["n", "bias", "MAE", "RMSE", "spear_w", "topN", "slope"]].round(3).to_string())
d = H[H.pos != "DST"]
for w in [0, .3, .5, .7, 1]:
    m = metrics(d.assign(b=w * d.fc + (1 - w) * d.FIX), "b"); P(f"  prod blend w={w}: RMSE {m['RMSE']:.3f} spear_w {m['spear_w']:.3f} topN {m['topN']:.2f}")
LOG.close()
