# Showdown history findings: 49 DK Showdown slates, 2023-2025 (2026-09-26)

Source: FantasyCruncher exports in `data/fc_history/Showdowns/` (subscription data, gitignored; **do not commit**).
Scripts: `analysis/showdown_history/` (they contain no FC data). Outputs: `data/fc_history/derived/showdown/` (gitignored).
This doc has aggregate statistics only, no player-level tables.

Reproduce (about 30 min total on 7 cores):
```
python analysis/showdown_history/build.py            # tidy -> players.parquet, qa.csv
python analysis/showdown_history/slate_sim.py 7      # enumeration + fields + strategies -> slates/*.pkl
python analysis/showdown_history/agg.py              # hindsight / field / strategy tables
python analysis/showdown_history/proj_own.py         # projection + ownership (LOSO)
python analysis/showdown_history/prod_model_eval.py  # production showdown ownership model on FC inputs (slow, ILPs)
```

**How much to trust this.** There are 49 games (17 from 2023, 14 from 2024, 18 from 2025). There are no lineup-level contest
results, so every "strategy" number comes from scoring lineups against a *simulated* field. Most construction effects
below are a few percentile points, with 90% CIs about as wide as the effect. I grade evidence as
**Supported** (CI excludes zero pooled and the effect points the same way in 2025), **Weak** (right direction, CI touches zero, or it holds
in only one cut), or **Not supported** (null or wrong sign).

---
## 1. Data quality

- **Own% is realized field ownership, not FC's projection (high confidence).** Evidence: (a) CPT sums are about 99.5% and FLEX
  sums about 495% per game. (b) 46 players with FC Proj = 0 still have FLEX ownership of 5% or more, up to about 21%. A projection
  tool would not give a 0-projection player 21%, but a real field does. (c) This matches the classic FC history, which was real ownership.
- **Missing ownership mass on 7 slates.** CPT sums: 2024 SF/SEA 76.8%, 2025 MIA/BUF 74.8%, SEA/ARI 89.7%, LAR/SEA 96.9%,
  MIN/LAC 97.3%, NYJ/NE 98.3%, DAL/WAS 98.7%. FLEX sums on those slates are 427-490%. Some owned players are absent from the export,
  probably late scratches or removed rows. The simulated field renormalizes to 100/500, which spreads that mass over the remaining players.
  This is a small distortion, but on those slates the field looks less concentrated than it really was.
- **FC Proj = 0 on 34% of rows.** These are mostly min-salary depth players. Their mean actual score is 1.1, and 2.1% of them scored 10 or more (max 31).
  **QB projections carry almost no signal:** the correlation of FC Proj with actual QB score is 0.07 (n=98). They are well calibrated
  in mean but carry no ranking information across slates. Within a game only 2 QBs are compared, so this matters less than it sounds.
- Checks passed: CPT salary = 1.5x FLEX, CPT Score = 1.5x FLEX, and CPT FC Proj = 1.5x FLEX on every row. No missing Score. The junk rows
  (other teams, zero ownership) were dropped by keeping the two teams that have ownership. The `2024_DEV_NO` filename is DEN/NO.
- Positions per game: about 2 QB, 2 K, 2 DST, 7 RB, 10 WR, 6 TE. That is 1,559 player-games in total.

## 2. Method

- **Exhaustive enumeration** of every legal DK Showdown lineup per game (1 CPT at 1.5x + 5 FLEX, $50k cap, both teams, no
  duplicates). That is about 5-14M lineups per game. I pruned players with 0 ownership, 0 projection and 0 actual, which never matters.
- **Hindsight-optimal** = the lineup with the highest actual score. I also kept the top 20 by actual score.
- **Simulated field** = the maximum-entropy distribution over *all legal lineups* whose CPT and FLEX marginals match the
  realized ownership, fitted by iterative proportional fitting (max marginal error about 1 percentage point). Three priors test sensitivity:
  F0 uniform; F1 salary-use tilt (exp(0.6 per $1k used)); F2 = F1 plus a projection tilt (exp(0.15 per projected point)).
  Percentile and top-1%/top-10% are computed exactly against that weighted field, with no sampling noise.
