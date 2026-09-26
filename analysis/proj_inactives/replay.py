"""Replay the game-day inactives source (scripts/inactives_pull.py) on past games.

Ground truth A: DNP = fantasy-position player absent from data/weekly_stats_{season}.parquet that week.
Ground truth B: nflverse weekly_rosters status INA (vs ACT) that week.
Universe: QB/RB/WR/TE on nflverse weekly_rosters ACT/INA for a team that played, and "relevant" =
had a stat row in some OTHER week of that season or the previous season (i.e. real fantasy names).
Also scores the ESPN-designation pipeline (OUT/DOUBTFUL => predicted DNP) where a pre-lock file exists.
Small JSON GETs only (2 per game + a few position lookups). Output: analysis/proj_inactives/replay_report.txt
"""
import os, sys
import pandas as pd

R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(R, "scripts"))
import inactives_pull as ip  # noqa: E402

REP = open(os.path.join(os.path.dirname(__file__), "replay_report.txt"), "w")
def P(*a):
    s = " ".join(str(x) for x in a); print(s); REP.write(s + "\n"); REP.flush()

FP = {"QB", "RB", "WR", "TE"}
DESIG = {(2026, 2): "output/player_status_2_20260920_160103.csv",   # 16:01Z Sun, last pre-lock
         (2026, 1): "output/player_status_23_20260910_185633.csv"}  # Thu 09-10 (stale; no Sun wk1 file exists)
CASES = [(2026, 1), (2026, 2), (2025, 1), (2025, 2)]

def stats_keys(season):
    w = pd.read_parquet(os.path.join(R, f"data/weekly_stats_{season}.parquet"), columns=["player_id", "week", "season_type"])
    return w[w.season_type == "REG"]

tot = {}
for season, week in CASES:
    games = ip.week_games(season, week)
    flag, audit = ip.collect(season, week, resolve_names=False, include_started=True)
    bad = [a for a in audit if a[2] != "ok"]
    flag = ip.map_to_player_id(flag, season) if len(flag) else flag
    ro = pd.read_parquet(os.path.join(R, f"data/weekly_rosters_{season}.parquet"),
                         columns=["gsis_id", "team", "position", "status", "week", "full_name"])
    ro = ro[(ro.week == week) & ro.status.isin(["ACT", "INA"]) & ro.position.isin(FP)].drop_duplicates("gsis_id")
    st = stats_keys(season)
    played_now = set(st[st.week == week].player_id)
    prev = stats_keys(season - 1)
    rel = set(st[st.week != week].player_id) | set(prev.player_id)
    teams_played = set(pd.read_parquet(os.path.join(R, f"data/weekly_stats_{season}.parquet"),
                                       columns=["team", "week"]).query("week == @week").team)
    U = ro[ro.team.isin(teams_played)].copy()
    U["dnp"] = ~U.gsis_id.isin(played_now)
    U["ina"] = U.status == "INA"
    fl = set(flag.player_id.dropna()) if len(flag) else set()
    U["espn_inactive"] = U.gsis_id.isin(fl)
    Ur = U[U.gsis_id.isin(rel)]
    P(f"\n== {season} wk{week}: {len(games)} games, {len(audit)} team-games, not ok: {bad[:4]}")
    P(f"  ESPN fantasy-pos inactives flagged: {len(flag)} (mapped {len(fl)}; unmapped {len(flag)-flag.player_id.notna().sum() if len(flag) else 0})")
    P(f"  flagged but not on nflverse ACT/INA universe: {len(fl - set(U.gsis_id))}")
    for name, X in (("all", U), ("relevant", Ur)):
        tp = (X.espn_inactive & X.dnp).sum(); fp = (X.espn_inactive & ~X.dnp).sum(); fn = (~X.espn_inactive & X.dnp).sum()
        tpi = (X.espn_inactive & X.ina).sum(); fpi = (X.espn_inactive & ~X.ina).sum(); fni = (~X.espn_inactive & X.ina).sum()
        P(f"  [{name}] n={len(X)} DNP={X.dnp.sum()} INA={X.ina.sum()} | vs DNP: TP={tp} FP={fp} FN={fn} "
          f"prec={tp/max(tp+fp,1):.3f} rec={tp/max(tp+fn,1):.3f} | vs INA: TP={tpi} FP={fpi} FN={fni}")
        tot.setdefault(name, [0, 0, 0]); tot[name][0] += tp; tot[name][1] += fp; tot[name][2] += fn
    fpx = Ur[Ur.espn_inactive & ~Ur.dnp]
    if len(fpx): P("  relevant flagged-but-played:", fpx[["full_name", "team", "position", "status"]].values.tolist())
    fnx = Ur[~Ur.espn_inactive & Ur.dnp & Ur.ina]
    if len(fnx): P("  relevant INA-but-not-flagged:", fnx[["full_name", "team", "position"]].values.tolist()[:10])
    if (season, week) in DESIG:
        d = pd.read_csv(os.path.join(R, DESIG[(season, week)]), dtype={"player_id": str})
        dz = set(d[d.status.isin(["OUT", "DOUBTFUL"])].player_id)
        X = Ur.assign(des=Ur.gsis_id.isin(dz))
        for lab, col in (("designation OUT/DOUBT", X.des), ("desig OR gameday", X.des | X.espn_inactive)):
            tp = (col & X.dnp).sum(); fp = (col & ~X.dnp).sum(); fn = (~col & X.dnp).sum()
            P(f"  [relevant] {lab} ({DESIG[(season, week)].split('/')[-1]}): TP={tp} FP={fp} FN={fn} "
              f"prec={tp/max(tp+fp,1):.3f} rec={tp/max(tp+fn,1):.3f}")
        extra = X[X.espn_inactive & ~X.des & X.dnp]
        P(f"  gameday adds over designation (true DNP, not OUT/DOUBT pre-lock): {len(extra)} ->",
          extra[["full_name", "team", "position"]].values.tolist()[:15])
for k, (tp, fp, fn) in tot.items():
    P(f"\nTOTAL [{k}] TP={tp} FP={fp} FN={fn} prec={tp/max(tp+fp,1):.3f} rec={tp/max(tp+fn,1):.3f}")
