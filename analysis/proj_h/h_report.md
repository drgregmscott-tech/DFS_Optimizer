# Step H: the RB/WR floor-share gap (upstream dilution). Measure it and test a fix

**Verdict: do NOT ship for Week 3.** The dilution is real and measurable, but removing it makes projections slightly worse on wk2, the fold that looks like Week 3. On wk1 the fix improves bias but not MAE. It fails the "must improve both folds" bar.

## Reproduce
```
bash analysis/proj_h/run_all.sh          # 12 backtest builds + 2 wk3 builds, restores output/ after each
python analysis/proj_h/h_eval.py > analysis/proj_h/h_out.txt
```
- `h_build.py` runs the unchanged `scripts/build_projections_statline.py` through `runpy`, with an optional monkeypatch. It also writes audit snapshots (pre/post-reconcile pools, the list of floor players) to `builds/<tag>/`.
- The base build reproduces the shipped wk2-main CSV exactly (max |diff| = 0).
- All 14 builds printed "Wrote N players". `output/` was restored with `git checkout -- output/`.
- Raw results: `h_out.txt`, `h_points.csv`, `h_usage.csv`.

## Mechanism (read from code)
- `apply_volume_prior` gives zero-history players priced at $4,000 a price share, blended at weight 1.0. For real weeks (week ≤ 18), `absent_player_price_factor` already cuts that volume to 25%.
- `reconcile_team_shares` sets `target = team_pred × pool_share`. The rush/recv `pool_share` comes from **historical** volume (basis "recent" or "full_season" on every team in both weeks, never "price"), and floor players contribute nothing to it.
- Floor players' mu does sit inside `raw_sum`, though. So `scale = target/raw_sum` shrinks every real contributor to make room for them. That is the dilution.
- The fix: set `price_share = 0` for zero-history (0 games) RB/WR/TE priced ≤ $4,200, unless depth-chart-guarded (RB rank 1, WR ≤ 3, TE 1). It is applied before the 14.0b normalisation.
- Because `target` does not change, reconciliation scales the remaining players **up**. This is the renormalisation the naive fix lacked. The data confirms it: mean projections of starters rose.

## 1. Size of the dilution (shipped/base builds, one row per team)
| | wk1 (24 teams) | wk2 (26 teams) |
|---|---|---|
| excluded floor players (RB/WR/TE) | 43/109/65 | 74/111/85 |
| floor share of rush price-share mass | 16.7% | 29.2% |
| floor share of recv price-share mass | 27.7% | 34.1% |
| **carries held by floor players after reconcile, per team** | **3.8** | **1.7** |
| **targets held by floor players after reconcile, per team** | **8.5** | **2.5** |
| real carries / targets those players actually got (all teams combined) | 8 / 20 | 16 / 51 |

- wk1 is the extreme case: BAL floor players held 8.1 carries and 15.1 targets.
- In wk2 the absent-player discount already removes most of the dilution. **Week 3 is a real week too, so it looks like wk2 here: about 1.7 carries and 2.5 targets per team.**

## 2. Projected vs real usage (the fix changes volume; slots are ranked by base projection)
| wk | slot | real | base | fix | ΔMAE (fix−base) [95% CI] |
|---|---|---|---|---|---|
| 1 | RB1 carries | 14.96 | 13.06 | 14.97 | −0.70 [−1.54, +0.18] |
| 1 | RB2 carries | 4.58 | 5.91 | 6.80 | +0.40 [−0.05, +0.86] |
| 1 | WR1 targets | 7.08 | 6.32 | 8.44 | +0.42 [−0.36, +1.24] |
| 1 | TE1 targets | 4.88 | 4.88 | 6.51 | +0.49 [−0.15, +1.11] |
| 2 | RB1 carries | 12.27 | 10.98 | 11.34 | −0.17 [−0.35, +0.03] |
| 2 | RB2 carries | 5.50 | 6.15 | 6.62 | **+0.21 [+0.02, +0.40]** |
| 2 | WR2 targets | 5.69 | 4.82 | 5.16 | **−0.16 [−0.28, −0.03]** |
| 2 | WR3 targets | 2.89 | 3.43 | 3.76 | **+0.15 [+0.01, +0.28]** |
| 2 | TE1 targets | 3.73 | 4.26 | 4.52 | +0.11 [−0.01, +0.22] |

- Team totals, MAE base → fix: wk1 RB carries 7.79 → 8.30, WR targets 5.09 → 5.58. wk2 RB carries 3.90 → 3.94, WR targets 4.09 → 4.16, TE targets 2.75 → 2.65.
- The fix helps RB1, which is under-projected. It hurts RB2, WR3 and TE, which are already over-projected.
- The reason: the volume goes back pro rata, but the under-projection is concentrated in RB1.

