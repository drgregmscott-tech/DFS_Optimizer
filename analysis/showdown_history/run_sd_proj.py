"""Step 2b: replay OUR statline engine (showdown path: FLEX build + _build_kicker_projections + apply_captain_multiplier)
on the 49 FC-history DK Showdown games. Reuses analysis/backtest_multi/run_backtest.py leak patches and the
run_ourproj.py flag set (props off, ignore_played_week, sigma_recal, volume prior, stack [inactive for showdown]).
Differences vs live production, all deliberate and documented in HANDOFF_showdown_ownership_refit_2026-09-26.md:
  * depth chart: --depth qb (default) = QB-only chart, QB1 = the game's starting QB from nflverse_games
    (home_qb_id/away_qb_id; known pre-lock in practice). --depth stub = empty chart (run_ourproj behaviour).
  * injury feed: game-day inactives -> status OUT (2024/25: weekly_rosters status != ACT for that week;
    2023: no local rosters -> absent from weekly_stats that week AND 0 actual points). Post-build OUT rows are
    zeroed (live does this via status_check apply). --no-inactives disables.
  * ownership: refine_showdown_ownership is stubbed (features are computed separately in sd_features.py).
Outputs (FC-derived, gitignored): data/fc_history/derived/showdown/ourproj_<tag>/proj_<slate>.csv
    python analysis/showdown_history/run_sd_proj.py --workers 6 [--depth stub] [--no-inactives] [--force]
"""
from __future__ import annotations
import argparse, contextlib, io, re, sys, time, traceback
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
R = Path(__file__).resolve().parents[2]
SD = R / "data/fc_history/derived/showdown"; SAL = SD / "salaries_sd"
FIX = {"LAR": "LA", "JAC": "JAX", "WSH": "WAS", "LVR": "LV"}


def nk(s): return re.sub(r"[^a-z]", "", re.sub(r"\b(jr|sr|ii|iii|iv|v)\b\.?", "", str(s).lower()))


def inactives(pd, slate, season, week, pool):
    """player_ids OUT for the game (see module doc). pool = FLEX rows of the salary file."""
    import numpy as np
    sk = pool[~pool.position_upper.isin(["DST", "K"])]
    if season in (2024, 2025):
        ro = pd.read_parquet(R / f"data/weekly_rosters_{season}.parquet")
        ro = ro[(ro.week == week) & ro.gsis_id.notna()]
        st = ro.drop_duplicates("gsis_id").set_index("gsis_id").status
        s = sk.player_id.map(st)
        return set(sk.player_id[s.notna() & (s != "ACT")]) | set(sk.player_id[s.isna() & ~sk.player_id.str.startswith("UNM")])
    ws = pd.read_parquet(R / f"data/weekly_stats_{season}.parquet")
    played = set(ws[ws.week == week].player_id)
    P = pd.read_parquet(SD / "players.parquet"); P = P[P.slate == slate]
    act = dict(zip(P.Player.map(nk) + "|" + P.Team.map(lambda t: FIX.get(t, t)), P.act))
    a = (sk.normalized_name + "|" + sk.normalized_team).map(act).fillna(0)
    return set(sk.player_id[~sk.player_id.isin(played) & (a <= 0)])


