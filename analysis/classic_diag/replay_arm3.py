"""Arm 3 of the replay test (see scripts/replay_validation.py's docstring for
the full 3-arm design): candidate pool + scenario scoring
(best_lineup_classic.py), graded against real results the same way Arms
1/B/C are graded. This is the piece that was built and smoke-tested but
never actually checked against real outcomes -- closing that gap.

Selection stays blind to real results (only pre-game info: projections +
simulated field + scenario model) -- results are revealed only after the
top-ranked candidate is picked, exactly like a real pre-lock decision.

usage: python analysis/classic_diag/replay_arm3.py [n_candidates] [field_n] [n_sims]
"""
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import replay_validation as rv
import best_lineup_classic as blc

N_CAND = int(sys.argv[1]) if len(sys.argv) > 1 else 80
FIELD_N = int(sys.argv[2]) if len(sys.argv) > 2 else 6000
N_SIMS = int(sys.argv[3]) if len(sys.argv) > 3 else 800


def main():
    rows = []
    for lab, (f, sid) in rv.SLATES.items():
        t0 = time.time()
        fpts_map, real_own_map, real_points, mine = rv.load_real(f)
        try:
            top_names, top_row = blc.pick_top(
                "dk", sid, n_candidates=N_CAND, field_n=FIELD_N, n_sims=N_SIMS, seed=3,
            )
        except Exception as exc:
            print(f"{lab}: Arm 3 failed ({type(exc).__name__}: {exc})", file=sys.stderr)
            continue
        ks = [rv.norm(n) for n in top_names]
        g = rv.grade(ks, fpts_map, real_points)
        row = dict(slate=lab, pre_game_avg_top10=top_row["avg_top10"], pre_game_worst_top10=top_row["worst_top10"],
                   pre_game_avg_top1=top_row["avg_top1"], picked_names=", ".join(top_names))
        row.update({f"arm3_{k}": v for k, v in g.items()})
        if mine:
            row["arm1_cash"] = mine["cash"]
            row["arm1_pct"] = mine["pct"]
        rows.append(row)
        print(f"{lab}: done in {time.time()-t0:.0f}s -- real result: {g}")

    out = pd.DataFrame(rows)
    pd.set_option("display.width", 220)
    print(out.to_string(index=False))
    print(f"\nCash count -- Arm3 (candidate pool + scenario scoring): {out.arm3_cash.sum()}/{len(out)}")
    out.to_csv("analysis/classic_diag/replay_arm3_results.csv", index=False)


if __name__ == "__main__":
    main()
