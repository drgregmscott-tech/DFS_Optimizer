# Showdown lineup-study findings: REAL fields, 142 DK Showdown contests, 2022-2026 (2026-09-28)

Source: FantasyCruncher Lineup Study exports in `data/fc_history/lineup_study/*_SHOWDOWN_*.json.gz` (subscription data, gitignored; **do not commit**).
Scripts (no FC data inside): `analysis/showdown_history/lineup_study_build.py` (parse + QA), `lineup_study_analysis.py` (feature tables),
`lineup_study_headline.py` (ownership test within optimizer-quality lineups). Outputs: `data/fc_history/derived/showdown/ls_*.csv`,
`ls_analysis_out.txt` (gitignored). The per-entry cache `data/fc_history/lineup_study/_sd_entries_cache.parquet` is raw-derived and stays gitignored.
This doc has aggregate statistics only.

This is the real-field replacement for §6-§8 of `HANDOFF_showdown_history_findings_2026-09-26.md` (which scored lineups against a
*simulated* maximum-entropy field). Section and rule numbering follow that doc and `SHOWDOWN_RULES.md`.

```
python analysis/showdown_history/lineup_study_build.py      # ~15 min, 14.9M entries -> cache + ls_qa.csv
python analysis/showdown_history/lineup_study_analysis.py   # ~30 min, needs ~16 GB RAM
cd analysis/showdown_history && python lineup_study_headline.py
```

## TL;DR (headline)
- **Leverage vs chalk tilt, real top-heavy GPP (the "big" 150-max contests): leverage loses, and chalk does NOT cost you.**
  Within each contest, the most-owned fifth of lineups (summed realized ownership) returned **1.21x** the field-average payout
  (capped at the 99.9th-pct prize; 90% CI 1.10-1.34), and the least-owned fifth returned **0.78x** [0.69-0.87]. That holds in all 4 full seasons.
  It survives controls:
  - Controlling for FC projection (per-contest OLS): +0.13 return per SD of ownership [+0.05,+0.20], positive in 4/4 seasons.
  - Only "optimizer-quality" lineups (≤$500 salary left and top-40% FC projection in that contest): top ownership fifth 1.22x [1.02-1.43], bottom 0.84x [0.69-1.00], n = 31 contests.
  - **Uncapped** return, which includes 1st-place prizes, is flat across ownership among quality lineups (top fifth 1.11x [0.91-1.34], bottom 1.09x).
    So chalk does not give up tail equity in the real field, but it does not clearly add any at the very top either.
- **Single-entry (SE Huddle, ~12-36k entries) is different.** Ownership raises cash rate a little (+2.2 pts for the top fifth, CI touches 0), but not return.
  Among quality SE lineups the *least*-owned fifth had the highest uncapped return (1.55x [1.20-1.95] vs 0.90x for the most-owned),
  driven by top prizes (n = 24 contests, capped returns overlap). **Weak** hint that differentiation pays at the top of SE. It is not a reason to add a leverage penalty.
- **Net for the optimizer:** keep lambda 0 (Rule 10 confirmed). Do not add a chalk tilt for SE. For large-field GPP, a mild chalk tilt is
  Weak-to-Supported on capped return, but it is not supported on uncapped return.
- **Biggest new construction finding.** A pass-catcher captain *without* his own QB in the FLEX loses consistently.
  - WR CPT, no own QB: cash -4.2 SE / -3.7 big, return 0.70x / 0.76x.
  - TE CPT, no own QB: cash -5.4 / -5.1, return 0.62x / 0.67x.
  - Negative in 4/4 seasons for TE and 7 of 8 season x contest cells for WR.
  - With the QB, the same captains are neutral to slightly positive.
- **Rule verdicts that change:**
  - Rule 7 (avoid 5-1) weakens: in the real field 5-1 is no worse than 4-2.
  - Rule 5 (two kickers) weakens from Supported to Weak.
  - Rule 3 (no DST captain) is confirmed on real money.
  - Rule 8 (<5%-owned CPT worst) is confirmed in big GPPs. In SE the #1 chalk captain under-returns and 5-15% is the sweet spot.

