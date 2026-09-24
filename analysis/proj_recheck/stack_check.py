"""Stack effect (FIX vs FIX_NS) on real outcomes, with/without the moved-team reconcile blow-ups;
compare to projection_stack.py docstring claims (forecast R2 wk1 .331->.426, wk2 .374->.420)."""
import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
import accuracy as A
D = A.frame(); D = D[D.position.isin(["QB", "RB", "WR", "TE"])]
D = D.assign(p=D["sub"].map(A.PRI)).sort_values("p").drop_duplicates(["player_id", "week"])
D["blow"] = D.proj_pass_att > 50
r2 = lambda x, y: np.corrcoef(x, y)[0, 1] ** 2
rows = []
for excl in (False, True):
    E = D[~D.blow] if excl else D
    for (w, pos), g in list(E.groupby(["week", "position"])) + [((w, "ALL"), g) for w, g in E.groupby("week")]:
        rows.append(dict(excl_blowups=excl, week=w, pos=pos, n=len(g),
                         **{f"R2_{v}": r2(g[v], g.act) for v in A.V},
                         **{f"MAE_{v}": (g[v] - g.act).abs().mean() for v in A.V},
                         R2_salary=r2(g.salary, g.act)))
T = pd.DataFrame(rows).round(3); T.to_csv(Path(__file__).parent / "stack_r2.csv", index=False)
pd.set_option("display.width", 250); print(T.to_string(index=False))
# largest stack moves and whether they were right
M = D.assign(ad=D.stack_delta.abs()).nlargest(25, "ad")
M["closer"] = (M.FIX - M.act).abs() < (M.FIX_NS - M.act).abs()
print(M[["slate_id", "player_name", "position", "salary", "proj_pass_att", "OLD", "FIX_NS", "stack_delta", "FIX", "act", "closer"]].round(1).to_string(index=False))
big = D[D.stack_delta.abs() >= 2]
print("|delta|>=2: n", len(big), "stack closer share", round(((big.FIX - big.act).abs() < (big.FIX_NS - big.act).abs()).mean(), 3),
      "excl blowups", round(((lambda b: ((b.FIX - b.act).abs() < (b.FIX_NS - b.act).abs()).mean())(big[~big.blow])), 3), len(big[~big.blow]))
