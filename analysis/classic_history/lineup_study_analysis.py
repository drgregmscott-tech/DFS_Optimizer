"""Real-field CLASSIC construction analysis on FC Lineup Study contests (2022-2026).

Reads the per-contest entry files written by lineup_study_build.py (gitignored) one contest at a time, and writes
AGGREGATE-ONLY tables to analysis/classic_history/out/:
  cl_feature_lift.csv     cash lift / return by feature level, per contest type, 90% CI over contests, season signs
  cl_shape_cash_vs_non.csv  mean shape of cashing vs non-cashing lineups (Phase 2 cross-reference), per contest type
  cl_headline.csv         ownership quintile test (all entries, <=$500 left, quality subset), incl. uncapped return
  cl_slopes.csv           per-SD slopes from per-contest OLS (ownership with/without FC-projection control; multi-feature model)
  cl_analysis_out.txt     text dump
Per-contest intermediate rows go to data/fc_history/derived/classic/ (gitignored).

Metrics are computed WITHIN a contest and averaged with EQUAL weight per contest (same as the Showdown study):
  cash lift = cash rate of level - contest cash rate (pts); ret_cap = mean payout (capped at contest 99.9th pct) /
  contest mean; ret = uncapped; top1 lift. 90% bootstrap CIs over contests. A level needs >= 30 entries in a contest.
"""
import glob, os, sys
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DER = os.path.join(ROOT, "data", "fc_history", "derived", "classic")
OUT = os.path.join(ROOT, "analysis", "classic_history", "out")
RS = np.random.RandomState(7)
MIN_N = 30
SEASONS = (2022, 2023, 2024, 2025)
LINES = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True); LINES.append(s)


def bucket(v, edges, labels):
    return pd.cut(v, edges, labels=labels, right=False).astype(str)


def cap3(v, top=3):
    return np.where(v >= top, f"{top}+", v.astype(int).astype(str))


def prep(d):
    d = d.copy()
    n = len(d)
    d["cashed"] = (d["payout_c"] > 0).astype(float)
    d["top1"] = (d["rank"] <= max(1, int(0.01 * n))).astype(float)
    d["top10"] = (d["rank"] <= max(1, int(0.10 * n))).astype(float)
    mp = d["payout_c"].mean()
    d["ret"] = d["payout_c"] / mp if mp > 0 else np.nan
    cap = d["payout_c"].quantile(0.999)
    pc = np.minimum(d["payout_c"], cap)
    d["ret_cap"] = pc / pc.mean() if pc.mean() > 0 else np.nan
    d["own_q"] = pd.qcut(d["own_sum"].rank(method="first"), 5, labels=False) + 1
    d["proj_q"] = np.nan; d["own_resid_q"] = np.nan
    if d["proj_sum"].notna().all() and d["proj_sum"].std() >= 3:
        x, y = d["proj_sum"].values.astype(float), d["own_sum"].values.astype(float)
        r = y - np.polyval(np.polyfit(x, y, 1), x)
        d["own_resid_q"] = pd.qcut(pd.Series(r, index=d.index).rank(method="first"), 5, labels=False) + 1
        d["proj_q"] = pd.qcut(d["proj_sum"].rank(method="first"), 5, labels=False) + 1
    d["left"] = 50000 - d["sal_used"]
    d.loc[d["sal_nan"], "left"] = np.nan
    d["left_b"] = pd.cut(d["left"], [-1e9, 500, 1000, 2000, 1e9], labels=["0-500", "500-1k", "1k-2k", "2k+"], right=True).astype(str)
    d["stack_rec_b"] = cap3(d["stack_rec"].values)
    d["stack_any_b"] = cap3((d["stack_rec"] + d["stack_rb"]).values)
    d["qb_rb_b"] = np.where(d["stack_rb"] > 0, "QB+own RB", "no own RB")
    d["naked"] = np.where(d["stack_rec"] + d["stack_rb"] == 0, "naked QB", "QB w/ teammate")
    d["bb_b"] = cap3(d["bb"].values, 2)
    d["qb_game_b"] = cap3(d["game_n"].values, 5)
    d["studs_b"] = cap3(d["studs"].values)
    d["punts_b"] = cap3(d["punts"].values)
    d["qb_sal_b"] = bucket(d["qb_sal"], [0, 5500, 6500, 7500, 1e9], ["<5.5k", "5.5-6.4k", "6.5-7.4k", "7.5k+"])
    d["qb_sal_rank_b"] = bucket(d["qb_sal_rank"], [1, 4, 9, 1000], ["top3 priced", "4-8", "9+"])
    d["qb_own_rank_b"] = bucket(d["qb_own_rank"], [1, 2, 4, 7, 1000], ["#1 QB", "#2-3", "#4-6", "#7+"])
    d["dst_sal_b"] = bucket(d["dst_sal"], [0, 2800, 3200, 3600, 1e9], ["<2.8k", "2.8-3.1k", "3.2-3.5k", "3.6k+"])
    d["te_sal_b"] = bucket(d["te_sal"], [0, 3500, 4500, 6000, 1e9], ["<3.5k", "3.5-4.4k", "4.5-5.9k", "6k+"])
    d["dst_conf_b"] = np.where(d["dst_conf"] > 0, "DST vs own player", "no conflict")
    d["dst_rb_b"] = np.where(d["dst_own_rb"] > 0, "DST+own RB", "no")
    d["flex_b"] = d["flex_pos"].map({1: "RB", 2: "WR", 3: "TE"}).fillna("?")
    d["max_team_b"] = cap3(d["max_team"].values, 5)
    d["lowown_b"] = cap3(d["n_lt2own"].values)
    d["top5own_b"] = cap3(d["n_top5own"].values, 4)
    d["dup_b"] = pd.cut(d["dupes"], [0, 1, 5, 20, 1e9], labels=["1 (unique)", "2-5", "6-20", "21+"]).astype(str)
    d["qb_proj_rank_b"] = "nan"
    return d


