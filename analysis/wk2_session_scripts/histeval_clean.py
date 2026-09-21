from load import *
import glob, numpy.linalg as la
R0='C:/Users/gmsco/Desktop/DFS_Optimizer/'
def build():
    rows=[]
    for f in sorted(glob.glob('hist_proj_clean/final_projections_dk_rotoguru_*_wk*.csv')):
        s=re.search(r'rotoguru_(\d+)_wk(\d+)',f); yr,wk=int(s.group(1)),int(s.group(2))
        p=pd.read_csv(f); p=p[p.position.isin(['QB','RB','WR','TE'])].copy(); p['season']=yr; p['week']=wk; rows.append(p)
    P=pd.concat(rows,ignore_index=True); P['k']=P.player_name.map(norm)
    A=pd.concat([pd.read_csv(R0+f'data/rotoguru_actuals_dk_{y}.csv') for y in (2019,2020,2021)]); A['k']=A.name.map(norm)
    A=A[A.rotoguru_position.isin(['QB','RB','WR','TE'])][['season','week','k','team','actual_points']].rename(columns={'team':'rteam'})
    A=A.drop_duplicates(['season','week','k'])
    M=P.merge(A,on=['season','week','k'],how='inner')
    return P,A,M
if __name__=='__main__':
    P,A,M=build(); print(len(P),len(M),M.groupby('season').week.nunique().to_dict())

def features(M):
    # ---- points history (rotoguru actuals, 2019-2021, ordered) ----
    A=pd.concat([pd.read_csv(R0+f'data/rotoguru_actuals_dk_{y}.csv') for y in (2019,2020,2021)]); A['k']=A.name.map(norm)
    A=A[A.rotoguru_position.isin(['QB','RB','WR','TE'])].drop_duplicates(['season','week','k']).sort_values(['k','season','week'])
    g=A.groupby('k').actual_points
    A['l3']=g.transform(lambda s:s.shift(1).rolling(3,min_periods=1).mean())
    A['l6']=g.transform(lambda s:s.shift(1).rolling(6,min_periods=1).mean())
    A['ewm']=g.transform(lambda s:s.shift(1).ewm(alpha=0.35,min_periods=1).mean())
    A['n_prior']=g.transform(lambda s:s.shift(1).expanding().count())
    # season-to-date and prior-season means
    A['std']=A.groupby(['k','season']).actual_points.transform(lambda s:s.shift(1).expanding().mean())
    ps=A.groupby(['k','season']).actual_points.mean().rename('ps').reset_index(); ps['season']+=1
    A=A.merge(ps,on=['k','season'],how='left')
    M=M.merge(A[['season','week','k','l3','l6','ewm','n_prior','std','ps']],on=['season','week','k'],how='left')
    # ---- usage (nflverse) ----
    ws=pd.concat([pd.read_parquet(R0+f'data/weekly_stats_{y}.parquet') for y in (2019,2020,2021)]); ws=ws[ws.season_type=='REG'].sort_values(['player_id','season','week'])
    for c in ['targets','carries','attempts','receptions','target_share','air_yards_share','wopr','receiving_air_yards','rushing_epa','receiving_epa']:
        if c not in ws: ws[c]=0.0
    use=['targets','carries','attempts','target_share','air_yards_share','wopr','receiving_air_yards']
    for c in use: ws['u_'+c]=ws.groupby('player_id')[c].transform(lambda s:s.shift(1).rolling(4,min_periods=1).mean())
    M=M.merge(ws[['player_id','season','week']+['u_'+c for c in use]].drop_duplicates(['player_id','season','week']),on=['player_id','season','week'],how='left')
    # ---- environment (schedules) ----
    S=pd.concat([pd.read_parquet(R0+f'data/schedules_{y}.parquet') for y in (2019,2020,2021)]); S=S[S.game_type=='REG']
    h=S[['season','week','home_team','away_team','spread_line','total_line','temp','wind','roof','home_rest','away_rest']].copy()
    h1=h.rename(columns={'home_team':'team','away_team':'opp','home_rest':'rest'}); h1['is_home']=1; h1['fav']=h1.spread_line   # spread_line = home margin expected
    a1=h.rename(columns={'away_team':'team','home_team':'opp','away_rest':'rest'}); a1['is_home']=0; a1['fav']=-a1.spread_line
    E=pd.concat([h1,a1])[['season','week','team','is_home','fav','temp','wind','roof','rest']]
    E['dome']=E.roof.isin(['dome','closed']).astype(float)
    M=M.merge(E.drop(columns='roof'),on=['season','week','team'],how='left')
    return M
