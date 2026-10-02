# Showdown follow-up: chalk tilt with OUR modeled ownership, plus construction detail (2026-09-28)

This follows up `HANDOFF_showdown_lineupstudy_findings_2026-09-28.md` (§8-9 open questions) and uses the same 142 real DK Showdown contests, the same metrics and the same grading (Supported / Weak / Not supported).
It contains aggregate statistics only. The FC data and every per-entry cache stay gitignored; **do not commit them**. `SHOWDOWN_RULES.md` and production code were not touched.

Scripts, all new and in `analysis/showdown_history/`:
- `lineup_study_ids_build.py` re-parses the files and keeps per-entry player ids. The old cache kept only derived features, so a re-parse was needed.
  - Outputs: `lineup_study/_sd_entries_ids.parquet` and `_sd_players.parquet` (raw-derived, gitignored).
  - It reuses the `lineup_study_build.py` helpers and reproduces the same 14,885,437 entries.
- `lineup_study_modeled_own.py --pools --proj --own --test` handles Task 1.
- `lineup_study_construction_detail.py` handles Task 2.

Outputs go to `data/fc_history/derived/showdown/`:
- Task 1: `ls_modown_*.csv` and `ls_modown_out.txt`. The replay files are in `ls_replay/`.
- Task 2: `ls_cd_*.csv` and `ls_cd_out.txt`.

Note: these scripts were written in an agent worktree. They read and write data in the main checkout, because the data only exists there. Set `DFS_ROOT` to override that location.

## TL;DR
- **Task 1: chalk tilt does NOT survive with our pre-lock modeled ownership. It is Not supported as an optimizer term. Keep lambda 0 everywhere.**
  - Big GPPs, same 69 contests, realized ownership: Q5-Q1 capped-return gap **+0.44 [+0.26,+0.64]** and projection-controlled slope **+0.13 [+0.05,+0.21]**. This reproduces the prior doc.
  - Same test with our modeled ownership: gap **+0.08 [-0.13,+0.28]**, slope **+0.007 [-0.07,+0.09]**.
  - Among optimizer-quality lineups the gap turns negative: **-0.13 [-0.40,+0.14]** (n = 30).
  - The edge lives in what the field knows at lock that our model does not. At lineup level, our summed ownership correlates only 0.56 with realized ownership.
- **Construction findings (Task 2), in order of usefulness:**
  1. **The QB's partner matters: QB CPT + his RB or TE beats QB CPT + his WR.** Pairing is by the highest-salary same-team FLEX.
     - Partner RB: cash **+6.7 SE / +4.1 big**, return 1.34 / 1.15.
     - Partner TE: **+7.3 / +5.7**, return 1.33 / 1.23.
     - Partner WR: +0.8 / -1.4, return 0.99 / 0.88.
     - WR is the field's default (57-61% of QB CPTs).
  2. **The pass-catcher-needs-QB rule is confirmed, and there is a sharper version: a WR CPT paired with another same-team WR (and no QB) is the worst skill shape.**
     - Cash -7.6 / -7.7, return 0.69 / 0.60, both CIs exclude 0.
     - TE CPT + WR partner: -5.2 / -7.2.
  3. **Moderate stacks win and max stacks don't, especially for QB CPT.** QB CPT with 1-2 teammates: cash +4.6 to +5.8 SE, +2.2 to +3.7 big. With 3-4 teammates: ~0. WR CPT with 3 teammates: -3.2 / -3.0 (CI excludes 0).
  4. **The cheap tier matters.** A **$600-1k** FLEX is the one bad cheap tier: cash -1.7 / **-2.6**, return 0.82 / 0.83, top-1% lift negative with the CI excluding 0 in SE.
     - A genuine min-price (≤$500) punt is neutral (return 1.04 / 0.98).
     - A $1.1-2k player is the best cheapest-slot choice (cash +1.4 / +1.4, return 1.15 / 1.08; CI touches 0).
     - Two ≤$500 players is a disaster in big fields (-10.3 cash, 0.39 return).
  5. **4-2 with the CPT on the heavy side is the mildly negative split** (-1.6 / -1.4, CI excludes 0).
     - When that heavy side is the *underdog*, top-1% lift is positive in SE (+0.61 [+0.09,+1.19]). This is Weak.
     - A 5-1 onto the CPT's team vs onto the opponent: no reliable difference.
  6. **No dominant winning template.** For every CPT position, the single most common top-1% shape covers only 5-9% of top-1% lineups. It takes 14-19 shapes to cover half.

