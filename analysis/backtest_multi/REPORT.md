# Multi-season leak-free backtest: results (2026-09-24)

Scope: DK 2014-2021, 129 weeks, n = 40,720 skill player-weeks, props off, closing Vegas lines, depth chart and injury status stubbed out. Use for comparing arms, not for absolute accuracy: the volume prior and variance model are fit on these same seasons, and the DK pool is the full Thu-Mon pool.

## Baseline (shipped config, matchup neutralised)
Bias -0.48, MAE 4.79, RMSE 6.68, Pearson .642, within-slate x position Spearman .607, top-N actual 15.68 (hit .552). Stable by season (Pearson .627-.658). RB bias -0.95, DST Pearson .283.

## Arm results (95% CIs by resampling weeks)
- **Matchup restored vs neutralised:** no effect. MAE +0.002 [-0.002, +0.006]; QB slightly worse (+0.045). Keep neutralised. The earlier 240-player-week gain does not replicate at this scale.
- **Stack off:** worse everywhere. MAE +0.101 [+0.080, +0.122], Spearman -.0085, also out of sample (2014-19). TE is also worse without the stack, so the stack does not hurt TE ranking. The stack causes most of the negative bias (-0.48 vs -0.09 without; RB -0.95 vs -0.17).
- **Sigma / p10:** actuals fall below p10 18.0% of the time (2018-21) vs a 10% target. The planned `mean - 1.28*1.07*sigma` fix over-corrects (2.7% below p10). A multiplier fit on 2014-17 gives 0.87 for skill positions and tests at 10.8% on 2018-21. By position: QB 1.37, RB 0.71, WR 0.85, TE 0.82; RB drifts between eras. See out/sigma_coverage_D.txt.

## Leak audit
- Clean: matchup factors (prior weeks only), stack and DST inputs, stats history. Embargo test (remove target-week and later data): 0 of 393 (2019 wk4) and 0 of 374 (2015 wk6) projections changed.
- Mild look-ahead, not neutralised: the DST model uses the actual starting QB and game-time wind. Closing lines are slightly optimistic.
- Stubbed: depth chart, injury status.
- In-sample: volume prior, variance model (2014-2021), stack (2020-21), sigma/DST (2014-17).

## scripts/ change
`scripts/build_projections_statline.py` (+17/-1): opt-in `canonical_teams=False` keyword mapping OAK->LV, SD/SDG->LAC, STL->LA. Fixes the DST abort and the lost Vegas lines for pre-2020 Raiders/Chargers/Rams skill players. Production output verified identical (test_default_preserved.py). Not committed at the time of writing.

## Not done / next
- Level correction after the stack (fit on 2014-19, test on 2020-21): the obvious next test for the -0.48 bias.
- Floor-share (H): needs nflverse historical depth charts (free, 2014-2021).
- QB rush volume: needs an engine change.
- Leave-one-season-out refits of the volume prior and variance model.
