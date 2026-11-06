# Handoff: field-lineup data as a construction prior (not an ownership-signal question)

**Filed:** 2026-10-07, split off the lineup-level-ownership session as a deliberately separate
topic (see `HANDOFF_lineup_level_ownership_2026-10-07.md`, done same day). Not started yet. Does
not depend on Week 5 — everything needed already exists in history data.

## Why this is a different question, not a continuation
The lineup-ownership session asked "does the field's correlated/joint ownership predict finish
better than per-player ownership." Answer: no — the joint structure is real (QB+WR rostered
together 2.7x independence, QB+TE 2.5x, bring-backs 1.4x) but carries ~zero finish signal beyond
what per-player ownership already has (+.129 joint ceiling vs +.133 per-player ceiling). That
closes the "predict finish" angle.

This handoff asks something else: regardless of whether it predicts finish, does the field's
*actual construction behavior* — real stack rates, bring-back rates, salary allocation shapes,
chalk-count distributions, by slate type/week/season — tell us anything useful as a **prior for
our own pool generation**? E.g.: are we under/over-stacking relative to the field in a way that
changes variance/ceiling of our builds; are there salary-allocation shapes the field favors that
we're not generating; does the field's bring-back rate suggest our pool should include more/fewer.
This is a construction-rules question, not a signal/prediction question, so the ownership
session's "wrong direction" verdict does not settle it either way.

## Where the evidence lives (already built, reuse don't rebuild)
- `data/fc_history/lineup_study/*_SE_dollar_*.json.gz` (651 files total across game types,
  2022-25) — real field lineups, matched to our `hist_meta` at ownership corr .99999 (verified
  2026-10-07, see `analysis/lineup_level_own_model/RESULTS.md`). This is the raw field-behavior
  data.
- `analysis/lineup_level_own_model/pairs.csv` (175k rows) — every player pair within a lineup,
  joint vs independent ownership (`pij`, `pi`, `pj`), pair type (`QB-RB_opp`, `diffgame`, etc.),
  by tag/season. Already has the co-occurrence lift computed; reusable for "what shapes does the
  field actually build" questions without re-deriving pair joint probabilities.
- `analysis/lineup_level_own_model/lineups_scored.csv` (18.9k rows, 63 pools x 100 lineups x 3
  arms) — per-lineup aggregates already computed: stack_n, bring, qb_stack_lg, n_games, sal,
  n_chalk_pair, salary distribution stats. This is OUR lineup pool's construction shape, already
  in a comparable format to what field data would need to be reduced to.
- `analysis/lineup_own_signal/RESULTS.md` and `analysis/lineup_level_own_model/RESULTS.md` — read
  both first; they're the full record of what's been tested on this data so far (signal/predict
  framing only — construction-prior framing has not been tried).

## What's already been ruled out (don't re-test under a signal framing)
- Joint ownership as a finish-prediction signal: dead, see above.
- Any re-rank lever built on per-player or joint ownership sums: inconclusive/dead, see item 15
  and the 2026-10-07 agent's RESULTS.md.
Do not re-ask "does X predict finish" here — that door is closed for lineup-level ownership
structure. This handoff is specifically about construction behavior as a prior, not prediction.

## Concrete angle to start with
1. From `data/fc_history/lineup_study/`, compute real-field distributions (by slate/season, or
   pooled if n is thin per-slate) for: stack rate (QB+same-team pass-catcher), bring-back rate,
   number of distinct games rostered, salary left on table / allocation shape, chalk-player count
   per lineup.
2. Compute the same distributions for our SE3max history pools from `lineups_scored.csv`
   (`stack_n`, `bring`, `n_games`, `sal`, `n_chalk_pair` are already there).
3. Compare the two distributions directly — not against finish, against each other. Where do we
   diverge from the field in a way that's plausibly a construction-quality issue (e.g. we build
   meaningfully fewer/more bring-backs, our salary-left distribution is shifted, we under/over
   stack relative to the field's actual rate)?
4. Where a gap is found, THEN test whether nudging construction toward the field's shape changes
   our pool's held-out finish distribution (reuse the LOSO pick-test machinery from
   `analysis/lineup_own_signal/evaluate.py` / the 2026-10-07 agent's `evaluate.py`) — don't ship
   on "field does X" alone; it only counts if it moves our held-out result.

## Scope note
Budget as its own session (or Opus agent per the user's standing preference for heavy analysis,
time-boxed well under 90 minutes given the reusable data). Follow `SUBAGENT_BRIEF.md` rules if
delegated: no FC data committed, two-track ship/inconclusive/drop verdict, held-out or it didn't
happen.

## Session discipline reminder
One topic per session. If this surfaces tangents (e.g. showdown-specific construction, which was
explicitly dropped — not parked — for the joint-ownership-as-signal question but is untested for
this construction-prior framing), park them rather than chasing mid-session.