## Task 1: headline test with OUR modeled pre-lock ownership

### Coverage (n)
- **Games.** The 142 contests cover 83 distinct games. They are a different set from the 49 FC-history games (Thu/Sat standalone games) the refit used: only 27 of those 49 overlap, and they supply 54 of the 142 contests.
  So instead of reusing the old replay, I rebuilt pools for all 83 games from the lineup-study player tables.
  - The pools are deeper than the FC-history exports (43-54 players vs ~32), which is closer to live.
  - Same id mapping as `build_pools.py`: 3,969/4,221 players mapped and 252 unmapped. Most unmapped players are low-owned. Their share of ownership mass was not re-audited.
- **Projections.** The production statline engine replay (`run_sd_proj.run_slate`, QB-only depth chart, inactives zeroed) succeeded on **80/83 games**.
  - The 3 failures are all the 2026 wk1-2 slates, which fail in engine cold start (a player_id dtype merge error at week 1-2). I dropped them.
- **Ownership.** Production `build_features` (noisy ILP) plus `predict` with the **current production artifact**.
- **Result: 138 contests (69 SE + 69 big, 2022-25).** The 2026 contests are the only ones missing.
- **Player-level fit, modeled vs realized (mean per contest):**
  - CPT corr 0.71 SE / 0.76 big.
  - FLEX corr 0.81 / 0.84, FLEX MAE 5.5 / 4.7 pts.
  - This is in line with the refit doc's history numbers (0.72 / 0.80), so the replay behaves as before.
- **Known caveats, carried over and not re-derived:**
  - K/DST modeled levels do not transfer from the replay (the ILP under-rosters K/DST).
  - QB CPT is over-predicted.
  - 2022-23 inactives use the weekly-stats proxy.
  - A few contests have 1 stray-team player (traded or stale team). The replay kept that player in the pool.
- **FC's own pre-lock `proj_own`** was planned as a second pre-lock source. It is populated on only 1 contest, so it cannot be used.

### Results (same method as `lineup_study_headline.py` / `own_slope`: within-contest quintiles, equal weight per contest, 90% bootstrap CIs; "quality" = ≤$500 left and top-40% FC projection)

| Cut | Ownership source | Contests | Q1 return | Q5 return | Q5-Q1 gap [90% CI] | contests + | Seasons + (gap) |
|---|---|---|---|---|---|---|---|
| Big, all | realized | 69 | 0.78 | **1.22** | **+0.44 [+0.26,+0.64]** | 44/69 | 4/4 |
| Big, all | **our model** | 69 | 0.96 | 1.04 | +0.08 [-0.13,+0.28] | 33/69 | 3/4 (2022 -0.23) |
| Big, quality | realized | 30 | 0.85 | **1.23** | **+0.38 [+0.04,+0.73]** | 20/30 | 4/4 |
| Big, quality | **our model** | 30 | 1.02 | 0.90 | **-0.13 [-0.40,+0.14]** | 13/30 | 1/4 |
| SE, all | realized | 69 | 1.02 | 1.00 | -0.02 [-0.26,+0.24] | 33/69 | mixed |
| SE, all | our model | 69 | 0.98 | 1.04 | +0.06 [-0.17,+0.30] | 35/69 | mixed |
| SE, quality | realized / our model | 22 | 1.14 / 1.00 | 1.05 / 0.90 | -0.09 / -0.10 | | mixed |

Projection-controlled OLS, per SD of summed ownership (the FC projection is the control):

| | Realized: big | Our model: big | Realized: SE | Our model: SE |
|---|---|---|---|---|
| Capped return | **+0.132 [+0.048,+0.214]**, 35/53 +, 4/4 seasons | +0.007 [-0.073,+0.094], 22/53 +, 2/4 | -0.043 [-0.157,+0.066] | -0.004 [-0.100,+0.094] |
| Cash rate | **+2.3 pts [+1.0,+3.7]** | +0.2 [-1.4,+1.7] | +0.5 | +0.5 |
| Points | **+1.95 [+1.25,+2.71]** | +0.59 [-0.24,+1.38] | +0.93 [+0.02,+1.90] | +0.55 [-0.27,+1.39] |
| Lineup corr with FC projection | 0.46 | 0.28 | 0.38 | 0.29 |
| Lineup corr with realized own | 1.00 | **0.56** | 1.00 | **0.49** |

