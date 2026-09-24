# Projection-fix recheck (2026-09-23)

Scripts: `accuracy.py`, `stack_check.py`, `shipped_variants.py` (reuses pivot_rerun harness `blc.score` + `rv.grade`).
Outputs: `accuracy_summary.csv`, `ranking_by_slate_pos.csv`, `stack_r2.csv`, `ship_*.csv`, `*_out.txt`.

Variants: OLD = committed output/ (pre-fix, pre-stack). FIX_NS = leak-free rebuild engine_projection
(wk1 fin/, wk2 rb_nolk/; equals nostack/ build exactly on wk1; nostack/ wk2 is the LEAKY build, not used).
FIX = same rebuild + stack. The props step never ran: no props snapshot exists for any of the 6 classic slates.
Pool forced to OLD's lock pool. Actuals from data/projection_error_log.csv. n=254 player-weeks with proj>8.

## 1. Accuracy (deduped player-week; bias = proj - actual)
| | OLD | FIX_NS | FIX |
|---|---|---|---|
| bias | -3.37 | -0.40 | +0.13 |
| MAE | 6.41 | 6.83 | 6.46 |
| RMSE | 8.98 | 9.90 | 8.44 |
| QB MAE / RMSE | 7.94 / 10.07 | 9.86 / 14.97 | 7.78 / 10.10 |
| Spearman within slate x pos (22 cells) | .226 | .201 | .184 |
| value Spearman (pts/$) | .090 | .079 | .044 |
| mean actual of projected top-N | 16.06 | 14.79 | 15.28 |

MAE diff FIX_NS-OLD +0.42 (95% -0.21..+1.12); FIX-OLD +0.05 (-0.45..+0.56). Top-N actual FIX_NS-OLD -1.27 (-2.59..-0.10), the only
significant rank metric, and it gets worse. Bias improved a lot; ranking did not improve and may have got worse.

**A bug in the reconcile fix itself (wk1):** `raw_sum` drops players whose `hist_team` (team of last game played) differs from the
current team, but `scale` is still applied to them. When the mover is the starting QB, raw_sum becomes the backups' volume only, so the starter gets
scale x his own mu: Cousins LV 134.5 pass att / 62.2 pts, Murray MIN 134.9 / 57.0, Geno NYJ 118.8 / 52.5, Willis MIA 59.9 / 32.8 (OLD 7-9 pts;
actual 15.8, 0.6, 9.3, 17.7). Without these 4 players (5 rows), wk1 QB R2 goes OLD .27 -> FIX_NS .37 -> FIX .50 (all players, stack_r2.csv). So part of the fix works
(real Burrow/Hurts/Lamar under-projection fixed), and it also has a clear failure mode. Wk2 has none of these blow-ups because hist_team had caught up after one game.

## 2. Shipped cash drop (seed 3, pct per slate wk1 m/e/a, wk2 m/e/a)
| variant | per slate | mean | cash |
|---|---|---|---|
| OLD | .90 .56 .92 .66 .26 .92 | .703 | 3 |
| FIX | .66 .53 .52 .50 .39 .90 | .583 | 1 |
| FIX, 4 blow-up QBs reset to OLD | .61 .67 .89 .50 .39 .90 | .660 | 2 |
| FIX_NS (no stack) | .91 .36 .80 .66 .39 .63 | .623 | 2 |
| OLD x exp(N(0,.05)) draws 1-3 | | .664 / .544 / .643 | 3/1/1 |
| FIX x noise draws 1-3 | | .563 / .590 / .641 | 2/2/2 |

FIX lineups on wk1 took Cousins (main), Geno (early) and Murray (afternoon, scored 0.6). Those are exactly the blow-ups. Paired bootstrap
FIX-OLD -0.120 [-0.261,+0.015]; after the reset -0.043 [-0.160,+0.071]; noise-averaged FIX-OLD -0.019 [-0.22,+0.22].
5% projection noise moves a slate's percentile by 0.19-0.20 on average (e.g. OLD wk1 afternoon .92 -> .37), and OLD's own 0.703 lands at
.54-.66 under noise, so it was a lucky draw. Seed also matters for OLD (s5 = 4/6, .753); FIX is seed-invariant.
Verdict: about 2/3 of the drop comes from the blow-up bug (signal, but from one bug). The rest is inside noise. The docstring's 3/6 / .703 is not a stable baseline.

## 3. Stack
The -28/-24/-24/-11 deltas are the stack's 0.5x floor clamp (STACK_LO) biting on the reconcile blow-ups. The stack pulled them toward the truth,
but only halfway. It is not a stack pathology. Excluding those players, all-player R2 is wk1 .486 -> .530 and wk2 .422 -> .450, the same direction as the
docstring (.331->.426, .374->.420) but smaller. Among |delta|>=2 moves (n=129 excluding blow-ups), the stack was closer only 46.5% of the time. MAE effect
-0.37 (-0.83..+0.05). The stack is roughly neutral to mildly positive. Among proj>8 players, the TE/QB rank metrics get worse with the stack (small cells).

## 4. Leaks in the fixed rebuilds
- Played-week zeroing: wk2 disabled (rb_nolk). No player that was live in OLD is zeroed in FIX on any slate (checked).
- depth_charts_current.parquet: the build uses the latest snapshot (2026-09-23). Compared with lock-time snapshots, the QB #1 changed only ATL (Tua->Penix) and NYG
  (Dart->Winston) in wk1, and NYG in wk2. No ATL/NYG QB is in the proj>8 set. 2-3 WR/TE #1 changes per week. Small leak, direction probably slightly favours FIX.
- Injury status: wk1 uses player_status_23_20260913_235229, wk2 uses player_status_2_20260921_234547. Both were pulled after games started. Only the role-change boosts are affected, since
  the pool is forced to OLD's. Small leak, favours FIX.
- Usage/stack features filter week < slate week (clean). The wk1 week-23 convention uses the whole 2025 season (clean).
Net: the leaks favour FIX slightly, so FIX's non-improvement is if anything overstated in its favour.

## 5. Verdict
- Keep the hist_team reconcile fix, but it needs a guard before Week 3: apply `scale` only to attributable players (or bound a mover's volume by
  his raw mu / the team target). Also add an assertion such as proj_pass_att <= ~50. Week 3 risk: offseason movers who have not played for the new team yet (returns
  from injury) and in-season trades. Quick check on each W3 build: grep for proj_pass_att > 50 or rush/target volume > the team target.
- Keep the stack (neutral to slightly positive, and it mitigates exactly this failure). It does not need changing.
- Do not change the lineup method on this evidence. 6 slates, 2 correlated weeks, per-slate noise sd ~0.2 percentile.
