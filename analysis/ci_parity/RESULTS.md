# CI parity: do the UI's Actions-built projections use the 2026-09-29 accuracy changes? (2026-09-29)

Question (owner): "i build them out of the frontend UI" -- the frontend reads output/final_projections_*.csv built by
.github/workflows/refresh_data.yml. Do ownership v2, the early-season blend and the QB recal actually run there?

## Finding before fix
Blend + QB recal configs lived under data/fc_history/derived/ (git-ignored) -> on Actions both printed
"config not found ... skipped" and silently no-op'd. Ownership v2 was already fine (all inputs tracked).

## Fix
- data/early_season_blend_config.json, data/qb_recal_config.json: tracked copies, coefficients only (salary-line m/b per
  position, per-week a/w; QB recal a..e, gate, min_week). No FC rows, no player data. Coefficients verified identical to
  the originals (only `_note` rewritten).
- scripts/build_projections_statline.py: EARLY_BLEND_CONFIG / QB_RECAL_CONFIG default to the tracked paths; CLI defaults
  stay ON, python-function defaults stay OFF (harness), --*-config overrides and missing-file no-op unchanged.

## CI-parity run
Clean `git worktree` of HEAD 74e85e8 + only the files above (no data/fc_history present), then refresh_slate's exact
build + apply commands (same flags: --volume-prior --sigma-recalibration --dst-model distributional, status file picked
by filename sort as the workflow does) for all six Wk3 classic slates, plus DK Wk2 main to exercise the blend.

| slate | build | apply | own v2 (log + cols) | blend | QB recal |
|---|---|---|---|---|---|
| dk wk3 main | ok | ok | ON (FFC log-blend), cols kept after apply | no-op (wk3 absent, correct) | 26 QBs, mean +0.67 |
| dk wk3 early | ok | ok | ON | no-op (correct) | 18 QBs, +0.82 |
| dk wk3 afternoon | ok | ok | ON | no-op (correct) | 8 QBs, +0.52 |
| fd wk3 x3 | ok | ok | n/a (DK-only by design) | n/a | n/a (DK-only) |
| dk wk2 main | ok | - | ON | 298 players, mean +0.46 | no-op (wk<3, correct) |

Josh Allen qb_recal_delta -2.22, est own 17.5 (old 16.9). optimizer.py on the CI-parity DK main pool: exit 0.
Worker (optimizer_api.js) passes the CSV through raw; frontend parseCSV is header-keyed and only requires
player_id/player_name/position/team/salary/final_projection, so new columns do not break anything.

## Inputs v2 needs (all tracked; order OK)
weekly_stats_{2023..2026}.parquet (refreshed by shared_pull `ingest_historical` BEFORE refresh_slate, committed; v2
filters to weeks < slate week, so ingesting last week's stats first is the desired order, not a leak),
output/final_projections_dk_dk_classic_wk{1..3}_*.csv (prior salary), data/ownership_actual_log.csv (lag own; Wk4 needs
the Wk3 main rows -- present), data/ownership_v2_dk_{linear,dst}.json.

## Remaining silent-degrade risks (no crash, but weaker)
1. team_stats (ingest_historical) is continue-on-error: if nflverse hasn't published last week, v2 runs on stale stats.
2. ownership_actual_log.csv is manual: if the prior week's real ownership isn't logged, the lag-own feature is missing.
3. Any v2 exception -> previous model, only a stderr WARNING. The build step stays green. Check for the
   "Ownership v2: ON" line or the est_own_v2_only column.
4. Local Python 3.14 vs CI 3.12 (pinned pandas 3.0.2); not exercised on 3.12 here.
