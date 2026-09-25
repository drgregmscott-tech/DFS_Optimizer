# ECR blend experiment: does FantasyPros weekly ECR improve our DK skill projections? (2026-09-25)

**Verdict: SHIP-PER-POSITION. RB yes, TE optional at a low weight, WR and QB no.** Keep the flag OFF by default. Turn it on for RB only after the implementation spec below has been built and diffed.

Scripts: `ecr_blend.py` (main), `ecr_extra_checks.py` (truncation check and weight curve).
Outputs: `results_historical.csv`, `results_live2026.csv`, `snapshot_week_map.csv`, `run_log.txt`, `stdout.txt`, `extra_checks.txt`, `ecr_pts_map_2020_2021.csv`.
The ECR and crosswalk data stay in the session scratchpad. They are not in the repo.

## 1. Data and joins

**Snapshot to week mapping** (`snapshot_week_map.csv`)
- A snapshot is assigned to the first REG week that has a game on a later calendar day.
- A player's ECR is used only if his team's game falls on a calendar day after the snapshot date. This drops Thursday/TNF and same-day games, 616 matched rows in total.
- Duplicate snapshots for the same week were resolved by keeping the latest one. Dropped: 2020-10-16 (kept 10-17, wk6), 2021-10-05 (kept 10-08, wk5), 2021-12-10 (kept 12-11, wk14).
- 2021-09-10 maps to wk1, which is not in the backtest.
- Testable weeks: 2020 has 11 (wk6-16), 2021 has 16 (wk2-17), and 2026 has wk1 and wk2 (09-11, 09-18).
- No snapshot is dated on or after the kickoff of any game it is applied to. This is enforced per team, not just per week.

**Crosswalk** (DynastyProcess `db_playerids` fantasypros_id -> gsis_id)

| Population | n | ECR match rate |
|---|---|---|
| Historical rows with proj>8 | 3,802 | 99.4% (QB 97.3, RB 99.9, TE 99.7, WR 100) |
| Historical rows with proj>0 | 9,981 | 93.4% (the misses are deep bench players ECR does not rank) |
| Our top-2N per position | 4,536 | 99.8% |
| Live 2026 | 240 | 98.8% |

- All matches came through gsis. The name+team fallback added 0.
- Live unmatched players: Brock Bowers wk1, Isiah Pacheco wk1, Jordan Mason wk2.
- 285 of 3,436 ECR rows with ecr<=1.5N did not join our pool. Most are TNF players (removed by design) or players absent from the RotoGuru pool.

**Reproduction.** Through `evaluate.load_arm` / `evaluate.metrics`, the full played set exactly reproduces n, Spearman and MAE for all eight 2020/2021 x position rows of `metrics_baseline_played.csv`.

The common-set numbers below are lower, for example baseline 2021 skill Spearman is .587. That is because the comparison is restricted to players ECR ranks, which removes the easy low-end rows. So the numbers are not directly comparable to REPORT.md.

## 2. Historical, played population, common set (weights chosen on the training season only; CIs resample weeks, B=2000)

Skill pooled. Δ is versus ours-alone.

| Arm / test (train) | n (weeks) | Ours Spearman / topN | ECR-only ΔSp | Best blend (train-chosen) | ΔSpearman | ΔtopN pts | ΔMAE |
|---|---|---|---|---|---|---|---|
| baseline, 2021 (2020) | 4505 (16) | .587 / 15.63 | +.005 [-.005,+.014] | z per-pos {QB0,RB.7,WR.5,TE.7} | +.014 [+.008,+.018] | +.15 [+.08,+.23] | rank-like |
| baseline, 2020 (2021) | 3127 (11) | .602 / 15.73 | -.002 [-.011,+.010] | z per-pos {QB0,RB.5,WR.4,TE.7} | +.012 [+.007,+.016] | +.16 [+.02,+.31] | rank-like |
| baseline, 2021, pts blend w=.7 | 4505 | MAE 4.83, bias +.01 | | pts | +.010 [+.002,+.017] | +.11 [+.01,+.21] | -.02 [-.08,+.04], bias +.18 |
| baseline, 2020, pts blend w=1.0 | 3127 | MAE 4.91, bias -.37 | | pts (= ECR only) | -.010 [-.018,+.001] | -.05 | +.05 [-.05,+.14] |
| no_stack, 2021 | 4505 | .576 / 15.27 | +.016 | z w=.5 | +.022 [+.015,+.028] | +.41 [+.12,+.69] | |
| no_stack, 2020 | 3127 | .589 / 15.44 | +.011 | z w=.5 | +.019 [+.012,+.025] | +.34 [+.21,+.48] | |

