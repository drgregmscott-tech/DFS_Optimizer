"""Does a bigger candidate pool help best_lineup_classic.py's scenario-scorer
actually identify a better real-world lineup, or does it just add noise?
Controlled comparison: same field_n/n_sims/seed, only n_candidates varies
(20 vs 100), graded against real results the same way as the other replay
arms.

usage: python analysis/classic_diag/replay_poolsize.py
"""
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import replay_validation as rv
import best_lineup_classic as blc

FIELD_N = 6000
N_SIMS = 800


def main():
    rows = []
    for lab, (f, sid) in rv.SLATES.items():
        fpts_map, real_own_map, real_points, mine = rv.load_real(f)
        row = dict(slate=lab)
        for n_cand in (20, 100):
            t0 = time.time()
            try:
                top_names, top_row = blc.pick_top(
                    "dk", sid, n_candidates=n_cand, field_n=FIELD_N, n_sims=N_SIMS, seed=3,
                )
            except Exception as exc:
                print(f"{lab} n={n_cand}: failed ({type(exc).__name__}: {exc})", file=sys.stderr)
                continue
            ks = [rv.norm(n) for n in top_names]
            g = rv.grade(ks, fpts_map, real_points)
            row[f"n{n_cand}_pregame_avgtop10"] = top_row["avg_top10"]
            row[f"n{n_cand}_pct"] = g["pct"]
            row[f"n{n_cand}_cash"] = g["cash"]
            print(f"{lab} n={n_cand}: done in {time.time()-t0:.0f}s -- real pct {g['pct']:.3f} cash={g['cash']}")
        rows.append(row)

    out = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print(out.to_string(index=False))
    out.to_csv("analysis/classic_diag/replay_poolsize_results.csv", index=False)


if __name__ == "__main__":
    main()
