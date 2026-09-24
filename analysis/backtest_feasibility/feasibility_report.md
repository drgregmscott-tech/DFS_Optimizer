# Multi-season leak-free projection backtest: feasibility check (2026-09-24)

## Verdict: PARTLY FEASIBLE. Feasible for DK 2014-2021 once two leaks are neutralised. Current code gives badly wrong backtests without that.

- **Data is there for DK 2014-2021.** That covers about 129 buildable weeks and roughly **40k skill player-weeks**, about 170x the 238 used so far. Everything needed is on disk: nflverse stats, schedules with real closing lines, weekly rosters, RotoGuru DK salaries (weeks 1-17, plus week 18 in 2021), RotoGuru DK actuals and precomputed matchup files.
- **FD covers only 2021** (18 weeks). There are no salaries for 2022-2024 on either site, and 2024/2025 have stats but no salary pool, so the engine can't build them.
- **LEAK 1: the 2026 depth-chart snapshot is fatal for past weeks.** `statline_model.load_depth_chart()` always reads the latest snapshot in `data/depth_charts_current.parquet` and ignores season. On the one-week dry run (DK 2019 wk6) it changed **136 of 367 projections** and zeroed most 2019 starting QBs: Brady 22.3 -> 2.2, Matt Ryan 19.5 -> 4.0, Rivers 16.7 -> 1.7, Wilson 20.8 -> 5.8. Removing it improved the week from Pearson .604 / MAE 4.67 to **.683 / 4.36**. Any backtest run through the current code without a fix measures this bug, not the model.
- **LEAK 2: fitted artifacts are in-sample.** `volume_prior_dk.json` and `statline_variance.json` were fit on all of 2014-2021. The projection stack was fit on 2020-2021, sigma recalibration and the DST model on 2014-2017. So there is no out-of-sample season for the shipped configuration unless those artifacts are refit leave-one-season-out, or unless you accept in-sample results for the prior and variance artifacts and say so.
- **Props: not available for any past season.** Every conclusion excludes the props anchor.
- **Ownership and current-year salaries: not used** by a past-week build.

---

## (a) nflverse stats, schedules, rosters and depth charts

| Season | weekly_stats rows (weeks) | weekly_rosters | schedules (games) | team_stats | RotoGuru salaries DK / FD | RotoGuru actuals |
|---|---|---|---|---|---|---|
| 2013 | 17,248 (1-21) | 30,184 | 267 | 534 | none | none |
| 2014 | 17,622 (1-21) | 30,196 | 267 | 534 | wk1-17 / none | DK 6,905 |
| 2015 | 17,613 | 30,202 | 267 | 534 | wk1-17 / none | DK 6,860 |
| 2016 | 17,552 | 35,020 | 267 | 534 | wk1-17 / none | DK 6,780 |
| 2017 | 17,477 | 51,321 | 267 | 534 | wk1-17 / none | DK 6,828 |
| 2018 | 17,414 | 52,219 | 267 | 534 | wk1-17 / none | DK 6,781 |
| 2019 | 17,362 | 51,619 | 267 | 534 | wk1-17 / none | DK 6,810 |
| 2020 | 17,602 | 44,128 | 269 | 538 | wk1-17 / none | DK 6,988 |
| 2021 | 18,969 (1-22) | 46,690 | 285 | 570 | wk1-18 / wk1-18 | DK 7,489, FD 8,025 |
| 2022, 2023 | **none** | none | none (lines are in games.csv) | none | none | none |
| 2024 | 18,981 | 46,579 | 285 | 570 | none | none |
| 2025 | 19,422 | 46,841 | 285 | 570 | none | none |
| 2026 | 2,225 (wk1-2) | 8,017 | 272 (64 with lines) | 64 | live exports only | live |

All files are `data/{weekly_stats,weekly_rosters,schedules,team_stats}_{season}.parquet`. Stats include REG and POST rows, and `load_history()` filters to REG games before the target week.

- **Depth charts.** The only depth-chart data locally is `data/depth_charts_current.parquet`: 554k rows, all 2026 timestamps (`dt` 2026-09-19 to 09-23). There is no historical depth data. Weekly rosters carry `depth_chart_position`, which is a position label, not a rank.
- **Free from nflverse (not downloaded):**
  - `stats_player` and schedules for 2022-2023. They are useless without salaries.
  - Weekly **depth_charts** for 2014-2021. nflverse's per-season files, 2001-2024, use the old weekly format; 2025+ uses the timestamped format. These would be the correct as-of-week replacement for the 2026 snapshot.
  - nflverse **injuries** for 2014-2021. The official weekly game-status report would be a leak-free replacement for `player_status` files.
- **Beyond 2021:** RotoGuru stopped at 2021 (ROADMAP.md:880-886). I know of no free DK/FD salary archive for 2022-2024.

## (b) Historical Vegas lines

