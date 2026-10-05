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
- **What's actually driving Trevor Lawrence's (and the broader cheap-chalk-QB) ownership miss.** Found
  while closing item 1 (2026-10-05): the QB `my_share` kneel-down/low-snap theory (both the attempts-only
  swap and the narrower min-snap floor) only explains a small slice of Lawrence's ~15-point miss (moves
  predicted ownership from ~3-4% to ~5-8% against 20-22% actual) — both fixes held, see item 1 writeup.
  Real driver is still unidentified. Kyler Murray's low share was also wrongly lumped into the kneel-down
  theory — his low share isn't attendance-driven at all. Needs its own session, not a quick follow-up.
- **FLEX-WR lineup-level rebuild.** Found while closing item 2 (2026-10-05): the `cl-flex-wr-highprice-bonus`
  was zeroed (was 3.0) because it's scoped wrong — DK's FLEX slot can be any of the 4 WRs, so "a $6,300+ WR
  in FLEX" as the solver sees it means "any 4-WR lineup holding a $6,300+ WR" (92% of real 4-WR lineups
  qualify), which isn't the same thing the original slot-based history finding measured. Next step: rebuild
  the FC classic history entries with every WR's own salary, then test a real lineup-level version on
  history with the §5 controls — either (a) 4-WR vs 3-WR split by the price of the *cheapest* WR, or (b) an
  "expected slot" term weighted by the share of the 4 WRs priced $6,300+. Only ship a bonus back if a
  lineup-level effect holds up held-out. Details/scripts: `analysis/wk4_construction_review/RESULTS_flex_wr.md`
  (`flex_slot_rank.py`, `flex_bonus_cost.py`). Needs its own session, not a quick follow-up.

## Open items

1. **Projections & ownership accuracy vs. Week 4 actuals.** ✅ DONE 2026-10-05. Standard post-slate
   grading: compare final projections and modeled ownership to real DK results across all slates played
   (main, early, afternoon, both showdowns once ATL/NO wraps Monday). Flag the biggest misses by
   position/player type, log real ownership into `ownership_actual_log.csv`. Feeds items 2, 3, and 8
   below — do this first.

   **Findings (full detail in `analysis/wk4_postmortem/` — local, gitignored):**
   - Correlation vs. actual: classic projections .63 (Wk1-3 avg) → .67 (Wk4); classic ownership .69 → .89;
     showdown projections .76 → .84; showdown ownership .86 → .93. Ownership clearly improved; projections
     flat vs. Wk3, up vs. Wk1-2 (edge over salary-only baseline: +.03/+.10/+.16/+.14, Wk1-4).
   - Logged Wk4 real ownership (main/early/afternoon/DET_CAR) into `ownership_actual_log.csv`. ATL/NO and
     FD out of scope (not played yet / no FD ownership export exists).
   - **Shipped:** showdown DST ownership floor bug (`exclude_skill_vs_opp_dst` in the ownership model's
     internal exposure sim was flooring every showdown DST to ~0.5%; fixed + retrained + rebuilt ATL/NO
     before lock) — `scripts/ownership_model_showdown.py`. Chalk-size fix v2 segmented, default now on
     (`DFS_OWN_CHALK_FFC_SEG`) after passing its first held-out week. DST projection recalibration
     (`dst_recal_v2`, `scripts/dst_model.py`) — 2014-17-fit intercept was running DST projections ~0.8-1.2
     pts high every season since 2021; refit intercept only, held out clean across every season/bucket.
   - **Investigated, answered, no code change:** FFC ownership disagreements are genuine wrongness, not
     staleness (re-pulling later doesn't help, MAE 10.18 vs 10.28) — FFC over-concentrates ownership into
     its own top plays. When FFC and our model disagree with FFC higher (the common case), we win ~3:1;
     closer to a coin flip when FFC is lower. Recommendation: keep trusting our model on disagreement, no
     code change needed (an adaptive down-weight-on-disagreement blend was tested and held — never beat
     the flat 0.45 blend held-out, see below).
   - **Tested and held (off by default, documented in code comments):**
     - Cheap-chalk-QB ownership tilt — wrong direction, history rules it out, dropped entirely.
     - QB `my_share` attempts-only swap (`DFS_OWN_V2_QB_ATT_SHARE`) — fixes Wk4 kneel-down artifact but
       makes 2021-25 history worse (loses real signal about unsettled QB competitions).
     - QB `my_share` min-snap floor (`DFS_OWN_V2_QB_SHARE_MINSNAP`) — same verdict as above for a sharper
       reason: 24% of historical starter-slates have a low-attempt backup game in the window, and the
       "diluted" share actually predicts those starters' real ownership well. Not a bug — see Parking Lot.
     - Adaptive FFC blend (down-weight FFC on disagreement, `DFS_OWN_FFC_ADAPTIVE`) — never beat the flat
       0.45 blend held-out on any of 2026's 12 live-FFC slates; every raw-FFC fold picked zero slope.

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
