"""Grade the sweep builds against real contests. 2026: DK contest files (lineup_replay/grade.py helpers, top-25% line).
History: FC Lineup Study SE contests (lineup_replay/hist_meta, contest min-cash). Outputs are contest/FC-derived: DO NOT COMMIT."""
import re, sys, itertools
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
LRD = REPO / "analysis" / "lineup_replay"
sys.path.insert(0, str(LRD))
import grade as G  # noqa

SID2LAB = {v[0]: k for k, v in G.SL.items()}


def scorer_2026(sid):
    lab = SID2LAB[sid]; _, contests, rr = G.SL[lab]
    C = G.contest(*contests["se"])
    wk = int(rr[2])
    ws = pd.read_parquet(REPO / "data" / "weekly_stats_2026.parquet"); ws = ws[ws.week == wk]
    raw = dict(zip(ws.player_display_name.map(G.norm), ws.fantasy_points_ppr))
    for rf in sorted((REPO / "data").glob(f"results_raw_dk_2026_wk{wk}*.csv")):
        r = pd.read_csv(rf); raw.update(dict(zip(r.player_name.map(G.norm), r.actual_fpts)))
    def f(g):
        pts = sum(C["fp"].get(k, raw.get(k, 0.0)) for k in g.player_name.map(G.norm))
        rank = int((C["pts"] > pts).sum()) + 1
        return pts, 1 - (rank - 1) / C["N"], pts >= C["cash_line"]
    return f


def scorer_hist(tag):
    M = np.load(LRD / "hist_meta" / f"{tag}.npz")
    fp = dict(zip(M["fp_ids"], M["fp"])); field = M["pts"]; N = len(field); mc = M["mincash"]
    def f(g):
        pts = sum(fp.get(int(str(n).split("#")[-1]), 0.0) for n in g.player_name)
        rank = int((field > pts).sum()) + 1
        return pts, 1 - (rank - 1) / N, pts >= mc
    return f


def main():
    rows = []
    files = sorted((HERE / "builds").glob("L_*.csv"))
    cache = {}
    for f in files:
        m = re.match(r"L_(.+)_(r\d+_u\d)_s(\d+)\.csv$", f.name)
        sid, cfg, seed = m.group(1), m.group(2), int(m.group(3))
        if sid not in cache:
            cache[sid] = scorer_hist(sid[5:]) if sid.startswith("hist_") else scorer_2026(sid)
        sc = cache[sid]
        L = pd.read_csv(f, dtype={"player_id": str}).drop_duplicates(["lineup_id", "player_id"])
        per = []
        for lid, g in L.groupby("lineup_id"):
            pts, pct, cash = sc(g)
            qb = g[g.position == "QB"].iloc[0]
            mates = tuple(sorted(g[(g.team == qb.team) & g.position.isin(["WR", "TE"])].player_id))
            per.append(dict(lid=lid, proj=g.projection.sum(), pts=pts, pct=pct, cash=cash,
                            pids=frozenset(g.player_id), qb=qb.player_id, stk=(qb.player_id,) + mates))
        P = pd.DataFrame(per).sort_values("proj", ascending=False).reset_index(drop=True)
        top = P.pids.iloc[0]
        ov = P.pids.map(lambda s: len(s & top))
        exp = L.groupby("player_id").lineup_id.nunique() / P.shape[0]
        t5 = P.pids.iloc[:5].tolist()
        pair = np.mean([len(a & b) for a, b in itertools.combinations(t5, 2)])
        rows.append(dict(slate=sid, src="hist" if sid.startswith("hist_") else "2026", cfg=cfg, seed=seed, n=len(P),
                         p1_pts=P.pts[0], p1_pct=P.pct[0], p1_cash=float(P.cash[0]), p1_proj=P.proj[0],
                         t3_pct=P.pct[:3].mean(), t3_cash=P.cash[:3].mean(), t3_any=float(P.cash[:3].any()),
                         t5_pct=P.pct[:5].mean(), t5_cash=P.cash[:5].mean(), t5_pts=P.pts[:5].mean(),
                         pool_pct=P.pct.mean(), pool_cash=P.cash.mean(), pool_pts=P.pts.mean(),
                         proj_gap_5=P.proj[0] - P.proj[4],
                         uniq_players=exp.size, max_exp=exp.max(), n_qb=P.qb.nunique(), n_stacks=P.stk.nunique(),
                         near_dup=(ov[1:] >= 8).mean(), t5_pair_overlap=pair, build_sec=float(L.build_sec.iloc[0])))
    D = pd.DataFrame(rows); D.to_csv(HERE / "per_build.csv", index=False)
    met = [c for c in D.columns if c not in ("slate", "src", "cfg", "seed")]
    S = D.groupby(["src", "slate", "cfg"])[met].mean().reset_index()  # seed-average within slate
    rng = np.random.default_rng(0)
    out = []
    for src, g in S.groupby("src"):
        for cfg, h in g.groupby("cfg"):
            r = dict(src=src, cfg=cfg, n_slates=h.slate.nunique(), seeds=D[(D.src == src) & (D.cfg == cfg)].seed.nunique())
            for c in met:
                r[c] = h[c].mean()
            out.append(r)
    T = pd.DataFrame(out); T.to_csv(HERE / "table.csv", index=False)
    # paired diffs vs r20_u1 (current preset), 90% bootstrap CI clustered by slate
    P = []
    for src, g in S.groupby("src"):
        W = g.set_index(["slate", "cfg"])
        base = g[g.cfg == "r20_u1"].set_index("slate")
        for cfg in sorted(g.cfg.unique()):
            if cfg == "r20_u1":
                continue
            h = g[g.cfg == cfg].set_index("slate")
            common = h.index.intersection(base.index)
            for c in ("p1_pts", "p1_cash", "p1_pct", "t3_cash", "t3_any", "t5_cash", "t5_pct", "pool_cash", "pool_pct"):
                d = (h.loc[common, c] - base.loc[common, c]).to_numpy()
                bs = [rng.choice(d, len(d)).mean() for _ in range(2000)]
                P.append(dict(src=src, cmp=f"{cfg}-r20_u1", metric=c, n=len(d), diff=d.mean(),
                              lo=np.percentile(bs, 5), hi=np.percentile(bs, 95)))
    P = pd.DataFrame(P); P.to_csv(HERE / "paired_vs_r20.csv", index=False)
    pd.set_option("display.width", 300); pd.set_option("display.max_columns", 40)
    cols = ["src", "cfg", "n_slates", "seeds", "p1_pts", "p1_cash", "p1_pct", "t3_cash", "t3_any", "t3_pct", "t5_cash", "t5_pct",
            "pool_cash", "pool_pct", "pool_pts", "uniq_players", "max_exp", "n_qb", "n_stacks", "near_dup", "t5_pair_overlap", "proj_gap_5", "build_sec"]
    print(T[cols].round(3).to_string(index=False))
    print(P.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
