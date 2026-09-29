# Classic pre-lock ownership re-test of the lineup-study chalk finding (2026-09-29)

WK3 postmortem parking-lot item 2 ("Pre-lock ownership re-test"). Classic sibling of `HANDOFF_showdown_construction_detail_2026-09-28.md` Task 1.
Script: `analysis/classic_history/lineup_study_modeled_own.py` (no FC data inside). Aggregate outputs: `analysis/classic_history/out/cl_modown_*.csv`, `cl_modown_out.txt`.
Nothing shipped. Nothing committed.

```
set CL_DER=<derived/classic cache>   (the per-entry cache lives in .claude/worktrees/agent-a7b681e8ca8724ccb/data/fc_history/derived/classic)
python analysis/classic_history/lineup_study_modeled_own.py                  # ~30 min on 12 procs, one contest per worker
OURPROJ_CTRL=1 python analysis/classic_history/lineup_study_modeled_own.py   # ~8 min: extra "our projection" control
```

## TL;DR
- **Unlike Showdown, the classic chalk edge does not vanish with our modeled ownership. It shrinks by about half, and most of what remains is our own projection re-encoded.**
- **Among quality lineups (same contests), the most-owned fifth versus the least-owned fifth, capped return:**

  | Format | Realized | Our model (v2) |
  |---|---|---|
  | SE | 1.21 vs 0.80 | 1.12 [1.03,1.21] vs 0.90 |
  | 20MAX | 1.30 vs 0.72 | 1.12 vs 0.89 |

  - SE Q5-Q1 gap: +0.40 realized, +0.21 [+0.06,+0.37] with our model (3/4 seasons).
  - Projection-controlled OLS in SE quality (FC projection held fixed): +0.18 capped return per SD realized, +0.10 [+0.03,+0.18] modeled.
- **The real question: does modeled ownership add anything once our own projection is also controlled?** The optimizer already maximizes that projection. The answer is only a little:
  - Capped return +0.08 per SD in SE and 20MAX quality, CI [-0.00,+0.17] and [+0.01,+0.16], 3/4 seasons.
  - Cash rate +1.8 to +2.1 pts; 3MAX is null.
  - That is about 1/3 to 1/2 of what our projection alone adds over FC (+0.08 to +0.10).
  - **Grade: Weak.**
- **The chalk-QB signal does not transfer.**
  - Our model's #1 QB matches the field's #1 QB in only **~10%** of contests (v2 9.9%, v1 9.4%).
  - Lineups built on our modeled #1 QB do *worse* than the field: SE -1.4 cash pts, 20MAX -2.9 [-5.2,-0.3], 0-1/4 seasons.
  - **Not supported.**
- **Player level (§6).** Holding FC projection and salary fixed, modeled ownership still predicts points:
  - QB +1.7, RB +1.9 pts per SD. That is roughly realized-sized, but it is our projection talking.
  - WR +0.9 and TE +0.7, about half of realized.
  - Adding modeled ownership barely dents realized ownership's coefficient (RB 2.7→2.5, WR 1.76→1.66). What the field knows is mostly not in our model.
- **Fidelity.**
  - Player-level corr with realized: 0.50 (v2) / 0.53 (v1).
  - Lineup-level corr: 0.42 across all lineups, 0.33 within the quality subset. Showdown was 0.56.
  - The live lock-time log (2026 wk1-2 main) is no better than the replay: live 0.63 / 0.56 against replay v2 0.61 / 0.65. The replay does not understate live quality.
- **Ceiling (how good a pre-lock source must be).**
  - Blending realized into modeled: at lineup corr ≈0.6 (quality subset) the SE quality slope reaches +0.15 and the gap +0.29. At ≈0.8 it matches realized.
  - FC's own `proj_own` exists for 2022-23 (195 contests). It has lineup corr 0.79-0.86 and shows the full edge or more (SE quality Q5 1.34). But it is unverified as truly pre-lock (see caveats).
- **Verdict: no chalk/ownership construction lever is shippable for classic on our modeled ownership. Keep lambda 0 for cash/SE, and do not add a chalk tilt or a "chalk QB" rule.**
  - The edge is real but lives in information our model does not have. The measurable part of our model's edge is our projection, which the optimizer already uses.
  - Track 2 (keep testing, low bar): a small modeled-ownership tiebreak among near-equal-projection lineups is Weak-positive. It is not worth a lever until ownership fidelity improves.
  - The better investment is ownership/projection inputs, especially a pre-lock source that reaches lineup corr ≥0.6-0.7.

