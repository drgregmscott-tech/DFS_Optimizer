# Week 3 Root-Cause Findings (living doc, started 2026-09-28)

Companion to `WK3_POSTMORTEM_CHECKLIST.md` §0. That file has the full brainstorm/context;
this file is where Phase 1 / Phase 2 results get written up as they're produced, per slate,
so findings don't get lost in chat. Update incrementally at each step boundary, not in one
big dump at the end.

## Game plan (agreed 2026-09-28)

### Phase 1: Player-level diagnostics (per slate: early, afternoon, main SE3max, main MME)

1. **Data prep** — parse each CSV to one row per entry (dedupe by EntryId), full roster + Points.
   Cash-line: top 25% rank for single-entry files, top 22% for MME/dime package.
2. **Cash-lift analysis** — per rostered player: field ownership %, cash rate rostered vs. not,
   lift/delta. Top cash-drivers and cash-killers (cap 5 for early/afternoon, 5-10 for main).
   Correlation check: does lift hold standalone, or is it a stack-pairing effect misattributed
   to one player? Report both standalone and paired-context lift.
3. **Four-way miss taxonomy** per flagged player: field hit/we missed, we hit/field missed,
   both missed, both hit.
4. **Root-cause tagging** per flagged player — pull our projection + modeled ownership,
   classify: good signal followed, good signal ignored/overridden, bad signal, no signal.
   For "field hit/we missed": timing/pipeline-latency issue vs. genuine model miss.
   Track "signal correct but seemingly not acted on" frequency (not its own workstream yet;
   promote to one if it recurs 2+ times).
5. **Structural checks** (whole distribution, not just tails) — systematic bias check
   (correlate modeled-ownership-minus-real-ownership against actual points, across all
   players/slates); salary-tier stratification; position/role tagging.
6. **Cross-week consistency** — rerun 1-5 against Week 1 and Week 2 exports (confirmed
   available in `data/contest_results/`). Look for recurring players/patterns/price-bands/
   positions across weeks. 2025+ historical replay parked as stretch goal.

**Phase 1 output:** written miss-list per slate (taxonomy + root-cause tag + salary/position
tags), bias-direction finding if any, cross-week consistency summary.

### Phase 2: Construction-level diagnostics (starts only after Phase 1 outputs exist)

- **Chalk-baseline check** — would a simple top-5-owned-per-slot build have beaten our actual
  lineups? Uses Phase 1 cash-lift data directly.
- **Pool-shape comparison** — our lineup pool's stack type/salary distribution/stud-vs-punt
  shape vs. shape of lineups that actually cashed, informed by which specific players Phase 1
  flagged as mispriced (so shape mismatches aren't misattributed to construction rules when
  they're really a player-input problem).
  **Use directly, don't re-derive (added 2026-09-28):** Phase 1's stack-pairing split (Step 2
  below) already found 12 of 80 flagged driver rows are pairing-driven, not standalone player
  effects — almost all QBs, where the real driver is the QB+WR1 stack (e.g. Dak Prescott wk2:
  +55pt with CeeDee Lamb rostered vs +7pt without; Isaiah Williams wk3, 3.1 real points, is a pure
  stack passenger on Geno Smith lineups). Feed this list into the pool-shape comparison directly —
  it's a concrete, already-quantified answer to "does our pool's stack rate match what actually
  drove cashes."

## Data inventory (confirmed 2026-09-28)

Classic DK contest exports available in `data/contest_results/`:
- Week 1 (13Sep2026): early, afternoon, main — no ownership cap noted in filename
- Week 2 (20Sep2026): early, afternoon (se3max), main (se3max + mme)
- Week 3 (27Sep2026): early, afternoon (se3max), main (se3max + mme)

No showdown slates played in Week 3 — showdown files excluded from this analysis.

FC history available in `data/fc_history/2026/` for Wk1-2 main (mme, single_entry, 3max).
FC Week 3 not yet pulled — Fantasy Cruncher site returning 502 as of 2026-09-28; not a
blocker for Phase 1 (DK exports carry ownership + realized lineups directly).

## Phase 1 results (first pass 2026-09-28, Steps 2-5 reworked 2026-09-28)

Step 1 (unchanged, done): `analysis/classic_diag/wk3_postmortem_phase1.py`. One row per entry (dedupe
EntryId), cash line = top 25% for single-entry/SE3max slates, top 22% for MME. 11 slates, wk1-3.

Steps 2-5 rework: `analysis/classic_diag/wk3_postmortem_phase1_v2.py` (imports the Step 1 parsing
from the v1 script). Outputs:
- `wk3_postmortem_v2_players.csv` — every player-slate row (field %, cash rate with/without, lift,
  lift z, our projection/ownership/chalk_score, gmscott81 entry count)
- `wk3_postmortem_v2_flags.csv` — 160 flagged player-slate rows (80 drivers, 80 killers) with
  stack-pairing split, snowflake result, four-way bucket, root-cause tag
- `wk3_postmortem_v2_flags_unique.csv` — same list collapsed to 92 unique week-player-direction rows
  (43 drivers, 49 killers), which is what the tables below show

The first-pass flag table, 5-way tag and Step 4 per-flag table are superseded by what follows.

### Step 2: cash drivers and cash killers (reworked)

**Method.** Lift = cash rate of entries rostering the player minus the slate's base cash rate (0.25,
or 0.22 MME). Eligible: field_n >= 20 and field% >= 5%. Drivers = top positive lift, killers = top
negative lift. Cap 5 each on early/afternoon, 10 each on main (both main variants). Every slate hit
its cap on both sides. `lift_z` (binomial) is in the CSV; every flagged row is |z| >= 4.7, so none
of these are small-sample noise at the entry level (they can still be one-game variance, which is
what Steps 3-4 are for).

Full per-slate lists are in the script output / flags CSV; unique-player tables are under Step 4.

**2b. Stack-pairing split (reworked to the correct definition).** For each flagged QB, partner =
that team's highest-field-owned WR/TE; for each WR/TE/RB, partner = that team's QB. Split the
player's entries into with-partner / without-partner and compute lift in each. Tag "standalone" if
the without-partner lift keeps the sign and at least half the magnitude; "pairing-driven" if the
lift is carried by the with-partner subset. DST has no single natural partner and is not split.

| | standalone | pairing-driven | thin subset (<20 entries) | n/a (DST) |
|---|---|---|---|---|
| drivers (80 rows) | 59 | 12 | 2 | 7 |
| killers (80 rows) | 69 | 2 | 6 | 3 |

The pairing-driven rows are almost all QBs, and the effect is large:
- Dak Prescott wk2 (all 3 variants): +55pt with CeeDee Lamb vs +7pt without (se3max); afternoon +33 vs -2.
- Tyler Shough wk1: +36-40 with Chris Olave vs +12-14 without.
- Jordan Love wk1 afternoon: +43 with Christian Watson vs -4 without. Lamar Jackson wk1 main: +26 with
  Zay Flowers vs +5 without.
- Isaiah Williams wk3 (WR, **scored 3.1 DK pts**): +54-64 with Geno Smith vs +9 without. His driver
  status is purely a stack artifact — he's a passenger on Geno Smith lineups.
- Carson Wentz wk2 (killer): -16 to -18 with Justin Jefferson vs -3 to -6 without.

Reading: QB cash lift is mostly the QB+WR1 stack, not the QB alone. Pass-catcher drivers
(Lamb, Olave, Schultz, JSN, Garrett Wilson, Juwan Johnson) are standalone — they carried lift
without their QB too. Killers are overwhelmingly standalone busts.

**2c. Snowflake test (reworked to the correct definition).** Same player, other slate variants of
the same week (early/afternoon vs main = different game sets; main se3max vs main MME = same games,
different contest, reported separately). 158 of 160 flagged rows keep the same lift sign in every
other game-set cut they appear in; 82 of 160 (drivers 51/80, killers 31/80) also made the capped
driver/killer list in another cut. Exceptions: Raiders DST wk2 (afternoon +14.5, main ~0) and Brock
Purdy wk2 (MME +10, afternoon -0.4).

Caveat, stated plainly: a player's DK points are identical across a week's slate variants, so the
snowflake test can't provide independent replication of the *outcome*. What it does show is that the
driver/killer calls are not artifacts of one field's composition, one contest size, or the cap
cutoff. Useful as a filter, weak as confirmation.

### Step 3: four-way taxonomy (rebuilt)

**Operational definition.** "Heavily weighted by the field" = field% >= 15%. "Heavily weighted by
us" = our modeled ownership >= 15% **or** our projection z >= 1.0 within position (z computed over
players the field used at >= 1% on that slate). Projection counts as "we hit" because projection is
what our lineups are built on; ownership is a secondary input.

- **Drivers** (good outcome): field on + us off = *field hit / we missed*; us on + field off = *we
  hit / field missed*; neither = *both missed*; both = *both hit*.
- **Killers** (bust): the four-way does not collapse. I expected it might (a killer should need a
  heavy field share to hurt), but killer field% has a median of 9.8% and only a quarter are >= 14%.
  A 7%-owned bust hurts every entry that rostered it just as much. So the same 2x2 applies,
  relabeled: *field trapped / we avoided*, *we trapped / field avoided*, *both trapped*, *neither
  heavy*.

| drivers (43 unique) | n | killers (49 unique) | n |
|---|---|---|---|
| both missed | 23 | neither heavy (mid-owned bust) | 29 |
| both hit | 9 | we trapped / field avoided | 11 |
| we hit / field missed | 8 | both trapped | 5 |
| field hit / we missed | 3 | field trapped / we avoided | 4 |

(Row-level, all 160: drivers 40/18/12/10, killers 45/19/10/6, same order.)

What this changes versus the first pass:
- Under the literal definition, only **3** unique drivers are "field hit / we missed": Aaron Jones
  wk2, Dalton Schultz wk2, Titans DST wk3. Most of the first-pass "field hit, we missed" names
  (Olave, Lamb, JSN, Dak) were players **our projection already rated strongly** (z 1.4-2.6). They
  land in "both hit" or "we hit / field missed". Our ownership number was wrong on them. Our
  projection was not. See Step 4 for whether we played them.
- The biggest driver bucket is "both missed" (23): cheap players nobody leaned on who hit
  (Geno Smith, Kenyon Sadiq, Jalen Coker, Isaiah Williams, Jaylen Warren).
- On the killer side, 11 "we trapped / field avoided" is the actionable bucket. It's our
  projection over-rating players the field sensibly faded, and wk3 alone has 5 of them: Josh Allen,
  Lamar Jackson, Justin Jefferson, Dalton Kincaid, Jonathan Taylor.

### Step 4: root-cause tagging (reworked, every flag tagged)

