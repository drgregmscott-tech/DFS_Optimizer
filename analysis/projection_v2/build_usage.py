"""Build a public-data (nflverse only, no FC) weekly usage table + pre-lock lag features.

Inputs : data/weekly_stats_{2020..2026}.parquet, data/nflverse_usage/{snap_counts,pbp_participation}_*.parquet,
         data/nflverse_usage/players.parquet (pfr->gsis map)
Output : data/nflverse_usage/usage_weekly.parquet   one row per (player_id, season, week) played (REG)
         data/nflverse_usage/usage_features.parquet one row per (player_id, season, week) for weeks 1-18, containing
         ONLY information available before that week's games (lags / EWMAs / prior-season aggregates).
"""
from pathlib import Path
import numpy as np, pandas as pd

R = Path(__file__).resolve().parents[2]
U = R / "data/nflverse_usage"
SEASONS = range(2020, 2027)


def dk_points(w):
    f = lambda c: w[c].fillna(0) if c in w else 0
    return (f("passing_yards") * .04 + f("passing_tds") * 4 - f("passing_interceptions") + 3 * (f("passing_yards") >= 300)
            + f("rushing_yards") * .1 + f("rushing_tds") * 6 + 3 * (f("rushing_yards") >= 100)
            + f("receptions") + f("receiving_yards") * .1 + f("receiving_tds") * 6 + 3 * (f("receiving_yards") >= 100)
            - f("rushing_fumbles_lost") - f("receiving_fumbles_lost") - f("sack_fumbles_lost")
            + 2 * (f("passing_2pt_conversions") + f("rushing_2pt_conversions") + f("receiving_2pt_conversions")))


def weekly():
    out = []
    for s in SEASONS:
        w = pd.read_parquet(R / f"data/weekly_stats_{s}.parquet")
        w = w[w.season_type.fillna("REG") == "REG"]
        w = w[w.position.isin(["QB", "RB", "WR", "TE", "FB"])].copy()
        w["dk"] = dk_points(w)
        out.append(w[["player_id", "player_display_name", "position", "season", "week", "team", "attempts", "sacks_suffered",
                      "carries", "targets", "receptions", "receiving_yards", "receiving_tds", "dk"]])
    w = pd.concat(out, ignore_index=True)
    # team pass volume from QB rows (attempts + sacks = dropbacks proxy), team targets
    tm = w.groupby(["season", "week", "team"]).agg(team_att=("attempts", "sum"), team_sacks=("sacks_suffered", "sum"),
                                                   team_tgt=("targets", "sum"), team_car=("carries", "sum")).reset_index()
    tm["team_db"] = tm.team_att + tm.team_sacks
    w = w.merge(tm, on=["season", "week", "team"], how="left")
    w["tgt_share"] = w.targets / w.team_tgt.replace(0, np.nan)
    return w


def snaps():
    pl = pd.read_parquet(U / "players.parquet")[["gsis_id", "pfr_id"]].dropna().drop_duplicates("pfr_id")
    out = []
    for s in SEASONS:
        p = U / f"snap_counts_{s}.parquet"
        if p.exists():
            d = pd.read_parquet(p); d = d[d.game_type == "REG"]
            out.append(d[["pfr_player_id", "season", "week", "offense_snaps", "offense_pct"]])
    d = pd.concat(out).merge(pl, left_on="pfr_player_id", right_on="pfr_id", how="inner")
    return d.rename(columns={"gsis_id": "player_id", "offense_pct": "snap_pct"})[["player_id", "season", "week", "offense_snaps", "snap_pct"]] \
        .drop_duplicates(["player_id", "season", "week"])


def routes():
    """Route proxy: on-field on a dropback play (time_to_throw non-null or was_pressure non-null w/ pass rushers>0)."""
    out = []
    for s in SEASONS:
        p = U / f"pbp_participation_{s}.parquet"
        if not p.exists():
            continue
        d = pd.read_parquet(p, columns=["nflverse_game_id", "play_id", "possession_team", "offense_players", "time_to_throw",
                                        "number_of_pass_rushers", "route"])
        db = d.time_to_throw.notna() | (d.route.fillna("").str.len() > 0)
        d = d[db & d.offense_players.notna()]
        d["season"] = d.nflverse_game_id.str[:4].astype(int)
        d["week"] = d.nflverse_game_id.str[5:7].astype(int)
        tdb = d.groupby(["season", "week", "possession_team"]).size().rename("part_team_db").reset_index()
        e = d[["season", "week", "possession_team", "offense_players"]].assign(
            player_id=d.offense_players.str.split(";")).explode("player_id")
        r = e.groupby(["player_id", "season", "week", "possession_team"]).size().rename("routes").reset_index()
        r = r.merge(tdb, on=["season", "week", "possession_team"])
        r["route_part"] = r.routes / r.part_team_db
        out.append(r[["player_id", "season", "week", "routes", "part_team_db", "route_part"]])
    return pd.concat(out).drop_duplicates(["player_id", "season", "week"])


def ewm_lag(g, col, hl):
    """EWMA of previous games (excludes current), halflife in games."""
    return g[col].transform(lambda x: x.shift(1).ewm(halflife=hl, min_periods=1).mean())


