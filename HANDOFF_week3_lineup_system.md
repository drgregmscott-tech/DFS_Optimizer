# Handoff: building the real Week 3+ lineup system (2026-09-22, follow-up session)

Written to close out a long follow-up session to `HANDOFF_dfs_army_variables.md` (read
that file for the full V1-V5 test detail and numbers -- this file is about what to DO
with the results, not re-deriving them). Greg's own framing at the end of this session:
he wants to combine today's validated results into ONE system for generating/ranking
Week 3+ SE3max lineups, and explicitly wants it usable via the app's frontend -- NOT
something that requires opening a new chat session every week to get an answer. This
file is the handoff into that build effort, which Greg said deserves its own session.

## 0. READ THIS FIRST: the infrastructure you think you need to build may already exist

Before designing anything new, this session discovered `scripts/pivot_finder.py` and
`scripts/ownership_heuristic.py` -- both run every slate already, producing
`output/chalk_scores_{site}_{week}.csv` and `output/pivot_suggestions_{site}_{week}.csv`
-- and `dfs_optimizer_frontend/index.html` already has a WORKING pivot panel wired to
both files (confirmed: 13 live references to `pivot_suggestions`/`chalk_score`/
`leverage_score`, a "no pivot suggestions loaded" empty-state, and an apply-pivot flow
that swaps a suggested player into the lineup being edited). `NFL_pivot_ui_handoff.md`
(filed 2026-08-02) documents two bugs against this same system -- a bad salary-based
pivot-eligibility filter, and the frontend not being wired up at all -- and BOTH appear
to have already been fixed since then (confirmed: `pivot_finder.py` now uses
`PROJECTION_TOLERANCE_PCT_OF_CASH_PROJECTION`, not a salary filter; the frontend wiring
described in that handoff's Finding 2 is live).

**This changes the shape of the next session's work, but not as far as "just wire in a
new score."** Greg's own words, said directly after seeing this section: **"the pivot
finder does exist but it doesn't currently function the way we need it to in order to
build these lineups correctly. we can piggyback off that or build on it but we can't
rely on it to get where we need to go."** Read that as the governing instruction, not
the "audit and extend" framing this section originally implied -- the existing
`leverage_score` mechanism is not assumed to be a reasonable base implementation that
just needs its ranking formula swapped. The plumbing (CSV contract, frontend panel,
weekly batch-run pattern) is worth REUSING. The actual construction/pivot/selection
LOGIC inside `pivot_finder.py` should be treated as likely inadequate for the validated
methodology (chalk anchor + salary-legal multi-swap combos + Monte Carlo worst-case
scenario ranking) until proven otherwise -- expect to build most of that logic fresh
(reusing `best_lineup_classic.py`'s scenario machinery and
`analysis/classic_diag/pivot_off_chalk.py`'s combo-generation approach as the real
starting point) and have it WRITE OUT to the file contract `pivot_finder.py` already
produces, rather than trying to reshape `pivot_finder.py`'s internals to match. Read
`scripts/pivot_finder.py` and `scripts/ownership_heuristic.py` in full before deciding
exactly how much of either is reusable (only skimmed this session, not fully read) --
but go in expecting "piggyback on the plumbing, replace the logic," not "light audit."

## 1. What today's session actually validated (full numbers in HANDOFF_dfs_army_variables.md section 8; summary here)

All against the same 6 real logged SE3max slates (wk1/wk2 main/early/afternoon),
replayed the same way as `scripts/replay_validation.py`.

| Method | Cash | Mean real percentile |
|---|---|---|
| Real submitted lineups (gmscott81, actual) | 0/6 | 0.367 |
| Pure real-field chalk (most-duplicated real lineup, no pivot) | 2/6 | 0.667 |
| Best from-scratch optimizer-built rule (`worst_top25_realstack` or `floor_sum`) | 3/6 | ~0.70 |
| **Chalk anchor + 1-3 same-position pivots, ranked by worst-case P(top-25%) across scenarios** | **4/6** | **0.819** |
| DST: literal cheapest salary, no matchup filter | 4/6 | 0.739 (but scored an ACTUAL -4.0 twice -- real tail risk, not hypothetical) |
| DST: cheapest-among-best-points-per-dollar-value (the recommended rule) | 2/6 | 0.691 (lower headline number, but confirmed real reason to prefer it -- see section 2) |
| V1 (stack by implied team total instead of QB projection) | 3/6 | 0.703 (byte-identical to the QB-projection baseline on 5/6 slates -- a clean null result) |

**V2 (pivot off chalk) is the single strongest result of the whole test campaign.** The
anchor was defined empirically, not guessed: the real field's most-duplicated exact
lineup on each slate (via `analysis/classic_diag/chalk_lineup_analysis.py`) -- NOT the
"highest-owned player at every slot" assembly, which busted the salary cap on all 6
slates when tried literally. Pivots were same-position swaps (RB<->RB, WR<->WR, TE<->TE)
to a lower-owned alternative, up to 3 at once, salary-legal, picked from the real
combinatorial pool by the same worst-case-across-scenarios Monte Carlo scoring
`analysis/classic_diag/best_lineup_classic.py` already implements
(`analysis/classic_diag/pivot_off_chalk.py`, new this session).

**A real bug was found and fixed during this build**: the pivot-combo generator could
independently pick the SAME replacement player for two different swapped-out slots,
producing an illegal duplicate-player roster. Fixed with a distinctness check plus an
assertion; the corrected run is what produced the 4/6/0.819 number above. If
`pivot_finder.py`'s existing multi-swap logic (if it has any -- unconfirmed, not yet
read in full) does something similar, check for the same class of bug.

