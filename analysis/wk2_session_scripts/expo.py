from load import *
SB='sb/output/'
def exposures(slate):
    L=pd.read_csv(SB+f'lineups_multi_dk_{slate}.csv'); n=L.lineup_id.nunique()
    e=L.groupby('player_id').size()/n*100; return e.rename('opt_exp')
def cmp(slate,k=None,wk=2,pos_filter=None):
    pr=pd.read_csv(R+f'output/final_projections_dk_{slate}.csv')
    try: d=pr.merge(exposures(slate),left_on='player_id',right_index=True,how='left').fillna({'opt_exp':0})
    except Exception: d=pr.copy(); d['opt_exp']=0.0
    if wk==2:
        p=players(k).drop_duplicates('name'); p['k']=p.name.map(norm); d['k']=d.player_name.map(norm); d=d.merge(p[['k','own','act']],on='k',how='left')
    else:
        o=pd.read_csv(R+'data/ownership_actual_log.csv'); o=o[o.slate_id==slate][['player_id','actual_ownership_pct']].rename(columns={'actual_ownership_pct':'own'}).drop_duplicates('player_id'); d=d.merge(o,on='player_id',how='left')
        e=pd.read_csv(R+'data/projection_error_log.csv'); e=e[e.slate_id==slate][['player_id','actual_fpts']].drop_duplicates('player_id').rename(columns={'actual_fpts':'act'}); d=d.merge(e,on='player_id',how='left')
    d['own']=d.own.fillna(0); return d