## 3. DK points (cut: base > 8; dedup player-weeks; 2000 bootstrap draws clustered by player-week)
| wk | grp | n | bias b→f | ΔMAE [CI] | ΔRMSE [CI] |
|---|---|---|---|---|---|
| 1 | RB | 32 | −2.20 → −1.34 | +0.10 [−0.26, +0.45] | −0.21 [−0.56, +0.16] |
| 1 | WR | 39 | −0.52 → +0.44 | +0.20 [−0.16, +0.54] | −0.07 [−0.41, +0.31] |
| 1 | TE | 17 | +0.47 → +1.30 | +0.28 [−0.15, +0.70] | +0.23 [−0.30, +0.74] |
| 1 | ALL | 88 | −0.94 → −0.04 | +0.18 [−0.04, +0.39] | −0.08 [−0.30, +0.17] |
| 2 | RB | 35 | +3.50 → +3.66 | **+0.08 [+0.02, +0.13]** | **+0.09 [+0.04, +0.14]** |
| 2 | WR | 53 | +1.01 → +1.15 | **+0.05 [+0.00, +0.10]** | +0.02 [−0.02, +0.07] |
| 2 | TE | 13 | +3.12 → +3.39 | **+0.21 [+0.01, +0.47]** | **+0.35 [+0.07, +0.68]** |
| 2 | ALL | 101 | +2.14 → +2.31 | **+0.08 [+0.04, +0.13]** | **+0.08 [+0.03, +0.15]** |

- Ranking is flat. Within-slate Spearman changed by between −0.05 and +0.04, and every CI includes 0.
- Top-N actual (RB5/WR8/TE3): RB −0.63 (wk1) and −0.55 (wk2); WR +0.16 and 0.00; TE 0 in both weeks. The CIs span 0.
- The union cut (base > 8 or fix > 8) gives the same picture.
- The fix mostly **lifts everyone uniformly**: +0.90 pts per meaningful player in wk1, +0.17 in wk2. So it acts as a level shift, not better ordering.
- The wk2 harm is small (about 0.08 pts MAE) but its CIs exclude zero. That is because the change is nearly deterministic, not because the effect is large.

## 4. Safety checks
- **Excluded players really are dead weight.** 507 player-weeks were excluded. Only one had 5 or more real touches: Germie Bernard, PIT, 8 targets in wk2. Kyle Juszczyk (SF, wk2) scored 10.7 DK while projected at 1.5; the fix sets him to 0.
- **Genuine low-priced contributors do get zeroed in wk1.** Travis Hunter ($3,400) and Tank Dell ($3,700) went from 5.5 to 0. The rank-3 WR guard did not catch them.
- **Guard.** The depth-chart guard spared 2–5 players per slate (e.g. Calvin Ridley, Devontez Walker, Jalen McMillan).
  - `depth_charts_current.parquet` is a 9/23 snapshot, so for wk1/wk2 the guard leaks future information slightly. Guard results on those weeks are optimistic.
  - No injury-replacement $4,000 RB1 existed in these slates, so that path is **untested on real data**. The only protection is the depth_rank == 1 guard.
- **Week 3 main, built with the fix:**
  - 245 players excluded, 1 guarded (McMillan). 149 players moved by 0.5 or more.
  - Mean change among players projected above 8: RB +0.06, WR +0.13, TE +0.18.
  - Biggest movers: Bowers +2.27, Okonkwo +1.89, McMillan +1.16. About a dozen $4,000 RBs dropped from roughly 1.3 to 0, including Pacheco (DET), who is not a dead roster spot.

## Recommendation
**Not for Week 3.**
- The dilution exists: about 1.7 carries and 2.5 targets per team in a real week, 3.8 and 8.5 in the wk1 lookback.
- But the shipped pipeline's errors are not mainly caused by it. Sending that volume back pro rata worsens the already over-projected RB2/WR3/TE more than it helps RB1.
- On wk2, the fold that matches Week 3, total MAE gets worse by +0.08 [+0.04, +0.13] and RMSE by +0.08 [+0.03, +0.15]. wk1 bias improves, but its MAE does not move significantly (+0.18 [−0.04, +0.39]).
- Evidence base: 2 weeks, 6 slates, about 67 RB, 92 WR and 30 TE meaningful player-weeks. The honest reading is "no gain, small harm on the relevant fold". It cannot distinguish a real benefit.

**If revisited:**
- The candidate change is in `scripts/statline_model.py`, `apply_volume_prior()`, before the Session 14.0b normalisation (~line 1212): zero `{comp}_price_share` where position ∈ {RB, WR, TE}, games_played == 0, salary ≤ 4200, and not depth-chart-guarded.
- It would need a **non-pro-rata** redistribution, weighted toward depth rank 1. That is a new design, not this fix.
- It would also need a guard that keeps real low-priced rookies (the Hunter/Dell pattern).
- Refitting the price curve (`data/volume_prior_*.json`) is out of scope: it was fitted on 2014–2021 data and cannot be revalidated before lock.