## 2. The DST finding, and why the lower-cash-count option is still the recommendation

Greg's own reasoning, given directly this session and saved to memory
(`feedback_dst_lean_believable_over_cheapest.md`): a bad defense against a great
offense can put up a genuinely negative DK score in a blowout. That's not hypothetical --
it happened twice in this exact replay (Dolphins, -4.0, on two different slates), and
the version that avoided it (cheapest-by-points-per-dollar-value, landing on a real
Carolina-pattern DST both times it applied) never went negative and hit two 26-point
scores. The lower aggregate cash count for the smarter rule looks like small-sample /
candidate-pool noise on the 2 slates it "lost" (one of them picked the literal SAME DST
as the winning default pick -- the difference was elsewhere in the roster, not the DST
choice). **Recommendation stands: cheapest DST among the best points-per-dollar value
options (`final_projection / salary`), not literally the cheapest, and not paying all
the way up to a "safe" expensive DST either.**

## 3. The loose thread that needs resolving before combining everything: the "4/6, 0.709" number

`HANDOFF_dfs_army_variables.md` section 0 (written before this session's detailed work)
references an EARLIER, separate result: an "origin-based `*_stackonly`" selection rule
that reportedly hit 4/6 cash, mean pctile 0.709, by restricting candidate selection to
lineups whose STACK came from the explicit stack-generation loop (not by roster
structure). This number **was never reproduced against this session's final
apparatus** -- the code has since moved through `*_realstack` (structure-based, tested
this session: best variant `worst_top25_realstack` got 3/6, 0.703) and `*_validated`
(stricter structure check, tested this session: 3/6, 0.628) as successive attempts to
replicate or beat that predecessor, and **neither one actually matched it**. The
`*_stackonly` rule itself no longer exists in the current `replay_selection_criteria.py`
-- it was superseded, not preserved as a running comparison arm.

**RESOLVED, 2026-09-22 follow-up session.** Re-added the origin-tagged restriction
(`worst_top25_stackonly`/`avg_top25_stackonly` in `replay_selection_criteria.py`,
argmax-restricted to `out["is_stack_forced"]`, which was already being computed and
returned by `candidates()`/`score()` -- no new logic, just re-adding the unused mask)
and ran it against the CURRENT candidate-pool/scenario code on the same 6 slates
(n_candidates=80, field_n=6000, n_sims=800, seed=3 -- same params as this session's
other selection-criteria tests).

**Result: it reproduces EXACTLY -- 4/6 cash, mean pctile 0.709, matching the original
claim byte-for-byte.** Not a stale artifact of superseded code; it's a real,
reproducible result. BUT it's still weaker than V2 (chalk anchor + pivot, 4/6 cash,
0.819 mean pctile) -- same cash count, meaningfully worse percentile, and a
fundamentally different mechanism (restricts SELECTION to noise-loop candidates that
happened to come from the forced-stack generation loop, vs. V2's construct-off-the-
real-chalk-anchor-then-swap approach). **Verdict: retire "4/6, 0.709" as a standalone
number going forward -- don't average it in as extra confirmation. V2 (chalk anchor +
pivot, worst_top25 ranking) remains the single strongest validated result and is what
the live system should be built around.**

## 4. What "the system" likely needs to become (next session designs this properly -- this is a starting sketch, not a spec)

- **Anchor construction, made live-usable.** Today's replay anchor (real field's
  most-duplicated lineup) can't be known before lock. For a live slate, the anchor needs
  to come from `ownership_heuristic.py`'s own `chalk_scores_{site}_{week}.csv`
  (`estimated_ownership_pct`) instead of real post-lock ownership -- assembled
  CAP-LEGALLY (a greedy or ILP construction, not naive top-owned-per-slot, which busted
  the cap on every one of the 6 historical slates when tried literally this session).
