"""Step 7: test the mis-treatments found in treatment_diag, held-out LOSO (history) on top of v2 (conditional logit offset).
T1 no-history (rookie/debut) players: our projection ~0 while DK salary says starter -> salary-implied floor.
T2 next-man-up: teammate OUT credits the player who ALREADY had the share (my_share, benef); the field credits the cheap
   replacement with LOW prior share. Features: cheap x vacated x low-share, by position.
Also: categorise the 20%+ WR/TE misses into these classes to say how much of the miss each explains."""
import sys; from pathlib import Path; import numpy as np, pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parent)); 
R=Path(__file__).resolve().parents[2]
exec(open(Path(__file__).resolve().parent/"offset_test.py").read().split("SETS={")[0])   # reuse loaders/features (P, gid, lrk, ...)
P["nohist"]=((P.prev_gp.fillna(0)==0)&(P.ytd_gp.fillna(0)==0)).astype(float)
P["nohist_sal"]=P.nohist*P.salk
cheap=(P.salary<5000).astype(float); low=(P.my_share<.12).astype(float)
P["nmu"]=cheap*P.vacated*low; P["nmu_te"]=P.nmu*(P.pos=="TE"); P["nmu_sal"]=P.nmu*P.salk
P["vac_hi_share"]=P.vacated*(1-low)
# which class does each 20%+ miss belong to?
M=P[(P.own>=20)&(P.own-P.v2>=8)]
cls=np.select([M.nohist==1,(M.vacated>=.25)&(M.my_share<.12)&(M.salary<5000),(M.vacated>=.25)],["no-history (rookie/debut)","next-man-up (cheap, low prior share, teammate OUT)","teammate OUT, already-featured"],"no role change (stud/price/matchup)")
tab=M.assign(cls=cls).groupby("cls").agg(n=("own","size"),real=("own","mean"),v2=("v2","mean"),fc=("fc_own","mean"),proj=("proj","mean"),fcproj=("fc_proj","mean"),act=("act","mean"),sal=("salary","mean"))
tab["miss_share"]=(M.assign(cls=cls,m=M.own-M.v2).groupby("cls").m.sum()/(M.own-M.v2).sum())
print("20%+ WR/TE under-sized by 8+, by class (history 2021-25):"); print(tab.round(2).to_string())
SETS={"v2 alone":[],"T1 no-history salary floor":["nohist","nohist_sal"],"T2 next-man-up (cheap x vacated x low share)":["nmu","nmu_te","nmu_sal","vac_hi_share"],
      "T1+T2":["nohist","nohist_sal","nmu","nmu_te","nmu_sal","vac_hi_share"]}
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
pd.DataFrame(store).assign(slate_id=P.slate_id,player_id=P.player_id).to_parquet(R/"data/fc_history/derived/cheap_wrte/wrte_treatfix_preds.parquet")
