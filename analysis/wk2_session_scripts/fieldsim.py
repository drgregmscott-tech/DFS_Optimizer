from expo import *
rng=np.random.default_rng(7)
def sim_field(d,n=30000,lo=48500,pw=1.0,stack_p=0.0):
    """d: pool with columns position, salary, own(actual %), act. returns array of lineup scores"""
    d=d[(d.own>0)&d.act.notna()].copy()
    pos={p:d[d.position==p].reset_index(drop=True) for p in ['QB','RB','WR','TE','DST']}
    w={p:(g.own.values**pw)/(g.own.values**pw).sum() for p,g in pos.items()}
    tot=[];
    B=n*6
    qb=rng.choice(len(pos['QB']),B,p=w['QB']); dst=rng.choice(len(pos['DST']),B,p=w['DST'])
    def multi(p,k):
        # k distinct via gumbel top-k
        g=-np.log(-np.log(rng.random((B,len(pos[p]))))) + np.log(w[p])
        return np.argsort(-g,axis=1)[:,:k]
    rb=multi('RB',3); wr=multi('WR',4); te=multi('TE',2)
    sal=lambda p,i: pos[p].salary.values[i]; pts=lambda p,i: pos[p].act.values[i]
    # roster: QB, RB2, WR3, TE1, FLEX (one of rb[2], wr[3], te[1] chosen by 45/40/15), DST
    fx=rng.choice(3,B,p=[.5,.4,.1])
    fs=np.where(fx==0,sal('RB',rb[:,2]),np.where(fx==1,sal('WR',wr[:,3]),sal('TE',te[:,1])))
    fp=np.where(fx==0,pts('RB',rb[:,2]),np.where(fx==1,pts('WR',wr[:,3]),pts('TE',te[:,1])))
    S=sal('QB',qb)+sal('RB',rb[:,0])+sal('RB',rb[:,1])+sal('WR',wr[:,0])+sal('WR',wr[:,1])+sal('WR',wr[:,2])+sal('TE',te[:,0])+fs+sal('DST',dst)
    P=pts('QB',qb)+pts('RB',rb[:,0])+pts('RB',rb[:,1])+pts('WR',wr[:,0])+pts('WR',wr[:,1])+pts('WR',wr[:,2])+pts('TE',te[:,0])+fp+pts('DST',dst)
    ok=(S<=50000)&(S>=lo); return P[ok][:n], ok.mean()
