#!/usr/bin/env bash
# Rebuild all 6 backtest slates base (fix=0) and fix (fix=1), then wk3 main live-style, restoring output/ after each.
cd /c/Users/gmsco/Desktop/DFS_Optimizer
FLAGS="--volume-prior --sigma-recalibration --dst-model distributional"
run () { # tag fix args...
  local tag=$1 fix=$2; shift 2
  python analysis/proj_h/h_build.py "$tag" "$fix" -- "$@" > "analysis/proj_h/builds/log_$tag.txt" 2>&1
  grep -E "Wrote [0-9]+ players|\[H\] floor" "analysis/proj_h/builds/log_$tag.txt" | sed "s/^/$tag: /"
  git checkout -- output/
}
mkdir -p analysis/proj_h/builds
for s in main early afternoon; do
  for fx in 0 1; do
    t=$([ $fx = 1 ] && echo fix || echo base)
    run ${t}_wk2_$s $fx --site dk --season 2026 --week 2 --slate-id dk_classic_wk2_${s}_20Sep2026 --vegas-slate-id dk_classic_wk2_main_20Sep2026 $FLAGS --backtest-no-leak
    run ${t}_wk1_$s $fx --site dk --season 2025 --week 23 --slate-id dk_classic_wk1_${s}_13Sep2026 --vegas-slate-id dk_classic_wk1_main_13Sep2026 $FLAGS --backtest-no-leak
  done
done
for fx in 0 1; do
  t=$([ $fx = 1 ] && echo fix || echo base)
  run ${t}_wk3_main $fx --site dk --season 2026 --week 3 --slate-id dk_classic_wk3_main_27Sep2026 --vegas-slate-id dk_classic_wk3_main_27Sep2026 $FLAGS
done
echo ALLDONE
