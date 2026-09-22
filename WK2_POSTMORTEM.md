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
- Showdown simulated field (`scripts/showdown_field.py`, validated by `analysis/showdown_own/validate_field.py`): CPT drawn from CPT ownership, 5 distinct FLEX from FLEX ownership, cap $50k and min $48.5k (real entries' median salary used is ~$49.7k), both teams required, weights tuned so accepted lineups reproduce the input ownership (MAE 0.06 CPT / 0.16 FLEX). Built from REAL ownership + actual points it matches real lineup score quantiles (50/75/90/95/99/99.9%) to within ~1-2 pts on wk1 (71.6/86.1/96.5/102.0/110.2/118.4 vs 70.4/87.3/98.3/104.0/111.4/118.5) and wk2 (118.9/130.7/138.6/145.0/149.6/156.7 vs 120.1/131.2/141.0/145.2/149.9/158.6). Weakness: team split is not stack-aware (real fields have more 3-3/4-2 on wk1); kicker-in-lineup 0.45 vs real 0.43.
- Model v2 adds an `isMin` feature (FLEX price <= $1,000: real 0-2% vs heuristic 5-12%). LOSO: FLEX corr 0.83/0.90, chalk MAE 12.5/7.5, chalk bias -2.0/-5.0; CPT wk2 chalk MAE 6.5, wk1 9.8 (heuristic 8.4 there, only 4 chalk rows).

## wk2 NYG@LAR logged + 3-slate refit (2026-09-22)
Logged both ownership (`data/ownership_raw_dk_showdown_2026_wk2_NygLar.csv`, 79/79 matched) and results
(`data/results_raw_dk_showdown_2026_wk2_NygLar.csv`, 79/79 matched, mean abs error 4.41) from the real
8,918-row DK export. Now 3 regular-season showdown slates logged (2/4 toward the ownership data gate,
3/4 toward the results gate).
- **Bug found and fixed in `ownership_model_showdown.py fit --validate`**: for any slate whose
  `final_projections` file was already built AFTER the model was wired into the pipeline (true here --
  NYG@LAR was built post-session-2), `estimated_ownership_pct` in that pool file IS the model's own
  prior-fit output, not the raw heuristic -- so the validate script's "heuristic" baseline for that slate
  was silently comparing model-vs-model (identical numbers). Fixed `_training_frame()` to prefer the
  preserved `estimated_ownership_pct_heuristic` column when present. After the fix, NYG@LAR's TRUE
  heuristic-vs-model comparison: CPT corr 0.54->0.80 (chalk MAE 8.7->7.4), FLEX corr 0.78->0.95 (chalk
  bias -18.0->-4.2, chalk MAE 20.0->7.7) -- the model clearly generalizes to a genuinely held-out 3rd
  slate, the first real out-of-sample confirmation (wk1/wk2-IndKC were both already "in-sample" by the
  time this fix was needed). Refit on all 3 slates and saved to `data/ownership_model_showdown_dk.json`.
- **Chalk-CPT extended to 3 slates** (`analysis/showdown_own/chalk_cpt2.py`, now runs all 3): NYG@LAR's
  chalk CPT was Jaxson Dart (23.5% usage, backup-QB-turned-starter narrative) -- 0 of 105 top-1% lineups,
  3.3% top-10%, mean 67.9 pts vs 83.2 field average, CPT-score rank 21/47. The pattern now holds on all 3
  independent slates: the single most-owned CPT had 0% (wk1 Nix, wk2-NYGLAR Dart) or a token (wk2-IndKC
  Walker, 10.6%) share of top-1% lineups despite 20-42% field usage each time. This is no longer just
  "n=2, one bad QB outcome" -- three different teams, three different chalk-CPT profiles (a rookie/backup
  QB, a bell-cow RB, a surprise-starter QB), same direction every time. Treat "fade the single most-owned
  captain for ceiling" as a real, if still small-sample (n=3), construction rule going forward -- it does
  not mean chalk CPT loses money outright (wk2-IndKC Walker was fine on raw points), just that it caps
  the top of the outcome distribution.
- **Graded the actual played lineup + all 10 alternates against the real NYG@LAR field**
  (`analysis/showdown_own/compare_lineups_graded_real.csv`). Actual played (Williams CPT / Stafford,
  Nabers, Adams, Rams DST, Parkinson): 114.13 pts, rank 1,432 of 8,868 = 84th percentile -- missed the
  top-10% cutoff (118.98 pts) by ~5 points, consistent with (a touch below) the model's pre-game ~29-31%
  P(top-10%) / ~20% worst-case estimate. Of Greg's own 10 generated alternates, 4 would have cleared
  top-10% in hindsight and one (Stafford CPT / Williams, Adams, Likely, Rams, Corum, 135.17 pts) would
  have cleared top-1% (rank 71 of 8,868). 3 of the top 4 real-outcome lineups used **Stafford at CPT**
  (not the model's chosen Williams) alongside a low-owned boom/bust pass-catcher (Isaiah Likely or
  Terrance Ferguson) who had an unpredictable big game -- this reads as favorable variance on specific
  low-owned players more than a systematic flaw in the model's captain choice, but it's a second
  data point (after session 2's "Adams CPT scored close behind Williams CPT pre-game") that the model's
  single top pick and the actual best-in-hindsight pick are not reliably the same lineup, which is the
  whole argument for scoring a large candidate pool and keeping several live rather than committing to
  one "best" lineup pre-lock. Found and fixed two bugs while doing this grading: (1) DK's raw player-level
  export has trailing whitespace on team/DST names (`'Rams '` vs the pipeline's `'Rams'`) that silently
  drops unmatched rows in any ad hoc join -- always `.str.strip()` both sides; (2) the CPT row's
  `actual_fpts` in the logged results file is ALREADY 1.5x-scaled (DK reports it that way), so summing a
  lineup's real score must NOT re-apply the 1.5x multiplier to the CPT row.

## Classic cash-line diagnostic (2026-09-22): why SE3max is 0-for-the-season
Origin: `gmscott81`'s DK Classic SE3max entries have missed the ~top-25% cash line in all 6 slates
logged so far (wk1 main/early/afternoon 2026-09-13, wk2 main/early/afternoon 2026-09-20) --
percentiles 21.7 / 14.4 / 47.5 / 58.7 / 42.2 / 36.0, never above the 75th-percentile cash line.
Analysis script: `analysis/classic_diag/top_drivers_classic.py` (mirrors
`analysis/showdown_own/top10_drivers.py`'s method) -- pools all 6 real DK exports (51,389 real
lineups total; downloaded to `~/Downloads`, not yet committed, see script for exact filenames),
parses every real lineup's roster, joins to that slate's `final_projections` for team/position/
salary/vegas, and joins to the same export's own player-ownership table for real ownership. Cash
label = real rank in the top 25% of that slate (SE3max's real min-cash line per earlier findings
in this file).
- **Bug found and fixed while building this**: DK's classic roster string has REPEATED slot labels
  (`RB RB WR WR WR`, not `CPT`/`FLEX` like Showdown). A first draft parsed slots into a
  `{slot: name}` dict, which silently kept only the LAST of each duplicate slot and dropped the
  other RB/WR players entirely -- this corrupted salary (summed to ~$29-32k instead of ~$49-50k),
  ownership sum, stack count, and team split for every single lineup in the pool. Fixed by keeping
  a list of `(slot, name)` tuples instead of collapsing into a dict. Re-ran after the fix; the
  numbers below are post-fix and sanity-checked against a hand-computed lineup salary sample
  (median $49,900, matches DK's real cap usage).
- **Real cash-line rate is a clean 25.0-25.1% at every one of the 6 slates** (confirms the ~25%
  cash-line assumption from earlier in this file rather than treating it as a rough estimate).
- **Pooled logistic regression for cash (51,389 rows, all 6 slates, standardized within slate;
  |z|>2 ~ real)**:
  ```
                   coef      z
  dst_own_z       -0.16 -11.12   (higher DST ownership -> LOWER cash prob, see DST tier below)
  dst_opp_total_z -0.06  -4.05   (DST facing a HIGHER-implied-total opponent -> lower cash prob)
  own_sum_z       +0.29 +26.01   (STRONGEST signal: higher total lineup ownership -> higher cash prob)
  sal_z           +0.09  +6.06   (using more of the $50k cap -> higher cash prob, weak)
  flex_te         +0.18  +6.67   (TE in the FLEX slot -> higher cash prob)
  stack2p         +0.16  +4.87   (QB + 2 pass-catchers -> higher cash prob; stack1 alone ~0, not real)
  bb1p            +0.20  +9.54   (>=1 bring-back player -> higher cash prob)
  ```
  Lift tables (P(cash|bucket) / 25%) tell the same story with real magnitudes:
  - **Ownership (own_sum, lineup's total combined ownership%)**: Q1 (least-owned) lift 0.77x, Q2
    0.88x, Q3 1.04x, Q4 (most-owned/chalkiest) lift **1.31x**. This is the single strongest effect
    in the whole analysis and it points the OPPOSITE direction from a "differentiate for leverage"
    instinct: in a top-25%-cash format (not a GPP-max format), being closer to the field's chalk is
    associated with cashing MORE, not less. This independently reconfirms, from real lineup-level
    data instead of a simulated replay, this file's earlier finding that a flat ownership-leverage
    PENALTY in the optimizer showed "no gain at any strength, even with perfect ownership
    knowledge" -- now with a mechanism: the field's chalk is disproportionately the RIGHT chalk in a
    format where you just need to clear a median-ish bar, not win outright.
  - **TE in FLEX**: lift **1.18x** (real, z=6.67) -- this is the concrete forward-test result for
    the item this file already flagged as untested ("TE in FLEX share rises from 12% (bottom half)
    to 29% (top 1%) in real fields; user currently unclicks it. Test."). Verdict: turn it on.
  - **Stack + bring-back**: stack=0 lift 0.92x, stack=1 lift 0.94x (barely different from no
    stack), stack=2 lift **1.11x**, stack=3 lift 1.10x. Bring-back=0 lift 0.91x, bring-back=1 lift
    1.08x, bring-back=2 lift **1.24x**. This REFINES (does not simply repeat) the earlier
    "bring-back neutral" finding from a narrower replay test -- across 51k real lineups the signal
    for bring-back is real and positive, and a single stack partner alone barely helps; it takes a
    real QB+2 double-stack to clear the no-stack baseline meaningfully.
  - **"Team split" finding RETRACTED and REMOVED, 2026-09-22.** The original "3-3/4-2 splits beat
    2-4/1-5" bullet (below, struck through in spirit -- removed from the code and this shouldn't be
    cited) was computed as "size of the single most-represented team among the 8 non-DST slots, vs.
    the rest." Two problems: (1) the label text used a hardcoded denominator of 6 copy-pasted from
    Showdown's genuinely-6-slot roster, so the displayed labels (3-3, 4-2, etc.) were simply wrong
    for classic's 8-slot roster; (2) more fundamentally, once cross-tabbed against the `stack`
    column already reported one bullet up, this "split" metric turned out to be near-deterministic
    given stack size (e.g. stack=2 -> dominant-team-count=3 in 99.9% of lineups, stack=3 -> 4 in
    100%) -- it isn't an independent structural lever, it's just a confusingly-relabeled restatement
    of the QB-stack-size finding already covered by `stack2p`/the stack lift table above. Unlike
    Showdown (where the whole roster really is 2 teams and a literal 3-3-vs-4-2 choice exists),
    classic's other 4-5 roster spots come from unrelated games, so "which team has the most total
    players" isn't a real build decision here. Removed from `top_drivers_classic.py` and
    `analysis/classic_diag/batch_cash_drivers.py` entirely rather than relabeled -- do not
    reintroduce without a metric that's actually independent of stack size.
  - **DST tier by real ownership**: <5% lift 0.92x, 5-12% lift **1.08x**, 12-25% lift **1.08x**,
    >25% lift **0.64x** (a real trap -- the single most popular DST tier performs WORST of all four,
    consistent with the chalk-CPT-caps-ceiling pattern found on the Showdown side, but here it's
    the FLOOR/cash-line format showing the opposite lesson: don't take the MOST chalky DST, but do
    stay in the moderately-chalky 5-25% band rather than getting cute with a <5%-owned dart).
  - **DST opponent implied total (continuous, z=-4.05)**: favor a DST whose opponent has a LOWER
    Vegas-implied point total -- the conventional "target a good matchup" DST logic, now confirmed
    against 51k real outcomes rather than assumed.
- **Grading `gmscott81`'s own 6 SE3max builds against these signals** (all 6 missed cash; this is
  why):
  | slate | stack | bb | dst_own tier | dst_opp_total | own_sum (field quartile) | result |
  |---|---|---|---|---|---|---|
  | wk1 main | 2 | 0 | 18.1% (good) | 15.7 (fine) | 103 (low) | 21.7 pctile |
  | wk1 early | 2 | 0 | 23.2% (good) | 15.7 (fine) | 126 (low-mid) | 14.4 pctile |
  | wk1 afternoon | 2 | 2 (great) | 17.5% (good) | 18.7 (fine) | 241 (chalkiest of the 6) | 47.5 pctile -- closest to cashing |
  | wk2 main | 1 | 0 | 9.2% (good) | 15.9 (fine) | 141 (low-mid) | 58.7 pctile |
  | wk2 early | 1 | 0 | **27.0% (worst tier)** | 16.5 (fine) | 221 (chalky) | 42.2 pctile |
  | wk2 afternoon | 1 | 0 | 21.7% (good) | **24.0 (worst matchup of the 6)** | 199 (chalky) | 35.9 pctile |

  Pattern: `bb=0` (no bring-back) in 5 of 6 builds, `flex=TE` used but the setting that enables it
  is normally off by default (`optimizer.py`'s `DEFAULT_STACK_MODE = "none"`, `DEFAULT_STACK_SIZE =
  1`, bring-back defaults to off -- so unless explicitly overridden, a build does NOT stack at all,
  which is exactly what shows up here: 4 of 6 builds effectively have no real stack beyond
  incidental overlap). `own_sum` was in the bottom half of the field on 4 of 6 (103, 126, 141, and
  even the two "chalky" ones at 221/241 aren't clearly Q4). One specific DST pick (wk2 early,
  Buccaneers at 27% owned) sat in the single worst-performing tier; one specific DST matchup (wk2
  afternoon, Jaguars vs. a 24-point-implied Rams-ish opponent) was the worst matchup of the six.
  wk1 afternoon did the most things right (stack 2, bring-back 2, chalkiest own_sum of
  the six) and came closest to cashing (47.5 pctile) but still missed -- a reminder that these are
  probability shifts on a ~25% base rate, not guarantees; a single slate can still miss on pure
  player-performance variance even with a well-built lineup.
- **Cross-check attempted and NOT confirmative**: compared `gmscott81`'s own 20 wk2-main MME
  lineups (8 of 20 cashed, i.e. 40% -- MME is NOT part of the "0/12" cash problem, only SE3max is)
  by the same features. Within-user own_sum was actually LOWER for the cashed lineups (84 vs 102)
  -- the OPPOSITE of the cross-field direction above. Not a contradiction: this is 20 sibling
  lineups from one optimizer batch differing mainly by which dart/diversification swap landed, a
  much weaker and more confounded comparison than the 51k-row cross-field regression. Treat the
  cross-field finding as the reliable one; this check mainly confirms the MME batch's structure
  (stack, bring-back, DST tier) was already reasonable across all 20, consistent with the "MME
  isn't the problem" framing.
- **Existing optimizer levers that map directly onto these findings** (no new code needed, these
  already exist): `--stack-mode qb --stack-size 2 --bring-back` (currently off by default),
  `--flex-positions RB,WR,TE` (TE currently unclicked in the UI per this file's earlier note),
  `--min-total-ownership` (currently 0/unused -- the lever that directly targets the own_sum
  finding). DST tier/matchup targeting has no dedicated lever yet; would need either a manual
  DST-tier exclude per week or a small ownership-band filter added to the pool.
- **What this does NOT yet have**: a committed replay-validation harness (`scripts/
  replay_validation.py`, still flagged as TODO elsewhere in this file) to confirm these specific
  setting changes actually improve REPLAYED lineup outcomes on these same 6 slates before adopting
  them as new defaults -- this diagnostic is real-lineup DESCRIPTIVE evidence (what wins in the
  field), which is a different and complementary check from a replay test (what the optimizer would
  have produced under a changed setting). Given the consistency and sample size here (6 independent
  slates, same direction every time, |z|>4 on every factor), recommend adopting the settings above
  for the next classic SE3max build now, and building the replay harness to confirm/refine rather
  than gating action on it.

### Within-batch cash-driver diagnostic (2026-09-22, `analysis/classic_diag/batch_cash_drivers.py`)
Narrower follow-up to the 51k-lineup diagnostic above: instead of comparing across the whole real
field (where structure varies wildly), build our OWN diversified batches with the confirmed
settings already fixed (stack=2, bring-back, 150 lineups x 6 slates = 900), grade every lineup
against real results, and compare cashed vs. missed WITHIN each batch. Two real bugs surfaced and
were fixed on the way to a trustworthy result, both worth reading before extending this script:
1. **`stack_is_favorite` column was silently all-NaN on the first run.** `stack_target` is stored
   as `"team:DET"` (see `optimizer.py`'s `_stack_label()`), but the script looked it up directly
   against team codes stored as bare `"DET"` -- a format mismatch that produced no error, just an
   empty/NaN column and an empty categorical breakdown. Fixed by stripping the `"team:"` prefix.
2. **A `split` column reused the exact same hardcoded-denominator-of-6 bug as `top_drivers_classic.py`
   (see below)** -- and once relabeled correctly, cross-tabbing it against the already-reported
   `stack` column showed it was near-deterministic given stack size (stack=2 -> dominant-team-count
   3 in 99.9% of lineups), not an independent feature. Removed entirely rather than relabeled.
   Neither bug ever reached an actual lineup build, replay arm, or setting -- both columns were
   purely reported/diagnostic, confirmed by grepping `optimizer.py`, `best_lineup_classic.py`,
   `classic_field.py`, and `replay_validation.py` for any use of `split` or `stack_is_favorite`
   outside this one reporting script.

**Result after both fixes**: 236/900 cashed (26.2%, barely above the field's flat 25% baseline).
The pooled logistic on total_projection/salary/own_sum/dst_own/dst_opp_total/
stack_team_implied_total found NO feature reaching significance (max |z|=1.36, salary) -- these
population-level signals stop discriminating once structure (stack=2+bring-back) is already held
fixed, consistent with the standing suspicion that own_sum/DST-tier are more "good vs. bad
structure" markers than independent levers on top of already-good structure. **TE-in-FLEX is the
one signal that DOES survive within-batch**: 29.9% cash rate (n=385) vs. 19.6% RB (n=250) vs. 27.2%
WR (n=265) -- real evidence this is an independent lever, not just correlated with overall build
quality, reinforcing the population-level 1.18x lift finding above from a cleaner angle.
Stack-favorite showed a reversal (non-favorite 40.0% vs. favorite 25.8%) but on n=25 vs. 875 --
too small to trust, treat as noise, not a finding. **Net: this test did not surface new actionable
levers beyond TE-in-FLEX; the real bottleneck remains the selection-criterion question already
flagged in `HANDOFF_classic_construction_replay.md` (picking the best lineup out of an already-good
batch, not finding more features to build toward).**
- **Also checked and NOT yet fixed [SUPERSEDED, see below]**: the existing ad hoc classic field
  simulator (`analysis/wk2_session_scripts/fieldsim.py`, referenced as an open question in the
  Showdown session-2 handoff) does NOT clear the validation bar the Showdown field simulator was
  held to. Validated against wk2's 3 real classic slates: it UNDER-predicts every quantile, by -1
  to -7pts at the median and -5 to -9pts at the 90th/95th/99th percentiles. Most likely cause: it
  draws each position independently with no team-stack correlation and no iterative-proportional-
  fitting reweighting after the salary-cap filter. Rebuilt properly the same session, see below.

## Classic field simulator built and validated (2026-09-22)
Generalized `scripts/showdown_field.py`'s method to a full 9-slot classic roster:
`scripts/classic_field.py`, validated by `analysis/classic_diag/validate_classic_field.py`. Two
things classic needed that Showdown's simpler 2-team/6-slot field didn't:
- **5 weight groups instead of 2** (QB, RB, WR, TE, FLEX vs. Showdown's CPT/FLEX), with a real
  ownership target that's a SINGLE number per player covering both a dedicated slot and the FLEX
  slot (DK's real export doesn't split "rostered as WR" from "rostered as FLEX" the way it splits
  CPT/FLEX for Showdown) -- the IPF correction tracks each player's TOTAL observed exposure across
  every weight group they can appear in and applies one correction factor to all of them.
- **Explicit stack-correlation bias.** An iid draw from marginal ownership reproduces almost no
  real QB-stacking on its own. Added a `stack_boost` multiplier on a QB's own teammates' draw
  weight when filling RB/WR/TE/FLEX slots for that same lineup, auto-scaled by the number of teams
  in the pool (a fixed boost dilutes hard on a 26-32-team main slate vs. a 4-6-team early/afternoon
  slate) -- calibrated against the real per-slate QB-stack rates from the cash-line diagnostic
  above (boost=3 base, scaled by `n_teams/8`, capped at 12).
- **Validated against all 6 real classic slates logged so far** (real ownership + real points fed
  in, compared to the real contest's own score quantiles -- same method as Showdown's
  `validate_field.py`): median through p95 within 0.1-3.0pts on every slate, p99/p99.9 within
  0.2-4.5pts (comparable to or tighter than Showdown's ~1-3pt bar). Real QB-stack rate (0.81-0.95
  across slates) reproduced within a few points (sim 0.90-0.96) after the auto-scaled boost;
  ownership MAE 0.37-1.12 (absolute percentage points) across slates.
- **This clears the bar to use it for candidate-lineup scoring** the way Showdown's
  `best_single.py`/`refine_single.py` score candidates' P(top-10%)/P(top-1%) against
  `showdown_field.py`.

## Classic scenario-scoring tool built (2026-09-22): `analysis/classic_diag/best_lineup_classic.py`
Classic counterpart to `analysis/showdown_own/best_single.py`, completing the port of the
"generate many candidates, score against a validated field under several correlated-outcome
scenarios, keep the worst-case not just the average" construction method to classic (the item
Greg flagged as wanting standardized/automated across both slate types).
- **Candidate generation**: many noisy solves (`optimizer.build_single_lineup` with
  `randomization_pct`) plus forced QB-stack solves (`stack_mode="qb", stack_size=2,
  bring_back=True`) on the top-projected-QB teams -- reuses the SAME optimizer functions the CLI
  and frontend already call, no new solver code.
- **Outcome model**: a per-game shared factor + per-team factor (own-vs-opposing-team skill
  correlation +0.21, calibrated from this file's own 2014-21 rotoguru finding), QB-to-own-WR/TE
  correlation +0.77 (also from that finding), DST-to-opposing-offense correlation -0.44 (same
  source). RB's correlation to the team passing factor is NOT a measured constant from that data
  -- set to a documented, honest approximation (0.3) rather than presented as fitted.
- **4 scenarios** (base / shootout / quiet-DST / run-heavy, varying the game-environment and
  pass-correlation strength) scored against `classic_field.py`'s validated field, reporting both
  the average P(top-10%) across scenarios and the WORST scenario (the Showdown session's method
  for catching a lineup that looks best on paper but is really a bet on one modeling assumption).
- **Smoke-tested end to end** on wk2 afternoon (20 candidates, small field/sim counts, ~30s):
  produced sensible output -- stacked candidates (McCaffrey/Purdy/49ers-type builds) scored
  25-32% avg top-10% / 3-8% avg top-1%, and the worst-case column visibly diverges from the
  average for several candidates (e.g. one build: 26.3% avg but only 20.0% worst-case) --
  confirming the robustness check does distinguish candidates the simple average would treat as
  equal. **Not yet run at full candidate/field/sim scale on a real slate to pick an actual
  lineup** -- that's the natural next use (same status as Showdown's tool before it was used for
  a real pick: `python analysis/classic_diag/best_lineup_classic.py dk <slate_id> [n_candidates]`).
- **Still open, same as Showdown's construction method**: whether/how to formalize this into
  `optimizer.py` or the frontend rather than keep it as an ad hoc analysis script -- this is the
  SAME still-open decision the Showdown handoff flagged, now applying to both slate types
  symmetrically. Also open: validating the RB-passing-factor approximation and the 4 scenario
  weightings against real classic outcomes the way `top10_drivers.py`-style analysis validated
  Showdown's construction findings, once this tool has been used on a few real slates.
