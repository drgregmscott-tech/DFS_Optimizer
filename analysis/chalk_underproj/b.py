import pandas as pd,numpy as np
d=pd.read_parquet('../../data/fc_history/derived/model_vs_fc/frame.parquet')
d=d[(d.ours>0)&(d.pos!='DST')].copy()
d['ow']=d.ours_own.fillna(0).clip(0,60); d['sk']=d.salary/1000
print('ours_own coverage',d.groupby('regime').ours_own.apply(lambda x:x.notna().mean()).to_dict(), 'corr own/ours_own',d[['own','ours_own']].corr().iloc[0,1].round(2))
feats={'A_own':['ours','ow'],'B_sal':['ours','sk'],'C_both':['ours','ow','sk']}
H=d[d.regime=='hist'];P=d[d.regime=='prod2026']
def fit(g,f):
    X=np.c_[np.ones(len(g)),g[f]];return np.linalg.lstsq(X,g.act-g.ours,rcond=None)[0]
def pred(g,f,b): return g.ours+np.c_[np.ones(len(g)),g[f]]@b
out=[]
for name,f in feats.items():
  for s in sorted(H.season.unique()):
    tr=H[H.season!=s];te=H[H.season==s].copy()
    te['new']=0.0
    for p in te.pos.unique():
      m=te.pos==p;te.loc[m,'new']=pred(te[m],f,fit(tr[tr.pos==p],f)).values
    out.append((name,s,te))
  te=P.copy();te['new']=0.0
  for p in te.pos.unique():
    m=te.pos==p;b=fit(H[H.pos==p],f);te.loc[m,'new']=pred(te[m],f,b).values
    if name=='C_both':print('full-hist coef',p,np.round(b,3))
  out.append((name,2026,te))
rng=np.random.default_rng(1)
def row(te):
  te=te.copy();te['d']=(te.act-te.new).abs()-(te.act-te.ours).abs()
  s=te.groupby('slate').d.agg(['sum','count']);b=[]
  for _ in range(500):
    i=rng.integers(0,len(s),len(s));x=s.iloc[i];b.append(x['sum'].sum()/x['count'].sum())
  return f"dMAE {te.d.mean():+.3f} [{np.percentile(b,2.5):+.3f},{np.percentile(b,97.5):+.3f}] n={len(te)}"
for name in feats:
  T=pd.concat([t for n,s,t in out if n==name and s!=2026]);T26=[t for n,s,t in out if n==name and s==2026][0]
  print('==',name)
  print(' hist LOSO all',row(T)); print(' hist LOSO chalk(own>=15)',row(T[T.own>=15]),'bias new %+.2f'%(T[T.own>=15].act-T[T.own>=15].new).mean())
  print(' hist per-season dMAE',T.assign(d=(T.act-T.new).abs()-(T.act-T.ours).abs()).groupby('season').d.mean().round(3).to_dict())
  print(' 2026 all',row(T26),' chalk',row(T26[T26.own>=15]))
  from scipy.stats import spearmanr
  print(' slate spearman hist ours %.3f new %.3f'%(T.groupby('slate').apply(lambda g:spearmanr(g.ours,g.act)[0]).mean(),T.groupby('slate').apply(lambda g:spearmanr(g.new,g.act)[0]).mean()))
