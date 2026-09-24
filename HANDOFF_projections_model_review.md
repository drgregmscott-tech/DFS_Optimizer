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

## 5. SESSION UPDATE (2026-09-23, continued) -- Lead 1 falsified, real cause found

**Lead 1 is DEFINITIVELY RULED OUT, not just direction-uncertain.** Checked git
history: `props_model.py` and `projection_stack.py` were both committed
2026-09-21 (11:36 and 12:46 local respectively) -- commits `8167025` and
`6457348`. Every build that produced a row in `data/projection_error_log.csv`
predates both:
- wk1 main/early/afternoon (dk+fd): committed 2026-09-13 19:41 (`74f94b9`).
- wk2 main/early/afternoon (dk): committed 2026-09-20 16:31-19:31
  (`full_refresh_dispatch` runs, before either feature existed).
- The one exception, wk2 showdown NYG/LAR (committed 2026-09-21 23:46, after
  both commits), doesn't run the stack anyway -- `stack_active` requires
  `site=="dk" and not showdown`, and Showdown is explicitly excluded.

So neither the props anchor nor the projection stack ran on ANY of the data
behind the measured +3.4 bias. Confirmed directly: `output/final_projections_
dk_dk_classic_wk1_main_13Sep2026.csv` (and every other wk1/wk2 classic file)
has no `engine_projection`/`stack_delta` columns at all -- those only exist in
a build that went through the post-09-21 code path. Don't spend further time
tracing Lead 1's mechanism by hand; it cannot have contributed to this bias,
full stop. (It may still be worth checking independently for CURRENT/future
builds once real data accumulates past 2026-09-21, but that's a different
question from what caused the measured bias.)

**Real cause, found and quantified with real data: `apply_volume_prior()`'s
generic team-sum price-share normalization (`statline_model.py` ~line
1128-1133) lets every floor-salary backup/emergency-string QB on a team's
slate roster siphon a real, non-trivial chunk of the team's price-implied
pass-attempt volume away from the actual starter.**

