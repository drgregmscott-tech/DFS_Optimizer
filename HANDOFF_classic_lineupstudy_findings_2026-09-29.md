# Classic lineup-study findings: REAL fields, 410 DK classic contests, 2022-2026 (2026-09-29)

Source: FantasyCruncher Lineup Study exports in `data/fc_history/lineup_study/*.json.gz`, all non-`SHOWDOWN`, non-`_LIST` files
(subscription data, gitignored; **do not commit**). Sibling of `HANDOFF_showdown_lineupstudy_findings_2026-09-28.md` (same method).
Scripts (no FC data inside), in `analysis/classic_history/`:
- `lineup_study_build.py`: parse, QA, per-entry features, per-player field/cash rostership.
- `lineup_study_analysis.py`: feature lift tables, the headline ownership test, per-contest regressions, and cash-vs-noncash shape.
- `lineup_study_players.py`: player-level "who consistently cashes" by role.

Committed outputs (aggregate only): `analysis/classic_history/out/cl_*.csv`, `cl_analysis_out.txt`.
Per-entry and per-player caches go to `data/fc_history/derived/classic/` (gitignored, raw-derived). This doc has aggregate statistics only.

```
FC_LS_DIR=<path to lineup_study> python analysis/classic_history/lineup_study_build.py   # ~15 min on 8 procs, 22.1M entries
cd analysis/classic_history && python lineup_study_analysis.py                              # ~60 min, low memory (one contest at a time)
python lineup_study_players.py                                                              # ~2 min
```

## TL;DR
- **Headline: in real classic fields, higher realized ownership predicts cashing and return. This holds after controlling for FC projection and among optimizer-quality lineups, in every GPP format and every season.**
  - The test: within each contest, lineups with ≤$500 salary left and top-40% FC projection were split into fifths by summed realized ownership.
    - SE (124 contests): the most-owned fifth had cash lift +8.8 pts [+7.0,+10.6] and capped return 1.20x [1.11,1.28]. The least-owned fifth had -8.0 pts and 0.80x.
    - 20-max (133 contests): most-owned 1.30x [1.23,1.37], least-owned 0.72x.
    - 3-max (61 contests): most-owned 1.23x, least-owned 0.78x.
  - Per-contest OLS on all lineups, with FC projection held fixed: +0.19 capped return per SD of ownership in SE [+0.14,+0.25] and +0.27 in 20-max [+0.23,+0.32]. Positive in 4/4 seasons for both.
  - **Uncapped return is flatter at the top.** Among SE quality lineups, the most-owned fifth returned 1.04x uncapped [0.96,1.12]. So chalk buys cash rate and average return, but not clearly first-place equity. This is the same shape as the Showdown result.
- **The mechanism is player-level: the crowd knows something FC's projection doesn't.** Holding FC projection and salary fixed, a player's realized ownership predicts his actual points:
  +1.1 (DST) to +2.8 (RB) pts per SD of log-ownership, positive in 4/4 seasons at every position (71-72 slates).
  Players owned 20%+ are over-represented in cashing lineups (cash/field rostership 1.09-1.24 at RB/WR/TE, 4/4 seasons). Players owned 2-5% are under-represented (0.76-0.89, 0/4 seasons).
  That is the repeatable pattern the §3 framing asked for. **Caveat:** this is post-lock ownership. See §7 and the pre-lock caveat already on file for Showdown.
- **How Phase 2 (11 slates) holds up at scale:**
  - **Confirmed:**
    - QB+2 stacks help, mainly on return: 1.12-1.14x, 4/4 seasons.
    - Bring-back helps a little.
    - 0 punts costs you.
    - Spend to within $500.
    - The hindsight chalk-lineup benchmark.
  - **Smaller than Phase 2 said:**
    - QB+2 cash lift is +1.0-1.4 pts, not +3.7.
    - QB+3 is not a further gain.
  - **Contradicted:**
    - "Cheap QB cashes." The QB-salary effect is null after a projection control, and the cash-vs-noncash QB salary gap is $10-40, not ~$200.
    - "More punts / more studs = better." One punt is the sweet spot, and 3+ studs is mildly negative.
  - The QB signal that does replicate is **QB ownership**: the #1-owned QB gives +5.0 cash pts, 4/4 seasons in SE.
