# Handoff: DFS Army/CashKeg strategy variables (2026-09-22)

Written mid-session at Greg's request to move a strategy-brainstorm thread into its own
session, so it doesn't compete for attention with the classic-construction replay work
already in flight (`HANDOFF_classic_construction_replay.md`). Read that file too --
this one assumes it as background and does not repeat it.

## 0. READ THIS FIRST: the actual goal, restated by Greg mid-session

**The goal is cashing a real SE3max lineup next week (Week 3), not a season-long research
program.** Greg was explicit about this after seeing the variable-testing plan below take
shape: "we gotta reality check that we still need to come up with some way of cashing this
next week. that's the main goal... we may not get it but we have to be closer, by a lot,
than we were last week." Do not let the methodologically-clean multi-week plan in section 4
become the whole session -- it's good science, but it will NOT by itself produce a
Week 3 recommendation on its own timeline (real-slate data grows ~1-3 slates/week, so a
proper one-at-a-time test campaign across 5 variables is realistically weeks, not days).

**Before spending time on this file's variable-testing plan, check what the OTHER thread
already produced.** `HANDOFF_classic_construction_replay.md` section 0 has a real-structure
stack-restricted selection-criteria test (`analysis/classic_diag/replay_selection_criteria.py`,
`avg_top25_realstack`/`worst_top25_realstack` columns) that was running in the background
when this file was written and had NOT yet reported back. Its predecessor
(origin-based `*_stackonly`) already hit 4/6 cash (mean pctile 0.709, up from 2/6 baseline)
by targeting the real SE3max cash line (P(top-25%), not P(top-10%)) and restricting
candidate selection to actually-correlated lineups. If the real-structure fix held up or
improved on that, **that may already be the "closer by a lot" answer for Week 3** --
check it before starting fresh on the variables below. Don't duplicate effort.

## 1. Where this thread came from

Greg has ~3 years in DFS Army (owner: Geek) plus learning from a player called CashKeg,
predating this project. Mid-session, after a round of general web research on NFL DFS cash
vs. GPP construction (sources and findings in section 2), Greg pushed back that he wanted to
brainstorm from that personal background specifically, not just generic web strategy content
or the project's own internal replay data. His points are in section 3.

## 2. External web research already done this session (for context, don't re-run)

Web searches (`WebSearch` tool) covered: NFL DFS cash game construction, single-entry cash
floor-player strategy, chalk/ownership fade timing, 50/50 stacking correlation, contest
payout structures (top-25%-line vs. true 50/50 vs. GPP), FLEX RB-vs-TE strategy, and DST
ownership-trap strategy. Key findings, with sources:

- **SE3max sits structurally between a true 50/50 (top ~50% cash, pure floor, minimal
  stacking) and a GPP (small top slice, max ceiling, heavy leverage)** -- it's a min-cash
  tournament format, not a true cash game, which matters for how much of the "cash game"
  advice below even applies.
- **Real tension #1 (not resolved by web research alone)**: generic sources say "stacking
  wins GPPs, not cash" and that correlation is a cash-game liability (wider outcome range on
  a bar-clearing format). This is the opposite of this project's own most-confirmed finding
  (QB+2+bring-back). Likely reconciliation: the sources are describing *extreme* stacks in
  *true* 50/50s; the project's own data already shows stack=2 is the sweet spot and stack=3
  adds nothing (1.11x vs 1.10x lift) -- i.e. "light stack, not a mega-stack" may satisfy both
  views. Not confirmed, just plausible.
- **Real tension #2, RESOLVED by Greg's DFS Army background (section 3)**: generic sources
  say cash-game FLEX should be RB (stable touches, TD-independent), directly opposite the
  project's own twice-confirmed TE-in-FLEX finding (population lift 1.18x; within-batch
  29.9% vs 19.6% cash rate). Greg's explanation: DK is full-PPR, so a real target hog gets
  floor from receptions, not touchdowns -- the generic "TE = TD-dependent landmine" critique
  is a FanDuel-shaped argument misapplied to DK. This reframes the variable from "TE vs RB"
  to "usage/target-share, of which position is just a proxy" -- see V4 in section 4.
