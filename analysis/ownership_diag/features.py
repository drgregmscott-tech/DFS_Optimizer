"""Build candidate pre-lock features on top of the LOWO frame (refit_final.pkl).

Pre-lock sources only: DK salary export (Salary, AvgPointsPerGame, Status),
previous week's DK salary export (salary change), nflverse weekly stats for
the PREVIOUS week (fpts, targets, carries), final_projections columns.
"""
from pathlib import Path
import numpy as np, pandas as pd

REPO = Path(r"C:\Users\gmsco\Desktop\DFS_Optimizer")
SCR = Path(r"C:\Users\gmsco\AppData\Local\Temp\claude\C--Users-gmsco-Desktop-DFS-Optimizer\36a97c4a-433e-4ff9-b857-c9a23bb65822\scratchpad")
OUT = REPO / "analysis/ownership_diag"


def sal_file(sid):
    return pd.read_csv(REPO / f"data/salaries_dk_{sid}.csv", dtype={"player_id": str})


def build():
    art, d = pd.read_pickle(SCR / "refit_final.pkl")
    d = d.copy()
    # --- DK export fields (what every DK user sees in the lobby) ---
    parts = []
    for sid, g in d.groupby("slate_id"):
        s = sal_file(sid).drop_duplicates("player_id").set_index("player_id")
        g = g.assign(dk_avg=g.player_id.map(s.AvgPointsPerGame).astype(float),
                     dk_status=g.player_id.map(s.Status).fillna(""))
        # vacated opportunity: same team+position teammates flagged OUT/D/IR on the export
        # weighted by their public DK avg (the "headline" the field sees)
        s2 = s.reset_index()
        inj = s2[s2.Status.isin(["OUT", "O", "D", "IR"])]
        vac = inj.groupby(["TeamAbbrev", "Position"]).AvgPointsPerGame.sum()
        g["vacated"] = [float(vac.get((t, p), 0.0)) for t, p in zip(g.team, g.position)]
        # previous-week salary (wk2 slates only; union of all wk1 classic exports)
        if g.week.iloc[0] == 2:
            prev = pd.concat([sal_file(f"dk_classic_wk1_{p}_13Sep2026") for p in ("main", "early", "afternoon")])
            prev = prev.drop_duplicates("player_id").set_index("player_id").salary
            g["sal_prev"] = g.player_id.map(prev)
        else:
            g["sal_prev"] = np.nan
        parts.append(g)
    d = pd.concat(parts).sort_index()
    d["sal_chg"] = ((d.salary - d.sal_prev) / 1000).fillna(0.0)
    d["has_prev_sal"] = d.sal_prev.notna().astype(float)
    # --- previous week actual stats (wk2 only; wk1 has no in-season prior) ---
    ws = pd.read_parquet(REPO / "data/weekly_stats_2026.parquet")
    w1 = ws[ws.week == 1].copy()
    w1["dkp"] = w1.fantasy_points_ppr + 3 * (w1.passing_yards >= 300) + 3 * (w1.rushing_yards >= 100) + 3 * (w1.receiving_yards >= 100)
    w1 = w1.set_index("player_id")
    wk2 = d.week == 2
    d["prev_fpts"] = np.where(wk2, d.player_id.map(w1.dkp), np.nan)
    d["prev_opps"] = np.where(wk2, d.player_id.map(w1.targets.fillna(0) + w1.carries.fillna(0)), np.nan)
    # --- public-value proxies ---
    d["pub_val"] = d.dk_avg / (d.salary / 1000)          # DK-displayed pts per $K
    d["our_val"] = d.final_projection / (d.salary / 1000)
    d["pub_minus_ours"] = d.dk_avg - d.final_projection
    grp = d.groupby(["slate_id", "position"])
    d["pub_val_rank"] = grp.pub_val.rank(ascending=False, pct=True)
    d["our_val_rank"] = grp.our_val.rank(ascending=False, pct=True)
    d["proj_rank"] = grp.final_projection.rank(ascending=False)
    d["sal_rank"] = grp.salary.rank(ascending=False)
    d["rank_gap"] = d.sal_rank - d.proj_rank           # + = projects better than priced
    # salary-implied points: per slate/position linear fit of proj on salary
    d["proj_vs_salfit"] = 0.0
    for _, g in grp:
        if len(g) > 3:
            b = np.polyfit(g.salary / 1000, g.final_projection, 1)
            d.loc[g.index, "proj_vs_salfit"] = g.final_projection - np.polyval(b, g.salary / 1000)
    d["game_total"] = d.over_under
    d["imp"] = d.implied_total
    d["imp_rank"] = d.groupby("slate_id").imp.rank(ascending=False, pct=True)
    d["cheap_te"] = ((d.position == "TE") & (d.salary <= 4000)).astype(float)
    d["qb_mid"] = ((d.position == "QB") & d.salary.between(5500, 6900)).astype(float)
    d["pos_n"] = grp.player_id.transform("count")
    d["is_q"] = d.dk_status.isin(["Q", "D"]).astype(float)
    # slate structure: how much of the position's projection is in top option
    d["top_gap"] = grp.final_projection.transform("max") - d.final_projection
    d["prev_fpts_f"] = d.prev_fpts.fillna(d.dk_avg)     # prior fpts where known, else DK avg
    d["prev_fpts_minus_sal"] = d.prev_fpts_f - 3.0 * d.salary / 1000  # "hit 3x last time"
    lg = lambda x: np.log(np.clip(x, 0.2, 74) / 75 / (1 - np.clip(x, 0.2, 74) / 75))
    d["resid"] = lg(d.own) - lg(d.lowo)
    d["err"] = d.lowo - d.own
    return d


CANDIDATES = ["dk_avg", "pub_val", "pub_val_rank", "pub_minus_ours", "sal_chg", "prev_fpts_f",
              "prev_fpts_minus_sal", "prev_opps", "vacated", "imp", "imp_rank", "game_total",
              "rank_gap", "proj_vs_salfit", "our_val", "cheap_te", "qb_mid", "is_q", "top_gap", "pos_n"]

if __name__ == "__main__":
    d = build()
    d.to_pickle(SCR / "diag_frame.pkl")
    print(d[["dk_avg", "sal_chg", "prev_fpts", "vacated"]].describe().round(2))