- **gmscott81's own 143 entries in these contests (2022-26) show a regime change, and it lines up with the headline.**
  - 2022-24: 87 entries, cashed about 63% against a ~28% base. Lineups sat at the 85th percentile of contest ownership.
  - 2025-26: 56 entries, cashed 27% (base 25%). Ownership fell to the 54th percentile.
  - QB+2 was rare in both eras (8% and 2%), so the missing QB+2 does not explain the drop. Falling chalk exposure might.
  - Small n; 40 of the 56 recent entries are two 2026 MME pools. Directional, but worth a look.

## 1. Data and quality
- **431 classic contest files; 22.1M entries.** The seasons are 2022 wk1-18, 2023 wk1-18, 2024 wk4-18 and 2025 wk1-18. **2026 has only wk1 and wk2 (2 slates), and wk3 is not in the pull.** 2024 wk1-3 is also absent, the same as Showdown.
  **Action for the 2026-10-02 trial deadline:** pull 2026 wk3 (and wk4 once it settles) classic contests, especially gmscott81's actual Wk3 contests, before the subscription lapses.
- **Contest types, grouped:**
  - **SE** (140 contests after exclusions): SE_dollar is the $1 Daily Dollar SE (~18k entries). SE_big is the $100 SE (~4.4k). The 2026 "SE" files run $3-$12.
  - **3MAX** (66): ~$1, ~18k entries.
  - **20MAX** (139): $1 20-max First Down (~178k), the $0.10 "dime" 20-max (~119k) and the 2026 "20MAX_low".
  - **DU** (65): the $5 GIANT Double Up, 150-max (~11.5k).
- **Excluded: 21 contests.**
  - 5 were truncated at the ~25.5k-row FC cap (2024wk5/9/10/12, 2025wk2 20-max). Rows/entrants was 0.14-0.79 on these, and FC's own% disagreed with the realized rostership, which confirms a partial field.
  - 16 had fewer than 1,000 entries (small wk12-18 3MAX/DU/SE side contests).
  - **Analysed: 410 contests, 21.9M entries.**
- **Schema verified on every file.** `roster_order` is QB,RB,RB,WR,WR,WR,TE,FLEX,DST in 431/431 files.
  - The QB slot holds a QB ≥99.4% of the time and the DST slot a DST 100%.
  - The TE slot holds a TE ≥98.3%. The misses are metadata-less players, whose position was filled from the slot.
  - 0-1.3% of rows per contest have an empty lineup and were dropped.
- **Scores: FC's per-player `fantasy_points` are reliable for classic.** The sum of the 9 players reproduces entry points exactly (p99 residual 0.0) on 425/431 files.
  - On 6 files a minority of lineups disagreed, up to 20%. There, all scores were re-solved by sparse least squares. The final p99 residual is ≤1e-6 on every file.
  - The Showdown-style full re-solve was not needed elsewhere.
- **Salaries are complete apart from 1-9 metadata-less players per file.** Those include FC placeholders `99999`/`999999` and a few late-listed players.
  - Their salary comes from the $50k-cap bound. That bound reproduces known salaries 98-100% of the time, mean 99.99%.
  - A handful of lineups exceed the cap with FC's listed salaries (≤0.013% of any contest; late swap). They are kept, but excluded from the bound.
- **Payouts.** `cash_amt` is all zero on 2025 wk15-17 (18 files). There, payouts were rebuilt from the prize table with tie-splitting.
  Where both exist, the rebuild agrees with `cash_amt` on a median 99.96% of rows. It agrees less (22-94%) on small 3MAX and DU contests because of tie/range handling. There `cash_amt`, which sums exactly to the prize pool, is used.
- **Ownership = realized rostership computed from the rows (the real field).** FC's stored `own` matches it (mean abs error 0.02-0.04 pts) on every complete file.
- **FC projections are unusable on 28 contests** (2022wk2, 2024wk15-17, 2025wk1-3 and a few others): 30-89% of lineups have a player projected 0, or projections are flat. Those contests are excluded from the projection-controlled tests only.
- **gmscott81** appears in 143 entries across 99 contests.

