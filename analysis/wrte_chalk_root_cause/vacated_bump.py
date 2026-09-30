"""Step 11: the injury-driven usage bump. (a) PROJECTION: does our WR/TE projection under-react to vacated teammate usage?
Fit act - proj ~ vacated terms LOSO on 2021-25 (true slate pool), check 2026 live projection too.
(b) OWNERSHIP (live): add k * vacated (WR/TE) to the shipped blend's log-ownership, k fit leave-one-week-out on 2026 wk1-3."""
import sys; from pathlib import Path; import numpy as np, pandas as pd
R=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(R/"analysis/ownership_v2"))
from common import metrics, allocate
H=pd.read_parquet(R/"data/fc_history/derived/ownership_v2/hist.parquet").merge(pd.read_parquet(R/"data/fc_history/derived/cheap_wrte/pool_fix_preds.parquet"),on=["slate_id","player_id"])
d=H[H.on_slate&H.in_pool&H.pos.isin(["WR","TE"])&H.act.notna()&(H.proj>0)].copy()
def X(d): 
    te=(d.pos=="TE").astype(float); lo=(d.my_share<.12).astype(float)
    return np.column_stack([d.vacated,d.vacated*te,d.vacated*lo,d.vacated*d.my_share])
res={}; pr=np.zeros(len(d)); coefs=[]
for s in sorted(d.season.unique()):
    te=(d.season==s).to_numpy(); A=X(d[~te]); b=np.linalg.lstsq(A,(d.act-d.proj)[~te].to_numpy(),rcond=None)[0]; coefs.append(b); pr[te]=d.proj[te]+X(d[te])@b
d["proj_b"]=pr
big=d.vacated>=.3
for nm,m in [("all WR/TE",np.ones(len(d),bool)),("teammate OUT (vacated>=.3)",big.to_numpy())]:
    print(f"{nm:28s} n={m.sum():5d} MAE proj {np.abs(d.act-d.proj)[m].mean():.3f} -> bumped {np.abs(d.act-d.proj_b)[m].mean():.3f} | bias {(d.act-d.proj)[m].mean():+.2f} -> {(d.act-d.proj_b)[m].mean():+.2f}")
print("LOSO coefs [vac, vac*TE, vac*lowshare, vac*share] mean:",np.round(np.mean(coefs,0),2).tolist(), "per-season vac:",np.round([c[0] for c in coefs],2).tolist())
# 2026 live projection check (no act in y2026 frame? use it if present)
Y=pd.read_parquet(R/"data/fc_history/derived/cheap_wrte/y2026_poolfix.parquet").reset_index(drop=True)
if "act" in Y and Y.act.notna().any():
    y=Y[Y.pos.isin(["WR","TE"])&Y.act.notna()&(Y.proj>0)]
    for nm,m in [("2026 all WR/TE",np.ones(len(y),bool)),("2026 teammate OUT",(y.vacated>=.3).to_numpy())]:
        print(f"{nm}: n={m.sum()} live proj bias (act-proj) {(y.act-y.proj)[m].mean():+.2f}")
# (b) ownership bump on shipped blend, LOWO
ship=Y.ship.to_numpy(); wr=Y.pos.isin(["WR","TE"]).to_numpy()
def bump(d,base,k):
    F=np.log(np.clip(base,.05,None))+k*d.vacated.fillna(0).to_numpy()*d.pos.isin(["WR","TE"]).to_numpy()
    out=np.zeros(len(d)); bud=d.assign(_v=base).groupby(["slate_id","grp"])._v.sum()
    for (sid,g),ix in d.groupby(["slate_id","grp"]).indices.items(): out[ix]=allocate(d.iloc[ix],F[ix],{g:bud[(sid,g)]})
    return out
K=[0,.5,1,1.5,2,2.5,3]; p=np.zeros(len(Y)); pick={}
for w in (1,2,3):
    tr=(Y.week!=w).to_numpy(); k=min(K,key=lambda k: metrics(Y[tr],bump(Y[tr],ship[tr],k),"own")["mae"]); pick[w]=k; p[~tr]=bump(Y[~tr],ship[~tr],k)
print("LOWO k picks (on MAE):",pick)
def sc(d,q):
    m=metrics(d,q,"own"); h=(d.own>=15).to_numpy()&d.pos.isin(["WR","TE"]).to_numpy()&(d.vacated>=.3).to_numpy()
    return {**{k:m[k] for k in ["corr","sp_slate","mae","catch20","bias20","corr_cheapWRTE","top10pct"]},"vacOUT15_pred":q[h].mean(),"vacOUT15_real":d.own.to_numpy()[h].mean()}
rows={}
for w in (1,2,3,"all"):
    m=(Y.week==w).to_numpy() if w!="all" else np.ones(len(Y),bool)
    rows[(w,"shipped")]=sc(Y[m],ship[m]); rows[(w,"shipped + vacated bump (LOWO)")]=sc(Y[m],p[m])
print(pd.DataFrame(rows).T.astype(float).round(3).to_string())
for k in K: print("fixed k",k,{a:round(b,3) for a,b in sc(Y,bump(Y,ship,k)).items()})