**By position** (baseline, played, z or rank blend, both folds). Detail is in `results_historical.csv`.
- **RB:** ΔSp +.015 to +.025, all CIs exclude 0. ΔtopN +.26 to +.48, all CIs exclude 0. The pts blend lowers MAE in 2021 (-.14) and is neutral in 2020.
- **TE:** ΔSp +.009 to +.024, three of four CIs exclude 0. ΔtopN is positive in 5 of 6 blend variants, and the CIs mostly include 0.
- **WR:** ΔSp +.009 to +.013, CIs exclude 0. **ΔtopN is negative in both folds** (-.02 to -.40), so WR fails the top-N part of the bar.
- **QB:** ECR is worse than ours (ECR-only ΔSp -.023 / -.052). Every train fold picked QB w=0 or hurt. Do not blend QB.

**Played vs all (inactive-knowledge share).** Baseline skill ΔSp is +.012/+.014 in the played population and +.017/+.020 in the all population. About a third of the ECR "gain" in the all-population variant is ECR knowing who is inactive. The played-only gain is still clearly positive.

**Stack in-sample caveat.** The no_stack arm, which has no in-sample stack, shows gains about 1.6x larger than baseline. The shipped stack already captures part of what ECR adds. Baseline is the conservative number.

## 3. Live 2026 (primary check), maps and weights fit on 2020+2021 pooled

- Sample: 237 player-weeks with ECR, taken from the 240 proj>8 rows (dedup main > early > afternoon). Wk1 n=110, Wk2 n=127, one cell per week x position.
- CIs come from a player bootstrap within cells, B=300.
- top-N is only computable for QB, because the proj>8 truncation leaves RB/WR/TE with fewer than 2N rows.

| Pos | Wk1 ΔSp (pts pp) | Wk2 ΔSp | Both, n | Both ΔSp pts_pp [CI] | ΔMAE pts_pp |
|---|---|---|---|---|---|
| RB (w=.7) | +.127 | +.107 | 67 | +.117 [+.027,+.225] | -0.41 |
| TE (w=1.0) | +.172 | +.364 | 29 | +.268 [-.060,+.643] | -0.53 |
| WR (w=.7) | -.005 | +.079 | 92 | +.037 [-.068,+.135] | -0.00 |
| QB (w=0) | 0 | 0 | 49 | 0 (ECR-only +.009) | 0 |
| Skill pooled | +.073 | +.137 | 237 | +.105 [+.026,+.196] | -0.18 |

- The RB and TE gains are non-negative in both live weeks. WR is slightly negative in Wk1.
- The live gains are about 5x the historical ones. Do not believe that size. Three reasons:
  - Weeks 1-2 are when our model knows least.
  - Each week x position is a single cell.
  - Truncating to our proj>8 inflates the blend gain. Tested historically in `extra_checks.txt`: RB ΔSp goes from +.018 to +.028 at w=.7. That is a small inflation, not 5x.
- Expect roughly +.01 to +.03 RB Spearman going forward, not +.1.

## 4. Sanity checks

- **Shuffle test.** ECR was permuted within week x position, 30 reps per fold/arm/pop, with the train-chosen weights. The blend gain vanishes and turns negative in every case (-.06 to -.64 ΔSp). Live: -.039 (sd .044, 50 reps). The historical gain therefore depends on the real ECR ordering, not on the blending mechanics.
- **Leakage.** There is no post-kickoff snapshot, and per-team game dates are enforced. Isotonic maps and weights were fit only on the training season, or on 2020+21 for live.
- **Crosswalk and reproduction.** Both are covered above and both pass.
- **Not tested.** ECR sd/best/worst were not used. A DST blend was not tested.

## 5. Why the result is still weak, and what it cannot tell us

