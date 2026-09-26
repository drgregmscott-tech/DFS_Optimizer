"""Lineup-level replay of early-season arms (research only; no FC data inside).
Uses players.parquet from anatomy.py (+ DST rows from base ourproj/FC) and lineup_eval.solve_k.
Variants per slate: base, prod, carry, their 0.35-FC blends, FC alone, and a QB-dilution fix ('q' suffix):
harness stubs the depth chart, so the reconcile guard can't identify QB1 and team pass attempts are split over ~2.5 QBs
(starter proj_pass_att ~24 vs 33 actual in EVERY week). qfix gives each team's top-salary QB the team's summed QB pass
volume at his own pass pts/attempt. Writes data/fc_history/derived/proj_early_season/{lineups_early.csv, lineup_early.txt}
    python analysis/proj_early_season/lineup_early.py
"""
import os, sys, glob, multiprocessing as mp
import numpy as np, pandas as pd
R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(R, "analysis/proj_lineup_level"))
DER = os.path.join(R, "data/fc_history/derived"); OUT = os.path.join(DER, "proj_early_season")
from lineup_eval import solve_k  # noqa: E402


def qfix(g, col, pa, pyd, ptd):
    v = g[col].values.copy()
    q = g[g.pos == "QB"]
    for t, h in q.groupby("team"):
        i = h.salary.idxmax(); tot = h[pa].sum(); own = g.at[i, pa]
        if own > 1:
            ppa = (0.04 * g.at[i, pyd] + 4 * g.at[i, ptd]) / own
            v[g.index.get_loc(i)] += (tot - own) * ppa
        for j in h.index:
            if j != i: v[g.index.get_loc(j)] = min(v[g.index.get_loc(j)], 2.0)
    return v


def load():
    X = pd.read_parquet(os.path.join(OUT, "players.parquet"))
    extra = ["proj_pass_yd", "proj_pass_td"]
    def rd(d):
        return pd.concat([pd.read_csv(f, dtype={"player_id": str}, usecols=["season", "week", "player_id"] + extra) for f in glob.glob(d)])
    X = X.merge(rd(os.path.join(DER, "ourproj/proj_*.csv")), on=["season", "week", "player_id"], how="left")
    for arm in ["prod", "carry"]:
        a = rd(os.path.join(OUT, arm, "proj_*.csv")).rename(columns={c: c + "_" + arm for c in extra})
        X = X.merge(a, on=["season", "week", "player_id"], how="left")
        for c in extra:
            lim = 1 if arm == "prod" else 4
            X[c + "_" + arm] = np.where(X.week <= lim, X[c + "_" + arm], X[c])
    # DST from FC pool + base ourproj (identical across arms)
    fc = pd.read_csv(os.path.join(DER, "fc_master_mapped.csv"), low_memory=False, dtype={"player_id": str})
    d = fc[(fc.site == "dk") & (fc.slate_kind == "classic") & (fc.slate_raw == "main") & (fc.pos == "DST") & fc.player_id.notna()].drop_duplicates(["season", "week", "player_id"])
    o = pd.concat([pd.read_csv(f, dtype={"player_id": str}, usecols=["season", "week", "player_id", "final_projection"]) for f in glob.glob(os.path.join(DER, "ourproj/proj_*.csv"))])
    d = d.merge(o, on=["season", "week", "player_id"])
    d = d.assign(act=d.score.fillna(0), fc=d.fc_proj.fillna(0).clip(lower=0), final_projection_prod=d.final_projection, final_projection_carry=d.final_projection)
    X = pd.concat([X, d[["season", "week", "player_id", "pos", "team", "salary", "act", "fc", "final_projection", "final_projection_prod", "final_projection_carry"]]], ignore_index=True)
    for c in ["final_projection", "final_projection_prod", "final_projection_carry"]:
        X[c] = X[c].fillna(0).clip(lower=0)
    X = X[X.salary > 0]
    X["slate"] = X.season * 100 + X.week
    return X


def objs(g):
    g = g.reset_index(drop=True)
    V = {"fc": g.fc.values}
    for k, c, sfx in [("base", "final_projection", ""), ("prod", "final_projection_prod", "_prod"), ("carry", "final_projection_carry", "_carry")]:
        V[k] = g[c].values
        V[k + "q"] = qfix(g, c, "proj_pass_att" + sfx, "proj_pass_yd" + sfx, "proj_pass_td" + sfx)
        for kk in [k, k + "q"]:
            V[kk + "_b35"] = 0.35 * g.fc.values + 0.65 * V[kk]
    return V


def job(a):
    s, g = a
    g = g.reset_index(drop=True)
    sal, pos, act = g.salary.values.astype(float), g.pos.values, g.act.values
    best = act[solve_k(sal, pos, act, 1)[0]].sum()
    rows = []
    for v, ob in objs(g).items():
        for r, L in enumerate(solve_k(sal, pos, np.nan_to_num(ob), 5)):
            rows.append(dict(slate=s, var=v, rank=r, score=act[L].sum(), best=best))
    return rows


def main():
    X = load()
    jobs = list(X.groupby("slate"))
    with mp.get_context("spawn").Pool(14) as p:
        res = p.map(job, jobs, chunksize=1)
    L = pd.DataFrame([r for rr in res for r in rr]); L.to_csv(os.path.join(OUT, "lineups_early.csv"), index=False)
    rng = np.random.default_rng(3)
    top = L[L["rank"] == 0].pivot(index="slate", columns="var", values="score")
    bo5 = L.groupby(["slate", "var"]).score.max().unstack()
    wk = top.index % 100; ss = top.index // 100
    cuts = {"wk1": wk == 1, "wk2": wk == 2, "wk1-2": wk <= 2, "wk3-4": (wk >= 3) & (wk <= 4), "wk5+": wk >= 5, "all": wk > 0}
    log = open(os.path.join(OUT, "lineup_early.txt"), "w")
    def P(s): print(s); log.write(s + "\n")
    pairs = [("fc", "base"), ("prod", "base"), ("carry", "base"), ("carry", "prod"), ("baseq", "base"), ("prodq", "prod"),
             ("base_b35", "base"), ("prod_b35", "prod"), ("carry_b35", "carry"), ("baseq_b35", "baseq"), ("prodq_b35", "prodq"), ("carryq", "prodq"), ("fc", "prodq")]
    for nm, M in [("rank-0", top), ("best-of-5", bo5)]:
        P(f"\n== {nm} lineup pts delta (mean, bootstrap 95% CI) by cut; n slates")
        rows = []
        for a, b in pairs:
            r = {"pair": f"{a} - {b}"}
            for c, m in cuts.items():
                d = (M[a] - M[b])[m].values
                if len(d) == 0: continue
                ci = np.percentile(d[rng.integers(0, len(d), (2000, len(d)))].mean(1), [2.5, 97.5])
                r[c] = f"{d.mean():+.1f} [{ci[0]:+.0f},{ci[1]:+.0f}] n{len(d)}"
            rows.append(r)
        P(pd.DataFrame(rows).set_index("pair").to_string())
        P(f"-- {nm} wk1-2 per season")
        e = M[wk <= 2]
        P(pd.DataFrame({f"{a}-{b}": (e[a] - e[b]).groupby(e.index // 100).mean() for a, b in pairs}).round(1).T.to_string())
        P(f"-- {nm} wk1-4 per season")
        e = M[wk <= 4]
        P(pd.DataFrame({f"{a}-{b}": (e[a] - e[b]).groupby(e.index // 100).mean() for a, b in pairs}).round(1).T.to_string())
    log.close()


if __name__ == "__main__":
    main()
