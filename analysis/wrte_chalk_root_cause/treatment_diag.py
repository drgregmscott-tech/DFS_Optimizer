"""Step 6 (owner correction): the inputs (salary, Vegas, usage, teammate injuries, position class) ARE available. How does OUR
treatment of them diverge from the field's? Response curves: real own vs v2 vs FC Own, and projection bias (act - our proj)
by teammate-OUT, rookie/return, price band, position."""
from pathlib import Path; import numpy as np, pandas as pd
R=Path(__file__).resolve().parents[2]
H=pd.read_parquet(R/"data/fc_history/derived/ownership_v2/hist.parquet").merge(pd.read_parquet(R/"data/fc_history/derived/cheap_wrte/v2_loso.parquet"),on=["slate_id","player_id"])
W=H[H.pos.isin(["WR","TE"])&H.in_pool].copy()
print("rows WR/TE in pool:",len(W)," proj==0 share %.3f; their real own mass share %.3f; mean own of proj==0 & salary>=4000: %.2f (n=%d)"%(
 (W.proj<=0).mean(), W.own[W.proj<=0].sum()/W.own.sum(), W.own[(W.proj<=0)&(W.salary>=4000)].mean(), ((W.proj<=0)&(W.salary>=4000)).sum()))
W["band"]=pd.cut(W.salary,[0,3500,4500,5500,7000,20000],labels=["<3.5","3.5-4.5","4.5-5.5","5.5-7","7+"])
W["vacb"]=pd.cut(W.vacated,[-1,.05,.2,.4,2],labels=["none","small","med","big"])
W["newrole"]=np.where((W.prev_gp.fillna(0)==0)&(W.ytd_gp.fillna(0)==0),"rookie/no-hist",np.where((W.week>1)&((W.ytd_gp.fillna(0)==0)|(W.wk_since_prev>1)),"return/absent","normal"))
W["bias"]=W.act-W.proj; W["fcb"]=W.act-W.fc_proj
agg=dict(n=("own","size"),real=("own","mean"),v2=("v2","mean"),fc=("fc_own","mean"),act=("act","mean"),proj=("proj","mean"),fcproj=("fc_proj","mean"))
for by in [["pos","band"],["pos","vacb"],["newrole"],["pos","band","vacb"]]:
    t=W[W.act.notna()].groupby(by,observed=True).agg(**agg); t["own_ratio_v2"]=t.v2/t.real; t["proj_bias"]=t.act-t.proj; t["fcproj_bias"]=t.act-t.fcproj
    print("\n== by",by); print(t.round(2).to_string())
# response: among players that are the TOP remaining target earner on a team with big vacated usage
b=W[(W.vacated>=.3)&(W.my_share>=.15)]
print("\nbeneficiaries (vacated>=.3, share>=.15) n=%d: real %.2f v2 %.2f fc %.2f | act %.1f proj %.1f fcproj %.1f"%(len(b),b.own.mean(),b.v2.mean(),b.fc_own.mean(),b.act.mean(),b.proj.mean(),b.fc_proj.mean()))
# does our proj respond to vacated at all?  slope of proj, fc_proj, act on vacated*share controlling salary
import numpy.linalg as la
d=W[W.act.notna()&(W.proj>0)].copy(); d["vs"]=d.vacated*d.my_share
X=np.column_stack([np.ones(len(d)),d.salk,d.vacated,d.vs,d.pos.eq("TE")])
for c in ["proj","fc_proj","act","own","v2"]:
    b_=la.lstsq(X,d[c].fillna(0).to_numpy(),rcond=None)[0]; print(f"{c:8s} slope on vacated {b_[2]:+.2f}  on vacated*share {b_[3]:+.2f}  (per salary $1k {b_[1]:+.2f})")
