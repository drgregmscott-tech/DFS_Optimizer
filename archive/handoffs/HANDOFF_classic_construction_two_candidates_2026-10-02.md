# Classic construction: the two "borrow from Showdown" candidates, backtested (2026-10-02)

Backtest only. Nothing live was changed (`data/optimizer_presets.json` and `scripts/optimizer.py` are untouched).
Scripts and outputs: `analysis/classic_exposure_test/`. Everything there is our own solver's output graded against DK's own
contest-result files (`data/contest_results/dk_classic_*`). There is no FC-derived data in it.

## The question, in the owner's words
> "test whether Classic lineup construction can borrow the two levers that appear to make Showdown outperform it right now
> ... Don't change anything live before backtesting."

- **Candidate 1:** wire the Classic Lineup Study findings into real optimizer terms, the way Showdown's became `--sd-*`.
- **Candidate 2:** "se3max_pool caps every player at 50% exposure across the pool, which structurally dilutes even the single
  highest-conviction (most chalk-aligned) lineup". Test raising the cap, and test a two-tranche split (a cash subset near the
  best lineup plus a diversified upside subset).

## Bottom line
- **Nothing cleared the ship bar.** Every candidate is **inconclusive, keep testing**. None is wrong-direction.
- **The Candidate 2 premise is mechanically false for the lineup the owner actually submits.** The pool builder makes lineups
  one after another, and the cap is `floor(0.5 x 100) = 50` uses per player (`optimizer.py` line ~2723). So the cap cannot bind
  until some player has already appeared in 50 lineups. The top lineups are built uncapped. Measured: the SE3max pick (top
  projection in the pool) is the **same lineup in 89% of paired builds at cap 1.0 vs 0.5**. Pick percentile -0.014 (SE 0.014),
  pick cash rate identical (22% both).
- **The real gap this test exposed is selection, not the cap.** The pool's hindsight-best lineup averages the 98th
  percentile. The lineup the documented process picks ("rank by projection", `feedback_se3max_pool_review_process`) averages
  the **60th**, and cashes 2 of 9 slates (22%), about what the owner actually got. The preset `_comment`'s "best lineup in a
  100-lineup pool lands at the 98th-99.9th percentile" is a hindsight ceiling that no pre-lock rule achieves. It should not
  be read as evidence the pool works.

## What was already done (verified in the repo, not redone)
- `se3max_pool` already carries the lineup study's shape terms: `cl-dst-band-bonus`, `cl-dst-expensive-penalty`,
  `cl-zero-punt-penalty`, `cl-three-plus-punt-penalty`, `cl-flex-rb-bonus`, `cl-flex-wr-penalty`. They are real ILP terms
  (`add_classic_shape_terms`, `classic_shape_adjustment`). They were shipped 2026-09-30 after a 9-slate check that came back
  inconclusive.
- QB+2 stacking is already a hard rule (`stack-mode qb, stack-size 2, bring-back`).
- "#1-owned QB" was already tested against our pre-lock ownership and correctly rejected
  (`HANDOFF_classic_prelock_ownership_retest_2026-09-29.md`).
- `WK3_POSTMORTEM_OPEN.md` item 12 is this session's parking-lot entry. No conflicts. Its stale claim that "none of it is
  wired" is corrected by the bullets above.

## Data and the distinction between the two sources
- **Graded slates.** The 9 real 2026 wk1-3 DK classic slates: main, early and afternoon each week, all SE3max fields
  (wk1 = the field the owner entered). These are the same files and grader as
  `analysis/classic_shape_weights/replay_cl_arm.py`, so the numbers here are apples-to-apples with the committed se3max_pool
  evidence. Cash means the top 25% (`rv.CASH_PCT`).
- **MME check.** The 2 real MME fields (wk2/wk3 main), where the owner actually entered 20 lineups. The owner's real entry
  counts are 1 per SE3max contest (9/9 slates) and 20 in each MME main.
- **Live settings for every build.** Stack qb/2 with bring-back, randomization 5%, uniqueness 1, lambda 0, the live `cl-*`
  weights.
- **Seeds.** 2 seeds per slate for the exposure arms, so 18 paired pools per arm. 12 paired seeds per slate for the stud term.
  All SEs are slate-level (n = 9).
