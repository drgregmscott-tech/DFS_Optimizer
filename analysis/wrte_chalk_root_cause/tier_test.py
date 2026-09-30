"""Step 9: does the field pick 'the best play in each price tier' (cheap WR, punt TE, etc.)? Our softmax ranks each player against
the whole position; test value/projection rank WITHIN a $1k salary tier (and within the cheap band), LOSO offset on v2."""
import sys; from pathlib import Path; import numpy as np, pandas as pd
R=Path(__file__).resolve().parents[2]
exec(open(Path(__file__).resolve().parent/"offset_test.py").read().split("SETS={")[0])
tier=(P.salary//1000).clip(upper=8); tg=pd.Series(gid).astype(str)+"_"+tier.astype(str)
for c,nm in [("val","tv"),("proj","tp"),("fc_proj","tf")]:
    r=P[c].groupby(tg.values).rank(ascending=False,method="min"); P[nm+"_lrk"]=np.log(r); P[nm+"1"]=(r<=1).astype(float)
P["tv1_gt"]=P.tv1*(P.gt_rank); P["tv1_te"]=P.tv1*(P.pos=="TE"); P["tv1_cheap"]=P.tv1*(P.salary<5000)
tg2=pd.Series(gid).astype(str)+"_"+(P.salary<5000).astype(str)
r=P.val.groupby(tg2.values).rank(ascending=False,method="min"); P["cb_lrk"]=np.log(r)*(P.salary<5000); P["cb1"]=((r<=1)&(P.salary<5000)).astype(float)
Pchk=P[P.own>=20]; print("realized 20pct+ WR/TE: share that are best value in their $1k tier %.2f (base rate for all WR/TE %.2f); best proj in tier %.2f (%.2f)"%(
  Pchk.tv1.mean(),P.tv1.mean(),Pchk.tp1.mean(),P.tp1.mean()))
SETS={"v2 alone":[],"value rank within $1k tier":["tv_lrk","tv1","tv1_te","tv1_cheap","tv1_gt"],"proj rank within tier":["tp_lrk","tp1"],"cheap-band value rank":["cb_lrk","cb1"],
      "DIAG FC proj rank within tier":["tf_lrk","tf1"]}
y=P.own.fillna(0).to_numpy(); bud=pd.Series(P.v2.values).groupby(gid).transform("sum").to_numpy()
def sm(F,ix_gid):
    m=pd.Series(F).groupby(ix_gid).transform("max").to_numpy(); e=np.exp(F-m); return e/pd.Series(e).groupby(ix_gid).transform("sum").to_numpy()
def fit(X,off,y,gd,l2=2.0):
    gs=pd.Series(y).groupby(gd).transform("sum").to_numpy(); t=y/np.where(gs>0,gs,1); w=gs/100
    mu,sd=X.mean(0),X.std(0); sd[sd==0]=1; Z=(X-mu)/sd
    def f(b):
        s=sm(off+Z@b,gd); return -(w*t*np.log(s+1e-12)).sum()+l2*b@b, Z.T@(w*(s-t))+2*l2*b
    b=minimize(f,np.zeros(Z.shape[1]),jac=True,method="L-BFGS-B").x; return b,mu,sd
def pred(X,off,gd,bb,bu):
    b,mu,sd=bb; F=off+((X-mu)/sd)@b if X.shape[1] else off.copy(); return np.minimum(sm(F,gd)*bu,75)
def met(ix,p):
    yy=y[ix]; pp=p[ix]; hi=yy>=20; cw=(P.salary.values[ix]<5500)&(yy>0)
    sp=np.nanmean([spearmanr(pp[j],yy[j])[0] for j in pd.Series(np.arange(len(ix))).groupby(gid[ix]).indices.values()])
    top=[]
    for j in pd.Series(np.arange(len(ix))).groupby(gid[ix]).indices.values():
        top.append(np.argmax(pp[j])==np.argmax(yy[j]))
    return dict(corr=np.corrcoef(pp,yy)[0,1],sp=sp,mae=np.abs(pp-yy).mean(),catch20=(pp[hi]>=15).mean(),pred20=pp[hi].mean(),real20=yy[hi].mean(),
                cheap_corr=np.corrcoef(pp[cw],yy[cw])[0,1],top1_hit=np.mean(top))
rows={}; seasons=sorted(P.season.unique()); store={}
for name,fs in SETS.items():
    X=P[fs].astype(float).fillna(0).to_numpy() if fs else np.zeros((len(P),0)); p=np.zeros(len(P)); coefs=[]
    for s in seasons:
        te=(P.season==s).to_numpy(); tr=~te
        if fs:
            bb=fit(X[tr],P.off.values[tr],y[tr],pd.factorize(gid[tr])[0]); coefs.append(bb[0])
        else: bb=None
        gte=pd.factorize(gid[te])[0]
        p[te]=pred(X[te],P.off.values[te],gte,bb,bud[te]) if fs else P.v2.values[te]
    store[name]=p
    m=met(np.arange(len(P)),p); m23=met(np.where(P.season<=2023)[0],p); m.update({"corr_2123":m23["corr"]})
    rows[name]=m
    if fs: print(name, dict(zip(fs,np.round(np.mean(coefs,0),2))))
t=pd.DataFrame(rows).T.astype(float).round(3); print(t.to_string())
m23=np.where(P.season<=2023)[0]; print("FC Own 2021-23 (WR/TE):",{k:round(v,3) for k,v in met(m23,np.nan_to_num(P.fc_own.values)).items()})
pd.DataFrame(store).assign(slate_id=P.slate_id,player_id=P.player_id).to_parquet(R/"data/fc_history/derived/cheap_wrte/wrte_tier_preds.parquet")
