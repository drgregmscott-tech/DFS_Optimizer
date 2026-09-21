import sys; sys.path.insert(0,'C:/Users/gmsco/Desktop/DFS_Optimizer/scripts')
from grid import *
from concurrent.futures import ThreadPoolExecutor
import pickle
SE=['--n-lineups','3','--uniqueness','3','--max-exposure','1.0','--min-salary-pct','99','--flex-positions','RB,WR','--lambda','0.063','--randomization-pct','5']
def T_filter(th):
    def f(df,d):
        return df[~(df.position.isin(['RB','WR','TE'])&(df.final_projection<=th))].copy()
    return f
def T_filter_own(th,g):
    def f(df,d): return T_own(g,'est')(T_filter(th)(df,d),d)
    return f
QB1=['--stack-mode','qb','--stack-size','1']
CONF={
 'user_style(QB1,noBB,filt7)':(SE+QB1,T_filter(7)),
 'preset(QB1,BB,nofilt)':(SE+QB1+['--bring-back'],None),
 'QB1,noBB,nofilt':(SE+QB1,None),
 'QB1,BB,filt7':(SE+QB1+['--bring-back'],T_filter(7)),
 'nostack,filt7':(SE+['--stack-mode','none'],T_filter(7)),
 'nostack,nofilt':(SE+['--stack-mode','none'],None),
 'QB2,noBB,filt7':(SE+['--stack-mode','qb','--stack-size','2'],T_filter(7)),
 'QB1,noBB,filt5':(SE+QB1,T_filter(5)),
 'user_style,lam0':(swap(SE,'--lambda','0')+QB1,T_filter(7)),
 'user_style,lam-0.05':(swap(SE,'--lambda','-0.05')+QB1,T_filter(7)),
 'user_style,lam+0.15':(swap(SE,'--lambda','0.15')+QB1,T_filter(7)),
 'user_style+estown0.10':(SE+QB1,T_filter_own(7,0.10)),
}
SEEDS=range(1,9)
def job(a):
    nm,k,wk,seed=a; args,tf=CONF[nm]; args=args
    args=args+['--seed',str(seed)]
    L=run(k,wk,args,tf,tag=f"{abs(hash(nm))%10000}s{seed}")
    if L is None: return (nm,k,wk,seed,None)
    return (nm,k,wk,seed,score(L,k,wk))
if __name__=='__main__':
    for k,wk in ALL: pool(k,wk)     # warm sim fields
    jobs=[(nm,k,wk,s) for nm in CONF for (k,wk) in ALL for s in SEEDS]
    out={}
    with ThreadPoolExecutor(4) as ex:
        for nm,k,wk,s,r in ex.map(job,jobs):
            if r is not None: out.setdefault(nm,{}).setdefault((k,wk),[]).append(r)
    pickle.dump(out,open('se_grid.pkl','wb')); print('DONE')
