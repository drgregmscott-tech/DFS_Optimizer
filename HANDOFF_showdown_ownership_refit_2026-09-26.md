# Showdown ownership refit on OUR replayed projections (2026-09-26)

Scope: refit/test `scripts/ownership_model_showdown.py` (DK Showdown ownership) with features built from **our own statline engine replayed on 49 FC-history Showdown games (2023-25)**. It replaces the FC-proxy analysis in `HANDOFF_showdown_history_findings_2026-09-26.md` §5b.
FC data is subscription data. Everything FC-derived is under `data/fc_history/derived/showdown/` (gitignored). This doc has aggregates only. Nothing was committed, and no production file (`scripts/`, `config/`, `data/*.json`, `SHOWDOWN_RULES.md`) was touched.

## TL;DR
- **The replay is only partly faithful. It is NOT faithful for K/DST.** The noisy ILP rosters K/DST much less on replayed pools (FLEX l_exp K -1.1, DST -1.4) than on our 4 real 2026 slates (K -0.18, DST -0.49). It is the same trap as the FC proxy, just smaller (FC gave -2.0/-3.0). Every model fitted on history K/DST rows over-predicts real-slate K FLEX ownership by +8 to +12 pts. **Do not take K/DST coefficients from history.**
- **Tested honestly, production is modestly miscalibrated on skill players, not on K/DST.** On history with our features the current artifact shows these errors:
  - CPT corr 0.72, FLEX corr 0.80.
  - QB over-predicted (CPT +2.9, FLEX +2.6). The size depends on the replay's depth-chart choice: +1.2/+0.3 with a stubbed chart. Weak.
  - FLEX WR +2.0 and $1-3k +2.1.
  - Far too few low-tail CPT players (1-5%): 133 predicted vs 315 real.
  - The K -8.5 / DST -4.6 biases are a replay artifact (see above).
- **Best candidate: add one feature, log FLEX salary (`lsal`). Fit skill rows on history + real, and fit K/DST flags on real slates only.**
  - Real-4 leave-one-slate-out (LOSO), candidate vs production recipe: FLEX MAE 3.68 vs 4.25, corr 0.914 vs 0.890, chalk MAE 8.0 vs 10.0. CPT MAE 1.29 vs 1.45, corr 0.865 vs 0.841.
  - It also wins on history LOSO: FLEX corr 0.845 vs 0.799 for the current artifact, CPT 0.770 vs 0.722.
  - Salary is identical live and in history, so this feature cannot be a proxy artifact.
- **Lineup level: no construction conclusion changes.** Leverage still loses with every ownership source (realized, current or candidate). Lambda 0 for Showdown stays.
- **Recommendation: do not ship yet. Ship after X**, where X = the candidate beats the current artifact on the next 2+ real DK Showdowns, fitted before those slates are seen. Confidence: medium that `lsal` helps, low on the exact coefficients.

## 1. What was built (all in `analysis/showdown_history/`, no FC data embedded)
| Script | Does |
|---|---|
| `resolve_weeks.py` | slate -> (season, week, game_id) → `derived/showdown/slate_weeks_resolved.csv` |
| `build_pools.py` | Showdown salary pools in live ingest schema (CPT 1.5x + FLEX rows, `slate_format=showdown`, gsis ids, pre-lock AvgPointsPerGame proxy) → `salaries_sd/`, `sd_id_map.parquet` |
| `run_sd_proj.py` | Runs the production statline engine's **showdown path** (FLEX build, `_build_kicker_projections`, `apply_captain_multiplier`) with the run_ourproj/run_backtest leak patches → `ourproj_<tag>/proj_<slate>.csv` |
| `sd_features.py` | `oms.build_features` (noisy ILP, 6 procs) on replayed pools, joined to realized ownership → `own_feats_ourproj.parquet`. `--real` caches the 4 real slates |
| `refit_ourproj.py` | 4(a)-(d) diagnostics, LOSO refits, candidate artifact (`--kd-real-only --cand +lsal --write`) |
| `lineup_check.py` | Step 5: chalk identification + simulated-field percentile of max-our-proj and leverage lineups |

Reproduce, in order:
```
resolve_weeks
build_pools
run_sd_proj --workers 6
sd_features --real
sd_features
refit_ourproj --kd-real-only --cand +lsal --write
lineup_check 6
```
The replay itself takes about 2 min. Features take about 15 min. The lineup check takes about 20 min.

