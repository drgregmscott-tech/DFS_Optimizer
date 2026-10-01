# WK3 Postmortem — Open Items Only (2026-09-30)

Everything else from `WK3_POSTMORTEM_CHECKLIST.md` (§0-§4 root cause, ownership v2, QB recal, inactives
tooling, the Showdown/classic Lineup Study, lambda reverify, own-penalty, etc.) is CLOSED/SHIPPED/RESOLVED.
That file is kept as the historical record — don't re-open it as a task list. This file is the only
active WK3 to-do list. When an item below closes, move its resolution note into the checklist and delete
it from here, don't let this file regrow into another sprawl.

## Pre-weekend priority list (narrowed 2026-10-01) — work these today/tomorrow

Everything gated on Wk4 game results (plays Sunday 2026-10-04) is EXCLUDED from this list on purpose —
nothing to do on those until game day/results land. Full detail for each item is below in `## Open`;
this section is just the active-now subset, ranked.

1. **WR ownership props-bump — CLOSED 2026-10-01, superseded by a real bug fix.** Tested three ways
   (blanket WR-wide feature, then segmented to the flagged next-man-up/vacated-usage cohort): both versions
   are track-2 at best — the segmented version closes the aggregate chalk gap (10.8→17.5, real 18.0) but
   can't separate beneficiaries the field actually bought (Downs, Gadsden, Skattebo — still under) from ones
   it didn't (Warren, Achane — already correct, got pushed wrong). Digging into *why* those specific
   players split that way (FFC-listed vs not) found the real issue was one layer down: **a production bug
   in `scripts/ingest_public_ownership.py`**, not a missing feature. Its table-selection logic picked by
   raw name+salary match count only; on Wk3, the early-slate table (a subset of main's pool) out-matched
   the real main table by one player (44 vs 43) and got saved as "main" in every refresh 9/24-9/27 —
   silently dropping every afternoon-game player from main-slate ownership for 4 days. That explains 8 of
   14 Wk3 "unlisted-chalk" misses (Henry, Olave, Shough, Vele, Lamb, Jeanty, Bateman, Deebo); re-scoring
   with the real main table moved unlisted-chalk bias -8.1→-4.8 (Henry 10.9%→18.5%, real 17.8%).
   **Fixed and shipped 2026-10-01:** `ingest_public_ownership.py` now picks by team coverage first,
   match count second (rejects a table if another covers teams materially better; loud warning under 70%
   coverage). Off-switch `DFS_FFC_PICK_BY_COVERAGE` (default 1/on). Verified live on both Wk4 slates:
   main now correctly picks "DraftKings -Main" (79% team coverage) instead of risking the Early/Thu-Mon
   subset tables, early correctly picks "DraftKings -Early Only" (94%).
   **Still open, NOT fixed by this:** Downs and Skattebo were genuinely left off FFC's list (not a
   selection-bug casualty) and our own v2 model ranks them too low on its own regardless of FFC — that's
   the same underlying cheap-WR/TE ranking problem already tracked (item 7 below), not solved here.
   Props-bump itself (both forms) is parked in the track-2 watch list below, not shippable, not worth
   more iteration until this bug-fix's downstream effect is seen on real weeks.
2. **Chalk-size fix v2 — precise/segmented version (item 11) — CLOSED 2026-10-01, no ship, one candidate
   moved to track-2.** See `analysis/chalk_size_fix_v2/RESULTS.md` (2026 ownership-derived, kept local).
   Tested gating the FFC-pull to identifiably-flagged chalk instead of the whole top-N: role-bump/vacated
   ≥ .15 (the originally-named flag) was tried first and dropped — it still hurt wk3 and captured far less
   of the cheap-chalk gain than hoped, so teammate-OUT usage is not the mechanism driving the gain. No
   literal "name-recognition" feature exists, so that idea was tested via proxies (FFC-ranks-us-much-lower,
   cheap salary tier, freezing already-high-owned players) across 9+ segment combinations, all in the
   RESULTS.md table. Freezing mega-chalk (anyone already shipped at 25%+) does cleanly fix the budget-raid
   problem — $7k+ bias30 unchanged in every week tested — but restricting the pull to $5.5k+ players still
   hurt wk3 even with the freeze, because FFC itself ranked those players worse than we did that week, not
   just a budget-allocation artifact. The one surviving candidate — pull toward FFC only for cheap (<$5.5k)
   top-N players, freeze anyone at 25%+ — is the only version that leaves mega-chalk untouched and still
   lifts cheap WR/TE catch20 .58→.75 (bias20 -8.1→-6.0). **Not shippable yet**: its params were picked after
   seeing all 3 wk1-3 weeks (not a clean prior held-out test), and FFC ownership has no history before
   2026, so there's no way to extend the sample via LOSO 2021-25 — confirmed, not assumed. Moved to the
   track-2 watch list below, gated on Wk4-5 real ownership as the first true out-of-sample check. Wiring
   if/when it ships: `apply_chalk_ffc` in `scripts/ownership_v2.py` gets `mask`/`protect` args (mask =
   salary < 5500, protect = final >= 25), params N=15 b=.5, new switch `DFS_OWN_CHALK_FFC_SEG` (default 0/
   off), audit column `own_chalk_ffc_seg`. No code shipped, nothing committed, no live artifacts touched.
