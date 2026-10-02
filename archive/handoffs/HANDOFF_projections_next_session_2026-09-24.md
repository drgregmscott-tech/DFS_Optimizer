# HANDOFF -- projections: maximize accuracy NOW (written 2026-09-24, for a fresh session)

Read this file first, then the four it points to (section 9). It is written to be
self-contained: a new session should be able to start work from section 5 without
re-reading the old chat.

## 0. The mission, in Greg's words

"We have to get better. No excuses. The point of this is to get better -- outside
sources or ideas or whatever -- but we have to come up with something more effective
than it has been. I don't expect projections to be perfect, but we need them as good
as they can get." And for this handoff: **improve the projections the absolute
maximum we can, right now, no delays.** Weekly post-slate refits (ownership refit,
recalibration once new results are logged) are a separate, deferred, recurring job --
do NOT let them crowd out what can be improved today.

Hard clock: Week 3 Sunday classic slates lock **2026-09-27 17:00 UTC (1:00 PM ET)**
(FD afternoon 20:05 UTC). The Thursday Atl@GB Showdown already locked
(2026-09-25 00:15 UTC). Anything worth shipping for Week 3 must be validated and
pushed before Sunday.

## 1. Working agreements (learned the hard way this session)

- **Heavy analysis goes to an Opus subagent** (`Agent` with `model: "opus"`; memory:
  `feedback_opus_for_heavy_work.md`). Greg said "opus 5.5" -- there is no 5.5; use
  the `opus` model option. Keep routine edits/verification in the main session.
  Brief subagents completely (they start cold), tell them research-only vs code, and
  **verify their headline numbers yourself before relaying** (see section 4: the
  Opus matchup-factor claim shrank by ~2/3 when I re-ran it).
- **Rigor over reassurance** (`feedback_rigor_over_reassurance_in_construction_testing.md`):
  state the real confidence basis, sanity-check strong results, never smooth over
  pushback. n is tiny (2 real weeks) -- say so every time.
- **I overstated once already.** After the reconcile fix I told Greg bias was
  "essentially eliminated" (+3.24 -> +0.11). True, but bias is not accuracy: the
  ownership session then showed ranking did NOT improve (section 3). Report BOTH
  bias and ranking metrics from now on.
- **Backtest rebuild hygiene.** Rebuild slates only leak-free: wk1 = `--season 2025
  --week 23`; wk2 = `--season 2026 --week 2` and played-week zeroing must be
  disabled (no switch exists yet -- build it, section 5 step A0). Restore `output/`
  with `git checkout -- output/<files>` afterwards; never commit test rebuilds.
  **Never swallow stderr on batch rebuilds** (`> /dev/null` hid a silent failure this
  session and produced a bogus "post-fix" comparison). Check every build prints
  `Wrote N players`.
- **Parallel sessions share this repo.** Untracked/uncommitted files from another
  session are not yours: stage explicit paths, never `git add -A`. Fetch and rebase
  before push (`git fetch origin; git log HEAD..origin/main`); automated refreshes
  land constantly.
- Windows tool flakiness: `EUNKNOWN ... lstat`, `unable to load netapi32.dll`,
  `python3` Store-alias permission errors are transient -- retry, or use `python`.
  An Edit that reports an EUNKNOWN error may have actually applied; re-read the file.
- Commits/pushes for fixes have been pre-approved by Greg in this project's flow;
  handoff docs were committed when he said so. Cloudflare Worker deploys:
  `cd cloudflare_worker/optimizer_api && npx wrangler deploy optimizer_api.js`.

## 2. State of the repo right now (origin/main as of 2026-09-24)

Shipped and live:
- **Reconcile fix** (`scripts/statline_model.py` `reconcile_team_shares()`): raw_sum
  is hist_team-aware; plus QB depth-chart suppression (`apply_volume_prior`,
  `pass_price_share` and `pass_mu` zeroed for depth-chart non-#1 QBs).
- **Guard for the fix's own bug** (ownership session, commit `0c09a0f`, Greg
  approved): depth-chart QB1 who changed teams counts toward raw_sum; QB with no
  depth-chart entry on a team whose chart names a QB1 is suppressed; backstop
  `QB_PASS_ATT_CAP = 55` clamps + warns.
- **Recommended-lineup feature removed** everywhere (commit `f30d552`; worker
  redeployed). `analysis/showdown_own/best_single.py` keeps a generalized
  `candidates()` and an uncalled `score()`.