## 1. Data and quality
- **142 contests = 71 SE + 71 big, 14,885,437 entries.** 2022 wk1-18, 2023 wk1-18, 2024 wk4-18, 2025 wk1-18, and 2026 wk1-2.
  - SE: DK "Huddle [Single Entry]", $5, 9.5k-36k entrants.
  - Big: mostly the $0.50 150-max "mini-MAX" (119-238k entrants). There are also 7 $10-$15 Millionaires and 5 $3 20-max Play-Action contests.
  - 2024 wk1-3 are not on FC.
  - Most weeks have the same game for SE and big. A few do not (2022 wk7/9, 2023 wk7/9/10, 2025 wk11/13/15, 2026 wk1).
- **Complete fields; no row cap.** Row counts equal `total_entrants` on every contest except one, which is short by 3. The ~25k-row cap in the extraction memory applies to classic 20-max contests only.
  0.2-0.9% of rows per contest have an empty or partial lineup and were dropped.
- **Schema (verified, not assumed).** Rows have the fields `[rank, entry_id, user, points, cash_amt (cents), player_ids]`. `player_ids[0]` is the CPT, and the other five are FLEX.
  Confirmed by least squares: points = 1.5·CPT + ΣFLEX fits with p99 residual 0.000 on all 142 contests. Assuming instead that slot 1 is the CPT gives 3-27 pts residual.
- **FC's per-player `fantasy_points` are wrong on some slates.** For example, on 2022wk12 SE the FC points sum to about 53 for a lineup that scored 149. Player scores were re-solved from entry points (exact).
- **Payouts.** `cash_amt` is all zero on 2025 wk15-17 (6 contests). There, payouts were rebuilt from the prize table with tie-splitting.
  Where both exist, the rebuild matches `cash_amt` on ≥97% of rows (≥99.5% on all but one).
- **Ownership = realized rostership computed from the rows themselves.** This is the real field and exact. It is also post-lock, so pre-lock projected ownership will be noisier (same caveat as the history doc).
- **Missing metadata on a few players.** Some players have only `{cnt, own}`. Positions and teams were filled from other files.
  Salaries were recovered from the $50k-cap bound. That method reproduces known salaries 42-100% of the time (per-contest check), so salary-based features on those ~25 contests carry a little noise.
  Team is unknown on ~1% of entries (split "?"), and those are excluded from the split/stack tables.
- **FC projections are unusable on a few slates.** These are 2023wk4 (constant) and a handful with near-zero spread. Those contests are excluded from the projection-controlled tests (63 SE / 62 big remain, fewer in the quality subset).

## 2. Method
- Every metric is computed **within a contest** and then averaged with **equal weight per contest**. 90% CIs come from bootstrapping over contests.
  A feature level needs ≥30 entries in a contest to count there.
- Metrics:
  - **Cash lift**: cash rate minus the contest cash rate, in points. Base rates: SE 23.0%, big 21.2%.
  - **Return (capped)**: mean payout / contest mean payout, with each payout capped at that contest's 99.9th-pct prize (1.00 = average entry, rake-free).
  - **Return (uncapped)** is also computed. It is dominated by a handful of 1st-place prizes per contest.
  - **Top-1% lift.**
- **Grading** (same bar as the history doc):
  - **Supported**: the CI excludes 0 and the sign holds in at least 3 of 4 seasons (2022-25), in both contest types unless stated.
  - **Weak**: right direction, but the CI touches 0 or it holds in only one cut.
  - **Not supported**: null or wrong sign.
- **The main limitation is that this is observational, not a strategy backtest.** Entries that captain a DST, leave $2k unspent or build a unique lineup are also, on average,
  worse players' lineups, so feature lifts mix "the shape is bad" with "people who build this shape are bad". The headline test addresses this with
  the projection control and the optimizer-quality subset. The other rows do not, so treat them as "what cashing real entries look like".

## 3. Real-field shape results (cash lift pts [90% CI]; capped return; n = 71 contests per type)

