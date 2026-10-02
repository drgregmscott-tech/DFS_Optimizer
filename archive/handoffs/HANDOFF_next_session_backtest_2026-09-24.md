# HANDOFF -- multi-season leak-free backtest + remaining accuracy items (written 2026-09-24, end of session)

Supersedes the action list in HANDOFF_projections_next_session_2026-09-24.md (read that for background; its steps 0, A-E, H are now DONE, see below).

## HARD RULES for the next sessions
- **Showdown Atl@GB (lock 2026-09-25 00:15 UTC) is frozen.** Do not change projections/ownership code paths that touch it before lock. Lineups for it are a separate session. (See "Open risk" below: the automated refresh can still rebuild it.)
- Sunday classic slates lock 2026-09-27 17:00 UTC (FD afternoon 20:05 UTC). Anything shipped for them must be validated and pushed before then.
- Heavy analysis -> Opus subagent (`Agent` model "opus"), brief fully, verify its headline numbers yourself before relaying (worked well this session: every agent number reproduced). Report bias AND ranking. State n. Stage explicit paths, never `git add -A`; fetch+rebase before push.

## What shipped this session (all on origin/main)
- Week 3 rebuilt with the QB blow-up guard; MIN Murray now 30 att / 12.7 pts (still low; WinWithOdds has 17.2 -- watch). No QB > 38 att.
- `--backtest-no-leak` flag (build_projections_statline.py) for leak-free backtest rebuilds of played weeks.
- **Matchup factor neutralised for QB/RB/WR/TE** (default; `--restore-matchup` reverts). Evidence: analysis/proj_b1/b1_report.md (Pearson .438->.484, MAE 6.56->6.30 on 240 player-weeks; wrong-way residual slope -0.8; fails within-slate Spearman on wk2 fold, top-N indistinguishable). Revisit ~Week 6 with a version that doesn't overlap the vegas factor.
- Public-projection logging: scripts/ingest_public_projections.py (DFF dk+fd, WinWithOdds dk) -> data/projections_public/, wired into refresh_data.yml. DATA ONLY. DFF `ppg_proj` is the projection (`proj_score` is a different, ~2x quantity).
- Showdown Atl@GB props pulled (25 players anchored); status re-applied. Props for Sunday classic NOT pulled; the auto-pull runs at 16:00 UTC Sunday (main/early) and 19:00 UTC (afternoon); ~227 credits left before the Showdown re-pull.
- Guarded baseline (analysis/proj_recheck/guarded_baseline_notes.md): bias +0.01, RMSE 8.11, Spearman within slate x pos .248, top-N 16.29 (parity with OLD, not better).

## Analyses done, nothing shipped (each has a written retest bar)
- Step C calibration (analysis/proj_c): slope 1.33 shipped vs 0.95 engine -> stack compresses spread; nothing passed LOWO. TE: stack may hurt TE ranking (moderate evidence, decided no change). QB: pass-att flat (sd 3.3 vs 8.7); QB rushing under-projected ~1 pt uniformly (fix inside engine).
- Step D sigma (analysis/proj_d): upper tail now fine (8.8% > p90); lower tail bad (15% < p10; ~25% incl. cheap players): p10 too high. Fix after Week 3: `max(0, mean-1.28*1.07*sigma)` after build_projections_statline.py:752, RE-SET the MME dart threshold (optimizer.py ~2031-2057) in the same change. Retest bar in d_report.md section 6.
- Step H floor-share (analysis/proj_h): dilution real (wk1 3.8 carries/8.5 targets per team; wk2 1.7/2.5) but the with/without fix does not help (wk2 MAE +0.08, wk1 no gain). Not shipped. If revisited: send freed volume to depth-chart #1 and guard low-priced real players.

## Open risk (Showdown)
Showdown Atl@GB is still in data/current_slate.json, so the automated full refresh (Thu 23:00 UTC, ~75 min before lock) will re-pull props, re-apply status and REBUILD it. Decide with Greg whether to let it run (fresher injuries/props) or freeze it (remove the entry from current_slate.json after the last desired build).

## NEXT SESSION PLAN (in order)

**1. Multi-season leak-free backtest (highest leverage; it makes every other fix testable).** Goal: thousands of player-weeks instead of 238. Feasibility questions to answer FIRST (~1 hour, Opus): (a) which historical seasons/weeks have nflverse stats + schedules + depth/roster data (data/ has 2014-2021 and 2025/2026; scripts/ingest_historical.py); (b) historical Vegas lines (scripts/vegas_*; the 2021 rotoguru harness `output/*rotoguru_2021*` and earlier sessions' harness in ROADMAP/SESSION_LOG likely built this -- find it and reuse); (c) DK/FD salary history (rotoguru 2021?) -- without salaries the price prior cannot run; (d) whether `--season/--week` lookback logic is leak-free for arbitrary past weeks (statline_model.build_usage(season, week) uses only prior weeks -- verify) and whether the played-week zeroing (`--backtest-no-leak`) plus depth-chart/status snapshot leaks are neutralised (depth_charts_current.parquet is a 2026 snapshot: must not be used for old seasons). Deliver a runnable harness + a leak audit, then re-run: matchup ablation (B1), stack shrinkage/TE effect (C), sigma/p10 calibration (D), floor-share (H), QB rush volume. Props are NOT available historically -- note which conclusions exclude props.
**2. Week 3 results as the third fold** (Sun/Mon): Stage 7 results (derive_actual_results.py FD; DK results export -> log_results.py) and Stage 6 ownership (log_ownership.py, sum ALL rows incl. FLEX). Rerun B1/C/D retest bars; also the public-projection blend test needs logged weeks (wk3 first).
**3. Props first live use** on the Sunday classic builds after the 16:00 UTC run: check `data/props/props_dk_classic_wk3_main_27Sep2026.csv` exists, the build prints "Props market anchor: adjusted N", spot-check big movers (weight 0.5, clamp 0.5-1.8x).
**4. Engine items (need the backtest to validate):** QB rush volume in the engine (~+1 pt/QB); stack refit on 2026/multi-season data (esp. TE); p10 fix + dart threshold; Murray/moved-QB pre-scale volume (raw_sum 5.0 -> 6x rescale; Murray 12.7 vs market 17.2).
**5. Ownership rebuild + refit** (Step I of the earlier handoff) once projections are final: rebuild wk1/wk2 DK classic leak-free with final code, refit both artifacts via scripts/fit_ownership_model.py, refit again after wk3 real ownership. Memory: project_ownership_model_state.md.
**6. Information timeliness / richer inputs** (longer term): snap/route participation, air yards, real-time injury/inactive handling; external-projection blend once several weeks are logged.

## Scoreboard (honest, Greg asked): projections ~5/10, ownership ~6/10 on "1 = useless, 10 = as good as the best models anywhere". No external benchmark exists; the ceiling for one-game NFL scoring is low (best models likely explain low-to-mid 30s % of variance vs our ~25%), so the accuracy gap is smaller than the scale suggests. Main constraint = sample size (2 weeks/6 overlapping slates), hence the backtest.