Mechanism: `volume_prior.share_from_salary()`'s fitted `QB|pass` curve
(`data/volume_prior_dk.json`) does NOT decay to ~0 at the salary floor --
its lowest knot is `(4042.3, 0.224)`, flat-extrapolated below that. A
real DK classic slate lists every rostered QB (starter + backup + often a
3rd/4th emergency arm), each priced near the $4000 floor. Each one gets
assigned share ~0.22-0.46 independently. The starter, near his curve's
ceiling (~0.977), is NOT flagged by the existing `SATURATED_SHARE_THRESHOLD`
special case (decision #20 in the code) -- that only fires when 2+ players
on the same team are BOTH >=0.90, which backups never are. So these shares
just fall through to the generic "team_sum > 1.0 -> divide by team_sum"
normalization (the Session 14.0b fix), which treats each backup's share as
equally informative as the starter's and divides the real volume among all
of them.

Confirmed directly on real slate data, e.g. CIN wk1 main: Joe Burrow
($6900) got `proj_pass_att` 22.13, while Joe Flacco ($4400, third arm)
got 5.20, Josh Johnson ($4000) got 6.48, Sean Clifford ($4000) got 2.74 --
four Bengals QBs splitting one team's ~37 pass attempts, when in reality
only Burrow was ever going to throw. Hand-computing the raw (undiluted)
share/team-volume math for that same slate reproduces this almost exactly
(Burrow ~19.6 vs the pipeline's 22.1 -- same order of magnitude, confirms
the mechanism, not just a plausible story).

**Quantified across all 43 real QB player-weeks (wk1+wk2, DK, `final_
projection > 8`) with real actual attempts from `weekly_stats_2026.parquet`:**
- Current pipeline: `proj_pass_att` sums to 75% of real attempts (992 vs
  1323); mean bias (actual - proj) = **+7.69 attempts**.
- Recomputing the SAME formula but as if each starter were the only QB in
  the price-share pool (no dilution): sums to 103% of real attempts (1361 vs
  1323); mean bias = **-0.88 attempts** -- statistically flat, i.e. the
  systematic component is essentially fully explained by this one mechanism.
  Mean absolute error also drops (9.07 -> 7.99 attempts) -- the residual is
  ordinary week-to-week variance, not a remaining systematic error.

Same pattern confirmed present for RB (rush_att ratio 0.75 vs actual, targets
ratio 0.70) -- e.g. DET wk1: Jahmyr Gibbs ($8000, real bellcow) diluted
against Isiah Pacheco ($5000, `final_projection` = 0.0, i.e. a confirmed
no-game player) and Jabari Small ($4000). Worth noting: RB dilution is NOT
necessarily the identical mechanism -- the RB share curve tops out around
0.775 (well under the 0.90 saturation threshold either way, and RB volume is
legitimately shared among 2+ real contributors in a way QB volume structurally
isn't), and a genuinely-zero-game player like Pacheco still consumed price
share because `apply_volume_prior()` runs on the full pool BEFORE the
`no_real_game_this_week` filter is applied to reconciliation. Confirm
separately before assuming the QB fix (below) automatically fixes RB too.

**This bug was live for every wk1/wk2 build** -- `--volume-prior` was passed
explicitly in both the documented manual command and `refresh_data.yml`'s
automated refresh (confirmed: `Automated refresh: dk_classic_wk2_main_...`
commits used exactly this flag). So per section 0's loop-back requirement:
this is a real, material, CONFIRMED bug (not speculation) in a mechanism that
fed directly into every projection `recommend_lineup.py`'s backtest was
validated against. Flag to the Week 3+ session before trusting the 3/6/0.703
number further -- a fix here would raise real starting-QB (and likely
lead-RB) projections and could shift which Monte Carlo candidates even exist,
per section 0's own warning.

## 7. RB checked, QB fix implemented and rebuild-validated (2026-09-23, continued again)

**RB: same generic mechanism (bench players inflating the team-sum
denominator), but NOT the same fix -- checked and deliberately NOT touched
this session.** Confirmed present, e.g. DET wk1: Jahmyr Gibbs ($8000) diluted
against Isiah Pacheco ($5000, `final_projection`==0.0 that build -- a
confirmed no-game player) and Jabari Small ($4000). But RB is not
winner-take-all the way QB is -- a real committee backfield can legitimately
have 2 real contributors, so "keep only the #1" is the wrong model. Tested
the obvious naive fix (zero any RB whose `final_projection`==0 in the same
build, i.e. confirmed no-game, then leave the existing >1.0-only
normalization as-is) against the same real 2026 wk1+wk2 data used for QB:
it made things WORSE, not better (ratio 0.74 -> 0.68 of real carries, MAE
5.07 -> 5.80 attempts). Root cause of the naive fix failing: the pipeline's
own team-sum normalization (Session 14.0b fix, `statline_model.py` ~line
1128) only ever rescales a share sum DOWN when it exceeds 1.0 -- it
deliberately leaves an under-1.0 sum untouched, because that's the
legitimate "pool doesn't fully cover team volume, real historical
reconciliation fills the gap" case. Zeroing out dead-weight bench RBs pulls
the sum below 1.0 more often than above it, and nothing then rescales the
REMAINING real contributors' shares back UP to compensate -- so the fix
needs to always renormalize among depth-chart-eligible players (not just
clip when over 1.0), which is a materially different, more careful change
than the QB one and deserves its own session. Not implemented. Flagging for
a future session, not doing it opportunistically alongside the QB fix.

## 8. QB fix: implemented, then rebuild-validated against real data -- important correction to the magnitude claim above

Implemented the depth-chart-based `pass_price_share` suppression exactly as
proposed in section 6 -- `apply_volume_prior()` now takes an optional
`depth_chart` param and zeroes `pass_price_share` for any QB the real depth
chart positively lists as not rank 1 (before the saturation/normalization
steps see it); `build_projections_statline.py` now loads the depth chart
once, earlier, and passes it through to both `apply_volume_prior()` and the
existing `apply_confirmed_starter_override()` call. See the code comments at
both sites for the full reasoning (which also explains why a real in-week
promotion is NOT blocked by this -- `apply_confirmed_starter_override()`
recomputes a promoted player's mu straight from his own mu_raw/participation
and never reads price_share).

**Then rebuilt the real wk1_main and wk2_main slates with the fix
(`--season 2025 --week 23` and `--season 2026 --week 2` respectively, same
flags the live pipeline uses) to check the ACTUAL effect against real data,
rather than trusting the offline hand-calculation in section 6. That
hand-calculation turned out to be an oversimplification -- it implicitly
assumed every QB gets the pipeline's cold-start price weight (`w=1.0`), but
`cold_start_weight()`'s taper hits exactly 0 at `games_played >= 
COLD_START_MAX_GAMES = 4.0`. The two real weeks land on opposite sides of
that cliff:**

- **Week 2 (`games_played`=1 for essentially every QB, since only 1 real
  2026-season game exists as history -> `w`≈0.6-0.8): the fix works as
  designed and materially large.** Real rebuild, CIN: Joe Burrow's
  `proj_pass_att` went 22.28 -> 35.02 (real week-2 attempts: 31). Across all
  20 real wk2 meaningful QB player-weeks: mean bias flipped from **+8.0**
  (under-projecting) to **-3.3** (now over-projecting, but smaller in
  magnitude), and MAE improved **9.05 -> 7.27 attempts** -- a real, net
  accuracy gain, but it overshoots into a new, smaller over-projection
  tendency rather than landing at zero. Worth a closer look separately
  (likely the `with_history` team-volume regression itself running a
  little hot off one noisy real game, not a new problem this fix
  introduced -- the same team_pred value was already being computed the
  same way before this fix; the fix just routes more of it to the right
  player instead of splitting it across players who were never going to
  see the field).
- **Week 1 (`games_played` 5-17 for nearly every real QB in the meaningful
  population, using full 2025-season history as the lookback -> `w`=0
  EXACTLY, since taper clips at `games_played`=4): the fix has ~no effect.**
  Real rebuild, CIN: Joe Burrow's `proj_pass_att` moved 22.13 -> 21.24 (a
  rounding-level change from reconciliation, not the fix doing real work).
  Confirmed directly: at `w=0`, `blend_volume()` ignores `price_volume`
  entirely (`mu = 1.0*history + 0.0*price`), so suppressing a backup's
  price_share cannot touch an established starter's projection at all.

**Correction to section 6's headline claim: the price-share dilution bug is
real and the fix is a genuine, validated improvement, but it does NOT
explain the WEEK 1 portion of the QB bias** (which was actually the larger
half of the original sample -- wk1 n=317 meaningful players vs wk2 n=153).
Week 1's QB under-projection must trace to something in the
history-side of the pipeline instead (own 2025-season `mu_raw` /
`build_usage()`'s recency-weighted average, `participation_effective`, or
the role-change block) -- NOT YET INVESTIGATED. That's the natural next
thread for this session or a follow-up: pull real week-1 QB `mu_raw`/
`games_played`/`participation_effective` values and trace why an
established starter's own-history-based volume estimate comes in low
against his real 2026 attempts, the same rigor standard applied above.

**Net assessment:** kept the fix (real, validated, non-regressive
improvement for the low-games-played population it actually reaches: true
rookies and every week-2-style single-game-history slate), but it should
NOT be read as "the QB bias is fixed" -- roughly half the original sample
(week 1) has an as-yet-unidentified separate cause. Per section 0's
loop-back requirement: still flag to the Week 3+ session before trusting the
3/6/0.703 backtest number, but with this correction -- the fix's real-world
impact on that backtest is concentrated in low-games-played situations
(rookies, injury-return weeks), not a blanket lift to every QB projection.

## 9. Full pre-Week-3 gap assessment (2026-09-23, continued a third time) -- root cause found, MAJOR fix implemented and validated

Greg asked for a full assessment of remaining gaps before generating real Week
3 lineups: address anything major, flag anything minor. This closes out
section 8's open thread (week 1's QB bias, unexplained by the price-share fix
alone) and turns out to explain almost ALL of the remaining bias, at every
position, not just QB.

**Root cause (MAJOR, confirmed and fixed): `reconcile_team_shares()`'s
`raw_sum` was never made `hist_team`-aware, even though this exact function
already fixed the identical problem for its SHARE NUMERATOR two sessions ago
(Session 15.2, the `full_usage`/`hist_team` mechanism cited in this
function's own docstring).** Traced directly from the still-open week-1
Burrow case: his own `pass_mu_raw` (from `build_usage()`) was **35.36** --
already an accurate, undiluted estimate (his real week-1 2026 attempts: 35)
-- yet his FINAL `proj_pass_att` came out at 22.13. `output/statline_
reconcile_dk_dk_classic_wk1_main_13Sep2026.csv` showed why: CIN's "pass"
`raw_sum` was 58.6 against a real target of 36.6, forcing `scale`=0.624
across every CIN quarterback. `raw_sum` sums `pass_mu` for every player
CURRENTLY rostered on CIN in the pool -- and Josh Johnson (CIN's real QB3,
priced at the salary floor) has `hist_team`=WAS: he genuinely played for
Washington last season, not Cincinnati. His own real ~11.4-attempt
Washington-based mu got summed into CIN's pool anyway, inflating `raw_sum`
and cutting every real Bengal QB's mu by 38% to compensate for a phantom
teammate's volume that was never Cincinnati's to begin with.

**Confirmed this is not QB-specific or rare -- it's league-wide and hits
every position with a real bench.** Scanning the SAME slate's `rush`
component (RB) found scale factors of **0.53-0.75x on nearly every team**
(MIA, BUF, BAL, CLE, CIN, IND, PHI, LAC, LV, TB, MIN, PIT, ...) -- RB isn't
winner-take-all like QB, so instead of one dramatic case it's a broad,
small-per-team drag from every team's real bench backs (and a smaller,
harder-to-fully-close remainder from TRUE zero-history bench players still
drawing a nonzero PRICE-implied share at the salary floor -- see the
"what's NOT fixed" note below). Matches the earlier finding that RB's bias
was concentrated in the `games_played`>=5 (established-player) bucket
(mean +6.27, median +5.18, n=82) rather than the cold-start bucket -- exactly
where the price-share-only QB fix (section 8) couldn't reach, and exactly
where this reconciliation bug operates regardless of `games_played`.

**Fix implemented in two parts, both in `statline_model.py`:**
1. `apply_volume_prior()`: extended the section-8 QB depth-chart fix to also
   zero `pass_mu` (not just `pass_price_share`) for a depth-chart-confirmed
   non-#1 QB, applied at the very end of the function (after the role-change
   recompute and cold-start blend both run, so nothing inside the function
   can silently undo it the way happened the first time this was tried).
2. `reconcile_team_shares()`: `raw_sum` now excludes a player's own `mu` from
   the sum when his `hist_team` doesn't match the team being reconciled (a
   true no-history player, `hist_team` NaN, is kept -- his own mu is ~0
   anyway, so excluding him would never matter and NOT excluding him is the
   safer default). This is position/component-general -- not a QB special
   case -- and reuses the exact `hist_team` column and reasoning
   `_pool_share()`'s docstring already established for the share numerator,
   just extended to the denominator that actually drives `scale`. The
   `scale` factor this produces is still applied to EVERY player in the
   team's pool afterward, unchanged from before -- a misattributed player's
   own final projection still reflects his new team's context, exactly like
   the existing numerator/denominator split already does for `pool_share`.

**Rebuild-validated against real 2026 wk1+wk2 outcomes, all 6 real DK classic
slates (`data/projection_error_log.csv`, `final_projection > 8`, deduped to
one row per real player-week), points-level bias (`actual_fpts -
final_projection`):**

| Position | n | Bias BEFORE | Bias AFTER | MAE before -> after |
|---|---|---|---|---|
| QB | 45 | **+4.78** | **-0.09** | 8.25 -> 8.78 |
| RB | 44 | **+3.87** | **+0.55** | 7.48 -> 7.88 |
| WR | 52 | **+4.48** | **+1.15** | 8.09 -> 7.98 |
| TE | 17 | -0.31 | -1.71 | 5.16 -> 4.52 |
| **ALL (incl. DST/K)** | **183** | **+3.24** | **+0.11** | 7.36 -> 7.54 |

The original section-1 headline finding -- the model under-projects
meaningful players by +3.4 pts on average -- is **essentially eliminated**
(+3.24 -> +0.11 on the DK subset checked here; the original full DK+FD
measurement was +3.37). MAE is flat to slightly worse (expected: MAE also
captures real week-to-week variance no volume fix can touch; BIAS -- the
systematic, fixable part -- is what collapsed). TE flipped from slightly
under to slightly over by about the same small magnitude (n=17, not a
concern). Verified no build failures/crashes across DK classic (all 6
wk1/wk2 slates), FD classic (wk1 main), and DK Showdown (wk1) -- the fix
doesn't break anything downstream.

**Rebuild artifacts were NOT committed** -- these test rebuilds mixed in the
NOW-current `projection_stack.py`/`props_model.py` code (which didn't exist
at original build time, see section 5) purely as a side effect of using the
current `build_projections_statline.py`; keeping them would corrupt the
historical record those files represent. All `output/*.csv` changes were
reverted with `git checkout` after each validation pass -- only the two
`scripts/*.py` fixes remain in the working tree.

**What's NOT fully fixed, flagged for awareness, not blocking:**
- **RB/WR residual (~+0.5 to +1.2 pts) not from this bug.** Traced to a
  DIFFERENT, already-known mechanism from section 7: RB/WR's `share_from_
  salary()` curves (unlike QB's) don't need to decay to near-zero at the
  salary floor to behave reasonably for a genuine committee -- but a true
  zero-history bench player (no `hist_team` at all, so untouched by this
  session's fix) still draws a real, nonzero PRICE-implied share at the
  floor (confirmed on BUF: `raw_sum` barely moved after this fix, 46.29 ->
  44.96, because all 3 real Bills backs had `hist_team`=BUF already -- the
  remaining pool inflation is from Frank Gore Jr./Ian Wheeler/Jackson
  Acker/Ben VanSumeren, all true zero-history depth players each drawing a
  small nonzero price share). Section 7 already concluded RB needs a
  dedicated, more careful fix (not "keep only rank 1" -- committees are
  real) and that conclusion stands; this session's fix closed the bigger,
  cleaner, cross-team-history piece of the RB/WR gap, not the remaining
  floor-share piece. NOT attempted this session: it would mean re-touching
  the FITTED `share_from_salary()` curve artifacts
  (`data/volume_prior_dk.json`/`_fd.json`, fit by `fit_volume_prior.py` on
  2014-2021 data) rather than pipeline logic, which is a bigger, riskier
  change deserving its own validation pass, not a same-session add-on.
- **Known, low-probability edge case of this session's fix:** a genuine
  starter-level trade/signing (not a bench player -- the actual QB1/RB1
  moving teams) would have his own `hist_team`-based mu excluded from HIS
  OWN new team's `raw_sum` too, which could under-drive that team's
  `scale` if he's the sole real contributor. In practice this should
  already be caught upstream by `apply_confirmed_starter_override()`/
  `apply_depth_chart_usage_prior()` (both run before reconciliation and
  already give a real, current-depth-chart-confirmed starter full credit
  regardless of which team his own history came from), so it's an
  acknowledged tradeoff, not a fix left half-done -- consistent with this
  same function's own documented stance on other reconciliation edge cases
  (see its SEA-2021-week-10 example already in the docstring).
- **`props_model.py`/`projection_stack.py` (section 5): code-reviewed this
  session, no logic bugs found, but still genuinely untested against real
  live market data end-to-end** (props needs a fresh near-kickoff odds pull
  this session had no way to fetch). `projection_stack.py`'s own docstring
  cites a real backtest (forecast R2 wk1 0.331->0.426, wk2 0.374->0.420);
  `props_model.py` has no equivalent backtest citation, only the WK2_
  POSTMORTEM motivation for building it. Recommendation: for Week 3, watch
  the "Props anchor: adjusted N player(s)" and "Projection stack: adjusted
  N player(s)" build log lines and sanity-check a few adjustted players by
  hand before trusting them blindly, same as any other first real-money use
  of a new mechanism.
- **DST (-0.52 mean bias) and TE (-1.71) are both small, roughly
  pre-existing, and not obviously connected to any mechanism this session
  touched** -- not investigated further, not blocking.

**Loop-back requirement (section 0), updated once more:** this is now a much
bigger correction to flag than section 8's QB-only, low-games-played-only
fix. The projection model `recommend_lineup.py`'s 3/6/0.703 backtest was
validated against carries a real, broad, now-fixed under-projection of every
skill position's established players. Re-validating that backtest after this
fix is more clearly warranted than it was after section 8's narrower fix --
this could plausibly change which Monte Carlo candidates the selection rule
even sees, not just their exact point values.

## 10. What NOT to do

- Don't touch `analysis/classic_diag/*.py` or `scripts/recommend_lineup.py` in
  this session — those are the Week 3+ lineup-system deliverables, out of scope
  here. If a projection fix affects them, flag it per section 0, don't silently
  patch across sessions.
- Don't wait for more weeks of real data before starting — Greg's explicit call
  this session was to review code for bugs/gaps NOW, in parallel with more data
  accumulating, not sequentially after.

## 10. HAND-IN FROM THE OWNERSHIP SESSION (2026-09-24) -- re-check of the section-9 fix, and the guard that is still OPEN

Full write-up: `analysis/proj_recheck/notes.md` (numbers below are from it; 254 player-weeks, projection>8, 6 DK classic slates, leak-free rebuilds). Companion: `HANDOFF_ownership_model_review.md` section 7 (ownership outcomes).

**Verdict: keep the reconcile fix, but it has a bug of its own that must be guarded before more slates are built.**
- Bias fixed (-3.37 -> -0.40 pts) but ranking did NOT improve: within-position rank corr .226 -> .201; actual points of the projected top-N fell 16.06 -> 14.79 (paired CI -2.59..-0.10). MAE 6.41 -> 6.83.
- **The bug:** `reconcile_team_shares()` excludes a player whose `hist_team` != current team from `raw_sum`, but still applies the team `scale` to him. When the STARTING QB is the one who moved, `raw_sum` is only his tiny backups' volume, so `scale` blows up and the starter is inflated. Wk1 rebuild: Cousins (LV) pass att 134 / 62 pts (actual 15.8), Murray (MIN) 135 / 57 (actual 0.6), Geno Smith (NYJ) 119 / 52.5 (actual 9.3), Willis (MIA) 60 / 33 (actual 17.7). Without those four, the fix clearly helps QB (wk1 QB R2 .27 -> .37, .50 with stack).
- **Recommended guard (NOT implemented -- Greg moved it to this chat):** scale only players counted in `raw_sum` (or cap a moved starter's volume / cap `scale`, e.g. <=~1.5), plus a fail-loud check on any player projecting pass attempts > ~50. Validate on the wk1 cases above AND on the live wk3 MIN case below.
- **LIVE WK3 CASE -- MIN passing:** wk3 main reconcile log: `MIN/pass raw_sum 10.92, target 30.13, scale 2.76x`; result: Kyler Murray ($5,100, hist_team ARI, 1 game) 13.7 pass att / 9.5 pts, Max Brosmer ($4,000, 0 games) 16.3 att / 7.0 pts, Wentz 0, McCarthy 0. **Murray has been cleared and announced as MIN's starter this weekend (Greg, 2026-09-24)** -- so 9.5 pts / 13.7 att is a real mis-projection, same mechanism. SEA/pass 1.72x looks fine (Darnold 15.6).
- **Shipped-lineup drop explained:** old 3/6, 0.703 -> fixed 1/6, 0.583; ~2/3 of that drop is this bug (shipped rule picked Cousins/Geno/Murray); with those four QBs reset 2/6, 0.660; rest is noise (5% projection noise alone moves a slate ~0.2 percentile). (The recommend_lineup feature was since removed from the repo.)
- **Projection stack:** roughly neutral-to-helpful; the "-28 pt" moves were the stack's 0.5x floor limiting the blown-up QBs. Keep.
- **Leaks in the old-vs-fixed comparison** slightly favor the fixed projections: depth_charts_current.parquet is a 9/23 snapshot; status files were pulled after kickoff; played-week zeroing must be disabled for wk2+ rebuilds (a switch does not exist yet -- add one for backtests).
- **Watch each week:** any QB with proj_pass_att > 50 or a team `scale` > ~1.5 in `output/statline_reconcile_*.csv`; offseason/in-season movers are the exposure.

**Merging the two workstreams:** ownership features that depend on projections (`final_projection`, `sigma`, `l_exp` from the optimizer) inherit any projection blow-up, so fix the guard first, then rebuild slates and refit both ownership artifacts (`data/ownership_model_dk.json`, `_ffc.json`) -- and refit again after wk3 real ownership is logged (Stage 6; `log_ownership.py` now refuses FLEX-less totals).
