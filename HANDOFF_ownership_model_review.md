# Handoff: ownership-model accuracy review (2026-09-23)

Split out from the Week 3+ lineup-system session (`HANDOFF_week3_lineup_system.md`)
at Greg's request, to run as its own session rather than compete for attention with
that build. Companion to `HANDOFF_projections_model_review.md` — same request, same
day, different model. Run these as separate sessions, not combined.

## 0. READ THIS FIRST — the loop-back requirement

**If this session finds and fixes a real, material bug in the ownership pipeline,
do not just ship the fix and move on.** Loop back to `HANDOFF_week3_lineup_system.md`
and work out what it means for that session's results, specifically:

- Three separate tests this session (`analysis/classic_diag/pivot_off_chalk_live.py`,
  `_v2`, `_v3`) concluded that substituting the model's `estimated_ownership_pct`
  for real post-lock ownership makes the chalk-anchor + ownership-driven-pivot
  method (validated at 4/6 cash, 0.819 mean percentile WITH real ownership) add
  ZERO value live, across all 6 logged slates, regardless of anchor construction
  or pivot eligibility threshold. **That conclusion was reached using the CURRENT
  ownership model — the one this session may find bugs in.** If this session
  fixes a real accuracy problem, THAT CONCLUSION NEEDS RE-TESTING, not just
  filed away as settled. It's entirely possible a fixed ownership model makes
  the stronger pivot method viable live after all — that was the whole point of
  shipping the ownership-independent `worst_top25_realstack` fallback
  (`scripts/recommend_lineup.py`) in the meantime, not a permanent verdict.
- `recommend_lineup.py`'s currently shipped method does NOT use ownership at all
  (deliberately, per the point above) — it is NOT directly invalidated by an
  ownership-model fix. But the "which method is actually best" landscape should
  be reassessed once ownership accuracy improves, since the stronger method
  might become usable.

## 1. The measured problem (this session's finding, real data)

Checked `data/ownership_actual_log.csv` (1,391 real logged rows, comparing the
model's `estimated_ownership_pct_at_lock` against real post-lock
`actual_ownership_pct`, 2026 Weeks 1-2) restricted to "meaningful" rows (either
side > 5% — i.e. real chalk-tier plays, not irrelevant punts):

- Correlation: **0.60**.
- MAE: **7.6 points**.
- Overall (unrestricted, all 1,391 rows): correlation 0.74, MAE 3.26 — the
  accuracy is much worse specifically in the tier that actually matters for
  construction decisions (chalk anchor selection, pivot eligibility).

## 2. The lead already found (medium-high confidence, from a background review agent this session)

**Fixed-budget softmax structurally squeezes out real low-owned options.**
`scripts/ownership_heuristic.py`'s `compute_estimated_ownership()` forces each
position group's TOTAL estimated ownership to sum exactly to a roster-slot-
derived budget (decision #5 in that file), regardless of how many genuinely
good options actually exist at that position on a given slate. The softmax
temperature (T=11-17 range, the file's own comments call this largely unfit)
isn't sharp enough to let a true standout absorb an outsized share the way real
ownership does -- so when a slate has 2-4 similarly-projected top plays at a
position, they all get pushed into similar double-digit ownership together, and
the fixed-budget conservation then squeezes the genuine 2nd/3rd-tier plays UP
too, killing the real long tail.

Verified directly against real `wk1_afternoon` data: Barkley (30%), Hampton
(86%), Jeanty (10.6%) all cluster high together in the model's estimate. The
module's own comments (lines ~398-406) already admit the fit "does not fully
close the 'top chalk plays are under-owned' gap" — meaning real top plays get
even MORE real-world share than the model gives them, so the model's conserved
budget necessarily spills the difference onto 2nd/3rd-tier alternatives that in
reality would be far less owned.

**This directly explains a concrete symptom found in the SAME session**: on
`wk1_afternoon`, when testing the live chalk-anchor+pivot method, ZERO of the
anchor's 7 swappable RB/WR/TE slots had ANY same-position alternative under 10%
estimated ownership — the model's ownership distribution had no real long-tail
leverage plays to offer AT ALL on that slate, under its own estimates. If the
tail-squeezing bug above is real, this is exactly the failure mode it would
produce.

## 3. Open question: is this a bug, or a correct reflection of a genuinely low-differentiation slate?

The background review flagged this as ambiguous and worth checking against MORE
real slates before treating it as fixable — `wk1_afternoon` alone isn't enough
to be sure the model is wrong rather than correctly describing a slate that
truly had little real ownership spread at the top. Check this first, across all
9 slates in `data/ownership_actual_log.csv` (not just the one flagged this
session), before assuming the fix direction.

## 4. Concrete first move for this session

1. Re-run the tail-sparsity check (a slate's number of "genuine sub-10% same-
   position alternatives available") across ALL logged slates, not just
   `wk1_afternoon`, to see how common/severe this actually is.
2. If confirmed as a real, common gap: consider whether the softmax temperature
   should be sharper (let a true standout absorb more relative share) --
   but preserve the REAL constraint that total estimated ownership per position
   group should still sum to ~100% of that slot's real-world budget. Don't just
   remove budget conservation; that constraint itself is legitimate, only how
   sharply share concentrates at the top is in question.
3. Validate any fix against `data/ownership_actual_log.csv` directly (MAE/
   correlation on the meaningful-ownership cut, section 1's own numbers) before
   calling it done -- same "validate against real data, not just code-reading
   intuition" standard as the projections handoff.

## 5. Files to read

- `scripts/ownership_heuristic.py` -- full read. Focus on `compute_chalk_scores()`,
  `compute_estimated_ownership()`, and the softmax temperature constants (search
  for `OWNERSHIP_SOFTMAX_TEMPERATURE` and decision #5's comments).
- `data/ownership_actual_log.csv` -- the ground truth for validating any fix.
- `HANDOFF_dfs_army_variables.md` / `HANDOFF_week3_lineup_system.md` -- background
  on why ownership accuracy matters so much right now (it's the identified
  bottleneck on the stronger, currently-shelved chalk-anchor+pivot method).

## 6. What NOT to do

- Don't touch `analysis/classic_diag/*.py` or `scripts/recommend_lineup.py` in
  this session -- Week 3+ lineup-system deliverables, out of scope here. Flag
  impact per section 0 instead of silently patching across sessions.
- Don't wait for more weeks of real data before starting -- same reasoning as
  the projections handoff, Greg's explicit call this session.
