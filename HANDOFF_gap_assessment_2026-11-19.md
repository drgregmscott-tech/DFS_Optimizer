# Handoff: DFS optimizer gap assessment, D1-D6 (2026-11-19)

Read first: `SUBAGENT_BRIEF.md` (if present), `DFS_Weekly_Process.md`, `CLAUDE.md`.

## Goal
Make the optimizer's projections as accurate as possible. Judge on projected DK points vs actual DK points.
Primary: 2021-25 leave-one-season-out (LOSO), slate-clustered bootstrap, 2000 reps, seed 20261118.
Secondary: 2026 weeks, using slate-id files only, after a roster check.
Do not validate outcomes (cash %, top-10 %). Do not frame work as beating a named product (Fantasy Cruncher is a reference, not the target).
Report MDE with every null. "Inconclusive" is not "wrong direction". Pre-declare every bar before running it.

## Working method
Opus 5.5 thinks (design, bar, review, decisions) -> Sonnet 5.5 builds -> Opus 5.5 reviews -> Haiku 5.5 coordinates.
Owner approves the action list; the Opus stage decides the rest.

## Rules
- Commits and pushes need explicit owner approval. Merges to main need explicit owner approval.
- Never commit FC-derived files or results (incl. `data/projection_stack_fd.json`, `data/fc_history/`).
- Run `git fetch` before any analysis; automated jobs push to origin.
- Stale-frame lesson: use only slate-id files pulled at the pre-lock commit. Roster-check every 2026 frame (row team vs nflverse 2026 weekly roster; under 2% mismatch passes). The week-only files `output/final_projections_{site}_{N}.csv` held 2021 rosters and were deleted (see cleanup below).
- FC-free data is required for anything committed as a fallback, with a provenance check.

## Current state (origin/main = 83dcca80, verified)
- Local main checkout is behind origin/main; fetch before reading outputs.

### D1 (simulation / QB recal): CLOSED
- Simulator mean: calibrated beats raw sim. Joint correlated simulator not shippable.
- QB recalibration: live, labelled "partly in-sample, 2026 inconclusive". Refit closed (+0.0036, CI spans 0, 2/5 seasons).
- Branch `claude/d1-part1-correlated-sims-004031` is local, unmerged. Nothing to ship.

### D2 (projection inputs): OPEN, one item (FD CI fallback, now HELD until 2026 wk14)
- Branch `claude/d2-projection-inputs-eada85` is pushed, head f2204623. Not merged to main.
- Commits on branch (not in main): c7786be1 (loud FD warning, FC-derived coefficients gitignored), ca39593c (Q pre-inactives discount, opt-in, k=0.760 refit on nflverse DK), 8f0a97e8 (schedule-based game key, BYE_OR_UNKNOWN fix), f2204623 (role-change adjustment, default off, labelled inconclusive / MAE worse).
- Already in main: 66eb8af3 (merge of earlier D2 work), which includes FD stack default-on (8f43f678) gated on the local FC-derived artifact existing.
- Ships by default: DK stack; FD stack where local FC-fit file exists; WR/RB/TE redistribution layers (on, small but real: RB and WR CIs exclude 0).
- Opt-in / off: Q discount `pre` mode (DFS_D2_QDISC_MODE=pre). Owner decision: keep opt-in, use before inactives only, not after news. Default-on waits for 2026 all-Q RMSE CI clearing zero.
- Dropped: red-zone stack feature (wrong direction, +0.004); role-change adjustment (drop, MAE worse on affected rows); QB refit (+0.0036, no gain).
- Harness fix: DFS_D2_HIST_STATUS (injury status from nflverse final report). Reruns barely moved; no labels changed. RB vacancy layer firing check passed (70/73 team-weeks in 2023-25 vs 32/32 in 2021-22).
- Reported (not verified by main session): pre-inactives k refit 0.760 on nflverse DK actuals; byte checks equal on DK and FD.
- HELD: FanDuel CI fallback (FC-free no-salary block, used only when the local FC-fit file is absent). Built and checked, NOT committed, sits uncommitted in the D2 worktree. CI stays unstacked with the loud warning.
  - Checks: leakage per held-out season all negative on RMSE (2021 -0.247, 2022 -0.229, 2023 -0.185, 2024 -0.118, 2025 -0.224; the 2021 fold has a small volume-prior leak, judged not to change the answer). Provenance 6/6 pass. Identity with FC-fit file present: DK byte-identical, FD identical apart from a new column.
  - Blocker: 2026 wk3-10 FD, active pool, 8 slates. RMSE -0.131 [-0.201, -0.052], passes. MAE +0.047 [+0.010, +0.092], CI excludes zero, worse, better in only 2 of 8 weeks. That trips the pre-declared revert condition, and it is outside the owner's waiver, which covered flat MAE only.
  - Decision (Opus stage, applied): hold. At 2026 wk14, re-score wk3-14 FD (12 slates) on a roster-checked frame. Commit only if the RMSE CI still excludes zero AND the MAE CI includes zero or sits below. Otherwise drop the fallback for good.
  - Optional pre-declared variant: 0.5 x delta. Ships only if history RMSE is -0.10 or better in 5 of 5 seasons, history MAE is no worse, and the 2026 MAE CI upper bound is at or below 0.
  - D2 is waiting for week 14 data; it will ask the owner before committing anything.