3. **Showdown `lsal` candidate re-test (item 1).** Wk4 Showdown (PIT/CLE) already played 2026-10-01 —
   this is NOT gated on future results, the data already exists. Log it into `ownership_actual_log.csv`
   and re-test today.
4. **Props pipeline timing audit, other lock windows — CLOSED 2026-10-01.** Audited the live cron-job.org
   job list directly (12 enabled jobs at the time) against actual lock times, using the owner's rule:
   injury report lands ~90 min before lock, so the near-lock pull should fire ~60-70 min before lock to
   catch it with rebuild time left. Sun main (10:55am CT vs. noon lock, confirmed `17:00:00Z`) and Thu/Mon
   night (6:00pm CT vs. ~7:15pm lock, confirmed Wk4 showdown `00:15:00Z`) were already correctly timed —
   no action needed there, an earlier version of this note wrongly flagged Thu/Mon as gapped. Two real
   gaps found and fixed: **Sunday afternoon** had only a 2:30pm CT ping, just 35 min before the typical
   ~3:05pm lock (too tight, not in the 60-70 min window) — added **"DFS Optimizer - Sun 2PM CT Refresh"**
   (every Sunday 2:00pm CT). **Sunday Night Football had no near-lock job at all** — added
   **"DFS Optimizer - Sun 615PM CT SNF Refresh"** (every Sunday 6:15pm CT, ~65 min before the typical
   ~7:20pm SNF lock; harmless no-op on weeks SNF isn't played). Both created live in cron-job.org, same
   worker URL/token pattern as the existing near-lock jobs, no `kind` param. 14 enabled jobs now.
**§5 frontend/rule additions (item 3) — COMPLETE, dropped from this list.** Confirmed done by the user
2026-10-01; its `## Open` entry below is now closed too (no stale sub-item list left).

**Left off this list on purpose (gated on Wk4, nothing actionable until then):**
- Role-bump TE fix — needs a real live TE-out case to confirm (item 10).
- Inactives timing log — needs to actually run Sunday 2026-10-04 game day (item 2); no design work left.
- Track-2 watch items (`--own-penalty`, `DFS_OWN_V2_COEF=truepool`, vac-bump k=1.0, WR/TE reallocation,
  stud-gap mismatch, QB residual gap, FFC cliff removal) — explicitly "re-test with Wk4 data."
- QB projection gap vs FC (item 9) — real but smaller, deprioritized, no urgency either way.

Item 8 (projection-stack refit + its ownership-refit follow-up) is fully done and dropped from this list
entirely — see the historical record further down if needed.

## Open

1. **Showdown ownership `lsal` candidate re-test — date-gated, not analysis work. CORRECTION 2026-10-01:
   PIT/CLE has NOT played yet as of this morning (kicks off tonight, ~9 hrs out) — an earlier note in this
   file wrongly said "already played," premise error, not a real result yet.**
   Reactivation condition: 2+ more real Showdown slates logged since frozen (still 4 as of 2026-09-28).
   Wk4 Showdown (PIT/CLE) should satisfy this once it's final. Action: after tonight's game, log real
   ownership into `ownership_actual_log.csv`, then re-test the candidate against it. If it still doesn't
   beat production, drop it for good instead of re-parking it again. Not actionable until tonight.
   Ref: `HANDOFF_showdown_ownership_refit_2026-09-26.md`.

2. **Inactives timing — in progress, has a concrete Sunday action.**
   `scripts/inactives_timing_log.py` needs to actually run Wk4 Sunday (2026-10-04) to log when
   ESPN/Sleeper first surface inactives, plus the human inactives check. No further design work needed,
   just execute on game day.

3. **§5 frontend/rule additions — CLOSED 2026-10-01.** Confirmed done by the user; duplicate entry
   cleaned up (see the note above in the priority-list section). No remaining sub-items tracked here.

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
   - **Ranking-signal test done 2026-09-30 (`analysis/ownership_rank_signal/RESULTS.md`, DO NOT COMMIT):
     premise confirmed and sharper than stated** — only 43.3% of real 20%+ chalk lands in our model's
     predicted top-k (41.3% at 30%+); the chalk we miss isn't borderline, its median rank is 9th when k=3,
     predicted at 9.2% for players who hit 27.4% real. Four new ranking candidates (usage/target-share
     trend, last-week breakout, slate uniqueness, name x value) all tested within noise (95% CIs include
     0) — **wrong-direction, drop.** Real finding: missed chalk is cheap ($5.9k avg) and **our own
     projection rates it low (13.6) where the field/FC rates it high** — no ranking add-on can promote a
     player our value inputs already rank 9th in group. FC's own recall is only 47.6% (we're not far off
     a commercial model in aggregate), but our gap concentrates in TE (33% vs FC 45%) and WR (39 vs 44).
   - **Projection-swap diagnostic done 2026-10-01 (`analysis/ownership_rank_signal/RESULTS.md` §follow-up):
     confirmed, gap is a projection gap, closed.** Swapping FC's history projection into the proj/val
     features (nothing else touched) raised rec20 43.3% -> 47.3% (+4.0 pt, CI [+1.7, +6.3]), matching FC's
     own 47.6%. Every position improved, TE/WR (the worst gaps) moved most. **No more ownership-side work
     here — this item is closed.** The fix lives in projection accuracy, not ownership ranking. Promotes
     item 8 below (RB/WR/TE-only projection-stack refit) to top priority — same lever, already has
     real history MAE gains, never tried with the QB split.

