from load import *
import numpy.linalg as la
def build():
    rows=[]
    o=pd.read_csv(R+'data/ownership_actual_log.csv'); o=o[o.slate_format=='classic']
    for wk,slist in ((1,['dk_classic_wk1_main_13Sep2026','dk_classic_wk1_early_13Sep2026','dk_classic_wk1_afternoon_13Sep2026']),(2,[slates[k] for k in ['main','early','afternoon']])):
        for sid in slist:
            pr=pd.read_csv(R+f'output/final_projections_dk_{sid}.csv')
            sal=pd.read_csv(R+f'data/salaries_dk_{sid}.csv')[['player_id','AvgPointsPerGame']].drop_duplicates('player_id')
            pr=pr.merge(sal,on='player_id',how='left')
            if wk==1:
                oo=o[o.slate_id==sid][['player_id','actual_ownership_pct']].rename(columns={'actual_ownership_pct':'own'}).drop_duplicates('player_id')
                pr=pr.merge(oo,on='player_id',how='left')
                # actual pts from error log
                e=pd.read_csv(R+'data/projection_error_log.csv'); e=e[e.slate_id==sid][['player_id','actual_fpts']].drop_duplicates('player_id'); pr=pr.merge(e,on='player_id',how='left'); pr=pr.rename(columns={'actual_fpts':'act'})
            else:
                k=[a for a,b in slates.items() if b==sid][0]; p=players(k).drop_duplicates('name'); p['k']=p.name.map(norm); pr['k']=pr.player_name.map(norm)
                pr=pr.merge(p[['k','own','act']],on='k',how='left')
            pr['own']=pr.own.fillna(0); pr['slate']=sid; pr['week']=wk; pr['ngames']=pr.team.nunique()/2
            rows.append(pr)
    return pd.concat(rows,ignore_index=True)