- `data/nflverse_games.csv` (7,548 games, 1999-2026) has `spread_line` and `total_line` on **every** game for 2013-2025, e.g. 267/267 in 2019 and 285/285 in 2021-2025. The same columns are in `schedules_{season}.parquet`, again 100% non-null.
- `scripts/backtest_harness.py::build_vegas_file()` (Session 10.1, decision #1) already turns these into the `vegas_odds.py` column contract using `implied = total/2 - spread/2`. It also checks that each game's two implied totals sum to the game total. This is the "earlier harness" the handoff mentions (ROADMAP.md:890-921, 1148).
- **Does it suffice? Yes.** These are closing lines, which are slightly sharper than what you have at the Sunday lock. That is a mild optimistic bias, not a future-data leak.
- **Hazard:** the harness writes `output/vegas_implied_totals_{week}.csv` keyed by **week only**, so a run for another season silently reuses or overwrites the same file. A new harness must key the file by season as well, or write to a private directory as the dry run does.

## (c) DK/FD salary history

| Source | Coverage | Rows |
|---|---|---|
| `data/salaries_dk_rotoguru_{2014..2020}_wk{1..17}.csv` | 7 seasons x 17 weeks | ~390-440 per week (2014: 6,436 rows over wk2-17) |
| `data/salaries_dk_rotoguru_2021_wk{1..18}.csv` | 18 weeks | 7,043 over wk2-18 |
| `data/salaries_fd_rotoguru_2021_wk{1..18}.csv` | FD 2021 only | ~437 per week |

- Rows already carry `player_id` (gsis) and `normalized_team`. The position mix in 2014 wk5 was QB 38, RB 107, WR 142, TE 84, DST 30.
- These are full-week pools (Thursday-Monday). The harness's `sunday_main_slate_teams()` gives an approximate main slate if one is needed.
- **Known gap:** no week-18 salary files for 2018-2020 (ROADMAP.md:905). Those seasons only had 17 weeks anyway, so nothing is missing.
- **What is lost without salaries (2022-2025, and FD before 2021):** the build cannot run at all, because `load_salaries()` is required and defines the player pool. You would also lose the volume prior's price share, which drives cold-start and role-change players and the week-1 build, plus the QB backup price suppression. With RotoGuru, **DK 2014-2021 keeps the price prior**.

## (d) Leak audit of `build_projections_statline.py` and `statline_model.py`

| Input | Leaks? | Evidence | Fix |
|---|---|---|---|
| `build_usage` / `load_history` / `team_volume_history` / `team_defense_history` | **N** | `statline_model.py:571` keeps only REG games with `week < week` from the same season | none; note there is no cross-season prior, so week 1 is price-only |
| Played-week team correction and no-game zeroing (`load_real_team_for_week`) | **Y** without the flag, **N** with `--backtest-no-leak` | `build_projections_statline.py:429-436` | always pass `ignore_played_week=True`. Side effect: inactive players are still projected (no OUT info), so the actual-0 scratches must be scored and reported separately |
| `depth_charts_current.parquet` via `load_depth_chart()` | **Y, severe** | `statline_model.py:700-727` takes the max `dt` with no season filter. Three consumers: `apply_volume_prior(depth_chart=)` (QB backup price suppression), `apply_confirmed_starter_override`, `apply_depth_chart_usage_prior`. Dry run: 136/367 projections changed, starting QBs zeroed | add a season/week argument that loads nflverse weekly depth charts as of that week, or return an empty frame for any season < 2026. Stub it in the harness until then |
| `output/player_status_{week}_*.csv` via `load_injury_status(week)` | **Y (contamination)** | `statline_model.py:730-749` globs by **week only**. Files exist for weeks 1, 2, 3, 10, 23 and 24 (2026 runs), so 2014-2021 wk1, 2, 3 and 10 would pick up 2026 injury news | key the glob by season, or stub it to empty. Optionally replace with nflverse injuries (game-status report) |
| `manual_role_overrides_{season}_{week}.csv` | N | keyed by season; none exist | none |
| `weather_{season}_wk{week}.csv` | N | missing, so neutral 1.0 | none (weather is simply absent historically) |
| Vegas file | N (closing lines) | see (b) | key the file by season |
| `matchup_factors_{site}_{season}_{week}.csv` | Unverified. Neutralised for QB/RB/WR/TE by default, so it only matters for `--restore-matchup` (B1) and DST | output/ has DK 2014-2021 (16-18 weeks each) and FD 2021 | before B1, check that `projections_matchup.py` uses only games before the target week |
| Salaries and team assignment | N | RotoGuru files are as-of-week | none |
| Current-year (2026) salaries | N | pool is loaded by `slate_id` | none |
| Props anchor | N if off | looks for `data/props/props_{slate_id}.csv`, which doesn't exist for RotoGuru slates. `props_weight` defaults to 0.0 in the function but **0.5 on the command line** | pass 0 explicitly |
| Ownership, `name_recognition_flags.csv` | N for projection accuracy | only feeds `estimated_ownership_pct` | ignore |
| `statline_variance.json` | **In-sample** | fit 2014-2021 | refit leaving one season out, or declare it in-sample |
| `volume_prior_dk.json` | **In-sample** | fit 2014-2021 | refit leaving one season out (`fit_volume_prior.py` writes to data/, so it needs an output-path argument) |
| `projection_stack_dk.json` (on by default, DK only) | In-sample for 2020-21 | fit seasons 2020 and 2021 | measure on 2014-2019 |
| `sigma_recalibration_dk.json` | In-sample for 2014-17 | fit 2014-2017 | measure on 2018-2021 |
| `dst_model.json` | In-sample for 2014-17 | fit 2014-2017 | measure on 2018-2021, or skip DST |
| Reconcile report | writes `output/statline_reconcile_*` | `build_projections_statline.py:697-702` | monkeypatch `OUTPUT_DIR` |

`backtest_harness.check_artifact_provenance()` (line 1190) already prints the in-sample overlaps listed in the table. Reuse it.

**Other blocker found:** the distributional DST aborts on 2019 wk10. The message was "LAC vs OAK: no team stats could be found for their opponent", an abbreviation mismatch between the vegas file and `team_stats_2019`. This most likely affects every OAK week before 2020, and probably SD and STL in 2014-2016. Fix it with a team-alias map in the harness, or run skill positions only (`--dst-model legacy`, or drop DST from scoring).

## (e) Recommended harness

**Design.** Write a new `analysis/backtest_multiseason/run.py` that runs the build in-process, following `dry_run_one_week.py`:
- Monkeypatch `OUTPUT_DIR` in `build_projections`, `build_projections_statline` and `backtest_harness` to a private directory, so data/ and output/ are never touched.
- Build the season-keyed vegas file with `backtest_harness.build_vegas_file`.
- Copy the matchup files in.
- Stub `load_depth_chart` and `load_injury_status` to empty. A later upgrade is an as-of-week nflverse depth-chart loader.
- Call `build_statline_projections(site, season, week, slate_id=f"rotoguru_{season}_wk{week}", vegas_slate_id=str(week), use_volume_prior=True, sigma_recal=True, dst_model_mode="distributional", ignore_played_week=True, props_weight=0.0, use_stack=True)`.
- Toggle one flag per arm.
- Score skill positions against nflverse DK points (PPR plus DK's 300/100/100 bonuses) or `rotoguru_actuals_dk_{season}.csv`.
- Report bias, MAE, Pearson, within-week x position Spearman, and top-N, plus p10/p90 coverage. Split every metric by season and by position.

**Scope.**
- DK 2014-2021, weeks 2-17 (and 18 in 2021): 129 weeks. Week 1 is price-only; run it as a separate cold-start arm.
- About 310-340 scored skill players per week, so **~40-43k player-weeks** full-week, or ~25k on the main slate only.
- FD: 2021 only, 17 weeks, about 5.5k player-weeks.

**Out-of-sample windows.** With the shipped artifacts: stack on 2014-2019, sigma/DST on 2018-2021. The prior and variance artifacts are in-sample everywhere until they are refit leaving one season out.

**Runtime.** The dry run did two builds of one week in about a minute, so roughly 20-40 s per build. That is about 1-1.5 h per arm for 129 weeks, and it parallelises by season.

**Effort.**
- About 0.5 day for the harness, depth/injury stubs, DST alias fix and scorer.
- About 1 day more for leave-one-season-out refits of the volume prior and variance artifacts. The fit scripts need an output-path argument, which is a `scripts/` change after the Showdown freeze.
- About 0.5 day for the historical depth-chart loader, which H needs.

**Planned re-runs** (all exclude props; salaries are available for DK 2014-2021):

| Re-run | Feasible? | Notes |
|---|---|---|
| B1 matchup ablation | **Yes** | Matchup files exist for DK 2014-2021. First confirm `projections_matchup.py` uses only prior weeks. |
| C stack shrinkage / TE | **Yes (DK only)** | Out-of-sample on 2014-2019, since the stack was fit on 2020-21. Around 30k player-weeks, so the TE question gets real power. |
| D sigma / p10 | **Yes** | Out-of-sample on 2018-2021 for sigma recalibration. The variance artifact is in-sample, so label it. |
| H floor share | **Partly** | The fix sends volume to depth-chart #1, which needs as-of-week historical depth charts (nflverse, free, not local). Without them it can only test the price-based variant. |
| QB rush volume | **Yes** | Engine-only. Around 4k QB-weeks. |

## Prototype dry run (done)

The one-week build is `analysis/backtest_feasibility/dry_run_one_week.py`, run on DK 2019 wk6. The first attempt at wk10 hit the OAK DST abort. All output is in `analysis/backtest_feasibility/out/`. A `find -newer` check confirmed nothing under `data/` or `output/` was written.

```
prod_leaky: n=335 bias=-0.42 MAE=4.67 pearson=0.604 spearman=0.648
clean:      n=335 bias=+0.19 MAE=4.36 pearson=0.683 spearman=0.717
players whose projection differs prod vs clean (>0.05): 136 of 367; max abs diff 20.10
```

This is one week (n=335), so treat the level as indicative only. The volume prior and variance artifacts are in-sample for 2019. The leak's direction and size are not in doubt.
