"""D sanity checks: paired cluster-bootstrap of LOWO pinball-10 gains; dart-flag impact of lowering p10.
usage: python analysis/proj_d/d_check.py <shipped_dir>"""
import sys, numpy as np, pandas as pd
sys.argv = sys.argv[:2]
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location("d", pathlib.Path(__file__).with_name("d_calib.py")); d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
rng = np.random.default_rng(1)
for cut in (8, 3):
    D = d.frame(cut)
    parts = []
    for w in (1, 2):
        tr, te = D[D.week != w], D[D.week == w].copy()
        y = te.act.to_numpy()
        pb = lambda q: np.maximum(.1 * (y - q), -.9 * (y - q))
        te["base"] = pb(te.statline_p10.to_numpy())
        te["alo"] = pb(d.f_k_lower_only(tr)(te)[0]); te["nk"] = pb(d.f_sigma_normal_k(tr)(te)[0])
        parts.append(te)
    T = pd.concat(parts, ignore_index=True)
    g = [v.index.to_numpy() for _, v in T.groupby("cl")]
    for c in ("alo", "nk"):
        diff = (T[c] - T.base).to_numpy()
        bs = [diff[np.concatenate([g[i] for i in rng.integers(0, len(g), len(g))])].mean() for _ in range(2000)]
        print(f"cut>{cut} {c}: mean pb10 change {diff.mean():+.3f} 95%CI [{np.percentile(bs,2.5):+.3f},{np.percentile(bs,97.5):+.3f}] (neg=better); per-week", [round(x, 3) for x in T.groupby('week').apply(lambda t: (t[c]-t.base).mean())])
# dart flag impact (optimizer.py:2054-2057, threshold 1.0 in mme_gpp preset) on shipped pools
for sid in ("dk_classic_wk2_main_20Sep2026", "dk_classic_wk1_main_13Sep2026"):
    f = pd.read_csv(d.S / f"final_projections_dk_{sid}.csv"); f = f[f.position.isin(d.SK) & (f.final_projection > 0)]
    m, p10 = f.final_projection, f.statline_p10
    for k in (1.0, 1.25, 1.44):
        q = np.maximum(m - k * (m - p10), 0)
        print(sid, f"k_lo={k}: players with p10<1.0 = {(q < 1).sum()}/{len(f)}; among final>8: {((q < 1) & (m > 8)).sum()}/{(m > 8).sum()}; salary>=4k: {((q<1)&(f.salary>=4000)).sum()}")
