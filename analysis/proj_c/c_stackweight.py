"""C follow-up: is the only ranking-changing candidate (re-weighting engine vs stack delta) real?
usage: python analysis/proj_c/c_stackweight.py <shipped_dir>   (reuses c_calib.frame/metrics)
 (1) fitted act ~ a + b*eng + c*delta by week (stability of b, c)
 (2) fixed-grid, no fitting: p = eng + lam*delta, and p = final + g*(eng - pos-slate-mean eng)  (spread boost of the engine part)
 (3) level-neutral LOWO version of e_eng_stack: rescale so train-week mean equals shipped train mean
 (4) paired bootstrap over position x slate cells / slates of the rank deltas.
"""
import sys
import numpy as np, pandas as pd
sys.argv = sys.argv[:2]
import c_calib as C

rng = np.random.default_rng(1)
D = C.frame(); D = D[D.position != "DST"].copy()
Dd = C.dedup(D)

print("== (1) act ~ a + b*eng + c*delta (dedup) ==")
for w in (1, 2, None):
    g = Dd if w is None else Dd[Dd.week == w]
    for p in [None] + C.SK:
        h = g if p is None else g[g.position == p]
        X = np.c_[np.ones(len(h)), h.eng, h.stack_delta]; c = np.linalg.lstsq(X, h.act, rcond=None)[0]
        print(f"wk{w or 'ALL'} {p or 'pooled':6s} n={len(h):3d} a={c[0]:+6.2f} b_eng={c[1]:.3f} c_delta={c[2]:+.3f}")

print("\n== (2a) fixed grid p = eng + lam*delta, per test week (no fitting) ==")
rows = []
for lam in (0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5):
    D["_p"] = D.eng + lam * D.stack_delta
    for w in (1, 2):
        r = C.metrics(D[D.week == w], "_p"); r.update(lam=lam, wk=w); rows.append(r)
R = pd.DataFrame(rows)
print(R[["lam", "wk", "bias", "mae", "rmse", "cell_sp", "cell_top", "pool_sp", "top20", "val_sp", "vtop20"]].round(3).to_string(index=False))

print("\n== (2b) fixed grid p = final + g*(eng - mean eng within slate x pos) : expand only the engine spread ==")
D["eng_c"] = D.eng - D.groupby(["slate_id", "position"]).eng.transform("mean")
rows = []
for gm in (0, 0.1, 0.2, 0.3, 0.5):
    D["_p"] = D.final_projection + gm * D.eng_c
    for w in (1, 2):
        r = C.metrics(D[D.week == w], "_p"); r.update(g=gm, wk=w); rows.append(r)
R2 = pd.DataFrame(rows)
print(R2[["g", "wk", "bias", "mae", "rmse", "cell_sp", "cell_top", "pool_sp", "top20", "val_sp", "vtop20"]].round(3).to_string(index=False))


def fit_neutral(tr):
    X = np.c_[np.ones(len(tr)), tr.eng, tr.stack_delta]; c = np.linalg.lstsq(X, tr.act, rcond=None)[0]
    m_ship = tr.final_projection.mean(); m_fit = (X @ c).mean()
    return c, lambda d: np.c_[np.ones(len(d)), d.eng, d.stack_delta] @ c - m_fit + m_ship


print("\n== (3) level-neutral eng/stack reweight, LOWO ==")
for tw in (1, 2):
    tr = Dd[Dd.week != tw]; te = D[D.week == tw].copy()
    c, f = fit_neutral(tr); te["_p"] = f(te); te["_b"] = te.final_projection
    a, b = C.metrics(te, "_p"), C.metrics(te, "_b")
    print(f"test wk{tw} fit b_eng={c[1]:.3f} c_delta={c[2]:.3f} (ratio c/b {c[2]/c[1]:.2f}) | "
          + " ".join(f"{k} {a[k]-b[k]:+.3f}" for k in ("bias", "mae", "rmse", "cell_sp", "cell_top", "pool_sp", "top20", "val_sp", "vtop20")))

print("\n== (4) paired bootstrap of rank gains (fixed lam=0.5 and LOWO neutral reweight vs shipped) ==")


def cellstats(te, col):
    out = []
    for (sid, p), h in te.groupby(["slate_id", "position"]):
        if len(h) >= 6:
            out.append(dict(sid=sid, p=p, sp=C.sp(h[col], h.act), top=h.nlargest(C.NTOP[p], col).act.mean()))
    return pd.DataFrame(out)


for lab in ("lam0.5", "lowo_neutral"):
    parts = []
    for tw in (1, 2):
        te = D[D.week == tw].copy()
        te["_p"] = te.eng + 0.5 * te.stack_delta if lab == "lam0.5" else fit_neutral(Dd[Dd.week != tw])[1](te)
        A, B = cellstats(te, "_p"), cellstats(te, "final_projection")
        parts.append(A.assign(dsp=A.sp - B.sp, dtop=A.top - B.top))
    P = pd.concat(parts)
    for m in ("dsp", "dtop"):
        d = P[m].to_numpy(); bs = [rng.choice(d, len(d)).mean() for _ in range(4000)]
        sl = P.sid.to_numpy(); us = np.unique(sl)
        bs2 = [np.concatenate([d[sl == s] for s in rng.choice(us, len(us))]).mean() for _ in range(4000)]
        print(f"{lab:13s} {m}: mean {d.mean():+.3f} cells>0 {(d>0).sum()}/{len(d)} (ties {(d==0).sum()}) cellCI [{np.percentile(bs,2.5):+.3f},{np.percentile(bs,97.5):+.3f}] slateCI [{np.percentile(bs2,2.5):+.3f},{np.percentile(bs2,97.5):+.3f}]")
    print(P.groupby("p")[["dsp", "dtop"]].mean().round(3).to_dict("index"))

print("\n== (5) per-position cell deltas vs shipped for fixed lam (engine-only=0, 0.5) ==")
for lam in (0, 0.5):
    parts = []
    for tw in (1, 2):
        te = D[D.week == tw].copy(); te["_p"] = te.eng + lam * te.stack_delta
        A, B = cellstats(te, "_p"), cellstats(te, "final_projection")
        parts.append(A.assign(dsp=A.sp - B.sp, dtop=A.top - B.top, wk=tw))
    P = pd.concat(parts)
    print(f"lam={lam}:", P.groupby(["p", "wk"])[["dsp", "dtop"]].mean().round(3).unstack().to_string())

print("\n== (6) TE check: cell count, and selection-neutral cut (eng>8 OR final>8, all TE with actual) ==")
L = pd.read_csv(C.REPO / "data/projection_error_log.csv", dtype={"player_id": str})
T = []
for sid in C.SL:
    f = pd.read_csv(C.S / f"final_projections_dk_{sid}.csv", dtype={"player_id": str})
    f = f[(f.position == "TE") & ((f.final_projection > 8) | (f.engine_projection > 8))]
    a = L[L.slate_id == sid].drop_duplicates("player_id").set_index("player_id").actual_fpts
    f = f.assign(act=f.player_id.map(a), slate_id=sid, week=int(sid.split("_wk")[1][0])).dropna(subset=["act"]); T.append(f)
T = pd.concat(T)
for sid, h in T.groupby("slate_id"):
    print(f"{sid:36s} n={len(h):2d} spear final {C.sp(h.final_projection, h.act):+.3f} eng {C.sp(h.engine_projection, h.act):+.3f} | top3 act final {h.nlargest(3,'final_projection').act.mean():5.1f} eng {h.nlargest(3,'engine_projection').act.mean():5.1f}")