FEATURES = ["stack_rec_b", "stack_any_b", "naked", "qb_rb_b", "bb_b", "qb_game_b", "qb_sal_b", "qb_sal_rank_b", "qb_own_rank_b",
            "left_b", "studs_b", "punts_b", "flex_b", "te_sal_b", "dst_sal_b", "dst_conf_b", "dst_rb_b", "max_team_b",
            "own_q", "own_resid_q", "proj_q", "lowown_b", "top5own_b", "dup_b"]
SHAPE = {"stack1": lambda d: d["stack_rec"] >= 1, "stack2": lambda d: d["stack_rec"] >= 2, "stack3": lambda d: d["stack_rec"] >= 3,
         "naked": lambda d: (d["stack_rec"] + d["stack_rb"]) == 0, "bringback": lambda d: d["bb"] >= 1,
         "studs": lambda d: d["studs"], "punts": lambda d: d["punts"], "sal_used": lambda d: d["sal_used"],
         "qb_sal": lambda d: d["qb_sal"], "dst_sal": lambda d: d["dst_sal"], "own_sum": lambda d: d["own_sum"],
         "flex_te": lambda d: d["flex_pos"] == 3, "dst_conflict": lambda d: d["dst_conf"] > 0, "left_le500": lambda d: d["left"] <= 500,
         "qb_own_rank1": lambda d: d["qb_own_rank"] == 1}


def per_contest(d, feat, meta):
    rows = []
    base = d["cashed"].mean(); t1 = d["top1"].mean(); t10 = d["top10"].mean()
    for lv, e in d.groupby(feat):
        if len(e) < MIN_N or str(lv) == "nan":
            continue
        rows.append({**meta, "feature": feat, "level": str(lv), "n": len(e), "share": len(e) / len(d),
                     "cash_lift": 100 * (e["cashed"].mean() - base), "ret": e["ret"].mean(), "ret_cap": e["ret_cap"].mean(),
                     "top1_lift": 100 * (e["top1"].mean() - t1), "top10_lift": 100 * (e["top10"].mean() - t10)})
    return rows


