"""Lineup-level structure analysis across every stored Showdown slate (data/contest_results/).
Top-10%/top-1% rates by team split, kicker, DST, CPT position, chalk-CPT tier. Run from repo root."""
import pandas as pd, re, sys
S={'wk1 DEN@KC':'wk1_Den_KC_14Sep2026','wk2 IND@KC':'wk2_Ind_KC_20Sep2026',
   'wk2 NYG@LAR':'wk2_NYG_LAR_21Sep2026','wk3 ATL@GB':'wk3_Atl_GB_24Sep2026'}
tok=re.compile(r'\b(CPT|FLEX)\s+')
def parse(s):
    p=tok.split(' '+s.strip()); return [(p[i],p[i+1].strip()) for i in range(1,len(p)-1,2)]
rows=[];miss=0
for lab,sid in S.items():
    sal=pd.read_csv(f'data/salaries_dk_dk_showdown_{sid}.csv'); sal['n']=sal.Name.str.strip()
    info=sal.drop_duplicates('n').set_index('n')[['TeamAbbrev','Position']]
    df=pd.read_csv(f'data/contest_results/dk_showdown_{sid}_full.csv',encoding='utf-8-sig')
    own=df[['Player','Roster Position','%Drafted']].dropna(); own['Player']=own.Player.str.strip()
    cpt_own=own[own['Roster Position']=='CPT'].set_index('Player')['%Drafted'].str.rstrip('%').astype(float)
    e=df.iloc[:,:6].dropna(subset=['Lineup']); N=len(e)
    for r in e.itertuples():
        pl=parse(r.Lineup); cpt=[n for t,n in pl if t=='CPT'][0]
        if any(n not in info.index for _,n in pl): miss+=1; continue
        teams=[info.TeamAbbrev[n] for _,n in pl]; pos=[info.Position[n] for _,n in pl]
        c=pd.Series(teams).value_counts()
        rows.append(dict(slate=lab,rank=r.Rank,N=N,pts=r.Points,cpt=cpt,cpt_pos=info.Position[cpt],
          cpt_own=cpt_own.get(cpt,0.0),split=f"{c.max()}-{6-c.max()}" if len(c)>1 else '6-0',
          K='K' in pos,DST='DST' in pos,fav_side=None))
d=pd.DataFrame(rows); d['top10']=d['rank']<=d.N*.10; d['top1']=d['rank']<=d.N*.01
print('lineups',len(d),'unmapped skipped',miss)
def tab(col,sub=None):
    x=d if sub is None else d[sub]
    g=x.groupby(['slate',col]).agg(n=('pts','size'),top10=('top10','mean'),top1=('top1','mean')); g[['top10','top1']]*=100
    p=x.groupby(col).agg(n=('pts','size'),top10=('top10','mean'),top1=('top1','mean')); p[['top10','top1']]*=100
    print(f'\n== {col} (pooled) =='); print(p.round(1).to_string())
    print(f'-- {col} top-10% by slate --'); print(g.top10.unstack(0).round(1).to_string())
for c in ['split','K','DST','cpt_pos']: tab(c)
d['own_tier']=pd.cut(d.cpt_own,[-1,2,5,10,15,100],labels=['<2','2-5','5-10','10-15','>15']); tab('own_tier')
