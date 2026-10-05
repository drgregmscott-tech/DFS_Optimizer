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
- **Classic ownership position-budget gap: TE and QB totals run short of real on every slate.** Found while
  closing item 3 (2026-10-05, `scripts/grade_accuracy_week.py` output): on all 6 Wk3-4 classic slates, our
  modeled ownership undershoots the real per-slate TE total by 10-36 pts and the QB total by 2.5-10 pts
  (WR/RB/DST totals are close). This is a different mechanism from the showdown DST/kicker chalk-underestimate
  in item 8 — it's classic-format, position-level, and consistent in direction every slate, which is exactly
  the kind of persistent pattern worth a real look (not yet root-caused: could be a genuine modeled-ownership
  scale issue per position, or a downstream step — chalk-size fix, FFC blend, renormalization — not preserving
  position totals the way the raw model intends). `own_budget_walkforward.py` in
  `analysis/recal_vs_spotadjust/` already found something adjacent: TE's history-fit budget has been slowly
  drifting (113→121, 2021-25) and a rolling budget narrows slate-total error without moving player-level MAE —
  suggesting the gap is post-model normalization, not a stale learned budget. Needs its own session: pull the
  position-sum chain (raw model output → chalk-size step → FFC blend → final renorm) and find where TE/QB mass
  leaks out.
- **FLEX-WR lineup-level rebuild.** Found while closing item 2 (2026-10-05): the `cl-flex-wr-highprice-bonus`
  was zeroed (was 3.0) because it's scoped wrong — DK's FLEX slot can be any of the 4 WRs, so "a $6,300+ WR
  in FLEX" as the solver sees it means "any 4-WR lineup holding a $6,300+ WR" (92% of real 4-WR lineups
  qualify), which isn't the same thing the original slot-based history finding measured. Next step: rebuild
  the FC classic history entries with every WR's own salary, then test a real lineup-level version on
  history with the §5 controls — either (a) 4-WR vs 3-WR split by the price of the *cheapest* WR, or (b) an
  "expected slot" term weighted by the share of the 4 WRs priced $6,300+. Only ship a bonus back if a
  lineup-level effect holds up held-out. Details/scripts: `analysis/wk4_construction_review/RESULTS_flex_wr.md`
  (`flex_slot_rank.py`, `flex_bonus_cost.py`). Needs its own session, not a quick follow-up.
- **Overlapping cron-job.org triggers queue behind each other near lock.** Found while closing item 6
  (2026-10-05): `refresh_data.yml`'s `concurrency: cancel-in-progress: false` means a second run that fires
  while one is still in progress waits for it instead of running concurrently — by design (a delayed refresh
  beats a skipped one), but real runs show this costing 10-14 minutes: 10-04 19:00 (`scheduled_full_refresh` +
  `near_lock_refresh` fired the same second, second one waited 581s and then repeated identical work), 10-03
  15:00/21:00 (vegas vs. injury collision, 818s/768s waits), 10-04 16:00 (vegas run queued 636s). Fix is in the
  cron-job.org schedule (offset the cadences so a full/near-lock run and a vegas/injury run never land in the
  same minute) or a dedupe in `cloudflare_worker/scheduled_refresh.js`, not in `refresh_data.yml` itself.
