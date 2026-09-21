import sys; sys.path.insert(0,'C:/Users/gmsco/Desktop/DFS_Optimizer/scripts')
from harness import *
import salary_anchor as sa, pickle, json
AN=sa.load_anchor('dk')
BASE=['--n-lineups','20','--uniqueness','1','--min-salary-pct','99','--flex-positions','RB,WR','--seed','1']
MME=BASE+['--max-exposure','0.35','--stack-mode','qb','--stack-size','1','--bring-back','--randomization-pct','18','--lambda','-0.005','--dart-exposure-cap','0.10','--dart-floor-threshold','1.0']
def swap(a,key,val):
    a=list(a); 
    if key in a: a[a.index(key)+1]=val
    else: a+= [key,val]
    return a
def drop(a,key,n=1):
    a=list(a); i=a.index(key); del a[i:i+1+n]; return a
def dropflag(a,key):
    a=list(a); a.remove(key); return a
def T_anchor(w):
    def f(df,d):
        df=df.copy(); m=(df.position!='DST')&(df.final_projection>0)
        an=sa.anchor_points(AN,df.position.values,df.salary.values)
        df.loc[m,'final_projection']=(1-w)*df.loc[m,'final_projection']+w*an[m.values]; return df
    return f
def T_own(g,col):
    def f(df,d):
        df=df.copy()
        if col=='actual':
            o=d.set_index('player_id').own; df['_o']=df.player_id.map(o).fillna(0)
        else: df['_o']=df.estimated_ownership_pct
        m=df.final_projection>0
        df.loc[m,'final_projection']=(df.loc[m,'final_projection']-g*df.loc[m,'_o']).clip(lower=0.1); return df.drop(columns='_o')
    return f
def T_oracle(df,d):
    df=df.copy(); a=d.set_index('player_id').act; m=df.final_projection>0; df.loc[m,'final_projection']=df.loc[m,'player_id'].map(a).fillna(0)+0.01; return df
CONF={
 'MME_preset':(MME,None),
 'MME_nostack_nocap':(swap(swap(dropflag(drop(MME,'--stack-mode') if False else MME,'--bring-back'),'--stack-mode','none'),'--max-exposure','1.0'),None),
 'MME_stack2':(swap(MME,'--stack-size','2'),None),
 'MME_cap60':(swap(MME,'--max-exposure','0.6'),None),
 'MME_rand5':(swap(MME,'--randomization-pct','5'),None),
 'MME_rand30':(swap(MME,'--randomization-pct','30'),None),
 'anchor50':(MME,T_anchor(0.5)),
 'anchor100':(MME,T_anchor(1.0)),
 'estown_pen0.10':(MME,T_own(0.10,'est')),
 'actown_pen0.10':(MME,T_own(0.10,'actual')),
 'oracle':(MME,T_oracle),
}
if __name__=='__main__':
    out={}
    names=sys.argv[1:] or list(CONF)
    for nm in names:
        args,tf=CONF[nm]; res={}
        for (k,wk) in ALL:
            L=run(k,wk,args,tf,tag=nm.replace('.','_'))
            if L is None: continue
            res[(k,wk)]=score(L,k,wk)
        out[nm]=res; print(nm,summarize(res),flush=True)
        pickle.dump(out,open('grid_'+('_'.join(names) if len(names)<3 else 'all')+'.pkl','wb'))
