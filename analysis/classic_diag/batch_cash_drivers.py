"""Within our OWN confirmed-settings candidate batches (stack=2, bring-back,
already-good structure), what distinguishes the lineups that actually cashed
from the ones that didn't? Unlike the original 51k-lineup diagnostic (which
compared across the WHOLE real field, where structure varies wildly), this
holds structure roughly fixed and asks a narrower, cleaner question: among
similarly-well-built lineups, which specific-player choices mattered.

usage: python analysis/classic_diag/batch_cash_drivers.py [n_lineups_per_slate]
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import optimizer
import replay_validation as rv
import replay_batch as rb

N = int(sys.argv[1]) if len(sys.argv) > 1 else 150


def main():
    frames = []
    for lab, (f, sid) in rv.SLATES.items():
        fpts_map, real_own_map, real_points, mine = rv.load_real(f)
        pool = optimizer.load_final_projections("dk", sid)
        pool["k"] = pool.player_name.map(rv.norm)
        own_map = pool.drop_duplicates("k").set_index("k").estimated_ownership_pct.to_dict()
        implied = pool.dropna(subset=["implied_total"]).drop_duplicates("team").set_index("team").implied_total

        lineups, n_gen = rb.build_batch(sid, N)
        rows = []
        for lid, g in lineups.groupby("lineup_id"):
            ks = g.player_name.map(rv.norm)
            graded = rv.grade(ks, fpts_map, real_points)
            dst_row = g[g.position == "DST"].iloc[0]
            flex_row = g[g.roster_slot == "FLEX"].iloc[0]
            raw_stack_target = g["stack_target"].iloc[0] if "stack_target" in g.columns else ""
            stack_team = raw_stack_target.split(":", 1)[1] if raw_stack_target.startswith("team:") else None
            own_sum = sum(own_map.get(k, 0.0) for k in ks)
            stack_total = implied.get(stack_team, np.nan)
            opp_of_stack = pool.loc[pool.team == stack_team, "opponent"].iloc[0] if (pool.team == stack_team).any() else None
            opp_total = implied.get(opp_of_stack, np.nan)
            is_favorite = (stack_total > opp_total) if pd.notna(stack_total) and pd.notna(opp_total) else np.nan
            rows.append(dict(
                slate=lab, lineup_id=lid, cash=graded["cash"], pct=graded["pct"],
                total_projection=g.projection.sum(), salary=g.salary.sum(),
                own_sum=own_sum, dst_own=own_map.get(rv.norm(dst_row.player_name), np.nan),
                dst_opp_total=implied.get(dst_row.opponent, np.nan),
                flex_pos=flex_row.position,
                stack_team=stack_team, stack_team_implied_total=stack_total,
                stack_is_favorite=is_favorite,
            ))
        frames.append(pd.DataFrame(rows))

    A = pd.concat(frames, ignore_index=True)
    print(f"Total lineups analyzed: {len(A)} across {A.slate.nunique()} slates ({A.cash.sum()} cashed, {(~A.cash).sum()} missed)\n")

    # standardize within slate so different slates' salary/projection/ownership scales don't confound
    for col in ["total_projection", "salary", "own_sum", "dst_own", "dst_opp_total", "stack_team_implied_total"]:
        A[col + "_z"] = A.groupby("slate")[col].transform(lambda x: (x - x.mean()) / max(float(x.std(ddof=0)), 1e-9))

    print("--- mean value: cashed vs missed (within-slate z-scores, so 0 = slate average) ---")
    zcols = [c for c in A.columns if c.endswith("_z")]
    print(A.groupby("cash")[zcols].mean().T.to_string())

    print("\n--- categorical breakdowns (cash rate by bucket) ---")
    for col in ["flex_pos", "stack_is_favorite"]:
        g = A.groupby(col, observed=True).agg(n=("cash", "size"), cash_rate=("cash", "mean")).reset_index()
        print(f"\n{col}:")
        print(g.to_string(index=False))

    # pooled logistic on cash outcome using the standardized features
    X = A[zcols].fillna(0.0)
    Xm = np.c_[np.ones(len(X)), X.values]
    y = A.cash.to_numpy(float)
    b = np.zeros(Xm.shape[1])
    for _ in range(25):
        p = 1 / (1 + np.exp(-Xm @ b))
        W = p * (1 - p)
        H = Xm.T @ (Xm * W[:, None]) + 1e-6 * np.eye(len(b))
        b = b + np.linalg.solve(H, Xm.T @ (y - p))
    se = np.sqrt(np.diag(np.linalg.inv(H)))
    print(f"\n--- pooled logistic for cash within our own batches ({len(A)} lineups; |z|>2 ~ real) ---")
    print(pd.DataFrame({"coef": b, "z": b / se}, index=["const"] + zcols).round(2).to_string())

    A.to_csv("analysis/classic_diag/batch_cash_drivers_results.csv", index=False)


if __name__ == "__main__":
    main()