## 1. Data, sources, coverage
- **Contests.** Same 410 analysed contests as `HANDOFF_classic_lineupstudy_findings_2026-09-29.md`.
  - 404 map to an FC-history main-slate replay pool. The 6 without a pool are 2024 wk1-3 or `b` slates.
  - **All 404 have ≥90% of realized ownership mass mapped:** median 0.999, p10 0.983, min 0.904. 99.5% of players owned ≥1% map; the median largest unmapped player is 0.38% owned.
  - Used, by format and season (2022/23/24/25/26): SE 35/34/25/34/10, 3MAX 17/16/12/16/4, 20MAX 36/36/24/35/6, DU 17/15/12/16/4.
  - Every lineup-study contest turned out to be on the main slate.
  - Unmapped players got a floor of 0.5%. Floors of 0% and 2% change nothing, to the third decimal (`v2_f0`, `v2_f2`).
- **Entry alignment.** The per-entry cache (worktree copy, all 431 files) was re-aligned to the raw JSON row by row. Points and lineup count were verified per contest, with 0 misaligned.
- **Modeled sources** (both use the production projection replay `run_ourproj.py` and the current ownership artifact, refit 2026-09-23, with pub_val = 0):
  - **v2 (primary, no leakage):** `ourproj/proj_<yr>_wk<n>.csv` `estimated_ownership_pct`. It has no inactive handling, so it is pessimistic: players ruled OUT pre-lock still get ownership.
  - **v1:** `fc_own_features_ourproj.parquet`, re-scored with the production artifact. Its pool zeroes every skill player without a weekly_stats row. That filter uses post-game info, so v1 is optimistic and leaky.
  - v1 and v2 agree closely (player corr ~0.9). Every conclusion holds on both, and v1 is only ~10-20% stronger.
  - Also tested: `heur`, the pure heuristic without the layered model.
- **FC `proj_own`.** It covers ≥95% of ownership mass on 195 contests (2022-23 only) and is absent 2024+. It is reported separately.

## 2. Pipeline check: realized ownership on the matched subset reproduces the doc
| | Doc (410) | This subset (404) |
|---|---|---|
| SE quality Q5 / Q1 capped return | 1.20 / 0.80 | 1.21 [1.12,1.29] / 0.80 |
| 20MAX quality Q5 / Q1 | 1.30 / 0.72 | 1.30 / 0.72 |
| 3MAX quality Q5 | 1.23 | 1.24 |
| SE quality OLS capped return per SD (FC-proj control) | +0.17 [+0.10,+0.24] | +0.176 [+0.106,+0.245] |
| 20MAX quality OLS | +0.27 | +0.271 |

The subset is effectively the full study.

## 3. Headline: realized vs our modeled ownership, same contests (quality subset = ≤$500 left and top-40% FC projection)

The first three data columns are capped-return ratios.

| Cut | Source | n | Q1 | Q5 | Q5-Q1 gap [90% CI] | Seasons + | Q5 cash lift |
|---|---|---|---|---|---|---|---|
| SE quality | realized | 122 | 0.80 | **1.21** | **+0.40 [+0.25,+0.55]** | 4/4 | +9.0 |
| SE quality | v2 | 122 | 0.90 | 1.12 [1.03,1.21] | +0.21 [+0.06,+0.37] | 3/4 | +3.4 [+1.6,+5.3] |
| SE quality | v1 | 122 | 0.90 | 1.15 | +0.25 [+0.09,+0.40] | 4/4 | +4.4 |
| 20MAX quality | realized | 131 | 0.72 | **1.30** | **+0.58 [+0.45,+0.71]** | 4/4 | +11.2 |
| 20MAX quality | v2 | 131 | 0.89 | 1.12 | +0.23 [+0.10,+0.37] | 3/4 | +4.0 |
| 3MAX quality | realized | 60 | 0.78 | 1.24 | +0.46 [+0.26,+0.66] | 4/4 | +10.0 |
| 3MAX quality | v2 | 60 | 0.88 | 1.14 | +0.26 [+0.06,+0.47] | 3/4 | +3.9 |
| SE quality | heuristic only | 122 | | | +0.17 [+0.04,+0.31] | 3/4 | |

