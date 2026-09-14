# Regular Season Week 1 Results — 2026-09-13

Output file named by ROADMAP.md's Session 8.1 card ("Outputs: `/logs/regular_season_week1_results.md` (tag results by site)"). Created 2026-09-14 once the first real post-game results export was available. See ROADMAP.md's Session 8.1/9.1 cards and SESSION_LOG.md's "Session 9.1" entry (2026-09-14) for the full decision trail — this file is the pointer/summary, not a duplicate of that detail.

## DK

**Slates run live:** `dk_classic_wk1_main_13Sep2026`, `dk_classic_wk1_early_13Sep2026`, `dk_classic_wk1_afternoon_13Sep2026` (per `data/current_slate.json`).

**Post-game logging status:**
- `dk_classic_wk1_main_13Sep2026` — ✅ logged 2026-09-14. Real contest-results export (`dk_classic_wk1_main_final_results_13Sep2026.csv`, 15,854-entry single-entry GPP) run through both `scripts/log_results.py` (→ `data/projection_error_log.csv`, 307/312 matched, 98.4%) and `scripts/log_ownership.py` (→ `data/ownership_actual_log.csv`, same match rate). Mean error (actual − projection): **+1.99**, mean abs error **4.67**. By position: QB +6.08, RB +2.51, WR +1.86, TE +1.16, DST −1.30.
- `dk_classic_wk1_early_13Sep2026` — not yet logged. No results export provided for this slate.
- `dk_classic_wk1_afternoon_13Sep2026` — not yet logged. No results export provided for this slate.

## FD

**Slates run live:** `fd_classic_wk1_main_13Sep2026`, `fd_classic_wk1_early_13Sep2026`, `fd_classic_wk1_afternoon_13Sep2026` (per `data/current_slate.json`).

**Post-game logging status:** none yet — no FD results export has been provided. FD's own actual-vs-projected and actual-ownership data points are still open; this is the standing "closes only once a real FD results export exists" gap, same shape as every other FD-specific item tracked in ROADMAP.md's "Known Deferred Validations" section.

## Data-gate progress this unlocked

- Session 9.2 (projection weight retuning): 1/4 real regular-season weeks logged (DK only, main slate only).
- Session 11.1 (ownership blend-weight/temperature retuning): 1/4-6 real regular-season weeks logged (DK only, main slate only).

Both remain blocked pending several more real weeks — see ROADMAP.md for each session's own data-gate requirement. Log DK's remaining Week 1 slates and any FD Week 1 results/ownership exports the same way (`scripts/log_results.py log` / `scripts/log_ownership.py log`, see `DFS_Weekly_Process.md` Stages 6-7) as they become available, rather than waiting for Week 2.