- **DST**: matches the project's own finding in spirit (avoid the popular "safe" DST,
  target a bad opposing offense) but frames it as salary/value efficiency ("if two DSTs face
  similarly bad offenses and one's way cheaper, take the cheap one") rather than a pure
  ownership-percentage rule -- a related but distinct angle.
- **New, unimplemented idea surfaced by web research**: never roster the DST directly facing
  your own stacked QB (obvious negative correlation) -- a cheap hard constraint, not
  currently enforced anywhere in the optimizer as far as this session found.
- Full source list: DFS Hub, Fantasy Alarm, Footballguys, Stokastic (multiple articles),
  RotoWire, TheScore, Fantasy Team Advisors, The Fantasy Footballers -- ask Greg or re-run
  the searches if the exact URLs are needed again.

## 3. Greg's DFS Army / CashKeg points (his words, condensed)

1. **QB selection**: almost always target QBs in the best scoring/game environments (highest
   implied team total / game total). Only real exception: an extreme value play (cheap
   backup in a good offense, easy salary smash).
2. **SE3max construction methodology**: think of it as a PIVOT off your cash lineup, not an
   independently-built lineup. If the cash build plays Ja'Marr Chase, the SE3max build fades
   Chase for Tee Higgins or Chase Brown instead -- do this in 1-3 roster spots, not the whole
   lineup.
3. **DST**: cheapest viable play for the cash lineup itself (defense upside is capped, so pay
   up elsewhere). For the SE3max pivot specifically, maybe a lower-owned DST still in a good
   spot, or just keep the cash DST depending on value -- not a blanket "always differentiate"
   rule.
4. **FLEX (DraftKings specifically)**: should be a player who gets real target volume. Can be
   a TE, but needs to be a genuine high-usage one -- because DK is full-PPR, scores are less
   TD-dependent than FanDuel, so catches alone carry more of the floor.
5. **Dart plays belong in MME, not SE3max.** SE3max is "cashy" -- a pivot off cash, not a
   ceiling-chasing GPP build.

## 4. Operationalized variables proposed this session (Greg has NOT yet confirmed this framing)

| # | Point | Variable | Testable how |
|---|---|---|---|
| V1 | QB best game environment | QB team implied total / game total as a stack-team selection threshold | Cheap replay toggle, testable now |
| V2 | SE3max = pivot off cash | New construction METHOD: build one anchor "cash" lineup, generate entries as 1-3 deliberate correlated swaps off it | **Needs new tooling**, not a flag -- biggest lift of the 5 |
| V3a | DST cheapest-viable for cash | DST min-salary constraint | Cheap replay toggle |
| V3b | DST lower-owned for the pivot lineups specifically | DST ownership target, CONDITIONAL on anchor-vs-pivot role | Depends on V2 existing first -- not independently testable |
| V4 | FLEX = high-usage, not "TE vs RB" | Replace position dummy with `proj_targets`/`proj_rec` threshold | Cheap replay toggle -- **data already exists**, confirmed `proj_targets` and `proj_rec` are already columns in `output/final_projections_*.csv`, no new ingestion needed |
| V5 | Darts belong in MME only | Variance-budget constraint (cap sub-median-floor players per SE3max lineup) | Cheap toggle, but needs a floor/variance metric defined first (not yet specified) |

## 5. Proposed testing methodology (Greg agreed to the general shape, details not finalized)

Given only 6 real slates of ground truth (growing slowly, ~1-3/week), a full factorial
across 5 variables is not statistically defensible -- explicitly flagged and accepted by
Greg. Proposed instead:
1. Test each cheap-toggle variable (V1, V3a, V4, V5) ONE AT A TIME against the current
   best-known baseline (stack=2 + bring-back + TE-in-FLEX), same replay methodology as
   `scripts/replay_validation.py` / `analysis/classic_diag/replay_selection_criteria.py`.
2. Only test COMBINATIONS where there's a specific reason to expect an interaction (e.g.
   V4 and the existing TE-in-FLEX finding are entangled and need joint testing) -- not a
   full grid.
3. Build V2 (anchor+pivot) as its own real project; fold V3b in only once V2 exists.
4. Use `scripts/classic_field.py` + `analysis/classic_diag/best_lineup_classic.py` (higher-N
   simulation, not ground truth but validated to real score quantiles) to screen combinations
   cheaply BEFORE spending real-slate replay budget confirming them.

## 6. Suggested first move for the new session

Given the section 0 reality check, recommend NOT starting the full V1-V5 program cold.
Instead:
1. First, check the real-structure stack-restricted selection-criteria result from the
   OTHER thread (see section 0) -- it may already be the fastest path to "closer by a lot"
   for Week 3, independent of anything in this file.
2. If more is needed, prioritize V4 (cheap, data already available, directly resolves a
   real tension) and V1 (cheap, already partially validated by both Greg's account and web
   research) first -- these are the fastest path to ONE concrete, replay-validated change
   for Week 3, rather than waiting on the full program.
3. Treat V2 (anchor+pivot methodology) and the full combination-testing plan as the
   longer-term track, explicitly not gating Week 3 on it.

## 7. What's NOT yet done

- V2 has no design beyond the one-paragraph description in section 3/4 -- needs real
  thought on how "pivot off an anchor lineup" would actually be implemented (which
  players are eligible swaps, how many swaps, correlation constraints on the swap itself).
- V3a/V3b (DST salary/ownership rules) and V5 (dart-play variance cap) -- not tested
  this session either, per section 6's own priority order (V1/V4 first).
