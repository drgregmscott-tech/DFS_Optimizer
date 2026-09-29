"""gmscott81 regime-change study, step 2: analysis on the regime_build.py caches.

Writes aggregate CSVs to analysis/classic_history/regime/out/ (no entry- or player-level FC data) and prints a report
(saved as out/regime_analysis_out.txt by redirect).

Eras: E1 = 2022-24, E2 = 2025-26; also 2025 vs 2026 split, because 2026 is the first season built with this repo's
optimizer (git starts 2026-07-21; how 2022-25 lineups were built is not documented anywhere in the repo or memory).
Cash = payout > 0. Contest exclusions match the lineup study (truncated field or < 1,000 entries).
Every CI bootstraps over contests (resample contest files), 90% intervals.
"""
import os, glob
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CH = os.path.dirname(HERE); ROOT = os.path.dirname(os.path.dirname(CH))
DER = os.path.join(ROOT, "data", "fc_history", "derived", "classic_regime")
OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
rng = np.random.default_rng(7)
POS = {0: "QB", 1: "RB", 2: "WR", 3: "TE", 4: "DST"}
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)

qa = pd.read_csv(os.path.join(CH, "out", "cl_qa.csv"))
qa["base"] = qa.file.str[:-8]
qa = qa[qa.me_entries > 0].set_index("base")
rost = pd.read_parquet(os.path.join(DER, "me_rosters.parquet"))

rows, prow, frow = [], [], []
for f in sorted(glob.glob(os.path.join(DER, "entries", "*.parquet"))):
    b = os.path.basename(f)[:-8]; q = qa.loc[b]
    if q.rows_vs_entrants < 0.9 or q.rows_used < 1000:
        continue
    e = pd.read_parquet(f); pl = pd.read_parquet(os.path.join(DER, "players", b + ".parquet")).set_index("pid")
    cash = e.payout_c > 0
    e["own_pct"] = e.own_sum.rank(pct=True)
    e["pts_pct"] = e.points.rank(pct=True)
    q_ok = e.proj_ok & (e.proj_sum > 0)
    e["proj_pct"] = e.proj_sum.where(q_ok).rank(pct=True)
    qual = q_ok & (e.sal_used >= 49500) & (e.proj_pct >= 0.6)
    e["own_pct_q"] = e.own_sum.where(qual).rank(pct=True)
    fq = e[qual]
    qb = pd.cut(fq.own_pct_q, [0, .2, .4, .6, .8, 1.0])
    qcash = (fq.payout_c > 0).groupby(qb, observed=False).mean().values
    # field reference: cash by all-lineup own percentile band (same bands used for my entries)
    ob3 = pd.cut(e.own_pct, [0, .5, .8, 1.0], labels=["<50", "50-80", ">=80"])
    for lvl, y in (e.payout_c > 0).groupby(ob3, observed=True):
        frow.append({"file": b, "season": int(q.season), "own_band": lvl, "field_cash": y.mean()})
    me = e[e.is_me]
    myr = rost[rost.file == b]
    for k, (idx, r) in enumerate(me.iterrows()):
        for s, p in enumerate(myr[myr.entry == k].sort_values("slot").pid.tolist()):
            x = pl.loc[p]
            prow.append({"file": b, "entry": k, "slot": s, "pos": POS.get(int(x.pos), "?"), "own": x.own,
                         "own_rank_pos": int((pl[pl.pos == x.pos].own > x.own).sum()) + 1, "sal": x.sal})
        oq = r.own_pct_q
        rows.append({"file": b, "season": int(q.season), "week": int(q.week), "ctype": q.ctype,
                     "entrants": int(q.rows_used), "base_cash": float(cash.mean()), "me_n": int(e.is_me.sum()), "entry": k,
                     "cash": bool(r.payout_c > 0), "roi_x": r.payout_c / max(q.cost_c, 1e-9),
                     "own_pct": r.own_pct, "pts_pct": r.pts_pct, "proj_pct": r.proj_pct, "qual": bool(qual[idx]),
                     "own_pct_q": oq, "qb_own_rank": int(r.qb_own_rank), "n_top5own": int(r.n_top5own),
                     "n_lt2own": int(r.n_lt2own), "stack_rec": int(r.stack_rec), "punts": int(r.punts),
                     "studs": int(r.studs), "sal_left": 50000 - r.sal_used, "dupes": int(r.dupes),
                     "qcash_ownbin": np.nan if np.isnan(oq) else qcash[min(4, int(oq * 5 - 1e-9))],
                     "qcash_top_bin": qcash[4], "qcash_all": float((fq.payout_c > 0).mean())})
