#!/bin/sh
# B1: leak-free rebuilds of wk1/wk2 DK classic with current code. Copies results into
# analysis/ownership_refit_wk3/rebuilds/ then restores output/ via git checkout. Never commit rebuilds.
cd "$(dirname "$0")/../.."
OUT=analysis/ownership_refit_wk3/rebuilds
for s in wk1_main_13Sep2026 wk1_early_13Sep2026 wk1_afternoon_13Sep2026; do
  python scripts/build_projections_statline.py --site dk --season 2025 --week 23 --slate-id dk_classic_$s \
    --volume-prior --sigma-recalibration --dst-model distributional --backtest-no-leak 2>&1 | grep -E "Wrote|Error|Traceback|layered|FFC"
  cp output/final_projections_dk_dk_classic_$s.csv $OUT/
done
for s in wk2_main_20Sep2026 wk2_early_20Sep2026 wk2_afternoon_20Sep2026; do
  python scripts/build_projections_statline.py --site dk --season 2026 --week 2 --slate-id dk_classic_$s \
    --volume-prior --sigma-recalibration --dst-model distributional --backtest-no-leak 2>&1 | grep -E "Wrote|Error|Traceback|layered|FFC"
  cp output/final_projections_dk_dk_classic_$s.csv $OUT/
done
git checkout -- output/
