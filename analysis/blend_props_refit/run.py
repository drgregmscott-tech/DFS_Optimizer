"""Early-season salary blend vs props-on / market-informed projections. Local only (FC-derived). No tracked edits.
A) 2026 wk1-3 leak-free rebuilds (analysis/lineup_replay/builds/old = no blend) vs actual DK pts.
B) LOWO shrunk refit on 2026.  C) History proxy: blend on top of FC projection (market-informed) LOSO 2021-25."""
import json, sys, re
from pathlib import Path
import numpy as np, pandas as pd
R = Path(__file__).resolve().parents[2]
sys.argv = ["x", "d_sal"]; sys.path.insert(0, str(R / "analysis/projection_v2"))
import task1_shrinkage as T1
cfg = json.loads((R / "data/early_season_blend_config.json").read_text())
SL = {p: tuple(v) for p, v in cfg["sal_line"].items()}; WD = cfg["weeks_disabled_2026-09-29"]
def norm(s): return re.sub(r"[^a-z]", "", re.sub(r"\b(jr|sr|ii|iii|iv|v)\b\.?", "", str(s).lower()))
pd.set_option("display.width", 220)

def S_of(d): return d.salary / 1000 * d.position.map(lambda p: SL[p][0]) + d.position.map(lambda p: SL[p][1])
def blend(E, S, pg, wk):
    p = WD.get(str(wk));
    if p is None: return E.copy()
    a = pg.map(lambda g: p[g]["a"]); w = pg.map(lambda g: p[g]["w"])
    return (E + a + w * (S - E)).clip(lower=0)

# ---------- A: 2026 rebuilds ----------
rows = []
for wk, date in [(1, "13Sep2026"), (2, "20Sep2026"), (3, "27Sep2026")]:
    seen = set()
    for sl in ["main", "early", "afternoon"]:
        sid = f"dk_classic_wk{wk}_{sl}_{date}"
        d = pd.read_csv(R / f"analysis/lineup_replay/builds/old/final_projections_dk_{sid}.csv", dtype={"player_id": str})
        d = d[d.position.isin(["QB", "RB", "WR", "TE"])]
        rf = R / f"data/results_raw_dk_2026_wk{wk}{'' if (sl=='main' and wk<3) else '_'+sl}.csv"
        act = pd.read_csv(rf); act = dict(zip(act.player_name.map(norm), act.actual_fpts))
        d["act"] = d.player_name.map(norm).map(act)
        pf = R / f"data/props/audit_{sid}.csv"
        if pf.exists():
            pa = pd.read_csv(pf, dtype={"player_id": str}); d["props"] = d.player_id.map(dict(zip(pa.player_id, pa.props_matched))).fillna(False)
        else:
            d["props"] = False
        d = d[~d.player_id.isin(seen)]; seen |= set(d.player_id)
        d["wk"] = wk; d["slate"] = sl; rows.append(d)
A = pd.concat(rows)
A = A[A.act.notna() & ((A.final_projection >= 3) | (A.salary >= 4000)) & (A.final_projection > 0)].copy()
A["E"] = A.final_projection; A["S"] = S_of(A); A["pg"] = np.where(A.position == "QB", "QB", "SKILL")
A["B"] = [0] * len(A)
A["B"] = pd.concat([blend(g.E, g.S, g.pg, wk) for wk, g in A.groupby("wk")])
A["B2"] = blend(A.E, A.S, A.pg, 2)  # wk2 weights applied to wk3 = "what if"
A["tier"] = pd.cut(A.salary, [0, 4999, 6499, 99999], labels=["<5k", "5-6.5k", "6.5k+"])
A["props"] = A.props.astype(bool)
def summ(g):
    r = {"n": len(g)}
    for k, c in [("E", "E"), ("blend", "B"), ("S", "S")]:
        r[f"mae_{k}"] = (g[c] - g.act).abs().mean(); r[f"bias_{k}"] = (g[c] - g.act).mean()
    x = g.S - g.E; y = g.act - g.E
    r["slope(act-E ~ S-E)"] = np.polyfit(x, y, 1)[0] if len(g) > 5 else np.nan
    r["se"] = np.std(y - np.polyval(np.polyfit(x, y, 1), x)) / (x.std() * np.sqrt(len(g))) if len(g) > 5 else np.nan
    return pd.Series(r)
