# Regular Season Week 1 Results — 2026-09-13

Output file named by ROADMAP.md's Session 8.1 card ("Outputs: `/logs/regular_season_week1_results.md` (tag results by site)"). See ROADMAP.md's Session 8.1/9.1 cards, the "FD post-lock results/ownership" entry in Known Deferred Validations, and SESSION_LOG.md's two 2026-09-14 "Session 9.1" entries for the full decision trail — this file is the pointer/summary, not a duplicate of that detail.

## DK

**Slates run live:** `dk_classic_wk1_main_13Sep2026`, `dk_classic_wk1_early_13Sep2026`, `dk_classic_wk1_afternoon_13Sep2026`.

**Post-game logging status — complete, all three slates, both results and ownership** (real DK contest-results exports run through `scripts/log_results.py` and `scripts/log_ownership.py`):

| Slate | Results match | Ownership match | Mean error (actual − proj) | Mean abs error |
|---|---|---|---|---|
| main | 307/312 (98.4%) | 307/312 (98.4%) | +1.99 | 4.67 |
| early | 192/194 (99.0%) | 192/194 (99.0%) | +2.05 | 4.93 |
| afternoon | 98/99 (99.0%) | 98/99 (99.0%) | +1.43 | 4.87 |

## FD

**Slates run live:** `fd_classic_wk1_main_13Sep2026`, `fd_classic_wk1_early_13Sep2026`, `fd_classic_wk1_afternoon_13Sep2026`.

**Results — complete, all three slates.** FD does not publish a copyable post-lock results export, so real fantasy points were derived directly from real nflverse box-score stats via a new script, `scripts/derive_actual_results.py`, using `scoring_rules.py`'s already-measured-exact site scoring (not estimated or converted from DK's numbers — see that script's module docstring and SESSION_LOG.md for the full reasoning and cross-check against DK's real export).

| Slate | Match | Mean error (actual − proj) | Mean abs error |
|---|---|---|---|
| main | 683/683 (100%) | +0.26 | 2.42 |
| early | 467/467 (100%) | +0.30 | 2.38 |
| afternoon | 233/233 (100%) | +0.17 | 2.42 |

**Ownership — permanently out of scope, not a gap awaiting more data.** FD does not publish real post-lock ownership anywhere, and real ownership cannot be legitimately derived from box-score stats or from DK's own ownership (who actually drafted which players in a real FD contest is not observable from here). Fabricating it would violate this project's own standing rule against estimating unobserved contest data (see ROADMAP.md's Known Deferred Validations section). `data/ownership_actual_log.csv` staying DK-only is correct; log FD only if FD itself ever starts publishing something real.

## Data-gate progress this unlocked

- Session 9.2 (projection weight retuning): 2 site-weeks / 4 needed (DK week 1 + FD week 1, tracked separately per site).
- Session 11.1 (ownership blend-weight/temperature retuning): 1/4-6 real regular-season weeks logged (DK-only, permanently — see above).

Both remain blocked pending several more real weeks. Log each future week's DK results/ownership and FD results (via `derive_actual_results.py`) the same way as they become available — see `DFS_Weekly_Process.md` Stages 6-7.