- **Strategies** pick lineups using only FC Proj and ownership. I score both the #1 lineup and the mean of the top 20 by the objective,
  and report paired differences vs the max-projection lineup with slate-bootstrap 90% CIs.
- **Caveats on the field.**
  (1) All three fields share the same marginals, so they differ only in how players are combined. The results barely move across
  F0/F1/F2 (under 1 percentage point). **That shows insensitivity to the prior, not that the field is correct.**
  (2) A maximum-entropy field has *less* stacking and correlation than a real field. Real fields pair QB and receivers, and favorites
  with their own team, more than independence implies. So "percentile" is optimistic for chalk-correlated lineups and understates leverage. My
  4 real slates showed the field's top-1% cutoff is harder than an independent field implies.
  (3) Leverage and chalk strategies use *realized* ownership as if it were known before lock. Real projected ownership is noisier.
  (4) The top-1% outcome is 0 or 1 per slate, so at n=49 it is nearly useless (1 hit = 2%). Rely on mean percentile and top-10%.

## 3. Hindsight-optimal lineups (n=49; top-20 in brackets)

| Feature | Hindsight #1 (90% Wilson CI) | Top-20 share | Field (F1) share |
|---|---|---|---|
| CPT = WR | 39% [28-51] | 32% | 31% |
| CPT = RB | 29% [19-40] | 29% | 27% |
| CPT = QB | 18% [11-29] | 20% | 22% |
| CPT = TE | 12% [6-22] | 13% | 11% |
| CPT = K / DST | 2% / 0% | 2.6% / 2.9% | 2.3% / 7.8% |
| Split 4-2 / 3-3 / 5-1 | 63% / 27% / 10% [5-20] | 50 / 33 / 17% | 49 / 35 / 16% |
| 0 / 1 / 2 kickers | 67% / 29% / 4% | 63 / 31 / 6% | 60 / 37 / 3.5% |
| Any DST | 22% | 27% | - |
| Uses the more expensive DST | 10% | 13.5% | - |
| CPT from the favorite | 67% [56-77] | - | - |
| Min-price (≤$1k) player used | 22% | - | - |
| FC-proj-0 player used | 18% | - | - |

- By season, the hindsight CPT position is noisy: WR was 9/14 in 2024, but in 2025 it was RB 6, TE 5, WR 4, QB 3.
  **2025 TE CPT (5/18 hindsight, 24% of top-20) is a sample-size warning, not a trend.**
- Chalk CPT: the median hindsight CPT was the 4th most-owned CPT (IQR 2-8), with mean CPT ownership 10.7%. The chalk CPT was the optimal
  captain in 8/49 games (16%), close to its average ownership of about 24%. 31% of hindsight CPTs were under 5% owned.
- Hindsight CPT projection rank: median 5th (IQR 3-8), and only 33% were top-3 projected. CPT salary: 45% cost $9k or more (FLEX price),
  12% cost under $4k.
- Salary used: median $48.9k (IQR 47.8-49.6k).
- **Interpretation.** Hindsight CPT positions are close to *field* CPT ownership shares for WR, RB, QB, TE and K. The field allocates
  captains by position roughly right. **The one clear over-allocation is DST at CPT (7.8% of field vs 0/49 hindsight and 2.9% of top-20).**

## 4. Projection quality (FC Proj vs actual, rows with proj > 0, n=1,029)

| Pos | n | Bias (act - proj) | corr(proj, act) | corr(sal, act) | SD actual |
|---|---|---|---|---|---|
| QB | 98 | +0.6 | **0.07** | 0.21 | 7.9 |
| RB | 199 | -0.5 | 0.63 | 0.61 | 9.1 |
| WR | 385 | -0.7 | 0.54 | 0.56 | 9.2 |
| TE | 152 | +0.1 | 0.51 | 0.53 | 7.7 |
| K | 97 | +0.8 | 0.15 | 0.21 | 4.6 |
| DST | 98 | -0.7 | 0.24 | 0.10 | 5.2 |