## 2. Method (same as Showdown)
- Every metric is computed **within a contest** and then averaged with **equal weight per contest**. 90% CIs come from bootstrapping over contests (2,000 draws). A level needs ≥30 entries in a contest to count there.
- Metrics:
  - **Cash lift**: level cash rate minus contest cash rate, in points. Base rates: SE 23.7%, 3MAX 25.6%, 20MAX 25.4%, DU 46.9%.
  - **Return (capped)**: mean payout capped at the contest's 99.9th-pct prize, divided by the contest mean.
  - **Return (uncapped).**
  - **Top-1% lift.**
- **Grading:**
  - **Supported**: the CI excludes 0 and the sign holds in ≥3 of 4 seasons (2022-25) in the GPP formats (SE/3MAX/20MAX), unless stated.
  - **Weak**: right direction, but the CI touches 0 or it holds in only one cut.
  - **Not supported**: null or wrong sign.
- Feature definitions copy WK3 Phase 2 exactly, for comparability:
  - Stack = same-team WR/TE with the QB. "Stack incl. RB" is also shown.
  - Studs = non-DST at ≥$7,000; punts = non-DST at ≤$4,000.
  - Bring-back = non-DST, non-QB players from the QB's opponent.
  - DST conflict = the DST faces one of the lineup's own players.
- **Observational, not a strategy backtest.** Shape lifts mix "this shape is good" with "people who build this shape are good".
  The headline test (§4) and the multi-feature regression (§5) add the FC-projection control and the optimizer-quality subset (≤$500 left and top-40% projection within the contest). Treat §3 as "what cashing real entries look like".
- **DU is a cash game (46.9% base, flat payouts) and behaves differently.** It is reported, but not used for GPP grading.

## 3. Real-field shape results (cash lift pts [90% CI], seasons with the sign; capped return in parentheses)