D = pd.DataFrame(rows); P = pd.DataFrame(prow); F = pd.DataFrame(frow)
D["era"] = np.where(D.season <= 2024, "E1_2022-24", "E2_2025-26")
D["era3"] = np.where(D.season <= 2024, "2022-24", D.season.astype(str))
D["mme"] = D.me_n >= 20
P = P.merge(D[["file", "entry", "era", "era3", "mme"]], on=["file", "entry"])
print("contests", D.file.nunique(), "entries", len(D))


def cw(df, col):  # contest-weighted mean: each contest counts once (20 MME entries in one contest = one vote)
    return df.groupby("file")[col].mean().mean()


def boot(df, fn, B=2000):
    g = [x for _, x in df.groupby("file")]
    v = [fn(pd.concat([g[i] for i in rng.integers(0, len(g), len(g))])) for _ in range(B)]
    return fn(df), np.nanpercentile(v, 5), np.nanpercentile(v, 95)


out = []
def summ(label, df):
    if len(df) == 0:
        return
    r = {"slice": label, "entries": len(df), "contests": df.file.nunique(), "cash_raw": round(df.cash.mean(), 3)}
    for name, fn in [("cash", lambda x: cw(x, "cash")), ("base", lambda x: cw(x, "base_cash")),
                     ("excess", lambda x: cw(x.assign(ex=x.cash - x.base_cash), "ex")),
                     ("own_pct", lambda x: cw(x, "own_pct")), ("pts_pct", lambda x: cw(x, "pts_pct")),
                     ("roi", lambda x: cw(x, "roi_x"))]:
        p, lo, hi = boot(df, fn)
        r[name] = round(p, 3); r[name + "_lo"] = round(lo, 3); r[name + "_hi"] = round(hi, 3)
    r.update({"qual_share": round(df.qual.mean(), 3), "qb_own_rank1": round((df.qb_own_rank == 1).mean(), 3),
              "qb_own_rank_med": df.qb_own_rank.median(), "n_top5own": round(df.n_top5own.mean(), 2),
              "n_lt2own": round(df.n_lt2own.mean(), 2), "qb_plus2": round((df.stack_rec >= 2).mean(), 3),
              "punts": round(df.punts.mean(), 2), "studs": round(df.studs.mean(), 2),
              "sal_left_med": df.sal_left.median(), "duped": round((df.dupes > 1).mean(), 3)})
    out.append(r)


summ("all", D)
for k, x in D.groupby("era"): summ(k, x)
for k, x in D.groupby("era3"): summ(k, x)
summ("E2 excl 2026 MME", D[(D.era == "E2_2025-26") & ~D.mme])
summ("2026 MME only", D[D.mme])
summ("2026 SE only", D[(D.season == 2026) & ~D.mme])
for (k, ct), x in D.groupby(["era", "ctype"]): summ(f"{k} {ct}", x)
summ("E1 excl DU", D[(D.era == "E1_2022-24") & (D.ctype != "DU")])
for k, x in D.groupby("season"): summ(f"season {k}", x)
S = pd.DataFrame(out); S.to_csv(os.path.join(OUT, "regime_summary.csv"), index=False)
print(S[["slice", "entries", "contests", "cash_raw", "cash", "cash_lo", "cash_hi", "base", "excess", "excess_lo", "excess_hi",
         "own_pct", "own_pct_lo", "own_pct_hi", "pts_pct", "pts_pct_lo", "pts_pct_hi", "roi", "roi_lo", "roi_hi"]].to_string(index=False))
print(S[["slice", "qual_share", "qb_own_rank1", "qb_own_rank_med", "n_top5own", "n_lt2own", "qb_plus2", "punts", "studs",
         "sal_left_med", "duped"]].to_string(index=False))


def diff(a, b, fn, B=4000):
    ga = [x for _, x in a.groupby("file")]; gb = [x for _, x in b.groupby("file")]
    v = np.array([fn(pd.concat([ga[i] for i in rng.integers(0, len(ga), len(ga))])) -
                  fn(pd.concat([gb[i] for i in rng.integers(0, len(gb), len(gb))])) for _ in range(B)])
    return fn(a) - fn(b), np.percentile(v, 5), np.percentile(v, 95), np.mean(v <= 0)


