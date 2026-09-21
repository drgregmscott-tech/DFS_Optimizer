from histeval_clean import *
P,A,M=build(); M=features(M)
M['sal']=M.salary/1000; M['sw']=M.season*100+M.week
M['proj']=M.final_projection
for c in ['l3','l6','ewm','std','ps']: M[c+'_f']=M[c].fillna(M[c].mean()); M['has_'+c]=M[c].notna().astype(float)
for c in [c for c in M.columns if c.startswith('u_')]+['fav','temp','wind','rest','is_home','dome']: M[c]=M[c].fillna(M[c].mean() if M[c].notna().any() else 0)
M['cold']=(M.n_prior.fillna(0)<1).astype(float)
M['implied']=M.implied_total.fillna(M.implied_total.mean()); M['ou']=M.over_under.fillna(M.over_under.mean())
M['sig']=M.sigma.fillna(M.sigma.mean())
M['y']=M.actual_points
def cvr2(cols,df,by=None):
    X=np.column_stack([np.ones(len(df))]+[df[c] for c in cols]); y=df.y.values; groups=df.sw.values; pred=np.zeros(len(df))
    for g in np.unique(groups):
        te=groups==g; b=la.lstsq(X[~te],y[~te],rcond=None)[0]; pred[te]=X[te]@b
    return 1-((y-pred)**2).mean()/y.var(), pred
def report(df,label):
    print('\n==',label,'n=%d weeks=%d'%(len(df),df.sw.nunique()))
    raw=df.proj.corr(df.y)
    print('  raw corr(engine proj, actual) %.3f  | corr(salary, actual) %.3f | raw engine R2 (uncalibrated) %.3f'%(raw,df.sal.corr(df.y),1-((df.y-df.proj)**2).mean()/df.y.var()))
    sets=[('salary',['sal']),('engine proj',['proj']),('salary+engine',['sal','proj']),
      ('+recent form (l3,l6,ewm)',['sal','proj','l3_f','l6_f','ewm_f','has_l3']),
      ('+season/prior avg',['sal','proj','std_f','ps_f','has_ps','has_std']),
      ('+recent usage',['sal','proj']+[c for c in df.columns if c.startswith('u_')]),
      ('+environment (spread,total,wx,home,rest)',['sal','proj','fav','ou','temp','wind','is_home','dome','rest']),
      ('+all',['sal','proj','l3_f','l6_f','ewm_f','has_l3','std_f','ps_f','has_ps','has_std']+[c for c in df.columns if c.startswith('u_')]+['fav','ou','temp','wind','is_home','dome','rest','cold'])]
    base=None
    for nm,c in sets:
        r,_=cvr2(c,df); 
        if nm=='salary+engine': base=r
        print('  %-42s CV R2 %.4f'%(nm,r)+('   (%+.4f vs salary+engine)'%(r-base) if base is not None and nm not in('salary','engine proj','salary+engine') else ''))
if __name__=='__main__':
    report(M,'ALL positions')
    for pos in ['QB','RB','WR','TE']: report(M[M.position==pos],pos)
    M.to_pickle('cvM_clean.pkl')