| Feature | SE cash lift | SE return | Big cash lift | Big return | Seasons same sign (SE/big) |
|---|---|---|---|---|---|
| CPT QB | **+2.9 [+1.0,+4.8]** | 1.08 | +1.1 [-0.3,+2.7] | 1.00 | 3/4, 3/4 |
| CPT RB | +0.6 | 1.07 | +0.8 | 1.12 | mixed |
| CPT WR | -1.6 [-3.6,+0.4] | 0.95 | **-1.9 [-3.6,-0.1]** | 0.90 | 4/4, 3/4 |
| CPT TE | -0.2 | 1.01 | +0.6 | 1.05 | mixed (2025 +3.5/+6.2) |
| CPT K | -1.8 [-4.5,+1.0] | 0.86 | -1.8 [-4.1,+0.6] | 0.86 | 4/4, 3/4 |
| CPT DST | **-4.5 [-7.8,-1.2]** | 0.91 | **-4.0 [-7.1,-0.8]** | 0.83 | 4/4, 4/4 |
| WR CPT + own QB / no own QB | -0.4 / **-4.2 [-6.2,-2.1]** | 1.07 / **0.70** | -1.3 / **-3.7 [-5.7,-1.6]** | 0.95 / **0.76** | no-QB: 4/4, 3/4 |
| TE CPT + own QB / no own QB | +1.5 / **-5.4 [-8.3,-2.2]** | 1.20 / **0.62** | +2.1 / **-5.1 [-7.9,-2.3]** | 1.17 / **0.67** | no-QB: 4/4, 4/4 |
| RB CPT + own QB / no own QB | **+2.9 [+0.2,+5.7]** / -1.4 | 1.14 / 1.18 | +2.2 / -1.5 | 1.16 / 1.20 | mixed |
| QB CPT + ≥1 own WR/TE / naked | +2.8 / +2.3 | 1.08 / 1.05 | +1.0 / +1.8 | 1.00 / 0.98 | naked is 2% of the field |
| Split 3-3 | +0.4 | 0.99 | -0.6 | 0.97 | mixed |
| Split 4-2 | **-1.2 [-1.9,-0.5]** | 0.96 | **-1.2 [-1.9,-0.5]** | 0.94 | 3/4, 3/4 |
| Split 5-1 | -1.3 [-3.3,+0.9] | 0.97 | -0.9 [-2.7,+0.9] | 0.95 | mixed (2022 +) |
| FLEX same team as CPT: 0-1 / 2 / 3 / 4 | ~0 / +0.9 / **-1.3** / -1.3 | | +1.3 / 0.1 / **-0.9** / -1.0 | | 3 same-team: 3/4 |
| 0 / 1 / 2 kickers | -0.3 / -0.1 / -1.5 [-4.6,+1.9] | 0.99 / 1.00 / 1.00 | -0.2 / +0.1 / -0.9 [-3.5,+1.7] | 1.01 / 0.98 / 0.94 | 2 K: 3/4, 3/4 |
| No DST | **+1.3 [+0.0,+2.6]** | 1.06 | +0.4 | 1.01 | 3/4, 2/4 |
| Cheap DST (when priced differently) | +0.5 | 1.15 | +0.4 | 1.03 | mixed |
| Expensive DST | -2.4 [-4.8,+0.2] | 0.86 | -2.0 [-4.6,+0.9] | 0.91 | 4/4, 3/4 |
| Both DSTs | -3.7 [-7.4,+0.4] | 1.04 | -2.4 | 0.96 | 3% of the field |
| CPT own <5% | -1.7 [-3.4,+0.2] | 0.96 | **-3.0 [-4.3,-1.7]** | **0.86** | 4/4, 4/4 |
| CPT own 5-15% | +1.7 [-0.1,+3.5] | **1.14 [1.04,1.24]** | +0.3 | 1.03 | 4/4, 2/4 |
| CPT own ≥15% | -0.2 | **0.89 [0.80,0.99]** | **+2.6 [+0.7,+4.6]** | 1.10 | mixed, 3/4 |
| #1 chalk CPT | 0.0; **top-1% -0.37 [-0.54,-0.19]** | 0.89 | +2.7 [-0.2,+5.6] | 1.09 | mixed, 4/4 |
| Salary left 0-500 / 500-1k / 1-2k / 2k+ | **+1.2 / -0.4 / -2.5 / -7.6** | 1.08 / 0.93 / 0.86 / 0.64 | **+1.6 / +0.5 / -0.9 / -6.0** | 1.11 / 1.01 / 0.91 / 0.68 | 4/4 |
| Punts (≤$4k FLEX price, non-DST) 0 / 1 / 2 / 3+ | **-2.3** / +1.0 / +1.1 / -2.9 | 1.00 / 1.04 / 1.05 / 0.91 | -1.5 / +0.7 / -0.3 / **-14.7** | 0.95 / 1.05 / 0.93 / 0.30 | 0 punts: 4/4, 3/4 |
| Studs (≥$7k FLEX price) ≤2 / 3+ | **-7.5** / +0.2 | 0.66 / 1.01 | **-7.3** / +0.4 | 0.66 / 1.02 | 95% of the field has 3+ |
| CPT from favorite / dog | 0.0 / +0.2 | 1.00 / 1.04 | -0.3 / +0.3 | 0.99 / 1.02 | null |
| Exact duplicates: unique / 2-5 / 6-20 / 21+ | **-5.7 / -2.2** / -0.4 / **+3.7** | 0.79 / 0.93 / 1.01 / 1.10 | **-10.0 / -5.8 / -2.6 / +2.9** | 0.49 / 0.70 / 0.87 / 1.15 | 4/4 |

