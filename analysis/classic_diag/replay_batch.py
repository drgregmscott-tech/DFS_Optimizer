"""How many of a diversified N-lineup batch (built with the confirmed
stack=2 + bring-back settings) would have actually cashed, graded against
real results? And does a bigger batch (100 vs 10) help the scenario-scorer
pick the actual winner more reliably? Two separate questions, both testable
without new simulation infrastructure -- reuses replay_validation.py's real-
result loading/grading and optimizer.py's own batch builder.

usage: python analysis/classic_diag/replay_batch.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import optimizer
import replay_validation as rv


def build_batch(sid, n_lineups):
    all_lineups, exposure, n_gen = optimizer.build_multi_lineup(
        "dk", sid, n_lineups=n_lineups, max_exposure_pct=0.5,
        randomization_pct=20.0, seed=7,
        stack_mode="qb", stack_size=2, stack_positions={"WR", "TE"}, bring_back=True,
        flex_positions={"RB", "WR", "TE"},
    )
    return all_lineups, n_gen


def main():
    rows = []
    for lab, (f, sid) in rv.SLATES.items():
        fpts_map, real_own_map, real_points, mine = rv.load_real(f)
        for n_req in (10, 100):
            lineups, n_gen = build_batch(sid, n_req)
            hits = 0
            pcts = []
            for lid, g in lineups.groupby("lineup_id"):
                ks = g.player_name.map(rv.norm)
                graded = rv.grade(ks, fpts_map, real_points)
                pcts.append(graded["pct"])
                hits += graded["cash"]
            rows.append(dict(slate=lab, n_requested=n_req, n_generated=n_gen, hits=hits,
                              hit_rate=hits / n_gen if n_gen else float("nan"),
                              mean_pct=sum(pcts) / len(pcts) if pcts else float("nan"),
                              max_pct=max(pcts) if pcts else float("nan")))
            print(f"{lab} n={n_req}: {hits}/{n_gen} cashed, mean pct {rows[-1]['mean_pct']:.3f}, best pct {rows[-1]['max_pct']:.3f}")

    out = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print(out.to_string(index=False))
    out.to_csv("analysis/classic_diag/replay_batch_results.csv", index=False)


if __name__ == "__main__":
    main()
