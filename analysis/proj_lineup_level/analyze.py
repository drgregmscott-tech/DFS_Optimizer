"""Summaries for lineup_eval.py output (research only; no FC data). Writes report.txt next to lineups.csv."""
import os
import numpy as np, pandas as pd

R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(R, "data/fc_history/derived/proj_lineup_level")
LOG = open(os.path.join(OUT, "report.txt"), "w")
def P(*a):
    s = " ".join(str(x) for x in a); print(s); LOG.write(s + "\n")
CASH = 0.543
rng = np.random.default_rng(11)
L = pd.read_csv(os.path.join(OUT, "lineups.csv"))
L["cash"] = L.score >= CASH * L.best
L["set"] = L.players.str.split("|").apply(frozenset)
top = L[L["rank"] == 0].set_index(["var", "slate"])
multi = L.groupby(["var", "slate"]).agg(bo5=("score", "max"), mo5=("score", "mean"), anycash=("cash", "max"), fcash=("cash", "mean"), n=("score", "size"))
slates = sorted(L.slate.unique())
assert (L.score <= L.best + 1e-6).all() and (L.salary <= 50000).all()
P(f"slates {len(slates)}; lineups {len(L)}; min top-K found {multi.n.min()}; all scores<=best, salary<=50000, roster asserts passed in solver")

def boot(d, B=2000):
    d = np.asarray(d, float); i = rng.integers(0, len(d), (B, len(d)))
    return np.percentile(d[i].mean(1), [2.5, 97.5])

def cmp(v, b, sl=None):
    sl = slates if sl is None else sl
    t, u = top.loc[v].loc[sl], top.loc[b].loc[sl]
    d = (t.score - u.score).values
    ch = np.array([len(x - y) for x, y in zip(t.set, u.set)])
    dc = (t.cash.astype(int) - u.cash.astype(int)).values
    mv, mb = multi.loc[v].loc[sl], multi.loc[b].loc[sl]
    d5 = (mv.bo5 - mb.bo5).values
    se = d.std(ddof=1) / np.sqrt(len(d)) if len(d) > 1 else np.nan
    lo, hi = boot(d); clo, chi = boot(dc); blo, bhi = boot(d5)
    c = ch > 0
    return dict(n=len(d), d=d.mean(), lo=lo, hi=hi, MDE=2.8 * se, cash=t.cash.mean(), cash_b=u.cash.mean(), dcash=dc.mean(), clo=clo, chi=chi,
                MDEcash=2.8 * dc.std(ddof=1) / np.sqrt(len(d)) if len(d) > 1 else np.nan,
                chg=c.mean(), nchg=ch.mean(), win_chg=(d[c] > 0).mean() if c.any() else np.nan, d_chg=d[c].mean() if c.any() else np.nan,
                bo5_d=d5.mean(), bo5_lo=blo, bo5_hi=bhi, any5=mv.anycash.mean(), any5_b=mb.anycash.mean(), f5=mv.fcash.mean(), f5_b=mb.fcash.mean())

def table(pairs, title):
    rows = [dict(var=v, base=b, **cmp(v, b)) for v, b in pairs]
    t = pd.DataFrame(rows).set_index(["var", "base"])
    P("\n== " + title); P(t.round(3).to_string()); return t

