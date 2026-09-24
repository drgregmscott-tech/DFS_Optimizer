"""B1: does matchup_factor help or hurt? Ablation on the GUARDED leak-free rebuilds.
usage: python analysis/proj_b1/b1_matchup.py <guarded_dir>   (writes b1_out.txt-style output to stdout + CSVs here)

Ablation method (validated, see b1_report.md sec 1): in statline_model.simulate the market factor
(matchup*vegas) multiplies ONLY yd_rate and td_rate, not volume/receptions/INT/fumbles. So
  engine_new = engine + S * (r - 1),  S = yardage+TD points from proj_* columns,
  r = (mf_new * vf_new) / (mf * vf).
Validated against a real rebuild with matchup neutralised (wk2 early): delta corr .9997, MAE .018.
Stack delta is additive and computed from engine; variants are evaluated on engine_projection (primary)
and engine_new + stack_delta ("final", secondary; assumes stack delta unchanged).
DST excluded: its matchup_factor is display-only (proj / league mean) and is never applied.
Player set fixed across variants: shipped final_projection > 8, alive, with actual; QB/RB/WR/TE.
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
rng = np.random.default_rng(0)


def rk(x):
    return pd.Series(np.asarray(x)).rank().to_numpy()


def frame():
    L = pd.read_csv(REPO / "data/projection_error_log.csv", dtype={"player_id": str})
    rows = []
    for sid in SL:
        f = pd.read_csv(S / f"final_projections_dk_{sid}.csv", dtype={"player_id": str})
        f = f[f.position.isin(NTOP) & (f.final_projection > 8)]
        if "injury_status" in f:
            f = f[f.injury_status != "OUT"]
        a = L[L.slate_id == sid].drop_duplicates("player_id").set_index("player_id").actual_fpts
        f = f.assign(act=f.player_id.map(a)).dropna(subset=["act"])
        f["slate_id"], f["week"], f["sub"] = sid, int(sid.split("_wk")[1][0]), sid.split("_")[3]
        rows.append(f)
    D = pd.concat(rows, ignore_index=True)
    D["S"] = (0.04 * D.proj_pass_yd + 4 * D.proj_pass_td + 0.1 * (D.proj_rush_yd + D.proj_rec_yd)
              + 6 * (D.proj_rush_td + D.proj_rec_td))
    return D


def variant(D, mf_new, vf_new):
    r = (mf_new * vf_new) / (D.matchup_factor * D.vegas_factor)
    return (D.engine_projection + D.S * (r - 1)).clip(lower=0)


def pooled(p, a):
    e = p - a
    return dict(pear=np.corrcoef(p, a)[0, 1], spear=np.corrcoef(rk(p), rk(a))[0, 1],
                bias=e.mean(), mae=np.abs(e).mean(), rmse=np.sqrt((e ** 2).mean()))


def cells(D, col):
    out = []
    for (sid, pos), g in D.groupby(["slate_id", "position"]):
        if len(g) < 6:
            continue
        n = NTOP[pos]
        out.append(dict(slate_id=sid, position=pos, n=len(g), week=g.week.iat[0],
                        sp=np.corrcoef(rk(g[col]), rk(g.act))[0, 1],
                        topact=g.nlargest(n, col).act.mean()))
    return pd.DataFrame(out)


def dedup(D):
    return D.assign(p=D["sub"].map(PRI)).sort_values("p").drop_duplicates(["player_id", "week"])


def evaluate(D, cols):
    Dd = dedup(D)
    res = []
    for c in cols:
        r = pooled(Dd[c].to_numpy(), Dd.act.to_numpy())
        C = cells(D, c)
        r.update(cell_sp=C.sp.mean(), cell_topact=C.topact.mean(), n=len(Dd), ncell=len(C))
        res.append(dict(variant=c, **r))
    return pd.DataFrame(res)


def boot_pooled(D, a, b, metric, B=2000):
    Dd = dedup(D)
    pa, pb, y = Dd[a].to_numpy(), Dd[b].to_numpy(), Dd.act.to_numpy()
    f = {"mae": lambda p, i: -np.abs(p[i] - y[i]).mean(),   # sign: + = a better
         "pear": lambda p, i: np.corrcoef(p[i], y[i])[0, 1],
         "rmse": lambda p, i: -np.sqrt(((p[i] - y[i]) ** 2).mean())}[metric]
    idx = np.arange(len(y))
    pt = f(pa, idx) - f(pb, idx)
    bs = []
    for _ in range(B):
        i = rng.choice(idx, len(idx))
        bs.append(f(pa, i) - f(pb, i))
    return pt, np.percentile(bs, 2.5), np.percentile(bs, 97.5)


def boot_cells(D, a, b, metric, B=4000):
    Ca, Cb = cells(D, a), cells(D, b)
    d = (Ca[metric] - Cb[metric]).to_numpy()
    bs = [rng.choice(d, len(d)).mean() for _ in range(B)]
    # also cluster by slate (6 clusters)
    sl = Ca.slate_id.to_numpy(); us = np.unique(sl)
    bs2 = []
    for _ in range(B):
        pick = rng.choice(us, len(us))
        bs2.append(np.concatenate([d[sl == s] for s in pick]).mean())
    return d.mean(), np.percentile(bs, 2.5), np.percentile(bs, 97.5), np.percentile(bs2, 2.5), np.percentile(bs2, 97.5), (d > 0).sum(), len(d)


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    D = frame()
    D.to_csv(OUT / "b1_frame.csv", index=False)
    print(f"rows (slate-level) {len(D)}; dedup player-weeks {len(dedup(D))}; by week:",
          dedup(D).week.value_counts().to_dict(), "by pos:", dedup(D).position.value_counts().to_dict())

    print("\n== factor dispersion (all alive skill rows, pre-cut) by week ==")
    for w in (1, 2):
        allr = pd.concat([pd.read_csv(S / f"final_projections_dk_{s}.csv") for s in SL if f"wk{w}" in s])
        allr = allr[allr.position.isin(NTOP) & (allr.final_projection > 0)]
        print(f"wk{w}", allr.groupby("position").matchup_factor.agg(["count", "std", "min", "max"]).round(3).to_dict("index"))
    print("S share of engine (scaled fraction) by pos:", (D.S / D.engine_projection).groupby(D.position).mean().round(3).to_dict())

    mf, vf = D.matchup_factor, D.vegas_factor
    V = {}
    for a in (0, 0.25, 0.5, 0.75, 1.0, 1.25):
        V[f"mA{a}"] = variant(D, mf ** a, vf)
    for b in (0, 0.5):
        V[f"vB{b}"] = variant(D, mf, vf ** b)
    for a in (0, 0.5):
        for b in (0, 0.5):
            V[f"mA{a}_vB{b}"] = variant(D, mf ** a, vf ** b)
    # shrink toward 1 (linear): w grid, same w both weeks
    W = (0, 0.25, 0.5, 0.75, 1.0, 1.25)
    for w in W:
        V[f"w{w}"] = variant(D, 1 + w * (mf - 1), vf)
    # by-week w
    for w1 in W:
        for w2 in W:
            wk = np.where(D.week == 1, w1, w2)
            V[f"W1_{w1}_W2_{w2}"] = variant(D, 1 + wk * (mf - 1), vf)
    D = pd.concat([D, pd.DataFrame(V), pd.DataFrame({k + "_F": v + D.stack_delta for k, v in V.items()})], axis=1)

    main = [c for c in V if not c.startswith("W1_")]
    print("\n== Q1 ablation, ENGINE (no stack), all weeks ==")
    E = evaluate(D, main); print(E.round(3).to_string(index=False)); E.to_csv(OUT / "b1_ablation_engine.csv", index=False)
    print("\n== Q1 ablation, FINAL (engine_variant + stack_delta) ==")
    print(evaluate(D, [c + "_F" for c in ["mA0", "mA0.5", "mA1.0", "vB0", "mA0_vB0"]]).round(3).to_string(index=False))
    print("\n== per week, matchup exponent (engine) ==")
    for w in (1, 2):
        print(f"-- wk{w}"); print(evaluate(D[D.week == w], [f"mA{a}" for a in (0, 0.25, 0.5, 0.75, 1.0, 1.25)]).round(3).to_string(index=False))

    print("\n== Q2 leave-one-week-out (choose exponent on one week, test on the other; vs a=1) ==")
    A = [f"mA{a}" for a in (0, 0.25, 0.5, 0.75, 1.0, 1.25)]
    for metric, better in (("cell_sp", max), ("mae", min), ("pear", max)):
        for tr, te in ((1, 2), (2, 1)):
            Etr = evaluate(D[D.week == tr], A).set_index("variant")[metric]
            best = Etr.idxmax() if better is max else Etr.idxmin()
            Ete = evaluate(D[D.week == te], list(dict.fromkeys([best, "mA1.0"]))).set_index("variant")[metric]
            imp = (Ete[best] - Ete["mA1.0"]) * (1 if better is max else -1)
            print(f"{metric:8s} train wk{tr} best={best:6s} -> test wk{te}: {Ete[best]:.4f} vs a=1 {Ete['mA1.0']:.4f}  improvement {imp:+.4f}")
    # LOWO for by-week shrink is not identifiable (each week's w is only fit on that week) -- see report.

    print("\n== Q3 bootstrap (+ = first better) ==")
    for a, b in (("mA0", "mA1.0"), ("mA0.5", "mA1.0"), ("mA0.5", "mA0"), ("mA0.25", "mA1.0")):
        for m in ("mae", "pear", "rmse"):
            pt, lo, hi = boot_pooled(D, a, b, m)
            print(f"pooled {m:5s} {a}-{b}: {pt:+.4f} 95% {lo:+.4f}..{hi:+.4f}  (cluster=player-week, n={len(dedup(D))})")
        for m in ("sp", "topact"):
            pt, lo, hi, lo2, hi2, wins, n = boot_cells(D, a, b, m)
            print(f"cells  {m:6s} {a}-{b}: {pt:+.4f} 95%cell {lo:+.4f}..{hi:+.4f} 95%slate {lo2:+.4f}..{hi2:+.4f} wins {wins}/{n}")
        for w in (1, 2):
            pt, lo, hi = boot_pooled(D[D.week == w], a, b, "mae")
            print(f"   wk{w} mae {a}-{b}: {pt:+.4f} 95% {lo:+.4f}..{hi:+.4f}")

    print("\n== Q4 shrink emulation: same w both weeks ==")
    print(evaluate(D, [f"w{w}" for w in W]).round(3).to_string(index=False))
    print("\n== Q4 by-week w grid: pooled MAE / cell_sp (rows w1 for wk1, cols w2 for wk2) ==")
    G = evaluate(D, [f"W1_{a}_W2_{b}" for a in W for b in W]).set_index("variant")
    for m in ("mae", "pear", "cell_sp"):
        T = pd.DataFrame([[G.loc[f"W1_{a}_W2_{b}", m] for b in W] for a in W], index=[f"w1={a}" for a in W], columns=[f"w2={b}" for b in W])
        print(m); print(T.round(4).to_string())
    # implied K for wk2 (1 game): current w_abs = 1/(1+4)=0.2; new K gives 1/(1+K) -> relative w = 5/(1+K)
    print("\nwk2 K-equivalents (1 game of 2026 data): relative w = 5/(1+K):",
          {K: round(5 / (1 + K), 3) for K in (4, 8, 12, 19, 49)})
    print("wk1 (17 games of 2025 at K=4, w_abs=.81): relative w = (17/(17+K))/(17/21):",
          {K: round((17 / (17 + K)) / (17 / 21), 3) for K in (4, 8, 17, 34)})

    print("\n== Q5 position / tier split: MAE and Pearson, a=0 vs a=1 (dedup) ==")
    Dd = dedup(D)
    Dd["tier"] = pd.cut(Dd.salary, [0, 4500, 6000, 7500, 20000], labels=["<4.5k", "4.5-6k", "6-7.5k", "7.5k+"])
    for key in ("position", "tier", "week"):
        rows = []
        for k, g in Dd.groupby(key, observed=True):
            r = {"grp": k, "n": len(g)}
            for c in ("mA0", "mA0.5", "mA1.0"):
                r[c + "_mae"] = np.abs(g[c] - g.act).mean(); r[c + "_pear"] = np.corrcoef(g[c], g.act)[0, 1]
            pt, lo, hi = boot_pooled(g, "mA0", "mA1.0", "mae", B=1000) if False else (np.nan,) * 3
            e0, e1 = np.abs(g.mA0 - g.act).to_numpy(), np.abs(g["mA1.0"] - g.act).to_numpy()
            dd = e1 - e0; bs = [rng.choice(dd, len(dd)).mean() for _ in range(2000)]
            r["mae_gain_a0"] = dd.mean(); r["lo"] = np.percentile(bs, 2.5); r["hi"] = np.percentile(bs, 97.5)
            rows.append(r)
        print(pd.DataFrame(rows).round(3).to_string(index=False))
    C0, C1 = cells(D, "mA0"), cells(D, "mA1.0")
    C0["d_sp"] = C0.sp - C1.sp; C0["d_top"] = C0.topact - C1.topact
    print("\ncell-level a=0 minus a=1 by position:"); print(C0.groupby("position")[["d_sp", "d_top"]].agg(["mean", "count"]).round(3).to_string())
    print(C0.round(3).to_string(index=False))

    print("\n== sanity: is there ANY positive matchup signal? negative exponents + residual regression ==")
    X = D.copy()
    for a in (-0.5, -0.25):
        X[f"mA{a}"] = variant(X, X.matchup_factor ** a, X.vegas_factor)
    for w in (1, 2):
        print(evaluate(X[X.week == w], ["mA-0.5", "mA-0.25", "mA0", "mA1.0"]).round(3).to_string(index=False))
    Xd = dedup(X)
    for w in (1, 2):
        g = Xd[Xd.week == w]
        x = g.S * np.log(g.matchup_factor)       # points the factor adds (log-linear), per player
        y = g.act - g.mA0                        # residual with matchup removed
        b = np.polyfit(x, y, 1)[0]
        print(f"wk{w}: slope of (actual - proj_without_matchup) on S*log(mf): {b:+.2f} (1 = factor exactly right, 0 = no signal), corr {np.corrcoef(x, y)[0,1]:+.3f}, n={len(g)}")
