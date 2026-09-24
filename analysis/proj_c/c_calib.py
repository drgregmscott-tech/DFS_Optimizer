"""C: calibration / spread-correction study on the SHIPPED leak-free builds (guard in, matchup neutral, stack on).
usage: python analysis/proj_c/c_calib.py <shipped_dir>  > analysis/proj_c/c_out.txt
Frame follows analysis/proj_b1/b1_matchup.py: skill rows = alive, shipped final > 8, with actual;
dedup player-weeks main>early>afternoon. DST: all alive DST rows with actual (no cut), reported separately.
All candidate corrections are fit on one week and scored on the other (LOWO); both folds must improve.
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd

REPO = Path(__file__).resolve().parents[2]
S = Path(sys.argv[1])
OUT = Path(__file__).resolve().parent
SL = [f"dk_classic_wk{w}_{s}_{d}" for w, d in ((1, "13Sep2026"), (2, "20Sep2026")) for s in ("main", "early", "afternoon")]
PRI = {"main": 0, "early": 1, "afternoon": 2}
NTOP = {"QB": 3, "RB": 5, "WR": 8, "TE": 3}
SK = list(NTOP)
TIERS = [0, 4000, 5000, 6000, 7500, 99999]
TL = ["<4k", "4-5k", "5-6k", "6-7.5k", "7.5k+"]
rng = np.random.default_rng(0)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)


def rk(x):
    return pd.Series(np.asarray(x, float)).rank().to_numpy()


def sp(a, b):
    return np.corrcoef(rk(a), rk(b))[0, 1]


def frame():
    L = pd.read_csv(REPO / "data/projection_error_log.csv", dtype={"player_id": str})
    rows = []
    for sid in SL:
        f = pd.read_csv(S / f"final_projections_dk_{sid}.csv", dtype={"player_id": str})
        f = f[f.position.isin(SK + ["DST"])]
        f = f[((f.position != "DST") & (f.final_projection > 8)) | ((f.position == "DST") & (f.final_projection > 0))]
        if "injury_status" in f:
            f = f[f.injury_status != "OUT"]
        a = L[L.slate_id == sid].drop_duplicates("player_id").set_index("player_id").actual_fpts
        f = f.assign(act=f.player_id.map(a)).dropna(subset=["act"])
        f["slate_id"], f["week"], f["sub"] = sid, int(sid.split("_wk")[1][0]), sid.split("_")[3]
        rows.append(f)
    D = pd.concat(rows, ignore_index=True)
    D["stack_delta"] = D.stack_delta.fillna(0)
    D["eng"] = D.engine_projection.fillna(D.final_projection)
    D["tier"] = pd.cut(D.salary, TIERS, labels=TL, right=False)
    D["pw"] = D.player_id + "_" + D.week.astype(str)
    return D


def dedup(D):
    return D.assign(p=D["sub"].map(PRI)).sort_values("p").drop_duplicates(["player_id", "week"]).drop(columns="p")


def ols(x, y):
    b, a = np.polyfit(x, y, 1)
    r2 = np.corrcoef(x, y)[0, 1] ** 2
    return a, b, r2


def boot_slope(d, col, B=2000):
    """cluster bootstrap by player-week (pw)."""
    g = {k: v.index.to_numpy() for k, v in d.groupby("pw")}
    keys = np.array(list(g)); x, y = d[col].to_numpy(), d.act.to_numpy()
    pos = {k: i for i, k in enumerate(d.index)}
    bs = []
    for _ in range(B):
        idx = np.concatenate([[pos[j] for j in g[k]] for k in rng.choice(keys, len(keys))])
        if np.ptp(x[idx]) == 0:
            continue
        bs.append(np.polyfit(x[idx], y[idx], 1)[0])
    return np.percentile(bs, 2.5), np.percentile(bs, 97.5)


def regtab(d, cols=("final_projection", "eng"), boot=True):
    out = []
    groups = [(p, d[d.position == p]) for p in SK + ["DST"]] + [("ALL_nonDST", d[d.position != "DST"])]
    for name, g in groups:
        for c in cols:
            a, b, r2 = ols(g[c], g.act)
            lo, hi = boot_slope(g.reset_index(drop=True), c) if boot else (np.nan, np.nan)
            out.append(dict(grp=name, col=c, n=len(g), npw=g.pw.nunique(), slope=b, lo=lo, hi=hi, icpt=a, R2=r2,
                            corr=np.sqrt(r2) * np.sign(b), bias=(g[c] - g.act).mean(), sd_proj=g[c].std(), sd_act=g.act.std()))
    return pd.DataFrame(out).round(3)


def bintab(d, col, by):
    return d.groupby(by, observed=True).agg(n=("act", "size"), proj=(col, "mean"), eng=("eng", "mean"),
                                            act=("act", "mean")).assign(bias=lambda t: t.proj - t.act).round(2)


# ---------------- metrics ----------------
def value_base(d):
    """salary-implied points per position (fit within the scored data, used only as a yardstick)."""
    v = np.zeros(len(d))
    for p in SK:
        m = (d.position == p).to_numpy()
        a, b, _ = ols(d.salary[m], d.act[m]); v[m] = a + b * d.salary[m]
    return v


def metrics(D, col):
    """D = one test week, slate-level rows, non-DST. Pooled level metrics on dedup rows; ranking on slates."""
    Dd = dedup(D); e = Dd[col] - Dd.act
    r = dict(bias=e.mean(), mae=e.abs().mean(), rmse=np.sqrt((e ** 2).mean()))
    cs, ct, ps, topk, vs, vtop = [], [], [], [], [], []
    for sid, g in D.groupby("slate_id"):
        for p, h in g.groupby("position"):
            if len(h) >= 6:
                cs.append(sp(h[col], h.act)); ct.append(h.nlargest(NTOP[p], col).act.mean())
        ps.append(sp(g[col], g.act))
        topk.append(g.nlargest(20, col).act.mean())
        # cross-position value: points per $1k (what a salary-constrained lineup optimizer trades on)
        vs.append(sp(g[col] / g.salary, g.act / g.salary))
        vtop.append(g.assign(v=g[col] / g.salary).nlargest(20, "v").act.mean())
    r.update(cell_sp=np.mean(cs), cell_top=np.mean(ct), pool_sp=np.mean(ps), top20=np.mean(topk),
             val_sp=np.mean(vs), vtop20=np.mean(vtop), ncell=len(cs))
    return r


# ---------------- candidate transforms: fit(train_df) -> apply(df) ----------------
def pav(x, y):
    o = np.argsort(x); xs, ys = x[o], y[o].astype(float)
    blocks = [[ys[i], 1, xs[i], xs[i]] for i in range(len(ys))]
    st = []
    for b in blocks:
        st.append(b)
        while len(st) > 1 and st[-2][0] / st[-2][1] > st[-1][0] / st[-1][1]:
            s2 = st.pop(); s1 = st.pop(); st.append([s1[0] + s2[0], s1[1] + s2[1], s1[2], s2[3]])
    kx = np.array([(b[2] + b[3]) / 2 for b in st]); ky = np.array([b[0] / b[1] for b in st])
    return kx, ky


def c_none(tr):
    return lambda d: d.final_projection.to_numpy()


def c_global(tr, shrink=1.0):
    a, b, _ = ols(tr.final_projection, tr.act); m = tr.final_projection.mean()
    k = 1 + shrink * (b - 1)
    return lambda d: (m + k * (d.final_projection - m)).clip(lower=0).to_numpy()


def c_pos(tr, shrink=1.0):
    P = {}
    for p in SK:
        g = tr[tr.position == p]; a, b, _ = ols(g.final_projection, g.act)
        m = g.final_projection.mean(); P[p] = (m, 1 + shrink * (b - 1), g.act.mean() - m)
    def f(d):
        m = d.position.map(lambda p: P[p][0]); k = d.position.map(lambda p: P[p][1]); o = d.position.map(lambda p: P[p][2])
        return (m + o * shrink + k * (d.final_projection - m)).clip(lower=0).to_numpy()
    return f


def c_iso(tr, per_pos=False):
    grp = SK if per_pos else [None]
    K = {}
    for p in grp:
        g = tr if p is None else tr[tr.position == p]
        K[p] = pav(g.final_projection.to_numpy(), g.act.to_numpy())
    def f(d):
        out = np.empty(len(d))
        for p in grp:
            m = np.ones(len(d), bool) if p is None else (d.position == p).to_numpy()
            kx, ky = K[p]
            # linear interpolation between block centres, flat beyond ends -> weakly monotone
            out[m] = np.interp(d.final_projection.to_numpy()[m], kx, ky)
        return out
    return f


def c_tier(tr, shrink=1.0):
    off = (tr.act - tr.final_projection).groupby(tr.tier, observed=True).mean() * shrink
    return lambda d: (d.final_projection + d.tier.map(off).astype(float).fillna(0)).to_numpy()


def c_tier_top(tr, shrink=1.0):
    """only the >= $6k tiers get an offset (the pre-registered 'stud under-projection' hypothesis)."""
    off = (tr.act - tr.final_projection).groupby(tr.tier, observed=True).mean() * shrink
    off = off[off.index.isin(["6-7.5k", "7.5k+"])]
    return lambda d: (d.final_projection + d.tier.map(off).astype(float).fillna(0)).to_numpy()


def c_salblend(tr):
    """per position act ~ a + b*final + c*salary($k)."""
    P = {}
    for p in SK:
        g = tr[tr.position == p]
        X = np.c_[np.ones(len(g)), g.final_projection, g.salary / 1000]
        P[p] = np.linalg.lstsq(X, g.act, rcond=None)[0]
    def f(d):
        out = np.empty(len(d))
        for p in SK:
            m = (d.position == p).to_numpy(); g = d[m]
            out[m] = np.c_[np.ones(len(g)), g.final_projection, g.salary / 1000] @ P[p]
        return out.clip(0)
    return f


def c_eng_stack(tr):
    """re-weight stack: act ~ a + b*eng + c*stack_delta (pooled non-DST)."""
    X = np.c_[np.ones(len(tr)), tr.eng, tr.stack_delta]
    c = np.linalg.lstsq(X, tr.act, rcond=None)[0]
    return lambda d: (np.c_[np.ones(len(d)), d.eng, d.stack_delta] @ c).clip(0)


CANDS = {
    "none": c_none,
    "a_global": c_global, "a_global_half": lambda t: c_global(t, 0.5),
    "b_pos": c_pos, "b_pos_half": lambda t: c_pos(t, 0.5),
    "c_iso_global": c_iso, "c_iso_pos": lambda t: c_iso(t, True),
    "d_tier": c_tier, "d_tier_half": lambda t: c_tier(t, 0.5), "d_tier_top": c_tier_top, "d_tier_top_half": lambda t: c_tier_top(t, 0.5),
    "e_salblend": c_salblend, "e_eng_stack": c_eng_stack,
}


def lowo(D):
    res = []
    for tw in (1, 2):
        tr = dedup(D[D.week != tw]); te = D[D.week == tw].copy()
        for name, fit in CANDS.items():
            te["_p"] = fit(tr)(te)
            r = metrics(te, "_p"); r.update(cand=name, test_wk=tw, fit_wk=3 - tw)
            res.append(r)
    R = pd.DataFrame(res)
    base = R[R.cand == "none"].set_index("test_wk")
    cols = ["bias", "mae", "rmse", "cell_sp", "cell_top", "pool_sp", "top20", "val_sp", "vtop20"]
    for c in cols:
        R["d_" + c] = R.apply(lambda r: r[c] - base.loc[r.test_wk, c], axis=1)
    return R


if __name__ == "__main__":
    D = frame(); D.to_csv(OUT / "c_frame.csv", index=False)
    Dd = dedup(D)
    print(f"slate rows {len(D)}; dedup player-weeks {len(Dd)}; by week/pos:\n", Dd.groupby(["week", "position"]).size().unstack())
    print("salary >= 7500 dedup non-DST:", ((Dd.salary >= 7500) & (Dd.position != "DST")).sum())

    print("\n==== T1 REGRESSIONS act ~ proj, DEDUP (cluster boot by player-week, B=2000) ====")
    print(regtab(Dd).to_string(index=False))
    print("\n==== T1 REGRESSIONS, UN-DEDUP within-slate rows (cluster boot by player-week) ====")
    print(regtab(D).to_string(index=False))
    print("\n==== T1 by week (dedup, final vs eng) ====")
    for w in (1, 2):
        print(f"-- wk{w}"); print(regtab(Dd[Dd.week == w], boot=False)[["grp", "col", "n", "slope", "icpt", "R2", "bias", "sd_proj", "sd_act"]].to_string(index=False))

    ND = Dd[Dd.position != "DST"].copy()
    ND["pbin"] = pd.qcut(ND.final_projection, 10)
    print("\n==== T1 calibration by final_projection decile (dedup non-DST) ====")
    print(bintab(ND, "final_projection", "pbin").to_string())
    for p in SK:
        g = ND[ND.position == p].copy(); g["pbin"] = pd.qcut(g.final_projection, 4 if p in ("QB", "TE") else 5)
        print(f"-- {p} quantile bins"); print(bintab(g, "final_projection", "pbin").to_string())
    print("\n==== T1 by salary tier (dedup non-DST), all + by week ====")
    print(bintab(ND, "final_projection", "tier").to_string())
    print(ND.groupby(["week", "tier"], observed=True).apply(lambda g: pd.Series(dict(n=len(g), bias=(g.final_projection - g.act).mean(), eng_bias=(g.eng - g.act).mean()))).round(2).unstack(0).to_string())
    print("\n-- tier x position bias (n) dedup")
    print(ND.groupby(["tier", "position"], observed=True).apply(lambda g: f"{(g.final_projection - g.act).mean():+.1f} ({len(g)})").unstack().to_string())
    print("\n-- tier bias bootstrap CI (cluster = player-week, dedup so 1 row each)")
    for t in TL:
        g = ND[ND.tier == t]; e = (g.final_projection - g.act).to_numpy()
        bs = [rng.choice(e, len(e)).mean() for _ in range(4000)]
        print(f"{t:7s} n={len(e):3d} bias={e.mean():+.2f}  95%CI [{np.percentile(bs, 2.5):+.2f},{np.percentile(bs, 97.5):+.2f}]")

    print("\n==== T1 stack vs engine decomposition (dedup non-DST) ====")
    a1, b1, _ = ols(ND.eng, ND.act); a2, b2, _ = ols(ND.final_projection, ND.act)
    print(f"slope eng {b1:.3f}  slope final {b2:.3f}; sd eng {ND.eng.std():.2f} sd final {ND.final_projection.std():.2f} sd act {ND.act.std():.2f}")
    print(f"corr(stack_delta, eng) {np.corrcoef(ND.stack_delta, ND.eng)[0, 1]:.3f}; corr(stack_delta, act-eng) {np.corrcoef(ND.stack_delta, ND.act - ND.eng)[0, 1]:.3f}")
    X = np.c_[np.ones(len(ND)), ND.eng, ND.stack_delta]; c = np.linalg.lstsq(X, ND.act, rcond=None)[0]
    print(f"act ~ {c[0]:.2f} + {c[1]:.3f}*eng + {c[2]:.3f}*stack_delta   (1.0/1.0 = shipped)")
    print("stack_delta mean by tier:", ND.groupby("tier", observed=True).stack_delta.mean().round(2).to_dict())

    # ---------------- T2 QB ----------------
    print("\n==== T2 QB ====")
    W = pd.read_parquet(REPO / "data/weekly_stats_2026.parquet")
    W = W[W.season_type == "REG"] if "season_type" in W else W
    W = W.groupby(["player_id", "week"], as_index=False)[["attempts", "passing_yards", "passing_tds", "carries", "rushing_yards", "rushing_tds"]].sum()
    Q = Dd[Dd.position == "QB"].merge(W, on=["player_id", "week"], how="left")
    Q.to_csv(OUT / "c_qb_frame.csv", index=False)
    print("n QB", len(Q), "with statline actual", Q.attempts.notna().sum())
    Q["p_pass"] = 0.04 * Q.proj_pass_yd + 4 * Q.proj_pass_td
    Q["p_rush"] = 0.1 * Q.proj_rush_yd + 6 * Q.proj_rush_td
    Q["a_pass"] = 0.04 * Q.passing_yards + 4 * Q.passing_tds
    Q["a_rush"] = 0.1 * Q.rushing_yards + 6 * Q.rushing_tds
    for w in (1, 2, None):
        g = Q if w is None else Q[Q.week == w]
        print(f"wk{w or 'ALL'} n={len(g)} corr(final,act) {np.corrcoef(g.final_projection, g.act)[0,1]:.3f}  corr(eng,act) {np.corrcoef(g.eng, g.act)[0,1]:.3f}"
              f"  corr(salary,act) {np.corrcoef(g.salary, g.act)[0,1]:.3f}  spear(final) {sp(g.final_projection, g.act):.3f} spear(sal) {sp(g.salary, g.act):.3f}"
              f"  sd proj {g.final_projection.std():.2f} sd act {g.act.std():.2f}")
    g = Q.dropna(subset=["attempts"])
    for pc, ac, lab in (("proj_pass_att", "attempts", "pass att"), ("proj_rush_att", "carries", "rush att"), ("proj_rush_yd", "rushing_yards", "rush yd"),
                        ("proj_pass_yd", "passing_yards", "pass yd"), ("proj_pass_td", "passing_tds", "pass td"), ("p_pass", "a_pass", "pass pts"), ("p_rush", "a_rush", "rush pts")):
        print(f"{lab:9s} proj mean {g[pc].mean():6.2f} sd {g[pc].std():5.2f} [{g[pc].min():.1f},{g[pc].max():.1f}] | act mean {g[ac].mean():6.2f} sd {g[ac].std():5.2f} | corr {np.corrcoef(g[pc], g[ac])[0,1]:+.3f} slope {np.polyfit(g[pc], g[ac], 1)[0]:+.2f}")
    print("corr(p_rush, act total)", round(np.corrcoef(g.p_rush, g.act)[0, 1], 3), " corr(p_pass, act total)", round(np.corrcoef(g.p_pass, g.act)[0, 1], 3))
    print("corr(a_rush, act total)", round(np.corrcoef(g.a_rush, g.act)[0, 1], 3), " corr(a_pass, act total)", round(np.corrcoef(g.a_pass, g.act)[0, 1], 3))
    # rushing QBs: top-8 by projected rush yards vs rest
    g = g.assign(rushq=g.proj_rush_yd >= g.proj_rush_yd.quantile(0.75))
    print("\nrushing-QB split (top quartile proj rush yd):")
    print(g.groupby("rushq").agg(n=("act", "size"), proj=("final_projection", "mean"), act=("act", "mean"), prush_yd=("proj_rush_yd", "mean"),
                                  arush_yd=("rushing_yards", "mean"), pcar=("proj_rush_att", "mean"), acar=("carries", "mean")).round(2).to_string())
    print("\nper-QB rush (dedup, sorted by actual rush yd):")
    print(g.sort_values("rushing_yards", ascending=False)[["week", "player_name", "salary", "final_projection", "act", "proj_rush_att", "carries", "proj_rush_yd", "rushing_yards", "proj_pass_att", "attempts"]].round(1).head(14).to_string(index=False))
    # counterfactual: how much rank signal lost to pass-att flatness / rush under-projection? oracle-volume test
    # replace projected volume with the actual volume, keep projected efficiency -> upper bound on what volume info is worth
    ypa = g.proj_pass_yd / g.proj_pass_att; tdpa = g.proj_pass_td / g.proj_pass_att
    ypc = g.proj_rush_yd / g.proj_rush_att.replace(0, np.nan); tdpc = g.proj_rush_td / g.proj_rush_att.replace(0, np.nan)
    base_other = g.eng - g.p_pass - g.p_rush
    orc_pass = base_other + g.p_rush + 0.04 * ypa * g.attempts + 4 * tdpa * g.attempts
    orc_rush = base_other + g.p_pass + (0.1 * ypc * g.carries + 6 * tdpc * g.carries).fillna(0)
    orc_both = base_other + 0.04 * ypa * g.attempts + 4 * tdpa * g.attempts + (0.1 * ypc * g.carries + 6 * tdpc * g.carries).fillna(0)
    for lab, v in (("engine", g.eng), ("oracle pass att", orc_pass), ("oracle carries", orc_rush), ("oracle both", orc_both)):
        print(f"{lab:16s} corr {np.corrcoef(v, g.act)[0,1]:.3f} spear {sp(v, g.act):.3f}")
    print("QB residual (act-final) vs salary corr:", round(np.corrcoef(g.salary, g.act - g.final_projection)[0, 1], 3),
          " vs proj_rush_yd:", round(np.corrcoef(g.proj_rush_yd, g.act - g.final_projection)[0, 1], 3),
          " vs implied_total:", round(np.corrcoef(g.implied_total, g.act - g.final_projection)[0, 1], 3))
    print("corr(implied_total, act) QB:", round(np.corrcoef(g.implied_total, g.act)[0, 1], 3), " corr(implied_total, final):", round(np.corrcoef(g.implied_total, g.final_projection)[0, 1], 3))

    # ---------------- T3 LOWO ----------------
    print("\n==== T3 LOWO candidates (non-DST, slate-level rows; fit on dedup train week) ====")
    SKD = D[D.position != "DST"].copy()
    R = lowo(SKD); R.to_csv(OUT / "c_lowo.csv", index=False)
    show = ["cand", "test_wk", "bias", "mae", "rmse", "d_mae", "d_rmse", "d_cell_sp", "d_cell_top", "d_pool_sp", "d_top20", "d_val_sp", "d_vtop20"]
    print(R[show].round(3).to_string(index=False))
    print("\nbase metrics:"); print(R[R.cand == "none"][["test_wk", "bias", "mae", "rmse", "cell_sp", "cell_top", "pool_sp", "top20", "val_sp", "vtop20", "ncell"]].round(3).to_string(index=False))
    print("\nBOTH-FOLD verdict (improve = lower mae AND lower rmse in both folds; rank = d_val_sp>0 & d_vtop20>0 both folds; cell = d_cell_sp>0 both):")
    for c, g in R.groupby("cand", sort=False):
        lvl = ((g.d_mae < 0) & (g.d_rmse < 0)).all(); val = ((g.d_val_sp > 0) & (g.d_vtop20 > 0)).all(); cel = (g.d_cell_sp > 0).all()
        print(f"{c:16s} level_both={lvl!s:5s} value_rank_both={val!s:5s} cell_rank_both={cel!s:5s}  mean d_mae {g.d_mae.mean():+.3f}  d_val_sp {g.d_val_sp.mean():+.4f}  d_vtop20 {g.d_vtop20.mean():+.3f}")

    # fitted parameters on ALL data (what would ship) and on each week (stability)
    print("\n==== fitted params per week (stability) ====")
    for w in (1, 2, None):
        tr = ND if w is None else ND[ND.week == w]
        a, b, _ = ols(tr.final_projection, tr.act)
        off = (tr.act - tr.final_projection).groupby(tr.tier, observed=True).mean().round(2).to_dict()
        pos = {p: tuple(np.round(ols(tr[tr.position == p].final_projection, tr[tr.position == p].act)[:2], 2)) for p in SK}
        print(f"wk{w or 'ALL'}: global slope {b:.3f} icpt {a:.2f} | tier offsets(act-proj) {off} | pos (icpt,slope) {pos}")
