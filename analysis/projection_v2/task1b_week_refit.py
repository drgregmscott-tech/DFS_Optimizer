"""Task 1b: does the salary blend help at week >= 3?  (salary-only term, same eval as task1_shrinkage.py)

final = E + a + w*(S - E), S = per-pos salary line. Fit per single week (wk1..wk6, wk7+) x pos group (QB/SKILL)
leave-one-season-out on 2021-25, plus a smooth model pooled over wk3-18:
    w(gp) = b0 + b1/(1 + cur_gp)      (cur_gp = player games played this season to date, nflverse)
Reports per-week held-out MAE / RMSE / slate Spearman by season, pos, tier, salary coef left on top, 2026 wk3 prod.

Also: 'public' refit (no FC data): salary line from rotoguru 2014-21 (public DK salary + DK pts), weights fit on
2021 rows only with nflverse DK pts as actual and rotoguru salary. Compared with the FC-fit.
Writes the aggregate-only outputs to data/fc_history/derived/projection_v2/ (git-ignored).
"""
import io, json, os, subprocess, sys
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import spearmanr

sys.argv = [sys.argv[0], "d_sal"]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import task1_shrinkage as T1  # noqa: E402

R, OUT = T1.R, T1.OUT
LAM = T1.LAM
WEEKS = [1, 2, 3, 4, 5, 6]
HMODE = os.environ.get("SMOOTH_H", "gp")  # gp: 1/(1+cur_gp); week: 1/week (team games = week-1)


def hfun(d):
    return 1 / d.week.values if HMODE == "week" else 1 / (1 + d.cur_gp.values)


def wk_bucket(w):
    return f"wk{w}" if w <= 6 else "wk7+"


def prep():
    X = T1.add_feats(T1.load_hist())
    X["wb"] = X.week.map(wk_bucket)
    return X


def fit_weeks(train, sl):
    t = T1.design(train, sl)
    t = t[t.played & t.E.notna() & ((t.E >= 3) | (t.salary >= 4000))]
    W = {}
    for (wb, pg), g in t.groupby(["wb", "pg"]):
        y = (g.act - g.E).values
        A = np.column_stack([np.ones(len(g)), g.d_sal.values])
        W[(wb, pg)] = np.linalg.solve(A.T @ A + np.diag([0, LAM]), A.T @ y)
    # smooth pooled wk3+: a + (b0 + b1/(1+gp)) * d_sal, per pg
    S = {}
    for pg, g in t[t.week >= 3].groupby("pg"):
        y = (g.act - g.E).values; h = hfun(g)
        A = np.column_stack([np.ones(len(g)), g.d_sal.values, g.d_sal.values * h])
        S[pg] = np.linalg.solve(A.T @ A + np.diag([0, LAM, LAM]), A.T @ y)
    return W, S


def apply(X, sl, W, S):
    X = T1.design(X, sl)
    c = X.E.values.copy(); cs = X.E.values.copy()
    for (wb, pg), b in W.items():
        m = ((X.wb == wb) & (X.pg == pg)).values
        c[m] = X.E.values[m] + b[0] + b[1] * X.d_sal.values[m]
    for pg, b in S.items():
        m = ((X.week >= 3) & (X.pg == pg)).values
        h = hfun(X)[m]
        cs[m] = X.E.values[m] + b[0] + (b[1] + b[2] * h) * X.d_sal.values[m]
    return X.assign(cand=np.maximum(c, 0), smooth=np.maximum(cs, 0))


def pop(d):
    return d[d.played & ((d.fc >= 5) | (d.E >= 5))]


