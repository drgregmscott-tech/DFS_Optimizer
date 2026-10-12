# RB + WR/TE same team, team's own QB out: is it negative correlation?

**Question (owner's premise, WK5_POSTMORTEM_CHECKLIST item 3):** when a lineup has an RB and a WR/TE from the same team
and that team's own starting QB is out (Swift + Burden/Raymond with Caleb Williams out), do the two scores move in
opposite directions (run-heavy script: RB up, WR down)? Or are they just two good plays that share a team?

**Answer: just two plays sharing a team.** There is no extra negative correlation when the QB is out. The backup-QB
week lowers both players' scores (the "both score less" case, not "one up, one down"), and salary already prices most of
that drop.

**Verdict: wrong-direction-drop. No lint rule.** Close the parking-lot item.

## Data and method
- Real DK points, 2014-2021 regular season (`data/rotoguru_actuals_dk_*.csv`), joined to nflverse games for the actual
  starting QB, final score, spread and total (`data/nflverse_games.csv`).
- Primary QB is the team-season's most frequent starter. QB-out is any week someone else started.
- Pairs are picked by pre-game salary, never by actual points. Each team-week's lead RB (top RB salary) is paired with
  its top-2 WR/TE by salary, with all players at $3,500 or more. A second check uses every pair of RB at $4,000+ and
  WR/TE at $3,500+.
- "resid r" is the correlation of each player's points above or below what their salary implies (fit per position per
  season). This strips out "good team, good players" level effects, which is the co-movement a lineup cares about.
- 95% confidence intervals come from bootstrapping team-seasons, so pairs from the same team-season are not counted as
  independent.

## Sample
- 4,128 team-weeks. **575 QB-out team-weeks (13.9%)**; 478 of them where the primary QB started at least 8 games
  that season.
- Lead universe: 7,779 pairs, **1,047 QB-out pairs** across 555 team-weeks. All-pairs universe: 23,160 pairs, 2,863
  QB-out.

## Core result (lead RB x top-2 WR/TE)
| | n | raw r | resid r (95% CI) |
|---|---|---|---|
| QB out | 1,047 | -0.032 | **-0.022** (-0.078 to +0.035) |
| QB in | 6,732 | -0.007 | **-0.034** (-0.057 to -0.011) |
| QB out, strict (primary started at least 8) | 879 | -0.049 | -0.046 |
| **Out minus in** | | | **+0.012** (-0.051 to +0.074) |

The all-pairs universe gives the same picture: out -0.018, in -0.031, difference CI -0.021 to +0.044. For scale,
same-team QB vs top WR/TE in this data is **+0.44**, and QB vs lead RB is +0.10. A same-team RB/WR correlation of about
-0.03 is essentially zero, and it is the same whether the QB plays or not.

### Robustness checks (all flat)
- Players who scored exactly zero (possible inactives) removed: out -0.012, in -0.038.
- Rank (Spearman) correlation instead of Pearson: out -0.012, in -0.020.
- WR only: out -0.013, in -0.029. TE only: out -0.083 (n=129), in -0.069.
- Holding team points constant (partial correlation): out -0.107, in -0.115. Once team scoring is held fixed, RB and WR
  do trade off for the same points, but equally whether or not the QB plays.
- Game script by Vegas spread and by actual result: no QB-out-specific pattern. The most negative bucket is "team won"
  (out -0.107, in -0.078), and that holds with the QB in too. Backup-QB teams are mostly underdogs (633 of 1,047
  pairs), where r is -0.003.

### Joint outcomes (boom = 4x value or better, bust = under 2x)
Shown as observed rate vs the rate if the two scores were independent.
| | both boom | RB boom + WR bust | RB bust + WR boom | both bust |
|---|---|---|---|---|
| QB out | 1.7% vs 1.8% (0.97x) | 7.8% vs 8.3% (0.95x) | 6.6% vs 5.7% (1.16x) | 25.9% vs 26.3% |
| QB in | 2.0% vs 2.4% (0.83x) | 8.0% vs 7.6% (1.05x) | 6.4% vs 6.4% | 20.2% vs 20.4% |

The claimed mechanism is "RB booms, WR busts". It does **not** happen more often with the QB out (0.95x, which is
less than independence). The joint "both boom" penalty is actually smaller with the QB out (0.97x) than with him in
(0.83x).

### Season by season (resid r, QB out / QB in, lead universe)
| Season | QB out | QB in |
|---|---|---|
| 2014 | +0.016 | -0.029 |
| 2015 | -0.147 | +0.010 |
| 2016 | +0.033 | -0.069 |
| 2017 | +0.062 | -0.029 |
| 2018 | -0.071 | -0.054 |
| 2019 | -0.050 | -0.058 |
| 2020 | +0.070 | -0.024 |
| 2021 | -0.010 | -0.025 |

QB-out is more negative than QB-in in only 3 of 8 seasons. Only 2015 shows anything, and that is noise at n of about
125.

## What QB-out actually does: a level drop, not a split
- Mean actual points with the QB out vs in: **RB 12.9 vs 14.7, WR/TE 11.1 vs 13.5**. Team points 18.9 vs 23.6; average
  margin -5.3 vs +0.9.
- Salary already drops (RB -$310, WR/TE -$535), so above or below salary-implied points shifts only about -0.7 for
  each player.
- The RB's share of the pair's points rises slightly (52.7% to 54.5%) as the pair's total falls from 28.3 to 24.0. This
  is a small tilt toward the RB inside a smaller pie, not the RB gaining while the WR loses.

## Wk5 CHI example
The 2026 Wk5 CHI@GB game has no score or starting-QB row in `nflverse_games.csv` yet, so it can't be checked here. The
historical answer covers it anyway: Swift + Burden/Raymond with Brissett-era CHI is the same kind of pair as the 1,047
QB-out pairs above.

## Recommendation
- **No change to `scripts/construction_lint.py`.** Don't add `CL_rb_pc_pair_no_qb`, and don't extend `CL_pc_pair_no_qb`
  to RBs. Same-team RB + WR/TE with the QB out carries no correlation penalty beyond the near-zero one any same-team RB/WR
  pair already has.
- The real QB-out cost is that both players score about 2 points less in raw terms. That belongs in projections, not
  in a lineup rule. Salary absorbs most of it, so it matters only if our projections do not lower a team's RB and WR/TE
  when the backup starts. Possible parking-lot check: does the injury pipeline cut same-team skill projections on a QB
  OUT? Not tested here.

## Files
- `rb_wr_no_qb_corr.py`: main analysis (about 2 minutes). Writes `results_raw.txt`, `pairs_lead.csv` and
  `pairs_all.csv`.
- `robustness.py`: zero-scorer, Spearman, point-share and QB-correlation scale checks (reads `pairs_lead.csv`).
- Data is RotoGuru plus nflverse only, no FC data, so it is safe to commit if the owner wants it.
