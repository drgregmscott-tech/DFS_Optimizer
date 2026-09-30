"""Backup/depth DNP frame (research; no FC data inside, but reads FC-slate-derived ourproj -> output git-ignored).

Universe: guarded production-faithful history rebuild (derived/proj_qb/ourproj_qb1, all positions, injuries stubbed)
2021-25 DK main slates, QB/RB/WR/TE. Label from public nflverse: weekly roster status, final injury designation,
snap counts (offense_snaps). zero_off = no offensive snap in the game.
Pre-lock features only: projection, salary, position, projection/salary rank at position within team,
lag snap% (last team game, last 3 team games), games with snaps in last 3, designation, practice status.
Output: data/fc_history/derived/qb_depth/dnp_frame.parquet
"""
import glob, os
import numpy as np, pandas as pd

R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
D = os.path.join(R, "data/fc_history/derived")
U = os.path.join(R, "data/nflverse_usage")
SK = ["QB", "RB", "WR", "TE"]
TEAMFIX = {"LAR": "LA", "JAC": "JAX", "OAK": "LV", "SD": "LAC", "STL": "LA", "WSH": "WAS"}


def roster(s):
    p = os.path.join(R, f"data/weekly_rosters_{s}.parquet")
    if not os.path.exists(p):
        p = os.path.join(R, f"analysis/inactives/raw/weekly_rosters_{s}.parquet")
    r = pd.read_parquet(p, columns=["season", "week", "gsis_id", "status", "game_type", "team", "depth_chart_position"])
    return r[r.game_type == "REG"].drop_duplicates(["week", "gsis_id"]).assign(season=s)


def snaps(seasons):
    ids = pd.read_parquet(os.path.join(U, "players.parquet"), columns=["gsis_id", "pfr_id"]).dropna().drop_duplicates("pfr_id")
    out = []
    for s in seasons:
        sc = pd.read_parquet(os.path.join(U, f"snap_counts_{s}.parquet"))
        sc = sc[sc.game_type == "REG"].merge(ids, left_on="pfr_player_id", right_on="pfr_id", how="left")
        out.append(sc[["season", "week", "gsis_id", "team", "offense_snaps", "offense_pct", "st_snaps"]])
    return pd.concat(out).dropna(subset=["gsis_id"]).drop_duplicates(["season", "week", "gsis_id"])


def lag_usage(sc, seasons):
    """Per player: snap% in the team's previous game(s) (0 if the team played and he had no snap row), as of each week."""
    team_games = sc.groupby(["season", "team"]).week.apply(lambda w: sorted(set(w))).to_dict()
    sc = sc.copy(); sc["idx"] = sc.season * 100 + sc.week
    rows = []
    by_p = {pid: g for pid, g in sc.groupby("gsis_id")}
    return by_p, team_games


def main(seasons=range(2021, 2026), proj_glob=os.path.join(D, "proj_qb/ourproj_qb1/proj_*.csv"), out_name="dnp_frame.parquet"):
    seasons = list(seasons)
    o = pd.concat([pd.read_csv(f, dtype={"player_id": str}, usecols=["season", "week", "player_id", "player_name", "position", "team",
                                                                       "salary", "final_projection", "games_played", "participation_effective"])
                   for f in glob.glob(proj_glob)])
    o = o[o.position.isin(SK) & o.season.isin(seasons)].drop_duplicates(["season", "week", "player_id"])
    o["team"] = o.team.replace(TEAMFIX)
    # ranks within team x position (pre-lock)
    o["proj_rank"] = o.groupby(["season", "week", "team", "position"]).final_projection.rank(ascending=False, method="first")
    o["sal_rank"] = o.groupby(["season", "week", "team", "position"]).salary.rank(ascending=False, method="first")
    o["n_pos_team"] = o.groupby(["season", "week", "team", "position"]).player_id.transform("size")
    top = o.groupby(["season", "week", "team", "position"]).final_projection.transform("max")
    o["gap_to_top"] = top - o.final_projection
    ro = pd.concat([roster(s) for s in seasons])
    o = o.merge(ro[["season", "week", "gsis_id", "status", "depth_chart_position"]], left_on=["season", "week", "player_id"],
                right_on=["season", "week", "gsis_id"], how="left").drop(columns="gsis_id")
    inj = pd.concat([pd.read_parquet(os.path.join(R, f"analysis/inactives/raw/injuries_{s}.parquet")) for s in seasons])
    inj = inj[inj.game_type == "REG"].drop_duplicates(["season", "week", "gsis_id"], keep="last")
    o = o.merge(inj[["season", "week", "gsis_id", "report_status", "practice_status"]], left_on=["season", "week", "player_id"],
                right_on=["season", "week", "gsis_id"], how="left").drop(columns="gsis_id")
    o["desig"] = o.report_status.fillna("None")
    sc = snaps(sorted(set(seasons) | {min(seasons) - 1}))
    o = o.merge(sc[["season", "week", "gsis_id", "offense_snaps", "offense_pct"]], left_on=["season", "week", "player_id"],
                right_on=["season", "week", "gsis_id"], how="left").drop(columns="gsis_id")
    o["zero_off"] = o.offense_snaps.fillna(0) <= 0
    # lagged snap share: team's previous games (this season; wk1 -> last season's final 3 team games)
    sc["idx"] = sc.season * 100 + sc.week
    tg = sc.groupby(["season", "team"]).week.unique()
    pp = sc.set_index(["gsis_id", "idx"]).offense_pct.to_dict()
    ptm = sc.sort_values("idx").groupby("gsis_id")[["idx", "team"]].apply(lambda g: list(zip(g.idx, g.team))).to_dict()
    L1, L3, N3, EV = [], [], [], []
    for r in o.itertuples():
        # team game list before this week (use player's current team; include prior season's tail)
        idxs = []
        for s_ in (r.season, r.season - 1):
            if (s_, r.team) in tg.index:
                idxs += [s_ * 100 + w for w in tg[(s_, r.team)] if s_ * 100 + w < r.season * 100 + r.week]
        idxs = sorted(idxs)[-3:]
        vals = [pp.get((r.player_id, i), 0.0) for i in idxs]
        # if player was on another team in those weeks (trade), take his own last 3 snap games instead
        own = [i for i, t in ptm.get(r.player_id, []) if i < r.season * 100 + r.week]
        if idxs and sum(vals) == 0 and own and own[-1] >= idxs[0]:
            vals = [pp.get((r.player_id, i), 0.0) for i in own[-3:]]
        L1.append(vals[-1] if vals else np.nan); L3.append(np.mean(vals) if vals else np.nan)
        N3.append(sum(v > 0 for v in vals) if vals else np.nan)
        EV.append(max([pp.get((r.player_id, i), 0.0) for i, _ in ptm.get(r.player_id, []) if i < r.season * 100 + r.week], default=0.0))
    o["snap_l1"], o["snap_l3"], o["n_snap_l3"], o["snap_max_ever"] = L1, L3, N3, EV
    o.to_parquet(os.path.join(D, "qb_depth", out_name))
    print(o.shape)


if __name__ == "__main__":
    main()
