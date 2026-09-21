import pandas as pd, numpy as np, re
pd.set_option('display.width',250,'display.max_columns',80,'display.max_rows',300)
D='C:/Users/gmsco/Downloads/'
R='C:/Users/gmsco/Desktop/DFS_Optimizer/'
slates={'main':'dk_classic_wk2_main_20Sep2026','early':'dk_classic_wk2_early_20Sep2026','afternoon':'dk_classic_wk2_afternoon_20Sep2026'}
files={'main':'results_se3max_dk_classic_wk2_main_20Sep2026.csv','early':'results_se3max_dk_classic_wk2_early_20Sep2026.csv','afternoon':'results_se3max_dk_classic_wk2_afternoon_20Sep2026.csv','mme':'results_mme_dk_classic_wk2_main_20Sep2026.csv','sd':'results_se3max_dk_showdown_wk2_Ind_KC_20Sep2026.csv'}
def players(k):
    df=pd.read_csv(D+files[k],encoding='utf-8-sig')
    p=df[['Player','Roster Position','%Drafted','FPTS']].dropna(subset=['Player']).copy()
    p['own']=p['%Drafted'].str.rstrip('%').astype(float)
    return p.rename(columns={'Player':'name','FPTS':'act'})
def entries(k):
    return pd.read_csv(D+files[k],encoding='utf-8-sig').iloc[:,:6]
def proj(k):
    return pd.read_csv(R+f'output/final_projections_dk_{slates[k]}.csv')
def norm(s):
    s=str(s).lower(); s=re.sub(r"[.'’]","",s); s=re.sub(r"\b(jr|sr|ii|iii|iv)\b","",s); return re.sub(r"[^a-z ]","",s).split() and ' '.join(re.sub(r"[^a-z ]","",s).split())
def merged(k):
    p=players(k); p['pos_r']=p['Roster Position']; p['k']=p.name.map(norm)
    pr=proj(k); pr['k']=pr.player_name.map(norm)
    pr=pr[pr.position!='DST'].copy() if False else pr
    # DST names: 'Panthers' vs team
    m=pr.merge(p.drop_duplicates('k')[['k','act','own','name']],on='k',how='left')
    m['slate']=k
    return m
TOK=re.compile(r'\b(DST|FLEX|QB|RB|WR|TE)\s+')
def parse_lineup(s):
    parts=TOK.split(' '+s.strip()+' ')
    out=[]; 
    for i in range(1,len(parts)-1,2): out.append((parts[i],parts[i+1].strip()))
    return out
def lineup_frame(k):
    e=entries(k).copy(); e=e[e.Lineup.notna()]; pr=proj(k); p=players(k).drop_duplicates('name')
    pr['k']=pr.player_name.map(norm); p['k']=p.name.map(norm)
    info=pr.set_index('k')[['team','opponent','position','salary','final_projection','estimated_ownership_pct']].to_dict('index')
    act=p.set_index('k')[['act','own']].to_dict('index')
    rows=[]
    for r in e.itertuples():
        L=parse_lineup(r.Lineup); 
        pl=[]
        for slot,nm in L:
            kk=norm(nm); i=info.get(kk,{}); a=act.get(kk,{})
            pl.append(dict(slot=slot,name=nm,team=i.get('team'),opp=i.get('opponent'),pos=i.get('position'),sal=i.get('salary'),proj=i.get('final_projection'),eown=i.get('estimated_ownership_pct'),act=a.get('act'),own=a.get('own')))
        rows.append((r.Rank,r.EntryName,r.Points,pl))
    return rows
def feats(rows):
    F=[]
    for rank,nm,pts,pl in rows:
        q=[p for p in pl if p['slot']=='QB'][0]; d=[p for p in pl if p['slot']=='DST'][0]
        sk=[p for p in pl if p['slot'] not in('QB','DST')]
        stack=sum(1 for p in sk if p['team']==q['team']); bb=sum(1 for p in sk if p['team']==q['opp'])
        own=[p['own'] or 0 for p in pl]; eown=[p['eown'] or 0 for p in pl]
        oppdst=sum(1 for p in sk+[q] if p['team']==d['opp'])
        # game stacks: max players from one team (non-dst)
        from collections import Counter
        c=Counter(p['team'] for p in pl if p['slot']!='DST'); mx=max(c.values())
        F.append(dict(rank=rank,name=nm,pts=pts,stack=stack,bb=bb,own_sum=sum(own),eown_sum=sum(eown),sal=sum(p['sal'] or 0 for p in pl),
            n_low=sum(1 for o in own if o<5),n_hi=sum(1 for o in own if o>=20),dst_own=d['own'] or 0,oppdst=oppdst,maxteam=mx,qb=q['name'],dst=d['name'],
            qb_own=q['own'] or 0,min_own=min(own),n_lt2=sum(1 for o in own if o<2),rb_sal=sum(p['sal'] or 0 for p in sk if p['pos']=='RB'),te_sal=sum(p['sal'] or 0 for p in sk if p['pos']=='TE'),
            flex_pos=[p['pos'] for p in pl if p['slot']=='FLEX'][0]))
    return pd.DataFrame(F)
