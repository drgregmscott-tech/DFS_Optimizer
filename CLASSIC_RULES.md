# DK Classic construction rules (living doc, created 2026-09-30)

Evidence-graded construction rules for DraftKings NFL Classic, the classic counterpart to `SHOWDOWN_RULES.md`.
Update after each slate batch. **As of 2026-09-30 the DST/punt findings are live in the optimizer; the FLEX rule was
replaced 2026-10-02 with a WR-price-tier version (see rule 3)** via all four classic presets (`cash`, `se_gpp`, `mme_gpp`,
`se3max_pool`). See "Optimizer enforcement" below.

## Evidence base
- **Classic FC Lineup Study:** 410 real DK classic contests, 21.9M entries, 2022-2026, SE / 3MAX / 20MAX / big GPP
  (`HANDOFF_classic_lineupstudy_findings_2026-09-29.md`). §3 = raw cash lift per shape feature (cash-rate pts vs the
  contest's base rate, 90% CI, seasons with the sign). §5 = multi-feature per-contest OLS that controls for FC projection,
  ownership, QB salary, QB+2, bring-back and salary left.
- **Grades:** *Supported* = CI excludes 0 and the sign holds in most seasons, in more than one contest type. *Weak* = right
  sign, CI touches 0 or only one format.
- **Real-slate sanity check** of the shipped weights: 9 real 2026 Wk1-3 DK classic slates (`analysis/classic_shape_weights/`).

## Rules

1. **DST salary: $2.8-3.1k is best, $3.6k+ is worst. Supported, all 3 formats.** Cash lift $2.8-3.1k +0.8 / +1.2 / +1.2
   (SE / 3MAX / 20MAX, 3MAX 4/4 seasons); $3.6k+ -2.3 / -2.8 / -2.9 (20MAX 0/4 seasons, return 0.86-0.90x). Under $2.8k is
   only neutral (+0.3 / +0.4), so the rule is "cheap and believable", not "cheapest DST".
   **Projection-controlled re-fit, 2026-10-05 (Wk4 construction review):** `analysis/wk4_construction_review/
   dst_band_controlled.py`, 362 contests, §5 controls (ownership, projection, QB salary, stack, punt, bring-back, salary
   left) + DST band dummies vs <$2.8k + FLEX dummies + DST conflict. Controlled cash lift (SE / 3MAX / 20MAX):
   - **$2.8-3.1k: +1.5 / +1.9 / +1.2, passes in all three (4/4 seasons pooled). Points +1.4 / +1.5 / +1.0.** Band holds,
     and is slightly stronger after controls than raw.
   - $3.2-3.5k: +0.8 / +1.6 / +0.6 cash (CI touches 0), points +0.9 pooled (passes). Not distinguishable from the band.
   - **$3.6k+: +0.2 / +0.2 / -0.3 cash, points +0.04 pooled -- zero in every format.** The raw -2.3 to -2.9 was the
     salary/projection confound (an expensive DST leaves less for everything else), which the solver already prices.
   - **But 2026 real DK fields say the opposite for OUR projections:** Wk1-4, 12 contests with a $3.6k+ DST in play,
     $3.6k+ lineups cashed **-8.2 raw / -9.4 controlled by our projection + realized ownership, 0/12 contests positive**
     (Wk4 alone -3.0 / -4.7, 0/4). FC's projection explains the expensive-DST gap away; ours doesn't -- i.e. our
     projections still over-rate expensive DSTs (the 2026-10-04 `dst_recal_v2` fix was intercept-only, not salary-tier).
   - **Decision: no weight change.** The penalty is doing real work as a correction on our own DST projection. The
     proper fix is on the projection side (salary-tier check of DST projection error), not here -- parked. A 2.0 -> 0.4 cut
     was drafted from the FC-controlled fit and reverted for this reason. Band: history-controlled holds; 2026 mixed
     (8/15 contests positive raw, Wk4 0/4). Holds, no change.
2. **Punts (non-DST at $4,000 or less): 0 is bad, 1 is best, 3+ is bad. Supported.** 0 punts -2.2 / -2.3 / -1.9 raw. After
   §5's projection control, having at least 1 punt is still worth **+1.4 to +1.9** (Supported in SE and 20MAX). 2 punts is
   neutral (+0.1 to +0.3). 3+ punts -2.7 / -4.1 / -4.7 raw (no controlled term). "More punts is better" is contradicted.
   **2026-10-05 update (Wk4 construction review):** a controlled re-fit (`analysis/wk4_construction_review/
   history_controlled_checks.py`, 353 contests, §5 controls + punt-count dummies vs 1 punt) gives **0 punts -1.2 cash /
   -1.0 pts (passes, holds)**, 2 punts +0.7 / +0.5 (ns), **3+ punts +0.4 cash / -0.35 pts, CI spans 0 in every format**.
   The raw 3+ penalty was a projection confound. 2026 real DK fields agree: Wk1-4, 0 punts -7.0 raw / -8.6 controlled,
   1/15 contests positive (Wk4 0/4) -- strongly holds; 3+ punts +8.5 raw / +6.6 controlled, 9/13 positive (Wk4 1/3).
   **Shipped: `--cl-three-plus-punt-penalty` 2.5 -> 0.5** (all four presets + UI defaults). Zero-punt 1.5 unchanged.
3. **FLEX position: the flat "RB > TE > WR" rule is NOT supported. Replaced 2026-10-02 by a WR-price-tier rule: pay up
   for a WR in FLEX, or don't use one at all.** The old grade came from §3's raw lift only (FLEX RB +0.7 to +1.0, FLEX WR
   -1.2 to -1.5). Controlled re-fit (`analysis/flex_position/flex_experiment.py`, 381 contests 2022-26, per-contest OLS =
   §5's model + FLEX=RB / FLEX=WR dummies, **TE as the omitted baseline** -- i.e. every number below is "vs TE", not "vs
   each other" -- then + the FLEX player's own projection, salary and ownership):
   - **RB vs TE is ~0 at every price tier, every format, on points or cash rate.** RB in FLEX is indistinguishable from TE.
     The old RB bonus was never a real effect -- `--cl-flex-rb-bonus` is dead, kept only for manual override.
   - **WR vs TE pooled across all prices is also ~0** (points CI spans 0 in every format; the one pooled cash-rate number
     that clears is a ~1pt edge, too small to act on alone). The original RB>WR grade was real as a *relative* statement
     but came entirely from WR underperformance in the mid tier below, not from RB being good or TE being bad.
   - **The real effect is a single salary-conditioned WR swing, confirmed per-format (not just pooled):**
     - **WR $6,300+:** beats TE by **+2.8 to +4.1 points** / **+3.9 to +6.1 cash-rate pts**, 4/4 seasons, **passes in all
       three formats (SE, 3MAX, 20MAX) on both metrics.** Also beats RB directly at this tier by +2.3 to +2.8 points
       (the rbwr term), 3/4 seasons. This is the single most robust number in the whole experiment and matches the PPR
       read: a pricey, high-target WR in FLEX outscores a same-tier RB or TE.
     - **WR $4,900-$6,300:** a real **downgrade** vs TE, -1.3 to -1.5 points / -1.6 to -2.0 cash-rate pts; passes in SE
       and 20MAX (3MAX trends the same direction, 4/4 season sign, but its own CI doesn't individually clear).
     - **WR under $4,900, and RB/TE at every price:** no proven effect either direction -- a statistical wash, not a
       proven inferiority. Don't read "cheap WR is bad" into this; the data just doesn't distinguish it from the rest.
   - Net ranking: **WR $6,300+ > {RB any price, TE any price, WR under $4,900} > WR $4,900-$6,300**, with only the top and
     bottom groups statistically real.
   - Results tables: `analysis/flex_position/out/` (local only, FC-derived).
   - **FLAG, 2026-10-05 (Wk4 construction review) -- 2026 real fields do not show it, and the optimizer applies it more
     broadly than the evidence.** (a) DK FLEX-slot WR $6.3k+ on 2026 Wk1-4 fields (15 contests): cash -0.3 raw vs field,
     6/15 positive (Wk4 -5.2, 1/4); TE in FLEX was the best raw FLEX (+5.3 Wk1-3 10/11, +1.8 Wk4 3/4). (b) The study's
     variable is the player in DK's FLEX *slot*; the solver can't see slots, so it gives +3.0 to ANY 4-WR lineup holding a
     $6.3k+ WR. In the replay (se3max_pool, 15 slates x 20 seeds) that turns **95% of builds into 4-WR lineups** (11% with
     the terms off). That lineup-level version was never tested on history (the FC parquet stores only the FLEX-slot
     player's salary); on 2026 fields it is -0.7 raw, 7/15. **Not changed** -- 15 contests don't overturn a 4/4-season
     finding -- but it is the top inconclusive-keep-testing item: rebuild the FC classic entries with every WR's salary and
     test "4 WR incl. a $6.3k+ WR" vs 3-WR builds with the same controls.
   - **Drill-down, same day (`analysis/wk4_construction_review/RESULTS_flex_wr.md`) -- bonus set 3.0 -> 0.**
     (1) Live UI builds never had it: the Cloudflare worker allowlist and `run_optimizer_dispatch.yml` were never given
     `cl_flex_wr_highprice_bonus`/`cl_flex_wr_midprice_penalty` when they were added 2026-10-02. The UI sent them; the
     worker dropped them; the Wk4 main MME run's actual command line has no `--cl-flex-wr-*` flags. Fixed in both files.
     (Moot now — both flags were zeroed the next day, see below; the worker redeploy that actually matters, for
     `cl_four_wr_no_stud_penalty`, is confirmed done — see rule 3's bottom line.) (2) The TE lean in live builds is plain projection-per-dollar:
     with every FLEX term off, TE wins FLEX on 8/12 2026 pools and RB on 4. TE-in-FLEX was also the best raw FLEX on 2026
     fields. (3) With the bonus on, 10/12 pools flip to 4 WR at -1.4 projected pts. The added WR is usually cheap
     ($3.0-4.4k). The bonus is "earned" by a stud WR that was already in the 3-WR lineup. 92% of real 4-WR lineups hold a
     $6.3k+ WR, and DK FLEX-slot placement is close to random by price (cheapest WR in FLEX 35%, priciest 24%), so the
     history's slot finding doesn't map to that lineup property. Pooled WR-vs-TE is ~0 on history. Midprice penalty 1.3
     kept (near-inert). Next test: same as above, plus an "expected slot" version (bonus x share of the 4 WRs priced
     $6.3k+).
   - **Lineup-level re-test, 2026-10-06 -- SHIPPED as a replacement: `--cl-four-wr-no-stud-penalty` 1.0, both price-tier
     flags 0.** (`analysis/wk4_construction_review/RESULTS_flex_wr_lineup_level.md`, local only.) Rebuilt the FC classic
     entries with every WR's own salary (`lineup_study_build.py`, additive columns `n_wr`, `wr_sal_min..max`, `n_wr_hp`,
     `share_wr_hp`) and re-ran §5 (382 contests, 2022-26, same controls, same grading, plus a slate-clustered bootstrap
     because contests on one slate share one outcome). Every number is per-contest OLS, 3-WR lineups as the baseline:
     - **The scope the bonus used ("4 WR incl. any $6.3k+ WR") is ~0:** -0.1 pts / -0.3 to -0.6 cash, 2/4 seasons, fails
       in every format. Zeroing the 3.0 bonus was right. 4-WR vs 3-WR overall is also ~0 (-0.2 to -0.35 pts).
     - **Option (a), split by the cheapest WR's price: dropped.** No cheapest-WR tier passes in all three formats
       (<$4k -0.1 pts, $4-4.9k -0.4 to -0.7, $4.9-6.3k -0.2; "cheapest WR $6.3k+" is 0.1% of lineups, pure noise).
     - **Option (b), expected-slot (4-WR x share of WRs $6.3k+): the effect is real but it is not a slot effect.** Read
       literally it is +4.3 pts per unit share on a -1.7 pt 4-WR baseline. But once the plain count of $6.3k+ WRs is
       controlled, the 4-WR x count interaction is ~0 (+0.0 to +0.1 pts, fails everywhere). The count effect itself
       (+1.0 pt per $6.3k+ WR) is an era effect: +1.9 to +2.4 in 2022-23, -0.0 to -1.3 in 2024-25, and it fails on the
       slate-clustered CI. Not shipped.
     - **What does hold: a 4-WR build with NO WR priced $6,300+.** vs all 3-WR lineups: **-1.6 / -1.6 / -1.8 pts, -2.5 /
       -2.4 / -2.7 cash, return 0.83-0.87x** (SE / 3MAX / 20MAX), passes in all three, 3-4/4 seasons, also passes
       slate-clustered pooled (-1.7 pts, 4/4). Quality subset the same (-1.8 to -2.1 pts). It is NOT just "no stud WR
       is bad": vs a 3-WR lineup that also has no $6.3k+ WR it is still **-0.9 / -1.0 / -1.0 pts, -1.4 / -1.4 / -1.6
       cash**, passes in all three formats, 3-4/4 seasons (slate-clustered: passes pooled and in 3MAX/20MAX, SE cash
       only). A 3-WR no-stud lineup alone is a weak,
       fading -1.0 pts (2/4 seasons). ~3.5% of the real field builds it.
     - **2026 real DK fields agree (15 contests Wk1-4, our projection + realized ownership controls):** 4-WR no stud vs
       3-WR -10.1 cash / -6.6 pts, 2/15 contests positive; vs 3-WR no stud -3.8 cash / -2.4 pts, 3/15 positive, Wk4
       -5.7 cash, 0/4 positive. The 2026 field is not in conflict this time.
     - **Shipped:** `--cl-four-wr-no-stud-penalty` 1.0 in all four presets and the UI preset bundles (sized from the
       cleanest effect, the -0.9 to -1.0 pts vs 3-WR-no-stud, not the bigger -1.7 that includes the fading no-stud
       part). `--cl-flex-wr-midprice-penalty` 1.3 -> 0: it was the same slot-scoped finding, it only fired when all 4
       WRs were $4.9-6.3k (a subset of the new term), and at lineup level that tier is -0.2 pts, ns.
       `--cl-flex-wr-highprice-bonus` stays 0. Wired through the worker allowlist, `run_optimizer_dispatch.yml` and
       `index.html` — **worker redeployed 2026-10-07** (`dfs-optimizer-api`, version `110adc9c`), confirmed
       `cl_four_wr_no_stud_penalty` live in the allowlist, so UI builds now actually apply this term. Replay ("Re-run 2026-10-06" below): identical lineups on all
       300 pairs. Our solver doesn't build this shape today, so it is a guardrail, not a fix for the 2026 misses.
       **Bottom line for rule 3: no FLEX-WR bonus exists at lineup level; the only real FLEX-WR effect is "don't play
       a 4th WR unless one of your WRs is $6,300+".**
4. **DST facing your own skill player: bad. Supported** (-1.9 / -2.1 / -3.0, 0/4 seasons, 11-13% of the field does it).
   Already a hard constraint (`exclude_skill_vs_opp_dst`, default on), not a `--cl-*` term.
5. **Ownership:** realized ownership predicts cashing (+1.1 DST to +2.8 RB per SD of log-ownership, 4/4 seasons), but
   `--own-penalty` fading is dropped and chalk tilt with our own modeled ownership showed no gain on history. Not a shape
   lever until the ownership model improves. See `WK3_POSTMORTEM_CHECKLIST.md` track-2 outcomes.
   **Superseded 2026-10-07 for pool ranking (not a shape term): our own modeled ownership DOES carry real lineup-sum
   signal once scored correctly** (WK4 postmortem items 12/15 — the earlier "no signal" reading used a pre-v2 ownership
   model never joined to the test pools). Held-out history partial-corr of lineup-sum ownership vs. real finish
   (controlling for projection) is +.08 to +.11 with today's v2 model, vs ~0 with the old one. **Shipped:** the built
   pool is now re-ranked by `z(sum projection) + 0.75*z(sum log(estimated_ownership_pct+.5))` after the existing
   projection-only sort (`_rank_lineups_by_proj_own()`, `scripts/optimizer.py`, single call site in classic
   `build_multi_lineup`, commit `97be43a7`, default ON — env `DFS_RANK_OWN_W` controls the weight, `0` turns it off,
   fails safe to pure-projection order on any error). **This changes which lineup lands at #1** — it's a noisy-but-real
   nudge toward chalk-awareness on the sort order, not an auto-submit signal; re-check it after each new week
   (`analysis/lineup_own_signal/check_2026.py`) and flip `DFS_RANK_OWN_W=0` if a future week turns it wrong-direction.
   Showdown untouched — separate ownership model/question.
6. **QB price, stud count, punts beyond 1-2: matter little or not at all.** QB+2 is real but smaller than assumed.

## Optimizer enforcement (2026-09-30)

Rules 1-3 are soft ILP terms in `solve_lineup()` (`add_classic_shape_terms()` in `scripts/optimizer.py`; also added to
`build_multi_lineup()`'s cross-stack-candidate score). **Same weights in all four classic presets.** The shape findings
held similarly across SE/3MAX/20MAX, and they are not the contest-type-specific "lean chalkier" ownership finding, so a
per-preset split has no evidence behind it.

Point scale follows Showdown: 1 cash-lift pt ~ 1 projected pt. Where §5 gives a projection-controlled coefficient, that
is used. Where it doesn't, the raw lift is shaded x0.75 (the zero-punt controlled/raw ratio, ~1.6/2.1), since part of a
raw shape effect may already be reflected in projection that the solver is maximizing.

| Flag | Value | Basis |
|---|---|---|
| `--cl-dst-band-bonus` | **0.8** | rule 1, raw +0.8/+1.2/+1.2 (mean ~1.07) x0.75 |
| `--cl-dst-expensive-penalty` | **2.0** | rule 1, raw -2.3/-2.8/-2.9 (mean ~2.67) x0.75. 2026-10-05: ~0 after FC-projection controls, but -9.4 cash vs OUR projection on 2026 fields (0/12) -- kept as a projection correction |
| `--cl-zero-punt-penalty` | **1.5** | rule 2, §5 controlled "≥1 punt" +1.4 to +1.9 |
| `--cl-three-plus-punt-penalty` | **0.5** (was 2.5) | rule 2, 2026-10-05 controlled re-fit: 3+ punts -0.35 pts / +0.4 cash, CI spans 0; 2026 fields +6.6 controlled, 9/13 |
| `--cl-flex-rb-bonus` | **0** (was 0.6) | rule 3: dead at every price tier after controls (2026-10-02). Kept for override only. |
| `--cl-flex-wr-penalty` | **0** (was 1.0) | rule 3: flat version dead after controls (2026-10-02) -- replaced by the two price-tier flags below. Kept for override only. |
| `--cl-flex-wr-highprice-bonus` | **0** (was 3.0) | 2026-10-05: as implemented it paid +3.0 for adding a cheap 4th WR next to a stud already rostered (see rule 3 drill-down); never reached live UI builds anyway (worker bug). Parked pending a lineup-level history test |
| `--cl-flex-wr-midprice-penalty` | **0** (was 1.3) | 2026-10-06: slot-based finding; at lineup level "all 4 WRs $4.9-6.3k" is -0.2 pts, ns, and is a subset of the term below. Kept for override only |
| `--cl-four-wr-no-stud-penalty` | **1.0** | rule 3 lineup-level re-test (2026-10-06): 4-WR build with no WR $6,300+ is -0.9 to -1.0 pts vs a 3-WR build that also lacks one (-1.6 to -1.8 vs all 3-WR), passes SE/3MAX/20MAX, 3-4/4 seasons; 2026 fields 12/15 negative |

Every flag can be overridden on the command line (`--cl-... 0` turns one off). All flags at 0 is byte-identical to the
pre-2026-09-30 solve. **Implementation note (fixed 2026-10-02):** classic has no explicit FLEX variable -- the solver
only knows "3 WR slots + 1 shared FLEX slot," not which specific player occupies FLEX. The two new FLEX-WR terms solve
this with an auxiliary binary per selected WR ("is this one the discretionary 4th WR"), pinned exactly to the real
extra-WR count (0 when you carry your normal 3 WRs, 1 when FLEX is a WR). The practical effect: a mandatory WR among your
fixed 3 can NEVER take the mid-price penalty no matter its own salary, and two $6,300+ WRs only earn the bonus once, not
twice -- both of those were real gaps in the first version of this term (same-day fix, never shipped). See
`add_classic_shape_terms()`'s docstring in `scripts/optimizer.py` for the full mechanics; `classic_shape_adjustment()`
replicates the same tagging logic for the cross-candidate scorer in `build_multi_lineup()` without needing a second LP solve.

### Real-slate sanity check (`analysis/classic_shape_weights/replay_cl_arm.py`, outputs `run_out*.txt`, `seeded_arms*.csv`)
9 real 2026 DK classic slates (Wk1-3 main/early/afternoon), graded against the real contest results in
`data/contest_results/` (top-25% cash line, SE3max field). se3max_pool structure (QB stack 2 + bring-back), 20 paired
5%-randomized seeds per slate = 180 pairs, terms off vs on:

| | off | on (shipped) |
|---|---|---|
| DST in $2.8-3.1k | 16% | 63% |
| DST $3.6k+ | 25% | 2% |
| 0 punts / 3+ punts | 19% / 13% | 4% / 0% |
| FLEX RB / FLEX WR | 18% / 15% | 34% / 0% |
| Mean projection | 123.5 | 122.6 (-0.9) |
| Mean real percentile | 0.549 | 0.580 (+0.030, slate-level SE 0.052) |
| Top-25% cash rate | 29.4% | 23.9% |

- **Feasible on every slate and seed.** Shape moves exactly as intended at under 1 projected point per lineup.
- **Real outcome: mixed, inside noise.** Percentile slightly up (driven by Wk2 early/main, +0.25 to +0.34), cash rate slightly
  down (Wk2 afternoon, Wk3 early). 9 slates cannot confirm or rule out a ~1-2 pt effect. That is expected: the study's
  effects are 1-3 cash pts, and the study itself (410 contests) is the evidence, not this check.
- The unshaded set (1.0 / 2.5 / 1.5 / 3.0 / 0.8 / 1.3) gave the same percentile/cash numbers at -1.1 projection. The shaded
  set was shipped because it gets the same shape shift more cheaply.
- Caveat: pools are the current `output/final_projections_*` files, not lock-time snapshots. Wk3 files may include
  post-lock rebuilds.
- **This sanity check predates the 2026-10-02 FLEX-WR price-tier rule** -- the FLEX row above (18%/15% -> 34%/0%) reflects
  the old, now-dead flat RB-bonus/WR-penalty weights, not `--cl-flex-wr-highprice-bonus`/`--cl-flex-wr-midprice-penalty`.
  Re-run `replay_cl_arm.py` with the new weights before trusting this table for the current FLEX behavior.

### Re-run 2026-10-05 with the FLEX-WR price-tier weights, 15 contests (Wk1-4, main MME and SE3max graded separately)
`analysis/weekly_construction_review/grade_week.py --week 1-4 --replay 20`, 300 pairs. Note: run while the DST
penalty was drafted at 0.4 (later reverted to 2.0), so the "on" arm is 0.8/0.4/1.5/2.5/3.0/1.3.

| | off | on |
|---|---|---|
| DST $2.8-3.1k / $3.6k+ | 13% / 19% | 50% / 9% |
| 0 punts / 3+ punts | 17% / 12% | 2% / 0% |
| FLEX RB / WR / TE | 20% / 11% / 69% | 1% / 95% / 5% |
| Mean projection | 125.1 | 123.5 (-1.6) |
| Real points | 129.7 | 130.1 |
| Mean real percentile | 0.582 | 0.591 (+0.008, slate SE 0.041, 8/15 slates up) |
| Top-25% cash rate | 34.0% | 37.3% |

Still inside noise. The big shape move is FLEX: the price-tier bonus makes nearly every build a 4-WR build (see the rule 3
flag). Wk4 alone was negative (main MME -0.19, main SE -0.18, afternoon -0.10, early +0.06).

### Re-run 2026-10-06 for the rule 3 lineup-level swap, 15 contests (Wk1-4), 300 pairs
`scripts/grade_construction_week.py --week 1-4 --replay 20 --candidate flex_wr_midprice_penalty=0,four_wr_no_stud_penalty=1.0`
(out: `analysis/wk4_construction_review/out/replay_4wr_nostud/`). "on" = the presets before this change (bonus 0, midprice
1.3); "cand" = the shipped swap.

| | off | on (old) | cand (shipped) |
|---|---|---|---|
| FLEX RB / WR / TE | 20% / 11% / 69% | 20% / 12% / 68% | same as on |
| 4-WR with no $6.3k+ WR | 0% | 0% | 0% |
| Mean real percentile | 0.582 | 0.628 | 0.628 (identical on 300/300 pairs) |
| Top-25% cash rate | 34.0% | 37.0% | 37.0% |

**The swap changes no lineup on these slates.** Our projections never build a 4-WR-no-stud lineup in the se3max_pool
structure (also 0/96 with no stack + 10% randomization). The term is a zero-cost guardrail for builds where exposure
caps, locks or thumbs push into cheap WRs; it is not a lever on current output. (The "on vs off" row differs from the
10-05 table because DST is back at 2.0 and the FLEX bonus is 0.)

## Caveats
- **First-pass point-scale calibration, like Showdown's `--sd-*` weights. Not a swept optimum.** Revisit once Wk4+ classic
  slates accumulate: re-run `replay_cl_arm.py 20` with new slates added and compare percentile/cash off vs on.
- DST band and FLEX never got a projection control in §5. If a future controlled fit shrinks them, lower the weights.
  **FLEX done 2026-10-02 (rule 3): the flat version collapsed (both old flags now 0), replaced by a WR-price-tier pair
  that IS controlled (`--cl-flex-wr-highprice-bonus`/`--cl-flex-wr-midprice-penalty`). DST done 2026-10-05 (rule 1):
  band held; $3.6k+ is ~0 after FC-projection controls but kept at 2.0 because 2026 fields show our own projection
  over-rates expensive DSTs. 3+ punts done 2026-10-05 (rule 2): cut 2.5 -> 0.5.**
- **2026-10-06: both FLEX-WR price-tier terms are now 0 in every preset, replaced by `--cl-four-wr-no-stud-penalty`
  (one binary, no slot assumption; see rule 3).** Historical note on the old terms: they were exactly scoped to the discretionary 4th WR (see "Optimizer enforcement" implementation
  note above, fixed 2026-10-02) -- still a soft nudge like every other `--cl-*` term (it doesn't force a WR into FLEX),
  but it no longer touches a mandatory WR's own price, and it adds a handful of extra binary variables per build (one
  per selected-WR-eligible player) whenever either flag is nonzero. Checked against a real 100-lineup `se3max_pool`
  build on a live Wk4 slate: no meaningful solve-time cost.
- The 3+ punt term rarely binds (13% of baseline lineups), so it is the least exercised.
- Punt definition is Phase 2's (non-DST salary ≤ $4,000). DST band is inclusive $2,800-3,100; expensive is ≥ $3,600.
