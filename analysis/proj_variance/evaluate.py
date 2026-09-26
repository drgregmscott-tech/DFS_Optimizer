"""Evaluate statline_variance variants from capture_variant.py runs (research only; NO FC data in this file).
Frame per tag = production-faithful build + MC draw summaries + actuals. Sigma recal refit (a*raw^b via
fit_sigma_recalibration.fit_position) under forward (fit 2021-22 -> test 2023+) and leave-one-season-out schemes;
QR p90 = a+b*final per position (same schemes).
Writes data/fc_history/derived/proj_variance/{frame_<tag>.parquet, frameS_<tag>.parquet, eval_report.txt}
    python analysis/proj_variance/evaluate.py --tags cur vol2021 vol2018
"""
import argparse, glob, os, sys
import numpy as np, pandas as pd
from scipy.optimize import minimize
R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(R, "scripts"))
DER = os.path.join(R, "data/fc_history/derived"); OUT = os.path.join(DER, "proj_variance")
Q = np.arange(1, 100)
LOG = None


def P(*a):
    s = " ".join(str(x) for x in a); print(s); LOG.write(s + "\n"); LOG.flush()


pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500); pd.set_option("display.max_columns", 40)


def build(tag):
    d = os.path.join(OUT, tag)
    fc = pd.read_csv(os.path.join(DER, "fc_master_mapped.csv"), low_memory=False, dtype={"player_id": str})
    fc = fc[(fc.site == "dk") & (fc.slate_kind == "classic") & (fc.slate_raw == "main") & fc.player_id.notna()
            & fc.pos.isin(["QB", "RB", "WR", "TE", "DST"])].drop_duplicates(["season", "week", "player_id"])
    fc = fc[["season", "week", "player_id", "salary", "score"]]
    o = pd.concat([pd.read_csv(f, dtype={"player_id": str}) for f in glob.glob(os.path.join(d, "proj/proj_*.csv"))])
    o = o.drop_duplicates(["season", "week", "player_id"])
    keep = ["season", "week", "player_id", "position", "final_projection", "sigma", "statline_p10", "statline_p90", "stack_delta",
            "proj_pass_yd", "proj_pass_td", "proj_rush_att", "proj_rush_yd", "proj_rush_td", "proj_targets", "proj_rec_yd", "proj_rec_td"]
    X = fc.merge(o[keep], on=["season", "week", "player_id"], how="inner")
    W = pd.concat([pd.read_parquet(os.path.join(R, f"data/weekly_stats_{s}.parquet"))[["player_id", "season", "week", "passing_yards",
         "passing_tds", "carries", "rushing_yards", "rushing_tds", "targets", "receiving_yards", "receiving_tds"]] for s in range(2021, 2027)])
    X = X.merge(W.drop_duplicates(["season", "week", "player_id"]), on=["season", "week", "player_id"], how="left", indicator=True)
    X["played"] = (X._merge == "both") | (X.position == "DST"); X = X.drop(columns="_merge")
    X["act"] = X.score.fillna(0.0).where(X.played, 0.0)
    D = pd.concat([pd.read_parquet(f) for f in glob.glob(os.path.join(d, "draws/draws_*.parquet"))]).drop_duplicates(["season", "week", "player_id"])
    X = X.merge(D, on=["season", "week", "player_id"], how="left")
    X = X[X.final_projection > 0].reset_index(drop=True)
    X["err"] = X.act - X.final_projection
    sh = X.stack_delta.fillna(0).values[:, None]
    qs = X[[f"q{q}" for q in Q]].values + sh
    ok = np.isfinite(qs[:, 0]); a = X.act.values; pit = np.full(len(X), np.nan)
    rng = np.random.default_rng(3)
    for i in np.where(ok)[0]:
        lo, hi = (qs[i] < a[i]).mean(), (qs[i] <= a[i]).mean()
        pit[i] = lo + rng.random() * (hi - lo) if hi - lo > 0.015 else np.interp(a[i], qs[i], Q / 100, left=0.0, right=1.0)
    X["pit"] = pit; X["mc_p90"] = X.q90 + X.stack_delta.fillna(0)
    X["ptier"] = pd.cut(X.final_projection, [0, 5, 8, 12, 16, 20, 99], labels=["<5", "5-8", "8-12", "12-16", "16-20", "20+"])
    X.to_parquet(os.path.join(OUT, f"frame_{tag}.parquet"))
    return X