def headline(d, meta, label, mask):
    s = d[mask]
    if len(s) < 500:
        return []
    s = s.copy()
    s["q"] = pd.qcut(s["own_sum"].rank(method="first"), 5, labels=False) + 1
    s["rq"] = np.nan
    if s["proj_sum"].notna().all() and s["proj_sum"].std() >= 3:
        x, y = s["proj_sum"].values.astype(float), s["own_sum"].values.astype(float)
        r = y - np.polyval(np.polyfit(x, y, 1), x)
        s["rq"] = pd.qcut(pd.Series(r, index=s.index).rank(method="first"), 5, labels=False) + 1
    bc, br, brr, b1 = s["cashed"].mean(), s["ret_cap"].mean(), s["ret"].mean(), s["top1"].mean()
    out = []
    for feat in ("q", "rq", "dup_b"):
        for lv, e in s.groupby(feat):
            if len(e) < 30:
                continue
            out.append({**meta, "subset": label, "feature": feat, "level": str(lv), "n": len(e),
                        "cash_lift": 100 * (e["cashed"].mean() - bc),
                        "ret_rel": e["ret_cap"].mean() / br if br > 0 else np.nan,
                        "ret_raw_rel": e["ret"].mean() / brr if brr > 0 else np.nan,
                        "top1_lift": 100 * (e["top1"].mean() - b1), "sub_ret_vs_field": br, "sub_n": len(s)})
    return out


def z(s):
    s = s.astype(float)
    return (s - s.mean()) / s.std() if s.std() > 0 else s * 0


def slopes(d, meta):
    out = []
    for label, s in (("all", d), ("quality", d[(d["left"] <= 500) & (d["proj_q"] >= 4)])):
        s = s.dropna(subset=["proj_sum", "own_sum", "qb_sal", "left"])
        if len(s) < 1000 or s["proj_sum"].std() < 3:
            continue
        r = {**meta, "subset": label, "n": len(s)}
        X1 = np.column_stack([np.ones(len(s)), z(s["own_sum"])])
        X2 = np.column_stack([X1, z(s["proj_sum"])])
        # multi-feature model: shape features jointly, with projection control (per-SD for continuous, 0/1 dummies)
        X3 = np.column_stack([X2, z(s["qb_sal"]), (s["stack_rec"] >= 2).astype(float), (s["punts"] >= 1).astype(float),
                              (s["bb"] >= 1).astype(float), z(s["left"].clip(upper=5000))])
        for y in ("cashed", "ret_cap", "top1", "points"):
            yy = np.nan_to_num(s[y].values.astype(float))
            b1 = np.linalg.lstsq(X1, yy, rcond=None)[0]; b2 = np.linalg.lstsq(X2, yy, rcond=None)[0]
            b3 = np.linalg.lstsq(X3, yy, rcond=None)[0]
            r[f"{y}_own_raw"] = b1[1]; r[f"{y}_own_ctrl"] = b2[1]; r[f"{y}_proj_ctrl"] = b2[2]
            for k, nm in enumerate(["own", "proj", "qbsal", "stack2", "punt1", "bb1", "left"]):
                r[f"{y}_m_{nm}"] = b3[k + 1]
        r["corr_own_proj"] = np.corrcoef(s["own_sum"], s["proj_sum"])[0, 1]
        # QB-salary slope with only a projection control
        X4 = np.column_stack([np.ones(len(s)), z(s["qb_sal"]), z(s["proj_sum"])])
        for y in ("cashed", "ret_cap"):
            r[f"{y}_qbsal_ctrl"] = np.linalg.lstsq(X4, np.nan_to_num(s[y].values.astype(float)), rcond=None)[0][1]
        out.append(r)
    return out


def shape_rows(d, meta):
    out = []
    grp = {"cash": d["cashed"] == 1, "noncash": d["cashed"] == 0, "field": d["cashed"] >= 0, "top1": d["top1"] == 1}
    if d["is_me"].any():
        grp["gmscott81"] = d["is_me"]
    for g, m in grp.items():
        e = d[m]
        if len(e) == 0:
            continue
        r = {**meta, "group": g, "n": len(e)}
        for k, f in SHAPE.items():
            r[k] = float(np.nanmean(f(e).astype(float)))
        out.append(r)
    return out


def boot(v, B=2000):
    v = np.asarray(v, float); v = v[np.isfinite(v)]
    if len(v) < 3:
        return np.nan, np.nan
    s = v[RS.randint(0, len(v), (B, len(v)))].mean(1)
    return np.percentile(s, 5), np.percentile(s, 95)