| Feature | SE (140) | 3MAX (66) | 20MAX (139) | DU (65) | Grade (GPP) |
|---|---|---|---|---|---|
| QB+0 WR/TE (share 18-25%) | -0.5 [-1.1,+0.2] (0.93) | -0.9 (0.91) | **-2.2 [-2.7,-1.7]** 0/4 (0.86) | +1.6 (1.05) | Weak-bad |
| QB+1 (48-52%) | -0.5 (0.95) | -0.6 (0.95) | +0.2 (1.00) | **-8.5** (0.84) | null |
| **QB+2 (24-30%)** | **+1.0 [+0.4,+1.6]** 3/4 (**1.14** [1.10,1.18] 4/4) | +0.8 [+0.1,+1.5] (**1.10** 4/4) | **+1.4 [+0.9,+1.9]** 4/4 (**1.12** 4/4) | -9.4 (0.85) | **Supported** (return); cash +1 |
| QB+3+ (2-3%) | +0.4 (1.11) | +0.1 (1.15) | **-1.9** (1.01) | -20.8 | Not supported beyond QB+2 |
| Naked QB (no RB/WR/TE teammate) | -0.8 [-1.4,-0.1] (0.92) | -1.2 (0.89) | **-2.4** 0/4 (0.85) | +0.1 | Supported-bad (GPP); fine in DU |
| QB + own RB | -0.1 (0.96) | +0.2 | -0.5 (0.96) | -4.8 | null |
| Bring-back 0 / 1 / 2+ | -0.9 / +0.7 / **+1.9** (0.95/1.05/1.11) | -0.8 / +0.4 / +1.9 | -1.1 / +1.1 / +1.8, 4/4 | -2.8/-2.4/-3.7 | Supported (small); drops out among quality lineups (§5) |
| QB-game players 1 / 2 / 3 / 4 / 5+ | -1.0/-1.0/-0.1/**+1.1/+1.5** (0.90…1.15) | -1.3/-0.9/-0.3/+0.6/+1.8 | -2.4/-0.9/+0.6/+1.2/+0.6 (…1.10) | | Supported (game stacks of 4+ return 1.06-1.15, 4/4) |
| Max from one team 1 / 2 / 3 / 4 / 5+ | -1.5/-0.5/+0.6/+0.6/-2.3 | -1.9/-0.9/+0.6/+0.8/-2.4 | -3.2/-0.6/**+1.2**/-0.3/**-5.8** | | 3 (or 4) best; 5+ bad |
| QB salary <5.5k / 5.5-6.4k / 6.5-7.4k / 7.5k+ | -0.8 / -0.4 / -1.2 / -1.1 (0.97/0.98/0.93/0.96) | -1.6/-0.2/-0.4/-1.3 | -0.4 / 0.0 / -0.9 / **-2.2 [-3.9,-0.4]** (0.90) | | **Not supported** as "cheap QB"; all CIs span 0 except 20MAX 7.5k+ |
| QB is top-3 priced on slate | -1.5 [-2.9,-0.2] (0.94) | -1.6 | **-1.9 [-3.1,-0.7]** 0/4 (0.91) | -7.8 | Weak-bad raw; **null after projection control** (§5) |
| **QB own rank #1 / #2-3 / #4-6 / #7+** | **+5.0 [+2.8,+7.3] 4/4** (1.21) / -0.9 / -1.0 / **-2.5** | +4.5 / +0.3 / -0.9 / -3.3 | **+5.2** 3/4 (1.22) / +0.6 / -0.8 / **-3.1** | +5.6/-3.8/-10.8/-17.8 | **Supported**: chalk QB cashes |
| Studs 0 / 1 / 2 / 3+ | -2.2 / -0.1 / +0.3 / **-1.2** | -2.5/-0.2/+0.4/-1.3 | -1.6/+0.1/+0.4/**-2.2** 0/4 (0.90) | -16.6/-5.6/-3.2/-10.2 | 1-2 studs best; 3+ mildly bad |
| Punts 0 / 1 / 2 / 3+ | **-2.2 [-3.2,-1.3]** (0.89) / +0.3 / +0.3 / **-2.7** | -2.3/+0.4/+0.2/-4.1 | -1.9/+0.3/+0.1/**-4.7** (0.77) | -10.4/-3.1/-3.8/-15.4 | **Supported**: 0 punts bad, 1 best, 3+ bad |
| Salary left 0-500 / 500-1k / 1-2k / 2k+ | +0.1 / -2.7 / -5.6 / -15.5 | +0.1/-2.6/-5.3/-15.8 | +0.2/-2.2/-6.0/-15.0 | | Supported, 4/4 |
| FLEX = RB / WR / TE | **+0.9 / -1.2** / -0.6 | +0.7 / -1.3 / -0.5 | **+1.0 4/4 / -1.5 0/4** / -0.3 | | **Supported**: RB FLEX > TE > WR |
| TE <3.5k / 3.5-4.4k / 4.5-5.9k / 6k+ | +0.6 / -0.6 / **-1.9** / -2.5 | -0.1/-0.5/-2.0/-3.3 | 0.0/-0.3/**-1.6**/-1.7 | | Weak: mid-priced TE is the worst bucket |
| DST <2.8k / 2.8-3.1k / 3.2-3.5k / 3.6k+ | +0.3 / **+0.8** (1.07) / -1.0 / **-2.3** (0.90) | +0.3/+1.2 (1.09, 4/4)/-1.2/-2.8 | +0.4/**+1.2** (1.06)/-1.3/**-2.9** 0/4 (0.86) | | **Supported**: expensive DST bad; $2.8-3.1k best, not min price |
| DST faces own player (11-13%) | **-1.9 [-2.4,-1.4]** (0.89) | -2.1 (0.88) | **-3.0** 0/4 (0.85) | 0.0 | **Supported** |
| DST + own RB | -1.1 [-1.8,-0.4] | -0.6 | -1.0 0/4 | | Weak-bad |
| # of the slate's top-5-owned players 0 / 1 / 2 / 3 / 4+ | -7.7/-3.5/+1.2/**+6.4/+10.6** (0.67…1.31) | -8.2/-3.2/+1.6/+6.5/+11.9 | -8.6/-2.8/+3.5/**+10.1/+14.8** (…1.56) | | Supported, 4/4 |
| # of <2%-owned players 0 / 1 / 2 / 3+ | **+3.6** / -2.7 / -7.2 / **-11.9** (1.17…0.47) | +3.8/-2.9/-8.2/-13.2 | +4.4/-2.8/-8.4/-14.0 | | Supported, 4/4 |
| Exact duplicates: unique / 2-5 / 6-20 / 21+ | -0.7 / +12.3 / +19.2 / **+26.6** (0.97…1.84) | -0.8/+6.8/+14.6/+26.1 | -1.0/+3.7/+5.8/+20.8 | | Supported, 4/4 (same as Showdown) |
| FC projection fifth 1…5 | -7.1 … **+7.9** (0.70…1.38) | -8.2 … +8.7 | -8.9 … +8.9 (…1.41) | | Supported |

Full tables, including top-1% lift, per-season values and DU: `analysis/classic_history/out/cl_feature_lift.csv` and `cl_analysis_out.txt`.

## 4. Headline test: ownership within contest, projection-controlled, among quality lineups (`cl_headline.csv`, `cl_slopes.csv`)

| Cut | Contests | Q1 (least owned) cash / capped ret | Q5 (most owned) cash / capped ret | Q5 uncapped | Q1 uncapped |
|---|---|---|---|---|---|
| SE, all entries | 140 | -8.3 / 0.67 [0.61,0.73] | **+9.1 [+7.5,+10.5] / 1.33 [1.25,1.42]** 4/4 | 1.23 [1.12,1.33] | 0.72 |
| SE, quality | 124 | -8.0 / 0.80 [0.73,0.88] | **+8.8 [+7.0,+10.6] / 1.20 [1.11,1.28]** 3/4 | 1.04 [0.96,1.12] | 0.86 [0.76,0.98] |
| SE, quality, ownership residual after projection | 123 | -7.5 / 0.81 | **+7.6 / 1.18 [1.10,1.26]** 3/4 | 1.06 [0.98,1.15] | 0.86 |
| 3MAX, quality | 61 | -8.8 / 0.78 | **+9.9 / 1.23 [1.13,1.34]** 4/4 | 1.13 [1.02,1.24] | 0.81 |
| 20MAX, all entries | 139 | -10.6 / 0.56 | **+12.1 / 1.49 [1.41,1.56]** 4/4 | 1.40 | 0.56 |
| 20MAX, quality | 133 | -9.6 / 0.72 [0.67,0.78] | **+11.1 / 1.30 [1.23,1.37]** 4/4 | 1.18 [1.10,1.26] | 0.76 |
| 20MAX, quality, own residual | 132 | -8.8 / 0.74 | **+10.0 / 1.29** 4/4 | 1.19 | 0.79 |
| DU, quality | 59 | -10.3 | +2.6 [-3.9,+9.4] | - | - |

Notes on the table:
- In DU the quality subset is small and its return ratios are unstable. Only 20 DU contests had enough spread for the residual cut.
- Across all DU entries, the most-owned fifth was +15.2 cash and the least-owned -18.1.

Per-contest OLS, per SD of summed ownership (90% CI; contests positive):

| | cash, raw | cash, proj-controlled | capped return, proj-controlled | points, proj-controlled |
|---|---|---|---|---|
| SE all | +6.4 pts | **+5.3 [+4.2,+6.3]** 96/129, 4/4 | **+0.19 [+0.14,+0.25]** 4/4 | +5.2 [+4.4,+6.0] |
| SE quality | +5.9 | **+5.4 [+4.3,+6.5]** 4/4 | **+0.17 [+0.10,+0.24]** 3/4 | +4.6 |
| 3MAX quality | +6.9 | **+6.5 [+4.5,+8.3]** 4/4 | **+0.24 [+0.14,+0.34]** 4/4 | +5.0 |
| 20MAX all | +8.2 | **+6.9 [+5.9,+7.9]** 4/4 | **+0.27 [+0.23,+0.32]** 4/4 | +6.0 |
| 20MAX quality | +7.4 | **+6.9 [+5.8,+8.1]** 4/4 | **+0.27 [+0.21,+0.33]** 4/4 | +5.3 |

- For comparison, FC projection itself carries less than ownership once both are in the model: +2.5-2.8 cash pts per SD across all entries and +2.0-2.5 among quality lineups.
  corr(own, proj) is 0.44-0.48 across all lineups and ~0.2 within the quality subset.
- **Reading.** Real classic fields behave like real 150-max Showdown fields, only more strongly. Holding projection and shape quality fixed, lineups built from what the field is on outscore those that aren't, by ~5 pts per SD.
  Ownership is not mainly a duplication penalty here (unique lineups are the *worst* bucket). It is information the crowd has and FC's projection lacks (player-level check in §6).
  At the extreme top (uncapped, first-place prizes), the chalk edge shrinks to about neutral in SE. That matches Showdown's "chalk doesn't cost tail equity but doesn't clearly add it".

## 5. Which shape features survive a projection control? (multi-feature per-contest OLS; `cl_slopes.csv`, `*_m_*` rows)
Every contest gets the model: y ~ ownership + FC projection + QB salary (per SD) + QB+2 (0/1) + ≥1 punt (0/1) + ≥1 bring-back (0/1) + salary left (per SD). Coefficients below are for **cash rate (pts)**, with capped return in parentheses.

| Term | SE all | SE quality | 3MAX quality | 20MAX all | 20MAX quality |
|---|---|---|---|---|---|
| Ownership (per SD) | **+5.1** (+0.18) | **+5.1** (+0.16) | **+6.3** (+0.22) | **+6.7** (+0.26) | **+6.6** (+0.25) |
| FC projection (per SD) | **+2.7** (+0.14) | **+2.4** (+0.15) | **+2.4** (+0.13) | **+2.8** (+0.14) | **+1.9** (+0.10) |
| QB salary (per SD) | +0.3 [-0.5,+1.2] (+0.01) | +0.1 | -0.1 | -0.1 (-0.01) | -0.3 (-0.02) |
| QB+2 stack | **+1.6 [+0.9,+2.3]** (**+0.19**, 4/4) | +0.8 [-0.3,+1.8] (**+0.17** [+0.09,+0.25], 4/4) | -0.7 (+0.12 [+0.02,+0.22]) | **+1.6** (**+0.14**, 4/4) | +0.9 [+0.0,+1.7] (**+0.16**, 4/4) |
| ≥1 punt | **+1.4** [+0.3,+2.5] (+0.07) | **+1.8** [+0.2,+3.3] | +1.4 [-0.7,+3.5] | **+1.4** (+0.07) | **+1.9** [+0.5,+3.2] (+0.10) |
| ≥1 bring-back | +0.4 [-0.3,+1.1] | -0.5 | -0.9 | **+0.7** | -0.1 |
| Salary left (per SD) | -0.5 | -0.5 | -0.2 | -0.4 | -0.3 |

- **QB salary is null** once projection is in the model, in every format and subset. With only a projection control, the QB-salary slope on cash is -0.1 to -0.6 pts per SD, and every CI spans 0.
- **QB+2 is a return feature more than a cash feature.** Among quality lineups it adds about +0.16 capped return (Supported, 4/4) but under 1 pt of cash rate. It raises the ceiling rather than the floor, which is what a GPP stack should do.
- **One punt helps**, by +1.4 to +1.9 cash pts after controls (Supported in SE and 20MAX).
- **Bring-back does not survive** the quality subset. Its raw lift is a correlate of good builds rather than an effect of its own.

## 6. Player-level: what do consistently-cashing players have in common? (`cl_player_roles.csv`, `cl_player_points_vs_own.csv`, `cl_player_own_coef.csv`)
This is the §3 framing question: not winning lineups, but roles that repeatedly show up in cashing lineups more than in the field.
- **Ownership tier is the dominant, repeatable signal.** It is measured as cash-lineup rostership / field rostership, averaged per slate over players with ≥2% ownership.

  | Ownership tier | RB | WR | TE | QB | DST |
  |---|---|---|---|---|---|
  | 2-5% | 0.78 (0/4) | 0.84 (0/4) | 0.91 (0/4) | 0.92 (0/4) | 0.94 (0/4) |
  | 5-10% | 0.91 | 0.95 | 0.91 | 0.95 | 0.98 |
  | 10-20% | 0.99 | 1.03 | 1.06 | 1.08 | 1.08 (4/4) |
  | 20%+ | **1.09 (4/4)** | **1.11 (4/4)** | **1.22 (4/4)** | 1.13 | 1.04 |

  These are SE values; 20MAX and 3MAX are nearly identical. The share of players who are clear "cash drivers" (ratio >1.25) rises from 12-18% in the 2-5% tier to 33-38% in the 20%+ tier.
- **Why: ownership predicts actual points beyond FC projection and salary.** This is a per-slate regression on the largest contest of each slate, with FC projection and salary as controls.
  Per SD of log-ownership: RB **+2.8** [+2.5,+3.2], WR **+1.8** [+1.5,+2.0], TE **+1.6** [+1.4,+1.9], QB **+1.5** [+1.0,+2.0], DST **+1.1** [+0.8,+1.5]. All 4/4 seasons, 71-72 slates.
  This is the classic-slate version of Phase 1 Step 5 ("our under-ownership correlates with points") and of the Showdown §5 finding. Where the field is, the points are, more than FC says.
- **Price tier on its own is not the pattern.** Within position, leverage by salary tier alone is 0.9-1.04 everywhere, with no tier consistently >1.
  Cheap chalk (for example, low- and mid-low-priced WRs owned 20%+: 1.13-1.16, 4/4; low-priced TE 10-20%: 1.12) does as well as expensive chalk (high-priced WR 10-20%: 1.14, 4/4).
  So Phase 1's "cheap band is where our misses cost points" is consistent with this. What matters is being on the cheap players the field is on, not cheapness itself.
- FC's projections run 0.5-1.8 pts high against actuals in almost every tier. Only the level is biased; the relative comparisons above are unaffected.

## 7. Cross-reference to WK3_ROOT_CAUSE_FINDINGS.md Phase 1/2

| Phase 2 claim (11 slates, n = 275K field entries) | At scale (410 contests, 21.9M) | Verdict |
|---|---|---|
| Hindsight chalk lineup beat our SE entry 9/9; "just play the chalk" | Most-owned fifth: +8.8 to +12 cash pts. More top-5-owned players is monotone (+6 to +15 at 3-4 of them). The effect holds with a projection control among quality lineups. | **Confirmed at scale** (still realized/post-lock ownership) |
| QB+2 stack lift +3.7 pts, QB+3 +6.7 | QB+2 +0.8 to +1.4 cash, return 1.10-1.14 (4/4). QB+3+ -1.9 to +0.4 cash, return 1.0-1.15. Controlled: QB+2 +0.16 return among quality lineups. | **Direction confirmed; magnitude ~1/3; QB+3 not confirmed** |
| Cashing field ~30% QB+2 vs our 0/40 MME | Cashing 28.5-33.1% vs non-cashing 26.6-31.2% (diff +1.6 to +1.9 pts, CI excludes 0) | **Confirmed** (the field level is ~30%; the gap is small) |
| Naked QB 13.5% cash vs 15.9% noncash | Naked QB -0.8 to -2.4 cash, return 0.85-0.92 | **Confirmed** |
| Cashing field QB salary ~$5,850 vs noncash ~$6,070; ours $6,333-6,748 | Cash vs noncash gap only -$10 (SE), -$7 (3MAX), -$39 (20MAX); CIs span 0 in SE/3MAX. Field average ~$6,220-6,290. Null after projection control. The top-3-priced QB is -1.5 to -1.9 raw. | **Contradicted as a price effect.** The replicable QB signal is **ownership** (#1-owned QB +5 cash, 4/4). The Wk1-3 cheap-QB result was those specific slates (Shough/Geno/Dak). |
| Our QBs pricier than the field | gmscott81 across 2022-26: QB $6,370 (SE), $6,675 (3MAX), $6,550 (20MAX) vs field $6,220-6,280 | **Confirmed as a long-standing trait of our builds**, but at scale not what separates cashing lineups |
| Punts: cashing 1.06 vs our 0.44; 0 punts -8.9, 2 +7.9, 3+ +8.6 | Cashing 1.08-1.10 vs noncash 1.07-1.09 (no meaningful gap). 0 punts -1.9 to -2.3 (Supported). 1 punt best. 3+ punts -2.7 to -4.7. | **"0 punts is bad" confirmed (at ~1/4 the size); "more punts better" contradicted** |
| Studs: 0 -15.4, 3+ +6.2 | 0 studs -1.6 to -2.5; 1-2 ≈ 0; **3+ -1.2 to -2.2 (0/4 in 20MAX)** | **Contradicted** (the Phase 2 stud gradient does not replicate) |
| Bring-back lift 0:-1.0 / 1:+0.9 / 2:+4.0 / 3+:+6.8 | 0: -0.9, 1: +0.7 to +1.1, 2+: +1.8 to +1.9. Not significant among quality lineups. | **Direction confirmed, small, Weak** |
| Salary left: ≤$500 fine; >$1k costs 3.6-12 pts | ≤$500 +0.1; 500-1k -2.2 to -2.7; 1-2k -5.3 to -6.0; 2k+ -15 | **Confirmed** |
| FLEX = TE 26.7% cash vs 21.1% noncash (and we played TE FLEX 66.7% in SE) | FLEX TE -0.3 to -0.6 (null to slightly bad); FLEX RB best (+0.7 to +1.0, 4/4); FLEX WR worst (-1.2 to -1.5, 0/4) | **Contradicted** (TE FLEX is not a cashing trait) |
| DST conflict | -1.9 to -3.0, 0/4 seasons, 11-13% of the field | **New, Supported** (Phase 2 measured it but reported no lift) |
| Phase 1 Step 5: under-owning players costs points, sharpest in the cheap band | Ownership → points beyond FC projection and salary, at all positions, 4/4 seasons | **Confirmed and generalised**. The cheap band is not special once ownership is known. |

**What this means for the Wk3 root-cause read:**
- The large sample says the two biggest construction levers are:
  1. Being on the field's chalk, especially the chalk QB.
  2. Stacking QB+2 for return in GPPs.
- QB price, stud count and punt count beyond one matter little or not at all.
- That points the root cause back toward **ownership/projection inputs** (Phase 1 Step 4a and the chalk_score ranking and softmax cap) rather than toward construction rules. The one construction item that holds up is the MME QB+2 setting.
- gmscott81's own history supports this:
  - The 2022-24 entries were built heavily on chalk (85th ownership percentile) and cashed ~63%.
  - The 2025-26 entries sit at about median ownership and cash at base.

## 8. Caveats
- **Realized, post-lock ownership.** This is the largest caveat. The headline says the *real* field's chalk is informative. It does not say *our pre-lock projected* ownership is.
  The checklist already records that a Showdown chalk tilt using our modeled ownership was **Not supported pre-lock**. Any classic chalk tilt must be re-tested with projected ownership before shipping. The effect here is an upper bound.
- Observational (§2). Only §4-§5 carry projection and quality controls, and FC projection is a weak control: ownership beats it.
  Some of the "ownership" effect is simply better projection information. That is useful to know, but it may be better captured by improving projections than by a leverage term.
- Multi-entry sharks dominate 20-max fields, and entries by the same user are correlated. The contest-level bootstrap handles this only partly.
- The ~25.5k-row cap truncated 5 contests (excluded). **2026 has only wk1-2**, so pooled numbers are 2022-25-driven, and 2026 is excluded from the season-sign counts.
- The gmscott81 era comparison is small (87 vs 56 entries). 40 of the recent entries come from 2 MME contests, and the contest mix shifted. It is directional only.
- DU is a cash game and is not graded with the GPP formats. The DU quality subset is too thin (20-59 contests) for the projection-controlled cut.

## 9. Open questions / next steps
1. **Pull 2026 wk3+ classic contests before 2026-10-02**, including gmscott81's Wk3 SE/SE3max/MME contests. This is the only data here with a deadline.
2. Re-run §4 with our **pre-lock projected ownership** (the `ownership_actual_log.csv` era) in place of realized ownership. This is the classic version of the Showdown pre-lock test, and it decides whether any chalk tilt is shippable.
3. MME stack-depth setting: allow or require QB+2 in a share of lineups (Phase 2 next step, now Supported on return at scale).
4. Candidate construction checks (all Supported here; informational until tested in replay):
   - No DST facing own players.
   - DST $2.8-3.1k over $3.6k+.
   - Prefer RB in FLEX over WR.
   - At least 1 punt, at most 2.
5. The gmscott81 2022-24 vs 2025-26 drop: check whether the build process changed at the 2025 boundary (tooling, ownership source).

## 10. Session log
- 2026-09-29: first classic pass. Built the parser (QA on all 431 files; scores verified exact), ran the feature/headline/player analyses, and cross-referenced Phase 2. Nothing shipped to the optimizer.
