# Post-Week 4 Checklist (created 2026-10-05)

Working task list, not a conclusion — nothing below has been investigated yet. Results: DK cashed main MME,
main SE, and afternoon SE; FD had injury-related issues (not yet diagnosed); Parker Washington's early-only
SE miss is confirmed true variance (right role/opportunity, just didn't convert — not worth digging into,
see item 7). Overall a clear step up from Week 3.

## Session discipline (same rule as the Wk3 postmortem, still applies)
One session = one topic from this list. A new idea that comes up mid-session goes in the Parking Lot below,
not into the current discussion. Dump anything unresolved into the Parking Lot at session end with enough
context to pick back up cold. A session that fully resolves one narrow question beats one that touches five
and resolves none.

## Parking Lot (add here, don't chase inline)
(empty — nothing parked yet)

## Open items

1. **Projections & ownership accuracy vs. Week 4 actuals.** Standard post-slate grading: compare final
   projections and modeled ownership to real DK results across all slates played (main, early, afternoon,
   both showdowns once ATL/NO wraps Monday). Flag the biggest misses by position/player type, log real
   ownership into `ownership_actual_log.csv`. Feeds items 2, 3, and 8 below — do this first.

2. **Winning-lineup/construction-rule review — should become standing weekly cadence, not just this week.**
   Separate from projection/ownership accuracy: look at what actually won/cashed this week (classic and
   showdown) and check whether `CLASSIC_RULES.md` / `SHOWDOWN_RULES.md` still hold up, or need an
   adjustment/addition based on real winning construction this week. Same grading motion as item 1 but
   aimed at construction rules instead of player-level projections. Going forward this should run every
   week as part of the standard post-slate review, not just get added ad hoc — fold it into whatever
   process item 1 ends up being.

3. **Recalibration vs. spot-adjust — objective assessment.** Right now there's no standing "recalibrate
   against this week's actuals" job for anything except QB (which has its own recal/autopromote layer).
   Everything else (RB/WR/TE/DST projections, the ownership model) gets fixed by ad hoc postmortem-driven
   patches. Decide, with evidence: is spot-adjusting outliers the right model, or has enough real data
   (4 weeks now) accumulated to justify a lighter-weight recurring refit for some pieces? Don't assume the
   answer — look at what a recalibration cadence would actually have changed this season vs. what the
   current ad hoc fixes already caught.

4. **Injury pipeline: ESPN lag + X-monitor override timeline, start-to-end.** ESPN is the nominal gold-standard
   status source but is lagging real news by enough that the X monitor exists as a rescue — confirmed again
   on the Colby Parkinson case (10/4 ~15:40Z, UnderdogNFL ahead of ESPN). The manual override-and-rebuild
   chain took an extra 5-10 minutes end to end. Before picking a fix, **trace the full current timeline**
   step by step (X post appears → read/judgment → write override → re-pull status → apply to each affected
   slate → rebuild pivots, per slate) and measure where the time actually goes. Only then evaluate whether
   scripting the apply chain is a net win (vs. just moving the bottleneck) or whether a faster primary status
   source would cut more time with less new surface area. Don't default to "automate the apply chain" without
   checking this first — flagged explicitly by the user as worth getting right, not rushing.

5. **Permission allow-list fix — scheduled tasks re-prompting every run.** Root cause confirmed:
   `.claude/settings.local.json`'s Bash allow-list entries are literal full command strings (exact slate ids,
   exact timestamped filenames), so a new timestamp or slate id never matches and every run re-prompts.
   Fix: widen the relevant entries to wildcard patterns (`Bash(python scripts/status_check.py apply *)`,
   `Bash(python scripts/status_check.py pull *)`, etc.) so routine, already-proven-safe commands stop
   prompting, while leaving anything genuinely risky ungated. Agreed, low-risk, do this early.

6. **GH Actions `refresh_data.yml` runtime — currently 10+ min on a full run, target ~50% reduction.**
   `refresh_slate` runs as a `max-parallel: 1` matrix (deliberately serialized to avoid matrix legs racing
   each other's git commits) — with 5-6 active slates most weeks, that's 5-6 fully serial jobs, each paying
   its own checkout + `pip install` + network pulls + commit/push/rebase. That's a meaningful chunk of the
   hour-to-lock window. Needs real investigation, not a guess from reading the YAML: instrument where time
   actually goes per step, then evaluate pip caching and/or restructuring so legs don't each commit
   individually (letting them run in parallel again without the race) as the two likely levers.

7. **FD injury issues — diagnose what actually happened.** User flagged FD had injury-related issues this
   week, separate from the Parkinson/Spears X-monitor catches (which worked correctly). Needs its own look:
   what went wrong on FD specifically, was it a pipeline gap or a one-off.
   *(Parker Washington's early-only SE miss is explicitly NOT part of this — confirmed true variance, drop it.)*

8. **Showdown-specific review.** DET/CAR and ATL/NO (once played) grading — same ownership/projection
   accuracy check as item 1, scoped to showdown. Persistent DST/kicker-as-cheap-FLEX-chalk underestimate
   (seen on PIT/CLE) — check if it recurs.

9. **Carried over from the Wk3 postmortem, still open — see `WK3_POSTMORTEM_OPEN.md` for full detail:**
   - Track-2 candidates gated on "re-test with Wk4 data" (own-penalty, truepool coef, vac-bump k, WR/TE
     reallocation, stud-gap mismatch, QB residual gap, chalk-size fix v2 segmented, next-man-up props bump).
   - TE role-bump fix (`apply_te_replacement`) — check against a real Wk4 TE-out case.
   - WR-out props-anchor question — do fresh pregame props already catch chalk-explosion cases the engine
     misses? Not yet tested.
   - Inactives timing log — confirm it ran and ran correctly on Wk4 Sunday.
   - Classic construction re-rank test (re-rank SE3max's 100-lineup pool by modeled-ownership-sum instead
     of raw projection) — not yet run, no new solves needed, data already in `pool_summary.csv`.
   - Multi-session concurrency gap (`MULTI_SESSION_CONCURRENCY_GAP.md`) — needs its own session, leading
     candidate is a lock file + shrinking the X-monitor's footprint.
   - Ownership v2 refit against the new RB/WR/TE projection-stack coefficients (shipped 10/1) — full
     history-rebuild refit never done.
