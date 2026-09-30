"""Step 8 (decisive): is the history chalk miss our PROJECTION or our projection->ownership MAPPING?
Rebuild v2 LOSO with the projection column swapped (all projection-derived features recomputed):
 A our proj (reproduces v2)  B FC proj (DIAG teacher: 'what if our projection were as good as FC's on these players')
 C our proj + boosted trees (richer mapping: shape/interactions, same inputs)."""
import sys; from pathlib import Path; import numpy as np, pandas as pd
R=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(R/"analysis/ownership_v2"))
from common import ALL, Model, metrics, mtable
H0=pd.read_parquet(R/"data/fc_history/derived/ownership_v2/hist.parquet").reset_index(drop=True)
def reproj(H,col):
    H=H.copy(); H["proj"]=H[col].clip(lower=0).fillna(0); p=H.in_pool&(H.proj>0); key=[H.slate_id,H.grp]
    H["val"]=np.where(p,H.proj/H.salk.clip(lower=1),0.0)
    for c in ["proj","val"]:
        x=H[c].where(p); H[c+"_rk"]=x.groupby(key).rank(ascending=False,method="min"); H[c+"_lrk"]=np.log(H[c+"_rk"].fillna(99))
        mu=x.groupby(key).transform("mean"); sd=x.groupby(key).transform("std").replace(0,np.nan); H[c+"_z"]=((x-mu)/sd).fillna(-3)
        H[c+"_gap"]=(x.groupby(key).transform("max")-x).fillna(10)
    H["cv"]=(H.sigma.fillna(0)/H.proj.clip(lower=.5)).clip(upper=5); return H
def loso(H,**kw):
    p=np.zeros(len(H))
    for s in sorted(H.season.unique()):
        te=(H.season==s).to_numpy(); p[te]=Model(ALL,**kw).fit(H[~te],"own").predict(H[te])
    return p
def chalk(H,p):
    w=H.pos.isin(["WR","TE"]).to_numpy(); hi=(H.own>=20).to_numpy()
    o={"wrte20_pred":p[w&hi].mean(),"wrte20_real":H.own.values[w&hi].mean()}
    gid=H.slate_id.astype(str)+H.grp; rr=pd.Series(p).groupby(gid.values).rank(ascending=False,method="first").values
    realrk=H.groupby(gid).own.rank(ascending=False,method="first").values
    o["wrte_real1_in_pred_top3"]=(rr[w&(realrk==1)]<=3).mean(); return o
rows={}; out={}
HB=reproj(H0,"fc_proj")
for nm,H,kw in [("A our proj (v2)",reproj(H0,"proj"),{}),("B FC proj (diag)",HB,{}),("C our proj + trees",reproj(H0,"proj"),{"trees":60})]:
    p=loso(H,**kw); out[nm]=p; m=metrics(H,p,"own"); m.update(chalk(H,p)); rows[nm]=m; print(nm,"done",flush=True)
m3=(H0.season<=2023).to_numpy()
rows["FC Own (2021-23 only)"]={**metrics(H0[m3],H0.fc_own.fillna(0).values[m3],"own"),**chalk(H0[m3].reset_index(drop=True),H0.fc_own.fillna(0).values[m3])}
for nm,p in out.items():
    rows[nm+" [2021-23]"]={**metrics(H0[m3],p[m3],"own"),**chalk(H0[m3].reset_index(drop=True),p[m3])}
t=pd.DataFrame(rows).T; cols=["corr","sp_slate","mae","catch20","bias20","corr_cheapWRTE","top10pct","wrte20_pred","wrte20_real","wrte_real1_in_pred_top3"]
print(t[cols].astype(float).round(3).to_string())
pd.DataFrame(out).assign(slate_id=H0.slate_id,player_id=H0.player_id).to_parquet(R/"data/fc_history/derived/cheap_wrte/proj_swap_preds.parquet")
