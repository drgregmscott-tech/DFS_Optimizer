"""Step 10 (ROOT CAUSE TEST): the 2021-25 training frame's pool includes ~7.6 teams per slate (~25% of players) whose games are
NOT on the contest slate (TNF/SNF/MNF etc.; real own exactly 0 for the whole team, FC Own exactly 0 too). v2 was fit on that
polluted pool, which teaches it to spread mass (flatten). Fix: pool = teams on the slate (pre-lock knowable: the DK salary
file / contest game list). Recompute within-slate features, refit v2 linear LOSO, compare to FC Own on the same pool, then
fit on all 2021-25 and score 2026 (never seen) against the shipped v2."""
import sys, json; from pathlib import Path; import numpy as np, pandas as pd
R=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(R/"analysis/ownership_v2"))
from common import ALL, Model, metrics, GROUPS
def refeat(df):
    df=df.copy(); p=df.in_pool&(df.proj>0); key=[df.slate_id,df.grp]
    df["tt_rank"]=df.team_total.where(df.in_pool).groupby([df.slate_id,df.pos]).rank(pct=True).fillna(0)
    df["gt_rank"]=df.game_total.where(df.in_pool).groupby(df.slate_id).rank(pct=True).fillna(0)
    for c in ["proj","val","salk","team_total","pressure"]:
        x=df[c].where(p); df[c+"_rk"]=x.groupby(key).rank(ascending=False,method="min"); df[c+"_lrk"]=np.log(df[c+"_rk"].fillna(99))
        mu=x.groupby(key).transform("mean"); sd=x.groupby(key).transform("std").replace(0,np.nan); df[c+"_z"]=((x-mu)/sd).fillna(-3)
        df[c+"_gap"]=(x.groupby(key).transform("max")-x).fillna(10)
    df["n_grp"]=p.groupby(key).transform("sum"); df["n_games"]=df.where(df.in_pool).groupby("slate_id").team.transform("nunique")/2
    df["pubv_rk"]=df.pubv.where(p&(df.pos!="DST")).groupby(key).rank(ascending=False); df["pubv_lrk"]=np.log(df.pubv_rk.fillna(99))
    df["last_val_lrk"]=np.log(df.last_val.where(p&(df.pos!="DST")).groupby(key).rank(ascending=False).fillna(99))
    df["min_sal"]=(df.salk_rk==df.groupby(key).salk_rk.transform("max")).astype(float)
    return df
def extra(H,p):
    w=H.pos.isin(["WR","TE"]).to_numpy(); hi=(H.own>=20).to_numpy(); m=metrics(H,p,"own")
    gid=(H.slate_id.astype(str)+H.grp).values; rr=pd.Series(p).groupby(gid).rank(ascending=False,method="first").values
    rk=H.groupby(gid).own.rank(ascending=False,method="first").values
    m.update(wrte20_pred=p[w&hi].mean(),wrte20_real=H.own.values[w&hi].mean(),real1_in_top3=(rr[w&(rk==1)]<=3).mean()); return m
H0=pd.read_parquet(R/"data/fc_history/derived/ownership_v2/hist.parquet").reset_index(drop=True)
on=H0[H0.pos!="DST"].groupby(["slate_id","team"]).own.sum().gt(0)
H0["on_slate"]=[on.get((s,t),False) for s,t in zip(H0.slate_id,H0.team)]
print("off-slate rows in old pool: %d of %d in_pool (%.1f%%)"%((H0.in_pool&~H0.on_slate).sum(),H0.in_pool.sum(),100*(H0.in_pool&~H0.on_slate).mean()/H0.in_pool.mean()))
Hold=H0; Hnew=refeat(H0.assign(in_pool=H0.in_pool&H0.on_slate))
cols=["corr","sp_slate","mae","catch20","bias20","corr_cheapWRTE","corr_7k","top10pct","wrte20_pred","wrte20_real","real1_in_top3"]
rows={}; S=sorted(H0.season.unique())
def loso(H):
    p=np.zeros(len(H))
    for s in S:
        te=(H.season==s).to_numpy(); p[te]=Model(ALL).fit(H[~te],"own").predict(H[te])
    return p
