"""Task 1: early-season shrinkage/blend layer on top of the engine projection.

    final = E + a + w_sal*(S - E) + w_prev*(P - E) + w_cur*(C - E) + w_ewm*(F - E)

  E    = engine projection (regenerated harness; wk1 = production-faithful prior-season lookback 'prod')
  S    = salary-implied DK pts (per-position linear fit of actual on salary, training seasons only)
  P    = prior-season DK pts/game, shrunk to S by prior games played: (gp*ppg + K*S)/(gp + K)
  C    = current-season DK pts/game to date (0 when cur_gp == 0; its weight is then irrelevant)
  F    = career recency-weighted DK pts/game (EWMA halflife 4 games, crosses seasons)
Weights fit by ridge (shrink to 0 = "trust engine") separately per week bucket x position group (QB / skill),
leave-one-season-out on 2021-25 FC-history main slates; then fit on all 2021-25 and applied to 2026 wk1-3.

FC-derived outputs (history uses FC 'score' as actual, FC projection as comparator) -> printed + written only to
data/fc_history/derived/projection_v2/ (git-ignored). This script itself contains no FC data.
"""
import io, json, subprocess, sys
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import spearmanr

R = Path(__file__).resolve().parents[2]
DER = R / "data/fc_history/derived"; OUT = DER / "projection_v2"; OUT.mkdir(parents=True, exist_ok=True)
U = R / "data/nflverse_usage"
K_PREV = 4.0
LAM = 30.0
WB = [("wk1", 1, 1), ("wk2", 2, 2), ("wk3", 3, 3), ("wk4-6", 4, 6), ("wk7+", 7, 18)]
TERMS = sys.argv[1].split(",") if len(sys.argv) > 1 else ["d_sal", "d_prev", "d_cur", "d_ewm"]
TAG = "" if len(sys.argv) <= 1 else "_" + "-".join(TERMS)


def wbucket(w):
    for n, lo, hi in WB:
        if lo <= w <= hi:
            return n


def load_hist():
    X = pd.read_parquet(DER / "proj_early_season/players.parquet")
    X = X[X.pos.isin(["QB", "RB", "WR", "TE"])].copy()
    X["E"] = np.where((X.week == 1) & X.final_projection_prod.notna(), X.final_projection_prod, X.final_projection)
    return X[["season", "week", "player_id", "player", "pos", "team", "salary", "fc", "act", "played", "E", "games_played"]]


def add_feats(X):
    F = pd.read_parquet(U / "usage_features.parquet",
                        columns=["player_id", "season", "week", "prev_gp", "prev_dk", "cur_gp", "cur_dk_mean", "dk_ewm4"])
    X = X.merge(F, on=["player_id", "season", "week"], how="left")
    X["cur_gp"] = X.cur_gp.fillna(0); X["prev_gp"] = X.prev_gp.fillna(0)
    X["pg"] = np.where(X.pos == "QB", "QB", "SKILL")
    X["wb"] = X.week.map(wbucket)
    X["sk"] = X.season * 100 + X.week
    return X


def sal_line(train):
    t = train[train.played & (train.act.notna())]
    return {p: np.polyfit(g.salary / 1000, g.act, 1) for p, g in t.groupby("pos")}


def design(X, sl):
    S = np.zeros(len(X))
    for p, c in sl.items():
        m = (X.pos == p).values
        S[m] = np.polyval(c, X.salary.values[m] / 1000)
    X = X.assign(S=S)
    P = np.where(X.prev_gp > 0, (X.prev_gp * X.prev_dk.fillna(0) + K_PREV * X.S) / (X.prev_gp + K_PREV), X.S)
    C = np.where(X.cur_gp > 0, X.cur_dk_mean.fillna(0), X.E)
    Fm = np.where(X.dk_ewm4.notna(), X.dk_ewm4, X.S)
    X = X.assign(P=P, C=C, Fm=Fm, d_sal=X.S - X.E, d_prev=P - X.E, d_cur=C - X.E, d_ewm=Fm - X.E)
    return X


def fit_cell(t):
    y = (t.act - t.E).values
    A = np.column_stack([np.ones(len(t))] + [t[c].values for c in TERMS])
    pen = np.diag([0.0] + [LAM] * len(TERMS))
    return np.linalg.solve(A.T @ A + pen, A.T @ y)


