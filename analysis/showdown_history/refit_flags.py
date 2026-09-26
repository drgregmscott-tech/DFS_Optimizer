"""Refit the production showdown ownership model's 4 coefficients (l_exp,isK,isD,isMin) using FC history features
(prod_feats.parquet from cache_features.py) and/or our real slates. Reports LOSO + held-out-real diagnostics.
Usage: python refit_flags.py [--write]   (--write updates data/ownership_model_showdown_dk.json)"""
import sys, json, warnings
from pathlib import Path
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
R = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(R / "scripts"))
import ownership_model_showdown as oms
F = oms.FEATURES
fc = pd.read_parquet(R / "data/fc_history/derived/showdown/prod_feats.parquet").reset_index(drop=True)
fc["year"] = fc.slate.str[:4].astype(int); fc["src"] = "fc"
real = oms._training_frame(); real["year"] = 2026; real["src"] = "real"
real = real.reset_index(drop=True)
cols = ["role", "live", "own", "slate", "year", "src", "position"] + F
real["position"] = real["position"].astype(str)
fc["position"] = fc["position"].astype(str)
D = pd.concat([fc[cols], real[cols]], ignore_index=True)
D["w"] = np.where(D.year >= 2025, 2.0, 1.0)

def fit_role(tr, role, lam=5.0, real_w=1.0):
    t = tr[(tr.role == role) & tr.live]
    w = t.w.to_numpy() * np.where(t.src == "real", real_w, 1.0)
    X = t[F]; mu = X.mean(); sd = X.std().replace(0, 1.0)
    A = np.c_[np.ones(len(t)), ((X - mu) / sd).to_numpy()]
    P = np.eye(A.shape[1]) * lam; P[0, 0] = 0
    Aw = A * w[:, None]
    wt = np.linalg.solve(Aw.T @ A + P, Aw.T @ oms._logit(t.own, oms.CAP[role]))
    return {"intercept": float(wt[0]), "coefs": dict(zip(F, map(float, wt[1:]))),
            "mu": mu.astype(float).to_dict(), "sd": sd.astype(float).to_dict()}

def predict_df(g, art):
    """g has role, live + features; predict per slate (waterfill is per slate)."""
    out = pd.Series(0.0, index=g.index)
    for s, gs in g.groupby("slate"):
        out.loc[gs.index] = oms.predict(gs, art)
    return out

def diag(g, pred, label):
    rows = []
    for role in ("CPT", "FLEX"):
        m = (g.role == role) & g.live
        a, p = g.own[m].to_numpy(), pred[m].to_numpy(); th = 20 if role == "FLEX" else 8; ch = a >= th
        r = dict(set=label, role=role, n=int(m.sum()), corr=round(float(np.corrcoef(a, p)[0, 1]), 3),
                 mae=round(float(np.abs(a - p).mean()), 2), chalk_mae=round(float(np.abs(a - p)[ch].mean()), 1))
        for pos in ("K", "DST", "QB", "WR"):
            mp = m & (g.position == pos)
            r["bias_" + pos] = round(float((pred[mp] - g.own[mp]).mean()), 1) if mp.any() else np.nan
        rows.append(r)
    return rows

cur = json.loads(oms.ARTIFACT.read_text())
res = []
slates = D.slate.unique().tolist(); realS = D[D.src == "real"].slate.unique().tolist()
FC = D[D.src == "fc"]; RL = D[D.src == "real"]

# baseline: current artifact
res += diag(FC, predict_df(FC, cur), "FC | current artifact")
res += diag(RL, predict_df(RL, cur), "REAL4 | current artifact (in-sample)")
# FC-only refit, tested on real (out of sample; features from our projections)
art_fc = {"roles": {r: fit_role(FC, r) for r in ("CPT", "FLEX")}}
res += diag(RL, predict_df(RL, art_fc), "REAL4 | FC-only refit (OOS)")
# LOSO on FC: FC-only refit vs FC+real refit
for label, real_w in (("FC LOSO | FC-only train", None), ("FC LOSO | FC+real train (real x3)", 3.0)):
    pr = pd.Series(0.0, index=FC.index)
    for s in FC.slate.unique():
        tr = D[(D.slate != s) & ((D.src == "fc") if real_w is None else True)]
        art = {"roles": {r: fit_role(tr, r, real_w=real_w or 1.0) for r in ("CPT", "FLEX")}}
        gs = FC[FC.slate == s]; pr.loc[gs.index] = oms.predict(gs, art)
    res += diag(FC, pr, label)
# LOSO on the 4 real slates with FC+real(x3) train
pr = pd.Series(0.0, index=RL.index)
for s in realS:
    art = {"roles": {r: fit_role(D[D.slate != s], r, real_w=3.0) for r in ("CPT", "FLEX")}}
    gs = RL[RL.slate == s]; pr.loc[gs.index] = oms.predict(gs, art)
res += diag(RL, pr, "REAL4 LOSO | FC+other real (x3)")
pd.set_option("display.width", 250)
print(pd.DataFrame(res).to_string(index=False))
final = {"roles": {r: fit_role(D, r, real_w=3.0) for r in ("CPT", "FLEX")}}
print(json.dumps({r: final["roles"][r]["coefs"] for r in final["roles"]}, indent=1))
print("current:", json.dumps({r: cur["roles"][r]["coefs"] for r in cur["roles"]}))
if "--write" in sys.argv:
    art = {"roles": final["roles"], "features": F, "lambda": 5.0,
           "trained_on": sorted(realS) + [f"fc_history_showdown_{len(FC.slate.unique())}_slates_2023-2025"],
           "weights": "2025+ x2; real slates x3", "cap": oms.CAP, "budget": oms.BUDGET,
           "noises": list(oms.NOISES), "n_lineups": oms.N_LINEUPS}
    oms.ARTIFACT.write_text(json.dumps(art, indent=2), encoding="utf-8"); print("wrote", oms.ARTIFACT)
