# Handoff: projection-model accuracy review (2026-09-23)

Split out from the Week 3+ lineup-system session (`HANDOFF_week3_lineup_system.md`)
at Greg's request, to run as its own session rather than compete for attention with
that build. Greg's framing: keep reviewing the projection and ownership models for
bugs/gaps/logical-improvement opportunities NOW, in parallel, rather than waiting
for more weeks of real data to accumulate — there's plenty to find via code review
alone. This file covers projections; `HANDOFF_ownership_model_review.md` covers
ownership as a separate session.

## 0. READ THIS FIRST — the loop-back requirement

**If this session finds and fixes a real, material bug in the projection pipeline,
do not just ship the fix and move on.** Loop back to `HANDOFF_week3_lineup_system.md`
and work out what it means for that session's results, specifically:

- `recommend_lineup.py`'s shipped method (`worst_top25_realstack`, 3/6 cash, 0.703
  mean percentile) was validated against the CURRENT projection model — including
  whatever bias this session finds. A materially different projection model could
  change which candidates the Monte Carlo pool even contains, let alone which one
  wins. The 3/6/0.703 number is not guaranteed to hold after a real projection fix
  — it needs re-validation on the same 6 logged slates, not an assumption that a
  "better" model can only help.
- Every other number in that investigation (chalk-anchor+pivot's 4/6/0.819, the
  three live-ownership-substitution rejections, the selection-criteria comparisons)
  used the current projection model as an input. A big enough projection change
  could shift which SELECTION RULE is actually best, not just how good the numbers
  look.
- Don't silently re-run everything either — flag the specific fix, its expected
  direction/magnitude of impact, and let a human (Greg) decide what's worth
  re-validating before real money is on it again.

## 1. The measured problem (this session's finding, real data, not a guess)

Checked `data/projection_error_log.csv` (2,709 real logged rows, 2026 Weeks 1-2)
restricted to "meaningful" players — `final_projection > 8`, i.e. the ones lineup
construction decisions actually turn on, not bench scraps:

- Correlation between `final_projection` and `actual_fpts`: **0.39** (weak).
- MAE: **7.5 points**.
- **Systematic bias: +3.4 points, confirmed direction (2026-09-23, verified
  directly against the CSV, not inferred): `actual_fpts - final_projection`
  averages +3.37 across this population (mean final_projection 11.45, mean
  actual_fpts 14.82) — the model UNDER-projects meaningful players on average,
  not over-projects.** (An earlier pass this session stated the opposite
  direction to Greg in conversation -- that was wrong and is corrected here.)
  Consistent across both weeks separately (wk1 n=317, MAE 8.05, corr 0.394;
  wk2 n=153, MAE 6.48, corr 0.381) -- not a one-week fluke, and consistent with
  `WK2_POSTMORTEM.md`'s earlier "stud under-projection" finding (same
  direction, independent source).

A systematic bias (not just noise) usually traces to something concrete and
fixable, which is why this is worth a real session rather than "more data will
sort it out."

## 2. Leads already found (by a background review agent this session, unverified beyond code-reading — confirm before acting)

**Lead 1 (direction needs re-examination in light of section 1's correction —
DON'T assume this explains the bias without re-checking the math): props-anchor
+ projection-stack may be double-counting the same signal.**
`scripts/build_projections_statline.py` runs `_apply_props_anchor()` (props
weight default 0.5, `props_model.py`) and then `_apply_projection_stack()`
(`projection_stack.py`) on the same players. For a props-matched ("meaningful")
player, `projection_stack.combine()` (line ~140) computes
`final = E_props + PROPS_DELTA_SHARE(0.5) * (S - E)`, where `S` is a ridge
regression fit to predict actual points from `E` (engine-only, no props) +
salary + last-4-game usage. `projection_stack.py`'s own docstring says the whole
reason the stack exists is that "sportsbooks price role, injuries, game script...
in ways our recency-weighted history cannot" — the EXACT same signal source the
props anchor already uses. So for a well-covered player, `E_props` has already
moved toward the market/role signal, and then 50% of a correction CALIBRATED
against engine-only projections gets layered on top of an input that's no longer
engine-only. `PROPS_DELTA_SHARE = 0.5` is flagged in the code itself as "an
assumption to re-test with real props data" (line ~31-32) — never validated with
both mechanisms live simultaneously.

**IMPORTANT CAVEAT added after re-verifying section 1's direction**: this lead
was originally framed as "double-counting inflates projections too high" — that
doesn't fit the CONFIRMED direction (the model still under-projects by 3.4 pts
on net, even with both corrections applied). A double-application of an
UPWARD-pushing correction being net-insufficient isn't a contradiction on its
own (e.g. if the corrections are individually too small, or don't reach enough
of the under-projected population, or interact with `E`'s own re-use in a way
that dampens rather than compounds) — but it means the mechanism can't be
assumed without actually tracing the math for a few real under-projected
players (start with the two biggest misses already in hand: Jahmyr Gibbs,
wk1_main, 22.5 proj vs 37.6 actual; the wk1_main row with 14.1 proj vs 31.2
actual) through both `_apply_props_anchor()` and `_apply_projection_stack()`
by hand to see where the correction falls short. Lines up directionally with
`WK2_POSTMORTEM.md`'s earlier "stud under-projection" finding either way —
worth investigating, just don't assume the specific double-counting mechanism
first proposed here is confirmed.

