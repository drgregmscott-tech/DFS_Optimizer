"""Logistic regression of top-10% finish on lineup structure, controlling for projection, across all stored
Showdown slates. Pooled (slate fixed effects) + per-slate sign consistency. Run from repo root.
Projection = FLEX-row final_projection sum with CPT x1.5 applied ONCE (CPT rows already carry it)."""
import pandas as pd, numpy as np, re
S={'DENKC':'wk1_Den_KC_14Sep2026','INDKC':'wk2_Ind_KC_20Sep2026','NYGLAR':'wk2_NYG_LAR_21Sep2026','ATLGB':'wk3_Atl_GB_24Sep2026'}
tok=re.compile(r'\b(CPT|FLEX)\s+')
def parse(s):
    p=tok.split(' '+s.strip()); return [(p[i],p[i+1].strip()) for i in range(1,len(p)-1,2)]
R=[]
for lab,sid in S.items():
    P=pd.read_csv(f'output/final_projections_dk_dk_showdown_{sid}.csv'); F=P[P.roster_role=='FLEX'].copy(); F['k']=F.player_name.str.strip()
    info=F.drop_duplicates('k').set_index('k')[['team','position','salary','final_projection']]
    df=pd.read_csv(f'data/contest_results/dk_showdown_{sid}_full.csv',encoding='utf-8-sig')
    e=df.iloc[:,:6].dropna(subset=['Lineup']); N=len(e)
    for r in e.itertuples():
        pl=parse(r.Lineup)
        if any(n not in info.index for _,n in pl): continue
        cpt=[n for t,n in pl if t=='CPT'][0]; names=[n for _,n in pl]
        c=pd.Series([info.team[n] for n in names]).value_counts()
        pos=[info.position[n] for n in names]
        R.append(dict(slate=lab,top10=int(r.Rank<=N*.10),proj=1.5*info.final_projection[cpt]+sum(info.final_projection[n] for t,n in pl if t=='FLEX'),
          sal=1.5*info.salary[cpt]+sum(info.salary[n] for t,n in pl if t=='FLEX'),
          s51=int(c.max()==5),s33=int(c.max()==3),K=int('K' in pos),DST=int('DST' in pos),
          cRB=int(info.position[cpt]=='RB'),cWR=int(info.position[cpt]=='WR'),cTE=int(info.position[cpt]=='TE'),cKD=int(info.position[cpt] in('K','DST'))))
d=pd.DataFrame(R); d['zproj']=d.groupby('slate').proj.transform(lambda x:(x-x.mean())/x.std()); d['zsal']=d.groupby('slate').sal.transform(lambda x:(x-x.mean())/x.std())
X=['zproj','zsal','s51','s33','K','DST','cRB','cWR','cTE','cKD']
print(len(d),'lineups; top10 rate',d.top10.mean().round(3))
def irls(y,X,it=50):
    X=np.asarray(X,float); y=np.asarray(y,float); b=np.zeros(X.shape[1])
    for _ in range(it):
        p=1/(1+np.exp(-X@b)); W=p*(1-p)+1e-9; H=X.T@(X*W[:,None])+1e-8*np.eye(X.shape[1])
        nb=b+np.linalg.solve(H,X.T@(y-p))
        if np.abs(nb-b).max()<1e-8: b=nb; break
        b=nb
    p=1/(1+np.exp(-X@b)); W=p*(1-p)+1e-9; se=np.sqrt(np.diag(np.linalg.inv(X.T@(X*W[:,None])+1e-8*np.eye(X.shape[1]))))
    return b,se
def fit(x):
    Xm=np.column_stack([np.ones(len(x)),x[X].astype(float).values]); b,se=irls(x.top10,Xm); return pd.Series(b[1:],index=X),pd.Series(b[1:]/se[1:],index=X)
D=pd.get_dummies(d.slate,drop_first=True).astype(float)
Xm=np.column_stack([np.ones(len(d)),d[X].astype(float).values,D.values]); b,se=irls(d.top10,Xm)
out=pd.DataFrame({'pooled_coef':b[1:1+len(X)],'pooled_z':b[1:1+len(X)]/se[1:1+len(X)]},index=X)
for s_ in S: out[s_]=fit(d[d.slate==s_])[0]
out['sign_agree(of 4)']=[max((np.sign(out.loc[v,list(S)])>0).sum(),(np.sign(out.loc[v,list(S)])<0).sum()) for v in X]
print(out.round(2).to_string())
print('\n(base: 4-2 split, QB captain. Pooled z overstates significance: lineups within a slate are highly duplicated/dependent -- use sign agreement.)')