- **Ownership work** (other session): FFC public ownership ingest
  (`scripts/ingest_public_ownership.py`, `data/ownership_public/`), FFC variant
  artifact, DK FLEX budget split RB49/WR34/TE17, `pub_val` feature, frontend shows
  model-vs-FFC ownership with a disagreement flag. Week-2 real-ownership log bug
  (dropped FLEX rows) fixed; `log_ownership.py` now refuses low totals.
- Week 3: 6 slates ingested (DK main/early/Showdown Atl@GB, FD main/early/afternoon),
  in `data/current_slate.json`, projections + lineup batches + pivot suggestions
  pushed. User uploaded slates to the frontend himself.

**Critical gap: the Week 3 `final_projections_*` currently in the repo were built
BEFORE the guard** (wk3 main reconcile still shows `MIN/pass raw_sum 10.92, target
30.13, scale 2.76x`; Murray 9.5 pts / 13.7 att, Brosmer 7.0 pts). Murray is
confirmed MIN's starter this weekend (Greg, 09-24), so that is a real
mis-projection. The guard is committed, so the next automated refresh (or a manual
`build_projections_statline.py` rebuild) fixes it -- **confirm a post-guard rebuild
has actually landed and inspect it before Sunday** (section 5 step 0).

Uncommitted at time of writing: `HANDOFF_projections_external_sources_and_accuracy.md`
(the Opus report + my verification block) and this file -- both committed with this
handoff.

## 3. Honest scoreboard (do not lose this)

Source: `analysis/proj_recheck/notes.md` (ownership session, 254 player-weeks,
proj>8, 6 DK classic slates, leak-free rebuilds; OLD = committed pre-fix outputs).

| | OLD (pre-fix) | FIX (reconcile fix, no guard) | FIX + stack |
|---|---|---|---|
| bias (proj - actual) | -3.37 | -0.40 | +0.13 |
| MAE | 6.41 | 6.83 | 6.46 |
| RMSE | 8.98 | 9.90 | 8.44 |
| Spearman within slate x position (22 cells) | .226 | .201 | .184 |
| mean actual pts of projected top-N | 16.06 | 14.79 | 15.28 |

Read it plainly: the fix removed the level bias but **did not improve ranking, which
is what lineup building needs** (top-N actual points fell, paired CI -2.59..-0.10).
Cause: the fix's own blow-up on moved starting QBs (Cousins LV 134 att / 62 pts vs
actual 15.8; Murray MIN 57 pts vs actual 0.6; Geno NYJ, Willis MIA) -- now guarded.
Excluding those four, wk1 QB R2 goes .27 -> .37 (.50 with stack), so the fix is
real for everyone else. **The guard has been validated only on the blow-up cases
(bias/RMSE/corr per slate in `HANDOFF_projections_model_review.md` section 10) --
the full 6-slate table above has NOT been re-run with the guard in.** That re-run is
the new baseline every later change must beat (step A).

Shipped-lineup-rule drop (3/6, .703 -> 1/6, .583): ~2/3 was this blow-up bug, the
rest is noise (5% projection noise alone moves a slate ~0.2 percentile). n=6 slates
cannot distinguish any lineup method; do not tune lineup methods on it.

## 4. What Opus found (full report: `HANDOFF_projections_external_sources_and_accuracy.md`)

Method: error log (`data/projection_error_log.csv`, **Weeks 1-2 only -- no wk3
actuals exist yet**), DK meaningful cut n=157 player-weeks, joins reproduced the
known headline numbers first.

1. **`matchup_factor` hurts.** `season_avg` in every output file = `final_projection
   / (matchup_factor*vegas_factor)` (`build_projections_statline.py:739`), so it is a
   free ablation. Opus (pre-fix data): Pearson .402 -> .500, monotone in an exponent
   sweep, both leave-one-week-out folds positive, isolates to matchup (vegas ~neutral).
   Mechanism: `SHRINKAGE_K_GAMES = 4.0` in `scripts/projections_matchup.py` (~line 83,
   used in `matchup_factors()` ~line 190) is far too weak on 1-2 games; factor swings
   0.66-2.21x. **My re-run on the post-fix (pre-guard) pipeline: direction holds,
   magnitude ~1/3 of the claim** -- Pearson .318 -> .350, Spearman .430 -> .468;
   matchup-only variant worst (.259), vegas-only best (.365). Not re-run: exponent
   sweep, LOWO, calibration slope. And it predates the guard (blow-up QBs inflate the
   noise), so re-measure on the guarded rebuild before sizing the fix.
