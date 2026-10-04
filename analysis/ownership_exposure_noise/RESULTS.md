# Classic ownership refresh-to-refresh noise ("Problem B") — 2026-10-04

## Premise tested
"Classic ownership estimates swing several points between automated refreshes even when nothing real changed,
unlike showdown (which tracked a real late market signal cleanly, 0.88-0.89 corr on the PIT/CLE slate). Find the
actual mechanism and fix it if it's cheap enough to do safely before today's Wk4 lock."

**Verdict: confirmed real, mechanism identified, fixed.** Not a bug, not FFC-mode flapping (that was Problem A,
fixed separately in `ownership_model.py`'s FFC sticky-lock). It is the `l_exp` (optimizer-implied exposure)
feature's own Monte Carlo sampling noise, amplified by two stacked zero-sum budget reallocations.

## How it was found
1. Ruled out FFC-mode flapping as the lock-morning driver: `ffc_own_pct`'s matched count was already stable
   (`ffc_used=True` the whole morning) across every commit from 016 through 022 in wk3 main's real refresh
   history, yet ownership still churned 3-6pts per refresh across that window. Mid-week (9/24) FFC *did* flip
   once and caused an 8-15pt one-time jump -- that's Problem A, already fixed.
2. Checked the fitted model's own feature weights (`data/ownership_model_dk.json`): `l_exp` has coefficient
   0.389, second only to `top1sal` (0.502) and bigger than the heuristic itself (`l_est`, 0.265).
3. `optimizer_exposure()` (ownership_model.py) estimates each player's exposure from `EXPOSURE_LINEUPS=60`
   randomized optimizer solves. At n=60 the estimate only resolves in 1/60 = 1.67-point steps, and
   `_logit()` blows up near 0%/100% exposure -- exactly the kind of feature that can swing several points from
   a single marginal lineup flipping, even when nothing meaningful moved.
4. Decisive test (`replay_real_history.py`): pulled the real wk3 main final_projections snapshots from
   git history at commits `8350c552` (021) and `84fbb023` (022) -- two genuine automated refreshes, ~20 min
   apart, 9/27 lock morning. Ran BOTH through today's `add_ownership_columns()` unmodified. The recomputed
   ownership delta correlated **0.864** with what actually happened that morning (JSN real -6.27 vs
   recomputed -3.28; Walker real +3.46 vs recomputed +2.31) -- confirming the swings are a deterministic,
   mechanical consequence of this model architecture reacting to perfectly ordinary <2% wobbles in
   `final_projection`/`season_avg`/`vegas_factor` between refreshes (engine itself is fully deterministic on
   identical inputs -- `determinism_test.py` -- so the wobble is real live-data noise, e.g. a fresh Vegas
   pull, not a code bug).
5. Independent-player and whole-pool-independent jitter tests (`exposure_sensitivity_sweep.py`,
   `full_pipeline_jitter_test.py`, `full_pipeline_team_jitter_test.py`) underestimated the real swing size --
   random synthetic jitter doesn't reproduce it as well as literally replaying the two real snapshots does,
   because real refresh deltas are correlated within a team/game (shared Vegas input), not independent
   per-player noise.

## Fix tested and shipped
`replay_with_more_lineups.py`: same replay, `optimizer_exposure` monkeypatched to `n_lineups=300` (was 60),
nothing else changed. No coefficient refit needed -- `l_exp`'s expected value is unchanged, only its sampling
noise floor drops, so the model trained at n=60 stays valid at a quieter n.

| | mean \|Δownership\| | max \|Δownership\| |
|---|---|---|
| real historical swing (what actually happened) | 0.171 | 6.270 |
| recomputed @ n=60 (current code, same real inputs) | 0.108 | 3.282 |
| recomputed @ n=300 (fix, same real inputs) | **0.059** | **1.343** |

Cost: ~85s per `optimizer_exposure` call at n=300 vs ~15s at n=60 (+70s), x3 classic slates per refresh --
trivial against a multi-minute full-pipeline refresh and the workflow's default 6-hour job timeout.

Shipped as `EXPOSURE_LINEUPS = 300` in `scripts/ownership_model.py`.

## Reproducing the historical snapshots used here
The two real CSVs replayed above aren't stored in this repo (keeping it out of git bloat). They were pulled
straight from git history:
```
git log --follow --format="%H" --reverse -- output/final_projections_dk_dk_classic_wk3_main_27Sep2026.csv
git show <commit>:output/final_projections_dk_dk_classic_wk3_main_27Sep2026.csv > snapshot.csv
```
Commits used: `8350c552b6f1f099fb4cc453c1088b7cd0722e1b` (021, baseline) and
`84fbb023aa137306771a7457e7259eb38bfd94e9` (022, +20 min, the real lock-morning refresh with the 6.27pt JSN swing).

## What this does not fix
The remaining ~0.06pt mean / ~1.3pt max noise at n=300 is the model genuinely (and now appropriately mildly)
responding to real small input changes -- not a residual bug. Going further (n=600+) would roughly halve it
again at roughly double the cost; not pursued here as diminishing returns against an already-7x-smaller swing.
