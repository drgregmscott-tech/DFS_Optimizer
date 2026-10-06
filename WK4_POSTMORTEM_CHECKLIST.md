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
- **Standing re-check: Σlog(own+.5) v2 re-rank blend for SE3max (from item 15, 2026-10-06).** Closed as
  inconclusive on history + 18 live 2026 pools — didn't clear the ship bar, no code shipped. Re-score
  cheaply as each week's SE3max pools accrue using `analysis/lineup_own_signal/check_2026.py` (just add
  the new pools). Ship bar per item 15's writeup: positive on held-out history in both comparable
  projection arms AND a 2026 result that isn't carried by one slate. Until then, stays closed/unwired.
- **Chalk-FFC fix (shipped `cbfc9db0`, 2026-10-05) may overshoot cheap backups on WR-out teams.** Found
  while closing item 11 (2026-10-06): on the Wk4 afternoon MIN slate (Justin Jefferson OUT), re-scoring
  Jennings under today's live chalk-FFC code gives 16.3% modeled vs 9.9% real ownership, driven by an FFC
  number of 48.8 that ran well ahead of what actually happened. One data point, not enough to act on, but
  worth checking again once more WR-out slates with the chalk-FFC fix live have been played.
- **Showdown skill-player FLEX ownership miss on ATL/NO — root-caused 2026-10-06, keep-testing, no ship.**
  Full session (Opus/general-purpose agent, `analysis/wk4_postmortem/RESULTS_showdown_skillplayer_flex.md`,
  local/gitignored): pooled FC showdown history (49 slates 2023-25, usable here unlike the K/DST case) with
  all 7 real 2026 showdown slates. Pooled skill-FLEX accuracy is fine (LOSO MAE 3.92, corr .91, bias +0.03);
  ATL/NO's 5.27 MAE is the worst of 7 but not a wild outlier. No cross-slate, sign-consistent positional bias
  — backup/change-of-scenery QBs get *under*-owned on other slates (Dart, Young), opposite of Penix's
  over-ownership; Penix repeating the same direction on both his 2026 slates is the one real thread but n=2.
  The TE/RB2 miss traces to a narrow, real cause: ATL/NO was the one slate (of 7) with a flat four-way TE
  group instead of one clear lead TE — exactly where the exposure model's known small-projection-gap-swings-
  ownership weakness (same mechanism already fixed for kickers) bites. Tested the obvious fix (QB/RB/TE
  position dummies in the ridge features) — made everything worse everywhere, including ATL/NO itself,
  because FLEX ownership is water-filled to a fixed budget after the raw score and the ridge fit ends up
  fighting a budget mechanism it can't see; a real fix needs `_waterfill`/`predict` itself to be
  position-aware, out of scope for a time-boxed session. **Verdict: watch, don't build.** Re-open when 2-3
  more slates repeat either shape: a Penix-style QB over-ownership, or another flat/no-favorite TE or RB
  committee slate — then there's enough n to fit a real feature with a wiring plan through the water-fill.
