# Chalk temperature (concentrate each group's top) — RESULTS (2026-09-30)

**Verdict: NO SHIP. `DFS_OWN_CHALK_TEMP` stays off (default gamma 1.0 = no-op).** Sharpening moves the numbers the right
way in all 5 seasons, but the gain is small. It also costs fit quality in every season: correlation drops everywhere, and
$7k+ MAE gets worse. The 2026 check makes $7k+ overshoot. The compression is mostly a **ranking** miss, and a
temperature transform can't fix that by design.

## Question
The owner's framing: our model is "too flat at the top". Real 30%+ players come out around 20, and cheap WR/TE chalk comes
out at about half size. Can we concentrate each position group's ownership (high shares get more, low shares get less,
same group total) with **no FFC or other new data**? Does 5 seasons of held-out history clearly support shipping it?

## Method
- `scripts/ownership_v2.py`: `allocate` is a softmax over the linear log-score. Each (slate, position) group is scaled
  to a fixed budget and water-filled at CAP 75. The natural lever is temperature: `new_i ∝ final_i ** gamma`
  (softmax of gamma·log share). It is applied after the vac bump and re-allocated to the **same** group total with the
  same CAP. QB/RB/WR/TE only (DST untouched). This is new function `apply_chalk_temp`, env `DFS_OWN_CHALK_TEMP=<gamma>`,
  default 1.0. Any failure makes it a no-op. The audit column is `LAST_AUDIT["own_chalk_temp"]`.
- History: `hist.parquet` for 2021-25 (48k rows, the current-code rebuild on FC salaries, the same frame the stud and
  cheap-WR/TE studies used). The base is v2 LOSO preds (`stud_own/v2_loso_fresh.parquet`) + vac bump. That matches what
  ships when FFC is absent.
- Grid: gamma ∈ {0.9…2.0}. gamma is picked leave-one-season-out by training-season skill MAE, a neutral objective rather
  than the target tier. It picked **1.1 in all 5 folds**.
- 2026 wk1-3: the shipped blend (v2+FFC) + vac bump, leave-one-week-out.
- Bands: cheap WR/TE (<$5.5k), mid, $7k+ (skill positions, in pool). Metrics: corr (on real>0), MAE,
  catch20 (real 20%+ predicted ≥15), catch30 (real 30%+ predicted ≥20), bias at real 20%+ and 30%+.

## History, pooled 2021-25 (held-out v2)
| band | gamma | corr | MAE | catch20 | catch30 | bias20 | bias30 |
|---|---|---|---|---|---|---|---|
| all skill | 1.0 | .685 | 2.10 | .40 | .35 | -14.2 | -20.7 |
| all skill | **1.1** | .677 | 2.09 | .45 | .38 | -13.2 | -19.2 |
| all skill | 1.3 | .660 | 2.14 | .49 | .46 | -11.2 | -16.1 |
| all skill | 2.0 | .605 | 2.61 | .54 | .55 | -5.8 | -8.3 |
| cheap WR/TE | 1.0 → 1.1 | .642 → .633 | 1.36 → 1.32 | .24 → .30 | .29 → .29 | -16.0 → -15.2 | -21.8 → -20.4 |
| mid | 1.0 → 1.1 | .667 → .659 | 2.41 → 2.39 | .37 → .40 | .34 → .39 | -15.2 → -14.3 | -21.4 → -19.9 |
| $7k+ | 1.0 → 1.1 | .510 → .507 | 5.78 → 6.00 | .54 → .58 | .39 → .40 | -11.7 → -10.4 | -19.0 → -17.2 |

## History, per season (gamma 1.0 → 1.1)
| season | skill MAE | skill corr | skill catch20 | skill bias30 | $7k+ MAE | $7k+ bias30 |
|---|---|---|---|---|---|---|
| 2021 | 1.99 → 1.98 | .66 → .65 | .33 → .39 | -23.7 → -22.5 | 4.73 → 4.82 | -24.4 → -23.0 |
| 2022 | 2.08 → 2.07 | .70 → .69 | .39 → .40 | -21.6 → -20.2 | 5.56 → 5.85 | -23.4 → -22.2 |
| 2023 | 2.19 → 2.19 | .67 → .66 | .41 → .44 | -17.1 → -15.1 | 5.76 → 6.00 | -13.7 → -11.1 |
| 2024 | 2.27 → 2.26 | .69 → .68 | .39 → .46 | -19.8 → -18.3 | 6.05 → 6.31 | -14.2 → -12.0 |
| 2025 | 2.04 → 2.02 | .71 → .70 | .48 → .53 | -22.3 → -20.8 | 7.53 → 7.74 | -22.5 → -21.3 |

The direction holds in 5/5 seasons: catch and bias improve, overall MAE is flat or slightly better. The costs are just as
consistent: corr drops about 0.01 every season, and $7k+ MAE gets worse every season.

## 2026 wk1-3 (shipped blend + vac, LOWO)
LOWO chose gamma 1.0, 1.0, 1.1, so the live data mostly says "don't sharpen".
| band | gamma 1.0 → 1.1 | MAE | corr | bias20 | bias30 |
|---|---|---|---|---|---|
| all skill | | 1.10 → 1.10 | .864 → .855 | -4.8 → -2.7 | -7.9 → -5.0 |
| cheap WR/TE | | .68 → .65 | .847 → .840 | -8.1 → -7.0 | -14.7 → -13.6 |
| $7k+ | | 8.78 → 9.69 | .752 → .732 | **-1.3 → +2.5** | -6.5 → -2.9 |
In wk3, $7k+ bias20 is already +4.5 at 1.0 and reaches +8.4 at 1.1. Once the live FFC blend is in, the studs are not
compressed on average, so sharpening every group makes them overshoot.

## Why it doesn't close the gap
1. **Tiny effect at the honest setting.** gamma 1.1 (the MAE-optimal pick in all 5 seasons) closes only about 7% of the
   30%+ gap (bias30 moves from -20.7 to -19.2). Bigger gamma closes more, but it pays with MAE and corr (at 2.0, skill
   MAE is +24% and corr drops .08).
2. **It's mostly a ranking miss, not a scale miss.** Within a group the transform keeps the order, so it can only make
   our top players bigger. At baseline, 60% of real 20%+ players get under 15 predicted and 65% of real 30%+ players get
   under 20. Most of those players are not our top-ranked ones, so sharpening pushes share onto the wrong players. That
   is why corr falls every season.
3. **The history base is not the live base.** History v2 has no FFC and is badly compressed ($7k+ bias30 -19). The live
   v2+FFC blend is already close to calibrated at $7k+ (bias20 -1.3). So a global temperature fit to history
   over-sharpens live.

## Ship call
Wrong direction as a fix for the chalk-compression problem. It's a calibration knob that trades ranking fit for top-tier
size, with no net accuracy win. Left **off by default**. The code stays in behind `DFS_OWN_CHALK_TEMP` because it's
cheap and inert. The remaining gap is about *which* players become chalk (the ranking signal), not how peaked the
distribution is.

## Files
- `scripts/ownership_v2.py`: modified. Adds `CHALK_TEMP_DEFAULT=1.0`, `chalk_temp_gamma()` and `apply_chalk_temp()`,
  called in `predict_v2` only when gamma ≠ 1.0. Default behaviour is unchanged.
- `analysis/chalk_temperature/test_temp.py`, `test_temp_out.txt`, `RESULTS.md`: new.
- `data/fc_history/derived/chalk_temp/{hist_table,y2026_table}.csv`: FC-derived, under the git-ignored `data/fc_history/`.