**Reading:**
- Realized ownership carries information about outcomes beyond FC's projection (+1.95 pts per SD). Our modeled ownership carries almost none (+0.59, CI spans 0).
- Our model is built mostly from projections via the ILP, so it mostly re-encodes projection. It does not capture the field's extra knowledge: late news, sharp consensus, or which captains sharks actually chose.
- The chalk edge in hindsight is therefore real, but it cannot be captured by tilting toward what *we* think will be chalk.

**Verdict:**
- **Chalk tilt with our modeled ownership: Not supported (big and SE).** The gap vanishes in all entries and flips sign among quality lineups. The OLS slope is 0.
- Leverage stays Not supported too: Q1 by modeled ownership is ~1.0, not a winner.
- **Keep lambda 0 for Showdown in every contest type.**
- The realized-ownership result stays valid as a *description*. It is not actionable pre-lock with the current ownership model.
- A chalk tilt would become testable again only with a pre-lock source that correlates far better with realized ownership (for example a late-swap/news-aware model). The bar is lineup-level corr well above 0.56. Parked.

## Task 2: construction detail (all 142 contests, 71 SE + 71 big)

Metrics are as in the source doc:
- **Cash lift**: pts vs the contest cash rate.
- **Return**: capped return.
- **Top-1% lift**: pts vs 1%.
- **Shares**: the equal-weight mean share of each level among the field, cashers and top-1% entries, *within the CPT-position group* where stated.

Caveats specific to this section:
- **Top-1% is thin.** SE contests have ~100-360 top-1% entries in total, split further by CPT position.
- **Top-1% shares understate the absolute level.** A contest with no top-1% entry for that CPT position contributes 0 to the share. Compare top-1% shares *across levels* (in the same row block), not against the field share in absolute terms. For "winning" behaviour, the top-1% lift with its CI is the reliable number.
- **Everything is observational** (source doc §2). Shape and builder skill are mixed.

### Q1. CPT position × primary same-team partner (partner = highest-salary FLEX on the CPT's team)
`ls_cd_partner_sal.csv` (a highest-owned partner version is in `ls_cd_partner_own.csv`; the pattern is the same).

| CPT | Partner | Field share SE / big | Cash-share SE / big | Cash lift SE | Cash lift big | Return SE / big |
|---|---|---|---|---|---|---|
| QB | WR | 61% / 57% | 56% / 50% | +0.8 [-1.6,+3.3] | -1.4 [-3.4,+0.7] | 0.99 / 0.88 |
| QB | RB | 26% / 30% | 32% / 35% | **+6.7 [+3.1,+10.2]** | **+4.1 [+1.5,+6.7]** | 1.34 / 1.15 |
| QB | TE | 9% / 9% | 9% / 10% | **+7.3 [+2.2,+12.9]** | **+5.7 [+1.7,+9.9]** | 1.33 / 1.23 |
| QB | none (naked) | <1% / 1% | | | | |
| RB | QB | 40% / 46% | 45% / 49% | **+4.2 [+1.0,+7.5]** | +2.6 [-0.1,+5.5] | 1.23 / 1.19 |
| RB | WR | 41% / 35% | 38% / 34% | -1.8 | -1.2 | 1.11 / 1.21 |
| RB | TE | 8% / 6% | | -0.8 | +0.2 | 0.93 / 0.94 |
| RB | RB (backfield mate) | 4% / 5% | | -2.4 | **-7.1 [-9.9,-4.4]** | 1.24 / 0.58 |
| WR | QB | 58% / 61% | 60% / 62% | -0.6 | -1.7 | 1.05 / 0.91 |
| WR | RB | 23% / 22% | 25% / 25% | -1.7 | -1.2 | 0.85 / 0.92 |
| WR | WR | 13% / 11% | 9% / 8% | **-7.6 [-10.2,-4.6]** | **-7.7 [-10.2,-4.8]** | 0.69 / 0.60 |
| WR | TE | 3% / 2% | | **-4.7** | **-4.7** | 0.64 / 0.68 |
| TE | QB | 49% / 54% | 51% / 55% | +0.5 | +0.4 | 0.95 / 1.00 |
| TE | RB | 24% / 22% | | -2.0 | -0.7 | 1.02 / 0.98 |
| TE | WR | 26% / 21% | 23% / 18% | **-5.2 [-8.6,-1.5]** | **-7.2 [-9.9,-4.4]** | 0.72 / 0.61 |