Per-contest OLS among quality lineups, per SD of summed ownership, with FC projection as the control (`cl_modown_slopes.csv`):

| | SE realized | SE v2 | 20MAX realized | 20MAX v2 | 3MAX realized | 3MAX v2 |
|---|---|---|---|---|---|---|
| Capped return | **+0.18** [+0.11,+0.25] | +0.10 [+0.03,+0.18] 3/4 | **+0.27** | +0.12 [+0.05,+0.18] 3/4 | +0.24 | +0.10 [-0.01,+0.21] |
| Cash (pts) | +5.4 | +2.4 [+1.2,+3.6] | +6.9 | +2.9 | +6.5 | +2.7 |
| Points | +4.6 | +1.9 | +5.3 | +2.2 | +5.0 | +2.0 |

## 4. Is it ownership or projection? (`cl_modown_joint.csv`, `cl_modown_ourproj_ctrl.csv`)
- **Lineup-level correlations** (mean over contests; all / quality):

  | Pair | All lineups | Quality |
  |---|---|---|
  | Modeled v2 with realized | 0.42 | 0.33 |
  | Modeled v2 with FC projection | 0.32 | 0.14 |
  | **Modeled v2 with OUR projection** | **0.68** | **0.70** |
  | Our projection with FC projection | 0.40-0.45 | 0.17 |

  Modeled ownership is mostly our projection re-encoded.
- **Our projection alone, with an FC-projection control**, adds +0.06 to +0.10 capped return per SD (4/4 seasons in quality). So our projection has information beyond FC's.
- **Modeled ownership with BOTH projections controlled** (quality subset):

  | Format | Capped return per SD | Seasons + | Cash (pts) | Points |
  |---|---|---|---|---|
  | SE | +0.08 [-0.00,+0.17] | 3/4 | +1.8 [+0.5,+3.2] | +1.4 |
  | 20MAX | +0.08 [+0.01,+0.16] | 3/4 | +2.1 [+0.6,+3.5] | +1.5 |
  | 3MAX | +0.05 [-0.08,+0.16] | 2/4 | null | null |

  - Across all lineups, the capped-return CIs span 0 in every format.
  - **Weak.**
- **Realized ownership with both projections controlled** is still +0.17 to +0.26. Given realized ownership, the modeled coefficient drops to +0.02 to +0.09.
  The part of realized ownership that our model does not explain (`realresid`) carries +0.15 to +0.24, which is nearly all of it.

## 5. Ceiling: how good must a pre-lock source be? (player-level blend w·realized + (1-w)·v2)
| Source | Lineup corr with realized (quality) | SE quality OLS capped return | SE quality Q5-Q1 gap |
|---|---|---|---|
| v2 (ours) | 0.33 | +0.10 | +0.21 |
| blend 5% | 0.48 | +0.13 | +0.26 |
| blend 10% | 0.59 | +0.15 | +0.29 |
| blend 15% | 0.68 | +0.17 | +0.34 |
| blend 25% | 0.81 | +0.19 | +0.39 |
| realized | 1.00 | +0.18 | +0.40 |
| FC proj_own (2022-23, 62 SE contests) | 0.79 | +0.33 | +0.60 |

- The slope is steep up to corr ~0.7 and saturates by ~0.8.
- The bar to recover most of the edge is **lineup corr ≥0.6-0.7 within quality lineups**, about double ours. That roughly corresponds to player-level corr ≥0.75.
- The FC `proj_own` row exceeds realized. That is a red flag for leakage or a late (near-lock) snapshot, not proof of a better source (§8).

## 6. Chalk QB (`cl_modown_qb.csv`)
- The realized #1-owned QB replicates: +4.9 cash in SE (ret 1.21) and +5.0 in 20MAX, 3/4 seasons.
- **Our #1 modeled QB matches the realized #1 QB in only 9.9% of contests** (2022 18%, 2023 9%, 2024 1%, 2025 11%).
  - This echoes the known issue that the model over-concentrates the top-salary player.
- Lineups using our modeled #1 QB:
  - SE: -1.4 cash pts [-4.1,+1.4], ret 0.94.
  - 20MAX: -2.9 [-5.2,-0.3], ret 0.86, 0/4 seasons.
  - Quality subset: SE -1.0, 20MAX -3.3.
