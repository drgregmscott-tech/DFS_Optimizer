# Multi-season leak-free projection backtest (DK 2014-2021)

This harness rebuilds every DK week from 2014 to 2021 with the shipped statline engine. Weeks 2-17 are covered, plus week 18 in 2021: 129 weeks and roughly 35k scored skill player-weeks. It scores the builds against real DK points. Results are in `REPORT.md`.

## Files

| File | Purpose |
|---|---|
| `run_backtest.py` | Runs the builds in-process, parallel by season, and can resume. It writes only to `out/`. |
| `evaluate.py` | Metrics for one or more arms. With two or more arms it also computes paired deltas against the first arm, with 95% CIs from a week-clustered bootstrap. |
| `leak_embargo_test.py` | Empirical leak test. It rebuilds one week with every season/week-keyed input truncated to what was known before kickoff, then diffs the result against the normal build. |
| `test_default_preserved.py` | Checks that the opt-in `scripts/` change leaves production output unchanged. It compares a real 2026 slate built with the HEAD module against the same slate built with the working-tree module. |
| `out/proj/<arm>/proj_<arm>_dk_<season>_wk<week>.csv` | Per-week projections. The `season` and `week` columns are prepended. |
| `out/work/<arm>/<season>_wk<week>/` | Private OUTPUT_DIR for each build: vegas file, regenerated matchup file, reconcile report. |
| `out/logs/<arm>/` | Per-week build stdout, `errors.txt` and the arm's config. |
| `out/eval_*.txt`, `out/metrics_*.csv` | Evaluator output. |

## Running

```
python analysis/backtest_multi/run_backtest.py --arm baseline --workers 8
python analysis/backtest_multi/run_backtest.py --arm matchup_restored --restore-matchup --workers 8
python analysis/backtest_multi/run_backtest.py --arm no_stack --no-stack --workers 8
python analysis/backtest_multi/run_backtest.py --arm no_sigma_recal --no-sigma-recal --workers 8
python analysis/backtest_multi/evaluate.py --arms baseline matchup_restored     # --pop all for inactives too
python analysis/backtest_multi/leak_embargo_test.py 2019 4
python analysis/backtest_multi/test_default_preserved.py
```

- **Timing.** One build takes about 18 s alone, or about 60 s when 16 run at once. An arm takes about 15-30 min with 8 workers.
- **Resuming.** Finished weeks are skipped. Pass `--force` to rebuild them.
- **Other arm flags.** `--no-volume-prior`, `--no-role-change`, `--dst-model legacy`, `--seasons 2018-2021`, `--weeks 2-10`.

## Build configuration

The build uses the shipped DK classic configuration, without props:

- `use_volume_prior=True`, `sigma_recal=True`, `dst_model_mode="distributional"`, `use_stack=True`
- `neutral_skill_matchup=True` (the shipped default)
- `ignore_played_week=True`, `props_weight=0.0`, `canonical_teams=True`
- slate `rotoguru_{season}_wk{week}`, which is the full Thursday-Monday DK pool

## Leak and data neutralisation (all in-process)

- **Depth chart.** `statline_model.load_depth_chart` is stubbed to empty, because the only local depth data is a 2026 snapshot.
- **Injury status.** `statline_model.load_injury_status` is stubbed to empty, because the `output/player_status_{week}_*` files come from 2026 runs and are keyed by week only.
- **Private output directories.** The `OUTPUT_DIR` of `build_projections`, `build_projections_statline` and `backtest_harness` points to a private directory for each (arm, season, week). This removes the week-keyed vegas-file collision.
- **Vegas file.** Built from `data/nflverse_games.csv` closing lines using `backtest_harness.build_vegas_file`.
- **Matchup file.** Regenerated for each week with `projections_matchup.build_matchup_factors`, which uses REG weeks before the target week only. The stale copies in `output/` are not used.
- **Team codes.** `canonical_teams=True` maps era codes (OAK/SD/STL, and RotoGuru's SDG) to current codes (LV/LAC/LA). This is a new opt-in keyword; see REPORT.md.

## Actuals

Actuals come from `data/rotoguru_actuals_dk_{season}.csv`, joined on RotoGuru gid = DK salary `ID`. These are real DK scores, and a player who did not play scores 0. On 2019 wk6 they correlate with nflverse PPR plus DK bonuses at r = .998.

The default population, `played`, keeps skill players with an nflverse stat row that week, plus all DSTs. It approximates production, where inactive players are zeroed by status news. Status news isn't available in the backtest.