- "No same-team pass-catcher" with a QB CPT (naked QB) is under 1-2% of the field. It is too rare to grade here, so see the source doc §3 for the binary version.
- **Grades:**
  - QB CPT + RB or TE as the primary partner: **Supported**. Both contest types, and the CIs exclude 0.
    Caveat: "RB partner" often means the WR1 was left out for salary, so part of this is a salary/projection effect and not purely correlation.
  - Pass-catcher CPT + same-team pass-catcher and no QB: **Supported**-bad. It is the sharp form of the source doc's "pass-catcher CPT needs his QB".
  - RB CPT + his QB: **Weak-to-Supported** (SE CI excludes 0, big touches 0).
  - RB CPT + backfield-mate RB: **Supported**-bad in big.

### Q2. Stack depth (FLEX on the CPT's team, 0-4) by CPT position (`ls_cd_stack_by_cpt.csv`)

| CPT | 1 | 2 | 3 | 4 |
|---|---|---|---|---|
| QB: field share SE / big | 7% / 9% | 33% / 32% | 42% / 38% | 18% / 20% |
| QB: cash lift SE | **+5.8 [+1.9,+9.7]** | **+4.6 [+1.7,+7.7]** | +0.8 | +0.3 |
| QB: cash lift big | **+3.7 [+0.9,+6.6]** | +2.2 [0.0,+4.7] | +0.2 | -1.2 |
| RB: cash lift SE / big | +0.3 / -1.0 | +0.8 / +0.7 | +1.0 / +1.3 | -0.7 / +1.2 |
| WR: cash lift SE / big | -0.8 / -1.0 | -0.3 / -1.4 | **-3.2 / -3.0** (CIs exclude 0) | -2.2 / -2.7 |
| TE: cash lift SE / big | -1.7 / -1.5 | +0.1 / +0.4 | -0.3 / +0.7 | +0.5 / +0.3 |

- **There is a CPT-specific pattern, but it runs opposite to "QB CPT wants deeper stacks".** QB CPT does best with 1-2 teammates. Among top-1%, the QB-CPT share with 2 teammates (35%) beats 3 (31-33%), even though 3 is the field's most common depth.
- RB CPT is flat across depths. WR CPT is mildly negative at every depth ≥2 in big.
- 0 teammates is ≤3% of the field for every skill CPT.
- **Grade:** "QB CPT: prefer 1-2 same-team FLEX over 3-4" is **Weak-to-Supported** (SE CIs exclude 0 at 1-2; big excludes 0 at 1). This overlaps Q1: a QB with 1-2 teammates is typically QB + RB/TE + one pass-catcher, or QB + one WR with more bring-back.

### Q3. Punt granularity (FLEX-5, non-DST, FLEX price; `ls_cd_n_*.csv`, `ls_cd_cheapest.csv`)

Cheapest non-DST FLEX in the lineup:

| Cheapest tier | Field SE / big | Top-1% share SE / big | Cash lift SE | Cash lift big | Return SE / big | Top-1% lift SE / big |
|---|---|---|---|---|---|---|
| ≤$500 (true min) | 7% / 11% | 7% / 11% | +0.1 | -0.1 | 1.04 / 0.98 | -0.17 / -0.07 |
| $600-1k | 7% / 7% | 4% / 6% | -1.8 [-3.8,+0.1] | **-2.6 [-4.3,-0.6]** | **0.82 / 0.83** | **-0.50 [-0.66,-0.32]** / -0.31 |
| $1.1-2k | 14% / 15% | 15% / 16% | +1.4 [-0.8,+3.6] | +1.4 [-0.9,+3.8] | 1.15 / 1.08 | +0.23 / +0.09 |
| $2.1-4k | 38% / 34% | 40% / 35% | -0.1 | -0.7 | 1.01 / 0.96 | ~0 |
| >$4k (no punt) | 35% / 32% | 34% / 32% | **-1.9 [-3.2,-0.6]** | **-1.4 [-2.8,-0.1]** | 1.00 / 0.97 | ~0 |

Count per tier:
- **Two or more ≤$500 players**: big -10.3 [-14.1,-6.0], return 0.39.
- **One ≤$500 player**: 0.0.
- **One $600-1k player**: -1.7 / -2.6, return 0.82 / 0.83.

**Direct answer:**
- Cashing lineups use a genuine min-price (≤$500) player about 8% (SE) to 12% (big) of the time, the same as the field.
- They use a $1-2k player as the cheapest piece about 15-17% of the time, slightly more than the field.
- Min-price vs $1-2k: neither hurts. $1-2k leans positive (CI touches 0). The tier that clearly hurts is **$600-1k**, a price where DK typically puts backup-level players who are neither free salary nor a real role.
- **Grades:**
  - "$600-1k FLEX is a leak": **Weak-to-Supported**. Big cash CI excludes 0, SE top-1% CI excludes 0, returns about 0.82 in both.
  - "At most one ≤$500": **Supported** in big.
  - "$1-2k value > min punt": **Weak**.
  - The source doc's "0 punts costs ~2 pts" is confirmed (-1.9 / -1.4 here).