def fit(train):
    sl = sal_line(train)
    t = design(train, sl)
    t = t[t.played & (t.E.notna()) & ((t.E >= 3) | (t.salary >= 4000))]
    W = {}
    for (wb, pg), g in t.groupby(["wb", "pg"]):
        W[(wb, pg)] = fit_cell(g)
    return sl, W


def apply(X, sl, W):
    X = design(X, sl)
    cand = X.E.values.copy()
    for (wb, pg), b in W.items():
        m = ((X.wb == wb) & (X.pg == pg)).values
        A = np.column_stack([np.ones(m.sum())] + [X.loc[m, c].values for c in TERMS])
        cand[m] = X.E.values[m] + A @ b
    return X.assign(cand=np.maximum(cand, 0))


def metrics(d, cols):
    r = {"n": len(d)}
    for c in cols:
        e = d[c] - d.act
        r[f"mae_{c}"] = e.abs().mean(); r[f"rmse_{c}"] = np.sqrt((e ** 2).mean()); r[f"bias_{c}"] = e.mean()
        rho = [spearmanr(g[c], g.act).correlation for _, g in d.groupby("sk") if len(g) > 5]
        r[f"rho_{c}"] = np.nanmean(rho)
    return pd.Series(r)


def main():
    X = add_feats(load_hist())
    hist = X[X.season <= 2025]
    parts = []
    for s in sorted(hist.season.unique()):
        sl, W = fit(hist[hist.season != s])
        parts.append(apply(hist[hist.season == s], sl, W))
    H = pd.concat(parts)
    sl, W = fit(hist)
    art = {"k_prev": K_PREV, "lam": LAM, "terms": TERMS,
           "sal_line": {p: list(map(float, c)) for p, c in sl.items()},
           "weights": {f"{a}|{b}": dict(zip(["a"] + TERMS, map(float, v))) for (a, b), v in W.items()}}
    (OUT / f"shrink_weights_2021_25{TAG}.json").write_text(json.dumps(art, indent=1))
    print("== weights fit on 2021-25 (a, w_sal, w_prev, w_cur, w_ewm)")
    for k, v in art["weights"].items():
        print(f"  {k:12s} " + " ".join(f"{x:+.3f}" for x in v.values()))
    pop = lambda d: d[d.played & ((d.fc >= 5) | (d.E >= 5))]
    act = lambda d: d[(d.act > 0) & (d.fc > 0) & d.played]
    cols = ["E", "cand", "fc"]
    print("\n== LOSO history, population played & (fc>=5 | E>=5), by week bucket")
    print(pop(H).groupby("wb").apply(metrics, cols=cols).round(3).T.to_string())
    print("\n== LOSO history, ACTIVE (act>0 & fc>0), by week bucket")
    print(act(H).groupby("wb").apply(metrics, cols=cols).round(3).T.to_string())
    E12 = pop(H[H.week <= 3])
    print("\n== LOSO wk1-3 by pos")
    print(E12.groupby("pos").apply(metrics, cols=cols).round(3).T.to_string())
    E12 = E12.assign(tier=pd.cut(E12.salary, [0, 5499, 6999, 99999], labels=["<5.5k", "5.5-7k", "7k+"]))
    print("\n== LOSO wk1-3 by salary tier")
    print(E12.groupby("tier", observed=True).apply(metrics, cols=cols).round(3).T.to_string())
    print("\n== LOSO wk1-3 by season (MAE E / cand / fc)")
    print(E12.groupby("season").apply(metrics, cols=cols)[["n", "mae_E", "mae_cand", "mae_fc", "rho_E", "rho_cand", "rho_fc"]].round(3).to_string())
    # does salary residual remain?
    for lab, d in [("wk1-2", pop(H[H.week <= 2])), ("wk3+", pop(H[H.week >= 3]))]:
        for c in ["E", "cand"]:
            A = np.column_stack([np.ones(len(d)), d[c], d.salary / 1000]); y = d.act.values
            b, *_ = np.linalg.lstsq(A, y, rcond=None); res = y - A @ b
            se = np.sqrt(np.diag(np.linalg.inv(A.T @ A)) * (res @ res) / (len(y) - 3))
            print(f"  salary coef on top of {c:4s} {lab}: {b[2]:+.2f}/$1k (t {b[2]/se[2]:.1f})")
    H.to_parquet(OUT / f"task1_loso_hist{TAG}.parquet")

    # ---- 2026 held out: harness E (wk1 prod, wk2 base) with FC; guarded FIX where available
    T = X[X.season == 2026]
    T = apply(T, sl, W)
    G = pd.read_csv(R / "analysis/proj_recheck/guarded_accuracy_frame.csv", dtype={"player_id": str})
    G = G[G["sub"] == "main"].drop_duplicates(["week", "player_id"])[["week", "player_id", "FIX"]]
    T = T.merge(G, on=["week", "player_id"], how="left")
    Tf = T[T.FIX.notna()].copy()
    Tf2 = apply(Tf.drop(columns=["cand"]).assign(E=Tf.FIX), sl, W).rename(columns={"cand": "FIXcand"})
    Tf = Tf.assign(FIXcand=Tf2.FIXcand.values)
    print("\n== 2026 wk1-2 main (harness engine), population")
    print(pop(T).groupby("week").apply(metrics, cols=cols).round(3).T.to_string())
    print("\n== 2026 wk1-2 main, guarded FIX rows, active played")
    Tp = Tf[Tf.played & (Tf.act > 0)]
    print(Tp.groupby("week").apply(metrics, cols=["FIX", "FIXcand", "fc"]).round(3).T.to_string())
    print(Tp.groupby("pos").apply(metrics, cols=["FIX", "FIXcand", "fc"])[["n", "rmse_FIX", "rmse_FIXcand", "rmse_fc", "bias_FIX", "bias_FIXcand"]].round(2).to_string())
    T.to_parquet(OUT / f"task1_2026_wk12{TAG}.parquet")

    # ---- 2026 wk3: committed pre-lock production files (git HEAD) vs DK actuals; no FC
    feats = pd.read_parquet(U / "usage_features.parquet", columns=["player_id", "season", "week", "prev_gp", "prev_dk", "cur_gp", "cur_dk_mean", "dk_ewm4"])
    rows = []
    for sub in ["main", "early", "afternoon"]:
        txt = subprocess.run(["git", "-C", str(R), "show", f"HEAD:output/final_projections_dk_dk_classic_wk3_{sub}_27Sep2026.csv"],
                             capture_output=True, text=True, encoding="utf-8", check=True).stdout
        o = pd.read_csv(io.StringIO(txt), dtype={"player_id": str})
        a = pd.read_csv(R / f"data/results_raw_dk_2026_wk3_{sub}.csv")
        a["player_name"] = a.player_name.str.strip()
        o = o[o.position.isin(["QB", "RB", "WR", "TE"])].merge(a, on="player_name", how="inner")
        o = o.rename(columns={"position": "pos", "final_projection": "E", "actual_fpts": "act", "player_name": "player"})
        o["season"], o["week"], o["sub"] = 2026, 3, sub
        rows.append(o[["season", "week", "sub", "player_id", "player", "pos", "salary", "E", "act", "injury_status"]])
    W3 = pd.concat(rows).merge(feats, on=["player_id", "season", "week"], how="left")
    W3["cur_gp"] = W3.cur_gp.fillna(0); W3["prev_gp"] = W3.prev_gp.fillna(0)
    W3["pg"] = np.where(W3.pos == "QB", "QB", "SKILL"); W3["wb"] = "wk3"; W3["played"] = True; W3["sk"] = W3["sub"]
    W3 = apply(W3, sl, W)
    P3 = W3[(W3.E >= 5) & (W3.act != 0)]
    print("\n== 2026 wk3 committed pre-lock production (props/injuries on) vs actual; E>=5 & act!=0")
    print(P3.assign(season=P3["sub"]).groupby("sub").apply(metrics, cols=["E", "cand"]).round(3).T.to_string())
    print(P3.assign(season=P3["sub"]).groupby("pos").apply(metrics, cols=["E", "cand"])[["n", "mae_E", "mae_cand", "rmse_E", "rmse_cand", "bias_E", "bias_cand"]].round(2).to_string())
    W3.to_parquet(OUT / f"task1_2026_wk3{TAG}.parquet")


if __name__ == "__main__":
    main()