print("== A1: 2026 rebuilds (no blend = E; current blend weights; salary line S). unique players per week ==")
print(A.groupby("wk").apply(summ).round(3).to_string())
print(A.groupby(["wk", "pg"]).apply(summ).round(3).to_string())
print(A.groupby(["wk", "position"]).apply(summ).round(3).to_string())
print(A.groupby(["wk", "tier"], observed=True).apply(summ).round(3).to_string())
w3 = A[A.wk == 3]
print("== A2: wk3 only (props exist only for wk3 classic), split by props_matched ==")
print(w3.groupby(["props", "pg"]).apply(summ).round(3).to_string())
print("wk3 with wk2 weights applied: MAE E %.3f  B2 %.3f" % ((w3.E - w3.act).abs().mean(), (w3.B2 - w3.act).abs().mean()))
for pr in [True, False]:
    g = w3[w3.props == pr]; print(f"  props={pr} n={len(g)} MAE E {(g.E-g.act).abs().mean():.3f} B2 {(g.B2-g.act).abs().mean():.3f}")
print("props coverage by week:", A.groupby("wk").props.mean().round(2).to_dict())

# ---------- B: LOWO shrunk refit on 2026 ----------
print("== B: leave-one-week-out refit on 2026, (a,w) per pg, ridge on w and a ==")
for lam in [0, 30, 100, 300, 1000]:
    out = []
    for hw in [1, 2, 3]:
        tr, te = A[A.wk != hw], A[A.wk == hw].copy()
        te["F"] = te.E
        for pg in ["QB", "SKILL"]:
            t = tr[tr.pg == pg]; X = np.column_stack([np.ones(len(t)), t.S - t.E]); y = (t.act - t.E).values
            a, w = np.linalg.solve(X.T @ X + lam * np.eye(2), X.T @ y)
            m = te.pg == pg; te.loc[m, "F"] = (te.E + a + w * (te.S - te.E))[m].clip(lower=0)
            out.append(dict(hold=hw, pg=pg, a=a, w=w))
        print(f"  lam={lam:5} hold wk{hw}: MAE E {(te.E-te.act).abs().mean():.3f} -> {(te.F-te.act).abs().mean():.3f}", end="; ")
        print(" ".join(f"{o['pg']} a={o['a']:+.2f} w={o['w']:+.3f}" for o in out[-2:]))

# ---------- C: history proxy ----------
H = T1.load_hist(); H = H[H.played & H.act.notna()].copy()
H["position"] = H.pos; H["S"] = S_of(H); H["pg"] = np.where(H.pos == "QB", "QB", "SKILL")
print("== C: history. residual slope on (S - base), base = harness E vs FC projection (market-informed proxy) ==")
res = []
for base in ["E", "fc"]:
    Hb = H[H[base].notna() & ((H[base] >= 3) | (H.salary >= 4000))]
    for wk in [1, 2, 3]:
        for pg in ["QB", "SKILL"]:
            g = Hb[(Hb.week == wk) & (Hb.pg == pg)]
            # LOSO over 2021-25, then 2026 held out (fit on all 2021-25)
            maes = []
            for s in [2021, 2022, 2023, 2025, 2026]:
                tr = g[(g.season != s) & (g.season <= 2025)]; te = g[g.season == s]
                if len(te) == 0: continue
                X = np.column_stack([np.ones(len(tr)), tr.S - tr[base]]); y = (tr.act - tr[base]).values
                a, w = np.linalg.solve(X.T @ X + np.diag([0, 30]), X.T @ y)
                F = (te[base] + a + w * (te.S - te[base])).clip(lower=0)
                maes.append((s, len(te), (te[base] - te.act).abs().mean(), (F - te.act).abs().mean(), a, w))
            M = pd.DataFrame(maes, columns=["s", "n", "mae0", "mae1", "a", "w"]); h = M[M.s <= 2025]
            n26 = M[M.s == 2026]
            res.append(dict(base=base, wk=wk, pg=pg, n=int(h.n.sum()), loso_mae0=np.average(h.mae0, weights=h.n),
                            loso_mae1=np.average(h.mae1, weights=h.n), seasons_better=int((h.mae1 < h.mae0).sum()),
                            w_mean=h.w.mean(), n26=int(n26.n.sum()) if len(n26) else 0,
                            mae0_26=n26.mae0.iloc[0] if len(n26) else np.nan, mae1_26=n26.mae1.iloc[0] if len(n26) else np.nan))
print(pd.DataFrame(res).round(3).to_string(index=False))
# 2026 in-history: harness E vs our rebuild E -- is the 2026 build a different animal than the harness?
print("== bias of base by week, history vs 2026 rebuild ==")
print(H[H.week <= 3].groupby(["week", H.season == 2026]).apply(lambda g: pd.Series({"bias_E": (g.E-g.act).mean(), "bias_fc": (g.fc-g.act).mean(), "n": len(g)})).round(2).to_string())
