"""Step 5 (2026 live): the live miss is IDENTITY (FFC ranks the chalk top-3, shipped blend ranks it lower) not size.
Correction candidate: on top of the shipped blend, add FFC *rank* indicators (top-1, top-3) in log space for WR/TE, coefficients
fit leave-one-week-out by within-slate softmax; renormalised to the shipped group budgets. Also a sanity: over-size of own #1."""
from pathlib import Path; import sys; import numpy as np, pandas as pd
from scipy.optimize import minimize
R=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(R/"analysis/ownership_v2"))
from common import metrics
Y=pd.read_parquet(R/"data/fc_history/derived/cheap_wrte/y2026_chalk.parquet").reset_index(drop=True)
miss=Y[Y.pos.isin(["WR","TE"])&(Y.own>=15)&(Y.own-Y.ship>=8)]
print("misses n=%d: FFC rank<=3 %.2f, <=5 %.2f, FFC missing %.2f; teammate OUT (vacated>=.3) %.2f; TE share %.2f; ship rank<=3 %.2f"%(
 len(miss),(miss.ffc_rk<=3).mean(),(miss.ffc_rk<=5).mean(),miss.ffc.isna().mean(),(miss.vacated>=.3).mean(),(miss.pos=="TE").mean(),(miss.ship_rk<=3).mean()))
w=Y.pos.isin(["WR","TE"]); print("base rates among WR/TE in pool w/ own>0: vacated>=.3 %.2f"%(Y[w&(Y.own>0)].vacated>=.3).mean())
for pos in ["WR","TE"]:
    x=Y[Y.pos==pos]; rr=x.groupby(x.slate_id).ship.rank(ascending=False,method="first").clip(upper=5)
    print(pos,"ship calib by rank:",x.assign(r=rr).groupby("r").agg(real=("own","mean"),pred=("ship","mean")).round(1).T.to_dict("index"))
gid=pd.factorize(Y.slate_id.astype(str)+Y.grp)[0]
f=Y.ffc.to_numpy(); has=np.isfinite(f)&(f>0); frk=Y.ffc_rk.to_numpy()
wr=Y.pos.isin(["WR","TE"]).to_numpy()
Y["f1"]=((frk<=1)&has&wr).astype(float); Y["f3"]=((frk<=3)&has&wr).astype(float)
srk=Y.groupby(gid).ship.rank(ascending=False,method="first").to_numpy(); Y["s1"]=((srk<=1)&wr).astype(float)
Y["f1te"]=Y.f1*(Y.pos=="TE"); Y["f3te"]=Y.f3*(Y.pos=="TE")
mask=(Y.ship>0).to_numpy(); y=Y.own.fillna(0).to_numpy()*mask
off=np.log(np.clip(Y.ship.to_numpy(),.05,None)); bud=pd.Series(Y.ship.to_numpy()).groupby(gid).transform("sum").to_numpy()
def sm(F,g):
    F=np.where(mask[idx_] if False else True,F,F); m=pd.Series(F).groupby(g).transform("max").to_numpy(); e=np.exp(F-m); return e/pd.Series(e).groupby(g).transform("sum").to_numpy()
def run(fs,ix):
    X=Y[fs].to_numpy(float)[ix]; g=pd.factorize(gid[ix])[0]; yy=y[ix]; gs=pd.Series(yy).groupby(g).transform("sum").to_numpy(); t=yy/np.where(gs>0,gs,1); ww=gs/100
    def fn(b):
        s=sm(off[ix]+X@b,g); return -(ww*t*np.log(s+1e-12)).sum()+.5*b@b, X.T@(ww*(s-t))+b
    return minimize(fn,np.zeros(len(fs)),jac=True).x
def apply(fs,b,ix):
    g=pd.factorize(gid[ix])[0]; p=sm(off[ix]+Y[fs].to_numpy(float)[ix]@b,g)*bud[ix]; return np.minimum(p,75)
SETS={"FFC top1/top3 flags":["f1","f3"],"+TE-specific":["f1","f3","f1te","f3te"],"+ shrink own #1":["f1","f3","s1"],"all":["f1","f3","f1te","f3te","s1"]}
def sc(d,p):
    m=metrics(d,p,"own"); hi=(d.own>=20).to_numpy()&d.pos.isin(["WR","TE"]).to_numpy()
    return dict(corr=m["corr"],sp=m["sp_slate"],mae=m["mae"],catch20=m["catch20"],bias20=m["bias20"],cheapWRTE=m["corr_cheapWRTE"],top10=m["top10pct"],wrte20_pred=p[hi].mean(),wrte20_real=d.own.to_numpy()[hi].mean())
rows={}
for w_ in (1,2,3,"all"):
    m=(Y.week==w_).to_numpy() if w_!="all" else np.ones(len(Y),bool); rows[(w_,"shipped")]=sc(Y[m],Y.ship.to_numpy()[m])
for nm,fs in SETS.items():
    p=np.zeros(len(Y)); bs=[]
    for wk in (1,2,3):
        te=(Y.week==wk).to_numpy(); b=run(fs,np.where(~te)[0]); bs.append(b); p[te]=apply(fs,b,np.where(te)[0])
    print(nm,"LOWO coefs",np.round(bs,2).tolist(),"| all-weeks fit",np.round(run(fs,np.arange(len(Y))),2).tolist())
    for w_ in (1,2,3,"all"):
        m=(Y.week==w_).to_numpy() if w_!="all" else np.ones(len(Y),bool); rows[(w_,nm)]=sc(Y[m],p[m])
    Y["p_"+nm]=p
t=pd.DataFrame(rows).T.astype(float).round(3); print(t.sort_index(level=0,sort_remaining=False).to_string())
Y.to_parquet(R/"data/fc_history/derived/cheap_wrte/y2026_rankfix.parquet")
