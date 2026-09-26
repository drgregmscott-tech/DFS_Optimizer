"""Lineup-level test of sigma recalibration under the production mean-variance objective
sum(final) - lambda*sum(sigma^2) (optimizer.py Session 10.5; frontend presets cash/SE 0.063, MME -0.005).
Research only; NO FC data. Reads proj_sigma/frame.parquet. Writes proj_sigma/{lineups.csv, lineups_report.txt}.
Sigma variants (all leave-one-season-out; 2026 fit on 2021-25):
  cur   : production sigma column
  pos   : sigma * c_pos, c_pos = realized residual sd / rms(sigma) per position (played+DNP, proj>0)
  tier  : sigma replaced by realized residual sd of the player's (position, projection tier) cell
    python analysis/proj_sigma/lineups.py [--workers 12] [--k 5]
"""
import argparse, os, sys, multiprocessing as mp
import numpy as np, pandas as pd

R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(R, "analysis/proj_lineup_level"))
OUT = os.path.join(R, "data/fc_history/derived/proj_sigma")
LAMS = [0.063, -0.005, -0.02]
CASH = 0.543


def sig_variants(X):
    X = X.copy()
    X["sig_pos"] = np.nan; X["sig_tier"] = np.nan
    for s in sorted(X.season.unique()):
        tr = X[X.season != s] if s != 2026 else X[X.season < 2026]
        c = tr.groupby("position").apply(lambda g: g.err.std() / np.sqrt((g.sigma ** 2).mean()))
        t = tr.groupby(["position", "ptier"], observed=True).err.std()
        m = X.season == s
        X.loc[m, "sig_pos"] = X.loc[m, "sigma"] * X.loc[m, "position"].map(c)
        X.loc[m, "sig_tier"] = [t.get((p, q), np.nan) for p, q in zip(X.loc[m, "position"], X.loc[m, "ptier"])]
    X["sig_tier"] = X.sig_tier.fillna(X.sigma)
    return X


def job(a):
    from lineup_eval import solve_k
    s, sal, pos, act, pids, objs, k = a
    best = solve_k(sal, pos, act, 1)[0]; bsc = act[best].sum()
    rows = []
    for v, obj in objs.items():
        for r, L in enumerate(solve_k(sal, pos, obj, k)):
            rows.append(dict(slate=s, var=v, rank=r, score=act[L].sum(), best=bsc, players="|".join(pids[L])))
    return rows


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workers", type=int, default=12); ap.add_argument("--k", type=int, default=5)
    a = ap.parse_args()
    X = pd.read_parquet(os.path.join(OUT, "frame.parquet"))
    X = X[X.salary > 0]
    X = sig_variants(X)
    P = open(os.path.join(OUT, "lineups_scales.txt"), "w")
    P.write(X.groupby(["season", "position"]).apply(lambda g: (g.sig_pos / g.sigma).median()).unstack().round(3).to_string())
    P.close()
    X["slate"] = X.season * 100 + X.week
    jobs = []
    for s, g in X.groupby("slate"):
        f = g.final_projection.values
        objs = {"base": f}
        for lam in LAMS:
            for v, col in [("cur", "sigma"), ("pos", "sig_pos"), ("tier", "sig_tier")]:
                objs[f"{v}|{lam}"] = f - lam * g[col].values ** 2
        jobs.append((s, g.salary.values.astype(float), g.position.values, g.act.values, g.player_id.values, objs, a.k))
    with mp.get_context("spawn").Pool(a.workers) as p:
        res = p.map(job, jobs, chunksize=1)
    L = pd.DataFrame([r for rr in res for r in rr])
    L.to_csv(os.path.join(OUT, "lineups.csv"), index=False)
    report(L)


def report(L):
    LOG = open(os.path.join(OUT, "lineups_report.txt"), "w")
    def P(*a):
        s = " ".join(str(x) for x in a); print(s); LOG.write(s + "\n")
    L["season"] = L.slate // 100
    L["cash"] = L.score >= CASH * L.best
    L["hit75"] = L.score >= 0.75 * L.best
    L["set"] = L.players.str.split("|").apply(frozenset)
    top = L[L["rank"] == 0].set_index(["var", "slate"])
    b5 = L.groupby(["var", "slate"]).score.max()
    P(f"slates {L.slate.nunique()}; variants {L['var'].nunique()}; seasons {sorted(L.season.unique())}")
    rng = np.random.default_rng(5)
    for lam in LAMS:
        P(f"\n== lambda {lam}: new vs cur (top lineup), per season. d=score diff, flips=share slates top lineup differs, chg=avg players changed")
        for v in ["pos", "tier"]:
            for seas in sorted(L.season.unique()) + ["all", "2023+"]:
                sl = [s for s in top.loc["base"].index if seas == "all" or (seas == "2023+" and s // 100 >= 2023) or s // 100 == seas]
                t, u = top.loc[f"{v}|{lam}"].loc[sl], top.loc[f"cur|{lam}"].loc[sl]
                d = (t.score - u.score).values
                ci = np.percentile(d[rng.integers(0, len(d), (2000, len(d)))].mean(1), [2.5, 97.5]) if len(d) > 2 else [np.nan, np.nan]
                ch = np.array([len(x - y) for x, y in zip(t.set, u.set)])
                bb = (b5.loc[f"{v}|{lam}"].loc[sl] - b5.loc[f"cur|{lam}"].loc[sl]).mean()
                P(f"  {v:4s} {str(seas):5s} n{len(sl):3d} d {d.mean():+6.2f} [{ci[0]:+.2f},{ci[1]:+.2f}] cash {t.cash.mean():.3f} vs {u.cash.mean():.3f}"
                  f" hit75 {t.hit75.mean():.3f} vs {u.hit75.mean():.3f} best5 d {bb:+.2f} flips {(ch > 0).mean():.2f} chg {ch.mean():.2f}")
        P(f"  (ref: cur|{lam} vs base(lambda=0) all: d {(top.loc[f'cur|{lam}'].score - top.loc['base'].score).mean():+.2f}, "
          f"cash {top.loc[f'cur|{lam}'].cash.mean():.3f} vs {top.loc['base'].cash.mean():.3f})")
    LOG.close()


if __name__ == "__main__":
    main()
