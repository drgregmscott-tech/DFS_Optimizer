"""Re-run the FC-history OUR-projection generator (analysis/ownership_fc_refit/run_ourproj.py)
with the skill-position matchup factor RESTORED, under several shrinkage rules.
Production code is not edited: everything is monkeypatched per worker.
Variants (outputs -> data/fc_history/derived/ourproj_mh_<variant>/, FC-derived, git-ignored):
  k4   : neutral_skill_matchup=False, SHRINKAGE_K_GAMES=4   (pre-B1 production)
  k16  : neutral_skill_matchup=False, SHRINKAGE_K_GAMES=16
  kq16 : neutral_skill_matchup=False, games-dependent k = 16/g (weight g^2/(g^2+16))
Baseline (matchup neutral for skill) = existing data/fc_history/derived/ourproj/.
    python analysis/proj_matchup_history/run_variants.py --variants k4,k16,kq16 --workers 12
"""
import argparse, sys, time, multiprocessing as mp
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
DER = REPO / "data/fc_history/derived"


def job(args):
    variant, season, weeks = args
    sys.path.insert(0, str(REPO / "analysis/ownership_fc_refit"))
    sys.path.insert(0, str(REPO / "analysis/backtest_multi"))
    sys.path.insert(0, str(REPO / "scripts"))
    import run_ourproj as ro
    import run_backtest as rb
    ro.OUTP = DER / f"ourproj_mh_{variant}"
    ro.WORK = DER / f"ourproj_mh_work_{variant}"
    orig = rb._install_patches

    def patched():
        pd, bp, bps, bh, pm = orig()
        if variant.startswith("kq"):
            c = float(variant[2:])
            def mf(weekly):
                pt = weekly.groupby(["opponent_team", "position", "week"])["fantasy_points"].sum().reset_index()
                g = pt.groupby(["opponent_team", "position"])["fantasy_points"]
                a = g.mean().reset_index().rename(columns={"opponent_team": "team", "fantasy_points": "pts_allowed_avg"})
                a["games"] = g.size().to_numpy()
                raw = a["pts_allowed_avg"] / a.groupby("position")["pts_allowed_avg"].transform("mean")
                w = a["games"] ** 2 / (a["games"] ** 2 + c)
                a["matchup_factor"] = w * raw + (1 - w)
                return a[["team", "position", "matchup_factor"]]
            pm.matchup_factors = mf
        else:
            pm.SHRINKAGE_K_GAMES = float(variant[1:])
        f0 = bps.build_statline_projections
        def f(*a, **kw):
            kw["neutral_skill_matchup"] = False
            return f0(*a, **kw)
        bps.build_statline_projections = f
        return pd, bp, bps, bh, pm
    rb._install_patches = patched
    return [(variant,) + r for r in ro.run_season((season, weeks, False))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", default="k4,k16,kq16")
    ap.add_argument("--workers", type=int, default=12)
    a = ap.parse_args()
    sys.path.insert(0, str(REPO / "analysis/ownership_fc_refit"))
    import run_ourproj as ro
    sal = ro.write_salaries()
    jobs = [(v, s, [w for (ss, w) in sorted(sal) if ss == s]) for v in a.variants.split(",") for s in range(2021, 2027)]
    t0 = time.time()
    with mp.get_context("spawn").Pool(a.workers) as p:
        res = p.map(job, jobs, chunksize=1)
    flat = [r for rr in res for r in rr]
    print(f"done {len(flat)} slates, {sum(str(r[3]).startswith('FAIL') for r in flat)} failed, {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
