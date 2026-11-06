# Handoff: stud-WR ($6,300+) count-effect projection miscalibration

**Filed:** 2026-10-07, during the weekly check-in session.

**Status: DONE, 2026-10-07 — not a calibration signal, drop as a lever.** The per-slate count
coefficient just measures how far the studs happened to beat our projection vs. the rest of the
flex field that week (stud-premium correlates .94 with the points coefficient, .92 with cash) —
it's the outcome itself, not a learnable pattern. The large Wk2 reading sits on the already-closed
stale Wk1-2 `output/` snapshot (studs projected at 7-12 pts under old files); Wk3/Wk4 are
current-code and cancel out (mean ~0). 72-week 2021-25 history check: stud premium mean -0.74/wk,
SD 2.76, no slate observable explains the swing (all |r|<=0.25: stud count, projection level, game
total, implied team total, slate total, pts/$1k). One real but already-known thread surfaced: a
salary-line correction to the stud-tier projection gap gives better RMSE (4/5 seasons) but not
better ranking or MAE — same skill-player salary-pull finding `analysis/blend_props_refit/
RESULTS.md` §5-6 already graded inconclusive. **Label: logged, real as outcome variance,
unexplained as calibration, too noisy to act on.** No production code touched. Full writeup:
`analysis/stud_wr_count/RESULTS.md` (local, gitignored, FC-derived).

The rest of this doc is kept as the original brief, for reference.

## Does not depend on Week 5
This used existing 5-year history plus 2026 Wk1-4 data already in hand.

## Read this framing note first
Unlike the lineup-ownership and FFC-dependency handoffs (both closed same day, 2026-10-07 — see
`HANDOFF_lineup_level_ownership_2026-10-07.md`, `HANDOFF_ffc_dependency_reduction_2026-10-07.md`),
this is **not** "run a known test against data we have." The straightforward levers for the
WR/stud-gap family (static/adaptive TE or stud-WR budget refits, tail-cut-and-respread, position
dummies in the ownership ridge) are already tried and dead (see Parking Lot / item 10 / item 12 in
`WK4_POSTMORTEM_CHECKLIST.md`). This session is closer to fresh idea generation on a real,
unexplained signal — go in expecting to generate and test new hypotheses, not apply an existing one.

## The signal, in one line
Controlling for our own projection + realized ownership, real cash rate rose sharply with the
count of $6.3k+ WRs rostered on 2026 Wk2-3 fields (+10 to +14 cash pts per stud WR), then reversed
(negative) in Wk4. History (2021-25) says this same count effect faded to ~0/negative after 2023.
Reads like our stud-WR projection is miscalibrated in a way that shows up on some slates and not
others — not a construction lever (the FLEX-WR lineup-level term itself tests ~0 once this count
is controlled for).

## Where this came from / what's already ruled out
- Found while closing the FLEX-WR lineup-level rebuild, 2026-10-06. Full detail:
  `analysis/wk4_construction_review/RESULTS_flex_wr_lineup_level.md` §"2026 real fields" and
  "Bottom line" (local, gitignored, FC-derived).
- Explicitly NOT tested further in that session — belongs with the projection-side WR $7k+
  stud-gap track, flagged to pick up separately. This is that pickup.
- Do not re-litigate: the original "classic PERSISTENT WR $7k+ -6.26" tracker flag (a different,
  now-closed thread) was already root-caused and closed as a stale-snapshot grading artifact, not
  real bias (`WK4_POSTMORTEM_CHECKLIST.md`, "Classic PERSISTENT flags" item). Don't reopen that —
  it's a different claim than this one (that one was "WR $7k+ projections run low across the whole
  season"; this one is "something about rostering MULTIPLE stud WRs together behaves inconsistently
  by week/season," a narrower and still-live claim).
- Cheap/mid RB replacement under-projection (item 10's real finding — RB backups <$7k project ~2pts
  low) is a related but separate, already-understood issue. Don't conflate the two.

## What's explicitly NOT in scope for this session
The TE ownership-budget item's one kept-alive thread (an in-season, 2026-only TE budget refit) is
gated on future data — the postmortem explicitly says "re-test with `step7_inseason_te.py` after
Wk5-6 if the 2026 TE total stays ≥125." It was a noise-level wash on only 3 weeks; starting it now
just repeats an underpowered test. Leave it until Wk5-6 land.

## Concrete starting angle
1. Pull the full 2021-25 history + 2026 Wk1-4 slate-level data already used for the FLEX-WR
   rebuild (same frame as `RESULTS_flex_wr_lineup_level.md`).
2. Characterize the count effect's sign-flip: is Wk4's reversal explained by something observable
   at the slate level (game environment, total points, field size/type, specific players driving
   the count in each direction) rather than being pure noise? Check whether the 2021-23 vs 2024-25
   fade-to-zero in history lines up with any observable shift (rule changes, pricing-model changes,
   roster-construction trends) rather than assuming it's unexplained drift.
3. If a real explanatory variable turns up, test whether adding it to the projection or ownership
   model (not a construction penalty — this is framed as a projection-calibration issue, not a
   lineup-building one) moves held-out accuracy. If nothing explains it, the honest outcome is
   "logged, real, unexplained, too noisy to act on yet" — that's a valid close, don't force a fix.

## Scope note
Budget as a time-boxed exploratory session (Opus agent per the user's standing preference for
heavy analysis) — this is open-ended, so set an explicit wall-clock budget up front rather than
letting it run long chasing leads.

## Session discipline reminder
One topic per session. If this surfaces the TE budget thread, the cheap/mid RB issue, or anything
showdown-specific, park it rather than chasing it inline.
