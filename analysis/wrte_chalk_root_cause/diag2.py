"""Step 3: what IS the realized #1-owned WR/TE of each slate, on every pre-lock ranking we can rebuild (and FC's, as diag)?"""
from pathlib import Path; import numpy as np, pandas as pd
R=Path(__file__).resolve().parents[2]
P=pd.read_parquet(R/"data/fc_history/derived/cheap_wrte/wrte_chalk_P.parquet")
P=P[P.pos.isin(["WR","TE"])].copy(); gid=P.slate_id.astype(str)+P.grp
rk=lambda c,asc=False: P.groupby(gid)[c].rank(ascending=asc,method="min")
P["talent"]=P.ytd_ppg.where(P.ytd_gp>=2,np.fmax(P.prev_ppg,P.ytd_ppg.fillna(0)))
P["fcv"]=P.fc_proj/P.salk
for c in ["proj","val","fc_proj","fcv","salary","lag_own","last_dk","talent","pubv","team_total","p3_tgt","v2","fc_own"]: P[c+"_R"]=rk(c)
ch=P[P.real_rk==1]
cols=[c for c in P if c.endswith("_R")]
print("realized #1 WR/TE per slate (n=%d). median rank and share ranked top-3 on each pre-lock ordering:"%len(ch))
print(pd.DataFrame({"median":ch[cols].median(),"top3":(ch[cols]<=3).mean(),"top1":(ch[cols]<=1).mean()}).round(2).to_string())
# concentration: does the field concentrate when there's a standout? real #1 own vs gap between #1 and #2 on projection
g=P.groupby(gid)
s=pd.DataFrame({"real1":g.own.max(),"v2_1":g.v2.max(),"fc1":g.fc_own.max(),"real_top1_share":g.own.max()/g.own.sum()})
print("\nslate-group level: real #1 own mean %.1f, v2 max mean %.1f, FC max %.1f"%(s.real1.mean(),s.v2_1.mean(),s.fc1.mean()))
print("dispersion of real #1 own across slates (sd): %.1f ; v2 max sd %.1f ; corr(v2max, real1) %.2f ; corr(fcmax, real1) %.2f"%(s.real1.std(),s.v2_1.std(),s[['v2_1','real1']].corr().iloc[0,1],s[['fc1','real1']].dropna().corr().iloc[0,1]))
