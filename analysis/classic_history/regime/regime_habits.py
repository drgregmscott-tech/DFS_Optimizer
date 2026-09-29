"""gmscott81 regime study, step 3: stated build habits vs actual entries, distance from FC-projection optimal,
2025 'same approach, bad year' test. Reads the regime_build.py caches (gitignored); writes aggregate CSVs only.

    python analysis/classic_history/regime/regime_habits.py > analysis/classic_history/regime/out/regime_habits_out.txt

Clustering unit = week (season+week): the same lineup was usually entered in SE/3MAX/20MAX the same week.
Distinct lineup = unique 9-player set within a week. Cash for a distinct lineup = cashed in ANY of its contests?
No: we use the mean cash over its entries (entries of one lineup in similar contests nearly always agree).
"""
import os, glob
import numpy as np, pandas as pd
from scipy.optimize import milp, LinearConstraint, Bounds

HERE = os.path.dirname(os.path.abspath(__file__))
CH = os.path.dirname(HERE); ROOT = os.path.dirname(os.path.dirname(CH))
DER = os.path.join(ROOT, "data", "fc_history", "derived", "classic_regime")
OUT = os.path.join(HERE, "out")
rng = np.random.default_rng(11)
POS = {0: "QB", 1: "RB", 2: "WR", 3: "TE", 4: "DST"}
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 50)

qa = pd.read_csv(os.path.join(CH, "out", "cl_qa.csv")); qa["base"] = qa.file.str[:-8]
qa = qa[qa.me_entries > 0].set_index("base")
rost = pd.read_parquet(os.path.join(DER, "me_rosters.parquet"))


def best_proj(pl):
    """Max FC-projection legal DK classic lineup from the contest's player pool (players with proj > 0)."""
    x = pl[(pl.proj > 0) & (pl.pos >= 0) & (pl.sal > 0)].reset_index()
    n = len(x); pos = x.pos.values
    c = -x.proj.values
    A = [x.sal.values, np.ones(n), (pos == 0), (pos == 1), (pos == 2), (pos == 3), (pos == 4), np.isin(pos, [1, 2, 3])]
    lo = [0, 9, 1, 2, 3, 1, 1, 7]; hi = [50000, 9, 1, 3, 4, 2, 1, 7]
    r = milp(c, constraints=LinearConstraint(np.vstack(A).astype(float), lo, hi), integrality=np.ones(n), bounds=Bounds(0, 1))
    return -r.fun if r.success else np.nan


rows, field = [], []
for f in sorted(glob.glob(os.path.join(DER, "entries", "*.parquet"))):
    b = os.path.basename(f)[:-8]; q = qa.loc[b]
    if q.rows_vs_entrants < 0.9 or q.rows_used < 1000:
        continue
    e = pd.read_parquet(f); pl = pd.read_parquet(os.path.join(DER, "players", b + ".parquet")).set_index("pid")
    ok = e.proj_ok & (e.proj_sum > 0)
    e["proj_pct"] = e.proj_sum.where(ok).rank(pct=True)
    e["cash"] = e.payout_c > 0
    bp = best_proj(pl)
    has_po = pl.proj_own.notna().sum() > 50
    # rank tables within contest
    qbs = pl[pl.pos == 0]; dsts = pl[pl.pos == 4]
    qb_proj_rank = qbs.proj.rank(ascending=False, method="min")
    qb_sal_rank = qbs.sal.rank(ascending=False, method="min")
    qb_po_rank = qbs.proj_own.rank(ascending=False, method="min") if has_po else None
    dst_proj_rank = dsts.proj.rank(ascending=False, method="min")
    dst_sal_rank_cheap = dsts.sal.rank(ascending=True, method="min")
    myr = rost[rost.file == b]
    me = e[e.is_me]
    # field benchmark: cash rate of field lineups within +-0.03 proj pct of each of my entries
    fe = e[ok & ~e.is_me]
    fp = fe.proj_pct.values; fc = fe.cash.values
    for k, (idx, r) in enumerate(me.iterrows()):
        pids = myr[myr.entry == k].sort_values("slot").pid.tolist()
        X = pl.loc[pids]
        qb = X.iloc[0]; flex = X.iloc[7]; dst = X.iloc[8]
        qb_id = pids[0]; dst_id = pids[8]
        mates = X.iloc[1:8]
        wr_mates = int(((mates.pos == 2) & (mates.team == qb.team)).sum())
        te_mates = int(((mates.pos == 3) & (mates.team == qb.team)).sum())
        m = np.abs(fp - r.proj_pct) <= 0.03 if not np.isnan(r.proj_pct) else np.zeros(len(fp), bool)
        rows.append({
            "file": b, "season": int(q.season), "week": int(q.week), "ctype": q.ctype, "me_n": int(e.is_me.sum()),
            "key": f"{int(q.season)}-{int(q.week)}|" + ",".join(sorted(pids)),
            "cash": bool(r.cash), "base_cash": float(e.cash.mean()), "proj_pct": r.proj_pct,
            "proj_gap": bp - r.proj_sum if r.proj_ok else np.nan, "proj_gap_pct": (bp - r.proj_sum) / bp if r.proj_ok else np.nan,
            "field_cash_matched": fc[m].mean() if m.sum() >= 30 else np.nan,
            "qb_proj_rank": int(qb_proj_rank.get(qb_id, 99)) if qb.proj > 0 else np.nan,
            "qb_sal_rank": int(qb_sal_rank[qb_id]), "qb_own_rank": int(r.qb_own_rank),
            "qb_po_rank": int(qb_po_rank[qb_id]) if (has_po and pd.notna(qb.proj_own)) else np.nan,
            "stack_rec": int(r.stack_rec), "wr_mates": wr_mates, "te_mates": te_mates, "bb": int(r.bb),
            "flex_pos": POS.get(int(flex.pos), "?"), "dst_sal": float(dst.sal),
            "dst_proj_rank": int(dst_proj_rank[dst_id]) if dst.proj > 0 else np.nan,
            "dst_cheap_rank": int(dst_sal_rank_cheap[dst_id]), "n_dst": len(dsts), "n_qb": len(qbs),
        })
