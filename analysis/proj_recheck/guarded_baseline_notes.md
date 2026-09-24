# Guarded re-baseline (Step A2, 2026-09-24)

Build: current main incl. QB guard (0c09a0f) + `--backtest-no-leak` (new; skips played-week team correction and
no-game zero-out). 6 real DK classic slates, wk1 `--season 2025 --week 23`, wk2 `--season 2026 --week 2`, all
5 build flags as in CI, no props snapshot (props inert). Harness: `baseline_guarded.py <dir>` (accuracy.py, FIX
sources swapped). n = 252 player-weeks (proj>8). Full output: `guarded_out.txt`. OLD = committed pre-fix output.
FIX_NS = engine only, FIX = engine + projection stack (what ships).

| | OLD | FIX_NS | FIX (ships) |
|---|---|---|---|
| bias | -3.36 | -0.67 | +0.01 |
| MAE | 6.42 | 6.37 | 6.33 |
| RMSE | 9.00 | 8.45 | 8.11 |
| Spearman within slate x pos (22 cells) | .235 | .238 | .248 |
| mean actual of projected top-N | 16.06 | 15.63 | 16.29 |

Read plainly: with the guard, the earlier ranking REGRESSION is gone (.201 -> .238/.248; top-N 14.79 -> 15.63/16.29)
and bias/RMSE are clearly better, but ranking is NOT clearly better than OLD either. Every paired CI vs OLD
straddles 0 (Spearman FIX-OLD +.013, -.091..+.097; top-N +0.23, -1.46..+1.83). Honest summary: bias fixed,
ranking restored to parity. n=6 slates / 2 weeks.

Per position (Spearman OLD/FIX_NS/FIX): QB .138/.121/.244, RB .368/.329/.458, WR .375/.386/.451,
TE -.029/.055/-.365. Watch: the stack makes TE ranking much worse (6 cells, tiny n) -- check in B/C.
QB/RB/WR benefit from the stack. The "large inflation" list is now benign (QBs 30-36 att, no >50).
Weak spots that remain: 6-7.5k and 7.5k+ tiers still under-projected (bias -2.0, -3.1); wk1 bias -1.3 vs wk2 +1.2.