- **`vegas_only` mode isn't actually light.** Found while closing item 6 (2026-10-05): `mode == 'vegas_only'`
  only skips the Vegas-pull-adjacent steps (team stats, status pull, public ownership/projections, ECR,
  props) — `build_projections_statline.py`, `status_check.py apply`, and `pivot_finder.py` still run for every
  active slate regardless of mode. Real 10-04 16:00/17:00 vegas-only runs took 17-18 minutes, at least 11
  billed job-minutes each, for what the naming implies should be a quick Vegas-only check. Needs a decision:
  is the full DK rebuild actually wanted on every vegas-only tick (new lines moving a projection is plausibly
  worth a rebuild), or should `vegas_only` skip `refresh_slate`'s build/apply/pivot steps entirely and let the
  next `full`/`near_lock` run pick it up?

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
   ✅ DONE 2026-10-05. Graded real Wk4 classic (4 contests) and showdown (DET/CAR, PIT/CLE) winning/cashing
   lineups against `CLASSIC_RULES.md` / `SHOWDOWN_RULES.md`, re-checked any drift with projection-controlled
   fits on FC history (362 classic / 118 showdown contests), and shipped what held up.

   **Shipped (commit `976f3350`):**
   - `cl-three-plus-punt-penalty` 2.5 → 0.5 (all classic presets) — no real penalty once projection is
     controlled for on 353 history contests; 2026 real fields favored 3+ punt lineups 9/13 contests.
   - `sd-stack-cap-penalty` 0.75 → 0, `sd-heavy-side-cpt-penalty` 0.5 → 1.25 in `showdown_se` only — the old
     per-extra-FLEX charge was wrong-direction past 3 same-team players on 118 history contests and 2026
     real slates.
   - **Found and fixed a real production bug**, not just a weight issue: the 2026-10-02 FLEX-WR price-tier
     terms were never added to the Cloudflare worker's parameter allowlist or the GH Actions dispatch
     workflow, so every UI classic build since then silently ran them at 0 regardless of preset — this is
     why real Wk4 builds were TE-heavy despite the "shipped" WR bonus. Wiring fixed and worker redeployed
     (`dfs-optimizer-api`, version `9d8593a0`).
   - `cl-flex-wr-highprice-bonus` 3.0 → 0 — now that the wiring fix would actually apply it, found the
     lineup-level version is scoped wrong (DK's FLEX slot can be any of 4 WRs, so the bonus pays for "any
     4-WR lineup" rather than the slot-level effect the history study measured — 92% of real 4-WR lineups
     qualify). Proper lineup-level rebuild/retest parked below, needs its own session.
   - New standing weekly tool: `scripts/grade_construction_week.py` — run `python
     scripts/grade_construction_week.py --week N` each week going forward (`--replay 20` adds an optional
     30-60 min optimizer on/off check). Report lands in `analysis/weekly_construction_review/out/wkN/`.
   - Everything else checked (DST $2.8-3.1k band, 0-punt penalty, DST-vs-own-player ban, FLEX WR mid-price
     penalty, QB-CPT-partner bonus, CPT-QB requirement, DST captain ban) confirmed again, no change.
   - Full write-up: `analysis/wk4_construction_review/` (local, gitignored, FC-derived numbers).

