# D — Spread / tail calibration of shipped projections (sigma, statline_p10/p90)

Research only. Nothing in scripts/, data/, output/ was changed.
Reproduce:
`python analysis/proj_d/d_calib.py <shipped_dir> > analysis/proj_d/d_out.txt` (all tables) and
`python analysis/proj_d/d_check.py <shipped_dir>` (paired bootstrap and dart-flag impact, saved as d_check_out.txt).
`<shipped_dir>` holds the six leak-free shipped builds (wk1/wk2 × main/early/afternoon).

Frame: non-DST players, alive, sigma>0, actual score present. Player-weeks deduplicated main>early>afternoon.
- Meaningful cut, final>8: **n=238** (wk1 112, wk2 126, 50 team-week clusters).
- Broad cut, final>3: n=431.

CIs are 95% cluster-bootstrap by team-week. DST is excluded because its statline_p10/p90 are 0 by construction.

## 0. Headline: the prior finding does not replicate on the shipped builds
The earlier analysis ran on pre-fix builds. It found 17.8% of actuals above p90, 68% inside the band, and sigma 7.4 against a realised residual SD of 9.1. On the guarded, shipped builds:

| cut>8 | below p10 | inside | above p90 |
|---|---|---|---|
| ALL (n=238) | 0.151 [0.10,0.20] | 0.761 [0.69,0.82] | **0.088 [0.04,0.14]** |
| wk1 / wk2 | 0.134 / 0.167 | 0.759 / 0.762 | 0.107 / 0.071 |
| QB 49 / RB 67 / WR 92 / TE 30 | .06 / .12 / .17 / .30 | .84 / .81 / .72 / .67 | .10 / .08 / .11 / .03 |
| salary 4-5k (54) | 0.259 [0.13,0.38] | 0.630 | 0.111 |
| final 8-12 (120) | 0.225 [0.16,0.29] | 0.692 | 0.083 |

Findings:
- **The upper tail is now calibrated** (8.8%, CI includes 10%).
- The remaining miss is the **lower tail**: p10 is too high for cheaper, lower-mean players.
- At cut>3 the miss is larger: 25% of actuals fall below p10, and 37% for final<8.
- Recentring on the per-position mean bias only brings below-p10 from 0.151 to 0.126 (cut>8) and from 0.251 to 0.167 (cut>3). So this is mostly a floor-shape problem, not a level problem.

Stack check: p10/p90 are already shifted by stack_delta (build_projections_statline.py:311-312), and there are 0 cases of p10>mean or mean>p90. The mean/quantile offset does not break coverage. Sigma is not shifted, which is correct because a shift does not change spread.

## 1–2. Sigma size: z=(actual−mean)/sigma
| group | n | bias | z sd | k_rmse = RMSE/rms(sigma) | residual skew |
|---|---|---|---|---|---|
| ALL cut>8 | 238 | −0.32 | 1.06 | **1.07 [0.94,1.20]** | 0.92 [0.68,1.14] |
| QB / RB / WR / TE | | | 1.04/1.01/1.09/1.07 | 1.04/1.03/1.11/1.09 | |
| wk1 / wk2 | | +1.29/−1.74 | 1.16/0.93 | **1.17 / 0.96** | |
| final 8-12 / 12-16 / 16-20 / 20+ | 120/71/32/15 | | | 0.98/1.04/1.23/1.28 | |
| ALL cut>3 | 431 | −0.74 | 0.96 | 1.00 | 1.21 |

- **Sigma is the right size overall.** k is about 1.0–1.07 and the CI includes 1.
- The two weeks point in opposite directions (1.17 against 0.96), so a per-position k fit on one week does not carry to the other.
- There is a weak shape signal: sigma is too small for high projections (k about 1.25 at final>16, n=47) and too large for cheap players (k 0.84 at final<8).
- Sigma barely ranks the size of the miss: Spearman(sigma, |residual|) is 0.13. Most of sigma's variation is mean-driven.

## 3. The Monte Carlo core (statline_model.py)
- **Yards and TDs are not independent.** `_draw_component` (lines ~482-491) scales both yards and TD probability by one shared gamma latent (`latent_sd`, fit to the measured yards/TD correlation). Teammates' volumes share a per-(team, component) shock (decision #18). The "independence" suspicion does not apply to the current code.
- **TD dispersion.** TDs are drawn Binomial(volume, rate×latent). Real 2026 multi-TD games run above the Poisson rate:

  | position | P(2+ TD) actual | P(2+ TD) Poisson | n |
  |---|---|---|---|
  | WR | 9.0% | 3.6% | 89 |
  | RB | 12.7% | 7.7% | 63 |

  Actual TD counts are also higher than projected (0.35 vs 0.29 per WR). This is about 8 events, so it is suggestive only. The model's own P(2+ TD) after the latent is not saved, so the comparison is against Poisson, not the model.
- **sigma and p10/p90 come from different sources.**
  - `sigma` = MC SD passed through `sigma_recalibration` (a power law fit on 2014-17, `sigma_recalibration_dk.json`), which pulls it toward historical residual SD. That fit includes projection error, which is why k≈1 today.
  - p10/p90 are raw MC percentiles (statline_model.py:2372-2373) and are not recalibrated (sigma_recalibration.py:119).
  - Implied sigma from (p90−p10)/2.56 is 8.3, against a shipped sigma of 7.7. The two are close.