def fit_recal(tr):
    import fit_sigma_recalibration as fsr
    out = {}
    for p, g in tr[tr.played & (tr.position != "DST")].groupby("position"):
        g = pd.DataFrame(dict(sigma=g.pts_sd.values, actual_points=g.act.values, final_projection=g.final_projection.values)).dropna()
        out[p] = fsr.fit_position(g, p, 10)
    return out


def apply_recal(X, par):
    s = X.sigma.copy()  # DST keeps its production sigma
    for p, e in par.items():
        m = (X.position == p) & (X.pts_sd > 0)
        s[m] = e["a"] * np.clip(X.pts_sd[m], *e["sigma_fit_range"]) ** e["b"]
    return s


def qr(x, y, tau):
    def f(t):
        r = y - t[0] - t[1] * x
        return np.mean(np.maximum(tau * r, (tau - 1) * r))
    b0 = np.polyfit(x, y, 1)[::-1]
    return minimize(f, b0, method="Nelder-Mead", options=dict(xatol=1e-6, fatol=1e-9, maxiter=4000)).x


def schemes(X):
    X = X.copy(); X["sig_fwd"] = apply_recal(X, fit_recal(X[X.season <= 2022]))
    X["sig_loso"] = np.nan; X["p90qr_loso"] = np.nan; X["p90qr_fwd"] = np.nan
    for s in sorted(X.season.unique()):
        tr = X[(X.season != s) & (X.season <= 2025)]; m = X.season == s
        X.loc[m, "sig_loso"] = apply_recal(X[m], fit_recal(tr))
    for p in ["QB", "RB", "WR", "TE"]:
        pl = X[X.played & (X.position == p)]
        t = pl[pl.season <= 2022]; cf = qr(t.final_projection.values, t.act.values, .9)
        mp_ = X.position == p; X.loc[mp_, "p90qr_fwd"] = cf[0] + cf[1] * X.loc[mp_, "final_projection"]
        for s in sorted(X.season.unique()):
            t = pl[(pl.season != s) & (pl.season <= 2025)]; c = qr(t.final_projection.values, t.act.values, .9)
            m = mp_ & (X.season == s); X.loc[m, "p90qr_loso"] = c[0] + c[1] * X.loc[m, "final_projection"]
    X["p90qr_fwd"] = X.p90qr_fwd.fillna(X.statline_p90); X["p90qr_loso"] = X.p90qr_loso.fillna(X.statline_p90)
    return X


def components(X, lab):
    PAIRS = {"pass": ("passing_yards", "passing_tds", "proj_pass_yd", "proj_pass_td", "sim_pass_yd", "sim_pass_td"),
             "rush": ("rushing_yards", "rushing_tds", "proj_rush_yd", "proj_rush_td", "sim_rush_yd", "sim_rush_td"),
             "rec": ("receiving_yards", "receiving_tds", "proj_rec_yd", "proj_rec_td", "sim_rec_yd", "sim_rec_td")}
    USE = {"QB": ["pass", "rush"], "RB": ["rush", "rec"], "WR": ["rec"], "TE": ["rec"]}
    rows = []
    Y = X[X.played & (X.position != "DST")]
    for pos, cs in USE.items():
        for c in cs:
            ya, ta, yp, tp, ys, ts = PAIRS[c]
            for seas in [2021, 2022, 2023, 2024, 2025, "23+"]:
                g = Y[(Y.position == pos) & ((Y.season >= 2023) if seas == "23+" else (Y.season == seas))]
                g = g[g[yp] > (150 if c == "pass" else 5)]
                ry = g[ya].fillna(0) - g[yp]; rt = g[ta].fillna(0) - g[tp]
                rows.append(dict(v=lab, pos=pos, c=c, season=str(seas), yd_act=ry.std(), yd_sim=np.sqrt((g[ys + "_sd"] ** 2).mean()),
                                 td_act=rt.std(), td_sim=np.sqrt((g[ts + "_sd"] ** 2).mean()), corr_act=np.corrcoef(ry, rt)[0, 1],
                                 corr_sim=g["sim_c_" + ys[4:]].mean()))
    T = pd.DataFrame(rows); T["yd_ratio"] = T.yd_sim / T.yd_act; T["td_ratio"] = T.td_sim / T.td_act
    return T


