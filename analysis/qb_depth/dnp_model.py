"""Pre-lock P(zero offensive snaps | not Out/Doubtful) for players we project > 5 (research; no FC data inside).
LOSO by season 2021-25 on the guarded history rebuild (dnp_frame.parquet). L2 logistic (scipy).
Reports AUC, calibration, catches at thresholds, and projection cost/benefit (EV shrink vs hard zero)."""
import json, os, sys
import numpy as np, pandas as pd
from scipy.optimize import minimize
from scipy.stats import rankdata

R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
D = os.path.join(R, "data/fc_history/derived/qb_depth")
MIN_PROJ = 5.0
NOQ = "--no-q" in sys.argv  # depth-only universe: players with no injury designation
TAG = "_noq" if NOQ else ""


def feats(o):
    f = pd.DataFrame(index=o.index)
    for p in ["QB", "RB", "WR", "TE"]:
        f[p] = (o.position == p).astype(float)
    f["lproj"] = np.log(o.final_projection.clip(lower=1))
    f["sal_k"] = o.salary / 1000
    pr, sr = o.proj_rank.clip(upper=4), o.sal_rank.clip(upper=4)
    f["not_top_proj"] = (pr > 1).astype(float)
    f["proj_rank"] = pr
    f["sal_below_proj_rank"] = (sr > pr).astype(float)  # a teammate at the position is priced higher than his proj rank implies
    f["QB2"] = ((o.position == "QB") & (pr > 1)).astype(float)
    f["QB_sal_not_top"] = ((o.position == "QB") & (sr > 1)).astype(float)
    f["gap_to_top"] = o.gap_to_top.clip(upper=20) / 10
    miss = o.snap_l3.isna()
    f["snap_miss"] = miss.astype(float)
    f["snap_l1"] = o.snap_l1.fillna(0)
    f["snap_l3"] = o.snap_l3.fillna(0)
    f["n_snap_l3_0"] = ((o.n_snap_l3.fillna(0) == 0) & ~miss).astype(float)
    f["never_snapped"] = (o.snap_max_ever.fillna(0) <= 0).astype(float)
    f["QB_snap_l3"] = f.QB * f.snap_l3
    f["q"] = (o.desig == "Questionable").astype(float)
    f["q_dnp"] = f.q * (o.practice_status.fillna("").str.contains("Did Not")).astype(float)
    f["q_lim"] = f.q * (o.practice_status.fillna("").str.contains("Limited")).astype(float)
    f["wk1"] = (o.week == 1).astype(float)
    f["gp_low"] = (o.games_played.fillna(0) < 2).astype(float)
    return f


def fit_logit(Xm, y, lam=1.0):
    mu, sd = Xm.mean(0), Xm.std(0) + 1e-9
    Z = np.c_[np.ones(len(Xm)), (Xm - mu) / sd]

    def nll(b):
        z = Z @ b
        return np.sum(np.logaddexp(0, z) - y * z) + lam * np.sum(b[1:] ** 2)

    def grad(b):
        p = 1 / (1 + np.exp(-(Z @ b)))
        g = Z.T @ (p - y); g[1:] += 2 * lam * b[1:]
        return g
    b = minimize(nll, np.zeros(Z.shape[1]), jac=grad, method="L-BFGS-B").x
    return b, mu, sd


def pred_logit(model, Xm):
    b, mu, sd = model
    return 1 / (1 + np.exp(-(np.c_[np.ones(len(Xm)), (Xm - mu) / sd] @ b)))


def auc(y, p):
    r = rankdata(p); n1 = y.sum(); n0 = len(y) - n1
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def load():
    o = pd.read_parquet(os.path.join(D, "dnp_frame.parquet"))
    ws = pd.concat([pd.read_parquet(os.path.join(R, f"data/weekly_stats_{s}.parquet"), columns=["player_id", "season", "week", "season_type", "fantasy_points_ppr", "passing_yards", "rushing_yards", "receiving_yards"]) for s in range(2021, 2026)])
    ws = ws[ws.season_type == "REG"].drop_duplicates(["player_id", "season", "week"])
    ws["dk"] = ws.fantasy_points_ppr + 3 * (ws.passing_yards >= 300) + 3 * (ws.rushing_yards >= 100) + 3 * (ws.receiving_yards >= 100)
    o = o.merge(ws[["player_id", "season", "week", "dk"]], on=["player_id", "season", "week"], how="left")
    o["act"] = np.where(o.zero_off, 0.0, o.dk.fillna(0))
    # universe: proj>5, not Friday Out/Doubtful, on the game-day 53 (ACT or INA), game was played by the team
    team_played = o.groupby(["season", "week", "team"]).offense_snaps.transform(lambda s: s.fillna(0).sum() > 0)
    U = o[(o.final_projection > MIN_PROJ) & ~o.desig.isin(["Out", "Doubtful"]) & o.status.isin(["ACT", "INA"]) & team_played].copy()
    if NOQ:
        U = U[U.desig == "None"]
    U["y"] = U.zero_off.astype(float)
    return U