2. **Sigma/ceiling miscalibrated** (pre-fix data, level bias removed): 17.8% of real
   scores exceed `statline_p90` (should be 10%), only 68% inside p10-p90 (should be
   80%); implied sigma ~7.4 vs realized residual std 9.1. Quantiles come from
   `np.percentile` of the Monte Carlo draws in `statline_model.py` (~lines 2338-2339);
   `sigma_recalibration.py:119` explicitly does not touch p10/p90. Do after item 1
   (item 1 moves the mean the distribution is built around).
3. **Calibration slope 1.25** on the meaningful cut (spread compressed: studs
   under-projected, mid-tier over); QB slope 0.64 / intercept +9.6, corr .244 (QB
   barely rank-orders). Level fix does not fix slope. Cheap to re-measure post-fix.
4. **Ensembling test (proxy):** blending z-scored `final_projection` with DK
   `AvgPointsPerGame` (free, already in salary files) gives an in-sample gain (.402
   -> .439 at 37.5% weight) but **fails one of two LOWO folds** (wk1 +.05, wk2 -.016).
   Not shippable on 2 weeks.
5. **Negative results (don't spend time):** per-player learned bias (wk1 vs wk2 error
   r = -0.011); "did he play" for the meaningful cut (1.9% of rows); game-environment
   quartile bias is non-monotone; RB/WR floor players' own bias is +0.10 (Opus ranks
   the floor-share gap BELOW items 1-3; caveat: that measures the floor players, not
   the upstream dilution they cause -- needs a with/without rebuild to settle).
6. **External sites (checked live 09-23):** Daily Fantasy Fuel -- server-rendered,
   robots allow, DK+FD, 446 players, per-row `data-` attributes (`ppg_proj`, `inj`,
   `starter_flag`, `depth_rank`, `proj_score`, `opp_rank`, L5/L10/season avg), point
   totals only, best scrape target. WinWithOdds -- server-rendered DataTables, DK only,
   820 players, includes real DK slate IDs (kills FFC-style fuzzy slate matching),
   zeroes non-playing depth players, but self-describes as prop-derived (likely
   correlated with our props anchor; do not scrape its `/api/` or `/download/`).
   Fantasy Life -- best data (floor/proj/ceiling/own) but only source is a
   robots-disallowed `/api/` endpoint + virtualized grid: **do not automate**. All
   three serve only the current week; **every week not logged is lost forever**.
   Not checked: whether DFF/WWO archive past weeks (10 minutes; would unblock
   backtests immediately).

## 5. Action plan (ordered; the "no delays" list)

**Step 0 -- Week 3 safety, first thing.** Confirm a post-guard rebuild of all 6 wk3
slates is on origin/main (check `output/statline_reconcile_*wk3*.csv`: MIN pass scale
should no longer be 2.76x; no QB > 50 pass att; unlisted backup QBs ~1 pt). If not,
rebuild (commands in `DFS_Weekly_Process.md` Step 2i; wk3 uses `--season 2026 --week 3`,
`--vegas-slate-id dk_classic_wk3_main_27Sep2026` for all non-main slates), push. Eyeball
side effects the ownership session flagged: 41 wk3 backup QBs drop to ~1 pt; 84
non-QB players shift slightly via team pass volume.

**Step A -- Re-baseline with the guard (must precede everything else).**
 A0. Add the switch to disable played-week zeroing for backtest rebuilds (open item
     in the projections handoff header; without it wk2+ rebuilds leak results).
 A1. Leak-free rebuild of the 6 real DK classic slates (wk1 x3 with `--season 2025
     --week 23`; wk2 x3 with `--season 2026 --week 2`, zeroing off) on current
     code; check every build succeeded; restore `output/` afterwards.
 A2. Recompute the section-3 table (bias, MAE, RMSE, within-slate x position
     Spearman, projected top-N actual, per-position QB/RB/WR/TE) on the guarded
     build. `analysis/proj_recheck/accuracy.py` already does this -- reuse it. This
     is the number every subsequent change must beat, on ranking metrics, not bias.