def bucket(v, b, title):
    wk = pd.Series(slates, index=slates) % 100
    bk = pd.cut(wk, [0, 2, 4, 8, 99], labels=["wk1-2", "wk3-4", "wk5-8", "wk9+"])
    out = []
    for name, sl in list(bk.groupby(bk, observed=True).groups.items()) + [(str(s), [x for x in slates if x // 100 == s]) for s in range(2021, 2027)]:
        r = cmp(v, b, list(sl)); out.append(dict(cut=name, n=r["n"], d=r["d"], lo=r["lo"], hi=r["hi"], dcash=r["dcash"], chg=r["chg"], bo5_d=r["bo5_d"]))
    P(f"\n-- {title}: {v} vs {b} by bucket/season"); P(pd.DataFrame(out).set_index("cut").round(2).to_string())

pd.set_option("display.width", 250)
P("\nLevels (rank-0 lineup): mean score / cash rate / best-of-5 / any-of-5 cash, hindsight best mean", round(top.loc["a0|none"].best.mean(), 1))
lv = pd.DataFrame({"score": top.score.groupby(level=0).mean(), "cash": top.cash.groupby(level=0).mean(),
                   "bo5": multi.bo5.groupby(level=0).mean(), "any5": multi.anycash.groupby(level=0).mean(), "frac5": multi.fcash.groupby(level=0).mean()})
P(lv.round(3).to_string())

# ---------------- 1. matchup ----------------
for f in ["none", "zDNP"]:
    table([(f"{v}|{f}", f"a0|{f}") for v in ["k4", "k16", "kq16"]], f"MATCHUP vs a0 (filter={f}); d=mean rank-0 lineup pts delta, CI=slate bootstrap")
for v in ["k4", "k16", "kq16"]:
    bucket(f"{v}|none", "a0|none", "MATCHUP")
# k16 vs kq16 identical?
same = (top.loc["k16|none"].players == top.loc["kq16|none"].players).mean()
P(f"k16 vs kq16 identical rank-0 lineups on {same:.2f} of slates")

# ---------------- 2. blend ----------------
for f in ["none", "zFC", "zDNP"]:
    pairs = [(f"a0|{f}", "a0|none")] if f != "none" else []
    pairs += [(f"w{w}b{b}|{f}", f"a0|{f}") for w in [0.2, 0.35, 0.5] for b in [0, 1]] + [(f"w1.0b0|{f}", f"a0|{f}")]
    table(pairs, f"FC BLEND vs ours (same filter={f}); first row = filter's own effect vs unfiltered ours")
for f in ["none", "zFC", "zDNP"]:
    bucket(f"w0.35b0|{f}", f"a0|{f}", f"BLEND w.35 filter={f}")
    bucket(f"w1.0b0|{f}", f"a0|{f}", f"FC alone filter={f}")

# LOSO choice of (w, bias) on training seasons, by rank-0 mean score
P("\n== LOSO: choose (w,b) on other seasons (max mean rank-0 score), apply to held-out season; delta vs ours same filter")
cands = ["a0"] + [f"w{w}b{b}" for w in [0.1, 0.2, 0.35, 0.5, 0.65, 0.8] for b in [0, 1]] + ["w1.0b0"]
for f in ["none", "zFC", "zDNP"]:
    d_all, c_all, b5_all, picks = [], [], [], []
    for s in range(2021, 2027):
        tr = [x for x in slates if x // 100 != s]; te = [x for x in slates if x // 100 == s]
        sc = {c: top.loc[f"{c}|{f}"].loc[tr].score.mean() for c in cands}
        pick = max(sc, key=sc.get); picks.append(f"{s}:{pick}")
        vv = top.loc[f"{pick}|{f}"].loc[te]; bb = top.loc[f"a0|{f}"].loc[te]
        d_all += list(vv.score.values - bb.score.values); c_all += list(vv.cash.astype(int).values - bb.cash.astype(int).values)
        b5_all += list(multi.loc[f"{pick}|{f}"].loc[te].bo5.values - multi.loc[f"a0|{f}"].loc[te].bo5.values)
    d_all = np.array(d_all); lo, hi = boot(d_all); clo, chi = boot(c_all); blo, bhi = boot(b5_all)
    P(f"  filter={f}: picks {picks}\n    held-out rank-0 d {d_all.mean():+.2f} [{lo:+.2f},{hi:+.2f}] n={len(d_all)}; dcash {np.mean(c_all):+.3f} [{clo:+.3f},{chi:+.3f}]; best-of-5 d {np.mean(b5_all):+.2f} [{blo:+.2f},{bhi:+.2f}]")

# needed n for observed effects (80% power, two-sided .05): n = (2.8*sd/d)^2
P("\n== n needed to detect the observed mean delta (80% power), rank-0 score")
for v, b in [("k4|none", "a0|none"), ("k16|none", "a0|none"), ("w0.35b0|none", "a0|none"), ("w0.35b0|zDNP", "a0|zDNP"), ("w0.35b0|zFC", "a0|zFC"), ("w1.0b0|zDNP", "a0|zDNP")]:
    d = top.loc[v].score.values - top.loc[b].score.values
    sd = d.std(ddof=1); m = d.mean()
    P(f"  {v} vs {b}: mean {m:+.2f}, sd {sd:.1f}, n needed {(2.8*sd/m)**2 if m else np.inf:.0f}; n for 3-pt effect {(2.8*sd/3)**2:.0f}")
LOG.close()
