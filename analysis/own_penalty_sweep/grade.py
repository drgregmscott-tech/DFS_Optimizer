"""own-penalty sweep grader (copied from lambda_reverify; lam column = own_penalty K). Grade lambda sweep builds vs real contests (2026 DK files; history FC Lineup Study SE fields). DO NOT COMMIT outputs.
Also: sigma calibration of the pools (z = (actual - proj)/sigma) for players with proj >= 5."""
import re, sys
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
LRD = REPO / "analysis" / "lineup_replay"
sys.path.insert(0, str(LRD))
import grade as G  # noqa

SID2LAB = {v[0]: k for k, v in G.SL.items()}
POOLS = REPO / "analysis" / "pool_randomization" / "builds" / "pools"


def scorer_2026(sid, preset):
    lab = SID2LAB[sid]; _, contests, rr = G.SL[lab]
    C = G.contest(*contests["mme" if (preset == "mme_gpp" and "mme" in contests) else "se"])
    wk = int(rr[2])
    ws = pd.read_parquet(REPO / "data" / "weekly_stats_2026.parquet"); ws = ws[ws.week == wk]
    raw = dict(zip(ws.player_display_name.map(G.norm), ws.fantasy_points_ppr))
    for rf in sorted((REPO / "data").glob(f"results_raw_dk_2026_wk{wk}*.csv")):
        r = pd.read_csv(rf); raw.update(dict(zip(r.player_name.map(G.norm), r.actual_fpts)))
    field = np.asarray(C["pts"]); t1 = np.sort(field)[::-1][max(int(len(field) * .01) - 1, 0)]
    fpt = lambda name: C["fp"].get(G.norm(name), raw.get(G.norm(name), np.nan))
    def f(g):
        pts = sum(np.nan_to_num(fpt(n)) for n in g.player_name)
        return pts, 1 - int((field > pts).sum()) / len(field), pts >= C["cash_line"], pts >= t1, np.nan
    return f, fpt


def scorer_hist(tag):
    M = np.load(LRD / "hist_meta" / f"{tag}.npz")
    fp = dict(zip(M["fp_ids"], M["fp"])); field = np.asarray(M["pts"]); mc = M["mincash"]; pay = np.asarray(M["cash"]); cost = float(M["cost"])
    t1 = np.sort(field)[::-1][max(int(len(field) * .01) - 1, 0)]
    fpt = lambda name: fp.get(int(str(name).split("#")[-1]), np.nan)
    def f(g):
        pts = sum(np.nan_to_num(fpt(n)) for n in g.player_name)
        r = int((field > pts).sum())
        return pts, 1 - r / len(field), pts >= mc, pts >= t1, (pay[r] if r < len(pay) else 0.0) / cost - 1 if cost > 0 else np.nan
    return f, fpt


def boot(d, rng, B=4000):
    bs = rng.choice(d, (B, len(d))).mean(1)
    return np.percentile(bs, 5), np.percentile(bs, 95)