D = pd.DataFrame(rows)
D["era"] = np.where(D.season <= 2024, "2022-24", D.season.astype(str))
D["wk"] = D.season.astype(str) + "-" + D.week.astype(str)
D["mme"] = D.me_n >= 20
D["stack_type"] = np.select([D.stack_rec == 0, (D.stack_rec == 1) & (D.bb == 0), (D.stack_rec == 1) & (D.bb >= 1),
                             (D.stack_rec >= 2) & (D.bb == 0)], ["naked", "QB+1", "QB+1+BB", "QB+2"], "QB+2+BB")
D["qb_wr_stack"] = D.wr_mates >= 1
D["dst_band"] = pd.cut(D.dst_sal, [0, 2799, 3100, 3500, 9999], labels=["<2.8k", "2.8-3.1k", "3.2-3.5k", "3.6k+"])
D["excess_matched"] = D.cash - D.field_cash_matched
print("entries", len(D), "contests", D.file.nunique(), "weeks", D.wk.nunique())

# distinct lineups (exclude 2026 MME pools from habit profiles; they're a randomized optimizer pool)
L = D.groupby("key").agg(era=("era", "first"), wk=("wk", "first"), mme=("mme", "max"), n_entries=("cash", "size"),
                         cash=("cash", "mean"), base=("base_cash", "mean"), fmatch=("field_cash_matched", "mean"),
                         **{c: (c, "first") for c in ["proj_pct", "proj_gap", "proj_gap_pct", "qb_proj_rank", "qb_sal_rank",
                                                       "qb_own_rank", "qb_po_rank", "stack_rec", "wr_mates", "bb", "stack_type",
                                                       "qb_wr_stack", "flex_pos", "dst_sal", "dst_band", "dst_proj_rank",
                                                       "dst_cheap_rank"]}).reset_index()
L["proj_pct"] = D.groupby("key").proj_pct.mean().values
L["excess_m"] = L.cash - L.fmatch
print("distinct lineups by era:", L.groupby(["era", "mme"]).size().to_dict())


def wboot(df, fn, B=3000):
    g = [x for _, x in df.groupby("wk")]
    v = [fn(pd.concat([g[i] for i in rng.integers(0, len(g), len(g))])) for _ in range(B)]
    return np.nanpercentile(v, 5), np.nanpercentile(v, 95)


