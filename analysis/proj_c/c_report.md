# C: calibration / spread correction on the shipped build (2026-09-24)

Reproduce (writes `c_out.txt`, `c_stackweight_out.txt`, `c_frame.csv`, `c_qb_frame.csv`, `c_lowo.csv`):

```
python analysis/proj_c/c_calib.py       <shipped_dir> > analysis/proj_c/c_out.txt
python analysis/proj_c/c_stackweight.py <shipped_dir> > analysis/proj_c/c_stackweight_out.txt
```
`<shipped_dir>` = the six leak-free shipped builds (guard in, matchup neutral for skill positions, stack on).
Frame: same as B1. Skill rows are alive players with shipped final > 8 and an actual score; player-weeks are
dedup'd main > early > afternoon. DST uses all alive DSTs with an actual score.
**n = 238 unique non-DST player-weeks (wk1 112, wk2 126) plus 50 DST; 472 slate-level rows; only 9 players at $7.5k+.**
There are two independent weeks. The six slates overlap, because main contains most of early and afternoon.

## 0. Leakage of the stack

`data/projection_stack_dk.json` is fit by `scripts/fit_projection_stack.py` on
`projection_stack_training_dk.csv`. That file holds 2020-21 weeks 2-17 only (12,052 rows) and has **no overlap
with the 2026 wk1/wk2 actuals**, so the coefficients are not leaky. Soft leak: the `projection_stack.py`
docstring cites wk1/wk2 2026 results ("held on 2026 data", "wk2 studs") as grounds for shipping it. The
decision to ship was therefore made while looking at these two weeks. Any "the stack helps" read on these
weeks is optimistic. Nothing fitted in this study touches its test week: all candidates are fit on one week
and scored on the other.

## 1. Calibration (act ~ proj, dedup, 95% CI from a player-week cluster bootstrap, B=2000)

| grp | n | slope final [CI] | icpt | R2 | slope ENGINE [CI] | bias final | sd proj / sd act |
|---|---|---|---|---|---|---|---|
| QB | 49 | 0.82 [0.20, 1.52] | +4.1 | .126 | 0.66 [0.21, 1.14] | -1.2 | 3.8 / 8.8 |
| RB | 67 | 1.43 [0.78, 2.01] | -6.2 | .285 | 1.17 [0.66, 1.55] | +0.8 | 3.6 / 9.6 |
| WR | 92 | 1.74 [0.85, 2.51] | -9.1 | .256 | 1.27 [0.54, 2.00] | +0.4 | 2.9 / 9.9 |
| TE | 30 | 0.51 [-2.04, 1.57] | +3.4 | .026 | 1.04 [-0.10, 1.98] | +1.6 | 2.2 / 7.1 |
| DST | 50 | 1.18 [-0.10, 2.51] | -2.2 | .091 | (same) | +0.9 | 1.6 / 6.1 |
| **pooled non-DST** | 238 | **1.33 [1.01, 1.67]** | -4.6 | .260 | **0.96 [0.72, 1.19]** | +0.3 | 3.7 / 9.6 |

The un-dedup'd within-slate view (n=472, same clustering) is nearly the same: pooled 1.31 [0.99, 1.66], engine 0.93.
By week, the pooled final slope is **1.54 in wk1 and 1.10 in wk2**. The QB slope is 1.31 in wk1 and 0.32 in wk2.

**Decomposition.** The slope above 1 comes **entirely from the stack**. The engine alone is calibrated in spread
(slope 0.96, sd 4.86). The stack delta is strongly anti-correlated with the engine (r = -0.70): it pulls every
player toward the position mean, which cuts the spread to sd 3.66. It still adds some signal (R2 .235 -> .260).
The joint fit act ~ -3.7 + 1.28·eng + 1.01·delta says the delta is about the right size and the engine part is
under-weighted. By week that is b_eng 1.49 / 1.08 and c_delta 1.30 / 0.94, so the ratio is stable but the level is not.

**Decile table (final, non-DST).** Deciles 1-7 (proj 8-14) are over-projected by +0.2 to +2.4. Deciles 8-10
(proj 14-24) are under-projected by -1.1, -2.5 and -2.0. The shape is monotone-ish and noisy: decile 6 is
-0.3 and decile 7 is +1.5. Per-position bins are in `c_out.txt`. The WR top quintile is -3.5 and the TE top
quartile is +6.3 (the opposite direction).

