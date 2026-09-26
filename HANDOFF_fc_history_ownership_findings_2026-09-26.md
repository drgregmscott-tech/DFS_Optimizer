# HANDOFF -- Fantasy Cruncher (FC) history and the ownership model (written Sat 2026-09-26)

FC data is subscription data and this repo is PUBLIC: `data/fc_history/` is gitignored. Do not commit FC data or
anything derived from it. This doc records method and conclusions only.

## What exists (committed)
- `scripts/fc_history_etl.py` -- normalizes FC "Lineup Rewind" exports -> `data/fc_history/derived/fc_master.csv`, QA report.
- `scripts/fc_history_map.py` -- maps FC players to gsis `player_id` (tiers: alias, week, season, global, name_mapping, any-pos,
  name-only, first-name prefix; DST = `DST_<TEAM>`), validates FC `score` vs DK points from nflverse weekly_stats (99.2% exact
  on 31.6k rows, 2021-2026) and RotoGuru 2021 (99.9%). Alias table: `data/fc_name_alias.csv`.
- `data/weekly_stats_2022/2023.parquet` added (needed for the mapping).

## Conclusions (confirmed / rejected / open)
CONFIRMED
- FC single-entry ownership == our real DK ownership logs on 2026 (corr .999). It is a valid ownership label set, 2021-2025.
- Production ownership model is systematically miscalibrated in shape, on history AND on real 2026: too few 10-20% players
  (2026: 11.2 pred vs 19.8 real), top player too high (66% vs 54%), too much on $7k+, too little on $5.5-7k.