- **The top projection is over-projected in Showdown.** The #1 projected player per game scored 3.1 below projection
  (SE 1.5, n=49). Ranks 2-3 were -1.0 (SE 0.9) and ranks 4+ were about 0. By year, for the top-6 skill players: 2023 +0.6, 2024 -2.5 (SE 1.1),
  2025 -0.8 (SE 0.9). The top calibration decile (proj 18.5+) averaged 20.2 actual vs 22.4 projected.
  **This is the opposite of the classic-slate "stud under-projection".** It is Weak evidence: about 2 SE, driven mostly by 2024. It may be
  regression to the mean, which a recalibration slope would absorb.
- Cheap players are over-projected: $1k or less is -1.4 and $1-3k is -1.1. These are the "cheap fill must be real" players.
- **Leave-one-slate-out (LOSO) models** (per position, 2025 weighted 2x). Pooled RMSE: raw FC 7.14, recalibrated FC 7.07, salary only 7.00,
  **FC + salary 6.95**, plus Vegas team total 6.94. Mean within-slate Spearman: 0.62 raw, 0.64 salary, 0.64 blend.
  - Salary alone matches or beats FC Proj (salary minus recal-FC MSE: -0.97, CI [-2.5, +0.5]).
  - The blend beats FC alone (MSE gain 1.67, 90% CI [0.54, 2.74]), **Supported** pooled. In 2025 alone the gain is +1.10 with CI [-0.86, 2.89], so Weak.
  - Kicker: salary ranks kickers far better than FC (within-slate Spearman 0.36 vs 0.11). K salary carries information FC misses.
  - QB: LOSO QB models barely beat the mean.
- Ceiling/floor bands: 6-7% of players beat the FC "ceiling" and 4-9% fall below the "floor". These bands are narrow percentiles (about p5/p95), and for DST
  the ceiling is almost never beaten (2%).
- **Bottom line.** FC Proj is only slightly better than salary in Showdown and slightly worse at K/QB. A per-position blend with salary
  helps by about 2% MSE. That is a small player-level gain, and I did not test it at lineup level.

## 5. Ownership

**Descriptive (averaged per game).**
- CPT ownership by position: WR 30.5%, RB 27.2%, QB 22.3%, TE 10.2%, DST 7.6%, K 2.2%.
- FLEX ownership totals: WR 164, RB 100, QB 87, TE 70, K 40, DST 29.
- Chalk concentration is stable across years: the max CPT is about 24%, the top-3 CPT about 52%, and the max FLEX about 58%.
  The CPT ownership of the top-projected player rose from 16% (2023-24) to 20% (2025).
- The chalk CPT is a QB (19 games) or RB (19), rarely a WR (8), even though WR is the most common hindsight CPT. It is the top-projected player 49% of the time.
- CPT/FLEX ownership ratio (players with FLEX ≥5%): QB 0.19, DST 0.18, RB 0.17, WR 0.12, TE 0.07, K 0.04.
- K averages 20% FLEX, 23.8% for favorites vs 16.8% for dogs. Favorite kickers also score more: 9.3 vs 7.7 actual.
- DST: the cheaper DST gets 9.5% FLEX and 1.5% CPT, the expensive one 19.7% and 6.0% CPT. Actual points are the same (5.4 vs 5.6).
  **The expensive DST costs about $1.1k more for about 0.2 pts and carries 4x the CPT ownership.**
- Min-price (≤$1k) players: 0.9% FLEX when proj = 0, 3.7% at proj 2-5, 5.8% at proj >5. CPT ownership is about 0.

**LOSO models** (ridge on logit ownership, waterfilled to 100/500 with caps 60/75; 2025 weighted 2x):

