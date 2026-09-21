import pandas as pd, numpy as np, re, sys
tok=re.compile(r'\b(CPT|FLEX)\s+')
def parse(s):
    p=tok.split(' '+s.strip()); return [(p[i],p[i+1].strip()) for i in range(1,len(p)-1,2)]
def run(f,label):
    df=pd.read_csv(f,encoding='utf-8-sig'); e=df.iloc[:,:6].dropna(subset=['Lineup']).copy(); N=len(e)
    L=[parse(s) for s in e.Lineup]; e['cpt']=[[n for r,n in l if r=='CPT'][0] for l in L]; e['flex']=[[n for r,n in l if r=='FLEX'] for l in L]
    e['pct']=1-(e.Rank-1)/N; own=e.cpt.value_counts(normalize=True)*100; e['cown']=e.cpt.map(own)
    t1=e.Rank<=N*.01; t10=e.Rank<=N*.10
    print(f'\n===== {label}: {N} lineups; mean pts {e.Points.mean():.1f}; top1% n={t1.sum()}')
    rows=[]
    for c in own.head(8).index:
        g=e[e.cpt==c]; rows.append(dict(cpt=c,n=len(g),usage=round(own[c],1),share_top1=round((t1&(e.cpt==c)).sum()/t1.sum()*100,1),mean_pts=round(g.Points.mean(),1),med_pct=round(g.pct.median(),2),top10=round(t10[g.index].mean()*100,1)))
    print(pd.DataFrame(rows).to_string(index=False))
    e['tier']=pd.cut(e.cown,[0,3,6,15,100],labels=['<3%','3-6%','6-15%','>15%'])
    print(e.groupby('tier',observed=True).agg(n=('Points','size'),mean=('Points','mean'),med_pct=('pct','median'),top1=('Rank',lambda r:(r<=N*.01).mean()*100),top10=('Rank',lambda r:(r<=N*.10).mean()*100)).round(2))
    p=df[['Player','Roster Position','FPTS']].dropna(subset=['Player']); fl=p[p['Roster Position']=='FLEX'].set_index('Player').FPTS
    cp=(fl*1.5).sort_values(ascending=False); print('top CPT scores:',cp.head(6).round(1).to_dict())
    top=own.index[0]; print(f'chalk CPT {top} ({own.iloc[0]:.1f}%): CPT-score rank {list(cp.index).index(top)+1}/{len(cp)}')
    # team split
    return e
run('C:/Users/gmsco/Downloads/dk_showdown_wk1_Den_KC_14Sep2026_results.csv','wk1 DEN@KC')
run('C:/Users/gmsco/Downloads/results_se3max_dk_showdown_wk2_Ind_KC_20Sep2026.csv','wk2 IND@KC')