- **Historical shape evidence.** Rotoguru DK 2014-21, actual score divided by leave-one-out season mean, compared with the model's p10/m and p90/m in the same mean bins:
  - Real q10/mean is 0.18–0.39 (it rises with the mean). The model's p10/mean is 0.27–0.35. **The MC floor is too high**, which matches the 2026 lower-tail miss.
  - Real q90/mean falls from about 2.1 at a mean of 10 to about 1.5 at a mean of 22. The model's p90/mean stays flat at about 2.0 at every mean level.
  - So historically the MC upper tail is too wide for high-mean players. The 2026 data (13% above p90 for final 20+, n=15) cannot confirm or reject this.
  - Caveat: a season mean is not a projection, so this is shape evidence only.

## 4. Candidate fixes, leave-one-week-out (fit on one week, score the other)
| cut>8 (n=238) | below | inside | above | pinball-10 | pinball-90 |
|---|---|---|---|---|---|
| shipped | .150 | .760 | .089 | 1.286 | 1.706 |
| (a) k half-width, global | .099 | .758 | .143 | 1.274 | 1.890 |
| (a) k half-width, per position | .152 | .723 | .125 | 1.239 | 1.951 |
| (a-lo) lower half-width only | .099 | .812 | .089 | 1.274 | 1.706 |
| normal: mean ± 1.28·k·sigma | .063 | .819 | .117 | **1.155** | 1.806 |
| (b) z-quantile map | .107 | .761 | .131 | 1.167 | 1.949 |
| (h) historical q/mean ratios (no 2026 fit) | .128 | .760 | .111 | 1.152 | 1.739 |

Pinball-50 is essentially unchanged across all rows (3.27).

- **Every change to the upper tail makes pinball-90 worse.** Leave p90 alone.
- For the lower tail, the paired cluster-bootstrap pinball-10 change against shipped (negative = better, both weeks agree in sign):

  | candidate | cut>8 | cut>3 |
  |---|---|---|
  | a-lo | −0.013 [−0.10,+0.07], not significant | −0.108 [−0.16,−0.06] |
  | p10 = mean − 1.28·k·sigma | −0.132 [−0.23,−0.05] | −0.216 [−0.26,−0.17] |

- The fitted lower multiplier k_lo is stable across weeks: 1.21 and 1.30 at cut>8 (1.25 on the full sample), and 1.50 and 1.37 at cut>3. It is the only stable parameter found.
- Option (c), an MC-core change such as a td-latent or floor/dud mixture, was not prototyped. It needs a historical coverage re-fit like Session 15.2c and cannot be validated by Sunday.

## 5. Downstream use
- **sigma** is used in three places in optimizer.py:
  - the objective `sum(mu) − lam·sum(sigma²)` (lines ~1617-1620 and ~2861);
  - sigma-mode randomization (lines ~1502 and ~2801);
  - the lineup attribute `sigma_total`.
- The lambda values in optimizer_presets.json (0.063 and −0.005) were swept against today's sigma scale. Multiplying sigma by k is the same as multiplying lambda by k². So a sigma rescale would silently change the validated lambda, and the data here does not support one (k≈1).
- **statline_p10** is read in one place only: the MME dart filter (optimizer.py:2031-2057). A player is a dart if p10 < `dart_floor_threshold` (1.0, mme_gpp preset), and darts are capped at 10% exposure. The frontend shows it as a hint only.
  - **Lowering p10 would change MME lineups materially.** In the wk2 main pool, players with final>8 flagged as darts go from 4/129 to 38/129 at k_lo=1.25 and 85/129 at 1.44. In wk1 main they go from 6 to 44 and 84.
  - The threshold of 1.0 is a heuristic tuned to today's p10 scale.
- **statline_p90** is not consumed by the optimizer, pivot_finder.py, or the ownership scripts. It is only displayed.

## 6. Recommendation: do not ship any spread change for Week 3
Reasons:
1. The problem this was meant to fix (upper tail too thin, sigma too small) is not present on the shipped builds. p90 coverage is 8.8% and k_rmse is 1.07 with a CI that includes 1.
2. The one robust finding is that **p10 is too high**. It is backed by both weeks, the historical shape evidence, and pinball-10. But p10's only consumer is the dart filter. Correcting p10 without re-tuning `dart_floor_threshold` would multiply dart flags by roughly 10×, which is an unvalidated construction change two days before lock.
3. Sigma: the per-week k values disagree (1.17 against 0.96), and any rescale moves the validated lambda. Leave it as is.

After Week 3 (measurable pass/fail):
- Compute the lower quantile as `p10 = max(0, final − 1.28·k·sigma)` with k≈1.07, or scale `(final − statline_p10)` by k_lo=1.25, in build_projections_statline.py right after line 752 (the `df["sigma"] = ...` line). This must be done together with re-setting `dart_floor_threshold` so the dart count per pool stays about the same (≈1.0 → ≈0 on the new scale; re-derive it).
- Pass criteria on wk1-3 leave-one-week-out:
  - below-p10 share within [0.07, 0.13] at cut>8, with every held-out week inside [0.05, 0.16];
  - pinball-10 improves in every held-out week;
  - p90 and sigma unchanged.

MC-core follow-up (a floor/dud mixture and a mean-dependent upper tail) should be validated against the historical 2014-21 coverage harness, not 2 weeks.

Confidence: 238 player-weeks in 50 clusters over 2 weeks. The CIs on per-position coverage are ±8–17 points, so the per-position differences (for example TE below p10 at 0.30) cannot be separated from noise. The week-to-week swing in k (1.17 vs 0.96) is as large as any effect measured here.
