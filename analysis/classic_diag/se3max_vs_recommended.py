"""FYI check requested by Greg (2026-09-23): does the "SE / 3-Max GPP" preset
("Build Lineups" -- optimizer.py's direct mean-variance ILP solve, the
manual GPP-portfolio feature) agreeing with recommend_lineup.py's pick (the
separate worst_top25_realstack Monte Carlo selection) predict anything about
real cash outcomes? Never tested before -- these are two independently-built
features that happen to read the same final_projections file, and nobody
had checked whether their agreement/disagreement carries real signal.

EXPLICIT CAVEAT (Greg's own framing, going in): this is n=6 real logged
slates across 2 real weeks with genuinely unusual variance (Week 1 one of
the highest-scoring weeks in recent memory, Week 2 a low-scoring response)
-- an FYI data point, not a statistically powered test. Don't over-read a
clean-looking pattern here any more than the "4/6, 0.709" number earlier
this investigation was over-read.

Method: for each of the 6 slates, build the SE/3-Max GPP preset's exact 3
lineups (build_multi_lineup with n_lineups=3, max_exposure=100, uniqueness=3,
randomization_pct=3, stack_mode="qb", stack_size=1, bring_back=True,
lam=0.063, exclude_skill_vs_opp_dst=True -- byte-identical to
dfs_optimizer_frontend/index.html's BUILTIN_PRESETS["SE / 3-Max GPP"]), then
compare each of those 3 against recommend_lineup.py's own pick (same
worst_top25_realstack call, imported directly -- not re-implemented) by
exact-lineup match and by player-overlap count out of 9. Grades every
lineup (the 3 SE3max picks AND the recommended pick) against the same real
results every other test in this investigation uses.

usage: python analysis/classic_diag/se3max_vs_recommended.py [n_candidates] [field_n] [n_sims]
"""
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import optimizer  # noqa: E402
import replay_validation as rv  # noqa: E402
from recommend_lineup import recommend_lineup  # noqa: E402

N_CAND = int(sys.argv[1]) if len(sys.argv) > 1 else 80
FIELD_N = int(sys.argv[2]) if len(sys.argv) > 2 else 6000
N_SIMS = int(sys.argv[3]) if len(sys.argv) > 3 else 800
SEED = 3


def se3max_lineups(site, slate_id, seed):
    # Byte-identical to BUILTIN_PRESETS["SE / 3-Max GPP"] in
    # dfs_optimizer_frontend/index.html (2026-09-23 snapshot).
    df, exposure, n_generated = optimizer.build_multi_lineup(
        site, slate_id,
        n_lineups=3, max_exposure_pct=100, uniqueness=3,
        randomization_pct=3, stack_mode="qb", stack_size=1,
        stack_positions={"WR", "TE"},  # optimizer.py's own CLI default (DEFAULT_STACK_POSITIONS) --
        # solve_lineup()/build_multi_lineup() only default this to None, the
        # CLI parses "WR,TE" into a set before calling; the frontend leaves
        # ctrlStackPositions at its own default checkbox state, which is the
        # same {WR, TE}, so this reproduces the real preset exactly.
        bring_back=True, lam=0.063, exclude_skill_vs_opp_dst=True,
        seed=seed,
    )
    out = []
    if "lineup_id" not in df.columns:
        df = df.copy()
        df["lineup_id"] = 1
    for lid, g in df.groupby("lineup_id"):
        out.append(set(g["player_name"].tolist()))
    return out


def main():
    rows = []
    for lab, (f, sid) in rv.SLATES.items():
        t0 = time.time()
        fpts_map, real_own_map, real_points, mine = rv.load_real(f)

        try:
            se3max_sets = se3max_lineups("dk", sid, SEED)
        except Exception as exc:
            print(f"{lab}: SE3max build failed ({type(exc).__name__}: {exc})", file=sys.stderr)
            continue

        try:
            # 2026-09-23: recommend_lineup() now returns up to top_n ranked
            # lineups stacked together (see its own docstring) -- this
            # comparison is specifically against THE recommendation (rank 1),
            # not the margin/confidence context ranks 2/3.
            rec_lineups = recommend_lineup("dk", sid, n_candidates=N_CAND, field_n=FIELD_N, n_sims=N_SIMS, seed=SEED)
            rec_lineup = rec_lineups[rec_lineups["recommendation_rank"] == 1]
        except Exception as exc:
            print(f"{lab}: recommend_lineup failed ({type(exc).__name__}: {exc})", file=sys.stderr)
            continue

        rec_set = set(rec_lineup["player_name"].tolist())
        rec_ks = [rv.norm(n) for n in rec_lineup["player_name"]]
        g_rec = rv.grade(rec_ks, fpts_map, real_points)

        best_overlap = -1
        exact_match_any = False
        se3max_grades = []
        for i, s in enumerate(se3max_sets):
            overlap = len(s & rec_set)
            best_overlap = max(best_overlap, overlap)
            if overlap == 9:
                exact_match_any = True
            ks = [rv.norm(n) for n in s]
            g = rv.grade(ks, fpts_map, real_points)
            se3max_grades.append(g)
            print(f"{lab}: SE3max lineup {i+1} overlap={overlap}/9 with recommended -- "
                  f"cash={g['cash']} pct={g['pct']:.3f}")

        best_se3max_pct = max((g["pct"] for g in se3max_grades), default=float("nan"))
        any_se3max_cash = any(g["cash"] for g in se3max_grades)

        row = dict(slate=lab, n_se3max_lineups=len(se3max_sets),
                   best_overlap_of_9=best_overlap, exact_match_any=exact_match_any,
                   rec_cash=g_rec["cash"], rec_pct=g_rec["pct"],
                   best_se3max_pct=best_se3max_pct, any_se3max_cash=any_se3max_cash,
                   runtime_s=round(time.time() - t0))
        rows.append(row)
        print(f"{lab}: done in {row['runtime_s']}s -- best_overlap={best_overlap}/9 "
              f"exact_match={exact_match_any} | recommended pct={g_rec['pct']:.3f} cash={g_rec['cash']} "
              f"| best SE3max pct={best_se3max_pct:.3f} any_cash={any_se3max_cash}")

    out_df = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print("\n" + out_df.to_string(index=False))

    high_overlap = out_df[out_df["best_overlap_of_9"] >= 7]
    low_overlap = out_df[out_df["best_overlap_of_9"] < 7]
    print(f"\nHigh-overlap slates (>=7/9 shared players, n={len(high_overlap)}): "
          f"recommended cash {high_overlap['rec_cash'].sum()}/{len(high_overlap)}, "
          f"mean pctile {high_overlap['rec_pct'].mean() if len(high_overlap) else float('nan'):.3f}")
    print(f"Low-overlap slates (<7/9 shared players, n={len(low_overlap)}): "
          f"recommended cash {low_overlap['rec_cash'].sum()}/{len(low_overlap)}, "
          f"mean pctile {low_overlap['rec_pct'].mean() if len(low_overlap) else float('nan'):.3f}")
    print(f"\nExact-match slates: {out_df['exact_match_any'].sum()}/{len(out_df)}")
    print("\n*** n=6 real slates across 2 unusually-variant weeks -- FYI signal, not a powered test. ***")

    out_df.to_csv("analysis/classic_diag/se3max_vs_recommended_results.csv", index=False)


if __name__ == "__main__":
    main()
