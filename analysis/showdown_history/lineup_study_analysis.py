"""Real-field Showdown construction analysis on FC Lineup Study contests (2022-2026).

Reads the per-entry cache from lineup_study_build.py and writes aggregate-only tables to
data/fc_history/derived/showdown/ls_*.csv plus a text dump ls_analysis_out.txt.

Outcome metrics, all computed within each contest, then averaged with EQUAL weight per contest:
  cash lift  = cash rate of entries with the feature - contest cash rate          (pct points)
  ret        = mean payout / contest mean payout (1.00 = average field entry; rake-free, cost-free)
  ret_cap    = same with each payout capped at the contest's 99.9th-pct payout (tames 1st-place outliers)
  top1 lift  = top-1% rate - 1%                                                     (pct points)
CIs: 90% bootstrap over contests (2000 draws). A level must have >= 30 entries in a contest to count there.
"""
import os, sys
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = os.path.join(ROOT, "data", "fc_history", "lineup_study", "_sd_entries_cache.parquet")
OUT = os.path.join(ROOT, "data", "fc_history", "derived", "showdown")
RS = np.random.RandomState(7)
MIN_N = 30
LINES = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s); LINES.append(s)


def prep(df):
    df = df.copy()
    g = df.groupby("contest")
    df["cashed"] = (df["payout_c"] > 0).astype(float)
    df["n"] = g["rank"].transform("size")
    df["top1"] = (df["rank"] <= np.maximum(1, np.floor(0.01 * df["n"]))).astype(float)
    df["top10"] = (df["rank"] <= np.floor(0.10 * df["n"])).astype(float)
    mean_pay = g["payout_c"].transform("mean")
    df["ret"] = df["payout_c"] / mean_pay
    cap = g["payout_c"].transform(lambda s: s.quantile(0.999))
    pc = np.minimum(df["payout_c"], cap)
    df["ret_cap"] = pc / pc.groupby(df["contest"]).transform("mean")
    df["pctile"] = 100.0 * df["rank"] / df["n"]
    # within-contest quintiles of summed realized ownership, and of ownership residual given FC projection
    df["own_q"] = g["own_sum"].transform(lambda s: pd.qcut(s.rank(method="first"), 5, labels=False) + 1)
    df["proj_q"] = np.nan
    df["own_resid_q"] = np.nan
    for cid, d in df.groupby("contest"):
        ok = d["proj_sum"].notna() & (d["proj_sum"] > 0)
        if ok.mean() < 0.95 or d.loc[ok, "proj_sum"].std() < 5:   # FC projections broken/partial on a few slates
            continue
        x, y = d.loc[ok, "proj_sum"].values, d.loc[ok, "own_sum"].values
        b = np.polyfit(x, y, 1)
        r = y - np.polyval(b, x)
        df.loc[d.index[ok], "own_resid_q"] = pd.qcut(pd.Series(r).rank(method="first"), 5, labels=False).values + 1
        df.loc[d.index[ok], "proj_q"] = pd.qcut(pd.Series(x).rank(method="first"), 5, labels=False).values + 1
    df["left"] = 50000 - df["sal_used"]
    df["left_b"] = pd.cut(df["left"], [-1, 500, 1000, 2000, 1e9], labels=["0-500", "500-1k", "1k-2k", "2k+"]).astype(str)
    df["studs_b"] = df["studs"].clip(upper=3).map(lambda v: "nan" if pd.isna(v) else ("3+" if v >= 3 else str(int(v))))
    df["punts_b"] = df["punts"].clip(upper=3).map(lambda v: "nan" if pd.isna(v) else ("3+" if v >= 3 else str(int(v))))
    df["cpt_own_t"] = pd.cut(df["cpt_own"], [-1, 5, 15, 101], labels=["<5", "5-15", ">=15"]).astype(str)
    df["chalk_cpt"] = np.where(df["cpt_own_rank"] == 1, "chalk CPT", "other CPT")
    df["dup_b"] = pd.cut(df["dupes"], [0, 1, 5, 20, 1e9], labels=["1 (unique)", "2-5", "6-20", "21+"]).astype(str)
    dt = np.where(df["n_dst"] == 0, "no DST",
          np.where(df["n_dst"] == 2, "both DST",
           np.where(df["dst_exp"] == 1, "exp DST", np.where(df["dst_cheap"] == 1, "cheap DST", "DST (same price)"))))
    df["dst_t"] = dt
    df["stack_b"] = df["stack_n"].astype(int).astype(str)
    df["n_k_b"] = df["n_k"].astype(int).astype(str)
    df["cpt_fav_b"] = df["cpt_fav"].map({1.0: "CPT fav", 0.0: "CPT dog"}).fillna("nan")
    df["cpt_sal_b"] = pd.cut(df["cpt_sal"], [0, 4000, 6900, 8900, 1e9], labels=["<=4k", "4.1-6.9k", "7-8.9k", ">=9k"]).astype(str)
    return df


