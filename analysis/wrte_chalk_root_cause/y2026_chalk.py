"""Step 4 (2026 live inputs): player-by-player on WR/TE chalk the shipped blend under-sized, and a LOWO test of pulling
public-consensus chalk (raw FFC top-N) toward raw FFC. FFC is the only public-consensus ownership we have live."""
from pathlib import Path; import sys; import numpy as np, pandas as pd
R=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(R/"analysis/ownership_v2"))
from common import metrics, allocate
D=R/"data/fc_history/derived/ownership_v2"
Y=pd.read_parquet(D/"y2026.parquet").reset_index(drop=True); Q=pd.read_parquet(D/"y2026_preds.parquet").reset_index(drop=True)
assert (Y.player_id.values==Q.player_id.values).all()
ship=Q["p_new_p_live-FFC_log_blend"].values; v2=Q.p_new_realized_linear.values; ffc=Y.ffc_own_pct.values
for w in (1,2,3):
    m=(Y.week==w).to_numpy(); print("wk",w,"shipped blend cheap WR/TE corr %.3f"%metrics(Y[m],ship[m],"own")["corr_cheapWRTE"])
Y["ship"]=ship; Y["v2"]=v2; Y["ffc"]=ffc
gid=Y.slate_id.astype(str)+Y.grp
Y["ffc_rk"]=Y.groupby(gid).ffc.rank(ascending=False,method="min"); Y["ship_rk"]=Y.groupby(gid).ship.rank(ascending=False,method="min")
Y["real_rk"]=Y.groupby(gid).own.rank(ascending=False,method="min")
Y["val_rk"]=Y.groupby(gid).apply(lambda d:(d.proj/d.salk).rank(ascending=False,method="min")).reset_index(level=0,drop=True)
Y["pv_rk"]=Y.groupby(gid).pub_val.rank(ascending=False,method="min")
miss=Y[Y.pos.isin(["WR","TE"])&(Y.own>=15)&(Y.own-Y.ship>=8)]
cols=["week","slate_id","player","pos","team","salary","own","ship","v2","ffc","proj","val_rk","pv_rk","ffc_rk","ship_rk","real_rk","sal_chg","vacated","my_share","lag_own","dk_avg_ppg"]
print("\n2026 WR/TE chalk under-sized by shipped blend by 8+ (n=%d)"%len(miss)); print(miss[cols].sort_values("own",ascending=False).round(1).to_string())
hi=Y[Y.pos.isin(["WR","TE"])&(Y.own>=20)]
print("\n2026 WR/TE 20%%+ (n=%d): real %.1f ship %.1f v2 %.1f rawFFC %.1f | ffc_rk median %.0f ship_rk median %.0f val_rk median %.0f"%(len(hi),hi.own.mean(),hi.ship.mean(),hi.v2.mean(),np.nan_to_num(hi.ffc).mean(),hi.ffc_rk.median(),hi.ship_rk.median(),hi.val_rk.median()))
# calibration by rank on each model
for c in ["ship","ffc"]:
    rr=Y.groupby(gid)[c].rank(ascending=False,method="first"); w=Y.pos.isin(["WR","TE"])
    print(c,"calibration by its own rank (WR/TE):"); print(Y[w].assign(r=rr[w].clip(upper=6)).groupby("r").agg(real=("own","mean"),pred=(c,"mean"),n=("own","size")).round(1).T.to_string())
# ---- candidate correction: for raw-FFC top-N in each slate x group, pull toward raw FFC by b (log space), renormalise to shipped budgets
def chalk_pull(d, base, f, N, b):
    rk=d.assign(_f=f).groupby(d.slate_id.astype(str)+d.grp)._f.rank(ascending=False,method="first").to_numpy()
    sel=(rk<=N)&np.isfinite(f)&(f>0)
    F=np.log(np.clip(base,.05,None)); F=np.where(sel,(1-b)*F+b*np.log(np.clip(f,.05,None)),F)
    out=np.zeros(len(d)); bud=d.assign(_v=base).groupby(["slate_id","grp"])._v.sum()
    for (sid,g),ix in d.groupby(["slate_id","grp"]).indices.items(): out[ix]=allocate(d.iloc[ix],F[ix],{g:bud[(sid,g)]})
    return out
def score(d,p):
    m=metrics(d,p,"own"); w=d.pos.isin(["WR","TE"]).to_numpy(); hi=(d.own.to_numpy()>=20)
    return dict(corr=m["corr"],sp=m["sp_slate"],mae=m["mae"],catch20=m["catch20"],bias20=m["bias20"],cheapWRTE=m["corr_cheapWRTE"],top10=m["top10pct"],
                wrte20_pred=p[w&hi].mean(), wrte20_real=d.own.to_numpy()[w&hi].mean())
grid=[(N,b) for N in (1,2,3,5) for b in (.25,.5,.75,1.0)]
out=np.zeros(len(Y)); pick={}
for w in (1,2,3):
    tr=(Y.week!=w).to_numpy(); te=~tr
    best=max(grid,key=lambda nb:-metrics(Y[tr],chalk_pull(Y[tr],ship[tr],ffc[tr],*nb),"own")["mae"]+0*0)
    pick[w]=best; out[te]=chalk_pull(Y[te],ship[te],ffc[te],*best)
print("\nLOWO picks (N,b) chosen on MAE:",pick)
rows={}
for w in (1,2,3,"all"):
    m=(Y.week==w).to_numpy() if w!="all" else np.ones(len(Y),bool)
    for nm,p in [("shipped",ship),("chalk-pull LOWO",out),("raw FFC",np.nan_to_num(ffc))]: rows[(w,nm)]=score(Y[m],p[m])
print(pd.DataFrame(rows).T.astype(float).round(3).to_string())
for nb in grid:
    p=chalk_pull(Y,ship,ffc,*nb); s=score(Y,p); print(nb,{k:round(v,3) for k,v in s.items()})
Y.assign(pull=out).to_parquet(R/"data/fc_history/derived/cheap_wrte/y2026_chalk.parquet")
