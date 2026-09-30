import pandas as pd,numpy as np
d=pd.read_parquet('../../data/fc_history/derived/model_vs_fc/frame_with_absence.parquet')
d=d[(d.ours>0)&(d.pos!='DST')&(d.regime=='hist')].copy()
print(d[['n_absent','absent_tgt']].describe().T[['mean','50%','max']])
d['abs']=np.where(d.n_absent.fillna(0)>0,'teammate_absent','none')
d['r']=d.act-d.ours;d['rf']=d.act-d.fc
for c,g in [('chalk',d[d.own>=15]),('all',d)]:
  print(c);print(g.groupby('abs').agg(n=('r','size'),act_ours=('r','mean'),act_fc=('rf','mean'),ours=('ours','mean'),fc=('fc','mean')).round(2))
C=d[d.own>=15]
# gap in ours vs fc explained? act-ours ~ (fc-ours)
g=C; b=np.polyfit(g.fc-g.ours,g.r,1);print('chalk: act-ours = %.2f*(fc-ours)+%.2f'%tuple(b))
g=d[d.own<5]; b=np.polyfit(g.fc-g.ours,g.r,1);print('nonchalk: act-ours = %.2f*(fc-ours)+%.2f'%tuple(b))
# pre-lock usable: blend toward FC? not live. Does ours_own (our model) flag chalk? own>=15 recall by ours_own>=12
print('recall of real chalk by ours_own>=12: %.2f'%(C.ours_own>=12).mean(), 'cov',C.ours_own.notna().mean())
