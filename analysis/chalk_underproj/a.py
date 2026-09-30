import pandas as pd,numpy as np
d=pd.read_parquet('../../data/fc_history/derived/model_vs_fc/frame.parquet')
d=d[(d.ours>0)|(d.fc>0)].copy()
rng=np.random.default_rng(0)
def ci(g,col):
    s=g.groupby('slate')[col].agg(['sum','count']);k=s.index.values
    b=[];
    for _ in range(1000):
        i=rng.integers(0,len(s),len(s));x=s.iloc[i];b.append(x['sum'].sum()/x['count'].sum())
    return f"{g[col].mean():+.2f} [{np.percentile(b,2.5):+.2f},{np.percentile(b,97.5):+.2f}]"
d['r_ours']=d.act-d.ours; d['r_fc']=d.act-d.fc
d['ob']=pd.cut(d.own,[-1,5,10,20,30,100],labels=['<5','5-10','10-20','20-30','30+'])
d['sb']=pd.cut(d.salary,[0,4500,5500,7000,20000],labels=['<4.5k','4.5-5.5k','5.5-7k','7k+'])
for reg in ['hist','prod2026']:
  D=d[d.regime==reg]; print('=====',reg)
  for ob,g in D.groupby('ob',observed=True):
    print(ob,len(g),'act-ours',ci(g,'r_ours'),'act-fc',ci(g,'r_fc'),'ours %.1f fc %.1f act %.1f'%(g.ours.mean(),g.fc.mean(),g.act.mean()))
  C=D[D.own>=15]
  print('-- chalk own>=15 by pos'); 
  for k,g in C.groupby('pos'): print(k,len(g),'act-ours',ci(g,'r_ours'),'act-fc',ci(g,'r_fc'))
  print('-- chalk by salary')
  for k,g in C.groupby('sb',observed=True): print(k,len(g),'act-ours',ci(g,'r_ours'),'act-fc',ci(g,'r_fc'))
  print('-- chalk where ours<fc-2 (we under FC)')
  g=C[C.ours<C.fc-2]; print(len(g),'act-ours',ci(g,'r_ours'),'act-fc',ci(g,'r_fc'))
  g=C[C.ours>=C.fc-2]; print('others',len(g),'act-ours',ci(g,'r_ours'),'act-fc',ci(g,'r_fc'))
  if reg=='hist':
    print('-- chalk by season'); 
    for k,g in C.groupby('season'): print(k,len(g),'act-ours %+.2f act-fc %+.2f'%(g.r_ours.mean(),g.r_fc.mean()))
    # control: salary-matched nonchalk
    print('-- residual vs own controlling ours: OLS act-ours ~ ours + own by pos')
    for p,g in D[D.pos!='DST'].groupby('pos'):
      X=np.c_[np.ones(len(g)),g.ours,g.own];b=np.linalg.lstsq(X,g.r_ours,rcond=None)[0];print(p,np.round(b,3))
