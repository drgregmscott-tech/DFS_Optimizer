import sys; sys.path.insert(0,'C:/Users/gmsco/Desktop/DFS_Optimizer/scripts')
from grid import *
from concurrent.futures import ThreadPoolExecutor
import pickle
SE=['--n-lineups','3','--uniqueness','3','--max-exposure','1.0','--min-salary-pct','99','--flex-positions','RB,WR','--lambda','0.063','--randomization-pct','5']
def targets(k,wk):
    d,_=pool(k,wk)
    x=d[(d.final_projection>0)&(d.position!='DST')]
    g=d[d.position!='DST'].groupby('team').agg(opp=('opponent','first'),ou=('over_under','first'),imp=('implied_total','first'),pts=('act','sum'))
    g=g[g.ou>0]; g['game']=g.apply(lambda r:'-'.join(sorted([r.name,r.opp])),axis=1)
    gm=g.groupby('game').agg(ou=('ou','first'),pts=('pts','sum'))
    top_game=gm.ou.idxmax(); best_game=gm.pts.idxmax()
    top_team=g.imp.idxmax(); best_team=g.pts.idxmax()
    return dict(top_game=top_game,best_game=best_game,top_team=top_team,best_team=best_team)
CONF={
 'auto(qb1,BB) [default]':lambda t:SE+['--stack-mode','qb','--stack-size','1','--bring-back'],
 'qb1,BB pinned top-implied team':lambda t:SE+['--stack-mode','qb','--stack-size','1','--bring-back','--stack-team',t['top_team']],
 'game-stack pinned top-O/U game':lambda t:SE+['--stack-mode','game','--stack-game',t['top_game']],
 'qb1,BB pinned to top-O/U game teams':lambda t:SE+['--stack-mode','qb','--stack-size','1','--bring-back','--stack-team',t['top_game'].split('-')[0]+','+t['top_game'].split('-')[1]],
 'HINDSIGHT best team pinned':lambda t:SE+['--stack-mode','qb','--stack-size','1','--bring-back','--stack-team',t['best_team']],
 'HINDSIGHT best game pinned':lambda t:SE+['--stack-mode','game','--stack-game',t['best_game']],
}
def job(a):
    nm,k,wk,seed,t=a; args=CONF[nm](t)+['--seed',str(seed)]
    L=run(k,wk,args,None,tag=f"t{abs(hash(nm))%10000}s{seed}")
    return (nm,k,wk,seed,None if L is None else score(L,k,wk))
if __name__=='__main__':
    T={}
    for k,wk in ALL: pool(k,wk); T[(k,wk)]=targets(k,wk); print(k,wk,T[(k,wk)],flush=True)
    jobs=[(nm,k,wk,s,T[(k,wk)]) for nm in CONF for (k,wk) in ALL for s in range(1,7)]
    out={}
    with ThreadPoolExecutor(4) as ex:
        for nm,k,wk,s,r in ex.map(job,jobs):
            if r is not None: out.setdefault(nm,{}).setdefault((k,wk),[]).append(r)
    pickle.dump((out,T),open('se_target.pkl','wb')); print('DONE',flush=True)
