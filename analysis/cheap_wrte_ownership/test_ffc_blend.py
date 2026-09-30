"""Step 5 (2026 only; history has no FFC): does the public FFC ownership projection carry the cheap WR/TE signal
the field prices in? Blend v2 linear (trained 2021-25 only, never saw 2026) with RAW FFC ownership (external,
not fit on 2026, so no in-sample leak) in log space, renormalised to v2's group budgets. alpha chosen
leave-one-week-out. Compared with the live FFC artifact (fit on wk1-2: only wk3 is fair for it)."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ownership_v2"))
from common import R, metrics, allocate  # noqa

D = R / "data/fc_history/derived/ownership_v2"
Y = pd.read_parquet(D / "y2026.parquet").reset_index(drop=True)
P = pd.read_parquet(D / "y2026_preds.parquet").reset_index(drop=True)
assert (Y.player_id.values == P.player_id.values).all()
v2 = P.p_new_realized_linear.values
ffc = Y.ffc_own_pct.values
listed = Y.ffc_listed.fillna(0).astype(bool).values if "ffc_listed" in Y else np.isfinite(ffc)
bud = Y.assign(_v=v2).groupby(["slate_id", "grp"])._v.sum()

def blend(df, a, v, f):
    fl = np.where(np.isfinite(f) & (f > 0), f, np.nan)
    # FFC missing -> fall back to v2 (fail-safe no-op for that player)
    F = np.where(np.isnan(fl), np.log(np.clip(v, .05, None)), (1 - a) * np.log(np.clip(v, .05, None)) + a * np.log(np.clip(fl, .05, None)))
    b = df.assign(_v=v).groupby(["slate_id", "grp"])._v.sum().groupby(level=1).mean().to_dict()
    out = np.zeros(len(df))
    for (sid, g), ix in df.groupby(["slate_id", "grp"]).indices.items():
        sub = df.iloc[ix]; out[ix] = allocate(sub, F[ix], {g: bud[(sid, g)]})
    return out

print("FFC coverage (share of rows with FFC value, share of cheap WR/TE ownership mass covered):",
      round(np.isfinite(ffc).mean(), 3), round(Y.own[np.isfinite(ffc) & Y.pos.isin(["WR","TE"]) & (Y.salary<5500)].sum() / Y.own[Y.pos.isin(["WR","TE"]) & (Y.salary<5500)].sum(), 3))
A = [0, .2, .3, .4, .5, .6, .7]
cw = lambda d, p: metrics(d, p, "own")["corr_cheapWRTE"]
chosen, pb = {}, np.zeros(len(Y))
for w in (1, 2, 3):
    tr = (Y.week != w).to_numpy()
    a = max(A, key=lambda a: metrics(Y[tr], blend(Y[tr], a, v2[tr], ffc[tr]), "own")["corr"])
    chosen[w] = a; te = ~tr; pb[te] = blend(Y[te], a, v2[te], ffc[te])
print("leave-one-week-out alpha (picked on overall corr, not cheap corr):", chosen)
rows = {}
for w in (1, 2, 3, "all"):
    m = (Y.week == w).to_numpy() if w != "all" else np.ones(len(Y), bool)
    d = Y[m]
    for name, p in [("v2 linear", v2), ("v2 x raw FFC blend (LOWO)", pb), ("raw FFC alone", np.nan_to_num(ffc)),
                    ("live FFC artifact", P.p_live_FFC_artifact.values), ("as-built pre-lock", P["p_as-built_pre-lock"].values)]:
        mm = metrics(d, p[m], "own")
        rows[(w, name)] = {k: mm[k] for k in ["corr", "mae", "catch20", "bias20", "corr_cheapWRTE", "top10pct"]}
t = pd.DataFrame(rows).T.astype(float).round(3)
print(t.to_string())
for a in A:
    p = blend(Y, a, v2, ffc); m = metrics(Y, p, "own")
    print(f"fixed alpha {a}: corr {m['corr']:.3f} mae {m['mae']:.3f} cheapWRTE {m['corr_cheapWRTE']:.3f}")
c = Y.pos.isin(["WR", "TE"]) & (Y.salary < 5500) & (Y.own >= 10)
print("cheap WR/TE 10pct+ real: mean own %.1f | v2 %.1f | blend %.1f | raw FFC %.1f" % (Y.own[c].mean(), v2[c.values].mean(), pb[c.values].mean(), np.nan_to_num(ffc)[c.values].mean()))