def main():
    rows, cache, sig, owncache = [], {}, [], {}
    for f in sorted((HERE / "builds").glob("L_*.csv")):
        m = re.match(r"L_(.+)__(mme_gpp|se3max_pool|se_gpp)_l([+-]\d\.\d{3})_s(\d+)__(v2|oracle)\.csv$", f.name)
        sid, preset, lam, seed, arm = m.group(1), m.group(2), float(m.group(3)), int(m.group(4)), m.group(5)
        key = (sid, preset)
        if key not in cache:
            cache[key] = scorer_hist(sid[5:]) if sid.startswith("hist_") else scorer_2026(sid, preset)
        sc, fpt = cache[key]
        L = pd.read_csv(f, dtype={"player_id": str}).drop_duplicates(["lineup_id", "player_id"])
        for a in {arm, "v2"}:  # own = the arm's ownership (oracle K=0 base reuses the v2 K=0 lineups)
            if (sid, a) not in owncache:
                x = pd.read_csv(HERE / f"pools_{a}" / f"final_projections_dk_{sid}.csv", dtype={"player_id": str}).drop_duplicates("player_id")
                owncache[(sid, a)] = (x.set_index("player_id").estimated_ownership_pct * 900.0 / x.estimated_ownership_pct.sum()).to_dict()
        L["own"] = L.player_id.map(owncache[(sid, arm)]).fillna(0.0)
        per = []
        for lid, g in L.groupby("lineup_id"):
            pts, pct, cash, top1, roi = sc(g)
            sg = g.sigma.sum() if "sigma" in g else np.nan
            per.append(dict(proj=g.projection.sum(), own=g.own.sum(), roi=roi, pts=pts, pct=pct, cash=cash, top1=top1,
                            var=(g.sigma ** 2).sum() if "sigma" in g else np.nan))
        P = pd.DataFrame(per); P["obj"] = P.proj - lam * P.own
        P = P.sort_values(["obj", "proj"], ascending=False).reset_index(drop=True)  # pick = top of the solve's own objective
        rows.append(dict(arm=arm, slate=sid, src="hist" if sid.startswith("hist_") else "2026", season=sid[6:10] if sid.startswith("hist_") else "2026",
                         preset=preset, lam=lam, seed=seed, n=len(P),
                         pick_pts=P.pts[0], pick_pct=P.pct[0], pick_cash=float(P.cash[0]),
                         mean_pts=P.pts.mean(), mean_pct=P.pct.mean(), cash=P.cash.mean(), top1=P.top1.mean(),
                         any_top1=float(P.top1.any()), best_pts=P.pts.max(), best_pct=P.pct.max(),
                         p90_pts=P.pts.quantile(.9), proj=P.proj.mean(), var=P["var"].mean(),
                         own=P.own.mean(), roi=P.roi.mean(), pick_roi=P.roi[0]))
    D = pd.DataFrame(rows)
    D = pd.concat([D, D[(D.arm == "v2") & (D.lam == 0) & (D.src == "hist")].assign(arm="oracle")], ignore_index=True)
    D.to_csv(HERE / "per_build.csv", index=False)
    met = ["pick_pts", "pick_pct", "pick_cash", "pick_roi", "roi", "own", "mean_pts", "mean_pct", "cash", "top1", "any_top1", "best_pts", "p90_pts", "proj", "var"]
    S = D.groupby(["arm", "src", "season", "slate", "preset", "lam"])[met].mean().reset_index()
    T = S.groupby(["arm", "preset", "src", "lam"])[met].mean().round(3)
    SE = S[S.lam.abs() > -1].groupby(["arm", "preset", "season", "lam"])[["pick_pts", "pick_cash", "mean_pct", "cash", "roi", "best_pts", "top1"]].mean().round(3)
    rng = np.random.default_rng(0); out = []
    for (arm, preset, src), g in S.groupby(["arm", "preset", "src"]):
        base = g[g.lam == 0].set_index("slate")
        for lam in sorted(g.lam.unique()):
            if lam == 0:
                continue
            h = g[g.lam == lam].set_index("slate"); c = h.index.intersection(base.index)
            for mt in met:
                d = (h.loc[c, mt] - base.loc[c, mt]).to_numpy()
                lo, hi = boot(d, rng)
                # leave-one-season-out stability: sign of mean diff per season
                seas = (h.loc[c, mt] - base.loc[c, mt]).groupby(h.loc[c, "season"]).mean()
                out.append(dict(arm=arm, preset=preset, src=src, lam=lam, metric=mt, n_slates=len(d), diff=d.mean(), lo90=lo, hi90=hi,
                                seasons_pos=int((seas > 0).sum()), seasons=len(seas)))
    Pd = pd.DataFrame(out); Pd.to_csv(HERE / "paired_vs_k0.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30); pd.set_option("display.max_rows", 500)
    print(T.to_string()); print(); print(SE.to_string()); print()
    key = Pd[Pd.metric.isin(["pick_pts", "pick_cash", "pick_roi", "mean_pct", "cash", "roi", "top1", "any_top1", "best_pts", "own", "proj"])]
    print(key.round(4).to_string(index=False)); print()


if __name__ == "__main__":
    main()