### Q4. Which side holds the 4 or 5 (`ls_cd_split_side.csv`, `ls_cd_split_side_fav.csv`, `ls_cd_split_side_by_cpt.csv`)
"CPT heavy" means the CPT's team is the 4 or 5 side; "CPT light" means the CPT is on the 2 or 1 side.

| Split / side | Field SE / big | Cash lift SE | Cash lift big | Return SE / big |
|---|---|---|---|---|
| 4-2, CPT heavy | 36% / 34% | **-1.6 [-2.4,-0.8]** | **-1.4 [-2.1,-0.6]** | 0.94 / 0.92 |
| 4-2, CPT light | 10% / 12% | -0.1 | -0.9 | 1.04 / 0.99 |
| 5-1, CPT heavy (5 on CPT's team) | 15% / 16% | -1.4 | -1.2 | 0.97 / 0.95 |
| 5-1, CPT light (CPT alone vs 5 opp) | 1% / 2% | -1.6 | -1.2 | 0.94 / 0.91 |
| 3-3 | 38% / 37% | +1.1 | +0.6 | 1.04 / 1.04 |

- **Who holds the heavy side.** The CPT's team is the heavy side 78% of the time in 4-2 and 93% in 5-1. The heavy side is the favourite about 2/3 of the time.
- **Heavy side on the underdog vs the favourite (4-2, CPT heavy):**
  - Underdog: SE return 1.07, top-1% lift **+0.61 [+0.09,+1.19]**.
  - Favourite: 0.99 / -0.02.
  - Big is in the same direction (+0.20 vs -0.08, CI spans 0).
  - Grade: **Weak** (a contrarian-stack signal, SE only).
- **5-1 onto the CPT's team vs onto the opponent: no reliable difference.** Both are about -1.2 to -1.6 cash with CIs spanning 0. The "CPT light" 5-1 is only 1-2% of the field.
  Exception by CPT: TE CPT alone vs 5 opponents is -6.6 [-11.3,-1.3] in big, but only 1% of TE-CPT lineups. WR CPT 4-2 heavy is -3.4 / -3.3 (CIs exclude 0), which is the Q2 WR-stack penalty again.
- **Grade:** 4-2 with the CPT on the heavy side is a mild **Supported** negative (-1.5, 3/4 seasons in the source doc). 3-3 is the best split on average (Weak). Rule 7's weakening stands.

### Q5. Winning templates (`ls_cd_template.csv`, `ls_cd_template_concentration.csv`)
Template = CPT pos | primary partner pos | CPT-team split | punts ≤$4k (0 / 1 / 2+) | K/DST in FLEX.

| CPT | Most common top-1% template | Top-1% share SE / big | Cash share SE / big | Field share SE / big | Templates to cover 50% of top-1% SE / big |
|---|---|---|---|---|---|
| QB | QB + WR, 3-3, 1 punt, no K/DST | 7.6% / 6.1% | 6.1% / 5.1% | 6.3% / 5.3% | 14 / 19 |
| RB | RB + QB, 3-3, 1 punt, no K/DST | 6.9% / 7.2% | 5.0% / 5.3% | 3.9% / 4.5% | 18 / 16 |
| WR | WR + QB, 3-3, 1 punt, no K/DST | 8.4% / 9.1% | 8.7% / 7.5% | 7.8% / 6.8% | 16 / 17 |
| TE | TE + QB (SE) / TE + RB (big), 4-2, 1 punt | 4.7% / 5.4% | 4.4% / 3.0% | 5.9% / 2.4% | 12 / 11 |

- **Winning shapes are diverse.** No template covers more than ~9% of top-1% lineups for its CPT position, and the most common winning template is roughly as common in the field.
- The recurring motif is **3-3, one punt, no K/DST in FLEX, with the QB in the lineup** (as CPT or as the partner). That is a style, not a single recognizable build.
- The only template notably over-represented in top-1% vs the field is RB CPT + his QB, 3-3, 1 punt (6.9-7.2% vs 3.9-4.5% field), which is consistent with Q1.
- **Grade:** "there is one dominant winning Showdown shape": **Not supported**. Rules should be constraints and avoid-lists (Q1-Q4), not a template to force.

### Q1b. QB-CPT partner position with projection/salary controls (`lineup_study_qb_partner_ctrl.py`, `ls_cd_qb_partner_ctrl.csv`)
Setup:
- QB-CPT entries only, with the partner defined as before (highest-salary same-team FLEX; WR, RB or TE).
- Per-contest OLS of cash (and capped return) on RB and TE dummies, with WR as the base.
- Contests are dropped if the FC projection is broken or if there are fewer than 30 RB- or TE-partner entries. That leaves n = 48 SE / 57 big.
- Controls are added in steps: M2 adds lineup FC projection; M3 adds partner FC projection and salary left; M4 adds partner salary.
- Estimates are in cash pts [90% CI].

| Model | RB vs WR, SE | TE vs WR, SE | RB vs WR, big | TE vs WR, big |
|---|---|---|---|---|
| M1 raw | +9.3 [+4.7,+13.8] | +9.8 [+3.6,+16.1] | +6.6 [+3.2,+10.0] | +8.5 [+3.8,+13.1] |
| M2 + lineup proj | +8.3 [+3.7,+12.6] | +10.6 [+4.3,+16.7] | +6.0 [+2.5,+9.5] | +8.8 [+4.4,+13.3] |
| M3 + partner proj + salary left | +9.1 [+3.6,+14.9] | +11.3 [+4.7,+17.9] | +5.8 [+1.9,+9.7] | **+10.0 [+5.4,+14.7]** |
| M4 + partner salary | +5.1 [-1.5,+11.8] | +8.5 [+0.2,+17.0] | +4.9 [0.0,+9.7] | **+8.5 [+3.7,+13.9]** |

Other checks:
- **Seasons.** Under M3, 3-4 of 4 seasons are positive (the SE exceptions are in 2022).
- **Capped return** tracks cash. In big under M4: RB +0.26 [+0.03,+0.49], TE +0.46 [+0.19,+0.76].
- **Matched comparison.** Within partner-projection quintiles (contest mean across quintiles):
  - RB vs WR: +12.7 SE / +5.7 big, CIs exclude 0.
  - TE vs WR: +4.9 SE (CI spans 0) / +5.6 big [+1.2,+9.6].
  - The per-quintile cells are thin (TE partners are rare in the top quintiles).
- **The partner's FC projection itself carries ~0 cash per SD** once position is in the model (-1.1 SE, +0.05 big). So the effect is not "the better projected partner".

**Reading:**
- The edge does **not** go away once the partner's projection is controlled. It is not "roster whoever projects best".
- It shrinks by roughly a third to a half once the partner's *salary* is controlled (M4). So part of the edge is that RB/TE partners are cheaper than WR1s at equal projection, and the saved salary goes elsewhere.
- The remainder is a position/correlation effect.

**Grades:**
- TE partner over WR: **Supported** (survives every control in big; SE CI just excludes 0 under M4).
- RB partner over WR: **Supported in big, Weak in SE** (under M4 the SE CI spans 0).
- Still observational, and builder skill is not controlled.

## Candidate optimizer rules (for Greg to decide; none implemented)

| Candidate | Evidence | Grade |
|---|---|---|
| Keep lambda 0; do not add a chalk tilt using our ownership model | Task 1: gap and slope ~0 with modeled ownership | Supported (as "no tilt") |
| Pass-catcher CPT: require his QB; forbid a same-team WR/TE as the only partner | Q1 (-7.6 / -7.7 cash) + source doc | Supported |
| QB CPT: allow and encourage RB/TE partners; do not force QB + WR1 | Q1 + Q1b: survives the projection control; ~1/3-1/2 of it is a salary effect | Supported (TE; RB in big), Weak (RB in SE) |
| QB CPT: cap same-team FLEX at 2-3, prefer 1-2 | Q2 | Weak-to-Supported |
| Avoid $600-1k FLEX; max one ≤$500 FLEX | Q3 | Weak-to-Supported / Supported |
| Penalize WR CPT + 3-4 same-team FLEX | Q2/Q4 (-3 cash) | Weak-to-Supported |
| Prefer the underdog as the heavy side in SE 4-2 | Q4 | Weak |

## Open
- Task 1 needs a better pre-lock ownership source before chalk tilt can be re-tested. The bar is lineup-level corr well above 0.56 with realized ownership.
- 2026 wk1-2 replay fails at engine cold start. That is minor, but it means the replay cannot cover week-1 games.
- Q1's RB/TE-partner projection control: done in Q1b.
