# DK Classic construction rules (living doc, created 2026-09-30)

Evidence-graded construction rules for DraftKings NFL Classic, the classic counterpart to `SHOWDOWN_RULES.md`.
Update after each slate batch. **As of 2026-09-30 the DST/punt findings are live in the optimizer; the FLEX rule was
replaced 2026-10-02 with a WR-price-tier version (see rule 3)** via all four classic presets (`cash`, `se_gpp`, `mme_gpp`,
`se3max_pool`). See "Optimizer enforcement" below.

## Evidence base
- **Classic FC Lineup Study:** 410 real DK classic contests, 21.9M entries, 2022-2026, SE / 3MAX / 20MAX / big GPP
  (`HANDOFF_classic_lineupstudy_findings_2026-09-29.md`). §3 = raw cash lift per shape feature (cash-rate pts vs the
  contest's base rate, 90% CI, seasons with the sign). §5 = multi-feature per-contest OLS that controls for FC projection,
  ownership, QB salary, QB+2, bring-back and salary left.
- **Grades:** *Supported* = CI excludes 0 and the sign holds in most seasons, in more than one contest type. *Weak* = right
  sign, CI touches 0 or only one format.
- **Real-slate sanity check** of the shipped weights: 9 real 2026 Wk1-3 DK classic slates (`analysis/classic_shape_weights/`).

## Rules

1. **DST salary: $2.8-3.1k is best, $3.6k+ is worst. Supported, all 3 formats.** Cash lift $2.8-3.1k +0.8 / +1.2 / +1.2
   (SE / 3MAX / 20MAX, 3MAX 4/4 seasons); $3.6k+ -2.3 / -2.8 / -2.9 (20MAX 0/4 seasons, return 0.86-0.90x). Under $2.8k is
   only neutral (+0.3 / +0.4), so the rule is "cheap and believable", not "cheapest DST". No projection-controlled term.
2. **Punts (non-DST at $4,000 or less): 0 is bad, 1 is best, 3+ is bad. Supported.** 0 punts -2.2 / -2.3 / -1.9 raw. After
   §5's projection control, having at least 1 punt is still worth **+1.4 to +1.9** (Supported in SE and 20MAX). 2 punts is
   neutral (+0.1 to +0.3). 3+ punts -2.7 / -4.1 / -4.7 raw (no controlled term). "More punts is better" is contradicted.
3. **FLEX position: the flat "RB > TE > WR" rule is NOT supported. Replaced 2026-10-02 by a WR-price-tier rule: pay up
   for a WR in FLEX, or don't use one at all.** The old grade came from §3's raw lift only (FLEX RB +0.7 to +1.0, FLEX WR
   -1.2 to -1.5). Controlled re-fit (`analysis/flex_position/flex_experiment.py`, 381 contests 2022-26, per-contest OLS =
   §5's model + FLEX=RB / FLEX=WR dummies, **TE as the omitted baseline** -- i.e. every number below is "vs TE", not "vs
   each other" -- then + the FLEX player's own projection, salary and ownership):
   - **RB vs TE is ~0 at every price tier, every format, on points or cash rate.** RB in FLEX is indistinguishable from TE.
     The old RB bonus was never a real effect -- `--cl-flex-rb-bonus` is dead, kept only for manual override.
   - **WR vs TE pooled across all prices is also ~0** (points CI spans 0 in every format; the one pooled cash-rate number
     that clears is a ~1pt edge, too small to act on alone). The original RB>WR grade was real as a *relative* statement
     but came entirely from WR underperformance in the mid tier below, not from RB being good or TE being bad.
   - **The real effect is a single salary-conditioned WR swing, confirmed per-format (not just pooled):**
     - **WR $6,300+:** beats TE by **+2.8 to +4.1 points** / **+3.9 to +6.1 cash-rate pts**, 4/4 seasons, **passes in all
       three formats (SE, 3MAX, 20MAX) on both metrics.** Also beats RB directly at this tier by +2.3 to +2.8 points
       (the rbwr term), 3/4 seasons. This is the single most robust number in the whole experiment and matches the PPR
       read: a pricey, high-target WR in FLEX outscores a same-tier RB or TE.
     - **WR $4,900-$6,300:** a real **downgrade** vs TE, -1.3 to -1.5 points / -1.6 to -2.0 cash-rate pts; passes in SE
       and 20MAX (3MAX trends the same direction, 4/4 season sign, but its own CI doesn't individually clear).
     - **WR under $4,900, and RB/TE at every price:** no proven effect either direction -- a statistical wash, not a
       proven inferiority. Don't read "cheap WR is bad" into this; the data just doesn't distinguish it from the rest.
   - Net ranking: **WR $6,300+ > {RB any price, TE any price, WR under $4,900} > WR $4,900-$6,300**, with only the top and
     bottom groups statistically real.
   - Results tables: `analysis/flex_position/out/` (local only, FC-derived).
4. **DST facing your own skill player: bad. Supported** (-1.9 / -2.1 / -3.0, 0/4 seasons, 11-13% of the field does it).
   Already a hard constraint (`exclude_skill_vs_opp_dst`, default on), not a `--cl-*` term.
5. **Ownership:** realized ownership predicts cashing (+1.1 DST to +2.8 RB per SD of log-ownership, 4/4 seasons), but
   `--own-penalty` fading is dropped and chalk tilt with our own modeled ownership showed no gain on history. Not a lever
   until the ownership model improves. See `WK3_POSTMORTEM_CHECKLIST.md` track-2 outcomes.
6. **QB price, stud count, punts beyond 1-2: matter little or not at all.** QB+2 is real but smaller than assumed.

## Optimizer enforcement (2026-09-30)

Rules 1-3 are soft ILP terms in `solve_lineup()` (`add_classic_shape_terms()` in `scripts/optimizer.py`; also added to
`build_multi_lineup()`'s cross-stack-candidate score). **Same weights in all four classic presets.** The shape findings
held similarly across SE/3MAX/20MAX, and they are not the contest-type-specific "lean chalkier" ownership finding, so a
per-preset split has no evidence behind it.

Point scale follows Showdown: 1 cash-lift pt ~ 1 projected pt. Where §5 gives a projection-controlled coefficient, that
is used. Where it doesn't, the raw lift is shaded x0.75 (the zero-punt controlled/raw ratio, ~1.6/2.1), since part of a
raw shape effect may already be reflected in projection that the solver is maximizing.

| Flag | Value | Basis |
|---|---|---|
| `--cl-dst-band-bonus` | **0.8** | rule 1, raw +0.8/+1.2/+1.2 (mean ~1.07) x0.75 |
| `--cl-dst-expensive-penalty` | **2.0** | rule 1, raw -2.3/-2.8/-2.9 (mean ~2.67) x0.75 |
| `--cl-zero-punt-penalty` | **1.5** | rule 2, §5 controlled "≥1 punt" +1.4 to +1.9 |
| `--cl-three-plus-punt-penalty` | **2.5** | rule 2, raw -2.7 to -4.7 x0.75 at the low-mid end; flat, once |
| `--cl-flex-rb-bonus` | **0** (was 0.6) | rule 3: dead at every price tier after controls (2026-10-02). Kept for override only. |
| `--cl-flex-wr-penalty` | **0** (was 1.0) | rule 3: flat version dead after controls (2026-10-02) -- replaced by the two price-tier flags below. Kept for override only. |
| `--cl-flex-wr-highprice-bonus` | **3.0** | rule 3, controlled WR-$6,300+-vs-TE range +2.8 to +4.1 pts, shaded to the low end |
| `--cl-flex-wr-midprice-penalty` | **1.3** | rule 3, controlled WR-$4,900-6,300-vs-TE range -1.3 to -1.5 pts, shaded to the low end |

Every flag can be overridden on the command line (`--cl-... 0` turns one off). All flags at 0 is byte-identical to the
pre-2026-09-30 solve. **Implementation note (fixed 2026-10-02):** classic has no explicit FLEX variable -- the solver
only knows "3 WR slots + 1 shared FLEX slot," not which specific player occupies FLEX. The two new FLEX-WR terms solve
this with an auxiliary binary per selected WR ("is this one the discretionary 4th WR"), pinned exactly to the real
extra-WR count (0 when you carry your normal 3 WRs, 1 when FLEX is a WR). The practical effect: a mandatory WR among your
fixed 3 can NEVER take the mid-price penalty no matter its own salary, and two $6,300+ WRs only earn the bonus once, not
twice -- both of those were real gaps in the first version of this term (same-day fix, never shipped). See
`add_classic_shape_terms()`'s docstring in `scripts/optimizer.py` for the full mechanics; `classic_shape_adjustment()`
replicates the same tagging logic for the cross-candidate scorer in `build_multi_lineup()` without needing a second LP solve.

### Real-slate sanity check (`analysis/classic_shape_weights/replay_cl_arm.py`, outputs `run_out*.txt`, `seeded_arms*.csv`)
9 real 2026 DK classic slates (Wk1-3 main/early/afternoon), graded against the real contest results in
`data/contest_results/` (top-25% cash line, SE3max field). se3max_pool structure (QB stack 2 + bring-back), 20 paired
5%-randomized seeds per slate = 180 pairs, terms off vs on:

| | off | on (shipped) |
|---|---|---|
| DST in $2.8-3.1k | 16% | 63% |
| DST $3.6k+ | 25% | 2% |
| 0 punts / 3+ punts | 19% / 13% | 4% / 0% |
| FLEX RB / FLEX WR | 18% / 15% | 34% / 0% |
| Mean projection | 123.5 | 122.6 (-0.9) |
| Mean real percentile | 0.549 | 0.580 (+0.030, slate-level SE 0.052) |
| Top-25% cash rate | 29.4% | 23.9% |

- **Feasible on every slate and seed.** Shape moves exactly as intended at under 1 projected point per lineup.
- **Real outcome: mixed, inside noise.** Percentile slightly up (driven by Wk2 early/main, +0.25 to +0.34), cash rate slightly
  down (Wk2 afternoon, Wk3 early). 9 slates cannot confirm or rule out a ~1-2 pt effect. That is expected: the study's
  effects are 1-3 cash pts, and the study itself (410 contests) is the evidence, not this check.
- The unshaded set (1.0 / 2.5 / 1.5 / 3.0 / 0.8 / 1.3) gave the same percentile/cash numbers at -1.1 projection. The shaded
  set was shipped because it gets the same shape shift more cheaply.
- Caveat: pools are the current `output/final_projections_*` files, not lock-time snapshots. Wk3 files may include
  post-lock rebuilds.
- **This sanity check predates the 2026-10-02 FLEX-WR price-tier rule** -- the FLEX row above (18%/15% -> 34%/0%) reflects
  the old, now-dead flat RB-bonus/WR-penalty weights, not `--cl-flex-wr-highprice-bonus`/`--cl-flex-wr-midprice-penalty`.
  Re-run `replay_cl_arm.py` with the new weights before trusting this table for the current FLEX behavior.

## Caveats
- **First-pass point-scale calibration, like Showdown's `--sd-*` weights. Not a swept optimum.** Revisit once Wk4+ classic
  slates accumulate: re-run `replay_cl_arm.py 20` with new slates added and compare percentile/cash off vs on.
- DST band and FLEX never got a projection control in §5. If a future controlled fit shrinks them, lower the weights.
  **FLEX done 2026-10-02 (rule 3): the flat version collapsed (both old flags now 0), replaced by a WR-price-tier pair
  that IS controlled (`--cl-flex-wr-highprice-bonus`/`--cl-flex-wr-midprice-penalty`). The DST band and the $3.6k+ DST
  penalty are still uncontrolled raw lifts and are next in line for the same test.**
- The FLEX-WR price-tier terms are exactly scoped to the discretionary 4th WR (see "Optimizer enforcement" implementation
  note above, fixed 2026-10-02) -- still a soft nudge like every other `--cl-*` term (it doesn't force a WR into FLEX),
  but it no longer touches a mandatory WR's own price, and it adds a handful of extra binary variables per build (one
  per selected-WR-eligible player) whenever either flag is nonzero. Checked against a real 100-lineup `se3max_pool`
  build on a live Wk4 slate: no meaningful solve-time cost.
- The 3+ punt term rarely binds (13% of baseline lineups), so it is the least exercised.
- Punt definition is Phase 2's (non-DST salary ≤ $4,000). DST band is inclusive $2,800-3,100; expensive is ≥ $3,600.
