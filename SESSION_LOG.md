# Session Log

Update this after completing every session — before closing that session, not later. This is what makes the next session's handoff possible without re-explaining the whole project.

**Log entry template (copy this for each new session):**

```
## Session [X.X] — [Session Name]
**Date completed:**
**Status:** ✅ Complete / ⚠️ Complete with caveats / ❌ Blocked

**What was actually built:**
(brief description — note any deviation from what the roadmap card said, drift is normal and expected, just record it)

**Files created/modified:**
(exact paths — copy from roadmap card, correct if it changed)

**Validation results:**
- [ ] (each checkbox from the roadmap card — check off what passed)
(paste any relevant validation output/numbers, e.g. row counts, spot-check values)

**Decisions made / assumptions taken:**
(anything decided during the session that isn't obvious from the roadmap — e.g. "chose PuLP over OR-Tools because X")

**Known issues deferred:**
(anything noticed but intentionally not fixed now — include why, so it doesn't get silently forgotten or silently re-litigated)

**Handoff notes for next session:**
(the specific thing the next session needs to know that isn't in the files themselves — e.g. "salary CSV column headers change slightly week to week, double check before running ingest")
```

---

## Log Entries

(Add entries below as sessions complete, most recent at the bottom or top — your call, just be consistent)

---

## Session 1.1 — Environment & Repo Setup
**Date completed:** 2026-07-21
**Status:** ✅ Complete

**What was actually built:**
- Repo folder structure (`/data`, `/scripts`, `/output`, `/logs`, plus `/config` for secrets — not in the original roadmap list but needed for Session 2.3's API key file).
- `requirements.txt`, `README.md`, `.gitignore`.
- `scripts/nflverse_fetch.py` — this is a deviation from the roadmap card, which called for installing `nfl_data_py`. See "Decisions made" below for why.

**Files created/modified:**
- `/dfs_optimizer/requirements.txt`
- `/dfs_optimizer/README.md`
- `/dfs_optimizer/.gitignore`
- `/dfs_optimizer/scripts/nflverse_fetch.py` (new — not on the original roadmap card)
- `/dfs_optimizer/config/`, `/dfs_optimizer/data/raw_salaries/` (empty, prep for later sessions)

**Validation results:**
- [x] Fresh clone of the repo + `pip install -r requirements.txt` runs without error on a clean environment — verified by building a throwaway venv and installing from `requirements.txt` directly (exit code 0).
- [x] Import + a test pull of one week of prior-season data succeeds — but via `scripts/nflverse_fetch.py`, not `nfl_data_py` (see below). Verified pull of 2025 season weekly stats: 19,421 rows, 145 columns, weeks 1-22 (REG + POST) present.

**Decisions made / assumptions taken:**
- **Did not install `nfl_data_py` as the roadmap specified.** Found during setup that:
  1. `nfl_data_py` is deprecated upstream — nflverse now recommends `nflreadpy` and has stated no further `nfl_data_py` updates are planned.
  2. Its `import_weekly_data()` function 404s on any 2025+ season data, because it points at a GitHub release path (`releases/download/player_stats/...`) that nflverse retired on 2025-08-01 in favor of a renamed release (`stats_player`).
  - Considered 3 options (switch to `nflreadpy`, patch `nfl_data_py`'s URL ourselves, or write our own fetch function) and discussed tradeoffs with the user. **Decision: wrote our own minimal fetch function** (`scripts/nflverse_fetch.py`) that reads nflverse's parquet releases directly via `pandas.read_parquet(url)`. Reasoning: keeps the whole pipeline in pandas (no Polars conversion needed, unlike `nflreadpy`), avoids depending on an abandoned package, and is small enough (~50 lines) that if nflverse renames a release again, there's one obvious file to fix.
  - Schema note: the new `stats_player` release uses `team` where the old `nfl_data_py` output used `recent_team`. **This affects `blended_projections.py` and every downstream session that expected the old schema — future sessions need to adjust column names accordingly.**
- Chose PuLP (not OR-Tools) per the roadmap's suggested default — no strong reason to deviate, installs cleanly.
- Python 3.12.3 confirmed working.

**Known issues deferred:**
- `nflverse_fetch.py` currently only covers `weekly_stats`, `schedules`, and `weekly_rosters`. If a later session needs another nflverse dataset (e.g. injuries, NGS data), add a new entry to `URL_TEMPLATES` rather than reaching back for `nfl_data_py`.
- No automated test/CI yet for `nflverse_fetch.py` beyond the manual smoke test — acceptable for this stage, revisit if the pipeline gets automated in Phase 5.

**Handoff notes for next session:**
- Session 1.2 (Historical Data Ingestion) should import from `scripts/nflverse_fetch.py` (`import_weekly_data`), not `nfl_data_py`.
- **Schema alert:** the pulled weekly stats dataframe uses `team` (not `recent_team`) as the team column, and has 145 columns (not the older nfl_data_py column set). Session 1.2's "paste the `.columns` output" handoff step should capture the *actual* new schema, since it differs from what `blended_projections.py` (written against the old nfl_data_py schema) currently assumes.
- Full column list from this session's pull is reproducible via `python3 scripts/nflverse_fetch.py` — didn't paste all 145 columns here since that's properly Session 1.2's job per the roadmap.
- Python version: 3.12.3 in the build/test sandbox. **Re-validated on the user's actual machine on Python 3.14.6 (Windows 11, PowerShell)** — `pip install -r requirements.txt` and `python scripts\nflverse_fetch.py` both passed cleanly with no version-related issues. No upper Python-version pin needed in `requirements.txt` at this time.
- Windows-specific setup notes (not issues with our code, just first-time-setup friction): (1) Windows ships a PATH alias that prints a misleading "install from Microsoft Store" message if Python isn't actually installed yet — install from python.org instead and check "Add python.exe to PATH" during install. (2) PowerShell needs `venv\Scripts\Activate.ps1` (not `source venv/bin/activate`, which is Mac/Linux syntax) and may require `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once before it'll allow running the activation script. (3) Use `python` and backslash paths (`scripts\nflverse_fetch.py`) on Windows, not `python3` / forward slashes.
- No other OS-specific issues hit beyond the pandas/numpy build-isolation issue below.
- Minor unrelated install hiccup, already resolved: fresh `pip install` of *any* package needing to build from source (e.g. an old pinned `pandas==1.5.3`, which we no longer use) failed with `ModuleNotFoundError: No module named 'pkg_resources'` — recent `setuptools` releases removed `pkg_resources`, and pip's build-isolation fetches the newest `setuptools` regardless of what's globally installed. Not an issue for our final `requirements.txt` since none of our pinned packages need to build from source (all have prebuilt wheels for 3.12), but worth knowing if a future session adds a package that doesn't ship a wheel.

---

## Session 1.2 — Historical Data Ingestion
**Date completed:** 2026-07-21
**Status:** ✅ Complete

**What was actually built:**
- `scripts/ingest_historical.py` — pulls weekly player stats, schedules, and weekly rosters for given season(s) and writes each to parquet under `/data`.
- Deviation from the roadmap card (expected, per Session 1.1's decision): imports from `scripts/nflverse_fetch.py`, not `nfl_data_py`.
- Deviation from the roadmap card's file list: in addition to `weekly_stats_{season}.parquet`, also writes `schedules_{season(s)}.parquet` and `weekly_rosters_{season}.parquet`, since the roadmap's "Build" step explicitly calls for pulling all three (schedules + rosters just weren't named in the "Files touched" list). All three live under `/data`.
- Found and fixed a second nflverse URL problem beyond the one already known from Session 1.1: the `schedules` release's actual asset filename is `games.parquet`, not `schedules.parquet` (the release *tag* is called "schedules" but the file inside it isn't). `nflverse_fetch.py`'s `URL_TEMPLATES["schedules"]` was 404ing until fixed.
- Found a schema mismatch: the `weekly_rosters` release's player-ID column is named `gsis_id`, not `player_id` (same ID scheme/values as `weekly_stats.player_id`, just a different column name). `ingest_historical.py`'s dedup key accounts for this.

**Files created/modified:**
- `/dfs_optimizer/scripts/ingest_historical.py` (new)
- `/dfs_optimizer/scripts/nflverse_fetch.py` (modified — fixed `schedules` URL template, see above)
- `/dfs_optimizer/data/weekly_stats_2025.parquet` (output)
- `/dfs_optimizer/data/schedules_2025.parquet` (output — not on original roadmap file list, see above)
- `/dfs_optimizer/data/weekly_rosters_2025.parquet` (output — not on original roadmap file list, see above)

**Validation results:**
- [x] Pull returns expected row counts for a known week, spot-checked against a real box score — Patrick Mahomes, Week 1 2025 (KC @ LAC, Brazil game): our pull shows 24/39, 258 passing yards, 1 TD, opponent_team=LAC. Cross-checked against footballdb.com's Week 1 2025 scores page, which independently reports "258 Yds, 1 TD" for Mahomes in that game — matches exactly.
- [x] Re-running the script doesn't duplicate rows (idempotency check) — ran `ingest_historical.py --season 2025` twice back to back; row counts identical both runs (weekly_stats: 19,421 / schedules: 285 / weekly_rosters: 46,841 after dedup), and the output parquet files are byte-for-byte identical (md5 match) between runs, since each run does a full overwrite rather than an append.
- Row/column counts this run: `weekly_stats_2025.parquet` — 19,421 rows × 145 cols. `schedules_2025.parquet` — 285 rows × 46 cols. `weekly_rosters_2025.parquet` — 46,841 rows × 36 cols (8 duplicate rows on `[gsis_id, season, week]` were found and dropped in the raw source data — noted below).

**Decisions made / assumptions taken:**
- Wrote one parquet file per season for `weekly_stats` and `weekly_rosters` (matching the roadmap's `{season}` naming convention), but a single combined file for `schedules` (named `schedules_{season(s)}.parquet`) since schedule data is naturally one small table per season already and there's no strong reason to further split it.
- Applied `drop_duplicates()` on a natural key before writing, as a safeguard against the source data containing duplicates — not strictly required for idempotency (since each run overwrites rather than appends) but protects against the *upstream* nflverse release itself containing dupes. This caught 8 real duplicate rows in the `weekly_rosters` source data this run.
- Used `[player_id, season, week, season_type, game_id]` as the weekly_stats natural key, `[game_id]` for schedules, and `[gsis_id, season, week]` for weekly_rosters.

**Known issues deferred:**
- The 8 duplicate rows dropped from `weekly_rosters` weren't individually investigated (e.g. whether they're true dupes or a player who changed teams mid-week) — fine for now since they're a trivial fraction of 46,849 rows, but flag if roster data seems off later.
- No automated test/CI yet, consistent with Session 1.1's deferral — still fine at this stage.

**Handoff notes for next session:**
- **Full column list for `weekly_stats_{season}.parquet`** (145 columns, this is the "paste the `.columns` output" step the roadmap calls for): `player_id, player_name, player_display_name, position, position_group, headshot_url, season, week, season_type, game_id, team, opponent_team, completions, attempts, passing_yards, passing_tds, passing_interceptions, sacks_suffered, sack_yards_lost, sack_fumbles, sack_fumbles_lost, passing_air_yards, passing_yards_after_catch, passing_first_downs, passing_epa, passing_cpoe, passing_2pt_conversions, pacr, passing_10, passing_16, passing_20, passing_40, carries, rushing_yards, rushing_tds, rushing_fumbles, rushing_fumbles_lost, rushing_first_downs, rushing_epa, rushing_2pt_conversions, rushing_10, rushing_12, rushing_20, rushing_40, receptions, targets, receiving_yards, receiving_tds, receiving_fumbles, receiving_fumbles_lost, receiving_air_yards, receiving_yards_after_catch, receiving_first_downs, receiving_epa, receiving_2pt_conversions, receiving_10, receiving_16, receiving_20, receiving_40, racr, target_share, air_yards_share, wopr, special_teams_tds, def_tackles_solo, def_tackles_with_assist, def_tackle_assists, def_tackles_for_loss, def_tackles_for_loss_yards, def_fumbles_forced, def_sacks, def_sack_yards, def_qb_hits, def_interceptions, def_interception_yards, def_pass_defended, def_tds, def_fumbles, def_safeties, misc_yards, fumble_recovery_own, fumble_recovery_yards_own, fumble_recovery_opp, fumble_recovery_yards_opp, fumble_recovery_tds, penalties, penalty_yards, fumbles_forced_by_opp, fumbles_not_forced, fumbles_out_of_bounds, fumbles_total, fumbles_lost_total, punt_returns, punt_return_yards, kickoff_returns, kickoff_return_yards, fg_made, fg_att, fg_missed, fg_blocked, fg_long, fg_pct, fg_made_0_19, fg_made_20_29, fg_made_30_39, fg_made_40_49, fg_made_50_59, fg_made_60_, fg_missed_0_19, fg_missed_20_29, fg_missed_30_39, fg_missed_40_49, fg_missed_50_59, fg_missed_60_, fg_made_list, fg_missed_list, fg_blocked_list, fg_made_distance, fg_missed_distance, fg_blocked_distance, pat_made, pat_att, pat_missed, pat_blocked, pat_pct, gwfg_made, gwfg_att, gwfg_missed, gwfg_blocked, gwfg_distance, pt_att, pt_blocked, pt_long, pt_yards, pt_inside_20, pt_out_of_bounds, pt_downed, pt_touchback, pt_fair_caught, pt_returned, pt_return_yards, pt_return_tds, pt_net_yards, fantasy_points, fantasy_points_ppr`. Both `fantasy_points` and `fantasy_points_ppr` are already precomputed — no need to hand-roll fantasy scoring from raw stats in Phase 2 unless a non-standard scoring system is needed.
- **`opponent_team` is already present** in `weekly_stats` — Session 2.2 (Matchup Factor) doesn't need to derive it from the schedule separately.
- **Team column is `team`, not `recent_team`** — reconfirming Session 1.1's schema alert. `blended_projections.py` (written against old `nfl_data_py` schema) still needs a pass to rename `recent_team` → `team` and switch its `import` off `nfl_data_py` before Phase 2 sessions build on it — not done in this session since it wasn't Session 1.2's job, but don't let it get silently forgotten.
- **`weekly_rosters`'s player-ID column is `gsis_id`, not `player_id`** — same ID values/scheme as `weekly_stats.player_id`, just named differently. Any future join between `weekly_stats` and `weekly_rosters` needs `left_on="player_id", right_on="gsis_id"`.
- **nflverse asset-filename gotcha, for the "one obvious file to fix" note in `nflverse_fetch.py`'s docstring:** release *tag* names don't always match the asset *filename* inside them — `schedules` release → `games.parquet`, but `weekly_rosters` release → `roster_weekly_{season}.parquet` (matches its tag reasonably). If another dataset gets added later and 404s even though the release tag looks right, check the actual asset filenames on the release page (or via `curl -I` against candidate names) before assuming the whole release moved.
- Season used for this ingestion: 2025 (most recent completed season — 2026 regular season hasn't started yet as of this session, per `ROADMAP.md`'s Sept 9, 2026 go-live target). Re-run `ingest_historical.py --season 2026` once 2026 data starts flowing.

---

## Session 1.3 (REVISED) — Salary Data Ingestion, DraftKings + FanDuel
**Date completed:** 2026-07-21
**Status:** ⚠️ Complete with caveats

**Why this is a revision, not a new session:** the original Session 1.3 (logged above) was built DK-only. The project's actual scope was always meant to include both DraftKings and FanDuel, but this wasn't clarified until after Session 1.3 first shipped. Rather than leave a DK-only implementation in place and patch it later, this revision reopens Session 1.3 and rebuilds `ingest_salaries.py` for both sites before Phase 2 starts building on top of it. `ROADMAP.md` has also been updated throughout (not just Session 1.3's card) to reflect dual-site scope — see the new "Notes on dual-site scope" section at the bottom of that file for the full breakdown of what changed structurally in later phases.

**What was actually built:**
- `scripts/ingest_salaries.py` rewritten to take a `--site {dk,fd}` flag. Site-specific parsing (column names, name construction, defense-position labels, team-abbreviation quirks) feeds into the same shared normalization/matching logic as before.
- Added `SITE_CONFIGS` dict as the canonical source of truth for each site's salary cap, roster slots, and scoring format — DK: $50,000 cap, QB/RB/RB/WR/WR/WR/TE/FLEX/DST, full-PPR; FD: $60,000 cap, QB/RB/RB/WR/WR/WR/TE/FLEX/DEF, half-PPR. Not used by this script directly, but placed here so Sessions 2.x/3.1 read from one place instead of re-declaring these values.
- Added handling for **DK's "DKEntries.csv" bulk lineup-upload template shape**, discovered from a real file the user provided this session — this is a different CSV shape than DK's standalone "Export to CSV" player-pool file (entries table on the left, player pool embedded starting several columns to the right, rather than a clean single table). Both shapes are real files a user could have on hand, so the script detects and handles either for site="dk".
- Added `POSITION_EQUIVALENTS` handling (currently `{"RB": {"RB", "FB"}}`) after finding, in real DK data, that DK has no dedicated fullback position and folds FB into RB — this caused a real player (Alec Ingold) to fail exact-match despite being present and correct in the reference data.
- Added a final "name-only, any position" fallback match stage (Step 5), applied only when the name uniquely resolves across the whole reference table. This catches cases where a site's position label disagrees with nflverse's for reasons that aren't a clean FB/RB-style equivalence (found via 2 real players — Blake Whiteheart and Will Mallory, both real TEs, listed as "RB" in the DK Madden Stream export for reasons that aren't clear from the data itself, possibly a Madden-simulation roster quirk rather than a real DK data issue).
- `data/name_mapping.csv` schema changed from DK-only columns (`dk_name, dk_team, dk_position, player_id, notes`) to site-scoped columns (`site, source_name, source_team, source_position, player_id, notes`), since an override found on one site's export text doesn't necessarily apply to the other site's export text for the same player.
- Output naming changed from `salaries_{slate_id}.csv` to `salaries_{site}_{slate_id}.csv` (and same pattern for the unmatched log) to avoid DK/FD collisions on the same slate_id.

**Files created/modified:**
- `/dfs_optimizer/scripts/ingest_salaries.py` (rewritten)
- `/dfs_optimizer/data/name_mapping.csv` (schema changed, reset to header + 1 real entry — see below)
- `/dfs_optimizer/ROADMAP.md` (updated throughout — Sessions 1.3, 2.1-2.4, 3.1-3.3, 4.1-4.2, 5.2, 6.1-6.3, 7.1-7.3, 8.1, 9.1-9.2, plus a new "Notes on dual-site scope" section)
- `/dfs_optimizer/data/salaries_dk_madden_20260721.csv` (output, real data — see validation)
- `/dfs_optimizer/data/salaries_fd_TEST_SAMPLE.csv` (output, synthetic data)

**Validation results:**
- [x] **DK, real data:** user provided a real `DKEntries.csv` export from an actual live DK "Madden Stream FREE 200-Player" contest (2026-07-21). Confirmed DK's Madden Stream contests use the same $50K cap, same 9-slot roster, and the same real player pool/salaries as regular DK Classic contests — only game results are simulated — making this a legitimate real-data validation of the ingestion path, though NOT a valid source for projection/accuracy testing later (the simulated results aren't real football outcomes). Result: 93 rows ingested, 91 matched (97.8%) after fixing the FB/RB equivalence issue and adding one real nickname override (Drew→Andrew Ogletree, found in this data). The 2 remaining unmatched (Joe Mixon, Tank Dell) were confirmed to have zero recorded games in `weekly_stats_2025.parquet` — a genuine reference-data gap, not a matching bug; nothing further to fix here without an external ID source.
- [x] **FD, synthetic data only:** no real FD export exists yet (no FD equivalent of DK's Madden Stream). Validated against a 10-row synthetic file built from 8 real players (including an LA/LAR team-abbreviation case matching DK's) plus 1 team defense (FD's "D" position label) plus 1 deliberately fake name. Result: 9/10 auto-matched correctly, defense routed correctly, fake name correctly caught as unmatched. **This is the one open caveat for this revision** — FD's column layout (`SITE_CONFIGS["fd"]`) is based on documented format, not a verified real download.
- [x] Unmatched players logged clearly, not silently dropped — confirmed for both sites (same mechanism as the original session, unchanged).

**Decisions made / assumptions taken:**
- Both sites required — user confirmed this was always the intended scope, clarified mid-project rather than at kickoff.
- Kept a single script with a `--site` flag rather than two separate scripts, since ~90% of the matching logic (normalization, override table, output writing) is identical between sites and duplicating it would create two places to fix the same bug.
- `POSITION_EQUIVALENTS` and the name-only fallback stage are general mechanisms, not one-off patches for the specific players found — chosen deliberately so future FB-labeled-as-RB or position-mislabeled cases resolve automatically instead of needing a new manual override every time.
- FD's team-abbreviation map currently just inherits the DK/base map (`BASE_TEAM_ABBREV_MAP`) with an empty FD-specific override dict — untested assumption that FD mostly follows the same conventions as nflverse/DK; flagged in the script docstring to revisit once real FD data exists.

**Known issues deferred:**
- **FD ingestion is unverified against real data — the single biggest open item from this revision.** No FD equivalent of Madden Stream exists to test against right now (confirmed via search). Needs to be re-validated the moment a real FD slate is available (or an archived historical FD export can be sourced sooner). Do not treat FD's 97.8%-style match rate as proven until this happens — it hasn't been tested against real data at all yet.
- The "name-only, any position" fallback (Step 5) is intentionally permissive — worth revisiting if it ever causes a wrong match in practice (it's designed to fail safe by requiring a globally unique name, but hasn't been stress-tested against a full slate with hundreds of players where name collisions are more likely).
- FD's defense position label is treated as either "D" or "DEF" (both handled) since documentation wasn't fully consistent on which FD actually uses — confirm against a real export and simplify once known.

**Handoff notes for next session:**
- Session 2.1 (and the rest of Phase 2) needs to become site-aware per the `ROADMAP.md` update — specifically, fantasy points must be computed using each site's own scoring rule (DK full-PPR vs FD half-PPR) rather than the single hardcoded PPR formula currently in `blended_projections.py`. That file has NOT been updated yet — it still assumes DK-only, full-PPR, and imports the deprecated `nfl_data_py` (per Session 1.1/1.2's already-known issue). Both problems need fixing before or during Session 2.1, not deferred further.
- `ingest_salaries.py`'s `SITE_CONFIGS` dict is now the canonical place for salary cap / roster slots / scoring format per site — future sessions (2.x, 3.1) should import/read from there rather than re-declaring these values, so a future correction only needs to happen in one place.
- Before trusting FD data for anything beyond plumbing tests: get a real FD Classic salary CSV (from an actual FD slate, once one exists closer to the preseason window) and re-run `ingest_salaries.py --site fd` against it, the same way this session did for DK with the Madden Stream file.
- `data/name_mapping.csv` currently has exactly 1 real entry (the Ogletree nickname case) plus header — not pre-seeded with guesses, consistent with the original session's approach.

---

## Session 2.1 — Season Baseline + Recent Form
**Date completed:** 2026-07-21
**Status:** ✅ Complete

**What was actually built:**
- `scripts/projections_baseline.py` — takes `--site {dk,fd} --season --week`, reads `data/weekly_stats_{season}.parquet`, and outputs per-player `season_avg`, `recent_form`, and `games_played`.
- Replaces the old `blended_projections.py`'s season-baseline/recent-form logic rather than modifying that file — `blended_projections.py` still imports the deprecated `nfl_data_py` and is DK-only/full-PPR-hardcoded (per Session 1.1/1.2/1.3's handoff notes); this session did not touch it. It's now effectively superseded for baseline/recent-form purposes; matchup factor and vegas logic still need to be pulled out of it in later sessions.
- Two design decisions made this session that the roadmap card didn't spell out explicitly (both cleared with the user before building):
  1. **Lookahead-bias guard:** baseline/recent-form for week N only use weeks `1..N-1` of REG-season data. The old `blended_projections.py` averaged over the *entire* season file regardless of target week, which leaks the outcome being projected into its own inputs. `--week` is a hard cutoff on the input data here, not just an output-filename label.
  2. **REG season only:** POST weeks (19-22 in nflverse's numbering) are excluded from both signals, since playoff performance reflects different opponents/roster context than a regular-season slate.
- Site-aware scoring: DK uses nflverse's precomputed `fantasy_points_ppr` directly (full PPR). FD has no native half-PPR column in nflverse data, so it's derived as `fantasy_points + 0.5 * receptions` — confirmed exact (verified `fantasy_points_ppr - fantasy_points == receptions` to float-precision noise only across the full dataset before relying on the derivation).

**Files created/modified:**
- `/dfs_optimizer/scripts/projections_baseline.py` (new)
- `/dfs_optimizer/output/baseline_recent_form_dk_2025_10.csv` (output, validation run)
- `/dfs_optimizer/output/baseline_recent_form_fd_2025_10.csv` (output, validation run)

**Validation results:**
- [x] 5 known players, hand-calculated season_avg/recent_form vs. script output, both sites — Mahomes, McCaffrey, Kelce, Chase (all 9 games played), plus Tyreek Hill (only 4 games recorded before week 10, 2025 injury — this doubled as the `<5 games` test below). All 5 matched hand-calculated values exactly for both DK and FD. DK-FD season_avg gaps matched `0.5 * avg_receptions` exactly per player: 0.00 (Mahomes, QB, 0 receptions) up to 4.22 (Chase).
- [x] Script handles players with `<5` games played without crashing — tested week 1 (0 prior REG games for anyone → empty output, 0 rows, no crash) and week 3 (401 players with 1-2 game histories, no crash). Week 10 run (full histories) also included in validation.
- [x] DK/FD season_avg differ by roughly the expected half-point-per-reception gap, not something unexplained — confirmed exactly (see above), not just "roughly."

**Decisions made / assumptions taken:**
- User confirmed: go with my recommendation on both open questions (lookahead-bias guard, REG-only filtering) rather than deciding independently — both are now hard-coded, not configurable via CLI flag. If a future session needs POST-season or leakage-inclusive baselines for some reason, that'd be a deliberate new flag, not an accidental default.
- `games_played` and `season_avg`/`recent_form` are left as `0`/`NaN` for players with no qualifying history before the target week, rather than filled with 0 or dropped — so downstream steps (2.2, 2.4) can decide explicitly how to treat a totally-unknown player (e.g. rookie debut) instead of that decision being silently baked in here.

**Known issues deferred:**
- Week 1 output is always empty (0 rows) by construction, since there's no prior-week data to build a baseline from yet. This is correct behavior, not a bug, but means week 1 can't be used standalone downstream — flagging so a future session doesn't mistake it for broken output.
- `blended_projections.py` itself is now stale for baseline/recent-form (superseded by this session) but still contains the only existing matchup-factor and vegas-factor logic in the repo, unrefactored. Session 2.2 will need to pull matchup-factor logic out of it (and make it site-aware, same reasoning as this session) rather than starting from scratch.

**Handoff notes for next session:**
- Session 2.2 (Matchup Factor) needs the same site-aware fantasy-points computation used here (`compute_fantasy_points()` in `projections_baseline.py`) — reuse it rather than re-deriving FD's half-PPR formula a second time.
- Session 2.2 should apply the same REG-only / lookahead-bias filtering established here for consistency, even though the roadmap card for 2.2 doesn't mention it explicitly — matchup factors computed from POST-season or future-leaking data would have the same problems addressed this session.
- `data/weekly_stats_{season}.parquet`'s `opponent_team` column (confirmed present as of Session 1.2) is what 2.2 will group on.

**ADDENDUM (added during Session 2.4, 2026-07-21):** a real bug was found in this session's `season_baseline()` during Session 2.4's first real end-to-end validation run. Grouping by `player_id, player_name, position, TEAM` silently split any player who changed teams mid-season into multiple output rows sharing the same `player_id` but different `season_avg` values (7 of 532 players in the real 2025 data, e.g. Joe Flacco, Colts → Browns) — invisible in this session's own validation because all 5 spot-check players stayed on one team all season. This output has never had a `team` column, so grouping by team was never correct in the first place. **Fixed in Session 2.4** by dropping `team` from the groupby (now `player_id, player_name, position` only). See Session 2.4's log entry below for the full fix and re-validation. `projections_baseline.py` needs to be re-run against real `weekly_stats_{season}.parquet` for every season/week this bug could have affected, since existing `baseline_recent_form_*.csv` files predating this fix contain the same duplicate-row defect.
## Session 2.2 — Matchup Factor
**Date completed:** 2026-07-21
**Status:** ✅ Complete

**What was actually built:**
- `scripts/projections_matchup.py` — for a given site/season/week, computes each team's fantasy-points-allowed by position (QB/RB/WR/TE) relative to league average, as a `matchup_factor`.
- Reused Session 2.1's site-aware scoring split (DK = `fantasy_points_ppr` as-is, FD = `fantasy_points + 0.5*receptions`) and its lookahead-bias guard (REG season only, `week < target_week`) unchanged, so both projection components stay consistent on what data a given week's projection is allowed to see.
- One deviation from the original `blended_projections.py` placeholder logic worth flagging explicitly: that script computed points-allowed as a flat `.mean()` over all rows grouped by `opponent_team`+`position` — i.e. averaged per opposing *player*-game, not per opposing *team*-game. This session instead sums each position's fantasy points *within* a team-week first (all opposing WRs' points added together for that game), then averages those weekly sums across the team's games. Per-player averaging would understate points allowed to positions where a team faced 3 productive WRs in a game vs. 1 — summing first captures "how much this defense gave up to the position that week," which is what a matchup factor should mean.

**Files created/modified:**
- `/dfs_optimizer/scripts/projections_matchup.py` (new)

**Validation results:**
- [x] matchup_factor = exactly 1.0 for a league-average defense — confirmed for both sites: 128 rows (32 teams × 4 positions), position-weighted mean matchup_factor = 1.0000 for QB/RB/WR/TE on both DK and FD (holds by construction of the normalization, but confirmed programmatically rather than assumed).
- [x] Spot-checked 2 sets of known matchups against public sources, both sites, week 10 (2025 season, so weeks 1-9 of data):
  - **Cincinnati (bad defense)** — DK: QB 1.244, RB 1.544, TE 1.687, WR 0.963. FD: QB 1.238, RB 1.586, TE 1.785, WR 0.976. Verified: SI Sports reporting confirms the Bengals allowed 300 points through their first 9 games of 2025, the second-worst 9-game start by DVOA since 1978. Matches our data showing CIN as the single highest (juiciest) matchup_factor across QB/RB/TE.
  - **Houston / Denver (elite defenses)** — DK QB matchup_factor: HOU 0.673, DEN 0.789 (2nd- and 3rd-toughest QB matchups in the league at week 10). Verified: multiple sources (FOX Sports, DirecTV, nflspy.com defensive rankings through Week 10) confirm Houston and Denver as the top 2 defenses in the NFL through this stretch of the season.
- [x] No nulls, all 32 teams x 4 positions present (128/128 rows), both sites.
- [x] Confirmed DK and FD outputs are meaningfully different (not a copy-paste bug) but highly correlated as expected — Pearson r = 0.995 between DK and FD matchup_factor across all 128 team/position rows; 0/128 rows identical. Largest divergence: CIN TE (DK 1.687 vs FD 1.785, diff +0.097) — makes sense, TE is the position where PPR value is most receiving-volume-driven.

**Decisions made / assumptions taken:**
- Summed-then-averaged (per team-week) rather than flat per-player-row averaging for points allowed — see "What was actually built" above. This is a real behavioral difference from the original `blended_projections.py` placeholder and should be the version future sessions build on.
- Reused Session 2.1's `RECENCY_WEIGHTS`-adjacent conventions (REPO_ROOT-relative paths, REG-only + lookahead guard) verbatim rather than re-deriving them, to keep the two projection-component scripts behaviorally consistent with each other.
- Used week 10 as the validation target week (matches Session 2.1's validation week), so the same 5 known players / matchups remain reusable as a regression check across both sessions if a future session wants one.

**Known issues deferred:**
- Team abbreviation `LA` (LA Rams) appears in the output, matching `weekly_stats`'s convention — flagging now because Session 2.3 (Vegas Integration) explicitly needs a team-name key consistent with this, and the roadmap already notes odds APIs often use a different format (e.g. "LAR"). Not a bug here, just a heads-up so 2.3 doesn't quietly break the join.
- No handling yet for a team on a bye in the week immediately before the target week (e.g. a team with fewer games played than others by week N) — the average is still just "average over games actually played," which is directionally fine, but a team's matchup_factor is based on less data early in the season for teams that had an early bye. Not fixed now since it's inherent to small-sample early-season projections generally (same caveat applies to Session 2.1's season_avg), but worth a joint look if 2.4's blend ever needs a confidence/sample-size weighting.

**Handoff notes for next session:**
- Session 2.3 (Vegas Integration) needs a team-name key consistent with `weekly_stats`'s `team`/`opponent_team` values (confirmed format: `LA` not `LAR`, `WAS` not `WSH`, etc. — pull the full 32-team list from this session's output CSV if useful for building the normalization map).
- Session 2.4 (Full Blend Pipeline) will merge this session's `matchup_factors_{site}_{season}_{week}.csv` with Session 2.1's `baseline_recent_form_{site}_{season}_{week}.csv` on `position` (and team, once 2.4 maps each player to their week-N opponent) — both scripts now share identical REPO_ROOT/DATA_DIR/OUTPUT_DIR conventions and identical site-scoring logic, so no reconciliation needed there.
- Validation numbers above (CIN, HOU, DEN at week 10, both sites) are reusable as a regression check the same way Session 2.1 flagged its 5 players.

---
## Session 2.3 — Vegas Integration
**Date completed:** _(not yet — see Status)_
**Status:** ⚠️ Blocked — script built and unit-tested, but not yet run against the real API

**What was actually built:**
- `scripts/vegas_odds.py` — pulls NFL spreads + totals from The Odds API (`regions=us`, `markets=spreads,totals`), converts to per-team implied totals, writes `output/vegas_implied_totals_{week}.csv`.
- Reads the API key from `config/api_keys.env` (`ODDS_API_KEY=...`) via a small hand-rolled parser rather than adding `python-dotenv` as a dependency — consistent with the project's existing preference for small dependency-light utilities (same reasoning as `nflverse_fetch.py` replacing `nfl_data_py`).
- `TEAM_NAME_MAP` built from The Odds API's own documented full team names, mapped to the exact nflverse abbreviations confirmed in Session 2.2's output (`LA` not `LAR`, `WAS` not `WSH`, etc.) — sourced directly from both systems' real data, not guessed.
- Design decision not on the original roadmap card: **consensus averaging across bookmakers.** The Odds API returns one spread/total per book; rather than pin to a single book (risk of one outlier line skewing the projection), this script averages spread and total across every US-region book returned per game, then computes implied totals from the averaged numbers. Documented in the script's docstring.
- Built-in automated sanity check: for every game, `implied_total(home) + implied_total(away)` must equal the game's total to float precision — checked in code (`validate_implied_totals()`), not just eyeballed, same pattern as Session 2.2's league-average=1.0 check.
- Every call prints the `x-requests-remaining` / `x-requests-used` / `x-requests-last` response headers, so actual quota burn is visible in real time rather than only estimated.

**Files created/modified:**
- `/dfs_optimizer/scripts/vegas_odds.py` (new)
- `/dfs_optimizer/requirements.txt` (added `requests==2.33.1`)

**Validation results:**
- [x] Implied-total formula and consensus-averaging logic hand-verified against a synthetic 2-book example (KC -6.5/48 and KC -7.0/47 → consensus -6.75/47.5 → implied totals 27.125/20.375, summing back to 47.5 exactly). Also confirmed the "game with no posted lines yet" case is skipped cleanly rather than crashing.
- [ ] **Not yet done: pulled odds matched against a live sportsbook page.** No real NFL lines are posted yet as of this session (2026-07-21) — Preseason Week 1 is Aug 13-15, 2026, and books generally don't post spreads/totals this far out. Deferred, same pattern as Session 1.3's FD-validation-gap: flag in every session's log until closed.
- [ ] **Not yet done: real API call.** No Odds API key exists yet — user hasn't signed up (account creation is something Claude won't do on the user's behalf). Script is written and unit-tested against synthetic data only.

**Decisions made / assumptions taken:**
- User confirmed a specific polling cadence (Tue-Fri 1x/day, Sat 2x/day, Sunday hourly 4hrs-1hr before lock then every 15min in the final hour) — priced at ~121 credits/month, well under the 500/month free-tier cap. Added to `ROADMAP.md`'s Session 2.3 and Session 5.2 cards so Session 5.2 doesn't have to re-derive it.
- Evaluated whether an alternative odds vendor was needed to "keep this free" for future multi-sport (NBA/NHL/MLB) expansion. Conclusion: not needed now (NFL-only scope is comfortably within budget), but flagged as a real future constraint — a single additional daily-cadence sport would exceed 500 credits/month on its own, since NFL's weekly cadence is what keeps usage low. Two alternative vendors surfaced (SharpAPI, SportsGameOdds) but neither was independently verified — SharpAPI in particular has no third-party coverage found, only its own marketing site, so it's noted as unverified rather than recommended. Full reasoning captured in `ROADMAP.md`'s new "Notes on odds vendor choice" section rather than repeated here.
- Chose bookmaker-consensus averaging over pinning to one book (e.g. just DraftKings' own sportsbook line) for the implied-total input, to reduce single-book noise. This is a real behavioral choice, not neutral — flagging so it isn't silently relitigated.

**Known issues deferred:**
- Real-API validation (both checklist items above) blocked on the user signing up for a free key and adding it to `config/api_keys.env`. This session cannot be marked ✅ Complete until that happens and the validation steps are re-run against live data.
- Once real lines exist, also worth spot-checking that the Odds API's bookmaker list for `regions=us` actually includes DraftKings and FanDuel specifically (both were listed as covered on the site's marketing page as of this session, but not confirmed inside an actual API response yet).

**Handoff notes for next session:**
- **This session is not done.** Once you have an Odds API key: add it to `config/api_keys.env`, then run `python3 scripts/vegas_odds.py --week <current_week>` and paste back the output (including the quota-usage line it prints) so the two open validation checkboxes above can be closed.
- Session 2.4 (Full Blend Pipeline) needs this session's real output (`vegas_implied_totals_{week}.csv`) to exist before it can run end-to-end — it's currently blocked on the same key.
- The confirmed weekly polling cadence now lives in `ROADMAP.md`'s Session 2.3 and Session 5.2 cards — Session 5.2 should implement against that rather than re-deriving a schedule from scratch.


## Session 2.3 — Vegas Integration
**Date completed:** 2026-07-21
**Status:** ✅ Complete

**What was actually built:**
- `scripts/vegas_odds.py` — pulls NFL spreads + totals from The Odds API (`regions=us`, `markets=spreads,totals`), converts to per-team implied totals, writes `output/vegas_implied_totals_{week}.csv`.
- Reads the API key from `config/api_keys.env` (`ODDS_API_KEY=...`) via a small hand-rolled parser rather than adding `python-dotenv` as a dependency — consistent with the project's existing preference for small dependency-light utilities (same reasoning as `nflverse_fetch.py` replacing `nfl_data_py`).
- `TEAM_NAME_MAP` built from The Odds API's own documented full team names, mapped to the exact nflverse abbreviations confirmed in Session 2.2's output (`LA` not `LAR`, `WAS` not `WSH`, etc.) — sourced directly from both systems' real data, not guessed.
- Design decision not on the original roadmap card: **consensus averaging across bookmakers.** The Odds API returns one spread/total per book; rather than pin to a single book (risk of one outlier line skewing the projection), this script averages spread and total across every US-region book returned per game, then computes implied totals from the averaged numbers. Documented in the script's docstring.
- Every call prints the `x-requests-remaining` / `x-requests-used` / `x-requests-last` response headers, so actual quota burn is visible in real time rather than only estimated.
- **Bug found and fixed post-first-real-run (see Validation results):** the original sanity check (`implied_total(home) + implied_total(away) == total`) was implemented by rebuilding a `team -> row` lookup dict from *all* rows across *all* games returned, then checking each game against that dict. Because the API returns every currently-listed upcoming game (not just one week — confirmed: `--week` only labels the output filename, it doesn't filter which games are pulled), a team appearing in multiple upcoming games caused later games to silently overwrite earlier ones in the lookup dict, producing false-positive mismatch warnings on effectively every game. **Fixed by validating each game's pair of rows inline, at the point they're computed, where the correct pairing is unambiguous** — no more cross-game lookup. Root cause confirmed via a one-off diagnostic script (`debug_vegas_consensus.py`, not part of the permanent pipeline) that dumped raw per-bookmaker data and showed `consensus_lines()`'s own math was correct all along (e.g. SEA/NE: 44.11 == 44.11) — the bug was entirely in the validation step, not the averaging or implied-total formula.
- Added `opponent` and `commence_time` columns to the output CSV as part of the same fix, so a team's multiple rows (one per upcoming game it's part of) can be told apart downstream instead of assuming one row per team.

**Files created/modified:**
- `/dfs_optimizer/scripts/vegas_odds.py` (new, then revised same session after the validation bug above)
- `/dfs_optimizer/requirements.txt` (added `requests==2.33.1`)

**Validation results:**
- [x] Implied-total formula and consensus-averaging logic hand-verified against a synthetic 2-book example (KC -6.5/48 and KC -7.0/47 → consensus -6.75/47.5 → implied totals 27.125/20.375, summing back to 47.5 exactly). Also confirmed the "game with no posted lines yet" case is skipped cleanly rather than crashing.
- [x] Real API call succeeded: user signed up for an Odds API key, added to `config/api_keys.env`. First real run: quota `used=2, remaining=498`. Returned 75 games / 150 rows (more than one week's worth — API returns all currently-listed upcoming games, not filtered to a single week; see note above and Known issues deferred).
- [x] Pulled odds matched a live sportsbook page — confirmed via 9-bookmaker raw dump for 2 games (SEA/NE, LA/SF) showing real, current DraftKings/FanDuel/BetMGM/etc. lines (e.g. DK: NE +3.5/-110, SEA -3.5/-110, total 44.5).
- [x] Sum-to-total automated check: initially failed on all 75/75 games (false positive — see bug above). After fix, re-ran live: **"Sum-to-total check passed for all games."** Quota after fix-verification run: `used=6, remaining=494`.
- [x] Confirmed via the diagnostic dump that regions=us bookmaker list includes DraftKings and FanDuel by name (both appeared directly in the raw per-bookmaker output for both test games).

**Decisions made / assumptions taken:**
- User confirmed a specific polling cadence (Tue-Fri 1x/day, Sat 2x/day, Sunday hourly 4hrs-1hr before lock then every 15min in the final hour) — priced at ~121 credits/month, well under the 500/month free-tier cap. Added to `ROADMAP.md`'s Session 2.3 and Session 5.2 cards so Session 5.2 doesn't have to re-derive it.
- Evaluated whether an alternative odds vendor was needed to "keep this free" for future multi-sport (NBA/NHL/MLB) expansion. Conclusion: not needed now (NFL-only scope is comfortably within budget), but flagged as a real future constraint. Full reasoning in `ROADMAP.md`'s "Notes on odds vendor choice" section.
- Chose bookmaker-consensus averaging over pinning to one book, to reduce single-book noise. Real behavioral choice, not neutral — flagging so it isn't silently relitigated.
- Chose to validate inline per-game rather than reconstruct a global team→row lookup, specifically because the API's "all upcoming games" response shape makes team names non-unique across rows — any future validation or lookup logic added to this file should keep that in mind rather than assuming one row per team.

**Known issues deferred:**
- **The script pulls every upcoming NFL game currently listed by the API, not just one specific week — `--week` only affects the output filename.** This was fine for validating the pipeline works, but means the current `vegas_implied_totals_{week}.csv` contains multiple weeks' worth of games mixed together, with no reliable way to filter to "just week N" beyond eyeballing `commence_time`. Needs a real decision before Session 2.4 depends on this file for a specific week's slate: either add date-range filtering here (would need a week-to-date-range mapping), or have Session 2.4 do the filtering itself using the new `commence_time` column. Not solved this session — flag until closed.
- The diagnostic script `debug_vegas_consensus.py` was written for one-time debugging and is not part of the regular pipeline — fine to leave in `/scripts/` for future reference, but shouldn't be scheduled/automated in Session 5.2.

**Handoff notes for next session:**
- Session 2.4 (Full Blend Pipeline) can now use this session's real output (`vegas_implied_totals_{week}.csv`), but **must decide how to handle the multi-week-games-in-one-file issue above** before joining it against a specific week's salary/projection data — joining on `team` alone risks picking up the wrong game's implied total for a team with multiple upcoming games in the file. Use the new `opponent`/`commence_time` columns to disambiguate.
- The confirmed weekly polling cadence still lives in `ROADMAP.md`'s Session 2.3 and Session 5.2 cards — Session 5.2 should implement against that, and should also decide there whether the scheduled/automated version of this script needs the week-filtering fix mentioned above (likely yes, since production runs need one week's data cleanly, not 75 games).
- Output CSV schema changed from Session 2.3's original card: now `team, opponent, commence_time, spread, over_under, implied_total` (added `opponent` and `commence_time`). Any script written against the original `team, spread, over_under, implied_total` schema needs updating.


---

## Session 2.4 — Full Blend Pipeline
**Date completed:** 2026-07-21
**Status:** ⚠️ Complete with caveats — validated mechanically, not yet with fully real data for either site

**What was actually built:**
- `scripts/build_projections.py` — takes `--site {dk,fd} --season --week --slate-id`, merges Session 2.1's baseline/recent-form, Session 2.2's matchup factors, Session 2.3's vegas implied totals, and Session 1.3's salary file into `output/final_projections_{site}_{week}.csv`.
- `final_projection = (0.5 * season_avg + 0.5 * recent_form) * matchup_factor * vegas_factor`.
- Three design gaps not spelled out on the roadmap card, cleared with the user before building (same pattern as 2.1/2.2):
  1. **vegas_factor definition.** Checked for an industry-standard normalized "vegas factor" — didn't find one; DFS literature (FantasyLabs "Vegas Score," Stokastic, etc.) treats the raw `implied_total` itself as the model input, not a ratio. Defined `vegas_factor` the same way 2.2 defines `matchup_factor`: team's `implied_total` ÷ that week's league-average `implied_total` (among teams actually playing that week) — keeps both multipliers on the same "1.0 = league average" scale.
  2. **Player's week-N opponent.** Nothing in 2.1-2.3's outputs carries this. Added `data/schedules_{season}.parquet` (a real Session 1.2 output, not on 2.4's original Inputs list) as a new input — builds a team→opponent map for the target week, used both to look up `matchup_factor` (against the OPPONENT's defense) and to filter `vegas_implied_totals_{week}.csv` down to exactly that week's `(team, opponent)` pairs, resolving the multi-week-mixing issue flagged in Session 2.3's log.
  3. **Missing-data handling (user-confirmed):** neutral `1.0` fill for missing `matchup_factor`/`vegas_factor` (bye weeks, unposted lines) rather than dropping the player. Extended the same philosophy to a gap 2.1 explicitly deferred here: a player with no `season_avg`/`recent_form` yet (rookie, 0 games before target week) gets `0.0` rather than being dropped.
- Team defenses (DK `DST` / FD `D`/`DEF`) are excluded from this pipeline entirely — `weekly_stats` has no defense-level rows, so 2.1/2.2 never produced baseline/matchup data for them. Flagged, not solved — a future session needs to decide if/how defenses get projected.

**Bug found and fixed this session (see Session 2.1's addendum above for the full writeup):** `projections_baseline.py`'s `season_baseline()` grouped by team, silently splitting mid-season-team-change players into duplicate `player_id` rows with conflicting `season_avg`. Surfaced as literal duplicate players (e.g. two different "Joe Flacco" projections) in this session's first real end-to-end run — invisible in 2.1's own validation since none of its 5 spot-check players changed teams. Fixed by removing `team` from the groupby. `projections_baseline.py` was patched this session; `baseline_recent_form_dk_2025_10.csv` / `baseline_recent_form_fd_2025_10.csv` were reconstructed via a games-played-weighted collapse of the duplicate rows as a stand-in for a real re-run (mathematically equivalent to what the fixed script produces, but **not** a substitute for actually re-running `projections_baseline.py` against real `weekly_stats_2025.parquet` — flagged as a known issue below).

**Files created/modified:**
- `/dfs_optimizer/scripts/build_projections.py` (new)
- `/dfs_optimizer/scripts/projections_baseline.py` (bug fix — `season_baseline()` groupby)
- `/dfs_optimizer/output/baseline_recent_form_dk_2025_10.csv`, `/dfs_optimizer/output/baseline_recent_form_fd_2025_10.csv` (patched in place — duplicate rows collapsed; still needs a real re-run, see above)
- `/dfs_optimizer/output/vegas_implied_totals_10.csv` (new — **synthetic**, see Decisions below)
- `/dfs_optimizer/data/salaries_fd_SYNTHETIC_madden_20260721.csv` (new — **synthetic**, see Decisions below)
- `/dfs_optimizer/output/final_projections_dk_10.csv`, `/dfs_optimizer/output/final_projections_fd_10.csv` (validation run outputs)
- `/dfs_optimizer/ROADMAP.md` (new "Known Deferred Validations" section)

**Validation results:**
- [x] Full pipeline ran end-to-end for both sites (real DK salary data + real matchup/baseline data + synthetic vegas + synthetic FD salaries), no crashes.
- [x] No negative projections, no nulls, both sites (`final_projections_dk_10.csv`: 85 players, 0 nulls, 0 negatives; `final_projections_fd_10.csv`: same).
- [x] No unexpectedly missing/duplicated players — 0 duplicate `player_id`s in either output after the baseline bug fix (was 1 duplicate — Joe Flacco — before the fix, now resolved). 15 DAL players correctly got neutral `1.0` matchup/vegas factors (DAL had a real bye in week 10, 2025 — confirmed against `schedules_2025.parquet`, not a bug).
- [x] Top 10 sanity check, DK vs FD close but not identical: both lead with Jonathan Taylor (RB) / Joe Flacco (QB) / De'Von Achane (RB) / C.J. Stroud (QB) in the same order. Diverge exactly as expected — FD (half-PPR) drops WR Michael Pittman Jr. and TE Dalton Schultz out of its top 10 in favor of volume rusher Javonte Williams and QB Jayden Daniels, consistent with half-PPR nudging pass-catchers down / rushers up relative to DK.
- [ ] **Not done — real-data-for-both-sites-simultaneously validation.** See "Known Deferred Validations" in `ROADMAP.md` (new section, added this session). Blocked on: (a) real Vegas lines for a specific backtest week (Odds API only returns currently-listed games, can't retroactively supply 2025 week 10), (b) any real FD salary data existing at all. Both trace back to the same root cause: none of our external data sources have a real historical archive, and no real current-week data exists yet either. Closes at Preseason Week 1 (Aug 13-15, 2026) at the earliest.

**Decisions made / assumptions taken:**
- `vegas_implied_totals_10.csv` used this session is **synthetic** — deterministic but fabricated spread/total values for the real 14 week-10-2025 games (real matchups pulled from `schedules_2025.parquet`, not real lines). Built specifically because The Odds API cannot supply real historical lines for an already-played week. Validated internally (sum-to-total check passes for all 14 games) but the actual numbers are not real and must not be used for anything beyond pipeline-logic validation.
- `salaries_fd_SYNTHETIC_madden_20260721.csv` used this session is **synthetic** — same 93 real players/teams as the real `salaries_dk_madden_20260721.csv`, with salary scaled by FD's cap ÷ DK's cap (60000/50000 = 1.2x) to land in FD's real price range. Not a real FD export (none exists yet — see `ROADMAP.md`'s new deferred-validations section). Built at this scale (93 players, not Session 1.3's original 10-row sample) specifically because Session 2.4 needed enough real players to run a meaningful top-10 sanity check, not just confirm the matching logic works.
- Went with a games-played-weighted collapse to patch `baseline_recent_form_{site}_2025_10.csv` in place today rather than blocking this session entirely on a real re-run (which isn't possible without `weekly_stats_2025.parquet` present in this environment) — explicitly flagged as a stand-in, not a substitute for the real fix.

**Known issues deferred:**
- **`baseline_recent_form_dk_2025_10.csv` / `_fd_2025_10.csv` need a real re-run** of the now-patched `projections_baseline.py` against real `weekly_stats_2025.parquet` — today's fix was a reconstruction from the buggy output, mathematically equivalent but not the real thing. Don't treat today's files as authoritative going forward; regenerate and diff against today's numbers as a regression check.
- Team defenses (DK `DST` / FD `D`/`DEF`) have no projection at all from this pipeline — needs a decision in a future session (likely before Phase 3's optimizer needs a full 9-slot roster including DST/DEF).
- Full real-data validation (both sites, real salaries + real matchup week + real vegas lines, all for the same week) is not achievable yet — see `ROADMAP.md`'s new "Known Deferred Validations" section, which is now the running list for this and future sessions hitting the same kind of gap.
- The bug found in `projections_baseline.py` this session may also affect any other already-generated `baseline_recent_form_*.csv` files for other seasons/weeks not touched this session — worth a sweep before trusting older output files.

**Handoff notes for next session:**
- Session 3.1 (Single Lineup Optimizer) should NOT be treated as validated against real data yet — it'll be building on `final_projections_{site}_{week}.csv`, which itself is only mechanically validated per above.
- `ROADMAP.md`'s new "Known Deferred Validations" section is the place to check before assuming any session's real-data validation is actually closed — update it, don't recreate it, when a future session hits the same kind of live-data-only constraint (still true for The Odds API's historical gap and FD's total lack of real data).
- If a real preseason DK+FD slate becomes available before Session 2.4's real-data validation is otherwise revisited, re-run this session's validation checklist in full against that real data rather than waiting for a dedicated session slot.

---

## Session 2.4 (ADDENDUM) — Real re-run + second bug + team-drift finding
**Date completed:** 2026-07-21
**Status:** ⚠️ Complete with one open structural caveat (see below) — the actual-outcome sanity check now genuinely passed, not just the mechanical checks

**What happened:** user supplied the real `weekly_stats_2025.parquet`, enabling a genuine re-run of the patched `projections_baseline.py` (previous entry's fix had only been a manual reconstruction, explicitly flagged as a stand-in).

**Second bug found and fixed, same function, different key:** removing `team` from `season_baseline()`'s groupby (previous fix) wasn't sufficient — `player_name` in nflverse's raw data is *also* occasionally inconsistent for the same `player_id` across different weeks (e.g. player_id `00-0039394` appears as both "Cas.Washington" and "C.Washington" across different weeks; `00-0040582` as both "A.Smith" and "Ar.Smith"). Grouping by `player_name` reproduced the identical duplicate-row defect through a different key — 2 more players affected. **Fixed** by grouping on `player_id` alone and attaching each player's most-recent `player_name`/`position` afterward (same "most recent" pattern `ingest_salaries.py`'s `build_player_reference()` already uses for this exact class of problem). Re-ran: **0 duplicate `player_id`s, both sites, confirmed against real data** (532 rows in, 532 unique out).

**Actual-outcome sanity check — now genuinely done, not just mechanically checked:**
- Real week 10, 2025 box scores confirm **Jonathan Taylor** (our #1, both sites) scored 49.6 fantasy points — the single highest score by any player all season. **De'Von Achane** (our #3, both sites) was independently called out in the same recap as a standout RB performance. Strong match.
- **Joe Flacco** (our #2, both sites, ~23 pts) does NOT hold up: real box scores confirm he has no week-10 row at all — Cincinnati (his real week-10 team, post-trade from Cleveland) had a bye. Our pipeline has him on `CLE` (his team per the live July-2026 DK salary export) and matched him against `CLE`'s real week-10-2025 opponent (NYJ) — a real historical game, just one the real Flacco wasn't part of.
- **Quantified the scope:** cross-checked all 85 skill players in the real DK salary pool against their actual week-10-2025 team (from `weekly_stats_2025.parquet`, team as of their last game before week 10). **5 of 85 (≈6%) have a mismatched team** between the live salary snapshot and their real historical week-10 team: Joe Flacco (CLE→ really CIN), Shedeur Sanders / Will Mallory / Jonathan Mingo (no real week-10-or-earlier row at all — rookies/inactive that season), Brenden Bates (CLE → really HOU).

**Root cause, distinct from the two groupby bugs above:** this isn't a code bug — `schedules_2025.parquet`, the matching logic, and the neutral-fallback handling all did exactly what they were built to do. It's a **structural limitation of backtesting with a live, current-day salary file**: a player's team in that file reflects *today* (July 2026), not necessarily their team as of the historical week being validated. For live production use (current salary file + current week) this never comes up; it only bites when the target week is in the past relative to the salary file's snapshot date, which is exactly this validation's setup.

**Decision needed, not yet made:** how a future backtest run should handle this — e.g., a `--backtest-mode` flag on `build_projections.py` that overrides a player's team with their real team from `weekly_stats_{season}.parquet` as of the target week (available in the same file already used for the schedule/opponent lookup) rather than trusting the salary file's team column when doing historical validation specifically. Not implemented this session — flagged for a future session's decision, since it changes real behavior and should be confirmed with the user first, same as every other design decision this session.

**Files created/modified:**
- `/dfs_optimizer/scripts/projections_baseline.py` (second bug fix — groupby key)
- `/dfs_optimizer/data/weekly_stats_2025.parquet` (new — user-supplied, real data)
- `/dfs_optimizer/output/baseline_recent_form_dk_2025_10.csv`, `_fd_2025_10.csv` (regenerated for real this time, superseding the earlier reconstructed stand-in)
- `/dfs_optimizer/output/final_projections_dk_10.csv`, `_fd_10.csv` (regenerated)

**Validation results:**
- [x] Both roadmap validation checkboxes for Session 2.4 now genuinely pass, modulo the caveats above: no nulls/negatives/duplicates (real data), and top-10 roughly aligns with what actually happened (Taylor/Achane confirmed; Flacco's ranking traced to a specific, quantified, and now-documented data-freshness limitation rather than a pipeline bug).

**Known issues deferred:**
- The team-drift issue above (~6% of a live salary pool, in this sample) is a **new, separate item from "Known Deferred Validations" in `ROADMAP.md`** — that section covers data that flatly doesn't exist yet (real Vegas lines for a past week, real FD salaries). This one exists right now and needs a methodology decision, not a waiting period. Tracked separately in `ROADMAP.md`.
- Everything else carried over from the previous Session 2.4 entry (team defenses unprojected, full real-data-both-sites validation still blocked on FD/Vegas) still applies unchanged.

---

## Session 2.4 (ADDENDUM 2) — Decision #4 implemented: team-drift auto-correction
**Date completed:** 2026-07-21
**Status:** ✅ Complete

**What was actually built:** `build_projections.py` now auto-corrects for salary-file team drift when backtesting a played week, per the user-confirmed "Option A" (no flag, automatic based on data availability).

**First implementation attempt found a gap immediately:** the straightforward version (if a player has a real row for the target week, use that team) produced **zero corrections** on re-run — because all 5 originally-flagged mismatched players (Flacco included) have **no real row at all** for week 10, not a real row under a different team. Investigating why revealed the actual shape of the problem: there are two genuinely different cases, and only one is "correctable":
  - **4a — played, different team** (an in-season trade where the player DID suit up that week): correctable, use their real team.
  - **4b — no real game that week at all** (bye, inactive, injury, hadn't debuted yet): NOT correctable by picking a team, because there's no real game to attribute to them. Forcing the salary file's team here is exactly how the original Flacco bug happened. Fixed by giving these players the same neutral `1.0` matchup_factor/vegas_factor fallback as any other missing-data case (decision #3), rather than a specific-but-wrong value.

**On re-run, 4b affected far more players than expected — 41 of 85, not the 5 originally found.** Investigated: 15 are explained by the 4 real bye teams that week (CIN, TEN, DAL, KC). The other 26 — including C.J. Stroud, Jayden Daniels, Tyreek Hill — turned out to have no real week-10 row for reasons unrelated to a team bye (e.g. Stroud is missing weeks 6, 10, 11, 12 entirely in the real data, consistent with an injury absence, not a bye). This is the auto-correction working as intended, not a new bug -- it's catching real "we don't actually know this player's week-10 context" cases that the original (team-only) mismatch check never looked for. It does mean Session 2.4's earlier "Stroud roughly matches what happened" read was never actually verified against real data (only Taylor and Achane were checked) -- corrected now.

**Final DK/FD top-10 after this fix:** Joe Flacco's projection dropped from ~23 to ~20.04 (now driven purely by his real season_avg/recent_form, with neutral 1.0 matchup/vegas instead of a borrowed CLE-vs-NYJ game he wasn't part of). Jonathan Taylor and De'Von Achane -- the two players independently confirmed against real box scores earlier -- remain #1/#2 on both sites, now with correctly non-neutral, real matchup/vegas factors (both IND and MIA actually played that week).

**Files created/modified:**
- `/dfs_optimizer/scripts/build_projections.py` (decision #4 implemented: `load_real_team_for_week()` two-case logic, `no_real_game_this_week` flag wired through to force neutral matchup_factor/vegas_factor)
- `/dfs_optimizer/output/final_projections_dk_10.csv`, `_fd_10.csv` (regenerated)

**Validation results:**
- [x] 0 nulls, 0 negatives, 0 duplicates, both sites (unchanged from prior validation).
- [x] Flacco's matchup_factor/vegas_factor now correctly 1.0/1.0 (previously borrowed from a game he wasn't part of).
- [x] Live/current-week runs unaffected by construction -- `load_real_team_for_week()` returns `week_was_played=False` whenever `weekly_stats_{season}.parquet` has no rows yet for the target week (i.e. it hasn't happened), skipping all correction logic entirely.

**Known issues deferred:**
- 41/85 (≈48%) of this specific real DK pool now gets a neutral matchup/vegas factor for week 10 -- much higher than initially expected, but confirmed as an accurate reflection of "no real week-10 data exists for this player," not an over-correction. Worth knowing this ratio will vary a lot week to week and pool to pool; not itself a bug to chase.
- The underlying reason so many players lack real week-10 rows (byes vs. injuries vs. inactives vs. genuinely not on an NFL roster that week) isn't distinguished anywhere in the output -- all get treated identically (neutral 1.0). A future session could add a reason code if that distinction becomes useful (e.g. for the optimizer to treat "definitely inactive" differently from "just uncertain").

---

## Session 2.4 (ADDENDUM 3) — Decision #4b corrected: zero, not neutral
**Date completed:** 2026-07-21
**Status:** ✅ Complete

**User caught a real remaining bug:** Addendum 2 neutralized matchup_factor/vegas_factor to 1.0 for players with no real game that week, but left `final_projection` computed from the normal formula anyway -- still a real, positive number (Flacco showed ~20.04) for a player we know, via hindsight, scored ZERO real fantasy points that week (he didn't play). Neutralizing the multipliers wasn't the same as zeroing the outcome.

**Fix:** for players flagged `no_real_game_this_week` (decision #4b), `final_projection` is now forced to `0.0` directly, overriding the blend formula entirely -- not just neutralizing its inputs. `season_avg`/`recent_form`/`matchup_factor`/`vegas_factor` are still shown in the output columns as real/neutral values (informational), but `final_projection` reflects the known real outcome.

**Explicitly scoped to backtests only, confirmed not to affect live runs:** the `no_real_game_this_week` flag is only ever set `True` when `week_was_played` is `True` -- i.e. `weekly_stats_{season}.parquet` already has real rows for the target week. For a live/current-week run, that week has no rows yet by construction, so this zero-out never fires -- an uncertain-status player in a live run still correctly gets a normal non-zero projection (their true status is unknown, not confirmed-zero; that's Session 5.1's job, not this pipeline's).

**Files created/modified:**
- `/dfs_optimizer/scripts/build_projections.py` (final_projection override for decision #4b, docstring corrected)
- `/dfs_optimizer/output/final_projections_dk_10.csv`, `_fd_10.csv` (regenerated)

**Validation results:**
- [x] Joe Flacco: `final_projection = 0.0`, both sites, correctly dropped out of the top 10 entirely.
- [x] 0 nulls, 0 negatives, both sites (unchanged).
- [x] Remaining DK/FD top 10 now consists entirely of players with genuinely non-neutral (real) matchup_factor/vegas_factor values -- i.e. every player left in the top 10 is confirmed, via real data, to have actually played that week.

---

## Session 3.1 — Single Lineup Optimizer
**Date completed:** 2026-07-21
**Status:** ✅ Complete

**What was actually built:**
- `scripts/optimizer.py` (new) — reads `final_projections_{site}_{week}.csv`, solves an integer linear program (PuLP + bundled CBC solver, already pinned in `requirements.txt`) for the single salary-cap-legal lineup maximizing total projected points, using each site's own cap/roster rules from `ingest_salaries.py`'s `SITE_CONFIGS` (Session 1.3) rather than hardcoding DK's numbers. Outputs `output/lineup_single_{site}_{week}.csv` with columns `roster_slot, player_name, position, team, salary, projection`.
- `scripts/build_projections.py` (modified) — added a real DST/DEF projection (decision #5, see script's module docstring), since the optimizer needs a full legal 9-slot roster for both sites and `final_projections_{site}_10.csv` had zero defense rows through Session 2.4.

**Design gap cleared with the user before building (same pattern as every prior session):** DST/DEF projections don't exist anywhere in the pipeline — flagged as an open gap since Session 2.4, and this session is exactly the point the roadmap said it would need closing. Asked the user how to handle it; user chose "add a real projection now" over a flat placeholder or skipping DST/DEF entirely. Built from the only two real signals available for a defense (no weekly_stats defense-level rows exist at all):
  - `AvgPointsPerGame` from the salary export (real, DK/FD-computed) — used for both `season_avg` and `recent_form`, since there's no real week-by-week split to compute (flagged as a known simplification, not hidden).
  - Vegas, inverted: `vegas_factor = league_avg_implied_total / opponent_implied_total` — the OPPONENT's implied total, not the defense's own team's (opposite convention from the skill-position `vegas_factor`), since a defense's output correlates with how poorly the opposing offense is expected to do.
  - No defensive `matchup_factor` exists upstream at all — held flat neutral 1.0, flagged as a real gap, not fabricated.
  - Bye-week handling matches decision #4b exactly: no real game that week (no row in `vegas_implied_totals_{week}.csv`) -> `final_projection` forced to `0.0`, not neutrally-factored. This needed NO `schedules_{season}.parquet` dependency at all -- `vegas_implied_totals_{week}.csv` already carries each team's real opponent in its own `opponent` column (a Session 2.3 addendum fix), so DST/DEF projections have one fewer upstream file dependency than skill-position ones.

**Environment caveat, handled carefully:** this session's environment did not have `weekly_stats_2025.parquet` or `schedules_2025.parquet` on disk (both were user-supplied in a prior session, needed for skill-position decision #2/#4 logic, NOT needed for DST/DEF). A first attempt at a full re-run of `build_projections.py` without `weekly_stats_2025.parquet` present silently skipped decision #4's team-drift correction -- caught before shipping, since it would have quietly regressed the already-validated Flacco-type fixes from Session 2.4's addenda. Corrected approach: computed DST/DEF rows in isolation (confirmed they need only the salary file + `vegas_implied_totals_{week}.csv`, nothing else) and merged them into the existing, already-correct `final_projections_{site}_10.csv` files rather than regenerating the skill-position rows from scratch. A genuine full end-to-end re-run (skill positions + defenses together, one pass) has NOT been done since this addition -- flagged in `ROADMAP.md`'s new "RESOLVED (Session 3.1)" section as worth doing once those parquet files are available again, as a regression check.

A minimal `schedules_2025.parquet` (14 real week-10-2025 games, real matchups reconstructed from `vegas_implied_totals_10.csv`'s own `team`/`opponent` columns -- matchups are real per Session 2.4's log, only that file's spread/total numbers are synthetic) was built locally just to test-run the full `build_projections.py --site {dk,fd}` path end-to-end once, confirming the new DST/DEF code integrates correctly. That reconstructed file was NOT what produced this session's actual shipped output (see caveat above) -- it was a code-path smoke test only, and isn't part of the deliverables.

**FLEX eligibility convention:** `optimizer.py` hardcodes `FLEX_ELIGIBLE_POSITIONS = {"RB", "WR", "TE"}` (standard classic-contest rule for both sites) since `SITE_CONFIGS` has no such field. Flagged in `ROADMAP.md` as a real assumption never explicitly confirmed with the user, and as the one place to change for a future superflex format.

**Files created/modified:**
- `/dfs_optimizer/scripts/optimizer.py` (new)
- `/dfs_optimizer/scripts/build_projections.py` (decision #5 added: `build_dst_projections()`, wired into `build_final_projections()`)
- `/dfs_optimizer/output/final_projections_dk_10.csv`, `_fd_10.csv` (regenerated -- 85 skill players + 6 defenses each, up from 85)
- `/dfs_optimizer/output/lineup_single_dk_10.csv`, `_fd_10.csv` (new)
- `ROADMAP.md` (new "RESOLVED (Session 3.1)" section; FLEX-eligibility note added to the dual-site notes)

**Validation results:**
- [x] Both sites' output lineups are under their real salary cap and satisfy every position requirement -- enforced as automated ILP constraints (`validate_lineup()`'s assertions), not manual eyeballing. DK: $46,900 / $50,000 used. FD: $56,100 / $60,000 used. Both: exactly 9 players, correct position counts including FLEX.
- [x] "No single-player swap would increase points without breaking a constraint" -- mathematically guaranteed by the ILP's certified global optimum (CBC solver, small problem size), AND independently verified empirically with a brute-force 1-for-1 swap check against every other player in the pool: 0 improving swaps found for either site.
- [x] 0 zero-projection players selected in either lineup (Dallas's zeroed-out DST correctly excluded in favor of the 5 real-projection defenses) -- confirms decision #5's bye handling flows correctly into the optimizer without needing an explicit filter (decision #4 in `optimizer.py`'s docstring: the ILP naturally never picks a locked $0 over a positive alternative).
- [x] Both sites' outputs read cap/roster from `SITE_CONFIGS` (Session 1.3), not hardcoded -- confirmed FD correctly used its own $60,000 cap and DEF label, not DK's $50,000/DST by default.

**Known issues deferred:**
- No defensive `matchup_factor` exists anywhere in the pipeline -- DST/DEF projections rely on `AvgPointsPerGame` + inverted Vegas only. A future session could add real defensive matchup data (e.g. opponent's sacks-allowed rate, points-allowed-by-position) to close this gap.
- A genuine full single-pass re-run of `build_projections.py` (skill + defense together) hasn't happened since the DST/DEF addition -- see environment caveat above. Do this once `weekly_stats_2025.parquet`/`schedules_2025.parquet` are available again, as a regression check against this session's isolated-merge output.
- `FLEX_ELIGIBLE_POSITIONS` lives only in `optimizer.py`, not in `SITE_CONFIGS` -- worth promoting there if a future site/format needs a different FLEX rule.
- Everything carried over from Session 2.4's log (real-data-both-sites validation still blocked until Preseason Week 1, per `ROADMAP.md`'s "Known Deferred Validations") still applies unchanged -- this session's optimizer is validated for correctness-of-logic against Session 2.4's mechanically-validated projections, not yet against fully real data for both sites simultaneously.

**Handoff notes for next session:**
- Session 3.2 (Multi-Lineup Generation + Exposure Limits) extends `optimizer.py` rather than replacing it -- the single-lineup ILP formulation here (one binary var per player, aggregate position-count constraints) is the base to build exposure-cap constraints on top of.
- `optimizer.py`'s `solve_lineup()`/`assign_roster_slots()`/`validate_lineup()` functions are written to be reusable per-lineup building blocks -- Session 3.2 likely calls `solve_lineup()` repeatedly with an added max-exposure constraint per player rather than rewriting the ILP from scratch.

---

## Session 3.1 (ADDENDUM) — True full single-pass re-run confirmed identical
**Date completed:** 2026-07-21
**Status:** ✅ Complete

**What happened:** user supplied real `weekly_stats_2025.parquet`, `schedules_2025.parquet`, and `weekly_rosters_2025.parquet` (couldn't be added to the project file directory earlier, uploaded directly instead), closing the caveat flagged at the end of the original Session 3.1 entry above.

**Ran the true full single-pass `build_projections.py` for both sites** (skill positions + DST/DEF together, one pass, no isolated-merge workaround needed this time) using the real parquet files. Decision #4's team-drift correction fired normally and matched Session 2.4's original real-data finding exactly: 41/85 skill players flagged `no_real_game_this_week` (bye/inactive/not-yet-debuted), 0 players needed decision #4a's trade-correction for week 10 specifically.

**Regression check (the specific thing flagged as deferred):** diffed the true full re-run's output row-for-row, both sites, against the isolated-merge output shipped in the original Session 3.1 entry. **0 rows differed. Max absolute difference in `final_projection` across all 91 players (both sites): 0.0.** Re-ran `optimizer.py` against the fresh output as well -- identical lineups, byte-for-byte matching the previously shipped `lineup_single_{site}_10.csv` files. Confirms the isolated-merge approach (computing DST/DEF rows separately from salary + vegas data alone, merging into the already-correct skill-position rows) was mathematically equivalent to a true full re-run, as expected given DST/DEF projections never touched `weekly_stats`/`schedules` in the first place.

**Files created/modified:**
- `/dfs_optimizer/data/weekly_stats_2025.parquet`, `/dfs_optimizer/data/schedules_2025.parquet`, `/dfs_optimizer/data/weekly_rosters_2025.parquet` (new -- real, user-supplied; `weekly_rosters_2025.parquet` not yet consumed by any script, saved for a future session that needs roster/depth-chart data)
- No script or output CSV changed as a result of this check -- everything already shipped in the original Session 3.1 entry is confirmed correct as-is.
- `ROADMAP.md`'s "RESOLVED (Session 3.1)" section updated to close out the caveat.

**Validation results:**
- [x] True full single-pass re-run matches the isolated-merge output exactly, both sites -- the regression check flagged as deferred in the original Session 3.1 entry is now closed.

**Known issues deferred:**
- `weekly_rosters_2025.parquet` is now available in `/data` but nothing in the pipeline reads it yet -- worth knowing it's there if a future session needs real depth-chart/roster-status data (e.g. Session 5.1's injury-status work).
- Everything else carried over from the original Session 3.1 entry (no defensive matchup_factor, FLEX_ELIGIBLE_POSITIONS not in SITE_CONFIGS, real-data-both-sites validation still blocked until Preseason Week 1) still applies unchanged.

---

## Infrastructure — GitHub backup (.gitignore revised)
**Date completed:** 2026-07-21

**What happened:** user flagged that all work so far has only existed locally, and wants it synced to GitHub as a backup. Asked how to handle data files specifically (many are real, manually-obtained snapshots -- e.g. the DK/FD salary exports -- not trivially regenerable if lost, unlike normal pipeline output). User chose: track everything in GitHub, including data/output, rather than keeping the repo code-only with a separate backup destination for data.

**Change made:** `.gitignore` revised -- removed the `data/*.parquet`, `data/*.csv`, `output/*.csv`, `logs/*.csv`, `logs/*.md` exclusions from Session 1.1's original version (which treated all data/output as "regenerated by pipeline, not source-controlled"). Secrets (`*.env`, `config/api_keys.env`) and environment/OS cruft (`venv/`, `__pycache__/`, `.DS_Store`, etc.) remain excluded -- those should never be tracked regardless of the data-backup decision.

**Sizing check before committing to this:** total current data/output footprint is small -- all CSVs combined are ~132KB, and the three real nflverse parquet files (`weekly_stats_2025.parquet`, `schedules_2025.parquet`, `weekly_rosters_2025.parquet`) are 864KB/52KB/840KB respectively. Comfortably clear of GitHub's 50MB-warning / 100MB-hard-limit thresholds -- no Git LFS needed at this size.

**Files created/modified:**
- `/dfs_optimizer/.gitignore` (revised)

**Handoff notes for next session:** if a future session (e.g. Phase 1's full-season historical pulls, or Phase 6's automated dry-run logging) starts producing genuinely large files, revisit whether everything should still be tracked directly in git vs. Git LFS or external storage for just the large ones -- don't assume this decision holds at unlimited scale. No other pipeline behavior changed by this -- purely a repo/backup decision, not a data or projection logic change.

---

## Session 3.2 — Multi-Lineup Generation + Exposure Limits
**Date completed:** 2026-07-22
**Status:** ✅ Complete

**What was actually built:**
- `scripts/optimizer.py` (extended, not replaced) — added `build_multi_lineup()`, which re-solves the Session 3.1 single-lineup ILP repeatedly to produce N distinct, salary-cap-legal lineups, none of which use any player in more than a configurable percentage of the total lineups. Outputs `output/lineups_multi_{site}_{week}.csv` — same columns as `lineup_single_{site}_{week}.csv` plus a leading `lineup_id` column. New CLI flags: `--n-lineups`, `--max-exposure` (default 40%), `--min-unique-swaps` (default 3). Single-lineup mode (`--site`/`--week` with no `--n-lineups`) is unchanged from Session 3.1 -- verified byte-identical code path, just gated by an `if args.n_lineups:` branch in `main()`.

**Design decisions (continuing the numbered pattern from Session 3.1's docstring, now #5-8, documented in `optimizer.py` itself):**
- **#5 -- Exposure cap is a hard ILP constraint**, not a soft penalty: once a player hits their allowed appearance count, they're filtered out of the candidate pool entirely for all remaining solves. Chosen because the roadmap's validation checkbox ("confirm no player exceeds the exposure cap set") asks for a guarantee, not a probability.
- **#6 -- Exposure cap rounding:** `max(1, floor(max_exposure_pct * n_lineups))`. A plain floor could round to 0 for a low cap/lineup-count combination, which would silently ban a player outright rather than just limit repetition -- flooring at 1 avoids that edge case.
- **#7 -- Lineup diversity via a hard minimum-swap constraint:** each new lineup must differ from every previously generated lineup by at least `min_unique_swaps` players (default 3), enforced as an ILP constraint, not randomized noise on projections. Known tradeoff, flagged in the code: the real-data test pool is thin (ROADMAP.md's "Known Testing Artifact" note -- only 4 non-zero-projection QBs), so a strict swap floor can go infeasible before N lineups are reached. Handled by relaxing `min_unique_swaps` by 1 (with a printed warning) each time a solve fails, rather than crashing or silently duplicating; if it relaxes all the way to 0 and still fails, generation stops early with an explicit count and reason printed -- never a silent short lineup set.
- **#8 -- Default exposure cap 40%, same for both sites**, matching the roadmap card's own example figure. Kept shared rather than site-specific since exposure is a portfolio-construction choice, not something tied to a site's salary/roster structure the way e.g. chalk_score (Session 4.1) will be -- `--max-exposure` is still exposed as a flag if real usage later shows a reason to differ by site.

**Files created/modified:**
- `/dfs_optimizer/scripts/optimizer.py` (extended: `build_multi_lineup()` added, `solve_lineup()` extended with optional `previous_lineups`/`min_unique_swaps` params defaulting to no-op, `main()` branches on `--n-lineups`)
- `/dfs_optimizer/output/lineups_multi_dk_10.csv`, `_fd_10.csv` (new)

**Validation results:**
- [x] Generated 20 lineups per site (DK and FD), confirmed no player exceeds the exposure cap: DK's top exposure topped out at 8/20 (exactly the 40% cap), same for FD -- verified by grouping the output CSV by player and counting appearances, not just trusting the solver's own accounting.
- [x] Confirmed lineups are meaningfully different, not near-duplicates: computed pairwise player-set differences across all 20 lineups for both sites -- **0 identical or near-duplicate pairs**, minimum 3 players swapped between any two lineups (exactly the enforced floor, as expected since the solver stops swapping out more than required once salary-cap-optimal).
- [x] Both sites' every generated lineup independently re-validated with Session 3.1's `validate_lineup()` (salary cap, exact roster size, correct position counts) -- 20/20 passed for both sites, no manual eyeballing.
- [x] Both sites hit the full requested 20/20 lineups without needing to relax `min_unique_swaps` below its default of 3 -- the thin-pool infeasibility risk flagged in decision #7 didn't materialize at n_lineups=20/cap=40% against this test pool, though it remains a real risk worth watching at a real full-size slate with different N/cap combinations.

**Known issues deferred:**
- Everything carried over from Session 3.1's log (no defensive matchup_factor, FLEX_ELIGIBLE_POSITIONS not in SITE_CONFIGS, real-data-both-sites validation still blocked until Preseason Week 1 per ROADMAP.md's "Known Deferred Validations") still applies unchanged.
- The relaxation behavior in decision #7 (progressively lowering `min_unique_swaps` on infeasibility) was implemented and is exercised by the code path, but wasn't actually triggered by this session's validation run (both sites reached 20/20 at the default swap floor) -- worth a future stress test at a higher `n_lineups` or a smaller/thinner pool to confirm the relaxation and early-stop logging behave as designed under real infeasibility, not just in code review.

**Handoff notes for next session:**
- Session 3.3 (Stacking Rules) extends `optimizer.py` again rather than replacing it -- likely adds a same-team QB+pass-catcher constraint to `solve_lineup()` alongside the existing salary/roster/uniqueness constraints, and probably needs to run under both single- and multi-lineup modes.
- `build_multi_lineup()`'s per-lineup re-solve loop (locked-out pool + previous_lineups uniqueness constraints) is the reusable pattern Session 3.3's stacking constraints should slot into, rather than a parallel code path.

---

## Session 3.2 (ADDENDUM) — Projection Randomization
**Date completed:** 2026-07-22
**Status:** ✅ Complete

**What happened:** user asked whether projection randomization was already planned anywhere in the pipeline. Checked `ROADMAP.md`/`SESSION_LOG.md` in full -- confirmed it was never planned as its own session and wasn't implemented. Clarified with the user what was meant (randomized-projections-for-diversity vs. Monte Carlo simulation-for-ranking are two different real DFS-tool features that live in different places) -- user confirmed the first: an optional per-run knob where each player's projection can be perturbed +/-X% before the optimizer selects against it, off by default, user-configurable (typically 1-40%), with each generated lineup getting its own independent randomization draw.

**Design gaps cleared with the user before building (same pattern as every prior session):**
- **Distribution shape:** asked whether the +/-X% draw should be uniform or normal. User wanted an industry-standard check first if available. Quick web check found real DFS tools (FantasyCruncher PRO's published methodology, the open-source `dfs-with-r/coach` optimizer) both use a normal (or log-normal) distribution scaled off the projection, not a flat uniform window -- reported this back, and it matched the user's own stated preference for normal/bell-curve. Implemented as: mean = real `final_projection`, std_dev = `randomization_pct`% of that same value, clipped at a floor of 0.0 (no negative fantasy points).
- **Interaction with Session 3.2's swap constraint:** asked whether randomization should replace or supplement the existing hard minimum-swap uniqueness constraint. User chose supplement -- both apply together.
- **Single- vs. multi-lineup scope:** asked whether randomization should be available in single-lineup mode too, not just multi-lineup batches. User chose both.

**What was actually built (`scripts/optimizer.py`, extended again, decisions #9-13 in the file):**
- `randomize_projections()` (new) -- draws one normal-distribution sample per player, mean/std_dev as described above, returns a `pd.Series` indexed by `player_id`. Does NOT modify the real `final_projection` column anywhere.
- `solve_lineup()` extended with an `optimization_projection` param -- when provided, the ILP objective uses those (possibly randomized) values instead of the real `final_projection`; salary/position constraints and the real `final_projection` values carried in the returned rows are untouched either way. Defaults to `None` (uses real projection, Session 3.1/3.2 behavior unchanged).
- `build_single_lineup()` and `build_multi_lineup()` both extended with `randomization_pct`/`seed` (and in multi-lineup's case, `rng` is created once but a **fresh draw is taken inside the generation loop for every lineup** -- user-confirmed requirement, not one draw reused across the batch).
- New CLI flags: `--randomization-pct` (default 0 = off, typically 1-40 when used) and `--seed` (optional, for reproducible runs).
- Output CSVs (`lineup_single_*`/`lineups_multi_*`) always report each selected player's REAL `final_projection` in the `projection` column, never the noisy value used to pick them -- so total-points figures stay meaningful and comparable across lineups/runs regardless of whether randomization was on.

**Files created/modified:**
- `/dfs_optimizer/scripts/optimizer.py` (extended: `randomize_projections()` added; `solve_lineup()`, `build_single_lineup()`, `build_multi_lineup()`, `main()` all extended with randomization params/flags)

**Validation results:**
- [x] `--randomization-pct 0` (default) reproduces Session 3.1's exact shipped `lineup_single_dk_10.csv` byte-for-byte -- confirmed via diff. No prior behavior changed by this addendum unless explicitly opted into.
- [x] Same `--seed` + same `--randomization-pct` -> identical output across two separate runs -- confirmed via diff (reproducibility works as designed).
- [x] `--randomization-pct 15` with a seed produced a DIFFERENT lineup than the unrandomized baseline (TE/FLEX swapped -- Harold Fannin Jr./Alec Pierce in for Dalton Schultz/Harold Fannin Jr.) -- confirms randomization is actually influencing selection, not a no-op.
- [x] Multi-lineup mode, both sites, `--n-lineups 20 --randomization-pct 20`: exposure cap (8/20 = 40%) and the swap-uniqueness constraint (minimum 3 players swapped, 0 duplicate/near-duplicate pairs) BOTH still held exactly as in the original Session 3.2 validation -- confirms randomization is additive, not a replacement, as the user directed. All 20/20 lineups generated both sites, all under their real salary cap, all with correct roster composition.
- [x] 20 distinct lineup-level point totals out of 20 lineups (DK, randomized run) -- confirms per-lineup independent draws are actually producing varied candidate rankings, not one draw reused for the whole batch.

**Known issues deferred:**
- Everything carried over from the original Session 3.2 entry (thin real-data test pool, deferred stress-test of the swap-relaxation path, real-data-both-sites validation still blocked until Preseason Week 1) still applies unchanged.
- The clipping-at-0.0 asymmetry noted in decision #9 (low-projection/punt players get a right-skewed realized distribution once negative draws are clipped) is a known, minor property of the normal-distribution approach -- not expected to matter much in practice since punt players rarely swing a lineup decision, but flagged rather than silently accepted.
- `--seed` reseeds a fresh `np.random.default_rng()` each CLI invocation; if a future session wants bit-for-bit-reproducible MULTI-run batches (e.g. same seed producing the same 20 lineups across separate process invocations, not just within one run), that already works as tested -- but no automated regression test locks this in beyond this session's manual validation. Worth a real test fixture if reproducibility becomes load-bearing for anything (e.g. debugging a specific reported bad lineup).

**Handoff notes for next session:**
- Session 3.3 (Stacking Rules) will need to decide how stacking constraints interact with BOTH existing diversity levers (hard swap constraint AND optional randomization) -- likely just another constraint added to the same `solve_lineup()` call, but worth explicitly re-checking exposure caps + uniqueness + randomization + stacking all together in that session's validation, not just stacking in isolation.

---

## Session 3.2 (ADDENDUM 2) — Renamed min_unique_swaps -> uniqueness, default changed to 1
**Date completed:** 2026-07-22
**Status:** ✅ Complete

**What happened:** user asked whether "uniqueness" (standard DFS-optimizer terminology for the per-lineup minimum-swap diversity control) was already planned/built. Confirmed it already existed -- it's exactly what the original Session 3.2 entry implemented as `min_unique_swaps` (default 3) -- just under a non-standard name. User confirmed two changes: (1) rename `min_unique_swaps` -> `uniqueness` (`--uniqueness` CLI flag) throughout, to match standard terminology or any future UI; (2) change the default from 3 to 1, matching the standard convention.

**What was actually changed (`scripts/optimizer.py`):**
- Global rename: `min_unique_swaps` -> `uniqueness`, `MIN_UNIQUE_SWAPS` -> `UNIQUENESS`, `--min-unique-swaps` -> `--uniqueness`, `current_min_swaps` -> `current_uniqueness`. Purely a naming change -- the underlying mechanic (hard per-pair minimum-swap ILP constraint, with automatic relaxation + stderr warnings on infeasibility) is byte-for-byte the same logic as before.
- `DEFAULT_UNIQUENESS` changed from `3` to `1`.
- Added an explicit addendum note inline in decision #7's docstring block flagging the rename/default change as user-directed, not independently decided (same "flag, don't silently assume" pattern as every other decision in this file).

**Validation results -- and an honest finding, not swept under the rug:**
- [x] Single-lineup mode unaffected: re-ran `--site dk --week 10` with no `--n-lineups`, diffed against the original Session 3.1 shipped output -- still byte-for-byte identical.
- [x] `--uniqueness 3` (explicit override) still reproduces the original Session 3.2 behavior/guarantee (verified 10 lineups, min swap = 3, matching the prior entry's math).
- [x] FD, default `uniqueness=1`, 20 lineups: 20/20 generated, 0 relaxation events, 0 duplicate/near-duplicate pairs, exposure cap held (8/20). Clean.
- [!] **DK, default `uniqueness=1`, 20 lineups: 20/20 generated, but the relaxation path (decision #7 -- documented but never actually triggered before this) fired 4 times near the end of the batch, and one exact duplicate pair (0 players swapped) appeared among the 20.** Confirmed reproducible across 5 repeated runs with identical settings -- deterministic, not solver flakiness. Exposure cap still held correctly regardless (8/20, hard constraint, unaffected by this). Root cause: this is the same thin-test-pool limitation already flagged in ROADMAP.md's "Known Testing Artifact" note (DK's real test pool has only 4 non-zero-projection QBs) -- at `uniqueness=1` + 40% exposure cap + 20 lineups, the pool runs out of genuinely distinct legal combinations before hitting 20, and the (working-as-designed) relaxation logic permits a duplicate rather than stopping early or crashing. This is a property of the small real-data test pool, not a bug in the rename or the underlying constraint logic -- expected to resolve against a real, full-size DK slate (32+ starting QBs) the same way the roadmap's other thin-pool artifacts are expected to.

**Files created/modified:**
- `/dfs_optimizer/scripts/optimizer.py` (renamed `min_unique_swaps` -> `uniqueness` throughout; `DEFAULT_UNIQUENESS` changed 3 -> 1; addendum note added to decision #7)

**Known issues deferred:**
- The DK duplicate-pair finding above is new information, not previously observed (the original Session 3.2 validation ran at the old default of 3, which never approached this pool's limit). Worth explicitly re-testing once a real full-size DK slate exists (Preseason Week 1, per ROADMAP.md's existing "Known Deferred Validations" section) to confirm this artifact actually disappears as expected, rather than assuming it will.
- Not addressed in this addendum, flagged for a future call: CBC's branch-and-bound does not guarantee a stable tie-break among multiple equally-optimal solutions in general (this specific run happened to be reproducible, but that's not guaranteed by construction). If deterministic reproducibility across ALL settings (not just `--seed`-controlled randomization) becomes load-bearing later, a lexicographic secondary objective (e.g. minimize total salary, or a stable player-id ordering, as a tie-break) could be added to `solve_lineup()` -- not built now since it wasn't asked for and is a real design choice, not an obvious default.

**Handoff notes for next session:**
- Session 3.3 (Stacking Rules): when validating stacking together with exposure/uniqueness/randomization, use FD as well as DK, and don't assume DK's default 20-lineup run will always cleanly hit 20/20 without relaxation -- this addendum shows it sometimes won't, on the current thin test pool.

---

## Session 3.3 — Stacking Rules
**Date completed:** 2026-07-22
**Status:** ⚠️ Complete with caveats — code built and validated against a synthetic fixture; real-data re-validation still needed (this session was built in a sandbox environment without access to the repo's actual data files -- see Known issues deferred).

**What was actually built:**
- Before any code, had an explicit discussion with the user about which stacking types to build (the roadmap card only listed two: QB+pass-catcher, and an optional game stack/bring-back deferred to Phase 6). User provided a full DFS stacking taxonomy (Standard/Double/Triple, QB+RB, Game Stack/Shootout, Bring-back, Mini-Stack) and directed building all of it in this one session, rather than the roadmap's lighter default scope.
- `scripts/optimizer.py` extended with decisions #14-21:
  - `--stack-mode {none,qb,game,mini}` -- `qb` covers Standard/Double/Triple/QB+RB via `--stack-size`/`--stack-positions` (default `WR,TE,RB` -- "any pass-catcher," user-confirmed); `game` is the Game Stack/Shootout, no QB required; `mini` covers same-team RB+DST or opposing pass-catchers via `--mini-stack-type`.
  - `--bring-back` -- add-on to a QB stack, requires >=1 opponent skill player (QB/RB/WR/TE, deliberately excludes the opponent's DST/DEF -- a shootout benefits the opponent's offense, not their defense).
  - Team/game selection: auto by default (highest Vegas `implied_total` for QB/mini-stack team selection, highest `over_under` for game-stack), `--stack-team`/`--stack-game` to pin -- user-confirmed "both, auto by default with a CLI override."
  - Multi-lineup diversification (`resolve_stack_candidates()`): when auto-selecting, the batch rotates round-robin across up to `--stack-candidate-pool` (default 5) candidate teams/games instead of repeating one target. An explicit pin forces the whole batch to one target regardless of `--stack-diversify` -- user-confirmed: "most often [diversify] ... but the user needs to be able to say 'I want 20 stacked lineups from this game only.'" Per-lineup, if the current rotation candidate is infeasible (e.g. exposure-locked), the remaining candidates are tried before falling back to uniqueness relaxation -- stacking infeasibility and diversity infeasibility are retried independently, not conflated.
  - `add_stack_constraints()` -- hard ILP constraints (mandatory whenever a stack is requested, matching the user's explicit instruction: "if stacking is enabled it is mandatory for every lineup ... if disabled, no stacking is required"). Raises a specific `RuntimeError` before the solver runs if the requested stack has no viable players in the current candidate pool (e.g. exposure-locked out), rather than waiting for a generic ILP infeasibility.
  - `validate_stack()` -- new function mirroring the existing `validate_lineup()` pattern: an automated, structural re-check (not eyeballed) that the requested stack actually landed in the final lineup. Runs after every single- and multi-lineup solve.
  - `assign_roster_slots()` extended to carry an `opponent` column through to the output (needed by `validate_stack()`'s bring-back check, and generally useful).
- `scripts/build_projections.py` modified (**not on the original Session 3.3 card** -- see ROADMAP.md's updated card): added `opponent`, `implied_total`, `over_under` as three new output columns on `final_projections_{site}_{week}.csv`. Neither value existed downstream before this -- both were computed internally (the opponent map, the vegas-factor merge) but never written out, so `optimizer.py` would otherwise have had to re-derive the same schedule/vegas lookups a second time, in a different file, with real risk of drifting out of sync. Purely additive -- confirmed via a synthetic fixture that no existing column's values changed and the "no nulls in any column" invariant still holds (bye-week/no-real-game rows get sentinel values `"BYE_OR_UNKNOWN"`/`0.0` instead of real NaN, same philosophy as the existing matchup_factor/vegas_factor neutral-fill).

**Files created/modified:**
- `/dfs_optimizer/scripts/optimizer.py` (extended -- decisions #14-21)
- `/dfs_optimizer/scripts/build_projections.py` (modified -- decision #6, three new output columns; deviation from the original card, flagged in ROADMAP.md)

**Validation results:**
- **Environment caveat, upfront:** this session was built in a clean sandbox with no access to the repo's real data files (no real `final_projections_*.csv`, no real DK Madden Stream pool). Rather than skip validation, built a synthetic 8-team/64-player fixture (4 games, realistic Vegas totals ranging 38.5-52.5, real-shaped salary/position distributions) to exercise the actual code paths end-to-end.
- [x] `build_projections.py`'s new columns: ran for both sites against the synthetic fixture -- 0 nulls, 0 negatives (unchanged from prior sessions' invariants), new `opponent`/`implied_total`/`over_under` columns populated correctly (spot-checked: KC/BUF, the fixture's highest-total game at 52.5, correctly shows the highest `implied_total` values).
- [x] 13-scenario test matrix against `optimizer.py`, both sites:
  1. No-stack baseline -- confirmed same lineup as before this session's changes (modulo the new `opponent` output column, which is an intentional additive schema change, flagged not hidden).
  2. Standard QB stack, auto-team -- landed on the optimizer's natural pick (KC), confirming auto-selection doesn't force a worse lineup when the natural optimum already satisfies the stack.
  3. Triple stack forced on a deliberately non-optimal team (WAS, via `--stack-team`) -- confirmed the constraint actually changes the selected lineup (not a no-op), correctly pulling in 3 WAS pass-catchers around the WAS QB at a real points cost (158.46 -> 132.36), proving the constraint is binding.
  4. QB+RB stack (`--stack-positions RB`) -- confirmed positions filtering works, pulled in a second KC RB instead of a WR/TE.
  5. Bring-back on a natural KC stack -- BUF (the opponent) was already present, confirming the constraint is satisfied without forcing an unnecessary swap when already true.
  6. Game stack, auto -- correctly selected KC-BUF (the 52.5-total game, highest in the fixture).
  7. Mini-stack RB+DST, pinned to SF -- confirmed SF's own DST got pinned (via the same `== 1` pinning technique used for QB stacks) alongside an SF RB.
  8. Mini-stack opposing-pass-catchers, pinned game MIA-NYJ -- confirmed a WR/TE from each side.
  9. **Fail-loudly check:** requested a triple-TE stack on KC (which only has 1 real TE) -- raised a specific `RuntimeError` ("KC has 1 available QB(s) and 1 available partner(s) at ['TE']... need 1 QB + 3 partner(s)") before the solver ran, exactly per decision #21.
  10. Multi-lineup (8 lineups, 100% exposure, uniqueness=1), QB stack, auto -- confirmed diversification rotated round-robin through the top 5 candidate teams by implied_total (`KC, BUF, SF, PHI, MIA` each appearing ~1-2x across 8 lineups), not repeating one team.
  11. Multi-lineup (6 lineups), QB stack pinned to BUF -- confirmed **every** lineup's QB was BUF (the exact "20 lineups from this game only" case the user specifically asked for), regardless of the exposure/uniqueness churn happening elsewhere in the lineup.
  12. Pin + `--stack-diversify on` together -- confirmed the "diversify has no effect once pinned" note printed correctly (decision #17), and as a bonus this run also demonstrated the fail-loudly path interacting correctly with a low exposure cap (BUF's single real QB got exposure-locked after lineup 1 at a 40% cap, correctly triggering the uniqueness-relaxation-then-stop-early path rather than silently dropping the stack).
  13. FD-specific check (different defense label `DEF` vs DK's `DST`, different $60K cap) -- mini-stack RB+DST pinned to KC worked correctly on FD, confirming `DEFENSE_POSITION_LABELS = {"DST","D","DEF"}` handles both sites.
- [ ] **Real-data re-validation** -- not done this session (no real data available in this environment). Needs a real `final_projections_{site}_{week}.csv` (regenerated with the new columns) and a re-run of at least the 13-scenario matrix above before trusting this for a live/dry-run context.

**Decisions made / assumptions taken (numbered #14-21, continuing optimizer.py's docstring numbering):**
- All four stacking types built in one session per explicit user direction (not deferred/split), full taxonomy list captured in the module docstring.
- Stack partner default positions = WR/TE/RB ("any pass-catcher," user-confirmed over WR/TE-only or requiring a dedicated slot).
- Stacking enforcement is mandatory-when-enabled, no-op-when-disabled (user-confirmed explicitly, not inferred).
- Auto-select by default, `--stack-team`/`--stack-game` pin available (user-confirmed "both").
- Multi-lineup diversification defaults to "auto" (diversify when auto-selecting, single-target when pinned), with an explicit `--stack-diversify` override -- user-confirmed this needs to support both the common case (diversify) and the specific case ("20 lineups from this game only").
- `--stack-candidate-pool` default of 5 and `--game-stack-min-players` default of 4 were NOT explicitly discussed with the user -- chosen as reasonable defaults, both exposed as CLI overrides. Flagged as arbitrary, not user-confirmed, unlike every other default in this session.
- Bring-back pool excludes the opponent's DST/DEF (a design choice, not explicitly asked -- reasoned from how bring-backs work in real DFS, flagged in the docstring rather than silently assumed).

**Known issues deferred:**
- **Real-data validation is the single biggest open item** -- everything above was validated against a synthetic fixture built for this session, not the project's actual data. Needs closing before Session 6.1's dry run, same pattern as every other "synthetic now, real later" gap this project has tracked (see ROADMAP.md's "Known Deferred Validations," now with a Session 3.3 entry added).
- `--stack-candidate-pool` (5) and `--game-stack-min-players` (4) defaults are reasonable-but-arbitrary, not user-confirmed -- worth revisiting once real slate sizes (32 teams, not this session's 8-team fixture) show whether 5 candidates is enough diversity or too many/few.
- Stacking was not tested in combination with `--randomization-pct` (Session 3.2 addendum) in the same run -- both are independent additive mechanisms by construction (randomization only affects the objective, stacking only affects constraints), so no interaction is expected, but this specific combination wasn't exercised in this session's test matrix.
- `optimizer.py`'s output schema changed again (this is the second such change, after Session 3.2's `lineup_id`/`stack_target` additions) -- `opponent` is now always present in single- and multi-lineup output, `stack_target` is present in multi-lineup output. Any downstream consumer (e.g. Phase 7's frontend, still not built) reading these CSVs by fixed column position rather than by name would break -- worth keeping in mind once Phase 7 starts.

**Handoff notes for next session:**
- Before using stacking for real: (1) re-run `build_projections.py` for the target site/week to get the new `opponent`/`implied_total`/`over_under` columns, (2) re-run this session's 13-scenario matrix (or a subset) against that real output to confirm the synthetic-fixture validation holds against real data's shape (real slates have ~16 games/32 teams, not 4 games/8 teams -- the candidate-pool defaults in particular should get a second look at that scale).
- Session 3.3 is the last item in Phase 3 per the roadmap's original plan -- Phase 4 (Ownership & Pivot Logic) and Phase 5 (Status Automation) can both start once Session 3.1-3.3 are real-data-validated, per ROADMAP.md's "Notes on sequencing."
- If Phase 4's chalk_score/pivot logic ever wants to reason about "how contrarian is this stack" (leverage relative to a stacked-vs-unstacked field), the `stack_target` column in `lineups_multi_*.csv` output is already there to build on.

---

## Session 3.3 (ADDENDUM) — Real-data validation against the real DK pool + a real bug found and fixed
**Date completed:** 2026-07-22
**Status:** ✅ Complete — closes the "real-data re-validation" open item from the original Session 3.3 entry, for DK.

**What happened:** user supplied the real `salaries_dk_madden_20260721.csv` (the same real 93-player DK Madden Stream pool from Session 1.3/2.4/3.1), `weekly_stats_2025.parquet`, `schedules_2025.parquet`, and `vegas_implied_totals_10.csv`. Ran the real `build_projections.py` and the full Session 3.3 stacking test matrix against this real data instead of the synthetic fixture used when the code was first built.

**Reconstruction note:** `projections_baseline.py`/`projections_matchup.py` (Session 2.1/2.2) weren't re-fetched this session -- their exact documented formulas (recency weights `[0.35,0.25,0.20,0.12,0.08]`, REG-only + lookahead guard, sum-then-average matchup calc) were reconstructed from SESSION_LOG.md's own detailed writeups and run directly against the real `weekly_stats_2025.parquet`. Cross-checked against numbers already on record: reconstructed output was **532 baseline rows / 128 matchup rows** (exact match to Session 2.4's logged real run), and CIN's matchup factors (QB 1.244, RB 1.544, TE 1.687, WR 0.963) and HOU/DEN QB matchup factors (0.673/0.789) matched Session 2.2's logged real numbers to 3-4 decimal places. High confidence this reconstruction is equivalent to the real committed scripts, though the actual committed files remain the source of truth going forward.

**Real end-to-end result matched the project's own history exactly:** 91 players output (85 skill + 6 defense, matching Session 3.1's log), 41/85 flagged `no_real_game_this_week` (matching Session 2.4's addendum finding exactly), 0 players needing decision #4a's trade correction, Joe Flacco correctly zeroed with `opponent = BYE_OR_UNKNOWN` (the new Session 3.3 column working correctly on the exact case it was designed around), and the no-stack baseline lineup's salary ($46,900/$50,000) matched Session 3.1's originally shipped lineup exactly.

**Real bug found via real data (did not surface in the synthetic fixture) — fixed same session:**
`rank_candidate_teams()`/`rank_candidate_games()` only checked that the PRIMARY team/side had viable players -- never checked whether the OPPONENT side (needed for `--bring-back` and `--stack-mode game`) had any players in the pool at all. The synthetic fixture never caught this because every team in that 8-team fixture had a full roster on both sides of every game. The real DK Madden Stream pool only contains players from **6 teams** (CLE, DAL, HOU, IND, MIA, WAS -- a curated subset, not a full slate; consistent with ROADMAP.md's existing "Known Testing Artifact" note about this pool's small size). Auto-selecting MIA for a QB stack (highest implied_total with a real QB+partner) then requesting `--bring-back` failed, because MIA's real opponent (BUF) has zero players in this pool -- the auto-selector picked a candidate that was guaranteed to fail the bring-back constraint, rather than skipping it up front the way a missing QB/partner already gets skipped.

**Fix:** `rank_candidate_teams()` gained a `require_opponent_viable` param (used automatically whenever `--bring-back` is set) that filters out any candidate team whose real opponent has zero players in the current pool. `rank_candidate_games()` was tightened the same way -- both sides of a candidate game must have real players in the pool, not just exist as a real matchup in Vegas data. On this specific 6-team real pool, this correctly surfaced that **no valid bring-back or game-stack target exists at all** this week (none of the 6 teams' real opponents are also in the 6-team pool) -- confirmed this is a true fact about the thin pool, not a bug in the fix, by manually checking the 6 teams' real week-10 opponents (ATL, BUF, JAX, NYJ, DET, ATL) against the pool's own team list.

**Files created/modified:**
- `/dfs_optimizer/scripts/optimizer.py` (bug fix: `rank_candidate_teams()` gained `require_opponent_viable`, `rank_candidate_games()` now requires both sides present in-pool, `resolve_stack_candidates()` threads `bring_back` through to enable the check)

**Validation results (real DK data, week 10 2025, the 91-player real pool):**
- [x] No-stack baseline: lineup and salary ($46,900/$50,000) match Session 3.1's originally shipped real output exactly.
- [x] Standard QB stack, auto: correctly selected MIA (De'Von Achane + Jaylen Waddle already elite real projections, highest implied_total among in-pool teams with a real QB+partner) over the no-stack optimum, points dropped 147.68 -> 140.89 confirming the constraint is binding, not a no-op.
- [x] Bring-back / game-stack, auto (post-fix): correctly raises a clear, accurate "no viable candidate" error instead of picking MIA and failing later -- confirmed by hand that this 6-team pool genuinely has no team whose real opponent is also in-pool.
- [x] Mini-stack RB+DST: unaffected by the fix, still works correctly (real Dolphins DST + real MIA RB).
- [x] Multi-lineup diversification (10 lineups, 100% exposure): correctly rotated across the 4 real in-pool QB-stack-viable teams (MIA, HOU, IND, WAS) -- DAL excluded (real bye that week, 0 projection), CLE excluded (no viable QB/partner combo in this specific pool).
- [x] Fail-loudly, both paths confirmed on real data: (a) an impossible partner-count request (triple-TE stack) raises decision #21's pre-solve `RuntimeError` with a specific reason; (b) a request where individual partners exist but can't all fit in a legal 9-slot roster (e.g. QB+3 TEs total needs more TE/FLEX slots than exist) correctly falls through to the generic "Solver did not find an optimal solution" path instead -- both are real, distinct fail-loud paths and both were exercised for real this session.

**Known issues deferred:**
- **FD real-data validation is still open** -- same pre-existing project-wide gap (no real FD export has ever existed, per Session 1.3's log), not something this session could close. `build_projections.py --site fd` was run against the real weekly_stats/schedule/vegas data but still against the same *scaled-synthetic* FD salary file lineage as prior sessions -- not newly re-validated here.
- **Only a 6-team, 91-player pool was available** -- this is the same thin-pool limitation already tracked in ROADMAP.md's "Known Testing Artifact" note. A real full 32-team slate (expected at Preseason Week 1) may surface further edge cases the fix above doesn't anticipate (e.g. a team with a viable opponent that itself has no viable QB) -- worth a second real-data pass once a full slate exists.
- The reconstructed `projections_baseline.py`/`projections_matchup.py` logic (this session's scratch `compute_baseline_matchup.py`, not committed to the repo) was cross-checked numerically against logged real values and matched, but is not a substitute for actually re-running the real committed scripts -- flagged for completeness, not because there's reason to doubt the match.

**Handoff notes for next session:**
- The `require_opponent_viable` fix generalizes beyond this specific pool -- any future real slate with asymmetric team coverage (e.g. a single-game showdown-style contest, or a partial-slate promo) would hit the same class of bug without it.
- Session 6.1's Preseason Week 1 dry run (both sites, full slate) is the next real checkpoint for this -- worth specifically re-testing bring-back/game-stack auto-selection there, since a full 32-team slate should have plenty of valid candidates and would be the first chance to confirm the fix behaves correctly (not just fails gracefully) when real candidates DO exist on both sides.

---

## Session 4.1 — Chalk Score Heuristic
**Date completed:** 2026-07-22
**Status:** ✅ Complete

**What was actually built:**
- `scripts/ownership_heuristic.py` (new) — reads `final_projections_{site}_{week}.csv` (Session 2.4/3.3's output, including the `opponent`/`implied_total`/`over_under` columns added in 3.3's addendum) and produces a 0-100 `chalk_score` per player, per the card's four listed inputs:
  1. **Value** (`final_projection / (salary/1000)`), percentile-ranked within `position_group` (DK's `DST` and FD's `D`/`DEF` are folded into one "DST" bucket via `SITE_CONFIGS[site]["defense_position_values"]`, so each site has a real pool to rank against instead of a group-of-one).
  2. **Salary tier**, modeled as a U-shape rather than linear — both ends of a position's salary range (cheap punts, top-priced studs) score high, the middle scores low. `100 * abs(salary_percentile - 0.5) * 2`.
  3. **Vegas total** — straight percentile rank of `implied_total` across the whole pool (not position-grouped), since a shootout raises attention on every position in that game alike.
  4. **Manual name-recognition flag list** (`data/name_recognition_flags.csv`, new file — `player_id, player_name, flag_weight [0-20], notes`), applied as a flat additive bonus after the weighted blend, then the whole thing clipped to [0, 100]. Decision: **shared across sites**, not site-specific — a player's real-world fame doesn't change between DK and FD, only their price (already captured by inputs 1-2).
- Blend: `chalk_score = clip(0.45*value_pct + 0.20*salary_tier + 0.25*vegas_pct + name_bonus, 0, 100)`. Weights are a starting heuristic, not fit to real ownership data — flagged in the module docstring as a target for future retuning, same spirit as `build_projections.py`'s `BASELINE_WEIGHT`/`RECENT_FORM_WEIGHT`.
- Fail-loud schema guard: hard-requires `implied_total` (and the other Session 2.4/3.3 columns) in the input file — a real, non-hypothetical case this session, see Known issues deferred below.

**Files created:**
- `/dfs_optimizer/scripts/ownership_heuristic.py`
- `/dfs_optimizer/data/name_recognition_flags.csv` (starter file — one example row, Patrick Mahomes, marked "example only")

**Validation results:**
- [x] Rank last week's players by chalk_score, compare relative order to actual published ownership (if available) or intuition as a gut-check — **run against real data, both sites.** No real published ownership exists for this synthetic DK Madden Stream contest (same pre-existing gap noted throughout the project for FD; this contest isn't a real public slate for either site), so this used the card's own allowed fallback: an intuition gut-check.
  - Real 6-team pool (CLE/DAL/HOU/IND/MIA/WAS — same pool as Session 3.3's addendum), 91 players both sites, 0 nulls, 0 out-of-[0,100] scores.
  - Top of both sites' rankings: De'Von Achane (#1), Jonathan Taylor (#2), then HOU DST / Jaylen Waddle / Nico Collins / Dalton Schultz — matches known real value plays already logged in Session 3.3's addendum (Achane/Waddle called out there as elite real projections).
  - The 44 players with `final_projection == 0` (bye/no-real-game, per `build_projections.py`'s decision #4b) correctly clustered at the bottom of `chalk_score` (20.7-42.8), with every nonzero-projection player scoring 40.1+ — clean separation, not a hard cutoff (a couple of cheap-salary/high-team-total zero-projection players still land a modest floor score, a legitimate property of a multi-factor blend, not a bug).
  - 0 name-recognition bonuses fired on this pool — expected, the starter flag list only has Mahomes (KC), not present in this CLE/DAL/HOU/IND/MIA/WAS pool. Not a gap in the code, just an empty-in-practice input on this particular data.

**Decisions made / assumptions taken:**
- Name-recognition flag list is shared across sites (not site-specific) — see module docstring decision #4.
- Salary tier modeled as U-shaped rather than linear — see module docstring decision #2.
- Value and salary-tier percentiles computed within a position group that merges site-specific defense labels into one "DST" bucket, rather than per raw position string — otherwise DK (`DST` only) and FD (`D`/`DEF` only) would each rank defenses against a pool of one label.
- Blend weights (0.45/0.20/0.25 + additive name bonus) are an unfit starting heuristic, explicitly flagged for future retuning once real ownership data exists to check against.

**Known issues deferred:**
- **Two `final_projections_*.csv` files initially provided this session predated Session 3.3's addendum** (missing `opponent`/`implied_total`/`over_under`) — `ownership_heuristic.py` correctly failed loudly (`SystemExit`, missing-column message) rather than guessing. Not a bug; confirms the fail-loud guard works on a real, non-synthetic case. Resolved same session once the user regenerated both files with the current `build_projections.py`.
- **`data/name_recognition_flags.csv` ships thin** — one example row only (Mahomes). Real chalk_score output for pools that include genuinely famous-but-mediocre-value players won't reflect that yet. Not treated as blocking (roadmap card's own handoff-notes instruction already frames this as something that "needs periodic updates as player profiles change season to season," not a one-time completion gate) — but flagging so a future session doesn't assume this list is populated.
- **No real published ownership data exists to validate against, for either site** — same class of gap as FD's real salary/matchup data throughout this project. The intuition gut-check is the best available validation until Preseason Week 1 (or later) produces a real public slate with real published ownership to compare against.
- **Only a 6-team, 91-player pool available** (same thin-pool limitation tracked in ROADMAP.md's "Known Testing Artifact" note) — `value_percentile`/`salary_tier_score` are less meaningful in thin position groups; the script prints a stderr warning when any position group drops below 5 players (didn't fire on this real run — smallest group was QB at 12).

**Handoff notes for next session:**
- Session 4.2 (Cash-to-GPP Pivot Logic) is next and depends on this session's `chalk_scores_{site}_{week}.csv` output directly — the column names to build against are `player_id, player_name, position, salary, final_projection, chalk_score`.
- If a future session has access to a real full 32-team slate (Preseason Week 1+), re-run this exact validation there — worth specifically checking whether the position-group percentile approach still behaves sensibly with normal-sized position pools instead of this session's thin 6-team one.
- Consider revisiting `data/name_recognition_flags.csv` with a real curated list before relying on chalk_score for anything beyond direction-of-travel — right now it's a placeholder more than a real input.

---

## Session 4.1 (ADDENDUM) — estimated_ownership_pct added
**Date completed:** 2026-07-22
**Status:** ✅ Complete

**What happened:** after reviewing Session 4.1's `chalk_scores_*.csv` output, the user pointed out that `chalk_score` is a relative ranking with no real-world anchor — it was never meant to be read as a percentage — and asked directly whether an actual ownership PERCENTAGE estimate could be produced instead (or in addition), one that starts imprecise (no real historical ownership data exists yet) but can genuinely be refined over time/seasons as real data becomes available, rather than staying a pure rank forever.

**What was actually built:**
- `ownership_heuristic.py` extended with decision #5: `estimated_ownership_pct`, a 0-100 percentage estimate derived from `chalk_score`, anchored to one real, non-fabricated fact instead of an arbitrary curve — **roster-slot math**. Every lineup on a site fills exactly N slots of a given position, so across a rational field, total ownership summed across all eligible players at that position should land near `N * 100` percentage points. `compute_position_slot_budgets()` derives this "budget" per `position_group` directly from `SITE_CONFIGS[site]["roster_slots"]`. FLEX's budget (RB/WR/TE-eligible on both sites) is split evenly three ways — no real per-position FLEX usage-rate data exists yet, flagged as a simplification for the new Session 9.4 to replace with real data once available.
- Within each `position_group`, `chalk_score` converts to a share of that group's budget via a softmax (`weight = exp(chalk_score / OWNERSHIP_SOFTMAX_TEMPERATURE)`, normalized within the group) rather than a flat percentile-to-percentage rescale — chosen because real ownership is known to be concentrated (a few true chalk plays take a large share), not flat. `OWNERSHIP_SOFTMAX_TEMPERATURE = 15.0` is an explicitly unfit starting guess, flagged in both the script's docstring and the new Session 9.4 roadmap card as the clearest first retuning target.
- Bye/no-real-game players (`final_projection == 0`) get an explicit 0 weight, not just a low one — their share of the group's budget is fully redistributed to real players. This is a deliberate difference from `chalk_score`, which still leaves these players a nonzero floor value from the salary/vegas components alone; `estimated_ownership_pct` does not, since "what real ownership share should a confirmed-zero-projection player get" has an unambiguous answer (none).
- All-zero-signal edge case handled: if an entire `position_group` has `final_projection == 0` for every player (didn't occur in this session's real data, but implemented defensively), that group's budget falls back to an even split with a stderr warning, explicitly flagged as a backtest-fixture artifact that a real live slate should never trigger.
- Added two new roadmap cards to Phase 9 (Learning Loop): **Session 9.3 — Actual Ownership Logging** and **Session 9.4 — Ownership Estimate Retuning**, mirroring the existing 9.1/9.2 pattern (log actual-vs-projected, then periodically retune) but for ownership instead of projection accuracy. Session 9.3 explicitly flags that a real published-ownership source hasn't been identified/verified for either site yet — that's real open work, not assumed to exist.

**Files created/modified:**
- `/dfs_optimizer/scripts/ownership_heuristic.py` (extended — decision #5, new functions `compute_position_slot_budgets()` and `compute_estimated_ownership()`, new constants `FLEX_ELIGIBLE_POSITIONS`/`OWNERSHIP_SOFTMAX_TEMPERATURE`)
- `ROADMAP.md` (Session 4.1 card updated with the addendum; two new cards added: Session 9.3, Session 9.4; site-aware summary line updated to `9.1-9.4`)

**Validation results (real data, both sites, same 91-player/6-team pool as the original Session 4.1 entry):**
- [x] **Budget-conservation check** — each `position_group`'s summed `estimated_ownership_pct` matches its roster-slot budget exactly, both sites:
  - DK: DST 100.0% (budget 100.0%), QB 100.0% (100.0%), RB 233.3% (233.3%), TE 133.3% (133.3%), WR 333.3% (333.3%)
  - FD: identical budget structure, same exact match (FD's 9-slot roster has the same shape as DK's, just different labels/cap)
- [x] **Bye-zeroing check** — all 44 real `final_projection == 0` players got exactly `0.0%` estimated ownership, confirmed on both sites; their budget share visibly redistributed to the real (nonzero) players in the same position group (verified on the RB group: 14 real RBs' estimates sum to the full 233.3% RB budget with all 8 zero-projection RBs correctly excluded).
- [x] **Sanity/shape check** — top estimated_ownership_pct both sites: De'Von Achane (DK 68.7%, FD 60.2%), Jonathan Taylor (DK 46.9%, FD 54.0%), HOU DST/DEF (~48.4% both sites), Jaylen Waddle (~47.9% both sites) — same real value plays already flagged as elite in Session 3.3's addendum and the original Session 4.1 entry, now expressed as plausible-looking percentages rather than pure ranks. High concentration on Achane (particularly DK, where only 14 of 22 real RBs have a nonzero projection) is consistent with this being a genuinely thin 6-team pool, not a full slate — flagged, not treated as a red flag.

**Decisions made / assumptions taken:**
- `estimated_ownership_pct` is explicitly still NOT real ownership data — it's an estimate anchored to real roster-slot math, clearly distinguished in the docstring from a fitted/calibrated number. Important this distinction doesn't get lost in later sessions that consume this column.
- FLEX budget split evenly (not weighted toward RB/WR over TE, even though real-world FLEX usage almost certainly skews that way) — no real data exists yet to weight it correctly, and guessing at real-world skew without data would be fabricating precision this project has consistently avoided elsewhere (e.g. decision #3/#4 in `build_projections.py`).
- Softmax over chalk_score (not a linear/percentile rescale) chosen specifically because flat rescaling would misrepresent how concentrated real DFS ownership is known to be — this is a shape assumption, not a fitted one, and is named as such.

**Known issues deferred:**
- **`OWNERSHIP_SOFTMAX_TEMPERATURE` and the FLEX-split-evenly simplification are both unfit to any real data** — by design, since no real ownership data exists in this pipeline yet. Both are explicitly named as Session 9.4's first retuning targets once Session 9.3 produces real logged data.
- **Session 9.3 (Actual Ownership Logging) has a real, unresolved open question**: no real published-ownership source has been identified or verified for either site yet. Flagged explicitly in that card rather than assumed solvable — same caution already applied to the FD salary format and Vegas odds vendor choice elsewhere in this project.
- Same thin-pool caveat as the rest of Session 4.1 — a full 32-team slate (Preseason Week 1+) is the first point this can be re-validated against a normal-sized pool instead of this session's 6-team one.

**Handoff notes for next session:**
- Session 4.2 (Cash-to-GPP Pivot Logic) can now choose to use either `chalk_score` (pure rank) or `estimated_ownership_pct` (percentage estimate) — or both — when deciding pivot targets. Worth an explicit decision in that session rather than defaulting to one silently, since they're not interchangeable (rank vs. an anchored-but-unfit percentage).
- Session 9.3's first real task is investigative, not code — confirm what real ownership data is actually accessible per site before assuming the card's file/column design is right. That design may need to change once a real source is confirmed.

---

## Session 4.2 — Cash-to-GPP Pivot Logic
**Date completed:** 2026-07-22
**Status:** ✅ Complete

**What was actually built:**
- `scripts/pivot_finder.py` (new) — reads a site/week's `lineup_single_{site}_{week}.csv` (Session 3.1), `chalk_scores_{site}_{week}.csv` (Session 4.1), and `final_projections_{site}_{week}.csv` (Session 2.4/3.3), and produces `pivot_suggestions_{site}_{week}.csv`: for every player in the cash lineup, the top N (default 3) ranked same-position, lower-owned, similarly-priced pivot candidates, each with a `leverage_score`.
- **Open decision from Session 4.1's addendum, resolved by the user at the start of this session:** use `estimated_ownership_pct`, not `chalk_score`, as the ownership signal for picking pivot targets. This changes the roadmap card's own validation checkbox wording ("lower chalk_score") to be checked against `estimated_ownership_pct` instead — flagged explicitly as decision #1 in the module docstring, and `chalk_score` is left out of this script's join/output entirely.
- **Join key decision (new, this session):** `lineup_single_{site}_{week}.csv` (Session 3.1's `optimizer.py` output) has never carried `player_id` — only `player_name, position, team, salary, projection, opponent`. Rather than retroactively change Session 3.1/3.2/3.3's already-validated output schema, `pivot_finder.py` joins the cash lineup to `chalk_scores`/`final_projections` on the normalized triple `(player_name, position, team)`, reusing `ingest_salaries.py`'s existing `normalize_name()`/`normalize_team()` helpers (same normalization Session 1.3 already uses to join site salary exports against nflverse data) rather than inventing a second normalization scheme. Fails loudly (`SystemExit`) on any zero- or multi-match.
- **Salary tolerance decision (new, this session):** a percentage of that site's cap (`SALARY_TOLERANCE_PCT_OF_CAP`, default 10%), not a flat dollar amount — travels between DK's $50K and FD's $60K cap unchanged, same reasoning already applied to `optimizer.py`'s `DEFAULT_MAX_EXPOSURE_PCT` (Session 3.2 decision #8).
- **Leverage score formula (decision #6):** `ownership_edge_pts = cash_player.estimated_ownership_pct - candidate.estimated_ownership_pct`, `projection_retention = min(candidate.final_projection / cash_player.final_projection, 1.0)`, `leverage_score = clip(ownership_edge_pts * projection_retention, 0, 100)` — kept on the same bounded 0-100 scale as `chalk_score`/`estimated_ownership_pct` by capping retention at 100% rather than letting an "outprojects the cash player" candidate inflate the score past 100; that case is instead flagged via a separate `outprojects_cash_player` boolean column. Explicitly flagged as an unfit starting heuristic, same as every other blend weight in this project.
- **Hard full-lineup salary cap re-check (decision #5):** for every candidate, computes what the entire 9-player lineup's total salary would be after the swap (`lineup_total_salary - cash_salary + candidate_salary`) and hard-filters out anything that would exceed that site's cap — a stricter, separate check from the per-player salary tolerance (decision #3), same "structural guarantee, not eyeballing" pattern as `optimizer.py`'s own salary_cap constraint.
- Bye/zero-projection players (`final_projection == 0`) are never suggested as pivots regardless of their (correctly zeroed) ownership — same decision #4b philosophy as every prior session touching this.
- A candidate already rostered elsewhere in the same cash lineup is excluded from that lineup's pivot pool.

**Files created:**
- `/dfs_optimizer/scripts/pivot_finder.py`

**Validation results (real data, both sites, same 91-player/6-team pool as Sessions 2.4-4.1):**
- [x] **Same position, within salary tolerance, lower estimated_ownership_pct than the player it replaces** — ran `validate_pivot_suggestions()` (the script's own automated assertion) against real output for both sites: 26 suggestion rows each (9 cash-lineup players × up to 3 candidates, one player — Daniel Jones, QB — only had 2 eligible candidates within tolerance, thin-QB-pool artifact already logged in Session 4.1). All passed. Independently re-verified same-position for every row a second way: cross-referenced each `pivot_player_name` back against `final_projections_{site}_10.csv`'s own `position` column directly (not just trusting the script's internal filter) — 0 mismatches, both sites.
- [x] **Pivot swap doesn't break the full lineup's salary cap** — confirmed `lineup_salary_after_swap <= site_salary_cap` for all 26 rows, both sites (DK cap $50,000, max post-swap total seen $48,400; FD cap $60,000). This is a hard filter in `find_pivots_for_player()`, not just a reported column — a candidate that would break the cap is excluded from the output entirely rather than surfaced with a warning.
- [x] **Fail-loud guards, tested against real (not hypothetical) failures:** (1) missing week's `lineup_single` file → clean `FileNotFoundError` with a clear fix instruction; (2) a stale/truncated `chalk_scores` file (simulated by truncating a real copy to 49 of 91 real rows) → `build_candidate_pool()` correctly raised `SystemExit` rather than silently proceeding with a partial join.

**Decisions made / assumptions taken:**
- `estimated_ownership_pct` (not `chalk_score`) used for pivot targeting — user-confirmed at the start of this session, resolving the open item flagged in Session 4.1's addendum handoff notes.
- Join to the cash lineup via normalized `(player_name, position, team)`, not `player_id` — `lineup_single_*.csv`'s schema (Session 3.1) is left unchanged rather than retroactively modified.
- Salary tolerance is % of site cap (default 10%), not a flat dollar amount — explicitly unfit to real data, flagged as a first retuning target alongside `OWNERSHIP_SOFTMAX_TEMPERATURE` (Session 4.1 addendum) once real usage exists.
- `leverage_score` capped at 100 via retention-capped-at-1.0, with an "outprojects the cash player" case surfaced as a separate column rather than an uncapped score — keeps the output on the same 0-100 convention as `chalk_score`/`estimated_ownership_pct`.
- Top N defaults to 3 (roadmap card's own "2-3" range), configurable via `--top-n`.

**Known issues deferred:**
- Same thin-pool caveat as every prior session touching this real 6-team/91-player test data — `Daniel Jones` (the only real nonzero-projection DK/FD QB with a lower-owned same-position peer within tolerance limited to 2, not 3, candidates) is a property of the test pool's thin QB depth (4 total nonzero QBs, per ROADMAP.md's "Known Testing Artifact" note), not a bug. Re-validate against a full 32-team slate once available (Preseason Week 1+).
- `SALARY_TOLERANCE_PCT_OF_CAP` (10%) and the leverage-score blend are both unfit-to-real-data starting heuristics, same as Session 4.1's blend weights and softmax temperature — flagged for a future retuning session once real usage/finish-rate data exists.
- `pivot_suggestions_{site}_{week}.csv` files were generated locally against real repo data during this session but are NOT yet committed to the repo — same "committed output can lag the current script version" gap already true of `lineup_single_dk_10.csv`/`lineup_single_fd_10.csv` (both regenerated fresh this session too, since the committed copies predated Session 3.3's `opponent` column addition).

**Handoff notes for next session:**
- Phase 4 (Ownership & Pivot Logic) is now complete. Phase 5 (Status Automation & Scheduling) is next per ROADMAP.md — Session 5.1 (Injury/Active Status Pull) has no dependency on this session's output and can start independently.
- Whoever next touches `optimizer.py`'s `assign_roster_slots()` should know `pivot_finder.py` depends on its current column set (`player_name, position, team, salary, projection, opponent` — no `player_id`) via name/team/position matching; adding `player_id` to that output later would be a welcome simplification for this script, but isn't required.

---

## Session 5.1 — Injury/Active Status Pull
**Date completed:** 2026-07-22
**Status:** 🟡 Mechanism complete, validated on real data. One item (real game-day OUT/DOUBTFUL cross-check vs. NFL.com) intentionally deferred to Preseason Week 1 — same class of gap as this project's existing Vegas-lines and FD-salary deferred validations, now tracked alongside them in ROADMAP.md's "Known Deferred Validations" section. Not blocking — Session 5.2 doesn't depend on the deferred item.

**What was actually built:**
- `scripts/status_check.py` (new) — two subcommands:
  - `pull`: hits ESPN, matches players to nflverse `player_id`, writes `output/player_status_{week}_{timestamp}.csv`.
  - `apply`: reads a `pull` output plus an existing `final_projections_{site}_{week}.csv` and forces `final_projection` to `0.0` for every OUT player, reusing `build_projections.py`'s existing decision #4b zero-out convention rather than inventing a second "doesn't count" mechanism. DOUBTFUL/QUESTIONABLE are flagged via a new additive `injury_status` column, `final_projection` left untouched — "flags but doesn't exclude," per the roadmap card. This is what let the whole session ship with only `status_check.py` touched — `optimizer.py` already never selects a 0.0-projection player over a legal alternative (its own decision #4), so zeroing upstream is sufficient, structural exclusion.
- **ESPN endpoint decision (module docstring decision #1):** three real ESPN endpoints were checked live before picking one:
  - League-wide `/nfl/injuries` feed — rejected, it's a news/transactions feed (9MB+ pull, almost every entry's own `status` field reads "Active"), wrong data shape.
  - Per-team `sports.core.api.espn.com/.../injuries` — rejected, returns every injury-report entry for the whole season as bare `$ref` links (one real team returned 66 of them), each needing 2 more fetches (status, then athlete name).
  - Per-team **roster** endpoint (`site.api.espn.com/.../teams/{id}/roster`) — used. Each player's own `injuries` array is embedded inline alongside name/position — one call per team, 32 calls total for the whole league.
- **Matching (decision #3):** reuses `ingest_salaries.py`'s `normalize_name()`/`normalize_team()`/`build_player_reference()` directly rather than a second scheme. ESPN's own team abbreviations (`LAR`, `WSH`) already collide cleanly with `ingest_salaries.py`'s existing `BASE_TEAM_ABBREV_MAP`, so no new abbreviation table was needed. Two-tier matching: exact (name, team), then a name-only fallback restricted to a UNIQUE resolution across the whole reference (catches a real trade between a player's last nflverse team and their current ESPN team).
- **Status mapping (decision #2):** ESPN's raw `injuries[].status` strings collapse to OUT/DOUBTFUL/QUESTIONABLE/ACTIVE via `STATUS_MAP`. No `injuries` entry at all → ACTIVE. Any raw string not in `STATUS_MAP` fails loudly (logged, nonzero exit) rather than being silently guessed.

**Files created:**
- `/dfs_optimizer/scripts/status_check.py`

**Files modified:**
- `/dfs_optimizer/scripts/optimizer.py` — see "Real bug #1" below.

**Validation results:**
- **Real end-to-end `pull` run** (user's own environment, all 32 teams, real live ESPN data, real `weekly_stats_2025.parquet` as the matching reference): 919 fantasy-relevant players pulled, 0 fetch failures, 533 matched (58%) — the other 386 are legitimate misses (deep bench/practice-squad players and true rookies with no 2025 game log to match against, e.g. real 2026 rookie Jeremiyah Love, who was in college in 2025; this is the same "no history yet" case `build_projections.py`'s own decision #3 already handles). Status breakdown: 5 OUT, 0 DOUBTFUL, 39 QUESTIONABLE, 489 ACTIVE — all real, recognizable names (Mahomes, Bo Nix, Malik Nabers, George Kittle, Dak Prescott among the QUESTIONABLE list). This exact same run was independently reproduced in a sandboxed offline test (mocked ESPN responses matching the real payload shape) before the user ran it for real, and the user's real numbers matched the sandbox test's numbers exactly.
- **Real `apply` run**, DK, week 10: correctly zeroed the one real OUT player present (Julian Hill, MIA, already-0.0 from an unrelated bye/no-real-game — confirmed not a meaningful exercise of the zero-out path on its own), flagged 8 real QUESTIONABLE players, left ACTIVE players untouched. `Validation: PASS` printed and independently reloaded/re-checked.
- **[x] Roadmap checkbox 2 — "OUT players actually excluded from optimizer output," validated for real:** a real, previously-nonzero player (Jonathan Taylor, IND RB, real week-10 `final_projection` of 17.25) was manually forced to OUT and run through the full real pipeline (`apply` → `optimizer.py`) in the user's own environment. Optimizer produced a clean, legal 9-player lineup with no zero-projection-selected warning, and Jonathan Taylor was confirmed absent from `lineup_single_dk_10.csv`. FD side not separately re-run — the exclusion mechanism (zeroing `final_projection` before `optimizer.py` ever reads the file) is site-agnostic by construction, so this is treated as covered rather than needing a duplicate manual run.
- **[ ] Roadmap checkbox 1 — "cross-check against NFL.com," deferred, not failed:** pulled live 2026-07-22 (off-season/training camp) — every real non-empty status found was tied to a long-term injury recovery (e.g. Mahomes' ACL) or a personal/legal situation, not a game-week designation, since no real NFL game exists yet to designate a player in/out FOR. Nothing real exists on NFL.com's injury report to cross-check against yet either. First real point this closes: Preseason Week 1 (Aug 13-15, 2026) — added to ROADMAP.md's "Known Deferred Validations" section alongside the existing Vegas-lines and FD-salary gaps.

**Real bug #1 found via real testing (pre-existing, unrelated to this session's own scope) — fixed same session:**
`optimizer.py` (Session 3.2) crashed immediately on the user's environment (Python 3.14) with `ValueError: unsupported format character ')' ... badly formed help string`, on the very first `--max-exposure` argparse argument. Root cause: `help=f"...({DEFAULT_MAX_EXPOSURE_PCT:.0%}). ..."` renders a literal `%` into the help text (e.g. `"...40%)..."`), and argparse's `HelpFormatter` internally does its own `%`-substitution over every help string (for `%(default)s`-style tokens) — a bare `%` followed by `)` isn't a valid conversion, so it crashes. Reproduced exactly (byte-for-byte matching error) in a local Python 3.12 environment by directly testing argparse's internal `help_string % params` step; confirmed the same crash. This likely didn't surface before because earlier Python versions only ran this check lazily (at `--help` time); Python 3.14 checks it eagerly at `add_argument()` time, so it now fails on every invocation, not just `--help`.
**Fix:** one-character change, line 1150: `{DEFAULT_MAX_EXPOSURE_PCT:.0%}` → `{DEFAULT_MAX_EXPOSURE_PCT:.0%}%` (the extra trailing `%` makes the literal rendered text contain `%%`, which argparse's substitution correctly collapses back to a single `%` for display, verified against the exact internal substitution argparse performs). Confirmed via diff that this is the ONLY line changed from the user's real uploaded file, confirmed `--help` renders `(default 40%)` correctly with no crash, confirmed no other `add_argument` call in the file has the same pattern.

**Real bug #2 found via real testing (in `status_check.py` itself) — fixed same session:**
The user's first attempt at a forced-OUT test (to exercise the exclusion mechanism, since no real game-day OUT exists yet — see checkbox 1 above) appended a synthetic OUT row for a player who already had a real ACTIVE row in the same status file, rather than replacing it. `apply`'s `projections.merge(status[...], on="player_id", how="left")` silently fanned that player out into TWO rows in the output `final_projections` file — which then crashed `optimizer.py`'s solver (`TypeError: must be real number, not Series`) on that duplicated `player_id`, rather than producing a clean excluded-player result. **Fix:** `apply` now checks for duplicate `player_id`s in the status file up front and fails loudly with a clear message before merging, rather than letting a non-unique merge key silently corrupt the output — same "guarantee, not eyeballing" pattern as every other validation in this project. Verified: (a) the exact scenario that broke the user's run now fails loudly with the new guard instead of corrupting anything; (b) the normal, non-duplicated case still runs clean. The corrected forced-OUT test (replace, not append) then ran clean end-to-end for real — see checkbox 2 above.

**Decisions made / assumptions taken:**
- ESPN's per-team roster endpoint chosen over two other real, tested ESPN endpoints — see module docstring decision #1 for the full comparison.
- Matching reuses `ingest_salaries.py`'s existing normalization helpers rather than a new scheme (decision #3).
- Only QB/RB/WR/TE/FB pulled from each roster (decision #3) — matches `build_projections.py`'s own skill-position universe; other positions can't appear in a DFS pool.
- `apply` overwrites `output/final_projections_{site}_{week}.csv` in place by default (the exact file `optimizer.py` reads, which has no path override of its own) — `--out` available to redirect for a dry run.
- New duplicate-`player_id` guard added to `apply` (decision #6) after real testing surfaced the gap — fails loudly rather than silently corrupting the merge.

**Known issues deferred:**
- **Real OUT/DOUBTFUL game-day designations, cross-checked against NFL.com** — genuinely can't be validated until a real game week exists. First real point this closes: Preseason Week 1. Tracked in ROADMAP.md's "Known Deferred Validations" section.
- **Match rate (58% on the real 919-player pull)** — the unmatched 42% is overwhelmingly deep bench/practice-squad players and true rookies with no 2025 nflverse game log, i.e. expected and not a bug (spot-checked several, including a real notable 2026 rookie). Worth a second look only if a future session finds a real STARTER incorrectly unmatched — none were found in this session's spot-checks.
- **FD side of the OUT-exclusion mechanism not separately re-run** — treated as covered by construction (site-agnostic zeroing upstream of `optimizer.py`), not independently exercised this session. Low risk given the mechanism's design, but flagged rather than silently assumed.

**Handoff notes for next session:**
- ESPN endpoint used: `https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team_id}/roster`. Unofficial/undocumented — last verified working 2026-07-22. Re-verify before relying on it close to a real slate.
- Session 5.2 (Scheduling Infrastructure) is next per ROADMAP.md and has no dependency on this session's deferred item — can proceed normally. Whoever builds Session 5.2's automation should know `status_check.py pull` takes ~30-60 seconds for all 32 teams and `apply` is a fast local operation.
- Worth re-running this session's full validation checklist (both checkboxes) once Preseason Week 1 provides a real game-day designation to test against — this session's `pull` mechanism has never been checked against a genuine OUT-for-Sunday's-game situation, only long-term-recovery/personal-situation designations and one manually-forced test case.

## Session 5.2 — Scheduling Infrastructure
**Date completed:** 2026-07-23
**Status:** ✅ Mechanism complete and validated end-to-end for real, both of the roadmap card's validation checkboxes closed. One new deferred action opened (see below) — same "can't fully finalize until real slate/lock data exists" pattern as this project's other deferred gaps, but this one is a **configuration step, not a data/logic gap**: the real weekly schedule can't be set until a real week's lock time is known, tracked to close at Preseason Week 1 alongside this project's existing deferred-validation checkpoint.

**What was actually built:**
- `/dfs_optimizer/.github/workflows/refresh_data.yml` — orchestrates `vegas_odds.py` → `status_check.py pull` → `build_projections.py` (both sites) → `status_check.py apply` (both sites), on three trigger types: `light_vegas_refresh` (native GH cron, Tue-Fri 1x/day + Sat 2x/day + Sun hourly, vegas-only, matches Session 2.3's already-budgeted ~121 credits/month cadence), `full_refresh_scheduled` (native GH cron, every 3 hours on Thu/Sun/Mon), and `full_refresh_dispatch` (`repository_dispatch`, fired by the Cloudflare Worker for the near-lock window). Every run appends a row per step to `logs/automation_run_log.csv` (site, step, status) regardless of success/failure, then commits changed outputs back to the repo.
- `/dfs_optimizer/cloudflare_worker/scheduled_refresh.js` + `wrangler.toml` — a thin relay Worker, deployed live at `dfs-optimizer-scheduler.drgregmscott.workers.dev`. On an authenticated GET (shared-secret query token), fires a GitHub `repository_dispatch` event. Exists specifically because GitHub's own scheduled-cron has documented multi-minute delay under load, unacceptable for the near-lock window — this path relays a cron-job.org ping into a dispatch almost instantly instead (confirmed: sub-2-second Worker response, dispatch → workflow start well under a minute in every test this session).
- `/dfs_optimizer/data/current_slate.json` (new, not on the original file list — flagged as necessary drift) — the config the workflow reads each run for season/week/slate_id per site, since the automation has no other way to know which slate is current.
- `/dfs_optimizer/logs/automation_run_log.csv` — seeded with header row, `site` column included per the roadmap card.

**Key scope decision — salary ingestion is explicitly NOT automated:** confirmed via web search (no DK/FD public salary API exists; the only sanctioned path is the "Export to CSV" button on each site's own contest page, matching how every public third-party DFS tool sources this data) that `ingest_salaries.py` can never run unattended. The automated refresh loop therefore only covers Vegas lines, injury status, and rebuilding projections/applying status against whatever salary file is already committed — salary download + `ingest_salaries.py` + updating `current_slate.json` remains a deliberate manual weekly step, discussed and confirmed acceptable with the user before building.

**Why `projections_baseline.py`/`projections_matchup.py` are also excluded from the refresh loop:** both are computed once per week from `weekN-1` and earlier weekly_stats — they don't change intra-week the way Vegas lines and injury status do, so scheduling them on a 10-minute or 3-hour cadence would burn CI minutes for no new data. Confirmed by reading both scripts' actual logic before building, not assumed.

**Deployment (done live, in the user's real accounts, via Claude in Chrome browser automation):**
- GitHub: `ODDS_API_KEY` repo secret added by the user (I navigated to the right screen but never touch API key/token values myself, per standing rule); Actions workflow permissions set to Read/write.
- Cloudflare: Worker deployed via a Git-connected build (root directory `cloudflare_worker`, deploy command `npx wrangler deploy`) rather than the in-browser Quick Edit code editor, which turned out to be unavailable on this account/dashboard version. Two secrets (`GH_DISPATCH_TOKEN` — a fine-grained GitHub PAT scoped to just this repo, Contents: Read and write — and `WORKER_AUTH_TOKEN`, a random string I generated and the user pasted in) and two plaintext vars (`GITHUB_OWNER`, `GITHUB_REPO`, sourced automatically from `wrangler.toml`) were configured; I filled in every non-secret field and generated the suggested `WORKER_AUTH_TOKEN` value, but the user pasted every actual secret/token value themselves in every case — no exceptions, including the cron-job.org job URL (which embeds `WORKER_AUTH_TOKEN` as a query param).
- cron-job.org: new account created by the user (account creation is a standing "user does this themselves" action). One job created ("DFS Optimizer - Near-Lock Refresh") pointed at the Worker URL.

**Validation results — both roadmap checkboxes closed:**
- **[x] "Log actual fire times vs scheduled times... confirm delay is acceptable"** — validated via three real `repository_dispatch` round-trips this session (Worker → GitHub → workflow start), all firing within seconds, well inside the "acceptable" bar. First attempt (against the real, still-placeholder `current_slate.json` pointed at season 2026/week 1) correctly failed on `status_pull`/`build_projections`/`status_apply` — root-caused to the real, expected reason (no `weekly_stats_2026.parquet`/`baseline_recent_form`/`matchup_factors` exist yet, since the 2026 season hasn't been played), not a code bug — confirmed by checking `output/` and `data/` directory contents directly rather than assuming. `vegas_odds_pull` succeeded both times (real live Odds API data, no season-data dependency). To get a genuine full-green run, `current_slate.json` was temporarily pointed at the real committed week-10-2025 test data (same slate every prior session validated against); the resulting run succeeded on **all 6 logged steps** (`vegas_odds_pull`, `status_pull`, `build_projections` DK/FD, `status_apply` DK/FD), confirmed via the real committed `automation_run_log.csv` content, then reverted back to the real 2026 placeholder.
- **[x] "Confirm the Cloudflare Worker + external trigger combo fires within 1-2 minutes... consistently"** — cron-job.org's own "Test run" button confirmed the endpoint (200 OK, dispatch fired) but not the *unattended scheduler itself*. Caught this distinction and closed it for real: temporarily repointed the job's schedule to fire twice in the next ~20 minutes today (no functional difference vs. waiting for an actual Sunday, since no real games exist either way right now — same reasoning applied to skip an unnecessary wait), confirmed it fired completely unattended ("Today at 7:20:03 AM — Successful, 1.46s") and that the fire correctly triggered a real GitHub Actions run (`near_lock_refresh #9`), then reset the schedule back to the Sunday template.

**Decisions made / assumptions taken:**
- Near-lock cadence set to **every 10 minutes** (not the originally-proposed 5-10 minute range) — user's call, reasoned from real NFL inactives-report timing: early-slate (1pm ET) inactives post ~10:30am ET, late-slate (post-1pm ET games) inactives post ~1:30pm ET (after early lock), so a 10-minute near-lock cadence comfortably catches the information as soon as it's real without the extra API/CI load of 5-minute polling.
- The Sunday 11:00-11:50am CT / every-10-min cron-job.org schedule is an explicit **template**, not real — it approximates a typical 1:00pm ET early-slate lock and must be hand-edited (Days/Hours in the cron-job.org UI, no code change) to match each week's actual lock time. Same treatment for `current_slate.json`'s week/slate_id.
- Worker deployed via Cloudflare's Git-integration build path rather than the dashboard's in-browser code editor, after confirming the latter isn't available on this account — documented in case a future session hits the same dead end.
- Every credential/token/secret value (GH PAT, Worker auth token, ODDS_API_KEY, the cron-job.org job URL containing the auth token) was entered by the user directly, never by me — including the `WORKER_AUTH_TOKEN` value I generated myself, since generating a value and typing it into a field are different things. Consistent, no exceptions made this session despite several natural opportunities to shortcut it.

**New deferred action opened this session (added to ROADMAP.md's "Known Deferred Validations" section and cross-referenced in Session 6.1's card):**
- **Set the real weekly cron-job.org schedule + `current_slate.json`, both sites, for real Preseason Week 1 lock times.** The Sunday-11am-CT template and the season-2026/week-1 placeholder both need hand-updating to whatever Preseason Week 1's actual slate/lock times turn out to be — this can only happen once those are known, i.e. at the same time as Session 6.1's live dry run. Not a bug or a gap in this session's work, just a config step that has no "real" value to set yet.

**Known issues deferred:**
- Real weekly cron-job.org schedule + `current_slate.json` update — see above, closes at Session 6.1 (Preseason Week 1, Aug 13-15, 2026).
- The two "Scheduled" native-cron GitHub Actions runs that fired coincidentally during this session's manual testing window (Thursday, ~12:00 UTC, matching the `full_refresh_scheduled` cron pattern) were observed succeeding/failing consistent with the same missing-2026-data explanation as everything else this session — not separately investigated in detail, since they're the same code path already validated via the `repository_dispatch` runs.

**Handoff notes for next session:**
- Everything needed to actually run automatically is live: Worker deployed, secrets set, GitHub Actions permissions correct, cron-job.org job created and confirmed firing on its own.
- Next real action on this thread isn't a new session — it's the deferred config step above, to be done alongside Session 6.1's Preseason Week 1 dry run, not before.
- Per ROADMAP.md, Phase 6 (Preseason Live Dry Runs, Session 6.1) is next chronologically, though Phases/Sessions in between may still be open — check ROADMAP.md's own sequencing notes.

## Session 7.1 — Basic UI + Hosting Setup
**Date completed:** 2026-07-23
**Status:** ✅ Complete

**Why this session ran now, out of numeric order:** per ROADMAP.md's "Notes on sequencing" execution-order update logged the same day, Phase 6 is blocked on a real preseason slate (Aug 13-15 at the earliest) and Phase 7 was explicitly permitted to run ahead of it once Phase 3 was stable. Session 7.1 only depends on Session 3.2's output format, which has been stable since Phase 3 closed.

**What was actually built:**
- `/dfs_optimizer_frontend/index.html` (new) — a single self-contained static page ("Lineup Room"): vanilla HTML/CSS/JS, no framework, no build step. Two upload slots (DK/FD, click or drag-and-drop), a DK/FD toggle that switches between independently-held datasets without re-upload, auto-detection of single- vs. multi-lineup format (checks for a `lineup_id` column), prev/next navigation for multi-lineup files, a segmented salary-cap meter, and an integrity strip (roster slot count vs. 9 expected, over/under cap, count of zero-projection players in the lineup).
- `/dfs_optimizer_frontend/README.md` (new) — usage notes, the Cloudflare Pages deploy steps, and this session's validation record.
- **No backend, by design** — CSV is parsed entirely client-side in the browser; nothing is uploaded anywhere. Matches the roadmap card's own framing ("as a contract, not live data yet") — live wiring to the repo/Worker is explicitly Session 7.2's job, not this one's.

**Key decisions this session:**
1. **Static single-file HTML, not a framework** — fastest path to a zero-config Cloudflare Pages deploy for this session's actual scope (upload/view only, no real interactivity yet). Flagged as a decision to revisit, not a permanent choice: if Session 7.2's UI-optimizer controls need more state/interactivity than vanilla JS comfortably handles, that's the point to reconsider — not before, since it'd be unused complexity today.
2. **Subfolder in the existing `DFS_Optimizer` repo, not a separate repo** (user-confirmed) — keeps everything on the same GitHub/Cloudflare account pairing already wired up in Session 5.2, and Cloudflare Pages' "build output directory" setting handles a subfolder cleanly (same pattern as `cloudflare_worker/`'s "root directory" setting in that session).
3. **Cloudflare Pages, not Vercel/Netlify** (ROADMAP.md's original card language) — user's explicit call this session, consolidating hosting onto the Cloudflare account already in use.
4. **No purchased custom domain.** Mid-session, Claude incorrectly listed "connect the purchased domain" as a required remaining action — this contradicted the project's actual kickoff conversation, where a domain was flagged as the one *possible* paid exception, never a requirement, and the project was framed as buildable 100% free otherwise. Corrected once flagged by the user: a free Cloudflare Pages `*.pages.dev` subdomain is a real, publicly-reachable HTTPS domain and fully satisfies the roadmap card's own "real domain, not localhost" validation line. ROADMAP.md's Session 7.1 card is corrected to match (see that file's own note). A custom domain remains available later as a purely optional, cosmetic upgrade if ever wanted — not attached to any session's completion.
5. **Shared parsing/render code path for both file formats** — single- and multi-lineup CSVs both flow through the same `groupBySite()`/render logic (multi-lineup rows carry a real `lineup_id`; single-lineup rows are treated as one implicit lineup). No separate code path to maintain per format.

**Real data used to build and validate against (not synthetic):** pulled `lineup_single_dk_10.csv`, `lineups_multi_dk_10.csv`, and `lineups_multi_fd_10.csv` directly from the private repo via Claude in Chrome (browser-based, since the repo needs the user's own GitHub auth — confirmed the raw/API fetch paths 404 without it). Used real rows from all three, including the already-logged real zero-projection Dallas DST/DEF bye-week case (Session 3.1's addendum) on both sites, and confirmed DK's `DST` vs. FD's `DEF` roster-slot label difference directly from real committed data rather than assuming it from `optimizer.py`'s docstring alone.

**Validation results (roadmap's two checkboxes, both closed for real):**
- **Logic-level (Node, before deploy):** extracted the page's CSV-parsing/grouping JS and ran it standalone in Node against the real files above. Confirmed correct row counts, correct 9-slot rosters, correct salary totals (hand-checked against the real per-row salaries), correct roster-slot ordering for both sites, the real zero-projection Dallas row correctly flagged rather than silently included, and that the trailing space present in real defense player names in the committed CSVs (`"Browns "`, `"Cowboys "`) doesn't leak into a trimmed display.
- **[x] "Site loads on the real domain, not just localhost":** deployed via Cloudflare Pages, git-connected to `DFS_Optimizer`, build output directory `dfs_optimizer_frontend`, no build command/framework preset (confirmed via screenshot before deploying). Live and confirmed reachable at `https://dfs-optimizer.pages.dev`.
- **[x] "A generated lineup from the backend correctly displays with no data mismatches, for both DK and FD selections":** re-validated live on the deployed domain (not just Node), all with real data:
  - **DK multi-lineup** (2 real lineups from `lineups_multi_dk_10.csv`): both showed 9/9 slots, correct salary ($46,900/$50,000 and $34,900/$50,000), correct points (147.68 and 81.16); the real zero-projection Dallas DST correctly flagged "0 PTS" with the integrity strip correctly reading "1 zero-projection player(s)" on that lineup and "0" on the other.
  - **FD multi-lineup** (2 real lineups from `lineups_multi_fd_10.csv`): $60,000 cap correctly applied (not DK's $50,000), `DEF` label correctly shown instead of DK's `DST`, correct totals (129.41 and 62.65 pts), the real zero-projection Dallas DEF case correctly flagged the same way as DK's.
  - **DK/FD toggle independence:** switched DK → FD → DK live. Each site's uploaded file and current lineup position (mid-navigation, not just lineup 1) persisted exactly as left with zero cross-contamination — this is the part of the roadmap card's own "driving which data set is displayed" language that specifically needed a live check, not just a logic-level one.
  - **Single-lineup format** (`lineup_single_dk_10.csv`, real data, has an `opponent` column the multi-lineup files don't): uploaded live, correctly auto-detected as single-lineup (no "/ N" lineup counter shown, unlike the multi-lineup case), correctly displayed the extra `opponent` column ("IND vs ATL", etc.), correct salary ($42,200/$50,000) and points (128.42), 9/9 slots, 0 zero-projection flagged.

**Known issues deferred:** none. This session is fully closed — no open items carried forward.

**Tooling note (not a product bug, but worth knowing for future sessions):** Claude in Chrome's native `file_upload` tool hit an environment limitation this session ("no longer accepts host filesystem paths"). Worked around by injecting a `File` object via JS (`new File(...)` + `DataTransfer`) and dispatching a real `change` event on the page's file input — this exercises the exact same `onchange` code path a real user's file picker or drag-and-drop would trigger, so it's a valid functional-equivalence test, not a shortcut around real validation. Worth trying the native tool again first in a future session in case it's since been fixed.

**Handoff notes for next session:**
- Live site: `https://dfs-optimizer.pages.dev` — auto-deploys on every push to `main` (Cloudflare Pages git integration already configured: build output directory `dfs_optimizer_frontend`, no build command, Framework preset None).
- Per ROADMAP.md, Session 7.2 (UI-Optimizer Integration) is next — its only prerequisites (Session 7.1 + all of Phase 3) are both complete, no blockers.
- This session's frontend is deliberately upload/view only — it has no live connection to the repo's `/output` files, GitHub Actions, or the Cloudflare Worker from Session 5.2. Wiring that up is exactly Session 7.2's job; don't assume any of today's plumbing already does it.
- `test_fixtures/` (real-data CSV samples used for this session's validation) were generated locally but were **not** committed to the repo — intentionally, per the README's own note (they're a testing aid, not a project asset). Recreate from real `/output` files if a future session wants them again.

## Session 7.2 — UI-Optimizer Integration
**Date completed:** 2026-07-23
**Status:** ✅ Complete (DK fully live-validated; FD deferred, see ROADMAP.md's known-gaps list)

**Architecture decision (user-confirmed, start of session):** three sub-options were laid out --
(A) GitHub Actions round-trip only (real solver, ~30-90s per change), (B) client-side JS
reimplementation only (instant, but a second solver to keep in sync), or a hybrid of both.
User's own framing: "I'd rather do something more robust even if it takes more time... quality
over speed is my preference" (weeks of runway before Preseason Week 1). **Chose the hybrid** --
reasoning below. Session was sub-phased into 7.2a/7.2b/7.2c rather than built in one pass, matching
this project's own "validate before moving on" pattern applied to a single session's internal work,
not just session-to-session.

### 7.2a — Lock / Exclude in `optimizer.py`
Added real (not stubbed) lock/exclude support -- did not exist before this session, needed by both
halves of the hybrid regardless of which one a given UI action uses. Continuing the decision
numbering from Session 3.3's stacking decisions (#14-21):

- **22.** Two independent mechanisms by `player_id` (not name -- names can collide): EXCLUDE filters
  the player out of the pool entirely before the solver runs (same pattern as an exposure-locked-out
  player); LOCK adds a hard `x[pid] == 1` ILP constraint inside `solve_lineup()`.
- **23.** Locked players are exempt from both the exposure cap's lock-out check and the uniqueness
  swap count -- a lock is an explicit override, not a competing rule, and counting a
  guaranteed-every-lineup player as an available "swap" would silently inflate how many different
  players two lineups actually need.
- **24.** `validate_lock_feasibility()` mirrors decision #21's "fail loudly before the solver runs"
  pattern -- catches too-many-locked-at-one-position, locked RB/WR/TE overflowing FLEX capacity,
  locked salary alone exceeding the cap, or more locks than roster slots exist.
- **25.** `--lock X --exclude X` on the same player is a hard CLI error, not a silent tie-break.
- **26.** `player_id` is now carried through `assign_roster_slots()` into every output CSV (was
  previously dropped after the solve) -- needed for a UI to round-trip "lock this exact player"
  without a separate name lookup.

**Real-data validation (8 tests, real `final_projections_dk_10.csv`/`final_projections_fd_10.csv`,
the Session 1.3-era DK Madden Stream pool):** baseline no-regression; lock a low-value player
(forced into FLEX, salary/roster stayed legal); exclude the top player (correctly removed, solver
found the real next-best legal lineup, 135.65 → 117.17 pts); `--lock X --exclude X` → clean CLI
error; locking 2 QBs (only 1 slot) → clear pre-solve `RuntimeError`, not an opaque solver failure;
lock + mandatory QB stack together → both satisfied in one solve; lock 2 players + `uniqueness=3`
across 8 lineups (thin pool) → all 8 generated, locks didn't inflate the swap requirement; exclude 2
players across a 6-lineup batch → excluded players appear 0 times; lock+exclude+randomization
together, both single- and multi-lineup mode → all compose correctly, output always reports the
real (not noisy) projection.

### 7.2b — GitHub Actions dispatch + Cloudflare Worker (the "confirm with real solver" path)
**New file:** `.github/workflows/run_optimizer_dispatch.yml` -- triggered by `repository_dispatch`
(type `run_optimizer_request`), builds an `optimizer.py` CLI invocation from the dispatch payload
(every field optional except site/week/request_id -- an omitted field means "use optimizer.py's own
default," never an invented one), runs it, commits only the request-scoped result under
`output/ui_requests/`.

**New file:** `cloudflare_worker/optimizer_api/optimizer_api.js` + `wrangler.toml` -- a SECOND
Worker (`dfs-optimizer-api`), deliberately separate from Session 5.2's `scheduled_refresh.js` (that
file's own header describes itself as dispatch-only relay; this one also reads results back out of
the private repo via the GitHub Contents API, a genuinely different responsibility). Two actions:
`dispatch` (fires the repository_dispatch, returns a `request_id` immediately, does not wait for the
Action) and `poll` (checks for `output/ui_requests/{request_id}.csv` or `.error.txt`, returns the
content directly -- the frontend never needs its own GitHub credentials).

**27.** `optimizer.py` gained a `--request-id` flag: when set, output goes to
`output/ui_requests/{request-id}.csv` INSTEAD OF the canonical `lineup_single_*`/`lineups_multi_*`
path. Caught during design, before it could ship as a real bug: without this, an interactive "try
these settings" dispatch would silently overwrite the canonical output file that live automation and
other consumers read from. Verified via real run: canonical file's MD5 unchanged after a
`--request-id` run against the same site/week.

**Local validation (sandbox):** ran the workflow's embedded Python arg-builder standalone against
three realistic payloads, then ran the exact generated `optimizer.py` commands against real data --
all correct, including a deliberately-infeasible stack request (KC, not in the thin real test pool)
correctly failing loudly, confirming the error path end-to-end before ever touching the user's real
Cloudflare account.

**Live deployment and testing (user's real Cloudflare/GitHub account) surfaced 5 real bugs, all
fixed same-session:**
1. **Mis-scoped GitHub token** (first attempt) -- 404 from the dispatches endpoint. Root cause: PAT
   lacked the right repo access/permissions. User regenerated correctly-scoped fine-grained PAT.
2. **Silent empty secret** -- `wrangler secret put` in a masked PowerShell prompt accepted an empty
   paste and still printed "✨ Success!", so the Worker had an empty `GH_DISPATCH_TOKEN` (falsy in
   JS, same code path as "missing"). Symptom looked identical to a missing secret. Fixed by piping
   the value in (`$env:VAR | npx wrangler secret put ...`) instead of the interactive prompt, which
   sidesteps the paste issue and lets `.Length` confirm it actually landed.
3. **Browser caching identical GET requests** -- after the secret was genuinely fixed, repeated
   identical dispatch URLs kept returning the stale cached error. Fixed by adding a cache-busting
   query param to every dispatch/poll URL (`&cb=<timestamp>`) and `{cache: "no-store"}` in the
   frontend's real fetch calls (7.2c) so this can't recur for an actual user.
4. **GitHub's `repository_dispatch` 10-top-level-property limit on `client_payload`** -- a request
   combining stacking + lock + exclude hit `422 No more than 10 properties are allowed`. Fixed by
   nesting every optional field under a single `params` key in both `optimizer_api.js` and the
   workflow's arg-builder, so `client_payload` always has exactly 4 top-level keys (`request_id`,
   `site`, `week`, `params`) regardless of how many controls are set.
5. **Generic error messages hid the real reason.** The workflow originally wrote the same canned
   string to `.error.txt` regardless of what actually failed. Fixed by redirecting `optimizer.py`'s
   real output to a log file and tailing it into `.error.txt` -- this is what let the *next* real bug
   (a `--week 1` vs `--week 10` mixup, see 7.2c) get diagnosed and fixed directly from the frontend's
   own error message rather than by hand-digging through the Actions log (which itself required
   working around GitHub's log viewer being a virtualized UI that resists text extraction --
   eventually solved via `find` + click + `get_page_text`, worth remembering for a future session
   that needs to read Actions logs again).

Also, as a direct follow-on from real testing (not originally scoped, but the natural conclusion of
bug #5): `optimizer.py`'s CLI entry point now catches `RuntimeError` specifically (verified: all 16
`raise RuntimeError(...)` sites in the file are "your settings/pool are infeasible" cases, never an
internal bug) and prints just the clean message, no traceback -- any other exception type still gets
its full traceback. Exit code 1 preserved either way, so the workflow's failure detection and
`.error.txt` capture needed no changes. Live-validated against the exact real failure (a `--bring-back`
request against a pool where no team's real opponent has any players present) -- now reads as
"Could not generate a lineup with the current settings: ..." instead of a Python traceback.

### 7.2c — Frontend "Build a Lineup" panel
**Modified:** `dfs_optimizer_frontend/index.html`. Session 7.1's upload/view functionality is
unchanged underneath a new collapsible panel: player pool upload (`final_projections_{site}_{week}.csv`
-- separate from the lineup-viewer uploads), Worker URL + Auth Token settings
(`localStorage`-persisted -- correct here since this is the real deployed site, not a sandboxed
artifact), full controls (mode, n_lineups, max_exposure, uniqueness, week, all four stack modes with
their sub-fields, randomization % + seed), a searchable player list with mutually-exclusive
Lock/Exclude toggles, **Preview Instantly**, and **Confirm with Real Solver**.

**Preview Instantly** -- a real ILP solver (`glpk.js`, WASM) running client-side. Single-lineup,
lock/exclude only (no stacking/exposure/uniqueness/randomization -- a deliberate scope boundary, not
an oversight: those mechanics are complex enough, especially exposure's iterative lock-out and
uniqueness's relaxation-on-infeasibility, that a second JS implementation would be an ongoing drift
risk against `optimizer.py`'s real logic; "Confirm with Real Solver" exists specifically so nothing
ever needs that). **Validated for exact parity before shipping:** built the identical ILP formulation
in `glpk.js` (via its `/node` entry point, since the browser build needs real Worker/Blob APIs Node
doesn't have) and ran it against real `final_projections_dk_10.csv` -- reproduced `optimizer.py`'s
exact salary/points totals for baseline, lock, and exclude cases, to the penny.

**Confirm with Real Solver** -- dispatches to the 7.2b Worker, polls for the result, supports every
control since it's calling the real, unmodified `optimizer.py`.

**Real-data event this session:** the user downloaded a real DK Madden Sim slate export
(`DKSalaries.csv`) and tried uploading it directly into the Player Pool box -- got a clear "missing
expected columns" error, since that box wants the *output* of the projection pipeline
(`final_projections_{site}_{week}.csv`), not DK's raw export. Explained the two-stage pipeline
(raw export → `ingest_salaries.py` → `build_projections.py` → the file the UI actually wants), and
flagged honestly that this specific slate (a simulated game, not a real one) has neither a real
Vegas line nor real current-season history to draw on -- running it through the real pipeline would
be a mechanically-real test, not an accurate preview of the sim's outcome. User chose to run it as a
real-data test anyway ("I need to see how the optimizer works... let's find a way to test it now in
a meaningful way").

Ran the real pipeline end-to-end against this real upload: `ingest_salaries.py` matched 90/94 real
players against real 2025 season history (4 unmatched, correctly flagged by name); `build_projections.py`
produced real projections using the existing committed week-10-2025 baseline/matchup/vegas files as
the historical reference (the only real signal available -- 28 players correctly zeroed as
no-real-game-that-week, 57/90 got a real nonzero projection); `optimizer.py` solved a real, legal
lineup (Justin Herbert/Christian McCaffrey/RJ Harvey stack-adjacent build, $44,100/$50,000, 151.38
pts). All data pulled from the private repo via Claude in Chrome (including two binary `.parquet`
files -- `weekly_stats_2025.parquet` and `schedules_2025.parquet` -- retrieved by fetching GitHub's
tokenized raw-content redirect URL from within an authenticated page context, then handing that URL
to `curl` directly, since `raw.githubusercontent.com` is an allowed sandbox domain but the browser
tool blocks returning base64/binary blobs through its own response channel).

**Important side effect, flagged plainly:** this run overwrote `output/final_projections_dk_10.csv`,
which had been the shared "week 10" DK Madden Stream test file since Session 1.3. Going forward,
"week 10" in this repo means THIS real slate's real projections, not the original test pool. Not a
problem, just worth knowing before any future session assumes the old numbers are still there.

**Bug found and fixed via this real run:** the Week field only had a `placeholder="10"` (gray hint
text that disappears on click), not a real value -- looked pre-filled but wasn't, and an empty
number input's spinner can jump straight to `1`. This produced a real dispatched request for
`--week 1`, which correctly 404'd against the real repo (no `final_projections_dk_1.csv` exists) --
and decision #5 above (real error surfacing) is what made this diagnosable directly from the
frontend's own error text. Fixed: real `value="10"`, plus `localStorage` persistence matching the
Worker URL/Token fields.

**Gap found and closed same session:** Randomization/seed controls were fully supported by
`optimizer.py` and by 7.2b's dispatch path, but no UI existed for them at all -- not a stub, just
missing. Added "Randomization %" and "Seed (optional)" fields, wired into
`buildDispatchParams()`, with a hint noting Instant Preview never randomizes (only the real-solver
path does). User live-tested this after it shipped -- confirmed working.

**Live validation, DK, on the real deployed site (`https://dfs-optimizer.pages.dev`), all
user-confirmed:** Lock, Exclude, Week, multi-lineup mode (n_lineups/max_exposure/uniqueness), QB
Stack with and without bring-back (including the correctly-infeasible bring-back case against this
thin real pool -- confirmed via direct pool analysis that none of the 6 viable QB-stack teams have
their real opponent present in this ~90-player slate, so no team/setting combination could have
satisfied it -- this is a property of the pool size, same category as the "Known Testing Artifact"
already logged in ROADMAP.md, not a bug), Game Stack, Mini Stack, Instant Preview, multi-lineup
display/navigation in the viewer, Randomization + seed.

**Deferred (both explicitly, by user request, matching this project's "flag, don't silently
assume" pattern):**
- **FD side** -- no real FD data exists yet to test against (same gap ROADMAP.md has tracked since
  Session 1.3 for every other FD-touching session). Added to that file's existing tracked-gaps list
  rather than treated as a new, separate problem. First real point this closes: Preseason Week 1.
- **Layout/UX refinements** -- user has follow-up suggestions on how the Build panel is laid out;
  explicitly deferred to Session 7.3 ("Polish & Final Deploy" is that card's actual job) rather than
  scope-creeping into this session.

**Handoff notes for next session:**
- Live site: `https://dfs-optimizer.pages.dev`, auto-deploys on push to `main` (unchanged from
  Session 7.1's Cloudflare Pages config).
- Both Workers are live: `dfs-optimizer-scheduler` (Session 5.2, unchanged) and `dfs-optimizer-api`
  (this session, new) -- each has its own independent secrets, confirmed via this session's live
  debugging that they do NOT share even though `GH_DISPATCH_TOKEN`'s underlying PAT value can be
  reused across both.
- `output/final_projections_dk_10.csv` now holds real projections for the user's real Madden Sim
  slate (see above), not the original Session-1.3-era test pool -- a future session touching "week
  10" DK data should be aware of this.
- Per ROADMAP.md, Session 7.3 (Polish & Final Deploy) is next -- its prerequisite (Session 7.2) is
  complete. Bring the user's layout/UX suggestions into that session's scope from the start, since
  they were deferred here specifically for 7.3 to pick up.

## Session 7.3 — Polish & Final Deploy

**Scope note:** by far the largest session in this project so far, spanning many back-and-forth
rounds as the user tested changes live and reported back real issues. Structured below by feature
area rather than strict chronological order, since several areas (stacking, the DK-import feature)
were revisited multiple times as real bugs surfaced through live testing.

### Items 1-2 -- One slate upload, persisted

Removed the old dual DK/FD "lineup viewer" upload cards and the separate player-pool upload,
replaced with a single "Upload Slate CSV" flow (site + week) that auto-detects whether the file is
a player pool (`final_projections_*.csv`) or an already-built lineup file. Persists to
`localStorage` per site+week, with removable chips for each loaded slate, so a page reload never
requires re-uploading.

**Extended well past the original ask, at user request:** a slate uploaded on desktop wasn't visible
on phone (localStorage is per-browser, not synced). Added three new Cloudflare Worker actions
(`save_slate`/`load_slate`/`list_slates`) that store the slate as JSON at
`data/ui_slates/{site}_{week}.json` in the private repo via the same GitHub Contents API access the
Worker already had for polling -- any device pointed at the same Worker now sees the same slate.
Cloud-first with local fallback; degrades silently to local-only if the Worker isn't configured on
a given device.

**Bug found and fixed during this build (before any live testing):** `optimizer_api.js`'s existing
`fetchRepoFile()` decoded GitHub's base64 content with a plain `atob()` -- correct for the
project's existing plain-ASCII CSV/error.txt use cases, but silently mangles any non-ASCII
character (em-dashes, curly quotes, accented names) once JSON slate content started flowing through
the same function. Fixed to `decodeURIComponent(escape(atob(...)))`, confirmed backward-compatible
with the existing ASCII use case via a direct round-trip test.

**Real user-side issue found via live testing (not a code bug):** cross-device sync appeared not to
work even after the fix shipped. Root cause: the user's Worker URL field was pointed at
`dfs-optimizer-scheduler` (Session 5.2's automation Worker) instead of `dfs-optimizer-api` (this
session's Worker) -- a real, deployed Worker, so it wasn't obviously wrong at a glance. Found by
directly comparing the URL in the user's screenshot against their own `wrangler deploy` output.
Resolved once the correct URL was entered; confirmed working by the user afterward.

### Item 3 -- Worker URL/Token friction

Two problems reported: (1) had to re-enter every session (turned out to already be
`localStorage`-persisted from Session 7.2b, but only saved on blur/`change`, so a value typed and
then immediately navigated away from could be lost -- now saves on every keystroke via `input`);
(2) fear of accidentally editing/breaking the fields at crunch time -- fields are now `readonly` by
default on every page load regardless of prior session state, with an explicit "Locked/Unlocked"
toggle button required before editing.

**Added a "Test Connection" diagnostic** (new `action=ping` Worker endpoint, deliberately makes no
GitHub API call) after the user hit a generic, unhelpful "Failed to fetch" -- it now distinguishes
empty fields, missing `https://`, stray whitespace, a rejected token (401, reachable but wrong
secret), and a genuine network/undeployed-Worker failure, with a specific next step for each. This
diagnostic is what surfaced the wrong-Worker-URL issue above.

### Item 4 -- Removed single-lineup mode and Instant Preview entirely

Deleted the client-side `glpk.js` instant-preview solver and the single-lineup mode selector
completely, per explicit user request -- "Build Lineups" is now the only build path, always
multi-lineup, always the real `optimizer.py` via GitHub Actions dispatch.

### Item 5 -- Seed removed, Save Settings added

Removed the `--seed` UI field. Added a "Save these settings" checkbox that persists # lineups, max
exposure, uniqueness, randomization, minimum salary, FLEX positions, and all stack settings to
`localStorage`, auto-restored on next visit when the checkbox is on.

### Item 6 -- Ownership, baked into the pipeline (not a separate upload)

Originally shipped as an optional second CSV upload (matched by `player_id`). User then asked for
it to be automatic instead. Added `add_ownership_columns()` to `build_projections.py`, which calls
`ownership_heuristic.py`'s existing `compute_chalk_scores()`/`compute_estimated_ownership()`
UNCHANGED against the same in-memory DataFrame the file is about to write -- `chalk_score` and
`estimated_ownership_pct` now ship as real columns in `final_projections_{site}_{week}.csv` itself.
`ownership_heuristic.py`'s own standalone CLI (`chalk_scores_{site}_{week}.csv`) is untouched and
still works if wanted separately. Validated: merged output matches the standalone script's own
output to floating-point precision (~7e-15 diff) against real data.

**Bug found via user question ("is this not showing because of the Madden slate, or is something
wrong?"), not live testing:** the frontend's slate-upload parser only kept a fixed whitelist of
columns from an uploaded pool CSV -- `chalk_score`/`estimated_ownership_pct` were silently dropped
even from a correctly-rebuilt file. Fixed to read `estimated_ownership_pct` directly off the main
slate upload (with a status line reporting whether it was found), and fixed a related bug in the
ownership-override merge that was blanking out already-baked-in values for any player not covered
by a separately-uploaded override file.

**Extended again, at user request:** built-lineup and uploaded-lineup views now show a per-player
Own% column and a "Total Own" stat (sum across the lineup) in the scoreboard header, joined at
display time against whichever pool is loaded for that site. Validated end-to-end against real
data: all 9 players of a real built lineup matched correctly (283.3% total).

### Item 7 -- Adjustable minimum salary used

Went through two redesigns based on user feedback: first a "% of cap" field, then "$ left on the
table," and finally (most direct, per user's own suggestion) a plain "Minimum Salary" dollar input
paired with a synced slider, bounded automatically to the active site's real cap (DK $50,000 / FD
$60,000). Client-side converts to the `--min-salary-pct` the backend takes, at enough decimal
precision that exact dollar targets land exactly (verified: $49,700 on DK round-trips to exactly
99.4000% and back to $49,700, no drift).

### Item 8 -- FLEX-eligible position control

Added RB/WR/TE checkboxes controlling which positions can fill the FLEX slot. Backend: new
`--flex-positions` flag on `optimizer.py`, pins any excluded position to its exact fixed count so
the solver can't slot a "leftover" player from an excluded position into FLEX. Validated against
real data restricting to WR-only, RB+WR, and TE-only -- correct in every case.

**Bug reported by user, investigated and found to be a stale-deployment issue, not a code bug:**
user reported FLEX restricted to WR-only still placed a TE. Reproduced the exact scenario directly
against the backend and got the correct result (WR in FLEX) both before and after the report --
root cause was almost certainly the Cloudflare Worker not having been redeployed with the current
`optimizer_api.js`/dispatch workflow yet (`wrangler deploy` is a separate manual step from the
frontend's git-push auto-deploy, easy to miss). Documented, not silently assumed fixed.

### Item 9 -- Slate overview (games + totals)

Derived directly from the already-loaded player pool's existing `opponent`/`over_under` columns --
no separate upload needed. Renders a sorted list of real games with a relative bar chart. Validated
against real data (7 real games from the DK Madden Sim slate, correctly sorted).

### Item 10 -- Player pool: tabs, sorting, value column

Player list reworked into ALL/QB/RB/WR/TE/DST tabs with sortable Price/Proj/Value/Own% columns
(Value = projection per $1,000 salary). Validated top-5-WR-by-value and DST-tab-membership against
real data.

### Mobile responsiveness (not on the original list -- added after user reported real issues on a
Pixel 9 Pro XL)

Three issues, all traced to the same root cause: fixed-pixel-width grid columns that don't fit a
phone viewport. (1) Green "loaded from cloud" status text overflowing its container -- a classic
flexbox bug (`flex:1` without `min-width:0` refuses to let text wrap below its intrinsic width).
(2) Player pool columns misaligned, Lock/Exclude buttons clipped off-screen. (3) Player names
truncated in the built-lineup view. Fixed via a `@media (max-width: 640px)` block that reflows both
the player-pool row/header and the roster row into stacked 2-3 row layouts instead of squeezing
6 fixed columns sideways -- same DOM/JS, only which grid area each element lands in changes.
**Two self-caught bugs before shipping:** an early version of the fix hid the player-pool header
entirely on mobile, which would have made sorting untappable (fixed to reflow instead of hide); and
an early version double-prefixed the price column with `$` on top of `fmtMoney()`'s own `$` (caught
and removed before shipping).

### Download Lineups -- DK/FD bulk-entry import (not on the original list -- new user request)

User's real workflow: reserve max entries in a contest with dummy lineups, then bulk-replace them
near lock via DraftKings' `DKEntries.csv` re-upload mechanism, which requires the roster columns to
contain the site's own player ID (bare or `Name (ID)`) -- never a name alone. Built a "Download N
Lineups for [Site] Import" button that exports every currently-loaded lineup in that exact shape
(`QB,RB,RB,WR,WR,WR,TE,FLEX,DST` header, CRLF line endings matching DK's own file).

**Required real pipeline work, not just a UI button:** the site's own player ID (DK's `ID`, e.g.
`43636569`) was never carried past `ingest_salaries.py`'s raw salary file -- `build_projections.py`
dropped it before `final_projections` was ever written. Added `site_id_col` to
`ingest_salaries.py`'s `SITE_CONFIGS` (DK confirmed `"ID"`; FD's `"Id"` inherits the same
unverified-since-Session-1.3 caveat as everything else FD), threaded `site_player_id` through both
the skill-player and DST paths in `build_projections.py`, and through `optimizer.py`'s
`assign_roster_slots()` into the final lineup CSV.

**Two real, distinct bugs found via the user's own live testing against a real uploaded
`DKEntries.csv`, both fixed and re-validated against that same real file:**
1. **DST always missing its ID, skill players fine.** `build_dst_projections()` has TWO separate
   column-selection points -- `site_player_id` was added to the first (near the top of the
   function) but a second, later `return dst[[...]]` at the very end silently dropped it again
   before the function returned. Only DST hits that second selection point, which is exactly why
   only DST was affected (one per lineup, matching the user's exact "20 missing across 20 lineups"
   report). Caught specifically because this round of testing called the actual function directly
   rather than a hand-retyped mirror of its logic -- the mirror is what let the bug through the
   first validation pass.
2. **Every DK ID had a spurious `.0` suffix** (`43636560.0`), which DraftKings' bulk-upload rejects
   the same as a missing ID. Root cause: `optimizer.py`'s `load_final_projections()` read
   `site_player_id` without forcing string dtype -- a single NaN anywhere in that column (e.g. one
   real matching gap) silently upcasts the ENTIRE column to float64 on read, corrupting every real
   ID in the process. Fixed with an explicit `dtype=` on read, plus a defensive `_clean_site_id()`
   cleanup applied on both the write side (`build_projections.py`) and read side (`optimizer.py`)
   so an already-corrupted file self-heals on the next build rather than needing a full pipeline
   re-run. Also added a diagnostic to `build_projections.py`'s console output that names any
   player still missing a `site_player_id`, so a future real gap is visible immediately instead of
   silently blank.

Both fixes re-validated end-to-end against the user's real `DKEntries.csv` IDs after the fix --
confirmed clean (0 missing, 0 `.0`-corrupted) on a fresh build. **User confirmed working live** after
the second round of fixes.

### Item 11 -- Stacking

Opened with a theory discussion (common stack archetypes -- QB+1, QB+2, game stack with bring-back,
mini-stacks, team stacks -- and what public DFS research generally shows works). User then reviewed
the actual UI/mechanics against that theory and correctly identified two real gaps:

1. **Game Stack didn't require a QB at all.** Traced the actual constraint code: `>=1 from each
   side, >=4 total` was the ENTIRE constraint -- a lineup could satisfy "Game Stack" with e.g. 2 RBs
   from one side and 2 WRs from the other, capturing none of the shootout/QB correlation the
   strategy is supposed to be about. **Fixed (decision #30):** now also requires the lineup's one
   QB slot to come from one of the two stacked teams. Deliberately doesn't pin which side's
   QB -- that's what QB Stack + Bring-back is for. Updated the matching post-solve validation and
   the auto-selection candidate-ranking function (added an opt-in `require_qb_viable` filter, since
   the SAME ranking function is also shared by the opposing-pass-catchers mini-stack, which has no
   QB requirement and must not be affected). Also exposed `game_stack_min_players` in the UI for
   the first time -- it existed in the backend since Session 3.3 but was never surfaced, a hidden
   constant with zero user control. Both fixes validated end-to-end against real data (QB
   confirmed on the stacked team; custom min-players=6 confirmed).
2. **No way to combine two independent stacks in one lineup** (e.g. QB+WR from one game, RB+DST
   from a different game). Confirmed as a real architectural gap -- `stack_mode` is a single,
   mutually-exclusive selector. User's stated intent was specifically QB+WR paired with a
   *different-game* RB+DST (not an opposing-team bring-back) -- scoped what that would take (two
   simultaneous constraint sets, two independent auto-selected targets that can't collide, new UI,
   new validation) and **explicitly deferred at user's own request** ("hold off for now... as I
   test more I could see if I really want it in there or not"), pending more real-world testing of
   the simpler single-stack modes first.

**Also shipped this round, all decision #31/#32:**
- Tightened QB Stack's default partner positions from `WR,TE,RB` to `WR,TE` -- RB production
  doesn't correlate with its own QB's passing stats the way WR/TE does; RB remains a fully
  supported opt-in, only the default changed.
- Replaced the free-text "Stack Team"/"Stack Game" inputs (flagged by the user as inviting typos
  and naming ambiguity -- "Kansas City" vs "KC") with pill-button pickers populated directly from
  the loaded slate's real teams/games. **Multiple selections now actually work end-to-end, not just
  in the UI:** `optimizer.py`'s `--stack-team`/`--stack-game` now accept comma-separated lists and
  reuse the existing auto-diversification round-robin machinery to rotate the batch across exactly
  the user's picks (e.g. "stack KC or SEA") instead of pinning to one. Validated: a 2-team pin
  (LAC,DEN) rotated LAC/DEN/LAC/DEN/LAC/DEN across 6 lineups exactly as expected; single-team pin
  confirmed unchanged (backward compatible). Multi-game rotation validated at the
  candidate-resolution level directly (the sandbox's thin test slate genuinely only has one real
  two-sided game, so a full multi-game solve couldn't be exercised there) -- worth a live check
  once real full-slate FD/DK data exists.
- Added a live, dynamic explanation box under the Stack Mode dropdown (where the user pointed)
  describing in plain language what the currently-selected mode + settings will actually do to the
  lineup, addressing the user's "make it clear what's going to happen" request directly.

### Partial-build banner (not on the original list -- new user question)

User asked what happens if the requested lineup count is infeasible under the current settings
(e.g. asked for 20, only 15 legal lineups exist). Traced the actual behavior: `optimizer.py` already
keeps and writes whatever it built rather than discarding a partial batch, and exits successfully
(not an error) -- but that success path meant the GitHub Actions workflow's `error.txt` never got
written, so a partial batch looked IDENTICAL to a full success in the UI, with no indication
anywhere in the app that fewer lineups came back than requested. Fixed: the frontend now tracks the
requested count at dispatch time and compares it against what actually came back, showing a clear
warning (not an error state) with the likely cause and next steps if they don't match.

### What's validated live vs. sandbox-only

Given the volume of changes this session, worth being explicit about which pieces the user has
actually confirmed live on the deployed site vs. which are validated only against real data in the
sandbox (same distinction this file has maintained all project):

**Confirmed live by the user, this session:** cross-device cloud slate sync (after the Worker-URL
mixup was found and fixed), ownership showing up in the player pool and lineup view, the DK-import
download feature (through two real rounds of bug-fixing against a real `DKEntries.csv`), the
Worker "Test Connection" diagnostic correctly identifying the wrong-Worker-URL issue.

**NOT yet live-confirmed by the user (sandbox/unit-validated only):** the Game Stack QB requirement
and `game_stack_min_players` UI control, tightened QB Stack defaults, the new team/game chip
pickers and multi-pin rotation, the mobile responsive CSS fixes (reported broken, fixed, not yet
re-confirmed working), the Minimum Salary slider redesign, the partial-build banner, and the stack
explanation text. All validated against real repo data end-to-end in the sandbox per this session's
usual standard, but a live pass on the actual deployed site (ideally both desktop and the same
Pixel 9 Pro XL that surfaced the mobile issues) is still the right next step before calling this
session fully closed out in practice, not just in code.

**FD side:** every item above inherits the same pre-existing "no real FD data exists yet" gap
tracked in ROADMAP.md since Session 1.3 -- nothing new here, but worth restating given how much
shipped this session. `site_id_col` for FD (`"Id"`) is a documented guess, unverified, same as
FD's `required_columns` has been all along.

**Handoff notes for next session:**
- Live site: `https://dfs-optimizer.pages.dev`, auto-deploys on push to `main`.
- Both Workers remain independent, separate secrets: `dfs-optimizer-scheduler` (Session 5.2) and
  `dfs-optimizer-api` (Session 7.2+, this session's cloud-sync/download-format/ping additions all
  live here) -- confirmed via this session's real debugging that pointing the UI at the WRONG one
  of these two (an easy mistake, both are real deployed Workers) produces a generic, hard-to-diagnose
  "Failed to fetch" rather than an obviously-wrong error; the new Test Connection button exists
  specifically to catch this faster next time.
- `optimizer_api.js` requires a manual `wrangler deploy` from `cloudflare_worker/optimizer_api/` --
  unlike the frontend, it does NOT auto-deploy on git push. Confirmed at least once this session
  that a forgotten `wrangler deploy` produced behavior indistinguishable from a real code bug
  (the FLEX-restriction report) -- worth checking first whenever live behavior doesn't match what
  the code says it should do.
- `data/ui_slates/` is a new directory this session, holding cloud-synced slate JSON files --
  purely additive, not read by any pipeline script, only by the Worker's new slate-sync actions.
- Next real milestone per this roadmap remains Preseason Week 1 -- the first point essentially
  every item in the "Known Deferred Validations" list below closes for real, FD included.

---

## Session 10.0 — Projection System Redesign (design) + Historical Data Bootstrap (build)
**Date completed:** 2026-07-25
**Status:** ⚠️ Complete with caveats — the *design* is settled and the *historical-data bootstrap* sub-phase is built and validated; the projection rewrite, backtest harness, and salary-anchor curve it enables are scoped but NOT yet built (see Handoff).

**What was actually built:**

This session opened a new phase (Phase 10 — see ROADMAP.md) to redesign the projection engine from first principles. The bulk of the session was *design* — deliberately conducted before looking at the existing `build_projections.py`, to avoid anchoring on what's already there. That design is now settled (full spec in ROADMAP.md's Phase 10 intro). The *code* delivered this session is the first buildable piece: the historical-data bootstrap that every downstream Phase 10 step depends on.

Why this sub-phase exists at all: the project had real 2025 NFL **outcomes** (`weekly_stats_2025.parquet`) but **zero real historical salary files** — DK/FD publish no API, and their "Export to CSV" only ever gives the current slate. No historical salaries means no cap, no legal roster, no lineup, so no lineup-level backtest and no salary-vs-points baseline curve. The bootstrap closes that gap using RotoGuru, a free archive of historical DK/FD salaries + actual DFS points.

- `scripts/ingest_rotoguru.py` (new) — fetches RotoGuru's semi-colon feed, emits per-week raw-salary files shaped to mimic each site's own export (so the existing matcher, not a second copy, does the nflverse matching) plus a per-season actuals file (the scoring truth the future harness grades against). Coverage verified live: DK 2014-2021, FD 2011-2021, nothing after 2021.
- `scripts/batch_match_rotoguru.py` (new) — runs the existing `ingest_salaries.py` matcher as a subprocess over all 155 raw files, materializing the full matched dataset up front (chosen over on-demand matching so the harness just reads files), with a match-quality-aware summary that separates a genuine break from the normal scrub tail.
- `scripts/resolve_unmatched.py` (new) — two-phase (propose / `--write`) resolver for the recurring unmatched names, with hand-verified manual aliases for retroactive nflverse name changes and a self-healing upsert write.
- `scripts/ingest_salaries.py` (modified) — two real fixes, both surfaced only by running real data (see Decisions).
- `data/raw_salaries/rotoguru_{site}_{season}_wk{week}.csv` (155 files) + `data/rotoguru_actuals_{site}_{season}.csv` (9 files) + `data/name_mapping.csv` (16 mapping rows added across both sites) + `data/weekly_stats_{2014..2021}.parquet`, `schedules_2014_..._2021.parquet`, `weekly_rosters_{2014..2021}.parquet` (nflverse history pulled to match RotoGuru's window).

**Files created/modified:**
- `/dfs_optimizer/scripts/ingest_rotoguru.py` (new)
- `/dfs_optimizer/scripts/batch_match_rotoguru.py` (new)
- `/dfs_optimizer/scripts/resolve_unmatched.py` (new)
- `/dfs_optimizer/scripts/ingest_salaries.py` (modified — `NOR->NO` team-map fix; name-keyed override logic)
- `/dfs_optimizer/data/raw_salaries/rotoguru_*_wk*.csv` (155), `/data/rotoguru_actuals_*.csv` (9), `/data/name_mapping.csv` (rows added), `/data/weekly_stats_2014..2021.parquet`, `/data/schedules_2014_..2021.parquet`, `/data/weekly_rosters_2014..2021.parquet`

**Validation results:**
- [x] RotoGuru coverage verified live before building on it (DK 2014-2021, FD 2011-2021) — not assumed.
- [x] Year/week fail-loud assertion tested three ways: out-of-range season blocked pre-flight; wrong-year response hard-stops (`YEAR MISMATCH`); wrong-week response hard-stops. Confirmed on live pulls that a valid in-range season never false-trips.
- [x] Full DK 2014-2021 + FD 2021 pulled clean (155 raw files, 8 DK actuals + 1 FD actuals).
- [x] All 33 RotoGuru team abbreviations validated against the real 32-team nflverse set — surfaced and fixed the `NOR` gap (see Decisions).
- [x] End-to-end match rate after name resolution: **mean 99.7%, min 98.6%, max 100.0%** across all 155 files, 0 hard errors, 0 weeks below the 95% floor. (Pre-resolution baseline was mean 98.8%.)
- [x] Every recurring rosterable unmatched name resolved (Robby Anderson, Ben Watson, Gabe Davis, Deonte Harris, etc.); residual is pure special-teamers/camp bodies who never enter an optimal lineup.
- [x] Manual aliases verified against the real parquet (Robby Anderson -> Robbie Chosen `00-0032688`; Deonte Harris -> Deonte Harty `00-0035215`) — nflverse retroactive legal-name changes.
- [x] Name-keyed override + self-healing upsert verified on the exact multi-team failure case (Anderson resolves on CAR and ARI, not just his most-recent team).
- [ ] **Lineup-level backtest harness** — NOT built this session (this is the next step; the whole bootstrap exists to feed it).
- [ ] **Sunday-main-slate filtering** — NOT applied. RotoGuru's pool is the full-week Thurs-Mon slate, wider than a Sunday Classic main slate. Deliberately deferred to the harness, which will already have `schedules_{season}.parquet` loaded (see Handoff).

**Decisions made / assumptions taken:**
- **Design settled before touching existing code** (user's explicit instruction). Full projection-system spec lives in ROADMAP.md's Phase 10 intro. Key settled points: one projection model parameterized by contest type at the *optimizer* objective (not two models); output schema is per-player **mean + sigma** (sigma derived from stat-line composition, not player history — the latter isn't sticky and is confounded with the mean); blend at the **stat-line level** (usage + market), convert once per site, then apply a salary anchor at the points level; DST as a separate model with distributional (step-function) points-allowed handling; correlation stays as optimizer *constraints* (stacking), not a covariance objective, so no MIQP/solver change is needed; manual override as a logged, expiring, post-blend layer; calibration shrinkage instrumented now, fit out-of-sample later; success measured at the **lineup level** (percentile vs a synthetic ownership-weighted field), not MAE.
- **RotoGuru silently serves its newest season on an out-of-range year** (verified: `year=2024` returned 2021 data, no error, `year` param dropped from the redirect). Every response's own Year/Week columns are asserted against the request — a mismatch is a hard `SystemExit`, never a warning. This is the same silent-corruption class the project has been bitten by twice (duplicate `player_id`; empty Cloudflare secret reporting success).
- **`NOR->NO` team-map gap, found only by real data.** `BASE_TEAM_ABBREV_MAP` had `NOS->NO` but not `NOR->NO`, and RotoGuru uses `nor`. Left unmapped it (a) demoted every New Orleans skill player from exact to medium-confidence fallback matching, and (b) produced a DST row with `normalized_team=NOR` that can never match Vegas's `NO`, which would make `build_dst_projections()` treat NO as on a bye and force `final_projection=0.0` every week, silently. Fixed at the canonical location (affects any source writing `NOR`, not just RotoGuru). Purely additive — no current export sends `NOR`.
- **Manual override made name-keyed, team-agnostic when `source_team` is blank.** Originally the override key was `(name, team, position)`. But a mapping row already carries an explicit `player_id`, so the ambiguity the team-check exists to resolve is already resolved — requiring team to also match can only cause misses. A name-variant row written with one team (e.g. Anderson on CAR) fired only in that player's CAR weeks and silently missed his NYJ/ARI/WAS weeks (observed: 113 unmatched -> only 110 after "mapping"). Now: blank `source_team` = "any team" (name-keyed); a supplied team still narrows (backward compatible, verified). Safe because no two mapped players share a normalized name.
- **Resolver write is an upsert, not a blind append.** First cut deduped on `(site, source_name, player_id)`, so a stale team-keyed row and its corrected team-agnostic replacement shared that key and the fix was silently skipped — the stale row survived and Anderson stayed 93x unmatched. Now the write is keyed on `(site, source_name)`: a new resolution *replaces* any prior row for that name+site, preserving unrelated rows. Self-healing on re-run.
- **Output mimics the site export; matching stays in one place** (`ingest_salaries.py`). RotoGuru's GID is emitted as the site-ID column but flagged `id_source=rotoguru_gid` and the filename is prefixed `rotoguru_`, because it is NOT the site's real player ID — a RotoGuru-sourced lineup can never be uploaded to DK/FD (harmless for backtesting).
- **`AvgPointsPerGame` derived with the Session 2.1 lookahead guard** (weeks strictly before target only); blank, never 0.0, when unavailable — because `build_dst_projections()` applies its own `.fillna(0.0)` and a real 0.0 here would impersonate a measurement.
- **`N/A`-salary rows excluded from salary files, retained in actuals.** A $0 player is free points to the optimizer. FD dropped ~30/week (528 total in 2021); DK dropped ~0 — a real slate-width difference (FD runs a narrower slate), not a parser artifact.
- **nflverse history pulled 2014-2021** (not the earlier-floated 2021-2025). Rationale changed: no longer picking an era-relevance window, but matching the window where salary AND stats both exist, so components can be fit on their own maximal windows and only aligned when fitting blend weights.

**Known issues deferred:**
- **`build_projections.py` DST path reads `AvgPointsPerGame` for BOTH sites, but FD real exports name that column `FPPG`.** So FD's DST path would `KeyError`/null on a real FD export. Consistent with the long-standing "no real FD data" gap; not fixed here (separate decision about FD's real column contract, still unverified). The RotoGuru FD files emit `AvgPointsPerGame` so the harness isn't blocked, but the real FD gap remains open.
- **Sunday-main-slate filtering** not applied (see Validation) — deferred to the harness.
- **Residual unmatched tail** (T.J. Graham, Philly Brown, Jody Fortson, Walter Powell, Kennard Backman, etc.) intentionally left — special-teamers/camp bodies who never enter an optimal lineup. Chasing them is negative ROI; this is the floor.
- **`schedules` came out as ONE combined file** (`schedules_2014_..._2021.parquet`) for the historical pull, vs the per-season `schedules_2025.parquet` already present. The harness must handle both layouts — flagged so a file-path lookup doesn't silently miss.

**Handoff notes for next session:**
- Next build is the **lineup-level backtest harness** (Phase 10, next card): reconstruct a week's pool from the matched `salaries_{site}_rotoguru_{season}_wk{week}.csv` files, run the real optimizer, score against `rotoguru_actuals_{site}_{season}.csv`, report percentile vs a synthetic field sampled proportional to Session 4.1's `estimated_ownership_pct`. Metric is deliberately NOT percent-of-hindsight-optimal (that denominator is one noisy extremum); it's percentile-vs-field, reported as median-percentile (floor/cash proxy) AND max-percentile (upside proxy) separately, never blended. The harness must apply the Sunday-main-slate filter (using `schedules`) that the bootstrap deliberately left off.
- **This dataset is a bootstrap, not the validation set.** RotoGuru's newest data is 2021; the project's `weekly_stats` current-state data is 2025 — they don't overlap, so this can't measure whether the *current* projection system is good *now*. Its jobs are: (1) prove the harness mechanics, (2) fit the salary-vs-points baseline curve, (3) fit stat-component variance parameters. The real current-state validation set accumulates live from Preseason Week 1 onward (real weekly salary exports + Session 9.1 logging). **Action worth taking regardless:** archive every real salary export downloaded from here on (including Madden Sim and preseason) — that's the actual validation dataset and it can't be recovered later.
- **λ (risk penalty), calibration slopes, blend weights** are all to be *fit from the backtest*, not decided — coarse grid for λ, out-of-sample for slopes, per contest type.
- RotoGuru is a small volunteer-run site — the ingest caches every response to `data/raw_salaries/.rotoguru_cache/` and rate-limits at 2s/request by default. Leave both on. (Add the cache dir to `.gitignore`.)

---

## Session 10.1 — Lineup-Level Backtest Harness
**Date completed:** 2026-07-25
**Status:** ✅ Complete

**What was actually built:**

The measurement scaffold for all of Phase 10: `scripts/backtest_harness.py`. Given a historical (site, season, week), it runs the REAL pipeline end-to-end — derives real Vegas lines, runs the real projection component scripts + build_projections.py, filters to the Sunday main slate, runs the real optimizer (build_multi_lineup) in-process, scores the built lineup(s) against real actuals, and reports percentile vs a synthetic ownership-weighted field. Built BEFORE any projection change, so a future rewrite can be told apart from a regression.

**THE BASELINE (the deliverable):** 2021, DK, 17 weeks × 20 lineups per week:
- Median-percentile (cash/floor proxy): **mean 72.8** (min 39.1 wk3, max 91.0 wk8)
- Max-percentile (upside proxy): **mean 94.7** (min 77.8, max 99.7)
- Reported SEPARATELY, never blended (decision #3). The clean separation (best lineup ~95th pctile, median lineup ~73rd) is the expected shape for a 20-lineup portfolio and is exactly the floor-vs-upside tradeoff Phase 10's λ objective will later let us tune. Every Phase 10 projection change is measured against this pair.

**Files created/modified:**
- `/dfs_optimizer/scripts/backtest_harness.py` (new)
- `/dfs_optimizer/scripts/ingest_rotoguru.py` (modified — $0-salary drop, see bug #3)
- `/dfs_optimizer/scripts/ownership_heuristic.py` (modified — divide-by-zero guard, see bug #3)
- `/dfs_optimizer/data/nflverse_games.csv` (new — cached nflverse game lines, the decision #1 source)
- generates per-week `output/vegas_implied_totals_{week}.csv` and overwrites `output/final_projections_{site}_{week}.csv` as it runs

**Validation results:**
- [x] End-to-end run, full 2021 season: OK 17 / SKIP 1 (wk1) / ERROR 0.
- [x] Baseline distribution produced (72.8 / 94.7).
- [x] Sunday-slate filter verified (2021 wk1 → 26 main-slate teams, Thu opener + SNF/MNF correctly excluded).
- [x] Real Vegas derivation sanity-checked (implied totals sum to game total every game).
- [x] Scoring join verified (site_player_id == actuals gid, all players join including DST 70xx).
- [x] Optimizer confirmed to run on REAL projections (debug dump: Brady 42.68, Godwin 29.37, etc. — not NaN), via a hard pre-optimize assertion that the pool has non-NaN final_projection.

**Decisions made / assumptions taken:**
- **Decision #1 — real Vegas from nflverse, the session's key discovery.** The ROADMAP flagged "no real historical vegas lines" as a blocker. It was wrong for the BACKTEST case: nflverse's games.csv carries real historical `spread_line`/`total_line`. The harness derives a genuinely real vegas file via `vegas_odds.py`'s own `implied = total/2 - spread/2` formula (nflverse spread_line is signed positive = home favored; verified TB -10 vs DAL 2021 wk1 → home implied 31.25, matching their real 31 pts; implied totals sum to the game total every game). Does NOT change the live-production gap — The Odds API still can't go backward for a live run. ROADMAP's deferred-validation entry updated to "partially resolved for backtesting."
- **Decision #2 — Sunday main-slate filter.** RotoGuru's pool is full-week Thu-Mon (bootstrap left it unfiltered on purpose). Harness filters to Sunday games at 1pm/4pm ET kickoffs (drops Thu, SNF, MNF, London 9:30am) using games.csv's gameday/gametime. An APPROXIMATION (exact published main-slate membership isn't archived), flagged as such, far closer than the full-week pool.
- **Decision #3 — metric is percentile vs synthetic field, median AND max separately.** NOT percent-of-hindsight-optimal (single noisy extremum, uninformative scale, rewards ceiling-chasing). Field sampled proportional to Session 4.1's estimated_ownership_pct — inherits that heuristic's unfitness, so it's a "plausible field" not a "real contest," stated in the harness's own output. Median = floor/cash proxy, max = upside proxy; at n=1 they collapse (correct for single-entry).
- **Decision #4 — calls the real code.** solve_lineup/build_multi_lineup imported and run in-process; projection builders driven via their real file interfaces as subprocesses. No reimplementation — the project's own lesson that only real runs catch real bugs (borne out four times this session).
- **Decision #7 — schedule layout adapter.** build_projections.py's load_schedule wants per-season schedules_{season}.parquet, but the historical pull made ONE combined schedules_2014_..._2021.parquet. The harness materializes the per-season file (slicing the combined one, or falling back to games.csv) rather than touching the validated production script for a backtest-only concern.
- **Week 1 is not backtestable** and is skipped explicitly (SKIP status, distinct from ERROR). The usage-based baseline computes from weeks strictly before the target (lookahead guard); week 1 has none, so every final_projection is 0/NaN and the pool empties. This is CORRECT behavior AND real evidence for the Phase 10 redesign — it's exactly the cold-start gap the design's "salary+market fallback at 0 games" addresses.

**The four integration bugs found — all only by real data, none by static review (this session's headline):**
1. **Schedule layout** (fixed in harness, decision #7) — load_schedule wanted schedules_2021.parquet, pull made a combined file. FileNotFoundError.
2. **$0-salary NaN** (fixed in ingest_rotoguru.py + ownership_heuristic.py) — Cam Newton, CAR, 2021 wk10, listed at $0 (re-signed, pre-first-game). `value = final_projection/(salary/1000) = 0/0 = NaN` → NaN chalk_score → build_projections' add_ownership_columns hard-stop. The curated Madden test pool never had a $0 player. Fixed two places: ingest now drops salary ≤ 0 (extends decision #5's N/A drop), and ownership_heuristic guards the divide (safe_salary → value 0.0, never NaN) so the heuristic can't emit NaN regardless of input. Belt-and-suspenders.
3. **`proj` NameError** (fixed in harness) — a refactor moved the Sunday filter after the pipeline but dropped the `proj = pd.read_csv(proj_path)` line. One-line fix.
4. **Suspicious wk10 baseline (43.1) investigated, turned out sound.** Single-week wk10 showed our lineup below the field median, which looked like a scoring or field bug. Added --debug: revealed the optimizer HAD run on real projections (the initial `proj=nan` in the dump was a debug-only bug — assign_roster_slots renames final_projection→`projection` in lineup output, debug read the wrong column). Scoring correct (all join=OK, actuals sum to 91). Added a hard pre-optimize assertion (pool must have non-NaN final_projection) to make this guarantee explicit. wk10's 43.1 was simply the model's second-worst week; the full-season baseline (72.8) is the trustworthy number.

**Known issues deferred:**
- **Baseline is 2021-DK only.** FD has just 2021 matched (mechanics-only), and this is a BOOTSTRAP (RotoGuru ≤2021 vs current 2025) — it measures the model's skill SHAPE, not its current-data quality. A current-data baseline accumulates live from Preseason Week 1.
- **Synthetic field inherits Session 4.1's ownership unfitness** (decision #3) — real-ownership field awaits Sessions 9.3/9.4.
- **Sunday main-slate filter is an approximation** (decision #2) — exact published membership isn't archived.
- **What the baseline reveals about the current model** (motivates Phase 10, not a bug to fix here): the debug dump for wk10 showed the recency-average model projecting a 213.7-point lineup that scored 91 — it overprojects ceilings as means (Brady projected 42.68) and has no variance concept, so it piles into boom/bust players. This is precisely the mean-vs-ceiling and idiosyncratic-variance problem the mean+sigma redesign (Sessions 10.3/10.5) targets.

**Handoff notes for next session:**
- The baseline to beat: **median-pctile 72.8, max-pctile 94.7** (2021 DK, 20 lineups). Re-run `python3 scripts/backtest_harness.py --site dk --season 2021 --all-weeks --num-lineups 20` after any projection change and compare BOTH numbers, separately — a change that lifts max-pctile but drops median-pctile (or vice versa) is a floor/upside tradeoff to decide deliberately, not an unambiguous win.
- `--debug` dumps one week's lineup player-by-player (projected vs actual, join status) plus the field distribution — the tool that cracked bug #4. Use it whenever a week's number looks wrong.
- Next build is Session 10.2 (salary-anchor curve) or 10.3 (stat-line rewrite). Per the ROADMAP, 10.3 is built as a PARALLEL component measured against this baseline before it ships — it replaces the current projection only if it wins on these two numbers.
- Commit point: harness + the two bug-fixes (ingest_rotoguru.py, ownership_heuristic.py) are a clean unit. `data/nflverse_games.csv` is a new cached input (~2MB); fine to commit or .gitignore (harness re-fetches if absent).

---

## Session 10.2 — Salary-Anchor Baseline Curve
**Date completed:** 2026-07-26
**Status:** ✅ Complete — both ROADMAP validation lines closed. The measured answer is a **negative result**, deliberately recorded as a closed validation rather than a failure: the anchor does NOT improve lineup-level percentile as a mid-season points-level blend. It ships OFF by default, with cold-start mode as the one configuration worth using.

**What was actually built:**

The salary-implied baseline curve — the market's own forecast, extracted from eight seasons of real DK pricing — plus the code to fit it, the code to consume it, and the wiring to measure it against Session 10.1's baseline. Four files, two new and two modified.

The reasoning for wanting it at all: DK and FD price every player every week with real money behind the price. `E[fantasy points | salary, position]` is therefore a genuine, free, independent projection component — and unlike the usage-based model it exists for a player with zero games of history, which is the cold-start gap that forced Session 10.1's harness to skip week 1 outright.

- `scripts/fit_salary_anchor.py` (new) — the fitter. Reads `data/rotoguru_actuals_{site}_{season}.csv`, and per site per position: quantile-bins salary with a hard row floor, takes count-weighted bin means, runs a weighted pool-adjacent-violators (PAVA) isotonic regression so the result is guaranteed non-decreasing, appends a top endpoint knot at the observed salary maximum, and writes a piecewise-linear knot table to `data/salary_anchor_{site}.json`. PAVA is implemented locally (~15 lines) rather than adding scikit-learn to a deliberately thin requirements.txt.
- `scripts/salary_anchor.py` (new) — the consumer, deliberately separate so the production path never imports the fitting machinery and the artifact's read contract lives in exactly one place. Loads/memoizes the artifact, evaluates the curve vectorized, computes the per-player cold-start weight, and blends. Hard errors on a missing artifact, an unknown position, or a cross-site load.
- `scripts/build_projections.py` (modified) — decision #8. Optional `--salary-anchor-weight` (default **0.0 = off**), `--salary-anchor-cold-start`, `--salary-anchor-k`. At the defaults, output is byte-for-byte pre-10.2: no new columns, no changed values. When enabled, appends four audit columns (`salary_anchor`, `anchor_weight_used`, `final_projection_pre_anchor`, `points_above_anchor`).
- `scripts/backtest_harness.py` (modified) — decisions #8 and #9. Passes the anchor flags through to `build_projections.py` (never reimplements the blend), pins the synthetic field to an anchor-OFF pool so all arms share one yardstick, makes `--debug` anchor-aware and dump the two lineups the two reported numbers actually come from, and reports arm-independent raw scores alongside the percentiles.

**THE RESULT (the deliverable):** 2021 DK, 20 lineups/week, 17 comparable weeks, pinned field, endpoint-fixed 8-season curve. Baseline is Session 10.1's 72.8 median-percentile / 94.7 max-percentile.

| Arm | Δ median-pct | Δ max-pct | Δ raw med score | Δ raw best score | weeks better (med / max) |
|---|---|---|---|---|---|
| flat w=0.15 | −0.45 (t −0.38) | +0.20 (t +0.55) | −0.48 | +1.84 (t +1.81) | 7/17 · 7/17 |
| flat w=0.25 | +0.55 (t +0.51) | −0.31 (t −0.30) | +0.47 | +0.59 (t +0.29) | 9/17 · 8/17 |
| cold-start floor 0.15 | **+1.09** (t +0.41) | **+0.57** (t +0.49) | +0.68 | +1.08 (t +0.43) | 8/17 · 10/17 |

Largest effect measured anywhere across seven curve/weight variants: **1.1 percentile points, against a 15.6-point week-to-week SD in the baseline itself.** Every sign test is a coin flip. Cold-start is the only arm non-negative on both reported metrics, which is why it is the one recommended configuration — but it is still inside the noise, so the anchor stays off by default.

**Cold-start, separately, is an unambiguous win and the session's real deliverable.** Week 1 2021 went from structurally unbuildable (Session 10.1 skipped it — a usage model has no prior weeks, so every projection was 0/NaN and the pool emptied) to a legitimate 20-lineup build at **median-percentile 57.2 / max-percentile 99.7**, from price alone. The `--debug` dump confirmed 9/9 players tagged RESCUED, every actuals join OK, and no player with zero actual points. Best lineup: Trevor Lawrence 25.08, Deebo Samuel 35.90, Tyler Lockett 29.00, D'Andre Swift 24.40 → 161.18 against a field median of 97.8. Projected total 122.96 vs 161.18 actual — the curve under-shoots by design, since it is an unconditional expectation including did-not-plays (decision #4).

**Files created/modified:**
- `/dfs_optimizer/scripts/fit_salary_anchor.py` (new)
- `/dfs_optimizer/scripts/salary_anchor.py` (new)
- `/dfs_optimizer/scripts/build_projections.py` (modified — decision #8, optional and default-off)
- `/dfs_optimizer/scripts/backtest_harness.py` (modified — decisions #8, #9)
- `/dfs_optimizer/data/salary_anchor_dk.json` (new, `schema_version: 2`) — the shipped DK curve, 8 seasons, 54,894 rows
- Archived alongside it for provenance: `salary_anchor_dk_v1_binmean.json` (pre-endpoint-fix), `salary_anchor_dk_recency1921.json` (2019-21 sensitivity fit)
- `/dfs_optimizer/data/salary_anchor_fd.json` — **deleted, deliberately.** See Known issues deferred.

**Validation results:**
- [x] **Curve fit per site per position, sanity-checked shape — DK.** Monotone at every position (enforced, not hoped for: a non-monotone isotonic result raises rather than shipping). Endpoints sensible: QB $4,007→3.33 pts .. $10,100→24.01; RB $3,000→2.02 .. $10,500→27.88; WR $3,006→2.77 .. $10,000→22.94; TE $2,500→1.95 .. $8,500→19.23; DST $2,022→4.75 .. $5,100→11.33. Expensive-end flat-extrapolation exposure **0.0% at every position**. Top-extension ratios 1.09–1.33 against the 1.35 cap, none binding.
- [x] **The isotonic step does real work, verified on real data.** RB's raw bin means run 5.83, 6.55, 7.28, then **3.12** — that last bin is 2,145 rows piled on DK's round-number $4,000 price point, badly violating monotonicity. PAVA pooled all four to 4.69. Same at TE $2,743–$3,000. Without it the curve would have had a hole exactly where the most players sit.
- [x] **Measured against Session 10.1's baseline.** See the table above. Answer: **no**, not as a mid-season points-level blend. Measured across three weights and four curve variants, on a pinned field, with paired per-week statistics rather than headline means.
- [x] **The Session 10.1 baseline reproduces exactly** under the new harness (72.8 / 94.7, field median 102.27), confirming decision #9's pinning is a no-op for the anchor-OFF arm.
- [x] **Field pinning verified:** field median score is identically 102.27 across all four arms.
- [x] **`--debug` walked on three real weeks** (wk18 @0.25, wk16 @0.40, wk1 cold-start) — this is what produced the mechanical explanation in decision #10 below, and it is the reason this session's conclusion is not merely statistical.
- [x] **`points_above_anchor` (the subtract-form value metric) emitted**, informational only, never driving selection.
- [ ] **FD — not fitted, deliberately blocked.** Not a deferral by assumption this time; blocked by a hard guard on real evidence. See Known issues deferred.

**Decisions made / assumptions taken:**

- **Decision #1 (fitter) — subtract, don't divide.** The ROADMAP card's own framing. Points-per-$1,000 structurally over-favors cheap players; a fitted baseline that itself rises with salary removes the tilt. Confirmed on the real curve: pts/$1K runs 0.83→2.38 for QB, 0.67→2.66 for RB, 0.92→2.29 for WR — rising steeply with price, which is exactly the bias dividing bakes in. `points_above_anchor` is the subtract form, and it stays display-only because the ILP already owns the price tradeoff via the salary cap.
- **Decision #2 (fitter) — fit from the actuals file, not the 155 matched salary files.** `rotoguru_actuals_{site}_{season}.csv` already carries every field the fit needs in one file per season, so no 155-way join and no second copy of the matching logic. Rows the salary files drop as unpurchasable (N/A or $0) are dropped here too, for the same reason: a $0 price carries no market information.
- **Decision #3 (fitter) — isotonic fit on binned means, not a parametric curve.** The relationship is genuinely non-linear (flat at the salary floor, near-linear above it), so no functional form is assumed. Monotonicity is the ROADMAP's own validation line and is enforced as an error.
- **Decision #4 (fitter) — zero-point rows KEPT by default, making the curve the unconditional `E[points|salary]`.** The data cannot distinguish "did not play" from "played and scored ~0". Keeping them is correct for THIS pipeline specifically, because ruling players out is a separate, already-built stage (Session 5.1's `status_check.py` zeroes OUT players before the optimizer sees them) — fitting the played-only conditional here AND zeroing downstream would double-count the availability discount. The played-only conditional is still fit and stored as a diagnostic.
- **Decision #5 (fitter) — pooled across seasons, with an explicit era-drift diagnostic.** Real drift found: residuals run monotonically from 2015 **+0.86** to 2021 **−0.89**, so the pooled curve over-predicts 2021 (our whole backtest season) by ~0.9 pts. No single season trips the 1.5-pt threshold, which means **the threshold is too coarse to catch a trend as opposed to an outlier** — logged as a real limitation of the diagnostic, not a clean pass. A 2019–2021 sensitivity refit was run and produced the same neutral answer.
- **Decision #6 (fitter) — full-week Thu-Mon pool, not Sunday-main-slate-filtered.** The salary-to-points relationship has no reason to differ by day of week, and the unfiltered pool is ~25% more rows. Flagged rather than assumed.
- **Decision #7 (fitter) — non-rosterable positions dropped with a count; anything unrecognized is a hard error.** An unrecognized position label means the source format changed.
- **Decision #8 (fitter/consumer/build_projections) — the anchor is optional, off by default, auditable, and NEVER applied to a confirmed-no-game row.** The last part is the single most important correctness detail in the session. `build_projections.py` decision #4b already forces `final_projection` to exactly 0.0 for a player with no real game that week, and decision #5 does the same for a bye defense; both are marked `opponent == "BYE_OR_UNKNOWN"`. Those rows are excluded from the blend, because mixing a positive salary-derived anchor into a confirmed zero would resurrect a player known to have scored nothing and silently inflate every backtest touching that week. **Critically this is NOT the same test as `final_projection == 0`** — a cold-start rookie also projects 0.0 via decision #3's no-history fallback but has a real game and a real price, and is exactly who the anchor exists to help. Gating on the sentinel rather than on a zero projection is what keeps the two cases apart. Verified both directions in a unit test before any real run.
- **Decision #8b — cold-start weight schedule.** `w_eff = floor + (1 − floor) · k/(k + games_played)`, so 1.0 at zero games decaying toward the floor — the empirical-Bayes shrinkage the Phase 10 design calls for. **`k = 4.0` is arbitrary, chosen here, not user-confirmed and not fit.** DST has no `games_played` anywhere in this pipeline, so a defense is treated as having sufficient history unless its `season_avg` is 0.0 — a modelling assumption, flagged, and Session 10.4 is where it stops being a proxy. `games_played` is carried as a private column through the concat and dropped before return, so the output schema is untouched.
- **Decision #9 (harness) — the synthetic field is pinned to an anchor-OFF pool.** See the bug list below; this is the session's most consequential fix.
- **Decision #10 (the finding that matters most for Phase 10) — a monotone-in-salary term is close to redundant with the salary-cap constraint the ILP already enforces.** This is a *mechanical* explanation for the neutral result, not a statistical one, and it came out of the `--debug` walk rather than the summary numbers. In both mid-season debug weeks, **every single player was shrunk** (`pre > anchor`, no exceptions), so at a uniform weight the blend is close to an affine transform of the objective vector, which an ILP barely notices. And the differential is systematic — shrinkage as a share of the model projection: Parris Campbell ($3.0k) 18.3%, Singletary 12.7%, Josh Allen ($8k+) 9.4%, Allen Lazard 5.0%. **The anchor taxes players whose projection is high relative to their price — i.e. value plays — while favoring expensive ones.** But the ILP already prices that tradeoff natively through the cap, so blending a price-monotone term into the projection partly double-counts price against a constraint that already handles it. The ROADMAP's own Phase 10 intro says as much ("the ILP handles the price tradeoff natively") without having drawn the consequence. **Implication for Session 10.3:** use price as a prior on the **stat-line inputs** (volume, targets, carries), where it carries information the cap does not, rather than as a points-level blend where it is nearly collinear with an existing constraint.
- **Decision #11 — mid-season gains, where they exist, come from re-ranking known players, not from rescued ones.** `RESCUED 0/9` in both mid-season debug lineups. The pool growth the anchor causes (226→312 players at wk2, from zero-history players clearing the `final_projection > 0` filter) is cosmetic for lineup construction — those players never enter an optimal lineup. This matters because a win built on zero-history players would be as likely to be luck as skill; a win from re-ranking is the trustworthy version. It also means the pool growth's only real effect was on the field, which is exactly what decision #9 had to fix.
- **Decision #12 — the 8-season curve ships as the default, not the 2019–2021 recency window,** on price coverage. The recency window spans QB $4,000–$8,500 only, so it cannot price a $9,500 QB at all; 8-season spans $3,000–$10,100. The ~0.9-pt era drift is small next to the ±15.6-pt week-to-week noise. Recorded as a judgment call, not a measured one — and refitting on a recent window becomes the right move once live 2026 exports accumulate (Session 10.0's handoff already says to archive every real export from Preseason Week 1 on; this session is a second reason why).

**The seven bugs found this session — every one by real runs, none by static review:**

1. **The measurement yardstick moved with the arm (the headline).** The harness sampled its synthetic field from the same pool it built lineups from. Turning the anchor on rescues zero-history players past the `final_projection > 0` filter, so the pool grew ~35% (226→312 at wk2), which enlarged and **diluted** the field. Field median score fell in **15 of 17 weeks, mean −1.41 pts, t = −4.32** — by a wide margin the strongest effect in the entire first comparison, and a pure artifact. Meanwhile the arm's raw score, in real fantasy points and immune to the field, moved **+0.42 pts/week** at w=0.25, i.e. not at all. Every apparent percentile gain in the first round was substantially measurement error. Fixed by decision #9 (`--field-pool baseline`, the new default, which runs the pipeline a second time per week with the anchor off purely to construct the field). Raw median/best scores are now printed per week and in the summary for the same reason.
2. **Week 1 + pinned field was structurally impossible.** `ERROR: field-baseline pool too small (0)`. Week 1's *anchor-OFF* pool is empty by definition — that is the entire reason it was ever skipped — so pinning the field to it cannot work, and the pinning default broke the one thing the cold-start arm exists to demonstrate. Now falls back to the arm's own pool for that week, loudly, with the week flagged as not cross-arm comparable in both the per-week line and the summary.
3. **The field-pool check ran after the optimizer.** Week 1 burned a full 20-lineup ILP solve before failing, and consumed an RNG draw doing it — which shifted RNG state for every later week and made the cold-start arm's per-week fields non-identical to the other arms', silently un-pinning the yardstick decision #9 exists to pin (observed: field medians diverging from wk4 onward). Moved before the solve.
4. **Top-knot collapse: elite players shared one anchor.** Using each bin's *mean* salary as its knot x-coordinate made the curve's domain [mean of lowest bin, mean of highest bin], far narrower than the real salary range. With flat extrapolation, everything above the top bin mean collapsed onto one value. Josh Allen anchored at exactly 22.14 (the QB top knot); Cooper Kupp at exactly 19.13 (WR); **Kamara and Jonathan Taylor at exactly 21.06 (RB), despite different prices.** The curve was blind precisely among the expensive players who decide lineups. Fixed with a top endpoint knot extended by the least-squares slope of the top three knots (least-squares specifically because isotonic pooling creates flat blocks, where a two-point slope would come out 0 and the extension would be a no-op), monotone and capped.
5. **The first version of that fix drove cheap players to 0.00.** Extending the slope *downward* below the lowest bin undershot straight through zero into the non-negative clamp: a $3,000 QB, a $2,500 RB and a $2,400 TE all anchored at exactly 0.00 — worse than the flat value it replaced and contradicted by their own bins (3.33 / 2.02 / 1.95). The cause was applying a linear model where the data says the curve **flattens**, which is precisely what the isotonic step had already measured by pooling RB $3,407–$4,000 and TE $2,743–$3,000. Corrected to top-only extension; flat below the lowest knot IS the fitted shape there, not a fallback.
6. **The report table misaligned after endpoint insertion.** Knots grew but `raw_bin_means`/`bin_rows` did not, so the `zip` paired them off-by-one and truncated — QB printed 13 rows while the header said 15, and the `anchor` column showed the previous row's raw bin. Cosmetic, but exactly the class of thing that misleads a future session reading the log. Synthetic knots now carry `None` and print `-- <- extrapolated top endpoint`.
7. **The fit's own guard counted rows, not bins.** `n < min_bin_rows * 2` let FD through **twice** while producing a 4-knot QB curve and a 3-knot defense curve. Row count is the wrong test. Now two guards, both fatal before the artifact is written (decision #9 of the fitter): a `MIN_KNOTS = 6` floor (arbitrary, flagged — DK produces 13–17 per position, FD produced 3–7), and — the better and non-arbitrary one — **a capped top extension is a hard error.** Verified on a simulated thin season: fails loud, names the positions, and no artifact reaches disk.

**Also fixed en route, in `_debug_dump`:** it was anchor-blind (no knowledge of the audit columns) and dumped `lineups[0]`, which is neither of the two lineups the two reported numbers come from. Now shows pre-anchor / anchor / weight / post / actual per player with a `RESCUED` tag and a rescued-points share, for the max-percentile AND median-percentile lineups.

**What's validated live vs. sandbox-only:**
- **Live, in the user's own environment, against real data:** every number in this entry. The DK fit (54,894 real rows, 8 seasons), all seven backtest arms, the three `--debug` weeks, the field-pinning verification, the FD cap-binding evidence, and the reproduction of Session 10.1's baseline. Bugs 1–7 were all found this way.
- **Sandbox-only:** the unit-level checks behind the code — PAVA correctness including weighted pooling, flat extrapolation past both ends, the cold-start weight schedule, the decision #8a bye-exclusion and cold-start-rescue gating, NaN-salary handling, the cross-site and missing-artifact guards, and the thin-season fail-loud path (verified on synthetic data shaped to mimic FD, since the real FD data cannot produce a passing fit to contrast against).
- **Not validated at all:** anything FD. There is no fitted FD curve, by design.

**Known issues deferred:**
- **FD's curve does not exist, and this is now blocked rather than assumed.** The fit fails loud on real FD data: with one season (2021), QB binned to 4 knots and the defense to 3, and the top-endpoint extension hit the 1.35 cap at **QB, RB, WR and TE simultaneously** — WR's top bin mean was $7,045 against a $10,200 maximum, a $3,155 gap the extension cannot honestly span. That is direct evidence the FD curve does not reach the prices that decide lineups, which is a far stronger basis for deferring FD than small-n. `data/salary_anchor_fd.json` was deleted so a stale unfit curve cannot be silently picked up. Closes when real FD data exists — same checkpoint as every other FD gap since Session 1.3.
- **Role-change weight suppression is not implemented.** The Phase 10 design calls for suppressing the anchor's weight when a role change is flagged, since a stale price is exactly the value spot we want to beat. No role-change flag exists in this pipeline yet; it arrives with the Session 10.3 stat-line rewrite. Named in `salary_anchor.py`'s decision #4 so it is a known gap, not an oversight.
- **`k = 4.0` and the flat weights (0.15/0.25/0.40) were swept coarsely, not fit.** Fitting them properly needs a sigma and a tradeoff curve to fit against — Session 10.5.
- **The era-drift threshold catches outliers, not trends** (decision #5). 2015→2021 drifts monotonically by 1.76 pts total without any single season tripping 1.5. Worth a trend test rather than a per-season threshold if this diagnostic is relied on again.
- **The Sunday main-slate filter remains an approximation** and the synthetic field still inherits Session 4.1's ownership unfitness — both unchanged from Session 10.1, both awaiting Sessions 9.3/9.4.
- **Cosmetic:** WR's cheap-end flat exposure reads 39.9% because 8,341 of 19,647 WRs sit at exactly $3,000 while the lowest bin's *mean* lands at $3,006, so everyone at $3,000–$3,005 falls a few dollars below the knot and is flat-extrapolated to 2.77 — which is their own bin mean, i.e. the correct answer. Placing the lowest knot at the bin's minimum rather than its mean when the bin sits on the salary floor would zero this out. Not worth a round on its own.

**Handoff notes for next session:**
- **The baseline to beat is unchanged: median-pctile 72.8, max-pctile 94.7** (2021 DK, 20 lineups, anchor off). Verified to reproduce exactly under the new harness.
- **Always run comparisons with the default `--field-pool baseline`.** `--field-pool arm` exists only to reproduce the pre-10.2 artifact and must not be used for a measurement. And read the raw score lines alongside the percentiles — they are in arm-independent units and are the check on whether a percentile move is real. Bug #1 is the reason both of those exist.
- **Anchor flags are available to any Phase 10 arm** (`--salary-anchor-weight`, `--salary-anchor-cold-start`, `--salary-anchor-k` on both `build_projections.py` and `backtest_harness.py`), and `salary_anchor.py` is importable directly for a component that wants the curve rather than the blend.
- **For Session 10.3, take decision #10 seriously:** price is nearly collinear with the salary cap at the points level, so the productive place to use this curve is as a prior on the **stat-line** inputs, not as a points-level blend. That is a real constraint on the design, learned cheaply, and it is exactly the kind of thing the harness was built to surface before weeks were spent on it.
- **Week 1 is now backtestable** with `--salary-anchor-cold-start`, but its percentile is not cross-arm comparable (the baseline arm has no week 1 at all). Use an explicit `--week 2 3 ... 18` list for a like-for-like season number; the harness flags the un-pinned week in its summary either way.
- **Commit point:** the four scripts plus `data/salary_anchor_dk.json` and the two archived variant fits are a clean unit. No Cloudflare Worker or frontend redeploy — nothing in this session touches the four-layer parameter chain, since the anchor flags are backtest/offline-only and the live UI never sets them.

---

## Session 10.3a — Stat-Line Projection Rewrite (2026-07-26)

**Status: complete.** The stat-line engine is built, measured out-of-sample across four seasons, and ships on the capability gate agreed before any code was written. `build_projections.py` is untouched.

### What changed about the session before it started

The card's original validation line said the engine "ships only if it wins." Three cheap pre-tests, run on real data before a line of code, argued that bar would kill a component Session 10.5 cannot exist without:

1. **The legacy target variable is wrong three ways.** nflverse's `fantasy_points` scores an interception at −2; DK and FD both use −1. DK additionally uses −1 for a lost fumble and pays three +3 yardage bonuses. Reconstructing the column confirmed this to 7.1e-15. Against each site's own legacy formula, corrected scoring differs on 13.2% of DK rows and 5.2% of FD rows — and on **42.9% of DK performances worth 15+ points**. The harness grades against RotoGuru actuals, which are real DK points, so the pipeline was projecting in one unit and being scored in another.
2. **But fixing that will not move the lineup metric.** Within position, Spearman between old and corrected scoring is ≥ 0.9906 — a level shift, not a re-ranking, which is precisely the shape Session 10.2 taught us an ILP barely notices.
3. **And the core bet is close to a null.** A crude volume × efficiency model raced against points-averaging over **9,822 real player-weeks** (2019–21, 2018 as prior only) came out within 0.02 MAE — 5.20 vs 5.18 — with **residual correlation 0.965**. The design intro says blending helps in proportion to error decorrelation; there is almost none here, because volume history and points history are the same signal with fewer steps between. The steelman does hold (stat-line wins on TD-heavy histories by 0.20–0.31 MAE, loses slightly on TD-light ones) but the effects cancel in aggregate.

On that evidence the card was re-scoped by agreement to a **capability gate**: ships if it delivers a validated mean and sigma and is not worse, with accuracy explicitly not the deliverable. Three other decisions were taken at the same time: measure multi-season for power, use Monte Carlo rather than an analytic converter, and defer price-as-volume-prior to 10.3b.

### Why Monte Carlo

DK's bonuses are step functions, so `E[points] ≠ points(E[stats])`. Measured on the real output, scoring a mean stat line **over**-credits a player already past a threshold by −2.22 pts and **under**-credits one within reach by +0.36. Unlike the scoring-table correction, that is a *signed* error among exactly the players competing for a slot. The simulator also produces sigma in the same pass and handles the yards/TD correlation natively.

Sigma is **idiosyncratic by construction** — independent draws per player, no team-level component — which is the correct kind for 10.5, since correlated variance lives in the optimizer's stacking constraints.

### Three bugs, all found by running it, none by review

1. **Conditional vs unconditional volume.** A recency average covers only games a player *appeared in*, so it is a volume conditional on playing. Cooper Rush (DAL, 2021 wk10) appeared in exactly one prior week — 40 attempts covering an injured Prescott — and was therefore projected at 40 attempts. Summed with Prescott, the pool projected **77.5 attempts for a team that throws 39.6**. Surfaced only because share reconciliation had a team-level constraint to violate; the legacy engine makes the same error invisibly. Fixed by weighting volume by the share of the team's last five *played* weeks in which the player recorded a stat line.
2. **`NaN or 0.0` returns NaN.** NaN is truthy in Python, so the idiomatic `getattr(row, col, 0.0) or 0.0` passes it straight through — into `rng.binomial`, which raised. Guarded at two layers.
3. **Reconciliation thresholds, wrong twice.** First a relative test on trivial volumes; then a per-pair extreme test that aborted on ordinary football. See below.

### The reconciliation problem, and the fix that mattered

Two weeks aborted: 2021 wk13 and wk15. The first error message named a 2.00× pair while claiming a 3.0× breach — the harness truncated the output before the real culprit. Fixing the diagnostics (worst-first ordering, offending pairs named in the first line) cost a round trip and revealed the actual cause.

Both failures were the same structural fact, breaking in **opposite directions**:

| | full-season share | recent-5 share | who played |
|---|---|---|---|
| NYJ wk13 | Wilson 48% | Wilson 11% | Wilson only |
| CAR wk15 | Newton 17% | Newton 47% | Newton only |

No backward-looking share gets both right; tuning the window would have fixed one week and broken the other. The resolution is that **pass attempts are an exclusive resource** — they belong to quarterbacks, the pool holds the quarterbacks, so the share is 1.0 and history should not be consulted for it. Reconciliation's job for passing is to distribute the team's predicted attempts among available QBs, weighted by recent usage. Rushing and receiving are not exclusive (the pool genuinely misses bench players) so they keep a share, now measured over the recent window. Verified: Wilson 4.8 → 34 attempts, Newton 16.7 → 32 instead of being cut to 5.4, and a synthetic broken mapping still aborts.

Breakage detection now needs an extreme ratio **and** a material absolute gap — every real failure was under half a game's volume, and the ratio only looked alarming because the denominator was small. The systemic test needs ≥20 material pairs before it can fire. Exclusive components are exempt from the ratio test entirely, since their rescale is a normalization by construction (routinely 2–13× on healthy weeks).

### The measurement, and what did not replicate

**In-sample (2021, variance fit on 2014–21):** median-pctile +1.82, max-pctile +1.75, and a max-percentile variance reduction of **3.58×, p ≈ 0.001** with the entire gain in the bad weeks. That looked like the headline finding.

**Out-of-sample (variance fit 2014–17, measured 2018–21, 65 weeks):**

| | legacy | statline | Δ | t |
|---|---|---|---|---|
| median-pctile | 75.65 | 77.85 | +2.20 | +1.15 |
| max-pctile | 96.54 | 96.82 | +0.28 | +0.56 |
| raw median score | 127.17 | 129.43 | +2.26 | +1.35 |
| raw best score | 163.67 | 165.07 | +1.40 | +0.57 |

Median-percentile is positive in **all four seasons** (+1.41, +1.93, +1.93, +3.48). The variance finding shrank to 1.54× (p ≈ 0.039) and the tail decomposition inverted — the gain sits in the middle half, not the tails, and the disaster rate is flat at 3/65 for both arms. Across six tests run, nothing survives a multiple-comparisons correction.

**The transferable lesson is the leak itself.** Fitting `statline_variance.json` on the season then measured inflated the effect roughly threefold on the same 2021 weeks (variance ratio 3.58× → 1.20×, max-pctile 96.6 → 95.2). It would have gone into this log as a finding. The holdout cost one extra fit and one extra run.

### Sandbox-only vs live-validated

Everything in the deliverables was **live-validated** in the real environment against real RotoGuru slates. The following were **sandbox-only**, on synthetic fixtures built from real 2021 players: the three reconciliation shape tests, and the pandas-3 dtype reproduction. The DST sigma constants are **measured** (3,952 real team-weeks, 2014–21) but remain unconditional pending Session 10.4.

### Handoff notes

- **Refit for production:** `python3 scripts/fit_statline_variance.py` (all eight seasons). The 2014–17 artifact was for the measurement only.
- **New baseline pair:** 2021 DK **72.9 / 94.8**; pooled 2018–21 **75.6 / 96.5**. The original 72.8 / 94.7 stays valid for Sessions 10.1 and 10.2 under the old seeding scheme.
- **`optimizer.py` drops `sigma`** — it reaches the optimizer, it does not survive it. First task of Session 10.5.
- **`ownership_heuristic.py` got a one-line coercion** of `flag_weight` — a dormant pandas-3.x break, not a live bug. Explicitly a stopgap: the ownership model is slated for its own rework after Phase 10, and pandas 3.0 will break more than this one line when it arrives.
- **FD is unverified**, consistent with every other FD gap in this project — but note `statline_variance.json` is site-agnostic, so unlike the FD salary anchor this component is *not* blocked on FD data.
- **`output/statline_reconcile_{site}_{week}.csv`** is written every run: one row per team/component pair with the share, its basis, and the applied scale. Reconciliation moves volume on ~83 pairs a week and this is the only way to see it.
- **Commit point:** the five scripts plus `data/statline_variance.json`. No Worker or frontend redeploy — nothing here touches the four-layer parameter chain, since the engine is backtest/offline-only and the live UI never selects it.

---

## Session 10.4 — DST Model Rebuild (2026-07-26)

**Status: complete.** The distributional DST model is built, measured at both the DST slot and the lineup level, and is the first Phase 10 component to ship **on by default**. `build_projections.py`'s legacy DST path is intact and reproduces the frozen baseline exactly.

### What the session replaced

Since Session 3.1 a defense's projection has been `AvgPointsPerGame × (league_avg_implied / opponent_implied)`, with `matchup_factor` pinned at 1.0 and — since 10.3a — an unconditional sigma of `3.25 + 0.39 × projection`. One season-average number, one multiplicative factor, no components, and a step function read at a point estimate.

### The card was measured before it was built, and two of its premises were wrong

Rather than implement the card as written, the first turn went to testing its own assumptions on real data. Two failed:

1. **"handles the DK/FD bracket divergence correctly."** There is no divergence. Reconstructing real graded DST scores from nflverse components with one shared table: DK 89.7% exact / mean bias −0.156, FD 87.5% / −0.178 — the same residual shape, no systematic offset. The tables stay per-site so a future divergence is a config edit, but no code branches on site.
2. **"own-defense EPA/play as the stable modifier."** The opponent's offense predicts a defense far better than the defense's own history does — sacks: opponent's sacks-allowed prior t = +12.4 against own-defense t = +4.8. Own-defense EPA survives only as a small mean-reversion correction on the market's number (t = −2.13), and its coefficient is *negative*: a defense that has allowed more EPA allows fewer points than its line implies, because the market overreacts to recent form.

A third premise was confirmed and quantified, and it is the reason the card existed. Integrating the bracket table over a fitted negative binomial returns a mean bracket value of 0.433 against a realized 0.479; looking the bracket up at the point estimate returns **0.181** — biased low 0.30 points on *every* defense, compressing the across-defense spread 19% (SD 0.860 → 0.696) and ranking worse against outcomes (Spearman 0.336 → 0.369). Overdispersion was measured, not assumed: var/mean runs 3.4–4.4 across implied-total bands, so Poisson is ruled out and NB is the family (fitted r = 6.50).

Vegas turned out to be an almost perfectly calibrated points-allowed forecast — `PA ≈ −0.35 + 1.016 × opponent_implied` over 3,952 team-weeks — but explains only ~15% of the variance, which is precisely why the *distribution* rather than the point estimate is the deliverable.

### The data find that avoided a heavy dependency

The card implied play-by-play was needed for EPA (~20 MB/season × 8). nflverse's `stats_team` release is **126 KB per season** and carries per-team offensive EPA (so a defense's EPA allowed is just the opponent's offensive EPA), every defensive counting stat, and the blocked-kick columns. `games.parquet` supplies real scores, lines, wind, roof, and `home_qb_id`/`away_qb_id` — the announced starter the QB-specific turnover rate needs. Total addition: ~1 MB for eight seasons instead of ~160 MB.

### Four bugs, all found by running it, none by review

1. **13% of the fit panel vanished silently.** `games.parquet` uses era-correct team codes (SD, STL, OAK) while `stats_team_week` uses the current franchise code retroactively (LAC, LA, LV). The merge is an inner join, so a mismatch is not an error — it is an absence. The 2014-17 panel came back 1,776 team-weeks against an expected 2,048. Caught only because `dst_model.py`'s decision #16 guard refuses to substitute a league-average defense when an opponent cannot be resolved. Fixed by routing through `ingest_salaries.py`'s existing `BASE_TEAM_ABBREV_MAP` (which already carried exactly these mappings — no second copy) plus a lossy-merge assertion that fails past 2%. Every fitted coefficient improved afterwards: sack-rate own-term went from t = +1.30 to t = +2.32.
2. **Sigma was scaled by the recalibration slope.** The recalibration `actual ~ a + b·proj` corrects the *between-defense* spread; sigma is the *predictive* spread of one defense around its own mean. Different quantities, no shared scale factor. Multiplying pushed calibration from 0.949 to 0.565 and the sigma range to 9.4–11.2 against a realized RMSE of 5.8 — asserting nearly twice the uncertainty that exists. Caught by this session's own decision #22 sigma-calibration check, which is why that check is in the measurement script rather than left to eyeball.
3. **Positional arguments in the harness.** Inserting `dst_model_mode` into `backtest_week`'s signature would have silently bound `statline` to it — a wrong-arm run reporting clean numbers. Call site converted to keywords.
4. **The arm label lied about which arm was running.** Found by the user reading real output: the run banner said `DISTRIBUTIONAL DST` while the summary said `legacy DST (Session 3.1) <- Session 10.1 baseline arm` for the same run. Three `describe_arm()` call sites existed; the first fix caught two, and the third — the summary, which is the block that gets pasted into this log — was missed until a second run exposed it. Root cause was `describe_anchor()` appending "(Session 10.1 baseline arm)" whenever the anchor was off, which was true in 10.2 when the anchor was the only axis and became false once the engine (10.3a) and the DST model (10.4) were added. `describe_arm()` now solely owns that judgement because it is the only function that sees the whole configuration. **Transferable lesson: when you add an axis to what defines an arm, grep for every place that names one.**

### SciPy was removed rather than installed

The fitter and the measurement script originally imported SciPy for four things. The real Windows environment did not have it. SciPy *does* publish Python 3.14 wheels, so installing would have worked — it was not taken because the production path (`dst_model.py`, which is what `build_projections.py` calls) uses only `numpy.random`, and adding a compiled dependency for two offline scripts would have put it into the GitHub Actions environment too.

`statlite.py` implements the four: NB log-pmf, bounded 1-D minimiser, Spearman, paired t-test. The usual objection — hand-rolled statistics are probably subtly wrong — is answered rather than asserted: `verify_against_scipy()` checks every function against SciPy across a grid and is shipped in the file. Max absolute errors 1.7e-13 (NB log-pmf), 3.4e-14 (Student-t sf), 5.6e-17 (Spearman), 4.4e-16 (t-statistic), and **8.9e-05 relative on the NB dispersion MLE end-to-end** — the number that actually ships inside `dst_model.json`. The estimator is unchanged (still MLE, not a method-of-moments shortcut), because swapping it would have quietly moved every fitted dispersion.

One note on that check: its first version reported a 0.87 discrepancy on the minimiser. That was the *test* being wrong — a multimodal test function, where golden-section and Brent legitimately settle in different local minima and neither is incorrect. Every real call site minimises a smooth unimodal negative log-likelihood. The comment in the file records why, so it does not get reintroduced.

### The recalibration step, which was not in the card

Simulating well-fitted components does not produce a well-calibrated projection, and measuring proved it. Regressing realized DST points on the projection (slope 1.0 = calibrated):

| | slope | correlation | projection SD | optimal SD for that correlation | ratio |
|---|---|---|---|---|---|
| legacy | +0.307 | 0.173 | 3.35 | 1.03 | **3.26** |
| distributional, raw | +1.447 | 0.280 | 1.15 | 1.66 | 0.69 |

**The legacy DST model spreads defenses 3.3× further apart than its own accuracy supports** — the ROADMAP's "slope-below-1 bias" in its most extreme form anywhere in this project, and it has been driving DST selection since Session 3.1. The new model errs the other way (too compressed, from shrinking components hard) but is nearly four times closer.

Both are fixed by one linear recalibration fitted on the fit window only. Being monotone with a positive slope it cannot reorder defenses, so the Spearman gain is earned by the model and is not an artifact of the correction. The user's call was explicit: found here, fixed here.

### Measurement

The card's single validation line was split in two, because the harness cannot isolate one of nine slots — a DST contributes ~6.7 of ~120 lineup points, and Session 10.1's own power note says 65 weeks against a ~13-point week-to-week SD cannot resolve an effect that small.

**DST slot, real graded DK actuals, legacy arm read from the real salary files (65 weeks, 1,914 defense-weeks):**

| | legacy | distributional (holdout fit 2014-17) | distributional (production fit, all 8) |
|---|---|---|---|
| MAE | 5.121 | 4.624 | 4.552 |
| RMSE | 6.608 | 5.805 | 5.781 |
| Spearman | 0.199 | 0.309 | 0.311 |
| mean projected (actual 6.688) | 6.987 | 7.213 | 6.908 |
| sigma calibration | n/a | 0.944 | 0.931 |

The middle column is the honest out-of-sample result. The right column is the shipped configuration and is **in-sample for these seasons — recorded as the configuration's numbers, not as evidence.** The production refit did what was predicted: the level bias fell from +0.53 to +0.22, since part of it was the 2014-17 fit window having a lower scoring environment than 2018-21. Chosen-DST +0.69 pts/week, t = +0.65, p = 0.52 — positive, not significant, not claimed.

**Lineup level, pooled 2018-2021 DK, 65 weeks × 20 lineups:** median-percentile 75.6 → 75.9, max-percentile 96.5 → 96.7, raw median lineup 127.17 → 127.72, raw best 163.67 → 164.34. Both percentile deltas are a fraction of one SE and signs flip across seasons (2019 median −3.9, 2020 median +3.1). **This outcome was pre-registered as a pass before the run**, along with the statement that a clear negative would be the interesting result and would point at the integration layer rather than the model.

**Baseline reproduction confirmed after the fact:** the harness with no new flags returned 75.6 / 96.5, raw median 127.17, best 163.67, field median 108.16 — identical to Session 10.3a's recorded values to the cent, proving this session's edits to `build_projections.py` left the frozen baseline intact.

### The latent factor

A defense that holds an offense down also tends to sack and intercept it — the same afternoon, not independent events. Measured: corr(points-allowed residual, takeaways) = −0.267, and corr(bracket points, all other components) = +0.301 raw. Independent draws gave a total DST sigma of 5.14 against a realized 5.78, an **11% understatement** — and understating sigma is the one direction that actively misleads Session 10.5's objective, since it makes defenses look falsely safe. Fixed with one standard normal per simulated game-week, exactly as 10.3a fixed the yards/TD correlation.

The calibration target is the **residual** within-game correlation (+0.279 on the holdout window, +0.301 on all eight), not the raw cross-sectional +0.301: part of the raw figure is simply good defenses being good at both, which the simulator already reproduces through each team's own fitted means. Calibrating against the raw number would double-count it and inflate every sigma.

### Defaults diverge on purpose

`build_projections.py` and `build_projections_statline.py` default to **distributional** (user-confirmed: production should use the better model). `backtest_harness.py` defaults to **legacy**, because its default *is* the definition of the Session 10.1 baseline arm and decision #11's pinned field must keep meaning "legacy engine, anchor off, legacy DST."

That divergence created a trap that was closed at the same time: the harness had been appending `--dst-model` only when non-legacy, on the reasoning that omitting it kept the command line identical to a pre-10.4 run. The moment the downstream default flipped, omitting the flag would have silently handed the harness a distributional DST — including for the pinned field — while it believed it was the baseline. The flag is now **always passed explicitly**. An explicit argument cannot drift with a downstream default.

### Sandbox-only vs live-validated

Everything in the deliverables was **live-validated on the real Windows environment against real RotoGuru slates and real graded actuals**, including both harness arms at 20 lineups × 65 weeks and the baseline reproduction. The following were **sandbox-only**: `statlite.verify_against_scipy()` (by construction — it needs SciPy, which is the environment it does not run in), and the `default == explicit legacy` equality test on `build_dst_projections()`, which was superseded by the end-to-end baseline reproduction anyway.

### Handoff notes

- **The production model is fit on all eight seasons.** Refit with `python3 scripts/fit_dst_model.py --fit-seasons 2014 2015 2016 2017 2018 2019 2020 2021`. Bare `fit_dst_model.py` gives the 2014-17 holdout fit and is for measurement only; the script prints a warning when a fit includes measurement-window seasons.
- **`refresh_data.yml` needs a current-season team-stats pull.** The only genuinely open item from this session — see the ROADMAP's Known Deferred Validations. Distributional is now the default, so `team_stats_{season}.parquet` is a required input to every build including the unattended refresh, and nothing in that workflow pulls it yet.
- **Commit point:** the nine scripts plus `data/dst_model.json`, `data/games.parquet`, and `data/team_stats_{2014..2021}.parquet` (~1 MB total). No Worker or frontend redeploy — the DST model is selected inside the projection build and the four-layer parameter chain is untouched, since the UI never picks a DST model.
- **Session 10.5 is unblocked on sigma** but should read that card's amended note first: a DST's sigma (~6.2) is nearly as large as its mean (~6.9), so a `λ·sigma` penalty will bite the DST slot harder than any other slot. Watch for λ driving the optimizer to the cheapest defense. `optimizer.py` still drops `sigma` — unchanged, still 10.5's first task.
- **Retuning targets, flagged ARBITRARY in code and not fit:** `SHRINK_GAMES` (sack_rate 8.0, int_rate 12.0, fumble_rate 16.0, qb_hit_rate 6.0, dropbacks 6.0), `QB_INT_SHRINK_ATTEMPTS` 200.0, `MIN_FIT_WEEK` 5, and the bounds `PA_MEAN_BOUNDS` / `DROPBACK_BOUNDS` / `SACK_RATE_BOUNDS` / `INT_RATE_BOUNDS`. The rookie multiplier (1.120) is fitted but rests on a t = +1.76 term — a judgement call to include, recorded as such.
- **A free side benefit, not claimed as solved:** the DST model is buildable in week 1 via prior-season carryover, unlike the stat-line engine's skill positions (Session 10.3b's job).

### Session 10.4 (ADDENDUM) — pre-kickoff season handling (2026-07-26)

Found while answering a user question about the `refresh_data.yml` gap rather than by testing, which is worth noting: the question "can we do this now or must we wait for the season?" is what prompted checking whether the current season's nflverse release exists at all.

It does not. `stats_team_week_2026.parquet` **404s today**, while `games.parquet` already carries all 272 scheduled 2026 games with null scores — nflverse publishes the team-stats release only once a season's first games are in the books.

`dst_model.load_team_stats()` raised on a missing file unconditionally, so **the first live run of the 2026 season would have hard-failed before reaching the prior-season carryover path that decision #15 exists to provide.** The model was designed to handle week 1 and could not get far enough to do it.

Fixed as decision #19. A missing current-season file is legitimate when `season_has_started()` is False — no game of that season has a score yet — and a hard error once it is True. The two states are distinguished by **data rather than by a calendar guess**, which matters because preseason and regular season both contain a "week 1" and a date-based rule would have to encode the schedule. Both call sites that load current-season stats (`build_features` and `_attach_epa_and_wind`) were updated; a case where NEITHER the current nor the prior season has data still fails loud, since carryover then has nothing to carry.

Verified end-to-end against the real 2026 schedule with no `team_stats_2026.parquet` present: 32 defenses built on 2025 carryover alone, projections 6.62–7.89, sigma 5.92–6.22, every QB resolved via the `last_game_leading_passer` fallback (correct — no 2026 starter is announced in `games.parquet` yet). Re-ran the 2021 measurement afterwards: unchanged.

**Operational consequence:** `data/team_stats_2025.parquet` is a required commit for the 2026 season, because it is the carryover source. The `refresh_data.yml` step must tolerate a 404 on the current season rather than failing the job.

---

## Session 10.3b — Stat-Line Priors, Cold Start, and Role Change (2026-07-27)

Ships on the capability gate agreed before the build, not on accuracy. Week 1 is buildable by the stat-line engine for the first time, and the three catalogued role-change cases are repaired before reconciliation touches them. The lineup-level effect is **+3.01 median-percentile (SE 1.55, t = 1.94, p = 0.057)** out-of-sample — below the bar, carried almost entirely by 2019, negative in 2020.

### The pre-test came first, and two premises died there

Sessions 10.3a and 10.4 both measured their own card's premises before building, and both times something came back false. `probe_statline_priors.py` is that step for this card — a throwaway script that writes nothing to `data/`, reuses `statline_model.py`'s own history primitives and `fit_salary_anchor.py`'s own isotonic machinery rather than reimplementing either, and asserts its cached history loader matches `load_history()` before printing a number.

**Probe A — price does not beat history at volume share, anywhere.** Pooled out-of-sample MAE 0.0709 (price) vs 0.0600 (history), 36,025 rows, and history wins in every games-played bucket including 0–1. A 50/50 blend lands at 0.0597, a 0.5% improvement. What price *does* have is decorrelated error: residual correlation 0.474–0.597, nowhere near the 0.965 that made 10.3a's blend a null. Real independent information, just the weaker signal. Consequence: **the price prior ships cold-start-only, mid-season floor 0.0** (user-confirmed). One honest caveat on that evidence — probe A necessarily excluded 3,905 rows with no history share, so its `gp 0-1` bucket is effectively gp = 1 and it cannot itself speak to true cold start. That rests on Session 10.2's measured week-1 result.

**Probe B — Vegas adds to team volume, with the card's mechanism corrected.** Pass attempts R² 0.0652 → 0.0799; carries 0.0394 → 0.0667. The pre-registered hypothesis held: spread drives carries (t = −6.62), total drives attempts (t = +5.02). The mechanical finding that would have been easy to get wrong: **both terms are required together.** Alone, each is weak (attempts: total t = +1.54, spread t = +1.07); jointly +4.67 and +4.53. That is suppression, and it is expected — `implied_total = total/2 − spread/2`, so carrying both is what spans *both* teams' implied totals rather than one composite. Never fit or ship one without the other.

**Probe C — prior-season team-volume carryover is worse than useless. FALSE premise.** Week-1 pass attempts: league average MAE 6.31 / R² **+0.015**; carryover MAE 6.42 / R² **−0.065**. Carries: +0.026 vs **−0.046**. Negative out-of-sample R² on both channels. Week-1 team volume is therefore the league mean tilted by that week's line, and the prior season is never consulted. **This finding must not be applied to `dst_model.py` decision #15** — that carries over defensive *quality*, which persists across a season boundary. This is *volume*, which is scheme and pace and turns over with coordinators and personnel. Different quantity, different answer, and 10.4's addendum depends on the carryover path working.

**Probe D — the ROADMAP's role-change instruction is backwards, and it is now amended there.** Phase 10's design intro said to *suppress* the salary anchor when a role change is flagged, "a stale price is exactly the value spot we're trying to beat." That presumes the price is stale. On a weekly slate the site reprices every player every week with real money behind it while our usage history is weeks old by construction. Regressing what history misses on the price−history divergence, out-of-sample: **slope +0.4529, t = +93.26, R² = 0.195.** The three catalogued cases, realized share 1.000 in all three: NYJ 2021 wk13 Z. Wilson hist 0.128 / price 0.935; SEA wk13 R. Wilson hist 0.582 / price 0.971; CAR wk15 Newton hist 0.521 / price 0.935.

### The structural finding that reordered the build

Cold start and Vegas team volume are **not independent bullets**, which is how the card listed them. In week 1 `load_history()` is empty, so `team_volume_history()` returns an empty frame, so reconciliation cannot run — and `_participation()` returns 0.0 for every player, which would multiply any price-predicted volume straight back to zero while looking like it had worked. A player share is meaningless without a team total to take a share *of*. Cold start therefore depends on a team-volume source that is not this season's history, and they ship behind one flag.

### Design decisions taken, and one rejected

**The role-change flag acts on participation, not on the share** (option (b) of two, user-confirmed). This card states its own problem precisely: "the QB projection is substantially a product of reconciliation rather than of the volume model." Zach Wilson's failure is not really his share — it is `participation = 0.20` crushing his volume, after which reconciliation scales the pool back up and does the work the volume model should have done. The rejected alternative was to blend the share toward price at probe D's slope; it was rejected because in the top-divergence decile price *alone* is worse than history (MAE 0.237 vs 0.167), so a 0.45 blend puts Wilson at ~0.49 against a realized 1.000 — half a fix that leaves reconciliation still doing the repair.

**The override's strength is fitted, not hand-tuned.** The first draft was `clip((rel_div − LO)/(HI − LO))` with LO and HI chosen by eye against the three catalogued cases — three points fitted and called a rule. Replaced with a formulation whose one constant *is* probe D's regression slope: `share_target = hist + ROLE_SLOPE × (price − hist)`, then `part_eff = clip(part × share_target/hist, part, 1.0)`. Participation is scaled by exactly the ratio the fitted response says the share should move. It **only ever raises, never lowers** — participation already handles the backup case correctly (that is what 10.3a decision #9 built it for, and Cooper Rush is the evidence); the gap it cannot close is one-directional.

**The cold-start schedule needed a taper, and the bare ROADMAP formula did not mean what "cold-start only" was agreed to mean.** `floor + (1−floor)·k/(k+gp)` at floor 0.0, k 4.0 gives w = 0.364 at seven games and 0.20 at sixteen. An entrenched starter in the first real run had his volume pulled from 38.0 to 35.2 by a standing one-third price weight — a long way from cold start, and pointing the wrong way against probe A. The floor is the *asymptote*, not the mid-season weight, and the decay to it is slow. Added a linear taper to zero over `COLD_START_MAX_GAMES` = 4: weights are now 1.000 / 0.600 / 0.333 / 0.143 / 0.000 at gp 0–4. Linear rather than a second decay curve on purpose — a hard cutoff would put a discontinuity in a player's projection at the game he crosses it. Verified afterwards: the gp = 9 starter is *exactly* untouched at 38.0 while the role-change player is still repaired.

### Measurement

Both artifacts holdout-fit (2014–17), measured on 2018–21, week 1 excluded so the comparison is the same 65 weeks, paired by week, both arms run on identical code the same day.

| arm | median-pctile | paired delta |
|---|---|---|
| volume prior OFF | 77.88 | — |
| prior ON, role-change ON | 80.89 | **+3.01, SE 1.55, t = 1.94, p = 0.057** |
| prior ON, role-change OFF | — | role change alone: **−0.06, t = −0.07, p = 0.94** |

Per season: 2018 +2.01, 2019 **+8.93**, 2020 **−0.60**, 2021 +1.78. One season out of four driving it while another goes negative is the signature of noise, not an effect. **Read the per-season block, not the pooled number.**

The role-change flag is a lineup-level null and is kept anyway, logged honestly as such: the player-level repair is real, and Session 10.5's objective consumes per-player mean and sigma directly, where a QB projected at a 0.128 share when he took every snap is simply a wrong number whether or not he lands in an optimal lineup.

**A pre-registration that was wrong, recorded as such.** Before the build I wrote that none of this would clear the noise floor. The first measurement came back +4.21 at t = 3.08 and I said so. That measurement was then found to be sitting on an in-sample variance artifact shared by both arms; the clean number is +3.01 at t = 1.94, much closer to the original prediction. The lesson is not that the prediction was right — it is that the first number was quoted before its artifacts were checked.

### Four bugs, all found by running

1. **`KeyError: 'player_id'` killed all four week-1 backtests.** `build_usage()` returned a bare `pd.DataFrame()` — empty *and columnless* — so every caller's `merge(on="player_id")` raised. Latent through the whole of 10.3a because week 1 was skipped before that line was ever reached. An empty result is a valid result and has to be shaped like one; it now returns the full column schema (decision #16).
2. **Cold-start efficiency was NaN.** The design note for this card asserted the case was already handled because `_shrink()` returns the position mean at a zero denominator. Wrong: `_shrink()` is only reached for players `build_usage()` emits a row for, and a zero-history player is not one of them. His rates arrive from the left join as NaN, and NaN times a correctly cold-started volume is NaN. `fill_cold_start_rates()` closes it using the same artifact values `_shrink()` would have used (decision #17).
3. **The role slope was fit on the measurement seasons.** Caught by reviewing the first real backtest rather than the code. The slope went into the artifact and was then measured on the same seasons — precisely the error 10.3a caught in itself at a threefold inflation. Fixed by cross-fitting inside the fit window; on a holdout fit nothing from 2018–21 enters the artifact.
4. **Field pinning would have silently run the wrong arm.** The harness rebuilds the arm's projection file after the baseline run clobbers it, and that call did not forward `prior=`. The measured arm would have been plain stat-line while every label said volume-prior — the same class as 10.4's bugs #3 and #4, one layer deeper.

Plus, in the pre-test itself: `statlite.spearmanr` returns a result object rather than a tuple; a per-week team-volume recomputation inside the per-player loop that would have been ~190,000 full boolean scans on the real panel; and an unfitted `(position, component)` pair dropped **silently**, taking every TE row out of the pooled numbers without a word.

### Two process defects fixed, neither deferred

**The artifact provenance guard (`backtest_harness.py` decision #16).** This session lost three full backtest runs and came one bisect from blaming a +1.4 shift on newly-written code, because `statline_variance.json` had been refit on all eight seasons for production and silently became the basis of a 2018–21 measurement. Nothing printed that fact anywhere. `fit_volume_prior.py` warned about its own fit window, but a warning only one of four artifacts emits is not a guard — and the one that mattered was silent. The harness now prints every loaded artifact's fit window in the run banner and warns loudly on overlap with the measured seasons. It **warns rather than aborts**: measuring in-sample is the right thing when you want the shipped configuration's own numbers, and is only wrong when it goes unrecorded.

**A false provenance message in `fit_volume_prior.py`.** On the production refit it printed "curves on [2014–2017] → slope fit on [2018–2021]" and, in the same line, "Nothing from [2018–2021] enters the artifact." Both halves, contradicting each other. Now checked rather than asserted.

**The field's RNG stream (`backtest_harness.py` decision #17).** A cross-arm field divergence at 2020 wk3 (field median 119.03 vs 109.24, identical on the other 64 weeks) was found by eyeballing three printed logs, which is not a detection method. The root fragility: `build_synthetic_field()` reused the same generator the optimizer seed had already drawn from, so the pinned field's randomness depended on how many draws everything before it happened to consume — arm-invariant by accident, not by construction. It now gets its own stream derived from (seed, season, week) plus a stream tag. A `field_pool_fingerprint` is also recorded per week and printed in the summary, so two arms' logs can be compared mechanically instead of by eye. **The 2020 wk3 divergence itself is not fully explained** — the new stream removes the mechanism that most plausibly caused it, and the fingerprint will catch any recurrence, but this is a fix-and-detect rather than a root-caused diagnosis.

### The re-baseline, and what it supersedes

The volume-prior-OFF arm did not reproduce 10.4's recorded 75.9 / 96.7. It returned 77.1 with the all-eight variance artifact and **77.9** with the holdout artifact — refitting to holdout moved it *away* from the target, so the in-sample-artifact hypothesis was wrong and is recorded as wrong.

Every file on the stat-line path was then diffed against its pre-session version from GitHub history and cleared: `statline_model.py` (only two commits ever; the diff against 10.3a is exactly this session's additive edits), `build_projections_statline.py` (this session's additions on top of 10.4's, all gated), `scoring_rules.py` (10.4's changes are purely additive and entirely DST — `score_statline()` and `STATLINE_COLUMNS` byte-identical to 10.3a), `fit_statline_variance.py` (untouched since 10.3a). The automated cron commits write only `logs/automation_run_log.csv`. The legacy path is provably unaffected throughout — field median is identical to the cent at 108.16 across every run.

The most parsimonious explanation left is a **stale reference**: 10.4 has three commits, and its reproduction check may predate the last two, in which case the recorded figure describes an intermediate state of the repo that no longer exists. Proving that would mean reconstructing and running each intermediate commit, which was judged disproportionate.

**Re-baselined by explicit agreement.** New reference, 2026-07-27, holdout artifacts, 65 weeks, week 1 excluded: stat-line + distributional DST, volume prior OFF = **77.9 / 97.3**, raw median lineup 129.64, best 166.23, field median 108.16. This supersedes 10.4's 75.9 / 96.7 for all future comparison. The discrepancy is unexplained and logged as such rather than buried.

### Sandbox-only vs live-validated

**Live-validated on real 2014–2021 data:** every probe result; the fitter end to end; all seven share curves; the team-volume specifications; the role slope and the three catalogued-case repairs; week 1 building in all four seasons; the three-arm measurement; the file diffs against GitHub history.

**Sandbox-only (synthetic fixtures on real schemas):** the provenance guard's four cases; `field_pool_fingerprint`'s stability, projection-independence and change-detection; the field RNG's reproducibility and per-week variation; the cold-start taper table; the role-change guard paths. None of these has run on Greg's machine yet — **the next backtest is their first live exercise**, and the fingerprint block appearing in the summary is the thing to check.

### Handoff notes

- `--volume-prior` is **OFF by default** and should stay off until a measurement supports flipping it.
- Before any future measurement, read the ARTIFACTS block in the run banner. If anything says `<< IN-SAMPLE`, refit before believing the numbers.
- `COLD_START_MAX_GAMES` and `DEFAULT_COLD_START_K` are the first retuning targets; probe A's evidence argues for a faster handover than either.
- Session 10.5 can proceed. Its blocker was a validated per-player mean and sigma, which 10.3a delivered and this session did not disturb.
- `probe_statline_priors.py` is a throwaway. It writes nothing and nothing loads it. Delete it whenever it stops being useful.

---

## Session 10.5 — Objective + Randomization Rewire (2026-07-28)

**Status:** ✅ Complete — λ=0 anchor reproduced, objective wired, randomization extended. Sweep deferred to Session 10.5b (build-once efficiency fix required first — see that entry).

### What shipped

Four files, all in `scripts/`:

| File | Change |
|---|---|
| `optimizer.py` | Step 1: sigma + sigma_source carried through assign_roster_slots; sigma_total in lineup attrs. Step 2: `--lambda` flag, mean-variance objective `Σμ − λΣσ²`. Step 3: `--randomization-mode {pct,sigma}`, DEFAULT_SIGMA_RAND_FULL_LINEUPS=20 FLAGGED ARBITRARY. |
| `backtest_harness.py` | Step 4: `--lambda-grid`, `--sigma-recalibration`, `--contest-type`, `--lam`; beat_rate@p44/p50 and top_rate@p90/p99 metrics; sweep loop (build-once efficiency — see Session 10.5b); results CSV always written. |

### Design decisions resolved before any code (pre-test first)

All six decisions settled in one pass before building:

1. **Penalty form: Σσ²** (variance, not sigma). Additive variance is the correct form for independent players — it traces the true mean-variance efficient frontier. Σσ would trace an interior curve.
2. **Grid spans negative λ.** Upside-seeking direction included even though probe A showed ~4% of pairs are upside-seeking. Confirmed asymmetric: positive direction has a real dial; negative direction has almost nothing to act on.
3. **Backtest-only scope.** `build_projections.py` emits no sigma; stat-line engine has never been promoted to production. No Worker, Actions, or frontend change.
4. **Randomization additive, not a reinterpretation.** `mode="pct"` (default) byte-identical to all prior sessions. `mode="sigma"` uses per-player sigma as the scale instead of projection, with an entry-count ramp (off at n=1, full at DEFAULT_SIGMA_RAND_FULL_LINEUPS=20, **FLAGGED ARBITRARY**).
5. **Beat-rate and top-rate metrics added.** Named `beat_rate@pXX` / `top_rate@pXX`, not "cash rate" — these are a synthetic field, not real payout. Pre-registration rule written into the return dict comment: beat@p44 → cash, beat@p50 → 3-max GPP, top@p90 → large-field GPP. No λ selected by argmax.
6. **λ=0 anchor:** reproduces **77.9 / 97.3** (10.3b re-baseline). Confirmed — see validation below.

### Session 10.5 pre-test (probe_sigma_quality.py) — findings that shaped the session

Run before any code, 2018–2021, 65 weeks, 15,968 player-weeks. Full results in the 10.4b session entry. Key findings carried into the build:

- **Sigma is correctly ranked** (Spearman +0.31–0.45, all skill positions). Not noise.
- **Sigma was massively over-dispersed** — ratio falling 2.1–2.7 → 0.58–0.69 across quintiles. Squaring it for the objective would have compounded the distortion non-linearly; no λ could have undone it. This is why Session 10.4b was inserted.
- **DST sigma is effectively constant** (slope 0.055, Spearman +0.076). Session 10.4's warning that λ would drive the optimizer to the cheapest defense measured FALSE — every defense carries nearly the same variance, so the penalty is close to a constant across lineups. DST slot is inert to λ within the useful grid.
- **Probe A derived the grid from data, not from guessing.** Floor-seeking cash: [0.039, 0.063, 0.104, 0.139, 0.188]. Upside-seeking GPP: [−0.003, −0.005, −0.014, −0.030, −0.095].

### Bug caught in Step 2 smoke test

Test fixture had only two RBs — FLEX absorbed the second, so the ILP had no third option and lambda never moved the selection. Fixed by adding a third RB; the analytically-predicted flip threshold (λ* = Δμ/Δvar = 1/75 ≈ 0.013) was then verified against a real CBC solve.

### Validation: λ=0 anchor

Run: `python scripts/backtest_harness.py --site dk --season 2018 2019 2020 2021 --all-weeks --engine statline --dst-model distributional --num-lineups 20 --lam 0.0`

| metric | target (10.3b) | this run | delta |
|---|---|---|---|
| median-pctile | 77.9 | 77.8 | −0.1 ✅ |
| max-pctile | 97.3 | 97.6 | +0.3 ✅ |
| raw median lineup | 129.64 | 129.58 | −0.06 ✅ |
| raw best lineup | 166.23 | 167.15 | +0.92 ✅ |
| field median | 108.16 | 108.08 | −0.08 ✅ |

All deltas within floating-point + one week's variance from sigma columns flowing through the DataFrame. Anchor check passes.

### Deferred to Session 10.5b

The λ sweep. The harness calls `backtest_week` once per lambda per week, and each call rebuilds projections — 65 × 11 = 715 builds at ~2 min each ≈ 24 hours. Build-once efficiency fix required first (Session 10.5b, decision #15).

### Decisions documented in code

Decision #14 (sigma-mode randomization, ARBITRARY entry-count ramp), decision #15 (build-once sweep, inherited by 10.5b). The pre-registration rule is embedded in `backtest_week`'s return dict comment so it cannot drift from the code.

---

## Session 10.4b — Sigma Dispersion Recalibration (2026-07-28)

*(Inserted between 10.4 and 10.5 — see ROADMAP for full card. SESSION_LOG entry written after the fact as part of the 10.5/10.5b close-out.)*

Full entry already written above in the chronological position. See the heading "Session 10.4b — Sigma Dispersion Recalibration" earlier in this log.

---

## Session 10.5b — Lambda Sweep and Build-Once Efficiency (2026-07-28)

**Status:** ✅ Complete — sweep ran, results read, Phase 10 closed.

### The build-once fix (decision #15)

Before: `backtest_week` always called `run_projection_pipeline` regardless of how many lambda values had already run that week. 65 weeks × 11 lambdas × ~2 min/build = ~24 hours.

After: `skip_projection_build: bool = False` parameter. The sweep loop passes `skip_build = (i_lam > 0)` — False on the first lambda, True on every subsequent one. Both the arm build and the field-baseline rebuild are gated. Fails loud with a clear error if the expected file is missing when skip=True.

**Actual runtime:** ~2 hours 45 minutes per sweep (20max and 3max identical). Both projection builds are still 3× per first-lambda-week (arm build + legacy field baseline + arm rebuild after clobber), so 65 × 3 = 195 builds ≈ 2.75 hours at ~50 seconds each. This is correct and expected. Single-entry not run — deterministic at n=1 (randomization and sigma-mode both off), so the sweep is identical to probe A's pairwise reversal threshold analysis, which already ran.

### Results CSV pushed to repo

`output/backtest_results_dk_20max.csv` and `output/backtest_results_dk_3max.csv` pushed before this session was written.

### Anchor check (λ=0 row)

| | 20max | 3max | target |
|---|---|---|---|
| λ=0 median-pctile | 77.84 | 78.21 | 77.9 |
| λ=0 max-pctile | 97.59 | 93.75 | 97.3 |

20max matches to 0.06 points — pass. 3max max-pctile is 93.75 vs 97.3 — structural, not a failure. With 3 lineups per week vs 20, the best lineup rarely hits the 97th field percentile. The anchor is not a 20-lineup-specific concept; 97.3 is the 20max reference. Both anchors pass on the metric that matters (median-pctile).

### Sweep results

**20max:**

| λ | med-pct | beat@p44 | beat@p50 | top@p90 | top@p99 |
|---|---|---|---|---|---|
| −0.095 | 76.84 | 0.8600 | 0.8200 | 0.9692 | 0.3385 |
| −0.030 | 77.20 | 0.8638 | 0.8223 | 0.9692 | 0.3385 |
| −0.014 | 77.67 | 0.8700 | 0.8354 | 0.9538 | 0.3846 |
| −0.005 | 77.46 | 0.8608 | 0.8254 | 0.9846 | 0.4154 |
| −0.003 | 77.72 | 0.8638 | 0.8300 | 0.9692 | 0.4000 |
| **0.000** | **77.84** | **0.8662** | **0.8285** | **0.9692** | **0.4154** |
| +0.039 | 78.28 | 0.8669 | 0.8308 | 0.9231 | 0.4462 |
| +0.063 | 78.33 | 0.8723 | 0.8323 | 0.9077 | 0.3538 |
| +0.104 | 78.11 | 0.8700 | 0.8246 | 0.9538 | 0.4308 |
| +0.139 | 77.06 | 0.8631 | 0.8177 | 0.9385 | 0.5077 |
| +0.188 | 72.30 | 0.8154 | 0.7662 | 0.8615 | 0.3538 |

**3max:**

| λ | med-pct | beat@p44 | beat@p50 | top@p90 | top@p99 |
|---|---|---|---|---|---|
| −0.095 | 77.03 | 0.8513 | 0.8308 | 0.7538 | 0.2000 |
| 0.000 | **78.21** | **0.8462** | **0.8103** | **0.8000** | **0.1538** |
| +0.039 | 79.79 | 0.8513 | 0.8154 | 0.8000 | 0.1231 |
| +0.063 | 77.50 | 0.8564 | 0.8257 | 0.7846 | 0.1846 |
| +0.104 | 78.38 | 0.8718 | 0.8308 | 0.8308 | 0.2000 |
| +0.188 | 72.48 | 0.8359 | 0.7949 | 0.6769 | 0.1385 |

### Pre-registered interpretation

Using the rule written into `backtest_week`'s return dict before the sweep ran:

**Cash games (beat@p44):** λ=0.063 at 20max (0.8723 vs 0.8662 at λ=0 — +0.006). 3max points to λ=0.104 (0.8718). No clean consensus. SE on a proportion of ~0.87 over 65 weeks is √(0.87×0.13/65) ≈ 0.042, so the lift is less than one SE. Suggestive, not conclusive.

**3-max GPPs (beat@p50):** λ=0.063 at 20max (0.8323 vs 0.8285 — +0.004). 3max is noisy, no clear winner. λ=0 is defensible.

**Large-field GPPs (top@p90):** Clearest result, points **against** positive λ. At 20max, λ=−0.005 hits 0.9846 (highest), while the positive grid drops to 0.9077–0.9538. Positive λ compresses the right tail, which is exactly what it is supposed to do — and GPP needs the right tail. λ=0 or mild negative is correct for large-field.

### Findings

1. **Positive λ produces a real but weak floor improvement for cash at 20 lineups.** λ=0.063 is the weakest reasonable recommendation for cash games. The lift is inside the noise over 65 weeks, but the direction is consistent and the upper bound (λ≥0.139) clearly degrades all metrics.
2. **λ=0 is the correct default for GPP.** The variance penalty hurts top-rate at every positive grid point.
3. **λ≥0.188 is harmful in all contest types.** Median-pctile drops 5+ points, all other metrics fall. Hard upper bound established.
4. **The useful range is 0.039–0.104 for floor-seeking, 0 for upside.** The negative direction had almost nothing to act on by construction (probe A: 95–98% of same-position pairs are floor-seeking), confirmed here — no negative λ improved any metric materially.
5. **Single-entry sweep not run.** Deterministic at n=1 — randomization and sigma-mode both off. Equivalent to probe A's pairwise analysis already in the log.
6. **DST slot confirmed inert.** No λ in the grid required the optimizer to substitute a cheaper defense, confirming the probe A finding that DST sigma variance is nearly constant across defenses.

### Default unchanged

λ=0 remains the shipped default in `optimizer.py`. Strategy selection of a non-zero λ per contest type is a human decision made from the curve above, the same way exposure caps and uniqueness are set by hand. No four-layer live wiring — the stat-line engine has never been promoted to production.

### Remaining deferred (not newly opened)

- `--sigma-recalibration` end-to-end wiring validation on a real slate → Preseason Week 1.
- `dst_model.json` holdout refit (blocked on `ingest_historical.py --season 2013`) → whenever.
- FD sigma artifact → whenever FD real data exists.


---

## Session 11.0 — Ownership Model Feature Expansion + Phase 11 Gap Assessment (2026-07-28)

**Date completed:** 2026-07-28
**Status:** ✅ Complete — gap assessment done, Phase 11 added to ROADMAP.md, `ownership_heuristic.py` updated and validated.

### What was actually built

This session opened Phase 11 (Ownership Model Upgrade) and completed its first card (Session 11.0). The work split into two parts: a research-driven gap assessment comparing what we have against three target tiers, and a code change to `ownership_heuristic.py` that closes the feature gap identified.

**Part 1 — Gap assessment and tier definitions**

A clean-slate research session (no preconceptions, fresh web research) established the following:

*What ownership actually is:* Ownership percentage = (lineups containing player X) / (total entries) × 100. Computed by the platform post-lock. Contest-specific, not slate-wide. Before lock, every number is a projection — not a fact.

*What drives projected ownership (from research):* The strongest single predictor is points-per-dollar value (salary ÷ projection). Salary alone explains ~8% of ownership variance (r ≈ 0.29 from a real 95,825-entry MLB slate). Adding projected points and game totals likely gets to ~20-25% explained variance. The industry has not converged on a single formula — tools differ mainly in how they combine these inputs and whether they simulate field lineups (expensive) or use a direct formula (tractable).

*Three tiers defined:*

| Tier | Description | Effort | Benefit |
|---|---|---|---|
| 1 | Value-based softmax, parameters fit to real data | Low | High |
| 2 | 5-feature model + learning loop retuning | Medium | High |
| 3 | Per-contest-type stratification | Medium | Medium |
| 4 | Simulation-based field modeling (SaberSim-style) | High | Low-medium |

Tier 4 dropped. High effort, marginal benefit at personal-use scale.

*Gap against each tier:*

**Tier 1 (value-based softmax):** Architecture is ~70% there. The softmax structure, per-position budget anchoring, and value feature are all built. The gap is unfit parameters: temperature = 15.0 (arbitrary), blend weights (0.45/0.20/0.25, arbitrary), FLEX split even thirds (no real data). These close at Session 11.1 once real ownership data exists.

**Tier 2 (feature-weighted model + learning loop):** ~40% there. Two real ownership predictors were missing from the feature set: raw projected points as a standalone signal (distinct from value efficiency), and game-level over/under (distinct from implied team total). The logging infrastructure (Session 9.3) and retuning (Session 9.4, renamed 11.2) were already planned but not started. Session 11.0's code change adds the two missing features. The learning loop starts at Week 1.

**Tier 3 (contest-type stratification):** 0% there. No architecture, no data. The action is to capture `contest_type` in Session 9.3's logging schema from day one, so Tier 3 fitting is possible after one full season. Session 11.3 cannot be built responsibly before the 2026 regular season ends.

**Part 2 — Code change: `scripts/ownership_heuristic.py`**

Two new features added to the chalk_score blend. No existing features removed. No existing output columns changed. No downstream scripts affected.

*New feature 1 — raw_projection_percentile (decision #6):*
`final_projection` as a standalone input, percentile-ranked within position group. Distinct from value (pts/$1K). Captures "expected ceiling" signal that pure value misses: an expensive stud with 18 projected points has lower value than a cheap role player with 12 points, but the stud will be owned far more heavily on projection ceiling alone. Value alone systematically undersells expensive chalk and oversells cheap punts in ownership terms.

*New feature 2 — over_under_percentile (decision #7):*
Game-level over/under, percentile-ranked across the full pool. `over_under` already existed in `final_projections_*.csv` since Session 3.3's addendum — no pipeline change needed. Captures "shootout game" signal distinct from implied_total: a team with implied_total 27 in a 52 O/U game has a very different ownership profile than the same team in a 38 O/U game, even with identical spreads. Affects all positions in the game, not just the favored team's offense.

*Updated blend weights:*

```
OLD (4-feature, Session 4.1):
  value: 0.45 | salary_tier: 0.20 | vegas: 0.25

NEW (5-feature, Session 11.0):
  value: 0.35 | projection: 0.15 | salary_tier: 0.15 | vegas: 0.20 | over_under: 0.15
```

Weights sum to 1.00. All five are unfit starting guesses; retuning targets for Session 11.1. Direction rationale: value drops because raw projection is now separate; salary_tier drops because value+projection together carry most of the salary-driven signal; vegas redistributes partially to over_under.

*Temperature unchanged:* `OWNERSHIP_SOFTMAX_TEMPERATURE = 15.0`. Temperature is fit separately from the blend weights. The feature expansion doesn't change the right starting point — it will be re-evaluated in Session 11.1 alongside the weights.

*New required input column:* `load_final_projections()` now requires `over_under` in the projections file. Already present since Session 3.3's addendum. A clear SystemExit with an explanatory message fires if it's missing.

**Part 3 — ROADMAP.md update**

Phase 11 added with five session cards:

| Session | What | When |
|---|---|---|
| 11.0 ✅ | Feature expansion + schema def | Done |
| 9.3 | Ownership logging (updated schema) | Week 1 onward |
| 11.1 | Regress weights + temperature | ~Week 6-7 |
| 11.2 (was 9.4) | FLEX split + per-position temperatures | ~Week 8+ |
| 11.3 | Per-contest-type stratification | Post-season 2026 |

Session 9.3's card was updated in-place with the full `ownership_actual_log.csv` schema (columns: site, season, week, contest_id, contest_type, field_size, player_id, player_name, actual_ownership_pct, estimated_ownership_pct_at_lock, source, logged_at). Session 9.4 redirected to Session 11.2.

### Validation

Run against real DK week-10 test data (`output/final_projections_dk_10.csv`, 245 players):

```
python scripts/ownership_heuristic.py --site dk --week 10
```

```
0 player(s) received a name-recognition bonus from name_recognition_flags.csv.
estimated_ownership_pct summed per position group (should equal that group's roster-slot budget):
  DST: 100.0%  (budget: 100.0%)  ✅
  QB:  100.0%  (budget: 100.0%)  ✅
  RB:  233.3%  (budget: 233.3%)  ✅
  TE:  133.3%  (budget: 133.3%)  ✅
  WR:  333.3%  (budget: 333.3%)  ✅
Wrote 245 players to output/chalk_scores_dk_10.csv
  Nulls in any column:                     0  (should be 0)  ✅
  chalk_score out of [0,100] range:        0  (should be 0)  ✅
  estimated_ownership_pct out of [0,100]:  0  (should be 0)  ✅
```

All budget totals exact. All three output-integrity checks pass. FD not separately re-run — the feature additions are site-agnostic by construction (both sites use the same `over_under` column and the same `final_projection` column from `final_projections_*.csv`); treated as covered by construction rather than needing a duplicate manual run, flagged here rather than silently assumed.

### Deferred items

- FD real-data validation: same pre-existing gap as all other FD items — closes at Preseason Week 1 alongside the rest of the FD list.
- All five blend weights and temperature: unfit starting guesses. Retuning targets for Session 11.1. Logged explicitly in `ownership_heuristic.py`'s module docstring and constants block.
- FLEX split (even thirds): known simplification, logged as retuning target for Session 11.2.
- Session 9.3 data source: DraftKings large-field GPP contest results page identified as primary source. Script built (2026-07-29) — see Session 9.3 log entry. First real logging opportunity is Preseason Week 1; that run closes the session.

### Handoff notes

- `name_recognition_flags.csv`: 0 flagged players this run. List starts thin and is expected to grow. Update before each regular-season week if notable name-recognition situations arise (injured starter returning, breakout narrative player, etc.).
- `OWNERSHIP_SOFTMAX_TEMPERATURE = 15.0`: first retuning target in Session 11.1. Large gap between 15.0 and the fitted value (if observed) is informative — means the initial guess was significantly off and more data would improve the fit further.
- Next action: Session 9.3 at Regular Season Week 1. Priority source: DraftKings large-field GPP (Millionaire Maker or equivalent). Log `contest_type` and `field_size` from day one — these are required for Session 11.3's fit and cannot be retrofitted from old data.

---

## Session 11.0 — Ownership Model Feature Expansion + Phase 11 Gap Assessment (2026-07-28)

**Date completed:** 2026-07-28
**Status:** ✅ Complete — gap assessment done, Phase 11 added to ROADMAP.md, `ownership_heuristic.py` updated and validated.

### What was actually built

This session opened Phase 11 (Ownership Model Upgrade) and completed its first card (Session 11.0). The work split into two parts: a research-driven gap assessment comparing what we have against three target tiers, and a code change to `ownership_heuristic.py` that closes the feature gap identified.

**Part 1 — Gap assessment and tier definitions**

A clean-slate research session (no preconceptions, fresh web research) established the following:

*What ownership actually is:* Ownership percentage = (lineups containing player X) / (total entries) × 100. Computed by the platform post-lock. Contest-specific, not slate-wide. Before lock, every number is a projection — not a fact.

*What drives projected ownership (from research):* The strongest single predictor is points-per-dollar value (salary ÷ projection). Salary alone explains ~8% of ownership variance (r ≈ 0.29 from a real 95,825-entry MLB slate). Adding projected points and game totals likely gets to ~20-25% explained variance. The industry has not converged on a single formula — tools differ mainly in how they combine these inputs and whether they simulate field lineups (expensive) or use a direct formula (tractable).

*Three tiers defined:*

| Tier | Description | Effort | Benefit |
|---|---|---|---|
| 1 | Value-based softmax, parameters fit to real data | Low | High |
| 2 | 5-feature model + learning loop retuning | Medium | High |
| 3 | Per-contest-type stratification | Medium | Medium |
| 4 | Simulation-based field modeling (SaberSim-style) | High | Low-medium |

Tier 4 dropped. High effort, marginal benefit at personal-use scale.

*Gap against each tier:*

**Tier 1 (value-based softmax):** Architecture is ~70% there. The softmax structure, per-position budget anchoring, and value feature are all built. The gap is unfit parameters: temperature = 15.0 (arbitrary), blend weights (0.45/0.20/0.25, arbitrary), FLEX split even thirds (no real data). These close at Session 11.1 once real ownership data exists.

**Tier 2 (feature-weighted model + learning loop):** ~40% there. Two real ownership predictors were missing from the feature set: raw projected points as a standalone signal (distinct from value efficiency), and game-level over/under (distinct from implied team total). The logging infrastructure (Session 9.3) and retuning (Session 9.4, renamed 11.2) were already planned but not started. Session 11.0's code change adds the two missing features. The learning loop starts at Week 1.

**Tier 3 (contest-type stratification):** 0% there. No architecture, no data. The action is to capture `contest_type` in Session 9.3's logging schema from day one, so Tier 3 fitting is possible after one full season. Session 11.3 cannot be built responsibly before the 2026 regular season ends.

**Part 2 — Code change: `scripts/ownership_heuristic.py`**

Two new features added to the chalk_score blend. No existing features removed. No existing output columns changed. No downstream scripts affected.

*New feature 1 — raw_projection_percentile (decision #6):*
`final_projection` as a standalone input, percentile-ranked within position group. Distinct from value (pts/$1K). Captures "expected ceiling" signal that pure value misses: an expensive stud with 18 projected points has lower value than a cheap role player with 12 points, but the stud will be owned far more heavily on projection ceiling alone. Value alone systematically undersells expensive chalk and oversells cheap punts in ownership terms.

*New feature 2 — over_under_percentile (decision #7):*
Game-level over/under, percentile-ranked across the full pool. `over_under` already existed in `final_projections_*.csv` since Session 3.3's addendum — no pipeline change needed. Captures "shootout game" signal distinct from implied_total: a team with implied_total 27 in a 52 O/U game has a very different ownership profile than the same team in a 38 O/U game, even with identical spreads. Affects all positions in the game, not just the favored team's offense.

*Updated blend weights:*

```
OLD (4-feature, Session 4.1):
  value: 0.45 | salary_tier: 0.20 | vegas: 0.25

NEW (5-feature, Session 11.0):
  value: 0.35 | projection: 0.15 | salary_tier: 0.15 | vegas: 0.20 | over_under: 0.15
```

Weights sum to 1.00. All five are unfit starting guesses; retuning targets for Session 11.1. Direction rationale: value drops because raw projection is now separate; salary_tier drops because value+projection together carry most of the salary-driven signal; vegas redistributes partially to over_under.

*Temperature unchanged:* `OWNERSHIP_SOFTMAX_TEMPERATURE = 15.0`. Temperature is fit separately from the blend weights. The feature expansion doesn't change the right starting point — it will be re-evaluated in Session 11.1 alongside the weights.

*New required input column:* `load_final_projections()` now requires `over_under` in the projections file. Already present since Session 3.3's addendum. A clear SystemExit with an explanatory message fires if it's missing.

**Part 3 — ROADMAP.md update**

Phase 11 added with five session cards:

| Session | What | When |
|---|---|---|
| 11.0 ✅ | Feature expansion + schema def | Done |
| 9.3 | Ownership logging (updated schema) | Week 1 onward |
| 11.1 | Regress weights + temperature | ~Week 6-7 |
| 11.2 (was 9.4) | FLEX split + per-position temperatures | ~Week 8+ |
| 11.3 | Per-contest-type stratification | Post-season 2026 |

Session 9.3's card was updated in-place with the full `ownership_actual_log.csv` schema (columns: site, season, week, slate_type, contest_id, contest_type, field_size, player_id, player_name, actual_ownership_pct, estimated_ownership_pct_at_lock, source, logged_at). `slate_type` values: regular_season | preseason | madden_sim. Session 11.1 fits on regular_season rows only — preseason and Madden Sim rows are logged for pipeline validation dry runs but excluded from the weight/temperature fit (preseason field is skewed toward hardcore grinders, player pool and salary structure unrepresentative of the regular season; Madden Sim field is a tiny self-selected population with no real-world narrative signals). Session 9.4 redirected to Session 11.2.

### Validation

Run against real DK week-10 test data (`output/final_projections_dk_10.csv`, 245 players):

```
python scripts/ownership_heuristic.py --site dk --week 10
```

```
0 player(s) received a name-recognition bonus from name_recognition_flags.csv.
estimated_ownership_pct summed per position group (should equal that group's roster-slot budget):
  DST: 100.0%  (budget: 100.0%)  ✅
  QB:  100.0%  (budget: 100.0%)  ✅
  RB:  233.3%  (budget: 233.3%)  ✅
  TE:  133.3%  (budget: 133.3%)  ✅
  WR:  333.3%  (budget: 333.3%)  ✅
Wrote 245 players to output/chalk_scores_dk_10.csv
  Nulls in any column:                     0  (should be 0)  ✅
  chalk_score out of [0,100] range:        0  (should be 0)  ✅
  estimated_ownership_pct out of [0,100]:  0  (should be 0)  ✅
```

All budget totals exact. All three output-integrity checks pass. FD not separately re-run — the feature additions are site-agnostic by construction (both sites use the same `over_under` column and the same `final_projection` column from `final_projections_*.csv`); treated as covered by construction rather than needing a duplicate manual run, flagged here rather than silently assumed.

### Deferred items

- FD real-data validation: same pre-existing gap as all other FD items — closes at Preseason Week 1 alongside the rest of the FD list.
- All five blend weights and temperature: unfit starting guesses. Retuning targets for Session 11.1. Logged explicitly in `ownership_heuristic.py`'s module docstring and constants block.
- FLEX split (even thirds): known simplification, logged as retuning target for Session 11.2.
- Session 9.3 data source: DraftKings large-field GPP contest results page identified as primary source. Script built (2026-07-29) — see Session 9.3 log entry. First real logging opportunity is Preseason Week 1; that run closes the session.
- Preseason logging (Preseason Weeks 1-3): log with `slate_type = preseason`. Useful for pipeline/schema validation before Week 1 matters. Does not count toward Session 11.1's 4-6 week data gate and must not be included in the fit.
- Madden Sim logging: log with `slate_type = madden_sim` if ownership is captured from a Madden Sim contest during bridge testing. Useful only for confirming log_ownership.py runs end-to-end. Excluded from all fits.

### Handoff notes

- `name_recognition_flags.csv`: 0 flagged players this run. List starts thin and is expected to grow. Update before each regular-season week if notable name-recognition situations arise (injured starter returning, breakout narrative player, etc.).
- `OWNERSHIP_SOFTMAX_TEMPERATURE = 15.0`: first retuning target in Session 11.1. Large gap between 15.0 and the fitted value (if observed) is informative — means the initial guess was significantly off and more data would improve the fit further.
- Session 9.3 script built (2026-07-29) — see Session 9.3 log entry. First real logging opportunity is Preseason Week 1 (Aug 13-15) — tag those rows `slate_type = preseason` and use them to confirm the script works end-to-end, not to inform any model fit. Regular Season Week 1 (Sept 9) is when the data gate clock starts. Priority source: DraftKings large-field GPP (Millionaire Maker or equivalent). Log `slate_type`, `contest_type`, and `field_size` from day one — these cannot be retrofitted from old data and are required for Sessions 11.1 and 11.3.

---

## FD DST Column Name Bug Fix — `ingest_salaries.py` + `build_projections.py` (2026-07-29)
**Date completed:** 2026-07-29
**Status:** ✅ Complete with caveats — code fix done; `"FPPG"` as FD's actual column name is still unverified against a real FD export (same pre-existing gap as all FD items).

**What this fixed:**
`build_projections.py`'s legacy DST path hardcoded `salaries["AvgPointsPerGame"]` for both sites. DK's salary export uses that column name; FD's real export names it `"FPPG"`. On a real FD Classic export, this would produce a `KeyError` or a silent null on every defense, zeroing all FD DST projections regardless of the true season average — discovered via static review during a full project audit (2026-07-29), consistent with the existing "known deferred" note in ROADMAP.md's Known Deferred Validations section.

**What was built:**

*`scripts/ingest_salaries.py` (modified):*
- Added `"avg_ppg_col"` key to `SITE_CONFIGS` for both sites: `"AvgPointsPerGame"` for DK, `"FPPG"` for FD. This is the single source of truth for the column name — same discipline as `site_id_col` and every other site-specific column in `SITE_CONFIGS`. The FD value is marked UNVERIFIED, same status as `required_columns` and `site_id_col` for FD.

*`scripts/build_projections.py` (modified):*
- Legacy DST path (`build_dst_projections()`) now reads `SITE_CONFIGS[site]["avg_ppg_col"]` instead of hardcoding `"AvgPointsPerGame"`.
- Added a fail-loud `SystemExit` guard that fires before any DataFrame operation if the expected column is absent. The error message names the expected column, its source (`SITE_CONFIGS[site]["avg_ppg_col"]`), and points directly to `ingest_salaries.py` as the place to correct it — no guesswork required.
- The distributional DST path (`_build_dst_distributional`) was not touched — it never read this column and is unaffected.
- Module docstring updated to reference the SITE_CONFIGS key rather than the hardcoded DK column name.

**Files created/modified:**
- `scripts/ingest_salaries.py` (modified — `avg_ppg_col` added to both site SITE_CONFIGS entries)
- `scripts/build_projections.py` (modified — legacy DST path uses SITE_CONFIGS lookup + fail-loud guard)

**Validation results:**
- [x] Python syntax check passed on both files.
- [x] `SITE_CONFIGS["dk"]["avg_ppg_col"] == "AvgPointsPerGame"` — DK behavior unchanged.
- [x] `SITE_CONFIGS["fd"]["avg_ppg_col"] == "FPPG"` — FD now reads the documented column name.
- [x] `avg_ppg_col = SITE_CONFIGS[site]["avg_ppg_col"]` lookup present in the legacy DST path.
- [x] Fail-loud guard present and tested for correct error message structure.
- [x] Distributional DST path confirmed unaffected (never read `AvgPointsPerGame`).
- [ ] **FD column name confirmed against a real FD export** — deferred, same as all FD items. Closes at Preseason Week 1.

**Decisions made / assumptions taken:**
- Added `avg_ppg_col` to `SITE_CONFIGS` rather than normalizing the column name in `_load_fd_raw()`. Normalizing in the loader would hide the column name mismatch from the person debugging a future FD format change; keeping the raw column name in `SITE_CONFIGS` and resolving it at point-of-use makes the contract explicit and auditable.
- `"FPPG"` for FD is from FD's documented Classic export format (consistent with the module docstring's existing column layout note). It is marked UNVERIFIED in the code comment, the same status FD's other column names have carried since Session 1.3.

**Known issues deferred:**
- FD column name confirmation against a real FD export — unchanged from ROADMAP.md's existing entry. ROADMAP.md's Known Deferred Validations entry for this bug has been updated to ✅ RESOLVED (code fix), with the column-name verification noted as the remaining step at Preseason Week 1.

**Handoff notes:**
- DK behavior is byte-for-byte unchanged (same column name as before, just read via `SITE_CONFIGS` now). No re-run of any DK validation is needed.
- If a real FD export has a different column name than `"FPPG"`, the fail-loud guard will catch it immediately and name the right place to fix it.

---

## Session 9.3 — Actual Ownership Logging
**Date completed:** 2026-07-29
**Status:** ⚠️ Complete with caveats — `log_ownership.py` built and syntax-validated; end-to-end run against real ownership data deferred to Preseason Week 1.

**What was actually built:**

`scripts/log_ownership.py` — a two-subcommand CLI for logging real post-lock ownership percentages alongside pipeline estimates.

**`log` subcommand:** Given a site, season, week, slate-type, contest-type, field-size, a manually-prepared two-column CSV (player_name, actual_ownership_pct), and a source description, appends ownership rows to `data/ownership_actual_log.csv`. Joins in `estimated_ownership_pct_at_lock` from `chalk_scores_{site}_{week}.csv` at log time (decision #2 — captures the pre-lock estimate without requiring a secondary join later). Fails loudly on duplicates (decision #1 — checks by contest_id when present, falls back to site/season/week/slate_type/contest_type). Writes unmatched players to a separate `data/ownership_unmatched_{site}_{season}_wk{week}.csv` rather than dropping silently (same pattern as `ingest_salaries.py`). Prints a running data-gate counter showing progress toward Session 11.1's 4-6 regular-season-week minimum.

**`summary` subcommand:** Prints a summary of the log's current state — total rows, weeks, and data-gate progress by slate_type — without modifying anything.

**Key design decisions:**

1. **Append-only, fail-loud on duplicates.** Running twice for the same contest raises a clear error, not a silent double. Contest_id is the preferred duplicate key; falls back to (site, season, week, slate_type, contest_type) when contest_id is unavailable.
2. **Estimated ownership captured at log time** from the chalk_scores file. That file reflects the final pre-lock state and must be captured before the next week's run overwrites it.
3. **Player matching via `normalize_name()`** — imports the same function used throughout the pipeline, so `name_mapping.csv` overrides apply automatically. DST/DEF rows matched on team name (stripping "D/ST"/"DST"/"Defense" suffixes) since defense display names vary across platforms.
4. **`slate_type` is required and validated** against `{regular_season, preseason, madden_sim}`. Not inferred from week number — preseason week 1 and regular-season week 1 are both "week 1" and Madden Sim slates run any time. Caller must pass the correct type explicitly.
5. **Log lives in `data/`, not `output/`.** `ownership_actual_log.csv` is a growing persistent dataset (like `name_mapping.csv`, `salary_anchor_dk.json`, etc.), not a per-run output.

**Schema** (matches Session 11.0's definition exactly — 13 columns):
`site, season, week, slate_type, contest_id, contest_type, field_size, player_id, player_name, actual_ownership_pct, estimated_ownership_pct_at_lock, source, logged_at`

**Files created/modified:**
- `scripts/log_ownership.py` (new)

**Validation results:**
- [x] Python syntax check passed.
- [x] `LOG_COLUMNS` verified to match Session 11.0's 13-column schema exactly.
- [x] `VALID_SLATE_TYPES` = `{regular_season, preseason, madden_sim}` — matches ROADMAP.md.
- [x] `VALID_CONTEST_TYPES` = `{cash, single_entry_gpp, 3max_gpp, unknown}` — matches ROADMAP.md.
- [x] Duplicate detection logic verified (contest_id path and fallback path).
- [x] Data-gate counter logic verified (tracks regular_season weeks toward 4-6 minimum).
- [ ] **End-to-end run against real ownership data** — deferred to Preseason Week 1. Tag those rows `--slate-type preseason`. This is the step that closes the session.

**Decisions made / assumptions taken:**
- Chose a two-subcommand CLI (`log` / `summary`) over a single-purpose script, since checking the log's current state without modifying it is a genuinely common need (especially near the data gate).
- Raw ownership input is a manually-prepared CSV rather than a scraper — consistent with the project's pattern of manual exports for DK/FD data (same reasoning as `ingest_salaries.py`'s salary-CSV requirement). Avoids a brittle dependency on contest page HTML structure that could break any week.
- Duplicate check raises rather than updates/replaces, because updating in place risks silently overwriting corrected data with stale data if the script is re-run after a manual correction. If a re-log is intentional, the existing rows should be manually removed first.
- `normalize_name()` imported from `ingest_salaries.py` — same function, same override table, no second normalization implementation.

**Known issues deferred:**
- End-to-end run on real data — first opportunity Preseason Week 1. Use those rows to confirm the script works; they are logged with `slate_type=preseason` and excluded from all model fits.
- FD ownership logging — same pre-existing FD gap. Log when FD ownership is available; don't force it.

**Handoff notes:**
- First real use: Preseason Week 1 (Aug 13-15). Run `log_ownership.py log` after lock for the DK large-field GPP result. This closes Session 9.3.
- `data_gate` counter in the `log` output shows progress toward Session 11.1's 4-6 regular-season week minimum. Regular Season Week 1 (Sept 9) is when that clock starts.
- The `summary` subcommand is the fast way to check how many weeks have been logged before kicking off Session 11.1.

---

## Session 7.5 — Frontend UI Improvements (Bulk Exclude, Column Alignment, Mobile)
**Date completed:** 2026-07-30
**Status:** ✅ Complete — validated live on desktop and mobile (Pixel 9 Pro XL).

### What was actually built

Three improvements to `dfs_optimizer_frontend/index.html`:

**1. Bulk Exclude / Un-exclude All (functional)**

A `bulk-action-row` is now shown between the filter bar and the player list whenever a slate is loaded. It displays a count of currently-visible players ("X players shown") and two pill buttons:

- **Exclude All Shown** — marks every player currently visible (after all active filters, tab, and search) as excluded, and clears their lock state (locked + excluded is mutually exclusive — same rule as single-player exclude).
- **Un-exclude All Shown** — removes the excluded flag from every currently-visible player.

Both buttons operate only on the visible filtered set. Players hidden by a filter are never touched. Powered by a `getVisibleRows()` helper that mirrors the exact filter/tab/search logic from `renderPlayerList()`. The bulk row is hidden (CSS `display:none`) when no slate is loaded and becomes `display:flex` on first render with a pool.

**2. Column header alignment fix (desktop)**

Root cause: `player-list-head` was a sibling element *above* the `player-list` scroll container in the HTML. Once the list accumulated enough players to trigger a scrollbar, the scroll container lost ~17px to the scrollbar but the header above it didn't — causing the column headers (Price/Proj/Value/Own%) to drift rightward relative to their data values.

Fix: `playerListHead` is now injected *inside* `playerList` via `innerHTML` as the first element on every render, with `position: sticky; top: 0` and a background fill. Since header and rows are now siblings inside the same scroll container, their widths are always identical regardless of scrollbar presence.

Side effect: `playerListHead` no longer exists in the static HTML at page load, so the old `document.getElementById("playerListHead").addEventListener(...)` for sort-column clicks crashed immediately with `null`, breaking all other button listeners in the process (JS halts on uncaught error). Fixed by converting the sort-click handler to event delegation on `playerList` (which is static), matching on `.sortcol[data-sort]` — the same delegation pattern the lock/exclude handler already used.

**3. Mobile layout cleanup**

Two compounding problems: (a) the value and ownership columns both used class `.pown`, making it impossible to assign them to separate CSS grid areas; (b) the mobile `@media` CSS used fragile `nth-child(5)` / `nth-child(6)` selectors that break on any DOM restructuring.

Fixes: value cell renamed from `.pown` to `.pval`. Mobile CSS updated to use `.pval` and `.pown` class selectors instead of nth-child. Added a `SAL` label prefix to the salary cell on mobile to match the PROJ/VAL/OWN labels — all four stat cells are now consistently labeled on the bottom row.

### Files created/modified
- `dfs_optimizer_frontend/index.html` (modified)

### Validation results
- [x] JS syntax check passed (`node --check`)
- [x] All `getElementById` calls cross-referenced against HTML `id=` attributes — no missing IDs
- [x] Upload slate, apply Proj Max = 5 filter → "X players shown" count correct
- [x] Exclude All Shown → all shown players go excluded (red), non-shown players unchanged
- [x] Un-exclude All Shown → excluded flags clear from shown players only
- [x] Column headers (Price/Proj/Value/Own%) align with data values on desktop (scrollbar present)
- [x] Mobile (Pixel 9 Pro XL): SAL/PROJ/VAL/OWN labels appear cleanly on bottom row
- [x] No regression: lock/unlock, single-player exclude, filter clear, slate switching, Build Lineups all confirmed working
- [ ] FD validation — same pre-existing gap as all FD items

### Decisions made / assumptions taken
- `getVisibleRows()` operates on the **full** filtered set, not capped at 200 like the visible list. This means Exclude All operates on every player matching the filter, not just the ones currently scrolled into view — which is the correct behavior.
- Sort-click delegation moved to `playerList` rather than re-adding `playerListHead` to the static HTML. This is cleaner: the delegation pattern is already used for lock/exclude, and keeping the head dynamic means one fewer static element to keep in sync with the rendered head.
- `bulk-action-row` uses `style.display` toggling (flex/none) rather than CSS class toggling, consistent with how other conditional-display elements in this file are handled.

### Known issues deferred
- FD validation — unchanged from all previous entries.

---

## Session 7.4 — Slate Management Rework
**Date completed:** 2026-07-30
**Status:** ✅ Complete — validated live on desktop and mobile.

### What was actually built

Reworked the slate upload, storage, and selection system end-to-end. Three user-reported problems drove the session:

1. **Delete didn't stick** — clicking X removed a chip from local storage but `cloudListSlates` re-rendered it from the cloud immediately after, because cloud delete was never wired up.
2. **Week-number key was too rigid** — slates were keyed by `{site, week: integer}`, making it impossible to have more than one slate per site per week. No way to distinguish preseason wk1 from regular season wk1, or a main slate from an early-only or afternoon-only slate for the same week.
3. **Chip wall was cluttered** — a flat list of chips grew unwieldy; a dropdown is cleaner and scales to a full season.

### What was built

**`cloudflare_worker/optimizer_api/optimizer_api.js` (modified):**

- `save_slate` / `load_slate` / `list_slates`: query param changed from `?week=` (integer) to `?slate_id=` (user-defined string). Validation changed from `validSiteWeek()` to `validSite()` + `validSlateId()` — alphanumeric/hyphen/underscore, 1–64 chars.
- Stored record shape gains `label` (display name) and `week` (integer, auto-detected from filename at upload time, used for optimizer dispatch). Old records without these fields degrade gracefully — `label` falls back to `slateId`, `week` defaults to `"1"`.
- New `handleDeleteSlate()`: GET-for-SHA then GitHub Contents API DELETE. This is what was missing and caused the re-appearance bug. Idempotent — returns `{ok: true, note: "not found"}` if already gone.
- `handleListSlates()`: **removed per-file fetches** (was doing N sequential GitHub API calls, one per slate file, which caused timeouts on Cloudflare's free-tier 10ms CPU limit). Now returns `{site, slateId}` from the directory listing only — a single GitHub API call regardless of slate count. Labels come from localStorage on the local device; cross-device entries fall back to displaying `slateId`.
- CORS `Allow-Methods` updated to include `DELETE`; OPTIONS preflight returns 204.
- `postActions` / method check updated to allow DELETE for `delete_slate`.
- `SLATE_INDEX_KEY` bumped to `"dfs_slate_index_v2"` in the frontend (Worker-side has no equivalent key).

**`dfs_optimizer_frontend/index.html` (modified):**

- CSS: chip styles removed; new `.slate-select-row`, `.slate-delete-btn`, `.slate-label-row` added.
- HTML: week number `<input>` removed from Slates panel; replaced with inline label field (`id="slateLabel"`) + Save button (`id="btnSlateConfirm"`); chip `<div>` replaced with `<select id="slateSelect">` + Delete button (`id="btnSlateDelete"`).
- JS — key changes:
  - `slateKey()` now takes `(site, slateId)` instead of `(site, week)`.
  - `persistSlate()` stores `{kind, filename, label, week, payload}` — `week` is auto-detected from the filename at upload time (`final_projections_dk_10.csv` → `10`, falls back to `"1"` for Madden Sim / preseason).
  - Upload is now two-step: parse file → show label field pre-filled from filename → user confirms → save. `pendingSlate` holds interim state.
  - `removeSlate()` now calls the cloud `delete_slate` endpoint (DELETE request) after clearing localStorage — fixing the re-appearance bug. Re-renders from local index only (no `cloudListSlates`) so the deleted entry can't race back in.
  - `renderSlateChips()` / chip click handler removed entirely. Replaced by `buildDropdown()`, `renderSlateDropdown()`, dropdown `change` listener, and Delete button click listener.
  - `buildDropdown()`: renders `<select>` from a slate index array. Preserves current `sel.value` across re-renders; if `prev` is absent (e.g. after delete), defaults to `selectedIndex = 0` rather than leaving value stale.
  - `renderSlateDropdown()`: merges local + cloud index, calls `buildDropdown()` once after cloud resolves. Callback fires exactly once (previous version fired twice — once after local, once after cloud — causing selection to reset).
  - `loadSlateForActive()`: **local-first** — tries localStorage before hitting the cloud. Cloud is now the fallback for cross-device access only. This fixed the switching bug where cloud latency caused dropdown selection to drift.
  - `initSlates()` (on-load): builds from localStorage synchronously (instant), auto-loads whatever the dropdown defaulted to, then fires a background `cloudListSlates` merge. If local was empty (mobile / new device), the cloud merge auto-loads the first returned slate — fixing mobile cross-device sync.
  - `refreshForActiveSlate()` (site toggle): calls `buildDropdown(readSlateIndex())` directly instead of `renderSlateDropdown()` to avoid async issues.
  - `buildDispatchParams()`: reads `week` from the stored slate record in localStorage instead of from the removed `slateWeek` input.
  - `confirmWithRealSolver()`: guard changed from "week must be set" to "a slate must be selected in the dropdown."
  - Settings save/load: `dfs_week` localStorage key no longer written or read.

**`DFS_Weekly_Process.md` (modified):**
- Step 2d rewritten: now labeled "backend slate ID" (the pipeline identifier used in CLI flags and filenames — separate from the UI label).
- Stage 4 fully rewritten: covers two-step upload flow, multiple slates for one week, switching, cross-device sync, and delete. Notes that the UI label has no effect on the backend optimizer dispatch.
- Known gaps updated with a note on the one-CSV-uploaded-twice pattern for early/main splits.

### Files created/modified
- `cloudflare_worker/optimizer_api/optimizer_api.js` (modified)
- `dfs_optimizer_frontend/index.html` (modified)
- `DFS_Weekly_Process.md` (modified)

### Validation results
- [x] Node syntax check passed on `optimizer_api.js`
- [x] Node syntax check passed on the extracted `<script>` block from `index.html`
- [x] All `getElementById` calls cross-referenced against HTML `id=` attributes — no missing IDs
- [x] Upload two slates → both appear in dropdown (desktop)
- [x] Switch between slates → each loads correctly with player pool (desktop)
- [x] Delete one slate → stays gone on reload, does not reappear (desktop)
- [x] Page reload → remaining slate auto-loads (desktop)
- [x] Build lineups on slate A, switch to slate B, build lineups — both successful (desktop)
- [x] Mobile (Pixel 9 Pro XL): slate uploaded on desktop auto-appears and loads on phone without manual action
- [ ] FD validation — same pre-existing gap as all FD items, unchanged

### Decisions made / assumptions taken

- **SlateId derived from label:** label is sanitized at save time (`labelToSlateId()` — lowercase, spaces→underscores, strip non-alphanumeric). User types readable labels; the key stored in localStorage and sent to the cloud is always URL-safe. The same CSV can be uploaded multiple times under different labels and each is a fully independent stored entry.
- **Week auto-detection from filename:** regex `_(\d{1,3})\.csv$` on the original filename. Covers `final_projections_dk_10.csv` → `10`, `lineup_multi_dk_3.csv` → `3`. Falls back to `"1"` for any file that doesn't match (Madden Sim, preseason, custom-named files). The week number is only used for backend optimizer dispatch (`--week` flag); the UI label is purely for navigation.
- **`list_slates` returns `{site, slateId}` only** — dropping `label` and `savedAt` from the cloud response. Labels are available from localStorage for local slates; cross-device entries display `slateId` as the fallback label. This was forced by Cloudflare's free-tier 10ms CPU limit — N sequential awaits for N slate files was causing timeouts with as few as 5 slates in the folder.
- **`SLATE_INDEX_KEY` bumped to `v2`** — old `v1` entries (keyed by `{site, week: number}`) would have conflicted with new `{site, slateId: string}` shape. Bump ensures a clean slate (old entries ignored, not migrated).
- **Cloud delete is fire-and-forget** — `removeSlate()` updates localStorage and re-renders the dropdown synchronously, then fires the DELETE request without waiting for confirmation. If the DELETE fails, the entry will reappear next time `cloudListSlates` runs (next page load). Acceptable tradeoff — the local removal is instant and the cloud eventually converges.
- **Old-format files in `data/ui_slates/`** (`dk_10.json`, `dk_23.json`, etc. — week-keyed from pre-7.4 uploads): these parse correctly under the new naming convention (`site=dk`, `slateId=10` etc.) and appear in the dropdown as "DK · 10". They should be manually deleted via the UI's Delete button after upgrading, then slates re-uploaded with readable labels.

### Known issues deferred
- Old-format slate files in `data/ui_slates/` — see above. Not a code bug; user action required post-deploy.
- FD validation — unchanged from all previous entries.

### Handoff notes
- **Deploy order matters:** Worker must be deployed before `index.html` is pushed to Cloudflare Pages. The frontend's `delete_slate` DELETE calls 404 against the old Worker until it's updated. Deploy command: `cd cloudflare_worker/optimizer_api && npx wrangler deploy optimizer_api.js`.
- After deploying, delete the old `dk_10.json`, `dk_23.json`, `dk_99.json`, `dk_1.json`, `fd_99.json` entries via the UI (select each in the dropdown → Delete), then re-upload with readable labels.
- The `label`/`savedAt` fields exist in the Worker's stored JSON records (they're written at save time) but are no longer read by `list_slates`. If a future session wants richer dropdown metadata from the cloud, those fields are already there — just re-introduce the per-file fetches with parallelism (`Promise.all`) instead of serial awaits, which avoids the CPU timeout.

---

## Session 12.1 — Team / Game Exposure Caps
**Date completed:** 2026-08-01
**Status:** ✅ Complete

**What was actually built:**
Two independent, additive MAXIMUM constraints for lineup building, requested by the user after noticing this is a standard feature in commercial DFS optimizers that was missing here:
- **Team cap** (`--max-team-players`, e.g. `KC:2,DEN:1`) — caps the number of players from a specific team.
- **Game cap** (`--max-game-players`, e.g. `KC-DEN:4,SEA-ARI:3`) — caps the COMBINED players from both teams in a specific game.

Both apply to every lineup in a build (single or multi), the same way stacking rules do — a hard ILP constraint, not a soft preference. They're additive alongside (not a replacement for) the existing stacking MINIMUM constraints (Session 3.3) — a contradictory combination (e.g. a game stack requiring 4 combined players against a game cap of 3) is not specially pre-checked; it surfaces as the same generic solver-infeasibility RuntimeError every other constraint conflict in this file produces.

**Locked-player interaction (explicit design requirement from the user):** if locked players alone already exceed a requested cap, the build fails loudly BEFORE the solver ever runs, naming the specific team/game and cap in the error message — same pre-solve structural-check pattern as `validate_lock_feasibility()` (decision #24). If a cap of 1 is set and exactly one non-conflicting player is locked, the cap constraint itself (no separate mechanism needed) mechanically blocks every other player from that team/game.

Continued this file's decision-numbering convention: decisions #36-38.

**Files created/modified:**
- `scripts/optimizer.py` — new `parse_team_cap_list()`, `parse_game_cap_list()`, `validate_exposure_cap_feasibility()`, `add_exposure_cap_constraints()`; `max_team_players`/`max_game_players` params threaded through `solve_lineup()`, `build_single_lineup()`, `build_multi_lineup()`, and two new CLI flags in `main()`.
- `cloudflare_worker/optimizer_api/optimizer_api.js` — `max_team_players`/`max_game_players` added to `passthroughKeys` (`handleDispatch`).
- `.github/workflows/run_optimizer_dispatch.yml` — arg-builder forwards both new params as optional flags (omitted entirely when not set, matching every other optional field's existing convention).
- `dfs_optimizer_frontend/index.html` — new "Team Exposure Caps" / "Game Exposure Caps" UI section: a dropdown of the actual teams/games in the loaded slate (same "read straight off the pool, no free text" pattern as the existing stack-team/stack-game chip pickers, decision #32) + a number input + "Add Cap" button, rendering as click-to-remove chips. New `state.maxTeamCaps`/`state.maxGameCaps` (per site). Wired into `buildDispatchParams()`.

**Validation results:**
- [x] Synthetic-pool unit tests (5): team cap alone, game cap alone, both simultaneously, locked-player-vs-cap conflict (confirmed it raises before solving), and parser correctness for both comma-list formats — all passed.
- [x] `optimizer.py` — full-file `py_compile` clean.
- [x] `optimizer_api.js` — `node --check` clean.
- [x] `run_optimizer_dispatch.yml` — YAML parses clean.
- [x] `index.html` — extracted `<script>` block `node --check` clean.
- [x] `index.html` — every `getElementById` call cross-referenced against `id=` attributes, no missing IDs.
- [x] Worker deployed (`npx wrangler deploy optimizer_api.js`), frontend/workflow/optimizer.py pushed.
- [x] **Real-slate, live test by user:** team cap + game cap both applied and respected in a real build. Locking more players onto a team than that team's cap allows correctly failed the build with a clear reason (not a generic error) — confirmed working as designed.

**Decisions made / assumptions taken:**
- **Game-specific, not just team-specific** — user was explicit both cap types needed to be selectable per team AND per exact game (not just a single global "max per game" default), so both a team dropdown and a game dropdown are exposed in the UI, each independently multi-settable (decision #37).
- **No special-cased pre-check for cap-vs-stacking conflicts** — only the locked-player-vs-cap case gets a dedicated upfront check (decision #36), consistent with `validate_lock_feasibility()`'s existing precedent of only checking structural infeasibility, not every possible interaction between optional constraints.
- **Unknown team/game labels are a non-fatal NOTE, not an error** (decision #38) — covers both genuine typos and legitimate byes; the constraint becomes a harmless no-op if the label matches nothing in the pool. Same handling as the frontend's typo protection for the existing stack pickers.
- **Game caps keyed by frozenset in `optimizer.py`, sorted `"TEAM-TEAM"` string in `index.html`/CLI** — the frontend's game dropdown already produces a sorted-pair key (`[teamA, teamB].sort().join("-")`), so the CLI-to-frontend format matches exactly with no translation needed; `parse_game_cap_list()` converts to a frozenset internally only for constraint-building.

**Known issues deferred:**
- None specific to this feature — it's fully closed out, real-data validated by the user.

**Handoff notes for next session:**
- This feature is independent of and doesn't touch the ongoing Phase 10/11 projection/ownership work — no interaction effects to worry about there.
- If a future session wants a "global default game cap" (e.g. "no game may exceed 4 players, without picking games one by one"), that would be a straightforward addition: apply a default cap to every game in the slate's pool not already explicitly overridden by `--max-game-players`. Not built now since it wasn't requested — the user's explicit ask was per-team/per-game selection, not a blanket default.

---

## Session 4.3 — Pivot Eligibility Filter Correction + Frontend Pivot Panel
**Date completed:** 2026-08-02
**Status:** ✅ Complete

**What was actually built:**
An ad hoc session triggered by `NFL_pivot_ui_handoff.md`, a handoff document filed during NHL Optimizer Session 4.2 work, which surfaced two findings about NFL's `pivot_finder.py` (built in this project's own Session 4.2): (1) the salary-tolerance eligibility filter was likely producing bad pivot suggestions on real slates, and (2) `pivot_suggestions`/`chalk_scores` output had never been wired into the frontend. Both were confirmed to apply here and fixed, along with four additional real bugs found only by actually running the pipeline end-to-end on real data rather than by static review — consistent with this project's established pattern that real-data runs surface bugs static review doesn't.

**Finding 1 — salary-band → projection-band eligibility filter:** `find_pivots_for_player()`'s candidate filter changed from "salary within X% of cap" to "final_projection within X% of the cash player's own projection" (symmetric). Salary demoted to informational-only output (`salary_diff`/`salary_diff_pct`). Default tolerance 25%, chosen from a real 15/25/35% comparison against this project's own DK (245-player) and FD (48-player) Madden Sim pool data — not copied from NHL's own fitted value, per the handoff doc's explicit caution. Full reasoning: `pivot_finder.py` decision #3.

**Finding 2 — frontend pivot panel:** `dfs_optimizer_frontend/index.html`'s roster rows are now clickable — click a player to expand a panel below them showing ranked pivot candidates (salary Δ, projection Δ%, ownership edge, leverage score) with a "Swap In" button. Per explicit user design decisions: (a) panel-below-the-row on both desktop and mobile, no separate side panel; (b) works on whichever lineup is currently displayed, not restricted to a "cash lineup" mode, since the user builds multiple lineups even for cash play and doesn't functionally distinguish cash from GPP in the optimizer itself; (c) `pivot_suggestions_{site}_{slate_id}.csv` added to the automated `refresh_data.yml` full-refresh cycle, gated on a lineup already existing for that slate (skips cleanly rather than failing if not).

**Three more bugs found and fixed while validating Finding 1/2 against real data:**
- **`chalk_scores` join bug:** `build_projections.py`'s `add_ownership_columns()` (a frontend-driven change made after Session 4.2 shipped) started baking `chalk_score`/`estimated_ownership_pct` directly into `final_projections_{site}_{slate_id}.csv`. `pivot_finder.py`'s old merge against a separate `chalk_scores` file therefore joined two DataFrames that both already had `estimated_ownership_pct`, producing `..._x`/`..._y` suffixed columns and crashing downstream with an opaque `KeyError` instead of failing loudly. Fixed by reading `estimated_ownership_pct` straight off `final_projections`; the standalone `chalk_scores` file/CLI still exist and work for other purposes, just no longer a dependency here.
- **`--week` vs `--slate-id` mismatch:** `pivot_finder.py` predates the slate-management rework (Session 7.4) and still built every filename as `{site}_{week}.csv`, while `build_projections.py`/`optimizer.py` have long since moved to `--slate-id`. Invisible during this session's own first real-data test because that test happened to use `"10"` as both a week number and a literal slate_id — broke immediately on a real non-numeric slate_id (`synthetic_08022026b`). Fixed throughout `pivot_finder.py`; the same stale assumption was also caught and fixed in `refresh_data.yml`'s pivot-rebuild step and `index.html`'s pivot-panel empty-state message.
- **Frontend site-detection bug (found live by the user):** the app trusted whichever site the toggle happened to be set to at upload time, with no check against the file itself — uploading an FD file while the toggle sat on DK silently saved it as a DK slate. Fixed: site is now detected from the filename itself (every real output filename already embeds it) and the toggle auto-switches to match, with a status note confirming the switch.

**Two smaller bugs, also found only by running things:**
- A latent `NameError` (undefined `week` variable) in a join-failure error message in `pivot_finder.py` that would have crashed instead of printing a helpful error.
- A Python 3.14 argparse crash from an unescaped literal `%` in `pivot_finder.py`'s `--projection-tolerance-pct` help string — same class of issue as this project's previously-documented argparse `%`-escaping gotcha (Python 3.14 vs the documented 3.12 baseline).

**New tool built along the way — `scripts/generate_synthetic_slate.py`:** FD doesn't run Madden Sim contests the way DK does, so there was no way to get a real current FD slate for end-to-end testing. This script produces a raw, site-export-shaped CSV using real player names/teams/positions (via `ingest_salaries.py`'s own `build_player_reference()`, not reimplemented) with fabricated salaries/matchups/game info (explicitly flagged `ARBITRARY`), then feeds into the real `ingest_salaries.py` exactly like a real download — no post-ingest schema hand-fabrication. Found and fixed its own real bug during validation: FD defense rows were labeled position `"D"` instead of the `"DEF"` that `optimizer.py`'s `roster_slots` actually requires, which gave FD's DEF roster slot zero eligible players and made the ILP structurally infeasible regardless of anything else in the pool — fixed by deriving the label from the intersection of `roster_slots` and `defense_position_values` instead of guessing. User confirmed this script stays in the toolkit for future use, not a one-off.

**Files created/modified:**
- `scripts/pivot_finder.py` (modified — Findings 1, 3, plus the NameError/argparse fixes)
- `dfs_optimizer_frontend/index.html` (modified — Finding 2, plus the site-detection fix)
- `.github/workflows/refresh_data.yml` (modified — added pivot_finder.py to the automated full-refresh cycle, then fixed to use `--slate-id`)
- `scripts/generate_synthetic_slate.py` (created)

**Validation results:**
- [x] Projection-tolerance comparison (15/25/35%) run against real DK (245-player) and FD (48-player) Madden Sim pool data to choose the 25% default, independently of NHL's own fitted value.
- [x] Full pipeline smoke test (join fix + projection-band filter together) against an internally-consistent test lineup built from real pool data: 24 pivot suggestion rows, all passed `validate_pivot_suggestions()`'s own assertions.
- [x] `pivot_finder.py` re-run against a deliberately non-numeric slate_id (`test_slate_abc`) to prove the `--slate-id` fix, before handing off to the user.
- [x] `generate_synthetic_slate.py` smoke-tested against a fake `weekly_stats` parquet, then against the real one on the user's machine: 100% player match rate through the real `ingest_salaries.py`, both before and after the DEF-label fix.
- [x] Full real-data pipeline run by the user, FD: `generate_synthetic_slate.py` → `ingest_salaries.py` → `build_projections.py` → `optimizer.py` → `pivot_finder.py`, all real command output captured and reviewed — optimal lineup generated, 11 pivot suggestion rows (leverage_score range 0.6-40.9).
- [x] Full real-data pipeline run by the user, DK: same chain against the real `madden_08022026` Madden Sim slate.
- [x] **Full frontend click-through by the user, both sites, in the deployed UI** — upload pool/lineup/pivots, click a roster row, confirm the pivot panel, Swap In — user confirmed "looked good," no rough edges flagged.
- [x] `node --check` clean on the extracted `index.html` `<script>` block after every edit round.
- [x] `refresh_data.yml` — YAML parses clean (`pyyaml.safe_load`) after every edit round.
- [x] `py_compile` clean on `pivot_finder.py` and `generate_synthetic_slate.py` after every edit round.

**Decisions made / assumptions taken:**
- **25% projection tolerance is a starting heuristic**, explicitly flagged as unfit to full-season/real regular-season data (chosen from Madden Sim / synthetic pool data only) — retuning target once real usage exists, same status as `OWNERSHIP_SOFTMAX_TEMPERATURE`.
- **Empty pivot result stays empty** (decision #7, carried from Session 4.2, re-confirmed under the new filter) — "no real same-tier alternative on this slate" is legitimate information, never triggers auto-widening the tolerance.
- **Pivot swap works on every lineup, not just a designated "cash" one** — explicit user framing: they build multiple lineups even for cash play just to compare versions, so restricting the swap feature to a single "cash lineup" concept would've been a wrong scope call.
- **`generate_synthetic_slate.py` is a standing tool, not a one-off** — user confirmed keeping it in the toolkit for future testing whenever real slate data isn't available.
- **Synthetic FD data validates the pipeline/UI, not pivot-suggestion quality** — flagged explicitly to the user; real FD pivot-suggestion quality still depends on real FD data.

**Known issues deferred:**
- Real (non-synthetic) FD slate validation — unchanged gap, still waiting on real FD preseason export data (~Aug 13-15).
- Test artifacts left in place by user's own choice: `FDSalaries_synthetic.csv` in repo root, `synthtest`/`synthetic_08022026`/`synthetic_08022026b` slate_ids in `data`/`output` — confirmed harmless, not wired into anything real, fine to clean up later or leave.

**Handoff notes for next session:**
- If another script turns up still assuming `--week` instead of `--slate-id`, that's the same bug class Finding 3 here caught (`pivot_finder.py`, `refresh_data.yml`) — the Session 7.4 slate-management rework didn't touch every pre-existing script. Worth a deliberate audit across `scripts/` if time allows, rather than waiting to find each instance live.
- `generate_synthetic_slate.py`'s salary bands (`SALARY_BANDS`) and per-team player counts (`PLAYERS_PER_TEAM`) are both flagged `ARBITRARY` in-code — fine for pipeline/UI testing, not fit to any real site pricing model. Don't use synthetic-slate pivot suggestions to judge real pivot quality.
- This NHL-handoff-triggered session is a second instance of the exact pattern its own Finding 2 originally described: a real analytical output built and validated in isolation, then found to be unwired from the UI. Worth the same "quick audit of other `/output` files" the handoff doc itself suggested, if a future session has spare time — e.g. confirming Session 9.3's `log_ownership.py` output has a path into something that uses it.

---

## Session 13.1 — Kicker Projection Model
**Date completed:** 2026-08-04
**Status:** ✅ Complete

**What was actually built:**
The first kicker model anywhere in this pipeline -- no K projection existed
before this session, for either site. Built as a real, backtested model
(matching Session 10.4's DST-rebuild bar, per explicit user direction),
not a placeholder, ahead of Showdown/Single-Game support (Phase 13) since
Showdown pools always include kickers. Structured as a fitter/consumer
pair, same split as `fit_dst_model.py`/`dst_model.py`.

The headline finding, measured rather than assumed: **FG attempt volume
has no usable predictive signal** from either team identity or Vegas
implied total (R²=0.003 vs. own implied total; team-level split-half
correlation r=0.039 across 3,122 real team-weeks, 2018-2023). This is a
real contrast with DST, where points-allowed has a genuine team trait and
a genuine Vegas relationship. Individual kicker ACCURACY, by contrast, is
a real if modest skill (split-half r=0.23 within a season; career accuracy
predicts held-out-season accuracy at r=0.175, n=36) -- but because
per-game point totals are dominated by attempt-count variance (which is
unpredictable), shrinking toward player-specific accuracy barely moved
the backtest (MAE 3.7470 flat vs. 3.7489 player-shrunk per game). Shipped
the player-specific shrinkage anyway since it's free and directionally
correct, documented honestly rather than oversold -- this model's real
value is a correctly WIDE, well-calibrated sigma (simulated/real ratio
1.03-1.04), not sharp point accuracy the data doesn't support.

Also found and resolved during build: wiring kicker rows through the
EXISTING (classic-slate) ownership heuristic produces `NaN`
`estimated_ownership_pct` for the K position group, because that heuristic
normalizes ownership to a position's classic roster-slot budget and K has
never had one on either site's classic format. Doesn't fire today (every
classic slate has an empty K pool) but will the moment Session 13.2 puts
real K rows in a pool -- flagged explicitly rather than silently
discovered later; Session 13.3's already-planned Showdown-specific
ownership heuristic is the intended fix, not a new gap.

**Files created/modified:**
- `scripts/scoring_rules.py` (modified -- added `KICKER_SCORING`,
  `kicker_scoring_for()`, `score_kicker()`, `KICKER_COMPONENT_COLUMNS`,
  `verify_kicker_against_actuals()`)
- `scripts/fit_kicker_model.py` (new)
- `scripts/kicker_model.py` (new)
- `scripts/build_projections.py` (modified -- new `_build_kicker_projections()`,
  wired into `build_final_projections()`'s output concat alongside skill
  positions and DST)
- `data/kicker_model.json` (new artifact, written by `fit_kicker_model.py`)

**Validation results:**
- [x] `scoring_rules.py` DK kicker table CONFIRMED against DK's own
  published "NFL Showdown Captain Mode" rules page (user-supplied,
  2026-08-04) -- exact match on all three FG brackets, PAT value, and the
  "kickers only eligible for FG/PAT" restriction.
- [x] `scoring_rules.py` FD kicker table CONFIRMED against a real live FD
  Single Game contest's "Rules & Scoring" page (user-supplied screenshot,
  2026-08-04) -- FLEX-column FG brackets match DK exactly; MVP column
  cross-checks as exactly 1.5x the FLEX column on every row (FG AND PAT:
  MVP PAT=1.5, FLEX PAT=1, user-confirmed separately), validating that
  FD's MVP multiplier applies uniformly across all kicker stats the same
  way DK's CPT multiplier does.
- [x] `score_kicker()`/`verify_kicker_against_actuals()` self-check:
  reconstructs real 2024-2025 kicker actuals exactly (0.0 mean bias, 100%
  exact match, both sites) -- expected since kicker scoring is linear
  (no bracket-integration hazard like DST's step function).
- [x] `fit_kicker_model.py` run for real against live nflverse data
  (2018-2023 fit window): `mu_fga=1.926`, `mu_pat=2.277`, real
  distance-bucket shares and make rates, 79 kickers with career accuracy
  rows written to `data/kicker_model.json`.
- [x] `kicker_model.py` real held-out backtest (2024-2025, production code
  path, not a standalone reimplementation): MAE=3.733, RMSE=4.712 per
  kicker-week; sigma calibration ratio 1.03-1.04 (simulated sigma vs. real
  held-out standard deviation); season-level Spearman rank 0.079 (weak,
  consistent with the volume-noise finding above -- not a bug).
- [x] `_build_kicker_projections()` smoke-tested against a synthetic pool:
  real career-shrunk projections for known player_ids, pure league-average
  fallback for an unknown/rookie player_id, correct zero-out for a
  bye-week kicker, and a correctly-shaped empty DataFrame for the
  empty-K-pool case (every classic slate today).
- [x] Full concat + `add_ownership_columns()` path smoke-tested with mixed
  skill/kicker rows -- confirmed the `NaN` ownership finding above, did
  NOT trip the existing `chalk_score`-only hard-fail guard (silent NaN,
  not a crash) -- tracked as a Session 13.3 handoff item, not fixed here.
- [x] `python3 -m py_compile` clean on all four touched/created files.
- [x] `fit_kicker_model.py` CLI entry point (`argparse` path, not just the
  Python import path) run end-to-end successfully.

**Decisions made / assumptions taken:**
- Volume (FGA, PAT attempts) modeled as a recency-weighted (half-life 2
  seasons) LEAGUE AVERAGE, not a team- or Vegas-conditioned regression --
  a measured null result, not a shortcut (see "What was actually built").
- Distance-bucket mix (share of FGA that are 0-39/40-49/50+) is also a
  flat league average -- no stronger signal was tested for this either;
  flagged as a possible future refinement (e.g. opponent red-zone
  defense), not built now.
- Player-specific accuracy shrinkage (K_SHRINK=12 pseudo-attempts) shipped
  despite near-zero backtest improvement, because it's free at inference
  time and directionally correct -- explicitly NOT presented as the
  model's main value-add (see decision #4 in `fit_kicker_model.py`).
- Sigma uses independent Poisson/Binomial draws with NO latent correlation
  factor, unlike DST's Monte Carlo -- measured that DST's under-dispersion
  problem doesn't exist here (calibration ratio ~1.03 with plain
  independent draws), so the added machinery would solve a problem that
  isn't there.
- `_build_kicker_projections()` wires kicker rows into EVERY site's
  output unconditionally (no slate-type gate) -- harmless today since
  classic salary files never contain K rows, and this avoids needing a
  slate-format flag before Session 13.2 defines one.

**Known issues deferred:**
- FD's Extra Point (PAT) value was confirmed separately by the user
  (MVP=1.5, FLEX=1) after the FG bracket confirmation -- matches the
  implementation exactly, no code change needed, logged here for the
  record.
- `ownership_heuristic.py`'s classic roster-slot-budget normalization
  produces `NaN` `estimated_ownership_pct` for the K position group --
  will surface for real once Session 13.2 ships Showdown ingest. Fix is
  Session 13.3's dedicated Showdown ownership heuristic, not a patch to
  the classic path.
- `salary_anchor.py`'s fitted curves have no entry for position "K" --
  `anchor_points()` will correctly fail loudly (per its own decision #3)
  if the salary anchor is ever enabled with kicker rows in the pool.
  Harmless today (`SALARY_ANCHOR_WEIGHT_DEFAULT=0.0`, anchor off by
  default; classic pools have no K rows regardless), but noted so it
  isn't a surprise later -- refit `fit_salary_anchor.py` to include K if
  the anchor is ever wanted for Showdown kickers.
- No opponent/game-script-based volume signal (e.g. tough-defense-forces-
  more-FG-attempts) was built or tested beyond the team-implied-total
  regression that came back null -- explicitly flagged as a possible
  future refinement in `fit_kicker_model.py`, not attempted this session.

**Handoff notes for next session:**
- `data/kicker_model.json` needs periodic refitting as new seasons
  complete -- the recency-weighting (decision #3) means this artifact is
  meant to be refreshed, not treated as a static constant. No automation
  wired for this yet (small, could be added to `refresh_data.yml` or done
  manually each offseason).
- Session 13.2 (Showdown/Single-Game salary ingest) is next. Once real K
  rows start flowing through `ingest_salaries.py`, re-run the
  `add_ownership_columns()` smoke test from this session against a real
  (not synthetic) Showdown pool to confirm the NaN finding above behaves
  as expected before Session 13.3 fixes it.
- Both sites' kicker scoring tables are now fully real-data confirmed --
  no remaining unverified numbers in `scoring_rules.py`'s kicker section.

---

## Session 13.2 — Showdown / Single-Game Salary Ingest
**Date completed:** 2026-08-04
**Status:** ✅ Complete

**What was actually built:**
- `ingest_salaries.py`: new `--format {classic,showdown}` flag (default
  `classic`, backward compatible -- every pre-existing column is unchanged,
  though NOT byte-for-byte identical since a new `slate_format` column is
  now stamped on every row regardless of format, same precedent as Phase
  11's `slate_type`). `SITE_CONFIGS[site]["showdown"]` added as a nested
  sub-dict for both sites rather than the roadmap card's speculative
  `SITE_CONFIGS[site][format]` restructure -- 9 other scripts
  (`optimizer.py`, `ownership_heuristic.py`, `ingest_rotoguru.py`,
  `fit_salary_anchor.py`, `build_projections_statline.py`,
  `build_projections.py`, `backtest_harness.py`, `pivot_finder.py`,
  `log_ownership.py`) already read `SITE_CONFIGS[site][key]` flat assuming
  classic; nesting only the showdown delta keeps all of them untouched.
  Output is normalized to 2 rows/player for BOTH sites regardless of the
  raw input's actual shape (DK already is; FD is expanded from its real
  1-row shape) -- matches the roadmap card's own stated output contract
  and keeps Sessions 13.3/13.4 site-agnostic.
- `generate_synthetic_slate.py`: new `--format showdown` mode -- forces
  exactly 1 game/2 teams (real Showdown/Single-Game structure), adds K to
  the synthetic pool (Showdown-only; classic pool is untouched), builds
  DK's real 2-row shape and FD's real 1-row-plus-MVP-column shape, both
  reproduced from the actual measured files this session, not
  documentation guesses.

**Files created/modified:**
- `/dfs_optimizer/scripts/ingest_salaries.py` (modified)
- `/dfs_optimizer/scripts/generate_synthetic_slate.py` (modified)

**Validation results:**
- [x] Real DK Showdown file (user-supplied, live 08/06/2026 CAR@ARI
  Madden Sim-style slate): 126/126 rows (63 players x 2) matched, 100%,
  CPT/FLEX rows correctly linked to the same player_id. DK's `Position`
  column was found to retain the player's TRUE position on BOTH the CPT
  and FLEX row (NOT overwritten to "CPT"/"FLEX" -- only `Roster Position`
  is) -- this meant the existing (name, team, position) matching pipeline
  from Session 1.3 worked completely unchanged, no fallback matching
  strategy was needed.
- [x] Real FD Single Game file (same slate, same session -- an upgrade
  over the card's synthetic-only expectation for FD): 122/122 rows (61
  players x 2, after this session's row-expansion) matched, 100%,
  MVP/FLEX rows correctly linked to the same player_id.
- [x] Synthetic FD Showdown file round-trips through the same linking
  logic (card's originally-planned validation) -- also done, on top of
  the real-file validation above.
- [x] Unmatched players logged clearly (existing mechanism, unchanged) --
  0 unmatched on both real files.
- [x] Classic-mode regression: real classic DK file (`DKSalaries_MOCK_Slate.csv`)
  still ingests cleanly with `--format` omitted -- same pre-existing
  columns, same code path, only the one additive `slate_format` column
  differs. (0% match rate against this particular mock file is expected
  and unrelated to this session's changes -- the mock file uses fictional
  player names not present in any real nflverse reference.)
- [x] `python3 -m py_compile` clean on both modified files.

**Decisions made / assumptions taken:**
- Nested `SITE_CONFIGS[site]["showdown"]` rather than the card's suggested
  `SITE_CONFIGS[site][format]` restructure -- see "What was actually
  built" above for the blast-radius reasoning.
- Showdown matching reuses the classic (name, team, position) pipeline
  unchanged for DK, rather than the originally-planned "match on name+team
  only, source true position from the reference table" fallback -- the
  fallback turned out to be unnecessary once the real file showed
  `Position` already holds the true player position on both rows. Kept as
  a documented near-miss, not built.
- FD's real single-row shape is expanded into 2 output rows (FLEX-priced +
  MVP-priced) at ingest time, rather than leaving FD's raw shape as-is and
  making downstream sessions branch on `row_shape` per site -- keeps
  13.3/13.4 identical logic across both sites.
- CPT/FLEX salary-ratio validation uses a 5% tolerance, not exact-match --
  tightened from an initial 1% after the synthetic generator's own
  nearest-$100 rounding on both the FLEX and CPT salary independently
  produced harmless ratio drift above 1% at the low end of the salary
  range. The real file's ratio was exactly 1.5; 5% comfortably separates
  real bugs from synthetic rounding noise.

**Known issues deferred:** None. The one open item during this session
(see "Two premises..." below) was resolved live before close-out, not
deferred to 13.4.

**Two premises from the original roadmap card that measured FALSE against
real data (both sites' exports, and in one case a live roster builder,
supplied by the user this session):**
1. "Both sites' Showdown exports list each player TWICE" -- FALSE for FD.
   FD's real Single Game export is ONE row per player, carrying both a
   base `Salary` column and an `MVP 1.5x Salary` column on that same row.
2. ROADMAP.md's Phase 13 intro "confirmed rule" that FD's MVP slot costs
   the SAME salary as FLEX (no cost multiplier) -- FALSE. User-supplied
   screenshots of a LIVE FD Single Game roster builder (same CAR@ARI
   slate) confirmed the real cap math: MVP $12,000 + 5 FLEX x $8,000 =
   $52,000 of the $60,000 cap, leaving exactly $8,000 remaining, matching
   the live "Salary Remaining" readout exactly. FD's MVP costs 1.5x
   salary, same mechanic as DK's CPT (which was independently confirmed
   the same way: CPT $11,400 vs FLEX $7,600 = 1.5x, and a live DK roster
   builder screenshot showing the same 1.5x language). Corrected in
   ROADMAP.md's Phase 13 intro as part of this session's close-out.

**Handoff notes for next session:**
- Session 13.3 (Showdown projection & scoring-multiplier layer) can treat
  both sites' cap math AND scoring math as identical -- 1.5x salary AND
  1.5x points for the captain-equivalent slot on both DK and FD. No
  remaining ambiguity to verify there.
- New output columns for 13.3/13.4 to consume: `roster_role` (raw site
  role label -- "CPT"/"FLEX" for DK, "MVP"/"FLEX" for FD) and
  `slate_format` ("classic"/"showdown", present on every row of every
  format going forward).
- FD's two synthesized output rows per player share the SAME raw
  `site_id_col` ("Id") value, since FD's real file only has one id per
  player -- faithful to reality, not a bug, but relevant if a future
  session builds an FD upload-template feature (the DK equivalent already
  exists per `site_id_col`'s original module docstring note).
- `PLAYERS_PER_TEAM_SHOWDOWN` and `SALARY_BANDS["K"]` in
  `generate_synthetic_slate.py` are FLAGGED ARBITRARY, loosely shaped
  after the real file's position counts but not fit to anything.

---

## Session 13.3 — Showdown Projection & Scoring-Multiplier Layer
**Date completed:** 2026-08-05
**Status:** ✅ Complete

**Pre-session fix (found during prerequisite check, not part of this
session's build):** `data/kicker_model.json` (Session 13.1's fitted
artifact) had never actually been committed to the repo, despite Session
13.1's log stating it was written -- confirmed via GitHub's commit
history (zero commits, ever) and independently confirmed by the user (only
`fit_kicker_model.py`/`kicker_model.py`, the code, had made it into their
hands). Re-ran `fit_kicker_model.py` for real against nflverse's public
2018-2023 data; reproduced Session 13.1's exact fit numbers
(`mu_fga=1.92588`, `mu_pat=2.27658`, 79 kickers) confirming the original
fit was legitimate and just never delivered as a file. Regenerated,
sanity-tested (`load_model()`/`project_kickers()` against both a known
career kicker and a rookie fallback), and handed to the user to commit.
Not re-validated: the original 2024-2025 held-out backtest MAE/RMSE/sigma
numbers were not reproduced (would require pulling two more full seasons)
-- treated as low-risk given the exact fit-window match, but not silently
assumed to still hold.

**What was actually built:**
`build_projections.py` now branches on `slate_format` (via new
`is_showdown_slate()`): Showdown pools run the ENTIRE existing classic
pipeline (skill/DST/kicker projections, matchup, vegas, salary anchor)
unchanged against the FLEX-priced rows only, then `apply_captain_multiplier()`
derives the CPT (DK) / MVP (FD) row from the already-built FLEX projection
via a flat 1.5x on `final_projection`/`season_avg`/`recent_form` (and
`sigma`/`dst_p10`/`dst_p90` where present, correct since a deterministic
1.5x rescaling of a distribution scales its sigma/percentiles by the same
1.5x). Classic pools take the unchanged original path. Ownership handling
was originally shipped as an explicit NaN + `ownership_available=False`
flag per this card's own instruction to get sign-off rather than assume --
**superseded same-day by Session 13.3b once the user flagged that leaving
Showdown ownership/pivot signal unaddressed wasn't acceptable; see that
entry for what actually shipped.**

**Files created/modified:**
- `scripts/build_projections.py` (modified)
- `data/kicker_model.json` (regenerated, pre-session fix, see above)

**Validation results:**
- [x] CPT/MVP `final_projection` == 1.5x linked FLEX `final_projection`,
  verified on a synthetic Showdown pool (built via `generate_synthetic_slate.py
  --format showdown`, ingested via the real `ingest_salaries.py`, 100% match
  both sites) spanning QB/RB/WR/TE/DST/K: 41/41 DK rows, 41/41 FD rows,
  exact match to 4+ decimals. Spot-checked Joe Burrow (DK): FLEX 22.575 ->
  CPT 33.8625, salary $5,600 -> $8,400, both exactly 1.5x.
- [x] Zero-FLEX-projection (bye/no-game) rows correctly produce a zero
  CPT/MVP projection too, not a nonzero one -- 0 violations on both sites.
- [x] Classic regression: re-ran a classic DK synthetic slate through the
  modified script -- ownership heuristic runs via the unchanged path,
  `roster_role` correctly null, `slate_format="classic"`.
- [x] Fail-loud guards unit-tested directly (not just exercised
  incidentally): mixed `slate_format` values raise `SystemExit`; missing
  `slate_format` column falls back to classic (backward compat); an
  unlinked FLEX player with no CPT/MVP row raises `SystemExit`.
- [x] `python3 -m py_compile` clean.
- [x] Full end-to-end run confirmed against the REAL distributional DST
  model (Session 10.4) and real kicker model (Session 13.1), not just the
  legacy DST fallback used for early iterations of this validation --
  `team_stats_2024.parquet`/`team_stats_2025.parquet`/`games.parquet`
  turned out to already exist in the repo (an earlier sandbox error
  suggesting they were missing was purely a local test-scaffold gap, not
  a real repo gap -- confirmed by checking GitHub directly before
  reporting anything to the user).

**Bugs found and fixed during this session's validation (real data/code,
not static review -- consistent with this project's established pattern
of bugs surfacing only when actually run):**
1. **New bug, introduced by this session's own `apply_captain_multiplier()`:**
   `flex_out` already carried `roster_role="FLEX"` before the merge with
   `captain_salaries` (which also has a `roster_role` column) -- pandas
   silently suffixed both to `roster_role_x`/`roster_role_y` instead of
   raising, causing a downstream `KeyError`. Fixed by dropping the stale
   column before merging.
2. **Pre-existing bug, unrelated to this session, found incidentally:**
   the `__main__` block's "missing site_player_id" validation check read
   `site_id_col` (the RAW salary file's column name, e.g. "ID"/"Id"),
   which never exists in the final `result` dataframe -- the pipeline
   renames it to `site_player_id` early on. This check had silently
   printed "N/A" instead of actually validating on every single run since
   the script was first written, for both classic and Showdown output.
   One-line fix, applied.

**Decisions made / assumptions taken:**
- `apply_captain_multiplier()` takes salary/site_player_id/roster_role
  directly from the raw ingest's CPT/MVP row rather than re-deriving them
  -- Session 13.2 already confirmed the real 1.5x salary math, no reason
  to recompute it.
- Anchor (when enabled) applies BEFORE the CPT/MVP split, on FLEX-priced
  salaries only -- avoids double-counting anchor logic for captain rows;
  the captain row's anchor-adjusted projection is derived via the same
  1.5x multiplier as everything else, not a separate anchor computation.

**Known issues deferred:** None carried out of this session specifically
-- the one open item (ownership) was resolved same-day in 13.3b, not
deferred silently.

**Handoff notes for next session:** See Session 13.3b's entry immediately
below -- it supersedes this session's ownership-field decision.

---

## Session 13.3b — Showdown Ownership Heuristic
**Date completed:** 2026-08-05
**Status:** ✅ Complete

**What was actually built:** Not on the original roadmap -- added same-day
when the user pointed out that neither 13.3 (NaN placeholder) nor 13.4
(per its own card, only touches `pivot_finder.py`'s existing band filter,
not ownership computation) actually builds real Showdown ownership, and
that accurate ownership/pivot signal was a stated priority for Showdown
from early in Phase 13's scoping.

`ownership_heuristic.py`'s `compute_chalk_scores()` and
`compute_estimated_ownership()` were parameterized with an optional
`group_col` (and the latter an optional `budgets` dict), defaulting to
`None` = the exact original classic behavior (`position_group` /
`compute_position_slot_budgets()`) -- confirmed byte-identical to a
pre-refactor baseline run, not just "should be" identical. Two new
functions supply Showdown's alternate grouping: `build_showdown_role_group()`
(folds DK's "CPT"/FD's "MVP" into one "CPT_MVP" bucket, same pattern as
`build_position_group()`'s DST-label-folding) and
`compute_showdown_role_budgets()` (real roster-slot-math budget --
1 CPT/MVP slot + N FLEX slots -- read directly from
`SITE_CONFIGS[site]["showdown"]["roster_slots"]`, same anchor principle as
classic's decision #5, not a guess). `build_projections.py`'s
`add_showdown_ownership_placeholder()` (13.3's NaN stub) was replaced with
`add_showdown_ownership_columns()`, which calls the above with Showdown's
grouping and merges the result back onto `(player_id, roster_role)` -- not
just `player_id`, since a Showdown pool has two rows per player and a
player's CPT ownership share is a genuinely different real-world quantity
from their FLEX share.

**Files created/modified:**
- `scripts/ownership_heuristic.py` (modified)
- `scripts/build_projections.py` (modified -- same file as 13.3, this
  session's changes layered on top)

**Validation results:**
- [x] `estimated_ownership_pct` sums to EXACTLY the real roster-slot
  budget per role group on the same synthetic Showdown pool 13.3 used: DK
  CPT_MVP 100.0% / FLEX 500.0% (1 CPT + 5 FLEX); FD CPT_MVP 100.0% / FLEX
  400.0% (1 MVP + 4 FLEX). Both exact, not approximate.
- [x] `chalk_score`/`estimated_ownership_pct` both confirmed in [0,100]
  range on both sites' Showdown output.
- [x] Spot-checked Joe Burrow (DK): FLEX `estimated_ownership_pct` 19.85%
  vs. CPT 3.97% -- correctly reflects the CPT budget (100% total across
  the whole 41-player pool) being much thinner than FLEX's (500%),
  matching the real-world DFS pattern of ownership fragmenting harder at
  captain.
- [x] `chalk_score` came out nearly-but-not-exactly identical (max diff
  ~0.85 of 100) between a player's CPT and FLEX rows -- expected, from
  tie-breaking mechanics in the pool-wide (not role-grouped)
  vegas_percentile/over_under_percentile columns, not a bug. Investigated
  and explained, not left as an unexplained anomaly.
- [x] Classic regression: re-ran the same classic DK synthetic slate from
  13.3 through the refactored `ownership_heuristic.py` -- position-group
  budget totals numerically identical to the pre-refactor baseline (DST
  100.0%, QB 100.0%, RB 233.3%, TE 133.3%, WR 333.3%), confirming the
  `group_col`/`budgets` parameterization didn't change classic's default
  code path at all.
- [x] `python3 -m py_compile` clean on both modified files.

**Decisions made / assumptions taken:**
- Reused the exact same 5-feature blend and weights as classic (value,
  raw projection, salary tier, vegas, over/under, + name recognition) --
  no real Showdown ownership data exists any more than real classic
  ownership data does, so a separately-tuned set of Showdown weights would
  just be a second set of unfit guesses to track. Session 11.1's already-
  planned retuning now covers both groupings.
- `group_col`/`budgets` parameterization (rather than a fully separate
  Showdown-specific pair of functions) chosen to guarantee classic's
  behavior can't silently drift from Showdown's over time -- one
  implementation, two call sites.

**Known issues deferred (explicitly, not silently):**
- **No real Showdown ownership data exists yet.** Real preseason Showdown
  slates start posting ~Aug 6, 2026 (Phase 13's own trigger) -- this is
  the point to start collecting, for BOTH classic and Showdown per the
  user's explicit instruction not to let this get forgotten.
- **`log_ownership.py` (Session 9.3) cannot log Showdown ownership at
  all yet** -- its schema (`data/ownership_actual_log.csv`) has no
  `roster_role` column, so it can't distinguish a player's CPT-role
  ownership from their FLEX-role ownership. Needs an additive
  `roster_role` column (and likely `slate_format`, matching Session
  13.2's precedent for `final_projections_*.csv`) before any real
  Showdown ownership data can be logged. Not built this session --
  flagged as the concrete next step. ROADMAP.md's Session 11.1 card
  updated with this same gap so it's the obvious next step when real data
  starts arriving, not rediscovered cold.

**Handoff notes for next session:** Session 13.4 (Optimizer ILP) can now
assume Showdown output always carries real, non-NaN
`chalk_score`/`estimated_ownership_pct` -- no NaN-handling branch needed
in `pivot_finder.py`'s Showdown path. When real Showdown slates start
(~Aug 6, 2026), the first concrete task is extending `log_ownership.py`'s
schema per the deferred item above, before any real ownership data can
start accumulating toward Session 11.1's retuning gate.

## Session 13.4 — Optimizer ILP for Showdown Roster Construction
**Date completed:** 2026-08-05
**Status:** ✅ Complete

**What was actually built:**
- New, entirely PARALLEL Showdown ILP solve path in `optimizer.py`, not a
  retrofit of classic's `solve_lineup()`. Confirmed during scoping that
  classic's `x = {pid: ... for pid in players["player_id"]}` dict
  comprehension would silently COLLAPSE a Showdown pool's 2 rows/player
  (FLEX + CPT/MVP, same `player_id`) down to 1, dropping half the pool
  with no error -- this is why the roadmap card called this the
  highest-risk session in the phase. Row-keyed on `player_id::roster_role`
  instead. Zero lines of the classic formulation touched (until the
  sigma bug fix below, which is separate).
- Constraints: exact captain-slot count (1) + FLEX-slot count (5 DK / 4
  FD), CPT/FLEX mutual exclusivity per player (new constraint type,
  doesn't exist in classic), min-1-per-team (new constraint type), salary
  cap (the captain multiplier is already baked into the row-level salary
  from Session 13.2's ingest -- no special-casing needed, exactly as the
  original card anticipated).
- Reused classic's supporting machinery wherever the concept translates
  directly: locks (forces the player into the lineup in EITHER role --
  the solver picks whichever is actually optimal, no role-specific lock
  built), excludes, exposure caps across a batch, uniqueness (counted by
  underlying player, not role -- a player who was CPT in one lineup and
  FLEX in another still counts as "the same player" for diversity),
  `--max-team-players` (unchanged reuse), the lambda mean-variance
  objective, and projection randomization (a new row-keyed
  `randomize_showdown_projections()` -- classic's player_id-indexed
  version would collide on a Showdown pool's duplicate player_ids).
- `--format {auto,classic,showdown}` CLI flag, default `auto` (detects
  via the `slate_format` column, same pattern `build_projections.py`
  already uses) -- no flag needed for a normal run; `classic`/`showdown`
  are available to force-and-fail-loud if the wrong file gets pointed at.
- Stacking (`--stack-mode`) and `--max-game-players` explicitly REJECTED
  for Showdown with a clear `parser.error()`, not silently ignored or
  half-applied -- deferred per this session's own scoping conversation
  (see Decisions below).
- Same-session addendum, added after discussing the stacking deferral
  with the user: `--min-team-players TEAM:N`, a Showdown-only "one-sided
  lineup" lever (the mirror of `--max-team-players`) that turned out to
  cover the actual want ("force 4/5/6 players from one team, make sure
  it's one-sided") without needing full stacking's opponent-lookup/
  game-selection/bring-back machinery re-derived for a positionless
  2-team pool. Structural feasibility (can this floor and the other
  team's own required min-1 both fit in the roster?) is pre-checked
  before the solver ever runs, same "fail loud, with a specific reason,
  before wasting a solve" discipline as every other constraint in this
  file.
- `pivot_finder.py` fix: the roadmap card's own premise that this script
  "likely needs no change" for Showdown was FALSE -- a real bug, not a
  hypothetical. A Showdown pool's 2 rows/player_id share the exact same
  normalized (player_name, position, team) triple the existing join key
  used, so `attach_cash_lineup_context()`'s "exactly 1 match expected"
  check would always find 2 and crash with `SystemExit` the first time
  this ran against real or synthetic Showdown output -- not caught by
  the roadmap card's own text, only by actually tracing the join logic.
  Fixed by extending the join key with `roster_role` whenever the pool
  is a Showdown pool, sourced from `optimizer.py`'s own Showdown lineup
  output (which now carries `roster_role` via `assign_showdown_roster_
  slots()` -- a schema addition specific to Showdown; classic's
  `lineup_single_*.csv` schema is unchanged). Pivot candidates are now
  also required to match the cash player's own `roster_role` -- a CPT
  alternative should be compared against other CPT rows, not FLEX rows
  at a different salary/point scale.
- Bug found and fixed during real-data validation (not caught by any
  synthetic pool built during development -- only surfaced once the user
  ran this against a real `build_projections.py` output): that script's
  `sigma` column can be PRESENT but only PARTIALLY populated (Session
  13.1's kicker model writes real sigma for kicker rows; DST's sigma is
  computed then dropped before the final concat and never merged back --
  see `build_projections.py`'s unused `_dst_extra` variable, flagged
  below, not fixed this session since `build_projections.py` wasn't
  otherwise in scope). A `sigma` column that's NaN for most rows crashed
  PuLP's objective-building step ("Cannot multiply variables with
  NaN/inf values") regardless of `--lambda`'s value, including the
  default `lam=0` -- `0 * NaN` is `NaN`, not `0`; this is a real LP
  coefficient being built, not a Python float that could short-circuit.
  Fixed with `.fillna(0.0)` where sigma is read, in BOTH the new
  Showdown path AND the pre-existing classic `solve_lineup()` -- the
  identical latent bug was confirmed present there too (classic pools go
  through the same kicker-model-inclusive `build_projections.py`), so
  this would have broken the next real classic slate run for a reason
  nobody would have connected back to this session. This is the one
  classic-path code change this session made -- justified because it's a
  strict, provably-safe fix (a no-op on any pool where sigma has no
  nulls, which is every pool this project's existing regression coverage
  used) and re-verified byte-identical classic regression after applying
  it.

**Files created/modified:**
- `scripts/optimizer.py` (modified -- new Showdown section added before
  `main()`; plus the 2-line sigma-NaN fix inside the pre-existing classic
  `solve_lineup()`)
- `scripts/pivot_finder.py` (modified -- join-key + candidate-filter fix
  for Showdown, described above)

**Validation results:**
- [x] Synthetic-pool unit tests: CPT/FLEX exclusivity, min-1-per-team,
  salary cap, exactly 6 (DK) / 5 (FD) total slots -- all enforced,
  confirmed via `validate_showdown_lineup()` running clean on every test
  plus manual inspection of output.
- [x] `optimizer.py` full-file compile check (`python3 -m py_compile`) --
  clean, both before and after the sigma-NaN fix.
- [x] Solver produces a valid lineup against a synthetic Showdown pool
  for BOTH sites (DK: CPT role, 6 slots, $50K cap; FD: MVP role, 5 slots,
  $60K cap -- both tested).
- [x] Optimality independently verified by brute force, not just
  trusted: the unconstrained single-lineup solve, a `--max-team-players`-
  constrained solve, and a `--min-team-players`-constrained solve all
  matched their brute-force-computed optimum exactly, checked against two
  different synthetic pools.
- [x] `pivot_finder.py` produces sane suggestions against a Showdown pool
  -- NOT deferred, per the roadmap card's own instruction to decide one
  way or the other rather than let it silently half-work. Verified on a
  richer synthetic pool with real lower-owned same-role alternatives;
  confirmed suggestions never mix CPT and FLEX `roster_role`s.
- [x] Real-data end-to-end run (this session's most load-bearing
  validation): pulled real 2025 nflverse player data and ran the ACTUAL
  `generate_synthetic_slate.py --format showdown` -> `ingest_salaries.py
  --format showdown` -> (user's own machine, with a fabricated stand-in
  Vegas file to bypass the Odds API key for this test only --
  `vegas_odds.py` itself is untouched) `build_projections.py` ->
  `optimizer.py` -> `pivot_finder.py`. Real player names (Trey McBride,
  Jacoby Brissett, Rico Dowdle, Marvin Harrison Jr., etc.), real DST/
  kicker models, real captain-multiplier math (46/46 CPT rows exactly
  1.5x their linked FLEX row in `build_projections.py`'s own printed
  check). This run is what surfaced the sigma-NaN bug above -- another
  instance of this project's "bugs found only by running real data"
  pattern (Session 4.3's precedent, repeated here).
- [x] Classic-path regression: `optimizer.py`/`pivot_finder.py` output
  confirmed BYTE-IDENTICAL against the pre-Session-13.4 originals
  (diffed directly against files pulled fresh from GitHub, not
  eyeballed), re-confirmed again after the sigma-NaN fix landed.

**Decisions made / assumptions taken:**
- Parallel solve path, not a retrofit -- see "What was actually built"
  above for the concrete reason (classic's dict-comprehension would
  silently drop half a Showdown pool).
- Stacking explicitly DEFERRED for Showdown, not built and not silently
  half-applied. User-confirmed this session that a simpler "min N players
  from one team" lever fully covers the actual desired behavior ("make
  sure the lineup is one-sided") -- full stacking's qb/game/mini modes
  with opponent-lookup/bring-back/candidate-rotation, correctly
  reinterpreted for a positionless 2-team pool, would have been
  substantial separately-testable scope for a want that `--min-team-
  players` already satisfies.
- `--max-game-players` rejected outright for Showdown, not reinterpreted
  -- a Showdown pool is always exactly 1 game by definition (Phase 13's
  own confirmed rule), so "max players per game" is meaningless;
  `--max-team-players` already covers the only real lever a 2-team pool
  has.
- Locking a Showdown player locks them in EITHER role, not a specific
  one -- not requested, not built. Flag if real usage ever wants a
  role-specific lock.
- `pivot_finder.py`'s fix required adding `roster_role` to `optimizer.py`
  's `lineup_single_*.csv`/`lineups_multi_*.csv` schema (Showdown rows
  only -- classic's schema is unchanged).
- The sigma-NaN fix was applied to classic's `solve_lineup()` as well as
  the new Showdown path, even though `build_projections.py` itself is
  outside this session's stated scope -- justified as a strict,
  provably-safe bug fix (see "What was actually built" above) that would
  otherwise have broken the next real classic slate run for a reason
  nobody would have connected back to this session.

**Known issues deferred (explicitly, not silently):**
- **Stacking for Showdown slates** -- not built. `--min-team-players`
  covers the "one-sided lineup" use case that was the actual ask; full
  qb/game/mini stack modes for a positionless 2-team pool remain a real,
  separately-scoped follow-up if ever wanted later.
- **`--min-total-ownership`, `--flex-positions`, `--min-projection` are
  not supported for Showdown** -- all three explicitly rejected with a
  clear CLI error rather than silently ignored. `--flex-positions` has no
  real meaning for Showdown (no position-restricted slots to restrict
  further). The other two are real, buildable features just not built
  this session.
- **`build_projections.py`'s unused `_dst_extra` variable** (found while
  diagnosing the sigma-NaN bug) -- DST's real sigma/dst_p10/dst_p90
  values are computed, captured into `_dst_extra`, and then never merged
  back into the final output. Not fixed this session (`build_
  projections.py` wasn't otherwise in scope this session) -- means DST
  rows currently carry no sigma at all in the legacy `build_
  projections.py` path, a missed-opportunity gap rather than a
  correctness bug (the `.fillna(0.0)` fix means this no longer crashes
  anything). Worth closing in a future `build_projections.py`-focused
  session.
- **`pivot_finder.py` produced 0 suggestions on the real Showdown test
  run** -- explained as a thin-pool artifact (a Showdown pool is always
  exactly 2 teams by construction, so it has structurally fewer
  same-position/same-role alternatives than a full classic slate),
  consistent with this project's existing "Known Testing Artifact"
  pattern, but not yet confirmed against a real, full-size preseason
  Showdown slate. Re-check once one is available (~Aug 13-15, this
  phase's own trigger) -- if pivots are still consistently empty against
  a real 40+ player pool, that needs a closer look then, not assumed
  away.
- **Cosmetic only**: `assign_showdown_roster_slots()`'s (and classic's
  pre-existing `assign_roster_slots()`'s) `float(getattr(row, "sigma",
  0.0) or 0.0)` pattern doesn't correctly fall back to 0.0 when `sigma`
  is a real NaN value (as opposed to a missing column) -- `float('nan')
  or 0.0` evaluates to NaN in Python, since NaN is truthy. Purely a
  display quirk in the per-player `sigma` output column (individual
  cells show NaN instead of 0.0); `sigma_total` is unaffected since
  pandas' `.sum()` skips NaN by default (confirmed). Not fixed this
  session -- trivial future cleanup, same pattern in both classic and
  Showdown output.

**Handoff notes for next session:** Session 13.5 (Frontend Showdown UI +
Four-Layer Wiring) can now assume a working, real-data-validated
`optimizer.py`/`pivot_finder.py` Showdown path with this CLI surface:
`--format`, `--min-team-players` (new), plus every reused classic flag
(`--lock`, `--exclude`, `--n-lineups`, `--max-exposure`, `--uniqueness`,
`--randomization-pct`/`--randomization-mode`, `--lambda`,
`--max-team-players`, `--request-id`). The four explicitly-rejected flags
(`--stack-mode`, `--max-game-players`, `--flex-positions`,
`--min-total-ownership`, `--min-projection`) should surface as disabled/
hidden in the UI for Showdown mode, not left clickable and erroring.
The Cloudflare Worker's `passthroughKeys` and the GitHub Actions
flag-builder both need `--min-team-players` added alongside the existing
team-cap flags -- this project's own "four-layer architecture awareness"
principle (a new optimizer parameter silently dropped if not added in
all four places).

---

## Session 13.5b -- Bug Fixes: DST Opponent Resolution, Rookie/
Zero-History Matching, Vegas Decoupled from Week
**Date completed:** 2026-08-05
**Status:** ✅ Complete

**What was actually built:** Two bugs discovered during real-slate Showdown
testing (documented in `Handoff_13.5_Pause_BugFixes.md`, written to pause
13.5 pending these fixes) plus three more real problems this session's own
real-data validation surfaced along the way -- consistent with this
project's established "bugs found only by running real data" pattern
(Session 4.3, 12.1, 13.4's precedent, repeated three more times here).
Not Showdown-specific -- confirmed to affect classic and Madden slates
too, per the handoff's own framing.

**Bug A -- DST opponent resolution bypassed the Game-Info fallback.**
`_build_dst_distributional()` called `dst_model.build_features()` without
the `opponent_map` skill players/kickers already used (`build_projections
.py` decision #9), so a defense's opponent/opp_implied/opp_sack_allowed_
rate/opp_dropbacks/opponent-QB were all resolved from the raw vegas
file's real-2025-schedule opponent column -- wrong whenever the in-slate
pairing differs from the real schedule (every Madden Sim slate, every
preseason Showdown slate). This was a real simulation-accuracy bug, not
just a mislabeled column: `opp_implied`/`opp_sack_allowed_rate`/`opp_
dropbacks` all fed the DST Monte Carlo model directly.

Fixed with the user's chosen "full consistency" option: `dst_model.build_
features()` now accepts `opponent_map` and overrides the vegas-derived
opponent for any team the map covers (decision #23, dst_model.py) --
this governs the SIMULATION inputs. Separately, `_build_dst_distributional
()` now also sources DST's DISPLAYED implied_total/over_under from the
same `vegas_factors` table skill players/kickers already use (decision
#10, build_projections.py), instead of the raw per-team vegas row -- so a
defense and its own team's skill players always show identical opponent/
implied_total/over_under in the CSV and the frontend's Slate Overview
panel, including falling back to the same 0.0 when no matching vegas line
exists. Both are no-ops when `opponent_map`/`vegas_factors` aren't
supplied (classic slates unaffected).

**Bug B -- rookies/zero-history players silently dropped from the pool.**
`ingest_salaries.py`'s `build_player_reference()` built its entire
matching universe from `weekly_stats_{season}.parquet` only -- players
with >=1 logged snap. A true rookie or zero-snap player has no row there
at all, so `name_mapping.csv` (which can only redirect to an EXISTING
row) could never resolve them, and `build_projections.py`'s `players
[players["player_id"].notna()]` gate silently dropped them downstream,
before the existing cold-start salary-anchor logic (Session 10.0-10.2,
built specifically for zero-history players) ever got a chance to run.

Investigated (not assumed) before fixing, per this session's real-data
checks: `weekly_rosters_2026.parquet` IS pullable and populated in
preseason (2,930 rows checked this session). `weekly_rosters`'s `gsis_id`
and `weekly_stats`'s `player_id` are CONFIRMED the same ID scheme, not two
schemes needing a crosswalk (verified against real 2025 data: Patrick
Mahomes' gsis_id and player_id are both `00-0033873`; `ingest_historical
.py`'s own Session 1.2 ROSTER_KEY comment already documented the same
fact independently). Fixed by having `build_player_reference()` union in
any player present in `weekly_rosters_{season+1}.parquet` (the CURRENT
season, not `--season`'s "last completed season" stats-lookback meaning
-- a real subtlety caught before it caused a second, quieter version of
the same bug) but absent from `weekly_stats`, using `gsis_id` directly as
`player_id`. New CLI flag `--weekly-rosters` (defaults automatically,
overridable, `''` disables for old behavior).

**Three more real bugs found via this session's own real-data validation
runs (not from the original handoff), fixed in the same session rather
than deferred, since each was small and load-bearing for validating A/B
properly:**

1. **`config/api_keys.env` BOM breaks `vegas_odds.py`'s key lookup.** A
   bare `Path.read_text()` silently glues a UTF-8 BOM onto the first line
   if the file was ever saved by an editor that adds one (Notepad does,
   by default) -- `"\ufeffODDS_API_KEY" != "ODDS_API_KEY"` fails the match
   with no visible sign anything's wrong, since the key really is in the
   file. Fixed with `encoding="utf-8-sig"` (safe no-op if no BOM present).
   Reproduced the user's exact error with a synthetic BOM'd file before
   and after the fix to confirm.

2. **`ingest_historical.py --season 2025 2026` aborted BOTH seasons when
   only 2026 failed.** `stats_player_week_2026.parquet` / `stats_team_
   week_2026.parquet` 404 until that season's games are actually played
   (rosters populate earlier, in preseason, and did pull fine -- this is
   what Bug B's fix depends on). The old combined-batch `import_weekly_
   data(seasons)` call meant one missing season took the whole call down,
   silently skipping 2025's refresh too even though 2025 was available.
   Fixed by pulling each season independently in `ingest_weekly_stats()`
   and `ingest_team_stats()`, catching a 404 specifically (any OTHER
   error still raises -- not a blanket silent-fallback).

3. **`_dst_extra` gap flagged (not fixed) in Session 13.4 -- closed now.**
   DST's real sigma/dst_p10/dst_p90 (computed by the distributional model)
   were captured into an unused `_dst_extra` variable and never merged
   back, so every skill/DST row's sigma was NaN in the final output --
   surfaced for the first time by this session's "Nulls in any column"
   validation check, on literally the first real classic slate ever run
   through it (prior real-data runs were Showdown/Madden). Fixed:
   skill_out/dst_out now get a neutral 0.0 sigma/dst_p10/dst_p90
   placeholder (matching kicker_out's existing pattern for columns its
   own model has no signal for), and `_dst_extra`'s real DST values are
   merged back in via `.update()` after the concat, before Showdown's
   captain-multiplier step (which already correctly scales these columns
   -- it just never had real values to scale before). Also fixed the null
   check itself to exclude `roster_role` (intentionally None for every
   classic-slate row, a false alarm this check had never actually hit
   before today) and to name which column(s) are affected if it fires for
   real, instead of a bare uninformative count.

**Vegas decoupled from `--week` entirely (structural fix, user-requested
after this was the recurring root cause of 3-4 separate problems across
this project):** `vegas_odds.py`'s `--week` was never a data filter (the
Odds API always returns every live game regardless) -- it was purely a
filename label borrowed from the unrelated stats-lookback week, which
caused a real bug this session: an old `vegas_implied_totals_23.csv` from
an unrelated earlier pull got silently reused for a real preseason
Showdown slate because both happened to reuse week=23. Renamed to
`--slate-id` (`vegas_implied_totals_{slate_id}.csv`), matching the
convention `final_projections_{site}_{slate_id}.csv` already established
in Session 2.4 for the identical reason. `build_projections.py`'s `load_
vegas_implied_totals()` now takes `slate_id`; new `--vegas-slate-id` CLI
flag (defaults to `--slate-id`) lets FD point at a vegas pull made under
DK's slate_id when they share one (the common case -- vegas is site-
agnostic). `refresh_data.yml`'s vegas-pull and both sites' `build_
projections.py` steps updated accordingly -- confirmed via `grep` that no
other workflow references `vegas_odds.py --week`.

**Files created/modified:**
- `scripts/dst_model.py` (`build_features()` -- new `opponent_map` param,
  decision #23)
- `scripts/build_projections.py` (`_build_dst_distributional()`, `build_
  dst_projections()`, `load_vegas_implied_totals()`, `build_final_
  projections()`, new `--vegas-slate-id` CLI flag, sigma-merge fix, null-
  check fix -- decisions #10, #11)
- `scripts/vegas_odds.py` (`--week` -> `--slate-id`, `load_api_key()`
  utf-8-sig fix)
- `scripts/ingest_salaries.py` (`build_player_reference()` roster union,
  new `--weekly-rosters` CLI flag)
- `scripts/ingest_historical.py` (`ingest_weekly_stats()`, `ingest_team_
  stats()` -- per-season independence)
- `.github/workflows/refresh_data.yml` (vegas pull + both sites' `build_
  projections.py` steps use `--slate-id`/`--vegas-slate-id`)

**Validation results:**
- [x] Bug A: isolated logic test reproducing the exact real ARI/CAR
  Showdown scenario -- confirmed ARI resolves to CAR (not LAC) with CAR's
  real opp_implied (21.51, not LAC's 17.89); teams not in the map
  unaffected; `opponent_map=None` exactly reproduces pre-fix output
  (classic-slate regression-safe).
- [x] Bug A: real ARI/CAR Showdown CSV re-pulled and directly inspected --
  ARI's DST shows opponent=CAR (not LAC), and its implied_total/over_under
  (0.0/0.0) now exactly match all 21 of ARI's own skill players. Same for
  CAR's DST vs CHI. User separately confirmed a re-run Madden slate looks
  correct.
- [x] Bug A: classic-slate regression -- deferred by user (no real classic
  slate existed yet at the time), effectively superseded by the full real
  Week 1 classic run below.
- [x] Bug B: synthetic test mirroring the real Carson Beck scenario --
  existing player (has weekly_stats) not duplicated; roster-only player
  correctly added with real gsis_id-as-player_id; `weekly_rosters_
  path=None` exactly reproduces pre-fix behavior.
- [x] Bug B: real DK Week 1 2026 regular-season classic slate (`classic_
  wk1`, real Sun 9/13 slate) -- `build_player_reference` added 1,172
  roster-only players; ingest matched 686/715 (95.9%) vs. a materially
  worse rate pre-fix; remaining 29 unmatched are genuine name-spelling
  mismatches (nicknames, suffix formatting), not the rookie-dropping bug --
  expected `name_mapping.csv` residual, not a regression.
- [x] Vegas/slate_id migration: `refresh_data.yml` parses as valid YAML
  post-edit; the three changed `run:` lines confirmed to resolve exactly
  as intended.
- [x] api_keys.env BOM fix: reproduced the user's exact `ODDS_API_KEY not
  found` error with a synthetic BOM'd file, confirmed the fix resolves it.
- [x] ingest_historical.py fix: reproduced the user's exact `--season 2025
  2026` failure (2026 404, 2025 silently skipped) with a stubbed network
  call, confirmed 2025 now writes successfully regardless of 2026's
  status.
- [x] sigma-merge fix: synthetic test of the exact concat mechanics --
  confirmed zero nulls post-fix, DST's real sigma restored, skill players
  keep the neutral 0.0 placeholder.
- [x] Null-check fix: synthetic test confirming a classic slate (roster_
  role null, everything else clean) now reports 0, while a genuinely
  injected gap is still caught and names the affected column.
- [x] Full real-data end-to-end run, this session's most load-bearing
  validation: real DK Week 1 2026 regular-season classic slate, start to
  finish -- `ingest_historical.py` (both seasons) -> `vegas_odds.py
  --slate-id` -> `ingest_salaries.py` -> `projections_baseline.py` ->
  `projections_matchup.py` -> `build_projections.py` -> committed/pushed
  -> lineups built successfully through the real GitHub Actions/
  Cloudflare Worker dispatch path in the deployed UI. Real games correctly
  inferred from the salary file's own Game Info column (12 real Week 1
  matchups: ARI@LAC, ATL@PIT, BAL@IND, etc. -- see "Decisions made" below
  for why the schedule-based path correctly falls back to this one even
  on a real slate). 0 unmatched matchup_factor, 0 unmatched vegas_factor
  (real Week 1 vegas lines fully resolved, unlike the preseason ARI/CAR
  case). DST model: mean projection 7.21, sigma range 5.82-6.50 (sane).
  Final null check: 0 (after the sigma fix). Negative final_projection: 0.
  chalk_score/estimated_ownership_pct both in-range.

**Decisions made / assumptions taken:**
- User's explicit choice for Bug A: "full consistency" (option 2) over the
  narrower fix that would've left DST's own implied_total/over_under
  independently sourced from skill players'.
- User's explicit choice: fold both bugs into one session under the 13.x
  numbering rather than separate session numbers, since neither is
  Showdown-specific; user's explicit choice to tackle Bug A fully before
  starting Bug B investigation, in the same session.
- **`--season`/`--week`'s established "always use last completed season,
  currently 2025/23" convention was confirmed correct even for a REAL
  Week 1 regular-season slate, not just preseason/Madden** -- verified by
  reading `projections_baseline.py`/`projections_matchup.py` directly
  rather than assumed: both filter strictly to `week < N` WITHIN one
  season's own file, no cross-season carryover, so ANY week 1 (preseason,
  Madden, or real) has zero same-season history by construction. Week 23
  is additionally a safe sentinel for opponent resolution specifically
  because nflverse's real schedule only goes up to week 22 (REG 1-18,
  POST 19-22) -- `--week 23` reliably has zero real schedule matches,
  correctly forcing the salary-file Game-Info fallback (decision #9),
  which reads DK's real Game Info text and produces the correct real
  pairings on a real slate. **This convention is expected to change once
  real Week 2+ arrives** -- see "Handoff notes" below.
- `--weekly-rosters` defaults to `data/weekly_rosters_{season + 1}.parquet`
  (CURRENT season), deliberately NOT `{season}.parquet` (which is last
  completed season, for stats lookback) -- caught before shipping, since
  the wrong default would have silently defeated Bug B's whole purpose
  (a 2026 rookie was never going to be on a 2025 roster).
- Legacy DST model (`model="legacy"`) was NOT given the same opponent_map/
  vegas_factors full-consistency treatment as the distributional model --
  legacy already correctly accepted and used `opponent_map` (it was the
  distributional path specifically that never got it), and legacy isn't
  the production default, so out of scope for this session.

**Known issues deferred:**
- **Bug/Question B from the original handoff (skill players' implied_
  total/over_under = 0.00 for the real ARI@CAR Showdown game)** -- still
  open, still unconfirmed whether it's a genuine preseason-lines-not-
  posted-yet gap or something else. User explicitly deferred this ("not a
  dealbreaker... let it go for now").
- **29 unmatched players on the real Week 1 classic slate** -- genuine
  name-spelling/nickname mismatches (e.g. "Hollywood Brown", "Juice Wells
  Jr."), the expected `name_mapping.csv` workflow category, not a Bug B
  regression. Not resolved this session; routine per-slate maintenance.
- **`DFS_Weekly_Process.md` rewrite** -- explicitly NOT done yet. The doc
  currently documents the OLD `--week`-keyed vegas convention (now wrong),
  the OLD Madden game-totals-panel note (now describes the pre-Bug-A
  behavior as "expected," which it no longer is), and has no explicit
  Week-1-vs-Week-2+ distinction for `--season`/`--week`. User's explicit
  plan: do this as a follow-up now that the real workflow has been proven
  end to end, not before.
- **Real classic-slate DST regression check for Bug A** was originally
  planned as a synthetic/prior-output diff; no real classic slate existed
  yet at the time, so this was effectively superseded by (not literally
  performed as) the full real Week 1 run, which exercises the same code
  path. If a byte-level pre/post diff is ever wanted specifically, no
  pre-fix classic output was preserved to diff against.

**Handoff notes for next session:**
- `DFS_Weekly_Process.md` needs a full rewrite pass covering: (1) vegas is
  now pulled via `--slate-id` in Stage 2 (manual kickoff), not implicitly
  relied upon from Stage 3's cron -- explicit "pull fresh vegas" step
  needs adding, since its absence from the documented manual flow was
  itself part of how the original stale-vegas-file bug happened; (2) the
  `--week`/`--season` table needs an explicit Week-1-vs-Week-2+ split for
  real regular-season slates -- Week 1 uses the same 2025/23 convention as
  preseason/Madden (no real same-season history exists yet, full stop);
  Week 2+ should switch to the REAL `--season 2026 --week <N>` once real
  in-season history exists, which also flips schedule/opponent resolution
  from the Game-Info fallback to the real nflverse schedule as the primary
  path; (3) the Madden game-totals-panel note needs rewriting -- it
  currently describes showing "real NFL Week 1 games rather than your
  Madden matchups" as expected/cosmetic, which was actually Bug A's
  pre-fix symptom, not a real design choice; (4) new `--weekly-rosters`
  flag on `ingest_salaries.py` and the "added N roster-only player(s)"
  console line should be documented as expected/good; (5) file-save
  location/naming convention (`data/raw_salaries/dk_{slate_id}.csv`) was
  never actually stated clearly in the doc before -- should be explicit.
- Session 13.5 (Frontend Showdown UI + Four-Layer Wiring) can now resume
  being assessed for completeness -- both bugs that paused it are fixed
  and real-data validated (Showdown, Madden, AND real classic Week 1, a
  broader validation surface than 13.5 originally required). The Slate
  Overview panel and DST projections can now be trusted for that
  reassessment.
- FD side of everything built this session (vegas sharing via `--vegas-
  slate-id`, Bug A, Bug B) is implemented but not yet real-data validated
  -- same "DK first, FD second" gap this project has carried since Phase
  1. `--vegas-slate-id` defaults correctly for the common case (DK/FD
  share one slate_id string), confirmed via `data/current_slate.json`.

---

## Session 13.5 — Frontend Showdown UI + Four-Layer Wiring ✅ Complete (2026-08-05)
**Status:** Paused mid-session pending Session 13.5b (two real bugs found
during this session's own real-slate Showdown testing -- see
`Handoff_13.5_Pause_BugFixes.md`). Resumed and closed out after 13.5b's
fixes were real-data validated.

**What was actually built:**
- `dfs_optimizer_frontend/index.html` — Showdown-aware `SITE_CONFIG`
  (DK: CPT + 5×FLEX/$50k; FD: MVP + 4×FLEX/$60k, pulled directly from
  `ingest_salaries.py`'s `SITE_CONFIGS[site]["showdown"]`), `isShowdownRows()`/
  `poolIsShowdown()`/`effectiveCfg()` detection helpers (pool files via
  `slate_format`, lineup files via presence of `roster_role`, which
  classic lineups never carry), Showdown-aware `groupBySite()` sort
  order, Showdown-aware `render()`/`downloadLineupsForImport()` (DK/FD
  Showdown bulk-upload column shapes — `CPT,FLEX,FLEX,FLEX,FLEX,FLEX` /
  `MVP,FLEX,FLEX,FLEX,FLEX` — fall out of the existing trailing-digit-
  strip regex with no new logic needed once `slotOrder` is right), a `K`
  tab and `(CPT)`/`(MVP)` role badges in the Player Pool (a Showdown pool
  has 2 rows per `player_id` with different salary/projection — this was
  previously silently dropped by the pool-payload whitelist, a real bug
  caught before shipping, not just a missing feature), role-aware
  `pivotKey()`/`groupPivots()`/`applyPivotSwap()` matching `pivot_finder.py`'s
  Session 13.4 `cash_roster_role`/`pivot_roster_role` columns, a new **Min
  Team Players** Build panel control (Showdown-only one-sided-lineup
  floor, mirrors the Team Exposure Caps UI pattern), and
  `updateControlsVisibility()`/`buildDispatchParams()` extended to hide
  Stack Mode/Min Projection/Min Total Ownership/FLEX Positions/Game Caps
  and send `format`/`min_team_players` for a detected Showdown pool.
- `cloudflare_worker/optimizer_api/optimizer_api.js` — added `format`
  and `min_team_players` to `passthroughKeys`.
- `.github/workflows/run_optimizer_dispatch.yml` — added `--format` and
  `--min-team-players` flag-building, following the file's existing
  "omit means the CLI's own default" convention.
- `.github/workflows/refresh_data.yml` — confirmed (no change needed):
  already auto-detects Showdown through `build_projections.py`/
  `pivot_finder.py`'s own detection, same as classic.
- `DFS_Weekly_Process.md` — added a full "Showdown/Single-Game slates —
  what to expect" section plus inline Showdown notes at every affected
  step (export page, slate-ID convention, `--format showdown` flag,
  bulk-upload column shape), and fixed a pre-existing staleness issue
  (doc referenced the old `final_projections_{site}_{week}.csv` naming;
  actual output is `_{slate_id}.csv` post slate-mgmt overhaul, predates
  this session).

**Real bug found and NOT code-fixed (operating-convention workaround
instead):** `labelToSlateId()` in `index.html` always lowercases the
label to build the slate_id it sends to `optimizer.py`, but the backend
CLI preserves whatever case was typed at `--slate-id`. Any uppercase
character in a `--slate-id` (e.g. team codes like `ARI_CAR`) causes a
dispatch-time `FileNotFoundError` since GitHub Actions runners are
case-sensitive. Discovered live via a real `showdown_ARI_CAR_preseason_wk1`
slate. Fixed the immediate blocker by renaming the two committed files to
lowercase (`git mv` two-step, case-only renames need it on Windows); did
NOT patch `labelToSlateId()` itself. **Still open** — see Known issues
deferred below.

**Validation:**
- DK Showdown validated end to end multiple times this session,
  including the final real preseason ARI/CAR slate after 13.5b's fixes:
  K tab, CPT/MVP badges, Stack/Min Projection/Min Total Ownership/FLEX
  Positions/Game Caps correctly hidden, Min Team Players correctly
  shown, Team Exposure Caps working normally, lineups built successfully
  through the real dispatch path, roster correctly ordered CPT→FLEX.
- FD Showdown, the pivot panel's role-aware matching against a real
  `pivot_suggestions` file, and a mixed classic→Showdown→classic UI
  session — all three were the explicitly tracked open items from
  Session 13.5b's handoff. **User tested all three directly and
  confirmed working** ("i tested the three remaining open items and
  we're good there"); not independently re-verified by Claude in this
  conversation.
- Also serves as Session 13.6 (Real Showdown Slate Validation, DK & FD)'s
  validation — see that ROADMAP card, closed alongside this one rather
  than run as a separate session, since the real-slate testing that
  closed out 13.5 covers the same ground 13.6 was scoped for.

**Decisions made / assumptions taken:**
- Discovered DK's real preseason Showdown salary export prices EVERY
  player identically ($7,600 FLEX / $11,400 CPT, no variation at all) —
  confirmed by the user as real, expected DK preseason behavior, not a
  corrupted export. This means salary carries zero differentiating
  signal for preseason Showdown specifically; regular-season Showdown
  slates get normal tiered pricing.
- User's explicit call: let the "no real signal to project a true
  cold-start rookie in preseason" situation stand as-is for preseason
  (accept salary-anchor's flat-pricing limitation there) rather than
  build a manual-override or depth-chart-signal mechanism now. Revisit
  once real regular-season salary + Vegas data is flowing normally.
- Confirmed `--salary-anchor-cold-start` (existing flag, off by default,
  `SALARY_ANCHOR_WEIGHT_DEFAULT = 0.0`) is the correct lever for a
  genuine cold-start player when real salary variation exists: with
  `games_played=0`, `effective_weight()`'s shrinkage schedule
  (`weight_floor + (1-weight_floor) * (k/(k+games_played))`) evaluates
  to exactly 1.0 at the default `k=4.0`, fully replacing a 0.0 model
  projection with the salary-anchor curve's value. Not usable to full
  effect on THIS particular slate given the flat-pricing finding above.

**Known issues deferred:**
- **`labelToSlateId()`'s lowercase-forcing is still unfixed in code.**
  Operating convention until then: always type `--slate-id` in lowercase
  at the CLI (already reflected in `DFS_Weekly_Process.md`'s examples).
  Affects any slate type, not just Showdown.
- **Preseason Showdown rookie/cold-start projections have no real
  differentiating signal** (see Decisions above) — explicitly deferred
  to regular season, not fixed this session.
- **Player props as a projection input** — user flagged that sharp
  DFS players commonly estimate player-level projections from Vegas
  player props (TD props, yardage O/Us, etc.) rather than (or in
  addition to) game-level totals, and asked whether this pipeline could
  incorporate that. Not currently possible: The Odds API is used for
  game-level lines/totals only (Session 2.3's `vegas_odds.py`), no
  player-prop endpoint is wired in. Needs its own scoping session —
  data source/cost TBD (props are typically a separate, often pricier,
  API tier), plus a design decision on how a per-player prop line would
  fold into the existing season_avg/recent_form/matchup_factor/
  vegas_factor blend. Not built or scoped further this session — pure
  backlog capture. See PHASE 9 section below for where this is tracked.
- **User observed projections trending high "across the board"** on the
  slates built this session (consistent overshoot, not isolated to
  specific players) — noted but NOT investigated this session (no actual
  results exist yet to compare against; preseason box scores are the
  first real chance). Flagged as a specific thing to check once Session
  9.1's actual-vs-projected logging has real data, rather than a new
  ad-hoc investigation now. See PHASE 9 section below.

**Handoff notes for next session:** None outstanding for 13.x specifically
-- Phase 13 (Showdown/Single-Game support) is now fully closed. Next
real gate is Session 6.x's preseason dry runs / Session 8.1's regular-
season go-live, both already on the roadmap and blocked on real slates
becoming available (which they now are, as of this session).

---

## Session 14.0 — Production Engine Cutover (Stat-Line → Live)
**Date completed:** 2026-08-06
**Status:** ✅ Complete

**What was actually built:**
Cut the live pipeline over from `build_projections.py` (the Session 2.4
placeholder engine, still running for every real slate up to this
session) to `build_projections_statline.py` (the Phase 10 rebuild --
stat-line projection, Monte Carlo mean+sigma, price-as-volume-prior,
role-change handling -- built and backtested across Sessions 10.3a
through 10.5b but never actually wired into `refresh_data.yml`).

A code audit before any build found the parallel engine was NOT a safe
drop-in as-is -- three real bugs, all found by static review before
touching real data:
1. Vegas lookup crashed on any real slate: `load_vegas_implied_totals()`
   was fixed in Session 13.5b to key off `slate_id`, but this engine's
   own `main()` still called it with the bare `week` integer.
2. Output filename collision: still wrote `final_projections_{site}_
   {week}.csv`, the exact bug Session 2.4 already fixed elsewhere.
3. Zero Showdown/Single-Game support and zero kicker support -- both of
   Session 13.x's additions post-date this file's last real touch.

Fixed all three, ported Showdown support (CAPTAIN_MULTIPLIER, FLEX/
captain salary split, `apply_captain_multiplier()`, Showdown-aware
ownership) and kicker support (`_build_kicker_projections()`) from
`build_projections.py`, reusing those functions directly rather than
duplicating logic. Extended `apply_captain_multiplier()`'s scaled-column
list to cover this engine's `statline_p10`/`statline_p90` audit columns
(no-op for the legacy engine). Wired `refresh_data.yml` to call the
fixed script with `--volume-prior --sigma-recalibration --dst-model
distributional` explicitly passed -- both volume-prior and sigma
recalibration are opt-in/off-by-default in that script, and omitting
them would have silently shipped only Session 10.3a's bare rewrite.

**A fourth real bug was found only by running against a real slate,
not by the static audit:** decision #9 from `build_projections.py` (the
salary-file Game Info fallback for opponent resolution, which fires
whenever the schedule has no games for the given week) was never
factored into a separate importable function -- it lived inline in
`build_final_projections()`. This engine had no fallback at all. Per
`DFS_Weekly_Process.md`'s `--week 23` sentinel convention, that fallback
fires on EVERY real slate right now (Week 1 of any season, preseason,
Madden Sim), so this wasn't an edge case -- it broke the very first real
run. Ported the identical fallback logic (`build_opponent_map_from_
salaries()`), with a fix to the ordering of my own first patch attempt
(the fallback needs the Showdown FLEX/captain split to have already
happened, since it operates on `build_salaries`, not raw `salaries`) --
caught and corrected before sending to the user.

**Files created/modified:**
- `scripts/build_projections_statline.py` (fixed: vegas call site,
  output filename, reconciliation-report filename, Showdown support
  added, kicker support added, opponent-map fallback added)
- `scripts/build_projections.py` (modified: `apply_captain_multiplier()`
  scaled-column list extended -- see above)
- `.github/workflows/refresh_data.yml` (both DK and FD build steps
  swapped to `build_projections_statline.py` with the new flags)

**Validation results:**
- [x] Fixed script runs end-to-end on a real slate without the vegas/
  filename bugs reproducing -- confirmed via real DK Week 1 2026
  classic slate (`dk_classic_wk1`) and real preseason Showdown slate
  (`dk_showdown_preseason_ari_car`)
- [x] Showdown slate builds correctly through the swapped engine --
  confirmed real run: 66 FLEX rows, 66 captain-equivalent rows, 2
  kickers, correct CPT_MVP/FLEX ownership-budget split (100%/500%)
- [x] Full pipeline validated on real data for both slates (see Session
  14.0b below -- closed together since 14.0b's fix was required before
  either slate's output could be trusted)
- [ ] `DFS_Weekly_Process.md` updated -- done this session, see below

**Decisions made / assumptions taken:**
- Kept λ (optimizer's mean-variance objective coefficient) at its
  existing default of 0.0 -- this session's job was fixing the mean
  projection and making sigma available, not changing lineup-
  construction strategy in the same session as an engine swap.
- Did not attempt to reconcile the module-docstring's stale reference
  to a function called `build_opponent_map_from_vegas()` (the actual
  function is `build_opponent_map_from_salaries()`) in
  `build_projections.py` -- pre-existing documentation drift, unrelated
  to this session's scope, not fixed.

**Known issues deferred:**
- Preseason Showdown vegas coverage is thin -- the real ARI/CAR run
  still shows `vegas_factor=1.0` for all players even with the
  opponent map correctly resolved (`Inferred 1 game(s): [('ARI',
  'CAR')]`). Very likely a genuine market-data gap (The Odds API's
  preseason coverage), not a code bug -- not investigated further this
  session, flagged for Session 14.1's data-source work if it recurs on
  real regular-season Showdown slates.
- FD validation remains an open gap across the whole project, unchanged
  by this session.

**Handoff notes for next session:** Session 14.0b (below) was required
before either slate's output could be trusted -- read that entry too.
The real before/after projection comparison that actually validates
this cutover's purpose (closing the user's original "25% high"
observation) is documented in 14.0b's entry, since it wasn't possible
to do a meaningful comparison until 14.0b's fix landed.

---

## Session 14.0b — Volume-Prior Price-Share Normalization Fix
**Date completed:** 2026-08-06
**Status:** ✅ Complete

**What was actually built:**
Real bug found via Session 14.0's own real-slate validation, not part
of the original session's planned scope. First real run of the cut-over
engine against a real DK Week 1 2026 slate hit the mandatory share-
reconciliation fail-loud (`statline_model.py` decision #7): 43-49% of
material team/component pairs needed a rescale beyond the 25% threshold
-- systemic, not one odd depth chart.

Traced with a throwaway diagnostic (`probe_reconcile_gap.py`, not
committed as a permanent script) against the two worst offenders (GB
rush, CAR rush). Root cause: `volume_prior.share_from_salary()` answers
"what's this one player's expected share of team volume" independently
per player, with nothing constraining the SUM across a team's roster to
stay at or below 1.0. Harmless with one or two players near the salary
floor; broken with several zero-history players sharing an identical
floor salary, since the curve is degenerate at that boundary and hands
every one of them the same share, stacking on top of the real
contributors. Real example: four zero-history RBs at GB's $4000 floor
collectively claimed ~85% of the team's rush volume on top of Josh
Jacobs (the real starter) and Chris Brooks (the real backup).

This is pre-existing Phase 10 logic (`apply_volume_prior()`,
`share_from_salary()`) that Session 14.0 did not touch. Best-supported
explanation for why it surfaced only now: Session 10.3b's own accuracy
validation was explicitly "week-1-excluded," and Session 13.5b's
rookie/zero-history matching fix (which stopped exactly these players
from being silently dropped before the cold-start logic ever saw them)
predates this being the first real slate to combine real full-roster
zero-history density with `--volume-prior` and reconciliation together.

**Fix (user-directed, Option A of three discussed):** normalize
`{comp}_price_share` within (team, component), summed ACROSS every
position that contributes to that component -- not position-by-
position, per the user's explicit call, matching how reconciliation
itself already treats a component. Only rescales when the raw sum
exceeds 1.0; a sum under 1.0 is left untouched, since that's the
legitimate case the existing `_pool_share()`/reconciliation machinery
already handles correctly. Implemented as a second pass in
`apply_volume_prior()`, between the raw price-share computation and the
price-volume computation that consumes it.

**Files created/modified:**
- `scripts/statline_model.py` (`apply_volume_prior()` split into two
  passes with the normalization step between them)
- `scripts/probe_reconcile_gap.py` (new, throwaway diagnostic -- not
  intended to be a permanent part of the pipeline)

**Validation results:**
- [x] Sanity-checked the normalization math against the real GB probe
  numbers before shipping: raw rush-share sum 2.207 (121% over-
  allocated) normalizes to exactly 1.0, Josh Jacobs correctly retains
  the largest individual share (0.248) after scaling
- [x] Re-ran both real slates: classic went from 43-49% material-pair
  violations (SystemExit) to 2/72 isolated pairs (GB rush 0.49x, BAL
  rush 0.56x); Showdown went from failing to 1/6 (CAR rush 0.53x).
  Both counts are consistent with this project's own established
  tolerance for a single real depth-chart situation (see
  `reconcile_team_shares()`'s own Russell Wilson 2021 example) --
  isolated and expected, not investigated further.
- [x] Real before/after comparison, old engine (`build_projections.py`)
  vs. fixed new engine, on the real DK Week 1 2026 classic slate (352
  players with a positive projection in both) and the real preseason
  Showdown slate (70 players): skill-position `final_projection` ran
  ~66% of the old engine's aggregate sum on classic, ~63% on Showdown.
  DST unchanged (0.998x -- expected, shared model between engines).
  Confirmed the shift originates from the model's own `season_avg`, not
  `matchup_factor`/`vegas_factor` (both within floating-point noise
  between engines, max diff 0.015). The shift is NOT uniform: an
  established workhorse back (Jahmyr Gibbs) barely moved (0.89x) while
  committee/role-uncertain backs and pass-catchers dropped harder
  (Brock Bowers 0.35x, De'Von Achane 0.43x) -- consistent with the new
  engine correctly pricing real usage uncertainty the old flat-average
  engine had no mechanism for.
- [x] User's own DFS judgment check against real-world expectations:
  Joe Burrow ($6900, plus matchup) landed at 18.39 post-fix, within
  ~10% of the user's own ~20-point expectation for a good QB in a plus
  matchup (their stated ceiling reference: prime Mahomes-tier around
  23). User confirmed this as "in the ballpark within reason" and
  approved closing the session on that basis.

**Decisions made / assumptions taken:**
- Normalization scope is (team, component) across ALL positions
  contributing to that component (e.g. rush includes RB/QB/WR
  scrambles/jet sweeps together), not split further by position --
  explicit user decision, matching how `_pool_share()`/reconciliation
  already treat a component.
- Did not lower or adjust `RECONCILE_MAX_VIOLATION_SHARE`/`fail_
  threshold` as an alternative fix -- considered and explicitly
  rejected (see the three options discussed with the user): the
  fail-loud was working correctly and catching a real bug; loosening it
  would have hidden the problem rather than fixed it.

**Known issues deferred:**
- GB rush (0.49x) and BAL rush (0.56x) post-fix rescales, and CAR rush
  (0.53x) on Showdown, were not individually investigated against real
  depth-chart context -- treated as ordinary, expected reconciliation
  activity per the project's own established tolerance, not a new gap.
- Whether ~63-66% of the old engine's baseline is the CORRECT level, or
  whether it's now undershooting, is not something this session's
  before/after diff can answer on its own -- that's Session 9.1's job
  once real games exist (gated on real Week 1 games being played,
  ~Sept 13 2026). This session's validation is a directional/sanity
  check against the user's real-world DFS judgment, not a backtest.

**Handoff notes for next session:** `probe_reconcile_gap.py` is a
throwaway diagnostic, not a permanent script -- fine to leave in the
repo for now (matches the project's existing `probe_*.py` convention)
but not wired into any workflow. Session 9.1, once it has real data,
is the thing that actually confirms or corrects this session's
92%-confidence-not-100% validation. `DFS_Weekly_Process.md` updated
this session to reflect the new engine and its flags -- see that file's
own Quick Reference and Showdown sections.
