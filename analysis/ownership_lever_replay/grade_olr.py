"""Grade ownership-lever replay builds vs real contests. DO NOT COMMIT outputs (FC/contest-derived).
usage: python grade.py step1 | sweep"""
import re, sys
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent; REPO = HERE.parents[1]
import importlib.util
_sp = importlib.util.spec_from_file_location("lam_grade", REPO / "analysis" / "lambda_reverify" / "grade.py")
LG = importlib.util.module_from_spec(_sp); _sp.loader.exec_module(LG)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40); pd.set_option("display.max_rows", 500)
RX = re.compile(r"O_(.+)__(cash|se_gpp|se3max_pool|mme_gpp)_(old|v2|v2novac|v2tp|oracle)_k([+-]\d\.\d{3})_s(\d+)(_def)?\.csv$")


def lineup_sets(f):
    L = pd.read_csv(f, dtype={"player_id": str})
    return sorted(tuple(sorted(g.player_id)) for _, g in L.groupby("lineup_id"))


def step1():
    B = {}
    for f in (HERE / "builds").glob("O_*_def.csv"):
        m = RX.match(f.name); B[(m[1], m[2], m[3])] = lineup_sets(f)
    rows = []
    for (sid, p, src), ls in B.items():
        if src == "old":
            continue
        o = B.get((sid, p, "old"))
        if o is None:
            continue
        rows.append(dict(slate=sid, preset=p, vs_old=src, n=len(ls), identical=ls == o,
                         shared=len(set(ls) & set(o))))
    D = pd.DataFrame(rows).sort_values(["preset", "vs_old", "slate"]); D.to_csv(HERE / "step1_identity.csv", index=False)
    print(D.groupby(["preset", "vs_old"]).agg(slates=("slate", "size"), identical=("identical", "sum"), shared=("shared", "mean")))


def sweep():
    rows, cache = [], {}
    own = {}
    for f in sorted((HERE / "builds").glob("O_*.csv")):
        m = RX.match(f.name)
        if not m or m[6]:
            continue
        sid, preset, src, k, seed = m[1], m[2], m[3], float(m[4]), int(m[5])
        if (sid, preset) not in cache:
            cache[(sid, preset)] = LG.scorer_hist(sid[5:]) if sid.startswith("hist_") else LG.scorer_2026(sid, preset)
        if sid not in own:
            o = pd.read_csv(HERE / "pools" / f"oracle__final_projections_dk_{sid}.csv", dtype={"player_id": str})
            own[sid] = dict(zip(o.player_id, o.estimated_ownership_pct))
        sc = cache[(sid, preset)][0]
        L = pd.read_csv(f, dtype={"player_id": str}).drop_duplicates(["lineup_id", "player_id"])
        per = []
        for _, g in L.groupby("lineup_id"):
            pts, pct, cash, top1 = sc(g)
            per.append(dict(proj=g.projection.sum(), pts=pts, pct=pct, cash=cash, top1=top1,
                            rown=sum(own[sid].get(p, 0) for p in g.player_id)))
        P = pd.DataFrame(per).sort_values("proj", ascending=False).reset_index(drop=True)
        rows.append(dict(slate=sid, src26="hist" if sid.startswith("hist_") else "2026",
                         season=sid[6:10] if sid.startswith("hist_") else "2026", preset=preset, own=src, k=k, seed=seed,
                         pick_pts=P.pts[0], pick_cash=float(P.cash[0]), mean_pts=P.pts.mean(), cash=P.cash.mean(),
                         mean_pct=P.pct.mean(), top1=P.top1.mean(), best_pts=P.pts.max(), proj=P.proj.mean(), real_own=P.rown.mean()))
    D = pd.DataFrame(rows); D.to_csv(HERE / "per_build.csv", index=False)
    met = ["mean_pts", "cash", "mean_pct", "pick_pts", "pick_cash", "best_pts", "top1", "proj", "real_own"]
    S = D.groupby(["src26", "season", "slate", "preset", "own", "k"])[met].mean().reset_index()
    base = S[S.k == 0].drop(columns="own").set_index(["preset", "slate"])
    rng = np.random.default_rng(0); out = []
    for (preset, src26, o, k), g in S[S.k != 0].groupby(["preset", "src26", "own", "k"]):
        g = g.set_index(["preset", "slate"]); c = g.index.intersection(base.index)
        for mt in met:
            d = g.loc[c, mt] - base.loc[c, mt]
            lo, hi = LG.boot(d.to_numpy(), rng)
            seas = d.groupby(g.loc[c, "season"]).mean()
            out.append(dict(preset=preset, src=src26, own=o, k=k, metric=mt, n=len(d), diff=d.mean(), lo90=lo, hi90=hi,
                            seasons_pos=int((seas > 0).sum()), seasons=len(seas)))
    Pd = pd.DataFrame(out); Pd.to_csv(HERE / "paired_vs_k0.csv", index=False)
    for mt in ["mean_pts", "cash", "pick_pts", "pick_cash", "top1", "real_own"]:
        print(f"\n== {mt}: diff vs k=0 [90% CI] (seasons>0 / seasons)")
        x = Pd[Pd.metric == mt].copy()
        x["cell"] = x.apply(lambda r: f"{r['diff']:+.3f} [{r.lo90:+.3f},{r.hi90:+.3f}] {r.seasons_pos}/{r.seasons}", axis=1)
        print(x.pivot_table(index=["preset", "src", "k"], columns="own", values="cell", aggfunc="first").to_string())
    print("\nk=0 baseline means:"); print(S[S.k == 0].groupby(["preset", "src26"])[met].mean().round(3).to_string())


if __name__ == "__main__":
    {"step1": step1, "sweep": sweep}[sys.argv[1]]()
