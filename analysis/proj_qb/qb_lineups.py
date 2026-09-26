"""Lineup-level test of QB recalibration on the production-faithful (QB1 guard) rebuild.
Research only; no FC data inside. Reuses analysis/proj_lineup_level/lineup_eval.py (ILP, cash proxy).
Variants (non-QB players identical = QB1 rebuild final_projection):
  q      QB1 rebuild as is                 a0   stubbed-depth history (all positions, reference)
  qeng   QB = engine_projection (no stack)  qcal QB = a+b*proj, fit LOSO on QB1 rows of OTHER seasons, by week bucket
  qfwd   same but fit only on PRIOR seasons (2021 left as q)   qsh QB = mean + 0.8*(proj-slate QB1 mean) (fixed shrink)
Writes data/fc_history/derived/proj_qb/{lineups.csv, lineups_report.txt}
"""
import glob, os, sys, multiprocessing as mp
import numpy as np, pandas as pd

R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DER = os.path.join(R, "data/fc_history/derived")
OUT = os.path.join(DER, "proj_qb")
sys.path.insert(0, os.path.join(R, "analysis/proj_lineup_level"))
import lineup_eval as le  # noqa: E402

VARS = ["a0", "q", "qeng", "qcal", "qfwd", "qsh"]


def wb(w):
    return np.select([w <= 1, w <= 4, w <= 9], [0, 1, 2], 3)


def load():
    fc = pd.read_csv(os.path.join(DER, "fc_master_mapped.csv"), low_memory=False, dtype={"player_id": str})
    fc = fc[(fc.site == "dk") & (fc.slate_kind == "classic") & (fc.slate_raw == "main") & fc.player_id.notna() & fc.pos.isin(le.POS)]
    fc = fc.drop_duplicates(["season", "week", "player_id"])[["season", "week", "player_id", "pos", "team", "salary", "score"]]
    played = set()
    for s in range(2021, 2027):
        w = pd.read_parquet(os.path.join(R, f"data/weekly_stats_{s}.parquet"), columns=["player_id", "season", "week"])
        played |= set(zip(w.season, w.week, w.player_id))
    fc["dnp"] = [(p != "DST") and ((s, w, i) not in played) for s, w, i, p in zip(fc.season, fc.week, fc.player_id, fc.pos)]
    fc["act"] = fc.score.fillna(0.0).where(~fc.dnp, 0.0)
    rd = lambda d, cols: pd.concat([pd.read_csv(f, dtype={"player_id": str}, usecols=["season", "week", "player_id"] + cols)
                                    for f in glob.glob(os.path.join(DER, d, "proj_*.csv"))]).drop_duplicates(["season", "week", "player_id"])
    X = fc.merge(rd("ourproj", ["final_projection"]).rename(columns={"final_projection": "a0"}), on=["season", "week", "player_id"])
    X = X.merge(rd("proj_qb/ourproj_qb1", ["final_projection", "engine_projection"]).rename(
        columns={"final_projection": "q", "engine_projection": "eng"}), on=["season", "week", "player_id"])
    X = X[X.salary > 0].reset_index(drop=True)
    X["slate"] = X.season * 100 + X.week
    X["wb"] = wb(X.week)
    isq = X.pos == "QB"
    X["qb1"] = isq & (X[isq].groupby(["slate", "team"]).salary.rank(ascending=False, method="first") == 1).reindex(X.index, fill_value=False)
    X["qeng"] = np.where(isq, X.eng, X.q)
    fitrows = X[X.qb1]
    X["qcal"] = X.q; X["qfwd"] = X.q
    coefs = []
    for s in X.season.unique():
        for b in range(4):
            m = isq & (X.season == s) & (X.wb == b) & (X.q > 5)
            for col, tr in [("qcal", fitrows[(fitrows.season != s) & (fitrows.wb == b)]),
                            ("qfwd", fitrows[(fitrows.season < s) & (fitrows.wb == b)])]:
                if len(tr) < 50: continue
                sl, ic = np.polyfit(tr.q, tr.act, 1)
                X.loc[m, col] = ic + sl * X.loc[m, "q"]
                coefs.append((col, s, b, len(tr), round(sl, 3), round(ic, 2)))
    mu = X[X.qb1].groupby("slate").q.mean()
    m = isq & (X.q > 5)
    X.loc[m, "qsh"] = X.loc[m, "slate"].map(mu) + 0.8 * (X.loc[m, "q"] - X.loc[m, "slate"].map(mu))
    X["qsh"] = X.qsh.fillna(X.q)
    for v in VARS:
        X[v] = X[v].fillna(0).clip(lower=0)
    return X, coefs


