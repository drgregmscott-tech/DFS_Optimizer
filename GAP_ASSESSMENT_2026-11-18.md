# NFL DFS Optimizer: Gap Assessment (2026-11-18)

Thinking-phase output (Opus). No tracked file was edited. Probe scripts are in
`analysis/gap_assessment_2026-11-18/` (gitignored): `solver_test.py`, `own_acc.py`, `own_acc2.py`, `stack_corr.py`.
Real-slate test used `output/final_projections_dk_dk_classic_wk10_main_15Nov2026.csv` (read-only).

**The premise being tested (owner's words, condensed only for headings):** a gap assessment to find what was missed or
built incompletely, judged against "the best commercially available DFS optimizer for NFL". Decisions, not proof. Prior
answers get reviewed, not trusted. Each gap is labeled FIX HERE or DEDICATED SESSION.

The headline: **the solver is correct. The biggest gap is the layer above it.** We optimize a single mean projection
with stacking as a yes/no rule. Commercial leaders (SaberSim, Stokastic, FC sims) build and pick lineups from
correlated game simulations. We have most of the parts (a Monte Carlo stat-line engine, a field simulator), but they are
not connected to lineup building.

---

## 1. Verdict summary: top 10 gaps, ranked by expected cash/accuracy impact

1. **No correlated lineup simulation.** Lineups are picked on summed means. Correlation enters only as a hard "QB + 1 partner" rule. Player sims exist but collapse to mean/sigma before the optimizer sees them. → DEDICATED SESSION (D1).
2. **Randomization is independent noise and breaks correlation.** At 10% it also drops lineup #1 by 3.0 pts on the wk10 test (136.9 vs 139.8). → FIX HERE (F2: anchor lineup #1 on the true projection). Real fix is sim-draw lineups, inside D1.
3. **Sigma is basically a scaled projection:** corr(sigma, projection) is 0.95-0.99 at every position on wk10. So lambda is really a "projection-squared" penalty, not a variance preference, and the cheat sheet's floor/ceiling carry no player-specific risk information. → part of D1.
4. **The participation floor drops real starters.** It is on by default and excluded Kyle McCord, MIA's starting QB (wk10, 11.6 projected, scored 13.8), and Carson Beck. The "no history = exempt" rule in its docstring never fires, because a 0-game player reads 0.0, not NaN. → FIX HERE (F1).
5. **We identify only about half the chalk.** Wk1-9 DK main: on average 5.4 of the field's real top-10 owned players are in our top 10. Our top-5 ownership averages 28% against the field's 33%. → DEDICATED SESSION (D3).
6. **Ownership never reaches lineup construction.** `own_penalty` defaults to 0, the ownership re-rank is off, and the near-max pivot is only a tag. So leverage is fully manual. The right fix is a field simulation (leverage then falls out of the math), not a linear fade. → part of D1/D3.
7. **The projection engine ignores red-zone role, and early-season shares start from scratch.** TD rate is per-opportunity with no RZ share. Share history is current-season only. The calibrated stack layer was fit on 2020-21 (not 2021-25) and FD has no stack layer at all. → DEDICATED SESSION (D2).
8. **QUESTIONABLE players keep their full projection.** There is no probability-weighted discount, and teammates get no partial redistribution. → DEDICATED SESSION (D2), small part.
9. **The SE/3-Max preset still builds QB+2.** That is not the owner's real stack. Ablation measured it at about -1.5 pts and -8 cash pts against QB+1. → FIX HERE (F4).
10. **Bring-back is all-or-nothing.** On 5 seasons of real data it adds correlation only in high-total games (0.16 in the top-total tercile, about 0.02 in the low tercile). → FIX HERE (F5: conditional bring-back flag, default off).

Smaller fix-here hygiene: F3, a fragile binary readout in the solver (`value() == 1`).

---

## 2. Per owner question

### Q1. Projection inputs (snaps, usage, target share, etc.) and the cheat sheet

**What we do today:**
- `statline_model.build_usage()` (`scripts/statline_model.py:608-728`) builds per-player volume from box-score history: pass attempts, carries, targets. It is recency-weighted, multiplied by participation (`:638-647`), with yards/TD/catch/INT rates shrunk to position means (`:676-688`).
- History is current season only (`load_history`, `:561-578`, REG and `week < target`).
- Team volume is Vegas-anchored (`vegas_anchored_team_volume`, `:935`, plus `volume_prior.py`), and a team-level shock correlates teammates' volume (`:3256-3268`).
- Weather enters through pass/rush efficiency and volume factors (`:3290-3300`).
- Layers in `build_projections_statline.py:1411-1475`:
  - props anchor (only if a props snapshot exists);
  - DK-only projection stack (`projection_stack.py`: salary + engine + last-4 targets/carries/attempts/target share/air-yards share/WOPR);
  - early-season salary blend, QB recal/autopromote;
  - who-replaces-whom RB/TE/WR vacancy redistribution, PFR snap-share role adjustment (DK only, clipped ±1.5, `:645-686`), QB-OUT teammate downgrade, Q-return.
- Matchup factor is neutralized to 1.0 for skill positions (`cheat_sheet.py:20-27`; tested and kept neutral twice).

**What is right:**
- The volume × share × efficiency structure is the correct architecture, and it is what commercial models use.
- Snap share, target share, air-yards share and WOPR are all present: snaps via the snap-role layer; the others via the stack.
- Vegas anchoring, weather, vacancy redistribution and props are all there.
- NFL has no "projected minutes" or "strikeouts"; the NFL equivalents are snaps/routes/targets, and we have all but routes.

**What is wrong or incomplete:**
- **Red-zone / goal-line share is absent.** TDs are the single biggest swing in DK scoring, and we model them as yards-per-opportunity × TD-per-opportunity, shrunk. A goal-line back and a between-the-20s back with equal carries get similar TD rates. nflverse pbp (free, 2021-25) gives RZ/inside-10 carries and targets. We do not fetch pbp (`nflverse_fetch.py:27-57`).
- **No prior-season carryover for shares.** Weeks 1-3 lean on the salary prior because current-season history is empty. This matches the repeated Wk1-2 accuracy and ownership dips.
- **The stack layer is fit on 2020-21 only** (`projection_stack.py:13-20`), not the 5-season history the project standard requires. FD gets no stack layer at all (`build_projections_statline.py:1420`, `site == "dk"`), and the snap layer is DK-only too. **FD projections are a less-corrected engine.**
- **Routes run / TPRR are absent.** Paid data (PFF/FTN), so not fixable for free. The snap layer is the free proxy.
- **Cheat-sheet signals that never reach the projection.** The v3 cheat sheet (`cheat_sheet.py:44-67`) computes:
  - Role Security (volume, team share, recent snap %, missed time, usage trend, Q tag);
  - season dud rate;
  - DST "upside setup" (opponent sack rate, INT rate, opposing skill injuries, weather);
  - a display-only matchup tier.

  None of these feed `final_projection` or sigma. Two of them, dud rate and role security, are exactly what player-specific variance should be built from. The display matchup tier says "smash spot" while the projection ignores matchup; that is a consistency problem the owner should know about.

**Decision:**
- Build RZ share and prior-season share carryover, and refit the stack on 2021-25 with an FD version → D2.
- Feed role security and dud rate into sigma → D1.
- Keep the matchup neutral (tested twice); relabel the cheat sheet's matchup bullet "display-only".

### Q2. Dynamic updates (news, weather, starting lineups)

**What we do today:**
- Full refresh every 3h Thu/Sun/Mon, plus about every 10 min in near-lock windows (`DFS_Weekly_Process.md:363-381`).
- `status_check.py` zeroes OUT; DOUBTFUL is treated as OUT; QUESTIONABLE is flagged but the projection is left unchanged (`status_check.py:598-638`).
- The rebuild re-runs vacancy redistribution and ownership.
- Weather is applied in the engine.

**What is right:** the cadence is commercial-grade, and OUT → teammate redistribution is automatic.

**What is wrong or incomplete:**
- QUESTIONABLE has no discount. A Q player plays about 80% of the time, often on a snap limit, and his teammates should get a partial bump.
- Lineups already built are never re-flagged when news breaks after the build. There is no late-swap helper that, at T-90 min, lists built lineups holding an OUT player and the best same-salary replacement.
- The 2026-10-24 retirement of the X monitor left the ESPN feed as the only automated source. That is fine, but it means the user's manual news is the backstop.

**Decision:** Q-tag discount → D2 (it needs a calibration on 2021-25 injury-report outcomes). Late-swap flagger → D5 (separate session; touches the UI).

### Q3. Simulation model

**What we do today:**
- **Player-level Monte Carlo exists.** `statline_model.simulate()` (`scripts/statline_model.py:3231-3353`) uses `DEFAULT_SIMS = 4000` (`:370`) with a shared per-team volume shock.
- **It is collapsed to `statline_mean`, `statline_sigma`, `p10`, `p90` per player (`:3343-3347`).** The optimizer only ever sees the mean (objective, `optimizer.py:2217-2220`) and the marginal sigma (lambda).
- QB passing TDs and each receiver's TDs are drawn **independently** (`:3316-3318`, each `_draw_component` call has its own latent). So even the engine under-states the QB-receiver link.
- There is no game-level shock (no shootout correlation between the two teams) and no lineup-level or contest-level sim.
- `classic_field.py` (a field simulator calibrated to real stack rates and salary use) exists but says it is "not yet wired up" for scoring candidate lineups (`classic_field.py:35-39`).

**Are we doing it?** No. We do straight addition of means plus a stack rule.

**How many simulations is "enough"?** It depends on the metric, because Monte Carlo error is sqrt(p(1-p)/N):
- **Player means:** sigma about 8 pts → SE = 8/sqrt(N). N = 4,000 gives ±0.13 pts. That is enough (today's setting is fine).
- **Cash rate (p ≈ 0.2-0.25):** N = 2,000 gives SE about 0.9 pts of cash %; N = 10,000 gives about 0.4. **5-10k is enough.**
- **Top-1% rate (p ≈ 0.01):** N = 1,000 gives 31% relative error; N = 10,000 gives 10%; N = 50,000 gives 4.5%. **10k is the practical sweet spot**, and 50k only matters for distinguishing lineups within about 10%.
- **Win / top-0.1% (milly-maker):** N = 10,000 gives 32% relative error. **For large-field GPP ranking, 25-50k is needed.**

So the owner's intuition holds for our contests (SE / 3-max / 20-max, cash line around top 20-25%): **10,000 sims is the target, and 50,000 adds nothing that changes a decision.** The exception is ranking lineups for a top-heavy 150-max milly field, where 25k+ starts to matter.

**Decision → D1 (dedicated session).** Specification is in §6.

### Q4. Stacking

**What we do today:**
- A hard ILP constraint: `stack_mode=qb` forces exactly one QB from the target team and ≥`stack_size` partners from `stack_positions`, default `WR,TE` (`optimizer.py:1281-1292`, `:408`).
- Bring-back, when on, is a hard "≥1 opponent skill player" (`:1294-1308`).
- Candidate stack teams are restricted to the top `--stack-candidate-pool` (default 5) teams by implied total (`:410`, `resolve_stack_candidates` `:2672`, `rank_candidate_teams` `:1167-1207`). The UI never sends this flag, so every UI build uses top-5.
- For each lineup the solver tries every candidate team and keeps the highest-projection result (`:3363-3408`).
- Separate always-on rule: 2+ same-team pass catchers requires that team's QB (`add_qb_pass_catcher_constraints`, `:2365-2368`).

**What we learned this session** (`stack_corr.py`):
- Real DK points, 2021-25 REG, 2,681 team-games.
- QB = in-game starter (most attempts, at least 15). Partner roles are assigned from **prior-week** usage only (season-to-date mean targets, or carries+targets for RB), with at least 2 prior games.

| QB paired with | corr | per-season range | P(QB+partner ≥ 50) | vs independent | ceiling lift |
|---|---|---|---|---|---|
| WR1 | 0.381 | 0.35-0.43 | 11.2% | 8.0% | 1.40x |
| WR2 | 0.373 | 0.33-0.42 | 5.9% | 3.6% | 1.63x |
| TE1 | 0.301 | 0.22-0.34 | 4.4% | 2.8% | 1.59x |
| WR3 | 0.255 | 0.15-0.32 | 2.8% | 1.7% | 1.65x |
| RB1 | 0.097 | 0.02-0.15 | 8.6% | 8.4% | 1.03x |
| Opp QB | 0.186 | | | | |
| Opp WR1 (bring-back) | 0.085 | 0.06-0.11 | | | |

Game environment, QB+WR1 by the team's implied total (within-season quintiles):

| Implied-total quintile | Mean implied | Mean QB+WR1 | P(≥50) | P(≥60) |
|---|---|---|---|---|
| 1 (worst) | 16.8 | 24.9 | 4.6% | 1.5% |
| 3 | 22.3 | 32.1 | 11.2% | 4.2% |
| 5 (best) | 27.6 | 38.3 | **20.7%** | **8.5%** |

Bring-back (corr of QB+WR1 with opp WR1) by game total tercile: low 0.02, mid 0.06, **high 0.16**.

**Answers to the owner's specific questions:**
- *QB1+WR1 vs QB1+WR2?* **Roughly equal correlation (0.38 vs 0.37), in all 5 seasons.** WR1 wins on raw mean; WR2 wins on ceiling lift per dollar. Do not hard-code "WR1 only". Let a sim objective price it.
- *What to stack?* WR and TE: yes; TE1 is real (0.30). **RB: no** (0.10, and no ceiling lift). Our default `WR,TE` is correct. The ablation that used "RB/WR/TE partners" was looser than live.
- *Price point:* nflverse has no salaries, so this is not settled here. The evidence above says correlation does not depend on the partner being the expensive WR1. So **cheap stack pieces keep the correlation benefit**, and paying up buys mean, not correlation. A salary-tier test on FC history fits inside D1's validation.
- *Game environment:* **targeting top environments matters a lot.** The top implied-total quintile has 4.5x the 50-point stack-ceiling rate of the bottom quintile. Our top-5-implied-team restriction is consistent with this (top 5 of about 13 teams ≈ top 40%), so keep it. Avoiding bad environments is the cheaper half of the same effect.
- *Bring-back:* only worth it in high-total games. The owner's general "no bring-back" is right for most games. MME's always-on bring-back is wrong in low-total games → F5.
- *Our live behavior:*
  - On wk10, the unstacked optimum had Purdy with **zero** same-team WR/TE. QB+1 cost 0.46 pts (139.84 vs 140.30).
  - Historically QB+1 costs 0.04 pts (`analysis/optimizer_fidelity_qb1_recheck_2026-10-27/`).
  - So QB+1 is nearly free, but **as a hard rule it adds no correlation value to the objective**. The solver picks whichever partner has the best mean per dollar, blind to correlation and ceiling. That is the core gap; it is fixed only by D1.

**Prior conclusion flagged:** "QB+1 hasn't helped" (owner) and "QB+1 is neutral vs no-stack" (fidelity recheck) are both true *for a mean-only objective*. That does not show stacking has no value. Under a mean objective a stack rule can at best be neutral. The value of correlation shows up only when lineups are scored on a joint distribution.

### Q5. Ownership and leverage

**What we do today:**
- `ownership_v2.py` is a softmax-allocated linear model (`build_features`, `:316-439`). Features: projection/value/salary ranks, implied total, Vegas, prior salary change, lagged ownership, usage share and vacated share, a target-spike signal, DK-average value, pressure (DST). It is blended with FFC live ownership plus chalk adjustments (`:631-905`).
- In construction it is used **nowhere by default**:
  - `own_penalty` defaults to 0 (`optimizer.py:2227-2231`);
  - `_rank_lineups_by_proj_own` is off (`DFS_RANK_OWN_W=0`, `:4654-4702`);
  - `_tag_near_max_pivot` is only an audit tag (`:4705-4759`);
  - `pivot_finder.py` lists same-position lower-owned alternatives for manual use.

**Accuracy measured this session** (`own_acc.py`, `own_acc2.py`; DK main classic, wk1-9, from `data/ownership_actual_log.csv`):

| | Mean wk1-9 | Wk4-9 only |
|---|---|---|
| Pearson | 0.79 | 0.84 |
| Spearman | 0.87 | 0.92 |
| MAE | 1.77 pts | 1.60 pts |
| Our top-10 ∩ field top-10 | **5.4 / 10** | 5.8 / 10 |
| Top-1 owned: field / ours | 44.2 / 36.2 | |
| Top-5 mean: field / ours | 33.0 / 28.2 | |
| Players ≥30%: field / ours | 2.6 / 1.6 | |
| When we say ≥20%, actual minus ours | -2.9 pts | |

**What is right:**
- The overall rank order is good (Spearman about 0.9 from wk3 on).
- When we call a player chalk, he usually is (slightly over-called, -2.9).
- "Don't fade chalk for its own sake" matches the evidence: linear own-penalty sweeps were flat to negative (`analysis/own_penalty_sweep/RESULTS.md`).

**What is wrong or incomplete:**
- **We miss who the chalk is about half the time**, and the top of the distribution is compressed. The field concentrates harder on 1-3 players than we predict.
- "Know the chalk to play the chalk" is our weakest point at the exact top of the distribution.
- Leverage has no automated home. Real leverage is "this lineup wins in sims more often than its ownership implies", which needs the field sim (`classic_field.py`) and the player sims together (D1).

**Decision:**
- D3: a top-of-distribution chalk-identity fix (a concentration/temperature term fit on 2021-25 FC labels, with the top-10 overlap metric as the target).
- D1: leverage through the field sim.
- Do **not** turn on `own_penalty`.

### Q6. Randomness, exposure caps, uniqueness: are we too random?

**What we do today:**
- Randomization: an independent normal draw per player per lineup, std = pct × projection (`randomize_projections`, `optimizer.py:1723-1783`; draw at `:1782`).
- Exposure caps: a pre-solve pool filter once a player hits floor(cap × N) (`:3229-3236`, `:3308-3312`).
- Uniqueness: a no-good cut against every prior lineup (`:2327-2335`).
- After the build, lineups are renumbered by real projection (`:3474`).

**Measured on wk10** (20 lineups, uniqueness 3, QB+1, exposure 100%):

| Randomization | #1 lineup | Mean | Min | Unique players |
|---|---|---|---|---|
| 0% | 139.84 | 137.59 | 136.85 | 33 |
| 5% | 139.84 | 136.51 | 133.87 | 37 |
| 10% | **136.89** | 133.26 | 128.44 | 51 |

**What is right:**
- At 5% (SE3max pool) the #1 lineup is untouched and the pool gives up about 1 pt on average. That is a tight, intelligent range. History agrees: r5 had the best #1-pick cash, 44% (`analysis/pool_randomization/RESULTS.md`).
- The MME exposure cap is the real cost driver, not randomness (ablation: 4.9-5.4 of the 8.7-pt pool sacrifice came from the 50% cap; `analysis/optimizer_ablation_2026-10-27/RESULTS.md`).

**What is wrong:**
1. At ≥10% the true optimum can drop out of the pool entirely: the best lineup is 3 pts worse.
2. Independent noise is the wrong kind of randomness. It can push a QB up and his WR down in the same draw, the opposite of reality. So "random" lineups are scattered across uncorrelated combinations rather than across plausible game scripts.

**Decision:**
- F2: always solve lineup #1 on the true (or thumbs-adjusted) projection.
- D1: replace independent noise with "optimize on one correlated sim draw per lineup" (how SaberSim builds). Randomness then becomes coherent game scripts.
- Keep 5% for SE3max. Keep the MME 35% cap until D1 can choose exposure by sim ROI.
- **Too random?** No for SE3max. MME at 10% is acceptable once F2 lands.

### Q7. Participation floors and lambda

**Participation floors**
- **What they do:** a hard pool exclusion of QB < 0.60, RB < 0.40, TE < 0.40 participation (share of the team's last N played weeks with a stat line). On by default (`optimizer.py:254`, `apply_participation_floor` `:530-577`). The UI passes it through (`optimizer_api.js:260`).
- **What we found:**
  - On wk10 main it removed 90 players with positive projection.
  - **It removed Kyle McCord, MIA's actual starter**: $4,000, projected 11.55, scored 13.76, 1.0% owned. It also removed Carson Beck (projected 11.06).
  - Both have `games_played = 0` and `participation_effective = 0.0`.
  - The docstring says players with no games-played history are exempt because they read as NaN (`:536-541`), but the code only exempts NaN (`:560`), and these rows are 0.0. **That is a bug.**
  - Every other dropped player projects at 2.6 or below, so the floor's real job (keeping dead-roster backups out) is already done by the projection engine. Its only live effect is the false positives.
- **Decision → F1:** exempt `games_played == 0`, and exempt QBs with `proj_pass_att >= 20` (the engine believes they start). Keep the floor otherwise.

**Lambda (variance penalty)**
- **What it does:** objective = Σμ − λ·Σσ² (`optimizer.py:2217-2220`).
- **What we found:**
  - σ tracks μ almost perfectly on the live pool (corr 0.986 QB, 0.964 RB, 0.956 WR, 0.950 TE).
  - So λ·σ² ≈ λ·k²·μ²: **a positive lambda is a quadratic penalty on high projections, not on risk.** That is why every positive-lambda test lost points (`analysis/lambda_reverify/RESULTS.md`, cash/SE moved 0.063 → 0 on 2026-09-26).
  - MME's -0.005 is a mild stud tilt. It measured as a small, real gain (+1.7 best-lineup pts on history, +2.3 on 2026), so keep it, but call it what it is.
- **Decision:**
  - Leave the values as they are: cash/SE 0, MME -0.005.
  - Mark lambda "advanced, do not change" in the UI tooltip.
  - Lambda becomes meaningful only after D1 produces player-specific σ.

### Q8. Is the solver generating optimal lineups, in order?

See §3. Short answers:
1. **Yes:** it returns the exact top projected legal lineup.
2. **With uniqueness = 1 the second lineup is the second-best distinct lineup, not "same lineup with one pivot".** The owner's expectation is not how an exact optimizer should behave, and ours behaves correctly. A 1-player pivot is usually salary-infeasible or worse than a 2-3 player reshuffle.
3. With randomness, caps and uniqueness, each lineup is optimal *for its own draw and constraints*. They are then renumbered by real projection, so the output order is "best real projection first", not "generation order".

### Q9. Contest-result data

See §4.

---

## 3. Solver behavior: what was run and what it showed

**Script:** `analysis/gap_assessment_2026-11-18/solver_test.py`, run on `dk_classic_wk10_main_15Nov2026` (386 players with projection > 0). It calls `optimizer.solve_lineup` / `build_multi_lineup` directly, read-only.

**T1. Is the "no controls" lineup the true top lineup?**
- Raw ILP with no floor and no skill-vs-DST rule: **140.30 pts**, $49,900: Purdy / Hubbard / J. Williams / E. Johnson / Jefferson / Concepcion / Wan'Dale Robinson / Warren / Colts.
- The default-rules optimum is identical (the rules cost 0 on this slate).
- Independent check: of every legal 1-for-1 swap off that lineup, **0 beat it**.
- CBC is called with no gap tolerance and solves in 0.4 s. **Verdict: optimal.**

**T2. Uniqueness = 1, no randomness: the sequence.**

| Lineup | Pts | Players changed vs L1 | Out → In |
|---|---|---|---|
| L2 | 140.21 | 3 | J. Williams, Jefferson, Wan'Dale → McCaffrey, London, Atwell |
| L3 | 140.00 | 2 | |
| L4 | 139.95 | 2 | |
| L5 | 139.92 | 2 | |

- The scores decrease monotonically, as exact N-best enumeration should.
- **Not one of them is a 1-player pivot.** The cut `Σx(prev) ≤ |prev| − u` (`optimizer.py:2332-2335`) means "at least u different". The solver then returns the best lineup that satisfies it, and a pure 1-for-1 swap is almost never the second-best lineup under a binding salary cap.
- **Verdict: correct behavior.** The owner's expectation should be updated, not the code.

**T3. QB+1 cost.** The unstacked optimum had zero same-team WR/TE with Purdy. The best QB+1 lineup over the top-5 implied teams (SF, BUF, JAX, DAL, KC) is SF at 139.84: **-0.46 pts.**

**T4. Randomness on a 20-lineup build.** See the Q6 table. At 10%, the pool's best lineup is 2.95 pts below the deterministic best.

**Code-path notes:**
- Greedy over stack candidates: each lineup solves one ILP per candidate team (up to 5) and keeps the best (`:3363-3408`). That is correct, at about 5x the solve time.
- Uniqueness relaxation steps down by 1 when infeasible (`:3410-3421`). Exposure-capped players are removed from the pool, not penalized.
- Cash preset: `n-lineups 3`, `uniqueness 0`, `randomization 0` → **3 identical lineups.** That is fine if intentional (same lineup in 3 cash games); flagged for the owner.
- `selected_ids = [pid for pid in x if x[pid].value() == 1]` (`:2378`) relies on CBC returning exactly 1.0. That is safe today but fragile → F3.

---

## 4. Contest-result data: what exists, what we use, what we do not

**Exists:**
- `data/contest_results/2026/Week_1..10/*_full.csv`: full DK/FD standings for every 2026 slate we played. Every entry's lineup, points and rank, plus the player %Drafted/FPTS block. There are SE3max and MME variants for Wk2-4.
- `data/results_raw_*` (player points), `data/ownership_actual_log.csv` (DK classic + showdown ownership, wk1-9).
- FC history (2021-25, 410 classic contests, lineup-level; local only).

**Used:**
- Ownership refits (`fit_ownership_model.py`, `log_ownership.py`).
- Weekly accuracy grading (`grade_accuracy_week.py`) and construction grading (`grade_construction_week.py`, including the owner's username).
- Cash-line grading in every replay study.
- Field construction priors (`classic_field.py` stack/salary calibration from 134 real contests).
- The construction rules (`CLASSIC_RULES.md`, FC lineup study).

**Not used:**
1. **Payout tables.** No $ data, so every study grades "top 25% = cash" (`feedback_cash_rate_proxy`). DK prize tables are visible on the contest page. Recording them per contest (one small CSV row per contest) unlocks real ROI grading and the right sim objective → D6.
2. **The field as a simulation opponent.** The real field's lineups could validate `classic_field.py`'s simulated field, then be used to score our candidates' win/cash odds per sim (D1's core loop). Today the field data is only used descriptively.
3. **The owner's own entries over time.** They are graded per week, but `ALL_WEEKS_LEDGER.md` stops at Wk7. Wk8-10 are not compiled → D6 (trivial).
4. **Ceiling-miss attribution.** The ledger says **85% of notable misses are ceiling misses** (351 of 411), not floor breaks. Our misses are players outscoring their projection by a lot. That is direct evidence that the gap is in ceiling/correlation modeling (D1), not mean accuracy.

**Baseline to beat (from existing work):**
- Top-projected lineup cashed 4/14 DK+FD main slates with the full preset pool, and 7/14 with minimal diversification (ablation).
- Pool cash 20-36% depending on settings.
- The owner's FC era cashed 59.9%.

---

## 5. Extra gaps the owner did not list

- **E1. FD is a second-class pipeline:** no projection stack, no snap layer, no real ownership labels (correctly, since FD exports none). FD should at least get a 2021-25-fit stack → D2.
- **E2. Showdown has no correlation model.** Hard rules only (`SHOWDOWN_RULES.md`), and the Wk5+ cash collapse is still open. A showdown sim is a natural second target after classic D1 (the 2-team game makes it simpler).
- **E3. Late swap.** No tool → D5.
- **E4. UI does not expose `--stack-candidate-pool`.** Every UI build uses top-5 implied teams silently. Fine as a default (supported above). Expose it read-only in the build summary so the owner knows.
- **E5. Docs drift.** CLAUDE.md says the preset default stack is 2. After F4, no GPP preset defaults to 2, so update the gotcha line (part of F4).

---

## 6. Gap disposition

| ID | Gap | Disposition |
|---|---|---|
| F1 | Participation floor drops 0-game starters | **FIX HERE** |
| F2 | High randomization drops the true optimum | **FIX HERE** |
| F3 | Fragile binary readout | **FIX HERE** |
| F4 | SE/3-Max preset QB+2 vs real QB+1 | **FIX HERE** |
| F5 | Bring-back only in high-total games (opt-in flag) | **FIX HERE** |
| D1 | Correlated sim + sim-based lineup selection | **DEDICATED SESSION** (largest, highest value) |
| D2 | Projection inputs: RZ share, prior-season carryover, 2021-25 stack refit + FD stack, Q discount | **DEDICATED SESSION** |
| D3 | Ownership chalk identity / top concentration | **DEDICATED SESSION** |
| D5 | Late-swap flagger | **DEDICATED SESSION** (UI + worker) |
| D6 | Payout capture + ledger Wk8-10 | **DEDICATED SESSION** (small, mostly owner data entry) |

### D1. Correlated simulation and sim-based selection (DEDICATED SESSION)

**Why it is too big for here:**
- It touches the engine output contract (draw matrices, not just summaries), adds a new selection stage, and needs validation on 2021-25 FC contests.
- It probably needs 2-3 sessions: (a) joint sims, (b) field sim + selection, (c) validation + UI.

**Scope:**
1. `statline_model.simulate()` returns an `(n_players × n_sims)` DK-points matrix: a new function `simulate_joint`, leaving `simulate` unchanged.
2. Add a QB↔receiver TD/yardage link (the QB's pass TDs allocated to receivers in proportion to target share inside each draw, instead of independent draws) and a game-level shock shared by both teams.
3. Calibration targets: the 2021-25 correlations in §2 Q4 (WR1 0.38, WR2 0.37, TE1 0.30, RB1 0.10, opp QB 0.19, opp WR1 0.09).
4. Player-specific sigma from the dud rate and role security already computed in `cheat_sheet.py`.
5. Candidate generation: 1,000-3,000 lineups, each the ILP optimum on one sim draw (replaces independent randomization).
6. Scoring: each candidate vs a `classic_field.py` field built from our ownership, across **10,000 sims**. Metrics: cash %, top-1 %, mean finish; ROI once D6 exists.
7. Selection: top by the contest-type metric. Cash/SE: cash %. 3-max/20-max: top-10 % with an overlap cap.
8. Validation: leave-one-season-out on the FC 2022-25 contests, then 2026 Wk1-10. Head-to-head vs the current SE3max pool #1 pick.

### D2. Projection inputs (DEDICATED SESSION)
- pbp fetch for RZ/inside-10 opportunity shares, 2021-25.
- Prior-season share carryover with weekly decay for weeks 1-4.
- Refit `projection_stack` on 2021-25, LOSO; add an FD fit.
- Q-tag discount calibrated from 2021-25 injury reports vs played/snap share.

Too big because each piece needs its own LOSO backtest across 5 seasons.

### D3. Ownership chalk identity (DEDICATED SESSION)
- Target metric: top-10 overlap, plus top-5 level.
- Candidate fixes: a concentration (temperature) term on the softmax top end, and the FFC blend weight at the top end.
- Fit on 2021-25 FC labels; check on 2026.

### D5. Late-swap flagger (DEDICATED SESSION)
At each near-lock refresh, write `late_swap_{site}_{slate_id}.csv`: lineups holding newly OUT/DOUBTFUL players, plus the best salary-legal swap from players whose games have not locked. Show it in the UI.

### D6. Payout capture + ledger (DEDICATED SESSION, small)
- `data/contest_payouts.csv` (contest_id, rank_lo, rank_hi, prize), entered by the owner from DK contest pages.
- Extend `ALL_WEEKS_LEDGER.md` to Wk10.

---

## 7. Build plan (FIX HERE items only, in order)

**General rules:**
- Builder works on a branch, not `main`.
- Do not touch `output/` or `data/props`.
- All tests read existing `output/final_projections_*` files.
- Run tests from repo root with `venv\Scripts\python.exe`.

### F1. Participation floor: exempt 0-game players and projected-starter QBs
- **File:** `scripts/optimizer.py`, function `apply_participation_floor` (lines 530-577).
- **Change:** build one `exempt` boolean Series and use it in BOTH the `below_floor` print mask (`:559-562`) and the return mask (`:574-577`):

  ```python
  gp = pd.to_numeric(players.get("games_played"), errors="coerce") if "games_played" in players.columns else pd.Series(np.nan, index=players.index)
  ppa = pd.to_numeric(players.get("proj_pass_att"), errors="coerce") if "proj_pass_att" in players.columns else pd.Series(0.0, index=players.index)
  exempt = (gp.isna() | (gp <= 0)) | ((pos == "QB") & (ppa.fillna(0) >= 20.0)) | players["player_id"].isin(locked_player_ids)
  drop = part.notna() & (part < floor) & (floor > 0.0) & ~exempt
  ```

  Print `players[drop]`, return `players[~drop].copy()`. Add a module constant `PARTICIPATION_FLOOR_QB_STARTER_ATT = 20.0`, used in place of the literal. Update the docstring to say 0-game rows are exempt (the old NaN wording was wrong) and why.
- **Acceptance:**
  - (a) On `dk_classic_wk10_main_15Nov2026`, with projection > 0 and the default floors, the returned pool contains Kyle McCord and Carson Beck.
  - (b) The dropped count with projection > 0 goes from 90 to 88 (± any other 0-game/≥20-attempt QBs; list them in the PR).
  - (c) No dropped-to-kept player has `final_projection < 3` other than 0-game rows.
  - (d) `--participation-floors ''` is still a no-op.
  - (e) A pool without `games_played`/`proj_pass_att` columns behaves exactly as before.

### F2. Anchor lineup #1 on the unperturbed objective
- **File:** `scripts/optimizer.py`, `build_multi_lineup` (randomization block `:3330-3339`).
- **Change:** add a parameter `anchor_first_lineup: bool = True`. The block becomes:

  ```python
  optimization_projection = None
  if randomization_pct > 0 and not (anchor_first_lineup and n_generated == 0):
      optimization_projection = randomize_projections(...)  # unchanged call
  elif thumbs_projection is not None:
      optimization_projection = thumbs_projection
  ```

  Note: when anchored and thumbs are set, lineup 1 uses the thumbs projection, matching the `elif`.
- **CLI:** add `--no-anchor-first-lineup` (`argparse.BooleanOptionalAction`, `dest="anchor_first_lineup"`, `default=pdef("anchor-first-lineup", True)`) and pass it through in `main()` wherever `build_multi_lineup` is called for classic.
- **Showdown:** apply the identical change in `build_multi_showdown_lineup` (`:4425+`), in its own per-lineup randomization block.
- **Worker:** no change (the default is on).
- **Acceptance:**
  - (a) wk10 main, 20 lineups, uniqueness 3, QB+1 WR/TE, randomization 10, seed 7: the max lineup projection = 139.84 (equals the randomization-0 top).
  - (b) Randomization 0 builds are byte-identical to before (diff the lineups CSV).
  - (c) With `--no-anchor-first-lineup`, the rand-10 result reproduces 136.89.
  - (d) One showdown slate: the rand-18 top lineup equals the rand-0 top lineup.

### F3. Robust binary readout
- **File:** `scripts/optimizer.py`. `solve_lineup` `:2378` becomes `x[pid].value() is not None and x[pid].value() > 0.5`. Apply the same pattern to the showdown solver's selected-rows line in `solve_showdown_lineup` (grep `.value() == 1`).
- **Acceptance:** `grep -n "value() == 1" scripts/optimizer.py` returns nothing; the wk10 rand-0 20-lineup build is byte-identical before/after.

### F4. SE/3-Max preset to QB+1
- **Files:**
  - `data/optimizer_presets.json`: `se_gpp` `"stack-size": 2` → `1`. Append `[UPDATED 2026-11-18: QB+2 -> QB+1 to match the owner's real builds; ablation (analysis/optimizer_ablation_2026-10-27) measured QB+2 at -1.5 pts / -8 cash pts vs QB+1]` to its `_comment`.
  - `dfs_optimizer_frontend/index.html:3786`: `ctrlStackSize: "2"` → `"1"`.
  - `CLAUDE.md` gotcha line 1: add "As of 2026-11-18 all GPP presets default to QB+1; the CLI default is also 1 (`DEFAULT_STACK_SIZE`, optimizer.py:400)."
- **Acceptance:**
  - (a) `python scripts/optimizer.py --site dk --slate-id dk_classic_wk10_main_15Nov2026 --preset se_gpp` (output to a temp dir via the existing `OUTPUT_DIR` override used in `analysis/lambda_reverify`) builds 3 lineups, each with exactly 1 QB and ≥1 same-team WR/TE.
  - (b) The JSON parses.
  - (c) The UI "SE / 3-Max GPP" preset shows stack size 1.

### F5. Conditional bring-back (opt-in)
- **File:** `scripts/optimizer.py`.
- **Change:** new param `bring_back_top_games: int = 0` threaded through `build_multi_lineup` → `solve_lineup` → `add_stack_constraints`, plus the single-lineup path.
  - In `add_stack_constraints`, inside `if bring_back:` (`:1294`), when `bring_back_top_games > 0` only enforce the bring-back if the target team's game is among the top-N `over_under` games in `players` (use `rank_candidate_games(players)[:N]` and frozenset membership). Otherwise skip the bring-back for that candidate (no constraint, no error).
  - `validate_stack` (`:1558`) must apply the same condition, so it does not reject a lineup with a legitimately skipped bring-back.
  - CLI: `--bring-back-top-games N` (`default=pdef("bring-back-top-games", 0)`). Preset `mme_gpp`: add `"bring-back-top-games": 3` with a `_comment` citing §2 Q4 (bring-back corr 0.16 high-total tercile vs 0.02 low, 2021-25).
  - Worker allowlist (`cloudflare_worker/optimizer_api/optimizer_api.js` passthroughKeys): add `"bring_back_top_games"`. Frontend MME preset: add the matching control value only if a control exists; otherwise CLI/preset only (note it in the PR).
- **Acceptance:**
  - (a) Default 0: an MME build is byte-identical to before on wk10 (seed fixed).
  - (b) With 3: every lineup whose QB team's game is outside the top-3 totals has bring-back not forced (spot-check that ≥1 lineup lacks an opponent player). Every lineup inside the top 3 has ≥1 opponent skill player.
  - (c) No "stacking infeasible" warnings that were absent at 0.

**Order: F3 → F1 → F2 → F4 → F5.** F3 makes the byte-identical checks for the others trustworthy. After all five: rebuild the wk10 SE3max pool preset at seed 7 and report #1 lineup projection, pool mean and unique players against the §2 Q6 table.