**Tag rules** (per flagged row, from our projection z within position and gmscott81's submitted
entries on that slate; entries matched on `EntryName` containing `gmscott81`, 1 entry on each
SE3max/single-entry slate, 20 on each MME):
- Driver: z >= 1.0 and rostered = *good signal followed*; z >= 1.0 and not rostered = *good signal
  ignored/overridden*; 0 <= z < 1.0 = *no signal (neutral)*; z < 0 = *bad signal*.
- Killer: z >= 1.0 = *bad signal* (we liked a bust); z < 0.5 and not rostered = *good signal
  followed*; z < 0.5 and rostered = *good signal ignored/overridden*; 0.5-1.0 = *no signal*.
- Separately, an ownership tag: our modeled ownership minus field% <= -10pt = under-owned, and for
  those rows, which ownership mechanism produced the number (below).
- Missing from our pool: none. Every flagged player matched our final_projections file.

Counts (unique week-player-direction, rows with mixed tags across variants listed separately):

| drivers (43) | n | killers (49) | n |
|---|---|---|---|
| no signal (neutral projection) | 20 | good signal followed (we faded a bust) | 21 |
| bad signal (projection below position mean) | 9 (+2 mixed) | bad signal (projected strong, busted) | 15 |
| good signal ignored/overridden | 5 (+6 mixed) | no signal (neutral) | 11 |
| good signal followed | 1 (+5 mixed) | good signal ignored/overridden | 2 |

All 92 have a tag. None are left "unconfirmed."

#### 4a. Correction to the headline mechanism (important)

The first pass attributed the WR/TE ownership misses to `OWNERSHIP_SOFTMAX_TEMPERATURE_BY_POSITION`.
Checking which code actually produced each week's `estimated_ownership_pct` shows that's only partly
right:

- **Wk1-2 files were built by the softmax heuristic.** Fitting softmax(chalk_score / T) to each
  wk1/wk2 pool reproduces the stored ownership at QB T=14 (max error 0.7-2.0pt) and DST T=15 (max
  error 0.00) exactly, and RB/WR/TE within a few points. (Files were committed pre-lock, e.g. wk2
  main at 2026-09-20 16:31Z; the layered model landed 2026-09-21.)
- **Wk3 files were built by the layered model** (`ownership_model.py`, FFC variant). The softmax is
  only one input there (`l_est`, coefficient 0.22). I reproduced wk3_main ownership exactly from the
  artifact and features (corr 1.000, MAE 0.00) and decomposed it. The heuristic softmax gives
  Amon-Ra St. Brown 13.1% and CeeDee Lamb 11.6%, nearly equal. The 38.3% vs 5.0% gap comes from
  **FFC listing**: Amon-Ra is on FFC's top-50 public ownership table (41.4%), so he gets
  `ffc_listed` +0.79 plus `l_ffc` +0.04. Lamb isn't listed, so he gets `l_ffc` -0.89 (imputed 1%)
  and `ffc_listed` 0. That's about a 1.7 logit gap from listing status alone. Optimizer exposure
  (`l_exp`) adds 0.66. The temperature contributes ~0.03.

What actually drives the under-ownership, by mechanism:

| mechanism | evidence |
|---|---|
| **wk1-2: chalk_score ranking (inputs), not temperature** | 80 wk1-2 chalk rows (field >= 10%) under-owned by >= 10pt: median chalk_score rank within position is **15 for WR, 12 for RB, 9 for TE**; only 18% of the WR rows were top-3 by chalk_score. The field's chalk was players our chalk_score ranked mid-pack (JSN wk2 afternoon rank 17 → 6.9% vs 35% field; Aaron Jones rank 23; Devaughn Vele rank 45-69). No temperature setting fixes a rank-17 player. |
| **wk1-2: softmax cap at the top (temperature/shape), secondary** | Where chalk_score *did* rank the player top-3, the flat softmax still capped them: TE max modeled 5-15% on non-afternoon wk1-2 slates vs field TE max 20-33%; Schultz (TE rank 3-5) 3.8-6.9% vs 21-24%; Ja'Marr Chase wk1 (WR rank 2) 16% vs 32%. Real, but it accounts for 3 of the 18 unique under-owned flags. |
| **wk3: FFC-unlisted cliff** | wk3 chalk (field >= 10%): FFC-listed players mean gap **+0.8pt** (n=82), unlisted **-9.6pt** (n=33). Every wk3 under-owned flag (Shough, Kincaid, Titans, Vikings) and the first pass's Olave/Vele wk3 rows are unlisted. FFC lists no DSTs at all, so for DST the cliff cancels within the DST budget and the DST miss falls back to chalk_score ranking (next row). |

Net effect on calibration, chalk rows (field >= 10%), mean gap (ours minus field) / MAE:

| | QB | RB | WR | TE | DST |
|---|---|---|---|---|---|
| wk1-2 heuristic | -3.8 / 5.1 | -10.0 / 13.7 | -10.3 / 10.8 | -11.1 / 11.1 | -4.1 / 4.7 |
| wk3 layered+FFC | +0.1 / 7.2 | -0.6 / 9.6 | -1.1 / 8.1 | -6.1 / 9.8 | -9.0 / 9.3 |

So the layered model removed most of the average chalk bias in wk3. The misses that remain are
individual players, mostly the FFC cliff. Also, **RB was not healthy in wk1-2**: its chalk gap
(-10.0) matched WR's. The first pass's "RB shape looks fine" came from one spot-check at the top of
the RB list (Henry/Swift). The Step 5 correlation for RB is weaker (-0.11 vs WR -0.28) because RB
chalk misses cost less in points, not because RB ownership was calibrated.

**What still stands from the first pass:** we under-owned field chalk at WR/TE in all three weeks,
and that under-ownership correlates with points (Step 5). The Amon-Ra/Lamb numbers are correct. The
code path is what changed: wk1-2 = chalk_score inputs plus a flat top end, wk3 = FFC listing
cliff. A temperature refit alone would not have fixed most of these.

#### 4b. QB and DST checked directly (was "unconfirmed")

- **QB, wk1-2:** stored ownership matches softmax T=14 exactly, and the shape is fine (chalk gap
  -3.8, MAE 5.1, lowest of any position). The QB misses are chalk_score ranking of cheap QBs:
  Tyler Shough wk1 main chalk 76.7 (rank 9) → 3.3% vs 11.2% field; Carson Wentz wk2 72.5 → 2.0% vs
  10.3%; Baker Mayfield wk2 early rank 4 → 6.8% vs 19%. Tag: **bad signal (chalk_score inputs)**.
  Not the temperature.
- **QB, wk3:** Tyler Shough 3.9% vs 16.8% (se3max) is the FFC-unlisted cliff (unlisted, `l_ffc`
  -0.89). Josh Allen, who is listed, was 20.3% vs 12.2%, i.e. over-owned. Tag: **bad signal (FFC
  cliff)**.