def job(a):
    s, sal, pos, act, pids, objs, k = a
    best = le.solve_k(sal, pos, act, 1)[0]
    rows = []
    for v, obj in objs.items():
        for r, L in enumerate(le.solve_k(sal, pos, obj, k)):
            rows.append(dict(slate=s, var=v, rank=r, score=act[L].sum(), best=act[best].sum(),
                             qb=pids[[i for i in L if pos[i] == "QB"][0]], players="|".join(pids[L])))
    return rows


def boot(d, n=4000, seed=1):
    rng = np.random.default_rng(seed)
    d = np.asarray(d); idx = rng.integers(0, len(d), (n, len(d)))
    return d.mean(), np.percentile(d[idx].mean(1), 2.5), np.percentile(d[idx].mean(1), 97.5)


def main():
    X, coefs = load()
    jobs = [(s, g.salary.values.astype(float), g.pos.values, g.act.values, g.player_id.values,
             {v: g[v].values for v in VARS}, 5) for s, g in X.groupby("slate")]
    with mp.get_context("spawn").Pool(12) as p:
        res = p.map(job, jobs, chunksize=1)
    L = pd.DataFrame([r for rr in res for r in rr])
    L["season"] = L.slate // 100
    L["cash"] = L.score >= le.CASH * L.best
    L.to_csv(os.path.join(OUT, "lineups.csv"), index=False)
    out = [f"slates {L.slate.nunique()}; coefs (col,season,bucket,n,slope,icpt): {coefs}"]
    for sub, name in [(L[L["rank"] == 0], "top-1"), (L, "top-5 avg")]:
        piv = sub.groupby(["slate", "var"]).agg(score=("score", "mean"), cash=("cash", "mean")).unstack("var")
        out.append(f"\n== {name}: mean score / cash by season ==")
        seas = piv.index // 100
        for s in sorted(set(seas)):
            p = piv[seas == s]
            out.append(f"{s} n{len(p)} " + " ".join(f"{v}:{p['score'][v].mean():.1f}/{p['cash'][v].mean():.2f}" for v in VARS))
        out.append("ALL " + " ".join(f"{v}:{piv['score'][v].mean():.1f}/{piv['cash'][v].mean():.2f}" for v in VARS))
        for v in ["a0", "qeng", "qcal", "qfwd", "qsh"]:
            d = piv["score"][v] - piv["score"]["q"]
            mm, lo, hi = boot(d)
            rec = d[seas >= 2023]
            per = " ".join(f"{s}:{d[seas == s].mean():+.1f}" for s in sorted(set(seas)))
            out.append(f"{v}-q score {mm:+.2f} [{lo:+.2f},{hi:+.2f}] 2023+ {rec.mean():+.2f} (n{len(rec)}) | {per} | "
                       f"cash diff {(piv['cash'][v]-piv['cash']['q']).mean():+.3f}")
    t = L[L["rank"] == 0].pivot(index="slate", columns="var", values="qb")
    out.append("\nQB changed vs q (top-1): " + " ".join(f"{v}:{(t[v] != t['q']).mean():.2f}" for v in VARS))
    pl = L[L["rank"] == 0].pivot(index="slate", columns="var", values="players")
    out.append("lineup changed vs q (top-1): " + " ".join(f"{v}:{(pl[v] != pl['q']).mean():.2f}" for v in VARS))
    txt = "\n".join(out); print(txt)
    open(os.path.join(OUT, "lineups_report.txt"), "w").write(txt)


if __name__ == "__main__":
    main()
