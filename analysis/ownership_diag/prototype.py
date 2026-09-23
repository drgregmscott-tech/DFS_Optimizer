"""Prototype: layered model + public-value signals, scored leave-one-week-out.

'Public projection' proxy = DK's own AvgPointsPerGame from the salary export
(what every DK user sees; wk1 = prior-season avg, wk2+ = season-to-date avg).
l_pexp = logit of optimizer exposure when projections are replaced by
0.5*ours + 0.5*dk_avg (ours alone where dk_avg <= 0).
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd

sys.path.insert(0, r"C:\Users\gmsco\Desktop\DFS_Optimizer\scripts")
sys.path.insert(0, str(Path(__file__).parent))
import ownership_model as om, fit_ownership_model as fom, ownership_heuristic as oh
from features import SCR

d = pd.read_pickle(SCR / "diag_frame.pkl")
B = oh.compute_position_slot_budgets("dk")
cache = SCR / "pexp.pkl"
if cache.exists():
    d["pexp"] = pd.read_pickle(cache)
else:
    d["pexp"] = 0.0
    for sid, g in d.groupby("slate_id"):
        h = g.copy()
        pub = np.where(h.dk_avg > 0, 0.5 * h.final_projection + 0.5 * h.dk_avg, h.final_projection)
        h["final_projection"] = pub
        e = om.optimizer_exposure(h, "dk")
        d.loc[g.index, "pexp"] = g.player_id.map(e).fillna(0.0).to_numpy()
        print(sid, "done", flush=True)
    d["pexp"].to_pickle(cache)
d["l_pexp"] = om._logit(d.pexp)
for c in ("pub_val", "pub_minus_ours", "proj_vs_salfit"):
    d[c + "_z"] = d[c].fillna(0.0)


def lowo(feats, ridge=1.0):
    pred = pd.Series(0.0, index=d.index); old = om.FEATURES
    for w in (1, 2):
        tr, te = d[d.week != w], d[d.week == w]
        om.FEATURES = feats
        try:
            art = fom.fit(tr, ridge); pred.loc[te.index] = fom.predict_slates(te, art, B)
        finally:
            om.FEATURES = old
    return pred


def metrics(p, idx=None):
    own = d.own if idx is None else d.own[idx]; p = p if idx is None else p[idx]
    m = (own > 5) | (p > 5); e = p - own; c = own >= 20
    return dict(corr_m=round(np.corrcoef(p[m], own[m])[0, 1], 3), mae_m=round(e[m].abs().mean(), 2),
                chalk_bias=round(e[c].mean(), 1), chalk_mae=round(e[c].abs().mean(), 1),
                chalk_ge10=f"{int(((p >= 10) & c).sum())}/{int(c.sum())}",
                miss12=int((e < -12).sum()), cheap_miss12=int(((e < -12) & (d.salary[e.index] <= 5500)).sum()),
                over12=int((e > 12).sum()))


BASE = list(om.FEATURES)
variants = {
    "base (shipped features)": BASE,
    "+pub_val": BASE + ["pub_val_z"],
    "+l_pexp": BASE + ["l_pexp"],
    "+l_pexp+pub_val": BASE + ["l_pexp", "pub_val_z"],
    "+pub_val+pub_minus_ours": BASE + ["pub_val_z", "pub_minus_ours_z"],
    "l_exp->l_pexp swap": [f if f != "l_exp" else "l_pexp" for f in BASE],
}
rows = []
preds = {}
for name, fs in variants.items():
    for ridge in (1.0, 10.0):
        p = lowo(fs, ridge); preds[(name, ridge)] = p
        r = dict(model=name, ridge=ridge, **metrics(p))
        for w in (1, 2):
            r[f"corr_w{w}"] = metrics(p, d.week == w)["corr_m"]
        rows.append(r)
res = pd.DataFrame(rows); print(res.to_string())
res.to_csv(Path(__file__).parent / "prototype_lowo.csv", index=False)
best = preds[("+l_pexp+pub_val", 1.0)]
d["proto"] = best
cols = ["slate_id", "player_name", "position", "salary", "own", "lowo", "proto", "dk_avg", "final_projection"]
print(d[d.own >= 30].sort_values("own", ascending=False)[cols].round(1).to_string())
d[cols + ["pexp", "exposure"]].round(2).to_csv(Path(__file__).parent / "proto_predictions.csv", index=False)