## 2. Mapping and coverage
- **Slate weeks: 49/49 resolved and unique.** All of them are Thu/Sat/Christmas standalone games. Of the 28 rematch slates, each was resolved by the FC home team ('vs'/'@' in Opp), which matched nflverse on 49/49.
  - FC Vegas total vs nflverse `total_line` was within ±1 on 48, and +2.5 on 2024 KC/PIT.
  - FC actual score vs nflverse PPR: median |diff| 0 on 48 slates, 0.5 on one. That one is 2023 MIN/PHI, which had a single candidate game.
  - The runner-up rematch correlated far worse (≤0.84 vs ≥0.81 chosen; the gap exceeded 0.1 on all 28).
- **Player ids: 1,554/1,559 mapped.**
  - Sources: fc_master 1,355, nflverse weekly_stats 98, rosters 3, DST 98.
  - 5 players are unmapped (4 at min salary, 4 with FC proj 0). They carry 0.02% of CPT and 0.35% of FLEX ownership mass in total. **Negligible.**
  - `weekly_rosters_2022/2023` are missing locally, but weekly_stats 2023 covered the gap.
- **Kickers are projected in history.** The kicker model is not player-conditioned, so the engine produces them. 2 K per slate on 48 slates. 2025 MIA/BUF has only one because the MIA kicker is absent from the FC export. Replayed K mean projection is 8.1 (SD 0.19), identical to live (8.1).
- **DST** used the distributional model on all 49 slates. `team_stats_2023` now exists locally, so the legacy-DST caveat from run_ourproj no longer applies.

## 3. Replay-faithfulness (deliberate differences vs live, and checks)
Deliberate differences:
1. **Depth chart.** It is QB-only: QB1 is the game's actual starting QB (nflverse `home/away_qb_id`), a mild leak that live usually knows pre-lock. Without it the QB guard cannot run. A `--depth stub` variant was also run.
2. **Inactives are zeroed.** 2024/25 use weekly_rosters status != ACT. 2023 uses "absent from weekly_stats that week and 0 actual points", which zeroes all 2023 backup QBs. Live gives those QBs about 1-2 pts, and their ownership is about 0 either way. Mean OUT per slate is 2.7.
3. **Other inputs:** no props, no weather files, AvgPointsPerGame = season-to-date mean.
4. **Pool size.** FC exports are trimmed to about 32 players per game vs 45-53 live.

Schema check vs `final_projections_dk_dk_showdown_wk3_Atl_GB_24Sep2026.csv`: same columns (live additionally has injury/heuristic columns). CPT projection, salary and sigma are exactly 1.5x FLEX in both.

**4(a) distribution check. Mean FLEX l_exp on live rows (realized own in brackets):**

| Pos | hist 2023 | hist 2024 | hist 2025 | real4 2026 |
|---|---|---|---|---|
| K | -0.66 (19%) | -1.58 (21%) | -1.18 (21%) | **-0.18 (19%)** |
| DST | -0.78 (18%) | -1.78 (13%) | -1.60 (12%) | **-0.49 (12%)** |
| QB | -0.27 (40%) | -2.56 (23%) | -2.64 (22%) | -3.19 (18%) |
| RB | -2.41 | -3.51 | -2.96 | -4.22 |
| WR | -2.42 | -2.63 | -2.62 | -4.31 |
| TE | -3.24 | -3.59 | -3.22 | -4.77 |

- The real slates have deeper live pools (about 45 live players vs about 26) and **lower top projections**. Mean top-6 FLEX projection is 13.8 on the real slates vs 17.6 in the replay (same in weeks 1-3: 18.8). The replay's top-6 matches FC's own top-6 (17.7). Team skill totals are similar (82 vs 90).
- So on real slates the flat about-8-pt K and DST projections are relatively more attractive, and the ILP rosters them more. That shifts the whole l_exp scale: all real-slate values are about 1-1.7 lower for skill positions, and K/DST are higher.
- **Verdict:**
  - Skill-position l_exp **ranks** transfer. The skill-position biases of history-fitted models on the real slates are small (-1.7 to +1.3 excluding QB).
  - K/DST **levels do not transfer.** History-fitted models over-predict real K FLEX by +8.5 to +11.8 and real DST by +4 to +16.
  - QB is sensitive to the depth-chart choice. Stub vs QB-chart moves the QB CPT bias from +1.2 to +2.9.
