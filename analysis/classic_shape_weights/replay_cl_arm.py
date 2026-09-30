"""Sanity check for the --cl-* classic shape weights (WK3_POSTMORTEM_OPEN item 5).
Reuses scripts/replay_validation.py's loaders/grader/solve path on the 6 real 2026
wk1-2 DK classic SE3max slates. Arm B = stack=2 + bring-back (se3max_pool structure);
Arm CL = Arm B + candidate --cl-* weights. n=6 spot check, not a statistical test.
usage: python analysis/classic_shape_weights/replay_cl_arm.py
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import optimizer  # noqa: E402
import replay_validation as rv  # noqa: E402

CL = dict(dst_band_bonus=1.0, dst_expensive_penalty=2.5, zero_punt_penalty=1.5,
          three_plus_punt_penalty=3.0, flex_rb_bonus=0.8, flex_wr_penalty=1.3)
import os  # noqa: E402
if os.environ.get("CL_SHADED"):  # raw-only terms x0.75 (the zero-punt controlled/raw ratio)
    CL = dict(dst_band_bonus=0.8, dst_expensive_penalty=2.0, zero_punt_penalty=1.5,
              three_plus_punt_penalty=2.5, flex_rb_bonus=0.6, flex_wr_penalty=1.0)


def solve(pool, cl, proj=None, max_cands=None):
    fixed_counts, flex_count = optimizer.parse_roster_requirements(optimizer.SITE_CONFIGS["dk"]["roster_slots"])
    sp = {"WR", "TE"}
    cands, _, _ = optimizer.resolve_stack_candidates(
        pool, "qb", sp, None, None, None, optimizer.DEFAULT_STACK_CANDIDATE_POOL,
        diversify_requested="off", bring_back=True)
    # Same cross-candidate pick as build_multi_lineup: best (proj + shape adj) over stack teams.
    best = None
    for c in cands[:max_cands]:
        try:
            sel = optimizer.solve_lineup(
                pool, optimizer.SITE_CONFIGS["dk"]["salary_cap"], fixed_counts, flex_count,
                stack_mode="qb", stack_size=2, stack_positions=sp, bring_back=True,
                target_team=c["target_team"], flex_positions={"RB", "WR", "TE"}, optimization_projection=proj, **cl)
        except Exception:
            continue
        base = sel["final_projection"].sum() if proj is None else proj.reindex(sel.player_id).sum()
        score = base + optimizer.classic_shape_adjustment(sel, fixed_counts, **cl)
        if best is None or score > best[0]:
            best = (score, sel)
    return best[1], fixed_counts


def shape(sel, fc):
    pos, sal = sel.position, sel.salary
    dst_sal = int(sal[pos.isin(["DST", "DEF"])].iloc[0])
    punts = int(((~pos.isin(["DST", "DEF"])) & (sal <= 4000)).sum())
    flex = "RB" if (pos == "RB").sum() > fc["RB"] else "WR" if (pos == "WR").sum() > fc["WR"] else "TE"
    return dict(sal=int(sal.sum()), dst=dst_sal, punts=punts, flex=flex, proj=round(sel.final_projection.sum(), 1))


CR = ROOT / "data" / "contest_results"
# rv.SLATES points at ~/Downloads copies that no longer exist; same files live in data/contest_results.
SLATES = {f"{w}_{s}": (str(CR / f"dk_classic_{w}_{s}_{d}{sfx}_full.csv"), f"dk_classic_{w}_{s}_{d}")
          for w, d in (("wk1", "13Sep2026"), ("wk2", "20Sep2026"), ("wk3", "27Sep2026"))
          for s in ("main", "early", "afternoon")
          for sfx in [("" if w == "wk1" else "_se3max")]}

rows = []
for lab, (f, sid) in SLATES.items():
    fpts, _, real_points, _ = rv.load_real(f)
    pool = optimizer.load_final_projections("dk", sid)
    pool = pool[pool.position.isin(["QB", "RB", "WR", "TE", "DST"])].copy()
    r = dict(slate=lab)
    for arm, cl in (("B", {}), ("CL", CL)):
        sel, fc = solve(pool, cl)
        g = rv.grade(sel.player_name.map(rv.norm), fpts, real_points)
        r.update({f"{arm}_{k}": (round(v, 3) if isinstance(v, float) else v) for k, v in {**shape(sel, fc), **g}.items()})
        r[f"{arm}_ids"] = frozenset(sel.player_id)
    r["same"] = r.pop("B_ids") == r.pop("CL_ids")
    rows.append(r)

out = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(out.to_string(index=False))
print(f"\ncash B={out.B_cash.sum()}/{len(out)}  CL={out.CL_cash.sum()}/{len(out)}  mean pct B={out.B_pct.mean():.3f} CL={out.CL_pct.mean():.3f}"
      f"  mean real pts B={out.B_pts.mean():.1f} CL={out.CL_pts.mean():.1f}  identical lineups={out.same.sum()}/{len(out)}")

# Noise reduction: n=1 lineup per slate is dominated by which 1-2 players boom.
# Paired seeded draws (se3max_pool's 5% randomization, same seed for both arms)
# give a small per-slate distribution of plausible lineups under each arm.
import numpy as np  # noqa: E402
N_SEEDS = int(sys.argv[1]) if len(sys.argv) > 1 else 0
if N_SEEDS:
    rr = []
    for lab, (f, sid) in SLATES.items():
        fpts, _, real_points, _ = rv.load_real(f)
        pool = optimizer.load_final_projections("dk", sid)
        pool = pool[pool.position.isin(["QB", "RB", "WR", "TE", "DST"])].copy()
        for seed in range(N_SEEDS):
            proj = optimizer.randomize_projections(pool, 5, np.random.default_rng(seed))
            for arm, cl in (("B", {}), ("CL", CL)):
                sel, fc = solve(pool, cl, proj, max_cands=5)
                g = rv.grade(sel.player_name.map(rv.norm), fpts, real_points)
                rr.append(dict(slate=lab, seed=seed, arm=arm, **shape(sel, fc), **g))
    R = pd.DataFrame(rr)
    R.to_csv(Path(__file__).parent / ("seeded_arms_shaded.csv" if os.environ.get("CL_SHADED") else "seeded_arms.csv"), index=False)
    agg = R.groupby(["slate", "arm"]).agg(pct=("pct", "mean"), cash=("cash", "mean"), pts=("pts", "mean"),
                                         punts=("punts", "mean"), dst=("dst", "mean"),
                                         flexRB=("flex", lambda s: (s == "RB").mean())).unstack("arm")
    print(agg.round(3).to_string())
    W = R.pivot_table(index=["slate", "seed"], columns="arm", values=["pct", "cash", "pts"])
    d = (W["pct"]["CL"] - W["pct"]["B"])
    print(f"\nseeded n={len(W)} pairs: cash rate B={W['cash']['B'].mean():.3f} CL={W['cash']['CL'].mean():.3f}; "
          f"mean pct B={W['pct']['B'].mean():.3f} CL={W['pct']['CL'].mean():.3f}; "
          f"paired pct diff {d.mean():+.3f} (slate-level SE {d.groupby(level=0).mean().std()/np.sqrt(d.index.get_level_values(0).nunique()):.3f})")
    print("per-slate pct diff:", d.groupby(level=0).mean().round(3).to_dict())
    shp = R.groupby("arm").agg(dst_band=("dst", lambda s: s.between(2800, 3100).mean()), dst_exp=("dst", lambda s: (s >= 3600).mean()),
                                zero_punt=("punts", lambda s: (s == 0).mean()), three_punt=("punts", lambda s: (s >= 3).mean()),
                                flex_rb=("flex", lambda s: (s == "RB").mean()), flex_wr=("flex", lambda s: (s == "WR").mean()),
                                proj=("proj", "mean"))
    print(shp.round(3).to_string())