| Role | Model | corr | MAE | chalk MAE (chalk n) | chalk bias | top-1 hit |
|---|---|---|---|---|---|---|
| CPT | proj-only (proj share, log proj rank) | 0.77 | 1.88 | 7.3 (195) | -2.2 | 49% |
| CPT | full (+sal, value, pos, min-price, proj0, fav, spread, total) | **0.81** | **1.59** | **5.9** | -2.3 | 51% |
| FLEX | proj-only | 0.84 | 7.40 | 14.7 (524) | +0.2 | 49% |
| FLEX | full | **0.87** | **5.58** | **9.9** | -2.1 | 33% |
| CPT/FLEX | production `ownership_model_showdown.py` | see §5b | | | | |

Chalk is ≥8% for CPT and ≥20% for FLEX. For 2025 alone, full CPT corr is 0.85 and FLEX 0.87. Standardized coefficients:
- **CPT:** projection share +0.80, salary +0.73, QB -0.26, DST +0.18, spread +0.13, fav 0, total 0.
- **FLEX:** projection share +0.61, log rank -0.62, proj0 -0.66, min-price -0.36, QB -0.39, salary +0.14, fav/spread/total about 0.

Systematic miscalibration of the full model:
- CPT: $9k+ over-predicted by 2.0, $5-9k under-predicted by about 0.5-0.9. **The field spreads CPT to mid-priced players more than projection implies.**
- FLEX: QB under-predicted by 2.7 and RB over-predicted by 1.9. It counts too few 2-5% FLEX players (51 predicted vs 141 real). **The real field has a longer, fatter low tail.**
- **Game environment (favorite, spread, total) adds ~nothing** once projection is in. Team-favorite status matters only through projection.
- Ownership adds a little signal about actual points beyond FC Proj: LOSO SSE 52,294 falls to 50,059 (4%). The crowd knows something FC doesn't, likely news.

**5b. Production model on this data.** `prod_model_eval.py` runs `build_features` + `predict` with the *current artifact*, using FC Proj
as `final_projection` and FC STDV as sigma. This is a proxy: production uses our projections, and FC's are different.
It ran on all 49 slates.

| Role | corr (all / 2025) | MAE | chalk MAE | chalk bias | top-1 hit |
|---|---|---|---|---|---|
| CPT prod | 0.71 / 0.76 | 2.21 | 7.2 | -3.2 | 39% |
| CPT LOSO full | 0.81 / 0.85 | 1.59 | 5.9 | -2.3 | 51% |
| FLEX prod | 0.77 / 0.74 | 7.95 | 12.5 | -2.8 | 18% |
| FLEX LOSO full | 0.87 / 0.87 | 5.58 | 9.9 | -2.1 | 33% |

The production model's biases on the FC-proxy inputs (predicted minus actual; see CORRECTION below, the K/DST ones do not transfer):
- **FLEX kicker -11.9 and FLEX DST -8.8 points.** The artifact's isK/isD penalties, fitted on 2-4 slates, push K/DST FLEX ownership far below the
  real ~20% / ~15%. This is the largest, clearest fix.
- CPT QB +2.1 (the ILP over-captains QBs, as FC projects QBs highest).
- FLEX WR +2.9, and FLEX $1-3k +4.3.
- Too many 0-2% players and too few 2-10% players. The same fat-low-tail miss as the classic model.

**CORRECTION (2026-09-26, checked after this section was written): the K/DST bias above is a proxy artifact, NOT a production bug.** The isK/isD flags are negative because with *our* projections the noisy ILP over-rosters K/DST (mean FLEX l_exp on the 4 real slates: K -0.18, DST -0.49) and the flags correct for that. With FC projections the ILP does not over-roster them (K -1.98, DST -3.02), so the same negative flags push predictions far too low. Actual K/DST FLEX ownership is the same in FC history (K ~20%, DST 12-18%) and the 4 real 2026 slates (K ~19%, DST ~12%). A real-slates-only leave-one-slate-out of the current 4-feature model predicts K within about 1-8 pts and DST within about 2-7 pts per slate (no systematic bias), and an FC-fitted refit over-predicts K/DST on the real slates by +9 to +12. **Do not refit the K/DST flags from FC-proxy features.** The other §5b findings (QB/WR/low-tail biases, LOSO corr) are also proxy-contaminated for the same reason; only a replay with our own projections settles them.