- The historical engine has **depth charts and injury status stubbed**. ECR knows Friday roles, and our live pipeline also knows them, so part of the RB gain is probably role knowledge the live engine already has. The live check argues against that being all of it: RB is positive in both weeks on the real pipeline. But it is n=67 across 2 cells.
- Historical ECR covers only 27 weeks (2020 wk6-16, 2021 wk2-17). No 2014-19 ECR is available, so the 2020-21 stack in-sample problem cannot be avoided except through the no_stack arm.
- The live frame is truncated at proj>8, so live top-N for RB/WR/TE could not be measured.
- **Tournament value is unmeasured.** A higher Spearman does not show that lineups win more.

## 6. Live refresh cadence (DynastyProcess `files/fp_latest_weekly.csv`)

- GitHub commits touching the file (last 15) show a "Daily FP scrape" about twice a day, near 07:00 UTC and 17:00-19:00 UTC, every day including weekends.
- Sun 2026-09-20 had commits at 07:24, **13:16** and 17:16 UTC. Commits appear only when the content changed.
- The current file (scrape_date 2026-09-25, 07:04 UTC) matches the db_fpecr 2026-09-25 snapshot on every QB/RB/WR/TE player: QB 70/70, RB 113, WR 178, TE 114.
  - The largest ecr difference is 0.7 (WR) and 0.15 (RB). QB and TE match exactly.
- A Sunday-morning build before the 17:00 UTC lock can use the ~07:00 UTC Sunday scrape (about 02:00 CT). There is sometimes a ~13:00 UTC scrape as well.
- **Limitation:** Sunday-morning inactive news (about 90 min before kickoff) and late Saturday news will not be reflected. Our status pipeline must stay authoritative: any player our status zeroes stays zero.
- The file's `scrape_date` is date-only. Log the git commit time or the fetch time.

## 7. Implementation spec (RB only, TE optional; do not ship without a diff test)

1. **CLI flag.** Add `--ecr-blend-rb FLOAT` (default 0.0 = OFF) and `--ecr-blend-te FLOAT` (default 0.0) to `scripts/build_projections_statline.py` argparse (~l.1005). DK classic only. Showdown and FD must ignore it.
2. **Placement.** Apply in `build_projections_statline.py` right after the stack (after l.786, `df = _apply_projection_stack(...)`) and before the no-game zeroing at l.795-798, so confirmed-no-game rows are still forced to 0. Downstream status zeroing (OUT/DOUBTFUL) must also run after it.
3. **Input.** Fetch `https://github.com/dynastyprocess/data/raw/master/files/fp_latest_weekly.csv` at build time and cache it to `data/ecr/fp_latest_weekly_<fetchUTC>.csv`.
   - Use rows with page `ppr-rb` / `ppr-te`, columns `fantasypros_id`, `ecr`, `scrape_date`, `player_game_kickoff_ts`.
   - Require `scrape_date` to be within 3 days of the build and in the current NFL week. Otherwise skip the blend with a WARNING.
   - Use ECR only for players whose kickoff_ts is later than the fetch time.
4. **Join.** Map fantasypros_id to gsis via `db_playerids.csv`, cached the same way, then join on `player_id`. There is no name fallback, because the historical fallback matched 0 rows.
5. **Points map.** Use `analysis/proj_ecr/ecr_pts_map_2020_2021.csv` (copied to `config/`), interpolated with np.interp on ecr, by position.
   - Blend: `final = (1-w)*final + w*map(ecr)`, and set `ecr_delta = new - old`.
   - Shift `statline_p10/p90` by `ecr_delta`, clipped at 0, the same way the stack does.
6. **Players missing from ECR.** Leave them unchanged (delta 0). Never blend a player whose final is 0.
7. **Weights.** RB w=0.5.
   - CV chose 0.7 in both folds. 0.5 is a judgment shrink given the stubbed-roles caveat, and it costs about .001 Spearman historically.
   - TE, if used: w=0.3, because TE MAE worsens above that on proj>8 players.
8. **Audit log.** Write to `logs/ecr_blend_<slate_id>.csv`:
   - per player: player_id, name, pos, ecr, ecr_pts, pre, post, delta
   - per build: fetch UTC time, git commit sha of the fetched file, file scrape_date, match rate among RB/TE with proj>8, count of skipped kickoff-passed players, weights
   - Print a one-line summary to stdout.
9. **Test before use.** With the flag at 0, output must be identical (reuse the `test_default_preserved.py` pattern). With the flag on, diff the wk3 slate and eyeball the 10 largest |delta|.
