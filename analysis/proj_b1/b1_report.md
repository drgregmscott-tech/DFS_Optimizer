# B1: matchup_factor ablation on the guarded, leak-free rebuilds (2026-09-24)

Script: `analysis/proj_b1/b1_matchup.py <guarded_dir>`. Full output: `b1_out.txt`. Frame: `b1_frame.csv`.
Validation rebuilds (wk2 early): `validate_wk2_early_control.csv` (unchanged inputs) and `validate_wk2_early_mf1.csv` (matchup file set to 1.0). `output/` was restored with `git checkout -- output/` after each build; both printed "Wrote 408 players".

**Sample:** QB/RB/WR/TE, shipped final_projection > 8, with an actual. 472 slate rows; **240 unique player-weeks after dedup** (main > early > afternoon): wk1 112, wk2 128; QB 49, RB 69, WR 92, TE 30. Within-slate metrics use 23 slate x position cells (n>=6). **That is 2 weeks and 6 slates. Treat everything below as a direction, not a precise size.**

## 0. How the factor is built and applied (and why the "free" ablation was wrong)

- `projections_matchup.py`: for each (defense, position), sum the fantasy points allowed to that position each week, then average over weeks -> ratio to the league mean -> shrink: `(g*raw + 4*1)/(g + 4)`, where g is the number of games in the lookback. Uses REG weeks strictly before the target week, so it is leak-free.
  - **wk1** (`--season 2025 --week 23`): the **whole 2025 season**, g = 17, so weight 17/21 = 0.81 on the raw ratio. This is last year's defenses, not this year's.
  - **wk2** (`--season 2026 --week 2`): **one game** of 2026, weight 1/5 = 0.20.
  - Dispersion (alive skill rows): wk1 std QB .154 / RB .122 / TE .233 / WR .128, range 0.61-1.57 (TE). wk2 std .100 / .097 / .110 / .065, range 0.80-1.26. So the "0.66-2.21x" swing claim does not describe these builds. **Wk1 (the well-sampled prior-season factor) is the more dispersed one.**
- `statline_model.simulate` multiplies **only yd_rate and td_rate** by `market_factor = matchup*vegas`. Volume, receptions, INTs and fumbles are not scaled. So `final * mf^(a-1)` is **not** a valid ablation. It overstates the effect by roughly 1/0.6 for WR and TE. The scaled share of engine points is QB 1.02, RB .79, WR .62, TE .60.
- Emulator used: `engine_new = engine + S*(r-1)`, with S = yardage+TD points from the proj_* columns and r = new/old market factor. **Validated** against a real rebuild with matchup neutralised (wk2 early, n=392): corr of predicted vs true delta **0.9997**, MAE 0.018 (the true deltas average 0.22). The naive scaling gives MAE 0.064. The control rebuild matched the guarded file exactly (max diff 0.0).
- **DST excluded.** A DST's matchup_factor is display-only (its projection divided by the league mean, in build_projections.py ~l.348). It is never applied, so any "DST effect" would be an artefact.
- The main metrics use engine_projection (no stack). The stack delta is additive and computed from the engine, so "final" = engine variant + the unchanged stack_delta, reported as a secondary result. Nothing was re-normalised.

## 1. Ablation (engine, n=240 player-weeks / 23 cells)

| variant | Pearson | Spearman | bias | MAE | RMSE | cell Spearman | cell top-N actual |
|---|---|---|---|---|---|---|---|
| a=0 | **.484** | **.503** | -0.40 | **6.30** | **8.39** | **.325** | **15.97** |
| a=0.25 | .475 | .497 | -0.42 | 6.35 | 8.44 | .306 | 15.84 |
| a=0.5 | .464 | .486 | -0.42 | 6.41 | 8.50 | .275 | 15.65 |
| a=0.75 | .452 | .475 | -0.42 | 6.48 | 8.57 | .274 | 15.76 |
| **a=1 (current)** | .438 | .463 | -0.41 | 6.56 | 8.65 | .268 | 15.64 |
| a=1.25 | .423 | .449 | -0.39 | 6.65 | 8.75 | .251 | 15.28 |
| vegas b=0 | .436 | .468 | -0.48 | 6.48 | 8.64 | .261 | 15.06 |
| vegas b=0.5 | .443 | .465 | -0.47 | 6.48 | 8.61 | .273 | 14.91 |
| a=0, b=0 | .485 | .502 | -0.46 | 6.26 | 8.39 | .342 | 16.64 |
| a=0, b=0.5 | .492 | .508 | -0.46 | 6.24 | 8.35 | .332 | 16.24 |

- Every metric changes monotonically in a; bias is flat, so this is a ranking and shape effect, not a level shift.
- Final (+stack): a=0 vs a=1 gives Pearson .529 vs .494 and MAE 6.44 vs 6.62.
- Vegas: removing it does not clearly help. The pooled correlation is flat to worse and top-N gets worse, so leave vegas alone.

Per week (engine): wk1 Pearson a=0 .497 vs a=1 .427, MAE 7.10 vs 7.52 (n=112). wk2 Pearson .450 vs .429, MAE 5.60 vs 5.72 (n=128). **Wk2 cell Spearman favours a=1 slightly (.315 vs .310).**

## 2. Leave-one-week-out (pick the exponent on one week, test on the other)

