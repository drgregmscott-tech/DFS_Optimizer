"""Step 3: (a) does a news-bearing projection close the cheap WR/TE gap? (diagnostic: FC's pre-lock projection
as an extra input, 2021-23 only, LOSO over those 3 seasons). (b) is it a temperature problem? (power-sharpen
v2 within group, exponent chosen leave-one-season-out). No FC data in this file."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ownership_v2"))
from common import ALL, R, Model, metrics, allocate, _groups  # noqa

H = pd.read_parquet(R / "data/fc_history/derived/ownership_v2/hist.parquet").reset_index(drop=True)
H["v2"] = pd.read_parquet(R / "data/fc_history/derived/cheap_wrte/v2_loso.parquet").v2.values
# (a)
T = H[H.season <= 2023].copy().reset_index(drop=True)
T["fcp"] = T.fc_proj.fillna(0).clip(lower=0)
T["fcv"] = T.fcp / T.salk.clip(lower=1)
T["fcp_gap"] = T.fcp - T.proj
T["fcv_lrk"] = np.log(T.fcv.where(T.in_pool & (T.proj > 0)).groupby([T.slate_id, T.grp]).rank(ascending=False).fillna(99))
res = {}
for name, f in {"v2 (3-season LOSO)": ALL, "v2 + FC proj inputs": ALL + ["fcp", "fcv", "fcp_gap", "fcv_lrk"]}.items():
    p = np.zeros(len(T))
    for s in (2021, 2022, 2023):
        te = (T.season == s).to_numpy()
        p[te] = Model(f).fit(T[~te], "own").predict(T[te])
    res[name] = metrics(T, p, "own")
res["FC Own"] = metrics(T, T.fc_own.fillna(0), "own")
print(pd.DataFrame(res).T[["corr", "mae", "catch20", "corr_cheapWRTE"]].astype(float).round(3).to_string())

# (b) sharpening: own ~ budget * v2^k / sum(v2^k) within slate-group
def sharpen(df, pred, k):
    F = np.log(np.clip(pred, 1e-4, None)) * k
    b = df.assign(_y=df.own * (df.in_pool & (df.proj > 0))).groupby(["slate_id", "grp"])._y.sum().groupby("grp").mean().to_dict()
    return allocate(df, F, b)
out = {}
for s in sorted(H.season.unique()):
    tr = (H.season != s).to_numpy()
    best = min([1.0, 1.1, 1.2, 1.3, 1.4, 1.5], key=lambda k: metrics(H[tr], sharpen(H[tr], H.v2[tr].values, k), "own")["mae"])
    out[s] = best
print("LOSO-chosen exponents (by MAE):", out)
p = np.zeros(len(H))
for s, k in out.items():
    te = (H.season == s).to_numpy(); p[te] = sharpen(H[te], H.v2[te].values, k)
print(pd.DataFrame({"v2": metrics(H, H.v2, "own"), "v2 sharpened (LOSO k)": metrics(H, p, "own")}).T[["corr","mae","catch20","bias20","corr_cheapWRTE"]].astype(float).round(3))
