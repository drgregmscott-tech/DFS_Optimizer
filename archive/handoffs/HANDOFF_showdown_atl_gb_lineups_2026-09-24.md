# HANDOFF -- DK Showdown ATL @ GB lineups, TONIGHT (written 2026-09-24 ~5:50 PM CT)

Slate: `dk_showdown_wk3_Atl_GB_24Sep2026`. **Lock 2026-09-25 00:15 UTC = 7:15 PM CT.** Projections and ownership are
considered FROZEN for this session's purposes: the only thing that may still change them is the automated refresh
(below). Do NOT change engine/ownership code, do NOT push changes to scripts/ or data/ (other than data that this
session's own lineup work needs). This session = build lineups, nothing else.

## 1. First 3 minutes: is the final refresh in?
The full refresh fires 23:00 UTC (6:00 PM CT), ~75 min before lock; it re-pulls Showdown props (6 credits; ~227 left),
re-applies injury status, rebuilds projections + pivots, and commits.
```
git fetch origin && git log origin/main --format='%h %ci %s' -8 | grep -i showdown
git pull --rebase origin main
```
Look for an automated commit for `dk_showdown_wk3_Atl_GB_24Sep2026` timestamped after 23:00 UTC. If it has not landed by
~6:30 PM CT, build from the current file (props anchor + status already applied at ~11 AM CT) and check injuries manually.
Files: `output/final_projections_dk_dk_showdown_wk3_Atl_GB_24Sep2026.csv` (FLEX rows + CPT rows, `roster_role`),
`output/pivot_suggestions_dk_...`, `output/lineups_multi_dk_...` (STALE batch from before the changes: rebuild it),
`data/salaries_dk_dk_showdown_wk3_Atl_GB_24Sep2026.csv`, `data/props/props_dk_showdown_wk3_Atl_GB_24Sep2026.csv`,
newest `output/player_status_3_*.csv` (last seen 09-24 00:01 UTC).

## 2. State of the projections (as of my last build, 09-24 ~11 AM CT; verify against the post-23:00 file)
- Built with the shipped engine (QB guard; matchup neutral; stack N/A on showdown) + props anchor on (25 of 29 market
  players matched, weight 0.5, clamp 0.5-1.8x). Top FLEX projections: Bijan Robinson 19.7, Jordan Love 18.1, Christian
  Watson 15.9, Michael Penix Jr. 13.6, Matthew Golden 12.5, Drake London 12.4, Tucker Kraft 9.5, kickers ~8, Packers DST 8.0.
- Props moved: Bijan +3.8, London +3.5, Kraft +2.5, Pitts +2.3; Love -0.9. 14 OUT players zeroed (incl. Josh Jacobs, Jayden Reed).
  **Re-verify OUT/QUESTIONABLE status right before building; a stale status file is the main remaining risk.**
- Known caveats (small n): projections ~5/10, ownership ~6/10 confidence; sigma/p10 too high on cheap players (p10 not fixed);
  QB ranking is noisy; kickers project ~8 nearly flat so K/DST choices are close to coin flips.

## 3. Ownership for Showdown
`scripts/ownership_model_showdown.py` (ridge on logit real ownership; 3 real slates by now if NYG@LAR got logged --
CHECK whether `HANDOFF_showdown_session2.md` step 1-2 (log NYG@LAR results into data/ownership_actual_log.csv, refit with
`python scripts/ownership_model_showdown.py fit --validate`) was ever done; if not, do NOT refit tonight -- ownership is
frozen; just note it for the next session). Known miss: narrative/mid-price pass-catchers are under-estimated by ~30 pts
(Waddle wk1, Warren wk2). Treat model ownership as approximate; the FLEX/CPT numbers in the frontend are model-only (FFC has
no Showdown ownership).

## 4. Lineup construction tooling (all existing; do not rebuild)
- Frontend (static site reading GitHub) -> Build Lineups dispatches to GitHub; or locally:
  `python scripts/optimizer.py --site dk --slate-id dk_showdown_wk3_Atl_GB_24Sep2026 --n-lineups 20` then
  `python scripts/pivot_finder.py --site dk --slate-id dk_showdown_wk3_Atl_GB_24Sep2026`. Per-row lock/exclude works on
  CPT vs FLEX rows separately (`pid:CPT` / `pid:FLEX`). Showdown needs both teams represented (min per team enforced).
- Findings from real Showdown slates (n=2-3, low confidence; see HANDOFF_showdown_session2.md sections 3-5,
  analysis/showdown_own/): 5-1 team splits performed best; chalk CPT analysis; simulated field in scripts/showdown_field.py;
  "pick best single lineup" scripts in analysis/showdown_own/best_single.py (uncalled score() kept). The recommended-lineup
  FEATURE was removed from the product (Greg didn't like it: slow, no edge shown) -- do not resurrect it; use these scripts only as
  analysis if asked.
- Memory notes: Greg excludes/thumbs-downs suspect backups in small builds and rides them in MME; lean DST/K cheap-and-believable
  over literally cheapest (small-sample tail risk).

## 5. Do / don't
- DO: confirm final refresh + injuries, build the lineup batch, explain the picks and the confidence basis honestly (n is tiny).
- DON'T: rebuild projections by hand, re-pull props (credits), touch the engine/ownership model, or push to scripts/. Another
  parallel session may be working in the repo: stage explicit paths only, never `git add -A`, fetch+rebase before push.
- After lock: log the Showdown results when available (Stage 7/6), which feeds the ownership refit (see
  HANDOFF_next_session_backtest_2026-09-24.md).

## 6. Prompt to paste
```
Read HANDOFF_showdown_atl_gb_lineups_2026-09-24.md. Confirm the 23:00 UTC refresh landed for dk_showdown_wk3_Atl_GB_24Sep2026 (lock 00:15 UTC), check current injury status, then help me build my lineups. Projections/ownership are frozen; no engine changes.
```