def per_contest(df, feat):
    rows = []
    for cid, d in df.groupby("contest"):
        base = d["cashed"].mean()
        for lv, e in d.groupby(feat):
            if len(e) < MIN_N or str(lv) == "nan":
                continue
            rows.append({"contest": cid, "season": d["season"].iat[0], "ctype": d["ctype"].iat[0], "level": str(lv),
                         "n": len(e), "share": len(e) / len(d), "cash": e["cashed"].mean(), "cash_lift": 100 * (e["cashed"].mean() - base),
                         "ret": e["ret"].mean(), "ret_cap": e["ret_cap"].mean(), "top1_lift": 100 * (e["top1"].mean() - d["top1"].mean()),
                         "top10_lift": 100 * (e["top10"].mean() - d["top10"].mean()), "pctile": e["pctile"].mean()})
    return pd.DataFrame(rows)


def boot(v, stat=np.mean, B=2000):
    v = np.asarray(v, float)
    if len(v) < 3:
        return np.nan, np.nan
    idx = RS.randint(0, len(v), (B, len(v)))
    s = stat(v[idx], axis=1) if stat is np.mean else np.array([stat(v[i]) for i in idx])
    return np.percentile(s, 5), np.percentile(s, 95)


def summarise(pc, feat, extra_levels=None):
    out = []
    for (ct, lv), g in pc.groupby(["ctype", "level"]):
        r = {"feature": feat, "ctype": ct, "level": lv, "contests": len(g), "entries": int(g["n"].sum()),
             "share": g["share"].mean(), "cash_lift": g["cash_lift"].mean()}
        r["cash_lo"], r["cash_hi"] = boot(g["cash_lift"])
        r["ret"] = g["ret"].mean(); r["ret_lo"], r["ret_hi"] = boot(g["ret"])
        r["ret_cap"] = g["ret_cap"].mean(); r["retcap_lo"], r["retcap_hi"] = boot(g["ret_cap"])
        r["top1_lift"] = g["top1_lift"].mean(); r["top1_lo"], r["top1_hi"] = boot(g["top1_lift"])
        r["top10_lift"] = g["top10_lift"].mean()
        for s in (2022, 2023, 2024, 2025):
            gs = g[g["season"] == s]
            r[f"cash_{s}"] = gs["cash_lift"].mean() if len(gs) else np.nan
            r[f"retcap_{s}"] = gs["ret_cap"].mean() if len(gs) else np.nan
        out.append(r)
    return pd.DataFrame(out)


def fmt(t):
    cols = ["ctype", "level", "contests", "entries", "share", "cash_lift", "cash_lo", "cash_hi", "ret_cap", "retcap_lo", "retcap_hi",
            "ret", "top1_lift", "top1_lo", "top1_hi", "top10_lift", "cash_2022", "cash_2023", "cash_2024", "cash_2025",
            "retcap_2022", "retcap_2023", "retcap_2024", "retcap_2025"]
    return t[cols].round(3).to_string(index=False)


FEATURES = ["cpt_pos", "stack_b", "split", "n_k_b", "dst_t", "own_q", "own_resid_q", "proj_q", "cpt_own_t", "chalk_cpt",
            "dup_b", "left_b", "studs_b", "punts_b", "cpt_pair", "cpt_fav_b", "cpt_sal_b"]


