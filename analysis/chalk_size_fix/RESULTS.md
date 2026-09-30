# Chalk-size fix: pull toward raw FFC for its top-N (2026-09-30)

**Question (premise restated).** The cheap-WR/TE and $7k+ ownership studies found the same miss: players who end up 20-30%+ owned are predicted at about half their real number, at every price. Raw FFC sizes chalk about right but ranks worse. Test: for players raw FFC puts in its slate top-N, pull our final ownership toward raw FFC by factor b. Does it fix chalk size on held-out weeks without hurting corr or MAE, on **both** the cheap WR/TE (<$5.5k) band and the $7k+ band?

## Answer

**No-ship. Label: inconclusive, keep testing.** The switch is built and **off by default** (`DFS_OWN_CHALK_FFC=0`).
- Wk1 and wk2 held out: it helps both bands. Corr goes up, MAE goes down, and cheap chalk catch goes up.
- Wk3 held out: it hurts. All-player corr drops .858 to .850 and MAE rises 1.221 to 1.260. Cheap corr drops .902 to .874 and $7k+ corr drops .701 to .668.
- It does not fix chalk size where the gap is biggest. 30%+ bias gets *worse* in every band (all: -8.2 to -9.3; $7k+: -6.5 to -8.5). Reason: the pull re-allocates the group budget, so moving top-15 players toward FFC takes mass from the true mega-chalk as often as it adds to it.
- The one consistent gain is cheap WR/TE 15-20%+ chalk. Across the 3 held-out weeks, catch20 goes .58 to .75, catch15 .75 to .83 and bias20 -8.1 to -6.0, and this holds every week.

That is 1 of 3 weeks hurting, and the 30%+ tier going the wrong way. This project ships only on a clean held-out win (for example, the v2 ship won every held-out week), so this does not meet the bar.

**Wk4-5 real ownership doesn't exist yet** (first Wk4 slate is 2026-10-01), so the spec's final Wk4-5 judgment could not be run. This verdict rests only on the wk1-3 leave-one-week-out numbers.

## Method
- **Data.** 2026 wk1-3 real DK ownership, 9 classic slates (`y2026.parquet`), with raw FFC `ffc_own_pct`. FFC lists 88% of real 20%+ skill players.
- **Baseline ("shipped").** The v2 x live-FFC log blend at a = .45 (`y2026_preds.parquet`), plus the live teammate-OUT vac bump (`apply_vac_bump`). This is exactly what runs live.
- **Candidate.** `scripts/ownership_v2.py` `apply_chalk_ffc`:
  - For QB/RB/WR/TE in raw FFC's slate top-N, log score = (1-b)·log(final) + b·log(FFC).
  - Each (slate, group) is then re-allocated to its own current budget with the existing `allocate` (75% cap). This is the same convention as the vac bump.
  - The evaluation calls this exact function.
- **Selection.** Grid N ∈ {3,5,8,10,15,20,30}, b ∈ {0,.25,.5,.75,1}. Picked leave-one-week-out by overall skill-player MAE on the two training weeks.
  - Picks were wk1 (15, .25), wk2 (15, .5), wk3 (20, .5).
  - Saved params: N = 15, b = .5.

## Held-out results (each week scored with params picked on the other two)

