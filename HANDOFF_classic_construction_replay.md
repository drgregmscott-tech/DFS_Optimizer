# Handoff: classic construction settings + replay validation (2026-09-22)

Written to close out a long session that started from the showdown ownership/construction
handoffs (`HANDOFF_showdown_ownership.md`, `HANDOFF_showdown_session2.md` -- still accurate for
that history, read them for background) and moved into a full classic cash-line diagnostic,
settings recommendation, and replay validation. Read this file first for the classic side.

**Bottom line up front**: this session found real, replay-confirmed evidence for two things worth
using next week (stack=2/bring-back, and the candidate-pool+scenario-scoring tool), found and
fixed several real bugs along the way (documented below so they aren't repeated), rejected one
idea after testing it (a hard ownership floor), and surfaced one promising idea that was NOT
built or tested (conviction-vs-chalk contrarian signal) -- flagged clearly as open, not done.

## 0. TOP PRIORITY for next session (Greg's explicit request, not yet run)
`python analysis/classic_diag/batch_cash_drivers.py [n_lineups_per_slate]` (default 150) --
written and syntax-checked this session but deliberately NOT executed (Greg asked for it to be
queued for next session rather than run now). Builds diversified batches with the confirmed
settings (stack=2, bring-back) for all 6 logged slates, grades every lineup against real results,
and compares cashed vs. missed lineups WITHIN each batch (not across the whole real field) on:
total projection, salary, ownership sum, DST tier/matchup, team split, FLEX position, and whether
the stack team was the game's favorite. This is a narrower, cleaner test than the original 51k-
lineup diagnostic since it holds structure roughly fixed -- it should sharpen (or narrow) whether
ownership/DST/split findings hold up even among already-well-built lineups, and whether stacking
the favorite specifically matters. Full detail and rationale also in `ROADMAP.md`'s Post-Week-2
Improvement Track, item 0.

## 1. Showdown work this session (quick summary, see WK2_POSTMORTEM.md for full detail)
- Logged wk2 NYG@LAR ownership + results (3rd showdown slate, 100% match rate both).
- Found and fixed a bug in `ownership_model_showdown.py fit --validate`: its "heuristic" baseline
  comparison was silently comparing the model against its own prior-fit output for any slate
  already built with the model wired in, hiding the true out-of-sample performance. Fixed; the
  model now shows a real, confirmed improvement on a genuinely held-out 3rd slate.
- Chalk-CPT pattern (top-owned CPT gets ~0% share of top-1% lineups) now confirmed on 3
  independent slates, not just 2.
- Graded the actual NYG@LAR lineup + 10 alternates against the real field: missed top-10% by
  ~5pts; 4 of 10 alternates would have cleared it, one would have cleared top-1%.

## 2. Classic cash-line diagnostic: what was found (WK2_POSTMORTEM.md has full numbers)
Pooled 51,389 real DK Classic SE3max lineups across all 6 slates logged so far (wk1 + wk2
main/early/afternoon) to find what predicts a top-25% cash finish. Strongest, most consistent
signals: higher combined lineup ownership, TE-in-FLEX, QB+2 stacks, a bring-back player, DST in a
moderate (5-25%) ownership tier facing a lower-implied-total opponent, and a 3-3/4-2 team split.
`gmscott81`'s own 6 SE3max builds all missed cash (percentiles 14-59%) and were graded against
these signals in WK2_POSTMORTEM.md's "Classic cash-line diagnostic" section.

**Important scope note, added after later discussion**: this finding is specific to SE3max
(min-cash, top-25%-line) play. Do NOT apply "lean chalkier" to MME or Showdown GPP-max play,
where fading chalk for ceiling is separately validated and the opposite logic applies.

## 3. Replay validation: what actually got tested, and what it means (the bulk of this session)
`scripts/replay_validation.py` -- the long-flagged TODO, finally committed. Tests specific
settings changes against the 6 real historical slates by literally re-solving with the pool's
real projections and grading the result against the real contest field. Iterated through several
real methodology bugs before landing on trustworthy numbers -- **all of these are documented in
code comments in the script itself**, but summarized here because they're easy to re-make:

### Bugs found and fixed during this work (read before extending this script)
1. **A `np.searchsorted` bug produced fake "rank 1" results.** Feeding a descending-sorted array
   into `searchsorted` (which requires ascending) silently returns garbage. First replay run
   showed an impossible "6/6 cash, rank 1 every time" -- caught by manually checking that the
   claimed winning score (167.54) was below the real field's actual max (252.84). Fixed with a
   direct `(real_points > pts).sum() + 1` count instead of a sort-based trick.
2. **A units-mismatch made an ownership floor infeasible on 3 of 6 slates and actively worse on
   another.** The first ownership-floor test set the constraint threshold from the REAL,
   post-lock ownership distribution's 60th percentile, then tried to enforce it using OUR OWN
   (much flatter/less concentrated) ownership model as the constraint's data source. Our model's
   theoretical ceiling for one slate (wk2 main) was ~116.6 against a required floor of 116.98 --
   no slack once salary/stack constraints were added, hence infeasible. Rescaling the floor to
   OUR OWN model's distribution (not real ownership's) fixed the infeasibility.
