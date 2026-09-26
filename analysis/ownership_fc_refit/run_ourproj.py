"""Regenerate OUR (statline engine) pre-game DK projections for FC-history main slates.

Reuses analysis/backtest_multi/run_backtest.py's leak patches (depth chart and
injury status stubbed, private OUTPUT_DIR, closing-line vegas file from
nflverse_games.csv, matchup factors regenerated from weeks < target,
ignore_played_week, props off). Differences vs that harness:
  * salary pool = FC single-entry MAIN slate for (season, week) (player_id =
    gsis from fc_master_mapped). Written to data/fc_history/derived/
    salaries_ourproj/ (FC-derived -> git-ignored path) and loaded via a
    monkeypatched load_salaries.
  * 2022/2023 have no schedules_{season}.parquet locally -> load_schedule is
    patched to read data/nflverse_games.csv; no team_stats_{2022,2023} ->
    DST uses dst_model_mode='legacy' for those seasons (distributional elsewhere).
Outputs (FC-derived, git-ignored): data/fc_history/derived/ourproj/proj_{season}_wk{week}.csv

    python analysis/ownership_fc_refit/run_ourproj.py --seasons 2021-2026 --workers 6
"""
from __future__ import annotations

import argparse
import contextlib
import io
import multiprocessing as mp
import sys
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DER = REPO / "data/fc_history/derived"
SAL = DER / "salaries_ourproj"
OUTP = DER / "ourproj"
WORK = DER / "ourproj_work"
TEAM_FIX = {"JAC": "JAX", "LAR": "LA", "WSH": "WAS", "LVR": "LV"}


def write_salaries():
    import pandas as pd
    SAL.mkdir(parents=True, exist_ok=True)
    d = pd.read_csv(DER / "fc_master_mapped.csv", low_memory=False, dtype={"player_id": str})
    d = d[(d.contest == "single_entry") & (d.slate_kind == "classic")
          & d.pos.isin(["QB", "RB", "WR", "TE", "DST"]) & d.player_id.notna()]
    out = {}
    for (s, w), g in d.groupby(["season", "week"]):
        g = g.drop_duplicates("player_id")
        team = g.team.map(lambda t: TEAM_FIX.get(t, t))
        f = pd.DataFrame({
            "Name": g.player, "Position": g.pos, "TeamAbbrev": team, "Salary": g.salary,
            "ID": [str(900000 + i) for i in range(len(g))], "name": g.player, "site": "dk",
            "salary": g.salary, "normalized_name": g.name_key, "normalized_team": team,
            "position_upper": g.pos, "player_id": g.player_id})
        p = SAL / f"salaries_dk_fcmain_{s}_wk{w}.csv"
        f.to_csv(p, index=False)
        out[(int(s), int(w))] = p
    return out


def run_season(job):
    season, weeks, force = job
    sys.path.insert(0, str(REPO / "analysis/backtest_multi"))
    import run_backtest as rb
    pd, bp, bps, bh, pm = rb._install_patches()
    games = pd.read_csv(REPO / "data" / "nflverse_games.csv")
    site_id = "ID"

    def load_sal(site, slate_id):
        return pd.read_csv(SAL / f"salaries_{site}_{slate_id}.csv", dtype={"player_id": str, site_id: str})
    bp.load_salaries = load_sal
    bps.load_salaries = load_sal
    if not (REPO / f"data/schedules_{season}.parquet").exists():
        def load_sched(s):
            g = games[games.season == s].copy()
            g["season_type"] = g["game_type"]
            return g
        bp.load_schedule = load_sched
        bps.load_schedule = load_sched
    dst_mode = "distributional" if (REPO / f"data/team_stats_{season}.parquet").exists() else "legacy"
    res = []
    for week in weeks:
        dest = OUTP / f"proj_{season}_wk{week}.csv"
        if dest.exists() and not force:
            continue
        work = WORK / f"{season}_wk{week}"
        work.mkdir(parents=True, exist_ok=True)
        for m in (bp, bps, bh):
            m.OUTPUT_DIR = work
        t0 = time.time()
        buf = io.StringIO()
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
            df.insert(0, "season", season)
            df.insert(1, "week", week)
            OUTP.mkdir(parents=True, exist_ok=True)
            df.to_csv(dest, index=False)
            st = "ok"
        except (Exception, SystemExit) as e:  # noqa: BLE001
            st = f"FAIL {type(e).__name__}: {str(e)[:200]}"
            with open(DER / "ourproj_errors.txt", "a", encoding="utf-8") as f:
                f.write(f"{season} wk{week}: {st}\n{traceback.format_exc()}\n{buf.getvalue()[-2000:]}\n")
        print(f"{season} wk{week} [{dst_mode}]: {st} ({time.time()-t0:.0f}s)", flush=True)
        res.append((season, week, st))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", default="2021-2026")
    ap.add_argument("--weeks", default="1-18")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    sys.path.insert(0, str(REPO / "analysis/backtest_multi"))
    from run_backtest import parse_range
    sal = write_salaries()
    seasons, wks = parse_range(a.seasons), parse_range(a.weeks)
    jobs = [(s, [w for w in wks if (s, w) in sal], a.force) for s in seasons]
    t0 = time.time()
    if a.workers <= 1:
        res = [run_season(j) for j in jobs]
    else:
        with mp.get_context("spawn").Pool(min(a.workers, len(jobs))) as pool:
            res = pool.map(run_season, jobs, chunksize=1)
    flat = [r for rr in res for r in rr]
    print(f"done: {len(flat)} weeks, {sum(r[2].startswith('FAIL') for r in flat)} failed, {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
