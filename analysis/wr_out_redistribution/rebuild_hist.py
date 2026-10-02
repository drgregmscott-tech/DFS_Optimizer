"""Leak-free current-code rebuild of 2021-25 DK main slates with the WR-out redistribution (apply_wr_replacement)
wired in. Same harness as analysis/who_replaces_whom/rebuild_hist.py (run_ourproj: FC salaries as inputs only,
closing-line vegas, depth chart stubbed, ignore_played_week), injury status PINNED to the Friday-known designation
(analysis/inactives/status_panel_2016_2025.csv: Out/Doubtful/IR/RES -> OUT), so WRW RB/TE and WRW WR all fire.
Code = this checkout; git-ignored data inputs (FC salaries, status panel) from the main checkout.
usage: python rebuild_hist.py <on|off> 2021:6,2021:13,...   outputs (FC-derived, never commit): hist_builds/<arm>/"""
import contextlib, io, os, sys, time
from pathlib import Path
D = Path(__file__).resolve().parent; CODE = D.parents[1]
DATA_REPO = Path(r"C:\Users\gmsco\Desktop\DFS_Optimizer")
arm, spec = sys.argv[1], sys.argv[2]
os.environ["DFS_WRW_WR"] = "1" if arm.startswith("on") else "0"
sys.path.insert(0, str(CODE / "analysis/backtest_multi"))
import run_backtest as rb
import pandas as pd
pd_, bp, bps, bh, pm = rb._install_patches()
import statline_model as sm
assert Path(sm.__file__).resolve().parents[1] == CODE.resolve(), sm.__file__
SAL = DATA_REPO / "data/fc_history/derived/salaries_ourproj"
P = pd.read_csv(DATA_REPO / "analysis/inactives/status_panel_2016_2025.csv")
P = P[P.desig.isin(["Out", "Doubtful", "IR/Reserve(no desig)"]) | (P.status == "RES")]
games = pd.read_csv(CODE / "data/nflverse_games.csv")
out = D / "hist_builds" / arm; out.mkdir(parents=True, exist_ok=True)
for sw in spec.split(","):
    season, week = map(int, sw.split(":"))
    if (out / f"proj_{season}_wk{week}.csv").exists():
        continue
    st = P[(P.season == season) & (P.week == week)]
    stat = pd.DataFrame({"player_id": st.gsis_id.astype(str), "team": st.team, "position": st.position, "status": "OUT"})
    sm.load_injury_status = lambda wk, _s=stat: _s
    def load_sal(site, slate_id):
        return pd.read_csv(SAL / f"salaries_{site}_{slate_id}.csv", dtype={"player_id": str, "ID": str})
    bp.load_salaries = load_sal; bps.load_salaries = load_sal
    if not (CODE / f"data/schedules_{season}.parquet").exists():
        def load_sched(s):
            g = games[games.season == s].copy(); g["season_type"] = g["game_type"]; return g
        bp.load_schedule = load_sched; bps.load_schedule = load_sched
    dst_mode = "distributional" if (CODE / f"data/team_stats_{season}.parquet").exists() else "legacy"
    work = out / f"work_{season}_wk{week}"; work.mkdir(exist_ok=True)
    for m in (bp, bps, bh): m.OUTPUT_DIR = work
    t0 = time.time(); buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            bh.build_vegas_file(games, "dk", season, week)
            mf = pm.build_matchup_factors("dk", season, week)
            mf.to_csv(work / f"matchup_factors_dk_{season}_{week}.csv", index=False)
            df = bps.build_statline_projections(
                "dk", season, week, f"fcmain_{season}_wk{week}", vegas_slate_id=str(week),
                dst_model_mode=dst_mode, use_volume_prior=True, sigma_recal=True,
                ignore_played_week=True, neutral_skill_matchup=True, props_weight=0.0,
                use_stack=True, role_change=True, canonical_teams=True)
        df.insert(0, "season", season); df.insert(1, "week", week)
        df.to_csv(out / f"proj_{season}_wk{week}.csv", index=False)
        wl = [l for l in buf.getvalue().splitlines() if "WRW WR" in l]
        print(f"{season} wk{week}: ok ({time.time()-t0:.0f}s) {wl[0][:220] if wl else 'no WRW WR line'}", flush=True)
    except (Exception, SystemExit) as e:
        print(f"{season} wk{week}: FAIL {type(e).__name__}: {e}\n{buf.getvalue()[-1500:]}", flush=True)
