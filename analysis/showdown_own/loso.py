import numpy as np, pandas as pd, itertools, sys
d=pd.read_csv('analysis/showdown_own/dataset.csv'); d=d[d.final_projection>0].copy()
CAP={'CPT':60.0,'FLEX':75.0}; BUD={'CPT':100.0,'FLEX':500.0}
def lg(p,cap): x=np.clip(np.asarray(p,float)/cap,0.003,0.997); return np.log(x/(1-x))
def il(z,cap): return cap/(1+np.exp(-z))
def feats(g,role):
    cap=CAP[role]; f=pd.DataFrame(index=g.index)
    f['l_est']=lg(g.estimated_ownership_pct,cap)
    f['l_exp']=lg((g.exp15+g.exp30+g.exp50)/3,cap)
    f['sal']=g.salary/(1500 if role=='CPT' else 1000)/10   # per-$10K-equivalent
    f['isK']=(g.position=='K')*1.0; f['isD']=(g.position=='DST')*1.0; f['isQB']=(g.position=='QB')*1.0
    f['salrank']=g.groupby('slate').salary.rank(pct=True) if False else g.salary.rank(pct=True)
    f['projrank']=g.final_projection.rank(pct=True)
    return f
def waterfill(r,b,cap):
    out=np.zeros(len(r)); free=r>0; rem=b
    for _ in range(20):
        t=r[free].sum()
        if t<=0 or rem<=0: break
        tr=np.where(free,r/t*rem,0); over=free&(tr>cap)
        if not over.any(): out=np.where(free,tr,out); break
        out=np.where(over,cap,out); rem-=cap*over.sum(); free&=~over
    return out
def ridge(X,y,lam):
    X=np.c_[np.ones(len(X)),X]; P=np.eye(X.shape[1])*lam; P[0,0]=0
    return np.linalg.solve(X.T@X+P,X.T@y)
def run(cols,lam,role,norm=True):
    res=[]
    slates=d.slate.unique()
    for te in slates:
        tr=d[(d.slate!=te)&(d.roster_role==role)]; ts=d[(d.slate==te)&(d.roster_role==role)]
        if cols=='heur': pred=ts.estimated_ownership_pct.values
        else:
            Ftr=feats(tr,role)[cols]; y=lg(tr.own,CAP[role])
            mu,sd=Ftr.mean(),Ftr.std().replace(0,1)
            w=ridge(((Ftr-mu)/sd).values,y,lam)
            Fts=(feats(ts,role)[cols]-mu)/sd
            z=w[0]+Fts.values@w[1:]; raw=il(z,CAP[role])
            pred=waterfill(raw,BUD[role],CAP[role]) if norm else raw
        res.append((te,ts.own.values,pred,ts))
    return res
def metrics(res,role):
    th=20 if role=='FLEX' else 8
    out=[]
    for te,a,p,ts in res:
        ch=a>=th
        out.append((te[-20:],round(np.corrcoef(a,p)[0,1],2),round(np.abs(a-p).mean(),2),int(ch.sum()),round((p-a)[ch].mean(),1),round(np.abs(p-a)[ch].mean(),1),round(np.abs(p-a)[a>=th*0.5].max(),1)))
    return out
if __name__=='__main__':
    for role in ['CPT','FLEX']:
        print('\n====',role)
        for name,cols in [('heur','heur'),('exp',['l_exp']),('heur+exp',['l_est','l_exp']),('exp+K/D',['l_exp','isK','isD']),('heur+exp+K/D',['l_est','l_exp','isK','isD']),('exp+sal+K/D',['l_exp','sal','isK','isD']),('all',['l_est','l_exp','sal','isK','isD','isQB','projrank'])]:
            for lam in ([1.0,5.0] if cols!='heur' else [0]):
                print(f'{name:14s} lam{lam:<4}',metrics(run(cols,lam,role),role))