**Salary tier (bias = proj - act, bootstrap 95% CI).**

| tier | n | bias | CI | wk1 | wk2 |
|---|---|---|---|---|---|
| <4k | 13 | +0.5 | [-1.8, +2.9] | -2.0 | +2.7 |
| 4-5k | 54 | +1.1 | [-1.0, +3.0] | +1.1 | +1.2 |
| 5-6k | 92 | +1.0 | [-0.4, +2.4] | -0.4 | +2.5 |
| 6-7.5k | 70 | -0.8 | [-3.1, +1.4] | **-3.8** | **+1.8** |
| 7.5k+ | 9 | -3.8 | [-11.8, +4.4] | -4.5 | -3.2 |

The earlier "$6-7.5k under-projected" finding **does not replicate**: it flips sign between weeks. Only $7.5k+
has the same sign in both weeks, and it rests on n = 4 + 5 players with a CI spanning ±8.

## 2. QB

- corr(final, actual) is 0.49 in wk1 and **0.18 in wk2** (Spearman 0.46 / 0.11); pooled 0.35 (n=49). Salary does
  no better (0.51 / 0.01). Wk2 was an unpredictable QB week for salary as well, so part of the "QBs don't
  rank-order" result is small-n noise: n=25 per week and a single week's QB correlation has an SE of about 0.2.
- **Spread:** sd proj 3.8 vs sd actual 8.8. The shipped QB slope is 0.82, so QBs are *not* too compressed; the
  engine is the over-dispersed one (slope 0.66).
- **Pass volume is flat.** proj_pass_att has sd 3.3 (mean 33) against an actual sd of 8.7, and corr(proj, act) is
  only +0.23. An oracle test puts actual attempts into the projection at the projected per-attempt efficiency.
  QB corr moves 0.25 -> 0.35. With actual carries too it reaches 0.40. So *perfect* volume information is worth
  about +0.1-0.15 corr. Realistic volume information is worth a fraction of that: flatness costs little
  achievable signal.
- **Rushing is under-projected in level:** projected 3.1 carries / 13.8 yd vs actual 4.0 / 18.0, about +1.1 DK
  pts per QB. It hits mobile QBs hardest. Daniels was projected 3.0-5.8 carries and got 5-7; Caleb Williams was
  projected 2.6 carries / 14 yd and got 10 / 65. But residual (act - final) vs proj_rush_yd has r = +0.02, so
  there is **no systematic under-projection of the known rushers' totals**. The top-rush quartile's total bias is
  -1.8, the same as the rest. The rushing level gap is uniform and does not change ranking.
- Actual-vs-actual: actual pass points explain the QB score (r .81) far more than actual rush points (.56). The
  QB ranking problem is mostly pass efficiency and TD variance, which no volume fix reaches.
- **Verdict:** nothing clearly broken and fixable before Sunday. The one defect is a uniform QB rush-volume
  under-projection (about 1 carry and 4 yd). It is a level issue worth about +1 pt per QB, and QB bias is -1.2
  overall.

## 3. Candidates, leave-one-week-out (fit on dedup train week, score the other week; `c_lowo.csv`)

Metrics: MAE and RMSE (level). Within-position ranking: cell_sp is the mean Spearman over slate × position cells
with ≥6 players, n=11 per week; cell_top is the actual score of the projected top-N. Cross-position:
pool_sp, top20 overall, val_sp (Spearman of points/$ within slate) and vtop20 (actual score of the top-20 by
projected points/$).

| candidate | level improves both folds | value-rank both | within-pos rank both | mean ΔMAE | Δval_sp | Δvtop20 |
|---|---|---|---|---|---|---|
| a global linear (full) | no (RMSE +0.10 wk2) | no | n/a (order kept) | -0.07 | -0.002 | +0.83 |
| a global linear (half) | **yes (tiny)** | no | n/a | -0.05 | +0.006 | +0.83 |
| b per-position linear | no | no | n/a | +0.22 | -0.022 | -0.37 |
| c isotonic global / per-pos | no | no | ~0 | +0.30 / +0.54 | - | - |
| d tier offsets (all / half / ≥6k only) | no | no | all: yes | +0.31 / +0.09 / +0.28 | negative | mixed |
| e1 per-pos act~final+salary | no | no | no | +0.41 | -0.045 | -1.68 |
| e2 re-weight eng vs stack (LOWO fit) | no (bias) | **yes** | **yes** | +0.11 | +0.013 | +0.92 |
| e2 level-neutral version | MAE yes, RMSE no | +0.005/+0.010 | +0.013/+0.044 | -0.11 | | |