- **Classic PERSISTENT flags from `grade_accuracy_week.py --week 4` (2026-10-06) — WR $7k+ piece
  [CLOSED 2026-10-06, confirmed stale-snapshot artifact]; DST/QB/TE/general-WR pieces still open, same
  trigger.** After fixing the tracker's per-format fallback gap (see item 1 fix log / commit `a962958b`),
  classic showed PERSISTENT flags: DST +1.13, QB -2.36, TE -0.76, WR -1.04 (plus salary-tier breakdowns,
  worst: WR $7k+ -6.26). The track-2 WR $7k+ stud-gap follow-up (`WK3_POSTMORTEM_OPEN.md`, same day)
  confirmed this exact suspicion for WR $7k+: a full 2021-25 current-code rebuild shows no real bias at any
  point in the season, and the 2026 Wk1-2 `output/` files are confirmed to predate current code (missing
  `engine_projection`, can't be reproduced by rebuilding) — so the WR $7k+ -6.26 flag was the stale
  pre-fix snapshot, not new drift. Root cause of the false flag: `grade_accuracy_week.py`'s current-era
  detection only tracks `GOVERNING_CONFIGS` (JSON files) by commit date, with no visibility into
  engine-code-only fixes (e.g. the WR-out redistribution / RB replacement bump, shipped as code commits)
  — those don't move the era window, so stale Wk1-2 files can still read as "current." DST/QB/TE/general-WR
  were NOT tested by this follow-up (it was WR $7k+-only) — same trigger still applies to those: once
  Week 5's classic slates lock and get graded, re-run `python scripts/grade_accuracy_week.py --week 5`.
  If they still show PERSISTENT with a genuine current-era week in the mix, that's real drift; if they
  shrink, same artifact. If they persist, the actual fix is adding engine-code commit dates to the
  era-detection window, not a projection change.
- **Trevor Lawrence / cheap-chalk-QB ownership miss — root-caused and fixed, SHIPPED 2026-10-06.**
  Real driver was never the QB `my_share` feature (that theory, closed 2026-10-05, only explained a small
  slice). The actual cause: the chalk-seg FFC pull (`apply_chalk_ffc_seg`) that's supposed to correct
  exactly this kind of miss is structurally blind to QBs for two independent reasons — (1) its $5,500
  salary gate was tuned for WR/TE price tiers, but chalk QBs cost $5.5-7k (Lawrence $5,900, Darnold exactly
  $5,500, both failed the `<` test); (2) its top-15-FFC cut is shared across all positions, and a 20%-owned
  QB (one roster slot) ranks below the slate's RB/WR/TE chalk (2-4 slots each) — Lawrence was 16th on
  wk4_main, Darnold 16th on wk4_afternoon, so even removing the salary gate didn't reach them. Fix: QBs now
  get their own top-3-by-FFC cut, no salary gate, re-allocated inside the QB budget only — RB/WR/TE output
  is byte-identical by construction, zero regression risk. 12 classic 2026 slates (only sample FFC exists
  for): QB corr .815→.843, QB MAE better on 11/12 slates, wins 3 of 4 leave-one-week-out weeks. Lawrence
  9.6→13.5 / 7.2→11.2 against real 22.2/19.9 — real improvement, still ~8pts short (remaining gap is in the
  base QB model, not the FFC pull). Shipped as `DFS_OWN_CHALK_QB_CUT=3` (default on) in `scripts/ownership_v2.py`.
  Re-grade after Wk5 (2026-only sample, FFC doesn't exist in 5-year history — same precedent as chalk-seg
  itself). Found a data bug in passing: `ffc_dk_dk_classic_wk3_main_27Sep2026.csv` was a byte-copy of the
  wk3_early file (ingest wrote the wrong table) — parking-lot, needs an md5-duplicate guard on the FFC
  ingest. Kyler Murray investigated 2026-10-06 — see below, **HOLD, not the rushing theory.**
  Full writeup: `analysis/wk4_postmortem/qb_chalk_lawrence/RESULTS.md` (local, gitignored).
- **Classic ownership position-budget gap: TE and QB totals run short of real on every slate — ROOT-CAUSED
  2026-10-06, NO SHIP.** Full session (Opus agent, `analysis/wk4_postmortem/te_qb_budget_gap/RESULTS.md`,
  local/gitignored): the v2 pipeline conserves TE/QB budget mass exactly through every step (vac bump →
  chalk-seg → QB cut) on a 12-slate 2026 production replay — there is no downstream leak. Two different,
  separate findings instead:
  - **The QB "gap" was a grading artifact, not real — FIXED 2026-10-06.** The full-file QB total is 98.6-100
    against real 99.5-99.9 (true gap ~1 pt). `grade_accuracy_week.budget()` was inner-joining to the contest
    export before summing, which dropped the 5-8 pts/slate v2 puts on 30-45 undrafted backup QBs (the live
    pool projects far more thin backups than the history training pool did, because the history rebuild gave
    most backups proj 0) — that's where the reported -2.5 to -10 came from. Fixed by summing the model side
    from the full per-slate `output/final_projections_dk_<sid>.csv` file instead of the matched rows
    (reporting-only change, re-verified on Wk3-4: QB gap now reads -0.1 to -1.2, matching the ~1pt true gap).
  - **The TE gap is real but is a 2026 field-level shift plus individual chalk misses, not a budget problem.**
    History real TE total/slate is 116.8±7.2; 2026 is 125.3±12.1 (Wk3-4: 128-149). Not predictable from slate
    features (value-feature corr only +0.37 in history). Inside a slate the shortfall sits on specific TE
    chalk (Mayer 33% real vs 2% ours, Kelce 31/16, Strange 14/4, Kincaid 21/10) — that's the chalk-size
    problem (item above), not the position budget. Tested and dropped: static TE budget refit (LOSO/rolling/
    2025-mean — wash or worse on history, worse TE MAE 10/12 2026 slates), adaptive per-slate TE budget
    (same), QB budget = 99.8 (worse QB MAE 12/12), tail-cut-and-respread (worse on relevant rows 12/12,
    chalk bias improves but that's the chalk-size fix's job). One kept-alive thread: an in-season (2026-only)
    TE budget was a noise-level wash on only 3 weeks of data — re-test with `step7_inseason_te.py` after Wk5-6
    if the 2026 TE total stays ≥125.
- **FLEX-WR lineup-level rebuild.** Found while closing item 2 (2026-10-05): the `cl-flex-wr-highprice-bonus`
  was zeroed (was 3.0) because it's scoped wrong — DK's FLEX slot can be any of the 4 WRs, so "a $6,300+ WR
  in FLEX" as the solver sees it means "any 4-WR lineup holding a $6,300+ WR" (92% of real 4-WR lineups
  qualify), which isn't the same thing the original slot-based history finding measured. Next step: rebuild
  the FC classic history entries with every WR's own salary, then test a real lineup-level version on
  history with the §5 controls — either (a) 4-WR vs 3-WR split by the price of the *cheapest* WR, or (b) an
  "expected slot" term weighted by the share of the 4 WRs priced $6,300+. Only ship a bonus back if a
  lineup-level effect holds up held-out. Details/scripts: `analysis/wk4_construction_review/RESULTS_flex_wr.md`
  (`flex_slot_rank.py`, `flex_bonus_cost.py`). Needs its own session, not a quick follow-up.