## 6. Construction under the simulated field

The max-FC-projection lineup scores about the 58-59th field percentile on average, with 2% top-1% and 12% top-10% (n=49).
Selected rows follow, all paired vs max-proj on the F1 field with 90% slate-bootstrap CIs. Full tables are in `derived/showdown/agg_out.txt`.

| Strategy | #1 lineup Δpct (all) | #1 Δpct (2025) | Top-20 avg Δpct (all) | Top-20 Δpct (2025) | Top-20 Δtop10 (all) |
|---|---|---|---|---|---|
| CPT restricted to RB/WR | -1.9 [-5.2,+1.7] | **-4.6 [-7.3,-1.8]** | -0.7 [-2.4,+1.0] | -0.8 [-3.2,+1.4] | +0.5 |
| RB/WR CPT + max 1 K (current rules) | -1.8 [-5.3,+1.6] | **-4.6 [-7.4,-1.9]** | -0.7 [-2.4,+1.1] | -0.8 | +0.5 |
| CPT = QB forced | +0.6 [-2.5,+4.1] | -1.6 | **+2.3 [+0.6,+4.0]** | **+3.2 [+1.7,+4.7]** | +1.3 |
| No K/DST/TE CPT | **+0.6 [+0.2,+1.2]** | 0 | +0.3 [-0.3,+0.9] | +0.9 [-0.1,+1.9] | +0.5 |
| Max 1 K | +0.1 | 0 | 0.0 | 0.0 | 0 |
| Exactly 2 K | **-7.7 [-13.7,-1.5]** | -4.7 | -3.4 [-7.1,+0.4] | -3.7 | -0.4 |
| No DST | -0.2 | +1.2 [+0.1,+2.5] | +0.1 | +0.4 | +0.1 |
| Cheap DST only | -0.1 | +0.5 | +0.5 [-0.1,+1.1] | +0.5 | +0.4 |
| Split 5-1 forced | -2.9 [-9.2,+3.3] | -1.6 | **-4.5 [-7.5,-1.5]** | -2.0 [-8.0,+3.2] | -2.4 |
| Split max 4 (no 5-1) | **+3.8 [+1.0,+6.9]** | +4.1 [0,+8.6] | +0.2 | -0.8 | +0.9 [+0.1,+1.8] |
| Split 3-3 | +3.1 | +4.4 | -0.3 | -1.6 | **+3.3 [+0.9,+5.7]** |
| ≥4 from favorite | -0.4 | -5.6 | **+2.4 [+0.3,+4.7]** | -0.2 | +2.2 |
| ≥4 from underdog | +0.6 | +0.3 | -3.0 [-6.6,+0.8] | -2.8 | +1.6 |
| CPT own <5% | **-6.3 [-11.6,-1.0]** | **-11.6** | -2.0 [-4.4,+0.6] | -2.7 | -0.1 |
| CPT own 5-15% | +0.4 | -3.8 | +0.9 | +0.5 | +2.0 |
| CPT own ≥15% | +3.5 [-0.6,+8.0] | +0.5 | +1.2 | -0.9 | 0.0 |
| Fade chalk CPT | **-1.8 [-3.4,-0.3]** | **-6.0 [-8.9,-3.3]** | -0.1 | -0.4 | +0.3 |
| Leverage (proj - 0.05×own sum) | -1.9 | -5.4 | **-2.9 [-4.9,-0.9]** | -1.2 | -0.2 |
| Leverage 0.1 / 0.2 | -7.4 / -10.1 | | **-5.3 / -12.5** | -1.4 / -9.5 | +1.3 / -1.8 |
| Chalk tilt (proj + 0.1×own sum) | +1.7 [-4.3,+8.2] | -6.7 | **+4.4 [+2.3,+6.8]** | +2.8 [-0.8,+6.6] | +1.2 |

