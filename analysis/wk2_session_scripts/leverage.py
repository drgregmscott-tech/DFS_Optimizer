import sys; sys.path.insert(0,'C:/Users/gmsco/Desktop/DFS_Optimizer/scripts')
from se_grid import *
import pickle
def fld(k,wk): return np.load(f'W1real_{k}.npy') if wk==1 else np.sort(pd.read_pickle(f'F_{k}.pkl').pts.values)
def T_pen(g,source):
    def f(df,d):
        df=df.copy(); m=df.final_projection>0
        if source=='old': o=df.estimated_ownership_pct
        elif source=='actual': o=df.player_id.map(d.set_index('player_id').own).fillna(0)
        else:
            pth=f'own_{source}/final_projections_dk_{SID_CUR}.csv'; n=pd.read_csv(pth,dtype={'player_id':str}); o=df.player_id.map(n.set_index('player_id').estimated_ownership_pct).fillna(0)
        df.loc[m,'final_projection']=(df.loc[m,'final_projection']-g*o[m]).clip(lower=0.1); return df
    return f
SE_BB=SE+QB1+['--bring-back']
CONF={'SE none':(SE_BB,None),'MME none':(MME,None)}
for src in ('old','new','lowo','actual'):
    for g in (0.05,0.10,0.20):
        CONF[f'SE pen {src} {g}']=(SE_BB,(g,src)); CONF[f'MME pen {src} {g}']=(MME,(g,src))
SID_CUR=None
def job(a):
    nm,k,wk,seed=a; args,tf=CONF[nm]; args=list(args)+['--seed',str(seed)]
    sid=SID[(k,wk)]
    if tf is None: t=None
    else:
        g,src=tf
        def t(df,d,g=g,src=src,sid=sid):
            df=df.copy(); m=df.final_projection>0
            if src=='old': o=df.estimated_ownership_pct
            elif src=='actual': o=df.player_id.map(d.set_index('player_id').own).fillna(0)
            else:
                n=pd.read_csv(f'own_{src}/final_projections_dk_{sid}.csv',dtype={'player_id':str}); o=df.player_id.map(n.set_index('player_id').estimated_ownership_pct).fillna(0)
            df.loc[m,'final_projection']=(df.loc[m,'final_projection']-g*o[m]).clip(lower=0.1); return df
    L=run(k,wk,args,t,tag=f"L{abs(hash(nm))%100000}s{seed}")
    if L is None: return (nm,k,wk,seed,None)
    d,_=pool(k,wk); a_=d.set_index('player_id').act
    s=L.assign(a=L.player_id.map(a_).fillna(0)).groupby('lineup_id').a.sum().values
    f=fld(k,wk); return (nm,k,wk,seed,(s,np.searchsorted(f,s)/len(f)))
if __name__=='__main__':
    for k,wk in ALL: pool(k,wk)
    jobs=[(nm,k,wk,s) for nm in CONF for (k,wk) in ALL for s in (range(1,7) if nm.startswith('SE') else [1])]
    rows=[]
    with ThreadPoolExecutor(4) as ex:
        for nm,k,wk,s,r in ex.map(job,jobs):
            if r is None: continue
            for x,p in zip(*r): rows.append((nm,k,wk,s,x,p))
    R_=pd.DataFrame(rows,columns=['cfg','slate','wk','seed','score','pct']); R_.to_pickle('leverage.pkl'); print('DONE')