- **Pivot ranking: build the validated logic fresh, don't retrofit `leverage_score`.**
  Greg's explicit call (see section 0): `pivot_finder.py` "doesn't currently function
  the way we need it to in order to build these lineups correctly... we can piggyback
  off that or build on it but we can't rely on it to get where we need to go." Its
  existing `leverage_score` (`ownership_edge_pts * projection_retention`) is a
  different, probably-never-replay-validated formula from what this session actually
  proved works (`worst_top25`: worst-case P(top-25%) across 4 correlated Monte Carlo
  scenarios, restricted to salary-legal multi-swap combos off a real chalk anchor). Go
  in planning to build the anchor + combo-generation + scenario-ranking logic fresh
  (starting point: `analysis/classic_diag/pivot_off_chalk.py` and
  `best_lineup_classic.py`), and have it feed the SAME output file contract
  `pivot_finder.py` already produces so the existing frontend panel keeps working --
  not to incrementally patch `pivot_finder.py`'s internals into shape. Still worth a
  real replay comparison against `leverage_score` once the new logic exists, same rigor
  this session applied throughout (see
  `feedback_rigor_over_reassurance_in_construction_testing.md`), but don't start from
  the assumption that `pivot_finder.py`'s current approach is a reasonable baseline.
- **DST rule wiring.** Unconfirmed whether `ownership_heuristic.py`/`pivot_finder.py`
  has ANY DST-specific logic today, or treats DST like any other position. Needs the
  points-per-dollar-value rule from section 2 wired in if not already present.
- **Performance for a live weekly run.** Today's Monte Carlo scoring
  (`n_candidates=80, field_n=6000, n_sims=800`) took 17-170 seconds per slate --
  fine as a one-time batch step near lock (matching how `pivot_finder.py` already seems
  to run offline into a static CSV), not fine if triggered per click in the frontend.
  Keep the existing "batch script writes a CSV, frontend just reads it" pattern rather
  than making the UI compute live.
- **Output file contract.** If the new scoring can be written into the SAME
  `pivot_suggestions_{site}_{week}.csv` / `chalk_scores_{site}_{week}.csv` shapes the
  frontend already reads, little or no frontend code needs to change. Confirm column
  compatibility (`leverage_score` is currently a displayed column -- decide whether it's
  replaced, or both are shown during a transition period) before touching
  `dfs_optimizer_frontend/index.html`.

## 5. Files this session created/modified (all uncommitted as of this handoff)

- `analysis/classic_diag/chalk_lineup_analysis.py` (new) -- empirical chalk-anchor
  definition from real field data (most-duplicated lineup + the salary-illegal
  highest-owned-per-slot assembly, for contrast).
- `analysis/classic_diag/pivot_off_chalk.py` (new) -- the V2 test; includes the
  duplicate-player bug fix and an assertion guarding against recurrence.
- `analysis/classic_diag/replay_v1_game_env.py` (new) -- V1 test, null result.
- `analysis/classic_diag/replay_v3a_cheap_dst.py` (new) -- V3a test, 3 DST variants.
- `analysis/classic_diag/replay_selection_criteria.py` (modified) -- added
  `floor_sum`/`floor_sum_validated` rules (V4 test).
- `analysis/classic_diag/best_lineup_classic.py` (modified) -- added `team_rank_key`
  (V1), `cheapest_dst_only`/`cheapest_viable_dst_only` (V3a), and `excluded_player_ids`
  threading through `candidates()`/`score()` to support both.
- `HANDOFF_dfs_army_variables.md` (modified) -- section 8 added with full V1/V4 numbers
  and the stale "DST-vs-opp-dst constraint not implemented" claim corrected (it's been
  live since Session 17, `optimizer.py` decision #56).
- Result CSVs: `analysis/classic_diag/replay_selection_criteria_results.csv`,
  `replay_v1_game_env_results.csv`, `replay_v3a_cheap_dst_results.csv`,
  `pivot_off_chalk_results.csv`.
- Memory: `feedback_dst_lean_believable_over_cheapest.md` (new).

**Commit these before or at the start of next session** -- nothing here has been
committed yet, per this project's "only commit when explicitly asked" convention.

## 6. Concrete starting checklist for next session

1. Read `scripts/pivot_finder.py` and `scripts/ownership_heuristic.py` in full.
2. Resolve the "4/6, 0.709" thread (section 3) -- reproduce or retire it.
3. Design the cap-legal live chalk-anchor construction from `chalk_scores`.
4. Build the chalk-anchor + multi-swap + Monte Carlo `worst_top25` pivot logic fresh
   (per Greg: don't rely on `pivot_finder.py`'s current logic to get there), then
   replay-compare it against `leverage_score` on the same 6 historical slates before
   fully cutting over.
5. Confirm/build the DST value rule inside the existing pipeline.
6. Decide the output file contract and any frontend changes needed.
7. Commit section 5's files.

## 7. What's explicitly NOT part of this build (per Greg, this session)

- V5 (no dart plays in single-entry SE3max) -- accepted as correct on Greg's own
  conviction, not tested, not gating anything here.
- Nothing about MME/multi-entry strategy -- this whole system is single-entry-focused
  (Greg plays SE3max as effectively single-entry; see his correction earlier this
  session that a "submit multiple diversified lineups" recommendation doesn't apply to
  his real usage).
