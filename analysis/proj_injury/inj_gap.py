"""Injury/inactive gap: production + regenerated projections vs FC pre-lock zeros (research only; no FC data here).

Inputs (gitignored): data/fc_history/derived/fc_master_mapped.csv, data/fc_history/derived/ourproj/proj_*.csv,
data/fc_history/derived/proj_injury/prod_<commit>.csv (last pre-lock production output from git, wk1/wk2 main).
Outputs: data/fc_history/derived/proj_injury/*.csv + report.txt (gitignored).
Lineups: faithful DK classic salary-cap ILP (QB,2RB,3WR,TE,FLEX,DST, $50k), scored on actual DK points (DNP=0).
"""
import glob, os
import numpy as np, pandas as pd, pulp
from scipy import stats

R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(R, "data/fc_history/derived/proj_injury")
LOG = open(os.path.join(OUT, "report.txt"), "w")
def P(*a):
    s = " ".join(str(x) for x in a); print(s); LOG.write(s + "\n"); LOG.flush()
POS = ["QB", "RB", "WR", "TE", "DST"]
TOPN = {"QB": 5, "RB": 10, "WR": 15, "TE": 5, "DST": 5}

fc = pd.read_csv(os.path.join(R, "data/fc_history/derived/fc_master_mapped.csv"), low_memory=False)
fc = fc[(fc.site == "dk") & (fc.slate_kind == "classic") & fc.player_id.notna() & fc.pos.isin(POS)]
fc = fc.drop_duplicates(["season", "week", "player_id"])[["season", "week", "player_id", "player", "pos", "team", "salary", "fc_proj", "score", "inj"]]

# DNP: skill player absent from nflverse REG weekly stats that week (no recorded stat). DST never DNP.
played = set()
for s in range(2021, 2027):
    w = pd.read_parquet(os.path.join(R, f"data/weekly_stats_{s}.parquet"), columns=["player_id", "season", "week"])
    played |= set(zip(w.season, w.week, w.player_id))
fc["dnp"] = [(p != "DST") and ((s, w, i) not in played) for s, w, i, p in zip(fc.season, fc.week, fc.player_id, fc.pos)]
fc["act"] = fc.score.fillna(0.0)
fc.loc[fc.dnp, "act"] = 0.0
fc["fc0"] = fc.fc_proj.fillna(0) <= 0.05

# ---------- ours ----------
ours = pd.concat([pd.read_csv(f, dtype={"player_id": str}) for f in glob.glob(os.path.join(R, "data/fc_history/derived/ourproj/proj_*.csv"))])
ours = ours.drop_duplicates(["season", "week", "player_id"])[["season", "week", "player_id", "final_projection"]]
prod = []
for c, wk in [("cefc761", 1), ("7e57cfe", 2)]:
    d = pd.read_csv(os.path.join(OUT, f"prod_{c}.csv"), dtype={"player_id": str})
    d = d[["player_id", "final_projection", "injury_status"]].assign(season=2026, week=wk)
    prod.append(d)
prod = pd.concat(prod).drop_duplicates(["season", "week", "player_id"])
H = fc[fc.season <= 2025].merge(ours, on=["season", "week", "player_id"], how="inner")
C = fc[fc.season == 2026].merge(prod, on=["season", "week", "player_id"], how="inner")
for X in (H, C):
    X.rename(columns={"final_projection": "ours"}, inplace=True)
    X["ours"] = X.ours.fillna(0).clip(lower=0)
    X["slate"] = X.season * 100 + X.week
P(f"history rows {len(H)} ({H.slate.nunique()} slates); 2026 rows {len(C)} (FC 2026 rows {int((fc.season==2026).sum())})")

# ---------- variants ----------
def redistribute(X, col, zmask, alpha):
    y = X[col].copy()
    rem = X[col].where(zmask, 0.0)
    keep = (~zmask) & (X[col] > 0) & (X.pos != "DST")
    g = [X.slate, X.team, X.pos]
    R_ = rem.groupby(g).transform("sum")
    base = X[col].where(keep, 0.0)
    den = base.groupby(g).transform("sum")
    y[zmask] = 0.0
    add = np.where(keep & (den > 0), alpha * R_ * base / den.replace(0, np.nan), 0.0)
    return y + np.nan_to_num(add)

