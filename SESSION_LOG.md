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