- DONE 2026-11-19: roster check on 2026 slate-id files (origin/main 63dcadda; nflverse 2026 rosters, DST rows excluded since they have no roster id). Pooled mismatch: DK classic 0.75%, DK showdown 0.29%, FD classic 0.78%, all under the 2% line. 5 of 79 individual frames sit above 2%, mostly week 1 (up to 4.0%). Passes at pooled level; those 5 frames are flagged, not excluded.

### D3 (ownership chalk identity): CLOSED, nothing shipped
- Top-K FFC blend: wrong direction (2026). alpha_top 0.6 inconclusive; alpha_top 0.8 ambiguous (top-10 +0.19, MAE about +2.9% on 16-slate frame, +1.3% on wk4-9). Concentration term: size-only, breaches MAE guardrail. Name features: inconclusive. Within-position template: worse.
- Miss decomposition: the 49 field picks outside our top 10 scored 3.3 pts lower on our projections (CI -5.6 to -1.0). Price bucket is automatic by construction, so it cannot settle projections vs price. Caveat: 1,383 actual-point rows matched by name, not player id.
- Remote branch `claude/d3-chalk-identity-794035` deleted from origin (verified). Local commit de3ac7eb (malformed-flag fix, default off) remains local. Results file `analysis/d3_chalk_identity/ALPHA_TOP_RESULTS_2026-11-19.md` is local and gitignored.
- Ownership projection-vs-price test: parked. Not run.

### D4 (calibration by position x salary tier, props anchor, ECR blend): CLOSED, nothing ships
- Calibration (a + b*proj per position x tier, LOSO): pooled RMSE improves, but CI upper < 0 in only 3/5 seasons (needs 4), dMAE worse, and 2026 (wk7-10 cheat sheets, played players) goes the wrong way (+0.187 RMSE). NOT SHIPPED. RERUN DONE 2026-11-19 on slate-id DK classic main frames, wk1-10 (2564 played rows). Verdict unchanged: NOT SHIPPED. LOSO CI upper below 0 in only 2021-23 (3/5, needs 4); dMAE worse in all 5 seasons (+0.04 to +0.22). 2026 dRMSE is now -0.050 (CI -0.22 to +0.09), so the earlier +0.187 was a stale-frame artifact, but MAE is still worse (+0.25). Inconclusive on 2026, not a pass. Results: scratch d4_rerun_results.csv.
- Props anchor: keep live 0.5 weight. Recheck at week 16.
- ECR blend (RB/TE): not evaluable (4 valid slates, need 8). Stays opt-in, default off.
- Uncommitted work in `analysis/d4_calibration/` (gitignored). Branch `claude/d4-calibration-tier-5419f1` points at main commit 6a65ef70; no commits of its own.
- Earlier D4 2026 numbers from `output/final_projections_dk_{w}.csv` were void (stale rosters).