- Why the real tops are lower (live props/injury/depth inputs vs replay, or just these 4 games) is **not resolved** (open question 1).

## 4. Results (bias = predicted - actual, pct pts; "tail" = count of FLEX 2-10% or CPT 1-5% players)

**4(b) Current production artifact, as-is, on replayed features**

| Set | Role | corr | MAE | chalk MAE | chalk bias | top-1 | QB | RB | WR | TE | K | DST | $1-3k | tail pred/act |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hist49 | CPT | 0.722 | 2.42 | 7.8 | -2.3 | 0.49 | +2.9 | -1.1 | +0.2 | -0.1 | -0.8 | -0.5 | +0.5 | 133/315 |
| hist49 | FLEX | 0.799 | 7.83 | 12.5 | -1.6 | 0.31 | +2.6 | +1.2 | +2.0 | +0.6 | -8.5* | -4.6* | +2.1 | 245/278 |
| hist2025 | CPT | 0.770 | 2.16 | 6.9 | -1.4 | 0.67 | +2.3 | -0.7 | +0.2 | 0.0 | -0.9 | -0.5 | +0.5 | 49/115 |
| hist2025 | FLEX | 0.798 | 7.44 | 12.6 | -1.7 | 0.39 | +2.0 | +1.8 | +1.8 | +0.6 | -9.8* | -3.8* | +2.4 | 107/112 |
| real4 (in-sample) | CPT | 0.849 | 1.41 | 6.6 | -1.7 | 0.50 | +1.4 | -0.2 | 0.0 | -0.6 | +0.3 | +0.5 | +0.5 | 16/27 |
| real4 (in-sample) | FLEX | 0.895 | 4.14 | 9.9 | -1.8 | 0.50 | +4.3 | +0.1 | -0.7 | -1.0 | -0.6 | +1.2 | +0.9 | 20/31 |

\* Replay artifact (§3), not a production error. With the stubbed depth chart the QB biases shrink (CPT +1.2, FLEX +0.3), while K/DST are unchanged (-7.9/-4.6).

Honest reading of production:
- Chalk is under-predicted (chalk bias about -2).
- QB is over-predicted. This is consistent with real4 FLEX QB +4.3, so it is Weak-to-Supported.
- The CPT low tail is badly too thin. Production predicts too many near-0 CPTs, which is the same fat-tail miss as classic.
- FLEX $1-3k is over-predicted by about 2 pts.

**4(c) Same 4 features, refit** (history with 2025 x2 + real x3, LOSO over all 53 slates):

| Fit | Set | CPT corr / MAE | FLEX corr / MAE | FLEX chalk MAE | FLEX K / DST bias (real4) |
|---|---|---|---|---|---|
| base4, all rows | hist49 LOSO | 0.724 / 2.36 | 0.809 / 7.17 | 10.5 | - |
| base4, all rows | real4 LOSO | 0.839 / 1.51 | 0.882 / 4.26 | 8.7 | **+10.3 / +6.3** |
| base4, all rows | real4 held-out (history only) | 0.835 / 1.53 | 0.878 / 4.40 | 9.1 | **+11.5 / +6.7** |
| base4, K/DST from real only | real4 LOSO | 0.847 / 1.43 | 0.894 / 4.15 | 9.3 | +0.7 / +1.3 |
| production recipe (real-only 4-feat) | real4 LOSO | 0.841 / 1.45 | 0.890 / 4.25 | 10.0 | +0.7 / +1.3 |

A plain refit of the 4 features buys nothing over production once K/DST are protected. Including history K/DST rows breaks K/DST on the real slates.

**4(d) Extra features.** All rows below have K/DST taken from real slates only. The history LOSO K/DST biases are therefore off by construction (about -7/-3.5) and are excluded from judgement.

