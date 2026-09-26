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
B. Ownership (3rd fold): rerun analysis/ownership_fc_refit/evaluate*.py-style LOWO with wk3; test the pair "$5.5-7k multiplier (x1.3-1.45) + top cap 60-65"; look at value rank / public-value features;
   check whether DFF/WWO (wk3 captured in data/projections_public/) and ECR (data/ecr_archive/) add anything as they accumulate. Refit BOTH artifacts per HANDOFF_week3_weekend_and_refit_plan_2026-09-25.md sec 4 only if it wins.
C. Lambda: re-verify cash/SE lambda 0 vs 0.063 with wk1-3 real slates on the FULL optimizer (stacks, exposures) via scripts/optimizer.py --lambda; consider a fresh sweep on 2021-25 history after the sigma fix (item E).
D. QB: refit projection_stack on guarded history (was fit 2020-21 on broken QB volume), then test QB = a + b*proj (b .64-.89 by week bucket) at lineup level incl. wk3; look at backup-QB starters (Mariota/Winston) that look low.
E. Sigma: fix the yards double-count (fit yards_cv net of latent in statline_variance.json), refit sigma_recalibration on 2021-25 (interim x0.90 RB/WR/TE), QR p90. Nothing reads p90 today.
F. Week 1 (next season, or test earlier on 2018-20 RotoGuru wk1): floor price weight ~0.75 for veterans on the wk1 sentinel path; refit volume_prior_dk.json (fit on 2014-2021).
G. Injury/inactive: build a verified game-day inactives source + scheduled pull/apply 60-75 min pre-lock; rule for QUESTIONABLE QB1; cross-check vs DFF/WWO ONLY with a Sunday-morning refetch (Thursday snapshots were stale: they had Lock as SEA QB1 while Darnold played).
   Questionable-haircut sizing needs nflverse injuries_{season} (public, ~1 MB/season, not downloaded).
H. Any FC-vs-ours re-run: now includes wk3 live pre-lock FC projection vs our production wk3 output (use PRE-LOCK commits, never HEAD output/ for a played week).
Standing principles: recent seasons matter more; judge at lineup level; report effect size + direction + what n would settle it; small shifts can flip lineups; FC = calibration benchmark only.
