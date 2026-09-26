"""Regenerate OUR early-season (wk1-4) projections under alternative history regimes (research only, no FC data inside).

Arms (all otherwise identical to analysis/ownership_fc_refit/run_ourproj.py; DST/team-stats untouched):
  base  : harness as-is (wk1 = empty history -> pure price prior; wk2-4 = current-season games only)
  prod  : PRODUCTION-FAITHFUL. wk1 reads the full prior REG season (production passes --season S-1 --week 23),
          and absent_discount is OFF at wk1 (production's week=23 -> absent_discount=False). wk2-4 identical to base,
          because production passes the real (season, week) from wk2 on -> no cross-season carryover.
  carry : CANDIDATE FIX. wk1 as prod; wk2-4 read prior REG season (weeks shifted by -30 so they sort first) +
          current-season weeks < W. RECENCY_WEIGHTS (last 5 games) and shrinkage then span both seasons.
Outputs (FC salary pool -> FC-derived, git-ignored): data/fc_history/derived/proj_early_season/{arm}/proj_S_wkW.csv
    python analysis/proj_early_season/regen_early.py --arms base,prod,carry --seasons 2021-2026 --weeks 1-4
"""
from __future__ import annotations
import argparse, contextlib, io, multiprocessing as mp, sys, time, traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DER = REPO / "data/fc_history/derived"
SAL = DER / "salaries_ourproj"
OUT = DER / "proj_early_season"


def run(job):
    arm, season, weeks = job
    sys.path.insert(0, str(REPO / "analysis/backtest_multi"))
    import run_backtest as rb
    pd, bp, bps, bh, pm = rb._install_patches()
    import statline_model as sm
    games = pd.read_csv(REPO / "data/nflverse_games.csv")
    bp.load_salaries = bps.load_salaries = lambda site, sid: pd.read_csv(SAL / f"salaries_{site}_{sid}.csv", dtype={"player_id": str, "ID": str})
    if not (REPO / f"data/schedules_{season}.parquet").exists():
        def ls(s):
            g = games[games.season == s].copy(); g["season_type"] = g["game_type"]; return g
        bp.load_schedule = bps.load_schedule = ls
    dst_mode = "distributional" if (REPO / f"data/team_stats_{season}.parquet").exists() else "legacy"
    orig_lh, orig_avp = sm.load_history, sm.apply_volume_prior

    def lh(s, w):
        cur = orig_lh(s, w)
        if arm == "base" or arm.startswith("curw"):
            return cur
        if w == 1 or arm == "carry":
            prev = orig_lh(s - 1, 99)
            if w == 1:
                return prev
            prev = prev.copy(); prev["week"] = prev["week"] - 30
            return pd.concat([prev, cur], ignore_index=True)
        return cur
    sm.load_history = lh
    if arm.startswith(("prodw", "curw")):   # candidate fix: prior-season lookback but price weight floored at wNN/100
        import numpy as np, volume_prior as vpm
        _cw, fl = vpm.cold_start_weight, int(arm.lstrip("prodcurw")) / 100.0
        vpm.cold_start_weight = lambda gp, *a, **k: np.maximum(_cw(gp, *a, **k), fl)
    res = []
    for week in weeks:
        dest = OUT / arm / f"proj_{season}_wk{week}.csv"
        if dest.exists():
            continue
        def avp(*a, **k):
            if arm != "base" and not arm.startswith("curw") and week == 1:  # prod*, carry
                k["absent_discount"] = False
            return orig_avp(*a, **k)
        sm.apply_volume_prior = avp
        work = OUT / f"work_{arm}" / f"{season}_wk{week}"; work.mkdir(parents=True, exist_ok=True)
        for m in (bp, bps, bh):
            m.OUTPUT_DIR = work
        t0, buf = time.time(), io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                bh.build_vegas_file(games, "dk", season, week)
                pm.build_matchup_factors("dk", season, week).to_csv(work / f"matchup_factors_dk_{season}_{week}.csv", index=False)
                df = bps.build_statline_projections(
                    "dk", season, week, f"fcmain_{season}_wk{week}", vegas_slate_id=str(week), dst_model_mode=dst_mode,
                    use_volume_prior=True, sigma_recal=True, ignore_played_week=True, neutral_skill_matchup=True,
                    props_weight=0.0, use_stack=True, role_change=True, canonical_teams=True)
            df.insert(0, "season", season); df.insert(1, "week", week)
            dest.parent.mkdir(parents=True, exist_ok=True); df.to_csv(dest, index=False); st = "ok"
        except (Exception, SystemExit) as e:  # noqa: BLE001
            st = f"FAIL {type(e).__name__}: {str(e)[:200]}"
            with open(OUT / "errors.txt", "a", encoding="utf-8") as f:
                f.write(f"{arm} {season} wk{week}: {st}\n{traceback.format_exc()}\n{buf.getvalue()[-1500:]}\n")
        print(f"{arm} {season} wk{week}: {st} ({time.time()-t0:.0f}s)", flush=True)
        res.append((arm, season, week, st))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="base,prod,carry"); ap.add_argument("--seasons", default="2021-2026")
    ap.add_argument("--weeks", default="1-4"); ap.add_argument("--workers", type=int, default=12)
    a = ap.parse_args()
    sys.path.insert(0, str(REPO / "analysis/backtest_multi"))
    from run_backtest import parse_range
    have = {tuple(int(x) for x in p.stem.replace("salaries_dk_fcmain_", "").split("_wk")) for p in SAL.glob("salaries_dk_fcmain_*.csv")}
    jobs = []
    for arm in a.arms.split(","):
        for s in parse_range(a.seasons):
            wk = [w for w in parse_range(a.weeks) if (s, w) in have and not (arm.startswith("prod") and w > 1)]
            if wk:
                jobs.append((arm, s, wk))
    with mp.get_context("spawn").Pool(min(a.workers, len(jobs))) as p:
        res = p.map(run, jobs, chunksize=1)
    flat = [r for rr in res for r in rr]
    print("done", len(flat), "fail", sum(r[3].startswith("FAIL") for r in flat))


if __name__ == "__main__":
    main()
