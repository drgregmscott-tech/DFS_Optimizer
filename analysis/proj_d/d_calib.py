"""D: spread / tail calibration of the SHIPPED leak-free builds (sigma, statline_p10/p90).
usage: python analysis/proj_d/d_calib.py <shipped_dir> > analysis/proj_d/d_out.txt
Frame follows analysis/proj_c/c_calib.py (alive, final>8 "meaningful" or final>3 "all", with actual,
dedup player-weeks main>early>afternoon). DST excluded (p10/p90 are 0 for DST by construction).
CIs: cluster bootstrap by team-week (teammates share game script), B=2000.
Candidate fixes are fit on one week and scored on the other (LOWO).
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd

REPO = Path(__file__).resolve().parents[2]
S = Path(sys.argv[1])
SL = [f"dk_classic_wk{w}_{s}_{d}" for w, d in ((1, "13Sep2026"), (2, "20Sep2026")) for s in ("main", "early", "afternoon")]
PRI = {"main": 0, "early": 1, "afternoon": 2}
SK = ["QB", "RB", "WR", "TE"]
TIERS = [0, 4000, 5000, 6000, 7500, 99999]; TL = ["<4k", "4-5k", "5-6k", "6-7.5k", "7.5k+"]
Z90 = 1.2815515655446004
rng = np.random.default_rng(0)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40); pd.set_option("display.precision", 3)


def frame(cut):
    L = pd.read_csv(REPO / "data/projection_error_log.csv", dtype={"player_id": str})
    rows = []
    for sid in SL:
        f = pd.read_csv(S / f"final_projections_dk_{sid}.csv", dtype={"player_id": str})
        f = f[f.position.isin(SK) & (f.final_projection > cut) & (f.sigma > 0)]
        if "injury_status" in f:
            f = f[f.injury_status != "OUT"]
        a = L[L.slate_id == sid].drop_duplicates("player_id").set_index("player_id").actual_fpts
        f = f.assign(act=f.player_id.map(a)).dropna(subset=["act"])
        f["week"], f["sub"] = int(sid.split("_wk")[1][0]), sid.split("_")[3]
        rows.append(f)
    D = pd.concat(rows, ignore_index=True)
    D = D.assign(p=D["sub"].map(PRI)).sort_values("p").drop_duplicates(["player_id", "week"]).drop(columns="p")
    D["m"] = D.final_projection
    D["stack_delta"] = D.stack_delta.fillna(0)
    D["tier"] = pd.cut(D.salary, TIERS, labels=TL, right=False)
    D["cl"] = D.team + "_" + D.week.astype(str)
    D["r"] = D.act - D.m
    D["z"] = D.r / D.sigma
    D["pbin"] = pd.cut(D.m, [0, 8, 12, 16, 20, 99], labels=["<8", "8-12", "12-16", "16-20", "20+"])
    return D.reset_index(drop=True)


def cboot(d, fn, B=2000):
    g = [v.index.to_numpy() for _, v in d.groupby("cl")]
    est = fn(d); bs = []
    for _ in range(B):
        idx = np.concatenate([g[i] for i in rng.integers(0, len(g), len(g))])
        bs.append(fn(d.loc[idx]))
    bs = np.array(bs)
    return est, np.percentile(bs, 2.5, axis=0), np.percentile(bs, 97.5, axis=0)


def cov(d, lo="statline_p10", hi="statline_p90"):
    return np.array([(d.act < d[lo]).mean(), ((d.act >= d[lo]) & (d.act <= d[hi])).mean(), (d.act > d[hi]).mean()])


def covtab(D, by, lo="statline_p10", hi="statline_p90", boot=True):
    out = []
    groups = [("ALL", D)] + [(f"{by}={k}", g) for k, g in D.groupby(by, observed=True)] if by else [("ALL", D)]
    for name, g in groups:
        g = g.reset_index(drop=True)
        if boot and len(g) >= 15:
            e, lo_, hi_ = cboot(g, lambda x: cov(x, lo, hi), B=1000)
            out.append([name, len(g)] + [f"{e[i]:.3f} [{lo_[i]:.2f},{hi_[i]:.2f}]" for i in range(3)])
        else:
            e = cov(g, lo, hi); out.append([name, len(g)] + [f"{x:.3f}" for x in e])
    return pd.DataFrame(out, columns=["group", "n", "below_p10", "inside", "above_p90"])


def zstats(D, by):
    def f(g):
        z = g.z; zc = (g.r - g.r.mean()) / g.sigma
        return pd.Series({"n": len(g), "bias": g.r.mean(), "z_mean": z.mean(), "z_sd": z.std(), "zc_sd": zc.std(),
                          "P(z<-1.28)": (z < -Z90).mean(), "P(z>1.28)": (z > Z90).mean(),
                          "P(zc>1.28)": (zc > Z90).mean(), "skew_r": g.r.skew(),
                          "sigma_mean": g.sigma.mean(), "sd_resid": g.r.std(), "rmse": np.sqrt((g.r ** 2).mean()),
                          "rms_sigma": np.sqrt((g.sigma ** 2).mean()),
                          "k_rmse": np.sqrt((g.r ** 2).mean()) / np.sqrt((g.sigma ** 2).mean()),
                          "k_sd": g.r.std() / np.sqrt((g.sigma ** 2).mean()),
                          "impl_sig_p": ((g.statline_p90 - g.statline_p10) / (2 * Z90)).mean()})
    rows = [f(D).rename("ALL")] + [f(g).rename(f"{by}={k}") for k, g in D.groupby(by, observed=True)]
    return pd.DataFrame(rows)


def pinball(y, q, tau):
    d = y - q
    return np.mean(np.maximum(tau * d, (tau - 1) * d))


def score(d, q10, q50, q90):
    y = d.act.to_numpy()
    return {"below": np.mean(y < q10), "inside": np.mean((y >= q10) & (y <= q90)), "above": np.mean(y > q90),
            "pb10": pinball(y, q10, .1), "pb50": pinball(y, q50, .5), "pb90": pinball(y, q90, .9)}


# ---- candidate fixes: each fit(tr) returns fn(te) -> (q10, q50, q90) ----
def f_none(tr):
    return lambda te: (te.statline_p10.to_numpy(), te.m.to_numpy(), te.statline_p90.to_numpy())


def _k_halfwidth(tr, pos_level):
    """(a) scale lower/upper half-widths about the mean by k_lo/k_hi chosen on tr to hit 10%/10%."""
    ks = {}
    grid = np.arange(0.5, 3.01, 0.01)
    for key, g in ([("ALL", tr)] + ([(p, tr[tr.position == p]) for p in SK] if pos_level else [])):
        lo_w, hi_w = (g.m - g.statline_p10).clip(lower=0.01), (g.statline_p90 - g.m).clip(lower=0.01)
        klo = grid[np.argmin([abs(np.mean(g.act < g.m - k * lo_w) - .1) for k in grid])]
        khi = grid[np.argmin([abs(np.mean(g.act > g.m + k * hi_w) - .1) for k in grid])]
        ks[key] = (klo, khi)

    def ap(te):
        kk = np.array([ks.get(p, ks["ALL"]) if pos_level else ks["ALL"] for p in te.position])
        return (np.maximum(te.m - kk[:, 0] * (te.m - te.statline_p10).clip(lower=0.01), 0).to_numpy(),
                te.m.to_numpy(), (te.m + kk[:, 1] * (te.statline_p90 - te.m).clip(lower=0.01)).to_numpy())
    ap.ks = ks
    return ap


def f_k_global(tr): return _k_halfwidth(tr, False)
def f_k_pos(tr): return _k_halfwidth(tr, True)


def f_k_lower_only(tr):
    """(a-lo) widen only the lower half-width (the one stable parameter across folds); p90 untouched."""
    f = _k_halfwidth(tr, False); klo = f.ks["ALL"][0]
    ap = lambda te: (np.maximum(te.m - klo * (te.m - te.statline_p10).clip(lower=0.01), 0).to_numpy(), te.m.to_numpy(), te.statline_p90.to_numpy())
    ap.klo = klo
    return ap


def f_sigma_normal_k(tr):
    """normal(mean, k*sigma), k = rmse/rms(sigma) on tr (global)."""
    k = np.sqrt((tr.r ** 2).mean() / (tr.sigma ** 2).mean())
    f = lambda te: (np.maximum(te.m - Z90 * k * te.sigma, 0).to_numpy(), te.m.to_numpy(), (te.m + Z90 * k * te.sigma).to_numpy())
    f.k = k
    return f


def f_zmap(tr):
    """(b) shape-aware: q_tau = m + sigma * empirical quantile of z on tr (absorbs bias+skew)."""
    q = np.quantile(tr.z, [.1, .5, .9])
    f = lambda te: (np.maximum(te.m + q[0] * te.sigma, 0).to_numpy(), (te.m + q[1] * te.sigma).to_numpy(), (te.m + q[2] * te.sigma).to_numpy())
    f.q = q
    return f


def f_zmap_centered(tr):
    """(b') like zmap but the median is forced to the mean (spread/shape only, no level correction)."""
    q = np.quantile(tr.z, [.1, .5, .9]); q = q - q[1]
    return lambda te: (np.maximum(te.m + q[0] * te.sigma, 0).to_numpy(), te.m.to_numpy(), (te.m + q[2] * te.sigma).to_numpy())


def f_hist(tr):
    """historical sd/mean shape from rotoguru (fitted in hist section, global HIST dict), no 2026 fitting."""
    def ap(te):
        q10 = np.array([HIST[p][0] for p in te.position]); q90 = np.array([HIST[p][1] for p in te.position])
        return (np.maximum(te.m * q10, 0), te.m.to_numpy(), te.m * q90)
    return ap


CANDS = {"none(shipped p10/p90)": f_none, "(a) k_halfwidth global": f_k_global, "(a) k_halfwidth per-pos": f_k_pos, "(a-lo) lower half-width only": f_k_lower_only,
         "normal k*sigma global": f_sigma_normal_k, "(b) z-quantile map": f_zmap, "(b') z-map median=mean": f_zmap_centered,
         "(h) hist ratio q/mean (no 2026 fit)": f_hist}
HIST = {}


def lowo(D):
    res = []
    for name, fn in CANDS.items():
        for te_w in (1, 2):
            tr, te = D[D.week != te_w], D[D.week == te_w]
            if name.startswith("(h)") and not HIST:
                continue
            q10, q50, q90 = fn(tr)(te)
            res.append({"cand": name, "test_wk": te_w, **score(te, q10, q50, q90)})
    R = pd.DataFrame(res)
    return R, R.groupby("cand", sort=False).mean(numeric_only=True).drop(columns="test_wk")


# ---- historical within-game dispersion from rotoguru 2014-2021 (engine independent) ----
def hist():
    fr = []
    for y in range(2014, 2022):
        r = pd.read_csv(REPO / f"data/rotoguru_actuals_dk_{y}.csv")
        r = r[r.rotoguru_position.isin(SK) & (r.salary > 0)]
        fr.append(r)
    R = pd.concat(fr)
    R["pos"] = R.rotoguru_position
    g = R.groupby(["season", "name", "team", "pos"]).actual_points
    R["n"] = g.transform("size"); R["s"] = g.transform("sum")
    R = R[R.n >= 8].copy()
    R["mu"] = (R.s - R.actual_points) / (R.n - 1)   # leave-one-out season mean
    R = R[R.mu > 8]
    R["mbin"] = pd.cut(R.mu, [8, 12, 16, 20, 99], labels=["8-12", "12-16", "16-20", "20+"])
    R["res"] = R.actual_points - R.mu
    out = R.groupby(["pos", "mbin"], observed=True).apply(lambda d: pd.Series({
        "n": len(d), "mu": d.mu.mean(), "sd": d.res.std(), "cv": d.res.std() / d.mu.mean(), "skew": d.res.skew(),
        "q10/mu": np.quantile(d.actual_points / d.mu, .1), "q90/mu": np.quantile(d.actual_points / d.mu, .9)}))
    for p in SK:
        d = R[R.pos == p]
        HIST[p] = (np.quantile(d.actual_points / d.mu, .1), np.quantile(d.actual_points / d.mu, .9))
    return R, out


def main():
    print("=" * 100); print("D. SPREAD CALIBRATION -- shipped leak-free builds, wk1+wk2 DK classic, non-DST")
    for cut in (8, 3):
        D = frame(cut)
        print(f"\n######## cut final>{cut}: n={len(D)} unique player-weeks (wk1 {sum(D.week==1)}, wk2 {sum(D.week==2)}), clusters={D.cl.nunique()}")
        print("stack shift check: p10/p90 carry stack_delta (build_projections_statline.py:311-312); rows with stack!=0:",
              int((D.stack_delta != 0).sum()), " p10<=m<=p90 violations:", int(((D.m < D.statline_p10) | (D.m > D.statline_p90)).sum()))
        print("\n-- TASK1 coverage of statline_p10/p90 (target .10/.80/.10), 95% cluster-boot CI")
        for by in (None, "position", "tier", "week", "pbin"):
            print(covtab(D, by, boot=(cut == 8)).to_string(index=False))
        # recentred: remove level bias (in-sample per position; illustrative), shift quantiles by bias
        b = D.groupby("position").r.transform("mean")
        Dc = D.assign(statline_p10=D.statline_p10 + b, statline_p90=D.statline_p90 + b)
        print("\n-- recentred (per-position in-sample mean bias added to p10/p90) -- spread-only problem")
        print(covtab(Dc, "position", boot=False).to_string(index=False))
        print("\n-- TASK1/2 z=(act-mean)/sigma (normal approx) and sigma vs realised residual")
        for by in ("position", "week", "tier", "pbin"):
            print(zstats(D, by).round(3).to_string())
        if cut == 8:
            print("\n-- implied sigma from p10/p90 vs shipped sigma vs realised (ratio sigma/impl):",
                  round((D.sigma / ((D.statline_p90 - D.statline_p10) / (2 * Z90))).median(), 3))
            e, lo, hi = cboot(D, lambda x: np.sqrt((x.r ** 2).mean() / (x.sigma ** 2).mean()))
            print(f"global k_rmse = {e:.3f} [{lo:.3f},{hi:.3f}]")
            e, lo, hi = cboot(D, lambda x: x.r.std() / np.sqrt((x.sigma ** 2).mean()))
            print(f"global k_sd (bias removed) = {e:.3f} [{lo:.3f},{hi:.3f}]")
            e, lo, hi = cboot(D, lambda x: x.r.skew())
            print(f"residual skew = {e:.3f} [{lo:.3f},{hi:.3f}]")
            # rank quality: does sigma rank |resid|?
            print("spearman(sigma, |resid|) =", round(D.sigma.rank().corr(D.r.abs().rank()), 3),
                  " spearman(p90-m, max(resid,0)) =", round((D.statline_p90 - D.m).rank().corr(D.r.clip(lower=0).rank()), 3))
            # TD dispersion check
            td = D.proj_pass_td.fillna(0) * 0 + D.proj_rush_td.fillna(0) + D.proj_rec_td.fillna(0)
            print("\n-- TASK3 skill TDs (rush+rec) for non-QB: mean projected TD", round(td[D.position != 'QB'].mean(), 3))
            DD = D.copy(); DD["exp_td"] = td
            TDA = actual_tds(DD)
            if TDA is not None:
                print(TDA)
            D8 = D
    print("\n######## HISTORICAL within-game dispersion (rotoguru DK 2014-2021, LOO season mean >8, >=8 games)")
    R, H = hist()
    print(H.round(3).to_string())
    print("HIST q10/mu, q90/mu by pos:", {k: tuple(round(x, 3) for x in v) for k, v in HIST.items()})
    # shipped model at comparable mean: ratio p10/m, p90/m and sigma/m by pos x bin
    D8b = D8[D8.m > 8].copy(); D8b["mbin"] = pd.cut(D8b.m, [8, 12, 16, 20, 99], labels=["8-12", "12-16", "16-20", "20+"])
    S2 = D8b.groupby(["position", "mbin"], observed=True).apply(lambda d: pd.Series({
        "n": len(d), "sigma/m": (d.sigma / d.m).mean(), "p10/m": (d.statline_p10 / d.m).mean(), "p90/m": (d.statline_p90 / d.m).mean(),
        "real_sd/m": d.r.std() / d.m.mean()}))
    print("\nshipped model spread at same mean bins (2026):"); print(S2.round(3).to_string())

    print("\n######## TASK4 candidate fixes, LOWO (fit on one week, score other; averaged over both folds), cut>8")
    R4, M4 = lowo(D8)
    print(R4.round(3).to_string(index=False)); print(M4.round(3).to_string())
    print("\nfull-sample fitted params (what would ship):")
    print(" k_halfwidth global:", f_k_global(D8).ks); print(" k_halfwidth per-pos:", f_k_pos(D8).ks)
    for c in (3,):
        D3 = frame(3); R3, M3 = lowo(D3); print("\nLOWO on cut>3 frame (n=%d):" % len(D3)); print(M3.round(3).to_string())
        print(" cut>3 fitted k_lo by week:", [round(f_k_lower_only(D3[D3.week == w]).klo, 2) for w in (1, 2)], " full:", round(f_k_lower_only(D3).klo, 2))
    print(" normal k:", round(f_sigma_normal_k(D8).k, 3), " zmap q:", f_zmap(D8).q.round(3))
    for w in (1, 2):
        print(f" wk{w}-only fits: kglob", f_k_global(D8[D8.week == w]).ks, " normal k", round(f_sigma_normal_k(D8[D8.week == w]).k, 3))


def actual_tds(D):
    """Actual rush+rec TDs from nflverse weekly_stats_2026 vs projected (Poisson var = mean)."""
    p = REPO / "data/weekly_stats_2026.parquet"
    if not p.exists():
        return None
    W = pd.read_parquet(p)
    idc = "player_id" if "player_id" in W else W.columns[0]
    tdcols = [c for c in ("rushing_tds", "receiving_tds") if c in W]
    if not tdcols:
        return "weekly_stats_2026 has no td cols: " + ",".join(W.columns[:30])
    W = W[W.season_type.eq("REG") if "season_type" in W else slice(None)]
    W["tds"] = W[tdcols].fillna(0).sum(axis=1)
    m = D[D.position != "QB"].merge(W[[idc, "week", "tds"]].rename(columns={idc: "player_id"}), on=["player_id", "week"], how="left")
    m = m.dropna(subset=["tds"])
    out = m.groupby("position").apply(lambda d: pd.Series({"n": len(d), "exp_td": d.exp_td.mean(), "act_td": d.tds.mean(),
                                                            "var_act": d.tds.var(), "poisson_var(E[mean])": d.exp_td.mean(),
                                                            "P(td>=2) act": (d.tds >= 2).mean(),
                                                            "P(td>=2) poisson": (1 - np.exp(-d.exp_td) * (1 + d.exp_td)).mean()}))
    return out.round(3).to_string()


if __name__ == "__main__":
    main()
