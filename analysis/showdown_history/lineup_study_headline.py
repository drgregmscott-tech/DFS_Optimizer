"""Headline check: does ownership still pay among *optimizer-quality* lineups in the real field?

The raw ownership-quintile result (lineup_study_analysis.py) is confounded: low-owned lineups include casual/junk builds
(salary left, weak projection). Here we restrict to entries that look like what our optimizer would submit:
  salary left <= $500 AND FC-projection quintile (within contest) >= 4,
then re-quintile summed realized ownership WITHIN that subset per contest and compare outcomes against the subset's
own base rates. Also: duplication buckets within the same subset.
Output: data/fc_history/derived/showdown/ls_headline_quality.csv (aggregate only).
"""
import os
import numpy as np
import pandas as pd
import lineup_study_analysis as A


def run(df, label, mask):
    rows = []
    sub = df[mask].copy()
    for cid, d in sub.groupby("contest"):
        if len(d) < 500 or d["proj_sum"].std() < 3 or d["proj_sum"].isna().any():
            continue
        d = d.copy()
        d["q"] = pd.qcut(d["own_sum"].rank(method="first"), 5, labels=False) + 1
        d["rq"] = np.nan
        x, y = d["proj_sum"].values, d["own_sum"].values
        r = y - np.polyval(np.polyfit(x, y, 1), x)
        d["rq"] = pd.qcut(pd.Series(r, index=d.index).rank(method="first"), 5, labels=False) + 1
        base_c, base_r, base_t1, base_t10 = d["cashed"].mean(), d["ret_cap"].mean(), d["top1"].mean(), d["top10"].mean()
        for feat in ["q", "rq", "dup_b"]:
            for lv, e in d.groupby(feat):
                if len(e) < 30:
                    continue
                rows.append({"subset": label, "feature": feat, "level": str(lv), "contest": cid, "season": d["season"].iat[0],
                             "ctype": d["ctype"].iat[0], "n": len(e), "cash_lift": 100 * (e["cashed"].mean() - base_c),
                             "ret_rel": e["ret_cap"].mean() / base_r if base_r > 0 else np.nan,
                             "ret_raw_rel": e["ret"].mean() / d["ret"].mean() if d["ret"].mean() > 0 else np.nan,
                             "top1_lift": 100 * (e["top1"].mean() - base_t1), "top10_lift": 100 * (e["top10"].mean() - base_t10),
                             "sub_ret_vs_field": base_r})
    return pd.DataFrame(rows)


def main():
    df = A.prep(pd.read_parquet(A.CACHE))
    quality = (df["left"] <= 500) & (df["proj_q"] >= 4)
    P = pd.concat([run(df, "quality", quality), run(df, "all_full_salary", df["left"] <= 500)])
    out = []
    for (sub, feat, ct, lv), g in P.groupby(["subset", "feature", "ctype", "level"]):
        r = {"subset": sub, "feature": feat, "ctype": ct, "level": lv, "contests": len(g), "entries": int(g["n"].sum())}
        for m in ["cash_lift", "ret_rel", "ret_raw_rel", "top1_lift", "top10_lift"]:
            v = g[m].dropna()
            r[m] = v.mean(); r[m + "_lo"], r[m + "_hi"] = A.boot(v)
        for s in (2022, 2023, 2024, 2025):
            r[f"ret_rel_{s}"] = g.loc[g["season"] == s, "ret_rel"].mean()
            r[f"top1_{s}"] = g.loc[g["season"] == s, "top1_lift"].mean()
        r["subset_ret_vs_field"] = g["sub_ret_vs_field"].mean()
        out.append(r)
    T = pd.DataFrame(out)
    T.to_csv(os.path.join(A.OUT, "ls_headline_quality.csv"), index=False)
    pd.set_option("display.width", 250)
    print(T.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