def calib(X, sig, p90, lab):
    Y = X[X.played & (X.position != "DST")].copy(); Y["z"] = Y.err / Y[sig]

    def f(g):
        h = np.histogram(g.pit.dropna(), bins=10, range=(0, 1))[0] / max(g.pit.notna().sum(), 1)
        return pd.Series(dict(n=len(g), z_sd=g.z.std(), below10=(g.act < g.statline_p10).mean(), above90=(g.act > g[p90]).mean(),
                              above_mcp90=(g.act > g.mc_p90).mean(), pit_maxdev=np.abs(h - .1).max(), pit_sd=g.pit.std()))
    Y["season"] = Y.season.astype(str)
    Z = Y[Y.season >= "2023"].assign(season="23+")
    return pd.concat([Y, Z]).groupby(["position", "season"]).apply(f).assign(v=lab)


def main():
    global LOG
    ap = argparse.ArgumentParser(); ap.add_argument("--tags", nargs="+", default=["cur", "vol2021", "vol2018"])
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args()
    LOG = open(os.path.join(OUT, "eval_report.txt"), "w")
    F = {}
    for t in a.tags:
        f = os.path.join(OUT, f"frame_{t}.parquet")
        F[t] = pd.read_parquet(f) if os.path.exists(f) and not a.rebuild else build(t)
        F[t] = schemes(F[t]); F[t].to_parquet(os.path.join(OUT, f"frameS_{t}.parquet"))
    base = F[a.tags[0]]
    P("== MEANS: final_projection variant vs", a.tags[0], "(same player-slates)")
    for t in a.tags[1:]:
        m = base.merge(F[t][["season", "week", "player_id", "final_projection", "pts_mean"]], on=["season", "week", "player_id"], suffixes=("", "_v"))
        d = m.final_projection_v - m.final_projection
        P(f"  {t}: n {len(m)} (base {len(base)}, var {len(F[t])}) mean d {d.mean():+.4f} sd {d.std():.4f} |d|max {d.abs().max():.3f} "
          f"p99|d| {d.abs().quantile(.99):.3f} corr {np.corrcoef(m.final_projection, m.final_projection_v)[0, 1]:.6f}; by pos mean d "
          + str(m.assign(d=d).groupby("position").d.mean().round(4).to_dict()))
        big = m.assign(d=d)[d.abs() > 0.5]
        if len(big):
            P("   |d|>0.5 rows:", len(big), big.groupby("position").size().to_dict())
    P("\n== COMPONENTS (played): simulated/actual residual sd ratios, sim yards-TD corr")
    T = pd.concat([components(F[t], t) for t in a.tags])
    P(T.pivot_table(index=["pos", "c", "season"], columns="v", values=["yd_ratio", "td_ratio", "corr_sim"]).round(3).to_string())
    P("  actual corr by season:", T[T.v == a.tags[0]].set_index(["pos", "c", "season"]).corr_act.round(3).to_dict())
    P("\n== CALIBRATION by pos x season. |prod = production sigma column (old recal) & raw MC p90; |loso, |fwd = refit recal + QR p90")
    rows = []
    for t in a.tags:
        rows += [calib(F[t], "sigma", "statline_p90", f"{t}|prod"), calib(F[t], "sig_loso", "p90qr_loso", f"{t}|loso"),
                 calib(F[t], "sig_fwd", "p90qr_fwd", f"{t}|fwd")]
    C = pd.concat(rows).reset_index()
    C.to_csv(os.path.join(OUT, "calib.csv"), index=False)
    for col in ["z_sd", "above90", "above_mcp90", "below10", "pit_maxdev", "pit_sd"]:
        P(f"-- {col}"); P(C.pivot_table(index=["position", "season"], columns="v", values=col).round(3).to_string())
    P("\n-- 2023+ pooled by position x tier (played)")
    for t in a.tags:
        Y = F[t][F[t].played & (F[t].position != "DST") & (F[t].season >= 2023)]
        P(t); P(Y.groupby(["position", "ptier"], observed=True).apply(lambda g: pd.Series(dict(n=len(g), zsd_prod=(g.err / g.sigma).std(),
            zsd_loso=(g.err / g.sig_loso).std(), zsd_fwd=(g.err / g.sig_fwd).std(), pit_sd=g.pit.std(), above_mcp90=(g.act > g.mc_p90).mean(),
            above_qr=(g.act > g.p90qr_loso).mean(), rawsd=np.sqrt((g.pts_sd ** 2).mean()), realized=g.err.std()))).round(3).to_string())
    LOG.close()


if __name__ == "__main__":
    main()