Notes:
- Stud/punt definitions copy the WK3 classic Phase 2 exactly (non-DST, FLEX price). In Showdown, $7k is mid-priced (95% of lineups have 3+ "studs"), so the stud metric only flags broken builds.
  The punt result matches classic in direction: 0 punts costs about 2 pts. Unlike classic, 3+ punts is a disaster in big GPPs.
- **Duplication is the real-field version of the §6 "chalk looks less duplicated" worry, and it cuts the other way.** Lineups shared with 21+ others cash more and return more.
  Unique lineups return about half the field average in big GPPs, and 0.59x even among optimizer-quality lineups. Being unique mostly means building something nobody else found worth building.
  Among quality SE lineups, unique ones have an uncapped return of 1.48 [0.82, 2.37]. That is too noisy to use.

## 4. Headline test in detail (ownership quintile within contest; `ls_headline_quality.csv`, `ls_own_slope_by_contest.csv`)

| Cut | Contests | Q1 (least owned) return | Q5 (most owned) return | Q5 uncapped | Q1 uncapped | Own slope on return, projection-controlled |
|---|---|---|---|---|---|---|
| Big, all entries | 71 | 0.78 [0.69,0.87] | **1.21 [1.10,1.34]** | - | - | **+0.13 [+0.05,+0.20]**, 40/62 contests +, 4/4 seasons + |
| Big, ≤$500 left | 43 | 0.89 | 1.16 [0.98,1.35] | 0.98 | 1.21 | - |
| Big, quality (≤$500 left + top-40% proj) | 31 | 0.84 [0.69,1.00] | **1.22 [1.02,1.43]** | 1.11 [0.91,1.34] | 1.09 | - |
| SE, all entries | 71 | 1.03 | 0.99 | - | - | -0.04 [-0.14,+0.06], 28/56 +, mixed |
| SE, quality | 24 | 1.16 [0.91,1.42] | 1.03 [0.78,1.28] | 0.90 [0.67,1.14] | **1.55 [1.20,1.95]** | - |

- Points: ownership predicts points even after controlling for FC projection. That is +1.9 pts per SD in big and +0.9 in SE, holding in 3-4 of 4 seasons.
  This is the §5 "ownership carries information" finding, now on real lineups: the crowd knows something FC's projection doesn't.