def main():
    U = load()
    F = feats(U); cols = list(F.columns); U["p"] = np.nan
    nsl = U[["season", "week"]].drop_duplicates().shape[0]
    print(f"universe rows {len(U)} over {nsl} slates; base rate {U.y.mean():.4f} ({U.y.sum():.0f} zero-snap rows, {U.y.sum()/nsl:.2f}/slate)")
    print("  zero-snap by status/pos per slate:", (U[U.y == 1].groupby(["status", "position"]).size() / nsl).round(2).to_dict())
    for s in sorted(U.season.unique()):
        tr, te = U.season != s, U.season == s
        U.loc[te, "p"] = pred_logit(fit_logit(F[tr].values, U.y[tr].values), F[te].values)
    print("\nLOSO AUC by season:", {int(s): round(auc(g.y.values, g.p.values), 3) for s, g in U.groupby("season")}, " all", round(auc(U.y.values, U.p.values), 3))
    for p_ in ["QB", "RB", "WR", "TE"]:
        g = U[U.position == p_]
        if g.y.sum() >= 5:
            print(f"  {p_}: n {len(g)} pos-rate {g.y.mean():.3f} AUC {auc(g.y.values, g.p.values):.3f}")
    # simple baseline rules for comparison
    base = {"not top proj at pos (QB2/RB2+..)": F.not_top_proj, "snap_l3 < .1": (U.snap_l3.fillna(0) < .1).astype(float), "Questionable": F.q}
    for k, v in base.items():
        print(f"  baseline {k}: AUC {auc(U.y.values, v.values + 1e-6 * U.p.values):.3f}")
    print("\nCalibration (LOSO) by predicted-p bin: n, mean p, observed rate")
    U["bin"] = pd.cut(U.p, [0, .01, .02, .05, .1, .2, .35, .5, 1])
    print(U.groupby("bin", observed=True).agg(n=("y", "size"), p=("p", "mean"), obs=("y", "mean")).round(3).to_string())
    print("\nThreshold table (LOSO): flagged/slate, caught/slate, precision, recall; real-player risk = flagged rows that played >=50% snaps")
    for t in [.1, .2, .3, .4, .5, .6]:
        fl = U.p >= t
        big = fl & (U.offense_pct.fillna(0) >= .5)
        print(f"  p>={t:.1f}: flagged {fl.sum()/nsl:.2f}/slate, caught {(fl & (U.y==1)).sum()/nsl:.2f}/slate, precision {U.y[fl].mean():.2f}, recall {U.y[fl].sum()/U.y.sum():.2f}, "
              f"flagged real starters(>=50% snaps) {big.sum()} rows ({big.sum()/nsl:.2f}/slate), their mean DK pts {U.act[big].mean():.1f}")
    print("\nProjection cost/benefit (LOSO), universe rows: sum sq err and MAE, per slate")
    U["ev"] = U.final_projection * (1 - U.p)
    for t in [.3, .5]:
        U[f"hz{t}"] = np.where(U.p >= t, 0.0, U.final_projection)
    for c in ["final_projection", "ev", "hz0.3", "hz0.5"]:
        e = U[c] - U.act
        print(f"  {c:16s} MAE {e.abs().mean():.3f}  RMSE {np.sqrt((e**2).mean()):.3f}  bias {e.mean():+.3f}   SSE/slate {(e**2).sum()/nsl:.0f}")
    print("  EV-shrink: mean shrink on non-DNP rows %.3f pts, on DNP rows %.2f pts" % ((U.final_projection * U.p)[U.y == 0].mean(), (U.final_projection * U.p)[U.y == 1].mean()))
    # production-style EV shrink only where p is meaningful (avoid shaving every player a hair)
    for t in [.1, .2]:
        c = f"ev_ge{t}"; U[c] = np.where(U.p >= t, U.ev, U.final_projection); e = U[c] - U.act
        print(f"  {c:16s} MAE {e.abs().mean():.3f}  RMSE {np.sqrt((e**2).mean()):.3f}  bias {e.mean():+.3f}   SSE/slate {(e**2).sum()/nsl:.0f}")
    print("\nPer-season SSE/slate gain of EV shrink (p>=.2) vs none:", {int(s): round((((g.final_projection-g.act)**2).sum()-((g["ev_ge0.2"]-g.act)**2).sum())/g[["week"]].drop_duplicates().shape[0], 1) for s, g in U.groupby("season")})
    model = fit_logit(F.values, U.y.values)
    b, mu, sd = model
    print("\nFull-fit coefficients (standardized):")
    for c, v in sorted(zip(cols, b[1:]), key=lambda x: -abs(x[1])):
        print(f"  {c:20s} {v:+.3f}")
    json.dump({"_note": "P(zero offensive snaps | not Out/Doubtful), proj>5 QB/RB/WR/TE, analysis/qb_depth/dnp_model.py; public nflverse labels, "
                        "fit on guarded history rebuild of FC slates.", "cols": cols, "b": b.tolist(), "mu": mu.tolist(), "sd": sd.tolist(), "min_proj": MIN_PROJ},
              open(os.path.join(D, f"dnp_model_candidate{TAG}_2026-09-29.json"), "w"), indent=1)
    U.drop(columns="bin").to_parquet(os.path.join(D, f"dnp_eval{TAG}.parquet"))
    top = U.sort_values("p", ascending=False).head(30)
    print(top[["season", "week", "player_name", "position", "team", "salary", "final_projection", "proj_rank", "snap_l3", "desig", "status", "p", "y", "act"]].round(2).to_string(index=False))


if __name__ == "__main__":
    main()
