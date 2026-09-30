"""Split the wk3+ QB MAE gap vs FC into starter-identity rows vs known-starter skill rows (research; no FC data)."""
import os
import numpy as np, pandas as pd
R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
X = pd.read_parquet(os.path.join(R, "data/fc_history/derived/qb_depth/qb_recal_eval.parquet"))
X = X[X.fc.notna()]
mae = lambda g, c: (g[c] - g.act).abs().mean()
# projection_v2-style pool: played & (fc>=5 | ours>=5), with stubbed (a) and guarded (q/prod) engines
P = X[X.played & ((X.fc >= 5) | (X.q >= 5) | (X.a_final_projection >= 5))].copy()
P["kind"] = np.where(P.q >= 8, np.where(P.started, "known starter", "known starter, <15 att"), np.where(P.started, "UNKNOWN starter (q<8, started)", "backup, played"))
print("pool n", len(P), "\nMAE stubbed a / guarded q / prod / cand / FC and sum-abs-err share of gap (prod - FC)")
tot = (P["prod"] - P.act).abs().sum() - (P.fc - P.act).abs().sum()
for k, g in P.groupby("kind"):
    d = (g["prod"] - g.act).abs().sum() - (g.fc - g.act).abs().sum()
    print(f"{k:32s} n{len(g):5d} " + " ".join(f"{mae(g,c):.2f}" for c in ["a_final_projection", "q", "prod", "cand", "fc"]) + f"  gap pts/row-pool {d/len(P):+.3f}")
print(f"{'ALL':32s} n{len(P):5d} " + " ".join(f"{mae(P,c):.2f}" for c in ["a_final_projection", "q", "prod", "cand", "fc"]) + f"  gap {tot/len(P):+.3f}")
K = P[(P.q >= 8) & P.started]
print("\nKnown starters by season: prod / cand / FC   (gap prod-FC, cand-FC)")
for s, g in K.groupby("season"):
    print(s, len(g), f"{mae(g,'prod'):.3f} {mae(g,'cand'):.3f} {mae(g,'fc'):.3f}  {mae(g,'prod')-mae(g,'fc'):+.3f} {mae(g,'cand')-mae(g,'fc'):+.3f}")
for lab, g in [("wk3-6", K[K.week <= 6]), ("wk7+", K[K.week >= 7])]:
    print(lab, len(g), f"{mae(g,'prod'):.3f} {mae(g,'cand'):.3f} {mae(g,'fc'):.3f}")
print("wk3-6 by season prod/cand/FC:")
for s, g in K[K.week <= 6].groupby("season"):
    print(" ", s, len(g), f"{mae(g,'prod'):.3f} {mae(g,'cand'):.3f} {mae(g,'fc'):.3f}")
print("\nKnown starters by salary tier: MAE(bias) q | prod | cand | FC ; slope prod/cand/FC")
K = K.copy(); K["tier"] = pd.cut(K.sal_rank, [0, 3, 6, 10, 16, 99], labels=["QB1-3", "QB4-6", "QB7-10", "QB11-16", "QB17+"])
for t, g in list(K.groupby("tier", observed=True)) + [("ALL", K)]:
    print(t, len(g), " | ".join(f"{mae(g,c):.2f}({(g[c]-g.act).mean():+.1f})" for c in ["q", "prod", "cand", "fc"]),
          " slope " + "/".join(f"{np.polyfit(g[c], g.act, 1)[0]:.2f}" for c in ["prod", "cand", "fc"]))
print("\nKnown starters components (pass pts / rush pts): MAE ours q vs FC; hybrid swaps")
K["h_fcrush"] = K.q_pass + K.fc_rush; K["h_fcpass"] = K.fc_pass + K.q_rush
print(" ".join(f"{c} {mae(K,c):.3f}" for c in ["q", "h_fcrush", "h_fcpass", "fc"]))
for c in ["pass", "rush"]:
    print(c, "corr ours %.3f FC %.3f; bias ours %+.2f FC %+.2f" % (K["q_"+c].corr(K["act_"+c]), K["fc_"+c].corr(K["act_"+c]), (K["q_"+c]-K["act_"+c]).mean(), (K["fc_"+c]-K["act_"+c]).mean()))
print("corr with act: q %.3f, implied_total %.3f, FC %.3f, cand %.3f; pass att corr ours %.3f" % (K.q.corr(K.act), K.implied_total.corr(K.act), K.fc.corr(K.act), K.cand.corr(K.act), K.q_proj_pass_att.corr(K.attempts)))
K["rt"] = pd.cut(K.tr_rpts, [-9, 1.5, 3, 5, 99], labels=["pocket", "1.5-3", "3-5", "runner5+"])
for t, g in K.groupby("rt", observed=True):
    print(t, len(g), " | ".join(f"{mae(g,c):.2f}({(g[c]-g.act).mean():+.1f})" for c in ["prod", "cand", "fc"]), "rush bias q %+.2f" % (g.q_rush - g.act_rush).mean())
K["sp"] = pd.cut(K.spread, [-30, -3, 3, 30], labels=["fav>3", "pk", "dog>3"])
for t, g in K.groupby("sp", observed=True):
    print(t, len(g), " | ".join(f"{mae(g,c):.2f}({(g[c]-g.act).mean():+.1f})" for c in ["prod", "cand", "fc"]), "att bias %+.1f" % (g.q_proj_pass_att - g.attempts).mean())
print("\nLineup proxy: mean actual of top-1 / top-3 QB by projection per slate (known starters), by season: prod | cand | FC")
for s, g in K.groupby("season"):
    r = []
    for c in ["prod", "cand", "fc"]:
        r.append(f"{np.mean([h.nlargest(1, c).act.mean() for _, h in g.groupby('week')]):.2f}/{np.mean([h.nlargest(3, c).act.mean() for _, h in g.groupby('week')]):.2f}")
    print(s, " | ".join(r))
# value proxy: best pts per $1k among top-5 value QBs