- **Not supported: a "chalk QB" rule on our ownership would pick the wrong QB about 90% of the time and lose money.**

## 7. Player-level §6 with modeled ownership (`cl_modown_player_coef.csv`)
Setup: fp ~ FC proj + salary + z(log own), largest contest per slate, 71 slates.
| Pos | Realized | v2 | Realized given v2 (joint) | v2 given realized |
|---|---|---|---|---|
| RB | +2.7 | +1.9 | +2.5 | +0.9 [+0.4,+1.5] |
| WR | +1.8 | +0.9 (3/4) | +1.7 | +0.3 [-0.1,+0.6] |
| TE | +1.7 | +0.7 | +1.6 | +0.1 [-0.2,+0.4] |
| QB | +1.5 | +1.7 | +1.2 | +1.2 [+0.6,+1.9] |
| DST | +1.1 | +0.9 | +1.0 | +0.4 |

- "Ownership predicts points beyond FC" survives in a weaker form with modeled ownership, but it is our projection (not controlled here) doing the work.
- The field's extra information (realized given modeled) is almost untouched.
- QB and RB are where our model carries something independent. WR and TE are where it misses.

## 8. Caveats and confidence
- **Replay vs live.**
  - pub_val = 0 and no FFC in history, while live uses both. The FFC variant only exists for 2026.
  - On the only live data (2026 wk1-2 main, n = 197 / 230 players), live lock-time corr was 0.63 / 0.56 against replay 0.61 / 0.65. So the replay is a fair proxy and does not understate live, as far as 2 slates can say.
- **Inactives.** v2 ignores pre-lock OUT news (pessimistic); v1 uses post-game "played" (leaky, optimistic). Truth is between them, and they differ only modestly.
- **The projection replay** stubs the depth chart and uses closing lines. 2022-23 DST uses the legacy model.
- **FC `proj_own`** looks too good: lineup corr 0.79-0.86 and a gap larger than realized. There is no evidence of when FC stamped it, so it may be a late or near-lock value.
  - Do not use it as proof that a public pre-lock source reproduces the edge. That needs a timestamped source.
- **Confidence basis.**
  - 122 SE / 131 20MAX / 60 3MAX contests, 2022-25 for season signs, 90% contest bootstrap.
  - Contest-level bootstrap only partly handles correlated multi-entry users.
  - The v2 effects hold 3/4 seasons with CIs clear of 0 before the our-projection control. After it, the CIs touch 0 in SE.
- DU is not graded (cash game). DU v2 Q5 is +5.8 cash [-0.6,+12.2].

## 9. Grades
| Cut | Grade |
|---|---|
| Chalk tilt on modeled ownership, FC-projection control only | Supported (small: ~half of realized) |
| Chalk tilt on modeled ownership beyond OUR projection (the real lever question) | **Weak** (SE/20MAX quality +0.08, CIs at 0; 3MAX null) |
| Chalk QB (#1 modeled QB) | **Not supported** (negative) |
| Leverage (fade modeled chalk) | Not supported (modeled Q1 is 0.88-0.90) |
| Player-level "ownership predicts points" with modeled ownership | Weak; it is our projection, and the field's extra info is not captured |

**Verdict for the parking-lot gate: no classic chalk/ownership construction lever is shippable. Keep lambda 0 for cash/SE, and do not add a chalk QB rule.**

## 10. Open follow-ups (parking lot, not chased)
1. **Ownership discrimination is the bottleneck.** Lineup corr 0.33 within quality lineups, and the #1 QB is right only 10% of the time. The top-player over-concentration (FC-history findings) is directly implicated.
   A retest after the Wk3 refit/calibration should report "#1 QB hit rate" and "quality-lineup corr" as the metrics, with a target of ≥0.6.
2. **FC `proj_own` timing.** If it is truly pre-lock, a public projected-ownership feed (FFC and others) might carry most of the edge. Measure FFC's lineup corr on 2026 slates as they accrue.
3. **Our projection beats FC's** at lineup level (+0.06 to +0.10 capped return per SD, 4/4 seasons in quality). That is a projections-push data point, not an ownership one.
4. Track 2: a modeled-ownership tiebreak among near-equal lineups (Weak). Re-test only after item 1 improves.