REJECTED (don't retry)
- Refit the base ownership layer on FC history -- with FC's projection OR with our regenerated projection. Projection-to-ownership
  corr in history is ~0.40 for both (ours .391 vs FC .383, same 23,278 rows); history-only model is too flat; layered with the
  2026 pub_val/FFC layer it only ties the honest baseline (n=2 weeks, within noise). No artifact shipped.
OPEN
- Calibration fix (salary-tier $5.5-7k correction, softer top-end cap, or flatter logistic scale): fit on 2026 real weeks,
  use FC-history shape as acceptance prior. Do after Week 3 real ownership is logged (3 folds).
- FC projection accuracy vs actual points vs OUR projection accuracy: NOT yet measured (the ownership test is not a projection test).
- Re-run the layered refit once wk3 is logged.

## Tooling to reuse (analysis/ownership_fc_refit/, untracked scripts)
- `run_ourproj.py` regenerates OUR pre-game projections for 2021-2025 (reuses analysis/backtest_multi leak patches: depth/injury
  stubbed, closing lines from nflverse_games.csv, prior-week-only matchups, props off; salaries from FC single-entry). 88 slates in ~9 min.
  Missing vs production: props, injuries/inactives, depth charts, role overrides, weather, pub_val, FFC.
- `build_ourproj_features.py`, `evaluate_ourproj.py`, `evaluate.py`: features and the full evaluation (LOSO on history + real 2026 test).
- `data/team_stats_2022/2023.parquet` (public nflverse) were downloaded for DST projection; untracked.

## Week 3 checklist
1. Log real wk3 ownership (sum ALL rows per player incl. FLEX). 2. Fit calibration candidates on wk1-3 with leave-one-week-out.
3. Accept only if it improves the 10-20% tier count/catch without hurting 20%+ catch; compare shape to FC history.
4. Refit both artifacts (dk + dk_ffc) per HANDOFF_week3_weekend_and_refit_plan_2026-09-25.md section 4.

## Addendum (Sat 2026-09-26): post-hoc calibration tested, NOT shipped
Tested power/temperature, $5.5-7k multiplier, top-end cap (and combos), position totals held fixed, leave-one-week-out on 2026
wk1-2 (FFC path, 6 slates), plus FC-history direction check. Nothing implemented; production unchanged.
- The 10-20% undercount is a DISCRIMINATION problem (many real 10-20% players ranked <10%), not a shape problem: no
  total-preserving transform moves the predicted 10-20% count past ~13 (real ~19.8). Earlier "shape fix" idea was too optimistic.
- $5.5-7k multiplier (x1.3-1.45) is the one effect that holds in history AND 2026 (tier total 304->352 vs real 346), but it costs
  20%+ precision (.71->.65, ~+1 false chalk call/slate) and 10-20% catch. Cap 60 is harmless but rests on 2 players.
- Retest after Wk3 as a pair (mid-tier multiplier + cap 60-65) on 3 folds; the real fix likely needs new features (value rank /
  public value), not calibration. Calibration scripts were in the scratchpad (not saved in repo).

## Addendum 2 (Sat 2026-09-26): projections work, PARKED items and verdicts
User principles: DFS changes every year so recent seasons matter more, don't demand huge samples; small projection changes can flip
optimizer choices so judge at LINEUP level (not only Spearman/RMSE); FC snapshots are true pre-lock; user has only a 1-week FC trial
(ends Fri 2026-10-02) so FC = calibration benchmark, not a weekly input. FC 2024 wk1-4 is an FC bug (unavailable).
Verdicts (research scripts in analysis/proj_*; outputs gitignored under data/fc_history/derived/):
- Matchup (already neutral for skill positions in production): lineup-level, no evidence of benefit (flips not net positive); sample can
  only detect ~5-6 lineup pts. Keep OFF; not proven harmless.
- FC blend (35% FC): +6.6 lineup pts unfiltered, but mostly FC's inactive knowledge (+2.0 with perfect DNP filter, n.s.). Not a live lever.
- Injury/inactive: perfect filter worth ~+4.5 lineup pts; FC zeros ~+2.0 (n.s.); teammate redistribution HURTS (do not add).
  Ranked to-do: game-day inactives pass 60-75 min pre-lock; zero-flag cross-check vs DFF/WWO with Sunday refetch (e.g. wk3 DFF has
  Nico Collins inj=O vs production QUESTIONABLE); cap non-QB1 QBs ~0; Questionable haircut needs nflverse injuries data (not downloaded).
- Leak found: output/final_projections_dk_dk_classic_wk1_main_13Sep2026.csv at HEAD is post-lock. Use commits cefc761 (wk1) / 7e57cfe (wk2).
  The old proj_recheck guarded frame used HEAD; redone pre-lock, no conclusion flips.
PARKED - early-season (Week 1): production wk1 gives price 0 weight and leans on last season; player-level this ranks WORSE than price-only
in 5/5 seasons (esp RB/TE). Candidate: floor the price weight ~0.75 for veterans on the wk1 sentinel path (statline_model.apply_volume_prior),
keep last-season efficiency. NOT shipped. Before shipping: rebuild 2026 wk1 with real depth chart, more wk1 slates (2018-20 RotoGuru),
refit volume_prior_dk.json (fit on 2014-2021, stale era). wk2-4 candidate fixes (carryover, higher price floor) neutral/worse.
PARKED - more FC data: user will pull showdown + early/afternoon slates + Week 3 post-slate during the trial; send one sample of each layout
so the ETL can be verified first (priority: wk3 post-slate, showdown recent seasons, early/afternoon recent seasons).
HARNESS CAVEAT: regenerated history (ourproj) stubs depth chart -> QB guard can't find QB1 -> starters ~24 pass att vs 33 actual; earlier
history-based QB claims (slope 1.05, QB under-projected 2.5) are unreliable. QB calibration needs production-like inputs.

## Addendum 3 (Sat 2026-09-26): QB, sigma, SEA, manual-status fix
- SEA wk3: Darnold confirmed active by user; no override needed. DFF (Thu night) and WWO (Thu morning) had Lock as SEA QB1 -> public snapshots can be
  stale; any zero-flag cross-check needs a Sunday-morning refetch. Commit a489bc6: config/manual_status_overrides.csv now also feeds the BUILD
  (statline_model._apply_manual_status_to_pull), so a manual QB1 OUT promotes the backup (before, it zeroed QB1 only after the build; backup stayed ~1 pt).
  Inert without a row for the week (byte-identical wk3 main). Scenario tested: Darnold OUT -> Lock 14.8 pts / 30.4 att.
- Automation gap: ESPN feed = designations only; QUESTIONABLE flags but changes nothing; no game-day inactives feed; last status pull Thu 9:09pm ET.
  Build later: verified inactives source + scheduled pull/apply 60-75 min pre-lock + rule for questionable QB1 (probability weighting = design choice).
- QB (production-faithful rebuild with guard): earlier harness QB claims withdrawn. Slope <1 every full season (.57-.80), spread too wide, top QBs
  over-projected, bias small; QB1 pass att over-projected +1-2. Candidate: QB = a + b*proj (b .64-.89 by week bucket), lineup effect +1.5..+1.7 (CI incl. 0),
  positive 2023-26, negative 2021-22. Needs stack refit on guarded history + wk3 actuals. Not shipped. Low backup starters (Mariota 9.8, Winston 8.4) look low.
- Sigma/p10/p90: sigma column roughly calibrated; RB/WR/TE ~5-15% too wide in 2023+ (z_sd .85-.93); p10 (QR) fine; raw MC over-dispersed (yards double-count:
  yards_cv fit as total CV then multiplied by a gamma latent; sim yards sd 1.8-2.1x actual); TD dispersion NOT too low at any position; FC floor/ceiling worse than ours.
  statline_p90 has no consumer. Fix later: fit yards_cv net of latent, refit sigma_recalibration on 2021-25 (interim: x0.90 on RB/WR/TE), QR p90.
- LAMBDA FINDING: presets cash and se_gpp use lambda=0.063 (data/optimizer_presets.json; from 2018-21 sweep, "suggestive not conclusive", +0.006 <1 SE). Bare-ILP test
  on 88 slates 2021-25: lambda .063 vs 0 = -5.1 lineup pts (CI -10.5..+0.1), negative in all 6 seasons, cash rate .114 vs .227; sigma is ~97% collinear with mean so it
  mostly penalises studs. Caveats: no stacks/constraints, cash proxy from 2 contests. MME lambda -0.005 unaffected. Verify with full optimizer before changing default.

## CHANGES MADE FOR WEEK 3 (2026-09-26)
1. `statline_model._apply_manual_status_to_pull` (commit a489bc6): manual status overrides feed the build so a QB1 OUT promotes the backup. Inert w/o a row.
   Use: add `3,<Player>,<TEAM>,OUT,<note>` to config/manual_status_overrides.csv, push, dispatch a refresh. Delete the row to revert. `week` must match.
2. Cash and SE/3-Max lambda 0.063 -> 0 in `data/optimizer_presets.json` and the frontend built-in presets (`dfs_optimizer_frontend/index.html`, BUILTIN_PRESETS).
   MME unchanged (-0.005). USER-SAVED CLOUD PRESETS ARE SEPARATE -- if any saved Cash/SE preset has lambda 0.063, edit it by hand.
   Revert = set both back to 0.063. Evidence: bare-ILP replay, 88 slates 2021-25, -5.1 lineup pts (CI -10.5..+0.1), negative all 6 seasons; NOT yet verified with the full
   optimizer (stacks/constraints); old sweep (2018-21) was +0.006, <1 SE. Re-verify after wk3 actuals.
3. ECR per-slate archive (commit 63e8673): data/ecr_archive/ecr_{slate_id}.csv written by scripts/archive_ecr.py in refresh_data.yml (fail-safe, data only). Confirm files appear after
   the next full refresh; if the workflow step never runs, check the Actions log.
4. FC tooling committed: scripts/fc_history_etl.py, scripts/fc_history_map.py, data/fc_name_alias.csv, weekly_stats 2022/2023, team_stats 2022/2023 (public nflverse; the latter two
   were downloaded by a subagent without explicit approval -- delete if unwanted; the DST rebuild in the analysis scripts needs them), analysis/proj_* and analysis/ownership_fc_refit scripts (no FC data inside).
   FC-derived outputs live only in the gitignored data/fc_history/derived/ (fc_master(_mapped).csv, ourproj*, proj_* reports). NEVER commit them (public repo, subscription data).
   Untracked and intentionally NOT committed: analysis/ownership_fc_refit/cache_2026.parquet, __pycache__, logs/unmatched_salaries_dk_dk_classic_wk3_afternoon_27Sep2026.csv (not ours to decide).
NOT changed, deliberately: matchup (stays neutral), no FC blend, no ownership refit/calibration, no QB recalibration, no sigma/p90 changes, no Week 1 price floor, no backup-QB cap.

## PICK-UP PLAN once Week 3 results arrive (Mon 2026-09-28) -- in this order
A. Log data (existing process): Stage 7 results (`log_results.py`; FD via derive_actual_results.py), Stage 6 real ownership (`log_ownership.py`, sum ALL rows per player incl. FLEX).
   Export FC Week 3 Rewind (all slates: main + early/afternoon + showdown if possible) before the trial ends Fri 2026-10-02; FC file naming fc_dk_2026_wk03_{slate}_{type}.csv into data/fc_history/2026/,
   then `python scripts/fc_history_etl.py` and `python scripts/fc_history_map.py` (send one showdown + one early/afternoon sample first; ETL never run on those layouts).
B. OWNERSHIP (all of this is unconditional except where marked):
   B0. SUNDAY RULE IN FORCE (from HANDOFF_week3_weekend_and_refit_plan_2026-09-25.md sec 4; nothing in this session changes it): cash ignore ownership; GPP/MME treat
       model-far-below-FFC players as chalk, use the higher of model/FFC, no leverage play on a model-only low-ownership call unless FFC agrees. Wk3 main example: Kelce 19 vs FFC 46, Mahomes 18 vs 46, Gibbs 47 vs 63.
   B1. Rebuild the 6 wk1/wk2 DK classic slates leak-free with FINAL code (--backtest-no-leak; wk1 --season 2025 --week 23, wk2 --season 2026 --week 2; every build must print `Wrote N players`;
       restore output/ with git checkout; never commit test rebuilds; use PRE-LOCK commits cefc761/7e57cfe if reading old outputs) + add the 3 wk3 slates. The current artifacts were fit on 2 weeks of PRE-guard projections.
   B2. Refit BOTH data/ownership_model_dk.json and data/ownership_model_dk_ffc.json (scripts/fit_ownership_model.py; FFC variant = om.FEATURES + om.FFC_FEATURES), leave-one-week-out on 3 weeks,
       meaningful cut (proj>8). Baseline to beat: corr .764, chalk bias -4.1 (FFC variant). Ship only if it wins held-out weeks.  (This refit was planned regardless; only shipping is conditional.)
   B3. FFC-floor test: for players FFC lists above ~30%, est = max(model, a*ffc), `a` chosen only by LOWO (start 0.7). Report corr, chalk-tier bias, top-10 overlap; ship only if better in >=2 of 3 folds and no harm to sub-10%.
   B4. Check whether status apply's ownership refresh (OUT + Doubtful) changes chalk vs the build-time number.
   B5. FC-history findings to test as additions (they did NOT beat the model alone): pair '$5.5-7k multiplier (x1.3-1.45) + top-player cap 60-65' (fixes tier totals, costs 20%+ precision if used alone; retest on 3 folds),
       value-rank / public-value features, DFF/WWO (data/projections_public) and ECR (data/ecr_archive) as they accumulate. 10-20% tier undercount is a discrimination problem, not a shape problem.
   B6. Showdown ownership is separate (ownership_model_showdown.py, fit on 4 slates); FC showdown history (parked, user pulling) is the main lever there.
   B7. Real wk3 ownership must be logged first (log_ownership.py, sum ALL rows per player incl. FLEX; the log guard refuses low totals).
C. Lambda: re-verify cash/SE lambda 0 vs 0.063 with wk1-3 real slates on the FULL optimizer (stacks, exposures) via scripts/optimizer.py --lambda; consider a fresh sweep on 2021-25 history after the sigma fix (item E).
D. QB: refit projection_stack on guarded history (was fit 2020-21 on broken QB volume), then test QB = a + b*proj (b .64-.89 by week bucket) at lineup level incl. wk3; look at backup-QB starters (Mariota/Winston) that look low.
E. Sigma: fix the yards double-count (fit yards_cv net of latent in statline_variance.json), refit sigma_recalibration on 2021-25 (interim x0.90 RB/WR/TE), QR p90. Nothing reads p90 today.
F. Week 1 (next season, or test earlier on 2018-20 RotoGuru wk1): floor price weight ~0.75 for veterans on the wk1 sentinel path; refit volume_prior_dk.json (fit on 2014-2021).
G. Injury/inactive: build a verified game-day inactives source + scheduled pull/apply 60-75 min pre-lock; rule for QUESTIONABLE QB1; cross-check vs DFF/WWO ONLY with a Sunday-morning refetch (Thursday snapshots were stale: they had Lock as SEA QB1 while Darnold played).
   Questionable-haircut sizing needs nflverse injuries_{season} (public, ~1 MB/season, not downloaded).
H. Any FC-vs-ours re-run: now includes wk3 live pre-lock FC projection vs our production wk3 output (use PRE-LOCK commits, never HEAD output/ for a played week).
Standing principles: recent seasons matter more; judge at lineup level; report effect size + direction + what n would settle it; small shifts can flip lineups; FC = calibration benchmark only.

## Addendum 4 (Sat 2026-09-26 evening): three "next effort" builds -- all BUILT, NONE ENABLED for Week 3
Verdicts + how to pick each up. Production artifacts/behaviour are unchanged from a489bc6/2f68df7 (verified: git diff of data/statline_variance.json, sigma_recalibration_{dk,fd}.json = none).
1. GAME-DAY INACTIVES (scripts/inactives_pull.py, tests analysis/proj_inactives/, workflow step COMMENTED OUT in refresh_data.yml). Source = ESPN per-game roster `didNotPlay`
   (sports.core.api.espn.com .../events/{eid}/competitions/{eid}/competitors/{tid}/roster). Verified only on FINISHED games; returns 404 before kickoff for wk3, so pre-kickoff availability
   (~90 min before) is UNVERIFIED and it may be a post-game field (also flags ~22 dressed-but-DNP backups/week). Replay wk1-2: precision 1.000, adds 53/29 true DNPs beyond ESPN designations.
   To try Sun: at 15:30-16:45Z run `python scripts/inactives_pull.py --season 2026 --week 3 --dry-run`, compare to official inactives; enable only if it matches (uncomment 8 lines).
   Pick-up: watch whether the dry run ever returns data pre-kickoff; if not, a no-op -- fall back to designations + manual overrides + a fresh DFF/WWO Sunday refetch.
2. YARDS DOUBLE-COUNT + SIGMA REFIT (new fitter code in scripts/fit_statline_variance.py, additive/inert unless --net-latent-from is used; analysis/proj_variance/).
   Refit artifacts SAVED, NOT LIVE: data/statline_variance.refit-2026-09-26.json, data/sigma_recalibration_{dk,fd}.refit-2026-09-26.json (untracked; the DK recal bins hold aggregates from
   FC-derived data -> do not commit them unless bins are stripped; repo is public). To try: copy over the live file (keep a backup), rebuild.
   Validated result: sim yards sd / actual residual sd 1.8-2.1x -> ~1.0-1.1 all positions, all seasons; TD dispersion still not too low; sigma z_sd 2023+ (LOSO) QB 1.01, RB .94, TE 1.00, WR .97
   (old 1.03/.86/.90/.91); ranking of sigma unchanged (level change only). Means move slightly (mean -0.015 pt, 99th pct |chg| .23, from DK +3 yardage bonuses) -- real, not a bug, accuracy unchanged.
   Lineup level: no improvement (lambda 0 identical; MME -0.005 flips top lineup on 6% of slates, no measurable effect). LAMBDA RE-SWEEP with new sigma: nothing positive beats 0; 0.063 clearly harmful
   (-6.1, CI -11.6..-0.7, cash .102 vs .227, negative 5 of 6 seasons) -> CONFIRMS lambda 0 for cash/SE; MME -0.005 neutral. ~300+ slates needed to resolve +-1 pt.
   Also available, not shipped: QR p90 = a + b*final (QB 13.92+.827f, RB 3.77+1.520f, WR 4.75+1.476f, TE 4.32+1.496f; needs edit in build_projections_statline.py; nothing reads p90);
   volume-dependent gamma shape in statline_model (yards-TD coupling is mildly under-modelled, slightly worse for RB/TE after the fix). FD: recal 'a'/fit range were rescaled only, no FD refit.
   Parked because: no lineup benefit shown, changes means (~0.2 pt) and DK showdown/FD/ownership-cv side effects the day before lock. Revisit after wk3 together with the QB work.
3. QB / PROJECTION STACK REFIT (analysis/proj_stack/; artifact data/projection_stack_dk_refit_2026-09-26.json, untracked, NOT wired; derived from FC-derived training data -> keep local).
   Refit on guarded 2021-25 history (49,169 rows). RB/WR/TE improve EVERY season 2021-26 (MAE RB 4.30->3.98, WR 4.42->4.17, TE 3.14->2.93; bias +0.3..0.8 -> ~-0.3) but QB1 slope stays ~.65 and
   QB1 bias worsens (-0.15 -> -1.21): the stack is fit on all QBs incl. backups. Lineup level +3.9 (CI -1.1..+9.1), negative in 2025 (-3.5), changes full lineup on 97% of slates (MDE ~7 pts).
   QB linear recal (a + b*old proj) is the only 2023+ CI above 0 (+4.3, 0.5..8.2). Week 3 ownership would shift 1-3 pts (chalk slightly chalkier: Allen 23.7->24.7, Kelce 18->21, Lamar 4.6->3.5) and
   ownership artifacts were fit on old-stack projections. Switch (proposal, not applied): scripts/projection_stack.py line 62 artifact_path -> f"projection_stack_{site}_refit_2026-09-26.json" for dk.
   Next: fit a QB1-specific term (stack on QB1 rows, or recal after refit); option to ship RB/WR/TE-only. Decide after wk3 (adds ~3 slates; useful mainly as a live QB1-bias check).
PICK-UP ORDER after wk3 (updates plan D/E above): (a) QB1-specific stack/recal + wk3 QB1 bias check; (b) then decide on RB/WR/TE stack refit AND sigma/variance refit TOGETHER (both move projections/sigma; rebuild, refit ownership once);
(c) QR p90 + volume-dependent yards shape; (d) inactives dry-run findings from Sunday.
