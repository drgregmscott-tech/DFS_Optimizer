# Stacked-exposure feature test (2026-09-23, uncommitted)

Scripts: `stacked_exposure.py` (builds exposure, ~5 min for 6 slates x 3 settings), `stacked_exposure_eval.py` (LOWO).
Outputs: `stacked_exposure_results.csv` (pooled / per-slate / per-week metrics + team eta2), `stacked_exposure_deltas.csv` (paired deltas, bootstrap CI).

Stacked lineups: per noisy draw (60, 25% noise, seed as optimizer_exposure, uniqueness 1) solve unstacked, take its QB team,
re-solve with stack_mode="qb" on that team. Settings (pre-specified): qb1 (QB+1 WR/TE), qb2 (QB+2 WR/TE/RB), qb1bb (QB+1 + bring-back). 0 fallbacks.

Verdict: no feature clearly and consistently helps. l_sexp is 0.92-0.95 correlated with l_exp and slightly hurts every variant.
team_qb_share is the only candidate: base +0.013 corr (CI .002-.024), +FFC +0.004 (6/6 slates up, but week-2 delta ~0).
Team-clustered residual share barely moves (+FFC 0.295 -> 0.284; permutation baseline 0.25). Not recommended for integration.
