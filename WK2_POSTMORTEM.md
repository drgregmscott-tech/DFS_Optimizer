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

## CORRECTION (2026-09-21, later): the historical engine-vs-salary result below was inflated by look-ahead
When a week's own games are already in weekly_stats/team_stats, the build knows who actually played: it zeroes players with no stat line
("no real game") and reallocates their volume to teammates who did play. My first historical rebuild used full-season stats files, so it had
that knowledge; the live engine does not (only the injury report). Rebuilt all 32 weeks (2020-21 wk2-17) with each week's stats/team-stats truncated
to weeks < wk (hist_one.py in the session scratchpad). Clean results, ~12,050 player-weeks:
- Engine alone CV R2 0.439 vs salary 0.394 overall, but BY POSITION the engine alone is ~tied with salary: QB +0.022, RB +0.003, WR -0.007, TE +0.011.
  Engine + salary 0.458. Per-week corr(engine)-corr(salary): mean +0.034, sd 0.027 (was +0.051); engine <= salary in 4 of 32 weeks.
- So 2026 wk2 (+0.007 to +0.014) is NOT unusual (about -1 sd). The original worry ("we are no better than salary") was right for skill positions.
- What the engine misses: recent usage (last-4-game targets/carries/attempts/target share/air yards) adds +0.047 R2 for TE, +0.024 RB, +0.018 WR beyond engine+salary
  (all-in: QB +0.020, RB +0.022, WR +0.023, TE +0.047). Environment/recent form/prior season add little. Market props (below) are the natural fix.
- Validity warning: backtest_harness builds each historical week the same (leaky) way, so past backtest projection-quality numbers carry this look-ahead too.

## DONE: calibrated projection stack (scripts/projection_stack.py, fit_projection_stack.py, data/projection_stack_dk.json) -- DK classic only
Findings that led to it (clean, pre-game rebuilds of 2020-21 wk2-17):
- Value check: grouping players by (engine - what salary alone predicts), actual minus salary-predicted points runs -1.8, -1.2, -0.1, +0.9, +2.2 across fifths
  (top-bottom ~4 pts; QB 5.7, RB 4.9, WR 3.4, TE 3.0). The engine finds value vs salary; it just does not beat salary on total R2.
- Volume check: for next-game WR/TE targets the engine's projected volume (R2 ~0.42-0.45) is no better than a last-4-game average, season average, or salary alone;
  engine + last-4 + salary reaches 0.46-0.47. RB carries and QB attempts: the engine is clearly best (0.55, 0.61).
- Stack = per-position ridge regression on salary, engine points and last-4-game usage (targets, carries, attempts, target share, air-yards share, WOPR, receiving air yards).
  Leave-one-season-out R2 vs engine+salary: RB +0.03/+0.02, WR +0.02/+0.02, TE +0.05/+0.05, QB ~0 (QB stack is salary + engine only).
  On 2026 data it never saw: wk2 corr 0.618 -> 0.653 (forecast R2 0.374 -> 0.420), wk1 forecast R2 0.331 -> 0.426; wk2 studs >= $5.8k engine 13.3, stack 15.2, actual 15.3.
- Applied as final = E + delta (unmatched by props) or E_props + 0.5*delta (matched; assumption to re-test with real props data); stacked value clamped to 0.5-1.8x engine.
  Not applied to Showdown (salary scale differs) or FD (no fit). Off switch: --no-stack. Refit: python scripts/fit_projection_stack.py.
- Lineup replay (6 slates, engine vs stack): SE preset +1.0, SE user-style +5.4, SE no-stack -5.6, MME +2.7 percentile points -- neutral-to-slightly-positive, all within noise.
  The gain is in calibration/forecast accuracy, not a lineup-level jump.
