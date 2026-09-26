"""Re-run the production-faithful QB1-guard history build (analysis/proj_qb/run_qb1.py) with
statline_model.score_statline wrapped so every player's Monte-Carlo draws are summarised
(fantasy-point quantiles 1..99 + component stat moments/correlations). Research only; NO FC data here.
Output (FC-derived, git-ignored): data/fc_history/derived/proj_sigma/draws/draws_{season}_wk{week}.parquet
    python analysis/proj_sigma/capture_draws.py --workers 6 [--seasons 2021-2026]
"""
from __future__ import annotations
import argparse, sys, multiprocessing as mp
from pathlib import Path
import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "analysis/proj_qb")); sys.path.insert(0, str(REPO / "scripts"))
DER = REPO / "data/fc_history/derived"
OUT = DER / "proj_sigma"
Q = np.arange(1, 100)
STATS = ["pass_yd", "pass_td", "rush_att", "rush_yd", "rush_td", "targets", "rec", "rec_yd", "rec_td"]


def run_season(job):
    import pandas as pd
    import run_qb1 as rq
    rq.OUTP = OUT / "proj"; rq.WORK = OUT / "work"
    import statline_model as sm
    orig_sim, orig_score = sm.simulate, sm.scoring_rules.score_statline
    season, weeks, force = job
    cap = {"on": False, "rows": []}

    def score_wrap(draws, site):
        pts = orig_score(draws, site)
        if cap["on"]:
            r = {f"q{q}": v for q, v in zip(Q, np.percentile(pts, Q))}
            r["pts_sd"] = float(pts.std(ddof=1)); r["pts_mean"] = float(pts.mean())
            for s in STATS:
                a = np.asarray(draws.get(s, np.zeros(1)), float)
                r[f"sim_{s}_m"] = float(a.mean()); r[f"sim_{s}_sd"] = float(a.std())
            for y, t in (("pass_yd", "pass_td"), ("rush_yd", "rush_td"), ("rec_yd", "rec_td")):
                a, b = np.asarray(draws[y], float), np.asarray(draws[t], float)
                r[f"sim_c_{y}"] = float(np.corrcoef(a, b)[0, 1]) if a.std() > 0 and b.std() > 0 else np.nan
            cap["rows"].append(r)
        return pts

    def sim_wrap(pool, site, variance, **kw):
        first = not cap.get("done")
        cap["on"] = first; cap["rows"] = [] if first else cap["rows"]
        df = orig_sim(pool, site, variance, **kw)
        if first:
            cap["done"] = True; cap["on"] = False
            assert len(df) == len(cap["rows"]), (len(df), len(cap["rows"]))
            cap["df"] = pd.concat([df[["player_id"]].reset_index(drop=True), pd.DataFrame(cap["rows"])], axis=1)
        return df

    sm.scoring_rules.score_statline = score_wrap
    sm.simulate = sim_wrap
    (OUT / "draws").mkdir(parents=True, exist_ok=True)
    for w in weeks:
        dest = OUT / "draws" / f"draws_{season}_wk{w}.parquet"
        if dest.exists() and not force:
            continue
        cap.clear(); cap.update(on=False, rows=[])
        (OUT / "proj" / f"proj_{season}_wk{w}.csv").unlink(missing_ok=True)
        rq.run_season((season, [w], True))
        if "df" in cap:
            d = cap["df"]; d.insert(0, "season", season); d.insert(1, "week", w); d.to_parquet(dest)
    return season


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seasons", default="2021-2026"); ap.add_argument("--weeks", default=None)
    a = ap.parse_args()
    lo, hi = map(int, a.seasons.split("-")) if "-" in a.seasons else (int(a.seasons),) * 2
    have = {}
    for p in (DER / "salaries_ourproj").glob("salaries_dk_fcmain_*_wk*.csv"):
        s, w = int(p.stem.split("_")[3]), int(p.stem.split("_wk")[1])
        if lo <= s <= hi and (a.weeks is None or w in eval(f"range({a.weeks.replace('-', ',')}+1)")):
            have.setdefault(s, []).append(w)
    jobs = [(s, [w], False) for s in sorted(have) for w in sorted(have[s])]
    with mp.get_context("spawn").Pool(a.workers) as pool:
        for r in pool.imap_unordered(run_season, jobs):
            pass
    print("done", len(jobs))


if __name__ == "__main__":
    main()
