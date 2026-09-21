import sys, shutil, os
from pathlib import Path
import pandas as pd
season=int(sys.argv[1]); wk=int(sys.argv[2]); ROOT=Path(sys.argv[3]); OUT=Path(sys.argv[4]); SRC=Path(sys.argv[5])
dst=OUT/f'final_projections_dk_rotoguru_{season}_wk{wk}.csv'
if dst.exists(): sys.exit(0)
SB=ROOT/f'{season}_{wk}'
if SB.exists(): shutil.rmtree(SB)
(SB/'output').mkdir(parents=True); shutil.copytree(SRC/'scripts',SB/'scripts'); shutil.copytree(SRC/'data',SB/'data')
if (SRC/'config').exists(): shutil.copytree(SRC/'config',SB/'config')
# leakage-free: the build for week wk sees only stats/team stats from weeks < wk of this season
for name in (f'weekly_stats_{season}.parquet',f'team_stats_{season}.parquet'):
    p=SB/'data'/name
    if p.exists():
        d=pd.read_parquet(p); d=d[d['week']<wk]; d.to_parquet(p)
sys.path.insert(0,str(SB/'scripts'))
import backtest_harness as bh
games=bh.load_games(); sid=f'rotoguru_{season}_wk{wk}'
try:
    bh.ensure_per_season_schedule(season); bh.build_vegas_file(games,'dk',season,wk)
    p=bh.run_projection_pipeline('dk',season,wk,sid,None,engine='statline',statline={'sims':2000,'seed':42},dst_model_mode='distributional',prior={'on':True,'floor':None,'k':None,'role_change':True},sigma_recal=True)
    shutil.copy(p,dst); print('ok',sid,flush=True)
except Exception as e:
    print('FAIL',sid,str(e)[-300:],flush=True)
finally:
    sys.path.pop(0); shutil.rmtree(SB,ignore_errors=True)