- **CORRECTION, 2026-09-22 follow-up session**: the "DST-facing-your-own-stack
  negative-correlation constraint... not implemented anywhere" claim above was WRONG.
  It's been in `scripts/optimizer.py` since Session 17 (`add_skill_vs_opp_dst_constraints`,
  decision #56, `DEFAULT_EXCLUDE_SKILL_VS_OPP_DST = True`) -- a hard constraint, on by
  default, and actually broader than the handoff's framing (forbids ANY skill player,
  not just the stacked QB, alongside their opponent's DST). `--allow-skill-vs-opp-dst`
  turns it off. No action needed; just don't re-flag this as missing again.

## 8. Follow-up session results, 2026-09-22 (V1 and V4 tested; selection-criterion question closed out)

Ran the rigorous selection-criterion test that section 0 pointed to
(`analysis/classic_diag/replay_selection_criteria.py`, now including the `*_validated`
rules that were coded but not yet run) plus two new tests for V1 and V4. All against the
same 6 real logged slates, same methodology as `HANDOFF_classic_construction_replay.md`.

**Selection-criterion verdict**: `worst_top25_realstack` (worst-case P(top-25%) across the
4 correlated scenarios, restricted to candidates with a real QB+teammate+bring-back
structure on the roster) is the best SINGLE rule of 11 tested: 3/6 cash, mean percentile
0.703 (vs. arm1's real submissions: 0/6, mean 0.367). The stricter `*_validated` filter
(QB+2 teammates+bring-back) that the code comments predicted would "match or beat 4/6"
did NOT pan out -- also 3/6 cash but a WORSE mean percentile (0.628), and it still missed
the exact slate (wk2_main) it was designed to rescue. Don't re-chase that prediction
without new evidence.

**V4 (FLEX/floor, tested via `floor_sum`, a new rule added to the same script)**: rather
than a blunt TE-vs-proj_targets proxy, tested selecting by the SUM of each roster's own
already-computed `statline_p10` (a calibrated floor estimate already in
`output/final_projections_*.csv`, unused anywhere in selection before now). Result: 3/6
cash, mean percentile 0.704 -- statistically on par with `worst_top25_realstack`, BUT it
picks a DIFFERENT lineup on 5 of 6 slates (verified by comparing each pick's exact
projected-points fingerprint, not just cash/pct) and cashes on wk2_early, which
`worst_top25_realstack` misses. Layering the strict `validated` mask on top of floor_sum
backfired badly (1/6 cash, mean 0.457) -- floor-maximizing and strict stack-validation
don't compose well; don't combine them naively.

**The actionable finding, since SE3max allows up to 3 entries**: you don't have to pick
just one rule. Generating BOTH the `worst_top25_realstack` pick and the `floor_sum` pick
from the same candidate pool and submitting both (2 of your 3 SE3max slots) would have
had at least one cash on 4/6 of the logged slates -- up from 0/6 real and 2/6 for the
original single-rule Arm 3 approach. (A third rule, `raw_proj_realstack`, was also tried
but added nothing -- it picks the IDENTICAL lineup as `worst_top25_realstack` on 4 of 6
slates, confirmed by exact projected-points match, so it's not a real third thesis.) This
is the strongest, most concrete "closer by a lot" candidate from this session -- n=6 is
still small, but it's real replayed data, not a hoped-for prediction.

**V1 (QB game environment, tested via `analysis/classic_diag/replay_v1_game_env.py`,
new)**: reranking which teams get forced-stack candidates by `implied_total` instead of
QB `final_projection` produced a byte-identical outcome on 5 of 6 slates and the same
cash/percentile on the 6th (pool size differed by 1 candidate but the top pick didn't
change) -- a clean null result in this automated-tooling context. Likely explanation:
`final_projection` already substantially proxies `implied_total` (rank correlation
0.83-0.93 across the 6 slates, checked before running this), and `top_teams=10` is
already generous enough that the reordering rarely changes which teams' stacks make the
pool at all. This does NOT mean Greg's underlying principle is wrong for a human
eyeballing a slate pre-lock -- it means it's already largely captured by the existing
automated pipeline, so it wasn't a lever worth building further tooling around.

**Files added/modified this session** (uncommitted as of this update): `floor_sum`/
`floor_sum_validated` rules added to `replay_selection_criteria.py`;
`analysis/classic_diag/replay_v1_game_env.py` (new); `best_lineup_classic.py`'s
`candidates()`/`score()` gained a `team_rank_key` param (default `"proj"`, reproduces
prior behavior exactly) to support the V1 test.

**Not touched this session**: V2 (anchor+pivot methodology), V3a/V3b (DST salary/
ownership), V5 (dart-play variance cap) -- still open, still explicitly not gating
Week 3 per section 6.
