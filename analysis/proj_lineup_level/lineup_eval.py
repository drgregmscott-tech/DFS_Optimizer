"""Lineup-level evaluation of projection variants (research only; contains NO FC data).

Reads (git-ignored, FC-derived): data/fc_history/derived/fc_master_mapped.csv,
  data/fc_history/derived/ourproj{,_mh_k4,_mh_k16,_mh_kq16}/proj_*.csv
Writes: data/fc_history/derived/proj_lineup_level/{lineups.csv, report.txt}
Lineups: DK classic ILP (QB,2-3RB,3-4WR,1-2TE,DST; 9 players; $50k), top-K distinct lineups per slate
(each new lineup must differ from every earlier one by >=1 player), scored on actual DK points (DNP=0).
Cash proxy: score >= 0.543 x hindsight-best lineup (calibrated on 2026 wk1-2 real contests, inj_gap.py).
    python analysis/proj_lineup_level/lineup_eval.py [--workers 14] [--k 5]
"""
import argparse, glob, os, multiprocessing as mp
import numpy as np, pandas as pd

R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DER = os.path.join(R, "data/fc_history/derived")
OUT = os.path.join(DER, "proj_lineup_level")
POS = ["QB", "RB", "WR", "TE", "DST"]
CASH = 0.543
WGRID = [0.0, 0.1, 0.2, 0.35, 0.5, 0.65, 0.8, 1.0]


def load():
    fc = pd.read_csv(os.path.join(DER, "fc_master_mapped.csv"), low_memory=False, dtype={"player_id": str})
    fc = fc[(fc.site == "dk") & (fc.slate_kind == "classic") & (fc.slate_raw == "main") & fc.player_id.notna() & fc.pos.isin(POS)]
    fc = fc.drop_duplicates(["season", "week", "player_id"])[["season", "week", "player_id", "player", "pos", "team", "salary", "fc_proj", "score"]]
    played = set()
    for s in range(2021, 2027):
        w = pd.read_parquet(os.path.join(R, f"data/weekly_stats_{s}.parquet"), columns=["player_id", "season", "week"])
        played |= set(zip(w.season, w.week, w.player_id))
    fc["dnp"] = [(p != "DST") and ((s, w, i) not in played) for s, w, i, p in zip(fc.season, fc.week, fc.player_id, fc.pos)]
    fc["act"] = fc.score.fillna(0.0).where(~fc.dnp, 0.0)
    fc["fc"] = fc.fc_proj.fillna(0.0).clip(lower=0)
    fc["fc0"] = (fc.fc <= 0.05) & (fc.pos != "DST")
    X = fc
    for v, d in [("a0", "ourproj"), ("k4", "ourproj_mh_k4"), ("k16", "ourproj_mh_k16"), ("kq16", "ourproj_mh_kq16")]:
        o = pd.concat([pd.read_csv(f, dtype={"player_id": str}, usecols=["season", "week", "player_id", "final_projection"])
                       for f in glob.glob(os.path.join(DER, d, "proj_*.csv"))]).drop_duplicates(["season", "week", "player_id"])
        X = X.merge(o.rename(columns={"final_projection": v}), on=["season", "week", "player_id"], how="inner")
        X[v] = X[v].fillna(0).clip(lower=0)
    X = X[X.salary > 0].reset_index(drop=True)
    X["slate"] = X.season * 100 + X.week
    return X


def solve_k(sal, pos, obj, k):
    import pulp
    idx = np.where(obj > 0.01)[0] if (obj > 0.01).sum() > 60 else np.arange(len(obj))
    pr = pulp.LpProblem("dk", pulp.LpMaximize)
    x = {i: pulp.LpVariable(f"x{i}", cat="Binary") for i in idx}
    pr += pulp.lpSum(float(obj[i]) * x[i] for i in idx)
    pr += pulp.lpSum(float(sal[i]) * x[i] for i in idx) <= 50000
    pr += pulp.lpSum(x.values()) == 9
    c = lambda p: pulp.lpSum(x[i] for i in idx if pos[i] == p)
    pr += c("QB") == 1; pr += c("DST") == 1
    pr += c("RB") >= 2; pr += c("RB") <= 3; pr += c("WR") >= 3; pr += c("WR") <= 4; pr += c("TE") >= 1; pr += c("TE") <= 2
    out = []
    for _ in range(k):
        pr.solve(pulp.PULP_CBC_CMD(msg=0))
        if pulp.LpStatus[pr.status] != "Optimal": break
        L = sorted(i for i in idx if x[i].value() > 0.5)
        out.append(L)
        pr += pulp.lpSum(x[i] for i in L) <= 8
    return out


def job(a):
    s, sal, pos, act, pids, objs, k = a
    rows = []
    best = solve_k(sal, pos, act, 1)[0]
    bsc = act[best].sum()
    for v, obj in objs.items():
        for r, L in enumerate(solve_k(sal, pos, obj, k)):
            assert len(L) == 9 and sal[L].sum() <= 50000
            pc = pd.Series(pos[L]).value_counts()
            assert pc.get("QB", 0) == 1 and pc.get("DST", 0) == 1 and pc.get("RB", 0) >= 2 and pc.get("WR", 0) >= 3 and pc.get("TE", 0) >= 1
            sc = act[L].sum()
            assert sc <= bsc + 1e-6
            rows.append(dict(slate=s, var=v, rank=r, score=sc, best=bsc, salary=int(sal[L].sum()), players="|".join(pids[L])))
    return rows


def variants(g, fold_bias):
    """all objective columns for one slate. fold_bias: FC bias to subtract (training-estimated)."""
    V = {}
    for f in ["none", "zFC", "zDNP"]:
        m = np.zeros(len(g), bool) if f == "none" else (g.fc0.values if f == "zFC" else g.dnp.values)
        for v in ["a0", "k4", "k16", "kq16"]:
            V[f"{v}|{f}"] = np.where(m, 0, g[v].values)
        for b in [0, 1]:
            fcb = np.where(g.fc.values > 0, np.clip(g.fc.values - fold_bias * b, 0, None), 0) if b else g.fc.values
            for w in WGRID[1:]:
                if w == 1.0 and b: continue
                V[f"w{w}b{b}|{f}"] = np.where(m, 0, w * fcb + (1 - w) * g.a0.values)
    return V


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workers", type=int, default=14); ap.add_argument("--k", type=int, default=5)
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    X = load()
    # FC bias (skill, fc>8, played) -- single global value; per-fold version checked in analyze step
    sk = X[(X.pos != "DST") & (X.fc > 8)]
    bias = float((sk.fc - sk.act).mean())
    print(f"rows {len(X)} slates {X.slate.nunique()} FC bias(skill fc>8) {bias:.2f}")
    jobs = []
    for s, g in X.groupby("slate"):
        jobs.append((s, g.salary.values.astype(float), g.pos.values, g.act.values, g.player_id.values, variants(g, bias), a.k))
    with mp.get_context("spawn").Pool(a.workers) as p:
        res = p.map(job, jobs, chunksize=1)
    L = pd.DataFrame([r for rr in res for r in rr])
    L.to_csv(os.path.join(OUT, "lineups.csv"), index=False)
    with open(os.path.join(OUT, "meta.txt"), "w") as f: f.write(f"fc_bias {bias}\n")
    print("done", len(L))


if __name__ == "__main__":
    main()
