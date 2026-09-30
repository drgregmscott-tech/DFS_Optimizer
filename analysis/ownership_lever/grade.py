"""Grade ownership-lever builds vs real contests, paired vs k=0 (same preset/lambda). DO NOT COMMIT outputs."""
import re, sys
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent; REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "analysis" / "lambda_reverify"))
import importlib.util
spec = importlib.util.spec_from_file_location("lamgrade", REPO / "analysis/lambda_reverify/grade.py"); LG = importlib.util.module_from_spec(spec); spec.loader.exec_module(LG)
sys.path.insert(0, str(HERE)); from own_sweep import real_own  # noqa
POOLS = LG.POOLS


def main(preset):
    rows, cache, owncache = [], {}, {}
    for f in sorted((HERE / "builds").glob(f"O_*__{preset}_*.csv")):
        m = re.match(rf"O_(.+)__{preset}_(mod|real)_k([+-]\d\.\d{{3}})_s(\d+)\.csv$", f.name)
        sid, arm, k, seed = m.group(1), m.group(2), float(m.group(3)), int(m.group(4))
        if sid not in cache:
            cache[sid] = LG.scorer_hist(sid[5:]) if sid.startswith("hist_") else LG.scorer_2026(sid, preset)
            pool = pd.read_csv(POOLS / f"final_projections_dk_{sid}.csv", dtype={"player_id": str})
            owncache[sid] = (dict(zip(pool.player_id, real_own(sid, pool))), dict(zip(pool.player_id, pool.estimated_ownership_pct)))
        sc = cache[sid][0]; ro, mo = owncache[sid]
        L = pd.read_csv(f, dtype={"player_id": str}).drop_duplicates(["lineup_id", "player_id"])
        per = []
        for lid, g in L.groupby("lineup_id"):
            pts, pct, cash, top1 = sc(g)
            per.append(dict(proj=g.projection.sum(), pts=pts, pct=pct, cash=cash, top1=top1,
                            real_own=sum(ro.get(p, 0) for p in g.player_id), mod_own=sum(mo.get(p, 0) for p in g.player_id)))
        P = pd.DataFrame(per).sort_values("proj", ascending=False).reset_index(drop=True)
        base = dict(slate=sid, season=sid[6:10] if sid.startswith("hist_") else "2026", src="hist" if sid.startswith("hist_") else "2026",
                    arm=arm, k=k, seed=seed)
        rows.append(dict(base, pick_pts=P.pts[0], pick_pct=P.pct[0], pick_cash=float(P.cash[0]), mean_pts=P.pts.mean(),
                         mean_pct=P.pct.mean(), cash=P.cash.mean(), top1=P.top1.mean(), any_top1=float(P.top1.any()),
                         best_pts=P.pts.max(), best_pct=P.pct.max(), proj=P.proj.mean(), real_own=P.real_own.mean(), mod_own=P.mod_own.mean()))
    D = pd.DataFrame(rows); D.to_csv(HERE / f"per_build_{preset}.csv", index=False)
    met = ["pick_pts", "pick_cash", "mean_pts", "mean_pct", "cash", "top1", "any_top1", "best_pts", "best_pct", "proj", "real_own", "mod_own"]
    S = D.groupby(["src", "season", "slate", "arm", "k"])[met].mean().reset_index()
    b0 = S[S.k == 0].drop(columns="arm").set_index("slate")
    rng = np.random.default_rng(0); out = []
    for (src, arm, k), g in S[S.k != 0].groupby(["src", "arm", "k"]):
        g = g.set_index("slate"); c = g.index.intersection(b0.index)
        for mt in met:
            d = (g.loc[c, mt] - b0.loc[c, mt]); lo, hi = LG.boot(d.to_numpy(), rng)
            seas = d.groupby(g.loc[c, "season"]).mean()
            out.append(dict(src=src, arm=arm, k=k, metric=mt, n=len(d), base=b0.loc[c, mt].mean(), diff=d.mean(), lo90=lo, hi90=hi,
                            seasons_pos=int((seas > 0).sum()), seasons=len(seas)))
    Pd = pd.DataFrame(out); Pd.to_csv(HERE / f"paired_vs_k0_{preset}.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 1000)
    for src in ["hist", "2026"]:
        print(f"==== {preset} {src}")
        x = Pd[(Pd.src == src) & Pd.metric.isin(["cash", "mean_pct", "top1", "any_top1", "best_pts", "pick_pts", "pick_cash", "proj", "real_own"])]
        print(x.drop(columns="src").round(4).to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "mme_gpp")
