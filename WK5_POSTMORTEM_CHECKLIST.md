# Post-Week 5 Checklist (created 2026-10-12)

Working task list, not a conclusion — nothing below has been investigated yet. Results per the user: DK
main cashed, DK afternoon cashed, DK early just missed, FD main cashed. Showdown (BAL/ATL, tonight) not
in scope yet — postmortem covers everything else, which is complete.

## Session discipline (same rule as every prior postmortem, still applies)
One session = one topic from this list. A new idea that comes up mid-session goes in the Parking Lot,
not into the current discussion. A session that fully resolves one narrow question beats one that
touches five and resolves none.

## New this week

- **FanDuel now has a lineup-level results/ownership export (beta).** User downloaded
  `data/contest_results/fd_classic_week5_main_11Oct2026_full.csv` alongside the usual three DK files
  (`dk_classic_wk5_{early,afternoon,main}_11Oct2026_full.csv`). Confirmed by inspection: **same shape as
  the DK full-export files** — `Rank, EntryId, EntryName, Points, Lineup, Player, Roster Position,
  %Drafted, FPTS` — plus an extra `Salary` column DK's export doesn't have. This closes a gap flagged
  explicitly in the Wk4 postmortem (item 7): *"there's no FD contest-results export/grading pipeline
  (unlike DK's `data/contest_results/`), so FD performance can't be quantified the way DK is — not worth
  building for one site with no judged export available."* That blocker may now be gone.
  - Confirmed by grep: `grade_accuracy_week.py` and `grade_construction_week.py` are DK-only today (no
    `fd`/`fanduel` branching); FD is only referenced in `ingest_public_projections.py` /
    `ingest_salaries.py` (building the slate, not grading it).
  - **Open question for the user, flagged in the task:** is this FD export a one-off beta download or a
    standing feature? If standing, check whether **prior weeks' FD data** is also retrievable the same
    way — that would let an FD accuracy/ownership track get built on more than one data point out of the
    gate, same as DK's multi-week history.

## Items

1. **Projections & ownership accuracy vs. Week 5 actuals (standard, every week).** Run
   `python scripts/grade_accuracy_week.py --week 5` and `python scripts/grade_construction_week.py
   --week 5` once showdown is in (or run DK/FD classic now, showdown separately later). Log Wk5 real
   ownership into `ownership_actual_log.csv`. Feeds everything else below.

2. **Build FD into the grading pipeline, if the beta export is a standing feature (see above).** ✅ DONE
   2026-10-12. User confirmed it's standing and supplied FD main-slate exports for weeks 1-5, not just
   Wk5. `grade_accuracy_week.py` now grades FD in its own section (`players_fd.csv`), fully segmented
   from DK — different salary scale, different scoring, never pooled into one number; caveats stated in
   the report text (DK-fit MATERIAL/Z thresholds and FD salary tiers carried over unvalidated).
   `grade_construction_week.py` got only safe plumbing (discovery/salary/proj loaders); FD rule-grading
   was deliberately NOT attempted — every rule is a DK price threshold fit on ~410 DK contests, and one
   data point (now five, still thin) isn't enough to derive FD's own.
   - **Side-effect bug found and fixed:** a 2026-10-10 reorg moved DK wk1-4 contest files into
     `data/contest_results/2026/Week_N/` subfolders; both graders' slate-discovery glob was non-recursive,
     so since that reorg the season-to-date tracker was silently seeing Wk5 only. Fixed (`CR.rglob`).
     Didn't cause a wrong PERSISTENT flag this time (Wk5 was the current-model window regardless), but
     stripped historical context from the un-gated chalk/salary-edge trend tables, and would have blocked
     real multi-week PERSISTENT detection going forward. Confirmed fixed: `--week 1-5` construction run
     and `--week 5` accuracy run both complete clean with full history visible again.
   - **Real finding, independently verified (not just the grading plumbing):** FD under-projects every
     skill position, every one of the 5 weeks now available (WR/RB/TE negative bias 5/5 weeks, QB
     negative 4/5) while DK's bias on the same players/weeks is near zero. Root cause traced to
     `scripts/build_projections_statline.py:1153-1189` — the projection stack, the early-season salary
     blend, and QB wk3+ recal are each gated `site == "dk"` and never run for FD at all. FD ownership also
     reads too flat (real chalk ~30% vs. modeled ~9%, 5/5 weeks), though all 5 FD exports are single-entry
     (1/1) contests — chalkier than the multi-entry fields the model is calibrated on — so that one is a
     softer signal than the projection-bias finding.
   - **Next step (own session, don't rush it into this one):** test extending those three DK-only layers
     to FD, backtested against FD's 2021-25 history (`output/baseline_recent_form_fd_2021..2025_*.csv`
     already exist) before touching anything live — same held-out-history bar every other model change
     here clears, not a quick patch off 5 weeks of 2026 data alone.
   - **Also needed, possibly its own session(s) once the above lands:** FD-specific roster-construction
     rules (an FD analog to `CLASSIC_RULES.md`) — DK's rules are DK price-band/slot-specific and don't
     transfer. Revisit once there's enough FD contest history to derive rules from (same bar as DK's ~410
     contests, or at least enough to not be fitting noise); FD's single-entry contest mix above may also
     need accounting for before rules derived from it are trusted the same way DK's are.