- Candidates (a), (b) and (c) are monotone, so they cannot change within-position order. Their cross-position
  effect is small or negative. The +0.83 vtop20 for global-half comes almost entirely from wk2 (+1.66 vs
  +0.01): it is one fold.
- Tier offsets are unstable because the 6-7.5k sign flips, and they hurt level out of sample.
- The only ranking-changing candidate with the same sign in both folds is **down-weighting the stack relative to
  the engine**. Checked in `c_stackweight.py`, the gain is **entirely TE**:

| p = eng + λ·delta | QB Δsp wk1/wk2 | RB | WR | TE |
|---|---|---|---|---|
| λ=0 (engine only) | -.07/+.07 | -.03/-.04 | +.02/-.11 | **+.41/+.66** (top-3 +3.9/+3.4 pts) |
| λ=0.5 | -.03/+.02 | -.01/.00 | +.01/-.04 | **+.24/+.49** |

  With a selection-neutral TE cut (engine > 8 OR final > 8), the engine beats final on Spearman in **6/6 slates**.
  Top-3 actual is better in 5/6 (wk1 early 3.3 vs 3.4 is the exception) (main: 16.1 vs 8.2 and 10.1 vs 6.5). The slates overlap, so this is
  really 2 weeks × ~16 TEs. It also contradicts the 2020-21 fit, where the TE stack improved OOS R2 over 32 weeks.
  At QB/RB/WR the stack's ranking effect is neutral to slightly positive (WR top-8 is worse without it:
  -0.8/-3.2).

## 4. Sanity checks

- The folds differ: wk1 has the 2025 lookback and wk2 is one game in. The pooled slope is 1.54 vs 1.10, tier
  signs flip, and QB slopes are 1.31 vs 0.32. Any parameter fit on one week transfers poorly to the other, which
  is why global/per-position fits fail RMSE in one fold. Week 3 has 2 games of 2026 data, which is closer to wk2
  than wk1.
- **Shrinkage should be read week by week.** The shipped projection is under-dispersed (slope 1.33), but the
  spread a correction should restore differs by roughly a factor of 5 between weeks (0.54 vs 0.10 excess slope).
  The lower CI bound on the pooled slope is 1.01.
- No candidate is fit on its test week. Dedup is applied to training rows, and scoring uses slate-level rows as
  in B1. The >8 cut selects on shipped final, which slightly favours final over engine; section 3's TE check
  uses a neutral cut.
- Headline-shrink check: every "improvement" in section 3 is either one-fold (global vtop20), level-only
  (global-half ΔMAE -0.05 on MAE ~6.5, about 1%), or reduces to TE (stack re-weight).

## 5. Recommendation

**Do not ship a spread or calibration correction for Week 3.** The pooled slope above 1 is real (CI 1.01-1.67),
but it comes from the stack's shrinkage, and its size is unstable across the two weeks. No transform improves
level in both folds by more than about 1% MAE, and monotone transforms cannot help within-position ranking,
which is what lineups need. The $6-7.5k offset does not replicate. $7.5k+ (-3.8) rests on n=9 with a CI of ±8.
A small top-tier bump (e.g. +1 pt for ≥$7.5k) is harmless but unsupported. If the user wants one "cheap and
safe" change, that is the ceiling. Evaluated as d_tier_top_half, it did not pass LOWO either.

**One flag for a user decision (not a recommendation to ship blind):** at TE the stack degrades ranking in both
weeks and on all 6 slates. The option is TE `final = engine` or λ=0.5, a fixed rule with no fitting. The case
for it: consistent sign and size (+0.4-0.7 Spearman, +3-4 pts top-3). The case against: about 30 TE
player-weeks, the choice was made after looking, and 32 weeks of 2020-21 showed the opposite. My confidence
that the effect is real is moderate at best. A reasonable middle path is λ=0.5 for TE only, or keeping it as a
manual tiebreak when choosing TEs.

**Needed to ship a real calibration:** at least 3-4 more weeks with a clean LOWO. Refit the stack's shrinkage
(b_eng/c_delta) on 2026 data once the engine has settled. Re-test QB rush volume (+1 carry / +4 yd is a level
fix worth doing in the engine, not as a post-hoc transform).
