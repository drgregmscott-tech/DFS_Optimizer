import sys; sys.path.insert(0,'C:/Users/gmsco/Desktop/DFS_Optimizer/scripts')
from leverage import *
import projection_stack as ps
def T_stack(k,wk):
    season,week=(2026,2) if wk==2 else (2025,23)
    def f(df,d):
        df=df.copy(); S=ps.apply_stack(df,'final_projection','dk',season,week)
        fin=ps.combine(df.final_projection,df.final_projection,S,pd.Series(False,index=df.index))
        df['final_projection']=fin.where(S.notna(),df.final_projection); return df
    return f
CFG={'SE preset(QB1,BB)':(SE_BB,None),'SE user_style(filt7)':(SE+QB1,T_filter(7)),'SE nostack':(SE+['--stack-mode','none'],None),'MME preset':(MME,None)}
def job(a):
    nm,ver,k,wk,seed=a; args,tf=CFG[nm]; args=list(args)+['--seed',str(seed)]
    st=T_stack(k,wk)
    if ver=='stack': t=(lambda df,d,tf=tf,st=st: tf(st(df,d),d) if tf else st(df,d))
    else: t=tf
    L=run(k,wk,args,t,tag=f"S{ver[0]}{abs(hash(nm))%1000}s{seed}")
    if L is None: return (nm,ver,k,wk,seed,None)
    d,_=pool(k,wk); a_=d.set_index('player_id').act
    s=L.assign(a=L.player_id.map(a_).fillna(0)).groupby('lineup_id').a.sum().values
    f=fld(k,wk); return (nm,ver,k,wk,seed,(s,np.searchsorted(f,s)/len(f)))
if __name__=='__main__':
    for k,wk in ALL: pool(k,wk)
    jobs=[(nm,v,k,wk,s) for nm in CFG for v in ('engine','stack') for (k,wk) in ALL for s in (range(1,7) if nm.startswith('SE') else [1])]
    rows=[]
    with ThreadPoolExecutor(6) as ex:
        for nm,v,k,wk,s,r in ex.map(job,jobs):
            if r is None: continue
            for x,p in zip(*r): rows.append((nm,v,k,wk,s,x,p))
    R_=pd.DataFrame(rows,columns=['cfg','ver','slate','wk','seed','score','pct']); R_.to_pickle('stackreplay.pkl'); print('DONE')