def summarise(pc, keys, metrics):
    out = []
    for key, g in pc.groupby(keys):
        r = dict(zip(keys, key if isinstance(key, tuple) else (key,)))
        r["contests"] = g["contest"].nunique(); r["entries"] = int(g["n"].sum()) if "n" in g else np.nan
        if "share" in g:
            r["share"] = g["share"].mean()
        for m in metrics:
            r[m] = g[m].mean(); r[m + "_lo"], r[m + "_hi"] = boot(g[m])
            by = g.groupby("season")[m].mean()
            r[m + "_seasons_pos"] = f"{int((by.reindex(SEASONS) > (1 if m.startswith('ret') else 0)).sum())}/{int(by.reindex(SEASONS).notna().sum())}"
            for s_ in SEASONS:
                r[f"{m}_{s_}"] = by.get(s_, np.nan)
        out.append(r)
    return pd.DataFrame(out)


def main():
    # exclusions from the build QA: truncated fields (FC ~25.5k row cap on a few 20-max pulls) and tiny contests (<1000);
    # projection-controlled tests skip contests where FC projections are missing/zero for >30% of lineups or flat
    Q = pd.read_csv(os.path.join(OUT, "cl_qa.csv"))
    drop = set(Q.loc[(Q["rows_vs_entrants"] < 0.99) | (Q["rows_used"] < 1000), "file"].str[:-8])
    badproj = set(Q.loc[(Q["lineups_with_noproj_player"] > 0.3) | (Q["proj_std_lineup"] < 3), "file"].str[:-8])
    log(f"excluded contests: {len(drop)} (truncated or <1000 entries); projection-control excluded: {len(badproj - drop)}")
    files = sorted(f for f in glob.glob(os.path.join(DER, "entries", "*.parquet")) if os.path.basename(f)[:-8] not in drop)
    feat_rows, head_rows, slope_rows, shp_rows = [], [], [], []
    for i, f in enumerate(files):
        d = pd.read_parquet(f)
        if os.path.basename(f)[:-8] in badproj:
            d["proj_sum"] = np.nan
        d = prep(d)
        meta = {"contest": d["contest"].iat[0], "season": int(d["season"].iat[0]), "ctype": d["ctype"].iat[0],
                "type": d["type"].iat[0], "slate": d["slate"].iat[0]}
        for feat in FEATURES:
            feat_rows += per_contest(d, feat, meta)
        head_rows += headline(d, meta, "all", d["cashed"] >= 0)
        head_rows += headline(d, meta, "le500", d["left"] <= 500)
        head_rows += headline(d, meta, "quality", (d["left"] <= 500) & (d["proj_q"] >= 4))
        slope_rows += slopes(d, meta)
        shp_rows += shape_rows(d, meta)
        if i % 25 == 0:
            print(i, os.path.basename(f), flush=True)
    F = pd.DataFrame(feat_rows); H = pd.DataFrame(head_rows); S = pd.DataFrame(slope_rows); SH = pd.DataFrame(shp_rows)
    os.makedirs(OUT, exist_ok=True)
    F.to_parquet(os.path.join(DER, "_per_contest_features.parquet")); H.to_parquet(os.path.join(DER, "_per_contest_headline.parquet"))
    S.to_parquet(os.path.join(DER, "_per_contest_slopes.parquet")); SH.to_parquet(os.path.join(DER, "_per_contest_shape.parquet"))

    log("contests by ctype/season:\n" + SH[SH.group == "field"].pivot_table(index="ctype", columns="season", values="n", aggfunc="count").to_string())
    FL = summarise(F, ["feature", "ctype", "level"], ["cash_lift", "ret_cap", "ret", "top1_lift"])
    FL.to_csv(os.path.join(OUT, "cl_feature_lift.csv"), index=False)
    cols = ["ctype", "level", "contests", "share", "cash_lift", "cash_lift_lo", "cash_lift_hi", "cash_lift_seasons_pos",
            "ret_cap", "ret_cap_lo", "ret_cap_hi", "ret_cap_seasons_pos", "ret", "top1_lift"]
    for feat in FEATURES:
        log(f"\n=== {feat} ===")
        log(FL[FL.feature == feat][cols].round(3).to_string(index=False))
    # also a pooled "all contest types" row per feature
    FA = summarise(F.assign(ctype="ALL"), ["feature", "ctype", "level"], ["cash_lift", "ret_cap"])
    FA.to_csv(os.path.join(OUT, "cl_feature_lift_alltypes.csv"), index=False)

    # shape cash vs noncash
    shp_cols = list(SHAPE)
    SHs = SH.groupby(["ctype", "group"])[shp_cols].mean()
    SHs["contests"] = SH.groupby(["ctype", "group"])["contest"].nunique()
    SHs.reset_index().to_csv(os.path.join(OUT, "cl_shape_cash_vs_non.csv"), index=False)
    log("\n=== shape: cashing vs non-cashing (mean of per-contest means) ===")
    log(SHs.round(3).to_string())
    # paired cash - noncash diffs with CI
    piv = SH.pivot_table(index=["contest", "ctype", "season"], columns="group", values=shp_cols)
    rows = []
    for ct in sorted(SH.ctype.unique()):
        p = piv.xs(ct, level="ctype")
        for k in shp_cols:
            dd = (p[(k, "cash")] - p[(k, "noncash")]).values
            lo, hi = boot(dd)
            by = pd.Series(dd, index=p.index.get_level_values("season")).groupby(level=0).mean()
            rows.append({"ctype": ct, "metric": k, "cash": p[(k, "cash")].mean(), "noncash": p[(k, "noncash")].mean(),
                         "diff": np.nanmean(dd), "lo": lo, "hi": hi,
                         "seasons_pos": f"{int((by.reindex(SEASONS) > 0).sum())}/{int(by.reindex(SEASONS).notna().sum())}"})
    D = pd.DataFrame(rows); D.to_csv(os.path.join(OUT, "cl_shape_diff.csv"), index=False)
    log("\n=== cash minus noncash, 90% CI over contests ===")
    log(D.round(3).to_string(index=False))

    HS = summarise(H, ["subset", "feature", "ctype", "level"], ["cash_lift", "ret_rel", "ret_raw_rel", "top1_lift"])
    HS.to_csv(os.path.join(OUT, "cl_headline.csv"), index=False)
    log("\n=== headline: ownership quintile within subset ===")
    hc = ["subset", "feature", "ctype", "level", "contests", "cash_lift", "cash_lift_lo", "cash_lift_hi", "ret_rel", "ret_rel_lo",
          "ret_rel_hi", "ret_rel_seasons_pos", "ret_raw_rel", "ret_raw_rel_lo", "ret_raw_rel_hi", "top1_lift"]
    log(HS[HS.feature.isin(["q", "rq"])][hc].round(3).to_string(index=False))
    log(HS[HS.feature == "dup_b"][hc].round(3).to_string(index=False))

    scols = [c for c in S.columns if any(c.startswith(y + "_") for y in ("cashed", "ret_cap", "top1", "points"))] + ["corr_own_proj"]
    rows = []
    for (sub, ct), g in S.groupby(["subset", "ctype"]):
        for c in scols:
            lo, hi = boot(g[c]); by = g.groupby("season")[c].mean()
            rows.append({"subset": sub, "ctype": ct, "coef": c, "mean": g[c].mean(), "lo": lo, "hi": hi, "contests": len(g),
                         "pos_contests": int((g[c] > 0).sum()),
                         "seasons_pos": f"{int((by.reindex(SEASONS) > 0).sum())}/{int(by.reindex(SEASONS).notna().sum())}"})
    SL = pd.DataFrame(rows); SL.to_csv(os.path.join(OUT, "cl_slopes.csv"), index=False)
    log("\n=== per-contest OLS slopes (per SD / per dummy), mean [90% CI] ===")
    pd.set_option("display.width", 250)
    log(SL.round(4).to_string(index=False))
    with open(os.path.join(OUT, "cl_analysis_out.txt"), "w") as fh:
        fh.write("\n".join(LINES))


if __name__ == "__main__":
    main()
