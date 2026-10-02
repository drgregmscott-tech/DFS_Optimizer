"""Score the fresh real-pipeline 2021-25 rebuilds (WR-out ON, Friday status pinned).
off = final - wrw_wr_delta_pts (post-hoc add; verified identical to an OFF build on 5 weeks), on = final.
Slice = WR-out teammates the mechanism touched. Variants re-derived post hoc with apply_wr_replacement(params=...)
on the same rebuilt pools. LOSO points scale refit two ways (least squares as eval_scale.py; bias-match to the
unaffected-WR control as wr_pipeline.py). Full-population + RB/TE WRW sanity."""
import io, contextlib, json, sys
from pathlib import Path
import numpy as np, pandas as pd
D = Path(__file__).resolve().parent; CODE = D.parents[1]; DATA = Path(r"C:\Users\gmsco\Desktop\DFS_Optimizer")
sys.path.insert(0, str(CODE / "scripts"))
import statline_model as sm
A = pd.concat([pd.read_csv(p, dtype={"player_id": str}) for p in sorted((D / "hist_builds/on").glob("proj_*.csv"))],
              ignore_index=True)
S = pd.concat([pd.read_parquet(CODE / f"data/weekly_stats_{y}.parquet") for y in range(2021, 2026)])
S = S[S.season_type == "REG"].fillna(0)
S["dk"] = S.fantasy_points_ppr + 3 * (S.rushing_yards >= 100) + 3 * (S.receiving_yards >= 100) + 3 * (S.passing_yards >= 300)
act = S.set_index(["season", "week", "player_id"]).dk
PN = pd.read_csv(DATA / "analysis/inactives/status_panel_2016_2025.csv")
inact = PN.set_index(["season", "week", "gsis_id"]).inactive
A["act"] = [act.get((s, w, p), np.nan) for s, w, p in zip(A.season, A.week, A.player_id)]
A["inactive"] = [bool(inact.get((s, w, p), np.isnan(a))) for s, w, p, a in zip(A.season, A.week, A.player_id, A.act)]
A["act"] = A.act.fillna(0.0)
SK = A.position.isin(["QB", "RB", "WR", "TE"]) & (A.final_projection > 0)
print(f"{A[['season','week']].drop_duplicates().shape[0]} weeks rebuilt, {SK.sum()} skill rows with proj>0")

# ---- variants (post hoc, same pinned status) ----
PF = json.loads((CODE / "data/wrw_wr_params.json").read_text())
K0 = PF["points_scale"]
VAR = {"shipped WR2/WR3 (rank3+ = .151)": PF["tgt_frac_by_rank"],
       "WR2/WR3 only, WR4+ = 0": {"WR": {"2": .143, "3": .151}},
       "WR1+WR2+WR3": {"WR": {"1": .078, "2": .143, "3": .151}},
       "all fitted cells (WR1/2/3, TE, RB)": {"WR": {"1": .078, "2": .143, "3": .151}, **{k: v for k, v in PF["_fitted_not_applied"].items() if k != "WR"}}}
P = pd.read_csv(DATA / "analysis/inactives/status_panel_2016_2025.csv")
P = P[P.desig.isin(["Out", "Doubtful", "IR/Reserve(no desig)"]) | (P.status == "RES")]
for v in VAR: A[v] = 0.0
for (s, w), g in A.groupby(["season", "week"]):
    st = P[(P.season == s) & (P.week == w)]
    stat = pd.DataFrame({"player_id": st.gsis_id.astype(str), "team": st.team, "position": st.position, "status": "OUT"})
    pool = g[g.position.isin(["RB", "WR", "TE"])]
    for v, fr in VAR.items():
        pp = dict(PF, tgt_frac_by_rank=fr, points_scale=1.0)
        if v.startswith("WR2/WR3 only"): pp["rank_clip"] = 99
        with contextlib.redirect_stdout(io.StringIO()):
            r = sm.apply_wr_replacement(pool, s, w, stat, params=pp)
        d = r.wrw_wr_delta_pts.where(r.sigma > 0, 0.0)
        A.loc[r.index, v] = d
first = list(VAR)[0]
chk = (A[first] * K0 - A.wrw_wr_delta_pts).abs().max()
print(f"consistency: post-hoc shipped variant x{K0} vs in-build delta, max abs diff {chk:.2e}")
A["off"] = A.final_projection - A.wrw_wr_delta_pts
CT = SK & (A.position == "WR") & (A[list(VAR)].sum(axis=1) == 0) & ~A.inactive