3. **Recalibration vs. spot-adjust — objective assessment.** ✅ DONE 2026-10-05. Opus-agent walk-forward
   analysis (`analysis/recal_vs_spotadjust/RESULTS.md`, local, gitignored).

   **Premise correction:** "QB has a standing weekly recal" was wrong — `_apply_qb_recal` is a one-time
   2021-25 coefficient fit (`data/qb_recal_config.json`), not a job that refits against new actuals. Nothing
   in the system refits weekly today.

   **Verdict: don't build an automatic weekly coefficient refit for DST, the RB/WR/TE stack, or the
   ownership model — wrong direction, evidence says drop it.**
   - DST bias is a fixed per-season offset (season-to-season SD 0.11 pts), not a weekly drift; in-season
     data gets ~0 optimal weight (n0 ≈ 75 weeks). Weekly/annual refit score identically (MAE 4.144 vs the
     shipped one-off v2 fit's 4.152) — refitting more often buys nothing.
   - RB/WR/TE stack coefficients bounce on salary/projection collinearity in-season (RB salary coef 2.62 ±
     1.20 after Wk1 vs. 1.52 in the 5-yr fit) and don't converge to a real signal; the one "gain" found
     (RB intercept refit) was an MAE artifact — bias got worse (-0.15 → -0.68) and RMSE got worse too.
   - Ownership: a weekly a+b recal is flat on MAE and makes chalk sizing *worse* on both history (-14.2 →
     -14.9) and 2026 (-8.9 → -10.1).
   - Catalog of every real Wk1-4 fix (table in RESULTS.md) shows each one was a bug, a static bias already
     visible across all 5 years of FC history (DST, the old stack, QB compression — found by a one-off
     history audit, not needing 2026 data), or a missing mechanism (who-replaces-whom, Q-return). None was
     a coefficient that drifted mid-season and needed in-season data to catch.

   **Shipped instead: a weekly accuracy/drift tracker — `scripts/grade_accuracy_week.py`.** Flags only,
   changes nothing automatically (same pattern as item 2's `grade_construction_week.py`). Run `python
   scripts/grade_accuracy_week.py --week N` after each week's results are logged (right after item 1).
   Auto-discovers played slates from `data/contest_results/`, grades current `output/final_projections_dk_*`
   against real DK results, flags PERSISTENT (season-to-date, ≥2/3 weeks same sign, |z|≥2.5) vs WEEK
   (single-week, |z|≥3) drift by position/salary tier, tracks ownership chalk sizing and position-budget
   gaps, and resets its trend window automatically when a governing config file changes. Verified against
   real Wk4 data: reproduces this week's known issues (DST +1.13 PERSISTENT pre-fix, QB -2.36 PERSISTENT,
   WR $7k+ -6.26 PERSISTENT, TE ownership budget short by 10-36 pts/slate) — on history it would have raised
   the DST/QB/stud-WR issues the same week or earlier than the manual postmortems did, with a low false-alarm
   rate (0-1 false positive across 15 history season-positions).

   **Kept standing:** full refits stay annual/offseason on the growing history pile; any *new* model still
   gets a one-time bias-by-season/tier/quintile audit against 2021-25 history before shipping (that audit is
   what would have caught DST and the stack years earlier — not a recurring job).

   **Still open, parked (tracker-flagged, not root-caused):** WR $7k+ and $4.5-7k under-projection persists
   all 4 weeks — ties into the existing stud-gap item below. QB/TE ownership totals run short on real
   slates. Showdown DST over-projected +3.1. Pick these up in a future session, not this one.

4. **Injury pipeline: ESPN lag + X-monitor override timeline, start-to-end.** ✅ DONE 2026-10-05.
   Opus-agent timeline trace using git commit times, ESPN's own `last_updated` field, and X post ids
   (Parkinson 10/4 and Coker 10/4 cases) — not estimated.

   **Finding: the manual apply chain was never the bottleneck.** It measured 2.5 min (1 slate) to ~5 min
   (4 slates) end to end. The real costs were: (1) CI's own near-lock pull cadence running up to **~55
   minutes apart**; (2) ~20 min of front-end delay in the agent reading all 5 X accounts before acting
   instead of acting on the first confirmed hit; (3) ~10 min of git-push collision overhead on Parkinson
   plus one fully duplicated chain on Coker (the known multi-session concurrency gap, in action); (4)
   ESPN's own lag, measured at 5-16 min across 3 cases.

   **X monitor reliability, now measured not estimated:** worked noon/evening, but had a **complete
   outage for the entire ~4.5hr afternoon window** (zero successful checks). Root cause per the user
   (2026-10-05): the loop needed a permission approval nobody was at the keyboard to give — not a Chrome
   bug — and the user has since reduced the standing-approval requirement, expected to fix this going
   forward.

   **Shipped:**
   - `X_INJURY_FEED_RUNBOOK.md` per-tick procedure rewritten: on a confirmed hit, act on the first
     account that confirms it (don't read the rest first), append the override row, commit/push, and
     stop — **do not** run `status_check.py pull`/`apply`/`pivot_finder.py` locally per slate.
     `status_check.py apply`'s existing `apply_manual_status_overrides()` already re-reads
     `config/manual_status_overrides.csv` on every CI run, so CI's own next pull applies the override
     to every affected slate automatically; the local apply chain only duplicated that work while adding
     real collision risk for ~3 minutes saved. Added `gh api .../dispatches -f event_type=near_lock_refresh`
     (confirmed working with the existing `gh` auth, no new token) as the immediate-trigger step instead,
     to shave the wait for CI's own cadence without re-running the heavy chain locally.
   - New unattended, browser-free backstop: `scripts/espn_diff_probe.py` +
     `.github/workflows/espn_diff_probe.yml` — pulls ESPN status and diffs against the last committed
     snapshot on a cheap, tight (5-10 min) cadence, escalating to a real `near_lock_refresh` dispatch
     only when something actually changed. This is what cuts the ~55-min CI cadence gap down without
     paying the full build+pivot cost (and its Actions-minutes budget, see item 6) on every tick, and
     covers any gap in the attended X monitor (the afternoon outage included) since it needs no browser
     or session to be open. Wired into the same cron-job.org → `cloudflare_worker/scheduled_refresh.js`
     relay as every other cadence (`kind=espn_diff`, proven reliable; GitHub's native `schedule:` trigger
     was not, see `refresh_data.yml`'s header).
   - **Manual one-time setup still needed (outside this repo's code, not yet done):** redeploy
     `cloudflare_worker/scheduled_refresh.js` (`npx wrangler deploy`), then add one cron-job.org job
     hitting the worker with `kind=espn_diff`, scoped to the same pre-lock windows
     `x_monitor_windows.py` reports, 5-10 min interval. Test via this workflow's `workflow_dispatch`
     before relying on it live.
   - **Not done:** `scripts/inactives_timing_log.py` (Sleeper vs. ESPN timing, observe-only) still exists
     but has never been run — only real way to tell if a faster primary feed than ESPN exists. Run it
     next Sunday.

5. **Permission allow-list fix — scheduled tasks re-prompting every run. DONE (2026-10-05).** Root cause
   confirmed: `.claude/settings.local.json`'s Bash allow-list entries were literal full command strings
   (exact slate ids, exact timestamped filenames), so a new timestamp or slate id never matched and every
   run re-prompted. Fixed by widening to wildcards: `status_check.py pull *`, `status_check.py apply *`
   (replacing the two one-off literal `apply` entries), plus `optimizer.py *` and `pivot_finder.py *` —
   the latter two pre-empt the same re-prompt for the "rebuild pivots" step the X-monitor SKILL.md files
   call for on a confirmed status contradiction (not yet exercised live, but same failure mode). Everything
   else in the allow-list (git, the `python -c` json reads, x_monitor_windows.py) was already fine as-is.

6. **GH Actions `refresh_data.yml` runtime — currently 10+ min on a full run, target ~50% reduction.
   ✅ DONE (2026-10-05).** Opus-agent-measured real per-job/per-step timing (not a guess) found a full run had
   grown from ~6.5min (10-01) to ~16min (10-04) in two days. Root causes, ranked by real cost: (1) biggest —
   `archive/history_data/`, a 1.75GB one-time backup committed 2026-10-02 and read by no script here, was
   being re-downloaded on every job's checkout (~28s × 11-12 jobs, ~28% of total runtime); (2) no pip cache,
   every job reinstalled `requirements.txt` from scratch (~10-15%); (3) `max-parallel: 1` serialized 5-8
   `refresh_slate` matrix legs that only needed to be serial because each one committed+pushed directly,
   racing other legs' commits (the Session 16.x incident this existed to prevent) (~30%+). `fetch-depth: 0`
   was checked and ruled out — repo history is small; it was file size at HEAD (the archive), not history
   depth. Shipped in `.github/workflows/refresh_data.yml` (commit `0244ad17`): blob:none partial-clone filter
   + sparse-checkout excluding `archive/` on every checkout step; `cache: pip` on both jobs that install
   deps; `refresh_slate` legs now upload their changed files as artifacts instead of touching git, and a new
   `commit_results` job does the one real commit+push after all legs finish, which is what made removing
   `max-parallel: 1` safe. Validated live via `workflow_dispatch` (run `37359070795`): full
   prepare→shared_pull→refresh_slate→commit_results→finalize chain succeeded, checkout times dropped from
   ~28s to 7-16s per job. That test only had 1 active slate (everything else was already locked), so true
   concurrent-multi-leg behavior is unverified until the next real multi-slate full run — check that run's
   timing when it happens. Two related gaps found but NOT fixed (out of scope for this item, see Parking Lot):
   overlapping cron-job.org triggers queuing behind each other, and `vegas_only` mode not actually being
   light.

7. **FD injury issues — diagnose what actually happened. ✅ DONE 2026-10-05.** Clarified with the user:
   the issue is Ja'Marr Chase (rostered on FD over Tee Higgins) getting hurt mid-game, and that FD build
   not cashing.

   **Verdict: confirmed true variance, no pipeline fix needed — agrees with the user's own read.**
   - Checked every `player_status_4_*` snapshot for Chase from 10/3 through pre-kickoff on 10/4: `ACTIVE`,
     no raw status flag, all week. Zero pre-game signal of injury risk.
   - Our model and the public DFF projection both correctly ranked Chase above Higgins pre-game (ours:
     14.1 proj/$9,100/15.6% own vs. 12.4 proj/$6,900/13.9% own; DFF: 17.3 vs. 12.2) — this was the right
     call with the information available at lock, not a model error.
   - The `OUT` → `QUESTIONABLE` status flips start at 19:01 UTC on 10/4 (~30 min after this game's kickoff),
     confirming the injury happened live, in-game — not a missed pre-game inactive or a feed lag the
     injury pipeline (items 4/7-adjacent) could have caught.
   - No construction angle either: this isn't a correlation/stacking issue (both Chase and Higgins show up
     across the FD pool builds for main and early), and FD's own rules (no real in-game swap window once
     locked) mean there was no realistic chance to react mid-slate.
   - **Real gap, noted but out of scope to fix today:** there's no FD contest-results export/grading
     pipeline (unlike DK's `data/contest_results/`), so "FD didn't cash" can't be quantified or graded the
     way item 1 does for DK — we're going on the user's report alone. Not worth building for one site with
     no judged export available; flagged for awareness only.

8. **Showdown-specific review.** ⏳ PART DONE 2026-10-05 (ATL/NO wasn't played yet when this ran — kicked off
   ~7:15pm CT tonight; grade it with `grade_wk4.py`/`grade_accuracy_week.py` once it's final). Opus-agent
   deep-dive, full writeup `analysis/wk4_postmortem/RESULTS_showdown_item8.md` (local, gitignored).

   **Shipped (code changed, NOT YET COMMITTED — needs a decision, see below):** Kicker FLEX ownership was
   badly under-owned (Bates 8.5% modeled vs 19.7% real on DET_CAR; Boswell 19.4% vs 32.7% real on PIT_CLE)
   — not a 2-slate fluke. Root cause: kicker FLEX ownership is sized from noisy optimizer exposure, which
   only correlates .11-.14 with the real field because our kicker projections are flat (7.9-8.3 across every
   2026 kicker, SD 0.19 in history) — tiny noise swings the rank. The real field instead rosters each team's
   kicker at a near-fixed rate regardless of projection: 23.8% for the favorite's kicker, 16.8% for the
   underdog's (97 kickers, 49 FC showdown slates, 2023-25; 2026 matches at 15-33%). Fix in
   `scripts/ownership_model_showdown.py` (`_k_prior`, `DFS_SD_K_PRIOR` env off-switch, default on): the
   top-projected live FLEX kicker per team gets that field prior instead of the exposure score; backups
   unaffected. Held out leave-one-season-out on 2023-25: kicker MAE 9.3→6.8, corr .11→.42, and overall FLEX
   MAE improves in every held-out season; on the 6 real 2026 slates kicker MAE 7.9→4.8, corr .33→.75.
   **To take effect for tonight's ATL/NO, this needs: commit + push + a showdown pool rebuild before lock —
   ask the user before doing this given it's a live-contest change close to lock.**

   **Investigated, no change:**
   - DST FLEX ownership (after the floor-fix already shipped in item 1) — same field-prior idea tested, but
     disagrees between history (helps, MAE 5.97→4.44) and real 2026 (hurts, 4.35→4.89). History-replay
     exposure doesn't behave like live exposure for DST, so history can't settle it here. **Inconclusive,
     keep testing** — re-check after 4-6 more real showdown slates. Candidate code exists
     (`sd_item8/kd_candidate.py`), not wired in.
   - Showdown DST projection +3.1 claim (from item 3's tracker) — **wrong-direction, drop.** Showdown DST
     uses the exact same `dst_model` path as classic (already covered by `dst_recal_v2`), and isolating
     primetime/standalone games (the ones that become showdown slates) in the 5-year history shows no extra
     bias vs. Sunday day games (-0.21 ± 0.22 vs. +0.06, not statistically different). The 2026 +2.46 reading
     was from pre-recal-v2 builds; ATL_NO was rebuilt after recal v2 went in, so tonight's DST numbers
     already reflect the fix. Nothing to ship, not showdown-specific.
   - Noted in passing, not acted on: kicker projections are essentially flat (would need real projection
     signal to improve further — separate, future projection-model item, not ownership).

9. **Carried over from the Wk3 postmortem — see `WK3_POSTMORTEM_OPEN.md` for full detail.** Two
   sub-items closed this session (2026-10-05, quick confirmations only — the rest below stays open,
   scoped deliberately per session-discipline rather than attempted in one sitting):

   - **Inactives timing log — CLOSED, confirmed NOT run.** `logs/inactives_timing_2026_wk4.csv` does not
     exist anywhere in the repo or any worktree. `scripts/inactives_timing_log.py` is a manual,
     terminal-attended script (must be started by hand Sunday morning) — nobody ran it. Same root cause
     as item 4's X-monitor afternoon outage (nobody at the keyboard). No code gap; this is pure execution
     — needs an explicit Sunday-morning reminder/habit, not a fix. Still a real gap: without it there's
     still no measured answer to "ESPN vs. Sleeper, who's faster," which is what item 4's
     `inactives_timing_log.py` was built to answer. Try again Wk5 Sunday.

   - **TE role-bump fix (`apply_te_replacement`) — CLOSED, checked against two real Wk4 TE-out cases,
     found a real structural gap (not shipped — single data point, and not firing was actually correct
     this week).** Real case: LA @ PHI (early slate) lost THREE pass catchers at once — PHI: A.J. Brown
     (WR, OUT), DeVonta Smith (WR, OUT), Dallas Goedert (TE, OUT); LA: Terrance Ferguson (TE, OUT), Colby
     Parkinson (TE, OUT). `wrw_te_delta_pts` was 0.0 for every TE on both teams in the live build.
     Reproduced `apply_te_replacement`'s trailing-usage inputs directly to confirm why:
     - **PHI:** the function picks the single OUT player with the *highest* trailing target share on the
       team and only proceeds if that player is a TE — A.J. Brown (.318 share) outranks Goedert (.150),
       so the whole TE-bump path is skipped regardless of Goedert's own vacancy. This is a real design
       gap: any team losing a bigger-target-share WR/RB alongside its TE1 can never get the TE bump, no
       matter how real the TE vacancy is, because the three replacement functions (`apply_rb_replacement`
       / `apply_te_replacement` / `apply_wr_replacement`) are mutually exclusive by construction (each
       only fires if its own position is the team's single biggest OUT vacator). Goedert's own row also
       failed independently on a `last_g` staleness check (his last played game trails the team's by one
       week).
     - **LA:** both OUT TEs (Ferguson .113, Parkinson .084 trailing target share) individually fall below
       the `min_tgt_share` 0.12 floor, so neither enters the vacated-share pool even combined (.197) —
       correctly reads as "no real starter lost," since Higbee (LA's actual TE1, .168 share, active) never
       lost any usage.
     - **Outcome check against real results:** not firing cost nothing this week. Ertz (PHI backup TE)
       scored 3.3 real points, in line with (slightly under) his un-bumped projection — no missed
       explosion. Higbee (LA) scored 11.7 vs. our 6.8 projection (and the real field also missed it,
       7.3% owned) — a real miss, but unrelated to the TE-bump mechanism (his own trailing share didn't
       move; reads as game-script/TD variance, not a vacated-target effect).
     - **Verdict: logged, not shipped.** The multi-position-OUT exclusivity gap is real and plausibly
       common (teams rarely lose exactly one position group), but this is one slate where it happened not
       to matter — not enough to justify a change on its own. Needs a few more real multi-position-OUT
       cases before deciding whether to make the three replacement functions additive instead of
       mutually exclusive. Logged here instead of in `WK3_POSTMORTEM_OPEN.md` since it's Wk4-sourced
       evidence on a Wk3-tracked item.

   **Still open, untouched this session (deliberately — see session-discipline note above):**
   - Track-2 candidates gated on "re-test with Wk4 data" (own-penalty, truepool coef, vac-bump k, WR/TE
     reallocation, stud-gap mismatch, QB residual gap, chalk-size fix v2 segmented, next-man-up props bump).
   - WR-out props-anchor question — do fresh pregame props already catch chalk-explosion cases the engine
     misses? Not yet tested.
   - Classic construction re-rank test (re-rank SE3max's 100-lineup pool by modeled-ownership-sum instead
     of raw projection) — not yet run, no new solves needed, data already in `pool_summary.csv`.
   - Multi-session concurrency gap (`MULTI_SESSION_CONCURRENCY_GAP.md`) — needs its own session, leading
     candidate is a lock file + shrinking the X-monitor's footprint.
   - Ownership v2 refit against the new RB/WR/TE projection-stack coefficients (shipped 10/1) — full
     history-rebuild refit never done. Scoped to its own dedicated session, not bundled into item 9 again.
