from load import *
def dkpts(d):
    f=lambda c: d[c].fillna(0)
    p=f('passing_yards')*.04+f('passing_tds')*4-f('passing_interceptions')+f('rushing_yards')*.1+f('rushing_tds')*6+f('receptions')+f('receiving_yards')*.1+f('receiving_tds')*6
    p+=-(f('rushing_fumbles_lost')+f('receiving_fumbles_lost')+f('sack_fumbles_lost'))+2*(f('passing_2pt_conversions')+f('rushing_2pt_conversions')+f('receiving_2pt_conversions'))
    p+=3*(f('passing_yards')>=300)+3*(f('rushing_yards')>=100)+3*(f('receiving_yards')>=100)
    return p
W=pd.read_parquet('ws2026_fresh.parquet'); W=W[W.season_type=='REG']; W['dk']=dkpts(W)
W['tds']=W.rushing_tds.fillna(0)+W.receiving_tds.fillna(0)
def usage_frame(wk,slate):
    pr=pd.read_csv(R+f'output/final_projections_dk_{slate}.csv'); pr=pr[(pr.position!='DST')&(pr.final_projection>0)]
    a=W[W.week==wk][['player_id','dk','targets','receptions','carries','attempts','receiving_yards','rushing_yards','passing_yards','tds','passing_tds']].rename(columns={'dk':'act'})
    m=pr.merge(a,on='player_id',how='left')
    # only teams that have played: all by now
    m['played']=m.act.notna(); m[['act','targets','carries','attempts','receptions']]=m[['act','targets','carries','attempts','receptions']].fillna(0)
    m['week']=wk; return m
U=pd.concat([usage_frame(1,'dk_classic_wk1_main_13Sep2026'),usage_frame(2,'dk_classic_wk2_main_20Sep2026')])
U.to_pickle('U.pkl')
