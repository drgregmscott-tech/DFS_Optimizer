"""History lineup replay, step 3: grade builds/hist/<old|new|fc>/lineups_multi_*.csv against the REAL FC Lineup Study
SE_dollar contest of the same slate (hist_meta/*.npz). FC-DERIVED -- DO NOT COMMIT outputs.

Per lineup: actual DK points, rank/percentile in the real field, cash (>= contest min-cash score), top-1%,
payout from the real prize table at that rank, ROI, and shape (QB salary, QB+WR/TE stack depth, punts, studs,
real summed field ownership). "pick" = the highest-projected lineup of a build (what a projection-first selector enters).
Paired comparisons (new-old, fc-old, fc-new) with 90% bootstrap CIs over slates.

usage: python analysis/lineup_replay/hist_grade.py
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
B = HERE / "builds" / "hist"


def main():
    rows = []
    for arm in ("old", "new", "fc"):
        for f in sorted((B / arm).glob("lineups_multi_dk_hist_*.csv")):
            m = re.search(r"hist_(h\d{4}w\d{2})_(cash|se_gpp|se3max_pool)_s(\d+)\.csv$", f.name)
            if not m:
                continue
            tag, preset, seed = m.group(1), m.group(2), int(m.group(3))
            M = np.load(HERE / "hist_meta" / f"{tag}.npz")
            fp = dict(zip(M["fp_ids"], M["fp"]))
            own = dict(zip(M["fp_ids"], M["own"]))
            field, cash, N = M["pts"], M["cash"], len(M["pts"])
            L = pd.read_csv(f).drop_duplicates(["lineup_id", "player_id"])
            L["pid"] = L.player_name.str.split("#").str[-1].astype(int)
            top1 = field[max(int(N * .01) - 1, 0)]
            for lid, g in L.groupby("lineup_id"):
                pts = sum(fp.get(p, 0.0) for p in g.pid)
                rank = int((field > pts).sum()) + 1
                pay = float(cash[min(rank, N) - 1]) if rank <= N else 0.0
                qb = g[g.position == "QB"].iloc[0]
                nd = g[g.position != "DST"]
                rows.append(dict(tag=tag, season=int(tag[1:5]), week=int(tag[6:]), arm=arm, preset=preset, seed=seed,
                                 lineup_id=lid, proj=g.projection.sum(), actual=pts, pct=1 - (rank - 1) / N,
                                 cash=pts >= M["mincash"], top1=pts >= top1,
                                 roi=(pay / float(M["cost"]) - 1) if cash.max() > 0 else np.nan,
                                 qb_sal=qb.salary, stack=int(((g.team == qb.team) & g.position.isin(["WR", "TE"])).sum()),
                                 punts=int((nd.salary <= 4000).sum()), studs=int((nd.salary >= 7000).sum()),
                                 field_own=sum(own.get(p, 0.0) for p in g.pid)))
    df = pd.DataFrame(rows)
    df.to_csv(HERE / "hist_lineups_graded.csv", index=False)
    keys = ["tag", "arm", "preset", "seed"]
    pick = df.loc[df.groupby(keys).proj.idxmax()].set_index(keys)
    agg = df.groupby(keys).agg(n=("actual", "size"), mean_pts=("actual", "mean"), best_pts=("actual", "max"),
                               cash_rate=("cash", "mean"), top1_rate=("top1", "mean"), mean_pct=("pct", "mean"),
                               roi=("roi", "mean"), qb_sal=("qb_sal", "mean"), stack=("stack", "mean"),
                               punts=("punts", "mean"), studs=("studs", "mean"), field_own=("field_own", "mean"))
    agg["pick_pts"] = pick.actual
    agg["pick_cash"] = pick.cash.astype(float)
    agg["pick_roi"] = pick.roi
    agg = agg.reset_index()
    agg.to_csv(HERE / "hist_summary.csv", index=False)
    rng = np.random.default_rng(0)
    out = []
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    for preset, g in agg.groupby("preset"):
        print(f"\n=== {preset}: mean over slates ===")
        print(g.groupby("arm")[["n", "mean_pts", "best_pts", "cash_rate", "top1_rate", "mean_pct", "roi", "pick_pts",
                                "pick_cash", "pick_roi", "qb_sal", "stack", "punts", "studs", "field_own"]].mean().round(3))
        W = g.pivot_table(index="tag", columns="arm", values=["mean_pts", "cash_rate", "pick_pts", "pick_cash", "roi", "mean_pct"])
        for a, b in (("new", "old"), ("fc", "old"), ("fc", "new")):
            for met in ("mean_pts", "cash_rate", "mean_pct", "roi", "pick_pts", "pick_cash"):
                if (met, a) not in W or (met, b) not in W:
                    continue
                d = (W[(met, a)] - W[(met, b)]).dropna().to_numpy()
                bs = [rng.choice(d, len(d)).mean() for _ in range(2000)]
                out.append(dict(preset=preset, cmp=f"{a}-{b}", metric=met, n_slates=len(d), diff=d.mean(),
                                lo=np.percentile(bs, 5), hi=np.percentile(bs, 95), win_share=(d > 0).mean()))
    C = pd.DataFrame(out)
    C.to_csv(HERE / "hist_paired.csv", index=False)
    print("\n=== paired diffs (90% bootstrap CI over slates) ===")
    print(C.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
