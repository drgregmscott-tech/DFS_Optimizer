# Field-lineup construction as a prior for our pool generation — RESULTS

**Date:** 2026-10-07. Source handoff: `HANDOFF_field_lineup_construction_priors_2026-10-07.md`.
Run by an Opus subagent in an isolated worktree; the worktree (and its scripts/data artifacts —
`construction_prior.py`, `construction_test.py`, `construction_check_2026.py`,
`construction_features.csv`, `construction_field.pkl`, the `*_out.txt` logs) was torn down before
this write-up could be copied over, so only the agent's final report survives. The data files were
FC-derived and would not have been committed anyway per `SUBAGENT_BRIEF.md`; the scripts are lost
and would need to be rewritten if this is revisited. Re-run cost should be low — the feature
extraction is a straightforward reduction of `data/fc_history/lineup_study/*_SE_dollar_*.json.gz`
and `lineups_scored.csv`, both still intact. A copy of this write-up also lives at
`analysis/lineup_level_own_model/CONSTRUCTION_PRIOR_RESULTS.md` (untracked, alongside that folder's
existing `RESULTS.md`).

## Verdict: DROP
The field's lineup construction is not a useful guide for building our pools. Nothing ships, no
production code was changed, nothing was committed.

## Question tested
Where does our SE3max pool build differently from the real SE field, and does pushing our build
toward the field's shape make our pick finish better on held-out history?

## 1. The gaps are real and large
Same features computed on both sides: 1.0M real SE $ field lineups across the 63 history slates,
and our 63 pools of 100 lineups each. Every material gap has the same sign on 55-63 of 63 slates
and in all 4 seasons.

- **Stacking and bring-back:** we use QB+2 in 100% of lineups vs 23% for the field; bring-back in
  100% vs 39%. Both were hard rules in the 9-29 preset these pools were built with. Production
  already dropped the forced bring-back on 10-02.
- **Two TEs:** 64% of our pool and 95% of our picks, vs 20% of the field.
- **Three RBs:** 8% of our pool vs 38% of the field.
- **One-game concentration:** 4.2 players from one game vs 3.0.
- **Salary shape:** we roster more studs and more punts; our QB costs ~$400 more.
- **Ownership:** total ownership is 37 points lower — this is the already-closed ownership
  question (see `analysis/lineup_level_own_model/RESULTS.md`), not re-tested here.

## 2. The field's own results say our side of each gap is equal or better
Regressed cashing on each feature, slate by slate, holding the lineup's FC projection and
ownership fixed.

- **Favor our side:** QB+2 (+0.48 cash pts per SD, 4/4 seasons), one-team and one-game
  concentration, more studs, more punts.
- **No effect:** bring-back, QB salary, 2 TEs.
- **Favors the field:** only more RBs (+0.53, CI [+0.02, +1.06]).
- Field cashers build almost exactly like non-cashers (within 0.05 SD on every construction
  feature). What separates them is projection and ownership (+0.22 / +0.28 SD) — construction, not
  so much.

## 3. Nudging toward the field doesn't move held-out finish
11 nudges x 3 projection arms (33 tests) through the existing leave-one-season-out pick test
(reused `analysis/lineup_own_signal/evaluate.py`-style LOSO machinery).

- None is positive in all three arms. 3 have a CI above zero, 6 have a CI below zero.
- More RBs — the one lean the field actually supports — is significantly **negative** on our
  production arm (-.042, CI [-.075, -.011]).
- Best-looking result: a cheaper QB at equal projection, +.074 [+.021, +.126] on the production
  arm, +.064 on the FC-projection arm. Doesn't hold up on inspection:
  - the field itself says QB price is worth zero;
  - negative on the old-projection arm;
  - each arm's gain comes from different seasons (not a consistent effect);
  - on 2026, every non-zero result traces to Week 2 only.
  Called inconclusive at a low bar, not worth more time. If ever revisited, it's a question of
  whether we over-project expensive QBs, not a construction rule.

## Conclusion
Construction isn't where our missed cashes come from. Our builds are already shaped more like the
field's *winners* than the field as a whole is. Combined with the earlier joint-ownership result
(see `analysis/lineup_level_own_model/RESULTS.md`), this closes the field-lineup data as a source
of construction rules — accuracy work belongs in projections, not pool-construction rules. As a
side benefit, this independently supports two current production settings: keep QB+2, keep
bring-back off.

## Caveats
- The history pools predate the 10-02 bring-back removal and the 9-30 construction
  penalty/bonus settings. Doesn't change the conclusion — the question was whether the field is a
  good guide, not whether our current settings match the field.
- Some 2024 Wk8 – 2025 Wk3 field files are missing player IDs for 5-37% of rows; those rows were
  dropped. The gaps hold on 60+ of 63 slates either way.

## Parked, not tested
Showdown construction compared with the field — not touched this session. The 2-TE rate looked
dramatic in the classic data but the field gives it no cash effect, and `CLASSIC_RULES` rule 3
already reached the same answer with stronger controls, so this wasn't chased further.
