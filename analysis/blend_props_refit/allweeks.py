"""All-weeks skill-only salary pull on CURRENT-code history projections (data/fc_history/derived/ourproj, regenerated
2026-09-26, pre-blend/pre-QB-recal, props off -- none exist historically). LOSO 2021-25; 2026 wk1-2 (ourproj) + wk3
(lineup_replay leak-free rebuild, props on) as second held-out. final = E + a + w*(S - E), S = live config salary line.
FC-DERIVED: local only."""
import glob, io, contextlib, sys, re, json
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import spearmanr
HERE = Path(__file__).resolve().parent; R = HERE.parents[1]
sys.argv = ["x", "d_sal"]; sys.path.insert(0, str(R / "analysis/projection_v2")); sys.path.insert(0, str(HERE))
import task1_shrinkage as T1
with contextlib.redirect_stdout(io.StringIO()):
    import run
SL = run.SL
fr = []
for f in glob.glob(str(R / "data/fc_history/derived/ourproj/proj_*.csv")):
    d = pd.read_csv(f, dtype={"player_id": str}, usecols=["season", "week", "player_id", "player_name", "position", "team", "salary", "final_projection"])
    fr.append(d)
P = pd.concat(fr); P = P[P.position.isin(["RB", "WR", "TE"])]
H = T1.load_hist()[["season", "week", "player_id", "act", "played", "fc"]]
P = P.merge(H, on=["season", "week", "player_id"], how="inner")
P = P[P.played & P.act.notna()]
w3 = run.A[(run.A.wk == 3) & (run.A.pg == "SKILL")].assign(season=2026, week=3, fc=np.nan)[["season", "week", "player_id", "player_name", "position", "team", "salary", "final_projection", "act", "fc"]]
P = pd.concat([P, w3], ignore_index=True)
P = P.drop_duplicates(["season", "week", "player_id"])
P["E"] = P.final_projection
P = P[(P.E > 0) & ((P.E >= 3) | (P.salary >= 4000))].copy()
P["S"] = P.salary / 1000 * P.position.map(lambda p: SL[p][0]) + P.position.map(lambda p: SL[p][1])
P["tier"] = pd.cut(P.salary, [0, 4999, 6499, 99999], labels=["<5k", "5-6.5k", "6.5k+"]).astype(str)
P["wb"] = np.where(P.week <= 4, "wk1-4", "wk5-18")
P["pg2"] = np.where(P.position == "RB", "RB", "WRTE")
P["d"] = P.S - P.E; P["y"] = P.act - P.E
print("rows by season:", P.groupby("season").size().to_dict(), " weeks 2024:", sorted(P[P.season == 2024].week.unique()))
print("raw residual slope (act-E ~ S-E) by season:", {s: round(np.polyfit(g.d, g.y, 1)[0], 3) for s, g in P.groupby("season")})

LAM = 30
def fit(t):
    X = np.column_stack([np.ones(len(t)), t.d]); return np.linalg.solve(X.T @ X + np.diag([0, LAM]) * 1.0 + np.diag([LAM, 0]), X.T @ t.y.values)
VARIANTS = {"global": [], "tier": ["tier"], "wb": ["wb"], "tier*wb": ["tier", "wb"], "pos2*tier": ["pg2", "tier"], "cheap_only(<5k)": None}
def predict(tr, te, keys):
    F = te.E.copy()
    if keys is None:  # only <5k gets a pull, fit on <5k
        a, w = fit(tr[tr.tier == "<5k"]); m = te.tier == "<5k"; F[m] = (te.E + a + w * te.d)[m]
        return F.clip(lower=0), {"<5k": (a, w)}
    if not keys:
        a, w = fit(tr); return (te.E + a + w * te.d).clip(lower=0), {"all": (a, w)}
    W = {}
    for k, g in tr.groupby(keys):
        W[k] = fit(g)
    for k, g in te.groupby(keys):
        if k in W: a, w = W[k]; F[g.index] = g.E + a + w * g.d
    return F.clip(lower=0), W
def metrics(te, F):
    te = te.assign(F=F); sk = te.season * 100 + te.week
    top = lambda c: te.assign(sk=sk).groupby("sk", group_keys=False).apply(lambda g: g.nlargest(24, c).act.mean()).mean()
    top_cheap = lambda c: te[te.salary < 5000].assign(sk=sk).groupby("sk", group_keys=False).apply(lambda g: g.nlargest(8, c).act.mean()).mean()
    sp = lambda c: te.assign(sk=sk).groupby("sk").apply(lambda g: spearmanr(g[c], g.act)[0]).mean()
    return dict(n=len(te), mae0=(te.E - te.act).abs().mean(), mae1=(te.F - te.act).abs().mean(),
                bias0=(te.E - te.act).mean(), bias1=(te.F - te.act).mean(), sp0=sp("E"), sp1=sp("F"),
                top24_0=top("E"), top24_1=top("F"), cheap8_0=top_cheap("E"), cheap8_1=top_cheap("F"))
out = []; final_w = {}
Pi = P.reset_index(drop=True)
for name, keys in VARIANTS.items():
    for s in [2021, 2022, 2023, 2024, 2025, 2026]:
        tr = Pi[(Pi.season != s) & (Pi.season <= 2025)]; te = Pi[Pi.season == s]
        F, W = predict(tr, te, keys)
        out.append(dict(variant=name, season=s, **metrics(te, F)))
    final_w[name] = predict(Pi[Pi.season <= 2025], Pi.iloc[:1], keys)[1]
O = pd.DataFrame(out); O["dmae"] = O.mae1 - O.mae0
pd.set_option("display.width", 250)
print("== per held-out season (2021-25 LOSO; 2026 = fit on all 2021-25) ==")
print(O.round(3).to_string(index=False))
h = O[O.season <= 2025]
print("== LOSO summary (n-weighted) ==")
print(h.groupby("variant").apply(lambda g: pd.Series({"dmae": np.average(g.dmae, weights=g.n), "seasons_better": (g.dmae < 0).sum(),
      "dtop24": (g.top24_1 - g.top24_0).mean(), "dcheap8": (g.cheap8_1 - g.cheap8_0).mean(), "dsp": (g.sp1 - g.sp0).mean(),
      "bias1": np.average(g.bias1, weights=g.n)})).round(3).to_string())
print("== final weights (fit 2021-25) ==")
for k, v in final_w.items(): print(k, {str(kk): tuple(np.round(vv, 3)) for kk, vv in v.items()})
# per-cell LOSO breakdown for best structured variant: pos2*tier and tier*wb
for keys in [["pg2", "tier"], ["tier", "wb"]]:
    rows = []
    for s in [2021, 2022, 2023, 2024, 2025, 2026]:
        tr = Pi[(Pi.season != s) & (Pi.season <= 2025)]; te = Pi[Pi.season == s].copy()
        te["F"], _ = predict(tr, te, keys)
        for k, g in te.groupby(keys):
            rows.append(dict(cell=k, season=s, n=len(g), d=(g.F - g.act).abs().mean() - (g.E - g.act).abs().mean()))
    C = pd.DataFrame(rows)
    print(f"== cell dMAE by season, keys={keys} ==")
    print(C.pivot_table(index="cell", columns="season", values="d").round(3).to_string())
json.dump({k: {str(kk): list(map(float, vv)) for kk, vv in v.items()} for k, v in final_w.items()}, open(HERE / "allweeks_weights.json", "w"), indent=1)
