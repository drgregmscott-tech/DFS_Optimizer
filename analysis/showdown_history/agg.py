"""Aggregate per-slate sim pickles -> summary tables (aggregate only). Output printed; redirect to derived/."""
import pickle
from pathlib import Path
import numpy as np, pandas as pd
R = Path(__file__).resolve().parents[2]; D = R / "data/fc_history/derived/showdown"
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40); pd.set_option("display.max_rows", 200)
res = [pickle.load(open(f, "rb")) for f in sorted((D / "slates").glob("*.pkl"))]
print("slates:", len(res))
rng = np.random.default_rng(1)
H = pd.concat([r["hind"].assign(slate=r["slate"]) for r in res]); H["year"] = H.slate.str[:4].astype(int)
S = pd.concat([r["strat"].assign(slate=r["slate"]) for r in res]); S["year"] = S.slate.str[:4].astype(int)


def wilson(k, n, z=1.645):
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return f"{k}/{n} = {p:.0%} [{c - h:.0%}, {c + h:.0%}]"


h0 = H[H["rank"] == 0]
print("\n=== HINDSIGHT OPTIMAL (1 per slate) ===")
for col in ["cpt_pos", "split", "nK", "nD", "expD", "cpt_fav", "n_min", "n_proj0"]:
    vc = h0[col].value_counts()
    print(col, "|", "; ".join(wilson(int(v), len(h0), ) + f" {k}" for k, v in vc.items()))
    print("   by year:", h0.groupby("year")[col].value_counts().unstack(fill_value=0).to_dict("index"))
print("cpt_own rank (1=chalk) quantiles:", h0.cpt_own_rank.describe()[["25%", "50%", "75%"]].to_dict(), " cpt_own mean", round(h0.cpt_own.mean(), 1),
      " share cpt_own<5:", round((h0.cpt_own < 5).mean(), 2), " chalk CPT (rank1):", int((h0.cpt_own_rank == 1).sum()))
print("cpt proj rank quantiles:", h0.cpt_proj_rank.describe()[["25%", "50%", "75%"]].to_dict(), " cpt proj rank<=3:", wilson(int((h0.cpt_proj_rank <= 3).sum()), len(h0)))
print("cpt salary tiers:", pd.cut(h0.cpt_sal, [0, 4000, 7000, 9000, 20000]).value_counts().sort_index().to_dict())
print("salary used quantiles:", h0.sal.describe()[["min", "25%", "50%", "75%"]].to_dict(), " ownsum median", h0.ownsum.median())
print("hindsight act median", h0.act.median(), "; its FC proj median", h0.proj.median())
print("\nTop-20 hindsight lineups: CPT pos share (pooled) and by year:")
print(H.groupby("year").cpt_pos.value_counts(normalize=True).unstack().round(3)); print(H.cpt_pos.value_counts(normalize=True).round(3).to_dict())
print("Top-20: split share", H.split.value_counts(normalize=True).round(3).to_dict(), " nK", H.nK.value_counts(normalize=True).round(3).to_dict(),
      " nD", H.nD.value_counts(normalize=True).round(3).to_dict(), " expD", H.expD.mean().round(3))
# field comparison
fld = pd.DataFrame([{**{f"cpt_{k}": v for k, v in r["fields"]["F1_salary"]["cpt_pos"].items()}, **{f"split_{k}": v for k, v in r["fields"]["F1_salary"]["split"].items()},
                     **{f"nK_{k}": v for k, v in r["fields"]["F1_salary"]["nK"].items()}} for r in res]).fillna(0)
print("\nField (F1) mean shares:", fld.mean().round(3).to_dict())
for k in ("F0_uniform", "F1_salary", "F2_sal_proj"):
    e = [r["fields"][k]["err"] for r in res]; sm = [r["fields"][k]["sal_mean"] for r in res]
    print(k, "IPF max marginal err median/max", round(np.median(e), 4), round(max(e), 4), " mean salary", round(np.mean(sm)),
          " q99-q50 pts", round(np.mean([r["fields"][k]["q"][0.99] - r["fields"][k]["q"][0.5] for r in res]), 1),
          " hindsight-opt pct", round(np.mean([r["fields"][k]["hind_pct"] for r in res]), 5))

print("\n=== STRATEGIES (chosen on FC proj/own; scored on actuals vs simulated field) ===")
base = "A_max_proj"
for sub, lab in ((S["rank"] == 0, "single lineup (#1 by objective)"), (S["rank"] < 20, "avg of top-20 by objective")):
    for yr in ("ALL", 2025):
        x = S[sub] if yr == "ALL" else S[sub & (S.year == 2025)]
        per = x.groupby(["strategy", "slate"])[[c for c in x.columns if c.startswith("F")] + ["act", "proj"]].mean()
        tab = per.groupby("strategy").mean()
        n = per.groupby("strategy").size()
        out = pd.DataFrame(dict(n=n, proj=tab.proj, act=tab.act))
        for k in ("F0_uniform", "F1_salary", "F2_sal_proj"):
            out[k[:2] + "_pct"] = tab[f"{k}_pct"] * 100; out[k[:2] + "_top1"] = tab[f"{k}_top1"] * 100; out[k[:2] + "_top10"] = tab[f"{k}_top10"] * 100
        # paired diff vs base on F1 pct and top10, bootstrap over slates common
        b = per.loc[base]
        ci = {}
        for s in out.index:
            a = per.loc[s]; common = a.index.intersection(b.index)
            d1 = (a.loc[common, "F1_salary_pct"] - b.loc[common, "F1_salary_pct"]).to_numpy() * 100
            d2 = (a.loc[common, "F1_salary_top10"] - b.loc[common, "F1_salary_top10"]).to_numpy() * 100
            da = (a.loc[common, "act"] - b.loc[common, "act"]).to_numpy()
            bs = [(d1[i].mean(), d2[i].mean(), da[i].mean()) for i in (rng.integers(0, len(d1), len(d1)) for _ in range(2000))]
            bs = np.array(bs)
            ci[s] = dict(dpct=f"{d1.mean():+.1f} [{np.percentile(bs[:, 0], 5):+.1f},{np.percentile(bs[:, 0], 95):+.1f}]",
                         dtop10=f"{d2.mean():+.1f} [{np.percentile(bs[:, 1], 5):+.1f},{np.percentile(bs[:, 1], 95):+.1f}]",
                         dact=f"{da.mean():+.1f} [{np.percentile(bs[:, 2], 5):+.1f},{np.percentile(bs[:, 2], 95):+.1f}]")
        out = out.join(pd.DataFrame(ci).T)
        print(f"\n-- {lab}, years={yr} (pct = mean field percentile; top1/top10 = % of slates/lineups; d* = paired vs {base} on F1, 90% boot CI) --")
        print(out.round(1).to_string())
# strategy characteristics
print("\nmax-proj lineup characteristics: cpt pos", S[(S.strategy == base) & (S["rank"] == 0)].cpt_pos.value_counts().to_dict(),
      " split", S[(S.strategy == base) & (S["rank"] == 0)].split.value_counts().to_dict(), " nK", S[(S.strategy == base) & (S["rank"] == 0)].nK.value_counts().to_dict())
