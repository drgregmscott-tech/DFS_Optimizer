"""Lineup-level old vs new sigma + lambda sweep (research only; NO FC data in this file). Objective = final - lambda*sigma^2
(optimizer.py mean-variance), bare DK classic ILP from analysis/proj_lineup_level/lineup_eval.solve_k, top-K distinct lineups.
MEANS held fixed at the <base> tag's final_projection so only sigma differs.
Sigma sets: old = production sigma column of <base>; new = <tag> w23 (recal fit 2021-25 with 2023+ double-weighted, leave-one-season-out; from recal_variants_<tag>.parquet); newf = <tag2> sig_fwd
(variance fit 2018-22 + recal fit 2021-22: clean forward holdout for 2023+).
    python analysis/proj_variance/lineups_sweep.py --workers 12
"""
import argparse, os, sys, multiprocessing as mp
import numpy as np, pandas as pd
R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(R, "analysis/proj_lineup_level"))
OUT = os.path.join(R, "data/fc_history/derived/proj_variance")
LAMS = [-0.02, -0.01, -0.005, 0.0, 0.01, 0.02, 0.04, 0.063, 0.1]
CASH = 0.543


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
    ap.add_argument("--base", default="cur"); ap.add_argument("--tag", default="vol2021"); ap.add_argument("--tag2", default="vol2018")
    ap.add_argument("--report-only", action="store_true")
    a = ap.parse_args()
    if not a.report_only:
        key = ["season", "week", "player_id"]
        X = pd.read_parquet(os.path.join(OUT, f"frameS_{a.base}.parquet"))
        X = X[X.salary > 0]
        for f, col, nm in [(f"recal_variants_{a.tag}.parquet", "w23", "new"), (f"frameS_{a.tag2}.parquet", "sig_fwd", "newf")]:
            Y = pd.read_parquet(os.path.join(OUT, f))[key + [col]].rename(columns={col: nm})
            X = X.merge(Y, on=key, how="left"); X[nm] = X[nm].fillna(X.sigma)
        X["slate"] = X.season * 100 + X.week
        jobs = []
        for s, g in X.groupby("slate"):
            f = g.final_projection.values; objs = {}
            for lam in LAMS:
                for v, col in [("old", "sigma"), ("new", "new"), ("newf", "newf")]:
                    objs[f"{v}|{lam}"] = f - lam * g[col].values ** 2
            jobs.append((s, g.salary.values.astype(float), g.position.values, g.act.values, g.player_id.values, objs, a.k))
        with mp.get_context("spawn").Pool(a.workers) as p:
            res = p.map(job, jobs, chunksize=1)
        L = pd.DataFrame([r for rr in res for r in rr]); L.to_csv(os.path.join(OUT, "lineups.csv"), index=False)
    report(pd.read_csv(os.path.join(OUT, "lineups.csv")))


def ci(d, rng):
    return np.percentile(d[rng.integers(0, len(d), (4000, len(d)))].mean(1), [2.5, 97.5])


def report(L):
    LOG = open(os.path.join(OUT, "lineups_report.txt"), "w")

    def P(*a):
        s = " ".join(str(x) for x in a); print(s); LOG.write(s + "\n")
    L["season"] = L.slate // 100; L["cash"] = L.score >= CASH * L.best
    L["set"] = L.players.str.split("|").apply(frozenset)
    top = L[L["rank"] == 0].set_index(["var", "slate"]); b5 = L.groupby(["var", "slate"]).score.max()
    m5 = L.groupby(["var", "slate"]).score.mean()
    rng = np.random.default_rng(7)
    slates = sorted(top.loc["old|0.0"].index)
    def sel(seas):
        return [s for s in slates if seas == "all" or (seas == "2023+" and s // 100 >= 2023) or s // 100 == seas]
    P(f"slates {len(slates)}; top-1 score, best-of-5, mean-of-5, cash proxy (>= {CASH} x hindsight best)")
    for lam in [-0.005, 0.0, 0.02, 0.063]:
        P(f"\n== lambda {lam}: NEW vs OLD sigma (means fixed). d=top1 diff [95% boot CI]; flips=share slates top lineup differs")
        for v in ["new", "newf"]:
            for seas in [2021, 2022, 2023, 2024, 2025, 2026, "2023+", "all"]:
                sl = sel(seas)
                if v == "newf" and seas in (2021, 2022, "all"): continue
                t, u = top.loc[f"{v}|{lam}"].loc[sl], top.loc[f"old|{lam}"].loc[sl]
                d = (t.score - u.score).values; c = ci(d, rng) if len(d) > 2 else [np.nan] * 2
                ch = np.array([len(x - y) for x, y in zip(t.set, u.set)])
                P(f"  {v:4s} {str(seas):5s} n{len(sl):3d} top1 d {d.mean():+6.2f} [{c[0]:+.2f},{c[1]:+.2f}] best5 d "
                  f"{(b5.loc[f'{v}|{lam}'].loc[sl] - b5.loc[f'old|{lam}'].loc[sl]).mean():+.2f} mean5 d "
                  f"{(m5.loc[f'{v}|{lam}'].loc[sl] - m5.loc[f'old|{lam}'].loc[sl]).mean():+.2f} cash {t.cash.mean():.3f} vs {u.cash.mean():.3f}"
                  f" flips {(ch > 0).mean():.2f} chg {ch.mean():.2f}")
    P("\n== LAMBDA SWEEP vs lambda=0 (same sigma set): top1 d [CI], mean5 d, cash; per season 2023+ direction (+/-/0) of top1 d")
    for v in ["old", "new", "newf"]:
        P(f"-- sigma {v}")
        for lam in LAMS:
            if lam == 0: continue
            out = []
            for seas in (["all", "2023+"] if v != "newf" else ["2023+"]):
                sl = sel(seas)
                d = (top.loc[f"{v}|{lam}"].loc[sl].score - top.loc[f"{v}|0.0"].loc[sl].score).values; c = ci(d, rng)
                d5 = (m5.loc[f"{v}|{lam}"].loc[sl] - m5.loc[f"{v}|0.0"].loc[sl]).values; c5 = ci(d5, rng)
                out.append(f"{seas}: top1 {d.mean():+5.2f} [{c[0]:+.2f},{c[1]:+.2f}] mean5 {d5.mean():+5.2f} [{c5[0]:+.2f},{c5[1]:+.2f}] "
                           f"cash {top.loc[f'{v}|{lam}'].loc[sl].cash.mean():.3f}/{top.loc[f'{v}|0.0'].loc[sl].cash.mean():.3f}")
            ps = []
            for seas in [2021, 2022, 2023, 2024, 2025, 2026]:
                sl = sel(seas); x = (m5.loc[f"{v}|{lam}"].loc[sl] - m5.loc[f"{v}|0.0"].loc[sl]).mean()
                ps.append(f"{seas % 100}:{x:+.1f}")
            P(f"  lam {lam:+.3f} | " + " | ".join(out) + " | mean5 by season " + " ".join(ps))
    LOG.close()


if __name__ == "__main__":
    main()
