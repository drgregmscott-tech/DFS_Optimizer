"""Step 4 check: does a proportional REALLOCATION of the OUT teammates' usage (proj x (1 + a*vac/(1-vac)), a fit
LOSO) beat our WR/TE projection on held-out MAE? (The flat bump made MAE worse.)"""
from pathlib import Path; import numpy as np, pandas as pd
R=Path(__file__).resolve().parents[2]
H=pd.read_parquet(R/"data/fc_history/derived/ownership_v2/hist.parquet")
d=H[H.in_pool&H.pos.isin(["WR","TE"])&H.act.notna()&(H.proj>0)].copy()
d["mult"]=(d.vacated/(1-d.vacated).clip(lower=.25)).clip(upper=3)
A=np.linspace(-.3,.6,19); p=np.zeros(len(d)); picks=[]
for s in sorted(d.season.unique()):
    tr=d.season!=s; a=min(A,key=lambda a: np.abs(d.act[tr]-d.proj[tr]*(1+a*d.mult[tr])).mean()); picks.append(round(a,2))
    te=(d.season==s).to_numpy(); p[te]=(d.proj*(1+a*d.mult))[te]
big=(d.vacated>=.3).to_numpy()
print("LOSO a picks:",picks)
for nm,m in [("all WR/TE",np.ones(len(d),bool)),("teammate OUT",big)]:
    print(f"{nm}: MAE proj {np.abs(d.act-d.proj)[m].mean():.3f} -> realloc {np.abs(d.act-p)[m].mean():.3f}")
