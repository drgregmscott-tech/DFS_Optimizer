"""Step 2: which candidate cause explains the chalk the v2 model misses? Held-out (leave-one-season-out) conditional-logit
on top of v2: F = log(v2_loso) + b.x within each slate x position (WR, TE), budgets fixed to v2's. Target = realized own.
Feature groups are the candidate causes. FC-derived columns are marked DIAG (history-only teacher, not a live input)."""
import sys; from pathlib import Path
import numpy as np, pandas as pd
from scipy.optimize import minimize
from scipy.stats import spearmanr
R = Path(__file__).resolve().parents[2]
P = pd.read_parquet(R/"data/fc_history/derived/cheap_wrte/wrte_chalk_P.parquet")
P = P[P.pos.isin(["WR","TE"])].reset_index(drop=True)
key=["slate_id","grp"]; g=P.groupby(key)
gid = pd.factorize(P.slate_id.astype(str)+P.grp)[0]
lz=lambda s: s.groupby(gid).transform(lambda x:(x-x.mean())/(x.std() or 1)).fillna(0)
lrk=lambda s,asc=False: np.log(s.groupby(gid).rank(ascending=asc,method="min").fillna(99))
# --- candidate features
P["off"]=np.log(P.v2.clip(lower=.05))
P["fcp_l"]=np.log1p(P.fc_proj.fillna(0)); P["fcp_lrk"]=lrk(P.fc_proj); P["fcv_lrk"]=lrk(P.fc_proj/P.salk)
P["gap"]=np.log1p(P.fc_proj.fillna(0))-np.log1p(P.proj)
talent=P.ytd_ppg.where(P.ytd_gp>=2, np.fmax(P.prev_ppg, P.ytd_ppg.fillna(0)))
P["tal_v"]=(talent.fillna(0)/P.salk); P["tal_v_lrk"]=lrk(P.tal_v); P["tal_v_z"]=lz(P.tal_v)
P["prev_rk_v"]=np.log(P.prev_rank.clip(lower=1))+np.log(P.salk)   # low = good player at low price
P["ret"]=(((P.ytd_gp.fillna(0)==0)&(P.week>1))|(P.last_same_season==0)&(P.week>1)).astype(float)
P["deb"]=((P.prev_gp.isna()|(P.prev_gp==0))&(P.ytd_gp.fillna(0)==0)).astype(float)
P["vac_sh"]=P.vacated*P.my_share; P["vac"]=P.vacated
P["top1v"]=(P.val_rk<=1).astype(float); P["top3v"]=(P.val_rk<=3).astype(float); P["top3p"]=(P.proj_rk<=3).astype(float)
vr=P.groupby(gid).v2.rank(ascending=False,method="first")
P["sh1"]=P.off*(vr<=1); P["sh3"]=P.off*(vr<=3); P["top1m"]=(vr<=1).astype(float)
P["lag_lrk"]=lrk(P.lag_own.fillna(0).where(P.lag_own>0)); P["lastdk_lrk"]=lrk(P.last_dk)
P["salup"]=P.sal_chg.clip(-1.5,1.5); P["tt_lrk"]=P.team_total_lrk
P["p3tgt_lrk"]=lrk(P.p3_tgt)
SETS={
 "v2 alone":[],
 "structural: top-N value flags (our proj)":["top1v","top3v","top3p"],
 "structural: sharpen v2's own top-1/top-3":["sh1","sh3","top1m"],
 "price lag: talent (ppg) per $ rank":["tal_v_lrk","tal_v_z","prev_rk_v"],
 "debut / return from absence":["ret","deb"],
 "teammate OUT (vacated x share)":["vac","vac_sh"],
 "recent usage/production spike":["p3tgt_lrk","lastdk_lrk","lag_lrk"],
 "DK price move":["salup"],
 "DIAG consensus projection (FC proj)":["fcp_l","fcp_lrk","fcv_lrk","gap"],
}
SETS["all rebuildable"]=sorted({c for k,v in SETS.items() if not k.startswith("DIAG") for c in v})
SETS["all rebuildable + DIAG consensus"]=SETS["all rebuildable"]+SETS["DIAG consensus projection (FC proj)"]
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
pd.DataFrame(store).assign(slate_id=P.slate_id,player_id=P.player_id).to_parquet(R/"data/fc_history/derived/cheap_wrte/wrte_offset_preds.parquet")
