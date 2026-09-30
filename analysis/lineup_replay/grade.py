"""Grade replay lineups (builds/<arm>/lineups_multi_*.csv) against the REAL DK contest (data/contest_results/*_full.csv).

Per lineup: actual DK points (contest FPTS block, fallback data/results_raw_dk_2026_*), rank in the real contest,
percentile, cash (top 25% SE/3-max, top 22% MME -- same lines as WK3_ROOT_CAUSE_FINDINGS Phase 1/2), top-1%,
plus construction shape (QB salary, stack depth, bring-back, punts <= $4K, studs >= $7K, real field own sum).
"Pick" = the highest-projected lineup in the build (what a projection-first selector submits).

usage: python analysis/lineup_replay/grade.py   -> lineups_graded.csv, summary.csv (DO NOT COMMIT: contest-derived)
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CR = REPO / "data" / "contest_results"
TOK = re.compile(r"\b(QB|RB|WR|TE|FLEX|DST)\s+")

# slate label -> (slate_id, {contest: (file, cash_pct)}, results_raw file)
SL = {
    "wk1_main": ("dk_classic_wk1_main_13Sep2026", {"se": ("dk_classic_wk1_main_13Sep2026_full.csv", .25)}, "wk1"),
    "wk1_early": ("dk_classic_wk1_early_13Sep2026", {"se": ("dk_classic_wk1_early_13Sep2026_full.csv", .25)}, "wk1_early"),
    "wk1_afternoon": ("dk_classic_wk1_afternoon_13Sep2026", {"se": ("dk_classic_wk1_afternoon_13Sep2026_full.csv", .25)}, "wk1_afternoon"),
    "wk2_main": ("dk_classic_wk2_main_20Sep2026", {"se": ("dk_classic_wk2_main_20Sep2026_se3max_full.csv", .25),
                                                    "mme": ("dk_classic_wk2_main_20Sep2026_mme_full.csv", .22)}, "wk2"),
    "wk2_early": ("dk_classic_wk2_early_20Sep2026", {"se": ("dk_classic_wk2_early_20Sep2026_se3max_full.csv", .25)}, "wk2_early"),
    "wk2_afternoon": ("dk_classic_wk2_afternoon_20Sep2026", {"se": ("dk_classic_wk2_afternoon_20Sep2026_se3max_full.csv", .25)}, "wk2_afternoon"),
    "wk3_main": ("dk_classic_wk3_main_27Sep2026", {"se": ("dk_classic_wk3_main_27Sep2026_se3max_full.csv", .25),
                                                    "mme": ("dk_classic_wk3_main_27Sep2026_mme_full.csv", .22)}, "wk3_main"),
    "wk3_early": ("dk_classic_wk3_early_27Sep2026", {"se": ("dk_classic_wk3_early_27Sep2026_se3max_full.csv", .25)}, "wk3_early"),
    "wk3_afternoon": ("dk_classic_wk3_afternoon_27Sep2026", {"se": ("dk_classic_wk3_afternoon_27Sep2026_se3max_full.csv", .25)}, "wk3_afternoon"),
}


def norm(s):
    s = str(s).lower()
    s = re.sub(r"[.'’]", "", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s)
    s = re.sub(r"[^a-z ]", "", s)
    return " ".join(s.split())


_cache = {}


def contest(fname, cash_pct):
    if fname in _cache:
        return _cache[fname]
    df = pd.read_csv(CR / fname, encoding="utf-8-sig", low_memory=False)
    tab = df[["Player", "%Drafted", "FPTS"]].dropna(subset=["Player"]).copy()
    tab["k"] = tab.Player.map(norm)
    tab["own"] = tab["%Drafted"].astype(str).str.rstrip("%").astype(float)
    own = tab.groupby("k")["own"].sum().to_dict()
    fp = tab.drop_duplicates("k").set_index("k")["FPTS"].to_dict()
    e = df.iloc[:, :6].dropna(subset=["Lineup"]).drop_duplicates("EntryId")
    pts = np.sort(e.Points.astype(float).to_numpy())[::-1]
    N = len(pts)
    out = dict(pts=pts, N=N, fp=fp, own=own, cash_line=pts[int(np.floor(N * cash_pct)) - 1],
               top1_line=pts[max(int(np.floor(N * .01)) - 1, 0)], median=float(np.median(pts)), cash_pct=cash_pct)
    _cache[fname] = out
    return out


def main():
    rows = []
    for lab, (sid, contests, rr) in SL.items():
        # fallback points: every results_raw file of that week, then nflverse PPR (+3 yardage bonuses ignored) by name
        wk = int(rr[2])
        ws = pd.read_parquet(REPO / "data" / "weekly_stats_2026.parquet")
        ws = ws[ws.week == wk]
        rawfp = dict(zip(ws.player_display_name.map(norm), ws.fantasy_points_ppr))
        for rf in sorted((REPO / "data").glob(f"results_raw_dk_2026_wk{wk}*.csv")):
            raw = pd.read_csv(rf)
            rawfp.update(dict(zip(raw.player_name.map(norm), raw.actual_fpts)))
        for arm in ("old", "new"):
            proj = pd.read_csv(HERE / "builds" / arm / f"final_projections_dk_{sid}.csv", dtype={"player_id": str})
            est = dict(zip(proj.player_id, proj.estimated_ownership_pct))
            for f in sorted((HERE / "builds" / arm).glob(f"lineups_multi_dk_{sid}_*.csv")):
                m = re.search(r"_(cash|se_gpp|se3max_pool|mme_gpp)_s(\d+)\.csv$", f.name)
                if not m:
                    continue
                preset, seed = m.group(1), int(m.group(2))
                ckey = "mme" if (preset == "mme_gpp" and "mme" in contests) else "se"
                C = contest(*contests[ckey])
                L = pd.read_csv(f, dtype={"player_id": str})
                L = L.drop_duplicates(["lineup_id", "player_id"])
                for lid, g in L.groupby("lineup_id"):
                    ks = g.player_name.map(norm)
                    miss = [k for k in ks if k not in C["fp"] and k not in rawfp]
                    pts = sum(C["fp"].get(k, rawfp.get(k, 0.0)) for k in ks)
                    rank = int((C["pts"] > pts).sum()) + 1
                    pct = 1 - (rank - 1) / C["N"]
                    qb = g[g.position == "QB"].iloc[0]
                    mates = g[(g.team == qb.team) & g.position.isin(["WR", "TE"])]
                    bb = g[(g.team == qb.opponent) & g.position.isin(["RB", "WR", "TE"])]
                    nd = g[g.position != "DST"]
                    rows.append(dict(slate=lab, arm=arm, preset=preset, seed=seed, contest=ckey, lineup_id=lid,
                                     proj=g.projection.sum(), actual=pts, rank=rank, pct=pct,
                                     cash=pts >= C["cash_line"], top1=pts >= C["top1_line"],
                                     cash_line=C["cash_line"], top1_line=C["top1_line"], N=C["N"],
                                     field_own=sum(C["own"].get(k, 0.0) for k in ks),
                                     est_own=sum(est.get(p, 0.0) for p in g.player_id),
                                     qb=qb.player_name, qb_sal=qb.salary, stack=len(mates), bring_back=len(bb),
                                     punts=int((nd.salary <= 4000).sum()), studs=int((nd.salary >= 7000).sum()),
                                     dst_sal=int(g[g.position == "DST"].salary.iloc[0]), salary=g.salary.sum(),
                                     n_missing_fpts=len(miss)))
    df = pd.DataFrame(rows)
    df.to_csv(HERE / "lineups_graded.csv", index=False)
    pick = df.loc[df.groupby(["slate", "arm", "preset", "seed"]).proj.idxmax()]
    agg = df.groupby(["slate", "arm", "preset", "seed"]).agg(
        n=("actual", "size"), proj=("proj", "mean"), mean_pts=("actual", "mean"), best_pts=("actual", "max"),
        cash_rate=("cash", "mean"), top1_rate=("top1", "mean"), mean_pct=("pct", "mean"), best_pct=("pct", "max"),
        cash_line=("cash_line", "first"), qb_sal=("qb_sal", "mean"), stack=("stack", "mean"), punts=("punts", "mean"),
        studs=("studs", "mean"), field_own=("field_own", "mean"), est_own=("est_own", "mean")).reset_index()
    agg = agg.merge(pick[["slate", "arm", "preset", "seed", "actual", "pct", "cash", "qb"]].rename(
        columns={"actual": "pick_pts", "pct": "pick_pct", "cash": "pick_cash", "qb": "pick_qb"}),
        on=["slate", "arm", "preset", "seed"])
    agg.to_csv(HERE / "summary.csv", index=False)
    print("missing-fpts player slots:", int(df.n_missing_fpts.sum()))
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    for preset, g in agg.groupby("preset"):
        t = g.groupby("arm")[["n", "proj", "mean_pts", "best_pts", "cash_rate", "top1_rate", "mean_pct", "pick_pts",
                              "pick_cash", "qb_sal", "stack", "punts", "studs", "field_own"]].mean()
        print(f"\n=== {preset} (mean over slate x seed) ===\n{t.round(3)}")
        w = g.pivot_table(index=["slate", "seed"], columns="arm", values=["mean_pts", "cash_rate", "pick_pts"])
        print(w.round(2))


if __name__ == "__main__":
    main()
