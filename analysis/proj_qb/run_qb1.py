"""Regenerate history projections with a leak-free QB-only depth chart so the
production QB guard (statline_model, 2026-09-24) works as in production.

QB1 source: highest DK salary QB on the team in the slate's own (pre-lock) salary
file. DK prices are published before the slate -> no result leakage. Other QBs on
the team get depth_rank 2,3,... by salary. Non-QB positions: no chart (same as
the ourproj harness). Output (FC-derived salaries -> git-ignored):
data/fc_history/derived/proj_qb/ourproj_qb1/proj_{season}_wk{week}.csv
    python analysis/proj_qb/run_qb1.py --workers 6
"""
from __future__ import annotations
import argparse, contextlib, io, multiprocessing as mp, sys, time, traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DER = REPO / "data/fc_history/derived"
SAL = DER / "salaries_ourproj"
OUTP = DER / "proj_qb/ourproj_qb1"
WORK = DER / "proj_qb/work_qb1"


def qb_chart(pd, sal):
    q = sal[sal.Position == "QB"].copy()
    q["depth_rank"] = q.groupby("normalized_team")["Salary"].rank(ascending=False, method="first")
    return pd.DataFrame({"player_id": q.player_id.astype(str), "team": q.normalized_team,
                         "position": "QB", "depth_rank": q.depth_rank.astype(int)})


def run_season(job):
    season, weeks, force = job
    sys.path.insert(0, str(REPO / "analysis/backtest_multi"))
    import run_backtest as rb
    pd, bp, bps, bh, pm = rb._install_patches()
    import statline_model as sm
    games = pd.read_csv(REPO / "data" / "nflverse_games.csv")

    def load_sal(site, slate_id):
        return pd.read_csv(SAL / f"salaries_{site}_{slate_id}.csv", dtype={"player_id": str, "ID": str})
    bp.load_salaries = load_sal
    bps.load_salaries = load_sal
    if not (REPO / f"data/schedules_{season}.parquet").exists():
        def load_sched(s):
            g = games[games.season == s].copy(); g["season_type"] = g["game_type"]; return g
        bp.load_schedule = load_sched; bps.load_schedule = load_sched
    dst_mode = "distributional" if (REPO / f"data/team_stats_{season}.parquet").exists() else "legacy"
    res = []
    for week in weeks:
        dest = OUTP / f"proj_{season}_wk{week}.csv"
        if dest.exists() and not force:
            continue
        dc = qb_chart(pd, load_sal("dk", f"fcmain_{season}_wk{week}"))
        sm.load_depth_chart = lambda dc=dc: dc.copy()
        work = WORK / f"{season}_wk{week}"; work.mkdir(parents=True, exist_ok=True)
        for m in (bp, bps, bh):
            m.OUTPUT_DIR = work
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
            OUTP.mkdir(parents=True, exist_ok=True); df.to_csv(dest, index=False); st = "ok"
        except (Exception, SystemExit) as e:  # noqa: BLE001
            st = f"FAIL {type(e).__name__}: {str(e)[:200]}"
            with open(DER / "proj_qb/errors.txt", "a", encoding="utf-8") as f:
                f.write(f"{season} wk{week}: {st}\n{traceback.format_exc()}\n{buf.getvalue()[-2000:]}\n")
        print(f"{season} wk{week}: {st} ({time.time()-t0:.0f}s)", flush=True)
        res.append((season, week, st))
    return res


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seasons", default="2021-2026"); ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    sys.path.insert(0, str(REPO / "analysis/backtest_multi"))
    from run_backtest import parse_range
    have = {}
    for p in SAL.glob("salaries_dk_fcmain_*_wk*.csv"):
        s, w = p.stem.split("_")[3], p.stem.split("_wk")[1]
        have.setdefault(int(s), []).append(int(w))
    jobs = [(s, sorted(have.get(s, [])), a.force) for s in parse_range(a.seasons) if s in have]
    (DER / "proj_qb").mkdir(parents=True, exist_ok=True)
    with mp.get_context("spawn").Pool(min(a.workers, len(jobs))) as pool:
        res = pool.map(run_season, jobs, chunksize=1)
    flat = [r for rr in res for r in rr]
    print(f"done {len(flat)}, failed {sum(r[2].startswith('FAIL') for r in flat)}")


if __name__ == "__main__":
    main()
