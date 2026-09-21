import pandas as pd, numpy as np, re
tok=re.compile(r'\b(CPT|FLEX)\s+')
def parse(s):
    p=tok.split(' '+s.strip()); return [n for i,n in [(p[i],p[i+1].strip()) for i in range(1,len(p)-1,2)]]
D='C:/Users/gmsco/Downloads/'
S={'wk1 DEN@KC':(D+'dk_showdown_wk1_Den_KC_14Sep2026_results.csv','dk_showdown_wk1_Den_KC_14Sep2026'),
   'wk2 IND@KC':(D+'results_se3max_dk_showdown_wk2_Ind_KC_20Sep2026.csv','dk_showdown_wk2_Ind_KC_20Sep2026')}
for lab,(f,sid) in S.items():
    P=pd.read_csv(f'output/final_projections_dk_{sid}.csv'); tm=P.drop_duplicates('player_name').set_index(P.drop_duplicates('player_name').player_name.str.strip()).team
    df=pd.read_csv(f,encoding='utf-8-sig'); e=df.iloc[:,:6].dropna(subset=['Lineup']).copy(); N=len(e)
    def sp(s):
        t=[tm.get(n.strip()) for n in parse(s)]; c=pd.Series(t).value_counts(); return f"{c.max()}-{6-c.max()}" if len(c)>1 else "6-0"
    e['split']=e.Lineup.map(sp); e['top1']=e.Rank<=N*.01; e['top10']=e.Rank<=N*.10
    g=e.groupby('split').agg(n=('Points','size'),field=('Points',lambda x:len(x)/N*100),mean=('Points','mean'),top1=('top1','mean'),top10=('top10','mean'))
    g['top1']*=100; g['top10']*=100; g['lift_top10']=g.top10/10
    print('\n',lab,f'({N} lineups; top1% n={e.top1.sum()})'); print(g.round(1).to_string())
