import subprocess, sys, os
from fieldsim import *
SB2='sb2/'
ALL=[('main',2),('early',2),('afternoon',2),('main',1),('early',1),('afternoon',1)]
SID={('main',2):'dk_classic_wk2_main_20Sep2026',('early',2):'dk_classic_wk2_early_20Sep2026',('afternoon',2):'dk_classic_wk2_afternoon_20Sep2026',
     ('main',1):'dk_classic_wk1_main_13Sep2026',('early',1):'dk_classic_wk1_early_13Sep2026',('afternoon',1):'dk_classic_wk1_afternoon_13Sep2026'}
_cache={}
def pool(k,wk):
    if (k,wk) in _cache: return _cache[(k,wk)]
    d=cmp(SID[(k,wk)],k if wk==2 else None,wk=wk); d['act']=d.act.fillna(0)
    sim,_=sim_field(d,20000,lo=48500,pw=1.0)
    _cache[(k,wk)]=(d,np.sort(sim)); return _cache[(k,wk)]
def make_slate(k,wk,transform=None,tag='X'):
    src=R+f'output/final_projections_dk_{SID[(k,wk)]}.csv'; df=pd.read_csv(src)
    sid=SID[(k,wk)]+'_'+tag
    if transform is not None:
        d,_=pool(k,wk); df=transform(df,d)
    df.to_csv(SB2+f'output/final_projections_dk_{sid}.csv',index=False); return sid
def run(k,wk,args,transform=None,tag='X'):
    sid=make_slate(k,wk,transform,tag)
    cmd=[sys.executable,'scripts/optimizer.py','--site','dk','--slate-id',sid]+args
    r=subprocess.run(cmd,cwd=SB2,capture_output=True,text=True)
    f=SB2+f'output/lineups_multi_dk_{sid}.csv'
    if not os.path.exists(f) or r.returncode!=0: 
        print('FAIL',k,wk,tag,r.stdout[-300:],r.stderr[-300:]); return None
    L=pd.read_csv(f); os.remove(f); return L
def score(L,k,wk):
    d,sim=pool(k,wk); a=d.set_index('player_id').act
    s=L.assign(a=L.player_id.map(a).fillna(0)).groupby('lineup_id').a.sum().values
    pct=np.searchsorted(sim,s)/len(sim)  # share of field beaten
    return s,pct
def summarize(res):
    # res: dict (k,wk)->(scores,pcts)
    allp=np.concatenate([v[1] for v in res.values()]); alls=np.concatenate([v[0] for v in res.values()])
    return dict(n=len(allp),mean_score=alls.mean().round(1),mean_pct=(allp.mean()*100).round(1),top25=(allp>=.75).mean().round(3),top10=(allp>=.90).mean().round(3),top1=(allp>=.99).mean().round(3),best_avg=np.mean([v[1].max() for v in res.values()]).round(3))