# ---- Task 1: habit profile per era (distinct lineups, MME pools excluded)
H = L[~L.mme]
hab = []
for era, x in list(H.groupby("era")) + [("2025-26 noMME", H[H.era != "2022-24"])]:
    hab.append({"era": era, "lineups": len(x), "weeks": x.wk.nunique(),
                "qb_proj_rank1": (x.qb_proj_rank == 1).mean(), "qb_proj_top3": (x.qb_proj_rank <= 3).mean(),
                "qb_proj_rank_med": x.qb_proj_rank.median(), "qb_sal_top3": (x.qb_sal_rank <= 3).mean(),
                "qb_sal_rank_med": x.qb_sal_rank.median(), "qb_own_rank1": (x.qb_own_rank == 1).mean(),
                "qb_own_top3": (x.qb_own_rank <= 3).mean(), "qb_own_rank_med": x.qb_own_rank.median(),
                "qb_projown_rank1": (x.qb_po_rank == 1).sum() / max(x.qb_po_rank.notna().sum(), 1) if x.qb_po_rank.notna().any() else np.nan,
                "qb_wr_stack": x.qb_wr_stack.mean(), "naked": (x.stack_type == "naked").mean(),
                "QB+1": (x.stack_type == "QB+1").mean(), "QB+1+BB": (x.stack_type == "QB+1+BB").mean(),
                "QB+2": (x.stack_type == "QB+2").mean(), "QB+2+BB": (x.stack_type == "QB+2+BB").mean(),
                "any_bb": (x.bb >= 1).mean(),
                "flex_RB": (x.flex_pos == "RB").mean(), "flex_WR": (x.flex_pos == "WR").mean(), "flex_TE": (x.flex_pos == "TE").mean(),
                "dst_sal_med": x.dst_sal.median(), "dst_lt2.8k": (x.dst_band == "<2.8k").mean(),
                "dst_2.8-3.1k": (x.dst_band == "2.8-3.1k").mean(), "dst_3.2k+": (x.dst_sal >= 3200).mean(),
                "dst_min_price": (x.dst_cheap_rank == 1).mean(), "dst_proj_rank_med": x.dst_proj_rank.median(),
                "proj_pct_mean": x.proj_pct.mean(), "proj_pct_ge95": (x.proj_pct >= 0.95).mean(),
                "proj_gap_pct_med": x.proj_gap_pct.median(), "proj_gap_med": x.proj_gap.median(),
                "cash": x.cash.mean(), "base": x.base.mean(), "field_matched": x.fmatch.mean()})
HB = pd.DataFrame(hab).round(3); HB.to_csv(os.path.join(OUT, "regime_habits_profile.csv"), index=False)
print(HB.T.to_string())

# ---- Task 2: projection distance and what predicts cashing (2022-25 real entries; distinct lineups)
R = L[L.era.isin(["2022-24", "2025"])].copy()
print("\n2022-25 distinct lineups", len(R), "weeks", R.wk.nunique(), "proj_pct known", R.proj_pct.notna().sum())
for era, x in R.groupby("era"):
    lo, hi = wboot(x, lambda d: d.excess_m.mean())
    print(f"{era}: cash {x.cash.mean():.3f}  field matched on proj pct {x.fmatch.mean():.3f}  excess vs matched {x.excess_m.mean():+.3f} [{lo:+.3f},{hi:+.3f}]"
          f"  proj_pct mean {x.proj_pct.mean():.3f}  gap% med {x.proj_gap_pct.median():.3f}")
feat = []
R["top_proj"] = R.proj_pct >= R.proj_pct.median()
R["qbproj1"] = R.qb_proj_rank == 1; R["qbown1"] = R.qb_own_rank == 1; R["qbsal_top3"] = R.qb_sal_rank <= 3
R["flexRB"] = R.flex_pos == "RB"; R["dst_sweet"] = R.dst_band == "2.8-3.1k"; R["qb2"] = R.stack_rec >= 2; R["bb1"] = R.bb >= 1
for sl, x in [("2022-24", R[R.era == "2022-24"]), ("2022-25", R)]:
    for fcol in ["top_proj", "qbproj1", "qbown1", "qbsal_top3", "flexRB", "dst_sweet", "qb2", "bb1", "qb_wr_stack"]:
        a = x[x[fcol] == True]; b_ = x[x[fcol] == False]
        if len(a) < 3 or len(b_) < 3:
            continue
        fn = lambda d: d[d[fcol] == True].excess_m.mean() - d[d[fcol] == False].excess_m.mean()
        lo, hi = wboot(x, fn)
        feat.append({"slice": sl, "feature": fcol, "n_yes": len(a), "n_no": len(b_), "cash_yes": a.cash.mean(), "cash_no": b_.cash.mean(),
                     "exm_yes": a.excess_m.mean(), "exm_no": b_.excess_m.mean(), "diff_exm": fn(x), "lo90": lo, "hi90": hi})
FT = pd.DataFrame(feat).round(3); FT.to_csv(os.path.join(OUT, "regime_habits_features.csv"), index=False); print(FT.to_string(index=False))
print("corr(proj_pct, cash) 2022-24 %.3f  2022-25 %.3f" % (R[R.era == "2022-24"].proj_pct.corr(R[R.era == "2022-24"].cash), R.proj_pct.corr(R.cash)))

