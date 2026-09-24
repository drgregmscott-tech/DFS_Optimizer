"""Multi-season leak-free projection backtest harness (DK 2014-2021).

Runs scripts/build_projections_statline.build_statline_projections() IN-PROCESS
for every (season, week) with a RotoGuru DK salary file, weeks 2-17 (2-18 in
2021). Writes ONLY under analysis/backtest_multi/out/. Leak fixes are in-process monkeypatches; the team-code fix uses an opt-in
scripts/ keyword (default off):

  * OUTPUT_DIR of build_projections, build_projections_statline and
    backtest_harness -> a private per-(arm, season, week) work dir, so the
    vegas file (keyed by week inside backtest_harness) can never collide
    across seasons and nothing reaches output/.
  * statline_model.load_depth_chart -> empty frame (the only local depth data
    is a 2026 snapshot; feasibility report LEAK 1).
  * statline_model.load_injury_status -> empty frame (output/player_status_
    {week}_* files are 2026 runs keyed by week only).
  * build_statline_projections(canonical_teams=True) (opt-in scripts/ flag,
    default False) -> team codes canonicalised
    (OAK->LV, SD->LAC, STL->LA) so the schedule opponent map matches the
    vegas file / team_stats codes. This is the DST "no team stats for their
    opponent" blocker, and it also silently dropped the opponent for every
    Raiders/Chargers/Rams skill player pre-2020.
    and RotoGuru 'SDG' -> 'LAC' (2014-2016 salary files). The first
    baseline/matchup_restored runs used an equivalent in-harness monkeypatch
    (LEGACY_CANON_PATCH); equivalence checked on 2014 wk10 / 2019 wk10.
  * matchup_factors_dk_{season}_{week}.csv is REGENERATED in-process with
    projections_matchup.build_matchup_factors() (REG weeks < target only)
    into the work dir rather than copied from output/.

Build call = shipped DK classic config minus props:
  use_volume_prior=True, sigma_recal=True, dst_model_mode='distributional',
  use_stack=True, neutral_skill_matchup=True, ignore_played_week=True,
  props_weight=0.0.  Arms flip one flag each (see --help).

Resumable: a finished week is skipped if its projection CSV exists
(--force rebuilds). Failures are logged to out/logs/<arm>/errors.txt and the
loop continues.

Usage:
  python analysis/backtest_multi/run_backtest.py --arm baseline --seasons 2014-2021 --workers 4
  python analysis/backtest_multi/run_backtest.py --arm matchup_restored --restore-matchup --seasons 2018-2021
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
HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
SITE = "dk"
LEGACY_CANON_PATCH = False  # True = monkeypatch instead of canonical_teams=True

TEAM_CANON = {"OAK": "LV", "SD": "LAC", "SDG": "LAC", "STL": "LA", "LAR": "LA",
              "LVR": "LV", "WSH": "WAS", "JAC": "JAX", "GNB": "GB", "NOR": "NO",
              "NOS": "NO"}


def parse_range(s: str) -> list[int]:
    out = []
    for part in s.split(","):
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def weeks_for(season: int, weeks: list[int]) -> list[int]:
    return [w for w in weeks
            if (REPO / "data" / f"salaries_{SITE}_rotoguru_{season}_wk{w}.csv").exists()]


def proj_path(arm: str, season: int, week: int) -> Path:
    return OUT / "proj" / arm / f"proj_{arm}_{SITE}_{season}_wk{week}.csv"


def _install_patches():
    """Import scripts/ modules and apply the in-process leak/alias patches."""
    sys.path.insert(0, str(REPO / "scripts"))
    sys.path.insert(0, str(HERE))
    import pandas as pd
    import build_projections as bp
    import build_projections_statline as bps
    import backtest_harness as bh
    import statline_model as sm
    import projections_matchup as pm

    sm.load_depth_chart = lambda: pd.DataFrame(
        columns=["player_id", "team", "position", "depth_rank"])
    sm.load_injury_status = lambda week: pd.DataFrame(
        columns=["player_id", "team", "position", "status"])

    real_sched, real_sal = bps.load_schedule, bps.load_salaries

    def canon_schedule(season):
        df = real_sched(season).copy()
        for c in ("home_team", "away_team"):
            df[c] = df[c].map(lambda t: TEAM_CANON.get(t, t))
        return df

    def canon_salaries(site, slate_id):
        df = real_sal(site, slate_id).copy()
        df["normalized_team"] = df["normalized_team"].map(lambda t: TEAM_CANON.get(t, t))
        return df

    if LEGACY_CANON_PATCH:   # pre-flag path (identical output; kept for audit)
        bps.load_schedule = canon_schedule
        bps.load_salaries = canon_salaries
    return pd, bp, bps, bh, pm


def run_season(job):
    arm, season, weeks, opts, force = job
    pd, bp, bps, bh, pm = _install_patches()
    games = pd.read_csv(REPO / "data" / "nflverse_games.csv")
    logdir = OUT / "logs" / arm
    logdir.mkdir(parents=True, exist_ok=True)
    done = []
    import statline_model as sm
    import volume_prior as vpm
    _lp = getattr(vpm, "_orig_load_prior", vpm.load_prior)
    _lv = getattr(sm, "_orig_load_variance", sm.load_variance)
    vpm._orig_load_prior, sm._orig_load_variance = _lp, _lv
    vpm.load_prior, sm.load_variance = _lp, _lv
    if opts.get("prior_path"):
        _pp = Path(opts["prior_path"].format(season=season))
        vpm.load_prior = lambda site, path=None: _lp(site, _pp)
    if opts.get("variance_path"):
        _vp = Path(opts["variance_path"].format(season=season))
        sm.load_variance = lambda path=None: _lv(_vp)
    for week in weeks:
        dest = proj_path(arm, season, week)
        if opts.get("depth_charts"):
            import hist_depth
            _dc = hist_depth.load_depth_chart_asof(season, week)
            if opts.get("dc_positions"):
                _dc = _dc[_dc["position"].isin(opts["dc_positions"].split(","))].reset_index(drop=True)
            sm.load_depth_chart = lambda _dc=_dc: _dc.copy()
        if dest.exists() and not force:
            done.append((season, week, "cached", 0.0))
            continue
        work = OUT / "work" / arm / f"{season}_wk{week}"
        work.mkdir(parents=True, exist_ok=True)
        for m in (bp, bps, bh):
            m.OUTPUT_DIR = work
        t0 = time.time()
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                bh.build_vegas_file(games, SITE, season, week)       # work/vegas_implied_totals_{week}.csv
                mf = pm.build_matchup_factors(SITE, season, week)    # REG weeks < week only
                mf.to_csv(work / f"matchup_factors_{SITE}_{season}_{week}.csv", index=False)
                df = bps.build_statline_projections(
                    SITE, season, week, f"rotoguru_{season}_wk{week}",
                    vegas_slate_id=str(week),
                    dst_model_mode=opts["dst_model"],
                    use_volume_prior=opts["volume_prior"],
                    sigma_recal=opts["sigma_recal"],
                    ignore_played_week=True,
                    neutral_skill_matchup=not opts["restore_matchup"],
                    props_weight=0.0,
                    use_stack=opts["stack"],
                    role_change=opts["role_change"],
                    canonical_teams=not LEGACY_CANON_PATCH,
                    **({"floor_share_fix": True} if opts.get("floor_share_fix") else {}),
                    **({"qb_rush_scale": opts["qb_rush_scale"]} if opts.get("qb_rush_scale", 1.0) != 1.0 else {}))
            df.insert(0, "season", season)
            df.insert(1, "week", week)
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(".tmp")
            df.to_csv(tmp, index=False)
            tmp.replace(dest)
            status = "ok"
        except (Exception, SystemExit) as e:  # noqa: BLE001 -- keep looping
            status = f"FAIL {type(e).__name__}: {str(e)[:300]}"
            with open(logdir / "errors.txt", "a", encoding="utf-8") as f:
                f.write(f"{season} wk{week}: {status}\n{traceback.format_exc()}\n")
        (logdir / f"{season}_wk{week}.log").write_text(buf.getvalue(), encoding="utf-8")
        dt = time.time() - t0
        print(f"[{arm}] {season} wk{week}: {status} ({dt:.0f}s)", flush=True)
        done.append((season, week, status, dt))
    return done


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arm", required=True, help="Arm name (used in output paths).")
    ap.add_argument("--seasons", default="2014-2021")
    ap.add_argument("--weeks", default="2-18")
    ap.add_argument("--workers", type=int, default=4, help="Parallel seasons.")
    ap.add_argument("--force", action="store_true", help="Rebuild cached weeks.")
    ap.add_argument("--restore-matchup", action="store_true",
                    help="B1: restore QB/RB/WR/TE matchup factor (shipped default neutralises it).")
    ap.add_argument("--no-stack", action="store_true", help="C: projection stack off.")
    ap.add_argument("--no-sigma-recal", action="store_true", help="D: sigma recalibration off.")
    ap.add_argument("--no-volume-prior", action="store_true", help="Volume prior off.")
    ap.add_argument("--no-role-change", action="store_true")
    ap.add_argument("--dst-model", default="distributional", choices=["distributional", "legacy"])
    ap.add_argument("--depth-charts", action="store_true",
                    help="Use leak-free nflverse historical depth charts (hist_depth.py, week < target).")
    ap.add_argument("--dc-positions", default=None,
                    help="Restrict --depth-charts to these positions, e.g. RB,WR,TE (historical QB charts are stale).")
    ap.add_argument("--floor-share-fix", action="store_true", help="H: floor-share exclusion (opt-in engine flag).")
    ap.add_argument("--qb-rush-scale", type=float, default=1.0, help="QB rush_mu multiplier (opt-in engine flag).")
    ap.add_argument("--prior-path", default=None,
                    help="Volume-prior artifact path; '{season}' is replaced by the built season (LOSO).")
    ap.add_argument("--variance-path", default=None,
                    help="statline_variance artifact path; '{season}' replaced by the built season (LOSO).")
    a = ap.parse_args()

    opts = {"restore_matchup": a.restore_matchup, "stack": not a.no_stack,
            "sigma_recal": not a.no_sigma_recal, "volume_prior": not a.no_volume_prior,
            "role_change": not a.no_role_change, "dst_model": a.dst_model,
            "depth_charts": a.depth_charts, "dc_positions": a.dc_positions, "floor_share_fix": a.floor_share_fix,
            "qb_rush_scale": a.qb_rush_scale, "prior_path": a.prior_path,
            "variance_path": a.variance_path}
    wk = parse_range(a.weeks)
    jobs = [(a.arm, s, weeks_for(s, wk), opts, a.force) for s in parse_range(a.seasons)]
    (OUT / "logs" / a.arm).mkdir(parents=True, exist_ok=True)
    (OUT / "logs" / a.arm / "config.txt").write_text(f"{opts}\nseasons={a.seasons} weeks={a.weeks}\n")
    print(f"arm={a.arm} opts={opts} jobs={[(j[1], len(j[2])) for j in jobs]}", flush=True)
    t0 = time.time()
    if a.workers <= 1:
        res = [run_season(j) for j in jobs]
    else:
        with mp.get_context("spawn").Pool(min(a.workers, len(jobs))) as pool:
            res = pool.map(run_season, jobs, chunksize=1)
    flat = [r for rr in res for r in rr]
    n_fail = sum(r[2].startswith("FAIL") for r in flat)
    print(f"done arm={a.arm}: {len(flat)} weeks, {n_fail} failed, {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