| week | band | model | corr | MAE | catch20 | catch15 | bias20 | bias30 | bias10-30 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | cheap WR/TE | shipped | .736 | .702 | .40 | .64 | -13.8 | -29.3 | -3.7 |
| 1 | cheap WR/TE | chalk | **.754** | **.670** | .40 | **.73** | -12.5 | -29.6 | -2.6 |
| 1 | $7k+ | shipped | .832 | 6.92 | 1.00 | .92 | -5.8 | -10.2 | +2.3 |
| 1 | $7k+ | chalk | **.858** | **6.72** | 1.00 | .92 | -4.3 | -8.1 | +2.7 |
| 1 | all | shipped / chalk | .841 / **.863** | 1.181 / **1.122** | | | -8.2 / -7.7 | -11.3 / -10.8 | top10% .688 / .700 |
| 2 | cheap WR/TE | shipped | .883 | .655 | .63 | .85 | -3.9 | -19.3 | -3.3 |
| 2 | cheap WR/TE | chalk | .884 | **.628** | **.75** | **.92** | -1.1 | -21.3 | -1.6 |
| 2 | $7k+ | shipped | .812 | 7.63 | 1.00 | 1.00 | -4.3 | -5.8 | -0.9 |
| 2 | $7k+ | chalk | **.873** | **6.81** | 1.00 | 1.00 | -5.7 | -7.6 | +0.9 |
| 2 | all | shipped / chalk | .881 / **.888** | 1.145 / **1.112** | | | -4.5 / -4.4 | -6.5 / -7.9 | .677 / .689 |
| 3 | cheap WR/TE | shipped | **.902** | **.693** | .64 | .75 | -8.6 | -6.2 | -7.5 |
| 3 | cheap WR/TE | chalk | .874 | .738 | **.91** | .81 | -6.6 | -4.6 | -5.6 |
| 3 | $7k+ | shipped | **.701** | 11.07 | 1.00 | .88 | +4.5 | -4.3 | +8.8 |
| 3 | $7k+ | chalk | .668 | **10.32** | 1.00 | .88 | +1.3 | -9.8 | +7.3 |
| 3 | all | shipped / chalk | **.858** / .850 | **1.221** / 1.260 | | | -4.1 / -4.5 | -6.5 / -9.0 | **.733** / .711 |
| all | cheap WR/TE | shipped / chalk | .847 / .845 | .684 / .678 | .58 / **.75** | .75 / **.83** | -8.1 / **-6.0** | -14.7 / -14.1 | -4.6 / -3.1 |
| all | $7k+ | shipped / chalk | .752 / **.777** | 8.78 / **8.19** | 1.00 / 1.00 | .93 / .93 | -1.3 / -2.7 | -6.5 / **-8.5** | +4.7 / +4.5 |
| all | all | shipped / chalk | .859 / .866 | 1.182 / 1.163 | .76 / .79 | .80 / .83 | -5.4 / -5.4 | -8.2 / **-9.3** | -2.7 / -2.2 |

Raw FFC alone for reference (all weeks, all players): corr .724, MAE 1.899, bias20 -1.9, bias30 -4.6.

The full in-sample grid is in `test_chalk_out.txt`. No (N, b) cell fixes 30%+ bias in both bands. Small N with large b (N = 3, b = 1) gets $7k+ bias30 to -2.7, but it costs cheap corr .847 to .743.

## Verdict
- **Ship: no.** It is 2 of 3 held-out weeks better, and wk3 is worse on corr, MAE and top-10%. The 30%+ chalk it was meant to fix gets worse in both bands. Default stays `DFS_OWN_CHALK_FFC=0`.
- **Keep testing: yes.** Score it on Wk4-5 real ownership alongside shipped, which costs nothing because it is behind the switch. The cheap WR/TE 20%+ gain (catch20 +.17, bias20 +2.1, in every week) is real on 3 weeks.
- **Most valuable fixable next step.** The mechanism is wrong for the 30%+ tier. A budget-preserving pull cannot raise mega-chalk (Achane 58, Bijan 59, Jeanty 54) without taking mass from the next tier. The next candidate should change the *shape* (concentration) of the top of each group, not re-rank toward FFC. One option is a per-group top-k temperature on the final log score, picked LOWO the same way. Test that on history too: it needs no FFC, so all 5 seasons of real ownership can judge it, instead of only 3 weeks.

## Files
- `scripts/ownership_v2.py` (**ready to commit**)
  - Adds `chalk_ffc_enabled`, `chalk_params` and `apply_chalk_ffc`.
  - `predict_v2(..., raw_ffc=None)` applies the pull after the vac bump when the switch is on. The audit column is `LAST_AUDIT["own_chalk_ffc"]`.
  - `refine_v2` passes `scored["ffc_own_pct"]` when an FFC table was used.
  - Off by default, and a fail-safe no-op on error.
- `data/ownership_v2_chalk.candidate-2026-09-30.json`: N = 15, b = .5, plus the LOWO picks (ready to commit).
- `analysis/chalk_size_fix/test_chalk.py` and `test_chalk_out.txt` (ready to commit; these use 2026 DK and FFC ownership only, no FC data).
- `data/fc_history/derived/chalk_size_fix_rows.csv`: player rows. This file is git-ignored via `data/fc_history/`.