# ---- Task 3: 2025 vs 2022-24; how unlikely is the 2025 cash rate under the 2022-24 process?
E1 = L[L.era == "2022-24"]; E25 = L[L.era == "2025"]
k25, n25, w25 = E25.cash.sum(), len(E25), E25.wk.nunique()
p1 = E1.cash.mean()
from scipy.stats import binom
print(f"\n2025: {n25} distinct lineups, {w25} weeks, cash-sum {k25:.1f} ({k25/n25:.3f}); 2022-24 distinct-lineup rate {p1:.3f}")
print("binomial P(<= 2025 cashes | p=2022-24 rate) = %.4f" % binom.cdf(np.floor(k25), n25, p1))
# week-clustered: draw w25 weeks from 2022-24 weeks (with replacement), per week one lineup (random), cash rate
wk1 = [x.cash.values for _, x in E1.groupby("wk")]
sims = np.array([np.mean([rng.choice(wk1[i]) for i in rng.integers(0, len(wk1), w25)]) for _ in range(20000)])
print("week-resampled P(rate <= %.3f) = %.4f" % (k25 / n25, np.mean(sims <= k25 / n25 + 1e-9)))
# also: use the excess-vs-matched metric (removes lineup projection difference)
ex1 = [x.excess_m.dropna().values for _, x in E1.groupby("wk") if x.excess_m.notna().any()]
sims2 = np.array([np.mean([rng.choice(ex1[i]) for i in rng.integers(0, len(ex1), w25)]) for _ in range(20000)])
print("week-resampled P(excess_vs_matched <= 2025's %.3f) = %.4f" % (E25.excess_m.mean(), np.mean(sims2 <= E25.excess_m.mean())))
# Posterior-ish: if 2022-24 true rate is uncertain, mix: p ~ Beta from clustered effective n (~weeks)
ne = E1.wk.nunique(); a_, b_ = p1 * ne + 1, (1 - p1) * ne + 1
ps = rng.beta(a_, b_, 20000); print("P(<=k25 | p ~ Beta(eff n=weeks)) = %.4f" % np.mean(rng.binomial(n25, ps) <= np.floor(k25)))
# per-feature differences 2025 vs 2022-24
cmpr = []
for c in ["proj_pct", "proj_gap_pct", "qb_proj_rank1", "qb_own_rank1", "qb_sal_top3", "qb2", "qb_wr_stack", "bb1", "flexRB", "flexTE",
          "dst_sweet", "dst_sal", "fmatch", "cash", "excess_m"]:
    g = lambda d, c=c: (d.assign(qb_proj_rank1=d.qb_proj_rank == 1, qb_own_rank1=d.qb_own_rank == 1, qb_sal_top3=d.qb_sal_rank <= 3,
                                 qb2=d.stack_rec >= 2, bb1=d.bb >= 1, flexRB=d.flex_pos == "RB", flexTE=d.flex_pos == "TE",
                                 dst_sweet=d.dst_band == "2.8-3.1k")[c].astype(float).mean())
    va = [g(pd.concat([x for x in [E1[E1.wk == w] for w in rng.choice(E1.wk.unique(), E1.wk.nunique())]])) -
          g(pd.concat([E25[E25.wk == w] for w in rng.choice(E25.wk.unique(), w25)])) for _ in range(1500)]
    cmpr.append({"feature": c, "2022-24": g(E1), "2025": g(E25), "diff": g(E1) - g(E25), "lo90": np.nanpercentile(va, 5), "hi90": np.nanpercentile(va, 95)})
CM = pd.DataFrame(cmpr).round(3); CM.to_csv(os.path.join(OUT, "regime_habits_2025_vs_E1.csv"), index=False); print(CM.to_string(index=False))
print("\nby season (distinct lineups):")
print(L[~L.mme].groupby("era").agg(n=("cash", "size"), cash=("cash", "mean"), fmatch=("fmatch", "mean"), proj_pct=("proj_pct", "mean"),
                                   qbown1=("qb_own_rank", lambda s: (s == 1).mean())).round(3).to_string())
S = L.copy(); S["season"] = S.wk.str[:4]
print(S[~S.mme].groupby("season").agg(n=("cash", "size"), cash=("cash", "mean"), fmatch=("fmatch", "mean"), proj_pct=("proj_pct", "mean"),
      gap=("proj_gap_pct", "median"), qbproj1=("qb_proj_rank", lambda s: (s == 1).mean()), qbown1=("qb_own_rank", lambda s: (s == 1).mean()),
      flexTE=("flex_pos", lambda s: (s == "TE").mean()), flexRB=("flex_pos", lambda s: (s == "RB").mean()), dst=("dst_sal", "median")).round(3).to_string())