| metric | train wk1 -> test wk2 | train wk2 -> test wk1 |
|---|---|---|
| MAE | a=0, **+0.121** | a=0, **+0.420** |
| Pearson | a=0, **+0.021** | a=0, **+0.069** |
| cell Spearman | a=0, **-0.005** | a=1 chosen, 0.000 |

On MAE and Pearson, both folds pick a=0 and both improve. On within-slate Spearman the finding **fails the both-folds rule** (wk2 slightly prefers a=1). So the pooled-accuracy result passes cross-validation, but the per-slate ranking result does not.

## 3. Bootstrap (+ = first variant better)

Pooled metrics resample 240 player-weeks. Cell metrics resample the 23 cells, and separately the 6 slates.

| comparison | MAE | Pearson | cell Spearman (cell CI / slate CI) | cell top-N actual |
|---|---|---|---|---|
| a=0 vs a=1 | +0.26 [+0.10, +0.42] | +.046 [+.013, +.079] | +.057 [+.016, +.105] / [+.007, +.102], 18/23 wins | +0.33 [-0.52, +1.31], 7/23 |
| a=0.5 vs a=1 | +0.15 [+0.07, +0.23] | +.027 [+.011, +.044] | +.007 [-.014, +.027] | +0.01 [-0.81, +0.98] |
| a=0.5 vs a=0 | -0.11 [-0.20, -0.03] | -.019 [-.036, -.003] | -.050 [-.082, -.024] | -0.32 [-0.65, -0.06] |

By week, MAE for a=0 vs a=1: wk1 +0.42 [+0.13, +0.72]; **wk2 +0.12 [-0.02, +0.26], which crosses 0.**

**Top-N actual (what matters for lineups) cannot be distinguished between options.**

## 4. Games-played shrink (emulated: mf_new = 1 + w(mf-1))

- A single w for both weeks: the result is the same monotone pattern as the exponent, best at w=0 (MAE 6.30 vs 6.56).
- A separate w per week (6x6 grid in b1_out.txt): the best is w1=0, w2=0 on MAE and Pearson. On cell Spearman it is w1=0 with w2 anywhere in 0..1.25 (range .313-.327, which is noise).
- Mapping to K for wk2 (1 game): relative weight = 5/(1+K). K=8 -> .56, K=19 -> .25, K=49 -> .10. The wk2 data prefers w=0 but only weakly (MAE 5.60 at w=0 vs 5.72 at w=1).
- **Key point:** the larger harm is in **wk1, where the factor had 17 games behind it**. A shrink constant keyed to 2026 games played would not have touched wk1. Wk1 did not suffer from too few games: it used last season's defenses. So a games-played schedule does not address what the data shows.
- Is the factor just too noisy, or wrong? Regress (actual minus the projection without matchup) on the points the factor adds, S*log(mf). The slope is **-0.83 in wk1 and -0.81 in wk2** (corr -.15 and -.10). A slope of 1 would mean the factor is right; 0 would mean it is noise. Both weeks point the wrong way, which is stronger than noise. One plausible mechanism is double counting with vegas, since implied totals already price in the defense. Negative exponents fit slightly better in both weeks (wk1 MAE 6.97 at a=-0.5 vs 7.10 at a=0), but **that is overfitting and should not be shipped**.

## 5. Splits (dedup; MAE gain from a=0 over a=1, 95% CI)

- By position: QB +0.75 [+0.19, +1.34] (n=49); WR +0.14 [+0.01, +0.27] (n=92); TE +0.20 [-0.14, +0.56] (n=30); RB +0.10 [-0.16, +0.36] (n=69). No position is clearly helped by matchup; QB is hurt most because nearly 100% of QB points get scaled. QB cell Spearman gains +.13 but top-3 actual falls -1.0 (6 cells).
- By salary tier: gains are positive in every tier (<4.5k +0.08, 4.5-6k +0.24, 6-7.5k +0.36, 7.5k+ +0.70 with n=8).
- DST is excluded throughout (its factor is not applied), so the result holds with DST out by construction.

## 6. Recommendation: (a) drop matchup for now (neutral 1.0 for skill positions); leave vegas as is

- **Basis:** 2 weeks, 6 slates, 240 player-weeks. Pooled MAE, RMSE and Pearson improve in both weeks and in both LOWO folds. The CI excludes 0 when the weeks are pooled; in wk2 alone it does not.
- **Size:** about 0.26 MAE and +.046 Pearson. That is modest, not a headline. Within-slate Spearman (+.057, CI excludes 0) fails the both-folds test, and top-N actual cannot be distinguished.
- **Why (a) over (b):** the evidence cannot tell a=0 from a heavy shrink such as K≈19 in wk2 (w=.25, MAE difference about 0.03). Shrinking cannot fix wk1, where the harm came from a well-sampled prior-season factor pointing the wrong way. Dropping is also the simplest option to reverse.
- Revisit around Week 6, with 5+ games of 2026 data and a vegas-orthogonal version, e.g. the residual of points allowed after controlling for the opponent's implied total.
- (c) leave as-is is the least supported option: it is never the best on any pooled metric in either week.

**Caveats:**
- Emulated rather than full rebuilds; validated to delta corr .9997 on one slate.
- The stack is held fixed.
- The player set is conditioned on the shipped final > 8.
- One wk2 week of the "1-game" regime is not much evidence about Weeks 3-4.