- Top-1% rate vs ownership: slightly positive in big (+0.15 pts per SD, CI excludes 0) and null in SE.
- **Reading.** In a real 150-max GPP the field is sharp enough that more-owned lineups are better lineups, and the duplication penalty on prize splitting does not offset that on average.
  The simulated-field caveat ("might not hold in a top-heavy GPP") **does not bite**. SE Huddle fields are softer and flatter: there, ownership buys cash rate but not return, and at the top the low-owned quality lineups did better.
  That last part rests on 24 contests and uncapped prizes, so it is Weak.

## 5. Rule-by-rule vs current `SHOWDOWN_RULES.md`

| Rule | Real-field verdict | Basis |
|---|---|---|
| 1. Highest projection wins | **Supported (confirmed).** Top FC-projection fifth: cash +5.1 SE / +3.1 big, 4/4 seasons. | §4 proj_q |
| 2. RB/WR CPT not supported as restriction | **Confirmed (Not supported as a restriction).** QB CPT is the best position in SE (+2.9, CI excludes 0) and WR the worst skill CPT (-1.6/-1.9). Refinement: a WR/TE CPT *without his own QB* is Supported-bad (see new rule). | §3 |
| 3. No K/DST CPT; TE fine | **DST: Supported** (-4.5/-4.0, 8/8 season-cells). **K: Weak** (-1.8, CI touches 0; 2% of field). **TE: confirmed fine**, but only with his QB. | §3 |
| 4. Cheap fill must be a real player | **Silent/consistent.** Role can't be seen here. 1-2 punts are fine, 0 punts costs about 2 pts, 3+ punts is -14.7 in big. | §3 |
| 5. At most one K | **Weakened to Weak.** 2 K is -1.5 / -0.9 cash, CIs span 0, return ~1.0 SE. The simulated -7.7 does not show up in the real field. Keep as a preference; it is harmless. | §3 |
| 6. DST lean cheap or skip | **Weak (confirmed direction).** No DST +1.3 SE [0.0,+2.6]. Expensive DST -2.4/-2.0 (4/4, 3/4 seasons), return 0.86/0.91. Cheap DST ~0. | §3 |
| 7. Avoid forced 5-1 | **Weakened (Not supported as stated).** Real 5-1 is -1.3/-0.9 (CI spans 0), the same as 4-2 (-1.2, CI excludes 0). 3-3 is ~0. Heavy same-team stacks (3-4 FLEX with the CPT) are mildly negative across the board, so 5-1 has no special penalty. The simulated -4.5 was a field artifact. | §3 |
| 8. Chalk CPT fine; avoid <5% | **Big GPP: Supported** (<5% CPT -3.0 [-4.3,-1.7], 4/4; ≥15% +2.6). **SE: Weak, with a twist.** <5% is -1.7 (CI touches 0), the #1 chalk CPT under-returns (0.89, top-1% lift -0.37, CI excludes 0), and 5-15% is best (return 1.14 [1.04,1.24]). | §3 |
| 9. Top projection over-projected | **Orthogonal** (player-level; not testable without per-player projection error). | - |
| 10. Lambda 0 | **Confirmed.** No real-field cut shows a leverage term paying on capped return. In big GPPs ownership is positive after the projection control. SE low-own upside is Weak and uncapped only. | §4 |
| **New: pass-catcher CPT needs his QB** | **Supported.** WR CPT with no own QB: -4.2 / -3.7 cash, 0.70x / 0.76x return. TE CPT with no own QB: -5.4 / -5.1, 0.62x / 0.67x. Both CIs exclude 0 and most seasons agree. Not projection-controlled, but it is large and consistent in both contest types. | §3 |
| **New: spend the salary** | **Supported.** $2k+ left costs -7.6 / -6.0 cash (4/4). ≤$500 left is best. | §3 |

## 6. Cross-reference to the simulated-field docs
- **History doc §6 "leverage loses, chalk tilt wins".**
  - *Leverage loses*: **settled, Supported** on real fields in both contest types (Q1 ownership is the worst or near-worst bucket; there is no positive leverage slope).
  - *Chalk tilt wins*: **strengthened for big GPPs on capped return** (it holds with the projection control and in the quality subset). It is not supported on uncapped return, and not supported for SE.
  - The §6 caveat ("max-entropy understates duplication, so chalk may be over-rated") is **answered**. Real duplication did not erase the chalk edge in 150-max fields.