pold=loso(Hold); pnew=loso(Hnew)
ev=Hnew.in_pool.to_numpy()   # score everyone on the TRUE slate pool (old model's off-slate mass is simply wasted)
E=Hnew[ev].reset_index(drop=True)
rows["v2 as shipped (fit on polluted pool)"]=extra(E,pold[ev]); rows["v2 refit on true slate pool"]=extra(E,pnew[ev])
m3=(E.season<=2023).to_numpy(); E3=E[m3].reset_index(drop=True)
rows["[21-23] v2 as shipped"]=extra(E3,pold[ev][m3]); rows["[21-23] v2 refit true pool"]=extra(E3,pnew[ev][m3]); rows["[21-23] FC Own"]=extra(E3,E3.fc_own.fillna(0).values)
# old model, but renormalise its mass onto the true pool (what live does: live pool is already correct)
t=pd.DataFrame(rows).T[cols].astype(float).round(3); print(t.to_string())
for s in S:
    k=(E.season==s).to_numpy(); print(s,"corr old %.3f new %.3f | cheapWRTE old %.3f new %.3f"%(metrics(E[k],pold[ev][k],"own")["corr"],metrics(E[k],pnew[ev][k],"own")["corr"],metrics(E[k],pold[ev][k],"own")["corr_cheapWRTE"],metrics(E[k],pnew[ev][k],"own")["corr_cheapWRTE"]))
pd.DataFrame({"slate_id":H0.slate_id,"player_id":H0.player_id,"on_slate":H0.on_slate,"v2_old":pold,"v2_new":pnew}).to_parquet(R/"data/fc_history/derived/cheap_wrte/pool_fix_preds.parquet")
# ---- 2026 (never seen): fit on all 2021-25 true pool vs polluted pool, score y2026
Y=pd.read_parquet(R/"data/fc_history/derived/ownership_v2/y2026.parquet").reset_index(drop=True)
onY=Y[Y.pos!="DST"].groupby(["slate_id","team"]).own.sum().gt(0); print("2026 frame: teams with zero real own (off-slate) =",int((~onY).sum()),"of",len(onY))
Mo=Model(ALL).fit(Hold,"own"); Mn=Model(ALL).fit(Hnew,"own")
po=Mo.predict(Y); pn=Mn.predict(Y); Q=pd.read_parquet(R/"data/fc_history/derived/ownership_v2/y2026_preds.parquet").reset_index(drop=True)
rows={}
for w_ in (1,2,3,"all"):
    k=(Y.week==w_).to_numpy() if w_!="all" else np.ones(len(Y),bool); d=Y[k].reset_index(drop=True)
    rows[(w_,"v2 polluted-pool fit (reproduces shipped v2)")]=extra(d,po[k]); rows[(w_,"v2 true-pool fit")]=extra(d,pn[k])
    rows[(w_,"shipped blend (v2 x FFC .45)")]=extra(d,Q["p_new_p_live-FFC_log_blend"].values[k])
mains=Y.slate_id.str.contains("main").to_numpy(); d=Y[mains].reset_index(drop=True)
rows[("main slates","v2 polluted")]=extra(d,po[mains]); rows[("main slates","v2 true-pool")]=extra(d,pn[mains]); rows[("main slates","shipped blend")]=extra(d,Q["p_new_p_live-FFC_log_blend"].values[mains])
print(pd.DataFrame(rows).T[cols].astype(float).round(3).to_string())
print("max abs diff polluted-fit vs shipped v2 col p_new_realized_linear: %.3f"%np.abs(po-Q.p_new_realized_linear.values).max())
Y.assign(v2_old=po,v2_new=pn,ship=Q["p_new_p_live-FFC_log_blend"].values,ffc=Y.ffc_own_pct).to_parquet(R/"data/fc_history/derived/cheap_wrte/y2026_poolfix.parquet")
json.dump({"feats":ALL,"b":Mn.b.tolist(),"mu":Mn.mu.tolist(),"sd":Mn.sd.tolist(),"budgets":Mn.budgets,"trained":"2021-25 true slate pool (teams with any realized own)","date":"2026-09-30"},
          open(R/"data/fc_history/derived/cheap_wrte/v2_truepool_fit.json","w"))
