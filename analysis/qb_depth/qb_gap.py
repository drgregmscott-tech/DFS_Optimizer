"""QB residual vs FC: decomposition (research; no FC data inside). Reads derived/qb_depth/qb_frame.parquet."""
import os, sys
import numpy as np, pandas as pd
from scipy.stats import spearmanr
R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
X = pd.read_parquet(os.path.join(R, "data/fc_history/derived/qb_depth/qb_frame.parquet"))
X = X[X.fc.notna() & (X.season <= 2025)]
X["q"] = X.q_final_projection
S = X[(X.week >= 3) & X.started].copy()  # pure skill: actual starters
def m(g, p, y="act"):
    e = g[p] - g[y]; b = np.polyfit(g[p], g[y], 1)[0]
    return f"mae {e.abs().mean():5.2f} bias {e.mean():+5.2f} slope {b:.2f}"
def gap(g, p="q", f="fc", y="act"):
    return (g[p]-g[y]).abs().mean() - (g[f]-g[y]).abs().mean()
print("== wk3+ actual starters (>=15 att), 2021-25 ==  n", len(S))
for s, g in S.groupby("season"):
    print(s, len(g), "ours", m(g, "q"), "| FC", m(g, "fc"), f"| gap {gap(g):+.2f}")
print("all", "ours", m(S, "q"), "| FC", m(S, "fc"), f"| gap {gap(S):+.2f}")
# bias-removed per season
S["q_db"] = S.q - (S.q - S.act).mean(); S["fc_db"] = S.fc - (S.fc - S.act).mean()
print("de-biased gap", round(gap(S, "q_db", "fc_db"), 3))
# linear-recal both (in-sample upper bound)
for p in ["q", "fc"]:
    b = np.polyfit(S[p], S.act, 1); S[p+"_lin"] = np.polyval(b, S[p])
print("in-sample linear-recal gap", round(gap(S, "q_lin", "fc_lin"), 3))
print("corr ours/FC with act: %.3f / %.3f; corr(ours,FC) %.3f" % (S.q.corr(S.act), S.fc.corr(S.act), S.q.corr(S.fc)))
b = np.linalg.lstsq(np.c_[np.ones(len(S)), S.q, S.fc], S.act, rcond=None)[0]; print("act ~ ours + fc coefs", b.round(3))
print("\n== tier (salary rank on slate) ==")
S["tier"] = pd.cut(S.sal_rank, [0, 3, 6, 10, 16, 99], labels=["QB1-3", "QB4-6", "QB7-10", "QB11-16", "QB17+"])
for t, g in S.groupby("tier", observed=True):
    print(t, len(g), "ours", m(g, "q"), "| FC", m(g, "fc"), f"| gap {gap(g):+.2f}")
print("\n== components: pass vs rush pts (hybrid swap) ==")
for c in ["pass", "rush"]:
    print(c, "ours mae %.2f bias %+.2f | FC mae %.2f bias %+.2f | corr ours %.3f FC %.3f" % (
        (S["q_"+c]-S["act_"+c]).abs().mean(), (S["q_"+c]-S["act_"+c]).mean(), (S["fc_"+c]-S["act_"+c]).abs().mean(),
        (S["fc_"+c]-S["act_"+c]).mean(), S["q_"+c].corr(S["act_"+c]), S["fc_"+c].corr(S["act_"+c])))
S["h_fcrush"] = S.q_pass + S.fc_rush; S["h_fcpass"] = S.fc_pass + S.q_rush
print("MAE ours %.3f | ours pass + FC rush %.3f | FC pass + ours rush %.3f | FC %.3f" % tuple((S[p]-S.act).abs().mean() for p in ["q", "h_fcrush", "h_fcpass", "fc"]))
for s, g in S.groupby("season"):
    print(" ", s, "ours %.2f  +FCrush %.2f  +FCpass %.2f  FC %.2f" % tuple((g[p]-g.act).abs().mean() for p in ["q", "h_fcrush", "h_fcpass", "fc"]))
print("rush att bias ours %+.2f FC %+.2f; rush yd bias ours %+.1f FC %+.1f; corr ryd ours %.3f FC %.3f" % (
    (S.q_proj_rush_att-S.carries).mean(), (S.fc_rush_att-S.carries).mean(), (S.q_proj_rush_yd-S.rushing_yards).mean(),
    (S.fc_rush_yd-S.rushing_yards).mean(), S.q_proj_rush_yd.corr(S.rushing_yards), S.fc_rush_yd.corr(S.rushing_yards)))
print("\n== rushing vs pocket (trailing rush pts/g) ==")
S["rtype"] = pd.cut(S.tr_rpts, [-9, 1.5, 3, 5, 99], labels=["pocket<1.5", "1.5-3", "3-5", "runner5+"])
for t, g in S.groupby("rtype", observed=True):
    print(t, len(g), "ours", m(g, "q"), "| FC", m(g, "fc"), f"| gap {gap(g):+.2f}", "rush bias ours %+.2f FC %+.2f" % ((g.q_rush-g.act_rush).mean(), (g.fc_rush-g.act_rush).mean()))
print("\n== game script: implied total / spread ==")
S["it"] = pd.qcut(S.implied_total, 4); S["sp"] = pd.cut(S.spread, [-30, -6, -2.5, 2.5, 6, 30])
for k in ["it", "sp"]:
    for t, g in S.groupby(k, observed=True):
        print(k, t, len(g), "ours", m(g, "q"), "| FC", m(g, "fc"), f"| gap {gap(g):+.2f}")
print("\n== pass component detail ==")
print("att bias %+.2f  yd bias %+.1f  td bias %+.3f  corr att %.3f yd %.3f td %.3f" % (
    (S.q_proj_pass_att-S.attempts).mean(), (S.q_proj_pass_yd-S.passing_yards).mean(), (S.q_proj_pass_td-S.passing_tds).mean(),
    S.q_proj_pass_att.corr(S.attempts), S.q_proj_pass_yd.corr(S.passing_yards), S.q_proj_pass_td.corr(S.passing_tds)))
# what explains FC - ours disagreement and who's right?
print("\n== residual regression: act - q ~ features (all seasons) ==")
S["d"] = S.fc - S.q
for cols in [["d"], ["salary"], ["implied_total"], ["spread"], ["tr_rpts"], ["tr_fp"], ["q_proj_pass_att"], ["games_played"],
             ["salary", "implied_total", "spread", "tr_rpts", "tr_fp", "q"]]:
    Z = S.dropna(subset=cols); A = np.c_[np.ones(len(Z)), Z[cols].values]
    b, res, *_ = np.linalg.lstsq(A, Z.act - Z.q, rcond=None)
    r = Z.act - Z.q - A @ b; se = np.sqrt(np.diag(np.linalg.inv(A.T @ A)) * r.var())
    print(cols, "coef", b[1:].round(3), "t", (b[1:] / se[1:]).round(1))
print("\n== within-slate spearman among starters ==")
for s, g in S.groupby("season"):
    print(s, "ours %.3f FC %.3f" % tuple(np.mean([spearmanr(h[p], h.act)[0] for _, h in g.groupby("week")]) for p in ["q", "fc"]))