def main():
    X = prep()
    hist = X[X.season <= 2025]
    parts, per = [], []
    for s in sorted(hist.season.unique()):
        tr = hist[hist.season != s]
        sl = T1.sal_line(tr)
        W, S = fit_weeks(tr, sl)
        parts.append(apply(hist[hist.season == s], sl, W, S))
        for (wb, pg), b in W.items():
            per.append({"held": s, "wb": wb, "pg": pg, "a": b[0], "w": b[1]})
    H = pop(pd.concat(parts))
    cols = ["E", "cand", "smooth", "fc"]
    print("== LOSO fitted weights by held-out season (w on S-E)")
    P = pd.DataFrame(per)
    print(P.pivot_table(index=["wb", "pg"], columns="held", values="w").round(2).to_string())
    print("\n== LOSO population by single week")
    print(H.groupby("wb").apply(T1.metrics, cols=cols).round(3).T.to_string())

    print("\n== held-out MAE gain (E - cand, + = better) and Spearman gain by week x season")
    rows = []
    for (wb, s), g in H.groupby(["wb", "season"]):
        m = T1.metrics(g, ["E", "cand", "smooth"])
        rows.append({"wb": wb, "season": s, "n": int(m.n), "dMAE": m.mae_E - m.mae_cand, "dRho": m.rho_cand - m.rho_E,
                     "dMAE_sm": m.mae_E - m.mae_smooth, "dRho_sm": m.rho_smooth - m.rho_E})
    G = pd.DataFrame(rows)
    print(G.pivot_table(index="wb", columns="season", values="dMAE").round(3).to_string())
    print(G.pivot_table(index="wb", columns="season", values="dRho").round(3).to_string())
    print("smooth model:")
    print(G.pivot_table(index="wb", columns="season", values="dMAE_sm").round(3).to_string())
    print(G.pivot_table(index="wb", columns="season", values="dRho_sm").round(3).to_string())
    summ = G.groupby("wb").agg(seasons=("season", "size"), mae_pos=("dMAE", lambda v: int((v > 0).sum())),
                               rho_pos=("dRho", lambda v: int((v > 0).sum())), dMAE=("dMAE", "mean"),
                               sm_mae_pos=("dMAE_sm", lambda v: int((v > 0).sum())), sm_dMAE=("dMAE_sm", "mean"))
    print(summ.round(3).to_string())

    for wb in ["wk3", "wk4", "wk5", "wk6"]:
        d = H[H.wb == wb]
        print(f"\n-- {wb} by pos (MAE E/cand/smooth)")
        print(d.groupby("pos").apply(T1.metrics, cols=["E", "cand", "smooth"])[["n", "mae_E", "mae_cand", "mae_smooth", "rho_E", "rho_cand"]].round(3).to_string())
        d = d.assign(tier=pd.cut(d.salary, [0, 5499, 6999, 99999], labels=["<5.5k", "5.5-7k", "7k+"]))
        print(d.groupby("tier", observed=True).apply(T1.metrics, cols=["E", "cand", "smooth"])[["n", "mae_E", "mae_cand", "mae_smooth", "rho_E", "rho_cand"]].round(3).to_string())

    print("\n== salary coef left on top (act ~ proj + salary_k), by week")
    for wb in ["wk1", "wk2", "wk3", "wk4", "wk5", "wk6", "wk7+"]:
        d = H[H.wb == wb]; out = []
        for c in ["E", "cand", "smooth"]:
            A = np.column_stack([np.ones(len(d)), d[c], d.salary / 1000]); y = d.act.values
            b, *_ = np.linalg.lstsq(A, y, rcond=None); res = y - A @ b
            se = np.sqrt(np.diag(np.linalg.inv(A.T @ A)) * (res @ res) / (len(y) - 3))
            out.append(f"{c} {b[2]:+.2f} (t {b[2]/se[2]:.1f})")
        print(f"  {wb:5s} n={len(d):5d}  " + "  ".join(out))

    # full fit + 2026 wk3 production
    sl = T1.sal_line(hist)
    W, S = fit_weeks(hist, sl)
    print("\n== full 2021-25 fit weights")
    for k, b in sorted(W.items()):
        print(f"  {k}: a={b[0]:+.3f} w={b[1]:+.3f}")
    for pg, b in S.items():
        print(f"  smooth {pg}: a={b[0]:+.3f} b0={b[1]:+.3f} b1={b[2]:+.3f}")
    feats = pd.read_parquet(T1.U / "usage_features.parquet", columns=["player_id", "season", "week", "prev_gp", "prev_dk", "cur_gp", "cur_dk_mean", "dk_ewm4"])
    rows = []
    for sub in ["main", "early", "afternoon"]:
        txt = subprocess.run(["git", "-C", str(R), "show", f"HEAD:output/final_projections_dk_dk_classic_wk3_{sub}_27Sep2026.csv"],
                             capture_output=True, text=True, encoding="utf-8", check=True).stdout
        o = pd.read_csv(io.StringIO(txt), dtype={"player_id": str})
        a = pd.read_csv(R / f"data/results_raw_dk_2026_wk3_{sub}.csv"); a["player_name"] = a.player_name.str.strip()
        o = o[o.position.isin(["QB", "RB", "WR", "TE"])].merge(a, on="player_name", how="inner")
        o = o.rename(columns={"position": "pos", "final_projection": "E", "actual_fpts": "act"})
        o["season"], o["week"], o["sub"] = 2026, 3, sub
        rows.append(o[["season", "week", "sub", "player_id", "pos", "salary", "E", "act"]])
    W3 = pd.concat(rows).merge(feats, on=["player_id", "season", "week"], how="left")
    W3["cur_gp"] = W3.cur_gp.fillna(0); W3["prev_gp"] = W3.prev_gp.fillna(0)
    W3["pg"] = np.where(W3.pos == "QB", "QB", "SKILL"); W3["wb"] = "wk3"; W3["played"] = True; W3["sk"] = W3["sub"]
    W3 = apply(W3, sl, W, S)
    P3 = W3[(W3.E >= 5) & (W3.act != 0)]
    print("\n== 2026 wk3 production files, per-week wk3 weights + smooth")
    print(P3.groupby("sub").apply(T1.metrics, cols=["E", "cand", "smooth"]).round(3).T.to_string())

    # ---- public refit (no FC): rotoguru salary line 2014-21; weights on 2021 w/ nflverse DK pts
    rg = pd.concat([pd.read_csv(R / f"data/rotoguru_actuals_dk_{y}.csv") for y in range(2014, 2022)])
    rg = rg[rg.rotoguru_position.isin(["QB", "RB", "WR", "TE"]) & (rg.salary > 0)]
    rg_played = rg[rg.actual_points.notna()]
    slp = {p: np.polyfit(g.salary / 1000, g.actual_points, 1) for p, g in rg_played.groupby("rotoguru_position")}
    print("\n== salary lines: FC 2021-25 vs public rotoguru 2014-21 (m, b)")
    for p in ["QB", "RB", "WR", "TE"]:
        print(f"  {p}: FC {sl[p][0]:.2f}/{sl[p][1]:+.2f}   public {slp[p][0]:.2f}/{slp[p][1]:+.2f}")
    uw = pd.read_parquet(T1.U / "usage_weekly.parquet", columns=["player_id", "season", "week", "dk"])
    Xn = X.merge(uw, on=["player_id", "season", "week"], how="left")
    Xn["act_nv"] = np.where(Xn.played, Xn.dk.fillna(0), 0.0)
    ok = Xn[Xn.played]
    print(f"  nflverse vs FC actual: corr {ok[['act','act_nv']].corr().iloc[0,1]:.4f}, mean abs diff {np.abs(ok.act-ok.act_nv).mean():.3f}")
    # public weights: fit on all 2021-25 rows but S from public line and act from nflverse
    Xp = Xn.assign(act=Xn.act_nv)
    Wp, _ = fit_weeks(Xp[Xp.season <= 2025], slp)
    print("== public-line + nflverse-act weights (2021-25 E rows)")
    for k in sorted(W):
        print(f"  {k}: FC a={W[k][0]:+.2f} w={W[k][1]:+.3f} | public a={Wp[k][0]:+.2f} w={Wp[k][1]:+.3f}")
    # LOSO with public line/act, evaluated on FC act (same eval)
    parts = []
    for s in sorted(hist.season.unique()):
        tr = Xp[(Xp.season <= 2025) & (Xp.season != s)]
        Wq, Sq = fit_weeks(tr, slp)
        parts.append(apply(hist[hist.season == s], slp, Wq, Sq))
    Hp = pop(pd.concat(parts))
    print("== LOSO public-fit, eval FC act")
    print(Hp.groupby("wb").apply(T1.metrics, cols=["E", "cand"]).round(3).T.to_string())
    art = {"sal_line_fc": {p: list(map(float, c)) for p, c in sl.items()},
           "sal_line_public": {p: list(map(float, c)) for p, c in slp.items()},
           "w_fc": {f"{a}|{b}": list(map(float, v)) for (a, b), v in W.items()},
           "w_public": {f"{a}|{b}": list(map(float, v)) for (a, b), v in Wp.items()},
           "smooth_fc": {k: list(map(float, v)) for k, v in S.items()}}
    (OUT / f"task1b_week_refit_{HMODE}.json").write_text(json.dumps(art, indent=1))
    pd.concat([H.assign(src="fc")]).to_parquet(OUT / f"task1b_loso_hist_{HMODE}.parquet")
    # production config: weeks whose per-week LOSO MAE gain was > 0 (tie counted as not-a-loss) in >= 4 held-out
    # seasons (wk1-4 have only 4 seasons: 2024 FC export starts wk5). wk3/wk4/wk5 fail -> absent (w = 0).
    ship = ["wk1", "wk2", "wk6", "wk7+"]
    cfg = {"_note": "Early-season salary blend (task1b_week_refit.py). final = E + a + w*(S - E), S = m*salary_k + b per pos; "
                    "QB/RB/WR/TE, DK classic only, after the projection stack. Weeks absent = no blend. "
                    "Fit on FC-history 2021-25 (FC-derived salaries/actuals): git-ignored, do not commit.",
           "fit": "LOSO 2021-25, ridge lam=30 on w, per week x {QB, SKILL}",
           "max_week": 18,
           "sal_line": {p: list(map(float, sl[p])) for p in ["QB", "RB", "WR", "TE"]},
           "weeks": {k.replace("wk", ""): {pg: {"a": float(W[(k, pg)][0]), "w": float(W[(k, pg)][1])} for pg in ["QB", "SKILL"]}
                     for k in ship}}
    (OUT / "early_season_blend_config.json").write_text(json.dumps(cfg, indent=1))


if __name__ == "__main__":
    main()