**Step B -- matchup shrinkage (Opus R1; likely the biggest ranking lever).**
 B1. On the guarded rebuild, redo the ablation properly: exponent sweep on
     `market_factor**alpha` (or matchup only), per-slate Spearman, LOWO with BOTH
     folds required non-negative, bootstrap CI. This decides whether R1 is worth
     more than ~+0.03 Pearson.
 B2. If it holds: make the shrinkage `k` a function of games played this season
     (strong in Weeks 1-4, relaxing later) in `projections_matchup.py`, not a bigger
     constant and not a global exponent. Rebuild, re-run A2's table, require ranking
     improvement, not just correlation. Delegate the sweep/implementation-checking to
     Opus; verify its numbers.
 B3. Loop-back (section 0 of the projections handoff): this changes `final_projection`
     again -- note impact for anyone using pivots/lineup tooling.

**Step C -- calibration slope / spread (Opus item 3).** Re-measure the slope by
position on the guarded, B-adjusted build. If studs are still systematically
compressed, test a monotone spread correction (e.g., isotonic/linear recalibration
fit on wk1/wk2, validated LOWO). QB is its own problem: slope .64 -- investigate why
QBs barely rank-order (thin history, Vegas-anchored team volume, cap interactions)
before adding any correction.

**Step D -- sigma / p10-p90 coverage (Opus R3).** After B/C. Build a PIT/coverage
test (where does each actual fall in its simulated distribution; histogram should be
flat; p10/p90 coverage near 10/80/10 on held-out weeks). Suspects: TD dispersion too
low; yards and TDs treated as independent when real big games are correlated. This
touches the Monte Carlo core -- measurable pass/fail, medium-to-major effort.

**Step E -- start logging external projections today (Opus R2), data-only.** New
`scripts/ingest_public_projections.py` modelled on `ingest_public_ownership.py`
(name+salary matcher, `data/projections_public/{site}_{slate_id}.csv`), DFF first
(regex over `<tr class="projections-listing">` data attributes), WWO second (header
assertion; HTML only). Wire into `refresh_data.yml` next to the FFC step. Do NOT wire
into the projection build yet. First spend ~10 minutes checking for past-week archive
URLs on DFF/WWO (Not checked by Opus; if they exist, the blend test becomes
runnable now). Also cheap: log DK `AvgPointsPerGame` alongside (already in salary
files) so the ensembling test gets more folds automatically.

**Step F -- Week 3 real results -> third fold.** After Sunday/Monday games: run Stage 7
(`derive_actual_results.py` for FD; DK results export -> `log_results.py`) and Stage 6
(`log_ownership.py`, sum ALL rows per player incl. FLEX). Wk3 becomes fold 3 for every
LOWO test above (LOWO with 2 folds is weak); rerun B1, ensembling, sigma coverage.
This is the "deferred weekly" work -- but it is also the fastest source of statistical
power, so schedule it the moment results post.

**Step G -- props/stack first live use.** No props snapshot existed for any wk1/wk2
classic slate, so `props_model.py` has never run on a real slate; `props_auto.py`
pulls near lock. On wk3 builds, watch the `Props anchor: adjusted N player(s)` and
`Projection stack: adjusted N` log lines and sanity-check a handful by hand (props
weight 0.5, clamp 0.5-1.8x engine mean). Stack verdict from the recheck: neutral to
mildly positive, keep. Do not tune props before there is any real-slate evidence.

**Step H -- RB/WR floor-share gap (deprioritized, not dead).** Measure the actual harm
with a with/without rebuild before touching fitted curves (`data/volume_prior_dk.json`
/`_fd.json`, fit on 2014-2021). Naive "zero the dead weight" made RB worse earlier
(ratio .74 -> .68; team-sum normalization only scales down) -- any fix must
renormalize among eligible players. A free depth/role prior from DFF/WWO
(`starter_flag`, `depth_rank`, zeroed depth players) could feed the existing
`depth_chart` parameter in `apply_volume_prior()` once Step E has data.

**Step I -- downstream ownership rebuild + refit (do not forget).** Ownership inherits
every projection change. When the projections work above is final for the week:
rebuild the 6 wk1/wk2 DK classic slates with the final code (leak-free), refit BOTH
`data/ownership_model_dk.json` and `data/ownership_model_dk_ffc.json` via
`scripts/fit_ownership_model.py` (`fit(..., feats=...)`; FFC variant =
`om.FEATURES + om.FFC_FEATURES`), then refit again after wk3 real ownership is logged.
Memory: `project_ownership_model_state.md`; details in `HANDOFF_ownership_model_review.md`
section 7.

