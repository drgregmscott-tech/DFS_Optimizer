# HANDOFF -- Week 3 weekend status + post-Week-3 ownership refit plan (written Fri 2026-09-25)

Companion to `analysis/prelock/SUNDAY_PRELOCK_CHECKLIST.md` (Sunday runbook) and
`HANDOFF_next_session_backtest_2026-09-24.md` (accuracy backlog). This file records what the
Friday status check found and fixed, what is left, and the ownership refit/test plan.

## 1. Fixed Friday 2026-09-25 (all on origin/main)
- **Out-QB promotion** (`2a746d7`): `statline_model.promote_depth_for_out_qbs()`, called from
  `build_projections_statline.py` before the volume prior. Depth-chart QB1 who is OUT/DOUBTFUL no
  longer holds the team's pass volume. WAS: Mariota 12.5 -> 33.2 pass att, 6.9 -> 10.0 pts.
  QB only; RB/WR/TE OUT cases still use the A4 backup boost.
- **DK afternoon classic slate added** (`7f0ae2e`): `dk_classic_wk3_afternoon_27Sep2026`, lock 20:05Z,
  ARI@SF, MIN@TB, BAL@DAL, LV@NO. Salary ingest needs `--season 2025` (2026 matched only 52.6%).
  Props: `props_auto.py` reuses the main slate's snapshot (same games, reuse window 8 h). FD gets no props.
- **Murray manual override** (`b04217d`): `data/manual_role_overrides_2026_3.csv`, rush share 0.45
  (measured against `team_carries_history` ~15; gives ~4.7 carries). 2025 ARI avg 5.8 carries/g vs 1.5
  modelled. Murray 12.7 -> 13.5 (DK), ~14.7-14.9 (FD); public ~17.6. **Delete/stale-proof:** the file is
  week-scoped by name (`_2026_3`), so it cannot leak into Week 4.
- **Doubtful = OUT in status apply** (`2785689`): `status_check.py apply` zeroes DOUBTFUL (label kept,
  p10/p90 zeroed, ownership refreshed). Questionable is NOT discounted (no evidence for a haircut size).

## 2. What must happen SUNDAY (none of it can be done earlier)
| When (UTC / CDT) | Action |
|---|---|
| 08:00Z / 03:00 | Automated full refresh pulls props (~144 of ~227 credits) for main/early; afternoon reuses it |
| ~09:00Z / 04:00 | `git pull`, `python analysis/prelock/prelock_check.py`. Check: props PASS + movers table; no `[FAIL]`; Murray/Mariota/Taylor still as above; wind TEN@NYG (22 mph on Fri forecast) |
| 12:00Z | Full refresh (status, vegas, FFC, rebuild) |
| ~15:30Z | Inactives for 17:00Z games: scan news for your core players |
| ~16:00Z | Full refresh picks up inactives. `prelock_check` again. If no new commit by 16:25Z, dispatch "Refresh Data" by hand (Fix A) |
| by 16:55Z | Final builds and upload for DK main/early, FD main/early (no props on FD) |
| ~18:35Z | Inactives for 20:05/20:25Z games (DK main late players, DK afternoon) |
| 19:00Z | Full refresh; `prelock_check --slate-id fd_classic_wk3_afternoon_27Sep2026` |
| by 20:00Z | Upload FD afternoon and DK afternoon. DK late swap only for confirmed inactive/role change |
| after 19:00Z | If late-window news breaks, dispatch the refresh by hand or swap manually (no scheduled pull) |
Also Sunday: the **Questionable list** (21 on DK main, 10 on afternoon) can only be resolved on the day;
cash rule = exclude Q players in 17:00Z games unless confirmed by 16:50Z. Also the **100-lineup pool
experiment** (checklist section 5b) runs after the props rebuild; save the entered set.

## 3. What happens MONDAY (or Sun night) -- nothing before this
1. Download DK contest results + ownership exports for each Week 3 classic slate; log them
   (`log_results.py`, `log_ownership.py`, sum ALL rows per player incl. FLEX; derive FD results with
   `derive_actual_results.py`). Week 3 = fold 3 for every retest bar.
2. Grade entered vs un-entered pool lineups against real results (adds slates 7-9 to replay evidence).
3. Props first-live evaluation: did the anchor help or hurt vs actuals (checklist W3; PROPOSALS #4 FD props).
4. Monday-night showdown (if one is configured): its own lock/props pull at 23:00Z Mon.
5. Then run the plan in section 4, and re-test the deferred engine items in
   `HANDOFF_next_session_backtest_2026-09-24.md` (p10 dart threshold, stack refit/TE, moved-QB pre-scale
   volume -- now visible in Murray's 6x MIN pass rescale).

## 4. Post-Week-3 ownership refit plan
**Problem.** Model vs FFC on top chalk (DK main wk3): Kelce 19 vs 46, Mahomes 18 vs 46, Gibbs 47 vs 63.
Chalk bias was -4.1 pts with the FFC variant, cheap-crowd plays under-estimated. Already tested with no
gain (do not retry): sharper softmax, last-week ownership, salary change, last-week points, injured-teammate
vacuum, stacked-optimizer exposure, heavier FFC blending.

**Sunday rule (no model change).** Cash: ignore. GPP/MME: treat model-far-below-FFC players as chalk, use the
higher of the two; no leverage play on a model-only low-ownership call unless FFC agrees.

**Steps (after step 3.1 is logged):**
1. Rebuild the 6 wk1/wk2 DK classic slates leak-free with FINAL code (`--backtest-no-leak`; wk1 `--season 2025
   --week 23`, wk2 `--season 2026 --week 2`; check every build prints `Wrote N players`; restore `output/`
   after with `git checkout -- output/<files>`; never commit test rebuilds). Add the 3 wk3 slates.
   Note the wk3 builds include the QB promotion, Murray override and Doubtful zeroing.
2. Refit BOTH `data/ownership_model_dk.json` and `data/ownership_model_dk_ffc.json` with
   `scripts/fit_ownership_model.py` (FFC variant = `om.FEATURES + om.FFC_FEATURES`), leave-one-week-out on
   3 weeks, meaningful cut (proj > 8). Baseline to beat: corr .764, chalk bias -4.1 (FFC variant).
3. **One new test: FFC floor.** For players FFC lists above ~30%, set estimated ownership = max(model, a * ffc)
   with `a` chosen only by leave-one-week-out (start 0.7). Report corr, chalk-tier bias, top-10 overlap. Ship
   only if it improves held-out weeks in >= 2 of 3 folds AND does not hurt the sub-10% tier. Report n honestly
   (3 weeks, ~9 slates, overlapping).
4. Also check: does status apply's ownership refresh (OUT + now Doubtful) change chalk vs the build-time number.
5. Showdown ownership is separate (`ownership_model_showdown.py`, refit on 4 slates Friday); not part of this.

## 5. Known gaps still open (not Sunday-blocking)
- FD has no props anchor (`props_auto.py` skips FD); PROPOSALS #4, test after Week 3.
- Moved/backup-QB volume is still patched by hand (Murray) rather than modelled: MIN pass scale 6.0x.
- `p10` still too high on cheap players' lower tail; dart threshold re-set pending (d_report.md section 6).
- `logs/unmatched_salaries_dk_dk_classic_wk3_afternoon_27Sep2026.csv` untracked (empty of players; ignorable).