- **Kyler Murray — rushing theory tested and rejected on history; real cause is a `my_share` staleness case,
  HOLD. Investigated 2026-10-06.** Full 2021-25 LOSO check (86 slates, same frame as `qb_share_refit`):
  rushing volume has ~zero correlation with the model's ownership miss (|r| < .04 for p3_car / recent rush
  yards / season rush yds/g). There IS a real cheap-rusher pocket (QBs < $6.5k with 25+ rush yds/g get 1.25x
  real ownership vs. predicted, holds 3/5 seasons, ~+1 pt) but it's small, and adding `p3_car` or a
  rush-yards feature to the live ridge model doesn't move Kyler (predicted 4.7→5.2 against real 19.8) and
  doesn't clear the ship bar (p3_car coefficient ~0, wins only 38/86 slates; a season-rush-yards variant is
  better in all 5 seasons but Wk1-3 live doesn't confirm it). **On history Kyler is actually predicted fine**
  (31 starts, real 5.44 vs. predicted 5.41) — 2026's miss is a live-only artifact of his `my_share` feature
  reading stale/diluted: 0.00 in Wk1 (traded to MIN, no games in the team's 3-game window yet), 0.33 in
  Wk3-4 (he left Wk1 early after 5 attempts). Forcing `my_share=1` largely closes the gap (Wk1 aft 5.3→15.3
  vs real 19.8; Wk4 aft 3.8→8.0 vs real 17.7) but no generic fix clears the live bar: filling zero-`my_share`
  QBs is flat on history and worse on 2026 (corr .684→.616-.658); a "no-share" dummy calibrates history but
  still loses on 2026, because the field faded OTHER zero-share starters that week (Daniels, Jones, Mariota,
  Bagent) while playing Kyler up — a generic flag can't tell them apart. **Open question for next pass:**
  what actually separates Kyler from those faded zero-share starters — price vs. the backup's projection
  gap, or a projected-starter/depth-chart signal we don't have yet. Test frame (`noshare_dummy.py`) is ready,
  ~2 min/variant, in `analysis/wk4_postmortem/qb_rushing_murray/` (local, gitignored). Same family as the
  already-held `DFS_OWN_V2_QB_ATT_SHARE` / `DFS_OWN_V2_QB_SHARE_MINSNAP` switches — not a new mechanism.
- **FFC ingest wrote the wk3_early table to wk3_main — FIXED 2026-10-06.** `ingest_public_ownership.py` now
  hashes the picked table's content (player/salary/proj_own, order-independent) and compares it against
  every other already-saved `ffc_{site}_*.csv` before writing; a byte-identical match to a different
  slate_id aborts the save instead of silently overwriting (two real slates should never share one 50-row
  FFC table). Deleted the known-corrupt `ffc_dk_dk_classic_wk3_main_27Sep2026.csv` (was a copy of
  wk3_early) so it can't poison future re-grading — downstream code already treats a missing FFC file as a
  safe no-op (falls back to the pub_val-only artifact), so losing that one file is strictly safer than
  keeping wrong data.
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

8. **Showdown-specific review.** ✅ DONE 2026-10-06 (ATL/NO graded; two Opus-agent passes, full writeup
   `analysis/wk4_postmortem/RESULTS_showdown_item8.md`, local/gitignored).

   **Shipped and confirmed: kicker FLEX field-rate prior (`DFS_SD_K_PRIOR`, default on).** Committed and
   pushed same day (`f3b09d64`); GitHub Actions had a real platform-wide outage that evening (confirmed via
   status.github.com), so the ATL/NO pool was rebuilt locally to get the fix live before lock
   (`sd_k_prior_applied=True` verified on Folk/Carlson). Root cause: kicker FLEX ownership was sized from
   noisy optimizer exposure (corr .11-.14 with the real field, because our kicker projections are flat,
   7.9-8.3 across every 2026 kicker) — the field instead rosters each team's kicker at a near-fixed rate
   regardless of projection (23.8% favorite's K, 16.8% underdog's K, 2023-25 FC history). ATL/NO was the
   first genuinely out-of-sample test (not in the fit, not in the original 6-slate check) and it missed on
   this one slate (K MAE 2.4→5.8) — a pick'em game (NO favored by only 1.2) where the field split the
   kickers almost evenly and both ran ~1 SD light on total kicker ownership, ordinary noise, not a
   structural break. Two tweaks were tested to fix the miss (spread-graded favorite weight, scaled-down
   prior level) — both made overall FLEX worse on history and on the other 6 real slates, so neither
   shipped. Across all 7 real 2026 slates the prior still wins clearly: kicker MAE 7.13→4.93, corr .36→.72,
   overall FLEX MAE 4.06→3.92. **Kept as shipped, no change.**

   **DST FLEX field-prior: tested, now DROPPED (not shipped).** Same prior idea for DST was inconclusive
   after the first 3 real slates; with ATL/NO added (4 real slates post-floor-fix) it's now a clear drop —
   helps on 3 of 7 live slates, hurts on 4, pooled DST MAE gets worse (4.11→4.49) and adds +2pts of bias
   on top of an already-well-calibrated production DST (+0.3 bias, 1.82 MAE on the 3 post-fix slates).
   Root cause of the history/live disagreement was run down (not just asserted): history-replay DST
   exposure (`l_exp`) runs structurally low vs. live (mean -1.37 vs -0.64) because the FC-derived history
   replay pools only contain the ~32 FC-listed players per slate vs. full DK pools live — confirmed this
   isn't the floor-bug artifact (history features predate both the bug and its fix). Conclusion: **history
   cannot be trusted to judge K/DST exposure-based ownership questions in showdown** (the kicker prior is
   unaffected since it doesn't use `l_exp`) unless the replay pools are rebuilt at full depth — not
   attempted, real scaffolding work, not worth it for one DST question.

   **Showdown DST projection +3.1 claim (item 3's tracker):** wrong-direction, dropped — showdown DST uses
   the same `dst_model`/`dst_recal_v2` path as classic, and isolating primetime/standalone games in 5-year
   history shows no extra bias vs. Sunday day games. The 2026 reading was from pre-recal-v2 builds.

   **New finding, not yet acted on — candidate for the next showdown ownership session:** ATL/NO's real
   FLEX miss wasn't K/DST at all, it was skill-player ownership — Penix (QB2) over-owned by 22pts, Kamara
   over-owned by 18pts, cheap TEs and RB2 Bijan/B.Robinson under-owned by 13-16pts. Parked, needs its own
   look.

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
     this week).** Real case: LA @ PHI (early slate) — PHI: DeVonta Smith (WR, OUT), Dallas Goedert
     (TE, OUT); LA: Terrance Ferguson (TE, OUT), Colby Parkinson (TE, OUT). `wrw_te_delta_pts` was 0.0 for
     every TE on both teams in the live build. Reproduced `apply_te_replacement`'s exact `outs` filter
     (not just the raw trailing-usage table — an earlier pass through this check skipped the `last_g`
     staleness gate and wrongly implicated A.J. Brown, who is correctly on NE now per the live DK salary
     file and was correctly excluded by that same gate; corrected before shipping this note) to confirm
     the real cause:
     - **PHI:** of the two OUT players, only DeVonta Smith (.270 trailing target share) passes the
       function's own filters — Goedert himself is filtered OUT of the vacancy pool by the `last_g`
       staleness gate (his last tracked game trails the team's current index by one week) before the
       position check even runs. Smith, a WR, becomes the team's single top OUT vacator, and the function
       only proceeds if that player is a TE — so the whole TE-bump path is skipped. This is a real design
       gap: any team losing a bigger-target-share WR/RB alongside its TE1 can never get the TE bump, no
       matter how real the TE vacancy is, because the three replacement functions (`apply_rb_replacement`
       / `apply_te_replacement` / `apply_wr_replacement`) are mutually exclusive by construction (each
       only fires if its own position is the team's single biggest OUT vacator).
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

   **Everything else that was still open under item 9 is promoted to its own item below (10-14)** —
   `WK3_POSTMORTEM_OPEN.md` is kept only as the detail store for the track-2 watch list (item 10) and the
   earlier history on each; it is no longer the active to-do list, this checklist is. One topic per
   session still applies — pick ONE of 10-14 per session, don't batch them.

10. **[Wk4 triage + both follow-ups done 2026-10-06; Wk5 still owed]** Track-2 candidates re-tested
    against real Wk4 data, then the two follow-up questions it raised were each tested on full 2021-25
    history. Full updated verdicts in `WK3_POSTMORTEM_OPEN.md`'s "Track-2 watch items" section. Summary:
    nothing newly shippable, but two real findings closed out and one real lead identified for projections.
    **Own-penalty fading** — closed for good, perfect ownership loses too. **Truepool coef** — Wk4 alone
    is a small win but pooled Wk1-4 still a wash, stays off. **Vac-bump k=1.0** — confirmed correct on
    held-out Wk4 ownership, no change. **WR/TE reallocation** — still inconclusive (n=5 this week); found
    the multi-position-OUT exclusivity gap (item 9) has a second real example (Hockenson). **Stud-gap —
    [CLOSED]**: the full-history week-of-season split found no real WR $7k+ bias anywhere in the season;
    the PERSISTENT -6.3 flag was a stale-snapshot grading artifact (2026 Wk1-2 `output/` files predate
    current code and can't be reproduced by rebuilding) — this also resolves the WR $7k+ piece of the
    Parking Lot's "Classic PERSISTENT flags" item. Found a real gap in `grade_accuracy_week.py`'s
    current-era detection: it only tracks JSON config commit dates, not engine-code-only fixes, so stale
    weeks can still read as current — worth fixing once confirmed it causes more false flags. The
    `--week 23` convention is re-confirmed correct, keep it. **QB residual** — closed verdict holds for a
    2nd week (best MAE of the season, 4.5). **Chalk-size fix v2 segmented** — this watch item's premise
    was stale, it already shipped 2026-10-05 and passed its first held-out week; re-confirmed again this
    session. **Next-man-up props bump** — flips to wrong-direction-drop (MAE worse, ~zero correlation with
    the field's real miss). The price-split follow-up on full history **confirmed half the hypothesis**:
    cheap (<$5k) and mid ($5-7k) replacements are genuinely under-owned by us every season (real field
    owns them ~2× what we predict) — but "expensive ones are over-owned" didn't hold on production data,
    that was a history-base-is-injury-blind artifact. Root cause traced to the **projection, not
    ownership**: our cheap-replacement point projections run ~2 pts low, which is why ownership (which
    tracks projection) misses too. Next step is retesting with the WR-out redistribution included and
    loosening the RB replacement bump's `points_scale` (0.65) for cheap backups specifically, held out by
    season — a projection-side fix, not an ownership-side one. Re-run all of item 10 again once Wk5
    results land.

11. **WR-out props-anchor question. ✅ DONE 2026-10-06, no ship — plumbing is fine, props just can't size a
    chalk explosion.** Opus-agent test, full writeup `analysis/wk4_postmortem/RESULTS_item11_props_anchor.md`
    (local, gitignored). Props only exist for Wk3-4 (classic) and Wk2-4 (showdown), so this is a small
    live-data check by necessity — usable fresh-at-lock cases: DeVonta Smith OUT (Wk4 early+main, PHI
    backups Wicks/Lemon) and Justin Jefferson OUT (Wk4 afternoon+main, MIN backups Addison/Hockenson/
    Jennings). Legette (Wk3) was stale — props pulled before the OUT news broke; Chase/Coker/McConkey were
    in-game injuries, not pregame WR-out cases, out of scope.

    **Plumbing confirmed clean:** the props-driven projection shift survives all the way through to
    `estimated_ownership_pct` — the projection stack only dampens its own correction term, not the props
    component, and both ownership models read the post-props `final_projection`. Nothing downstream washes
    the signal out (corrects an open question in the brief: `own_vacated`/`own_vac_bump` were suspected
    swapped, checked and they're not — no bug there).

    **Props help, but only partly, and 0.5 (today's default) is already near-best:** re-scoring the real
    live builds at props_weight 0/0.5/1.0 shows 0.5 closes 15-55% of each beneficiary's ownership gap
    (Wicks 16.2 -> 20.1 vs 25.8 actual); pushing to 1.0 adds only 1-3 more points and makes WR/TE ownership
    error flat-to-worse across all three test slates.

    **Root cause of the remaining miss: the props market itself can't distinguish an explosion from an
    ordinary promotion.** Lemon's market bump (2.2x engine) was bigger than Wicks's (1.9x) but Lemon drew
    3% real ownership against Wicks's 26% — the market signal doesn't rank-order correctly here. A direct
    "market edge" ownership bump (fit on one week, checked on the other) only moved error ~0.02-0.05 and
    didn't fix chalk sizing — left unshipped, logged as keep-testing in the parking lot below, not killed
    outright (one train/test split, not enough to call it dead).

    **The signal that does separate them is raw FFC public ownership** (Wicks 39 vs Lemon 6 vs Addison 70)
    — already live via the chalk-FFC change shipped 2026-10-05 (`cbfc9db0`), after these slates locked;
    under today's code it alone lifts Wicks 11.35 -> 20.1, same ballpark as the props blend. **Verdict:
    nothing new to ship for props specifically — the chalk-FFC fix already shipped is doing this job.**
    See parking lot for one watch item this surfaced.

12. **Classic construction re-rank test. ✅ DONE 2026-10-06, no ship — real limit found one level deeper.**
    Pure re-rank on existing pool data (no new solves), Opus-agent deep-dive, full writeup
    `analysis/classic_rerank/RESULTS.md` (local, gitignored — uses FC-derived history). Paired test across
    18 real-2026 SE3max pools (9 Wk1-3 slates x 2 seeds, two independently-built pool sources) plus 20
    held-out 2022-25 history pools.
    - **Ranking by modeled-ownership-sum alone: wrong-direction, drop.** +.048 / -.021 / -.078 percentile
      across the three comparable sets; no within-pool signal on history.
    - **Projection+ownership blend (weight ~0.5-1): inconclusive, keep testing at a low bar, not shipped.**
      Net effect ~+.01 percentile pooled; the one apparent win (A/cap50, +.054) comes from 2 of 9 slates
      (wk2_main, wk1_early) — drops to +.014 excluding them. Datasets disagree on sign for several variants
      (e.g. lean-contrarian w=-.5 is +.09 on one pool source, -.17 on the other) — flagged as noise, not a
      lever. No production code changed; `scripts/optimizer.py`'s `_rank_lineups_by_projection` untouched.
    - **Real finding: the pick rule isn't the main limiter, our ownership model's lineup-level signal is.**
      On the identical held-out history pools, picking the most-owned lineup by **real** post-lock
      ownership adds +.10 to +.13 percentile and +10 to +40 cash points over the current projection pick —
      confirming the Classic Lineup Study's "chalk cashes" effect holds inside our own pools. Picking by
      **our modeled** ownership instead adds -.08 to +.01 — i.e. `estimated_ownership_pct` has decent
      player-level accuracy (~.8 corr) but ~zero signal at the lineup-sum level once projection is held
      fixed (partial corr of modeled-own vs. real finish, controlling for proj: history ~0 today vs. ~+.18
      with real ownership).
    - **Next concrete step (not this item, needs its own session):** train/score ownership at the
      lineup-sum level, not just per-player — target is that partial-corr gap (~0 → closer to +.18) on the
      20 already-graded history pools (`analysis/lineup_replay/hist_lineups_graded.csv` + `builds/hist`).
      If a future ownership-model change closes even half that gap on held-out history, re-run
      `analysis/classic_rerank/rerank_test.py` — the re-rank lever itself is proven worth ~+.10 percentile
      per pick once ownership is accurate enough. Wiring plan for that future test already drafted in
      RESULTS.md (`_rank_lineups_by_proj_own`, env `DFS_RANK_OWN_W` off-switch, called at optimizer.py's two
      pool-ranking call sites ~3116/~4189).

13. **Multi-session concurrency gap.** Done (2026-10-06) — full writeup/status in
    `MULTI_SESSION_CONCURRENCY_GAP.md`. Root cause: the real Wk4 collision was the interactive session and
    a scheduled `x-injury-monitor-*` task both running the full local pull/apply/pivot/push chain inside a
    live window; item 4's decided fix (push-only, let CI's apply pick it up) was written into
    `X_INJURY_FEED_RUNBOOK.md` on 2026-10-05 but never applied to the 5 live scheduled-task prompts, which
    were still telling Claude to run the heavy chain. Fixed by rewriting all 5
    `~/.claude/scheduled-tasks/x-injury-monitor-*/SKILL.md` prompts to push-only + rebase-retry-on-reject,
    and generalizing the same pattern to interactive sessions in the runbook. Lock file / dispatcher not
    needed — only one real collision in git history, and it's now explained and closed at the source.

14. **[CLOSED 2026-10-06, found stale]** Ownership v2 refit against the new RB/WR/TE projection-stack
    coefficients. This was already run and rejected on 2026-10-01 —
    `analysis/ownership_v2_refit_after_projstack/RESULTS.md`: the new stack shifted projections almost
    uniformly (corr to old proj 0.985-0.991) with little ranking change per slate×position, so there was
    nothing for a refit to recalibrate; LOSO refit on the new features was flat-to-worse than just
    swapping the feature. Verdict: wrong-direction, drop. No further action.

15. **Lineup-level ownership signal. ✅ DONE 2026-10-06, no ship. The gap was mostly a stale-model artifact.**
    Opus-agent re-analysis of existing pools, no new solves. Full writeup: `analysis/lineup_own_signal/RESULTS.md` (local,
    gitignored, FC-derived). It covers all 63 built history SE3max pools, 2022-25 x 3 projection arms, re-graded from
    `hist_meta`, plus the 18 live-settings 2026 pools.
    - **Why item 12 saw ~0:** `builds/hist/*/final_projections` (09-29) carry the **pre-v2** layered ownership model. Production
      v2 lives in the 10-01 `ourproj` regen, which was never joined to these pools. Scored with v2 refit
      leave-one-season-out (held-out), the partial corr of lineup own vs real finish given proj goes from -.040 to
      **+.084 as a sum and +.111 as Σlog(own+.5)**. Real post-lock ownership gets +.105 / +.133 on the same 63 slates.
      Item 12's "+.18 ceiling" came from its 21-slate subset, where real is +.20. The held-out v2 number is ~the same as
      in-sample (+.093), so it is not a fit artifact. The log-sum adds about +.03 for ours and for real alike, positive in
      all 4 seasons. Max-owned player, top-2, spread and the count of 20%+ players carry little. The signal is "fewer
      low-owned darts", not "one max-chalk play".
    - **Re-rank pick with z(proj)+w·z(Σlog v2), w chosen leave-one-season-out: inconclusive, keep testing, not shipped.**
      History arm new is +.032 pct [-.017,+.081] (23-12 W-L). Arm old is -.019 and arm fc is +.046. On 2026 there is no gain
      outside wk2_main. Inside the top 30 projected lineups, where the pick happens, our signal halves (+.057, real +.088).
      Even perfect real ownership gives an unstable pick gain on 63 slates (+.10 / .00 / +.04 by arm). Plain v2 sum re-rank:
      drop. **No production code changed.**
    - Re-test cheaply as Wk4+ SE3max pools accrue (`check_2026.py`). Wiring if it ever clears: item 12's
      `_rank_lineups_by_proj_own` scoring Σlog(own+.5), env `DFS_RANK_OWN_W` default 0. Item 12's RESULTS.md line "our
      modeled ownership has no within-pool signal on history" describes the pre-v2 model only.