Reading this honestly:
- The max-proj lineup captains a QB in 26/49 games, because FC projects QBs highest. **Restricting CPT to RB/WR costs about 2 percentile points on the #1 lineup and 4.6 points in 2025.**
  On the top-20 average it is neutral, and forcing a QB captain *helps* the top-20 average (+2.3, CI excludes 0; 2025 +3.2).
  On 49 games, the "RB/WR CPT" rule is **Not supported** as a restriction. Hindsight says QBs are optimal CPT 18-20% of the time, about their ownership share.
- **Leverage loses and chalk tilt wins in this simulated field.** Treat this with caution. A maximum-entropy field under-represents correlated chalk
  stacks, so chalk-heavy lineups look *less* duplicated than they are. And in a percentile metric, low-owned players' upside is
  already priced as "field doesn't have it" only in expectation. This mostly says **ownership contains information about points** (see §5, the 4% SSE gain),
  consistent with the classic finding that a flat leverage penalty gives no gain. It does **not** show chalk is +EV in real top-heavy GPPs.
- Most other rows have CIs spanning 0.

## 7. Other observations

- Favorites: 67% of hindsight CPTs came from the favorite (vs about 55% of field CPT ownership, not computed exactly). A favorite-heavy top-20 was +2.4 pctl, but 2025 was flat. **Weak.**
- Residual (actual - FC) by position x favorite: RB on dogs -1.4, RB on favorites +0.4, WR on favorites -1.3, TE on favorites +1.0, QB on dogs +1.0.
  All are within about 1 SE. Noise-level; don't act.
- Hindsight lineups rarely use a DST (22%) and almost never the expensive one (10%).
- Punts: 22% of hindsight lineups include a ≤$1k player and 18% include an FC-0 player. The hindsight optimum leaves a median of $1.1k unspent.
  Punts appear only when a cheap player *happens* to score, and nothing in the data lets us predict that (FC-0 rows average 1.1 pts).

## 8. Evidence grade per current SHOWDOWN_RULES.md rule (n=49 vs 4 real slates)