- **Why the 410-contest Lineup Study can't grade this.** It shows that real-field entries with higher realized ownership
  cash more. It cannot say what exposure cap our own pool builder should use, because that requires our own solve, and only
  these 9 graded 2026 slates have one. It is the "why concentration might help" context, not the test.
- **Return metric.** DK result files have no payout tables, so capped return could not be computed. Cash rate, mean
  percentile and top-1% hits stand in for it.

## Candidate 1 remainder: stud-count term (studs = non-DST >= $7,000)
**Evidence grade first (SHOWDOWN_RULES template): Weak.**
- 3+ studs is raw-only: -1.2 cash pts in SE, -1.3 in 3MAX, -2.2 in 20MAX (0/4 seasons).
- 0 studs is -1.6 to -2.5.
- It is not in the §5 projection-controlled model, and the study's own §7 says stud count "matter[s] little or not at all".

**Test.** `replay_stud_arm.py` (test-only monkeypatch, same aux-binary mechanics as the 3+ punt term). 9 slates x 12 paired
seeds on top of the live `cl-*` set.

| Arm | 3+ stud share | 0-stud share | Proj | Real pct | Paired d pct (SE) | Slates up/down | Cash |
|---|---|---|---|---|---|---|---|
| Live cl-* (base) | 39.8% | 10.2% | 122.6 | 0.577 | - | - | 21.3% |
| 3+ stud pen 0.9 (raw x0.75) | 18.5% | 10.2% | 122.4 | 0.569 | -0.008 (0.018) | 2/5 | 20.4% |
| 3+ stud pen 1.65 | 9.3% | 10.2% | 122.2 | 0.576 | -0.001 (0.017) | 2/5 | 22.2% |
| 3+ pen 0.9 + 0-stud pen 1.65 | 18.5% | 0.9% | 122.4 | 0.590 | +0.013 (0.028) | 3/5 | 21.3% |

- The term moves shape as designed, at a small projection cost.
- Real results are flat.
- The only positive arm's +0.013 is almost entirely one slate (wk1_afternoon +0.186). The other 8 slates net slightly
  negative.

**Grade: inconclusive, keep testing (low priority). Do not wire.** The evidence is Weak and the replay is null.

## Candidate 2a: raise se3max_pool's max-exposure
Paired vs live cap 0.5. For each metric, d = change and SE = slate-level SE; slates up/down are in brackets.

**SE3max use (100-lineup pool, 1 entry picked by top projection)**

| | Cap 0.5 (live) | Cap 1.0 |
|---|---|---|
| Same pick as cap 0.5 | - | 89% |
| Pick real pct | 0.604 | 0.590 (d -0.014, SE 0.014) |
| Pick cash | 22% | 22% |
| Top-3 any cash | 33% | 33% |
| Hindsight-best in pool (ceiling) | 0.982 | 0.966 |
| Pool cash rate / mean pct | 26.4% / 0.518 | 29.2% / 0.566 (d +2.8 pts, SE 3.8; +0.048, SE 0.039; [6/3]) |
| Top-1% lineups per pool | 0.94 | 0.67 |
| Max player exposure / avg pairwise overlap | 50% / 3.0 of 9 | 94% / 4.5 |

**20-entry portfolio (the owner's MME entry count), graded vs the 9 SE3max fields**

| | Cap 0.5 | 0.65 | 0.8 | 1.0 |
|---|---|---|---|---|
| Cashes per 20 | 5.39 | 5.28 | 5.56 | 5.67 (d +1.4 pts, SE 4.7) |
| Mean pct | 0.528 | 0.555 | 0.563 | 0.577 (d +0.050, SE 0.044; [6/3]) |
| Portfolios with a top-1% hit | 22% | 22% | 11% | 11% |
| Mean proj / our modeled own sum | 117.0 / 152 | 119.2 / 161 | 120.9 / 167 | 122.1 / 172 |

**20-entry portfolio vs the REAL MME fields (cashes per 20, mean pct)**

| Slate | Cap 0.5 | 0.65 | 0.8 | 1.0 |
|---|---|---|---|---|
| wk2_main | **10.5**, 0.708 | 8.5, 0.656 | 7.0, 0.584 | 5.5, 0.542 |
| wk3_main | 3.0, 0.460 | 3.0, 0.507 | 3.5, 0.557 | 3.5, 0.555 |

**Read.**
- For the 1-entry SE3max pick, the cap is irrelevant by construction, and the data confirm it.
- For multi-entry, a higher cap does what you'd expect. It concentrates on the projection/chalk core (+5 proj, +20 modeled
  ownership), nudges mean percentile up and gives up ceiling (top-1% hits halve).
