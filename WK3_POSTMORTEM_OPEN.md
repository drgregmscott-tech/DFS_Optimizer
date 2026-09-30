# WK3 Postmortem — Open Items Only (2026-09-30)

Everything else from `WK3_POSTMORTEM_CHECKLIST.md` (§0-§4 root cause, ownership v2, QB recal, inactives
tooling, the Showdown/classic Lineup Study, lambda reverify, own-penalty, etc.) is CLOSED/SHIPPED/RESOLVED.
That file is kept as the historical record — don't re-open it as a task list. This file is the only
active WK3 to-do list. When an item below closes, move its resolution note into the checklist and delete
it from here, don't let this file regrow into another sprawl.

## Open

1. **Showdown ownership `lsal` candidate re-test — date-gated, not analysis work.**
   Reactivation condition: 2+ more real Showdown slates logged since frozen (still 4 as of 2026-09-28).
   Wk4 Showdown (PIT/CLE, 2026-10-01) should satisfy this. Action: after Wk4 Showdown results are in
   `ownership_actual_log.csv`, re-test the candidate against them. If it still doesn't beat production,
   drop it for good instead of re-parking it again.
   Ref: `HANDOFF_showdown_ownership_refit_2026-09-26.md`.

2. **Inactives timing — in progress, has a concrete Sunday action.**
   `scripts/inactives_timing_log.py` needs to actually run Wk4 Sunday (2026-10-04) to log when
   ESPN/Sleeper first surface inactives, plus the human inactives check. No further design work needed,
   just execute on game day.

3. **§5 frontend/rule additions (5 small items, none started) — own short session, not urgent.**
   - Flag/avoid 2 same-team WRs with no correlating QB rostered.
   - Prefer filling FLEX with an afternoon-slate player on multi-window main-slate builds.
   - Show projected team totals (not just game totals) wherever Vegas info displays.
   - Show expected pace of play per game, if a data source exists for it (unconfirmed feasible).
   - MME stack-depth setting: build MME pools as two merged dispatches (majority `--stack-size 1`,
     ~25-30% `--stack-size 2`) instead of one uniform batch — this is a workflow habit change, not code
     (the `--stack-size` flag already exists and is wired end-to-end).

4. **§6 revisit-parked-decisions sort — own short session, not urgent.**
   Re-read the parked/rejected list and sort each into (a) actually wrong direction, correctly killed, or
   (b) right direction, underpowered, should be an active track-2 item. Candidates already flagged:
   Showdown ownership refit (see #1 above — already has its own trigger), QB/projection-stack refit
   (RB/WR/TE shelved alongside a bad QB1 result — should they have shipped separately?), sigma/yards
   refit (mechanism validated, sample-size problem not signal problem), FFC-floor/ownership refits more
   broadly.

## Track-2 watch items (re-test with Wk4 data, not active work until then)

- `--own-penalty` fading: dropped as wrong direction on history + 2026 replay; flag stays default 0.
  Re-test only if ownership accuracy improves further (history v2 corr is .66 vs FC's .83-.88).
- `DFS_OWN_V2_COEF=truepool`: refit coefficients built but default OFF (2026 replay was slightly worse).
  Re-score on Wk4-5.
- Vac-bump k=1.0: shipped default ON; re-check the constant against Wk4-5 results.
- WR/TE "who replaces whom" projection reallocation: inconclusive (bias better, MAE worse) — keep
  watching, don't ship yet.
- Stud-gap harness-vs-live mismatch ($6.5k+ RB/WR/TE: history harness over-projects, 2026 live
  under-projects) — find the root cause (suspect the Wk1 `--season 2025 --week 23` convention) before
  any stud calibration change.
- QB residual gap vs FC — closed per the checklist (surprise starters only, covered by QB auto-promote),
  but keep an eye on it in Wk4 results since it was only a 1-week check.

## Housekeeping flagged this session, not yet decided

- `data/nflverse_usage/` (35MB, unused by any script) — delete or explicitly `.gitignore`.
- Leftover test-build output from tonight's Showdown fix verification
  (`output/lineups_multi_dk_dk_showdown_wk4_PIT_CLE_01Oct2026_shared.csv/.lint.txt`,
  `output/vegas_implied_totals_dk_showdown_wk4_PIT_CLE_01Oct2026.csv`) — not a real intended build, safe
  to delete.