| Rule | Verdict at n=49 | Basis |
|---|---|---|
| 1. Highest projection wins | **Supported, with a caveat.** Max-proj is a strong baseline, and few restrictions beat it. But the top projection is over-projected (-3.1) and salary is as predictive as FC. | §4, §6 |
| 2. RB or WR at CPT | **Not supported as a restriction.** Hindsight CPT is WR 39 / RB 29 / QB 18 / TE 12%, about equal to field shares. The restriction costs -1.9 overall and -4.6 in 2025 (#1 lineup). | §3, §6 |
| 3. No K/DST CPT; TE usually not | **Supported for K/DST** (0/49 DST, 1/49 K hindsight; the field over-uses DST CPT at 7.8%). **TE: Not supported** (12% hindsight, 2025 5/18). | §3 |
| 4. Cheap fill must be a real player | **Supported (descriptive).** Min-price and FC-0 players average 1-2 pts, and $1-3k players are over-projected by about 1.1. Punts win only by luck. | §4, §7 |
| 5. At most one K | **Supported** as an "avoid 2 K" rule: 2 K is -7.7 [-13.7,-1.5] on the #1 lineup and 4% of hindsight. Max-1-K as a constraint costs ~0 because the optimizer rarely builds 2 K. | §3, §6 |
| 6. DST lean cheap or skip | **Weak.** Cheap-only DST is +0.5 [-0.1,+1.1] top-20. The expensive DST scores the same as the cheap one for about $1.1k more and 4x CPT ownership. The hindsight optimum skips DST 78% of the time. | §5, §6 |
| 7. 5-1 unsupported; 4-2/3-3 fine | **Supported (as "avoid forcing 5-1").** Forced 5-1 is -4.5 [-7.5,-1.5] top-20. Hindsight 5-1 is 10% vs 16% of the field. 2025 alone is inconclusive. | §3, §6 |
| 8. Chalk CPT: no clean fade; <5% worst | **Supported.** CPT <5% is -6.3 [-11.6,-1.0] (#1) and -11.6 in 2025. Fading the chalk CPT is -1.8 [-3.4,-0.3]. The chalk CPT is optimal 16% of the time, about its ownership. | §3, §6 |

## 9. Proposed SHOWDOWN_RULES.md edits (for Greg to apply)

- Evidence base line: add "plus 49 FC-history games 2023-25 (player-level + simulated field; see HANDOFF_showdown_history_findings_2026-09-26.md)".
- Rule 2 → **demote to Weak/Not supported**: "Do not restrict CPT to RB/WR. QB is a legitimate captain (hindsight 18-20%, about
  its field share). Keep Greg's WR tiebreak only when projections are close."
- Rule 3 → "Don't captain K or DST (0-2% of optimal; the field wastes ~8% on DST CPT). TE CPT is fine when projection supports it."
- Rule 5 → keep "at most one K", now Supported (2-K builds -7.7 pctl, 4% of optima).
- Rule 6 → "DST: skip or the cheaper one; the pricier DST buys ~0 points and 4x CPT ownership" (Weak).
- Rule 7 → "Avoid forced 5-1 (Supported, -4.5 pctl top-20); 4-2 is the modal optimal split (63%)."
- Rule 8 → "Chalk CPT is fine; avoid <5%-owned captains (Supported)."
- New Weak rule: "FC/any projection's #1 player tends to be over-projected in Showdown (-3 pts, ~2 SE). Don't let one stud's projection force the CPT."
- Candidate opt-in flags: `--max-kickers 1` (harmless), `--no-cpt-positions K,DST` (tiny +, CI excludes 0), `--max-team-players 4`
  (avoid 5-1; +3.8 on #1 lineup). **Drop** `--cpt-positions RB,WR` as a candidate default.

## 10. Recommendations (ranked by expected value x confidence)

1. **Do not add an RB/WR-only captain restriction. Do add a K/DST-captain exclusion and max 1 K** (Medium confidence). They are cheap and
   consistent with hindsight and with the simulation.
2. **Showdown ownership model: DO NOT change the isK/isD flags (see §5b CORRECTION).** The FC-proxy K/DST bias was an artifact of feeding FC projections
   into a model calibrated on our projections. Any refit of shape (position/salary/min-price terms) has to use features built from OUR projections, i.e. a replay of
   our pipeline on history (open question). The FC-based LOSO figures (CPT corr 0.81 / FLEX 0.87) show what projection-share + salary + position can reach, not a validated production gain.
   Observations below are directional only:
   - CPT over-predicted for $9k+ and under-predicted for $5-9k.
   - FLEX QB under-predicted by about 2.7.
   - Too few 2-5% FLEX players.
   - Favorite/spread/total add nothing.

   Caveat: FC Proj is not our projection, so refit the *shape* (position, salary and min-price terms) and keep optimizer exposure
   as the projection-driven feature, then check on our 4 real slates.
3. **Projection: blend salary into Showdown projections per position, especially K** (Medium). This gives a 2% MSE gain LOSO, and kicker ranking is
   0.36 vs 0.11 Spearman. Shrink the single top projection toward the position mean (Weak; about 2 SE). Validate at lineup level first.
4. **Avoid 5-1 by default in single-entry** (Medium-weak). Allow it only for deliberate game-script bets.
5. **Leverage settings: keep the ownership penalty at 0 (lambda 0) for Showdown SE/cash** (Medium). Nothing here supports a flat leverage term,
   and it cost 3-12 percentile points in the simulation. Chalk-tilt gains are not trusted (field artifact risk).

## 11. Open questions
- A real-field check. The 4 logged real DK Showdown contests could calibrate how much more correlated the real field is than
  maximum entropy (for example, fit a QB-receiver and same-team pairing tilt to the real lineups, then rerun `slate_sim.py` with it). That is the
  biggest uncertainty in §6.
- Rerun the strategy grid with *our* projections and *predicted* ownership once our Showdown pipeline can be replayed on history.
- TE captains in 2025 (5/18 hindsight): noise or trend? Revisit after 2026 Showdowns.
- Missing ownership mass on 7 slates: check the raw FC export for dropped rows.