- Other signal families tested as add-ons to the stack + Vegas (leave-one-week-out CV R2 increments, 2020-21 clean data): all ~0.
  Defense-vs-position (rolling 8/3-game points allowed to the position, and the engine's own matchup_factor): +0.000 to +0.002 (QB +0.006 for matchup_factor).
  Pace / expected plays / expected pass rate (team rolling plays and pass rate, own and opponent-faced): -0.002 to +0.001.
  Vacated usage from teammates ruled Out/Doubtful (nflverse injuries; last-4 target share, air-yards share, carries, attempts): +0.000 to +0.002.
  Game environment (spread, total, weather, home, rest) earlier: ~0. Conclusion: the measurable free signal is recent usage (done) and market prices (props); the rest is noise.
- Odds API markets: no targets prop exists (422). Available and not yet pulled: player_rush_attempts, player_pass_attempts, player_pass_completions (1 credit/game each).
  Receptions (pulled) is the closest to targets: the blend sets targets = receptions / catch rate.
- props audit: builds now write data/props/audit_{slate_id}.csv (engine-only vs market stat means per player at build time) so per-stat blend weights can be FIT against actual stat lines once
  a few weeks of props exist (the engine-only means cannot be rebuilt after games without look-ahead).
- Still to do: fix the engine's own WR/TE volume layer (price prior weight decays slowly: k=4), test injury/teammate-absence and snap/route features through the same clean harness,
  expected-fantasy-points (opportunity) data (the nflverse URL I tried 404'd), and re-fit the stack with real props-blended weeks as they accumulate.

## PROJECTIONS: what the FIRST (leaky) historical check found (2026-09-21, scratchpad scripts not committed)
Rebuilt 31 historical weeks (2020 wk2-17, 2021 wk2-17; 2019 fails on OAK/LV team-abbrev in the DST model) with the CURRENT production engine
(statline + volume prior + sigma recal + distributional DST + participation fix) and scored against actual DK points (~11,700 player-weeks).
- Engine beats salary historically: CV R2 0.465 vs 0.396 (salary+engine 0.477); raw corr 0.682 vs 0.629. Every position (QB +.03, RB +.044, WR +.016, TE +.053).
  Beat salary in 29 of 31 weeks (mean corr diff +0.051, sd 0.025). Weeks 2-3 specifically: +0.026 to +0.056.
- 2026 wk2 is a weak tail week: corr 0.618 vs salary 0.611 (+0.007). A 2-week average that low happens ~5% of the time historically.
  Ruled out live-only components as the cause (depth-chart prior, confirmed-starter override, weather, role change: each moves corr by <=0.007).
- Signals we CAN measure from nflverse history (recent form, season/prior avg, recent usage, spread/total/weather/home/rest) add only +0.016 R2 combined
  beyond engine+salary (TE +0.02, WR +0.013, QB +0.014, RB +0.007). No big missing signal in that data.
- Market TD odds DO add a lot: DK Anytime-TD implied prob (from Market_Betting data/sportsbook_props, pre-game snapshots) on 290 RB/WR/TE player-weeks
  (wk1+wk2 main): R2 alone 0.359 vs engine 0.290 vs salary 0.298; engine+TD prob 0.363 (+0.07 over engine alone). corr with actual TDs 0.245 vs engine's 0.138.
  In-sample, 2 weeks -- forward-test before trusting. Session 14.1 deferred props "pending real evidence"; this is that evidence.
- Joint game structure (2014-21 rotoguru, 4,126 team-games): corr(QB, opposing DST) -0.42; own skill total vs opposing DST -0.44; own DST vs own offense ~-0.08;
  own vs opposing skill +0.21; QB vs own WR+TE +0.77. The ILP forbids skill-vs-own-DST but projections/variance are not jointly modeled.

## OPEN: revisit projections (accuracy vs variance vs outcomes)
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
- Ownership-penalty leverage (points penalty = g x ownership%): RE-TESTED after the ownership rebuild, six slates, SE (3 lineups x 6 seeds) and MME.
  No gain at any strength, with old ownership, new ownership (in-sample and leave-one-week-out), or REAL ownership (oracle).
  SE mean percentile vs no penalty: real ownership g=0.05 +2.0 / 0.10 -0.6 / 0.20 -5.5; new ownership 0.05 -1.9 / 0.10 -14.9 / 0.20 -18.8;
  leave-one-week-out ownership 0.05 -1.3 / 0.10 -12.7 / 0.20 -24.1. MME: within +/-4 for g<=0.10 (noise); strong penalties hurt.
  Even perfect ownership knowledge does not help at these strengths, and accurate chalk estimates made the penalty look WORSE
  (it removes the efficient chalk that scored in both weeks). Do not add a leverage term yet; revisit with more weeks and, if at all, MME only
  with a smarter form (leverage on expected top-heavy payoff, not a flat points subtraction).

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

## Showdown ownership assessment (2026-09-21)
Data: wk1 DEN@KC (player-level, partial) + wk2 IND@KC (logged this session, plus 4,733 real lineups). Scripts: `analysis/showdown_own/` (dataset, LOSO comparison, chalk-CPT analysis), model `scripts/ownership_model_showdown.py`, artifact `data/ownership_model_showdown_dk.json` (wired into `add_showdown_ownership_columns`, fail-safe to heuristic; ~30s per build).
- Heuristic signature = classic: chalk under-estimated (FLEX chalk bias -12.5/-9.9; wk2 Walker CPT 12% est vs 42% real; kickers 6% vs 31%).
- Feature that matters: optimizer exposure computed separately for CPT and FLEX rows (noisy showdown ILP, 15/30/50% noise x 60). Leave-one-slate-out, 3 features (exposure, K flag, DST flag), ridge on logit scale, water-filled to CPT 100 / FLEX 500.
  - wk2 CPT: corr 0.81 -> 0.96, chalk MAE 16.3 -> 3.3. wk1 CPT: 0.62 -> 0.59, chalk MAE 8.4 -> 10.1 (only 4 chalk rows; Nix 20% CPT is a hype miss).
  - FLEX: corr 0.69 -> 0.81 / 0.83 -> 0.87; chalk bias -12.5 -> -0.8 / -9.9 -> -3.3; chalk MAE 18.9 -> 14.5 / 12.9 -> 10.2.
  - Not fixed: narrative/mid-price pass-catchers (Waddle 39% real vs ~0 exposure, Warren 41% vs 5%); worst FLEX miss still ~33-38 pts. Two slates only: treat coefficients as a first calibration; refit after NYG@LAR and each week (`python scripts/ownership_model_showdown.py fit --validate`).
- Chalk-CPT question (wk2 only, one game): Walker (42% CPT) lineups averaged 121.7 pts vs 119.5 overall, median finish 58th percentile, and he was the 4th-best CPT score (40.2). But they were only 0.25% top-1% lineups vs 1% baseline (5 of 47 top-1% lineups vs 42% usage) and 11% top-10% (vs 10%). Chalk CPT was NOT bad on points; it capped ceiling (top lineups had Kelce/Mahomes/Butker CPT: Kelce CPT lineups 7% top-1%, 46% top-10%). Cheap/low-owned CPT tier (<3%) had the lowest mean (108) but the highest top-1% rate (3%). One game cannot confirm or refute "fade chalk captains"; need 3+ slates with lineup-level exports.
- Update, wk1 DEN@KC lineup-level export (8,845 lineups; `analysis/showdown_own/chalk_cpt2.py` runs both slates). Chalk CPT there was Bo Nix (20.2% CPT, 58% FLEX): he scored 7.4 FLEX / 11 as CPT (CPT-score rank 10 of 44). Nix-captain lineups: 0 of 98 top-1% lineups, 0.6% top-10%, median finish 34th percentile, mean 62.6 pts vs 71.6 overall. The >15% CPT tier had the worst results of any tier (0.56% top-10). Winners: Walker CPT (12.9% usage, 89% of top-1% lineups, 55.6 as CPT) and Mahomes CPT (11%). Every top-1% lineup was a KC CPT.
- Both slates together: the top-owned CPT was mediocre-to-bad in both (wk1 clear miss; wk2 fine on average points but 0.25% top-1%), and in neither did the top-1% lineups use the top-owned CPT more than ~11% of the time vs its usage (wk2 Walker) or 0% (wk1 Nix). That is consistent with "chalk captains cap the ceiling" but n=2 games; the wk1 miss came from a QB whose FLEX ownership (58%) the field over-weighted, and wk2's chalk did not miss on points. Winning captains were the players who had monster games, whatever their ownership.