**Every build, every week (cheap watch items):** `WARNING share reconciliation ...
clamped`; any team pass `scale` > ~1.5 or QB pass att > 50 in
`output/statline_reconcile_*.csv` (offseason/in-season movers are the exposure).

## 6. Decisions needed from Greg

1. Approve step B2's approach (games-played-dependent shrinkage) once B1 confirms it,
   vs. dropping matchup entirely for the first N weeks (simplest, larger change).
2. Comfortable shipping a projection change for Sunday's slates based on 2 weeks of
   evidence if it clears "both LOWO folds + ranking improves"? (Recommendation: yes
   for B, no for anything that only clears in-sample.)
3. Green light to build the DFF/WWO logging ingest and add it to the automated refresh
   (scraping public HTML pages only; DFF robots allow, WWO HTML page only).
4. Fantasy Life: keep it manual-only (recommended -- API is robots-disallowed), or ask
   FantasyLife+ about a sanctioned export?
5. Whether to hand ranking-quality work (Steps B-D) to Opus subagents end to end with
   me verifying, or in smaller checkpoints.

## 7. Carryover from the ownership chat (so nothing is lost)

- FFC ingest is integrated and runs in the automated refresh; variant artifact and
  layered model refit on corrected real ownership (leave-one-week-out, meaningful cut:
  corr .639 -> .676 pub_val -> .764 +FFC; chalk bias -7.9 -> -6.8 -> -4.1). Remaining
  gap: cheap-crowd plays (Mayer/Jones/Schultz types) still under-estimated.
- Tested, no gain (don't retry without new data): sharper softmax; last-week
  ownership; salary change; last-week points; injured-teammate vacuum; stacked-optimizer
  exposure / team-QB-share / teammate exposure (`analysis/ownership_diag/stacked_exposure_notes.md`);
  heavier FFC blending.
- Lineup-method verdicts: chalk-anchor + real-ownership pivot is 2-3/6 (~.72-.75), not
  4/6 (.819) (real ownership had lost every FLEX row); live-substitution pivots add
  zero; shipped rule re-scored 1/6 (.583) -- ~2/3 of the drop was the QB blow-up bug;
  n=6 cannot separate methods. Do not tune lineup methods on it.
- Showdown: DK Showdown support for `recommend_lineup.py` was built and validated on 2
  slates, then removed with the feature (Greg: didn't like it, too slow). `HANDOFF_showdown_*.md`
  files exist from earlier Showdown ownership work.
- Ownership open items are in section 5, Step I; `log_ownership.py` guard prevents
  another FLEX-less log.

## 8. Known gotchas / conventions

- Season/week: real Week 1 = `--season 2025 --week 23`; Week 2+ = `--season 2026 --week N`
  (also for Showdown -- format does not change lookback). Slate ids are the full raw-file
  stem (`dk_classic_wk3_main_27Sep2026`). One shared Vegas pull; other slates pass
  `--vegas-slate-id`.
- `data/projection_error_log.csv` has Weeks 1-2 only (2,709 rows; Showdown players logged
  twice, CPT rows 1.5x -- use FLEX rows for base values). It is pre-fix output, so
  `final_projection` there is the OLD pipeline; recompute from rebuilds.
- `season_avg == recent_form` in every row by design. DK/FD share nothing for DST label:
  DK `DST`, FD `D` (use `optimizer.DEFENSE_POSITION_LABELS`).
- Reconciliation math: exclusive component (pass) target = team predicted attempts;
  `scale = target/raw_sum` applies to every rostered player; `raw_sum` excludes
  hist_team mismatches (my fix) except depth-chart QB1 (guard).
- Frontend is a static site reading GitHub live; slates are uploaded via a native file
  picker only the user can operate.

## 9. Files to read, in this order

1. This file.
2. `HANDOFF_projections_model_review.md` -- header open-action list, sections 5-9 (the
   reconcile-fix trace) and section 10 (ownership session's re-check + guard).
3. `analysis/proj_recheck/notes.md` and `accuracy.py` (the baseline harness).
4. `HANDOFF_projections_external_sources_and_accuracy.md` (Opus report; section 0 is my
   post-fix verification).
5. `HANDOFF_ownership_model_review.md` section 7; memory index
   `C:\Users\gmsco\.claude\projects\C--Users-gmsco-Desktop-DFS-Optimizer\memory\MEMORY.md`.
