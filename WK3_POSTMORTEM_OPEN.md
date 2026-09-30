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

4. **§6 revisit-parked-decisions sort — RESOLVED 2026-09-30.** Sorted all 4 named candidates:
   - Showdown `lsal` refit: still date-gated, unchanged (see #1 above).
   - QB/projection-stack refit: **(b) track-2, actionable now** — RB/WR/TE MAE improved every season
     2021-26 (RB 4.30->3.98, WR 4.42->4.17, TE 3.14->2.93), shelved only because refitting on all QBs
     (backups included) hurt QB1 (bias -0.15 -> -1.21). The RB/WR/TE-only split, leaving QB on its
     already-shipped separate recal/guard/autopromote path, was never actually tested. **Added below as
     priority item 7.**
   - Sigma/yards-variance refit: **already closed**, not a sample-size problem as originally framed —
     sigma only reaches the solver through lambda, and lambda is 0, so no amount of data produces a
     lineup gain regardless of sample size. Only reopens if sigma gets a new consumer (e.g. MME sims).
   - FFC-floor/ownership refits (9 sub-items): mostly (a) wrong-direction, correctly killed (flatter
     logistic, mid x1.3-1.45, history-tuned joint layer, rank features, min-price DST flag, FFC floor
     a=0.7 — all confirmed with real corr/MAE evidence). Two corrections: **DST power 1.25 should move
     from "track-2" to closed/superseded** — v2's DST softmax already beats it (top-DST .38-.42 vs .29)
     and stacking a power on top of v2 was never tested, so nothing to track. **FFC cliff removal** is
     the one real (b) item — fixes ~1/3 of the unlisted-chalk miss (chalk bias -9 -> -7.5/-7.7/-6.7) at a
     small corr cost (-.01 to -.03), but needs real Wk4+ data to set a ship bar (no source doc ever set
     one) — added to the track-2 watch list below, Sunday-gated like item 1.

## Open (added 2026-09-30, from the system-grade review — see `analysis/model_vs_fc/RESULTS.md`) — PRIORITY ORDER, work these next

7. **Expensive-player ($7k+) ownership gap — CLOSED 2026-09-30, reframed as a ranking miss, not shipped.**
   Four held-out studies, in order:
   - `analysis/stud_ownership/RESULTS.md` (untracked, DO NOT COMMIT — FC-derived aggregates): graded against
     real DK ownership, not FC's dead projected-Own column (the .291-vs-.797 number above was FC's own
     pre-lock opinion, 2021-23 only, correctly retired as a calibration target). Live 2026 $7k+ corr is
     already .743. Five candidate stud features (role/vacated, Vegas, price tier, momentum, pts/$) tested
     2021-25 LOSO: none moved $7k+ corr by more than +.018, none consistent across seasons —
     **wrong-direction, killed.** Real finding: $7k+ chalk and cheap-WR/TE chalk are **the same mechanism**
     (every band's ownership model predicts real 20-30%+ chalk at about half), not two separate problems.
   - `analysis/chalk_size_fix/RESULTS.md` + `scripts/ownership_v2.py` (`apply_chalk_ffc`, env
     `DFS_OWN_CHALK_FFC`, default off): pull top-N players toward raw FFC by factor b. Helped 2 of 3
     held-out 2026 weeks but made the target tier (30%+ real) worse in aggregate — fixed group budgets mean
     the pull steals share from true mega-chalk. **Inconclusive, off by default**, not re-tested since a
     mechanistically cleaner candidate (below) doesn't have this flaw.
   - `analysis/chalk_temperature/RESULTS.md` + `scripts/ownership_v2.py` (`apply_chalk_temp`, env
     `DFS_OWN_CHALK_TEMP`, default off): sharpen each group's distribution toward its current top (no FFC
     needed, testable on all 5 history seasons). Catch-rate/bias direction improves in all 5 seasons but
     correlation drops every season and $7k+ MAE gets worse; overshoots $7k+ on live 2026 (already
     near-calibrated there via the FFC blend). **Wrong-direction, killed.**
   - **Root cause, confirmed three ways: this is a ranking/classification miss, not a distribution-shape
     miss.** 60-65% of real 20%+/30%+-owned players aren't even in our model's top tier, so no amount of
     resizing/sharpening the tiers we already have right fixes it — it lands on the wrong players.
   - **Next step (not started, needs a fresh session):** find the signal that predicts *which* players the
     field will make chalk (not how big to make our current top tier). See
     `HANDOFF_ownership_ranking_signal_2026-09-30.md` for the pickup plan.

8. **QB/projection-stack refit — RB/WR/TE-only split, from §6.** The 2021-26 stack refit
   (`data/projection_stack_dk_refit_2026-09-26.json`, untracked, not wired) improved RB/WR/TE MAE every
   season (RB 4.30->3.98, WR 4.42->4.17, TE 3.14->2.93, bias +0.3..0.8 -> ~-0.3) but was shelved whole
   because fitting on all QBs (backups included) hurt QB1 (bias -0.15 -> -1.21). The split was never
   tried. **Work needed:** rebuild the stack refit for RB/WR/TE only (leave QB on its already-shipped
   separate recal/guard/autopromote path), re-run the lineup replay on 2021-25 + 2026 Wk1-3, refit
   ownership once after (the stack shifts ownership 1-3 points), ship if it holds up.
9. **QB projection gap vs FC (FC beats us by 0.22 MAE, history) — real but smaller, fine to leave for
   later.** QB recal + auto-promote (shipped this postmortem) closed the surprise-starter piece; this is
   the remaining base projection-accuracy gap on known starters. Same note applies: grade against real
   results, not FC's number specifically.

~~Replace the dead FC ownership benchmark~~ — **partially dropped, corrected 2026-09-30.** FC actually
gave two separate things, and the first drop conflated them:
1. **Pre-lock projections** (FC's `Own` column) — another model's opinion, not the field itself. Correctly
   dropped as a calibration target; the goal is the real field, not parity with a commercial product.
2. **Post-lock REAL ownership aggregated across many real contests we never personally entered** (the
   410-contest classic / 142-contest Showdown Lineup Study) — this is genuine field data, not an opinion,
   at a breadth our own `ownership_actual_log.csv` can't match on any single contest we entered. **Correction
   (2026-09-30): nothing is lost going forward.** DraftKings itself makes real results + real ownership for
   every contest we enter downloadable the next day — that's exactly what already feeds
   `ownership_actual_log.csv` every week, FC or no FC. FC's only unique value here was backfilling
   **historical breadth we didn't personally capture at the time** (past weeks/seasons, and contests we
   weren't entered in) — that backfill is what's gone, not any future slate's data. No action needed; the
   $7k+ work in item 5 and every future week's ownership logging are both fine on the existing pipeline.

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
- FFC cliff removal (from §6) — fixes ~1/3 of the unlisted-chalk miss (chalk bias -9 -> -7.5/-7.7/-6.7)
  at a small corr cost (-.01 to -.03). No ship bar was ever set; shadow-score on real Wk4+ slates, ship
  if it keeps the chalk gain with corr loss <=.005 in >=2 of 3 new held-out weeks.

## Housekeeping flagged this session, not yet decided

- `data/nflverse_usage/` (35MB, unused by any script) — delete or explicitly `.gitignore`.
- Leftover test-build output from tonight's Showdown fix verification
  (`output/lineups_multi_dk_dk_showdown_wk4_PIT_CLE_01Oct2026_shared.csv/.lint.txt`,
  `output/vegas_implied_totals_dk_showdown_wk4_PIT_CLE_01Oct2026.csv`) — not a real intended build, safe
  to delete.