| Features | hist49 LOSO CPT corr/MAE | hist49 LOSO FLEX corr/MAE | hist2025 FLEX corr/MAE | real4 LOSO CPT corr/MAE | real4 LOSO FLEX corr/MAE/chalk | FLEX QB bias hist/real4 |
|---|---|---|---|---|---|---|
| base4 | 0.725/2.39 | 0.802/7.55 | 0.800/7.23 | 0.847/1.43 | 0.894/4.15/9.3 | +1.8/+3.3 |
| **+lsal** | **0.770/2.14** | **0.845/6.78** | **0.837/6.61** | **0.865/1.29** | **0.914/3.68/8.0** | +4.8/+5.2 |
| +pos (QB,RB,TE) + lsal | 0.755/2.18 | 0.779/8.03 | 0.778/7.66 | 0.844/1.23 | 0.874/4.16/12.1 | -11.4/-6.5 |
| +pshare (projection share of slate top-6) | 0.770/2.12 | 0.847/7.24 | 0.839/7.19 | 0.876/1.12 | 0.908/3.90/10.1 | +8.5/+6.1 |
| +pos+lsal+pshare | 0.794/1.94 | 0.827/7.35 | 0.824/7.22 | 0.901/0.99 | 0.903/3.81/10.9 | -6.2/-3.8 |
| +pos+lsal+lrank | 0.775/2.02 | 0.829/7.29 | 0.826/7.07 | 0.841/1.18 | 0.896/3.87/11.3 | -5.5/-3.1 |
| base4/+pos+lsal + FLEX raw floor 1-2 pts | same CPT | FLEX MAE worse (+0.1 to +0.4) | worse | - | worse | - |

- **Position dummies** over-correct QB, flipping it to -6 to -11. The QB dummy absorbs the depth-chart-sensitive QB l_exp level. Reject.
- **Projection share** helps CPT (real4 CPT MAE 0.99-1.12) but worsens FLEX chalk MAE and QB bias. It is also projection-level-dependent, which is the exact thing §3 shows does not transfer. Park it until more real slates exist.
- **A low-tail additive floor** fixes counts but costs MAE and chalk accuracy everywhere. Reject in this form.
- **`lsal`** is the only addition that improves every set on corr, MAE and chalk MAE and is projection-independent. It does **not** fix the QB over-prediction (it makes it slightly worse, +5).

## 5. Lineup-level check (49 history slates; field = F1 max-entropy matching REALIZED ownership; candidate = LOSO predictions)

(i) Chalk identification

| Role | top-1 hit cur → cand | top-3 overlap cur → cand | within-slate Spearman cur → cand |
|---|---|---|---|
| CPT | 0.49 → 0.51 | 1.63 → 1.67 | 0.685 → 0.768 |
| FLEX | 0.31 → 0.45 | 1.63 → 2.02 | 0.777 → 0.823 |

Predicted top CPT is a QB 27-28/49 times under both models vs 19/49 real. Both models miss the field's RB chalk captains: RB was the real top CPT 19 times, but predicted only 9-10.