3. **Carried from the Wk5 Sunday parking lot — RB+WR same-team-no-QB correlation rule.** ✅ CLOSED,
   NO LINT CHANGE 2026-10-12. Tested on 8 seasons of real DK box scores (2014-2021, RotoGuru + nflverse
   starter/game data), not simulation. Teams with their primary QB out (575 of 4,128 team-weeks, 13.9%):
   salary-adjusted RB-vs-WR/TE correlation is -0.022 (95% CI -0.078 to +0.035) vs -0.034 when the QB
   plays (CI -0.057 to -0.011) — essentially the same, not more negative. The claimed mechanism ("RB
   booms while WR busts") doesn't show up: that joint outcome is *less* frequent with the QB out (0.95x
   independent-odds) than with him in (1.05x). Held up across rank correlation, WR-only/TE-only splits,
   holding team total points constant, and per-season breakdown (QB-out only looked worse in 1 of 8
   seasons, n~125, reads as noise). What QB-out actually does: **both** players score less (team total
   23.6→18.9 pts) — a level drop, not an opposite-direction split. Verdict: wrong-direction-drop. No
   `CL_rb_pc_pair_no_qb` rule added, `CL_pc_pair_no_qb` left as-is (WR/TE-only). Full writeup:
   `analysis/rb_wr_no_qb_correlation/RESULTS.md`. Parking-lot note from the agent, not yet tested: whether
   the injury pipeline already lowers same-team RB/WR/TE projections when a QB is ruled OUT (separate
   question from this lint rule).

4. **Carried from the Wk5 Sunday parking lot — model-vs-FFC ownership gap on high-chalk TE/RB.** ✅
   RB SHIPPED, TE DROPPED/PARKED 2026-10-12. Not a general cap/compression at the chalk end — each player
   had a different cause:
   - **Swift ($6,200) and Gibbs' underlying mechanism — real, fixed.** Both priced above the $5,500 seg
     salary gate, so (like the Wk4 QB gap) structurally excluded from the chalk-FFC pull regardless of FFC
     rank. New RB-only top-3-by-FFC cut (`apply_chalk_ffc_rb_cut` in `scripts/ownership_v2.py`, same
     construction as the QB cut — no salary gate, re-allocated inside RB's own budget, QB/WR/TE output
     byte-identical by construction, verified on all 15 slates). Settings (k=3, b=.5) inherited from the QB
     cut, not tuned on this data. 15 DK classic slates wk1-5 2026: RB MAE 1.313→1.232, RB corr .912→.920,
     wins 4/5 weeks; leave-one-week-out held-out MAE 1.313→1.264, 3/5 weeks; no regression at $7k+/$9k+ RB.
     Shipped default-on: `DFS_OWN_CHALK_RB_CUT=3` (0 = off), `DFS_OWN_CHALK_RB_CUT_B` to override b.
     Re-grade after Wk6.
   - **McBride ($6,700) — same salary-gate cause plus a second mechanism (budget drag from cheap-TE pulls),
     both tested, both dropped for TE.** The identical RB-style cut applied to TE is wrong-direction (worse
     on 11-13 of 15 slates) — not shipped. Shielding McBride-like priced-up TEs from the drag was also
     tested and made TE worse overall — dropped. A narrower pull-up for $5,500+ TEs only is inconclusive
     (wins just Wk5 itself) — parked, re-test once 3+ more slates have a priced-up TE as FFC's slate-top TE.
   - **Likely — not our bug.** Already inside the existing chalk pull (raised to 16.1); real was 13.1, so
     FFC's 40.4 was the actual miss, not the model.
   - **Broader finding for lineup review:** FFC runs systematically hot on chalky RB/TE across all 15
     slates (+8 to +15 pt average overshoot); our shipped numbers are already closer to real in every
     salary band outside the untouched top-3. Unlike the QB case (where FFC was the accurate side), a
     large "model under FFC" gap on a chalky RB/TE is normal and usually means *we're* closer to right —
     don't reflexively flag it as a miss in Sunday review.
   - Full analysis: `analysis/wk5_postmortem_item4_terb_chalk_gap/RESULTS.md` (local). Full context in
     memory `project_wk5_parking_lot`.