3. **After fixing #2, the floor turned out to be non-binding and did nothing.** An unconstrained
   (stack+bring-back, no floor) solve already lands at the ~94th percentile of the pool's own
   achievable ownership range -- our model already prefers high-ownership players just by
   maximizing points, because ownership and quality correlate in the model too. A floor at the
   60th (or even 90th, on our own model's scale) percentile sits BELOW that natural optimum and
   changes nothing. Confirmed by checking that "Arm 2b" and "Arm B" (structural settings, no
   floor at all) produced byte-identical results.

### The arms as they ended up, and what each one means
- **Arm 1 (as-is)**: the real submitted `gmscott81` lineups. 0/6 cash (known already).
- **Arm B (structural settings only: stack=2, bring-back, TE-in-FLEX-allowed, NO ownership
  floor)**: 1/6 cash, better percentile on most slates. Clean test -- not confounded by ownership,
  since these settings genuinely aren't something the optimizer's DEFAULT_STACK_MODE="none" does
  on its own.
- **Arm C-real (structural settings + a GENUINELY BINDING 90th-percentile ownership floor,
  idealized with real post-lock ownership swapped in)**: 2/6 cash net, but high variance --
  helped a lot on 2 slates (one flipped a miss to a 96%-percentile cash), hurt badly on 3.
  Conclusion: forcing ownership past what a good/stacked projection ALREADY naturally implies is
  a real, higher-variance lever, not a safe free win. **Recommendation: do not add a hard
  ownership-floor constraint.** (Arm C-est, the realistic version on our own model's scale,
  could not be made both binding and non-infeasible without extreme thresholds -- not pursued
  further; our ownership model would need to be more concentrated before this is even testable.)
- **Arm 3 (candidate pool + scenario scoring, `analysis/classic_diag/best_lineup_classic.py`,
  run via `analysis/classic_diag/replay_arm3.py`)**: generates ~114-130 candidates (noisy solves +
  forced QB-stacks), scores each against the validated `classic_field.py` simulated field across
  4 correlated-outcome scenarios, and picks the single top-ranked candidate by average P(top-10%)
  -- selection stays blind to real results, exactly like a real pre-lock decision. Result: **2/6
  cash, percentile improved on 4 of 6 slates (sometimes by 40-60 points), but WORSE than the real
  submission on 2 of 6.** Also not uniformly better than the simpler Arm B pick -- better on 3
  slates, worse on 3. Runtime was very manageable: 35-124 seconds per slate at this scale (130
  candidates / 6,000-lineup field / 800 sims), which matters for the earlier time-crunch concern.

### The honest overall verdict from replay testing
- **Structural settings (stack=2, bring-back) are the most confidently-recommended change.**
  Backed by (a) a strong, high-N population regression, (b) the near-universal real-field
  practice (85-96% of real lineups stack), and (c) a clean, non-confounded replay showing
  0/6->1/6 cash. TE-in-FLEX is a real but softer signal (no "everyone already does this"
  backstop) -- treat as case-by-case, not always-on.
- **A hard ownership-floor constraint is REJECTED.** Real, demonstrated downside risk (Arm
  C-real's 3 regressions) for uncertain, high-variance upside. Do not implement this as a
  setting.
- **The candidate-pool + scenario-scoring tool (Arm 3) shows real promise (0->2/6 cash) but is
  not a guaranteed upgrade over a single well-structured pick** -- it's a genuinely different,
  higher-effort selection process with its own variance, not a strict dominance over Arm B.
  Worth using, but go in knowing it can pick a worse lineup than a simple stacked build on any
  given slate; the net edge is only visible in aggregate.
- **n=6 slates is small for all of the above.** None of this is statistically proven; it's the
  best real-data read available right now. Keep replaying as more weeks accumulate
  (`scripts/replay_validation.py` and `analysis/classic_diag/replay_arm3.py` are both committed
  and reusable -- add new slates to their `SLATES` dicts as they're logged).

### Open question raised after this analysis, NOT yet resolved: is "select by P(top-10%)" the right criterion at all?
Greg asked directly whether Arm 3's 2 losses-to-the-actual-submission (wk1 afternoon, wk2
afternoon) might be caused by the SELECTION CRITERION itself (ranking candidates by average
P(top-10%)) rather than bad luck. A same-data check supports this: on those exact 2 slates, Arm
B (a plain "maximize projected points with structure" pick, no simulation-based ranking at all)
would have done noticeably BETTER than Arm 3. But it's not a clean sweep either -- on 3 OTHER
slates Arm 3 beat Arm B, including converting a miss to a cash on wk2 main. Net: a real, genuine
3-3 split between "pick by top projection" and "pick by P(top-10%)," not a verdict either way.

This comparison isn't fully clean, though: Arm B wasn't drawn from the SAME candidate pool Arm 3
generated -- it was a separate, single direct solve. **The rigorous version of this test, not yet
done: from the IDENTICAL candidate pool `best_lineup_classic.py` already generates, re-rank and
select by different criteria and grade each** -- at minimum: (a) highest raw projected points in
the pool (isolates "does simulation-based ranking beat just trusting the projections, holding the
candidate-generation process fixed"), and (b) highest `worst_top10` instead of `avg_top10` (the
robustness/worst-case metric the code already computes but never actually uses for selection --
Showdown's session flagged worst-case as the metric that catches "trap" lineups the average
misses). This is cheap to test (no new Monte Carlo needed, `best_lineup_classic.score()`'s
`return_detail=True` already returns the full ranked candidate table with all these columns per
candidate) and would cleanly isolate whether the selection RULE is the problem, independent of
candidate generation or field simulation. **Recommend this as the first thing the next session
does before trusting Arm 3's P(top-10%) selection rule as the final method.**

### Two more tests run after the above (same session, in direct response to follow-up questions)
- **Diversified-batch hit rate** (`analysis/classic_diag/replay_batch.py`): built 10- and
  100-lineup batches per slate with the confirmed settings (stack=2, bring-back, randomization for
  diversity, 50% max exposure) and graded EVERY lineup individually against real results. Hit
  rate: ~28% average across slates at n=10, ~27% at n=100 -- consistent between batch sizes (as
  expected, since both draw from the same underlying edge), and modestly above the field's flat
  25% baseline, matching the earlier single-lineup evidence. **The important finding: the BEST
  lineup within every 100-lineup batch landed at the 98th-99.9th percentile, in all 6 slates.**
  There is a lot of realizable value sitting in a large candidate pool -- the bottleneck is
  entirely about identifying which one in advance, which is exactly the open selection-criterion
  question above, not about generating more candidates.
- **Does a bigger candidate pool make the SCENARIO-SCORER's pick better?** Controlled test: same
  field_n=6000/n_sims=800/seed, only n_candidates varies (20 vs 100),
  `analysis/classic_diag/replay_poolsize.py`. **Answer: no.** Cash count was 1/6 either way; mean
  real percentile across the 6 slates was actually slightly BETTER with 20 candidates (~61%) than
  with 100 (~57%), and on one slate (wk2 afternoon) the 100-candidate pick was dramatically worse
  (28.9% vs 70.2%). Two slates picked the IDENTICAL lineup at both pool sizes (the forced-stack
  candidates already dominate a small pool). **This confirms the batch-hit-rate finding from a
  different angle: every candidate pool already contains a near-perfect lineup (98th-99.9th
  percentile per the batch test above); the bottleneck is that ranking candidates by average
  P(top-10%) from a limited-sample Monte Carlo isn't reliable enough to consistently find it, and
  a bigger pool just gives that unreliability more room to elevate the wrong candidate.** This is
  the same root cause as the open selection-criterion question above, confirmed independently:
  **the priority fix is a better/more reliable selection rule, not a bigger search space or a
  different candidate-generation setting.** Recommend the next session start there (test
  selection by raw projection and by `worst_top10` from the identical candidate pool, per the
  section above) rather than tuning pool size, field size, or sim count further.

## 4. Concrete recommendation for next week's classic slate
1. Turn on `--stack-mode qb --stack-size 2 --bring-back` (or the UI equivalents) for every
   classic build. This is the most confidently-evidenced change from this whole session.
2. Consider TE-in-FLEX case by case depending on that week's actual TE options, not as an
   always-on default yet.
3. Do NOT add a min-total-ownership floor.
4. Optionally, for a slate where you have enough lead time (not a last-minute injury-news
   scramble), run `python analysis/classic_diag/replay_arm3.py` reworked for the LIVE slate (see
   "what's not yet done" below -- it currently only runs on the 6 historical slates) to get a
   scenario-scored candidate ranking rather than relying on a single build. Treat it as one more
   input, not an oracle -- it improved on 4 of 6 historical slates and was worse on 2.

## 5. Flagged but NOT built or tested: the "conviction vs. chalk" idea
Raised by Greg from a real example: this past week, the projection engine showed an unusually
strong signal on Carolina's DST (cheap, top-projected) that conflicted with playing chalk
Bijan Robinson -- the field's chalk pick (Bijan) happened to hit, but the underlying idea is
distinct from anything built this session: **when the model's OWN conviction (a large gap
between its valuation and the field's chalk) is unusually large, that gap-size is itself a
signal worth acting on, independent of ownership-sum rules.** This is different from and
possibly more promising than the population-level "own_sum correlates with cashing" work --
that work may mostly be re-describing "good players tend to be popular" rather than finding an
independent lever, whereas this idea is about spotting SPECIFIC decisions where the model
disagrees sharply with the crowd. Nothing has been built or tested for this yet -- it needs its
own dedicated investigation (start point: the value-gap groundwork already in
`scripts/projection_stack.py`'s engine-minus-salary-predicted analysis, and the DST model's
already-documented real edge in WK2_POSTMORTEM.md). Recommend a future session start here rather
than continuing to tune ownership-floor mechanics, which this session already tested and
rejected.

## 6. What's built, committed, and reusable
- `scripts/classic_field.py` -- validated classic field simulator (median-p95 within 0.1-3.0pts
  on all 6 logged slates, real stack rate reproduced).
- `analysis/classic_diag/best_lineup_classic.py` -- candidate generation + scenario scoring,
  now with a `pick_top()` convenience function (added this session) for getting just the
  top-ranked candidate's player list.
- `scripts/replay_validation.py` -- the 3(4)-arm replay harness (Arm 1/B/C-real/C-est), reusable
  for future settings tests. Read its module docstring and inline comments before changing the
  ownership-floor logic -- the calibration bugs above are easy to reintroduce.
- `analysis/classic_diag/replay_arm3.py` -- runs Arm 3 against the same 6 historical slates.
  **Not yet adapted for a live, upcoming slate** (it assumes real post-lock results exist for
  grading) -- that adaptation (drop the grading step, just report the top-ranked candidate for a
  slate that hasn't happened yet) is a small, real piece of remaining work if you want to use
  this tool for an actual pre-lock decision next week.
- `analysis/classic_diag/top_drivers_classic.py`, `validate_classic_field.py` -- the diagnostic
  and field-validation scripts, both reusable for future weeks.

## 7. Cautions carried forward + new ones
- **This replay used each slate's CURRENT `output/final_projections_*.csv` as a stand-in for
  "as it stood near lock."** Classic wk1/wk2 slates are long past lock and the automated refresh
  skips locked slates, so this should be close, but it was never cross-checked against a git-
  history snapshot from the actual lock timestamp. If replay results ever look surprising, check
  this first.
- **`git pull --rebase` before touching anything** -- automated commits land constantly. All of
  this session's work is committed as of `06c9a74` on `main`; anything after that in this
  conversation (the recalibrated replay arms, `replay_arm3.py`) is NOT YET committed as of this
  handoff being written -- commit it in the next session or before ending this one.
- **Don't re-litigate the ownership-floor idea from scratch** -- it was tested properly (not
  hand-waved) and rejected for a specific, documented reason (Arm C-real's variance). If revisited,
  start from section 3's bug list, not from zero.
