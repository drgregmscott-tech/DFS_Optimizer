# Week 2 (2026) post-mortem: findings and open items

Started 2026-09-21 after Weeks 1-2 produced no cashing SE3max/MME lineups on DK.
Analysis scripts were run from a session scratchpad, not committed (see
"Replay harness" below). This file is the running list so nothing gets lost.

## Data used
- Week 2 DK results: SE3max main/early/afternoon/showdown, MME main (real fields + ownership).
- Week 1 DK results: SE3max main/early/afternoon (real fields, no MME).
- Contest cash lines: SE3max min-cash ~top 25% (rank ~3,996 of ~15,900); MME min-cash rank 28,495 of ~110,300, next tier rank 9,375.

## DONE (committed 6b8f6e2)
1. Week 2+ absent-player volume discount (`statline_model.absent_player_price_factor`).
2. Ownership recomputed after OUT zeroing (`status_check.refresh_ownership`).

## DONE (ownership rebuild; see scripts/ownership_model.py, scripts/fit_ownership_model.py, data/ownership_model_dk.json)
3. Layered DK ownership model: heuristic + optimizer-implied exposure (60 lineups, 25% noise) + salary/reliability layer,
   renormalized to position budgets with a 75% cap. Fit on wk1+wk2 (6 slates), leave-one-week-out:
   - wk2 (trained on wk1): corr 0.70 -> 0.85, chalk bias -14.1 -> -1.4, chalk MAE 15.0 -> 10.9 (target was ~10).
   - wk1 (trained on wk2): corr 0.73 -> 0.77, chalk bias -13.6 -> -3.8, chalk MAE 17.1 -> 17.1 (NOT improved: small-slate hype
     misses like Achane 58% vs 19%, McConkey 51% vs 10%, min-priced TE Mayer 36% vs 2%).
   - wk2 main rebuilt: Bijan 4.3% -> 32.5% (real 42.6%), Henry 22.5 -> 32.1 (32.8), main-slate corr 0.65 -> 0.80.
   Falls back to the heuristic on any error; DK classic only. Refit weekly: `python scripts/fit_ownership_model.py`.
   Follow-ups: (a) add last-week DFS points as a feature once a 3rd week can validate it (it lifted wk2 R2 0.56 -> 0.67 in-sample);
   (b) hype/news misses on small slates are not explained by any feature we have; (c) contest-type differences not modeled;
   (d) FD and Showdown still on the heuristic.

## OPEN: revisit projections at the end (accuracy vs variance vs outcomes)
- Stud under-projection: players >= $5.8k projected ~11.4 vs actual ~17.5 over wk1-2 (30% above model p90). Week 1 ran hot,
  so part is environment. Model's price->points curve is flatter (1.3->1.9 pts/$k) than realized/historical (1.5->3.1, anchor 1.9->2.4).
  Salary-anchor blend did NOT help in replay -> likely a usage/volume-allocation issue, not a salary tilt. Re-check after item 1 effects.
- Model correlation with actuals (~0.6) is about equal to salary alone for skill players; DST model has real edge (top-3 DST ~10-12 pts vs pool ~6.5).
- Week 2+ history is current-season only (1 game). Model weights W1 ~2x what data suggests and under-weights 2025 form
  (not statistically significant, n=184). Decide on prior-season carryover with 2018-21 data.
- Cheap value plays (proj 5.5+, $3-4.9k): mean is unbiased (7.2 proj vs 7.9 act) but median 6.4, only 9% hit 4x, 22% score <=3.
  Question: is the objective (mean) the right thing to maximize for these slots? Ceiling / p90 weighting?
- Mid-tier ($4.9-6k RB/WR) was the worst value bucket (55-57% under 1.5x).
- Re-fit ABSENT_* constants each week (started from 2 weeks + 2018-21 check).
- Rebuilding a past week after its games are in weekly_stats_2026.parquet gives very different projections (Bijan 26 vs 18). Unexplained; investigate before any backtest rebuilds.
- Projection error is driven by team-game outcomes (CAR 104 fantasy pts vs ATL 38): no joint game model; RB and DST projections for the same game are not coherent.

## OPEN: construction / settings (test forward on Week 3+ with the replay)
- SE: the "exclude RB/WR/TE proj <= 7" filter looked harmful in replay (5/6 slates), driven by one slate. Test forward.
- SE: TE in FLEX share rises from 12% (bottom half) to 29% (top 1%) in real fields; user currently unclicks it. Test.
- QB stack in 85-96% of real lineups at every tier (table stakes, not a differentiator). Bring-back neutral. Stack size 2 worse.
- MME: nine players pinned at the 35% exposure cap; replay favored looser caps / no stack (+12.6 pctile, 6/6 slates) but gain is mid-distribution, not top 1%.
- Game/team targeting: pinning to top-O/U game or top implied team did not beat the default. Hindsight-best team is worth ~+20 pctile / 72% top-25%,
  so predicting the right game is the biggest lever; Vegas total alone found the best game on 2 of 6 slates.
- Lambda (variance penalty): floor-seeking +0.15 hurt; 0 / 0.063 / -0.05 indistinguishable.
- Decision #56 (no skill vs own DST) + a Bijan lock removed Panthers DST (26 pts, top-projected, cheapest) in Week 2.
- Ownership-penalty leverage (estimated ownership): no gain in replay so far; re-test after the ownership rebuild.

## OPEN: validation
- Old backtest field (ownership-weighted random) was far too weak (75th pct median vs real 22nd-43rd).
- Ownership-weighted simulated field built from ACTUAL ownership reproduces real field quantiles within ~2-7 pts (Week 1 within ~2 after stretching spread x1.10).
  Works for any slate with known ownership + player points. Cannot reach 2014-21 (no ownership).
- Replay harness should be committed as `scripts/replay_validation.py` and fed every week's results (TODO).
- Need real MME fields for Week 1 (none available) and Week 3+.

## Success criteria
- Ownership: chalk (>20% real) within ~10 pts on average, both weeks.
- Replay: no degradation vs current settings on Weeks 1 and 2; track SE top-25% rate and mean percentile each week.
- Real goal stated by user: approach 50% cash rate in SE3max.