- **DST, wk1-2:** matches global T=15 exactly, shape fine (gap -4.1, MAE 4.7). The miss is the
  field's min-price DST: Jets wk1 ($2,500, chalk rank 8-9) 4.4-5.4% vs 15-17%. Tag: **bad signal
  (chalk_score doesn't reward the cheapest viable DST)**.
- **DST, wk3:** MAE doubled to 9.3. Titans ($2,400, chalk 58.1, rank 8) 7.8% vs 23-29%, Vikings
  16% vs 36%. Same min-price pattern as Jets wk1, now inside the layered model. Tag: **bad signal
  (same cheap-DST ranking issue, recurring wk1 → wk3)**.

#### 4c. Aaron Jones wk2, diagnosed

Our wk2 file: $5,100, projection **6.08**, 6.6 rush att, 1.2 targets, season_avg 5.89 on
`games_played=1`, chalk rank 23, ownership 2.9%. Field 20-25%, actual 13.5 DK pts. Jordan Mason
(same team) was **OUT** in the same file: projection zeroed, but his 7.55 projected rush attempts
were not given to anyone.

Cause, two parts, both verified in the file and code:
1. **Season rollover to a 1-game sample.** In wk1 our file had Jones at season_avg 9.94 over 12
   (2025) games → 10.3 projection, 11.2 rush att. By wk2 season_avg was his single 2026 game (a
   split with Mason). His projection dropped 41% on one game of evidence.
2. **An OUT teammate's volume is not reallocated.** The in-week backup boost in
   `statline_model.py` (A4 path) only sets `participation_effective = 1.0` for a depth-chart #2
   whose starter is OUT. Jones was already at 1.0, so that path can't raise his share of team
   volume. Mason's carries disappeared with him.

In wk3 (2 games, Mason still OUT) our projection was back to 13.3 with 11.4 rush att. The model
caught up one week late. Tag: **bad signal (projection inputs: small-sample season_avg plus no
vacated-volume reallocation)**. This is a projection/pipeline issue, not ownership. It fits the
checklist §0 pattern: "low projection, heavy real usage, explainable by an OUT teammate we did
have."

#### 4d. Was the signal acted on? (gmscott81 submitted-lineup check)

For every flag, `my entries` below is how many of gmscott81's entries on that slate rostered the
player (one number per slate variant in the order listed).

**Signal there, lineup didn't use it: 20 player-slate rows, 12 unique players, every week.**
Drivers: Chris Olave (wk1 early/main, wk2 early), Dallas Goedert and Ashton Jeanty (wk1), Zay Flowers
(wk1), CeeDee Lamb, JSN, Dak Prescott, Panthers DST (wk2 afternoon/se3max), Jahmyr Gibbs (wk3 early),
Garrett Wilson (wk3 se3max). Killers rostered despite a weak projection: Kenny Gainwell (wk1),
Khalil Shakir (wk3, 1/1 se3max and 4/20 MME).

Rigor check. You can't roster every strong projection, so I compared against the base rate. On
SE/single-entry slates, strong-projection players (z >= 1, field >= 5%) that did **not** end up
flagged were rostered **45%** of the time (39/86). Strong-projection players who became **cash
drivers** were rostered **6%** of the time (1/18). Fisher exact p = 0.001. Rows aren't fully
independent (about 12 unique players), but the gap is too large to be an artifact. We weren't
fading chalk in general either: unflagged strong-projection players with field >= 15% were rostered
56% of the time. What separated the drivers from the rest isn't visible in these columns.

This clears the checklist's 2+ recurrence bar several times over. **Candidate workstream: "signal
legibility / selection."** Why do strong-projection players who go on to cash rarely make the
submitted lineup? Possible causes are construction settings, pool review, or manual picks. Flagged,
not started.

**Josh Allen (the §0 precedent).** A wk3 killer on all three variants (-17 to -20pt). Our projection
had him highest of any QB (27.6, z 2.44, 23% modeled ownership). He was rostered in the SE3max
entry and 5/20 MME entries. From the model's side this is **bad signal, acted on**. If the pre-lock
human flag was the correct call, it's a human signal overridden by the model's number. The pre-lock
chat flag itself was not re-derived (transcripts aren't reliably available). This is an accepted
gap. The lineup data above is the operational proxy.

#### 4d-2. Row-level root-cause counts, corrected (2026-09-28)

The unique-player table above collapses multi-slate-variant players into "+mixed" annotations,
which understates the real counts. Row-level (160 flags, one row per slate-variant, no collapsing):

| drivers (80 rows) | n | % | killers (80 rows) | n | % |
|---|---|---|---|---|---|
| no signal (neutral projection) | 35 | 44% | good signal followed (correctly faded) | 30 | 38% |
| bad signal (projected below pos mean) | 21 | 26% | bad signal (projected strong, busted) | 28 | 35% |
| good signal ignored/overridden | 17 | 21% | no signal (neutral) | 19 | 24% |
| good signal followed | 7 | 9% | good signal ignored/overridden | 3 | 4% |

Reading this straight: the killer side is not as bad as the driver side — we correctly fade a bust
(38%) more often than we chase one (35%), and we almost never keep rostering something our own
projection is actively warning us about (4%). The driver side is worse: only 9% of cash drivers
were both correctly flagged by our projection AND actually rostered; 21% were correctly flagged and
NOT rostered (the "signal legibility" gap — see Step 4d); the remaining 70% (no signal + bad signal)
means most cash drivers looked average-or-worse in our own projection beforehand, which is either
real unpredictable variance or a missing feature — not yet known which.

**User discussion, 2026-09-28:** raised that this isn't just a signal-quality question — busts and
misses are reportedly making it into submitted lineups regularly (real observed losses, not just
this backtest), which points at salary tier / role clustering of the misses that actually get
rostered, not just whether a signal existed in the abstract. **Logged as its own parking-lot item**
in `WK3_POSTMORTEM_CHECKLIST.md` (driver-side signal coverage + killer-side bust base rate +
salary/role clustering of misses that make it into real lineups) — this needs a dedicated session,
not a Phase 2 sub-task. It is a signal-quality-and-selection question, not the construction-shape
question Phase 2 is scoped to answer.

#### 4e. Per-player tables (all 92)

Columns: slates = variants flagged in; field% / lift = range across those; our own% = max; proj z =
mean; my entries = gmscott81 entries per variant; ownership mechanism only shown where under-owned
>= 10pt (number in parentheses = chalk_score rank within position).

**Drivers**

| wk | player | pos | $ | slates | field% | lift pt | our own% | proj z | my entries | four-way | root cause | ownership mechanism | stack split |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| wk1 | ashton jeanty | RB | 6600 | afternoon,main | 10-37 | +14..+24 | 10.6 | 0.72 | 0/0 | both hit | good signal ignored/overridden; no signal (neutral projection) | chalk_score rank (6) | standalone |
| wk1 | chris olave | WR | 6700 | early,main | 28 | +18..+20 | 10.8 | 1.62 | 0/0 | both hit | good signal ignored/overridden | chalk_score rank (11); chalk_score rank (5) | pairing-driven; standalone |
| wk1 | christian watson | WR | 5900 | afternoon | 20 | +30 | 22.4 | 0.80 | 0 | both hit | no signal (neutral projection) |  | standalone |
| wk1 | dallas goedert | TE | 4100 | afternoon,main | 11-26 | +12..+13 | 16.4 | 1.70 | 0/0 | both hit | good signal ignored/overridden |  | standalone |
| wk1 | dandre swift | RB | 6100 | early,main | 10-19 | +14..+22 | 13.2 | 0.36 | 0/0 | both missed | no signal (neutral projection) |  | standalone |
| wk1 | derrick henry | RB | 6700 | main | 7 | +22 | 19.4 | 0.89 | 0 | we hit / field missed | no signal (neutral projection) |  | standalone |
| wk1 | devaughn vele | WR | 3500 | early,main | 11-15 | +16..+17 | 0.7 | -1.23 | 0/0 | both missed | bad signal (projection below pos mean) | chalk_score rank (45); chalk_score rank (69) | pairing-driven; standalone |
| wk1 | jalen coker | WR | 4600 | early,main | 8-12 | +35..+36 | 6.9 | 0.23 | 0/0 | both missed | no signal (neutral projection) |  | standalone |
| wk1 | jordan love | QB | 5700 | afternoon | 5 | +22 | 9.8 | -0.39 | 0 | both missed | bad signal (projection below pos mean) |  | pairing-driven |
| wk1 | lamar jackson | QB | 6800 | main | 6 | +15 | 7.2 | 0.04 | 0 | both missed | no signal (neutral projection) |  | pairing-driven |
| wk1 | raiders | DST | 2900 | afternoon | 18 | +20 | 17.4 | 0.98 | 1 | both hit | no signal (neutral projection) |  | n/a (DST or no team) |
| wk1 | tyler shough | QB | 5600 | early,main | 11-15 | +31..+33 | 5.4 | 0.39 | 0/0 | both missed | no signal (neutral projection) |  | pairing-driven |
| wk1 | zay flowers | WR | 6400 | main | 10 | +16 | 12.6 | 1.99 | 0 | we hit / field missed | good signal ignored/overridden |  | standalone |
| wk2 | aaron jones | RB | 5100 | main_se3max,main_mme | 20-25 | +14 | 2.9 | -0.88 | 0/0 | field hit / we missed | bad signal (projection below pos mean) | chalk_score rank (23) | standalone |
| wk2 | brock purdy | QB | 6200 | main_mme | 11 | +10 | 7.5 | 1.61 | 5 | we hit / field missed | good signal followed |  | standalone |
| wk2 | bryce young | QB | 5400 | main_se3max,main_mme | 5-6 | +7..+10 | 2.7 | 0.77 | 0/0 | both missed | no signal (neutral projection) |  | standalone |
| wk2 | ceedee lamb | WR | 7300 | afternoon,main_se3max,main_mme | 18-37 | +18..+38 | 24.4 | 2.04 | 0/0/4 | both hit | good signal followed; good signal ignored/overridden | softmax cap (chalk rank<=3) | standalone |
| wk2 | chris olave | WR | 7200 | early | 5 | +26 | 5.2 | 1.54 | 0 | we hit / field missed | good signal ignored/overridden |  | standalone |
| wk2 | dak prescott | QB | 6400 | afternoon,main_se3max,main_mme | 12-21 | +21..+35 | 23.7 | 1.42 | 0/0/5 | we hit / field missed | good signal followed; good signal ignored/overridden |  | pairing-driven |
| wk2 | dalton schultz | TE | 3200 | early,main_se3max,main_mme | 21-24 | +35..+45 | 6.9 | 0.28 | 0/0/0 | field hit / we missed | no signal (neutral projection) | chalk_score rank (5); softmax cap (chalk rank<=3) | standalone |
| wk2 | devonta smith | WR | 6800 | early | 8 | +27 | 3.7 | 0.28 | 0 | both missed | no signal (neutral projection) |  | standalone |
| wk2 | garrett wilson | WR | 6000 | main_mme | 13 | +10 | 2.6 | 0.62 | 0 | both missed | no signal (neutral projection) | chalk_score rank (38) | standalone |
| wk2 | jake ferguson | TE | 3800 | afternoon | 12 | +26 | 10.6 | -0.09 | 0 | both missed | bad signal (projection below pos mean) |  | standalone |
| wk2 | jamarr chase | WR | 7600 | early,main_se3max,main_mme | 11-20 | +10..+26 | 5.5 | -0.05 | 0/0/0 | both missed | bad signal (projection below pos mean); no signal (neutral projection) | chalk_score rank (17) | standalone |
| wk2 | jaxon smithnjigba | WR | 8100 | afternoon,main_se3max,main_mme | 9-35 | +18..+33 | 6.9 | 2.28 | 0/0/5 | we hit / field missed | good signal followed; good signal ignored/overridden | chalk_score rank (17) | standalone |
| wk2 | panthers | DST | 2700 | early,main_se3max | 5-7 | +27..+35 | 10.8 | 1.53 | 0/0 | we hit / field missed | good signal ignored/overridden |  | n/a (DST or no team) |
| wk2 | patriots | DST | 3100 | main_se3max | 5 | +18 | 3.8 | 0.53 | 0 | both missed | no signal (neutral projection) |  | n/a (DST or no team) |
| wk2 | raiders | DST | 2600 | afternoon | 6 | +15 | 0.9 | -0.67 | 0 | both missed | bad signal (projection below pos mean) |  | n/a (DST or no team) |
| wk2 | stefon diggs | WR | 5300 | main_se3max,main_mme | 9-10 | +12..+14 | 6.6 | 0.65 | 0/5 | both missed | no signal (neutral projection) |  | standalone |
| wk3 | brock bowers | TE | 6600 | afternoon | 5 | +21 | 0.5 | 0.29 | 0 | both missed | no signal (neutral projection) |  | standalone |
| wk3 | brock purdy | QB | 6500 | main_se3max,main_mme | 6-7 | +15..+17 | 4.5 | 0.96 | 0/2 | both missed | no signal (neutral projection) |  | standalone |
| wk3 | garrett wilson | WR | 6300 | main_se3max,main_mme | 24-30 | +20..+22 | 19.9 | 1.14 | 0/2 | both hit | good signal followed; good signal ignored/overridden |  | standalone |
| wk3 | geno smith | QB | 4900 | early,main_se3max,main_mme | 5-9 | +46..+53 | 1.5 | -0.71 | 0/0/0 | both missed | bad signal (projection below pos mean) |  | pairing-driven; standalone |
| wk3 | george kittle | TE | 4800 | afternoon,main_se3max,main_mme | 7-24 | +23..+24 | 19.9 | 0.55 | 0/0/2 | both missed | no signal (neutral projection) |  | standalone |
| wk3 | isaiah williams | WR | 3300 | early,main_se3max,main_mme | 5-8 | +18..+24 | 1.9 | -1.15 | 0/0/2 | both missed | bad signal (projection below pos mean) |  | pairing-driven; standalone |
| wk3 | jahmyr gibbs | RB | 8800 | early,main_se3max,main_mme | 25-29 | +27..+31 | 52.6 | 2.48 | 0/1/4 | both hit | good signal followed; good signal ignored/overridden |  | standalone |
| wk3 | jaylen warren | RB | 5700 | early,main_se3max,main_mme | 10-12 | +24..+31 | 14.1 | 0.01 | 1/0/2 | both missed | bad signal (projection below pos mean); no signal (neutral projection) |  | standalone; thin subset (<20) |
| wk3 | juwan johnson | TE | 3700 | afternoon,main_se3max,main_mme | 6-23 | +25..+34 | 12.9 | -0.47 | 0/0/1 | both missed | bad signal (projection below pos mean) |  | standalone |
| wk3 | kenyon sadiq | TE | 3500 | early,main_se3max | 7 | +41..+47 | 1.4 | -0.90 | 0/0 | both missed | bad signal (projection below pos mean) |  | standalone |
| wk3 | michael wilson | WR | 5200 | afternoon | 9 | +34 | 20.3 | 0.39 | 0 | we hit / field missed | no signal (neutral projection) |  | standalone |
| wk3 | titans | DST | 2400 | main_mme | 23 | +13 | 7.8 | 0.40 | 7 | field hit / we missed | no signal (neutral projection) | FFC-unlisted cliff | n/a (DST or no team) |
| wk3 | tyler shough | QB | 5400 | main_se3max,main_mme | 13-17 | +24..+25 | 3.9 | 0.20 | 0/0 | both missed | no signal (neutral projection) | FFC-unlisted cliff | standalone |
| wk3 | vikings | DST | 3100 | afternoon | 36 | +17 | 16.0 | 0.89 | 1 | both hit | no signal (neutral projection) | FFC-unlisted cliff | n/a (DST or no team) |

**Killers**

| wk | player | pos | $ | slates | field% | lift pt | our own% | proj z | my entries | four-way | root cause | ownership mechanism | stack split |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| wk1 | baker mayfield | QB | 5900 | main | 7 | -15 | 6.9 | 0.59 | 0 | neither heavy (minor-owned killer) | no signal (neutral projection) |  | standalone |
| wk1 | chargers | DST | 3500 | afternoon | 29 | -12 | 31.1 | 0.96 | 0 | both trapped | no signal (neutral projection) |  | n/a (DST or no team) |
| wk1 | devon achane | RB | 7000 | main | 18 | -11 | 1.3 | -0.31 | 0 | field trapped / we avoided | good signal followed | chalk_score rank (29) | standalone |
| wk1 | emeka egbuka | WR | 6200 | main | 7 | -13 | 5.8 | -0.55 | 0 | neither heavy (minor-owned killer) | good signal followed |  | standalone |
| wk1 | jamarr chase | WR | 7800 | main | 32 | -15 | 16.2 | 2.14 | 0 | both trapped | bad signal (projected strong, busted) | softmax cap (chalk rank<=3) | standalone |
| wk1 | james cook | RB | 7200 | early | 5 | -17 | 5.4 | -0.05 | 0 | neither heavy (minor-owned killer) | good signal followed |  | standalone |
| wk1 | jayden reed | WR | 4900 | afternoon | 9 | -10 | 6.5 | -0.60 | 0 | neither heavy (minor-owned killer) | good signal followed |  | standalone |
| wk1 | joe burrow | QB | 6900 | early,main | 12-19 | -22..-20 | 16.7 | 1.18 | 0/0 | both trapped | bad signal (projected strong, busted) |  | standalone |
| wk1 | jordan addison | WR | 5800 | afternoon | 10 | -14 | 13.9 | -0.41 | 0 | neither heavy (minor-owned killer) | good signal followed |  | standalone |
| wk1 | justin herbert | QB | 6100 | main | 12 | -11 | 10.1 | 1.90 | 0 | we trapped / field avoided | bad signal (projected strong, busted) |  | standalone |
| wk1 | kenny gainwell | RB | 5200 | early | 6 | -17 | 13.5 | 0.26 | 1 | neither heavy (minor-owned killer) | good signal ignored/overridden |  | standalone |
| wk1 | kyle pitts | TE | 4700 | early | 7 | -17 | 3.5 | 1.14 | 1 | we trapped / field avoided | bad signal (projected strong, busted) |  | standalone |
| wk1 | kyler murray | QB | 5500 | afternoon,main | 7-20 | -13..-12 | 11.4 | -0.75 | 0/0 | field trapped / we avoided | good signal followed |  | standalone |
| wk1 | marshawn lloyd | RB | 4800 | main | 8 | -11 | 0.0 | -1.68 | 0 | neither heavy (minor-owned killer) | good signal followed |  | thin subset (<20) |
| wk1 | quentin johnston | WR | 4700 | afternoon | 29 | -11 | 8.2 | 0.14 | 0 | field trapped / we avoided | good signal followed | chalk_score rank (14) | standalone |
| wk1 | saquon barkley | RB | 6900 | main | 23 | -10 | 7.5 | 0.39 | 0 | field trapped / we avoided | good signal followed | chalk_score rank (10) | standalone |
| wk1 | tee higgins | WR | 6300 | main | 10 | -12 | 6.2 | 0.44 | 0 | neither heavy (minor-owned killer) | good signal followed |  | standalone |
| wk1 | tony pollard | RB | 5600 | early | 10 | -16 | 2.1 | 0.23 | 0 | neither heavy (minor-owned killer) | good signal followed |  | thin subset (<20) |
| wk2 | baker mayfield | QB | 5600 | main_se3max,main_mme | 7-10 | -13 | 3.4 | 0.54 | 0/0 | neither heavy (minor-owned killer) | no signal (neutral projection) |  | standalone |
| wk2 | caleb williams | QB | 6800 | early,main_se3max,main_mme | 10-18 | -21..-16 | 15.7 | 1.18 | 1/0/6 | we trapped / field avoided | bad signal (projected strong, busted) |  | standalone |
| wk2 | carson wentz | QB | 4600 | main_se3max,main_mme | 8-10 | -16..-13 | 2.0 | -0.95 | 0/0 | neither heavy (minor-owned killer) | good signal followed |  | pairing-driven |
| wk2 | colston loveland | TE | 5000 | main_se3max,main_mme | 9-11 | -18..-16 | 4.1 | -0.53 | 0/0 | neither heavy (minor-owned killer) | good signal followed |  | standalone |
| wk2 | dallas goedert | TE | 4800 | early,main_se3max,main_mme | 9-18 | -17..-15 | 3.3 | 0.90 | 0/0/0 | neither heavy (minor-owned killer) | no signal (neutral projection) | chalk_score rank (9) | standalone |
| wk2 | david montgomery | RB | 6500 | main_se3max,main_mme | 11-12 | -14..-13 | 12.2 | 0.53 | 0/3 | neither heavy (minor-owned killer) | no signal (neutral projection) |  | standalone |
| wk2 | emeka egbuka | WR | 6400 | main_se3max,main_mme | 12-15 | -13 | 3.9 | 0.68 | 0/1 | neither heavy (minor-owned killer) | no signal (neutral projection) | chalk_score rank (18) | standalone |
| wk2 | justin herbert | QB | 6000 | afternoon | 6 | -19 | 7.9 | 0.50 | 0 | neither heavy (minor-owned killer) | no signal (neutral projection) |  | standalone |
| wk2 | justin jefferson | WR | 7800 | main_se3max,main_mme | 19-21 | -17..-14 | 5.7 | 1.78 | 0/5 | both trapped | bad signal (projected strong, busted) | chalk_score rank (12) | standalone |
| wk2 | kalif raymond | WR | 3600 | early | 7 | -16 | 11.1 | 1.31 | 1 | we trapped / field avoided | bad signal (projected strong, busted) |  | standalone |
| wk2 | ladd mcconkey | WR | 6200 | afternoon | 8 | -18 | 9.4 | 1.07 | 0 | we trapped / field avoided | bad signal (projected strong, busted) |  | standalone |
| wk2 | luther burden | WR | 5700 | main_se3max,main_mme | 10-13 | -16..-14 | 8.4 | 0.80 | 0/6 | neither heavy (minor-owned killer) | no signal (neutral projection) |  | standalone |
| wk2 | michael wilson | WR | 5400 | afternoon | 5 | -15 | 3.1 | 0.00 | 0 | neither heavy (minor-owned killer) | good signal followed |  | standalone |
| wk2 | mike evans | WR | 6600 | afternoon | 24 | -13 | 15.0 | 1.13 | 0 | both trapped | bad signal (projected strong, busted) |  | standalone |
| wk2 | mike gesicki | TE | 3600 | early | 9 | -20 | 5.3 | 1.80 | 0 | we trapped / field avoided | bad signal (projected strong, busted) |  | thin subset (<20) |
| wk2 | rome odunze | WR | 5500 | early,main_se3max,main_mme | 5-9 | -17..-15 | 10.6 | -0.18 | 0/0/0 | neither heavy (minor-owned killer) | good signal followed |  | standalone |
| wk2 | trevor lawrence | QB | 5800 | afternoon | 14 | -18 | 5.6 | 0.36 | 0 | neither heavy (minor-owned killer) | good signal followed |  | standalone |
| wk3 | bryce young | QB | 5600 | main_se3max,main_mme | 8 | -19..-17 | 5.5 | -0.31 | 0/0 | neither heavy (minor-owned killer) | good signal followed |  | standalone |
| wk3 | cardinals | DST | 2300 | afternoon | 5 | -19 | 8.9 | -1.46 | 0 | neither heavy (minor-owned killer) | good signal followed |  | n/a (DST or no team) |
| wk3 | dalton kincaid | TE | 5500 | early,main_se3max,main_mme | 14-21 | -19..-17 | 7.3 | 1.23 | 0/0/2 | we trapped / field avoided | bad signal (projected strong, busted) | FFC-unlisted cliff | standalone |
| wk3 | david montgomery | RB | 6000 | main_se3max,main_mme | 9-10 | -16..-14 | 1.0 | -0.66 | 0/0 | neither heavy (minor-owned killer) | good signal followed |  | standalone |
| wk3 | ers | DST | 3600 | afternoon | 14 | -18 | 11.3 | 0.68 | 0 | neither heavy (minor-owned killer) | no signal (neutral projection) |  | n/a (DST or no team) |
| wk3 | isaiah likely | TE | 4700 | early | 5 | -16 | 3.0 | 0.60 | 0 | neither heavy (minor-owned killer) | no signal (neutral projection) |  | standalone |
| wk3 | jonathan taylor | RB | 7600 | main_se3max,main_mme | 5-8 | -15..-14 | 19.0 | 1.06 | 0/3 | we trapped / field avoided | bad signal (projected strong, busted) |  | standalone; thin subset (<20) |
| wk3 | josh allen | QB | 8000 | early,main_se3max,main_mme | 12-20 | -20..-17 | 23.2 | 2.44 | 0/1/5 | we trapped / field avoided | bad signal (projected strong, busted) |  | standalone |
| wk3 | justin jefferson | WR | 7500 | afternoon,main_se3max,main_mme | 6-18 | -20..-18 | 22.5 | 1.48 | 1/0/1 | we trapped / field avoided | bad signal (projected strong, busted) |  | standalone |
| wk3 | khalil shakir | WR | 4800 | main_se3max,main_mme | 5-6 | -18..-16 | 5.1 | -0.05 | 1/4 | neither heavy (minor-owned killer) | good signal ignored/overridden |  | standalone |
| wk3 | kyler murray | QB | 5100 | afternoon | 9 | -22 | 2.6 | -0.66 | 0 | neither heavy (minor-owned killer) | good signal followed |  | standalone |
| wk3 | lamar jackson | QB | 7500 | afternoon,main_se3max,main_mme | 6-15 | -21..-14 | 26.6 | 1.43 | 0/0/2 | we trapped / field avoided | bad signal (projected strong, busted) |  | standalone |
| wk3 | tetairoa mcmillan | WR | 6000 | early,main_se3max,main_mme | 10-18 | -16..-14 | 13.2 | 0.60 | 0/0/3 | neither heavy (minor-owned killer) | no signal (neutral projection) |  | standalone |
| wk3 | treveyon henderson | RB | 5200 | early,main_se3max,main_mme | 6-9 | -16..-13 | 0.7 | -1.19 | 0/0/0 | neither heavy (minor-owned killer) | good signal followed |  | standalone; thin subset (<20) |

Threads across the per-player tags:
- **Cheap pass-catchers and cheap QBs that hit** make up most of the driver-side "bad signal"
  list: Vele $3.5K, Isaiah Williams $3.3K, Sadiq $3.5K, Juwan Johnson $3.7K, Ferguson $3.8K, Geno
  $4.9K, Love $5.7K. These match the Step 5 finding that the miscalibration that matters for points
  sits in the cheapest band.
- **Our high-projection QBs busting** is the dominant killer-side "bad signal": Burrow wk1,
  Herbert wk1, Caleb Williams wk2, Allen and Lamar wk3. This is on the projection side. The first
  pass's ownership framing missed it entirely.

### Step 5: structural checks (bias check kept; salary stratification added)

Bias check, reproduced: corr(our ownership minus field%, actual FPTS) = **-0.179** across 2,632
matched rows. By position: WR -0.28, TE -0.24, QB -0.12, RB -0.11, DST -0.05. Same as the first
pass.

**Salary stratification.** Fixed per-position bands (low / mid-low / mid-high / high): WR <$4.5K /
4.5-6K / 6-7.5K / 7.5K+; TE <$3.5K / 3.5-4.5K / 4.5-6K / 6K+; RB <$5K / 5-6.5K / 6.5-8K / 8K+; QB
<$5.5K / 5.5-6.5K / 6.5-7.5K / 7.5K+; DST <$2.8K / 2.8-3.2K / 3.2-3.6K / 3.6K+. Rows with field
>= 2% (players the field actually used).

| corr(gap, FPTS) | low | mid-low | mid-high | high |
|---|---|---|---|---|
| all positions | **-0.20** (n=203) | -0.06 (402) | -0.09 (235) | +0.16 (74) |
| WR+TE | **-0.36** (96) | -0.09 (206) | -0.11 (120) | -0.08 (37) |
| WR | **-0.30** (73) | -0.09 (139) | -0.19 (86) | -0.08 (28) |
| TE | **-0.36** (23) | -0.10 (67) | +0.32 (34) | -0.23 (9) |
| QB+RB+DST | -0.11 (107) | -0.11 (196) | -0.09 (115) | +0.34 (37) |

Mean gap (ours minus field) is roughly uniform across bands: -1.4 to -4.1pt for WR, -2.2 to -2.8pt
overall. So **we under-own about equally at every price, but the under-ownership that costs points
is concentrated in the cheapest band**, most sharply at WR/TE (-0.36 vs about -0.1 elsewhere). The
high band flips positive for QB/RB/DST (+0.34, n=37): expensive players we over-owned who then
underperformed. That's the Allen/Lamar/JT killer pattern from Step 4. wk3-only high band: +0.37.
High-band n is small, so read that sign as directional.

Robustness: within-position salary *quartiles of the full pool* put nearly every field-relevant
player in Q3-Q4 (DK pools are dominated by min-price backups), so that cut isn't informative
(WR+TE Q3 -0.23, Q4 -0.09). The fixed bands above are the primary result.

**Status, 2026-09-28: no new action this session.** This finding was already flagged in the first
pass and confirmed here with the salary cut. No fix is in motion for it specifically. **Logged as a
priority pointer** in `WK3_POSTMORTEM_CHECKLIST.md`'s Parking Lot — when the standing ownership
refit (checklist §4) happens, prioritize the cheap band specifically rather than treating all
salary tiers as equally in need of the fix, since that's where the miscalibration actually costs
points.

Position/role tagging: per-flag position, salary and projection rank are in the flags CSV and the
Step 4 tables.

### Step 6: cross-week consistency (closed out)

Side-by-side by week, from the Step 3/4 tables above:

- **wk1:** Chris Olave (WR), Juwan Johnson (TE), Jets DST flagged.
- **wk2:** Dalton Schultz (TE), Ja'Marr Chase (WR), Garrett Wilson (WR), Aaron Jones (RB), Jaxon
  Smith-Njigba (WR), Terry McLaurin (WR) flagged.
- **wk3:** Chris Olave (WR, repeat from wk1), Devaughn Vele (WR), Titans DST, Tyler Shough (QB)
  flagged.

The recurring thread is **position (WR/TE), not a specific player or team** — Chris Olave repeating
in wk1 and wk3 is the only literal same-player repeat, and it's the same WR softmax mechanism
hitting him twice independently, not evidence of a player-specific bug. Every week has at least 2
WR flags and at least 1 TE flag; the softmax root cause in Step 4 was fit once (on 2 slates,
pre-wk1) and never retuned, so it has been silently under-pricing WR/TE chalk in the SAME direction
for all three weeks running — this is the "shared root cause, not three unrelated bugs" the
checklist's §0 suspected, at least for the portion of the misses that flow through the ownership
model.

_Note (2026-09-28 rework): Step 6 is kept as written. Its mechanism wording ("same WR softmax mechanism") is superseded by Step 4a: wk1-2 misses trace mainly to chalk_score ranking, wk3 to the FFC-unlisted cliff. The cross-week position pattern it describes still holds._

## Phase 1 status (rework complete 2026-09-28)

All six rework items are done and verified against real output. Nothing is blocked:
1. Step 2 caps + killers: done (5/5 early/afternoon, 10/10 main, all 11 slates).
2. Step 2 stack-pairing split: done (correct with/without-partner definition).
3. Step 2 snowflake: done (cross-variant, same week). The outcome-identity caveat is noted above.
4. Step 3 four-way: rebuilt. Killer variant justified from the data, not forced.
5. Step 4 per-player root cause: all 92 tagged. QB/DST checked directly, Aaron Jones diagnosed,
   gmscott81 lineup check done. Josh Allen pre-lock chat not re-derived (accepted gap).
6. Step 5 salary stratification: done, overall and WR/TE.

Findings that change or add to the first-pass headline:
- **Mechanism correction:** the wk3 WR cliff (Amon-Ra 38% vs Lamb 5%) is the FFC-unlisted
  penalty in `ownership_model.py`, not the softmax temperature. Wk1-2 misses are mostly
  chalk_score *ranking*, with the softmax top-end cap as a secondary (TE, top-3 WR) factor. The
  under-ownership plus points correlation stands. A temperature-only refit would not fix it.
- **Signal not acted on:** strong-projection players who became cash drivers were rostered 1/18
  times on SE slates, vs 39/86 for strong-projection players who didn't (p = 0.001). This recurs
  every week and is the candidate "signal legibility / selection" workstream.
- **Projection-side misses the first pass didn't see:** our top-projected QBs busting (Allen,
  Lamar, Burrow, Herbert, Caleb Williams), and cheap pass-catchers/QBs hitting from below the
  position mean. Both are consistent with the cheap-band concentration in Step 5.
- **Aaron Jones:** 1-game season_avg after rollover, plus no reallocation of an OUT teammate's
  volume. Projection pipeline, not ownership.
- **Recurring cheap-DST miss** (Jets wk1, Titans wk3): chalk_score doesn't capture the field's
  min-price DST preference.

Phase 2 (construction-level diagnostics) can start from these outputs. Fix work (ownership refit
incl. FFC-unlisted handling and chalk_score inputs; vacated-volume reallocation) belongs with the
standing pickup plan (checklist §4), not here.

## Phase 2 results (2026-09-28)

Script: `analysis/classic_diag/wk3_postmortem_phase2.py`. It imports Step 1 parsing from
`wk3_postmortem_phase1.py`, `load_entries` from `wk3_postmortem_phase1_v2.py`, and reads the Phase 1
outputs (`wk3_postmortem_v2_players.csv` for field%/salary/team, `wk3_postmortem_v2_flags.csv` for the
pairing-driven list). Outputs: `wk3_postmortem_phase2_chalk.csv`, `wk3_postmortem_phase2_shape.csv`,
`wk3_postmortem_phase2_pairs.csv`. It covers the same 11 slates, cash lines and gmscott81 matching as
Phase 1: 1 entry on each of the 9 SE/SE3max slates and 20 on each of the 2 MME slates, 49 entries total.

### Step 1: chalk baseline

**Method.** Take the top 5 players by real field ownership at each of QB/RB/WR/TE/DST. Enumerate
every valid DK classic lineup from that pool (QB, 2 RB, 3 WR, TE, FLEX from RB/WR/TE, DST, salary
<= $50,000), which gives 4.1K-26K lineups per slate. Report three things:
(a) the lineup with the highest total ownership ("chalk lineup");
(b) the same, but required to include a QB plus a same-team WR/TE;
(c) the cash rate across all valid top-5 lineups (the "chalk universe").
Each is scored with real DK points and ranked against the real field.

Caveat: this uses the post-lock field %Drafted, which isn't available before lock. That makes it a
hindsight upper bound on a "just play the chalk" strategy. A pre-lock version would have to use
projected ownership, and our ownership misses (Phase 1 Step 4a) would degrade it.

| slate | cash line | chalk pts | chalk rank (pctile) | chalk cashed | chalk-universe cash rate | my best pts | my best rank (pctile) | my cashes |
|---|---|---|---|---|---|---|---|---|
| wk1_early | 170.1 | 168.7 | 1465 (27%) | no (1.4 short) | 23% | 119.9 | 4727 (86%) | 0/1 |
| wk1_afternoon | 134.8 | 128.5 | 1586 (33%) | no | 50% | 117.1 | 2487 (53%) | 0/1 |
| wk1_main | 160.9 | 157.0 | 4658 (29%) | no | 21% | 119.9 | 12406 (78%) | 0/1 |
| wk2_early | 116.5 | 112.5 | 1467 (31%) | no | 19% | 96.8 | 2741 (58%) | 0/1 |
| wk2_afternoon | 136.0 | 144.8 | 621 (13%) | **yes** | 33% | 115.8 | 3035 (64%) | 0/1 |
| wk2_main_se3max | 132.9 | 137.5 | 3206 (20%) | **yes** | 34% | 119.3 | 6544 (41%) | 0/1 |
| wk2_main_mme | 134.6 | 137.5 | 21050 (19%) | **yes** | 23% | 168.1 | 2795 (3%) | **6/20** |
| wk3_early | 137.9 | 155.0 | 506 (11%) | **yes** | 24% | 130.1 | 1621 (34%) | 0/1 |
| wk3_afternoon | 146.0 | 131.8 | 2370 (50%) | no | 17% | 121.3 | 3325 (70%) | 0/1 |
| wk3_main_se3max | 145.3 | 166.0 | 1191 (8%) | **yes** | 39% | 122.4 | 9111 (58%) | 0/1 |
| wk3_main_mme | 146.0 | 160.2 | 8669 (10%) | **yes** | 13% | 188.1 | 593 (1%) | **2/20** |

On the 9 SE slates:
- The chalk lineup cashed on **4 of 9** slates. Our submitted entry cashed on **0 of 9**.
- The chalk lineup outscored our entry on **9 of 9** slates, by **+26.6 pts** on average.
- The chalk lineup never finished worse than the 50th percentile. Our entry averaged the 58th
  percentile, and 5 of our 9 entries finished below the field's median.
- Adding a required QB stack (b) gave the same lineup on 10 of 11 slates. On wk3_early it scored
  139.6 instead of 155.0 and still cashed.

The chalk universe (c) cashed at 28.7% on average across the SE slates, against a 25% base. So the
edge is mostly in the single highest-owned build, and the universe as a whole is only slightly
better than a random field entry.

On MME, our 20-entry pools had a better ceiling than the single chalk lineup: our best entry ranked
at the 3rd percentile in wk2 and the 1st in wk3. But our cash rate was 6/20 (30%) in wk2 and 2/20
(10%) in wk3, against a 22% base. The average of our 20 entries was 120.4 in wk2 and 117.0 in wk3,
both well below the chalk lineup's 137.5 and 160.2.

**Rigor read.** 4 of 9 against a 25% base rate is a binomial p of about 0.17, so the chalk lineup's
cash rate is **not** a statistically significant beat of base. 0 of 9 for our entries is p of about 0.075
against the 25% base, which is borderline, and has held for three straight weeks. The 9-of-9
head-to-head result is stronger: a sign test gives p = 0.002. Even so, the 9 slates share weeks and
players, so they aren't fully independent. Direction and magnitude are clear: **a naive,
hindsight-owned chalk build beat our SE entry on every slate by about 27 pts**. Our SE entries sit
below the field's median, not merely short of the cash line.

### Step 2: pool shape vs the cashing field

Each entry gets the following shape metrics:
- QB stack: the count of same-team WR/TE with the QB. `stack1` means at least 1, `stack2` means at
  least 2, and `naked` means no same-team RB/WR/TE at all.
- Bring-back: at least 1 player from the QB's opponent.
- DST conflict: the DST is facing one of our own players.
- Salary used.
- Studs: non-DST players at $7,000 or more.
- Punts: non-DST players at $4,000 or less.
- Summed field ownership.
- FLEX position, QB salary, and DST salary.

Opponents come from our projection file. In the table, "cash" and "noncash" are the field excluding
our own entries.

Pooled shape, SE slates (9) and MME slates (2):

| | SE cash field | SE noncash | **mine SE (9)** | MME cash field | MME noncash | **mine MME (40)** |
|---|---|---|---|---|---|---|
| QB + >=1 WR/TE stack | 81.7% | 78.2% | 100% | 79.3% | 75.5% | 100% |
| QB + >=2 WR/TE stack | **31.3%** | 23.7% | **22.2%** (2/9) | **29.6%** | 24.6% | **0%** (0/40) |
| naked QB | 13.5% | 15.9% | 0% | 15.5% | 18.6% | 0% |
| bring-back | 48.7% | 42.8% | 33% | 39.7% | 37.5% | **100%** |
| studs (>= $7K) | 1.99 | 1.77 | 2.00 | 2.18 | 1.86 | 2.00 |
| punts (<= $4K) | **1.06** | 0.87 | **0.44** | 1.13 | 0.86 | 0.95 |
| salary used | 49,864 | 49,833 | 49,889 | 49,865 | 49,833 | 49,853 |
| QB salary | **$5,851** | $6,052 | **$6,333** | **$5,845** | $6,083 | **$6,748** |
| DST salary | $2,885 | $2,981 | $3,044 | $2,824 | $2,990 | $2,850 |
| summed field own% | 167 | 154 | 213 | 123 | 108 | 108 |
| FLEX = TE | 26.7% | 21.1% | 66.7% | 32.9% | 24.2% | 32.5% |

Which shape features carried cash lift in the field? These are all non-gmscott81 entries, 275K in
total, pooled with a per-slate base-rate adjustment:

| feature value | 0 | 1 | 2 | 3+ |
|---|---|---|---|---|
| QB+WR/TE stack size, lift | -2.8pt | -0.7pt | **+3.7pt** | **+6.7pt** |
| studs, lift | **-15.4pt** | -8.0pt | +3.1pt | +6.2pt |
| punts, lift | **-8.9pt** | +2.1pt | +7.9pt | +8.6pt |
| bring-back players, lift | -1.0pt | +0.9pt | +4.0pt | +6.8pt |

Salary left on the table barely matters up to $500 (-0.6 to +0.5pt). Past $1,000 it costs -3.6 to
-12pt. All 49 of our entries left $500 or less, so salary use isn't a problem.

Reading this straight:
1. **Stack depth, not stack presence, is the gap.** We stack 100% of the time, which is more than
   the field. But QB+2 is where the field's lift starts (+3.7pt; +6.7 at QB+3). We built QB+2 in
   only 2/9 SE entries, both in wk3, and in **0/40 MME entries**. The cashing field was at about 30%
   in both formats. Every one of our 40 MME entries was the same template: QB+1, 1 bring-back. That
   looks like a construction-rule setting, not a player-level choice. Worth checking the MME stack
   config in the optimizer, but that fix is out of scope here.
2. **We pay up at QB; the cashing field goes cheap.** Our average QB salary is $6,333 on SE and
   $6,748 on MME. The cashing field averaged about $5,850, and the non-cashing field about $6,070. So
   ours is above even the losers. This is the construction-level face of Phase 1's Step 4 killer
   finding: our high-projection QBs bust (Allen $8,000 wk3 SE, Lamar, Burrow, Herbert, Caleb). And the
   QBs that cashed were cheap (Shough $5.4-5.6K, Geno $4.9K, Dak $6.4K).
3. **Too few punts on SE.** We averaged 0.44 punts per SE lineup against 1.06 in the cashing field.
   0 punts carries -8.9pt of lift in the field, and 5 of our 9 SE entries had 0 punts. This matches
   Phase 1 Step 5: the cheap band is where our miscalibration costs points, and Phase 1's cheap
   drivers were all under $4K (Sadiq, Isaiah Williams, Vele, Schultz, Juwan Johnson). On MME we
   were at 0.95, close to the field.
4. **Studs match the field.** We averaged 2.0 per lineup against 2.0-2.2 in the cashing field. The
   stud/punt imbalance is on the punt side only. We did it by spending mid-range, not by paying up
   for more studs.
5. **SE entries are more chalk-concentrated than the field** (summed ownership 213 vs 167 in the
   cashing field). But the chalk lineup in Step 1 still beat them, so the problem isn't "too
   chalky." It's which chalk: the Phase 1 "we trapped / field avoided" QBs and WRs.

Sample-size note: the field-side lifts come from n = 1.5K to 140K per bucket and are solid. Our
side is 9 SE entries plus 40 MME entries. The MME QB+2 = 0/40 and bring-back = 40/40 are
deterministic, not noise. The SE shape numbers (n = 9) are directional only.

### Step 3: Phase 1 pairing-driven stacks, did we build them?

For each Phase 1 pairing-driven row, we took the rate at which each group rostered the player plus
the partner (the stack itself). These come from `wk3_postmortem_phase2_pairs.csv`.

| slate | stack (X + partner) | cash field | noncash field | mine |
|---|---|---|---|---|
| wk1_early | Shough + Olave | 28.4% | 5.1% | 0/1 |
| wk1_early | Vele + Shough | 11.9% | 1.3% | 0/1 |
| wk1_afternoon | Love + Watson | 7.7% | 1.2% | 0/1 |
| wk1_main | Shough + Olave | 21.7% | 4.7% | 0/1 |
| wk1_main | Lamar + Flowers | 5.7% | 1.9% | 0/1 |
| wk2_afternoon | Dak + Lamb | 32.0% | 7.8% | 0/1 |
| wk2_main_se3max | Dak + Lamb | 25.7% | 2.1% | 0/1 |
| wk2_main_mme | Dak + Lamb | 23.0% | 2.0% | **2/20 (10%)** |
| wk3_early | Geno + G. Wilson | 24.7% | 1.5% | 0/1 |
| wk3_early / main_se3max | Geno + Isaiah Williams | 7.1% / 5.2% | 0.3% / 0.4% | 0/1, 0/1 |
| wk2 main (killer) | Wentz + Jefferson | 1.7-2.2% | 7.5-10.2% | 0/1, 0/20 |

We built the winning QB+WR1 stack **2 times out of 30 entry-opportunities** (10 SE entry-slate pairs + 20 MME entries on Dak+Lamb), both in wk2 MME. The cashing
field built it at 6-32%, typically about 5-15x the non-cashing field's rate. We also avoided the one
pairing-driven killer stack, Wentz+Jefferson.

This is consistent with Step 2: we stack at 100%, but on the wrong QBs. Our QBs were
higher-priced and higher-projected, and the winning stacks ran through cheap QBs: Shough, Geno,
Love, Dak. Phase 1 tagged most of those QBs as "no signal" or "bad signal" (Geno z -0.71, Shough z
0.2-0.4, Love z -0.39). So this is mostly a **player-input problem showing up in construction**, not
a stacking rule problem. The exception is Dak+Lamb (z 1.42 / 2.04), which appears in the Phase 1
"good signal ignored" list.

### What Phase 2 changes or confirms about the Phase 1 read

- **Confirms:** the biggest single construction signal (QB salary: ours about $500-900 above the
  cashing field) is the Phase 1 QB-projection problem. Our top-projected QBs bust, and the cheap QBs
  that hit sit below our position mean. It's not a separate construction bug.
- **Confirms:** too few punts on SE lines up with Phase 1 Step 5's cheap-band finding.
- **Adds, genuinely construction-level:**
  1. The **MME template is fixed at QB+1 with a bring-back** (40/40 entries). The field's cash
     lift sits at QB+2 and deeper, which we never build in MME. This is a settings finding, not a
     player-input one.
  2. A **hindsight chalk lineup beat our SE entry 9/9** (+26.6 pts mean). Our SE entries are below
     median, not near-misses. Because the chalk build uses post-lock ownership, this is an upper
     bound. It's a benchmark, not a recommended strategy.
- **Doesn't support:** salary left on the table, or stud count, as causes. Both match the cashing
  field.
- **Inconclusive at this n:** whether the chalk lineup's 4/9 cash rate genuinely beats base
  (p about 0.17), and all SE shape metrics (n = 9 entries). These are directional only.

Next steps, not started, for checklist §4 and the parking lot:
- MME stack-depth setting: allow or require QB+2 in some share of lineups.
- A pre-lock chalk benchmark that uses our projected ownership instead of real ownership, to test
  whether the 9/9 result survives without hindsight.
- A QB-price prior or check, tied to the Phase 1 QB-bust finding.

## Phase 2 status (complete 2026-09-28)

Both parts are done across all 11 slates: the chalk baseline and the pool-shape comparison, which
includes the Phase 1 pairing-driven stack check. Nothing is blocked. The fix work is listed in the
next steps above and is out of scope for this session.

## Session log

- 2026-09-28: Game plan finalized and agreed. File created. Phase 1 Step 1 to begin in a
  new session.
- 2026-09-28: Phase 1 Steps 1-3, 5 run across all 11 slates (wk1-3). Core finding: ownership-model
  gap vs. real field ownership correlates negatively with actual points, ~2x stronger at WR/TE than
  other positions, consistent across all three weeks.
- 2026-09-28: Phase 1 Step 4 (manual root-cause tagging) and Step 6 (cross-week consistency)
  completed in the same session per user instruction to keep Phase 1 in one sitting. Root cause
  identified and localized to a specific constant (`OWNERSHIP_SOFTMAX_TEMPERATURE_BY_POSITION`) in
  `ownership_heuristic.py`, confirmed via direct chalk_score-vs-ownership spot-checks, not just
  correlational. Phase 1 closed out. Next session: Phase 2 construction-level diagnostics, or the
  softmax retuning fix itself if the user wants to jump straight to shipping a correction.
- 2026-09-28: Steps 2-5 reworked per user review (`wk3_postmortem_phase1_v2.py`): drivers+killers
  with caps, correct stack-pairing split, correct snowflake test, literal four-way, per-player root
  cause for all 92 flags with gmscott81 lineup check, salary stratification. Headline mechanism
  corrected (wk3 = FFC-unlisted cliff in the layered model; wk1-2 = chalk_score ranking plus softmax
  cap). Phase 1 complete.
- 2026-09-28: Phase 2 run (`wk3_postmortem_phase2.py`, 11 slates). Hindsight chalk lineup beat our
  SE entry 9/9 (+26.6 pts mean; chalk cashed 4/9, ours 0/9). Pool shape: we always stack but never
  QB+2 in MME (0/40, fixed QB+1+bring-back template) vs ~30% in cashing field; our QBs ~$500-900
  pricier than cashing field's; SE punts 0.44 vs 1.06. Phase 1 winning QB+WR1 stacks built 2/30
  times. Mostly confirms Phase 1 player-input read; MME stack-depth setting is the new construction
  finding. Phase 2 complete.
- 2026-09-28: Parking-lot deep-dive (signal coverage & selection) run
  (`wk3_signal_coverage_deepdive.py`). Killer bust share is normal variance, not elevated; no-signal
  drivers share only "cheap / cheap QB"; real-lineup misses split by price (busts expensive, missed
  drivers cheap). Routed to track 2 and existing §4 items. See section below.
- 2026-09-29: Phase 2 checked at scale on the FC Lineup Study classic slice (410 real DK contests, 21.9M entries,
  2022-26; `analysis/classic_history/`). Two findings confirmed:
  - The chalk baseline: realized ownership predicts cash and return after an FC-projection control among quality
    lineups, 4/4 seasons.
  - QB+2: confirmed on return (1.10-1.14x), but its cash lift is about 1/3 of Phase 2's +3.7.
  "Cheap QB" (null after the projection control; the #1-owned QB is the real signal) and the stud/punt gradients were
  contradicted. See `HANDOFF_classic_lineupstudy_findings_2026-09-29.md` §7 for the claim-by-claim table.

## Parking Lot Item: Signal Coverage & Selection Deep-Dive (2026-09-28)

Script: `analysis/classic_diag/wk3_signal_coverage_deepdive.py` (reads the Phase 1 v2 players/flags
CSVs, adds extra columns from our final_projections files, re-parses the 11 contest CSVs for
lineups). Outputs: `analysis/classic_diag/wk3_sigcov_*.csv`. This is a signal-quality-and-selection
question, not construction shape, and is kept separate from Phase 2.

### (a) Killer-side bust base rate

**Definitions.**
- *Eligible pool*: the same pool the killer flags were drawn from: player-slate rows with field_n
  >= 20 and field% >= 5%, with a projection. n = **562 rows** (282 unique week-player).
- *Strong*: projection z >= 1.0 within position (same z as Phase 1).
- *Bust (primary)*: actual DK points in the **bottom quartile of the player's position on that
  slate** (percentile over players the field used at >= 1%). This is position-relative, so a 9-pt QB
  and a 3-pt WR are judged against their own slot, and it doesn't depend on our projection.
- *Bust (alt)*: scored <= 50% of our projection. This is a "missed our number badly" check.

**Result 1: strong projections bust less often than everyone else, not more.**

| cut | z>=1 bust rate | rest bust rate | Fisher p |
|---|---|---|---|
| all eligible rows (bottom quartile) | **12.5%** (20/160) | **20.6%** (83/402) | 0.03 |
| unique week-player | 11.8% (n=76) | 20.9% (n=206) | 0.09 |
| alt def (<= 50% of proj) | 16.9% | 19.9% | 0.48 |

**Result 2: the 35% killer figure is about what the pool would produce anyway.** "35% of killers
were z>=1" is P(strong | killer), so it has to be compared to P(strong | not killer) in the same
eligible pool, not to zero:

| comparison | killers | comparison group | Fisher p |
|---|---|---|---|
| z>=1 share: killers vs rest of eligible pool | **35.0%** (28/80) | **27.4%** (132/482) | 0.18 |
| z>=1 share: killers vs other bottom-quartile busts | 21.1% (8/38) | 18.5% (12/65) | 0.80 |

Strong players are also more rostered (median field% 17% vs 10%). A popular player who busts is more
likely to show up as a large negative-lift "killer" than an obscure player who busts. That selection
effect explains most of the small 35-vs-27 gap. The z cut doesn't change this: at z >= 0.5 the share
is 59% vs 47%, and at z >= 1.5 it's 11% vs 15%.

**By position (the one place it isn't clean).** WR and RB z>=1 plays almost never busted (WR 3.6% vs
21%, p=0.001; RB 0% vs 18%, p=0.006). **QB (18.5% vs 14.6%, n=27) and DST (35% vs 26%, n=23)
strong plays busted at or above base rate.** Both n's are small, so read that as directional. It
does match the existing QB-bust finding (Step 4e / Phase 2 Step 1).

**Reading.** At the aggregate level this is normal variance. Our strong projections are *better*
than average at avoiding busts. The 35% comes from strong players being popular, so their busts get
flagged. The only live thread is QB/DST, and QB is already routed to §4 Step D.

### (b) What's common among the 35 no-signal drivers

Comparison: no-signal drivers (0 <= z < 1, n=35 rows / 23 unique week-player) vs. every other
eligible neutral-z player who was **not** a driver (n=188). Features were taken from our
final_projections files. Mann-Whitney for continuous features, Fisher for shares.

| feature | no-signal drivers | neutral-z non-drivers | p |
|---|---|---|---|
| **low salary band share** | **23%** | **7%** | **0.01** |
| **QB share** | **26%** | **11%** | **0.03** |
| WR share | 26% | 42% | 0.09 |
| median salary | $5,400 | $5,700 | 0.32 |
| field% | 10.4% | 11.3% | 0.76 |
| our own% minus field% | -4.2 | -3.6 | 0.21 |
| team implied total | 23.0 | 23.5 | 0.32 |
| games_played (sample size) | 2 | 2 | 0.58 |
| same-position teammate OUT | 66% | 56% | 0.35 |
| upside ratio (p90 / proj) | 2.08 | 2.16 | 0.05 (drivers *lower*) |
| **actual pts minus our proj** | **+14.3** | **-1.4** | <0.001 |

Checked but not usable: `roster_role` is empty in every file. "Any teammate OUT" is true for about
100% of both groups (injury lists are long), so it can't discriminate.

What the data supports:
1. **Price clusters cheap, but only modestly.** The low-band share is 23% vs 7% against neutral-z
   peers. Across all 80 drivers it's 24% vs 15% of the pool. Median salary isn't significantly
   different. "Cluster cheap" is true at the bottom band, not across the price range.
2. **Cheap QBs.** Shough (4 rows), Bryce Young (2), Purdy (2), Lamar (1). Some of these are
   pairing-driven (Step 2b), meaning the lift came from the QB+WR stack.
3. **Repeat names across variants.** 23 unique players. Schultz (3), Kittle (3), Shough (4) and
   Swift / Coker / Diggs / Warren / Purdy (2 each) make up most of the 35 rows.
4. **No matchup or game-script signal.** Implied total, field%, ownership gap and sample size all
   match the comparison group.
5. **One clear role-change case.** Jaylen Warren wk3: his same-position teammate was OUT, and that
   teammate's season average was 10.3. This is the same vacated-volume mechanism as Aaron Jones (Step
   4c), already routed to §4. No other no-signal driver has a comparable vacated role.

**Reading.** The only thing these 35 share is that they beat our projection by about 14 points. No
pre-game feature in our data separates them from neutral players who didn't hit, apart from price
(bottom band) and position (cheap QB). That's consistent with mostly outcome variance, plus a
cheap-band tilt that the existing cheap-band ownership/projection item already covers. I found no
role-change or game-script pattern to build a feature from. n = 23 unique, so a weak feature could
still be hiding.

### (c) Salary-tier / role clustering in gmscott81's submitted lineups

**Method.** Every roster slot in every entry on all 11 slates, grouped as *mine* (gmscott81: 9 SE
entries, 40 MME entries), *cashing field*, and *non-cashing field*. Slots are tagged with salary
band (Step 5 bands), position, and whether that player-slate was a flagged killer or driver. Field
groups are weighted so each group counts as one lineup per slate. For "my" rows, 20 MME entries on a
slate are not independent, so treat the pooled slot p-values as descriptive.

**Killers I rostered cluster expensive, and at QB.** Share of my roster slots that were flagged
killers, all 11 slates pooled (441 slots):

| band / pos | my slots | my killer rate | rest of my slots | p | non-cashing field killer rate |
|---|---|---|---|---|---|
| low | 68 | **1.5%** | 12.6% | 0.005 | 3.6% |
| mid-low | 199 | 6.0% | 14.9% | 0.003 | 8.4% |
| mid-high | 106 | **18.9%** | 8.4% | 0.004 | 15.8% |
| high | 68 | **22.1%** | 8.8% | 0.003 | 17.4% |
| QB | 49 | **30.6%** | 8.4% | <0.001 | 29.7% |
| WR | 161 | 14.3% | 8.9% | 0.11 | 10.7% |

15 of the 19 killer player-slates in my lineups were mid-high or high salary. 13 were tagged "bad
signal (projected strong, busted)": Allen, Lamar, Caleb Williams, Jefferson (x3 slates), Kincaid,
J. Taylor. Our killer rates are a little above the non-cashing field's in every band. They're
**about equal at QB** (30.6% vs 29.7%), so the expensive-QB bust is a mistake the non-cashing field
also made.

**Drivers I missed cluster cheap.**

| | cashing field | mine | non-cashing field |
|---|---|---|---|
| low-band slots per lineup, SE | **1.68** | 1.11 | 1.44 |
| low-band slots per lineup, MME | **2.04** | 1.45 | 1.52 |
| share of low-band slots that were flagged drivers, SE | **21%** | **0%** | 7% |
| share of low-band slots that were flagged drivers, MME | **38%** | 16% | 17% |
| low-band pts per $1k, SE / MME | 3.44 / 3.84 | 2.12 / 2.84 | 2.29 / 2.44 |
| mid-low slots per lineup, SE / MME | 3.37 / 3.12 | **4.11 / 4.05** | 3.52 / 3.48 |

Flagged-driver coverage by band: low **2/19** rostered, mid-low 8/31, mid-high 4/20, high 3/10.

**Reading.** In real lineups the misses split by price. **We roster busts at the top (QB and
high/mid-high studs we projected strongly) and miss drivers at the bottom** (we play fewer
bottom-band players than the cashing field, and not the ones who hit). We fill that space with
extra mid-low players, who returned the lowest points per $1k of any band in our lineups. This is
the same pattern Phase 2 found at the construction level (pricier QBs, fewer punts). It adds that
the busts are *specifically* the strong-projection studs and the missed upside is *specifically* the
cheap band. The pattern is consistent across SE and MME. n is small: 9 SE lineups, 40 correlated MME
entries across 2 slates. This is directional, not proven.

### Recommendation

- **(a): close as normal variance at the aggregate level.** Strong projections bust *less* than the
  pool (12.5% vs 20.6%, p=0.03). The 35% killer share isn't elevated (vs 27%, p=0.18). Keep the
  QB/DST sub-signal (z>=1 QBs/DSTs bust at or above base rate) as part of §4 Step D's QB price/bust
  check. It doesn't need its own workstream.
- **(b): mostly variance. No new feature workstream.** The only structure is cheap band plus cheap
  QB, and both already live in §4 (Step B cheap-band priority, Step D QB). Warren-type vacated volume
  is already routed (Step 4c).
- **(c): track 2 watch item, the one real thread here.** It's direction-consistent across SE, MME
  and Phase 2: we're overweight expensive strong-projection studs and mid-low filler, and
  underweight the cheap band where the cashing field found its drivers. It doesn't clear the track-1
  bar at this n (9 SE lineups). What would move it to track 1: the same pattern in Wk4-5 real lineups
  (low-band slots per lineup below the cashing field, and killer slots concentrated mid-high/high),
  or replication in the FC Lineup Study (§3), which has the sample size to test whether "more
  cheap-band slots" predicts cashing across many contests. Until then, report per-slate
  "low-band slots vs cashing field" and "killer slots by band" in each post-slate review. Rerun this
  script with the new slates added.

## Parking Lot Item: On-Demand Debugging Time Loss (2026-09-28)

Sources: `gh run list --workflow run_optimizer_dispatch.yml` for 2026-09-13/14, 09-20/21 and 09-27,
`gh run view <id> --log` for every failed run, and `scripts/optimizer.py`. All times UTC. Main lock
was 17:00 each Sunday. No new script; this is log and code reading.

### What actually broke the wk3 pre-lock runs (the read in the checklist was wrong)

The 4 wk3 failures (16:38:38, 16:40:13, 16:43:29, 16:46:06, all `fd_classic_wk3_main`) were not a
thin pool. They were a **structural conflict between `--lock` on a QB and `--stack-mode qb` with
auto-selected stack teams**:

1. `--lock 00-0039150` (Bryce Young, CAR) adds `x[Young] == 1` (`solve_lineup`, `locked_{pid}`).
2. `--stack-mode qb` with no `--stack-team` auto-ranks teams via `rank_candidate_teams()` and takes
   the top 5 (`resolve_stack_candidates()`): BUF, BAL, DET, SF, KC. **The ranking ignores locks**,
   so CAR is never a candidate.
3. For each candidate, `add_stack_constraints()` adds "exactly 1 QB from the target team"
   (`stack_qb_{team}`). The roster has 1 QB slot. Young plus a BUF/BAL/... QB is 2 QBs. Every
   candidate is infeasible, at any uniqueness, any salary floor, any projection floor.

So the uniqueness relaxation (2 → 1 → 0) could never help, and the "pool too thin -- see decision #7"
message pointed at the wrong cause. `validate_lock_feasibility()` catches "2 QBs locked" (and did, with
a clear message, on wk2 run 35523717927) but has no lock-vs-stack check.

**The data rules out the other suspects directly:**

| suspect | evidence | verdict |
|---|---|---|
| salary floor 82.8% | wk2 identical failures ran at 99.5% and 99.4%; wk3 at 82.8%. Same outcome at both | not the cause |
| FD roster thinner than DK | wk2 run 35523681319 was **DK**, same Young lock, same failure | not the cause |
| min-projection 4.0 / participation floor | only drops non-candidates (Bowers, low-proj bench); Young is locked so exempt from both | not the cause |
| lock + auto QB stack | present in all 7 infeasible runs across wk2+wk3, absent in every success | **the cause** |

The one successful wk3 FD run with a QB lock that got as far as generating lineups (14:08:57,
`--lock 00-0033873`) locked a QB whose team (BUF) *was* in the auto top 5, which fits the mechanism.
The fix the user landed on (drop the lock, 16:49:10) works for the same reason.

### Latency per attempt

Each dispatch round trip was 23-61 s of Actions runtime (median ~30 s), plus UI polling and
re-editing. Gaps between attempts were 1.5-3.3 min. Wk3: first failure 16:38:38 to first good main
build 16:49:39 = **~11 min** of the last 21. The solver itself is fast; the cost is that each guess
costs ~2-3 min wall clock and the message gives no hint which guess to make.

### Recurrence: this is not a one-off

| week | failed on-demand runs within 60 min of main lock | what failed |
|---|---|---|
| wk1 (09-13) | **0** of ~50 runs | nothing (3 failures on Mon 09-14 12:50-12:56, a Python traceback, not near lock) |
| wk2 (09-20) | **7** (16:00-16:46) | 3x FD + 1x DK: **same Bryce Young lock + auto QB stack** (16:20, 16:22, 16:25, 16:45); 1x lock 2 QBs (clear error, fixed in 1 try); 2x git push race (16:00, 16:14) |
| wk3 (09-27) | **5** (16:00-17:00), plus 3 earlier | 4x **same Young lock + auto QB stack** (16:38-16:46); git push race at 14:05, 14:08, 15:52 |

The lock-vs-stack trap hit **the same player, the same way, two Sundays running**, each time inside
the last ~45 min. Wk2 had it on both FD (16:20-16:25, ~5 min lost) and DK (16:45, ~2 min, 15 min
before lock).

**Second, separate bug found: git push race.** 5 runs (wk2 x2, wk3 x3) generated their lineups fine
("Generated 10/10") and then failed at `git push` with `cannot lock ref 'refs/heads/main'`, because
another concurrent run pushed first. The "Commit request result" step does one `pull --rebase` and
one `push`, no retry. To the user these look identical to an optimizer failure. This is the same
concurrency family as the §1 lineup-file overwrite race (several people building at once), but the
§1 fix did **not** cover it: it changed file names, not the push. It's still live in the current
workflow. None of these 5 fell in the final 20 min, so it didn't cause the wk3 main time loss.

### Verdict

- **Mostly a diagnostics/UX gap, with a small logic gap underneath. Not user trial-and-error in the
  sense of a bad strategy.** The solver was right to call it infeasible, but the optimizer (a) let the
  QB lock and the auto QB stack conflict silently, and (b) blamed pool thinness, which sent the user
  toward salary floor / site / excludes, none of which were the problem.
- **Recurring, not a one-off.** 2 of 3 weeks (wk2, wk3), same trigger, same pre-lock window. Wk1
  clean. Cost per week: roughly 5-11 minutes in the final 45.
- **Is it the 3-week common factor?** Partly, and only as a compounding factor. It ate review time in
  wk2 and wk3. It didn't produce a bad lineup: the lock was abandoned both times, and per Step 4e
  Young was a wk3 killer we correctly didn't roster. The modeling findings in Phase 1/2 are
  unaffected. Evidence basis: 12 run logs read directly, n = 2 affected weeks. Confidence is high on
  mechanism (it's deterministic), moderate on "recurs" (two instances of the same thing).
- **Connection to §1 bugs:** the lock/stack trap is unrelated to either. The git push race is a
  sibling of the overwrite race (same concurrent-use cause, different mechanism, not fixed).

### Proposed fixes (not implemented)

Track 1 (small, deterministic, worth shipping before wk4 lock):
1. **Locked QB + `--stack-mode qb` with no `--stack-team`: pin the stack to the locked QB's team**
   (or at least add it to the candidate list). That's almost certainly what the user means. If 2+
   pinned teams exclude the locked QB's team, fail up front with "Locked QB X (CAR) conflicts with
   QB stack teams [...]". This goes in `validate_lock_feasibility()` / `resolve_stack_candidates()`.
2. **Push retry in `run_optimizer_dispatch.yml`**: loop `pull --rebase && push` 3-5 times with a short
   backoff. Mechanical, removes fake "failures" of successful builds.

Track 2 (worth tracking, not urgent):
3. When a lineup is infeasible at uniqueness 0, re-solve once with each optional constraint dropped
   (lock, stack, salary floor, projection floor) and name the one whose removal makes it feasible.
   It's cheap and general, but fix 1 already covers the only case seen in 3 weeks.
4. A local/instant feasibility check to skip the Actions round trip. Not proposed for now: with 1 and
   2 in place, no observed failure would have needed it.