8. **QB/projection-stack refit — RB/WR/TE-only split — SHIPPED 2026-10-01.** Refit RB/WR/TE only
   (`analysis/proj_stack/refit_eval_rbwrte.py`, QB excluded from the fit entirely this time) on 2021-25,
   MAE/bias improved every season 2021-2026 for all three positions (e.g. RB bias +0.89->+0.01, WR
   +0.69->-0.06, TE +0.41->-0.06; MAE down across the board). Lineup-level score deltas are directionally
   positive most seasons but the aggregate 95% CI still spans 0 (n=88 history slates) — real per-player
   accuracy gain, lineup-level payoff plausible but not yet statistically proven.
   **Live as of 2026-10-01:** `data/projection_stack_dk.json` now holds the new RB/WR/TE coefficients
   (`data/projection_stack_dk_refit_rbwrte_2026-10-01.json`) merged with the QB block unchanged from the
   prior 2020-21 fit (QB already has its own separate wk3+ recal/autopromote layer downstream; this QB
   block is only a week1-2 safety net). Old live artifact backed up at
   `data/projection_stack_dk.json.bak_2026-09-21`. Smoke-tested (`apply_stack` loads and scores cleanly).
   **Not yet done — tracked as its own item, see `HANDOFF_ownership_refit_after_projstack_2026-10-01.md`:**
   refit the ownership v2 coefficients against the new projections (full history rebuild chain). Not a
   blocker — the ranking-signal diagnostic already showed the gain lands even on ownership's *unrefit*
   coefficients (just swapping the better projection into existing features raised recall 43%->47%) — but
   a real refit should still close the loop and is the natural next session.
9. **QB projection gap vs FC (FC beats us by 0.22 MAE, history) — real but smaller, fine to leave for
   later.** QB recal + auto-promote (shipped this postmortem) closed the surprise-starter piece; this is
   the remaining base projection-accuracy gap on known starters. Same note applies: grade against real
   results, not FC's number specifically.
