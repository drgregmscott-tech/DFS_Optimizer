"""QB residual vs FC with shipped recal ON + QB1 guard ON (guarded rebuild q). Research only; no FC data inside."""
import json, os, numpy as np, pandas as pd
R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
X = pd.read_parquet(os.path.join(R, "data/fc_history/derived/qb_depth/qb_recal_eval.parquet"))
X = X[(X.season <= 2025) & (X.week >= 3)].copy()
# production-now: recal only on TOP projected QB per team with q>=8 (LOSO cand), blend off for QB wk>=3
top = X.groupby(["season", "week", "team"]).q.transform("max") == X.q
X["ship"] = np.where(top & (X.q >= 8), X.cand, X.q)
X["known"] = top & (X.q >= 8)
mae = lambda g, c: (g[c] - g.act).abs().mean()
def row(lab, g): print(f"{lab:32s} n={len(g):5d} ship {mae(g,'ship'):.2f} FC {mae(g,'fc'):.2f} gap(ship-FC) {mae(g,'ship')-mae(g,'fc'):+.2f}  bias ship {(g.ship-g.act).mean():+.1f} FC {(g.fc-g.act).mean():+.1f}")
U = X[X.fc.notna() & X.played & ((X.fc >= 5) | (X.ship >= 5))]
print("== Universe: played, FC or ours >=5, wk3+ 2021-25 =="); row("ALL", U)
n = len(U)
for lab, m in [("known starter (top,q>=8), started", U.known & U.started), ("surprise starter (not known)", ~U.known & U.started),
               ("known but did not start", U.known & ~U.started), ("other (backup, >=5)", ~U.known & ~U.started)]:
    g = U[m]; row(lab, g); print(f"   share of total gap: {((g.ship-g.act).abs().sum()-(g.fc-g.act).abs().sum())/n:+.3f}")
K = U[U.known & U.started].copy()
print("\n== Known starters by season =="); [row(str(s), g) for s, g in K.groupby("season")]
K["tier"] = pd.cut(K.sal_rank, [0, 3, 6, 10, 16, 99], labels=["QB1-3", "QB4-6", "QB7-10", "QB11-16", "QB17+"])
print("\n== by salary tier =="); [row(str(t), g) for t, g in K.groupby("tier", observed=True)]
K["runner"] = pd.cut(K.q_rush, [-1, 2.5, 5, 99], labels=["rush<2.5", "2.5-5", "5+"])
print("\n== by projected rush pts =="); [row(str(t), g) for t, g in K.groupby("runner", observed=True)]
K["fav"] = pd.cut(K.spread, [-99, -6.5, -3, 3, 6.5, 99], labels=["fav>6.5", "fav3-6.5", "pk", "dog3-6.5", "dog>6.5"])
print("\n== by spread =="); [row(str(t), g) for t, g in K.groupby("fav", observed=True)]
K["wk"] = pd.cut(K.week, [2, 6, 10, 14, 30], labels=["3-6", "7-10", "11-14", "15+"])
print("\n== by week =="); [row(str(t), g) for t, g in K.groupby("wk", observed=True)]
# biggest misses: where FC much closer than us
K["edge"] = (K.ship - K.act).abs() - (K.fc - K.act).abs()
print("\n== known starters, 25 rows where FC beat us most ==")
print(K.nlargest(25, "edge")[["season", "week", "player", "salary", "ship", "fc", "act", "q_rush", "fc_rush", "act_rush", "q_pass", "fc_pass", "act_pass"]].round(1).to_string(index=False))
print("\nwhy (pass vs rush component, known starters, MAE): pass ours %.2f FC %.2f | rush ours %.2f FC %.2f" % (
    (K.q_pass - K.act_pass).abs().mean(), (K.fc_pass - K.act_pass).abs().mean(), (K.q_rush - K.act_rush).abs().mean(), (K.fc_rush - K.act_rush).abs().mean()))
# surprise starters: what did we project and FC
S = U[~U.known & U.started]
print("\n== surprise starters: mean ship %.1f FC %.1f act %.1f, per slate %.2f; FC>=10 share %.2f; our q>=5 share %.2f" % (
    S.ship.mean(), S.fc.mean(), S.act.mean(), len(S) / U.groupby(['season', 'week']).ngroups, (S.fc >= 10).mean(), (S.q >= 5).mean()))
print("  of these, salary < 5500: %.2f; mean salary %d" % ((S.salary < 5500).mean(), S.salary.mean()))
# lineup relevance: per slate, QB top-1 / top-3 by proj and by value (proj/salary) among all QBs
print("\n== lineup proxy (all QBs on slate, wk3+) mean actual of picks ==")
A = X[X.fc.notna()]
for c in ["ship", "fc"]:
    t1 = A.groupby(["season", "week"]).apply(lambda h: h.nlargest(1, c).act.mean()).mean()
    t3 = A.groupby(["season", "week"]).apply(lambda h: h.nlargest(3, c).act.mean()).mean()
    A["v"] = A[c] / A.salary * 1000
    v3 = A.groupby(["season", "week"]).apply(lambda h: h.nlargest(3, "v").act.mean()).mean()
    zero = A.groupby(["season", "week"]).apply(lambda h: (h.nlargest(5, "v").act < 3).mean()).mean()
    print(f"{c:5s} top1 {t1:.2f} top3 {t3:.2f} value-top3 {v3:.2f} value-top5 dud(<3pts) rate {zero:.2f}")