### Cleanup: stale numbered output files (APPROVED, PUSHED)
- Branch `claude/cleanup-stale-numbered-outputs`, commit 60a9e207, pushed to origin (verified). Not merged to main.
- Deletes 46 files under `output/`: DK week-only `final_projections_dk_{1..18,23,99,MOCK}.csv`, `_fieldbase` files, `_10_BACKUP`, `_10_FORCED_TEST`, `_oldengine` files; FD `fd_10`, `fd_99`, `fd_MOCK`.
- Caller check passed: all live callers pass explicit slate-id paths. Live readers verified: status_check (refresh_data.yml passes explicit path), ownership_heuristic (hand-run only), fit_sigma_recalibration (refit path only).
- Owner should decide whether to merge it to main.

### Sigma recalibration (open question, not blocking)
- Live artifact `data/sigma_recalibration_dk.json` was fit on 2014-17 data. A 2021-25 refit exists as `data/sigma_recalibration_dk.refit-2026-09-26.json` (committed 3a5fd777), and no code loads it (guess, not diffed). Decide later whether to switch; fix the refit path's week-only read (`fit_sigma_recalibration.py:136`) first.

## Not started
- **D5, late-swap flagger (new session, scope is a guess):** after lock, flag lineup players whose status changed (OUT, inactive, newly-out Q). Suggest a swap from the same game window or later, chosen by projection. Use slate-id files and the schedule-based game key from D2 (8f0a97e8). Bar: replay 2026 wk3-11; recall 100% of real OUT/inactive lineup players whose game had not locked; at most one false flag per slate. Read-only toward DK; never submits.
- **D6, payout ledger (new session, scope is a guess):** log entry fees and payouts per contest from DK and FD contest exports, so profit can be measured (cash rate has never been checked against actual profit). Bar: ledger reconciles to site balance or history within $1 per week, 2026 wk1-11. No fabricated FD ownership. Keep account data local.

### Decisions recorded 2026-11-19 (owner delegated to Opus thinker)
- **D5 projection definition = `proj_last`** (last pre-lock frame, >= 3 DK pts). Observable n=7, best-case lower bound 0.59; the bar cannot pass at any true recall. D5 stays PARKED. Bar numbers unchanged.
- **Sigma recalibration: KEEP the live 2014-17 `data/sigma_recalibration_dk.json`.** Sigma recal rewrites only `sigma`, not `final_projection`, so projected-points accuracy is unchanged by construction. Sigma has almost no lineup consumers (lambda 0 for cash/SE/showdown, -0.005 MME). The 2021-25 refit is not validated per season, and it is coupled to an un-shipped variance artifact (`data/statline_variance.refit-2026-09-26.json`). The `fit_sigma_recalibration.py:136` item was a stale docstring, not a broken read.
- **Hygiene flag, owner decision pending:** `data/sigma_recalibration_dk.refit-2026-09-26.json` (and the FD refit and `data/projection_stack_dk_refit_2026-09-26.json`) were committed to main in 3a5fd777. The 09-26 handoff says these hold FC-derived aggregates and should not be committed unless stripped. Not touched; owner decides whether to remove or strip.

## Open decisions for the owner
1. FD CI fallback: held. Re-score at 2026 wk14. The owner's existing waiver does NOT cover a worse-MAE result, so any commit needs a new owner decision. Drop it if the wk14 rule fails.
2. Merge `claude/d2-projection-inputs-eada85` (f2204623) into main? Recommended once the fallback review and roster check pass. Brings the loud FD warning and Q `pre` opt-in into CI, and the FD stack's fallback path.
3. Merge `claude/cleanup-stale-numbered-outputs` (60a9e207) into main?
4. Sigma recalibration: switch to the 2021-25 refit later, or keep 2014-17?