def variants(X):
    V = {"ours": X.ours}
    z = X.fc0 & (X.pos != "DST")
    V["zFC"] = X.ours.where(~z, 0.0)
    V["zFC_r50"] = redistribute(X, "ours", z, 0.5)
    V["zFC_r100"] = redistribute(X, "ours", z, 1.0)
    V["zDNP"] = X.ours.where(~X.dnp, 0.0)                     # perfect inactive filter (upper bound)
    V["zDNP_r50"] = redistribute(X, "ours", X.dnp, 0.5)
    V["zFCorDNP"] = X.ours.where(~(z | X.dnp), 0.0)
    V["fc"] = X.fc_proj.fillna(0)
    V["fc_zDNP"] = V["fc"].where(~X.dnp, 0.0)
    return pd.DataFrame(V, index=X.index)

# ---------- player-level metrics ----------
def pmetrics(X, V):
    m = (X[["ours"]].max(axis=1) > 0) | (X.fc_proj > 0) | (X.act > 0)
    m &= X.pos != "DST"
    rows = []
    for v in V.columns:
        e = (V.loc[m, v] - X.act[m])
        # within slate x pos rank corr on players with any projection
        sp = []
        for _, g in X[m].groupby(["slate", "pos"]):
            if len(g) >= 5: sp.append(stats.spearmanr(V.loc[g.index, v], g.act).correlation)
        # top-N mean actual per slate x pos
        tn = []
        for (s, p), g in X[m].groupby(["slate", "pos"]):
            idx = V.loc[g.index, v].sort_values(ascending=False).index[:TOPN[p]]
            tn.append(X.act[idx].mean())
        rows.append(dict(var=v, n=int(m.sum()), RMSE=np.sqrt((e ** 2).mean()), MAE=e.abs().mean(), spear=np.nanmean(sp), topN=np.mean(tn)))
    return pd.DataFrame(rows).set_index("var").round(3)

# ---------- lineup ILP ----------
def optimal(g, obj):
    g = g[obj > 0.01] if (obj > 0.01).sum() > 60 else g
    obj = obj[g.index]
    pr = pulp.LpProblem("dk", pulp.LpMaximize)
    x = {i: pulp.LpVariable(f"x{k}", cat="Binary") for k, i in enumerate(g.index)}
    pr += pulp.lpSum(obj[i] * x[i] for i in g.index)
    pr += pulp.lpSum(g.salary[i] * x[i] for i in g.index) <= 50000
    pr += pulp.lpSum(x.values()) == 9
    cnt = lambda p: pulp.lpSum(x[i] for i in g.index if g.pos[i] == p)
    pr += cnt("QB") == 1; pr += cnt("DST") == 1
    pr += cnt("RB") >= 2; pr += cnt("WR") >= 3; pr += cnt("TE") >= 1
    pr += cnt("RB") <= 3; pr += cnt("WR") <= 4; pr += cnt("TE") <= 2
    pr.solve(pulp.PULP_CBC_CMD(msg=0))
    return [i for i in g.index if x[i].value() > 0.5]

def lineups(X, V, cash_ratio):
    rows = []
    for s, g in X.groupby("slate"):
        g = g[g.salary > 0]
        best = X.act[optimal(g, g.act)].sum()
        base = set(optimal(g, V.loc[g.index, "ours"]))
        for v in V.columns:
            L = base if v == "ours" else set(optimal(g, V.loc[g.index, v]))
            sc = X.act[list(L)].sum()
            rows.append(dict(slate=s, var=v, score=sc, best=best, flips=len(L - base),
                             dnp_in=int(X.dnp[list(L)].sum()), cash=sc >= cash_ratio * best))
    return pd.DataFrame(rows)

def lsum(Ld):
    b = Ld[Ld["var"] == "ours"].set_index("slate").score
    out = []
    for v, g in Ld.groupby("var"):
        d = g.set_index("slate").score - b
        bs = [d.sample(len(d), replace=True, random_state=k).mean() for k in range(1000)]
        out.append(dict(var=v, n=len(g), mean=g.score.mean(), median=g.score.median(), pct_best=(g.score / g.best).mean(),
                        cash_rate=g.cash.mean(), d_vs_ours=d.mean(), ci_lo=np.percentile(bs, 2.5), ci_hi=np.percentile(bs, 97.5),
                        slates_changed=(g.flips > 0).mean(), mean_flips=g.flips.mean(), dnp_per_lu=g.dnp_in.mean()))
    return pd.DataFrame(out).set_index("var").round(3)

# ---------- cash line calibration from real 2026 contests ----------
cr = []
for wk, f in [(1, "dk_classic_wk1_main_13Sep2026_full.csv"), (2, "dk_classic_wk2_main_20Sep2026_se3max_full.csv")]:
    r = pd.read_csv(os.path.join(R, "data/contest_results", f), usecols=["Points"], encoding="utf-8-sig").Points.dropna()
    g = C[C.week == wk]
    best = g.act[optimal(g, g.act)].sum()
    cl = np.percentile(r, 78)
    cr.append(cl / best)
    P(f"2026 wk{wk} main: entries {len(r)}, ~cash line (78th pct) {cl:.1f}, hindsight best {best:.1f}, ratio {cl/best:.3f}, top1% {np.percentile(r,99):.1f}")