E1 = D[D.era == "E1_2022-24"]; E2 = D[D.era == "E2_2025-26"]
dr = []
for lab, a, b in [("E1 - E2", E1, E2), ("E1 - E2(no MME)", E1, E2[~E2.mme]), ("E1 - 2025", E1, D[D.season == 2025]),
                  ("E1(excl DU) - E2(no MME)", E1[E1.ctype != "DU"], E2[~E2.mme])]:
    for m, fn in [("excess_cash", lambda x: cw(x.assign(ex=x.cash - x.base_cash), "ex")),
                  ("own_pct", lambda x: cw(x, "own_pct")), ("pts_pct", lambda x: cw(x, "pts_pct"))]:
        p, lo, hi, pn = diff(a, b, fn)
        dr.append({"cmp": lab, "metric": m, "diff": p, "lo90": lo, "hi90": hi, "boot_share_le0": pn})
DR = pd.DataFrame(dr).round(3); DR.to_csv(os.path.join(OUT, "regime_era_diff.csv"), index=False); print(DR.to_string(index=False))

cs = D.groupby(["era3", "ctype"]).agg(entries=("cash", "size"), contests=("file", "nunique"), cash=("cash", "mean"),
                                       base=("base_cash", "mean"), own_pct=("own_pct", "mean"), pts_pct=("pts_pct", "mean")).round(3)
cs.to_csv(os.path.join(OUT, "regime_by_season_type.csv")); print(cs.to_string())

# Within-era: my cash rate by own-percentile band vs the field's cash rate in the same band of the same contests.
F = F.merge(D[["file", "era3"]].drop_duplicates(), on="file")
wr = []
for era, x in D.groupby("era3"):
    t = pd.cut(x.own_pct, [0, .5, .8, 1.0], labels=["<50", "50-80", ">=80"])
    for lvl, y in x.groupby(t, observed=True):
        fr = F[(F.file.isin(y.file)) & (F.own_band == lvl)].field_cash.mean()
        wr.append({"era": era, "own_band": lvl, "entries": len(y), "contests": y.file.nunique(), "my_cash": round(y.cash.mean(), 3),
                   "field_cash_same_band_same_contests": round(fr, 3), "my_pts_pct": round(y.pts_pct.mean(), 3)})
W = pd.DataFrame(wr); W.to_csv(os.path.join(OUT, "regime_within_era.csv"), index=False); print(W.to_string(index=False))
FB = F.groupby(["era3", "own_band"], observed=True).field_cash.mean().round(3); print("field cash by own band (all lineups, my contests)"); print(FB.to_string())
for era, x in D.groupby("era"):
    print(era, "n", len(x), "corr(own_pct, cash)=%.3f" % x.own_pct.corr(x.cash.astype(float)),
          "corr(own_pct, pts_pct)=%.3f" % x.own_pct.corr(x.pts_pct))

# Counterfactual (modest): among quality-shaped entries, field cash rate at my own quintile vs at the top own quintile.
cf = D[D.qual].groupby("era3").agg(n=("cash", "size"), contests=("file", "nunique"), my_cash=("cash", "mean"),
                                    field_at_my_own_quintile=("qcash_ownbin", "mean"), field_at_top_own_quintile=("qcash_top_bin", "mean"),
                                    field_quality_all=("qcash_all", "mean"), my_own_pct_q=("own_pct_q", "mean")).round(3)
cf.to_csv(os.path.join(OUT, "regime_counterfactual.csv")); print(cf.to_string())

P["chalk20"] = P.own >= 20; P["low5"] = P.own < 5
agg = dict(slots=("own", "size"), own_mean=("own", "mean"), own_med=("own", "median"), chalk20=("chalk20", "mean"),
           low5=("low5", "mean"), own_rank_med=("own_rank_pos", "median"),
           top1_at_pos=("own_rank_pos", lambda s: (s == 1).mean()), sal_mean=("sal", "mean"))
PP = P.groupby(["era3", "pos"]).agg(**agg).round(3); PP.to_csv(os.path.join(OUT, "regime_player_exposure.csv")); print(PP.to_string())
PE = P[~P.mme].groupby(["era", "pos"]).agg(**agg).round(3); PE.to_csv(os.path.join(OUT, "regime_player_exposure_noMME.csv")); print(PE.to_string())