def stats(e): return f"bias {e.mean():+.2f} MAE {e.abs().mean():.3f} RMSE {np.sqrt((e**2).mean()):.3f}"
def loso(x, dcol, how):
    out = []
    for s in sorted(x.season.unique()):
        tr, te = x[x.season != s], x[x.season == s]
        e = tr.act - tr.off
        if how == "ls": k = (e * tr[dcol]).sum() / (tr[dcol] ** 2).sum()
        else:
            c = A[CT & (A.season != s)]; k = (e.mean() - (c.act - c.off).mean()) / tr[dcol].mean()
        out.append(te.assign(k=k, p=te.off + k * te[dcol]))
    return pd.concat(out)
cbias = (A[CT].act - A[CT].off).mean()
print(f"control (unaffected active WRs) n={CT.sum()} bias {cbias:+.2f}")
for v in VAR:
    for inc in (False, True):
        x = A[SK & (A[v] > 0) & (inc | ~A.inactive)].copy()
        lab = "incl T-90 inactive as 0" if inc else "active"
        print(f"\n== {v} | {lab} | n={len(x)} rows")
        print(f"   off            {stats(x.act - x.off)}")
        print(f"   fixed k={K0}    {stats(x.act - (x.off + K0 * x[v]))}  seasons RMSE better "
              f"{sum(np.sqrt(((g.act-g.off-K0*g[v])**2).mean()) < np.sqrt(((g.act-g.off)**2).mean()) for _, g in x.groupby('season'))}/5")
        for how in ("ls", "biasmatch"):
            o = loso(x, v, how)
            better = sum(np.sqrt(((g.act - g.p) ** 2).mean()) < np.sqrt(((g.act - g.off) ** 2).mean()) for _, g in o.groupby("season"))
            print(f"   LOSO k[{how:9s}] {o.k.min():.2f}-{o.k.max():.2f}  {stats(o.act - o.p)}  seasons RMSE better {better}/5")
        if v == first and not inc:
            x["on"] = x.off + K0 * x[v]
            for s, g in x.groupby("season"):
                print(f"     {s} n={len(g):3d} off {stats(g.act-g.off)} | on {stats(g.act-g.on)}")
# rank 4+ = rows the shipped variant touches but the "WR4+ = 0" variant does not
x = A[SK & (A[first] > 0) & ~A.inactive].copy()
deep = x["WR2/WR3 only, WR4+ = 0"] == 0
for nm, g in [("rank 2-3", x[~deep]), ("rank 4+", x[deep])]:
    print(f"\n shipped variant, {nm}: n={len(g)} base proj {g.off.mean():.2f} | off {stats(g.act-g.off)} | on {stats(g.act-g.off-K0*g[first])}")
for nm, g in [("rank 4+ incl inactive", A[SK & (A[first] > 0) & (A['WR2/WR3 only, WR4+ = 0'] == 0)])]:
    print(f" {nm}: n={len(g)} inactive share {g.inactive.mean():.2f} | off {stats(g.act-g.off)} | on {stats(g.act-g.off-K0*g[first])}")

# ---- full population (skill, proj>0) ----
F = A[SK]
print(f"\nFULL population n={len(F)}: off {stats(F.act-F.off)} corr {F.off.corr(F.act):.4f} | on {stats(F.act-F.final_projection)} corr {F.final_projection.corr(F.act):.4f}")
Fa = F[~F.inactive]
print(f"FULL active n={len(Fa)}: off {stats(Fa.act-Fa.off)} corr {Fa.off.corr(Fa.act):.4f} | on {stats(Fa.act-Fa.final_projection)} corr {Fa.final_projection.corr(Fa.act):.4f}")
for pos in ("WR", "TE", "RB"):
    g = Fa[Fa.position == pos]
    print(f"  {pos} n={len(g)}: off {stats(g.act-g.off)} | on {stats(g.act-g.final_projection)}")
# ---- RB / TE WRW still behaving in the same fresh builds ----
for col, nm in (("wrw_delta_pts", "WRW RB"), ("wrw_te_delta_pts", "WRW TE")):
    g = A[SK & (A[col] > 0) & ~A.inactive]
    print(f"{nm} affected active n={len(g)}: without {stats(g.act-(g.off-g[col]))} | with {stats(g.act-g.off)}")
ov = A[(A.wrw_wr_delta_pts > 0) & ((A.wrw_delta_pts > 0) | (A.wrw_te_delta_pts > 0))]
print("rows touched by WR-out AND RB/TE WRW:", len(ov))
A.to_parquet(D / "scored.parquet")