**Lead 2 (lower confidence, unconfirmed): one-directional participation
"restoration" boosts with no symmetric downward correction.**
`apply_confirmed_starter_override`, `apply_depth_chart_usage_prior`, and the
volume-prior's role-change block (`statline_model.py`, called from
`build_projections_statline.py` lines ~594-634) are all boost-oriented for
players under-credited by raw participation history — no equally-aggressive
downward counterpart exists for backups being over-credited.
`WK2_POSTMORTEM.md` (line ~71) checked this against CORRELATION (each move
&lt;=0.007), not against LEVEL/bias — a set of boosts could leave rank-order
nearly unchanged while still shifting the mean. Not confirmed as a real cause,
worth a targeted bias-only ablation, not a rebuild.

**No smoking gun found** in `projections_matchup.py`/`projections_baseline.py` —
their vegas/matchup factors are simple multiplicative percentiles with no obvious
one-sided skew, and the props devig math (`power_devig`, TD budget scaling) looks
deliberately conservative and self-documented as bias-aware already.

## 3. Concrete first move for this session

**Direction is confirmed (section 1) — the model under-projects meaningful
players by 3.4 pts net.** Given Lead 1's mechanism doesn't obviously fit that
direction (see its caveat above), start with the by-hand trace suggested there
(pick 2-3 real large-miss players, walk them through
`_apply_props_anchor()`/`_apply_projection_stack()` step by step) BEFORE running
a broad ablation sweep — cheaper to falsify or confirm the specific mechanism on
a few real examples than to rerun the whole pipeline with a flag flipped and
guess at why the number moved.

**Ablation test, once a specific mechanism is suspected**: rerun the projection
pipeline with that specific correction reduced or off (`--props-weight 0`, or an
adjusted `PROPS_DELTA_SHARE`) against the historically logged slates and check
whether the bias actually shrinks and in the expected direction. Don't skip
straight to changing a constant without confirming the mechanism first via the
by-hand trace above — same rigor standard the rest of this project holds (see
`feedback_rigor_over_reassurance_in_construction_testing.md`).

## 4. Files to read (in this priority order)

- `scripts/build_projections_statline.py` — the LIVE pipeline's main entry point
  (the automated refresh calls it with `--volume-prior --sigma-recalibration
  --dst-model distributional`). Read fully.
- `scripts/props_model.py`, `scripts/projection_stack.py`,
  `scripts/fit_projection_stack.py` — trace exactly how `final_projection` gets
  assembled: what gets summed/multiplied, any boosts, any shrinkage, any
  double-application risk.
- `scripts/projections_baseline.py`, `scripts/projections_matchup.py` — lower
  priority, already checked once with no clear lead found.
- `data/projection_error_log.csv` — the ground truth to validate any hypothesis
  against. Don't fix based on code-reading alone; confirm against this file.
- `WK2_POSTMORTEM.md` — has the earlier "stud under-projection" finding Lead 1
  connects to.

## 5. What NOT to do

- Don't touch `analysis/classic_diag/*.py` or `scripts/recommend_lineup.py` in
  this session — those are the Week 3+ lineup-system deliverables, out of scope
  here. If a projection fix affects them, flag it per section 0, don't silently
  patch across sessions.
- Don't wait for more weeks of real data before starting — Greg's explicit call
  this session was to review code for bugs/gaps NOW, in parallel with more data
  accumulating, not sequentially after.
