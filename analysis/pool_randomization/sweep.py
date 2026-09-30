"""SE3max pool randomization/uniqueness sweep (2026-09-29). DO NOT COMMIT builds/ (history pools are FC-derived).

Pools ("cur" = current production inputs; early blend is disabled in data/early_season_blend_config.json):
  2026: wk1-2 = lineup_replay/builds/old (blend off; QB recal is a no-op before wk3; ownership v2 does not enter the
        solve at lambda 0), wk3 = lineup_replay/builds/new (QB recal + v2, blend never applied wk3).
  hist: lineup_replay/builds/hist/old + production _apply_qb_recal (blend config weeks={} -> no-op), FC-zero proxy re-applied.
Runs optimizer.build_multi_lineup (tracked code, unchanged) with the se3max_pool preset and overrides.
usage: python sweep.py <nproc>
"""
import os, sys, time, io, contextlib, tempfile
from pathlib import Path
from multiprocessing import Pool
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
LR = REPO / "analysis" / "lineup_replay" / "builds"
sys.path.insert(0, str(REPO / "scripts"))
OUT = HERE / "builds"
PRESET = dict(n_lineups=100, max_exposure_pct=0.5, uniqueness=1, randomization_pct=20.0,
              stack_mode="qb", stack_size=2, stack_positions={"WR", "TE"}, bring_back=True, lam=0.0)
# (label, randomization_pct, uniqueness, seeds)
CONFIGS = [("r0_u1", 0, 1, [1]), ("r3_u1", 3, 1, [1, 2, 3]), ("r5_u1", 5, 1, [1, 2, 3]),
           ("r10_u1", 10, 1, [1, 2, 3]), ("r20_u1", 20, 1, [1, 2, 3]),
           ("r0_u2", 0, 2, [1]), ("r0_u3", 0, 3, [1]), ("r3_u2", 3, 2, [1, 2]), ("r3_u3", 3, 3, [1, 2])]
S26 = ["dk_classic_wk1_main_13Sep2026", "dk_classic_wk1_early_13Sep2026", "dk_classic_wk1_afternoon_13Sep2026",
       "dk_classic_wk2_main_20Sep2026", "dk_classic_wk2_early_20Sep2026", "dk_classic_wk2_afternoon_20Sep2026",
       "dk_classic_wk3_main_27Sep2026", "dk_classic_wk3_early_27Sep2026", "dk_classic_wk3_afternoon_27Sep2026"]
HIST = sorted(pd.read_csv(REPO / "analysis/lineup_replay/hist_summary.csv").query("preset=='se_gpp'").tag.unique())


def prep():
    (OUT / "pools").mkdir(parents=True, exist_ok=True)
    import build_projections_statline as bps
    for s in S26:
        src = LR / ("new" if "wk3" in s else "old") / f"final_projections_dk_{s}.csv"
        pd.read_csv(src, dtype={"player_id": str}).to_csv(OUT / "pools" / f"final_projections_dk_{s}.csv", index=False)
    for t in HIST:
        o = pd.read_csv(LR / "hist" / "old" / f"final_projections_dk_hist_{t}.csv", dtype={"player_id": str})
        zero = o.final_projection <= 0
        o["no_real_game_this_week"] = False
        with contextlib.redirect_stdout(io.StringIO()):
            n = bps._apply_early_season_blend(o.copy(), int(t[6:]))
            n = bps._apply_qb_recal(n, int(t[6:]))
        n.loc[zero, "final_projection"] = 0.0
        n.drop(columns=["no_real_game_this_week"]).to_csv(OUT / "pools" / f"final_projections_dk_hist_{t}.csv", index=False)


def job(a):
    sid, lab, r, u, seed = a
    f = OUT / f"L_{sid}_{lab}_s{seed}.csv"
    if f.exists():
        return
    import optimizer
    d = tempfile.mkdtemp(prefix="pr_")
    import shutil
    shutil.copy(OUT / "pools" / f"final_projections_dk_{sid}.csv", d)
    optimizer.OUTPUT_DIR = Path(d)
    kw = dict(PRESET); kw.update(randomization_pct=float(r), uniqueness=u)
    t0 = time.time()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            L, _, n = optimizer.build_multi_lineup("dk", sid, seed=seed, **kw)
    except Exception as e:
        (OUT / f"ERR_{sid}_{lab}_s{seed}.txt").write_text(repr(e)); return
    L = L.copy(); L["build_sec"] = time.time() - t0
    L.to_csv(f, index=False)
    shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    if not (OUT / "pools").exists() or len(list((OUT / "pools").glob("*.csv"))) < len(S26) + len(HIST):
        prep()
    only = sys.argv[2] if len(sys.argv) > 2 else None
    # history (time budget): every other slate (32), 1 seed per setting, uniqueness arms r0_u3/r3_u3 only
    HC = [(l, r, u, ss[:1]) for l, r, u, ss in CONFIGS if l not in ("r3_u2", "r0_u2")]
    jobs = [(sid, lab, r, u, s) for sid in S26 for lab, r, u, ss in CONFIGS for s in ss]
    jobs += [(f"hist_{t}", lab, r, u, s) for t in HIST[::2] for lab, r, u, ss in HC for s in ss]
    if only:
        jobs = [j for j in jobs if only in j[0]]
    with Pool(int(sys.argv[1])) as p:
        for i, _ in enumerate(p.imap_unordered(job, jobs)):
            if i % 50 == 0:
                print(i, len(jobs), flush=True)