(ii) Field percentile, diff vs the max-our-projection lineup (pct points, 90% slate-bootstrap CI). Max-our-proj averages the 59th percentile (#1 lineup) and the 56th (top-20 mean), with 13% top-10%.

| Strategy | #1 lineup Δ | top-20 Δ | 2025 #1 Δ |
|---|---|---|---|
| lev 0.05 using realized own | -3.6 [-7.9, +0.5] | -2.2 [-3.7, -0.7] | -4.9 |
| lev 0.05 using current pred | -4.0 [-9.1, +0.7] | -0.6 [-2.6, +1.5] | -2.4 |
| lev 0.05 using candidate pred | -1.8 [-6.3, +2.4] | -0.9 [-2.3, +0.5] | +1.6 |
| lev 0.1 realized / current / candidate | -6.8 / -8.7 / -6.5 | -4.6 / -5.6 / -3.0 | |
| lev 0.2 realized / current / candidate | -10.9 / -13.3 / -15.2 | -12.3 / -14.3 / -14.3 | |

**No construction conclusion changes.** Leverage is ≤0 with every ownership source, including perfect (realized) ownership, and the CIs mostly exclude gains. The candidate makes small leverage somewhat less harmful than current, but the CIs overlap heavily. Keep lambda 0 for Showdown. Better ownership calibration matters for **display/pivot reading** (chalk ranks), not for the optimizer objective.

## 6. Candidate artifact
`data/fc_history/derived/showdown/ownership_model_showdown_dk.candidate.json`:
- Same schema as production, plus `"features"`, `"weights"` and `"kd_real_only": true`.
- Fit: features `l_exp, isK, isD, isMin, lsal`; lambda 5; history 2025 x2; real slates x3; history K/DST rows excluded.

Standardized coefficients (intercept, then each feature), candidate vs current:

| Role | Model | intercept | l_exp | isK | isD | isMin | lsal |
|---|---|---|---|---|---|---|---|
| CPT | candidate | -4.18 | 0.84 | -0.12 | +0.02 | +0.46 | +1.26 |
| CPT | current | -4.75 | 0.98 | -0.34 | +0.05 | -0.57 | - |
| FLEX | candidate | -2.47 | 1.20 | -0.06 | -0.07 | -0.09 | +0.98 |
| FLEX | current | -3.46 | 1.61 | -0.23 | -0.26 | -0.85 | - |

Changes in plain words:
- **Salary** takes over most of the isMin role. isMin flips to slightly positive at CPT, which is collinear with lsal and not interpretable alone.
- **l_exp** is down-weighted.
- **K/DST** flags now have a much smaller SD (0.08 vs about 0.21) because history K/DST rows are excluded from the standardization. In raw (unstandardized) units the K/DST penalties are similar to current.

Proposed code change (NOT applied). It is backward-compatible: the current artifact has no `features` key, so the default list keeps it byte-identical.
```diff
--- scripts/ownership_model_showdown.py
@@ def build_features(df):
     f["isMin"] = (sal_flex <= MIN_PRICE_FLEX).astype(float)
+    f["lsal"] = np.log(np.clip(sal_flex, 200, None) / 1000.0)   # FLEX-equivalent salary, $k (log)
     f["live"] = (pool["final_projection"] > 0).values
     return f
@@ def predict(feats, artifact):
     out = pd.Series(0.0, index=feats.index)
+    feat_list = artifact.get("features", FEATURES)
     for role in ("CPT", "FLEX"):
         m = artifact["roles"][role]
         idx = feats.index[feats["role"] == role]
-        X = (feats.loc[idx, FEATURES] - pd.Series(m["mu"])) / pd.Series(m["sd"])
-        z = m["intercept"] + X.to_numpy() @ np.array([m["coefs"][k] for k in FEATURES])
+        X = (feats.loc[idx, feat_list] - pd.Series(m["mu"])[feat_list]) / pd.Series(m["sd"])[feat_list]
+        z = m["intercept"] + X.to_numpy() @ np.array([m["coefs"][k] for k in feat_list])
```
`fit()` would also need a way to include the history frame. For now the candidate is produced by `refit_ourproj.py`.

## 7. Recommendation and confidence
**Do not ship now. Ship after X.**

X is: freeze this candidate today, then score it vs the current artifact on the next 2+ real DK Showdown slates (Week 3 onwards, logged in `ownership_actual_log.csv`) that neither has seen. Ship if it matches or beats current on FLEX MAE and chalk MAE and shows no K/DST bias above about 5 pts.

Why not ship now:
- (a) Its K/DST calibration rests on 4 real slates. That is the same as production, so no worse, but it is untested out of sample on a new pool shape.
- (b) The real-4 gain (FLEX MAE -0.57) comes from 4 games with heavy tails.
- (c) The lineup-level impact is nil (§5). There is no urgency before lock.

Evidence grades:
- `lsal` helps: **Supported**. It wins on history LOSO, 2025-only and real4 LOSO. The feature is projection-independent.
- Production over-predicts QB: **Weak**. The size depends on the depth chart, though real4 shows it too.
- Production under-covers the CPT low tail: **Supported**. It holds in history under both replays, and on real4 (16 predicted vs 27 real).
- The K/DST flags are correct as-is: **Weak**. This is the real4-only evidence; history cannot test it.

What would make this wrong:
- The real-4 pools are atypical, for example because of early-season 2026 projection levels. l_exp scales would then shift again as the season matures, and the history-weighted l_exp coefficient (1.20 vs 1.61) would mis-scale.
- DK changes Showdown pricing.

## 8. Open questions
1. Why are live 2026 top projections about 25% lower than the replay (13.8 vs 17.6 top-6)? Candidates: props/injury/depth inputs, the deeper live pool, or 4-game noise. Rerun one live 2026 showdown through `run_sd_proj.py` machinery (a trimmed pool, no props) to split the causes. This is the key to ever using history K/DST rows.
2. QB over-prediction persists in every non-dummy model. It might need a QB-specific l_exp slope (an interaction) fitted once more real slates exist.
3. RB chalk captains are under-identified (predicted top CPT is RB 10/49 vs 19/49 real).
4. Low-tail shape: a mixing/temperature change inside the logit (not an additive floor) is untested.
