"""SKILL-only LOWO shrunk refit on 2026 rebuilds (QB excluded). Uses run.py's frame."""
import sys, io, contextlib
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import spearmanr
sys.path.insert(0, str(Path(__file__).resolve().parent))
with contextlib.redirect_stdout(io.StringIO()):
    import run
A = run.A[run.A.pg == "SKILL"].copy()
for lam in [100, 300]:
    print(f"lam={lam}")
    for hw in [1, 2, 3]:
        tr, te = A[A.wk != hw], A[A.wk == hw].copy()
        X = np.column_stack([np.ones(len(tr)), tr.S - tr.E]); y = (tr.act - tr.E).values
        a, w = np.linalg.solve(X.T @ X + lam * np.eye(2), X.T @ y)
        te["F"] = (te.E + a + w * (te.S - te.E)).clip(lower=0)
        r = lambda c: (te[c] - te.act).abs().mean()
        sp = lambda c: np.mean([spearmanr(g[c], g.act)[0] for _, g in te.groupby("slate")])
        top = lambda c: te.nlargest(40, c).act.mean()
        tiers = " ".join(f"{t}:{(g.E-g.act).abs().mean():.2f}->{(g.F-g.act).abs().mean():.2f}" for t, g in te.groupby("tier", observed=True))
        pr = te[te.props]; pt = f" props-matched {len(pr)}: {(pr.E-pr.act).abs().mean():.3f}->{(pr.F-pr.act).abs().mean():.3f}" if len(pr) else ""
        print(f"  hold wk{hw} a={a:+.2f} w={w:+.3f} MAE {r('E'):.3f}->{r('F'):.3f} bias {(te.E-te.act).mean():+.2f}->{(te.F-te.act).mean():+.2f} "
              f"spearman {sp('E'):.3f}->{sp('F'):.3f} top40act {top('E'):.2f}->{top('F'):.2f} | {tiers}{pt}")
# final fit on all 3 weeks, lam=300
X = np.column_stack([np.ones(len(A)), A.S - A.E]); y = (A.act - A.E).values
print("all-3-week fit lam=300 (a,w):", np.linalg.solve(X.T @ X + 300 * np.eye(2), X.T @ y).round(3))