def hindsight(df):
    """What did the actual winners / cashers look like vs the field (shape shares)."""
    rows = []
    for feat in ["cpt_pos", "split", "n_k_b", "dst_t", "stack_b", "cpt_own_t", "dup_b", "studs_b", "punts_b"]:
        for ct, d in df.groupby("ctype"):
            fld = d[feat].value_counts(normalize=True)
            cash = d[d["cashed"] == 1][feat].value_counts(normalize=True)
            t1 = d[d["top1"] == 1][feat].value_counts(normalize=True)
            for lv in fld.index:
                rows.append({"feature": feat, "ctype": ct, "level": lv, "field": fld.get(lv, 0), "cashers": cash.get(lv, 0), "top1": t1.get(lv, 0)})
    return pd.DataFrame(rows)


def own_slope(df):
    """Per-contest regression of outcome on standardized own_sum, controlling for FC proj_sum (both z-scored)."""
    rows = []
    for cid, d in df.groupby("contest"):
        ok = d["proj_sum"].notna() & (d["proj_sum"] > 0)
        d = d[ok]
        if len(d) < 1000 or d["proj_sum"].std() < 5:
            continue
        z = lambda s: (s - s.mean()) / s.std()
        X = np.column_stack([np.ones(len(d)), z(d["own_sum"]), z(d["proj_sum"])])
        X1 = np.column_stack([np.ones(len(d)), z(d["own_sum"])])
        r = {"contest": cid, "season": d["season"].iat[0], "ctype": d["ctype"].iat[0], "n": len(d)}
        if not np.isfinite(X).all():
            continue
        for y in ["cashed", "ret_cap", "top1", "points"]:
            yy = np.nan_to_num(d[y].values.astype(float))
            b = np.linalg.lstsq(X, yy, rcond=None)[0]
            b1 = np.linalg.lstsq(X1, yy, rcond=None)[0]
            r[f"{y}_own_ctrl"] = b[1]; r[f"{y}_proj_ctrl"] = b[2]; r[f"{y}_own_raw"] = b1[1]
        r["corr_own_proj"] = np.corrcoef(d["own_sum"], d["proj_sum"])[0, 1]
        rows.append(r)
    return pd.DataFrame(rows)


def main():
    df = pd.read_parquet(CACHE)
    df = prep(df)
    log("entries", len(df), "contests", df["contest"].nunique())
    log(df.groupby(["ctype", "season"]).agg(contests=("contest", "nunique"), entries=("rank", "size")).to_string())
    allsum = []
    for feat in FEATURES:
        pc = per_contest(df, feat)
        t = summarise(pc, feat)
        allsum.append(t)
        log("\n=== " + feat + " ===")
        log(fmt(t))
    S = pd.concat(allsum)
    S.to_csv(os.path.join(OUT, "ls_feature_lift.csv"), index=False)
    H = hindsight(df)
    H.to_csv(os.path.join(OUT, "ls_hindsight_shares.csv"), index=False)
    log("\n=== shares: field vs cashers vs top1% ===")
    log(H.round(3).to_string(index=False))
    O = own_slope(df)
    O.to_csv(os.path.join(OUT, "ls_own_slope_by_contest.csv"), index=False)
    log("\n=== ownership slope per SD of own_sum (per-contest OLS), mean [90% CI] and seasons positive/total ===")
    for ct, g in O.groupby("ctype"):
        for col in ["cashed_own_raw", "cashed_own_ctrl", "cashed_proj_ctrl", "ret_cap_own_raw", "ret_cap_own_ctrl",
                    "top1_own_raw", "top1_own_ctrl", "top1_proj_ctrl", "points_own_raw", "points_own_ctrl"]:
            lo, hi = boot(g[col])
            by = g.groupby("season")[col].mean()
            log(f"{ct:4s} {col:18s} mean {g[col].mean():+.4f} [{lo:+.4f},{hi:+.4f}] pos {int((g[col]>0).sum())}/{len(g)}  " +
                " ".join(f"{s}:{v:+.4f}" for s, v in by.items()))
        log(f"{ct} corr(own_sum, proj_sum) mean {g['corr_own_proj'].mean():.2f}")
    # contest-level context
    ctx = df.groupby(["ctype"]).agg(cash_rate=("cashed", "mean"), dup_mean=("dupes", "mean"),
                                   uniq_share=("dupes", lambda s: (s == 1).mean()))
    log("\n", ctx.to_string())
    with open(os.path.join(OUT, "ls_analysis_out.txt"), "w") as fh:
        fh.write("\n".join(LINES))


if __name__ == "__main__":
    main()