- **§6 CPT restricted to RB/WR (-1.9, 2025 -4.6).** Consistent: real WR CPT is the weakest skill captain and QB CPT the strongest in SE. **Strengthened.**
- **§6 forced 5-1 (-4.5) and "max 4 per team" (+3.8).** **Weakened.** The real field shows no 5-1-specific penalty. The `--max-team-players 4` candidate flag loses its evidence base.
- **§6 exactly 2 K (-7.7).** **Weakened** to about -1 pt, CI spans 0.
- **§6 CPT own <5% (-6.3) and fade chalk CPT (-1.8).** <5%: **confirmed in big, Weak in SE.** Fade chalk CPT: **contradicted in SE** (the chalk CPT under-returns there) and **confirmed in big**.
- **§6 no K/DST/TE CPT (+0.6).** DST part **strengthened**; TE part refined (fine only with his QB).
- **§3 hindsight "field over-uses DST CPT (7.8%)".** Real field shares: DST CPT 7% SE / 5% big, and they lose. **Confirmed.**
- **Ownership-refit doc §5** (leverage ≤0 with every ownership source, lambda 0). **Confirmed with real lineups**, and it is a stronger statement now: ownership has a *positive* projection-controlled effect in big GPPs.
  Its conclusion that better ownership prediction matters for display and pivots, not the optimizer objective, still stands. If anything, pre-lock ownership now has some value as a mild *tiebreak toward* chalk in large GPPs. That is untested with projected (not realized) ownership.
- **History doc §5 "ownership adds ~4% SSE beyond FC Proj".** **Strengthened** at lineup level: +0.9 to +1.9 pts per SD of ownership after the projection control.

## 7. Caveats
- Observational. Shape lifts mix the effect of the shape with the skill of the people who build it (§2). Only §4 has projection and quality controls.
- Ownership is realized, not projected. A pre-lock version would be noisier, so the chalk effect is an upper bound.
- FC projection is the control, and it is a weak one (QB corr 0.07 per the history doc). Some "ownership" signal may be projection information that FC missed.
- Big contests are mostly $0.50 150-max mini-MAX with multi-entry sharks. Results may differ in $20+ single-entry-max or milly-maker structures. Entries by the same user are correlated, which the contest-level bootstrap handles only partly.
- 2026 (2 weeks) is included in the pooled numbers but not in the season-sign counts.

## 8. Proposed SHOWDOWN_RULES.md edits (for Greg to decide)
- Evidence base: add "plus 142 real DK Showdown contests 2022-26 (14.9M lineups; see HANDOFF_showdown_lineupstudy_findings_2026-09-28.md)".
- New Supported rule: "WR/TE captain → roster his QB in the FLEX." Candidate optimizer flag: pair a pass-catcher CPT with his QB.
- Rule 3: DST CPT now Supported on real money. K CPT Weak.
- Rule 5: downgrade to Weak (keep as a preference).
- Rule 7: drop "avoid forced 5-1" as Supported. It becomes "no split is clearly best; heavy one-team stacks are mildly negative." Drop the `--max-team-players 4` candidate.
- Rule 8: big GPP: keep "avoid <5% CPT; chalk CPT fine". SE: "5-15% CPT is the sweet spot; the #1 chalk CPT under-returns" (Weak).
- Rule 10: keep lambda 0 for SE. For large-field GPP, a small positive chalk tilt is Weak-to-Supported on capped return. Test it with *projected* ownership before any change.

## 9. Open questions
- Re-run §4 with our pre-lock *projected* ownership instead of realized ownership, to check whether the big-GPP chalk edge survives a realistic signal.
- Split big contests by structure (150-max mini-MAX vs Millionaire vs 20-max). n is currently too small outside mini-MAX.
- Aside (not analysed): the classic lineup-study files have the same schema (9 slots) and are still untouched. The §3 checklist item remains open.
