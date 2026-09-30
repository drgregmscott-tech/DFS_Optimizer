"""Fit v2 linear + DST on the FIXED 2021-25 frame (true slate pool) and write tracked coefficient artifacts
(coefficients only, no FC rows): data/ownership_v2_dk_linear_truepool.json, data/ownership_v2_dk_dst_truepool.json.
Also LOSO before/after for linear and DST on the true pool."""
import json, sys; from pathlib import Path; import numpy as np, pandas as pd
R=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(R/"analysis/ownership_v2"))
from common import ALL, GROUPS, Model, metrics
from part3_dst import dst_feats, F_DST_OPT
D=R/"data/fc_history/derived/ownership_v2"
Hn=pd.read_parquet(D/"hist.parquet").reset_index(drop=True); Ho=pd.read_parquet(D/"hist.polluted-2026-09-29.parquet").reset_index(drop=True)
m=Model(ALL).fit(Hn,"own")
json.dump({"kind":"ownership_v2_softmax_linear","fit":"realized DK SE own 2021-25 (86 slates), TRUE slate pool (off-slate teams removed), 2026-09-30",
           "features":ALL,"pos_interaction_order":GROUPS,"mu":m.mu.tolist(),"sd":m.sd.tolist(),"b":m.b.tolist(),"budgets":m.budgets,"cap":75.0},
          open(R/"data/ownership_v2_dk_linear_truepool.json","w"),indent=1)
dn=dst_feats(Hn); d=Model(F_DST_OPT,l2=3.0,pos_inter=False).fit(dn,"own")
json.dump({"kind":"ownership_v2_dst_softmax","fit":"TRUE slate pool 2026-09-30","features":F_DST_OPT,"mu":d.mu.tolist(),"sd":d.sd.tolist(),"b":d.b.tolist(),"budget":100.0},
          open(R/"data/ownership_v2_dk_dst_truepool.json","w"),indent=1)
print("budgets old/new:",json.load(open(R/"data/ownership_v2_dk_linear.json"))["budgets"],m.budgets)
# DST LOSO on true pool: old-pool fit vs new-pool fit
do=dst_feats(Ho); S=sorted(Hn.season.unique())
def dl(Dtr_all,Dte_all):
    p=np.zeros(len(Dte_all))
    for s in S:
        te=(Dte_all.season==s).to_numpy(); p[te]=Model(F_DST_OPT,l2=3.0,pos_inter=False).fit(Dtr_all[Dtr_all.season!=s],"own").predict(Dte_all[te])
    return p
pn=dl(dn,dn); po=dl(do,dn)
print("DST LOSO on true pool: old-fit corr %.3f mae %.3f | new-fit corr %.3f mae %.3f"%(np.corrcoef(po,dn.own)[0,1],np.abs(po-dn.own).mean(),np.corrcoef(pn,dn.own)[0,1],np.abs(pn-dn.own).mean()))