10. **Role-bump chalk gap (teammate OUT -> backup gets a bump the field reacts to) — WORK IN PROGRESS,
    needs a dedicated session before the weekend.** Full writeup: `analysis/role_bump_chalk_gap/RESULTS.md`
    (DO NOT COMMIT, FC-derived).
    - **RB: already closed**, shipped in a prior session (2026-09-30, `apply_rb_replacement`/WRW RB,
      `DFS_WRW_RB`). Re-validated 2026-10-01, actively firing on live wk4 builds.
    - **TE: SHIPPED 2026-10-01.** `apply_te_replacement`/WRW TE (`DFS_WRW_TE`, default on). Vacated-target
      redistribution fit on 2016-25 box scores held out by season; next-TE bias +2.2->+0.9 (2021-25
      current-code frame), no full-population regression. **Not yet confirmed on a real live TE-out case**
      (2026 wk1-3 only had 2 cases, both overshot, sample too small to mean anything). Check the first real
      Wk4+ TE-out slate.
    - **WR: no clean lever found, correctly not shipped.** A dedicated WR-out redistribution model (fit on
      2016-25 box scores) helps PROJECTION (bias +2.28->+0.94) but that's out of scope for the ownership
      question asked. On OWNERSHIP specifically: we already pick the field's same top-owned beneficiary
      77.5% of the time (FC: 79.8%) — ranking isn't the problem. The real miss is sizing the ~30-40% chalk
      explosion outliers (Parker, Gallup, Palmer-type cases) that a uniform "full promotion" ownership
      feature can't distinguish from ordinary promotions (tested, made ranking worse, correctly not
      shipped). This explosion-sizing miss is the SAME mechanism as item 7 below (chalk_size_fix) —
      see that item, now reopened.
    - **Props check (open, not yet tested):** we already pull live sportsbook player props
      (`_apply_props_anchor` in `scripts/build_projections_statline.py`) which reprice in real time on
      injury news, and they DO reach ownership indirectly (through the `final_projection` that ownership's
      proj/val features read — same inheritance path as every other projection input). Not yet tested:
      on WR-out slates where a props snapshot was actually fresh/available at lock, does the
      props-anchored projection already catch the chalk-explosion cases the engine-only model misses?
      Worth checking before concluding this is unsolvable from available data.
11. **Chalk-size fix (pull top-N toward raw FFC) — REOPENED 2026-10-01, was "inconclusive, keep testing,"
    not dead.** `analysis/chalk_size_fix/RESULTS.md` (2026-09-30): the broad version (blend ALL of FFC's
    slate top-N toward FFC by one fixed factor, N/b picked by grid search) helped 2 of 3 held-out 2026
    weeks on every metric (corr up, MAE down, cheap-chalk catch20 up in every week, .58->.75) but failed
    the ship bar because it steals ownership budget from true mega-chalk in the 30%+ tier (one global rule
    applied to a mixed-cause group). Correctly logged as "keep testing," not killed — `chalk_temperature`,
    the follow-up candidate meant to replace it, was itself later killed (wrong-direction), so nothing
    superseded this. **This is the same underlying mechanism identified independently three times now**
    (cheap WR/TE ownership, $7k+ ownership, and item 10's WR-out explosion cases): the field sizes
    top-of-group chalk better than we do. **Segmented version tested and CLOSED 2026-10-01** — see
    `analysis/chalk_size_fix_v2/RESULTS.md`. Role-bump/vacated-usage gating was dropped (wrong mechanism);
    the surviving candidate (cheap <$5.5k pull + freeze mega-chalk at 25%+) is track-2, gated on Wk4-5 —
    full writeup in the priority-list item 2 entry above, don't duplicate here.

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
- FFC cliff (model-side fix) — SUPERSEDED 2026-10-01: most of what looked like an unlisted-chalk model
  problem on Wk3 main was actually the table-selection bug fixed in item 1 above. A real model-side
  tradeoff still exists for genuinely-unlisted players (per-row alpha=1 tested and killed as
  wrong-direction, -13 chalk bias; budget-preserving re-rank tested and inconclusive) but it's secondary
  now — re-evaluate only after a few weeks on the bug-fixed ingest, since the input data itself was wrong.
- Chalk-size fix v2, segmented (`analysis/chalk_size_fix_v2/RESULTS.md`, `DFS_OWN_CHALK_FFC_SEG` not yet
  wired): cheap (<$5.5k) FFC-pull + freeze mega-chalk at 25%+ is the only segment that avoids hurting
  $7k+ bias30 while still lifting cheap WR/TE catch20 .58→.75. Params picked in-sample on wk1-3 (not a
  clean held-out test) — re-run with Wk4-5 held out, pre-committed params, before considering shipping.
- Next-man-up props bump (`analysis/wr_ownership_props_bump_segmented/`) — closes the aggregate cheap-chalk
  gap but lifts chased and ignored beneficiaries alike (can't tell Downs/Gadsden from Warren/Achane); only
  .45 corr with the actual residual vs .81 with ownership overall. Re-test pooled Wk3-5 once more props
  weeks exist; needs a second signal to separate "field bought this" from "field ignored this" before
  it's shippable.

## Housekeeping flagged this session, not yet decided

- **[CLOSED 2026-10-01]** `data/nflverse_usage/` — checked, doesn't exist (only unrelated
  `data/nflverse_games.csv` is present). Nothing to delete.
- **[CLOSED 2026-10-01]** Leftover test-build Showdown output — checked, none of the three flagged
  files exist in `output/`. Nothing to delete.
