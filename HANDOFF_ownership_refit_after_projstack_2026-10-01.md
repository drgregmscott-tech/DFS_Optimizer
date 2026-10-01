# Handoff: refit ownership v2 after the RB/WR/TE projection-stack swap (2026-10-01)

## Where this comes from

Full chain this week: `analysis/cheap_wrte_ownership/RESULTS.md` found the $7k+/cheap-WR/TE chalk gap →
`HANDOFF_ownership_ranking_signal_2026-09-30.md` reframed it as a ranking miss, not a sizing miss →
`analysis/ownership_rank_signal/RESULTS.md` confirmed it, then its follow-up (`test_proj_swap.py`) proved
the lever is projection accuracy, not ownership logic: swapping a better projection into ownership's
*existing, unrefit* features raised chalk rank-recall from 43.3% to 47.3% (closing the gap to FC's own
47.6%). That pointed straight at the already-shelved RB/WR/TE projection-stack refit
(`WK3_POSTMORTEM_OPEN.md` item 8, originally from §6) — refit and shipped live today.

## What's live now (as of 2026-10-01)

- `data/projection_stack_dk.json` — the production projection-stack artifact every slate build reads —
  now holds **new RB/WR/TE coefficients** (fit on 2021-25, `analysis/proj_stack/refit_eval_rbwrte.py`),
  merged with the **QB block unchanged** from the prior 2020-21 fit. QB is intentionally excluded from the
  new refit; it already has its own separate wk3+ recal/autopromote layer
  (`scripts/build_projections_statline.py`), so this QB block is just a week1-2 safety net, not a live
  lever.
- Old live artifact backed up at `data/projection_stack_dk.json.bak_2026-09-21` — restore from there if
  anything looks wrong this week.
- Validated: RB/WR/TE MAE and bias improve every season 2021-2026 (not just on average — check
  `analysis/proj_stack/refit_eval_rbwrte_out.txt` for the full per-season table). Lineup-level score impact
  is directionally positive most seasons but the aggregate 95% CI still includes 0 (n=88 history slates) —
  real, honest caveat: don't oversell the lineup-level number, the per-player accuracy gain is the solid
  part.
- Smoke-tested: `projection_stack.load_artifact("dk")` loads and `apply_stack` scores cleanly on synthetic
  rows. Not yet tested against a real live slate build end-to-end — **do that first thing next session**
  (run a normal classic projection build for the current week and sanity-check the output looks reasonable
  before trusting it for a real slate).

## What's NOT done yet — this is the actual task for the new chat

**Refit the ownership v2 coefficients against the new projections.** Ownership's `proj`/`val` features are
computed live from whatever `scripts/projection_stack.py` currently outputs, but the ownership model's own
fitted weights (`data/ownership_v2_dk_linear.json`, `data/ownership_v2_dk_dst.json`) were calibrated against
the *old* (2020-21, QB-included) projection-stack output. The rank/value distribution they were trained on
has now shifted for RB/WR/TE.

**Is this urgent?** No — treat it as a polish pass, not a blocker. The ranking-signal diagnostic
(`analysis/ownership_rank_signal/RESULTS.md`, follow-up section) already proved the gain shows up even on
*unrefit* ownership coefficients, just from swapping in a better projection. So ownership is already
reaping some of this benefit live, right now, with no further action. A refit should still close the loop
and squeeze out the rest, but there's no fire to put out.

### The rebuild chain (real, multi-step, not a single script)

This is the actual reason this got split into its own session — it's a chain of several existing scripts,
not a quick diff:

1. **Regenerate history projections with the new stack.** The projection engine needs to run across all
   2021-25 history slates with the new `data/projection_stack_dk.json` in place (it already is — this step
   is just re-running whatever script originally built `data/fc_history/derived/fc_own_features_ourproj.parquet`
   so it picks up the new RB/WR/TE coefficients). Look at `analysis/ownership_fc_refit/build_ourproj_features.py`
   first — that name matches the artifact.
2. **Rebuild `analysis/model_vs_fc/frame.parquet`** (via `analysis/model_vs_fc/build.py`) — this merges the
   regenerated projections into the frame `analysis/ownership_v2/build.py` reads for `proj`/`final_projection`.
3. **Rebuild ownership's history frame**: `analysis/ownership_v2/build.py` → writes
   `data/fc_history/derived/ownership_v2/hist.parquet`. This is the file every ownership test this week
   (`cheap_wrte_ownership`, `ownership_rank_signal`, etc.) reads.
4. **Refit the linear ownership artifacts** on the rebuilt `hist.parquet`. Find the script that originally
   produced `data/ownership_v2_dk_linear.json` / `data/ownership_v2_dk_dst.json` (grep for `linear_path(` /
   `dst_path(` writers in `analysis/ownership_v2/` or `scripts/ownership_v2.py` itself — I did not locate
   the exact writer script this session, confirm it exists before assuming you need to write one from
   scratch).
5. **Re-run the same evidence bar as every other ownership test this week**: LOSO 2021-25 first (corr,
   catch20, bias20, cheap-WR/TE corr, $7k+ corr — `common.metrics`/`mtable` already does this), then the
   2026 wk1-3 live check. Grade against real DK ownership only, never FC's dead projected-Own column.
6. **Ship bar**: don't ship on a worse catch20/bias20/corr than the current live artifact on any of the
   graded slices. If it's mixed, treat it the same way `chalk_size_fix`/`chalk_temperature` were treated —
   write the honest verdict, don't force a ship.

### Restate the premise before starting (standing project rule)

Confirm for yourself first: "the projection-stack refit changed the proj/val distribution that ownership's
linear model was calibrated on; refitting that model should recover additional accuracy beyond what
swapping the raw feature already bought for free." Check that against the rebuilt `hist.parquet` before
assuming it's true — it's the natural next step, not a guaranteed win.

## Priority list for this weekend (ranked)

1. **Sanity-check the live projection-stack swap on a real upcoming slate build** before trusting it —
   run the normal classic build for this week's slate(s), eyeball RB/WR/TE projections for anything
   obviously broken (the smoke test so far was synthetic rows only).
2. **Ownership v2 refit** (this handoff) — polish pass, not urgent, but the natural next session; closes
   the loop on the $7k+/cheap-WR/TE chalk work from this week.
3. **QB projection gap vs. FC** — smaller, lower priority, unchanged from before, fine to leave for later.
4. **Other open items untouched this week, in `WK3_POSTMORTEM_OPEN.md`:** Showdown `lsal` candidate
   re-test (date-gated on Wk4 Showdown results), inactives-timing log (needs Sunday 2026-10-04 to run),
   §5 frontend/rule additions (own short session), FFC-cliff-removal watch item (also Sunday-gated).

## Files from this session

- `analysis/ownership_rank_signal/RESULTS.md` (+follow-up section), `test_rank.py`, `test_proj_swap.py`,
  outputs — all DO NOT COMMIT (FC-derived aggregates) except the `.py` scripts themselves.
- `analysis/proj_stack/refit_eval_rbwrte.py`, `refit_eval_rbwrte_out.txt` — the RB/WR/TE-only refit.
- `data/projection_stack_dk_refit_rbwrte_2026-10-01.json` — the raw RB/WR/TE-only artifact (research
  output, not what's live).
- `data/projection_stack_dk_LIVE_CANDIDATE_2026-10-01.json` — the merged (new RB/WR/TE + old QB) candidate,
  now copied into the live path.
- `data/projection_stack_dk.json` — **live production file, now updated**.
- `data/projection_stack_dk.json.bak_2026-09-21` — **backup of the pre-swap live file**, restore from here
  if needed.
- Nothing committed to git this session.