def features(w):
    w = w.sort_values(["player_id", "season", "week"]).reset_index(drop=True)
    w["tprr"] = w.targets / w.routes.replace(0, np.nan)
    g = w.groupby("player_id")
    # career-long recency-weighted (crosses seasons), current season to-date, prior season
    for col in ["tgt_share", "snap_pct", "route_part", "tprr", "dk", "targets"]:
        for hl in (2, 4, 8):
            w[f"{col}_ewm{hl}"] = ewm_lag(g, col, hl)
    gs = w.groupby(["player_id", "season"])
    w["cur_gp"] = gs.cumcount()
    w["cur_dk_mean"] = gs.dk.transform(lambda x: x.shift(1).expanding().mean())
    w["cur_tgt_share"] = gs.tgt_share.transform(lambda x: x.shift(1).expanding().mean())
    w["cur_route_part"] = gs.route_part.transform(lambda x: x.shift(1).expanding().mean())
    w["cur_snap_pct"] = gs.snap_pct.transform(lambda x: x.shift(1).expanding().mean())
    w["lag1_snap"] = g.snap_pct.shift(1); w["lag1_route"] = g.route_part.shift(1); w["lag1_share"] = g.tgt_share.shift(1)
    w["lag1_seasonweek"] = g.season.shift(1) * 100 + g.week.shift(1)
    ps = w.groupby(["player_id", "season"]).agg(prev_gp=("dk", "size"), prev_dk=("dk", "mean"), prev_share=("tgt_share", "mean"),
                                                prev_route=("route_part", "mean"), prev_snap=("snap_pct", "mean"),
                                                prev_tgt=("targets", "mean")).reset_index()
    ps["season"] += 1
    # team pass volume prior (team-level EWMA of dropbacks, crossing seasons)
    tm = w.drop_duplicates(["season", "week", "team"])[["season", "week", "team", "team_db", "team_tgt"]].sort_values(["team", "season", "week"])
    tm["team_db_ewm"] = tm.groupby("team").team_db.transform(lambda x: x.shift(1).ewm(halflife=6, min_periods=1).mean())
    tm["team_tgt_ewm"] = tm.groupby("team").team_tgt.transform(lambda x: x.shift(1).ewm(halflife=6, min_periods=1).mean())
    return w, ps, tm


def main():
    w = weekly()
    w = w.merge(snaps(), on=["player_id", "season", "week"], how="left").merge(routes(), on=["player_id", "season", "week"], how="left")
    w.to_parquet(U / "usage_weekly.parquet")
    print("weekly rows", len(w), "snap cov", w.snap_pct.notna().mean().round(3), "route cov by season",
          w.groupby("season").route_part.apply(lambda x: x.notna().mean()).round(2).to_dict())
    f, ps, tm = features(w)
    lagcols = [c for c in f.columns if "_ewm" in c or c.startswith(("cur_", "lag1_"))]
    # "played" rows carry lags for their week; for weeks a player did not play we still need pre-week state ->
    # forward-fill the last known state into a full (player, season, week) grid.
    grid = f[["player_id"]].drop_duplicates().merge(pd.DataFrame([(s, k) for s in SEASONS for k in range(1, 19)], columns=["season", "week"]), how="cross")
    # state AFTER each game = lags of the next row; easiest: compute post-game state by re-running lag on shifted index.
    post = f.copy()
    post["week"] += 1  # state after week k available for week k+1 (approx; bye weeks handled by ffill)
    # recompute post-game EWMAs including current game
    g = post.groupby("player_id")
    for col in ["tgt_share", "snap_pct", "route_part", "tprr", "dk", "targets"]:
        for hl in (2, 4, 8):
            post[f"{col}_ewm{hl}"] = g[col].transform(lambda x: x.ewm(halflife=hl, min_periods=1).mean())
    gs = post.groupby(["player_id", "season"])
    post["cur_gp"] = gs.cumcount() + 1
    for c, s in [("cur_dk_mean", "dk"), ("cur_tgt_share", "tgt_share"), ("cur_route_part", "route_part"), ("cur_snap_pct", "snap_pct")]:
        post[c] = gs[s].transform(lambda x: x.expanding().mean())
    post["lag1_snap"], post["lag1_route"], post["lag1_share"] = post.snap_pct, post.route_part, post.tgt_share
    post["lag1_seasonweek"] = post.season * 100 + post.week - 1
    keep = ["player_id", "season", "week"] + lagcols
    grid = grid.merge(post[keep], on=["player_id", "season", "week"], how="left").sort_values(["player_id", "season", "week"])
    # carry state forward across byes/absences; cross-season carry only for EWMAs (cur_* reset each season)
    ew = [c for c in lagcols if "_ewm" in c] + ["lag1_snap", "lag1_route", "lag1_share", "lag1_seasonweek"]
    grid[ew] = grid.groupby("player_id")[ew].ffill()
    cur = [c for c in lagcols if c.startswith("cur_")]
    grid[cur] = grid.groupby(["player_id", "season"])[cur].ffill()
    grid["cur_gp"] = grid.cur_gp.fillna(0)
    grid = grid.merge(ps, on=["player_id", "season"], how="left")
    tmf = tm[["season", "week", "team", "team_db_ewm", "team_tgt_ewm"]]
    grid.to_parquet(U / "usage_features.parquet"); tmf.to_parquet(U / "team_volume_features.parquet")
    print("features rows", len(grid))


if __name__ == "__main__":
    main()
