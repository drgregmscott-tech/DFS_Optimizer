#!/bin/sh
# B4: wk3 build-time ownership vs after status_check apply (OUT+DOUBTFUL zero + ownership refresh).
# Rebuilds wk3 (--backtest-no-leak, season 2026 week 3) with the status file that was current at the
# production pre-lock build (16:30 for main/early, 19:45 for afternoon), saves build-time copy, then
# runs apply to a separate file. Restores output/ via git checkout. Never commit.
cd "$(dirname "$0")/../.."
OUT=analysis/ownership_refit_wk3/b4
mkdir -p $OUT
for s in ${SLATES:-main early afternoon}; do
  if [ $s != afternoon ]; then mv output/player_status_3_20260927_1930*.csv output/player_status_3_20260927_1945*.csv $OUT/ ; SF=output/player_status_3_20260927_163048.csv; else SF=output/player_status_3_20260927_194535.csv; fi
  python scripts/build_projections_statline.py --site dk --season 2026 --week 3 --slate-id dk_classic_wk3_${s}_27Sep2026 \
    --volume-prior --sigma-recalibration --dst-model distributional --backtest-no-leak --vegas-slate-id dk_classic_wk3_main_27Sep2026 2>&1 | grep -E "Wrote|Traceback|Error"
  cp output/final_projections_dk_dk_classic_wk3_${s}_27Sep2026.csv $OUT/buildtime_$s.csv
  python scripts/status_check.py apply --site dk --week 3 --status-file $SF \
    --projections-file $OUT/buildtime_$s.csv --out $OUT/applied_$s.csv 2>&1 | grep -E "OUT|DOUBTFUL|Traceback|Error" | head -4
  git checkout -- output/
  rm -f $OUT/player_status_3_*.csv
done