def run_slate(job):
    slate, season, week, tag, depth, use_inact, force = job
    outd = SD / f"ourproj_{tag}"; dest = outd / f"proj_{slate}.csv"
    if dest.exists() and not force:
        return slate, "cached", 0
    sys.path.insert(0, str(R / "analysis/backtest_multi"))
    import run_backtest as rb
    pd, bp, bps, bh, pm = rb._install_patches()
    import statline_model as sm
    import ownership_model_showdown as oms
    oms.refine_showdown_ownership = lambda df, site: df
    games = pd.read_csv(R / "data/nflverse_games.csv")
    sal = pd.read_csv(SAL / f"salaries_dk_sd_{slate}.csv", dtype={"player_id": str, "ID": str})
    def load_sal(site, slate_id): return sal.copy()
    bp.load_salaries = load_sal; bps.load_salaries = load_sal
    if not (R / f"data/schedules_{season}.parquet").exists():
        def load_sched(s):
            g = games[games.season == s].copy(); g["season_type"] = g["game_type"]; return g
        bp.load_schedule = load_sched; bps.load_schedule = load_sched
    g = games[(games.season == season) & (games.week == week) & (games.game_type == "REG")]
    teams = set(sal.normalized_team)
    g = g[g.home_team.isin(teams) & g.away_team.isin(teams)].iloc[0]
    if depth == "qb":
        dc = pd.DataFrame({"player_id": [g.home_qb_id, g.away_qb_id], "team": [g.home_team, g.away_team],
                           "position": "QB", "depth_rank": 1})
        sm.load_depth_chart = lambda: dc.copy()
    flex = sal[sal.roster_role == "FLEX"]
    out_ids = inactives(pd, slate, season, week, flex) if use_inact else set()
    inj = flex[flex.player_id.isin(out_ids)][["player_id", "normalized_team", "position_upper"]].rename(
        columns={"normalized_team": "team", "position_upper": "position"}).assign(status="OUT")
    sm.load_injury_status = lambda wk: inj.copy()
    dst_mode = "distributional" if (R / f"data/team_stats_{season}.parquet").exists() else "legacy"
    work = SD / f"ourproj_work_{tag}" / slate; work.mkdir(parents=True, exist_ok=True)
    for m in (bp, bps, bh):
        m.OUTPUT_DIR = work
    t0 = time.time(); buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            bh.build_vegas_file(games, "dk", season, week)
            mf = pm.build_matchup_factors("dk", season, week)
            mf.to_csv(work / f"matchup_factors_dk_{season}_{week}.csv", index=False)
            df = bps.build_statline_projections(
                "dk", season, week, f"sd_{slate}", vegas_slate_id=str(week), dst_model_mode=dst_mode,
                use_volume_prior=True, sigma_recal=True, ignore_played_week=True, neutral_skill_matchup=True,
                props_weight=0.0, use_stack=True, role_change=True, canonical_teams=True)
        df["inactive_out"] = df.player_id.astype(str).isin(out_ids)
        df.loc[df.inactive_out, ["final_projection", "sigma"]] = 0.0
        df.insert(0, "slate", slate); df.insert(1, "season", season); df.insert(2, "week", week)
        df["dst_mode"] = dst_mode; df["n_out"] = len(out_ids)
        outd.mkdir(parents=True, exist_ok=True); df.to_csv(dest, index=False); st = "ok"
    except (Exception, SystemExit) as e:  # noqa: BLE001
        st = f"FAIL {type(e).__name__}: {str(e)[:300]}"
        (work / "error.txt").write_text(traceback.format_exc() + "\n" + buf.getvalue()[-4000:], encoding="utf-8")
    (work / "build.log").write_text(buf.getvalue(), encoding="utf-8")
    return slate, st, round(time.time() - t0)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--depth", default="qb", choices=["qb", "stub"]); ap.add_argument("--no-inactives", action="store_true")
    ap.add_argument("--force", action="store_true"); ap.add_argument("--only", default=None)
    a = ap.parse_args()
    import pandas as pd
    W = pd.read_csv(SD / "slate_weeks_resolved.csv")
    if a.only: W = W[W.slate.isin(a.only.split(","))]
    tag = a.depth + ("_noinact" if a.no_inactives else "")
    jobs = [(r.slate, int(r.season), int(r.week), tag, a.depth, not a.no_inactives, a.force) for r in W.itertuples()]
    with ProcessPoolExecutor(a.workers) as ex:
        for s, st, dt in ex.map(run_slate, jobs):
            print(f"{s}: {st} ({dt}s)", flush=True)


if __name__ == "__main__":
    main()