- Every difference is inside 1-1.2 SE, and the 2 real MME fields split: cap 0.5 clearly best on wk2, cap 0.8-1.0 slightly
  better on wk3.
- This is the Lineup Study's direction ("more chalk cashes"), but not detectable on 9 slates.

**Grade: inconclusive, keep testing.** Not wrong-direction for multi-entry. Irrelevant for SE3max.

## Candidate 2b: two-tranche pool
- **100-pool version:** 20 lineups at cap 1.0 / uniqueness 1, plus 80 at cap 0.5 / uniqueness 2 / randomization 10%.
  - SE3max pick: d pct -0.028 (SE 0.020). Top-3 any cash 44% vs 33% (+1 slate). Pool cash +1.2 pts (SE 1.6).
  - Top-1% per pool: 1.11 vs 0.94.
- **20-entry version:** 5 cash lineups (cap 1.0) plus 15 upside lineups (cap 0.5, uniqueness 2, randomization 10%).
  - SE3max fields: cashes 5.22 vs 5.39, mean pct -0.006 (SE 0.021) [4/5]. Top-1% hit in 28% of portfolios vs 22%.
  - Real MME fields: wk2 7.0 cashes vs 10.5; wk3 **5.0 vs 3.0**, best 0.951 vs 0.873.

**Grade: inconclusive, keep testing.** Neutral on cash, slightly more ceiling, real-MME split 1-1.

## Single most valuable fixable thing
**Nothing here clears the ship bar, so there is no wiring plan for the cap or the stud term.**

The most valuable fixable item this test surfaced is the **SE3max selection rule**:
- The pool already contains a ~98th-percentile lineup on average, but "rank by projection" picks a 60th-percentile one,
  about field-median-plus, and cashes 22%.
- The pick is where Classic SE3max is losing, and no exposure setting touches it.
- Concretely, the next test is: within the existing 100-lineup pool, does re-ranking by **pre-lock modeled ownership sum (or
  projection + ownership blend)** pick better than raw projection on these 9 slates?
  - This is the pre-lock-honest version of the Lineup Study's ownership headline.
  - `pool_summary.csv` / `lineups_graded.csv` already hold every pool lineup with `proj`, `own` (our pre-lock model),
    `pct` and `cash`. The test is a ~20-line re-rank, no new solves.
  - The rank rule must be pre-committed before looking. The existing `analysis/classic_diag/replay_selection_criteria.py`
    touches this area, so check its results first so it isn't duplicated.
- **Caveat:** the earlier pre-lock QB-ownership retest failed because our ownership model's top picks disagree with the
  field. A lineup-level own-sum re-rank may inherit that weakness. That is exactly what the test would show.

**Track-2 re-test conditions:**
- **Cap (multi-entry only):** re-grade cap 0.5 vs 0.8 on each new real MME main (Wk4+). Ship 0.8 for MME-type builds only
  if, pooled over at least 6 MME slates, cashes per 20 are up with the slate-level CI excluding 0. Leave se3max_pool's cap
  alone either way, since it does not affect the SE3max pick.
- **Two-tranche:** same pooled MME re-grade. It is a ceiling lever, so judge it on top-1% / best-lineup, not cash.
- **Stud term:** only revisit if a projection-controlled (§5-style) coefficient for 3+ studs comes back Supported.

## Housekeeping / caveats
- Projections are each slate's current `output/final_projections_*` file (the same stand-in caveat as `replay_validation.py`).
- 2 seeds for the exposure arms, after a 3-seed, 10-arm run was cut for time (it was on pace for ~90 min). Caps 0.65/0.8 were
  run for the 20-entry portfolio only.
- While restarting the sweep I ran `taskkill /IM python.exe`, which also stops any unrelated Python process that was running
  on the machine at that moment.
- Files: `exposure_sweep.py`, `analyze_sweep.py`, `analysis_out.txt`, `lineups_graded.csv`, `pool_summary.csv`,
  `replay_stud_arm.py`, `stud_arms.csv`, `stud_log.txt`, `sweep_log.txt`. Not committed.
