"""gmscott81 regime study, step 3: slate-level clustering check. E1 contests are 3 formats of the same weekly slate, often
with the same lineup, so contest bootstrap overstates independence. Re-bootstrap over SLATES and count how often the same
9-player lineup was entered in several contests of one slate. Output: out/regime_cluster.csv (aggregates only)."""
import os, glob
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); CH = os.path.dirname(HERE); ROOT = os.path.dirname(os.path.dirname(CH))
DER = os.path.join(ROOT, "data", "fc_history", "derived", "classic_regime")
rng = np.random.default_rng(11)
qa = pd.read_csv(os.path.join(CH, "out", "cl_qa.csv")); qa["base"] = qa.file.str[:-8]; qa = qa.set_index("base")
R = pd.read_parquet(os.path.join(DER, "me_rosters.parquet"))
rows = []
for f in sorted(glob.glob(os.path.join(DER, "entries", "*.parquet"))):
    b = os.path.basename(f)[:-8]; q = qa.loc[b]
    if q.rows_vs_entrants < 0.9 or q.rows_used < 1000:
        continue
    e = pd.read_parquet(f, columns=["payout_c", "is_me"]); base = float((e.payout_c > 0).mean())
    me = e[e.is_me]
    for k, pay in enumerate(me.payout_c):
        key = tuple(sorted(R[(R.file == b) & (R.entry == k)].pid))
        rows.append({"slate": b.split("_")[0], "season": int(q.season), "file": b, "cash": pay > 0, "base": base,
                     "lineup": hash(key), "mme": len(me) >= 20})
D = pd.DataFrame(rows); D["era"] = np.where(D.season <= 2024, "E1", "E2")
out = []
for era, x in D.groupby("era"):
    x = x.assign(ex=x.cash - x.base)
    sl = x.groupby("slate").ex.mean(); g = [y for _, y in x.groupby("slate")]
    v = [np.mean([gg.ex.mean() for gg in (g[i] for i in rng.integers(0, len(g), len(g)))]) for _ in range(4000)]
    uniq = x.groupby("slate").lineup.nunique().sum()
    ul = x.drop_duplicates(["slate", "lineup"])
    out.append({"era": era, "entries": len(x), "contests": x.file.nunique(), "slates": x.slate.nunique(),
                "distinct_lineups": int(uniq), "excess_slate_w": round(sl.mean(), 3),
                "lo90": round(np.percentile(v, 5), 3), "hi90": round(np.percentile(v, 95), 3),
                "slates_any_cash": round(x.groupby("slate").cash.max().mean(), 3),
                "cash_distinct_lineups": round(ul.cash.mean(), 3)})
O = pd.DataFrame(out); O.to_csv(os.path.join(HERE, "out", "regime_cluster.csv"), index=False); print(O.to_string(index=False))