5. **X injury monitor — need a Sunday-unattended workaround, this week specifically.** User will not be
   at the computer this coming Sunday (lock day). The X monitor (Chrome-based, attended) can't run
   unsupervised. Start from what Wk4's postmortem already found (item 4, `WK4_POSTMORTEM_CHECKLIST.md`):
   - `scripts/espn_diff_probe.py` + `.github/workflows/espn_diff_probe.yml` already exist as an
     unattended, browser-free backstop (diffs ESPN status on a tight cadence, escalates to a real refresh
     on a real change) — built specifically to cover gaps in the attended X monitor. Need to verify it's
     actually deployed/scheduled (Wk4 notes said manual cron-job.org setup was still pending) and decide
     if it's sufficient alone for a fully-unattended Sunday, or if something else is needed to approximate
     what the X monitor catches that ESPN's own feed lags on.
   - `scripts/inactives_timing_log.py` (Sleeper vs. ESPN timing) has never actually been run on a real
     Sunday (flagged open in both the Wk3 and Wk4 postmortems) — if it needs a human to start it, that's
     also blocked this Sunday; worth deciding whether to automate its start or skip it this week.

6. **Mobile/phone frontend UI cleanup — things are messy, ownership view broken on mobile.** User says
   some views (at minimum player ownership) can't be read correctly on the phone version of the frontend.
   Needs its own session: reproduce on a real mobile viewport, identify which views/components break
   (ownership columns specifically called out, check for others), fix layout/overflow issues.

7. **DK early slate near-miss — OPEN, real lead found, keep digging here.** Initial look (2026-10-12)
   found two different mechanisms, not one:
   - **CHI/GB (early slate): Bagent-led correlated bust, and it was flaggable.** Bagent projected 17.4,
     scored 3.18 — and every CHI pass-catcher busted alongside him (Kmet 3.5→1.8, Loveland 10.2→3.9,
     Burden 12.1→8.9, Odunze 10.2→6.0), the signature of a bad QB game dragging the whole passing
     offense down. Bagent's `games_played=2` this season drove his `season_avg`/`recent_form` to 15.8,
     feeding the 17.4 projection — but DK's own displayed average for him (`dk_avg_ppg`) was only 6.0, a
     2.6x gap. `dk_avg_ppg` already exists in the pipeline for every player but today only feeds the
     ownership model's `pub_val` (`scripts/ownership_model.py`), never the points projection. This is a
     live recurrence of an already-documented gap in `scripts/statline_model.py` (the "Cooper Rush" case:
     *"a recency-weighted average over a player's history averages only the games he appeared in... so a
     backup who started once looks like a full-time starter forever"*). Distinct from the generic
     "backup QB risk" question already closed for good in the Wk4 postmortem (Kyler Murray — price,
     QB2-gap, depth-chart signals tested and ruled out); this is a narrower, new, testable candidate:
     thin-sample (`games_played` low) vs. `dk_avg_ppg` divergence as a projection-confidence flag for
     QBs whose own recency-weighted average rests on only 1-2 starts.
   - **TB/DAL (showdown): CeeDee Lamb bust, NOT flaggable — different mechanism.** Projected 24.9, scored
     2.9, but `games_played=4` (established), `proj_targets=10.52` (normal volume), no injury/role
     signal anywhere. Reads as genuine unpredictable game-level variance on a correctly-projected
     established player, same category as Wk4's Parker Washington miss — nothing in available pre-game
     data separates this case. No further action.
   - **Next step, own session:** backtest the `games_played`-thin / `dk_avg_ppg`-divergence signal on
     2021-25 history before touching anything — one data point today, needs the same held-out-history bar
     every other change here has cleared.

## Parking Lot (add here, don't chase inline)
- **Does the injury pipeline already down-adjust same-team RB/WR/TE projections when a QB is ruled OUT?**
  Raised by the item-3 agent as a byproduct, not tested. Real effect of a QB-out game is a team-wide
  points drop (see item 3), which is a projection question, not a lineup-construction rule — worth
  checking whether `build_projections_statline.py` already captures it before assuming it's missing.
