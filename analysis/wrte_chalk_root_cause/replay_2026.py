"""A/B replay of 2026 wk1-3 (9 DK classic slates) through the SHIPPED code path scripts/ownership_v2.predict_v2
(v2 skill softmax + live-FFC log blend a=.45 + v2 DST), current vs true-pool coefficients, and the teammate-OUT
bump k (chosen leave-one-week-out). Target = realized ownership."""
import os, sys, json; from pathlib import Path; import numpy as np, pandas as pd
R=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(R/"scripts")); sys.path.insert(0,str(R/"analysis/ownership_v2"))
import ownership_v2 as ov
from common import metrics
f=pd.read_parquet(R/"analysis/ownership_refit_wk3/frame.parquet").reset_index(drop=True)
Q=pd.read_parquet(R/"data/fc_history/derived/ownership_v2/y2026_preds.parquet")
lf=Q.set_index(["slate_id","player_id"]).live_ffc
f["live_ffc"]=[lf.get((a,str(b)),np.nan) for a,b in zip(f.slate_id,f.player_id)]
ctxs={}
def run(coef,k):
    os.environ["DFS_OWN_V2_COEF"]=coef; lin,dst=ov.load_artifacts("dk"); out=np.full(len(f),np.nan); bump=np.zeros(len(f))
    for sid,ix in f.groupby("slate_id").indices.items():
        s=f.iloc[ix]; w=int(s.week.iloc[0])
        if w not in ctxs: ctxs[w]=ov.Ctx(ov.load_stats(2026,w),ov.load_prior_salary("dk",2026,w),ov.load_lag_own("dk",2026))
        fr=ov.to_frame(s,s[["l_exp","l_est"]],2026,w,slate_id=sid)
        live=s.live_ffc.to_numpy() if s.ffc_listed.fillna(0).sum()>0 else None
        if live is not None: live=np.where(np.isfinite(live),live,0.05)
        os.environ["DFS_OWN_VAC_BUMP"]="1" if k else "0"
        fin,_=ov.predict_v2(fr,ctxs[w],lin,dst,live,vac_k=k)
        out[ix]=fin; bump[ix]=ov.LAST_AUDIT.get("own_vac_bump",np.zeros(len(ix)))
    return out,bump
Y=pd.DataFrame({"slate_id":f.slate_id,"week":f.week.astype(int),"player_id":f.player_id,"pos":f.position.replace({"D":"DST","DEF":"DST"}),
                "salary":f.salary,"own":f.own.fillna(0),"proj":f.final_projection})
def sc(p,m):
    d=Y[m].reset_index(drop=True); q=np.nan_to_num(p[m]); r=metrics(d,q,"own")
    w=d.pos.isin(["WR","TE"]).to_numpy(); h=(d.own>=20).to_numpy()
    return {k:r[k] for k in ["corr","sp_slate","mae","catch20","bias20","corr_cheapWRTE","top10pct"]}|{"wrte20_pred":q[w&h].mean(),"wrte20_real":d.own.values[w&h].mean()}
K=[0,.5,1,1.5,2]; P={}
for c in ["current","truepool"]:
    for k in K: P[(c,k)]=run(c,k)[0]; print(c,k,"done",flush=True)
allm=np.ones(len(Y),bool); rows={}
for c in ["current","truepool"]:
    lowo=np.zeros(len(Y)); picks={}
    for w in (1,2,3):
        tr=(Y.week!=w).to_numpy(); kk=min(K,key=lambda k: sc(P[(c,k)],tr)["mae"]); picks[w]=kk; lowo[~tr]=P[(c,kk)][~tr]
    P[(c,"LOWO")]=lowo; print(c,"LOWO k picks:",picks,"| k picked on all 3 weeks:",min(K,key=lambda k: sc(P[(c,k)],allm)["mae"]))
for key in [("current",0),("current","LOWO"),("current",1),("truepool",0),("truepool","LOWO"),("truepool",1)]:
    for w in (1,2,3,"all"):
        m=(Y.week==w).to_numpy() if w!="all" else allm; rows[(w,f"{key[0]} k={key[1]}")]=sc(P[key],m)
t=pd.DataFrame(rows).T.astype(float).round(3); print(t.sort_index(level=0,sort_remaining=False).to_string())
# reproduce check vs stored shipped column
ship=Q.set_index(["slate_id","player_id"])["p_new_p_live-FFC_log_blend"]; sp=np.array([ship.get((a,str(b)),np.nan) for a,b in zip(f.slate_id,f.player_id)])
ok=np.isfinite(sp)&np.isfinite(P[("current",0)]); print("replay current k=0 vs stored shipped: max abs diff %.3f, corr %.4f"%(np.abs(sp[ok]-P[("current",0)][ok]).max(),np.corrcoef(sp[ok],P[("current",0)][ok])[0,1]))
