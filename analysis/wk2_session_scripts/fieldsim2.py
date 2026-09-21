from expo import *
def sim_field2(d,n=15000,ps=0.5,p2=0.3,lo=48500,seed=3,pw=1.0,flexp=(.5,.4,.1)):
    rng=np.random.default_rng(seed)
    d=d[(d.own>0)&d.act.notna()].reset_index(drop=True)
    g={p:d[d.position==p].reset_index(drop=True) for p in ['QB','RB','WR','TE','DST']}
    W={p:(x.own.values**pw)/(x.own.values**pw).sum() for p,x in g.items()}
    qteam={t:i for i,t in enumerate(g['QB'].team)}
    pc=d[d.position.isin(['WR','TE','RB'])]
    out=[];stk=[];tries=0
    def pick(p,k,excl,mask=None):
        w=W[p].copy(); 
        for e in excl.get(p,()): w[e]=0
        if mask is not None: w=w*mask
        w=w/w.sum(); return list(rng.choice(len(w),k,replace=False,p=w))
    while len(out)<n and tries<n*40:
        tries+=1
        q=rng.choice(len(g['QB']),p=W['QB']); qt=g['QB'].team[q]
        chosen={'RB':[],'WR':[],'TE':[]}; ns=0
        if rng.random()<ps:
            k=2 if rng.random()<p2 else 1
            for _ in range(k):
                cand=[(p,i) for p in ('WR','TE','RB') for i in np.where((g[p].team==qt).values)[0] if i not in chosen[p]]
                if not cand: break
                w=np.array([g[p].own[i] for p,i in cand]); j=rng.choice(len(cand),p=w/w.sum()); p,i=cand[j]
                if (p=='WR' and len(chosen['WR'])<3) or (p=='RB' and len(chosen['RB'])<2) or (p=='TE' and len(chosen['TE'])<1): chosen[p].append(i); ns+=1
        need={'RB':2-len(chosen['RB']),'WR':3-len(chosen['WR']),'TE':1-len(chosen['TE'])}
        for p in need:
            if need[p]>0: chosen[p]+=pick(p,need[p],{p:chosen[p]})
        fx=rng.choice(3,p=flexp); fp=('RB','WR','TE')[fx]; 
        ex=[fp]; f=pick(fp,1,{fp:chosen[fp]})[0]
        dst=rng.choice(len(g['DST']),p=W['DST'])
        pl=[('QB',q)]+[(p,i) for p in chosen for i in chosen[p]]+[(fp,f),('DST',dst)]
        sal=sum(g[p].salary[i] for p,i in pl)
        if sal>50000 or sal<lo: continue
        out.append(sum(g[p].act[i] for p,i in pl)); stk.append(ns)
    return np.array(out),np.mean(stk),len(out)/tries
