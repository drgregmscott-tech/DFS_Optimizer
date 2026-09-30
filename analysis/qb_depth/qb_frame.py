"""QB gap frame (research only; contains no FC data). Joins the guarded QB1 history rebuild (proj_qb/qb_rows.csv:
q_* = production-faithful QB1-guard engine, a_* = stubbed), vegas from ourproj, FC rush components + depth from the
model_vs_fc frame, actual components from nflverse weekly stats, and pre-lock trailing QB features.
Output (FC-derived -> git-ignored): data/fc_history/derived/qb_depth/qb_frame.parquet
"""
import glob, os
import numpy as np, pandas as pd

R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DER = os.path.join(R, "data/fc_history/derived")
OUT = os.path.join(DER, "qb_depth"); os.makedirs(OUT, exist_ok=True)


def main():
    X = pd.read_csv(os.path.join(DER, "proj_qb/qb_rows.csv"), dtype={"player_id": str})
    v = pd.concat([pd.read_csv(f, dtype={"player_id": str}, usecols=["season", "week", "player_id", "position", "implied_total",
                                                                      "over_under", "opponent", "games_played"])
                   for f in glob.glob(os.path.join(DER, "ourproj/proj_*.csv"))])
    v = v[v.position == "QB"].drop_duplicates(["season", "week", "player_id"]).drop(columns="position")
    X = X.merge(v, on=["season", "week", "player_id"], how="left")
    F = pd.read_parquet(os.path.join(DER, "model_vs_fc/frame.parquet"))
    F = F[F.pos == "QB"].drop_duplicates(["season", "week", "player_id"])[
        ["season", "week", "player_id", "fc_rush_att", "fc_rush_yd", "fc_rush_td", "pdepth", "inj"]]
    X = X.merge(F, on=["season", "week", "player_id"], how="left")
    # actual components
    ws = pd.concat([pd.read_parquet(os.path.join(R, f"data/weekly_stats_{s}.parquet")) for s in range(2019, 2027)])
    ws = ws[ws.season_type == "REG"]
    fum = [c for c in ["rushing_fumbles_lost", "sack_fumbles_lost", "receiving_fumbles_lost"] if c in ws]
    ws["fum"] = ws[fum].fillna(0).sum(axis=1)
    X = X.merge(ws[["player_id", "season", "week", "fum"]], on=["player_id", "season", "week"], how="left")
    X["fum"] = X.fum.fillna(0)
    X["act_rush"] = .1 * X.rushing_yards + 6 * X.rushing_tds + 3 * (X.rushing_yards >= 100)
    X["act_pass"] = X.act - X.act_rush  # includes INT, fumbles, 2pt, 300 bonus
    X["q_rush"] = .1 * X.q_proj_rush_yd + 6 * X.q_proj_rush_td
    X["q_pass"] = X.q_final_projection - X.q_rush
    X["fc_rush"] = .1 * X.fc_rush_yd + 6 * X.fc_rush_td
    X["fc_pass"] = X.fc - X.fc_rush
    X["spread"] = X.over_under / 2 - X.implied_total  # + = underdog
    X["sal_rank"] = X.groupby(["season", "week"]).salary.rank(ascending=False, method="first")
    # pre-lock trailing QB features from nflverse (prior games this season + last season, as-of week)
    w = ws[ws.position == "QB"][["player_id", "season", "week", "attempts", "carries", "rushing_yards", "rushing_tds",
                                 "passing_yards", "passing_tds", "fantasy_points_ppr"]].copy()
    w = w[w.attempts.fillna(0) + w.carries.fillna(0) >= 10].sort_values(["player_id", "season", "week"])
    w["rpts"] = .1 * w.rushing_yards + 6 * w.rushing_tds
    w["idx"] = w.season * 100 + w.week
    rows = []
    for pid, g in w.groupby("player_id"):
        idx, rp, att, car, fp = g.idx.values, g.rpts.values, g.attempts.values, g.carries.values, g.fantasy_points_ppr.values
        rows.append(pd.DataFrame({"player_id": pid, "idx": idx, "_rp": rp, "_att": att, "_car": car, "_fp": fp}))
    W = pd.concat(rows)
    X["idx"] = X.season * 100 + X.week
    feats = []
    for pid, g in X.groupby("player_id"):
        h = W[W.player_id == pid]
        for i, r in g.iterrows():
            p = h[h.idx < r.idx].tail(12)  # last 12 starts
            feats.append((i, p._rp.mean() if len(p) else np.nan, p._car.mean() if len(p) else np.nan,
                          p._att.mean() if len(p) else np.nan, p._fp.mean() if len(p) else np.nan, len(p)))
    Fe = pd.DataFrame(feats, columns=["i", "tr_rpts", "tr_car", "tr_att", "tr_fp", "tr_n"]).set_index("i")
    X = X.join(Fe)
    X.to_parquet(os.path.join(OUT, "qb_frame.parquet"))
    print(X.shape, X.columns.tolist())


if __name__ == "__main__":
    main()