CASH = float(np.mean(cr))
P(f"cash proxy = {CASH:.3f} x hindsight-best lineup (mean of 2 real slates; GPP min-cash ~top 22%, not a true cash game)")

# ---------- 2026 production vs FC ----------
P("\n== 2026 wk1-2 MAIN: last pre-lock production commit (wk1 cefc761 16:31Z, wk2 7e57cfe 16:31Z) vs FC")
C["prod_status"] = C.injury_status.fillna("NA")
a = C[C.fc0 & (C.ours > 5) & (C.pos != "DST")]
b = C[(C.fc_proj > 5) & (C.ours <= 0.05) & (C.pos != "DST")]
cols = ["week", "player", "pos", "team", "salary", "ours", "fc_proj", "prod_status", "inj", "dnp", "act"]
P(f"FC~0 & prod>5: n={len(a)}, DNP {int(a.dnp.sum())}, sum prod pts {a.ours.sum():.1f}, sum actual {a.act.sum():.1f}")
P(a[cols].sort_values(["week", "ours"], ascending=[True, False]).round(1).to_string(index=False))
P(f"prod~0 & FC>5: n={len(b)}, DNP {int(b.dnp.sum())}")
if len(b): P(b[cols].round(1).to_string(index=False))
m = C[(C.fc_proj > 5) & C.dnp & (C.pos != "DST")]
P(f"FC>5 but DNP (FC misses) 2026: n={len(m)}; of those prod>5: {int((m.ours>5).sum())}")
if len(m): P(m[cols].round(1).to_string(index=False))
VC = variants(C)
P("\n2026 player metrics (skill, any proj/act>0)"); P(pmetrics(C, VC).to_string())
LC = lineups(C, VC, CASH)
P("\n2026 lineups (n=2 slates; anecdotal)"); P(LC.pivot(index="var", columns="slate", values=["score", "flips", "dnp_in"]).round(1).to_string())

# ---------- history ----------
P("\n== 2021-2025 regenerated projections (injuries STUBBED) with FC zeros as 'known out at lock' oracle")
hs = H[H.pos != "DST"]
z = hs[hs.fc0]
P(f"FC zeros (skill): n={len(z)}; DNP {z.dnp.mean():.3f}; scored>0 {(z.act>0).mean():.3f}; mean act {z.act.mean():.2f}")
for thr in [0, 5, 10]:
    zz = z[z.ours > thr]
    P(f"  FC zero & ours>{thr}: n={len(zz)} ({len(zz)/H.slate.nunique():.1f}/slate), DNP precision {zz.dnp.mean():.3f}, "
      f"played&scored>=5 {(zz.act>=5).mean():.3f}, mean ours {zz.ours.mean():.1f}, mean act {zz.act.mean():.2f}")
d5 = hs[hs.dnp & (hs.ours > 5)]
P(f"DNP & ours>5: n={len(d5)} ({len(d5)/H.slate.nunique():.1f}/slate); FC recall (FC zero) {d5.fc0.mean():.3f}; "
  f"FC>5 (FC misses) {(d5.fc_proj>5).mean():.3f} -> {int((d5.fc_proj>5).sum())} rows")
fm = hs[hs.dnp & (hs.fc_proj > 5)]
P(f"FC misses overall (FC>5, DNP): n={len(fm)} ({len(fm)/H.slate.nunique():.2f}/slate), sum FC pts {fm.fc_proj.sum():.0f}")
VH = variants(H)
P("\nhistory player metrics"); P(pmetrics(H, VH).to_string())
LH = lineups(H, VH, CASH)
LH.to_csv(os.path.join(OUT, "lineups_history.csv"), index=False)
LC.to_csv(os.path.join(OUT, "lineups_2026.csv"), index=False)
P("\nhistory lineups (per-slate independent optimal lineup; bootstrap CI over slates)"); P(lsum(LH).to_string())
P("\nby season d_vs_ours (zFC, zDNP)")
b = LH[LH["var"] == "ours"].set_index("slate").score
for v in ["zFC", "zFC_r50", "zDNP"]:
    d = (LH[LH["var"] == v].set_index("slate").score - b)
    P(v, d.groupby(d.index // 100).mean().round(2).to_dict())
