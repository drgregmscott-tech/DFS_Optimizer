import pandas as pd, numpy as np, re
f='C:/Users/gmsco/Downloads/results_se3max_dk_showdown_wk2_Ind_KC_20Sep2026.csv'
df=pd.read_csv(f,encoding='utf-8-sig'); e=df.iloc[:,:6].dropna(subset=['Lineup']).copy()
tok=re.compile(r'\b(CPT|FLEX)\s+')
def parse(s):
    p=tok.split(' '+s.strip()); return [(p[i],p[i+1].strip()) for i in range(1,len(p)-1,2)]
L=[parse(s) for s in e.Lineup]; e['cpt']=[[n for r,n in l if r=='CPT'][0] for l in L]; e['flex']=[[n for r,n in l if r=='FLEX'] for l in L]
e['pct']=1-(e.Rank-1)/len(e)  # higher = better
own=e.cpt.value_counts(normalize=True)*100
e['cpt_own']=e.cpt.map(own)
print('entries',len(e),'\nCPT usage & outcomes (top 10 by usage):')
top=own.head(10).index
rows=[]
for c in top:
    g=e[e.cpt==c]; rows.append(dict(cpt=c,n=len(g),own=round(own[c],1),mean_pts=round(g.Points.mean(),1),median_pct=round(g.pct.median(),3),top1=round((g.Rank<=len(e)*.01).mean()*100,1),top10=round((g.Rank<=len(e)*.10).mean()*100,1)))
print(pd.DataFrame(rows).to_string(index=False)); print('overall mean pts',round(e.Points.mean(),1),'baseline top1 1%, top10 10%')
# Walker CPT vs Walker FLEX vs no-Walker, conditional on the rest of the build
W='Kenneth Walker III'
e['walker']=np.where(e.cpt==W,'CPT',np.where(e.flex.map(lambda x:W in x),'FLEX','none'))
print('\nWalker slot:'); print(e.groupby('walker').agg(n=('Points','size'),mean=('Points','mean'),pct=('pct','median'),top1=('Rank',lambda r:(r<=len(e)*.01).mean()*100),top10=('Rank',lambda r:(r<=len(e)*.10).mean()*100)).round(2))
# CPT ownership tier
e['tier']=pd.cut(e.cpt_own,[0,3,6,15,100],labels=['<3%','3-6%','6-15%','>15%'])
print('\nBy CPT ownership tier:'); print(e.groupby('tier',observed=True).agg(n=('Points','size'),mean=('Points','mean'),med_pct=('pct','median'),top1=('Rank',lambda r:(r<=len(e)*.01).mean()*100),top10=('Rank',lambda r:(r<=len(e)*.10).mean()*100)).round(2))
# CPT scoring rank: each player's would-be CPT points (1.5x) rank
p=df[['Player','Roster Position','FPTS']].dropna(subset=['Player']); fl=p[p['Roster Position']=='FLEX'].set_index('Player').FPTS
cp=(fl*1.5).sort_values(ascending=False); print('\nBest possible CPT scores:'); print(cp.head(8).round(1).to_string())
print('Walker CPT rank among all players by CPT points:',list(cp.index).index(W)+1,'of',len(cp))
# among lineups with the same non-CPT core? proxy: expected-vs-actual for players
