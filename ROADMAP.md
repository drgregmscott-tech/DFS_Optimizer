# NFL DFS Optimizer — Build Roadmap

**Target milestones:**
- Preseason Week 1 (Aug 13-15, 2026) — first live dry run against real data
- Preseason Weeks 2-3 (Aug 20-29) — refinement cycles
- Regular Season Week 1 (Sept 9, 2026) — go-live

**Rule for every session below:** a session is not "done" until its validation step passes. If validation fails, that session isn't complete — you don't move to the next one.

**Repo structure assumed throughout:**
```
/dfs_optimizer
  /data           <- raw + processed data files
  /scripts        <- all pipeline scripts
  /output         <- generated projections, lineups
  /logs           <- session log + automation run logs
  SESSION_LOG.md
  ROADMAP.md
```

**How to use this for session handoff:** at the start of each new session, provide: (1) this session's card below, (2) the relevant SESSION_LOG.md entries for prerequisite sessions, (3) the actual current contents of any files listed under "Files touched." That's the full context a fresh session needs — no need to re-explain the whole project.

---

## PHASE 1 — Foundation & Data Pipeline
*Target: July 20-27*

### Session 1.1 — Environment & Repo Setup
**Prerequisites:** None — first session.

**Files touched (created):**
- `/dfs_optimizer/requirements.txt`
- `/dfs_optimizer/README.md`
- `/dfs_optimizer/.gitignore`
- Folder structure: `/data`, `/scripts`, `/output`, `/logs`

**Inputs:** None.

**Outputs:** A cloneable repo that installs cleanly.

**Build:**
- GitHub repo, Python environment, folder structure above
- Install core libraries: `nfl_data_py`, `pandas`, `numpy`, `pulp` (or `ortools`)
- `requirements.txt` pinned to working versions

**Validation (required to close session):**
- [ ] Fresh clone of the repo + `pip install -r requirements.txt` runs without error on a clean environment
- [ ] `import nfl_data_py` and a test pull of one week of prior-season data succeeds

**Handoff notes to log:** which Python version used, any OS-specific install issues hit and how resolved.

---

### Session 1.2 — Historical Data Ingestion
**Prerequisites:** Session 1.1 complete (environment working).

**Files touched (created):**
- `/dfs_optimizer/scripts/ingest_historical.py`
- `/dfs_optimizer/data/weekly_stats_{season}.parquet` (output)

**Inputs:** None (pulls directly from nflverse via `nfl_data_py`).

**Outputs:** `weekly_stats_{season}.parquet` — one row per player per week, columns include player_id, player_name, position, recent_team, opponent_team, week, raw stat columns.

**Build:**
- Script to pull weekly player stats, schedules, and rosters via `nfl_data_py`
- Store as local parquet (switch to Supabase/Postgres later only if you need it queryable from the frontend directly)

**Validation:**
- [ ] Pull returns expected row counts for a known week (spot-check against Pro Football Reference)
- [ ] Re-running the script doesn't duplicate rows (idempotency check)

**Handoff notes to log:** exact schema/column names produced (paste the `.columns` output) — every future session depends on knowing these exactly.

---

### Session 1.3 — Salary Data Ingestion
**Prerequisites:** Session 1.2 complete (need player_id scheme to match against).

**Sites:** DraftKings AND FanDuel — both required. See Notes on dual-site scope, below Phase 9, for what this means project-wide.

**Files touched (created):**
- `/dfs_optimizer/scripts/ingest_salaries.py` (takes a `--site {dk,fd}` flag)
- `/dfs_optimizer/data/salaries_{site}_{slate_id}.csv` (output — one per site per slate)
- `/dfs_optimizer/data/name_mapping.csv` (manual override table for unmatched names, scoped per site)

**Inputs:** Manually downloaded salary CSV per site (place in `/data/raw_salaries/`) — DK's "Export to CSV" from the player pool, or DK's "DKEntries.csv" bulk-upload template (both shapes are real files users have on hand and both are supported); FD's Classic slate CSV export.

**Outputs:** Normalized salary table per site with player_id matched to the Session 1.2 schema. DK: $50,000 cap, roster QB/RB/RB/WR/WR/WR/TE/FLEX/DST, full-PPR scoring. FD: $60,000 cap, roster QB/RB/RB/WR/WR/WR/TE/FLEX/DEF, half-PPR scoring. (Cap/roster/scoring are carried as metadata in `ingest_salaries.py`'s `SITE_CONFIGS` for Session 3.1 and Phase 2 to read, not used by this script directly.)

**Build:**
- Script to ingest DK and FD salary CSV exports (neither site has a stable free public API for this — stays a manual download step for both)
- Site-specific column parsing (DK and FD use different export layouts entirely) feeding into shared name/team normalization and matching logic
- Handle each site's team-defense position label separately (DK: `DST`; FD: `D`/`DEF`) — routed to a synthetic id, not a real player_id
- Handle site-specific position quirks (e.g. DK has no fullback slot and folds FB into RB — confirmed via real data in this session's revision)
- Normalize player names/teams to match nflverse player IDs from Session 1.2
- Build `name_mapping.csv` as a persistent, per-site override table for known mismatches (e.g., nicknames like "Drew" vs "Andrew") so you're not re-solving the same mismatches every week

**Validation:**
- [ ] 100% of players in a sample salary file successfully match to a player_id from Session 1.2's dataset, OR every non-match is a confirmed real data gap (e.g. player had zero games in the reference season) rather than a matching bug — for both sites
- [ ] Unmatched players are logged clearly to a file, not silently dropped — for both sites

**Handoff notes to log:** list of name-mismatch patterns found and added to `name_mapping.csv` per site — this list will keep growing, note it every session it changes. Note explicitly whether each site's validation used real or synthetic salary data, since a site validated only on synthetic data needs re-checking against a real file before Session 2.4/3.1 depend on it.

---

## PHASE 2 — Projection Engine
*Target: July 27 - Aug 3*

### Session 2.1 — Season Baseline + Recent Form
**Prerequisites:** Session 1.2 complete. Need `weekly_stats_{season}.parquet`.

**Sites:** Fantasy points differ by site (DK = full PPR, FD = half PPR — see `ingest_salaries.py`'s `SITE_CONFIGS` from Session 1.3), so this session computes and outputs per site.

**Files touched (created):**
- `/dfs_optimizer/scripts/projections_baseline.py` (takes a `--site {dk,fd}` flag)

**Inputs:** `/data/weekly_stats_{season}.parquet`

**Outputs:** `/output/baseline_recent_form_{site}_{season}_{week}.csv` — columns: player_id, player_name, position, season_avg, recent_form, games_played

**Build:**
- Season baseline calculation (from earlier blended_projections.py logic), using the site's scoring rule (full PPR for DK, half PPR for FD) to compute fantasy_points from raw stats
- Recency-weighted recent form calculation

**Validation:**
- [ ] For 5 known players, manually hand-calculate expected baseline/recent-form values and confirm the script matches — for both sites (the same 5 players, since the underlying stats are identical, only the scoring differs)
- [ ] Script handles players with <5 games played (rookies, midseason signings) without crashing
- [ ] Spot-check that a player's DK and FD season_avg differ by roughly the expected half-point-per-reception gap, not by something unexplained

**Handoff notes to log:** the 5 players used for manual verification and their confirmed values, for both sites (reusable regression test later).

---

### Session 2.2 — Matchup Factor
**Prerequisites:** Session 1.2 complete.

**Sites:** Same reasoning as 2.1 — points allowed by position depends on the scoring rule, so this runs per site.

**Files touched (created):**
- `/dfs_optimizer/scripts/projections_matchup.py` (takes a `--site {dk,fd}` flag)

**Inputs:** `/data/weekly_stats_{season}.parquet`

**Outputs:** `/output/matchup_factors_{site}_{season}_{week}.csv` — columns: team, position, matchup_factor

**Build:**
- Opponent points-allowed-by-position calculation (using the site's scoring rule), normalized to league average

**Validation:**
- [ ] Spot-check 2-3 known "good matchup" / "bad matchup" cases against public matchup rankings — for both sites
- [ ] Confirm matchup_factor of exactly 1.0 for a league-average defense (sanity check on the normalization math) — for both sites

**Handoff notes to log:** the specific matchups spot-checked and source used to verify.

---

### Session 2.3 — Vegas Integration
**Prerequisites:** None (independent data source), but needs a team-name key consistent with Session 1.2's `recent_team` values.

**Sites:** Site-agnostic — implied team totals don't depend on which DFS site you're building for, so this session's output is shared by both.

**Files touched (created):**
- `/dfs_optimizer/scripts/vegas_odds.py`
- `/dfs_optimizer/config/api_keys.env` (gitignored — never commit this)

**Inputs:** The Odds API (free tier, requires signup for API key).

**Outputs:** `/output/vegas_implied_totals_{week}.csv` — columns: team, spread, over_under, implied_total

**Build:**
- Connect to The Odds API (500 req/month free)
- Calculate implied team totals from spread + total
- Team name normalization to match Session 1.2/1.3 naming (odds APIs often use different team name formats — e.g. "LA Rams" vs "LAR")
- Consensus across books: average spread/total across every US-region bookmaker returned per game, rather than pinning to one book, so a single outlier line doesn't skew the implied total.

**Confirmed polling cadence (for Session 5.2 to implement, budgeted here):**
- Tue–Fri: 1 pull/day
- Saturday: 2 pulls/day
- Sunday, 4hrs–1hr before lock: 1 pull/hour
- Sunday, final hour before lock: 1 pull/15min
- = 14 pulls/week, 2 credits/pull (spreads+totals, us region only) = **28 credits/week, ~121 credits/month** — leaves ~380 credits/month of headroom on the free tier for NFL alone. This does NOT cover a second daily-cadence sport (see dual-site-scope-style note below on multi-sport odds vendor, bottom of file) — re-budget before adding NBA/NHL/MLB.

**Validation:**
- [ ] Pulled odds match what's publicly shown on a sportsbook site at the same timestamp
- [ ] Implied total calculation verified by hand for 3 games (favorite/underdog sign errors are the classic bug)
- [ ] Implied totals for each game sum back to that game's total (built into `vegas_odds.py` as an automated check, not just manual)

**Handoff notes to log:** confirm API key is stored in `.env` and gitignored, not hardcoded — flag explicitly in the log that this was checked. Also log whether real-line validation was possible at build time or deferred (preseason lines may not be posted yet depending on when this session runs — Preseason Week 1 is Aug 13-15, 2026).

---

### Session 2.4 — Full Blend Pipeline
**Prerequisites:** Sessions 2.1, 2.2, 2.3 all complete.

**Sites:** Runs once per site (DK and FD), since it joins in each site's salary file and site-specific projection inputs from 2.1/2.2.

**Files touched (created):**
- `/dfs_optimizer/scripts/build_projections.py` (merges outputs of 2.1-2.3, takes a `--site {dk,fd}` flag)

**Inputs:**
- `/output/baseline_recent_form_{site}_{season}_{week}.csv`
- `/output/matchup_factors_{site}_{season}_{week}.csv`
- `/output/vegas_implied_totals_{week}.csv` (shared across sites)
- `/data/salaries_{site}_{slate_id}.csv` (for player pool / salary join)

**Outputs:** `/output/final_projections_{site}_{week}.csv` — columns: player_id, player_name, position, team, salary, season_avg, recent_form, matchup_factor, vegas_factor, final_projection

**Build:**
- Combine all four components into final_projection using the blend formula
- Output the clean weekly projections table, per site

**Validation:**
- [ ] Run end-to-end on a full past week of real data, output has no negative projections, no nulls, no unexpectedly missing players — for both sites
- [ ] Top 10 projected players for a past week roughly align with what actually happened (sanity check, not accuracy check yet) — confirm DK and FD rankings are close but not identical (half-PPR should nudge pass-catching specialists down and volume rushers up relative to DK)

**Handoff notes to log:** the exact blend formula/weights used at this point (these will change later in Phase 9 — log the starting values so drift is trackable). Confirm both sites' formulas use the same weights (0.5/0.5/matchup/vegas) — only the input fantasy_points values should differ by site, not the blend logic itself, unless a reason emerges to diverge them later.

---

## PHASE 3 — Optimizer Core
*Target: Aug 3-10*

### Session 3.1 — Single Lineup Optimizer
**Prerequisites:** Session 2.4 complete. Need `final_projections_{week}.csv`.

**Files touched (created):**
- `/dfs_optimizer/scripts/optimizer.py`

**Inputs:** `/output/final_projections_{site}_{week}.csv`

**Outputs:** `/output/lineup_single_{site}_{week}.csv` — one optimal lineup, columns: roster_slot, player_name, position, team, salary, projection

**Sites:** Runs once per site, reading cap/roster config from `ingest_salaries.py`'s `SITE_CONFIGS` (Session 1.3) rather than hardcoding: DK = $50,000 cap, QB/RB/RB/WR/WR/WR/TE/FLEX/DST; FD = $60,000 cap, QB/RB/RB/WR/WR/WR/TE/FLEX/DEF.

**Build:**
- PuLP/OR-Tools integration: salary cap + roster position constraints, parameterized per site instead of hardcoded to one site's rules

**Validation:**
- [ ] Output lineup is under salary cap and satisfies every position requirement (write this as an automated assertion in the script, not manual eyeballing) — for both sites, confirming each uses its own cap/roster, not DK's by default
- [ ] Manually verify no single-player swap would increase points without breaking a constraint — for both sites

**Handoff notes to log:** which solver library ended up being used and why, if PuLP vs OR-Tools decision came up. Confirm both sites' constraint sets were verified independently, not just DK with FD assumed to follow.

---

### Session 3.2 — Multi-Lineup Generation + Exposure Limits
**Status:** ✅ Complete (2026-07-22) — see SESSION_LOG.md for full detail.

**Prerequisites:** Session 3.1 complete.

**Files touched (modified):**
- `/dfs_optimizer/scripts/optimizer.py` (extended, not replaced)

**Inputs:** `/output/final_projections_{site}_{week}.csv`

**Outputs:** `/output/lineups_multi_{site}_{week}.csv` — N lineups, one lineup_id column added

**Build:**
- Generate N lineups with max-exposure caps per player (e.g., no player in more than 40% of lineups)

**Validation:**
- [x] Generate 20 lineups per site, confirm no player exceeds the exposure cap set
- [x] Confirm lineups are meaningfully different from each other, not near-duplicates

**Handoff notes to log:** default exposure cap chosen and why — note if it differs by site (e.g. FD's higher cap could justify a different default) or is kept the same intentionally.

**Resolution:** default exposure cap = 40% (`DEFAULT_MAX_EXPOSURE_PCT = 0.40`), matching this card's own example figure. Kept the same for both DK and FD intentionally — exposure is a portfolio-construction choice, not tied to a site's salary/roster structure, unlike e.g. Session 4.1's site-specific chalk_score. `--max-exposure` remains a CLI override per run if a future session finds a reason to split it by site. Diversity enforced via a hard minimum-swap ILP constraint (default 3 players) between every pair of lineups, with automatic relaxation + stderr warnings if the (currently thin, real-data test) pool can't support it — full reasoning in `optimizer.py`'s decisions #5-8. Both sites hit 20/20 lineups at the default settings against the current test pool; the relaxation path is implemented but not yet stress-tested against real infeasibility — flagged as a good target for a future session's validation, not blocking.

**Addendum (2026-07-22):** projection randomization added -- an optional `--randomization-pct` (0=off default, typically 1-40 when used) that perturbs each player's projection via a normal distribution (mean = real projection, std_dev = pct% of it) before that lineup's solve, on top of (not instead of) the swap-uniqueness constraint above. Available in both single- and multi-lineup modes; multi-lineup mode draws independently per lineup. See `optimizer.py` decisions #9-13 and SESSION_LOG.md's addendum entry for full reasoning and validation.

**Addendum 2 (2026-07-22):** the swap-uniqueness control was renamed `min_unique_swaps` -> `uniqueness` (`--uniqueness`) to match standard DFS-optimizer terminology, and its default changed from 3 to 1, both user-directed. Re-validating at the new default surfaced a real (not previously observed) finding on DK's thin real-data test pool: at `uniqueness=1` + 40% exposure + 20 lineups, the pool runs out of genuinely distinct legal lineups before reaching 20, and the documented relaxation fallback (working as designed) permits one exact-duplicate pair rather than stopping early. FD was unaffected (0 relaxations, 0 duplicates) at the same settings. This is attributed to the already-documented "Known Testing Artifact" (DK's test pool has only 4 non-zero-projection QBs) -- flagged as worth re-checking once a real full-size DK slate exists, not assumed fixed. See SESSION_LOG.md's addendum 2 entry for full detail.

---

### Session 3.3 — Stacking Rules
**Status:** ✅ Complete (code + synthetic-data validation, 2026-07-22; real-DK-data validation + a real bug fix same day via addendum) — see SESSION_LOG.md for full detail. **FD real-data validation still pending**, same pre-existing gap as everything else FD — see the "Known Deferred Validations" section below.

**Prerequisites:** Session 3.2 complete.

**Files touched (modified) -- expanded from the original card's scope, see SESSION_LOG.md:**
- `/dfs_optimizer/scripts/optimizer.py` (as originally scoped)
- `/dfs_optimizer/scripts/build_projections.py` -- **not on the original card.** Stacking needs each player's week-N opponent and each team's Vegas implied total to auto-select and validate stacks; neither was ever written to `final_projections_{site}_{week}.csv` (both existed only as internal variables in build_projections.py). Added as three new output columns -- `opponent`, `implied_total`, `over_under` -- purely additive, no existing column's values changed. **Any `final_projections_*.csv` generated before this session needs to be regenerated before stacking will work against it** (`load_final_projections()` in optimizer.py now hard-requires the two new columns and will raise a clear SystemExit if they're missing).

**Inputs:** `/output/final_projections_{site}_{week}.csv` (now including `opponent`/`implied_total`/`over_under`).

**Outputs:** `/output/lineup_single_{site}_{week}.csv` and `/output/lineups_multi_{site}_{week}.csv` (both now include an `opponent` column always; multi-lineup output adds a `stack_target` column when stacking is used) -- a small output-schema change from Sessions 3.1/3.2's shipped files, flagged not hidden.

**Build -- full taxonomy, user-directed scope expansion beyond the card's original two items (discussed and confirmed with the user before building, see SESSION_LOG.md):**
- QB stack (`--stack-mode qb`), size 1-3 via `--stack-size`, covers Standard/Double/Triple stacks and QB+RB depending on `--stack-positions` (default WR/TE/RB -- "any pass-catcher," user-confirmed)
- Bring-back (`--bring-back`), an add-on to a QB stack requiring >=1 opponent skill player
- Game Stack / Shootout (`--stack-mode game`), standalone, no QB required
- Mini-Stack (`--stack-mode mini`), two types via `--mini-stack-type`: same-team RB+DST, or opposing pass-catchers
- Team/game selection: auto (highest Vegas implied_total/over_under) by default, `--stack-team`/`--stack-game` to pin
- Multi-lineup batches diversify across a rotating candidate pool by default when auto-selecting; a pin forces the whole batch to one target (`--stack-diversify` to override)

**Validation:**
- [x] Every generated lineup with stacking enabled actually contains the required correlated players — for both sites (validated via `validate_stack()`, a new function mirroring `validate_lineup()`'s existing automated-assertion pattern — not eyeballed)
- [x] Confirm an intentionally too-strict stack rule fails loudly (raises an error), not silently — confirmed via a deliberately-impossible request (triple-TE stack against a team with 1 real TE), raises `RuntimeError` with a specific reason before the solver even runs
- [ ] **Real-data re-validation** — all validation above ran against a synthetic 8-team/64-player fixture (no real repo data was available in the environment this session was built in). Needs re-running against a real `final_projections_{site}_{week}.csv` (regenerated with the new columns first) before this is trusted for a live/dry-run context.

**Handoff notes to log:** all four stacking types from the user's full taxonomy were built (none deferred) -- see SESSION_LOG.md for the complete decision list (#14-21) and the 13-scenario test matrix.

---

## PHASE 4 — Ownership & Pivot Logic
*Target: Aug 10-13*

### Session 4.1 — Chalk Score Heuristic
**Prerequisites:** Session 2.4 complete (needs final_projections + salary data).

**Files touched (created):**
- `/dfs_optimizer/scripts/ownership_heuristic.py`

**Inputs:** `/output/final_projections_{site}_{week}.csv`

**Outputs:** `/output/chalk_scores_{site}_{week}.csv` — columns: player_id, chalk_score (0-100 scale), **estimated_ownership_pct (0-100 scale, added same-day addendum — see below)**

**Sites:** Computed per site — chalk/ownership perception is driven by that site's own salary and value context, not shared, since DK and FD price (and therefore "value") the same player differently.

**Build:**
- Value + salary tier + Vegas total + manual name-recognition flag list → chalk_score
- **Addendum (same session):** chalk_score is a relative ranking with no real-world anchor — user asked directly for an actual percentage estimate that can be refined over time as real data comes in, not just a rank. Added `estimated_ownership_pct`: chalk_score converted to a percentage via a softmax within each position group, scaled so each group's TOTAL ownership matches a real structural fact (roster-slot math: every lineup fills exactly N slots of a position, so total ownership across that position's eligible pool should land near N × 100 percentage points — FLEX split evenly across RB/WR/TE, no real per-position FLEX usage-rate data exists yet). Still not real data, but anchored to something real instead of an arbitrary curve. Full reasoning: `ownership_heuristic.py`'s module docstring, decision #5.

**Validation:**
- [x] Rank last week's players by chalk_score, compare relative order to actual published ownership for that site (if available) or intuition as a gut-check on direction, not precision — check both DK and FD ownership patterns separately, don't assume they match. No real published ownership exists for this synthetic Madden Stream contest (same class of gap as everything else FD -- see ROADMAP.md's FanDuel validation gap note), so this ran as the card's own allowed fallback: an intuition gut-check, on the real 6-team pool (CLE/DAL/HOU/IND/MIA/WAS). Passed for both sites -- see SESSION_LOG.md's Session 4.1 entry for the actual numbers.
- [x] `estimated_ownership_pct` addendum: confirmed each position group's total estimated ownership matches its roster-slot budget exactly (both sites) — see SESSION_LOG.md's Session 4.1 (ADDENDUM) entry for the actual per-group numbers. Confirmed bye/no-real-game players (final_projection == 0) correctly get exactly 0.0%, with their share of the budget redistributed to real players, not left as a phantom floor value.

**Handoff notes to log:** the manual name-recognition flag list used (this needs periodic updates as player profiles change season to season) — note if it's shared across sites or needs site-specific entries. `OWNERSHIP_SOFTMAX_TEMPERATURE` (currently 15.0, unfit to real data) is the clearest first target for Session 9.3/9.4 below once real ownership data exists.

---

### Session 4.2 — Cash-to-GPP Pivot Logic
**Prerequisites:** Sessions 3.1 and 4.1 complete.

**Files touched (created):**
- `/dfs_optimizer/scripts/pivot_finder.py`

**Inputs:** `/output/lineup_single_{site}_{week}.csv`, `/output/chalk_scores_{site}_{week}.csv`, `/output/final_projections_{site}_{week}.csv`

**Outputs:** `/output/pivot_suggestions_{site}_{week}.csv` — per cash-lineup player, top 2-3 ranked pivot candidates with leverage_score

**Sites:** Runs per site, since pivots are found within one site's own player pool/salary structure — a DK pivot suggestion is meaningless for an FD lineup and vice versa.

**Build:**
- Given a cash lineup, generate ranked pivot suggestions per position based on leverage score
- **Decision (user-confirmed, resolving Session 4.1 addendum's open item):** uses `estimated_ownership_pct`, not `chalk_score`, as the ownership signal for picking pivot targets. Consequently the validation checkbox below checks `estimated_ownership_pct`, not `chalk_score` — see `pivot_finder.py`'s module docstring, decision #1.
- **Join decision:** `lineup_single_{site}_{week}.csv` (Session 3.1) has no `player_id` column — joins to `chalk_scores`/`final_projections` via normalized `(player_name, position, team)` instead, reusing `ingest_salaries.py`'s existing normalization helpers. Full reasoning: decision #2.
- **Salary tolerance decision:** a percentage of that site's cap (default 10%), not a flat dollar amount — travels between DK's $50K and FD's $60K cap unchanged. Full reasoning: decision #3.

**Validation:**
- [x] For a test cash lineup on each site, confirm every suggested pivot is same position, within salary tolerance, and has a lower **estimated_ownership_pct** than the player it replaces (see decision above re: chalk_score to estimated_ownership_pct) — ran against real data, both sites: 26 suggestion rows each, all passed the script's own validate_pivot_suggestions() assertion, independently re-verified same-position a second way by cross-referencing final_projections_{site}_10.csv directly. See SESSION_LOG.md's Session 4.2 entry for the actual numbers.
- [x] Confirm pivot swap doesn't break salary cap for the full lineup (using that site's cap) — hard-filtered in find_pivots_for_player() (a candidate that would break the cap never appears in the output), confirmed on real data both sites (DK cap $50,000, max post-swap total seen $48,400; FD cap $60,000). See SESSION_LOG.md's Session 4.2 entry.

**Handoff notes to log:** salary tolerance and projection tolerance values chosen for "acceptable" pivots — note if tolerance is an absolute dollar amount (which would need to scale between DK's $50K and FD's $60K cap) or a percentage of cap (which travels between sites unchanged). **Resolved:** percentage of cap, default 10% — see decision above.

---

### Session 4.3 — Pivot Eligibility Filter Correction + Frontend Pivot Panel
**Prerequisites:** Session 4.2 complete. Triggered by a handoff finding from the NHL Optimizer project (`NFL_pivot_ui_handoff.md`), not a scheduled card.

**Files touched (modified):**
- `scripts/pivot_finder.py`
- `dfs_optimizer_frontend/index.html`
- `.github/workflows/refresh_data.yml`
- `scripts/generate_synthetic_slate.py` (created — kept in the toolkit for future use, not a one-off)

**Inputs:** `output/lineup_single_{site}_{slate_id}.csv`, `output/final_projections_{site}_{slate_id}.csv` (unchanged from 4.2, except see Finding 3 below)

**Outputs:** `output/pivot_suggestions_{site}_{slate_id}.csv` (unchanged shape, new eligibility basis — see below)

**Sites:** Runs per site, unchanged from 4.2.

**Build — four real findings, all fixed in this session:**

1. **Eligibility basis changed from salary-band to projection-band** (the NHL handoff's core finding, confirmed to apply here too): candidates are now filtered by similarity in `final_projection`, not `salary`. Salary is a weak proxy for "similar projected output" since it also prices in matchup/role certainty/market perception, not just points. New default: `PROJECTION_TOLERANCE_PCT_OF_CASH_PROJECTION = 25.0`, symmetric off the cash player's own projection — chosen from a real-data 15/25/35% comparison against this project's own Madden Sim pool (not copied from NHL's fitted value). Salary is now informational-only output (`salary_diff`/`salary_diff_pct` columns), not a gate. Full reasoning: `pivot_finder.py` decision #3.
2. **`chalk_scores` join bug** (found while re-validating on real data, unrelated to Finding 1): `build_projections.py`'s `add_ownership_columns()` (a frontend-driven change made after Session 4.2 shipped) started baking `chalk_score`/`estimated_ownership_pct` directly into `final_projections_{site}_{slate_id}.csv`. `pivot_finder.py`'s old merge against a separate `chalk_scores` file therefore joined two DataFrames that both already had `estimated_ownership_pct`, silently producing `..._x`/`..._y` suffixed columns and crashing downstream with an opaque `KeyError`. Fixed by reading `estimated_ownership_pct` straight off `final_projections`, dropping the `chalk_scores` dependency entirely. Decision #0.
3. **`--week` vs `--slate-id` mismatch** (found live, on a real non-numeric slate_id): this script predates the slate-management rework (Session 7.4) and still took `--week`, building every filename as `{site}_{week}.csv`. Every other script (`build_projections.py`, `optimizer.py`) moved to `--slate-id` a while back. The gap was invisible during this session's own earlier real-data test because that test happened to use `"10"` as both a week number and a literal slate_id. Fixed throughout — this script now takes `--slate-id` exclusively, matching `build_projections.py`/`optimizer.py`. The same stale assumption was also found and fixed in `refresh_data.yml` (the automated pivot-suggestion rebuild step) and `index.html`'s pivot-panel empty-state message. Decision #0b.
4. **Frontend pivot panel** (the handoff's Finding 2): click a roster row → a panel expands below it showing that player's ranked pivot candidates (salary Δ, projection Δ%, ownership edge, leverage score) with a Swap In button per candidate. User-confirmed design: same panel-below-the-row pattern on desktop and mobile (no separate side panel), and swap works against whichever lineup is currently on screen — not restricted to a single "cash lineup" mode, since the user doesn't functionally distinguish cash from GPP builds in how they use the optimizer. Pivot suggestions load as their own file kind (`pivots`), paired to whichever slate/lineup they belong to, reusing the existing cloud-sync plumbing but deliberately NOT registered in the visible slate dropdown (a pivot file isn't something you'd select as "the active slate" on its own).

**Also found and fixed in the same pass (not part of the original 4 findings, surfaced by actually running things on real data):**
- A latent `NameError` (undefined `week` variable) in a join-failure error message that would have crashed instead of printing a helpful error.
- A Python 3.14 argparse crash from an unescaped literal `%` in a `--projection-tolerance-pct` help string (same class of issue as the project's known argparse `%`-escaping gotcha).
- `generate_synthetic_slate.py`'s FD defense rows were labeled position `"D"` instead of the `"DEF"` `optimizer.py`'s `roster_slots` actually requires — a mismatched label that gave FD's DEF slot zero eligible players, making the ILP structurally infeasible regardless of anything else in the pool. Fixed by deriving the label from the intersection of `roster_slots` and `defense_position_values` instead of guessing.
- The frontend was trusting whichever site the toggle happened to be on at upload time, with no check against the file itself — an FD upload while the toggle sat on DK silently saved as a DK slate. Fixed: site is now detected from the filename itself (every real output filename already has it embedded) and the toggle auto-switches to match, with a status note confirming the switch.

**Validation:**
- [x] Finding 1 (projection-band filter): validated against the real 245-player DK / 48-player FD Madden Sim pool (tolerance comparison), then full-pipeline smoke-tested end-to-end (24 pivot rows, all passed `validate_pivot_suggestions()`), then re-validated a second time after the slate-id fix against a real, freshly-ingested FD synthetic slate (`synthetic_08022026b`) — 11 pivot suggestion rows, leverage_score range 0.6-40.9, real command output captured.
- [x] Finding 2 (frontend panel): full click-through by the user in the deployed UI, both DK (`madden_08022026`) and FD (`synthetic_08022026b`) — "looked good," including the Swap In flow.
- [x] Finding 3 (slate_id fix): re-run against a deliberately non-numeric slate_id (`test_slate_abc`) to prove the fix, then confirmed on the user's own real run.
- [x] Finding 4 (site-detection fix): fixed after being caught live by the user during the click-through (uploading an FD file showed as DK); no separate synthetic repro needed since the real bug was the reproduction.
- [x] `node --check` clean on the extracted `index.html` script block after every edit round.
- [x] `refresh_data.yml` — YAML parses clean (`pyyaml.safe_load`) after every edit round.

**Decisions made / assumptions taken:**
- **25% projection tolerance is a starting heuristic, not a fitted value** — chosen from real DK/FD pool data this session, explicitly flagged as unfit to full-season data (Madden Sim / synthetic pool only). Retuning target once real regular-season usage exists, same status as `OWNERSHIP_SOFTMAX_TEMPERATURE`.
- **Empty pivot result is legitimate information, not an error** (decision #7, carried from 4.2, re-confirmed under the new filter) — "no real same-tier alternative on this slate" is accepted as-is, never triggers auto-widening the tolerance.
- **`generate_synthetic_slate.py` kept in the toolkit** (user-confirmed) rather than treated as a one-off script — reuses real player names/teams via `ingest_salaries.py`'s own `build_player_reference()`, fabricates only salaries/matchups/game info (flagged `ARBITRARY`), and feeds into the real `ingest_salaries.py` exactly like a real download rather than hand-fabricating the post-ingest schema.
- **FD still has no real (non-synthetic) slate validated** — the synthetic slate proved the pipeline and UI work end-to-end, but says nothing about real pivot-suggestion quality. Real FD validation remains gated on real FD export data (~Aug 13-15), unchanged from every prior session's note.

**Known issues deferred:**
- None blocking — user confirmed the full click-through "looked good" on both sites, no rough edges flagged.
- Real FD data validation — carried forward, unchanged gap.

**Handoff notes for next session:**
- Test artifacts left in place by user's own choice (not cleaned up): `FDSalaries_synthetic.csv` in repo root, `synthtest`/`synthetic_08022026`/`synthetic_08022026b` slate_ids in `data`/`output`. Harmless, not wired into anything that would confuse a future real run — fine to ignore or clean up later.
- If a future session finds another script still assuming `--week` instead of `--slate-id`, that's the same bug class as Finding 3 here — the slate-management rework (Session 7.4) didn't touch every script that existed before it, and this session found two more instances of it (`pivot_finder.py`, `refresh_data.yml`) that had gone unnoticed. Worth a deliberate audit if time allows.

---

## PHASE 5 — Status Automation & Scheduling
*Target: Aug 10-13, parallel with Phase 4*

### Session 5.1 — Injury/Active Status Pull
**Status:** 🟡 Mechanism complete and validated on real data; one validation item intentionally deferred (see below) — same "can't fully validate until real data exists" pattern as the Vegas-lines and FD-salary gaps elsewhere in this roadmap. Not blocking — Session 5.2 has no dependency on the deferred item.

**Prerequisites:** Session 1.2 complete (need player_id matching scheme).

**Sites:** Site-agnostic — a player's injury status is the same fact regardless of which DFS site you're building for, so this session's output is shared by both.

**Files touched (created):**
- `/dfs_optimizer/scripts/status_check.py`

**Files touched (modified):**
- `/dfs_optimizer/scripts/optimizer.py` — one-line bug fix, found during this session's real validation testing, unrelated to this session's own scope. See SESSION_LOG.md's Session 5.1 entry for details.

**Inputs:** ESPN's per-team roster endpoint (`site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{id}/roster`) — see decision #1 in `status_check.py`'s module docstring for why this endpoint was chosen over two other real ESPN options that were tried and rejected. Last verified working: 2026-07-22.

**Outputs:** `/output/player_status_{week}_{timestamp}.csv` — columns: player_id, player_name, team, position, status (OUT/DOUBTFUL/QUESTIONABLE/ACTIVE), raw_status, last_updated, match_method.

**Build:**
- ESPN injury endpoint integration
- Status filter logic (OUT excludes from optimizer input; QUESTIONABLE flags but doesn't exclude) — implemented as a second `status_check.py` subcommand (`apply`) that zeroes `final_projection` for OUT players by reusing `build_projections.py`'s existing zero-out convention (decision #4b), rather than adding a filter step to `optimizer.py` itself. This is what let the whole session ship with only one file touched, per this card's own file list.

**Validation:**
- [ ] Cross-check pulled statuses against NFL.com's official injury report for the same day — must match. **Deferred, not failed:** pulled live 2026-07-22 (off-season/training camp) — every real non-empty status found was tied to a long-term injury recovery or personal situation, not a game-week designation, since no real NFL game exists yet to designate a player in/out FOR. There's nothing on NFL.com's injury report to cross-check against yet either. First real point this closes: Preseason Week 1 (Aug 13-15, 2026), same checkpoint as this roadmap's other deferred-validation gaps — see "Known Deferred Validations" below.
- [x] Confirm OUT players are actually excluded from optimizer output for both sites (run optimizer with a test OUT player, confirm absence in both DK and FD results), not just flagged in a column nobody reads. **Validated for real, DK side:** a real, previously-nonzero player (Jonathan Taylor, IND RB, real week-10 `final_projection` of 17.25) was manually forced to OUT status and run through the full real pipeline (`status_check.py apply` → `optimizer.py`) in the user's own environment. Confirmed absent from the resulting lineup; optimizer ran clean with no zero-projection-selected warning. **FD side not separately re-run** — the exclusion mechanism (zeroing `final_projection` before `optimizer.py` ever sees the file) is site-agnostic by construction, same file/column contract either site reads, so this is treated as covered by construction rather than needing a duplicate manual run; flagged here rather than silently assumed.

**Handoff notes to log:** ESPN endpoint used: `https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team_id}/roster` (unofficial, undocumented — verify still working before relying on it for anything time-sensitive). Last verified working: 2026-07-22. Two other real ESPN endpoints were tried and rejected for this job — see `status_check.py`'s module docstring, decision #1, for the reasoning (both were either the wrong data shape or too expensive in round trips).

---

### Session 5.2 — Scheduling Infrastructure
**Prerequisites:** Sessions 1.3, 2.4, 5.1 complete (this orchestrates all the refresh-able scripts).

**Status:** ✅ Complete (2026-07-23) — mechanism deployed live and validated end-to-end for real, both validation checkboxes below closed. One new deferred action opened (config only, not a data/logic gap) — see ROADMAP.md's "Known Deferred Validations" section and Session 6.1's card. See SESSION_LOG.md for full detail.

**Sites:** Automation needs to trigger the DK and FD pipeline runs separately (different salary files land at different times if the two sites post slates at different points), so the schedule/run log should be able to distinguish which site a given run covers.

**Files touched (created):**
- `/dfs_optimizer/.github/workflows/refresh_data.yml`
- `/dfs_optimizer/cloudflare_worker/scheduled_refresh.js` (+ `wrangler.toml`, needed for deployment, not on the original list)
- `/dfs_optimizer/logs/automation_run_log.csv` (add a `site` column)
- `/dfs_optimizer/data/current_slate.json` (new, not on the original list — the config the automation reads each run to know which season/week/slate_id to target per site)

**Inputs:** All prior scripts (this session wires them into scheduled execution, doesn't create new logic).

**Outputs:** Running automation, plus a run log recording actual fire times per site.

**Build:**
- GitHub Actions cron for regular-interval updates (every few hours on game day), run once per site
- Cloudflare Worker + external trigger (cron-job.org) for the critical near-lock window (**every ~10 min** in the final hour, revised down from the originally-proposed 5-10 min range — see decisions below), aware that DK and FD slates can lock at different times
- For `vegas_odds.py` specifically, this session should implement the cadence already budgeted in Session 2.3's card: Tue-Fri 1x/day, Sat 2x/day, Sunday 1x/hour from 4hrs-1hr before lock, then 1x/15min in the final hour (~121 credits/month, confirmed against the free tier's 500/month cap). This is a different (lighter) cadence than the salary/projection refreshes, since odds move less frequently than player pool/injury status close to lock.
- **Explicit scope decision:** salary ingestion (`ingest_salaries.py`) and the once-per-week `projections_baseline.py`/`projections_matchup.py` are deliberately NOT part of the automated refresh loop — see SESSION_LOG.md's Session 5.2 entry for the full reasoning (no DK/FD salary API exists at all; the baseline/matchup scripts don't produce new data intra-week). The automated loop covers Vegas lines, injury status, and rebuilding/re-applying projections against whichever salary file is already committed.

**Validation:**
- [x] Log actual fire times vs scheduled times over a few days for both sites — confirm GitHub Actions delay is acceptable for non-critical updates. **Closed 2026-07-23:** three real `repository_dispatch` round-trips (Worker → GitHub → workflow start) all completed within seconds. A genuine full-green run (all 6 logged steps) was confirmed by temporarily pointing `current_slate.json` at real committed week-10-2025 test data, then reverted.
- [x] Confirm the Cloudflare Worker + external trigger combo fires within 1-2 minutes of scheduled time consistently, for both sites' lock windows. **Closed 2026-07-23:** confirmed the cron-job.org scheduler itself (not just its manual "Test run" button) fires unattended and correctly triggers a real GitHub Actions run — verified via a temporary same-day schedule change, then reset to the real weekly template.

**Handoff notes to log:** observed delay patterns, any failures and how caught/resolved. Note if DK and FD lock times ever diverged enough to matter for scheduling. ✅ Logged in SESSION_LOG.md's Session 5.2 entry.

---

## BRIDGE TESTING — Madden Sims (optional, now through Preseason Week 1)
*Added 2026-07-23, during the Phase 6/7 reorder discussion. Not a numbered phase or session with its own hard validation checkboxes — this is ongoing, opportunistic real-data exercise to use during the dead time between Phase 5 finishing early and Phase 6 being able to start for real (blocked on a real preseason slate regardless — see "Known Deferred Validations" below). Optional: Phase 7 has no dependency on this, and this has no dependency on Phase 7 — either can be worked whenever, in whatever order, or skipped entirely if the time is better spent on Phase 7.*

**Why Madden Sims and not something else:** DK's Madden Stream contests are the same real, year-round DK data source already used to validate Sessions 1.3, 2.4, 3.1, 3.3, and 4.1 — this isn't a new data source, just continued use of one already proven out. Confirmed via DraftKings' own schedule page: Madden Stream contests run daily, with Classic (3-game) slates locking multiple times a day, so real lock events are available far more often than the three preseason dry-run weeks will provide.

**What this can actually validate for real, worth doing opportunistically:**
- **Full end-to-end weekly workflow rehearsal, timed.** Every session so far validated its own script in isolation against real Madden data; nothing has walked the entire real sequence in one sitting the way it'll actually be run live — download salary CSV → `ingest_salaries.py` → `build_projections.py` → `status_check.py apply` → `optimizer.py` → stacking → `pivot_finder.py` → `ownership_heuristic.py`. Useful as a rehearsal of the human workflow, not just the code.
- **Real (not manually forced) automation reps.** Session 5.2 validated the cron-job.org → Worker → GitHub Actions chain by temporarily repointing the schedule to fire early. A live Madden slate's real, naturally-occurring lock time can exercise the same chain without forcing it — repeatable several times over these three weeks instead of the one-off manual test.
- **Repeat runs against different slate compositions**, to catch anything that only surfaces with a different real player pool than the single week-10-2025 test file everything's been validated against so far.

**What this explicitly does NOT close, so don't mistake a clean Madden run for these being resolved:**
- **FanDuel** — no Madden Sims equivalent exists on FD; this gap only closes at a real FD preseason slate (see "Known Deferred Validations" below).
- **Full 32-team slate size** — Madden Classic slates are still a small pool (~6 teams), same "Known Testing Artifact" limitation already documented below; won't stress-test the uniqueness/exposure edge case found in Session 3.2's addendum at real scale.
- **Real injury/game-day statuses** — these are simulated games, not real NFL games, so there's no real OUT/DOUBTFUL designation tied to them either way; Session 5.1's deferred NFL.com cross-check still only closes at Preseason Week 1.

**No required output file or validation checklist.** If a real issue is found during a bridge-testing session, log it as a dated addendum in SESSION_LOG.md the same way other addenda in this project have been handled, and flag it in this section if it changes what's safe to assume going into Phase 6.

---

## PHASE 6 — Preseason Live Dry Runs
*Target: Aug 13-29*

### Session 6.1 — Preseason Week 1 Dry Run (Aug 13-15)
**Prerequisites:** Phases 1-5 all complete.

**⚠️ Note added 2026-08-11:** this session was never formally run in its scheduled Aug 13-15 preseason window -- project attention moved into Phase 10-14 engine work instead, and no `/logs/dry_run_week1_issues.md` punch list exists. Its core intent -- run the full pipeline live, both sites, against real data, for the first time -- was substantively achieved for FD by **Session 14.1c (2026-08-11)**, run against a real regular-season Week 1 2026 slate instead of preseason. That session found and fixed five real bugs live (see its SESSION_LOG.md entry), which is exactly the kind of outcome this card exists to produce. **Not carried over from 14.1c:** a formal DK+FD punch list in this exact file/format, and the cron-job.org near-lock automation firing during a real lock window (still open, see Known Deferred Validations -- user's explicit call is to configure that closer to the real lock rather than now). Treat this card as substantively closed for FD's pipeline mechanics specifically, still open for the automation-firing check and for any formal DK-side re-confirmation.

**Sites:** Run the full pipeline for both DK and FD this week — a site that's never been dry-run isn't proven, regardless of how well its unit tests passed.

**Files touched:** `/dfs_optimizer/data/current_slate.json` (real week/slate_id, both sites) — carried over from Session 5.2's deferred action, not new scope. Otherwise none new — this is an execution/observation session. Fixes get logged as a punch list.

**Inputs:** Live preseason Week 1 slate, both sites.

**Outputs:** `/logs/dry_run_week1_issues.md` (punch list for Session 6.2, tag each issue with which site(s) it affects)

**Build:**
- **Carried over from Session 5.2 (deferred action, do this first):** once Preseason Week 1's real slate/lock times are known, update `data/current_slate.json` (real season/week/slate_id, both sites) and the cron-job.org "DFS Optimizer - Near-Lock Refresh" job's schedule (Days/Hours, currently a Sunday-11am-CT/every-10-min template) to match. This is the first point either has a real value to be set to — see ROADMAP.md's "Known Deferred Validations" section and SESSION_LOG.md's Session 5.2 entry for why it couldn't be done sooner.
- Run the full pipeline live end to end, for DK and FD. No real money.

**Validation:**
- [ ] Full pipeline runs start to finish without manual intervention, for both sites (the actual goal of this test)
- [ ] Every failure/manual fix needed is logged, tagged by site
- [ ] Generated lineups' actual results vs projections compared, both sites (expect roughness in preseason — focus on pipeline reliability over accuracy)
- [ ] Confirm the near-lock automation (cron-job.org → Cloudflare Worker → GitHub Actions) actually fires during a real lock window and produces a real, correctly-timed refresh — first genuine real-world exercise of Session 5.2's mechanism

**Handoff notes to log:** the full punch list, prioritized, with each item tagged DK/FD/both.

---

### Session 6.2 — Preseason Week 2 Dry Run (Aug 20-22)
**Prerequisites:** Session 6.1 complete, punch list addressed.

**Files touched:** Whatever files the Week 1 punch list points to.

**Inputs:** Live preseason Week 2 slate, both sites + `/logs/dry_run_week1_issues.md`

**Outputs:** `/logs/dry_run_week2_issues.md`

**Build:** Apply fixes from Week 1. Re-run full pipeline for both sites.

**Validation:**
- [ ] Every issue from 6.1 is specifically re-tested and confirmed fixed, on whichever site(s) it originally affected
- [ ] No new manual interventions required beyond expected ones (e.g. salary CSV download from each site)

**Handoff notes to log:** which Week 1 issues resurfaced (if any) — recurring issues need a different fix approach. Note if one site is consistently less stable than the other.

---

### Session 6.3 — Preseason Week 3 Dry Run (Aug 27-29)
**Prerequisites:** Session 6.2 complete.

**Inputs:** Live preseason Week 3 slate, both sites + `/logs/dry_run_week2_issues.md`

**Outputs:** `/logs/dry_run_week3_issues.md`, and a go/no-go decision note for Phase 8 (per site — it's possible one site is ready and the other isn't).

**Build:** Final dry run before real season, both sites.

**Validation:**
- [ ] Full pipeline runs clean, unattended, through the critical near-lock window, for both sites
- [ ] Explicit go/no-go judgment logged per site — if no-go for either, identify specifically why before Regular Season Week 1

---

## PHASE 7 — Frontend / Hosting
*Target: parallel with Phase 6, finish by Sept 9*

### Session 7.1 — Basic UI + Hosting Setup ✅ Complete (2026-07-23)
**Prerequisites:** Session 3.2 complete (need a stable lineup output format to build the UI against).

**Sites:** UI needs a DK/FD toggle or selector from the start — retrofitting a site switch after the UI is built single-site is more work than building it in.

**Files touched (created):**
- `/dfs_optimizer_frontend/` — built as a **subfolder in this repo** (user-confirmed this session), not a separate repo. Keeps one GitHub/Cloudflare account pairing, same "build output directory" pattern already used for `cloudflare_worker/` in Session 5.2.

**Inputs:** `/output/lineups_multi_{site}_{week}.csv` format (as a contract, not live data yet).

**Outputs:** Deployed to **Cloudflare Pages free tier** — `https://dfs-optimizer.pages.dev`. Built and validated this session; see SESSION_LOG.md's Session 7.1 entry for the full record.

**Correction (this session):** this card previously read "Vercel/Netlify free tier, connected to purchased domain." Neither holds. Cloudflare Pages was used instead (consolidates onto the Cloudflare account already wired up in Session 5.2), and **no domain purchase is needed or planned** — this project is confirmed personal-use-only, and a free `*.pages.dev` subdomain is a real, publicly-reachable HTTPS domain that fully satisfies this card's own "real domain, not localhost" validation line below. A custom domain remains available later as a purely optional, cosmetic add-on, not a requirement — worth remembering if a future session (e.g. Session 7.3's "live domain" language) is tempted to re-introduce a domain-purchase assumption.

**Build:** Simple frontend (upload/view players, view generated lineups) with a site selector (DK/FD) driving which data set is displayed. Shipped as a single static `index.html` (vanilla HTML/CSS/JS, no framework, no build step) — fastest path to a zero-config Cloudflare Pages deploy for this session's scope; revisit only if Session 7.2's interactivity needs outgrow vanilla JS, not before.

**Validation:**
- [x] Site loads on the real domain, not just localhost — confirmed live at `https://dfs-optimizer.pages.dev`.
- [x] A generated lineup from the backend correctly displays with no data mismatches, for both DK and FD selections — confirmed live, real repo data, both the single- and multi-lineup formats, including the DK `DST`/FD `DEF` slot-label difference and the real zero-projection Dallas DST/DEF bye case. Full detail in SESSION_LOG.md.

---

### Session 7.2 — UI-Optimizer Integration ✅ Complete (2026-07-23)
**Prerequisites:** Session 7.1 and Phase 3 (all of it) complete.

**Files touched (created/modified):**
- `scripts/optimizer.py` — added `--lock`/`--exclude` (decisions #22-26), `--request-id` (decision #27), and clean-error-message handling for the CLI entry point (Session 7.2c hotfix).
- `.github/workflows/run_optimizer_dispatch.yml` — new. On-demand real-solver dispatch path.
- `cloudflare_worker/optimizer_api/optimizer_api.js` + `wrangler.toml` — new. Second Worker (`dfs-optimizer-api`), separate from Session 5.2's `scheduled_refresh.js`, handling dispatch + poll.
- `dfs_optimizer_frontend/index.html` — new "Build a Lineup" panel: player pool upload, full controls (mode, exposure, uniqueness, stacking, randomization, lock/exclude), instant client-side preview (glpk.js), and the real-solver confirm flow. Session 7.1's upload/view functionality is unchanged underneath it.

**Inputs:** Live optimizer output.

**Outputs:** Interactive UI controls wired to real backend behavior.

**Build:** Connect frontend controls (exposure limits, stack rules, lock/exclude players) to the optimizer backend, respecting the site selector from 7.1 (e.g. exposure/stack controls should operate on the currently-selected site's lineups, not mix DK and FD data).

**Architecture decision (user-confirmed this session, given the runway before preseason):** hybrid, not a single approach —
1. **Instant preview** — a real ILP solver (glpk.js, WASM) running client-side in the browser. Single-lineup, lock/exclude only (no stacking/exposure/randomization — see below for why). Confirmed exact parity against `optimizer.py`'s real PuLP/CBC output on real data (same salary/points totals to the penny, same players selected) before shipping.
2. **Confirm with Real Solver** — the frontend dispatches to a Cloudflare Worker, which fires a `repository_dispatch` that runs the actual, unmodified `optimizer.py` via GitHub Actions (typically 20-90s), commits its result to a request-scoped path (`output/ui_requests/{request_id}.csv`, never the canonical `lineup_single_*`/`lineups_multi_*` files), and the frontend polls the Worker for the result. Supports every control, including stacking/exposure/uniqueness/randomization, since it's the real file — no second implementation to drift out of sync.

Deliberately NOT replicated in the client-side instant-preview solver: stacking, exposure caps, uniqueness, randomization. Only lock/exclude + salary/roster constraints. This was a scope decision, not an oversight — those mechanics (especially exposure's iterative lock-out and uniqueness's relaxation-on-infeasibility) are complex enough that a second JS implementation would be a real, ongoing drift risk; "Confirm with Real Solver" exists specifically so nothing ever needs that.

**Validation:**
- [x] Every UI control actually changes optimizer output as expected — test each control individually, for both DK and FD selected.
  - **DK: fully validated, live, on the real deployed site** (`https://dfs-optimizer.pages.dev`) against a real DK Madden Sim slate the user downloaded and ran through the real pipeline this session (see SESSION_LOG for the full real-data trail). Individually confirmed working: Lock, Exclude, Week, multi-lineup mode (n_lineups/max_exposure/uniqueness), QB Stack (with and without bring-back — including the infeasible-request case correctly failing with a clear message, not a crash), Game Stack, Mini Stack, Randomization (+ seed), Instant Preview, multi-lineup navigation/display in the viewer.
  - **FD: deferred**, same reason as every other FD gap tracked in this file since Session 1.3 — there is no real FD data to validate against yet. First real point this closes: Preseason Week 1, same as the rest of the FD list below.
  - Five real bugs were found and fixed via this live testing (not caught by local/sandboxed validation alone) — see SESSION_LOG's Session 7.2 entry for the full list. Flagging here because it's the reason this checkbox required actual live use of the deployed site, not just code review, to close honestly.

---

### Session 7.3 — Polish & Final Deploy ✅ Complete (2026-07-24)
**Prerequisites:** Session 7.2 complete.

**Build:** Cleanup, mobile responsiveness, final deploy. **Also the home for the user's layout/UX refinement suggestions on the Session 7.1/7.2 UI** (explicitly deferred here rather than 7.2, per user request at the end of that session — 7.2's own scope was wiring controls to real behavior, not refining how they're laid out).

By far the largest session in this project -- see SESSION_LOG.md's Session 7.3 entry for full detail. Delivered all 10 of the user's original UI polish items (single persistent slate upload, extended to cross-device cloud sync; Worker URL/Token friction fixed with a lock-by-default + Test Connection diagnostic; single-lineup mode and Instant Preview removed entirely; Save Settings replacing seed; ownership baked directly into `final_projections` automatically, including a per-lineup Own% display; minimum-salary and FLEX-position controls; slate overview; player-pool tabs/sort/value column) plus item 11 (stacking review -- Game Stack fixed to actually require a QB, `game_stack_min_players` exposed, QB Stack defaults tightened, free-text team/game inputs replaced with slate-derived multi-select pickers that genuinely rotate the batch across multiple picks). Also shipped, beyond the original list: mobile responsive fixes for a real reported phone-layout bug, a DK/FD bulk-entry "Download Lineups" import feature (required real pipeline changes to carry the site's own player ID through, and surfaced/fixed two real bugs via the user's own live testing against a real `DKEntries.csv`), and a partial-build warning banner.

**Two items explicitly deferred, both at user's own request, not oversights:**
- Running two independent stack rules in one lineup simultaneously (e.g. QB+WR from one game plus RB+DST from a different game) -- scoped as a real architectural change, user chose to test the simpler single-stack modes more first before deciding whether it's worth building.
- FD side of everything shipped this session remains unverified against real data -- same standing gap as the rest of this project since Session 1.3, tracked in the Known Deferred Validations list below, not treated as new.

**Validation:**
- [x] Every feature validated against real repo data end-to-end in the sandbox (real DK Madden Sim slate, real uploaded `DKEntries.csv` for the download-import feature) -- see SESSION_LOG.md for specifics per item.
- [x] Cloud slate sync, ownership display, and the DK-import download feature specifically confirmed live on the deployed site by the user (the latter through two real rounds of bug-fixing).
- [ ] **Not yet done:** a full live walkthrough of this session's LATER changes specifically -- the Game Stack QB fix, the new team/game chip pickers and multi-pin rotation, the mobile CSS fixes (reported broken once already), the Minimum Salary slider, and the partial-build banner -- on both a desktop browser and the same Pixel 9 Pro XL that surfaced the original mobile bug. Sandbox-validated only as of this session's close.

### Session 7.5 — Frontend UI Improvements ✅ Complete (2026-07-30)
**Prerequisites:** Session 7.4 complete.

**What this added:**
- **Bulk Exclude / Un-exclude All** — pill buttons shown between the filter bar and player list whenever a slate is loaded. Operates on the full filtered set (not capped at 200). Players hidden by filters are never touched.
- **Column alignment fix** — `playerListHead` moved inside the `player-list` scroll container as a `position: sticky` element. Fixes the ~17px rightward drift that appeared when the scrollbar was visible (desktop).
- **Mobile layout cleanup** — value cell renamed from `.pown` to `.pval` (was colliding with ownership cell class). Mobile CSS updated to class-based selectors (was fragile `nth-child` targeting). SAL label added to salary cell on mobile for consistency.
- **Bug fix:** sort-column click handler converted from direct `playerListHead.addEventListener` (crashed `null` since head is now dynamic) to event delegation on `playerList`.

**Files modified:**
- `dfs_optimizer_frontend/index.html`

**Validation:**
- [x] JS syntax check passed; all `getElementById` cross-referenced — no missing IDs
- [x] Bulk exclude/un-exclude confirmed correct on desktop and mobile
- [x] Column headers align with data values with scrollbar present (desktop)
- [x] Mobile stat labels (SAL/PROJ/VAL/OWN) clean on Pixel 9 Pro XL
- [x] No regression on existing functionality
- [ ] FD validation — same pre-existing gap as all FD items

---

### Session 7.4 — Slate Management Rework ✅ Complete (2026-07-30)
**Prerequisites:** Session 7.3 complete.

**What this fixed:** Three user-reported issues with the slate upload/management system: (1) the X/delete button removed a slate from local storage but it reappeared immediately because cloud delete was never wired up, (2) slates were keyed by `{site, week: integer}` making it impossible to have more than one slate per site per week — no way to distinguish preseason wk1 from regular season wk1, or main slate from early/afternoon splits, (3) the chip list grew cluttered; a dropdown scales better.

**Files modified:**
- `cloudflare_worker/optimizer_api/optimizer_api.js` — slate endpoints reworked (see below); must be redeployed separately from git push: `cd cloudflare_worker/optimizer_api && npx wrangler deploy optimizer_api.js`
- `dfs_optimizer_frontend/index.html` — Slates panel HTML/CSS/JS fully reworked
- `DFS_Weekly_Process.md` — Steps 2d and Stage 4 updated

**Key changes:**
- Slate identity changed from `{site, week: integer}` to `{site, slateId: string}`. SlateId is derived from a user-typed label at upload time (e.g. "Classic Wk 3" → `classic_wk3`). The same CSV can be uploaded multiple times under different labels as fully independent entries.
- New `delete_slate` Worker endpoint (GitHub Contents API DELETE). Wired to the Delete button in the UI. Fixes the re-appearance bug.
- `list_slates` simplified to a single GitHub API call (directory listing only — no per-file fetches). Previous N+1 design caused timeouts on Cloudflare's free-tier 10ms CPU limit with as few as 5 slates.
- Upload is two-step: choose file → label field appears pre-filled from filename → confirm. Week number auto-detected from filename for optimizer dispatch (defaults to `"1"` for Madden Sim / preseason / custom-named files).
- Chip wall replaced with `<select>` dropdown. Delete button wired to both localStorage and cloud.
- `loadSlateForActive()` changed to local-first (was cloud-first). Fixed the switching bug where cloud latency caused dropdown selection to drift.
- On-load init: builds from localStorage synchronously, then fires background cloud merge. If local was empty (mobile / new device), cloud merge auto-loads the first returned slate — restoring cross-device sync.
- `SLATE_INDEX_KEY` bumped to `v2` — old week-keyed entries ignored cleanly.

**Validation:**
- [x] Node syntax check on both files
- [x] All `getElementById` calls cross-referenced against HTML ids — no missing IDs
- [x] Upload two slates, switch between them — both load correctly (desktop)
- [x] Delete one — stays gone on reload, does not reappear (desktop)
- [x] Build lineups on two different slates in the same session — both successful
- [x] Mobile (Pixel 9 Pro XL): slate uploaded on desktop auto-loads on phone without manual action
- [ ] FD validation — same pre-existing gap as all FD items

**Note on old cloud files:** After deploying, delete the old week-keyed entries in `data/ui_slates/` (`dk_1.json`, `dk_10.json`, etc.) via the UI's Delete button, then re-upload slates with readable labels.

---

## PHASE 8 — Regular Season Go-Live
*Target: Sept 9*

### Session 8.1 — Week 1 Regular Season Live Run
**Prerequisites:** Phase 6 go-decision logged (per site), Phase 7 complete.

**Sites:** Go live on whichever site(s) got a "go" from Phase 6 — if only one site passed its dry runs, it's fine to launch that one first and follow up with the other rather than blocking on both.

**Outputs:** `/logs/regular_season_week1_results.md` (tag results by site)

**Build:** Real slate, real automation, first live-money-adjacent test — DK and FD in parallel if both are cleared.

**Validation:**
- [ ] Full pipeline runs unattended through lock, per site being launched
- [ ] Post-game: actual results vs projections logged, per site — first real data point for Phase 9

---

## PHASE 9 — Learning Loop
*Ongoing, starts Regular Season Week 2+*

### Session 9.1 — Actual-vs-Projected Logging
**Prerequisites:** Session 8.1 complete.

**Sites:** Log per site — a player's raw stat outcome is shared, but projection error is site-specific since DK and FD project different fantasy-point values for the same player (full vs half PPR) and are priced differently.

**Files touched (created):**
- `/dfs_optimizer/scripts/log_results.py`
- `/dfs_optimizer/data/projection_error_log.csv` (grows weekly; add a `site` column)

**Build:** Automated post-game script logging projection error per player/position/site.

**Validation:**
- [ ] Confirm logged actuals match real box scores for a spot-check sample, and that DK/FD rows compute different fantasy-point actuals for the same player where expected (PPR gap)

---

### Session 9.2 — Weight Retuning (after ~4 weeks of data minimum)
**Prerequisites:** Session 9.1 running for 4+ weeks.

**⚠️ Revised by Phase 10 (2026-07-25):** this card's premise — regression-reweighting the *four* projection components (season_avg, recent_form, matchup_factor, vegas_factor) — assumes the original Session 2.1-2.4 blend, which Phase 10 replaces. Two changes carry over: (1) the components themselves change (Phase 10 blends a small number of decorrelated stat-line sources, not those four), and (2) FFA's 11-season finding that accuracy-weighting is statistically interchangeable with equal-weighting means aggressive per-week retuning is a live overfitting risk, not a straightforward win — see Phase 10's design intro. Keep this card's *intent* (fit weights against logged error, per site) but read it through Phase 10's component set and its caution against chasing week-to-week noise.

**Sites:** Decide explicitly whether DK and FD get separate retuned weights or share one blend — worth a deliberate call here rather than defaulting to shared, since half-PPR could plausibly shift the ideal weighting between recent form and matchup factor.

**Files touched (modified):** `/dfs_optimizer/scripts/build_projections.py` (blend weights updated, per site if they end up diverging)

**Inputs:** `/data/projection_error_log.csv`

**Build:** Regression-based reweighting of the four projection components, run separately per site's error data.

**Validation:**
- [ ] Backtested retuned weights on held-out weeks show equal or better error than original hand-picked weights, for each site independently — if not, don't ship, investigate why

---

### Session 9.3 — Actual Ownership Logging
*Added during Session 4.1's addendum, when `estimated_ownership_pct` was added to `ownership_heuristic.py` — that estimate is anchored to real roster-slot math but not to any real ownership data, since none exists in this pipeline yet. This card is the other half of that decision: the mechanism to eventually get real data to check it against. Same relationship to Session 9.4 as Session 9.1 has to 9.2, just for ownership instead of projection accuracy.*

**⚠️ Script built 2026-07-29 — session closes on first real end-to-end run (Preseason Week 1). See the updated card below (Phase 9) and SESSION_LOG.md's Session 9.3 entry for full detail.**

**Prerequisites:** Session 8.1 complete (live enough to have real slates running), AND a real published-ownership source identified for at least one site/contest type (see Build below — this is a real open question, not a given).

**Sites:** Log per site — DK and FD price the same player differently, so their real ownership numbers for the same player are never expected to match.

**Files touched (created):**
- `/dfs_optimizer/scripts/log_ownership.py` ✅ built 2026-07-29
- `/dfs_optimizer/data/ownership_actual_log.csv` (grows weekly; columns: site, week, player_id, actual_ownership_pct, estimated_ownership_pct_at_time, source)

**Build:**
- ✅ Script built. See SESSION_LOG.md's Session 9.3 entry.

**Validation:**
- [ ] **End-to-end run against real ownership data** — first opportunity Preseason Week 1. Tag those rows `--slate-type preseason` to confirm the script works end-to-end. This closes the session.
- [ ] Confirm logged actuals genuinely come from a real contest's real ownership breakdown for a spot-check sample.
- [ ] Confirm the DK/FD ownership numbers logged for the same real player in the same real slate are NOT expected to be equal, and aren't accidentally being logged as if they were.

**Handoff notes to log:** which real ownership source(s) were actually usable per site — if only one site has a workable source, flag that explicitly rather than letting Session 9.4 assume both sites have equal real data to retune against.

---

### Session 9.4 — Ownership Estimate Retuning (after Session 9.3 has real data for at least one full slate)
**Prerequisites:** Session 9.3 producing real logged ownership data for at least one site.

**Sites:** Same explicit-decision pattern as Session 9.2 — decide whether DK and FD get separately retuned parameters or share one, don't default to shared without checking whether their real ownership shapes actually diverge.

**Files touched (modified):** `/dfs_optimizer/scripts/ownership_heuristic.py` (`OWNERSHIP_SOFTMAX_TEMPERATURE`, the FLEX-split-evenly simplification, and potentially the chalk_score blend weights themselves, all retuned/replaced using real data where the current version is an admitted unfit guess — see that script's module docstring, decision #5)

**Inputs:** `/data/ownership_actual_log.csv`

**Build:**
- Fit `OWNERSHIP_SOFTMAX_TEMPERATURE` (and any other decision #5 constants worth revisiting) against real logged ownership error, same regression-style spirit as Session 9.2's projection-weight retuning.
- Revisit the FLEX-split-evenly simplification specifically — real logged data should reveal actual RB vs WR vs TE FLEX usage rates, which is strictly better than an even three-way split once available.

**Validation:**
- [ ] Backtested retuned estimated_ownership_pct on held-out real weeks shows equal or better error against actual logged ownership than the original unfit constants, for each site independently — if not, don't ship, investigate why (same bar as Session 9.2)

---

### Backlog idea — Player props as a projection input
*Flagged during Session 13.5's closeout (2026-08-05).* **Promoted to
Session 14.1 (2026-08-06)** — see PHASE 14 below for the scoped session
card. Kept here as the historical record of when/why this was first
flagged: sharp DFS players commonly estimate player-level projections
from Vegas player props (TD props, yardage O/Us, etc.) rather than
relying on game-level totals alone.

### Backlog idea — Investigate systematic high bias in projections
*Flagged during Session 13.5's closeout (2026-08-05).* **Root cause
identified 2026-08-06, NOT via Session 9.1's logging (that's still
gated on real games being played, ~Sept 13) but via a direct code audit:
the live pipeline (`refresh_data.yml`) has been calling the Session 2.4
placeholder engine (`build_projections.py`) the entire time — the Phase
10 stat-line rebuild (`build_projections_statline.py`) was built,
backtested, and validated, but never actually wired into production.
See Session 14.0 below.** This doesn't retroactively rule out other
contributing causes (Session 9.1 still needs to run once real games
exist, to confirm the fix and catch anything else), but it's very
likely the dominant one — the legacy engine has no participation
weighting, no price-implied volume prior, and stacks two market
multipliers (`matchup_factor` x `vegas_factor`) directly on a naive
season/recent-form average.

---

## PHASE 10 — Projection System Redesign
*Opened 2026-07-25. A ground-up redesign of the projection engine, deliberately specced from first principles BEFORE re-reading the existing `build_projections.py`, to avoid anchoring on the current recency-weighted-average approach. The original engine (Sessions 2.1-2.4) was intentionally a get-something-working placeholder; this phase replaces it. The design below is settled and user-agreed; the cards implement it in dependency order.*

### The settled design (read this before any Phase 10 card)

**One model, parameterized optimizer.** A projection estimates what happens on the field, which doesn't change with contest type. What changes is how the *optimizer* uses it. So there is ONE projection model; cash vs single-entry/3-max vs 20-max differ only in the optimizer's objective, not in separate projection models.

**Output schema is per-player mean + sigma, per site.** Not a bare point estimate, not a full distribution. The user's actual strategy ("cash floor with GPP upside", played at 1-3 entries) decomposes precisely: suppress *idiosyncratic* variance (individually boom/bust players — lowers your floor), source all upside from *correlated* variance (stacking — fattens the right tail for free). Implementing that needs a per-player sigma alongside the mean. Objective becomes maximize `sum(mean) − λ·(idiosyncratic sigma)`, correlation enforced as a constraint. λ is high for cash, moderate for single-entry/3-max, lower for 20-max.

**Mean, not median.** The optimizer maximizes a sum, and expectation is linear (median is not additive). The right-skew concern (TD-dependent boom/bust over-selection) is handled by the λ·sigma penalty, not by switching to median.

**sigma from stat-line composition, not player history.** Historical per-player SD isn't sticky year-to-year and is confounded with the mean (a bigger projection mechanically carries bigger absolute variance). Instead, model variance per stat component (receptions low, yards moderate, TDs high) and combine, conditioning sigma on the projection rather than on player identity. This is a second, independent reason to blend at the stat-line level.

**Blend at the stat-line level, small number of decorrelated components.** Usage-based (nflverse history) + market-based (Vegas implied total now; prop-derived TDs later) blended as *stat lines*, converted once to DK points and once to FD points, then a salary-implied baseline anchor applied at the points level. Blending helps in proportion to error *decorrelation*, not component count — so a few genuinely different information sources, fixed conservative weights, NOT many similar sub-models. (FFA's 11-season finding: accuracy-weighting is statistically interchangeable with equal-weighting because source accuracy doesn't persist week to week — so resist heavy retuning of blend weights; this directly tempers the ambition of the old Session 9.2 card.)

**⚠️ Amended by Session 10.2 (2026-07-26) — "a salary-implied baseline anchor applied at the points level" above is now measured, and it does NOT work at the points level.** The curve itself was fit successfully and ships (Session 10.2's card below), but blending it into `final_projection` produced no lineup-level improvement at any weight tested: the largest effect across seven curve/weight variants was 1.1 percentile points against a 15.6-point week-to-week SD, with every sign test a coin flip.

The reason is mechanical, not statistical, and it was found by walking real debug weeks player-by-player. **A monotone-in-salary term added to the objective is close to redundant with the salary-cap constraint the ILP already enforces.** Every single player in both debug weeks was shrunk by the blend (`pre > anchor`, no exceptions), so at a uniform weight it is nearly an affine transform of the objective vector — which an ILP barely notices. Worse, the differential is systematic: shrinkage as a share of the model projection ran 18.3% for a $3,000 WR versus 9.4% for an $8,000+ QB, meaning **the anchor taxes players whose projection is high relative to their price — value plays — and favors expensive ones.** The cap already prices that tradeoff, exactly as this section's own "the ILP handles the price tradeoff natively" line says; blending price into the projection double-counts it against an existing constraint.

**Two consequences carry forward:**
1. **Session 10.3 should use price as a prior on the STAT-LINE inputs** (volume, targets, carries), where it carries information the salary cap does not — NOT as a points-level blend. This is a real constraint on the design, learned cheaply before weeks were spent on it.
2. **The anchor's genuine, non-redundant value is the cold start**, which is the one thing the usage model cannot do at all. See Session 10.2's card for the measured week-1 result.

**Blend weights dynamic on data sufficiency (cold start).** No separate rookie model. At zero games of usage data a projection is essentially salary + market; as games accumulate the usage component takes over (empirical-Bayes shrinkage schedule). Same mechanism handles mid-season role changes and elevated backups. Critical caveat: suppress the salary anchor's weight when a role change is flagged — a stale price is exactly the value spot we're trying to beat.

> **AMENDED by Session 10.3b (2026-07-27) — this caveat is BACKWARDS for weekly DFS, and is superseded.** It presumes the *price* is the stale signal. On a weekly slate the site reprices every player every week with real money behind it, while our usage history is weeks old by construction — so the price is the *fresh* signal and the history is the stale one. Measured out-of-sample over 36,025 player-week-components: regressing what history misses on the price−history divergence gives slope **+0.4529, t = +93.26, R² = 0.195**. The three catalogued cases are unambiguous (realized share 1.000 in all three): NYJ 2021 wk13 Z. Wilson hist 0.128 / price 0.935; SEA wk13 R. Wilson hist 0.582 / price 0.971; CAR wk15 Newton hist 0.521 / price 0.935. A role-change flag therefore **raises** the price's influence, it does not suppress it. Implemented as a participation override in `volume_prior.py` decisions #2–#5. The original caveat may still hold for a *within-week* injury that post-dates pricing; nothing here measures that case.

**DST is a separate, distributional model.** Points-allowed is scored as a step function on both sites, so `E[f(X)] ≠ f(E[X])` — you must integrate over the bracket probabilities given the opponent's implied total, not look up one bracket. DST is more predictable than its reputation (public analysis ~0.37 correlation, beating WR/TE point projections). Inputs: distributional points-allowed (dominant), sack rate, turnover rate (QB-specific, rookie-adjusted), own-defense EPA/play as the stable modifier, wind. It is the sharpest illustration of why mean and sigma are tracked separately (compressed means, enormously dispersed outcomes).

**⚠️ Amended by Session 10.4 (2026-07-26) — this paragraph's central claim is CONFIRMED and two of its supporting details are not.** The `E[f(X)] ≠ f(E[X])` argument is right and now quantified: point-estimate bracket lookup is biased low 0.30 pts on every defense, compresses the across-defense spread 19%, and ranks worse (Spearman 0.336 vs 0.369). Integration is the whole ballgame and it delivered — DST-slot Spearman rose 0.199 → 0.311 against real graded actuals.

What did not survive contact with data: (1) **"own-defense EPA/play as the stable modifier"** — the opponent's offense carries ~4× the signal the defense's own history does, and own-defense EPA survives only as a small mean-reversion correction on the market's number. (2) **"more predictable than its reputation (~0.37 correlation)"** — measured here at 0.30 Spearman / 0.30 Pearson on a real out-of-sample slate, so the direction is right but the public figure is optimistic. Wind is real but marginal (t = −2.98 on eight seasons, null on four, and null on every volume channel because books price the forecast into the total line). The "compressed means, dispersed outcomes" point is exactly right: a DST's sigma (~6.2) now measures nearly as large as its mean (~6.9).

**Correlation stays in constraints (stacking), not the objective.** For 1-3 entries this is correct and — importantly — keeps the problem linear, so CBC/PuLP is retained (a covariance objective would force a MIQP). Exposure caps / uniqueness / randomness are *portfolio* levers (make lineups differ from each other); they do almost nothing at 1-3 entries and randomness at 1 entry is actively harmful. Randomness should scale with entry count and, once sigma exists, be sigma-proportional rather than a flat uniform percentage.

**Manual override layer:** post-blend, expiring (week-stamped, stale ones fail loud), auditable (pre/post columns), logged for the learning loop.

**Calibration shrinkage:** the known slope-below-1 bias (projections overstate the top-to-bottom gap) is real and free, but ours must be fit OUT-OF-SAMPLE, not hardcoded from someone else's slopes. Instrument now (Session 9.1), fit later. Note it fights points-per-dollar's cheap-player bias — resolved because the ILP handles the price tradeoff natively, so value stays display-only and never drives selection.

**Success is measured at the lineup level.** MAE is the wrong scoreboard (two projection sets with identical MAE build completely different lineups; what drives selection is ordering within salary band). The metric is percentile against a synthetic ownership-weighted field, reported as median-percentile (cash/floor proxy) AND max-percentile (upside proxy) separately — never blended, since λ trades between them and that tradeoff curve is the point.

**Share reconciliation is mandatory, specifically because of stacking.** If the QB projection and his stacked receivers' projections aren't derived from the same team pass-volume number, the stack is internally incoherent — which corrupts the exact mechanism the user's whole strategy depends on. After building player projections, aggregate to team level, compare against Vegas-derived team targets, rescale shares, fail loud past a threshold.

---

### Session 10.0 — Historical Data Bootstrap ✅ Complete (2026-07-25)
**Prerequisites:** none (foundational for the rest of Phase 10).

**Why:** the project has real 2025 outcomes but no real historical salary files (DK/FD publish no API; "Export to CSV" is current-slate only). No salaries -> no cap -> no legal lineup -> no lineup-level backtest and no salary-anchor curve. RotoGuru (free archive, DK 2014-2021 / FD 2011-2021) closes it.

**Files created:** `scripts/ingest_rotoguru.py`, `scripts/batch_match_rotoguru.py`, `scripts/resolve_unmatched.py`; modified `scripts/ingest_salaries.py`. Data: 155 matched salary files, 9 actuals files, nflverse 2014-2021 history.

**Result:** mean 99.7% match (min 98.6%, 0 errors, 0 low weeks) across all 155 files. Full detail + the three real bugs found only by live data (`NOR->NO`, team-keyed override miss, upsert dedup block) in SESSION_LOG.md's Session 10.0 entry.

**This is a bootstrap, not the validation set** — RotoGuru's newest is 2021, the project's current-state `weekly_stats` is 2025, no overlap. Its jobs: prove harness mechanics, fit the salary curve, fit stat-component variance. Real current-state validation accumulates live from Preseason Week 1.

---

### Session 10.1 — Lineup-Level Backtest Harness ✅ Complete (2026-07-25)
**Prerequisites:** Session 10.0 complete. **Build this BEFORE any projection change** — without it, a rewrite can't be told from a regression, and the existing system has no measured baseline.

**BASELINE (2021, DK, 17 weeks × 20 lineups):** median-percentile **mean 72.8** (min 39.1, max 91.0); max-percentile **mean 94.7** (min 77.8, max 99.7). Reported separately, never blended. This is the number every later Phase 10 projection change is measured against. See SESSION_LOG.md's Session 10.1 entry for the four integration bugs found (all only by real data) and the week-1 cold-start finding.

**⚠️ Amended by Session 10.2 (2026-07-26) — the harness gained `--field-pool` (its decision #9), and every future comparison must use the default.** The field was sampled from the same pool lineups were built from, so a projection change that enlarges the pool also enlarges and DILUTES the field, and our percentile rises for a reason unrelated to the projection. Measured when the salary anchor was first switched on: the field's median score fell in **15 of 17 weeks, mean −1.41 pts, t = −4.3** — stronger than any real effect in that comparison, and a pure artifact. `--field-pool baseline` (now the default) pins every arm to one yardstick by rebuilding an anchor-off pool per week purely for the field. **The baseline figures above are unaffected and reproduce exactly**, since pinning is a no-op when the arm being measured is the baseline itself. Two further consequences: raw median/best lineup scores are now printed per week and in the summary (arm-independent units, so they are the check on whether a percentile move is real), and week 1 cannot be pinned at all (its anchor-off pool is empty by definition) so it falls back to its own pool and is flagged as not cross-arm comparable.

**⚠️ Re-baselined by Session 10.3a (2026-07-26) — the harness now derives each week's RNG from `(seed, season, week)` (its decision #13), which changes the field draws.** The old scheme threaded one generator through the whole run, so a week's field depended on every week before it — fine until a week did not consume its draws, and an ERRORED or SKIPPED week returns before touching the RNG. Measured: the stat-line arm errored on 2021 wk13, and from wk14 onward its field silently diverged from the legacy arm's (wk14 108.82 vs 107.92, wk17 100.66 vs 99.63), un-pinning the very yardstick decision #9 exists to pin. This is Session 10.2's bug #3 recurring through a different mechanism, which is the argument for removing the coupling rather than patching the symptom twice.

**The re-measured numbers, which are the anchor from Session 10.3a on:**
- **2021 DK, 17 weeks × 20 lineups:** median-percentile **72.9**, max-percentile **94.8**. Raw scores came back *identical to the cent* (median 118.08, best 148.23) — the optimizer built the same lineups; only the field sample moved, by 0.06 points. The metric is not seed-sensitive.
- **Pooled 2018–2021 DK, 65 weeks × 20 lineups:** median-percentile **75.6 ± 1.6 SE**, max-percentile **96.5 ± 0.6 SE**. Per season: 2018 80.6 / 98.3, 2019 75.1 / 96.7, 2020 74.1 / 96.4, 2021 72.9 / 94.8. Use the pooled pair for anything needing power; 17 weeks against a ~16-point week-to-week SD cannot detect an effect smaller than about 9 percentile points.

The original **72.8 / 94.7** remains the valid historical record for Sessions 10.1 and 10.2, which were internally consistent under the old scheme. Do not restate their conclusions against the new pair.

**Known data gap:** 2018/2019/2020 wk18 error on both arms for want of `salaries_dk_rotoguru_{season}_wk18.csv`. Symmetric, so it biases nothing, but `batch_match_rotoguru.py` would recover three weeks.

**Sites:** DK first (8 seasons of real matched data). FD has only 2021 matched — usable to prove the mechanics, not to fit anything.

**Files touched (created):** `/dfs_optimizer/scripts/backtest_harness.py`; likely `/dfs_optimizer/output/backtest_*.csv` for results.

**Build:**
- Reconstruct a week's legal player pool from `data/salaries_{site}_rotoguru_{season}_wk{week}.csv`, **filtered to the Sunday main slate** using `schedules_{season}.parquet` (the bootstrap deliberately left the full-week Thurs-Mon pool unfiltered — the harness owns this, once, since it loads schedules anyway). NOTE the schedules layout wrinkle: 2014-2021 is ONE combined `schedules_2014_..._2021.parquet`, 2025 is per-season — handle both.
- Run the real `optimizer.py` against that pool (real imported functions, not a reimplementation — the project's own hard-won lesson that only real runs catch the real bugs).
- Score the built lineup(s) against `rotoguru_actuals_{site}_{season}.csv`.
- **Metric = percentile against a synthetic field**, NOT percent-of-hindsight-optimal (that denominator is a single noisy extremum, is uninformative in scale, and rewards ceiling-chasing which is explicitly not the user's strategy). Sample the field proportional to Session 4.1's `estimated_ownership_pct` (chalk-concentrated, far more realistic than uniform; the circularity — our ownership estimate could be wrong — is acknowledged and is what Sessions 9.3/9.4 eventually fix). Report **median-percentile (cash/floor proxy) and max-percentile (upside proxy) separately, never blended.** At n=1 they collapse to one number, which is correct for single-entry.

**Validation:**
- [x] Harness reconstructs a known week's pool, solves, and scores end-to-end against real actuals with no manual step. **Confirmed: full 2021 season ran OK 17 / SKIP 1 / ERROR 0.**
- [x] Produces a baseline percentile distribution for the CURRENT projection system. **72.8 median-pctile / 94.7 max-pctile (see header).**
- [x] Sunday-slate filter verified against a spot-check week (pool excludes Thu/Mon-only players correctly). **Confirmed: 2021 wk1 filter returns 26 main-slate teams, correctly excluding the Thu opener and SNF/MNF.**
- [x] Real historical Vegas derived from nflverse games.csv (decision #1) — the ROADMAP's "no real historical vegas" blocker is closed for BACKTESTING (not live). Sanity check (implied totals sum to game total) passes every game.
- [x] Week 1 correctly identified as not-backtestable (cold-start: no prior-week data) and skipped explicitly, not errored.

---

### Session 10.2 — Salary-Anchor Baseline Curve ✅ Complete (2026-07-26)
**Prerequisites:** Session 10.0 (needs historical salaries). Independent of 10.1, but 10.1's harness makes its value measurable.

**Outcome in one line:** the curve was fit successfully and ships **off by default**; the measured answer to this card's own second validation question is **no** at the points level, and that negative result is recorded as a closed validation, not a failure. The real deliverable turned out to be **cold-start**. Full detail, all seven bugs, and the paired statistics are in SESSION_LOG.md's Session 10.2 entry.

**Sites:** per site (DK full-PPR and FD half-PPR price differently). **DK fitted and measured; FD blocked** — see the Known Deferred Validations entry below.

**Files touched:**
- `/dfs_optimizer/scripts/fit_salary_anchor.py` (new) — the fitter. Quantile bins → count-weighted bin means → weighted PAVA isotonic regression → top endpoint knot → piecewise-linear knot table.
- `/dfs_optimizer/scripts/salary_anchor.py` (new) — the consumer, deliberately separate so the production path never imports the fitting machinery.
- `/dfs_optimizer/scripts/build_projections.py` (modified) — decision #8. `--salary-anchor-weight` (default **0.0 = off**), `--salary-anchor-cold-start`, `--salary-anchor-k`. At the defaults, output is byte-for-byte pre-10.2.
- `/dfs_optimizer/scripts/backtest_harness.py` (modified) — decisions #8, #9 (see the amendment on Session 10.1's card below).
- `/dfs_optimizer/data/salary_anchor_dk.json` (new, `schema_version: 2`) plus two archived variant fits for provenance.

**Build:** fit the empirical points-vs-salary relationship by position from the matched historical data (the 4for4-style baseline: subtract a fitted salary baseline rather than dividing, which structurally over-favors cheap players). This is the market's own forecast, free, and doubles as a sanity check on whether the model is drifting from the market for good reasons or bad. Its immediate secondary payoff: tells us how much signal DK/FD pricing carries vs our historical component — real information about the market-vs-model balance, learned cheaply, before committing weeks to the model side. **That secondary payoff is the one that actually paid** — see the amendment to Phase 10's design intro above.

**Validation:**
- [x] **Curve fit per site per position on the historical data; sanity-checked shape (monotonic-ish, sensible endpoints).** DK, 54,894 real rows across 2014–2021. Monotone at every position (enforced as an error, not hoped for). Expensive-end flat-extrapolation exposure 0.0% everywhere; top-extension ratios 1.09–1.33 against a 1.35 cap, none binding. The pts/$1K tier table confirms this card's own premise: 0.83→2.38 for QB, 0.67→2.66 for RB — rising steeply with price, which is exactly the bias that dividing bakes in and subtracting removes.
- [x] **Measured against Session 10.1's baseline: does adding the anchor help lineup-level percentile?** **No, not as a mid-season points-level blend.** Against 72.8 median-pctile / 94.7 max-pctile, on a pinned field over 17 comparable weeks: flat w=0.15 → −0.45 / +0.20; flat w=0.25 → +0.55 / −0.31; cold-start floor 0.15 → +1.09 / +0.57. Largest effect across seven curve/weight variants: **1.1 percentile points against a 15.6-point week-to-week SD**, all |t| ≤ 1.81, every sign test 7–10 of 17. Cold-start is the only arm non-negative on both metrics, which is why it is the one recommended configuration — but it is inside the noise, so the anchor stays off by default.
- [x] **Session 10.1's baseline reproduces exactly** (72.8 / 94.7, field median 102.27) under the modified harness, confirming decision #9's field pinning is a no-op for the anchor-OFF arm.
- [x] **Cold-start makes week 1 backtestable, and it works.** Week 1 2021 went from structurally unbuildable (Session 10.1 skipped it — no prior weeks, empty pool) to **median-pctile 57.2 / max-pctile 99.7** from price alone: 9/9 players RESCUED, every actuals join OK, no zero-point players. This is the one thing the anchor does that the usage model cannot do at all, and it is the session's real deliverable.
- [ ] **FD — deliberately blocked, not deferred by assumption.** The fit now fails loud on real FD data. See Known Deferred Validations.

**Handoff notes to log:** all logged in SESSION_LOG.md. The two that matter most for later sessions: (1) always compare with the harness's default `--field-pool baseline` and read the arm-independent raw scores alongside the percentiles — the first round of this session's measurement was substantially a moving-yardstick artifact (field median fell in 15/17 weeks, t = −4.3, stronger than any real effect); (2) the anchor is never applied to a `BYE_OR_UNKNOWN` row, and that gate is deliberately NOT `final_projection == 0`, because a cold-start player also projects 0.0 and is precisely who the anchor is for.

---

### Session 10.3a — Stat-Line Projection Rewrite (the core rebuild — "Gap 1") ✅ Complete (2026-07-26)
**Prerequisites:** Sessions 10.1 and 10.2 (harness to measure it, anchor as a component). Built as a NEW parallel component co-existing with `build_projections.py`, which is **untouched and deliberately frozen** — it is the measurement baseline, and correcting even its known-wrong scoring would invalidate every number Sessions 10.1 and 10.2 recorded.

**Outcome in one line:** the engine ships on the **capability gate** agreed before the build — a validated per-player mean *and* sigma, which Session 10.5's objective cannot exist without. Measured out-of-sample over 65 weeks it is **parity with a mild positive tilt**: median-percentile +2.20 (t = +1.15, positive in all four seasons), max-percentile +0.28, raw median lineup score +2.26. Nothing significant, nothing worse. Full detail, the three bugs real runs caught, and the in-sample-leak lesson are in SESSION_LOG.md's Session 10.3a entry.

**Deliverables (all live-validated in the real environment unless noted):**
- `/dfs_optimizer/scripts/scoring_rules.py` (new) — exact DK/FD scoring applied to a stat line. Reproduces nflverse's own `fantasy_points_ppr` to 7.1e-15, which is how its arithmetic is proven rather than asserted.
- `/dfs_optimizer/scripts/fit_statline_variance.py` (new) — the fitter. Writes `data/statline_variance.json`, **site-agnostic** (a stat line is real football; only the converter is site-specific). Notably this is the one Phase 10 component *not* blocked on real FD data.
- `/dfs_optimizer/scripts/statline_model.py` (new) — the consumer: participation-weighted volume, empirical-Bayes-shrunk efficiency, share reconciliation, and the Monte-Carlo draw scheme.
- `/dfs_optimizer/scripts/build_projections_statline.py` (new) — the parallel engine. Writes the **same filename and a superset of the same schema**, which is why `optimizer.py`, `ownership_heuristic.py`, the Worker and the frontend all consume it with zero changes.
- `/dfs_optimizer/scripts/backtest_harness.py` (modified) — `--engine {legacy,statline}`, multi-season `--season`, per-week RNG derivation.
- `/dfs_optimizer/scripts/ownership_heuristic.py` (modified, one line) — `flag_weight` coerced to numeric. A dormant pandas-3.x break, not a live bug; a stopgap ahead of the planned ownership rework, not an investment in it.

**Why Monte Carlo rather than an analytic mean:** DK's bonuses are step functions, so `E[points] ≠ points(E[stats])`. Measured on real data, scoring a mean stat line **over**-credits a player already past a threshold by −2.22 pts and **under**-credits one within reach by +0.36. That is a signed re-ranking error among exactly the players competing for a slot — unlike the scoring-table correction itself, which is a level shift (Spearman ≥ 0.9906 within position) that an ILP barely notices.

**⚠️ The legacy engine's target variable is wrong, and stays wrong on purpose.** nflverse's `fantasy_points` scores an interception at −2; DK and FD both use −1. DK additionally uses −1 for a lost fumble and pays three +3 yardage bonuses. Against each site's own legacy formula the corrected scoring differs on **13.2% of DK rows and 5.2% of FD rows**. `build_projections.py` keeps the old behaviour so the baseline stays valid; only the new engine is correct. A future session must not "helpfully" fix it without re-baselining first.

**Validation:**
- [x] Stat-line component produces per-player mean AND sigma, with an **empirical** within-player yards/TD correlation reproduced by a calibrated latent factor — verified on an independent seed, every component within 0.007 of its measured target. The independence assumption it replaces would have given 0.172 against a measured 0.375 for WR receiving.
- [x] Measured against the Session 10.1 baseline at the lineup level, out-of-sample (variance fit 2014–17, measured 2018–21).
- [x] Share reconciliation step with fail-loud past threshold.

---

### Session 10.3b — Stat-Line Priors, Cold Start, and Role Change ✅ Complete (2026-07-27)
**Prerequisites:** Session 10.3a. Everything here was deferred by explicit agreement, not overlooked.

**Outcome in one line:** ships on the **capability gate** agreed before the build — week 1 is buildable by the stat-line engine for the first time (all four seasons, real percentiles) and the three catalogued role-change cases are repaired *before* reconciliation touches them. The accuracy result is **not** a win: out-of-sample, week-1-excluded, paired over the same 65 weeks, median-percentile **+3.01 (SE 1.55, t = 1.94, p = 0.057)** — below the bar, with 2019 carrying almost all of it (+8.93) and 2020 flipping negative (−0.60). Two of the card's four premises measured FALSE before any code was written and one measured backwards. Full detail in SESSION_LOG.md's Session 10.3b entry.

**The one problem this card exists to solve:** 10.3a's volume model is participation-weighted (a recency average over games a player *appeared in* is a volume conditional on playing, which made a one-start backup look like a permanent starter). That fix is right, and it cannot distinguish "was hurt, is healthy now" from "is a backup." Reconciliation currently does the repair — for passing it allocates the team's whole predicted attempt total among available QBs — which is structurally sound but means **the QB projection is substantially a product of reconciliation rather than of the volume model.** A real role/depth-chart signal is what closes that.

**What shipped** (`volume_prior.py` consumer / `fit_volume_prior.py` fitter, the same split as 10.2 and 10.4; artifact `data/volume_prior_{site}.json`; one flag `--volume-prior`, **OFF by default**):
- **Price as a prior on stat-line VOLUME** — `E[share | salary, position, component]`, isotonic, reusing `fit_salary_anchor.py`'s own PAVA and top-endpoint machinery. **Cold-start only** (mid-season weight floor 0.0, user-confirmed): probe A measured price *losing* to history at every games-played level, pooled MAE 0.0709 vs 0.0600, so a standing mid-season blend was not taken. Residual correlation 0.47–0.60 — real independent information, just the weaker signal.
- **Cold start**, making week 1 buildable. `w = floor + (1−floor)·k/(k+gp)` **× a linear taper to zero over `COLD_START_MAX_GAMES` = 4**. The taper was added after a real run showed the bare schedule leaves a standing 36% price weight at seven games — the floor is the *asymptote*, not the mid-season weight, and "cold-start only" is not true without it.
- **Role-change flag** — acts on **participation**, not on the share (option (b) of two, user-confirmed), so the volume model produces the right answer before reconciliation is consulted, which is exactly what this card asked for. Strength is probe D's **fitted** slope, not a hand-picked constant.
- **Vegas-anchored team volume** — ships with the card's mechanism **corrected**. Both terms always, never one: spread drives carries (t = −6.62, favourites run out the clock), total drives attempts (t = +5.02); alone each is weak (t = +1.54 / +1.07), jointly +4.67 / +4.53, because `implied_total = total/2 − spread/2` and carrying both spans *both* teams' implied totals.

**Premises that measured FALSE, before any code was written** (`probe_statline_priors.py`, a throwaway pre-test that writes nothing):
- **Prior-season team-volume carryover is worse than useless** — week-1 pass attempts R² **−0.065** vs the league mean's +0.015, carries **−0.046** vs +0.026. Week-1 team volume is the league mean tilted by the line; the prior season is not consulted. **This does NOT apply to `dst_model.py` decision #15** — that carries over defensive *quality*, which persists across a season boundary; this is *volume*, which is scheme and pace and turns over with the coordinator.
- **Cold start and team volume are NOT independent bullets.** In week 1 `load_history()` is empty → `team_volume_history()` returns an empty frame → reconciliation cannot run → and `_participation()` returns 0.0 for every player, which would multiply any price-predicted volume straight back to zero. A player share needs a team total to be a share *of*. Cold start therefore *depends* on the Vegas team volume, and they ship behind one flag.

**Side finding, recorded because it reframes an existing component:** team-history volume prediction — what reconciliation has anchored to since 10.3a — explains **6.5%** of pass-attempt variance and **3.9%** of carry variance. That does not make reconciliation wrong (its job is stacking coherence, not team-volume accuracy), but it has been normalizing to a much weaker number than its role suggests. The Vegas terms roughly double it.

**Retuning targets, all flagged ARBITRARY in code and none of them fit:** `COLD_START_MAX_GAMES` 4.0 and `DEFAULT_COLD_START_K` 4.0 (**first targets** — probe A's evidence argues for a faster handover than either), `ROLE_CHANGE_MIN_DIVERGENCE` 0.05, `ROLE_CHANGE_MIN_HIST_SHARE` 0.02, `TEAM_VOLUME_BOUNDS`, plus 10.3a's inherited `SHRINK_K` (yards 40, TD 120, catch 40, INT 400), `RECONCILE_FAIL_THRESHOLD` 0.40, `RECONCILE_MIN_VOLUME` 10.0, `RECONCILE_EXTREME_ABS` 60.0, `RECONCILE_MAX_VIOLATION_SHARE` 0.25, `RECENT_SHARE_MIN_VOLUME` 25.0. `ROLE_SLOPE` is the one constant here that **is** fitted.

**Validation:**
- [x] **Week 1 becomes buildable by the stat-line engine and is measured, not assumed.** All four seasons produce a real percentile (2018 95.0, 2019 81.4, 2020 89.4, 2021 78.0 median-pctile). Correctly flagged NOT cross-arm comparable — a week-1 baseline pool is empty by definition, so the field falls back to the arm's own pool.
- [x] **A returning starter is projected sensibly without reconciliation doing all the work.** Participation before → after the override: Z. Wilson 0.20 → 0.76, R. Wilson 0.60 → 0.78, Newton 0.80 → 1.00. Printed by `fit_volume_prior.py` every run.
- [x] **Price-as-volume-prior measured separately from the rest.** `--no-role-change` isolates it: role change is a **lineup-level null** (−0.06, t = −0.07, p = 0.94). The whole +3.01 is cold start plus Vegas team volume. The flag is kept anyway for the player-level repair, which Session 10.5's objective consumes directly — a QB at a 0.128 predicted share when he took every snap is a wrong projection whether or not he lands in an optimal lineup.

**Deferred, by agreement:**
- The **~+2.0 unexplained discrepancy** against 10.4's recorded 75.9 / 96.7. Every file on the stat-line path was diffed against its pre-session version and cleared (`statline_model.py`, `build_projections_statline.py`, `scoring_rules.py` — 10.4's changes there are purely additive DST, `score_statline()` byte-identical — and `fit_statline_variance.py`, untouched since 10.3a). The variance artifact was tested empirically and exonerated. Most likely a **stale reference**: 10.4's figures may predate its own final commits. **Re-baselined by agreement** rather than chased further — see the new reference below.
- `--volume-prior` **stays OFF by default** until a measurement supports it. 10.4 shipped its model on by default on a measured improvement; this card has none.

**New reference numbers (2026-07-27, holdout artifacts, 65 weeks, week 1 excluded):** stat-line + distributional DST, volume prior OFF = **77.9 / 97.3**, raw median lineup 129.64, best 166.23, field median 108.16. This supersedes 10.4's recorded 75.9 / 96.7 for all future comparison. With the volume prior ON: **80.9 / 97.5**.

---

### Session 10.4 — DST Model Rebuild ✅ Complete (2026-07-26)
**Prerequisites:** Session 10.0. Independent of 10.1-10.3 (self-contained; ran in parallel). The card's "best ROI-per-effort in the phase" call held up.

**Outcome in one line:** the distributional model **ships ON BY DEFAULT** — the first Phase 10 component to do so — on a DST-slot improvement measured against real graded actuals (MAE −0.50, RMSE −0.80, **Spearman +0.11**), with the lineup-level check confirming no regression (+0.3 median-pctile / +0.2 max-pctile, both inside one SE, as pre-registered). It also produces the **conditional DST sigma** Session 10.5 needs and closes the flat `matchup_factor = 1.0` gap open since Session 2.4. Full detail, the four bugs real runs caught, and the two design premises that measured out FALSE are in SESSION_LOG.md's Session 10.4 entry.

**Deliverables (all live-validated on the real Windows environment):**
- `/dfs_optimizer/scripts/dst_model.py` (new) — the simulator. Monte-Carlo over per-component distributions, bracket table integrated per draw, mean + conditional sigma from one pass.
- `/dfs_optimizer/scripts/fit_dst_model.py` (new) — the fitter, writes `data/dst_model.json`. Deliberately separate so the production path never imports fitting machinery (same split as 10.2's `salary_anchor` / `fit_salary_anchor`).
- `/dfs_optimizer/scripts/measure_dst.py` (new) — DST-slot measurement against real graded RotoGuru DST actuals.
- `/dfs_optimizer/scripts/statlite.py` (new) — the four SciPy functions this needed (NB log-pmf, bounded 1-D minimiser, Spearman, paired t-test), on numpy + stdlib. SciPy was NOT installed on the real environment and the production path did not need it; `verify_against_scipy()` proves every function matches SciPy to ~1e-13.
- `/dfs_optimizer/scripts/scoring_rules.py` (modified) — gained the DST table (it had none), `score_dst()`, `dst_points_allowed()`, and `verify_dst_against_actuals()`.
- `/dfs_optimizer/scripts/build_projections.py` (modified) — `--dst-model`, **default `distributional`**. `--dst-model legacy` reproduces pre-10.4 output byte-for-byte.
- `/dfs_optimizer/scripts/build_projections_statline.py` (modified) — same flag forwarded; the distributional path also supersedes 10.3a's placeholder DST sigma.
- `/dfs_optimizer/scripts/backtest_harness.py` (modified) — `--dst-model` (**default stays `legacy`**, see below), DST model added to the arm label, flag always passed explicitly.
- `/dfs_optimizer/scripts/nflverse_fetch.py`, `ingest_historical.py` (modified) — the `stats_team` release (~126 KB/season) and `games.parquet`.
- `/dfs_optimizer/data/dst_model.json` (new, `schema_version: 1`) — production fit, all eight seasons.

**⚠️ THE DEFAULTS DIVERGE ON PURPOSE, and this is the single most important thing to know about this card.** `build_projections.py` and `build_projections_statline.py` default to **distributional** (production should use the better model). `backtest_harness.py` defaults to **legacy**, because its default *is* the definition of the Session 10.1 baseline arm, and decision #11's pinned field must keep meaning "legacy engine, anchor off, legacy DST" or every recorded Phase 10 number becomes incomparable. The harness therefore passes `--dst-model` **explicitly on every invocation** rather than relying on a downstream default — an omitted flag would have silently handed it a distributional DST while it believed it was the baseline.

**⚠️ NEW REQUIRED INPUT FOR THE AUTOMATED REFRESH.** Because distributional is now the default, `data/team_stats_{season}.parquet` and `data/dst_model.json` are required inputs to **every** projection build, including the GitHub Actions refresh. `refresh_data.yml` needs a step pulling the CURRENT season's team stats each week; without it the DST model runs on prior-season carryover alone (degraded, not wrong) or fails loud if the file is absent entirely. **This is an open item — see Known Deferred Validations.**

**Measured results:**

*DST slot, real graded DK actuals, legacy arm read from the real salary files (65 weeks, 1,914 defense-weeks):*

| | legacy | distributional (holdout fit) | distributional (production fit) |
|---|---|---|---|
| MAE | 5.121 | 4.624 | **4.552** |
| RMSE | 6.608 | 5.805 | **5.781** |
| Spearman | 0.199 | 0.309 | **0.311** |
| mean projected vs actual 6.688 | 6.987 | 7.213 (+0.53) | **6.908 (+0.22)** |
| sigma calibration | n/a | 0.944 | 0.931 |

The middle column is the honest out-of-sample number (fit 2014-17). The right column is the shipped production fit and is **in-sample** for these seasons — recorded as the configuration's numbers, not as evidence. Chosen-DST +0.69/week, t = +0.65, p = 0.52: positive, not significant, not claimed.

*Lineup level, pooled 2018-2021 DK, 65 weeks × 20 lineups, legacy engine, anchor off:*

| | baseline | distributional DST | delta |
|---|---|---|---|
| median-percentile | 75.6 ± 1.6 | 75.9 ± 1.8 | +0.3 |
| max-percentile | 96.5 ± 0.6 | 96.7 ± 0.6 | +0.2 |
| raw median lineup | 127.17 | 127.72 | +0.55 |
| raw best lineup | 163.67 | 164.34 | +0.67 |

Both percentile deltas are a fraction of one SE and signs flip across seasons (2019 median −3.9, 2020 median +3.1), which is what noise looks like. **This was pre-registered as a pass before the run**: a DST moves ~6.7 of ~120 lineup points and cannot clear a 1.8-point SE. The card ships on the DST-slot evidence; the harness run is a regression check, and it passed.

**Baseline reproduction confirmed:** re-running the harness with no new flags returns **75.6 / 96.5**, raw median 127.17, best 163.67, field median 108.16 — identical to Session 10.3a's recorded values to the cent. `build_projections.py` was modified this session and the frozen baseline is provably intact.

**Two of this card's own design premises measured FALSE, and the card is amended rather than quietly satisfied:**
1. **"handles the DK/FD bracket divergence correctly" — there is no divergence.** DK and FD share every bracket and every component value. Verified by reconstructing real graded actuals for both sites from nflverse components: DK 89.7% exact / mean bias −0.156, FD 87.5% / −0.178. Tables stay per-site so a future divergence is a config edit, but no code branches on site.
2. **"own-defense EPA/play as the stable modifier" — the OPPONENT's offense carries roughly four times the signal the defense's own history does** (sacks: opponent's sacks-allowed prior t = +12.4 vs own t = +4.8). Own-defense EPA survives as a small mean-reversion correction on the market's number (t = −2.13), not as a quality signal. The model follows the data and the card is corrected here.

**Validation:**
- [x] **Distributional points-allowed integrates over real brackets per site (not a single-bracket lookup).** Confirmed and quantified: integrating over the fitted NB returns mean bracket value 0.433 against a realized 0.479, while point-estimate lookup returns 0.181 — biased low 0.30 pts on **every** defense, compressing the across-defense spread 19% (SD 0.860 → 0.696) and ranking worse (Spearman 0.336 → 0.369). Fitted NB dispersion r = 6.50; overdispersion measured at var/mean 3.4–4.4, so Poisson is ruled out on data, not assumed.
- [x] **Measured against Session 10.1 baseline for the DST slot specifically.** Both halves done — direct DST accuracy against real graded actuals (table above) and the lineup-level A/B against 75.6 / 96.5. The card's single line was split into two measurements because the harness cannot isolate one of nine slots.
- [x] **Conditional sigma delivered** (`sigma_source = dst_simulated_session_10_4`), replacing 10.3a's unconditional `3.25 + 0.39 × projection` placeholder and clearing the blocker flagged on Session 10.5's card. Calibration 0.931 (1.00 ideal); range 5.56–6.78 and genuinely varying with the opponent.
- [x] **`matchup_factor = 1.0` retired** — the gap flagged since Session 2.4. Now carries the ratio of a defense's simulated mean to the league-average simulated mean (real observed range 0.60–1.55).
- [ ] **FD unverified**, same standing gap as everything FD. Weaker exposure than the FD salary anchor: the DST scoring table IS verified against real FD 2021 actuals, and the model is site-parameterised throughout. See Known Deferred Validations.
- [x] **`refresh_data.yml` team-stats step** — ✅ Resolved in Session 10.5b. `ingest_historical.py --season {season}` step added before projection builds, `continue-on-error: true`, tracked in run log.

---

### Session 10.5 — Objective + Randomization Rewire (needs 10.3a's sigma)
**Prerequisites:** Session 10.3a (sigma now exists), Session 10.4b (sigma dispersion corrected).
**Status:** ✅ Complete (2026-07-28). Sweep deferred to Session 10.5b (build-once efficiency required). See SESSION_LOG.md for full detail.

**Files touched:** `scripts/optimizer.py` (sigma carry-through, `--lambda` flag, mean-variance objective `Σμ − λΣσ²`, `--randomization-mode {pct,sigma}`), `scripts/backtest_harness.py` (sweep infrastructure, beat/top-rate metrics, results CSV).

**Validation:**
- [x] λ=0 reproduces 10.3b re-baseline: **77.8 / 97.6** pooled (target 77.9 / 97.3) — within floating-point + one week's variance. ✅
- [x] λ sweep run in Session 10.5b. ✅

**Key decisions:** penalty form is Σσ² (variance, not sigma); grid spans negative λ; backtest-only scope; `mode="pct"` default byte-identical to all prior sessions; beat@p44 → cash, beat@p50 → 3-max, top@p90 → GPP selection rule pre-registered in code.

**DST warning from 10.4 measured FALSE.** DST sigma is nearly constant across defenses (slope 0.055, Spearman +0.076) — no λ in the useful grid drives the optimizer to the cheapest defense.

---

### Session 10.5b — Lambda Sweep and Build-Once Efficiency
**Prerequisites:** Session 10.5.
**Status:** ✅ Complete (2026-07-28). Phase 10 closed. See SESSION_LOG.md for full detail and sweep tables.

**Files touched:** `scripts/backtest_harness.py` (`skip_projection_build` parameter, decision #15), `.github/workflows/refresh_data.yml` (team-stats pull step, closes 10.4 deferred item).

**Build-once fix:** `skip_projection_build: bool = False` in `backtest_week`. Sweep loop passes `skip_build = (i_lam > 0)` — full pipeline on the first lambda, optimizer-only on all subsequent. Fails loud if the expected projection file is missing. Runtime: ~2h45m per sweep (3× builds on first-lambda week: arm + field-baseline + arm-rebuild after clobber; ~195 total builds for 65 weeks × 11 lambdas).

**refresh_data.yml:** `ingest_historical.py --season {season}` step added before projection builds, `continue-on-error: true`. Tracked in run log as `team_stats_pull`. **Closes the Session 10.4 deferred item.**

**Sweep results (DK, 2018–2021, 65 weeks, holdout artifacts):**

20max — λ=0 anchor: 77.84 / 97.59. Useful range: λ=0.039–0.104 for cash floor; λ=0 for GPP.
- Cash (beat@p44): λ=0.063 best at 0.8723 vs λ=0 at 0.8662 (+0.006, < 1 SE — suggestive, not conclusive).
- 3-max GPP (beat@p50): λ=0.063 at 0.8323 vs λ=0 at 0.8285. No clear winner.
- Large-field GPP (top@p90): λ=−0.005 best at 0.9846; positive λ hurts (drops to 0.9077 at λ=0.063). λ=0 or mild negative correct for GPP.
- λ≥0.188 harmful everywhere (median-pctile −5.5, all other metrics fall). Hard upper bound established.

3max — λ=0 anchor: 78.21 / 93.75. Same directional pattern; noisier. λ=0.104 best on beat@p44 (0.8718).

**Pre-registered selection applied:**
- Cash games: λ=0.063 (weakest reasonable recommendation; inside noise over 65 weeks, consistent direction).
- 3-max GPP: λ=0 (no improvement measured).
- Large-field GPP: λ=0 (positive λ provably hurts top-rate).

**Default unchanged.** λ=0 remains the shipped default. Strategy selection of a non-zero λ is a human decision from the curve above, same as exposure caps and uniqueness.

**Single-entry not run.** Deterministic at n=1 — equivalent to probe A's analysis, already in log.

**Deferred (not newly opened):**
- `--sigma-recalibration` end-to-end wiring validation → Preseason Week 1.
- `dst_model.json` holdout refit (needs `ingest_historical.py --season 2013`) → whenever.
- FD sigma artifact → whenever FD real data exists.

---


- Phases 1-3 are strictly sequential
- Phases 4 and 5 can run in parallel, both need Phase 3 done first
- Phase 6 is the real validation gate for everything before it
- Phase 7 can start as early as Phase 3 is stable
- **Execution-order update (2026-07-23):** Phases 1-5 finished ahead of schedule (2026-07-23 vs. the original Aug 10-13 target), well before Phase 6 can start for real — Phase 6 is blocked on a real preseason slate existing at all (Aug 13-15 at the earliest, per this roadmap's own milestones and "Known Deferred Validations" below), not on anything still open in this project. Rather than sit idle, **Phase 7 (Frontend/Hosting) is being executed next, ahead of Phase 6** — this was already permitted by this section's own "Phase 7 can start as early as Phase 3 is stable" note, just not previously acted on. Phase numbers are intentionally left unchanged (only the execution order deviates) since both files have extensive existing cross-references keyed to "Phase 6"/"Session 6.x" specifically meaning the preseason dry runs — renumbering would be pure churn for no functional benefit. The optional Madden Sims bridge-testing entry above (between Phase 5 and Phase 6 in this document's order) has no dependency relationship with Phase 7 in either direction and can be worked whenever, or skipped, independent of Phase 7's progress.
- Ownership sophistication, correlation-matrix stacking, and MLB expansion are deliberately excluded — v2 work, after core NFL product is proven through a live season

## Notes on dual-site (DraftKings + FanDuel) scope
Added retroactively during Session 1.3's revision (see SESSION_LOG.md) — the project was DK-only through the original Session 1.3 before this was clarified. What this changes, structurally:

- **Site-agnostic (no change needed):** Session 1.1 (environment), Session 1.2 (nflverse historical data), Session 2.3 (Vegas odds), Session 5.1 (injury status). These operate one level below any DFS site's rules.
- **Site-aware, runs once per site (DK and FD in parallel, same logic parameterized):** Session 1.3 (salary ingestion), Sessions 2.1/2.2/2.4 (projections — because DK is full-PPR and FD is half-PPR, so fantasy point values genuinely differ, not just formatting), Session 3.1-3.3 (optimizer — different cap and roster slots), Session 4.1/4.2 (ownership/pivots — different price context), Session 5.2 (scheduling — both sites' refreshes), Sessions 6.1-6.3 (dry runs — both sites), Session 8.1/9.1-9.4 (go-live and learning loop — both sites).
- **Needs a site concept in the UI:** Phase 7 (frontend) — a site selector/toggle, not two separate apps.
- **Canonical site config lives in one place:** `ingest_salaries.py`'s `SITE_CONFIGS` dict (Session 1.3) is the source of truth for each site's salary cap, roster slots, and scoring format (full vs half PPR) — later sessions should read from there rather than re-declaring these values, so a correction in one place propagates everywhere.
- **FLEX eligibility is NOT in `SITE_CONFIGS`, added as a hardcoded assumption in Session 3.1's `optimizer.py`** (`FLEX_ELIGIBLE_POSITIONS = {"RB", "WR", "TE"}` — standard classic-contest DFS rule on both DK and FD, but never explicitly confirmed with the user since `SITE_CONFIGS` only stores the roster_slots list, not which positions can fill FLEX). If a future site/format needs a different rule (e.g. superflex allowing QB in FLEX), this is the one place to change — worth eventually promoting into `SITE_CONFIGS` itself rather than living only in `optimizer.py`.
- ~~**FanDuel validation gap:**~~ ✅ **RESOLVED (Session 14.1c, 2026-08-11).** As of Session 1.3's revision, DK's ingestion path had been validated against real data while FD's was synthetic-only. FD's ingestion path is now validated against a real FD Classic Week 1 2026 export -- see Known Deferred Validations below for the full list of what this closed.

## Known Deferred Validations (blocked until a real current-week NFL slate exists)
*Added during Session 2.4. Update this list every session that hits one of these gaps -- it's the single place to check "can this actually be validated for real yet?" instead of re-discovering the same blocker session after session.*

These are all instances of the same underlying problem: several data sources (The Odds API, live DK/FD salary exports) only exist for **games that are either currently live-listed or already happened** -- there is no real historical archive available to us, and no real future-week data exists yet. That means backtesting against a past season (e.g. 2025) and validating against real current data are two different things that can't both be true of the same run.

- **Real Vegas lines for a specific backtest week.** The Odds API's `/odds` endpoint only returns currently-listed games -- it can't retroactively supply real lines for a past week (e.g. 2025's week 10, already played) or a future week too far out for books to have posted lines yet. `vegas_odds.py`'s output for any week outside "currently listed" is necessarily synthetic or absent. **First point this closes for real:** once real preseason games are close enough that books post lines -- Preseason Week 1, Aug 13-15, 2026, per this roadmap's own milestone. **PARTIALLY RESOLVED for BACKTESTING (Session 10.1):** nflverse's `games.csv` carries real historical `spread_line`/`total_line` going back decades, so the backtest harness derives a genuinely real (not synthetic) `vegas_implied_totals_{week}.csv` for any past week using `vegas_odds.py`'s own `implied = total/2 - spread/2` formula (verified: implied totals sum to the game total every game). This closes the blocker for HISTORICAL BACKTESTING only -- the LIVE production gap (The Odds API can't supply a future/current week retroactively, and can't post lines before books do) is unchanged.
- ~~**Real FD salary data, at all.**~~ ✅ **RESOLVED (Session 14.1c, 2026-08-11).** Real FD Classic Week 1 2026 export ingested successfully. `required_columns`, `site_id_col` ("Id"), and `avg_ppg_col` ("FPPG") — all previously documented guesses — confirmed correct against the real file with no corrections needed. `ingest_salaries.py`'s comments updated from UNVERIFIED to CONFIRMED.
- ~~**Session 2.4's full real end-to-end validation, both sites.**~~ ✅ **RESOLVED (Session 14.1c, 2026-08-11).** Real FD Week 1 2026 salaries, real matchup data, and real vegas-derived context all existed simultaneously for the same slate, same week, alongside DK. Full pipeline run end-to-end: ingestion → projections → optimizer → frontend export, both sites, confirmed live.
- ~~**Session 3.3's stacking logic, against real data -- DK closed same day (addendum), FD still open.**~~ ✅ **RESOLVED (Session 14.1c, 2026-08-11).** FD stacking confirmed live against the real Week 1 2026 slate (12 games / 24 teams) -- both a normal and a stacked build succeeded. User's explicit call: a 12-game/24-team real slate is a good enough test of full-slate stack feasibility; not waiting for a full 16-game/32-team week specifically to close this.
- ~~**Session 5.1's real OUT/DOUBTFUL game-day designations, cross-checked against NFL.com.**~~ ✅ **RESOLVED (Ad Hoc Session A1, 2026-09-10).** Real Week 1 2025-season-labeled slate (season=2025, week=23 per this project's season/week sentinel convention) now exists 3 days from lock, giving real game-week designations to check for the first time -- 2026-07-22's pull only ever saw long-term-recovery/personal-situation statuses, since no real game existed yet to designate anyone in/out FOR. A real pull on 2026-09-10 returned 60 OUT, 2 DOUBTFUL, 23 QUESTIONABLE, 521 ACTIVE across 606 matched players (78.6% match rate), including a real, verifiable game-week designation (Patrick Mahomes, KC QB, "Questionable") that was spot-checked directly against ESPN's live endpoint before trusting the pull. `apply` was run against all 7 real committed Week 1 slate files (DK classic main/early, DK showdown, FD classic main/early/afternoon, FD showdown); every OUT player's `final_projection` confirmed 0.0 on reload (the script's own built-in re-check), and a handful of QUESTIONABLE/DOUBTFUL players (Zay Flowers, Tua Tagovailoa, Brock Bowers, etc.) spot-checked to confirm they were flagged but left non-zero, per decision #4's "flag, don't exclude" design. This also surfaced and fixed a real, separate bug found in the same pass: ESPN now returns a raw status of `"Suspension"` (title case, not previously seen) which wasn't in `STATUS_MAP` and was causing `status_check.py pull` to fail loudly (`sys.exit(1)`) whenever a suspended player appeared on a pulled roster -- added `"suspension": "OUT"` to `STATUS_MAP`. NFL.com's own injury report was not directly diffed against (no such fetch was built this session), so this closes "real game-day designations exist and the mechanism works against them," not a line-by-line NFL.com cross-check -- flagged here rather than silently claimed as the stronger validation.
- **Session 5.2's real weekly cron-job.org schedule + `current_slate.json`, both sites.** This one's a configuration gap rather than a data-quality gap -- the automation mechanism itself is fully built and validated (see SESSION_LOG.md's Session 5.2 entry), but the cron-job.org near-lock job (currently a Sunday-11am-CT/every-10-min *template*, approximating a typical 1:00pm ET early-slate lock) and `current_slate.json` (currently a season-2026/week-1 *placeholder*) both need hand-updating to whatever the real Week 1 slate/lock times turn out to be. **User's explicit call (Session 14.1c, 2026-08-11): deliberately waiting until closer to lock to set real values, not an oversight.** First point this actually needs doing: shortly before Week 1's real lock time.
- ~~**Session 7.2's UI-Optimizer Integration, FD side.**~~ ✅ **RESOLVED (Session 14.1c, 2026-08-11).** FD confirmed live on the deployed site against the real Week 1 2026 slate: lineups built successfully, both unstacked and stacked. One real bug found and fixed via this live use, not caught by code review -- see below (`optimizer.py`'s FD defense-label mismatch, "D" vs "DEF").
- ~~**Session 7.3's "Download Lineups" DK/FD-import feature, FD side.**~~ ✅ **RESOLVED (Session 14.1c, 2026-08-11).** `site_id_col` ("Id") confirmed correct against a real export. One real bug found via an actual FD upload attempt and fixed: FD's real bulk-upload validator rejects the `"Name (ID)"` cell format DK's uploader tolerates -- FD's own on-screen instructions describe that format as valid, but that text is written for their manual web-grid entry, not their file-upload parser. `index.html`'s FD export switched to ID-only per cell; DK's export unchanged. Confirmed live: FanDuel accepted the re-exported file.
- **Session 7.3's Game Stack QB requirement (decision #30) and multi-team/multi-game stack pinning (decision #32), full-size slate.** Both validated end-to-end against real data, but the only real test pool available this session (the DK Madden Sim slate) has just 6 teams and exactly one real two-sided game -- multi-game rotation specifically was only validated at the candidate-resolution level directly, not through a full multi-game solve, since a second real game wasn't available to solve against. **DK's own full-size confirmation:** whenever DK is next re-tested against a full 32-team real slate. **FD: RESOLVED (Session 14.1c, 2026-08-11)** -- real 12-game/24-team Week 1 2026 slate, stack build confirmed live; user's explicit call that this size is a good enough test of full-slate stack feasibility.
- **Session 7.3's mobile responsive CSS fixes and several other late-session UI changes, live re-confirmation.** Fixed based on a real user-reported bug (Pixel 9 Pro XL layout issues), validated by static structural checks (syntax, DOM-id cross-reference, balanced grid areas) but not yet re-confirmed working live on that same device, nor has the Minimum Salary slider, the new stack team/game chip pickers, or the partial-build warning banner been exercised live yet. See SESSION_LOG.md's Session 7.3 entry, "What's validated live vs. sandbox-only" section, for the full breakdown of what has and hasn't been user-confirmed.

- ~~**FD volume prior never fit (Session 10.3b's FD portion).**~~ ✅ **RESOLVED (Session 14.1c, 2026-08-11).** `data/volume_prior_fd.json` fit on FD's one available real matched season (2021, 18 weeks) -- necessarily single-season and in-sample, unlike DK's 8-season holdout-then-production fit, since no second FD season exists to hold out. Role-change slope +0.6732 (t=59.59), all three catalogued cases (Wilson/Wilson/Newton) flagged correctly. Committed and confirmed live against the real Week 1 2026 slate.

- ~~**FD sigma recalibration never fit (Session 10.4b's FD portion).**~~ ✅ **RESOLVED for QB/RB/WR/TE (Session 14.1c, 2026-08-11), DST deliberately left raw.** `data/sigma_recalibration_fd.json` fit on the same single real FD season. QB, RB, WR, TE all fit; FD's QB curve (b=0.144, r²=0.323) landed almost exactly on DK's own independently-fit QB curve (b=0.138, r²=0.678) despite a third of the data -- real convergence, not coincidence. DST would not fit even after including week 1 ("0 usable bins") -- investigated against DK's own DST fit, which is *also* weak (r²=0.548, required clamping) on 4x the data, so this was judged a genuinely marginal fit on either site rather than an FD-specific gap worth forcing with loosened thresholds. Left raw; the consumer (`sigma_recalibration.py`) already handles a missing position gracefully. Also fixed a real architecture gap found in the same pass: this artifact was a single shared file with only an internal `"site"` field distinguishing DK from FD -- fitting FD would have silently overwritten DK's file. Changed to a site-keyed filename (`sigma_recalibration_{site}.json`), matching `volume_prior_{site}.json`'s convention. DK's existing fit preserved via a plain rename, no refit needed.

- **`backtest_harness.py` -- two real, pre-existing filename-keying bugs found and partially fixed (Session 14.1c, 2026-08-11).** Neither is FD-specific; both affect DK equally, just never surfaced because nothing had re-exercised this harness since an earlier session moved the projection engine and the vegas-lookup helper to slate_id-based file naming. (1) `run_projection_pipeline()`'s vegas lookup expected a slate_id-named file that `build_vegas_file()` never wrote (week-named instead) -- fixed by passing `--vegas-slate-id` explicitly. (2) `run_projection_pipeline()`'s own post-build file check still looked for the old week-based projections filename -- fixed. **NOT fixed, flagged open:** `backtest_week()` (the standard multi-week/lambda-sweep entry point, a different function from the one just fixed) has three of its own references to the same old week-based filename, at least one of which looks like the same bug class -- unverified, since nothing this session called `backtest_week()` directly. **First point this needs checking:** the next real backtest or lambda-sweep run through `backtest_week()`, either site -- treat an unexpected "file not found" there as this exact issue before assuming something new.

- ~~**`optimizer.py`'s FD lineup builds were always infeasible (found live, Session 14.1c, 2026-08-11).**~~ ✅ **RESOLVED.** FD's real defense position label is `"D"`, but `SITE_CONFIGS["fd"]["roster_slots"]` names the slot `"DEF"` -- the solver keyed its player pool by the literal position string, so the DEF slot's required pool was silently empty on every FD build (an always-infeasible constraint, not a thin-pool issue). DK never hit this because its slot name and raw label are both `"DST"`. Fixed by canonicalizing `{DST, D, DEF}` to the active site's own roster-slot name at load time. Confirmed live: both stacked and unstacked FD builds succeed.

- ~~**`index.html`'s FD "Download Lineups" export was rejected by FanDuel's real uploader (found live, Session 14.1c, 2026-08-11).**~~ ✅ **RESOLVED.** FD's file-upload validator rejects the `"Name (ID)"` cell format DK's uploader tolerates, despite FD's own on-screen instructions describing it as valid (that text is for their manual web-grid entry, not the file-upload parser). FD export switched to ID-only; DK unchanged. Confirmed live: FanDuel accepted the re-exported file.

- **Session 15's participation floor has not been independently re-validated against one specific real violation post-fix, unlike Session 15's own pivot fixes (B1/B2), which were.** Resting on the user's own real-build confirmation ("not seeing any flags... i think we're good") rather than a traced example the way Daniel Jones/Riley Leonard was traced pre-fix. **First point this closes for real:** if a backup-shaped player ever reappears in a real build, or the next time a real Jones/Leonard-shaped case (a starter returning from a late-season injury) shows up on a real slate to check the floor against directly.
- **Session 15's participation floor is scoped to classic slates only — Showdown deferred, not built.** Showdown's CPT/FLEX role model doesn't map onto a position-keyed floor the same way classic's roster slots do; silently no-ops there with a printed NOTE rather than erroring. **First point this would need addressing:** if a Showdown-specific version of the backup-QB problem is ever reported for real.

Until Preseason Week 1: treat Session 2.4 (and by extension anything built on top of it in Phase 3+) as validated for correctness-of-logic only, not for real-world data quality. Re-run Session 2.4's validation checklist in full once real data exists for both sites.

- **FD's salary-anchor curve cannot be fit, and is now BLOCKED rather than deferred by assumption (Session 10.2).** This one is different in kind from the other FD gaps in this list: it isn't "untested," it's "demonstrably not fittable on the data that exists." With only 2021 matched (RotoGuru has no FD before 2011 and nothing after 2021, and only 2021 was matched in Session 10.0), QB bins to 4 knots and the defense to 3, and the top-endpoint extension hits its cap at **QB, RB, WR and TE simultaneously** — WR's top bin mean is $7,045 against a $10,200 salary maximum, a $3,155 gap the extension cannot honestly span. A capped top means expensive players compress onto a near-flat anchor, which is precisely the region that decides lineups. `fit_salary_anchor.py` now treats both conditions as hard errors before writing anything, and `data/salary_anchor_fd.json` was deleted so a stale unfit curve can't be silently picked up. Note this also exposed and fixed a real hole in the fitter's own guard — it counted ROWS, not BINS, and let a 3-knot curve through twice. **User's explicit call (Session 14.1c, 2026-08-11): stays blocked, no action taken.** Largely moot regardless — the production stat-line engine (`build_projections_statline.py`) never used the salary anchor at all (decision #4), only the legacy engine did. **First point this would close for real, if ever revisited:** whenever enough real FD Classic slates accumulate to fit against.

- ~~**`refresh_data.yml` needs a current-season team-stats pull (opened by Session 10.4).**~~ ✅ **RESOLVED in Session 10.5b.** `ingest_historical.py --season {season}` step added before projection builds, `continue-on-error: true`, tracked in run log as `team_stats_pull`.

  **The pre-kickoff wrinkle, verified 2026-07-26:** nflverse does NOT publish `stats_team_week_{season}.parquet` until that season's first games are played — the 2026 asset 404s today while `games.parquet` already carries all 272 scheduled 2026 games with null scores. So the refresh step cannot simply pull the current season and assume success. `dst_model.py`'s decision #19 handles this: a missing current-season file is legitimate when `season_has_started()` is False (no game has a score yet) and a hard error once it is True, so the two states are told apart by data rather than by a calendar guess. Verified end-to-end — 2026 week 1 builds 32 defenses on 2025 carryover alone, projections 6.62–7.89, sigma 5.92–6.22.

  **What this means concretely:** `data/team_stats_2025.parquet` is a REQUIRED commit for the 2026 season (it is the carryover source), and `team_stats_2026.parquet` only becomes fetchable after Preseason/Week 1 games are played. The workflow step must tolerate a 404 on the current season without failing the run.

  **Fix (doable now):** add a step to `refresh_data.yml` ahead of `build_projections.py` that pulls the current season's team stats and does not fail the job on a 404, plus commit `team_stats_2025.parquet`. **First point the current-season half matters for real:** once 2026 games have actually been played — Preseason Week 1, alongside the other Session 6.1 checkpoint items.

- ~~**FD's DST model is unverified end-to-end (Session 10.4).**~~ ✅ **RESOLVED (Session 14.1c, 2026-08-11).** Real FD Classic Week 1 2026 export ran through the DST model end-to-end successfully (distributional model, all real games, no byes).

- ~~**FD DST projection path reads the wrong column name (found during Session 10.0).**~~ ✅ **CODE FIX COMPLETE (2026-07-29), REMAINING STEP RESOLVED (Session 14.1c, 2026-08-11).** `ingest_salaries.py`'s `SITE_CONFIGS` now has an `"avg_ppg_col"` key per site (`"AvgPointsPerGame"` for DK, `"FPPG"` for FD). `build_projections.py`'s legacy DST path reads that key instead of hardcoding DK's column name, and a fail-loud `SystemExit` guard fires if the column is absent, naming the right place to fix it. `"FPPG"` confirmed correct against a real FD Classic export. The RotoGuru harness is unaffected (its FD files already emit `AvgPointsPerGame`). See SESSION_LOG.md's FD DST Column Name Bug Fix entry for full detail.

## RESOLVED (Session 2.4 addendum): salary-file team drift in backtests
*Originally logged as an open decision; implemented this session ("Option A" -- auto-correct, no flag). Kept here rather than deleted, since the reasoning is worth keeping visible for future sessions touching this logic.*

Confirmed with real data: when a backtest uses a **live, current-day salary file** (e.g. today's DK Madden Stream export) against a **historical target week** (e.g. week 10, 2025), any player who's changed teams -- or simply didn't play that week at all (bye, injury, inactive, hadn't debuted) -- between that historical week and today can get matched to the wrong context. Quantified in Session 2.4's DK validation run: the #2 overall projected player (Joe Flacco) was matched to a real week-10-2025 game (`CLE` vs `NYJ`) he wasn't actually part of (he was on `CIN`, which had a bye that week).

**Implemented in `build_projections.py`:** if `weekly_stats_{season}.parquet` already has real rows for the target week (i.e. it's already been played), each player's team is cross-checked against their real game that week, with two distinct outcomes:
- **Played under a different team** (in-season trade) -> corrected to their real team.
- **No real game that week at all** (bye, injury, inactive, not yet on a roster) -> `final_projection` forced to `0.0` directly (not just matchup_factor/vegas_factor neutralized to 1.0 -- an earlier version of this fix stopped there, which still left a real nonzero `final_projection` for a player confirmed via hindsight to have scored zero real fantasy points; caught by the user, corrected same session). This only ever fires for an already-played week -- a live run with an uncertain-status player still correctly gets a normal non-zero projection, since that's genuine uncertainty (Session 5.1's job), not a confirmed zero.

If the target week hasn't happened yet (a live/current run), `weekly_stats` has no rows for it by construction, so none of this logic runs and the salary file's team is used as-is -- **live production behavior is unchanged.** Automatic, no flag to remember.

**Worth knowing for future sessions:** on the one real pool tested (85 skill players, DK, week 10 2025), 41 (≈48%) ended up in the "no real game" bucket -- most explained by 4 real team byes that week, the rest by individual injuries/inactives unrelated to any team-level bye. This ratio isn't a bug and will vary week to week; it's just how much uncertainty exists when validating a *current* salary snapshot against an *arbitrary past* week.

## Known Testing Artifact (NOT a data/logic problem): small pool distorts "top 10" sanity checks
*Added during Session 2.4, after the user questioned why a $3,300 WR3 (Josh Downs, DK) ranked in a top-10 projection ahead of several QBs -- verified this is a property of the test data, not the pipeline.*

Session 2.4's real-data validation run used the 93-player DK Madden Stream contest pool (the only real salary data available, per Session 1.3's log) as a stand-in for a full week-10-2025 slate. Two things compound to make this pool's "top 10" look unrepresentative of what a real slate would produce:

1. **The pool itself is tiny.** A real DK slate has 25-32+ starting-caliber QBs (one per active team, often two). This test pool has **12 QBs total, period** -- it's a small Madden Stream contest, not a real week's full player pool.
2. **The team-drift fix (resolved item above) correctly zeroed out several of those 12** -- Jayden Daniels ($8,300, the single highest-salaried player in the whole pool), Dak Prescott, C.J. Stroud, and Joe Flacco all had strong real season_avg values but no real game that specific week (bye/injury), so their `final_projection` is correctly `0.0`. That leaves only **4 QBs with any nonzero projection** in this particular pool.

Verified every individual number behind this (season_avg, recent_form, matchup_factor, vegas_factor, the blend formula itself) is computed correctly for both the QBs and Josh Downs -- nothing in the pipeline is malfunctioning. The distortion is entirely external: with only 4 real QBs to compete against, a well-projected cheap WR3 can out-rank most of the "QB" bucket in this pool by pure thinness of the field, not by outperforming what a real full slate's QB depth would produce. **This resolves itself automatically** the moment `build_projections.py` runs against a real, full DK/FD slate (Preseason Week 1 or later) -- no code change needed, just real data with a normal-sized player pool. Flagging here so a future session doesn't mistake this pool's top-10 shape for a real property of the model.


## RESOLVED (Session 3.1): DST/DEF projections added
*Previously an open gap since Session 2.4 ("Team defenses have no projection at all from this pipeline — needs a decision in a future session, likely before Phase 3's optimizer needs a full 9-slot roster including DST/DEF"). This is that future session -- Session 3.1's optimizer needs a legal 9-slot roster for both sites, and neither site's roster is legal without a DST/DEF slot filled.*

**Decision (user-confirmed):** added a real (not placeholder) DST/DEF projection to `build_projections.py`, built from the only two genuinely real signals available for a defense — DK/FD's own `AvgPointsPerGame` (real season average, used for both `season_avg` and `recent_form` since no week-by-week defense data exists to split them), and Vegas, inverted: `vegas_factor = league_avg_implied_total / opponent_implied_total` (a defense benefits when the offense it's facing is expected to score less — the opposite convention from the skill-position `vegas_factor`, which uses the player's own team). No defensive `matchup_factor` exists anywhere upstream, so it's held flat neutral (1.0) — flagged as a real gap a future session could close with real defensive matchup data, not silently fabricated. Full reasoning: `build_projections.py`'s module docstring, decision #5.

Bye-week handling matches the existing decision #4b philosophy exactly: a defense with no row in `vegas_implied_totals_{week}.csv` that week (bye) gets `final_projection` forced to `0.0`, not a neutrally-factored guess. Verified on the real week-10-2025 pool: Dallas (real bye that week) correctly zeroed out; the other 5 real defenses (HOU, CLE, IND, WAS, MIA) got non-neutral vegas-based projections.

**Known caveat, RESOLVED same-day (Session 3.1 addendum):** this session's environment did not initially have `weekly_stats_2025.parquet` or `schedules_2025.parquet` available (both were user-supplied in a prior session and are needed for the SKILL-position pipeline's decision #2/#4 logic, not for DST/DEF). Rather than risk silently regressing the already-validated skill-position numbers (which reflect Session 2.4's addenda 1-3, including the Flacco team-drift/zero-out fix) by re-running the full pipeline without those files, Session 3.1 first computed DST/DEF rows in isolation (they only need the salary file + `vegas_implied_totals_{week}.csv`, confirmed to need no schedule/weekly_stats dependency at all) and merged them into the existing, already-correct `final_projections_{site}_10.csv` files rather than regenerating those files from scratch.

The user then supplied real `weekly_stats_2025.parquet`, `schedules_2025.parquet`, and `weekly_rosters_2025.parquet` the same day, enabling a genuine true full single-pass re-run of `build_projections.py` (skill positions + DST/DEF together, one pass, real decision #4 team-drift correction firing normally -- 41/85 skill players correctly flagged `no_real_game_this_week`, matching Session 2.4's original finding exactly). **Diffed row-for-row against the isolated-merge output: 0 rows differed, max absolute difference in `final_projection` across all 91 players (both sites) was 0.0.** The isolated-merge approach and the true full re-run are confirmed equivalent -- no correction needed, nothing shipped in Session 3.1 needs to change.

## Notes on odds vendor choice (added during Session 2.3)
The Odds API (Session 2.3's chosen vendor) is confirmed sufficient for **NFL-only** scope at the polling cadence in Session 2.3's card: ~121 credits/month against a 500/month free-tier cap, comfortable headroom. This does NOT hold if the roadmap's excluded "MLB expansion" (see Notes on sequencing, above) or any other daily-cadence sport (NBA, NHL) gets un-deferred later — a single additional daily sport at the same polling aggressiveness would push past 500/month on its own, since NFL's weekly single-lock cadence is what keeps usage low, and daily sports lock every day.

Before any future multi-sport session gets built: re-evaluate odds vendors at that time rather than assuming The Odds API's free tier still fits, or defaulting straight to a paid plan without checking. As of Session 2.3 (July 2026), two alternatives surfaced that didn't exist when this roadmap was first written: SharpAPI (claims a 12 req/min rate-limit free tier instead of a monthly credit cap — but as of this writing has no independent reviews or third-party coverage found, only its own marketing site; treat as unverified, not a safe default) and SportsGameOdds (broader book/league coverage, free "Amateur" tier at 2,500 objects/month, somewhat more established-feeling but still not independently verified here). Neither was vetted hands-on. The safest fallback if free-tier math doesn't work at that time is simply upgrading The Odds API to its $30/month 20K-credit tier — trivial cost against the rest of this project, and removes the problem outright rather than optimizing around a thinner polling schedule that risks stale lines near lock.


---

## PHASE 11 — Ownership Model Upgrade
*Opened 2026-07-28. Structured response to the gap assessment comparing the
current heuristic against Tier 1/2/3 ownership model targets defined during
the 2026-07-28 ownership model research session. Phase 10 is complete;
this phase can run in parallel with Phase 6 (preseason dry runs) for the
code work, and in parallel with the regular season for the data-collection
and fitting sessions.*

**Why a new phase, not a revision to Phase 4 or 9:**
Phase 4 (Session 4.1) shipped the correct architecture: value-based softmax,
per-position budgets, estimated_ownership_pct. The problem isn't the
structure -- it's that the parameters are unfit guesses (temperature = 15.0,
weights = 0.45/0.20/0.25, FLEX split = even thirds) and two real ownership
predictors were missing from the feature set. Phase 9 (Sessions 9.3/9.4)
always planned to close the data gap; this phase adds the feature expansion
that makes the eventual retuning worthwhile, and locks in the data schema
before a single real ownership number is logged.

**The gap assessment (full) is in SESSION_LOG.md's Phase 11 entry.**

**Tier definitions (established 2026-07-28):**
- Tier 1: Value-based softmax with parameters fit to real data. Architecture
  already built; gap is unfit constants and two missing features.
- Tier 2: Feature-weighted model (5 inputs) + learning loop retuning.
  Closes once 11.0 ships, real data flows through 9.3, and 11.1 fits.
- Tier 3: Per-contest-type stratification. Requires a full season of
  tagged data before fitting is meaningful.
- Tier 4: Simulation-based field modeling (SaberSim-style). Dropped --
  high effort, marginal benefit for personal-use scale. Not built.

---

### Session 11.0 — Feature Expansion + Schema Prep
**Status:** ✅ Complete (2026-07-28)
**Prerequisites:** Session 4.1 complete (updates ownership_heuristic.py in place).
**Blocking:** Nothing blocked here -- pure code work, no real data needed.

**Files touched (modified):**
- `scripts/ownership_heuristic.py` -- two new features added to chalk_score
  blend, one required input column added, blend weights updated. No existing
  output column changed; no existing feature removed.

**What changed in ownership_heuristic.py:**

*New feature 1 -- raw_projection_percentile (decision #6):*
`final_projection` as a standalone feature, percentile-ranked within
position_group. This is distinct from value (pts/$1K): a player can have a
great raw projection AND poor value (expensive stud), or great value AND a
modest raw projection (cheap punt). Both signals predict ownership
independently. Research finding from the 2026-07-28 session: salary and
projected points together explain ~20-25% of ownership variance vs ~8% for
salary alone. The existing value feature partially captures this but not
fully -- an expensive player with 18 projected points has lower value than a
cheap player with 12 projected points, but the expensive player gets owned
far more heavily on projection ceiling alone. This feature corrects that.

*New feature 2 -- over_under_percentile (decision #7):*
Game-level over/under (O/U) as a separate signal from implied_total.
`over_under` already exists in `final_projections_*.csv` (added in Session
3.3's addendum). Percentile-ranked across the full pool (not
position-grouped), same approach as vegas_percentile. Why separate from
implied_total: a team with implied_total 27 in a 52 O/U game (shootout) has
a very different DFS ownership profile than the same team in a 38 O/U game
(defensive game with one dominant offense), even with identical point
spreads. The O/U captures "shootout game" signal that affects all positions
in the game, including the trailing team's skill positions and the leading
team's DST opponent.

*Updated blend weights (5-feature, all UNFIT starting guesses):*
```
OLD (4-feature, Session 4.1):
  VALUE 0.45 | SALARY_TIER 0.20 | VEGAS 0.25

NEW (5-feature, Session 11.0):
  VALUE 0.35 | PROJECTION 0.15 | SALARY_TIER 0.15 | VEGAS 0.20 | OVER_UNDER 0.15
```
Direction rationale: value drops because raw projection is now separate;
salary_tier drops because value+projection together carry the salary-driven
signal; vegas drops slightly to share with over_under; projection and
over_under are new at 0.15 each. All five weights are retuning targets for
Session 11.1. The module docstring tracks the old weights explicitly for
diff visibility.

*New required input column:*
`load_final_projections()` now requires `over_under` in addition to the
existing required columns. `over_under` has been in `final_projections_*.csv`
since Session 3.3's addendum -- if a file generated before that addendum is
used, this will raise a clear SystemExit with a message explaining which
column is missing and why.

*OWNERSHIP_SOFTMAX_TEMPERATURE unchanged (still 15.0):*
Temperature is fit separately from the blend weights. The 5-feature
expansion doesn't change the right starting point for temperature -- it will
be re-evaluated in Session 11.1 against real data alongside the weights.

**Schema prep for Session 9.3:**
The `ownership_actual_log.csv` schema is defined here so Session 9.3
implements it correctly from day one. See the Session 9.3 card update below.

**Validation:**
- [x] `ownership_heuristic.py` runs without error against the existing
  Madden Sim test data (DK week 10, FD week 10). Output columns unchanged;
  chalk_score and estimated_ownership_pct within expected ranges (0-100,
  no nulls). Verified that `over_under` is present in the test
  `final_projections_*.csv` (it has been since Session 3.3's addendum).
- [x] With `--site dk --week 10`, print output shows 5 feature components
  summing correctly and all players have non-null chalk_score values.
- [x] `estimated_ownership_pct` group totals still match roster-slot budgets
  exactly (the softmax-to-budget logic is unchanged; this is a regression
  check confirming the new features don't disturb it).

**Handoff notes:**
Session 9.3 can now be built against the schema defined in this session's
notes. Session 11.1 cannot be built until Session 9.3 has 4-6 weeks of real
data -- design the script now if desired, but don't fit against fewer than
4 weeks.

---

### Session 9.3 — Actual Ownership Logging *(updated card)*
*Original card added during Session 4.1's addendum. Schema updated by
Session 11.0 (2026-07-28) to include contest_type and field_size, which
are required for Session 11.3's contest-type stratification. Script built
2026-07-29. Session closes on first real end-to-end run (Preseason Week 1).*

**Status: ⚠️ Script built — pending first live run to close.**

**Prerequisites:** Session 8.1 complete (live enough to have real slates
running), AND a real published-ownership source identified for at least one
site/contest type.

**Sites:** Log per site -- DK and FD price the same player differently, so
their real ownership numbers for the same player are never expected to match.

**Files touched (created):**
- `scripts/log_ownership.py` ✅ built 2026-07-29
- `data/ownership_actual_log.csv` (grows weekly)

**Full schema for ownership_actual_log.csv (defined Session 11.0):**
```
site              -- dk | fd
season            -- e.g. 2026
week              -- NFL week number
contest_id        -- platform's own contest identifier, if available
contest_type      -- cash | single_entry_gpp | 3max_gpp
                     (log "unknown" if the contest type can't be determined
                     reliably -- don't guess; bad labels are worse than
                     missing ones for Session 11.3's fit)
field_size        -- number of entries in the logged contest
                     (ownership behavior differs between 100-entry and
                     50,000-entry fields; this is needed to weight or
                     stratify observations in Session 11.1)
player_id         -- nflverse player_id, same scheme as rest of pipeline
player_name       -- for human spot-checking
actual_ownership_pct   -- the real published number (0-100 scale)
estimated_ownership_pct_at_lock  -- what our model predicted at lock time
                                    (from chalk_scores_{site}_{week}.csv)
source            -- where the actual number came from
                     (e.g. "dk_contest_page", "rotogrinders_tracker")
logged_at         -- ISO timestamp of when this row was written
```

**Data source guidance (resolved in this card):**
DraftKings publishes ownership percentages on the contest results page for
large-field GPPs post-lock. This is the most reliable source -- no
third-party dependency, same data the platform uses internally. Recommended
first target: the Millionaire Maker or equivalent large-field single-entry
GPP. For cash games and small-field contests, ownership is often not
published by the platform; log what's available, note the source, and do not
fabricate or estimate entries for contest types that can't be observed.

Third-party trackers (e.g. RotoGrinders' ownership tool for DK large-field
contests) are an acceptable supplementary source when the platform page
itself doesn't expose ownership in a copyable format. Always record the
source in the `source` column.

**Priority order for logging:** large-field DK GPPs first (most reliably
published, largest sample per week, most strategically important). DK cash
and FD ownership second (less reliably published -- log when available, skip
when not, never fabricate).

**Build:**
- ✅ Built 2026-07-29. Two subcommands: `log` (appends rows to
  `ownership_actual_log.csv`) and `summary` (prints current log state
  and data-gate progress without modifying). See SESSION_LOG.md's
  Session 9.3 entry for full design decisions and schema verification.

**Validation:**
- [x] Schema matches Session 11.0's 13-column definition exactly.
- [x] Syntax check passed.
- [x] Duplicate detection, data-gate counter, and unmatched-player logging
      verified by inspection.
- [ ] **End-to-end run against real ownership data** — first opportunity
  Preseason Week 1. Tag those rows `--slate-type preseason` to confirm
  the script works end-to-end. This single checkbox closes the session.
- [ ] Confirm logged actuals match what's published on the contest page for
  a spot-check sample (5+ players across multiple ownership levels).
- [ ] Confirm `estimated_ownership_pct_at_lock` is populated correctly
  from the chalk_scores file for the same week.

---

### Session 9.4 — Ownership Estimate Retuning
*Renamed Session 11.2 in the Phase 11 numbering. This card is kept here for
cross-reference continuity; the authoritative card is Session 11.2 below.*

---

### Session 11.1 — Regression Retuning (Blend Weights + Temperature)
**Prerequisites:** Session 9.3 running for 4-6 weeks minimum. Do not fit
on fewer than 4 weeks -- the model will overfit to noise. The script can
be written before data exists; the fit itself must wait.

**ADDED Session 13.3b (2026-08-05) -- Showdown data gate, separate from
classic's:** Session 13.3b built a real Showdown-specific ownership
heuristic (roster_role-grouped: CPT/MVP vs FLEX), but it's fit on the same
UNFIT starting-guess weights/temperature as classic, since no real
Showdown ownership data exists yet either. This session's scope now
covers retuning BOTH groupings, not just classic's -- but they're gated
independently: classic's 4-6-week data gate above is unaffected and can
still be met on its own schedule, while Showdown's gate cannot even START
until two things happen, neither built yet: (1) real Showdown slates need
to be posting (first chance ~Aug 6, 2026 preseason, Phase 13's trigger
date), AND (2) `log_ownership.py` (Session 9.3) needs an additive
`roster_role` column before it can log Showdown ownership at all -- its
current schema has no way to distinguish a player's CPT-role ownership
from their FLEX-role ownership, which are different real quantities under
13.3b's model. Not built as of 13.3b's close-out -- flagged here so it's
the obvious next step once real Showdown data starts arriving, not
rediscovered cold.

**Data gate:** ~4-6 player-weeks per position × ~50 players per slate =
~200-300 observations minimum before fitting. At 16+ weeks of real data the
fit becomes genuinely stable.

**Sites:** Fit DK and FD separately. The pipeline already enforces this
(ownership_heuristic.py is site-specific); the fit must be too.

**Files touched (created):**
- `scripts/fit_ownership_params.py` -- fits weights and temperature,
  writes artifact. Same fitter/consumer split as Session 10.4b's
  `fit_sigma_recalibration.py` / `sigma_recalibration.py`.
- `data/ownership_params_{site}.json` -- fitted artifact, loaded by
  ownership_heuristic.py when present.

**Files touched (modified):**
- `scripts/ownership_heuristic.py` -- load fitted params from artifact
  when present; fall back to hardcoded defaults with a warning when not.
  Graceful degradation, not a crash. Same pattern as sigma_recalibration.py.

**Method:**
1. For each player-week in `ownership_actual_log.csv`, compute the 5
   feature values (value_percentile, raw_projection_percentile,
   salary_tier_score, vegas_percentile, over_under_percentile) from the
   corresponding week's `final_projections_*.csv`.
2. Fit a log-linear model: `log(actual_ownership_pct + 0.5)` as a linear
   function of the 5 features. Log-linear because ownership is bounded
   0-100 and right-skewed (a few players at 40%+, most at <10%). The +0.5
   floor prevents log(0) on unrostered players.
3. Temperature: grid search from 5.0 to 30.0 in steps of 0.5. For each
   candidate temperature, compute estimated_ownership_pct using that
   temperature and measure MAE against actual_ownership_pct across all
   logged weeks. Pick the value that minimizes MAE.
4. FLEX split: if logged data has enough observations (see Session 11.2),
   do not hardcode here -- defer to 11.2.
5. Holdout validation: fit on weeks 1-N, validate on the most recent 2
   weeks. If validation MAE >= baseline MAE (from the unfit constants),
   do not ship -- investigate.

**Artifact schema (data/ownership_params_{site}.json):**
```json
{
  "schema_version": 1,
  "fit_date": "YYYY-MM-DD",
  "site": "dk",
  "n_weeks": 8,
  "n_observations": 412,
  "temperature": 12.5,
  "weights": {
    "value": 0.31,
    "projection": 0.18,
    "salary_tier": 0.12,
    "vegas": 0.23,
    "over_under": 0.16
  },
  "validation_mae": 4.2,
  "baseline_mae": 6.8,
  "notes": "Fit on weeks 1-6, validated on weeks 7-8."
}
```

**Validation:**
- [ ] Holdout MAE improves over baseline (unfit constants) for both DK and
  FD -- if not, do not ship, investigate.
- [ ] Retuned estimated_ownership_pct still sums to roster-slot budget per
  position group (the softmax-to-budget normalization is unchanged; this
  confirms the new temperature doesn't break the budget constraint).
- [ ] Top-5 most-owned players per position per week (by actual ownership)
  are correctly ranked in the top-5 by estimated_ownership_pct on held-out
  weeks -- rank ordering within position group is more important than
  absolute accuracy for the optimizer's use case.

**Handoff notes:** log the fitted temperature and weights in SESSION_LOG.md.
The gap between fitted and original constants is informative -- a large gap
(e.g. temperature 15.0 fitted to 8.0) means the initial guess was
significantly off and more real data would likely improve the fit further.

---

### Session 11.2 — FLEX Split + Position-Level Temperature Retuning
*(Originally Session 9.4 -- Ownership Estimate Retuning. Renumbered and
scoped more precisely by Phase 11.)*

**Prerequisites:** Session 11.1 complete. Session 9.3 running for 8+
weeks (need enough FLEX position data to split reliably).

**Files touched (modified):**
- `scripts/fit_ownership_params.py` -- extend to fit per-position
  temperature and FLEX usage rates.
- `data/ownership_params_{site}.json` -- extend artifact schema to include
  per-position temperatures and FLEX splits.
- `scripts/ownership_heuristic.py` -- read per-position temperatures from
  artifact if present; fall back to global temperature when not.

**Two specific improvements:**

*FLEX split by real field behavior:*
The current even-thirds FLEX split (RB/WR/TE each get 1/3 of the FLEX
budget) is a known simplification. Real DFS fields fill FLEX with RBs more
often than WRs, and WRs more often than TEs. Logged ownership data reveals
the actual split by checking: across all observed lineups implied by the
ownership percentages, what fraction of FLEX usage goes to each position?
This can be estimated from the logged ownership totals per position relative
to their hard-slot budgets -- the excess above the hard-slot budget is FLEX
usage. Replace the even-thirds split with the observed ratio once enough
data exists.

*Per-position temperatures:*
The global OWNERSHIP_SOFTMAX_TEMPERATURE (currently 15.0, to be refit in
11.1) may not be right for every position. QB ownership in DFS is known to
be more concentrated than RB ownership (there are fewer viable QB options
and they're more consensus). DST ownership is more volatile week to week
than skill positions. Check whether fitting a separate temperature per
position improves MAE on held-out weeks. If yes, ship per-position
temperatures in the artifact. If not (improvement < 0.5 MAE points),
keep the global temperature -- complexity isn't worth it at that margin.

**Validation:**
- [ ] Backtested FLEX-corrected estimated_ownership_pct shows RB/WR/TE
  estimated totals closer to their respective logged actuals than the
  even-thirds baseline, on held-out weeks.
- [ ] Per-position temperature MAE improvement check: only ship per-position
  temperatures if improvement >= 0.5 MAE points vs global temperature.
- [ ] All validation checks from 11.1 still pass after this update.

---

### Session 11.3 — Contest-Type Stratification
**Prerequisites:** Session 9.3 running for one full regular season (17+
weeks) with `contest_type` logged reliably for at least two contest types.
This session cannot be built responsibly before the 2026 regular season
ends. Design the approach now; execute in the 2026-2027 offseason.

**Data gate:** ~16 logged weeks × 50 players per slate × 2 contest types
minimum = ~1,600 observations. Less than this and the per-contest-type
fit is noisier than the global fit and shouldn't be shipped.

**Files touched (modified):**
- `scripts/ownership_heuristic.py` -- add `--contest-type` argument
  (cash | single_entry_gpp | 3max_gpp). When provided, load a
  contest-type-specific fitted artifact if present; fall back to the global
  fit from Session 11.1 with a printed warning when not.
- `scripts/fit_ownership_params.py` -- extend to fit per-contest-type.
- `data/ownership_params_{site}_{contest_type}.json` -- per-contest-type
  artifact files. The global artifact (no contest_type suffix) from Session
  11.1 remains as the fallback.
- `scripts/optimizer.py` -- pass `--contest-type` through from the CLI
  to `ownership_heuristic.py` (four-layer architecture: frontend,
  Cloudflare Worker passthroughKeys, GitHub Actions flag-builder,
  optimizer.py argparse -- all four must be updated).
- Cloudflare Worker `optimizer_api.js` -- add `contest_type` to
  passthroughKeys whitelist.
- `.github/workflows/run_optimizer_dispatch.yml` -- add `contest_type`
  to the flag-builder.
- `dfs_optimizer_frontend/index.html` -- add contest-type selector to the
  Build panel (cash / single-entry GPP / 3-max GPP).

**Why contest-type stratification matters:**
Research finding (Establish The Run, 2026): ownership can swing 15-20
percentage points for the same player between a 3-max field and a
single-entry field of the same size and stakes. Cash-game fields converge
on high-floor players; GPP fields spread out more and chase upside.
A single ownership model predicts neither well at the extremes.

**Validation:**
- [ ] For each contest type with 8+ held-out weeks of logged data,
  per-contest-type MAE improves over the global model's MAE on those same
  weeks -- if not, don't ship per-type params for that contest type;
  fall back to global.
- [ ] The four-layer architecture update (frontend → Worker → Actions →
  optimizer.py) is confirmed end-to-end: setting a contest type in the
  UI produces a lineup built with the correct type-specific ownership
  estimate, not the global fallback.

---

## Summary: Phase 11 sequencing

| Session | What | When | Tier closed |
|---|---|---|---|
| 11.0 ✅ | Feature expansion + schema def | Pre-season (done) | Tier 2 setup |
| 9.3 ⚠️ | Ownership logging — script built, first live run pending | Preseason Week 1 | Data foundation |
| 11.1 | Regress weights + temperature on real data | ~Week 6-7 | Tier 1 + Tier 2 |
| 11.2 | FLEX split + per-position temperatures | ~Week 8+ | Tier 2 refinement |
| 11.3 | Per-contest-type stratification | Post-season 2026 | Tier 3 |

---

## PHASE 11 — Ownership Model Upgrade
*Opened 2026-07-28. Structured response to the gap assessment comparing the
current heuristic against Tier 1/2/3 ownership model targets defined during
the 2026-07-28 ownership model research session. Phase 10 is complete;
this phase can run in parallel with Phase 6 (preseason dry runs) for the
code work, and in parallel with the regular season for the data-collection
and fitting sessions.*

**Why a new phase, not a revision to Phase 4 or 9:**
Phase 4 (Session 4.1) shipped the correct architecture: value-based softmax,
per-position budgets, estimated_ownership_pct. The problem isn't the
structure -- it's that the parameters are unfit guesses (temperature = 15.0,
weights = 0.45/0.20/0.25, FLEX split = even thirds) and two real ownership
predictors were missing from the feature set. Phase 9 (Sessions 9.3/9.4)
always planned to close the data gap; this phase adds the feature expansion
that makes the eventual retuning worthwhile, and locks in the data schema
before a single real ownership number is logged.

**The gap assessment (full) is in SESSION_LOG.md's Phase 11 entry.**

**Tier definitions (established 2026-07-28):**
- Tier 1: Value-based softmax with parameters fit to real data. Architecture
  already built; gap is unfit constants and two missing features.
- Tier 2: Feature-weighted model (5 inputs) + learning loop retuning.
  Closes once 11.0 ships, real data flows through 9.3, and 11.1 fits.
- Tier 3: Per-contest-type stratification. Requires a full season of
  tagged data before fitting is meaningful.
- Tier 4: Simulation-based field modeling (SaberSim-style). Dropped --
  high effort, marginal benefit for personal-use scale. Not built.

---

### Session 11.0 — Feature Expansion + Schema Prep
**Status:** ✅ Complete (2026-07-28)
**Prerequisites:** Session 4.1 complete (updates ownership_heuristic.py in place).
**Blocking:** Nothing blocked here -- pure code work, no real data needed.

**Files touched (modified):**
- `scripts/ownership_heuristic.py` -- two new features added to chalk_score
  blend, one required input column added, blend weights updated. No existing
  output column changed; no existing feature removed.

**What changed in ownership_heuristic.py:**

*New feature 1 -- raw_projection_percentile (decision #6):*
`final_projection` as a standalone feature, percentile-ranked within
position_group. This is distinct from value (pts/$1K): a player can have a
great raw projection AND poor value (expensive stud), or great value AND a
modest raw projection (cheap punt). Both signals predict ownership
independently. Research finding from the 2026-07-28 session: salary and
projected points together explain ~20-25% of ownership variance vs ~8% for
salary alone. The existing value feature partially captures this but not
fully -- an expensive player with 18 projected points has lower value than a
cheap player with 12 projected points, but the expensive player gets owned
far more heavily on projection ceiling alone. This feature corrects that.

*New feature 2 -- over_under_percentile (decision #7):*
Game-level over/under (O/U) as a separate signal from implied_total.
`over_under` already exists in `final_projections_*.csv` (added in Session
3.3's addendum). Percentile-ranked across the full pool (not
position-grouped), same approach as vegas_percentile. Why separate from
implied_total: a team with implied_total 27 in a 52 O/U game (shootout) has
a very different DFS ownership profile than the same team in a 38 O/U game
(defensive game with one dominant offense), even with identical point
spreads. The O/U captures "shootout game" signal that affects all positions
in the game, including the trailing team's skill positions and the leading
team's DST opponent.

*Updated blend weights (5-feature, all UNFIT starting guesses):*
```
OLD (4-feature, Session 4.1):
  VALUE 0.45 | SALARY_TIER 0.20 | VEGAS 0.25

NEW (5-feature, Session 11.0):
  VALUE 0.35 | PROJECTION 0.15 | SALARY_TIER 0.15 | VEGAS 0.20 | OVER_UNDER 0.15
```
Direction rationale: value drops because raw projection is now separate;
salary_tier drops because value+projection together carry the salary-driven
signal; vegas drops slightly to share with over_under; projection and
over_under are new at 0.15 each. All five weights are retuning targets for
Session 11.1. The module docstring tracks the old weights explicitly for
diff visibility.

*New required input column:*
`load_final_projections()` now requires `over_under` in addition to the
existing required columns. `over_under` has been in `final_projections_*.csv`
since Session 3.3's addendum -- if a file generated before that addendum is
used, this will raise a clear SystemExit with a message explaining which
column is missing and why.

*OWNERSHIP_SOFTMAX_TEMPERATURE unchanged (still 15.0):*
Temperature is fit separately from the blend weights. The 5-feature
expansion doesn't change the right starting point for temperature -- it will
be re-evaluated in Session 11.1 against real data alongside the weights.

**Schema prep for Session 9.3:**
The `ownership_actual_log.csv` schema is defined here so Session 9.3
implements it correctly from day one. See the Session 9.3 card update below.

**Validation:**
- [x] `ownership_heuristic.py` runs without error against the existing
  Madden Sim test data (DK week 10, FD week 10). Output columns unchanged;
  chalk_score and estimated_ownership_pct within expected ranges (0-100,
  no nulls). Verified that `over_under` is present in the test
  `final_projections_*.csv` (it has been since Session 3.3's addendum).
- [x] With `--site dk --week 10`, print output shows 5 feature components
  summing correctly and all players have non-null chalk_score values.
- [x] `estimated_ownership_pct` group totals still match roster-slot budgets
  exactly (the softmax-to-budget logic is unchanged; this is a regression
  check confirming the new features don't disturb it).

**Handoff notes:**
Session 9.3 can now be built against the schema defined in this session's
notes. Session 11.1 cannot be built until Session 9.3 has 4-6 weeks of real
data -- design the script now if desired, but don't fit against fewer than
4 weeks.

---

### Session 9.3 — Actual Ownership Logging *(updated card)*
*Original card added during Session 4.1's addendum. Schema updated by
Session 11.0 (2026-07-28) to include contest_type and field_size, which
are required for Session 11.3's contest-type stratification. Schema further
updated (2026-07-28) to add slate_type, which is required to correctly
exclude preseason and Madden Sim data from Session 11.1's fit. The original
card's build intent and prerequisites are unchanged.*

**Prerequisites:** Session 8.1 complete (live enough to have real slates
running), AND a real published-ownership source identified for at least one
site/contest type.

**Sites:** Log per site -- DK and FD price the same player differently, so
their real ownership numbers for the same player are never expected to match.

**Files touched (created):**
- `scripts/log_ownership.py`
- `data/ownership_actual_log.csv` (grows weekly)

**Full schema for ownership_actual_log.csv (defined Session 11.0, slate_type added 2026-07-28):**
```
site              -- dk | fd
season            -- e.g. 2026
week              -- NFL week number
slate_type        -- regular_season | preseason | madden_sim
                     CRITICAL: Session 11.1 fits on regular_season only.
                     Preseason and Madden Sim data is logged (useful for
                     pipeline validation and dry runs) but excluded from
                     the weight/temperature fit. Do NOT omit this column
                     or log everything as regular_season -- bad labels
                     here corrupt the fit in a way that's hard to detect.
contest_id        -- platform's own contest identifier, if available
contest_type      -- cash | single_entry_gpp | 3max_gpp
                     (log "unknown" if the contest type can't be determined
                     reliably -- don't guess; bad labels are worse than
                     missing ones for Session 11.3's fit)
field_size        -- number of entries in the logged contest
                     (ownership behavior differs between 100-entry and
                     50,000-entry fields; this is needed to weight or
                     stratify observations in Session 11.1)
player_id         -- nflverse player_id, same scheme as rest of pipeline
player_name       -- for human spot-checking
actual_ownership_pct   -- the real published number (0-100 scale)
estimated_ownership_pct_at_lock  -- what our model predicted at lock time
                                    (from chalk_scores_{site}_{week}.csv)
source            -- where the actual number came from
                     (e.g. "dk_contest_page", "rotogrinders_tracker")
logged_at         -- ISO timestamp of when this row was written
```

**Data source guidance (resolved in this card):**
DraftKings publishes ownership percentages on the contest results page for
large-field GPPs post-lock. This is the most reliable source -- no
third-party dependency, same data the platform uses internally. Recommended
first target: the Millionaire Maker or equivalent large-field single-entry
GPP. For cash games and small-field contests, ownership is often not
published by the platform; log what's available, note the source, and do not
fabricate or estimate entries for contest types that can't be observed.

Third-party trackers (e.g. RotoGrinders' ownership tool for DK large-field
contests) are an acceptable supplementary source when the platform page
itself doesn't expose ownership in a copyable format. Always record the
source in the `source` column.

**Priority order for logging:** large-field DK GPPs first (most reliably
published, largest sample per week, most strategically important). DK cash
and FD ownership second (less reliably published -- log when available, skip
when not, never fabricate).

**Preseason logging guidance:**
Log preseason ownership data with `slate_type = preseason`. Preseason data
is real human behavior in a real DFS contest and is useful for two things:
validating that the logging script and schema work correctly before the
regular season, and dry-running the full Session 9.3 workflow. However,
preseason ownership must NOT be used to fit Session 11.1's weights or
temperature for two reasons: (1) starters play 1-2 series max, so the
player pool and role structure look nothing like the regular season, and
DK/FD salary pricing is experimental with very little signal; (2) the
preseason DFS field is almost entirely hardcore grinders, not the casual
majority that dominates a 50,000-entry regular season GPP. The ownership
behavior is systematically different and would teach the model the wrong
things. Log it, tag it, but exclude it from the fit.

**Madden Sim logging guidance:**
Log Madden Sim ownership data with `slate_type = madden_sim`. Same
exclusion from Session 11.1's fit applies, and more strongly: Madden Sim
ownership reflects a tiny self-selected grinder population with no
real-world narrative, injury, or recency-bias signals driving it. It is
useful solely for pipeline validation (confirming log_ownership.py runs
correctly end-to-end), not for any ownership model calibration.

**Build:**
- ✅ Built 2026-07-29. Two subcommands: `log` (appends rows to
  `ownership_actual_log.csv`) and `summary` (prints current log state
  and data-gate progress without modifying). See SESSION_LOG.md's
  Session 9.3 entry for full design decisions and schema verification.

**Validation:**
- [x] Schema matches Session 11.0's 13-column definition exactly.
- [x] Syntax check passed.
- [x] Duplicate detection, data-gate counter, and unmatched-player logging
      verified by inspection.
- [ ] **End-to-end run against real ownership data** — first opportunity
  Preseason Week 1. Tag those rows `--slate-type preseason` to confirm
  the script works end-to-end. This single checkbox closes the session.
- [ ] Confirm logged actuals match what's published on the contest page for
  a spot-check sample (5+ players across multiple ownership levels).
- [ ] Confirm `estimated_ownership_pct_at_lock` is populated correctly
  from the chalk_scores file for the same week.

---

### Session 9.4 — Ownership Estimate Retuning
*Renamed Session 11.2 in the Phase 11 numbering. This card is kept here for
cross-reference continuity; the authoritative card is Session 11.2 below.*

---

### Session 11.1 — Regression Retuning (Blend Weights + Temperature)
**Prerequisites:** Session 9.3 running for 4-6 regular-season weeks minimum.
Do not fit on fewer than 4 regular-season weeks -- the model will overfit to
noise. Preseason and Madden Sim rows in `ownership_actual_log.csv` are
excluded from the fit by filtering on `slate_type == "regular_season"`.
The script can be written before data exists; the fit itself must wait.

**Data gate:** ~4-6 regular-season weeks × ~50 players per slate =
~200-300 observations minimum before fitting. At 16+ weeks the fit becomes
genuinely stable. Preseason and Madden Sim rows do not count toward this
gate -- they are excluded from the fit by the slate_type filter.

**Sites:** Fit DK and FD separately. The pipeline already enforces this
(ownership_heuristic.py is site-specific); the fit must be too.

**Files touched (created):**
- `scripts/fit_ownership_params.py` -- fits weights and temperature,
  writes artifact. Same fitter/consumer split as Session 10.4b's
  `fit_sigma_recalibration.py` / `sigma_recalibration.py`.
- `data/ownership_params_{site}.json` -- fitted artifact, loaded by
  ownership_heuristic.py when present.

**Files touched (modified):**
- `scripts/ownership_heuristic.py` -- load fitted params from artifact
  when present; fall back to hardcoded defaults with a warning when not.
  Graceful degradation, not a crash. Same pattern as sigma_recalibration.py.

**Method:**
1. Filter `ownership_actual_log.csv` to `slate_type == "regular_season"`
   only. For each remaining player-week, compute the 5 feature values
   (value_percentile, raw_projection_percentile, salary_tier_score,
   vegas_percentile, over_under_percentile) from the corresponding week's
   `final_projections_*.csv`.
2. Fit a log-linear model: `log(actual_ownership_pct + 0.5)` as a linear
   function of the 5 features. Log-linear because ownership is bounded
   0-100 and right-skewed (a few players at 40%+, most at <10%). The +0.5
   floor prevents log(0) on unrostered players.
3. Temperature: grid search from 5.0 to 30.0 in steps of 0.5. For each
   candidate temperature, compute estimated_ownership_pct using that
   temperature and measure MAE against actual_ownership_pct across all
   logged weeks. Pick the value that minimizes MAE.
4. FLEX split: if logged data has enough observations (see Session 11.2),
   do not hardcode here -- defer to 11.2.
5. Holdout validation: fit on weeks 1-N, validate on the most recent 2
   weeks. If validation MAE >= baseline MAE (from the unfit constants),
   do not ship -- investigate.

**Artifact schema (data/ownership_params_{site}.json):**
```json
{
  "schema_version": 1,
  "fit_date": "YYYY-MM-DD",
  "site": "dk",
  "n_weeks": 8,
  "n_observations": 412,
  "temperature": 12.5,
  "weights": {
    "value": 0.31,
    "projection": 0.18,
    "salary_tier": 0.12,
    "vegas": 0.23,
    "over_under": 0.16
  },
  "validation_mae": 4.2,
  "baseline_mae": 6.8,
  "notes": "Fit on weeks 1-6, validated on weeks 7-8."
}
```

**Validation:**
- [ ] Holdout MAE improves over baseline (unfit constants) for both DK and
  FD -- if not, do not ship, investigate.
- [ ] Retuned estimated_ownership_pct still sums to roster-slot budget per
  position group (the softmax-to-budget normalization is unchanged; this
  confirms the new temperature doesn't break the budget constraint).
- [ ] Top-5 most-owned players per position per week (by actual ownership)
  are correctly ranked in the top-5 by estimated_ownership_pct on held-out
  weeks -- rank ordering within position group is more important than
  absolute accuracy for the optimizer's use case.

**Handoff notes:** log the fitted temperature and weights in SESSION_LOG.md.
The gap between fitted and original constants is informative -- a large gap
(e.g. temperature 15.0 fitted to 8.0) means the initial guess was
significantly off and more real data would likely improve the fit further.

---

### Session 11.2 — FLEX Split + Position-Level Temperature Retuning
*(Originally Session 9.4 -- Ownership Estimate Retuning. Renumbered and
scoped more precisely by Phase 11.)*

**Prerequisites:** Session 11.1 complete. Session 9.3 running for 8+
weeks (need enough FLEX position data to split reliably).

**Files touched (modified):**
- `scripts/fit_ownership_params.py` -- extend to fit per-position
  temperature and FLEX usage rates.
- `data/ownership_params_{site}.json` -- extend artifact schema to include
  per-position temperatures and FLEX splits.
- `scripts/ownership_heuristic.py` -- read per-position temperatures from
  artifact if present; fall back to global temperature when not.

**Two specific improvements:**

*FLEX split by real field behavior:*
The current even-thirds FLEX split (RB/WR/TE each get 1/3 of the FLEX
budget) is a known simplification. Real DFS fields fill FLEX with RBs more
often than WRs, and WRs more often than TEs. Logged ownership data reveals
the actual split by checking: across all observed lineups implied by the
ownership percentages, what fraction of FLEX usage goes to each position?
This can be estimated from the logged ownership totals per position relative
to their hard-slot budgets -- the excess above the hard-slot budget is FLEX
usage. Replace the even-thirds split with the observed ratio once enough
data exists.

*Per-position temperatures:*
The global OWNERSHIP_SOFTMAX_TEMPERATURE (currently 15.0, to be refit in
11.1) may not be right for every position. QB ownership in DFS is known to
be more concentrated than RB ownership (there are fewer viable QB options
and they're more consensus). DST ownership is more volatile week to week
than skill positions. Check whether fitting a separate temperature per
position improves MAE on held-out weeks. If yes, ship per-position
temperatures in the artifact. If not (improvement < 0.5 MAE points),
keep the global temperature -- complexity isn't worth it at that margin.

**Validation:**
- [ ] Backtested FLEX-corrected estimated_ownership_pct shows RB/WR/TE
  estimated totals closer to their respective logged actuals than the
  even-thirds baseline, on held-out weeks.
- [ ] Per-position temperature MAE improvement check: only ship per-position
  temperatures if improvement >= 0.5 MAE points vs global temperature.
- [ ] All validation checks from 11.1 still pass after this update.

---

### Session 11.3 — Contest-Type Stratification
**Prerequisites:** Session 9.3 running for one full regular season (17+
weeks) with `contest_type` logged reliably for at least two contest types.
This session cannot be built responsibly before the 2026 regular season
ends. Design the approach now; execute in the 2026-2027 offseason.

**Data gate:** ~16 logged weeks × 50 players per slate × 2 contest types
minimum = ~1,600 observations. Less than this and the per-contest-type
fit is noisier than the global fit and shouldn't be shipped.

**Files touched (modified):**
- `scripts/ownership_heuristic.py` -- add `--contest-type` argument
  (cash | single_entry_gpp | 3max_gpp). When provided, load a
  contest-type-specific fitted artifact if present; fall back to the global
  fit from Session 11.1 with a printed warning when not.
- `scripts/fit_ownership_params.py` -- extend to fit per-contest-type.
- `data/ownership_params_{site}_{contest_type}.json` -- per-contest-type
  artifact files. The global artifact (no contest_type suffix) from Session
  11.1 remains as the fallback.
- `scripts/optimizer.py` -- pass `--contest-type` through from the CLI
  to `ownership_heuristic.py` (four-layer architecture: frontend,
  Cloudflare Worker passthroughKeys, GitHub Actions flag-builder,
  optimizer.py argparse -- all four must be updated).
- Cloudflare Worker `optimizer_api.js` -- add `contest_type` to
  passthroughKeys whitelist.
- `.github/workflows/run_optimizer_dispatch.yml` -- add `contest_type`
  to the flag-builder.
- `dfs_optimizer_frontend/index.html` -- add contest-type selector to the
  Build panel (cash / single-entry GPP / 3-max GPP).

**Why contest-type stratification matters:**
Research finding (Establish The Run, 2026): ownership can swing 15-20
percentage points for the same player between a 3-max field and a
single-entry field of the same size and stakes. Cash-game fields converge
on high-floor players; GPP fields spread out more and chase upside.
A single ownership model predicts neither well at the extremes.

**Validation:**
- [ ] For each contest type with 8+ held-out weeks of logged data,
  per-contest-type MAE improves over the global model's MAE on those same
  weeks -- if not, don't ship per-type params for that contest type;
  fall back to global.
- [ ] The four-layer architecture update (frontend → Worker → Actions →
  optimizer.py) is confirmed end-to-end: setting a contest type in the
  UI produces a lineup built with the correct type-specific ownership
  estimate, not the global fallback.

---

## Summary: Phase 11 sequencing

| Session | What | When | Tier closed |
|---|---|---|---|
| 11.0 ✅ | Feature expansion + schema def | Pre-season (done) | Tier 2 setup |
| 9.3 ⚠️ | Ownership logging — script built, first live run pending | Preseason Week 1 | Data foundation |
| 11.1 | Regress weights + temperature on real data | ~Week 6-7 | Tier 1 + Tier 2 |
| 11.2 | FLEX split + per-position temperatures | ~Week 8+ | Tier 2 refinement |
| 11.3 | Per-contest-type stratification | Post-season 2026 | Tier 3 |

---

## PHASE 12 — Optimizer Constraint Enhancements

### Session 12.1 — Team / Game Exposure Caps
**Prerequisites:** Session 7.3 complete (FLEX eligibility / lock-exclude patterns this session's feasibility check mirrors).

**Status:** ✅ Complete (2026-08-01) — see SESSION_LOG.md for full detail.

**Files touched (modified):**
- `scripts/optimizer.py`
- `cloudflare_worker/optimizer_api/optimizer_api.js`
- `.github/workflows/run_optimizer_dispatch.yml`
- `dfs_optimizer_frontend/index.html`

**Build:**
- `--max-team-players TEAM:N[,TEAM:N...]` — hard cap on players from a specific team.
- `--max-game-players TEAM-TEAM:N[,TEAM-TEAM:N...]` — hard cap on combined players from both teams in a specific game.
- Both additive alongside existing stacking minimums (Session 3.3) — contradictions surface as normal solver infeasibility, not a special-cased error.
- Pre-solve feasibility check: a locked player that already exceeds a requested cap fails loudly with a specific reason before the solver runs, matching `validate_lock_feasibility()`'s existing pattern (decision #24).
- Frontend: team/game pickers sourced from the loaded slate (same pattern as the existing stack-team/stack-game chip pickers), each paired with a cap-value input, rendered as removable chips.

**Validation:**
- [x] Synthetic-pool unit tests (team cap, game cap, combined, locked-player conflict, parser correctness)
- [x] `optimizer.py` full-file compile check
- [x] `optimizer_api.js` Node syntax check
- [x] `run_optimizer_dispatch.yml` YAML parse check
- [x] `index.html` extracted-script Node syntax check + `getElementById`/`id=` cross-reference
- [x] Worker deployed, all files pushed
- [x] Real-slate live test: team cap + game cap both respected in an actual build
- [x] Real-slate live test: over-limit lock correctly fails the build with a clear reason

**Handoff notes:** Deferred (not requested, not needed): a "global default game cap" that applies to every game not explicitly overridden. Would be a small addition if wanted later — see SESSION_LOG.md Session 12.1 handoff notes.

---

## PHASE 13 — Showdown / Single-Game Slate Support

**Trigger:** Real preseason Showdown-format slates begin posting on both
DK and FD starting Thursday preseason games (~Aug 6, 2026). This phase adds
support for DK's Captain Mode and FD's Single Game format, both sites,
built on top of the existing classic-slate pipeline rather than as a
parallel project.

**Confirmed rules (verified against current site documentation, Session
13.0 scoping conversation; FD's MVP salary rule CORRECTED in Session 13.2
against a live FD roster builder -- the original text below was wrong,
struck through and replaced):**
- **DK Captain Mode:** 6 roster spots — 1 CPT + 5 FLEX. Any position
  eligible in any spot, including K (kickers are NOT currently modeled
  anywhere in this pipeline — see Session 13.1). CPT scores 1.5x fantasy
  points AND costs 1.5x the FLEX-listed salary. Minimum 1 player from each
  team. Salary cap unchanged at $50,000. Both the CPT and FLEX-priced
  version of each player appear as separate rows in DK's Showdown export.
  Re-confirmed in Session 13.2 against a real live 08/06/2026 CAR@ARI
  export (CPT $11,400 / FLEX $7,600 = 1.5x exactly) and a live DK roster
  builder screenshot.
- **FD Single Game:** 5 roster spots — 1 MVP + 4 FLEX. Any position
  eligible in any spot, including K. MVP scores 1.5x fantasy points ~~at
  the SAME salary as FLEX (no cost multiplier — this is a real mechanical
  difference from DK, not a simplification)~~ **AND costs 1.5x the
  FLEX-listed salary, same mechanic as DK's CPT — CORRECTED in Session
  13.2.** The "no cost multiplier" claim above was wrong: a live FD Single
  Game roster builder (same 08/06/2026 CAR@ARI slate) showed MVP $12,000 +
  5 FLEX x $8,000 = $52,000 of the $60,000 cap, leaving exactly $8,000
  remaining, matching the live "Salary Remaining" readout exactly. Minimum
  1 player from each team. Salary cap unchanged at $60,000.
- Both sites: exactly 2 teams in the pool (the single game), so
  cross-game constraints (Session 12.1's game caps, opponent-lookup logic
  in stacking) either don't apply or need reinterpretation — see Session
  13.4.

**Why this is multiple sessions, not one:** Showdown isn't a parameter
change on the classic pipeline — it changes the salary-export shape
(Session 13.2), requires a scoring layer that doesn't exist yet for an
entire position (Session 13.1 — kickers), replaces the core ILP's
fixed-position-count assumption with a totally different roster-construction
model (Session 13.4, the highest-risk piece), and touches the same
four-layer wiring (optimizer.py / Worker / Actions / frontend) every prior
cross-cutting feature in this project has required (Session 13.5). Per this
project's own validation discipline (a session isn't done until its
validation step passes on real or synthetic data), these don't compress
into one sitting without skipping steps that have caught real bugs before
(see Session 4.3's pattern of finding bugs only by running real data).

**Sequencing note:** Session 13.1 (kicker model) has no Showdown-specific
dependency and could in principle run any time — it's needed here because
Showdown pools always include kickers and none exist in the pipeline today.
Sessions 13.2-13.5 are sequential (each depends on the prior). Session 13.6
(real-slate validation) is gated on both a real slate AND 13.1-13.5 being
functionally complete on synthetic data first — if the Thursday slate
arrives before 13.1-13.5 are done, it can still serve as the real-data
validation input for whichever of those sessions ARE ready by then, with
the rest validated later against the next available Showdown slate.

---

### Session 13.1 — Kicker Projection Model
**Prerequisites:** None (independent of Showdown-specific work; needed
because no kicker model exists anywhere in the current pipeline).

**Sites:** Both — kicker scoring differs slightly by site (see Build).

**Files touched (created):**
- `scripts/kicker_model.py` (new — consumer script, same fitter/consumer
  split discipline as `dst_model.py`/`fit_dst_model.py`)
- `scripts/fit_kicker_model.py` (new — fits FG-distance-bucket make rates
  and PAT rates to real historical data, separate from the consumer per
  this project's established principle)

**Files touched (modified):**
- `scripts/scoring_rules.py` — add `score_kicker()` and `kicker_scoring_for(site)`,
  mirroring the existing `score_statline()`/`scoring_for()` and
  `score_dst()`/`dst_scoring_for()` pairs. DK/FD both score PAT (1 pt) and
  FG by distance bracket (0-39/40-49/50+) — confirm exact bracket point
  values for both sites against current official rules before fitting,
  since minor site differences here would silently bias the model.
- `scripts/build_projections.py` — wire kicker projections into the main
  output alongside skill-position and DST projections.

**Inputs:** `data/weekly_stats_{season}.parquet` (nflverse kicking stats —
FGA/FGM by distance, XPA/XPM), Vegas implied team totals (existing
`vegas_odds.py` output, reused as the team-scoring-context signal the same
way DST's model uses it).

**Outputs:** `output/kicker_projections_{site}_{slate_id}.csv` — columns:
player_id, team, projected_points, sigma (if a distributional approach is
used, matching DST's Monte Carlo pattern rather than a point estimate —
decide during build whether kicker variance is worth modeling explicitly
or if a simpler point-estimate is sufficient given kickers' low DFS
salary/impact ceiling relative to skill positions).

**Build:**
- Historical FG-make-rate by distance bucket, PAT-make rate (both very
  high and stable — mostly a volume question, not an accuracy question)
- Volume driver: team scoring context (red-zone trips proxy via Vegas
  implied team total, similar to how `dst_model.py` already uses
  opponent-implied totals) — a kicker's expected points is mostly "how
  many scoring drives end in a FG vs TD for this team this week," which
  ties back to existing Vegas infrastructure, not a from-scratch signal.
- FLAGGED ARBITRARY: any bucket-boundary or weighting constant chosen
  without real-data fitting, same discipline as every other model in this
  project.

**Validation:**
- [ ] Backtest against real historical kicker actuals (RotoGuru or
  nflverse), MAE/RMSE reported the same way Session 10.4's DST rebuild
  reported its numbers, so kicker model quality is comparable/trackable
  alongside the other position models.
- [ ] Spot-check 5 known kickers' projections against hand expectations.
- [ ] `scoring_rules.py`'s new `score_kicker()` verified against real
  nflverse kicking stats for both DK and FD point values (decision #1's
  technique, reused).

**Handoff notes to log:** Final chosen FG-bracket point values for DK and
FD (confirm against current site rules, not memory — kicker scoring
occasionally changes). Whether variance/sigma was modeled or a simpler
point estimate was used, and why.

---

### Session 13.2 — Showdown / Single-Game Salary Ingest ✅ Complete (2026-08-04)
**Prerequisites:** None (independent of Session 13.1; can run in parallel
if needed, though sequential is fine too).

**Outcome in one line:** shipped against REAL exports for BOTH sites
(user supplied live 08/06/2026 CAR@ARI DK Showdown and FD Single Game
files this session, not just synthetic) -- 100% match on both (126/126 DK
rows, 122/122 FD rows post-expansion). Two premises in this card measured
FALSE against real data: FD does NOT duplicate rows like DK (one row per
player, two salary columns on it), and the Phase 13 intro's "FD MVP costs
the same as FLEX" rule was wrong (corrected above -- MVP costs 1.5x, same
as DK's CPT, confirmed via a live FD roster builder). Full detail in
SESSION_LOG.md's Session 13.2 entry.

**Sites:** DraftKings AND FanDuel — both required, same dual-site
discipline as Session 1.3.

**Files touched (modified):**
- `scripts/ingest_salaries.py` — add Showdown/Single-Game entries to
  `SITE_CONFIGS` (or a `slate_format` dimension crossing site ×
  {classic, showdown} — decide the cleanest structure during build,
  likely `SITE_CONFIGS[site][format]` nesting to avoid duplicating the
  team-abbreviation/name-matching logic that's shared across formats).
  Core new parsing need: both sites' Showdown exports list each player
  TWICE — once as CPT/MVP-priced, once as FLEX-priced — a different shape
  than `_load_dk_raw()`/the FD loader handle today. The CPT/MVP row and
  FLEX row for the same underlying player need to be linked (shared
  player_id, distinct salary/role) rather than treated as two unrelated
  players. **CORRECTION (measured against a real file): this "list each
  player TWICE" premise is FALSE for FD — see SESSION_LOG.md.** Shipped as
  `SITE_CONFIGS[site]["showdown"]` nesting (not a full `[site][format]`
  restructure — 9 other scripts read the flat classic structure).
- `scripts/generate_synthetic_slate.py` — add a Showdown-shaped output
  mode for both sites, since real Showdown exports may not be available
  for every dev iteration (same rationale as the existing synthetic-slate
  tool: FD in particular has no reliable free-to-generate real test data).

**Inputs:** Manually downloaded DK Showdown / FD Single Game salary CSV
exports (place in `/data/raw_salaries/`, same convention as classic).

**Outputs:** `data/salaries_{site}_{slate_id}.csv`, same shape as classic
output plus a `roster_role` column (shipped instead of `cpt_eligible`/
`is_captain_row` — carries the raw site label directly: "CPT"/"FLEX" for
DK, "MVP"/"FLEX" for FD) distinguishing the two rows per player, plus a
`slate_format` column ("classic"/"showdown") on every row.

**Build:**
- Site-specific Showdown/Single-Game column parsing.
- Link CPT/MVP row to FLEX row for the same player (needed downstream so
  the optimizer can enforce "can't roster both versions of the same
  player" — Session 13.4).
- Confirm real DK Showdown column layout against a real export (DK has
  live Madden Sim-style test data available same as classic). **DONE —
  DK's `Position` column retains the TRUE player position on both CPT and
  FLEX rows (not overwritten), so the existing classic matching pipeline
  worked unchanged for DK.** FD Single Game export shape — **DONE, real
  file supplied this session (upgrade over the card's synthetic-only
  expectation).**

**Validation:**
- [x] 100% of players in a real DK Showdown sample file match correctly,
  CPT/FLEX rows correctly linked to the same player_id. (126/126, real
  08/06/2026 CAR@ARI file.)
- [x] Synthetic FD Showdown file round-trips through the same linking
  logic — done, AND validated against a real FD file this session too
  (122/122, upgrade over the card's original "real FD data in 13.6"
  expectation).
- [x] Unmatched players logged clearly, not silently dropped (same bar as
  Session 1.3). 0 unmatched on both real files.

**Handoff notes:** Session 13.3 can treat both sites' cap math and scoring
math as identical (1.5x salary AND 1.5x points for the captain-equivalent
slot) — no remaining ambiguity. See SESSION_LOG.md for the full list of
new columns and deferred/flagged items (`PLAYERS_PER_TEAM_SHOWDOWN`,
`SALARY_BANDS["K"]` in the synthetic generator).

---

### Session 13.3 — Showdown Projection & Scoring-Multiplier Layer ✅ Complete (2026-08-05)
**Prerequisites:** Session 13.1 complete (kicker projections exist to
feed the pool). Session 13.2 complete (CPT/MVP-linked salary data exists).

**Outcome in one line:** CPT/MVP projections derive as an exact 1.5x
multiplier on the linked FLEX-priced player's projection (verified 41/41
exact match, both sites, synthetic pool spanning QB/RB/WR/TE/DST/K). The
ownership question below was originally punted (NaN placeholder) and then
resolved for real in Session 13.3b immediately after -- see that card.
Full detail in SESSION_LOG.md's Session 13.3 entry.

**Files touched (modified):**
- `scripts/build_projections.py` — derive CPT/MVP row projections from
  the linked FLEX-priced player's projection: DK CPT = 1.5x points (salary
  already 1.5x from the raw export, nothing to do there); FD MVP = 1.5x
  points at unchanged salary. Applies uniformly across whatever
  position/model produced the FLEX projection (skill-position stat-line
  model, DST model, or the new Session 13.1 kicker model) — no
  per-position special-casing needed here, just a multiplier applied
  post-hoc to whichever projection already exists for that player.

**Explicit decision to make and log:** Ownership modeling (Phase 11) is
fit entirely on classic-slate position groups and CPT selection behaves
very differently from FLEX selection (concentration effects the current
softmax model has never seen). Recommend `chalk_score`/
`estimated_ownership_pct` are either omitted or clearly marked
"unavailable — Showdown" in Showdown output, rather than silently
returning a classic-fit number that would mislead the pivot-finder /
frontend chalk display. Get explicit sign-off on this rather than assuming.
**RESOLVED (Session 13.3b, same day): the user flagged that ownership/pivot
signal is a stated priority for Showdown, not something to leave
unaddressed. The NaN placeholder below was replaced with a real
roster_role-grouped ownership heuristic -- see Session 13.3b's card
immediately following this one.**

**Validation:**
- [x] CPT/MVP projection = 1.5x the linked FLEX projection, verified for
  a sample of players across all position types (including K and DST/DEF,
  which are Showdown-eligible unlike classic). 41/41 DK, 41/41 FD, exact
  match to 4+ decimals on a synthetic Showdown pool built from real
  nflverse player data.
- [x] Ownership/chalk fields confirmed absent or clearly flagged in
  Showdown output, not silently populated with a misleading classic-fit
  number. (Superseded same-day by Session 13.3b -- see that card for the
  real values now shipped instead of a placeholder.)

**Handoff notes to log:** Final decision on ownership field handling for
Showdown: shipped first as an explicit NaN + `ownership_available=False`
flag (this card's original ask), then upgraded same-day to a real
Showdown-specific heuristic once the user flagged that leaving it
unaddressed wasn't acceptable -- see Session 13.3b.

---

### Session 13.3b — Showdown Ownership Heuristic ✅ Complete (2026-08-05)
**Prerequisites:** Session 13.3 complete (Showdown final_projections pipeline
exists to attach ownership columns to).

**Why this exists as its own card:** not on the original roadmap. Added
same-day when the user pointed out that neither 13.3 (which punted via NaN)
nor 13.4 (which per its own card only touches pivot_finder.py's existing
band-eligibility filter, not ownership computation) actually builds real
Showdown ownership -- and that accurate pivot/ownership signal was stated
as a real priority for Showdown early in Phase 13's scoping, just secondary
to accurate projections. Sequenced between 13.3 and 13.4 so pivot_finder
has real scores to test against in 13.4 instead of NaN placeholders.

**Files touched (modified):**
- `scripts/ownership_heuristic.py` -- `compute_chalk_scores()` and
  `compute_estimated_ownership()` both gained an optional `group_col`
  parameter (and the latter an optional `budgets` parameter), defaulting
  to `None` = exact original classic behavior (position_group /
  compute_position_slot_budgets), byte-identical output confirmed against
  a pre-refactor baseline run. New functions: `build_showdown_role_group()`
  (folds DK's "CPT"/FD's "MVP" into one "CPT_MVP" bucket, mirroring
  build_position_group()'s DST-label-folding pattern) and
  `compute_showdown_role_budgets()` (derives the real budget split --
  1 CPT/MVP slot + N FLEX slots -- directly from
  `SITE_CONFIGS[site]["showdown"]["roster_slots"]`, same real-roster-slot-math
  anchor as classic's decision #5, not a guess).
- `scripts/build_projections.py` -- `add_showdown_ownership_placeholder()`
  (13.3's NaN stub) replaced by `add_showdown_ownership_columns()`, which
  calls the above with Showdown's grouping and merges the result back onto
  `(player_id, roster_role)` -- not just `player_id`, since a Showdown pool
  has two rows per player and a CPT ownership share is a genuinely
  different real-world quantity from that same player's FLEX share.

**Design decision -- why roster_role instead of position_group:** Showdown
has no position-based roster slots at all (any position eligible in either
the 1 CPT/MVP slot or the N FLEX slots), so classic's per-position
percentile grouping has no meaning here. The blend's 5 features and their
weights are otherwise unchanged and reused as-is -- same UNFIT starting
guesses as classic, since no real ownership data (Showdown OR classic)
exists yet to fit against. Session 11.1's already-planned retuning now
covers both groupings, not a second separate set of magic numbers.

**Validation:**
- [x] `estimated_ownership_pct` sums to exactly the real roster-slot budget
  per role group: DK CPT_MVP 100.0%/FLEX 500.0% (1 CPT + 5 FLEX), FD
  CPT_MVP 100.0%/FLEX 400.0% (1 MVP + 4 FLEX) -- both exact, not
  approximate, on a synthetic Showdown pool.
- [x] chalk_score/estimated_ownership_pct both stay in [0,100] range on
  both sites' Showdown output.
- [x] Spot-checked a real player pair (Joe Burrow, DK): FLEX
  estimated_ownership_pct 19.85% vs. CPT 3.97% -- correctly reflects the
  much thinner CPT budget (100% total across the whole pool vs. FLEX's
  500%), matching real-world Showdown ownership fragmentation patterns.
- [x] chalk_score came out nearly-but-not-exactly identical between a
  player's CPT and FLEX rows (max diff ~0.85 of 100) -- expected, from
  tie-breaking in the pool-wide (not role-grouped) vegas/over_under
  percentile columns, not an error.
- [x] Classic regression: re-ran a classic DK slate through the refactored
  `ownership_heuristic.py` -- position-group budget totals numerically
  identical to the pre-refactor baseline (DST 100.0%, QB 100.0%, RB
  233.3%, TE 133.3%, WR 333.3%).

**Known issues deferred (flagged explicitly, not silently skipped):**
- **No real Showdown ownership data exists yet to fit against** -- same
  gap classic ownership has always had, now shared by two groupings
  instead of one. Real preseason Showdown slates start posting ~Aug 6,
  2026 (Phase 13's own trigger date) -- this is the point to start
  collecting.
- **`log_ownership.py` (Session 9.3) cannot currently log Showdown
  ownership at all** -- its logged schema
  (`data/ownership_actual_log.csv`: field_size, player_id, player_name,
  actual_ownership_pct, etc.) has no `roster_role` column, so it has no
  way to distinguish "this player's ownership when rostered as CPT" from
  "as FLEX" -- two different real quantities under this session's model.
  Before any real Showdown ownership data can be logged, `log_ownership.py`
  needs an additive `roster_role` column (and probably `slate_format`,
  matching the precedent Session 13.2 already set for
  `final_projections_*.csv`). Not built this session -- flagged as the
  concrete next step, needed before Session 11.1 can retune the Showdown
  grouping specifically (11.1 can still retune the classic grouping alone
  once its existing 4-6 week gate is met, independent of this gap).

**Handoff notes for next session:** Session 13.4 (Optimizer ILP) can now
assume Showdown output always carries real chalk_score/estimated_ownership_pct
-- no NaN handling needed in pivot_finder.py's Showdown path. Session 11.1's
prerequisites section has been updated with the log_ownership.py gap above
so it isn't rediscovered cold when real Showdown data starts arriving.

---

### Session 13.4 — Optimizer ILP for Showdown Roster Construction ✅ Complete (2026-08-05)
**Prerequisites:** Session 13.3 AND 13.3b complete (pivot_finder.py's
Showdown validation below wants real chalk_score/estimated_ownership_pct
to test against, not NaN placeholders).

**Outcome in one line:** shipped as a PARALLEL solve path (row-keyed on
`player_id::roster_role`, not a retrofit of classic's `solve_lineup()`)
after confirming classic's player_id-keyed dict comprehension would have
silently dropped half of every Showdown pool -- real-data validated on
the user's machine against actual 2025 nflverse players through the full
`generate_synthetic_slate.py` → `ingest_salaries.py` → `build_projections.py`
→ `optimizer.py` → `pivot_finder.py` chain, which is also what caught a
real cross-cutting bug (a partially-null `sigma` column that crashed both
the new Showdown path AND the pre-existing classic solver). Two premises
in this card measured FALSE against real code tracing, not just real
data: `pivot_finder.py` did NOT "likely need no change" (a real crash,
fixed), and stacking was NOT kept/adjusted/disabled as originally framed
-- the user clarified mid-session that the actual want ("make the lineup
one-sided") is fully covered by a much simpler `--min-team-players`
floor, so full stacking is deferred outright rather than half-built for
a 2-team pool. Full detail in SESSION_LOG.md's Session 13.4 entry.

**Files touched (modified):**
- `scripts/optimizer.py` — new solve path for Showdown/Single-Game slates,
  entirely separate from the classic ILP (zero lines of classic's existing
  formulation touched, aside from the sigma-NaN fix below). Delivers:
  - Exactly 1 CPT (DK) or MVP (FD) slot + N FLEX slots (5 for DK, 4 for FD).
  - Mutual exclusivity: the CPT-row and FLEX-row of the same underlying
    player can never both be selected.
  - Minimum 1 player from each of the 2 teams in the pool.
  - The captain salary multiplier is already baked into the CPT/MVP row's
    listed salary from Session 13.2's ingest, so the existing
    `<= salary_cap` constraint needed no special-casing.
  - `--format {auto,classic,showdown}` (default `auto`, detects via
    `slate_format`).
  - `--min-team-players TEAM:N` (NEW, same-session addendum) — the
    "one-sided lineup" lever that replaced full stacking support; a
    structural pre-check fails loudly before the solver runs if a
    requested floor is impossible.
  - `--stack-mode` and `--max-game-players` are REJECTED for Showdown
    with a clear CLI error (deferred, not silently ignored).
    `--min-total-ownership`/`--flex-positions`/`--min-projection` are
    likewise rejected — not built this session.
  - Locks/excludes/exposure caps/uniqueness/`--max-team-players`/
    `--lambda`/randomization all reused from classic where the concept
    translates directly (uniqueness counts by underlying player, not
    role; a lock forces either role, solver's choice).
- `scripts/pivot_finder.py` — the roadmap's premise here measured FALSE:
  a Showdown pool's 2 rows/player_id share the same (name, position,
  team) triple the existing join key used, so the "exactly 1 match"
  check always found 2 and crashed. Fixed by extending the join key with
  `roster_role` for Showdown pools (sourced from `optimizer.py`'s
  Showdown output, which now carries that column). Pivot candidates are
  now also required to match the cash player's own `roster_role`.

**Validation:**
- [x] Synthetic-pool unit tests: CPT/FLEX exclusivity enforced, min-1-per-team
  enforced, salary cap respected, exactly 6 (DK) / 5 (FD) total slots.
- [x] `optimizer.py` full-file compile check.
- [x] Solver produces a valid lineup against a synthetic Showdown pool
  for both sites — AND optimality independently confirmed by brute force
  (unconstrained, `--max-team-players`-constrained, and
  `--min-team-players`-constrained solves all matched their brute-forced
  optimum exactly).
- [x] `pivot_finder.py` produces sane suggestions against a Showdown pool
  — not deferred; verified same-`roster_role` candidates only.
- [x] Real-data end-to-end run on the user's machine: real 2025 nflverse
  players through the actual pipeline (not just synthetic fixtures) —
  this is what surfaced the sigma-NaN bug (see below), consistent with
  this project's "bugs found only by running real data" pattern.
- [x] Classic-path regression: `optimizer.py`/`pivot_finder.py` output
  confirmed byte-identical against the pre-13.4 originals, both before
  and after the sigma-NaN fix.

**Handoff notes to log:** Stacking is DEFERRED for Showdown, not
kept/adjusted/disabled as this card originally framed the choice —
`--min-team-players` (new) covers the real want instead. `pivot_finder.py`
needed a real fix, not just a verify pass. A cross-cutting sigma-NaN bug
was found and fixed in BOTH the new Showdown path and the pre-existing
classic `solve_lineup()` (see SESSION_LOG.md — `build_projections.py`'s
`sigma` column can be present-but-partially-null since the Session 13.1
kicker model landed, which would have broken the next real classic slate
run too). `build_projections.py`'s unused `_dst_extra` variable (DST
sigma computed, then dropped, never merged back) is flagged for a future
`build_projections.py`-focused session, not fixed here (out of this
session's scope). Session 13.5 needs `--min-team-players` added to the
Cloudflare Worker's `passthroughKeys` and the GitHub Actions flag-builder
alongside the existing team-cap flags, and the frontend needs to hide/
disable the four Showdown-rejected flags rather than leave them clickable.

---

### Session 13.5 — Frontend Showdown UI + Four-Layer Wiring ✅ Complete (2026-08-05)
**Status note:** Paused mid-session pending Session 13.5b (two real bugs
found during real-slate Showdown testing, documented in `Handoff_13.5_
Pause_BugFixes.md`). Resumed after 13.5b's fixes were real-data validated
and closed out. Also serves as Session 13.6's closure — see that card.

**Prerequisites:** Session 13.4 complete.

**Files touched (modified):**
- `dfs_optimizer_frontend/index.html` — Showdown-aware `SITE_CONFIG` +
  detection helpers, Showdown-aware roster sort/render/download (DK/FD
  bulk-upload column shapes), `K` tab + CPT/MVP role badges in Player
  Pool, role-aware pivot panel matching, new Min Team Players control,
  Build panel hide/show + dispatch param wiring for Showdown.
- `cloudflare_worker/optimizer_api/optimizer_api.js` — `format` and
  `min_team_players` added to `passthroughKeys`.
- `.github/workflows/run_optimizer_dispatch.yml` — `--format` and
  `--min-team-players` flag-building added.
- `.github/workflows/refresh_data.yml` — confirmed, no change needed.
- `DFS_Weekly_Process.md` — full Showdown section + inline notes added.

**Validation:**
- [x] `node --check` clean on extracted `index.html` script block.
- [x] `optimizer_api.js` Node syntax check.
- [x] Both workflow YAML files parse clean.
- [x] Worker deployed.
- [x] Real DK Showdown slate (not just synthetic) validated end to end
  multiple times, including after 13.5b's fixes: K tab, CPT/MVP badges,
  Build panel hide/show, Min Team Players, Team Exposure Caps, lineup
  build through real dispatch, CPT→FLEX roster order.
- [x] FD Showdown, pivot panel role-aware matching, mixed classic/
  Showdown UI session — user-confirmed working, not independently
  re-verified by Claude. See SESSION_LOG.md's Session 13.5 entry.

**Real bug found, NOT code-fixed (deferred):** `labelToSlateId()` always
lowercases the slate_id it sends on dispatch, but the backend CLI
preserves whatever case was typed at `--slate-id` — a mismatch causes a
dispatch-time `FileNotFoundError`. Workaround: always use lowercase
`--slate-id` at the CLI (reflected in `DFS_Weekly_Process.md`). Code fix
not done this session — affects any slate type, not just Showdown.

**Handoff notes logged:** See SESSION_LOG.md's Session 13.5 entry —
covers the flat-preseason-Showdown-salary finding, the player-props
backlog item, and the "projections trending high" observation (both
now tracked under PHASE 9 below).

---

### Session 13.5b — Bug Fixes: DST Opponent Resolution, Rookie/
Zero-History Matching, Vegas Decoupled from Week ✅ Complete (2026-08-05)
**Prerequisites:** Session 13.4 complete. Not dependent on 13.5 itself --
both bugs fixed here are confirmed NOT Showdown-specific (affect classic
and Madden slates too), which is why this is numbered separately rather
than folded into 13.5's own card.

**Trigger:** Two real bugs found during Session 13.5's own real-slate
Showdown testing, documented in `Handoff_13.5_Pause_BugFixes.md`:
Bug A (DST's opponent resolution bypassed the Game-Info fallback skill
players/kickers already use) and Bug B (rookies/zero-history players
silently dropped from the pool before the cold-start salary-anchor logic
ever saw them).

**Files touched (modified):** `scripts/dst_model.py`, `scripts/build_
projections.py`, `scripts/vegas_odds.py`, `scripts/ingest_salaries.py`,
`scripts/ingest_historical.py`, `.github/workflows/refresh_data.yml`. See
SESSION_LOG.md's Session 13.5b entry for the full per-file breakdown --
three additional real bugs (an `api_keys.env` BOM issue, `ingest_
historical.py` aborting an entire multi-season pull when only one season
404'd, and Session 13.4's flagged-but-unfixed `_dst_extra` sigma gap) were
also found and fixed in this same session via real-data validation, plus
a structural fix decoupling vegas data from `--week` entirely (now keyed
by `--slate-id`, matching the existing salary/projections convention).

**Validation:** Real-data validated end to end against three different
real slates this session -- a real preseason ARI/CAR Showdown slate, a
re-run Madden slate, and (most load-bearing) a full real DK Week 1 2026
regular-season classic slate carried all the way through to lineups built
via the live GitHub Actions/Cloudflare Worker dispatch path. Full details
and numbers in SESSION_LOG.md.

**Handoff notes to log:** `DFS_Weekly_Process.md` still needs a rewrite
pass reflecting everything this session changed (vegas via `--slate-id`,
the Week-1-vs-Week-2+ `--season`/`--week` split, the corrected Madden
game-totals-panel note, the new `--weekly-rosters` flag) -- explicitly
deferred to its own follow-up, not done this session. See SESSION_LOG.md's
Session 13.5b entry, "Handoff notes for next session," for the full list.

---

### Session 13.6 — Real Showdown Slate Validation (DK & FD) ✅ Complete (2026-08-05)
**Status note:** Closed alongside Session 13.5 rather than run as a
separate session — the real-slate testing that resumed/closed 13.5 (real
DK Showdown end to end, plus user-confirmed FD Showdown) covers this
card's full scope. See Session 13.5's card and SESSION_LOG.md entry for
the actual validation detail; not duplicated here.

**Prerequisites:** Sessions 13.1-13.5 complete on synthetic data. A real
DK Showdown and/or FD Single Game slate available (first opportunity:
preseason Thursday games, ~Aug 6, 2026 — exact availability depends on
whether both sites post Showdown-format contests for that slate).

**Note (Session 13.2):** the *ingest* layer's real-data validation for
both sites already happened in Session 13.2, ahead of schedule — both
sites' 08/06/2026 CAR@ARI exports were used, not just synthetic. This
session's scope is validating the FULL pipeline (13.3 projections/scoring
through 13.5 frontend), not re-validating ingest from scratch.

**Files touched:** None from this card directly — the real fixes real-data
testing surfaced (DST opponent resolution, rookie/zero-history matching,
vegas/week decoupling) are tracked under Session 13.5b, not here.

**Validation:**
- [x] Full real-data pipeline run, DK Showdown: ingest → kicker/skill/DST
  projections → CPT multiplier → optimizer → frontend build → DK
  bulk-upload export, end to end.
- [x] Full real-data pipeline run, FD Single Game — user-confirmed, not
  independently re-verified by Claude (see Session 13.5's entry).
- [x] Session 13.2's previously-UNVERIFIED FD Showdown column assumptions
  confirmed via this real FD Showdown test.

**Handoff notes logged:** Both sites had real Showdown slates available
for this validation (the real preseason ARI@CAR Showdown, DK and FD).

---

## Summary: Phase 13 sequencing

| Session | What | Depends on | Real-data gate |
|---|---|---|---|
| 13.1 | Kicker projection model | None | Historical nflverse kicking data (available now) |
| 13.2 | Showdown/Single-Game salary ingest | None (13.1 not required) | DK: available now (Madden Sim-style). FD: unverified until 13.6 |
| 13.3 | Projection scoring-multiplier layer ✅ | 13.1, 13.2 | Synthetic sufficient |
| 13.3b | Showdown ownership heuristic ✅ | 13.3 | Synthetic sufficient for the heuristic itself; real Showdown ownership DATA (for eventual retuning, Session 11.1) gated on real slates ~Aug 6, 2026 + a log_ownership.py schema change, neither built yet |
| 13.4 | Optimizer ILP rewrite ✅ | 13.3, 13.3b | Real-data validated (user's own machine, real 2025 nflverse players through the full pipeline) — stacking deferred, `--min-team-players` shipped instead |
| 13.5 | Frontend + four-layer wiring ✅ | 13.4 | Real-data validated: real DK Showdown end to end, FD Showdown/pivot panel/mixed UI user-confirmed |
| 13.5b | Bug fixes: DST opponent resolution, rookie matching, vegas/week decoupling ✅ | 13.4 | Real-data validated: real Showdown slate, real Madden slate, real Week 1 2026 classic slate end to end |
| 13.6 | Real Showdown slate validation, both sites ✅ | 13.1-13.5 | Closed alongside 13.5 — same real-slate testing covers both cards |

**Phase 13 is now fully closed** as of 2026-08-05. **Update 2026-08-11:** Phase 6's core intent (full pipeline, both sites, live, real data) was substantively met by Session 14.1c against a real regular-season Week 1 2026 slate, rather than by a formally-run Phase 6 session against preseason -- see Session 6.1's card note for the exact scope of what did and didn't carry over. Remaining real gate on the roadmap: Phase 8 (regular-season go-live), plus the cron-job.org near-lock automation firing check (deliberately deferred until closer to real lock, user's call).

---

## PHASE 14 — Production Engine Cutover & Market Data Expansion
*Opened 2026-08-06. Triggered by two user observations on a real DK Week 1
2026 test slate: projections running ~25% high versus what the user
normally expects, and a question about why player props aren't used
anywhere in the pipeline. A code audit (not a guess) traced the first
issue to a real gap — see Session 14.0's trigger note below — and
confirmed the second as a genuine, already-flagged backlog item. Both
get their own session rather than a quick patch, per this project's
design-before-build discipline.*

### Session 14.0 — Production Engine Cutover (Stat-Line → Live) ✅ Complete (2026-08-06)
**Backfilled 2026-08-14 (Session 15) -- see SESSION_LOG.md for the full
entry, including the real old-vs-new engine diff numbers that close out
the validation checklist below. The work itself happened on 2026-08-06;
only the roadmap/log paper trail was missing until now.**

**Prerequisites:** Sessions 10.3a, 10.3b, 10.4, 10.4b, 10.5, 10.5b
(the stat-line engine itself — all already complete and backtested).

**Trigger:** Code audit (2026-08-06) found that `refresh_data.yml` —
the workflow that builds every real slate's projections — has always
called `scripts/build_projections.py`, the Session 2.4 placeholder
engine, for QB/RB/WR/TE:
`final_projection = (0.5*season_avg + 0.5*recent_form) * matchup_factor * vegas_factor`.
`scripts/build_projections_statline.py` — the actual Phase 10 rebuild
(stat-line projection, Monte Carlo mean+sigma, price-as-volume-prior,
role-change handling), backtested over 65 weeks at 75.6/96.5
median/max-percentile — was built as a schema-compatible drop-in
("co-exist with `build_projections.py` until the harness says it
wins," per its own docstring) but the actual cutover step in
`refresh_data.yml` was never done. Only DST (`dst_model.py`, Session
10.4) and Kicker (`kicker_model.py`, Session 13.1) actually made it
into the live path. `optimizer.py` itself documents the consequence:
its own comment notes "the legacy production path carries no sigma
column," meaning Session 10.5's variance-aware objective has never
operated on any real slate either.

**A second code audit (same day), comparing `build_projections_statline.py`
against the CURRENT `build_projections.py`, found the parallel engine is
NOT a safe drop-in as-is** — it predates several fixes and an entire
feature area added to the legacy engine after Session 10.3a:

1. **Vegas lookup would crash on any real slate.** Session 13.5b fixed
   `load_vegas_implied_totals()` to key off `slate_id` (not `week`).
   `build_projections_statline.py`'s own `main()` still calls it as
   `load_vegas_implied_totals(week)` — passes a bare integer into a
   function that now expects a slate_id string. Raises
   `FileNotFoundError` on any slate where `slate_id != str(week)`,
   which is effectively all of them post slate-management overhaul.
2. **Output filename collision.** Still writes
   `final_projections_{site}_{week}.csv` — the exact bug Session 2.4
   already fixed elsewhere (`{slate_id}` naming, so two slates in the
   same week don't overwrite each other).
3. **Zero Showdown/Single-Game support.** No `CAPTAIN_MULTIPLIER`, no
   `--format` flag, no CPT/MVP handling anywhere — all of Phase 13 was
   built after this file was last touched.
4. **`--volume-prior` and `--sigma-recalibration` are opt-in flags,
   off by default.** Without explicitly passing both, `refresh_data.yml`
   would get only Session 10.3a's bare rewrite — silently losing
   10.3b's price-implied volume prior and 10.4b's sigma recalibration,
   which is most of what actually validated well in the backtest.

DST, salary ingest, and opponent-map logic are safe as-is — the
stat-line script imports those functions directly from
`build_projections.py` rather than duplicating them, so fixes made
there already carry over.

**Sites:** DK and FD both, same as every projection-build session.

**Files touched (modified):**
- `scripts/build_projections_statline.py` — fix vegas call site
  (`slate_id` not `week`), fix output filename (`{slate_id}` not
  `{week}`), port Showdown/Single-Game support (CAPTAIN_MULTIPLIER,
  `--format`, CPT/MVP role handling — likely extract into a function
  shared with `build_projections.py` rather than duplicate; decide
  during build)
- `.github/workflows/refresh_data.yml` — swap the `build_projections.py`
  call to `build_projections_statline.py` for both DK and FD steps,
  with `--volume-prior --sigma-recalibration` explicitly passed, and
  `--dst-model distributional` confirmed passed (matching current
  production default)
- `DFS_Weekly_Process.md` — update if the CLI invocation changes

**Inputs:** Same as `build_projections.py` currently uses (salaries,
baseline/recent-form, matchup factors, vegas implied totals) plus
`data/volume_prior_dk.json` / `_fd.json` and sigma recalibration
artifacts from Sessions 10.3b/10.4b.

**Outputs:** `output/final_projections_{site}_{slate_id}.csv`, same
schema as today plus `sigma`, `statline_p10`, `statline_p90`, and
`proj_*` audit columns (per `build_projections_statline.py`'s decision
#1).

**Build:**
- Fix the three concrete bugs above (vegas call site, output filename,
  opt-in flags) before touching anything else
- Port Showdown support
- Wire `refresh_data.yml` to the fixed script
- Do NOT change `optimizer.py`'s default `--lambda 0.0` as part of this
  session — the point is fixing the mean projection and finally
  activating sigma as an available input, not changing lineup-
  construction strategy in the same session as a mean-projection fix.
  A future session can revisit λ once sigma has been live and observed
  for a few real weeks.

**Validation:**
- [x] `node`/Python syntax checks pass on all modified files
- [x] Fixed script runs end-to-end on a real slate without the vegas/
  filename bugs reproducing
- [x] Showdown slate still builds correctly through the swapped engine
  (real DK and/or FD Showdown slate, not just synthetic)
- [x] **Real old-vs-new engine diff, run for real by Session 15
  (2026-08-14)** — same test slate, both engines' output compared
  player-by-player: 292 matched players, old engine averaged 8.32
  points/player vs. new engine's 5.13 — a real **-40.5% mean shift**,
  same direction as and larger than the user's original ~25%-high
  estimate. Closes this checkbox with real numbers instead of the
  original "not yet run" gap. See SESSION_LOG.md's Session 14.0 entry
  for the full comparison, including individual player examples.
- [x] Full pipeline (ingest → projections → optimizer → frontend →
  export) validated end to end post-swap, both sites
- [x] `DFS_Weekly_Process.md` updated if CLI changed — N/A, the CLI
  invocation itself didn't change (`--volume-prior --sigma-recalibration
  --dst-model distributional`, same flags the doc already documented);
  only `refresh_data.yml`'s internal call target changed.

**Handoff notes to log:** the actual before/after projection numbers on
the real Week 1 slate — this is the evidence for whether the inflation
issue is closed, partially closed, or unrelated to the engine.
**Closed 2026-08-14 (Session 15, backfilled): -40.5% mean shift on a real
slate, same direction as the original ~25%-high observation — the
inflation issue this phase opened to investigate is confirmed closed.**

---

### Session 14.1 — Player Props as a Projection Input (Scoping + Design) ✅ Complete (2026-08-06) — Resolution: Deferred
**Prerequisites:** Session 14.0 (props should fold into whichever
engine is live — no point designing against the pipeline being
replaced).

**Trigger:** User asked why the pipeline doesn't use player props,
flagged during Session 13.5's closeout as a backlog idea, promoted to
a full session on 2026-08-06 alongside 14.0. See "Backlog idea — Player
props as a projection input" above (PHASE 9 section) for the original
flag.

**This is explicitly a design/scoping session, not a full build** — per
this project's design-before-build discipline, no code touches
`volume_prior.py` or `statline_model.py` until the data-source and
blend-placement decisions below are made explicitly.

**Data source decision — options identified 2026-08-06:**

The project already has an account with **The Odds API** (used by
`vegas_odds.py`), which added NFL player props as a market on a
separate endpoint (`/v4/sports/{sport}/events/{eventId}/odds`, one
event at a time — the current game-level pull uses the whole-sport
`/v4/sports/{sport}/odds` endpoint instead). No new vendor is
*required*. Real numbers, verified against the provider's own docs:

- **Cost formula:** `[unique markets returned] x [regions]`, per event.
  A ~14-game week at, say, 8 relevant markets (see narrowed list
  below), 1 region = ~112 credits per full pull. Compare to the
  current spreads+totals pull, which costs 2 credits for the ENTIRE
  week in one call (different endpoint). Free tier is 500 credits/
  month — likely insufficient if `refresh_data.yml`'s near-lock
  polling pulls props on every cycle the way it does game lines. Paid
  tiers start at $30/mo (20,000 credits).
- **Historical/backtest data is a real constraint, not just a cost
  one.** Historical player-props data is a separate, pricier paid tier
  even on The Odds API, and only available from May 2023 forward —
  there's no equivalent to the 2014-2021 RotoGuru archive Phase 10 was
  backtested against. Props validation will have to be forward
  (live, a few real weeks), not backtested — slower, weaker evidence
  than the rest of this project's validation bar. Decide explicitly
  whether that's acceptable before building.

**Alternative evaluated: SportsGameOdds** (`sportsgameodds.com`).
Structurally different pricing — bills one "object" per event
regardless of how many markets/bookmakers are pulled, versus The Odds
API's per-market-per-region credit meter. Verified against their own
pricing page (2026-08-06): free "Amateur" tier is 2,500 objects/month,
10-minute update interval, includes DraftKings and FanDuel among 9
bookmakers, and explicitly includes player props at that tier. For a
once-or-twice-per-week refresh cadence pulling ~14 NFL games, that's
comfortably inside the free tier where The Odds API's props usage
likely would not be — a genuinely better fit for this project's
free-to-operate goal, if the coverage and reliability hold up in
practice. Trade-offs to weigh: newer service (public launch ~2024,
versus The Odds API operating since 2017 — shorter track record on a
real football weekend), and historical data (needed for any future
backtest) is gated to their $299+/mo Pro tier, worse than The Odds
API's already-flagged gap. A neutral third-party source independently
corroborates the free-tier bookmaker count and update interval, which
is reassuring, but the head-to-head comparison content itself is
vendor-authored (SportsGameOdds's own comparison page) and should be
read as a starting point, not taken at face value — spot-check via a
real free-tier signup and probe call before committing either way.

**Not deeply evaluated, flagged for awareness only:** OddsPapi (flat
per-request pricing, historical bundled at every tier per their own
marketing — worth a look if both options above disappoint),
Sportradar's Odds Comparison Player Props API (enterprise-oriented,
likely priced above this project's bar). Not worth session time unless
both primary options fail the probe step.

**Props relevance — narrowed from the full NFL market list, first
pass (2026-08-06), to work through together:**

*Core — direct 1:1 with existing stat-line components in
`statline_model.py`, clear scoring relevance:*
- `player_pass_yds`, `player_pass_tds`, `player_pass_interceptions`
  (QB — INT is real negative scoring on both sites)
- `player_rush_yds`, `player_rush_tds`
- `player_receptions`, `player_reception_yds`, `player_reception_tds`
- `player_anytime_td` — different shape (Yes/No, not an over/under
  line) but useful as a cross-check against summed rush_tds +
  reception_tds for the same player, and may end up being the more
  reliable TD signal on its own

*Secondary — volume-only signal, not a direct scoring stat, marginal
value over what `volume_prior.py` already extracts from price:*
- `player_pass_attempts`, `player_rush_attempts` — worth testing
  whether these add anything once props are live, not worth the
  credit cost to include from day one

*Worth adding given Session 13.1's kicker model already exists:*
- `player_field_goals`, `player_kicking_points`

*Excluded — no direct DK/FD scoring correspondence:*
- `player_pass_completions` (redundant with attempts+yards)
- `player_pass_longest_completion`, `player_reception_longest`,
  `player_rush_longest` (no "longest" bonus in standard DK/FD classic
  scoring)
- `player_pats` (minor, low value for the credit cost)
- `player_1st_td`, `player_last_td` (low liquidity, largely redundant
  with `player_anytime_td`, order-specific noise)
- `player_pass_rush_yds`, `player_pass_rush_reception_tds`,
  `player_pass_rush_reception_yds`, `player_rush_reception_tds`,
  `player_rush_reception_yds` (combo markets — redundant with the
  individual splits already listed; possible future use as a
  reconciliation cross-check, not core)

*Not applicable at all:*
- `player_sacks`, `player_solo_tackles`, `player_tackles_assists` —
  individual defensive-player props. This project's DST scoring is
  team-level (DK `DST`/FD `DEF`), not IDP. No use for these regardless
  of source.

This is a first pass — flagged explicitly as something to work through
together rather than settled unilaterally, since the user has the DFS
domain judgment call on which of these genuinely move a projection.

**Files touched (new, once design is settled):**
- `scripts/probe_player_props.py` — throwaway probe script, run
  against a real upcoming slate with the user's own API key, to
  measure real market coverage and real credit/object cost before
  committing to a source
- Eventually (NOT this session): `scripts/vegas_props.py` (new,
  parallel to `vegas_odds.py`) and modifications to `volume_prior.py`
  / `statline_model.py`

**Build, phased:**
1. Probe both candidate sources against a real slate — confirm actual
   market coverage this early in the season (preseason bookmaker
   coverage is often thinner than regular season) and actual real cost
2. Make the data-source decision explicitly, budget-aware
3. Finalize the props market list (the narrowed list above, worked
   through together)
4. Design where props enter the blend without duplicating
   `vegas_factor`/team `implied_total` — leading candidate: a third
   source alongside usage-history and price-implied volume in
   `volume_prior.py`, own empirical weight, consistent with Session
   10's "blend at stat-line level, decorrelated sources" principle.
   TD props are probably the single highest-value addition, since TD
   rate is the hardest thing for a usage-based model to get right.
5. Design de-vig methodology — the over/under `point` line isn't free
   of house edge, and `anytime_td`-style Yes/No markets need a real
   implied-probability treatment, not a naive read of the posted line.

**Validation:**
- [x] Probe confirmed real market coverage against 3 real Preseason
  Week 1 2026 games — zero coverage, traced to a genuine documented
  vendor limitation (no NFL preseason props on The Odds API), not a
  code bug or billing gate. See SESSION_LOG.md for the full trace,
  including a real vendor-name-collision check (`theoddsapi.com` vs.
  this project's actual `the-odds-api.com`).
- [x] Real cost modeled against the project's actual `refresh_data.yml`
  cadence (~8x/week, not the 3x/week first estimated) — both The Odds
  API (~6,054 credits/month, ~12x over its 500 free tier) and
  SportsGameOdds (~4,128 objects/month, over its 2,500 free tier under
  a realistic 5-kickoff-window week) would exceed their free tiers at
  production cadence. Validation-scale usage (a handful of pulls, not
  weekly) fits inside The Odds API's existing free tier with no new
  vendor needed.
- [ ] ~~Data-source decision made explicitly, budget-aware, written
  down~~ — superseded. See **Resolution** below: the data-source
  decision became moot once the build itself was deferred.
- [ ] ~~Final props market list agreed~~ — not reached, not needed.
- [ ] ~~Blend-placement design written and agreed~~ — not reached, not
  needed. No code touched `volume_prior.py`/`statline_model.py`, per
  this card's original design-before-build boundary, held for the
  entire session.
- [ ] ~~Forward-validated against live weeks~~ — not applicable; nothing
  was built to validate.

**Resolution (2026-08-06):** Deferred, not built, not abandoned. Once
Session 14.0 is understood as already wiring in two market-derived
signals (`vegas_factor` at team level, price-as-volume-prior at player
level via salary), the user's own side-by-side comparison against a
market-blended-simulation reference framework judged the existing
volume-level market anchoring as a more principled design than a naive
points-level market blend would have been. Given that, a third
market-derived signal (player props) carries real, distinct risks —
double-counting via correlation (not just mis-weighting), unvalidated
de-vig math, interaction with Session 14.0b's share-reconciliation fix,
and small-sample weight-fitting with no historical props backtest
available — that aren't worth taking on speculatively, without
evidence the existing signals are actually insufficient.

**Explicit reopening trigger (not indefinite deferral):** once Session
9.1's actual-vs-projected logging has real data, check whether real
projection error is concentrated in cold-start/low-history/
committee-role players specifically (the pattern that would implicate a
missing market signal) versus broad/uniform across player types (the
pattern that implicates usage-modeling/calibration instead — λ, sigma,
volume-prior tuning — which props would not fix). Only the first
pattern is grounds to reopen this card. All groundwork above (vendor
comparison, real cost numbers, first-pass market list, both probe
scripts, the cache-by-game design note in SESSION_LOG.md) stays valid
and doesn't need to be re-derived if that happens.

**Handoff notes to log:** see SESSION_LOG.md's Session 14.1 entry for
the full real numbers (credit-cost math, the MLB sanity-check catching
a real market-key error, the vendor-name-collision trace) and the
complete reasoning behind the deferral decision.

---

### Session 14.2 — Post-14.0/14.1 Reassessment
**Prerequisites:** Session 14.0 complete. Session 14.1 closed as of
2026-08-06, resolved as a deliberate deferral rather than a build (see
that card's Resolution) — so this checkpoint isn't waiting on props
work in progress, just on Session 9.1 having real data to assess
against, same gate as everything else post-cutover.

**Purpose:** explicit checkpoint, not a new build. Session 14.0 came out
of one real observation on one real test slate (the 25%-high
projection gap); Session 14.1 came out of the other (props as a
possible missing signal), and resolved into "existing market signals
judged sufficient, pending evidence otherwise" rather than a build.
Once Session 9.1 has real data, reassess where the projection system
actually stands against both original flags — including running the
specific cold-start-concentrated-vs-broad-error check that Session
14.1's card sets up as the real trigger for reopening player props —
before deciding what (if anything) comes next. User's own framing
(2026-08-06): "we are clearly pointing out some gaps and we need to
see where things land after the updates are applied."

**Build:** None — this is a review session. Compare real slate output
before/after both sessions, revisit whether Session 9.1 (actual-vs-
projected logging, still gated on real games ~Sept 13) changes the
picture once it has data, and decide whether further projection work
is warranted or whether the system is in good enough shape to shift
focus elsewhere (FD validation, Phase 6 preseason dry runs, etc.).

**Validation:** N/A — defer scoping until 14.0/14.1 are actually done
and there's real output to look at.

---

### Session 15 — Pre-Season Hardening: Participation Floor + Pivot Pipeline Fixes ✅ Complete (2026-08-14)

**Trigger:** two real, user-reported problems from the first real production use of the Phase 14 engine — a backup QB (Riley Leonard, IND) outranking the actual starter (Daniel Jones) in a real Week 1 2026 DK build, and the cash-to-GPP pivot feature (Session 4.2/4.3) never having produced output on any real slate, ever.

**Build:** `apply_participation_floor()` in `optimizer.py`, a new `--participation-floors` flag (default `QB:0.6,RB:0.4,TE:0.4`, ON by default, classic slates only) that excludes a player from the candidate pool if he's barely appeared in his team's last 5 games — `--lock` overrides it for a known exception. `games_played`/`participation_effective` now survive into `final_projections_*.csv` (previously computed internally, dropped before the final CSV) to make the floor possible at all. Separately, `pivot_finder.py` fixed to read the file real usage actually produces (`lineups_multi_*.csv`, not `lineup_single_*.csv`, which was the entire reason pivots had never worked), plus two further real bugs found and fixed while validating that fix against real data: a salary-cap re-check that summed the wrong thing (was checking a swap against the sum of ALL rostered players across 20 lineups, not one lineup — $175,900 against a $50,000 cap, failing every candidate silently), and an FD defense position-label mismatch ("D" vs "DEF") that crashed the script outright. Also found: the real UI build path never wrote the slate-keyed lineup file pivots depend on at all (it only wrote a per-request file used for polling) — fixed with a second write.

**Files:** `scripts/optimizer.py`, `scripts/build_projections_statline.py`, `scripts/pivot_finder.py`, `cloudflare_worker/optimizer_api/optimizer_api.js`, `.github/workflows/run_optimizer_dispatch.yml`, `dfs_optimizer_frontend/index.html`. Full decision-by-decision detail in SESSION_LOG.md.

**Validation:**
- [x] Participation floor unit-tested against synthetic data shaped like the real Jones/Leonard/Richardson case; user-confirmed on a real production build (no backup-QB-shaped rosterings observed) — see SESSION_LOG.md for the caveat on how directly this was re-traced vs. B1/B2 below.
- [x] Pivot fixes confirmed end-to-end against the user's real Week 1 2026 DK and FD builds — real output (29 rows/14 players DK, 19 rows/12 players FD, 0 salary-cap violations either site), remaining "no candidates" cases hand-verified as genuine, not bugs.
- [x] User confirmed uploading and viewing correct pivot suggestions in the deployed UI.
- [x] All modified files pass their respective syntax/compile checks (`py_compile`, `node --check`, YAML parse, `getElementById` cross-reference).

---

### Session 15.1 — Pivot Live Auto-Load + Weekly Process Reorg ✅ Complete (2026-08-15)

**Trigger:** with Session 15's pivot pipeline confirmed working, the remaining friction was that the user still had to manually re-upload the pivot file into the UI every time they wanted current data — exactly what's easy to forget under real time pressure near lock. User's own framing: "I'm not scrambling for pivots in the last hour."

**Build:** new Worker action `load_pivots` reads `output/pivot_suggestions_{site}_{slate_id}.csv` live from GitHub on every call, mirroring how a lineup build already always reads whatever's currently committed rather than anything cached. Frontend's pivot-loading function tries this live read first, falling back to the old upload-and-cache path only if the Worker is unreachable — manual upload still works, just no longer required. Separately, reorganized `DFS_Weekly_Process.md` per user request: pivot generation moved from Stage 4 (after lineup building) to a new Step 2j, inserted between the old "build final projections" (2i) and "commit and push" (renumbered 2j → 2k) — builds a rough, disposable local lineup batch purely to seed pivots, so projections/lineups/pivots all push together in one cycle instead of two.

**Files:** `cloudflare_worker/optimizer_api/optimizer_api.js`, `dfs_optimizer_frontend/index.html`, `DFS_Weekly_Process.md`.

**Validation:**
- [x] `node --check` clean on both JS files; `getElementById` cross-reference clean.
- [x] User-confirmed working on the real deployed Worker/UI post-redeploy: "appears to be working correctly" — pivots load with no upload step.
- [x] All internal Step 2i/2j/2k cross-references in `DFS_Weekly_Process.md` grep-verified consistent after renumbering.

**Closes the loop opened by Session 15's original trigger report** — nothing outstanding remains from either the backup-QB or the pivot report.

---

Session 15.2 — Pre-Season Deep Dive: Projections ✅ Complete (2026-08-15)

Trigger: user's original open-ended ask (2026-08-14) to deep-dive projections while there's still time before real games start. Planned approach: pull real 2026 teams/players through the pipeline hunting for other Jones/Leonard-shaped situations (committee backfields, offseason team changes, rookie Week 1 starters, anyone who missed time late in 2025), plus a sigma/uncertainty sanity pass.

Build: found and fixed two real production bugs, diagnosed two further real statistical limitations (deferred to Session 15.2b below), reassessed against fresh live data to confirm the fixes and check for anything missed.

The confirmed-starter override. Six real Week 1 2026 players (Sam LaPorta, Tucker Kraft, Garrett Wilson, Rome Odunze, Alvin Kamara, Michael Penix Jr.) projected at a literal 0.0 despite being real, rostered players — traced to the existing role-change override's own divide-by-zero guard always blocking at exactly-zero participation, and confirmed that patching the guard alone doesn't help (a real injury-returning starter's price runs BELOW his established share, not above — the override's whole shape points backward for this group). Fixed by checking nflverse's real daily depth-chart feed instead of inferring role from price: a confirmed #1 with zero recent participation gets full credit for his established role; a genuine backup (Kamara, Penix — both real #2s) is correctly left alone. Live and confirmed in production (Run #153).
status_check.py's stale filename convention, found while validating #1 live: the automated "zero out OUT players" step had been silently overwriting an orphaned legacy-engine filename since the Session 14.0 cutover, on both sites, never touching the real file optimizer.py reads. Fixed in refresh_data.yml. Live and confirmed in production (Run #153) — 6 real OUT players correctly zeroed on the real file, both sites, for the first time since the cutover.
Reconciliation misattributes traded players to the wrong team. 70 players on the real Week 1 2026 slate had a current team different from their 2025 team; their real historical volume was being credited to their NEW team's share estimate instead of the team that actually produced it (Carolina's real rush pool share came out at 55.7% purely from Rico Dowdle's real production being counted toward Pittsburgh). Fixed — confirmed against real data (Carolina 55.7%→99.2%; team-level correlation with real 2025 identity -0.183→+0.239). Built, validated, and confirmed pushed and live — verified directly against the GitHub repo at the start of Session 15.2b, before any of that session's own work began.
Diagnosed, not built: the team-volume model's weak history coefficient (Mechanism 1) and sigma's failure to reflect team-volume prediction uncertainty (Mechanism 3) — both real, quantified findings needing proper backtesting before a fix. Deferred to new Session 15.2b, user's explicit call.
Judged genuinely unfixable, not deferred: Calvin Ridley (TEN) and James Conner (ARI) both sit behind real, currently-unresolved depth-chart competitions — any assigned number would be a guess dressed up as a signal. Left as documented, accepted limitations.

Files: scripts/nflverse_fetch.py, scripts/ingest_historical.py, scripts/statline_model.py, scripts/build_projections_statline.py, .github/workflows/refresh_data.yml, scripts/status_check.py. Full decision-by-decision detail in SESSION_LOG.md.

Validation:

 Items 1-2 confirmed live in real production (GitHub Actions Run #153, 2026-08-15) — not just probed/validated locally.
 Item 3 validated end-to-end against real data and confirmed pushed and live (verified at the start of Session 15.2b).
 Items 4-5 are diagnostics/decisions, not builds — no validation checkboxes apply; see SESSION_LOG.md.

---

Session 15.2b — Team Volume Modeling: History Weight + Sigma Propagation ✅ Complete, one piece shipped and one correctly rejected (2026-08-15/16)

Prerequisites: Session 15.2 complete (confirmed pushed and live before this session began — see corrected note above).

Trigger: two real, quantified findings from Session 15.2's diagnostics, both in the same root-cause area (team-level volume modeling), both judged too large to build without proper backtesting in that session. User's explicit call to combine them into one dedicated session rather than open a third.

Part 1 — opponent run-defense strength, shipped: the team-volume "with_history" rush regression gains a fourth term (the upcoming opponent's own recency-weighted carries-allowed), fitted alongside the existing three. Probed on real, held-out 2022-2024 data across four rotated holdout splits (t = 2.34 to 3.71 every time) before building, then re-confirmed on the model's own actual production convention (train 2014-17, test 2018-21: t = 3.48, R²_oos 0.0677→0.0728). A real data trap was caught and fixed during validation: `games.csv` still carries era-accurate team codes for relocated franchises (STL/OAK/SD) while the stats feed retroactively relabels every season with the current code (LA/LV/LAC) — without normalizing, every historical Rams/Raiders/Chargers game would have silently failed to join its Vegas line. Built into `fit_volume_prior.py`, `volume_prior.py`, `statline_model.py`, `build_projections_statline.py`; validated end-to-end against a real working copy of the full dependency chain, not just standalone probes. Refit and shipped for both sites — DK clean on the first run (rush `opp_rush_allowed` t=+4.81); FD initially failed on a command mistake (an 8-season fit-seasons range copied from DK's convention without checking FD's real data availability — FD has only one real matched historical season, 2021, a known pre-existing limitation, not a new one), corrected to the documented single-season FD convention and succeeded (t=+2.08, role slope reproduced exactly: +0.6732, t+59.59, matching the original Session 14.x fit). Both `data/volume_prior_dk.json` and `data/volume_prior_fd.json` pushed and confirmed green in real GitHub Actions runs, both sites.

Part 2 — sigma propagation, investigated and correctly NOT shipped: built a real, measured team-shock calibration (`fit_statline_variance.py`'s new `fit_team_shock()`) — residual SD and a REAL teammate pass-through slope per component, found via a direct regression on real player-level data (not assumed): 0.74-0.76 across pass/rush/recv on the full 8-season fit (t = 28-60), confirming teammates' real volumes genuinely do move together beyond what each player's own independent variance already explains. Built the mechanism into `statline_model.py`'s `simulate()` — one correlated shock per (team, component) per simulation, shared by every player on that team, sized to the measured slope. A rigorous coverage backtest on 1,062 real held-out 2022-2024 team-weeks then showed the mechanism makes things WORSE, not better: today's independent draws already land close to real team-total variance (84.5% actual coverage of a nominal 80% interval, before adding anything), and adding the shock at ANY scale pushed coverage further away (up to 92% at full scale) — a grid search over the shock's scale factor found no value between 0 and 1 that improved on doing nothing. Root cause: this isn't a magnitude problem fixable by scaling down — summing any real positive correlation on top of an already-adequate baseline can only inflate the sum's variance further, never reduce it. A correct fix needs `fit_volume_dispersion()`'s own `r` parameter recalibrated NET of team-level variance, jointly with the correlation, not a shock added beside an unchanged `r` — genuinely bigger scope than this session's plan. `simulate()`/`_draw_volume()` reverted to their original, unmodified form (confirmed byte-identical apart from a documentation note explaining the rejection). `fit_team_shock()` itself was kept and shipped — real, validated measurement, just not yet consumed by anything live. Deferred to new Session 15.2c below.

Files: scripts/fit_volume_prior.py, scripts/volume_prior.py, scripts/statline_model.py, scripts/build_projections_statline.py, scripts/fit_statline_variance.py, data/volume_prior_dk.json, data/volume_prior_fd.json, data/statline_variance.json. Full decision-by-decision detail in SESSION_LOG.md.

Validation:

 Part 1: probed on real held-out data before building (four rotated splits, then the production convention itself); validated against the real edited code end-to-end, not simulated; refit and confirmed green in real GitHub Actions, both sites.
 Part 2: real measurement validated (teammate pass-through regression, t = 28-60); mechanism built and then validated AGAINST rejection via a real 1,062-team-week coverage backtest — the validation step doing exactly the job it exists to do, catching a real over-correction before it shipped.

---

Session 15.2c — Team-Level Volume Correlation, Correctly Scoped ✅ Complete (2026-08-16)

Prerequisites: Session 15.2b complete. `data/statline_variance.json` already carried the real, measured team_shock numbers (residual SD + pass-through slope, all three components) this session used as its starting point — no new measurement pass was needed before design work began.

Trigger: Session 15.2b's own finding — a correlated team-level volume shock, added beside the existing independent per-player `r` parameter, is proven (real 1,062-team-week backtest) to push team-total calibration further from nominal at every scale tested, not closer. The real teammate correlation this was meant to capture (t = 28-60, all three components) is genuine and still needed a home; it just could not be an additive add-on to an unchanged `r`.

Purpose: `fit_volume_dispersion()` (fit_statline_variance.py) fits each player's own negative-binomial `r` against his real week-to-week variance around his OWN season average — a quantity that already, apparently, bakes in enough real-world team-context swings that summing several teammates' independent draws lands close to real team-total variance on its own. Adding correlation on top of that unchanged `r` could only inflate the sum further. The fix: recalibrate `r` net of the team-level share it already absorbed, then add a correlated shock sized to that share.

What shipped: `r` decomposed per (position, component) using fit_team_shock()'s own regression residual (real team-level share ranging 26%–59% across six pairs). WR/rush excluded — its team-level share came out negative on real data (pooled rush slope doesn't fit WR gadget-play volume; a football-knowledge call, confirmed with the user). The shock itself needed two corrections before it could be added back without over-covering: an analytical `sqrt(r/(r+1))` term cancelling a real negative-binomial mixture-variance inflation (verified numerically), and an empirical scale factor (0.70, found by grid search against a real 2022-2024 held-out coverage backtest, landed on independently three separate times, once per component). `statline_model.py`'s `simulate()` now draws one shared shock per (team, component), correlating teammates' volumes for the first time — replacing full independence, decision #15's original assumption.

Files: scripts/fit_statline_variance.py, scripts/statline_model.py, data/statline_variance.json. Full decision-by-decision detail, exact backtest numbers, and the real-slate validation comparison are in SESSION_LOG.md.

Validation:

 Conditional-r decomposition and the WR/rush exclusion both probed on real 2014-2021 data before building, then confirmed to reproduce exactly once wired into production code.
 Coverage backtest run on genuinely out-of-sample 2022-2024 data (not the 2014-2021 fit window) at three stages — baseline, decomposed r alone (confirmed under-covers, proving real variance was removed), decomposed r plus the fully-corrected shock (landed within 1-4 points of nominal 80%/50% on all three components, vs. baseline's own gaps).
 `python3 -m py_compile` clean; functional tests confirmed real correlation for included pairs, none for the excluded pair, zero-mean shock (no bias to any projection), and graceful degradation on an artifact missing team_shock.
 300 real held-out team-weeks run through the actual shipped `simulate()` function with no errors.
 Real GitHub Actions run (manual trigger) green.
 Full pipeline re-run end to end on a real live slate (dk_classic_wk1_091326 / fd_classic_wk1_091326) in the user's own environment; old-vs-new final_projection and sigma compared directly — median projection change $0.00, median sigma change ~-0.1%, no drastic differences, every meaningful mover explained.

This also resolves Session 15.2b's own carried-forward "Mechanism 3" item (the simulator previously treated team-volume prediction mu as a perfectly-known constant) — the shared shock mechanism built here is that fix. Session 15.2 (opened across 15.2/15.2b/15.2c) is now fully closed.

---

### Session 15.3 — Pre-Season Deep Dive: Ownership, Plus a Real-Deployment Debugging Chain ✅ Complete (2026-08-16)

Prerequisites: none blocking — started independent of Session 15.2, same user call as that session's card.

Trigger: same as Session 15.2's card — the ownership half of the original open-ended deep-dive ask.

Opened as a scoping pass against real 2026 data (the real Week 1 Classic slate and the one real preseason Showdown slate available at the time) and turned into ten real, validated fixes across six files once the real NE@SEA season-opener Showdown slate was run through the pipeline for the first time with `current_slate.json`'s `season` field finally correct. Each fix was found by running real data, not by reading code, and several were only found because fixing the previous one exposed the next: a Showdown DST Vegas-line mismatch on anomalous-schedule slates (`build_projections_statline.py`, `dst_model.py` decision #24); a `current_slate.json` season-field bug that had silently defeated the model's own Week-1 carryover design on every real 2026 build to date, found while chasing a min-priced-player ownership complaint (`statline_model.py` decision #19, made the season correction safe); three more missing-file crashes surfaced one real GitHub Actions run at a time once the season field was corrected (`projections_matchup.py`, `ingest_salaries.py`, `status_check.py`); a true-Week-1 regression in the session's own first ownership fix, where every skill player showing zero current-season participation got punished relative to defenses that never had a participation concept at all (`ownership_heuristic.py` decisions #8 and #9); the value-ratio blowup that decision #9 correctly re-exposed, fixed with a salary floor on the two ownership features that broke down at a slate's price minimum (`ownership_heuristic.py` decision #10); and, found immediately after, a real projections-layer bug where multiple same-team Showdown QBs saturated a Classic-fit price-to-share curve simultaneously, producing a near-even split across a real team's whole QB depth chart instead of concentrating volume on the real starter (`statline_model.py` decision #20, composing with rather than replacing an existing normalization fix from an earlier session). A real integer-overflow bug was caught and fixed during decision #20's own validation before it shipped. Full decision-by-decision detail, exact before/after numbers, and the real-data validation for each fix are in SESSION_LOG.md.

Files: scripts/build_projections_statline.py, scripts/dst_model.py, scripts/statline_model.py, scripts/ownership_heuristic.py, scripts/projections_matchup.py, scripts/ingest_salaries.py, scripts/status_check.py, data/current_slate.json (user-applied season correction).

Validation:

 Every fix designed and validated against real, live 2026 data, not synthetic test data — the real Week 1 Classic slate and the real NE@SEA Showdown season opener.
 Each fix regression-checked against a real, normal-case comparison before being confirmed safe (real Classic DST, 26 real Classic teams byte-identical, a synthetic mixed-participation pool, real Classic top-15 and cheapest-DST-tier, and an isolated real-data before/after confirming zero effect on RB/WR/TE).
 python3 -m py_compile clean on every modified file.
 Every fix pushed and confirmed via real GitHub Actions runs, including three genuine real-run failures diagnosed from real Actions logs and fixed in sequence, not just local validation.
 Final state confirmed by the user directly against the real, live optimizer UI: no remaining flags.

Known issues deferred: defense still sits modestly atop real Captain ownership on Showdown (~6%, down from dominant pre-fix) — no feature yet captures "ceiling relative to cost," a future design question, not urgent. Session 11.1 (ownership constant retuning against real logged data) remains fully blocked pending `data/ownership_actual_log.csv`, now with four more constants on its eventual list. This session's own "Known Deferred Validations" note below describing `current_slate.json` as a placeholder is now stale (see that section).

This closes the original open-ended projections+ownership deep-dive ask opened across Sessions 15/15.2/15.2b/15.2c/15.3.

---


### Session 16 — Per-Player Exposure Override + Thumbs Up/Down Projection Nudge ✅ Complete (2026-08-21)

Prerequisites: none blocking — a pre-season, off-cycle session (Sept 9 regular-season start still the gate on Sessions 9.x/11.x), triggered by Greg's real use of the PGA optimizer surfacing two commercial-optimizer functions the NFL pipeline didn't have yet.

Trigger: Greg's explicit ask to scope, then build, both in the same session: (1) a per-player override on max exposure, alongside the existing shared `--max-exposure` default; (2) a thumbs up/down vote that nudges a player's projection for one build without overwriting the real, pipeline-calculated number.

Feature 1 shipped as `--player-exposure PLAYER_ID:FRACTION,...`, layered on top of the existing exposure-cap mechanism (Session 3.2) rather than replacing it — a named player uses his own ceiling, everyone else keeps using the global default. Locking a player while also giving him an override is a hard, upfront error (a lock already means 100%). Confirmed Showdown already tracks a player's exposure as one combined count across his CPT/FLEX rows (pre-existing, unchanged), so the override follows that same convention automatically. A related, deliberately-declined third idea — a minimum-exposure floor tied to a thumbs-up, so a truly favored player is guaranteed at least some lineups — was scoped and talked through with Greg but not built: it's a strictly weaker, redundant version of the existing Lock feature, and would override the solver's real signal without adding genuinely new information. Not on the roadmap; Lock remains the tool for that.

Feature 2 shipped as `--thumbs-up`/`--thumbs-down` (plain player_id lists), a fixed ±10% multiplier for one build only. Went through a real mid-session design correction: the first version multiplied `final_projection` directly, which would have shown a flagged player's boosted/reduced number in the output CSV and every downstream total instead of his real one. Rebuilt to route through the same `optimization_projection` seam `--randomization-pct` already established — a solver-input-only adjustment, `final_projection` and `sigma` both untouched, verified directly against real output. The ±10% multiplier itself was empirically probed (not guessed) against the real, live Week 1 FD Classic pool: ran the real 20-lineup solver at several boost levels against three real fringe players (RB/WR/TE) and read off the resulting exposure counts before settling on 10% as the smallest round number that reliably produced a real, non-trivial move without maxing out the exposure cap. `THUMBS_UP_MULTIPLIER`/`THUMBS_DOWN_MULTIPLIER` are FLAGGED ARBITRARY, same status as this project's other real-but-unfit constants.

Two real UI bugs found by Greg after using both features live, both fixed same session: the global Max Exposure field had no listener telling the per-player placeholder text to refresh when it changed; and the per-player exposure input was too narrow to display "100" on desktop (rendered as "10") due to browser spinner-arrow rendering differences between desktop and mobile.

Files: scripts/optimizer.py, .github/workflows/run_optimizer_dispatch.yml, cloudflare_worker/optimizer_api/optimizer_api.js, dfs_optimizer_frontend/index.html. Full decision-by-decision detail (#48-55), the exact real-data probe numbers, and the mid-session design corrections are in SESSION_LOG.md.

Validation:

 Every mechanism tested directly against real, live data (the real Week 1 FD Classic pool and the real NE@SEA DK Showdown pool), covering both features across classic/Showdown and single/multi-lineup modes, plus every conflict/edge case (lock+override conflict, thumbs-up/down overlap, unknown ids, exposure with no --n-lineups, thumbs+randomization composition).
 Confirmed directly in real output that a flagged player's reported projection is always his real number, never the adjusted one, including when selected into an actual lineup.
 python3 -m py_compile / node --check / YAML parse clean on all four files; index.html id cross-reference clean.
 A realistic dispatch payload run through the actual arg-builder logic end-to-end into the real optimizer.py against real data.
 Two real UI bugs found via Greg's own live use, fixed and re-validated same session.
 Not yet done: a from-scratch confirmation through the actual live deployed site (dispatch → Worker → real GitHub Actions run) the way past sessions (e.g. 12.1) closed out — Greg has informally confirmed both features work live, but that was UI spot-checking, not a fresh end-to-end Actions run trace.

A portable handoff summary of both features' architecture, the pitfalls found and corrected, and what needs re-deriving per sport (the ±10% multiplier is NFL/DK/FD-specific, not portable as a number) was written separately for Greg to bring into `DFS_Optimizer_NHL` and `DFS_Optimizer_PGA` — not part of this repo.

---

## Ad Hoc Sessions — Pre-Season Readiness Assessment Findings (2026-09-10)

Not part of the original Phase numbering above. Opened from a deliberate, slow, one-area-at-a-time readiness review (projections, then ownership, then lineup construction/optimizer tuning) three days before the real 2026 Week 1 Sunday slate, done as pure assessment — no code changed during the review itself. Each card below is a finding from that review, scoped into its own session so it can be picked up independently, in whatever order the real calendar allows. Numbered A1-A5 (not continuing the Session N sequence above) specifically so they never collide with an in-progress or future Phase session number.

### Ad Hoc Session A1 — Injury/Active-Status Pipeline Emergency Fix
**Status:** ✅ Complete (2026-09-10) — root cause found and fixed, `STATUS_MAP` gap fixed, real Week 1 pull/apply run against all 7 committed slates, deferred-validation entry closed. See below for what the real root cause turned out to be (not ESPN, not rate-limiting).

**Prerequisites:** none blocking — should run before or immediately alongside Week 1 itself, not deferred behind anything else on this list.

**Trigger:** found during the projections readiness review. Two real, confirmed problems, live right now:
1. No `output/player_status_*.csv` has been committed since **2026-09-03**, even though `current_slate.json` was updated that same day to point at the real Week 1 slates, and multiple `full_refresh_scheduled`/`full_refresh_dispatch` GitHub Actions runs have completed successfully since then. The ESPN roster-injuries endpoint itself was confirmed live and working (hit directly during the review — real, current Week 1 2026 data, e.g. Patrick Mahomes genuinely "Questionable" as of 2026-09-08). The failure is somewhere in the CI path specifically, not the data source, and could not be root-caused further without the actual GitHub Actions run logs.
2. A real, confirmed `STATUS_MAP` gap in `scripts/status_check.py`: ESPN is returning a raw status string `"Suspension"` (6 real Week 1 2026 players — James Pearce Jr., Phidarian Mathis, Cam Taylor-Britt, Jeshaun Jones, Brock Rechsteiner, Dorance Armstrong) that isn't in `STATUS_MAP`, tripping the script's fail-loud exit. Present since at least 2026-08-19; does not fully explain finding #1's exact Sep-3 cutoff, but is a confirmed, independent bug regardless.

Also separately confirmed via ROADMAP's own "Known Deferred Validations" section: **the OUT/DOUBTFUL zero-out mechanism has never been cross-checked against a real regular-season game-day designation** (deferred at Session 5.1, never revisited since — SESSION_LOG.md's own log ends at Session 16, 2026-08-21, with no later re-validation entry).

**Scope:**
1. Get a real GitHub Actions run log for a recent failed/no-op `status_pull` step and find the actual CI-side failure (rate limiting on ESPN from the runner IP, a dependency issue, an unhandled exception not reproducible locally — the review could not access Actions logs to narrow this further).
2. Add `"suspension": "OUT"` (or the correct real-world mapping) to `STATUS_MAP` in `scripts/status_check.py`.
3. Once fixed, do one full manual `status_check.py pull` + `apply` pass against the real Week 1 slate(s) and manually spot-check 3-4 known real injury situations against what actually lands in `final_projections_{site}_*.csv` — don't trust the automation blindly on the first real run back.
4. Close (or explicitly re-open with a new date) the long-standing "real OUT/DOUBTFUL cross-checked against NFL.com" deferred validation in this file's "Known Deferred Validations" section, now that a real regular-season game week finally exists to check it against.

**Actual root cause (found via the real Actions log, requested from Greg since no `gh` CLI/token was available in-session):** not ESPN, not rate-limiting, not the `STATUS_MAP` gap. `refresh_data.yml`'s `status_pull` step (and the `team_stats` step right above it) built a `python3 -c "..."` command as a **double-quoted** shell string, then spliced `${{ needs.prepare.outputs.season_week_pairs }}` — literal JSON containing `"` characters, e.g. `[{"season": 2025, "week": 23}]` — directly into it. Bash doesn't allow a literal unescaped `"` inside a double-quoted string; the first `"` in `"season"` closed the outer quote early, and the rest of the JSON spilled out as unquoted/mangled shell tokens. `json.loads` then choked on the corrupted fragment: `Expecting property name enclosed in double quotes: line 1 column 3`. This failed **before any HTTP request was made** — every single CI run, 100% of the time, ever since `season_week_pairs` was introduced (Session 16.x's multi-slate rework) — which is exactly why it worked locally (this project's own `status_check.py pull` was always called directly, never through this shell wrapper) and why the direct-ESPN-hit test during the review looked fine. The `continue-on-error: true` + inner `|| echo "::warning::..."` swallowed the failure completely, so the job still showed green.

**Fix applied:** both the `team_stats` and `status_pull` steps in `refresh_data.yml` now pass `season_week_pairs` through an `env:` var (`SEASON_WEEK_PAIRS`) and read it via `os.environ[...]` inside the Python one-liner, instead of splicing the JSON into the shell string — sidesteps the quoting collision entirely rather than trying to escape it.

**Files touched:** `scripts/status_check.py` (`STATUS_MAP` gap), `.github/workflows/refresh_data.yml` (the actual root cause).

**Validation:**
- [x] A fresh `status_check.py pull --season 2025 --week 23` succeeds locally with the `STATUS_MAP` fix in place — no unmapped-status exit, 606/771 matched (78.6%), OUT: 60, DOUBTFUL: 2, QUESTIONABLE: 23, ACTIVE: 521. CI-side success still needs confirming on the next scheduled/dispatched run now that the workflow fix is committed (the local run validates the script; the shell-quoting fix can only be proven by an actual Actions run).
- [x] `"Suspension"` no longer trips the fail-loud exit (added `"suspension": "OUT"` to `STATUS_MAP`) — the 6 originally-flagged players (Pearce Jr., Mathis, Taylor-Britt, Jones, Rechsteiner, Armstrong) turned out to be non-skill-position players filtered out by `ESPN_RELEVANT_POSITIONS` before ever reaching `STATUS_MAP` on this particular pull, so the fix couldn't be re-confirmed against those exact 6 this session, but the mapping is now correct for the next skill-position player ESPN reports as suspended.
- [x] A real OUT player from a real, current slate is confirmed zeroed in `final_projections_{site}_{slate_id}.csv` after `apply` — run against all 7 real committed Week 1 slate files (DK classic main/early, DK showdown, FD classic main/early/afternoon, FD showdown); every OUT player's `final_projection` confirmed 0.0 via the script's own built-in reload check on every file. Real QUESTIONABLE/DOUBTFUL players (Patrick Mahomes, Zay Flowers, Tua Tagovailoa, Brock Bowers, etc.) spot-checked to confirm flagged-not-zeroed behavior. Closes the Session 5.1 deferred validation — see "Known Deferred Validations" above.
- [ ] Root cause of the Sep-3 CI gap documented in SESSION_LOG.md, whatever it turns out to be.

---

### Ad Hoc Session A2 — Ownership Data Collection Kickoff + Name-Recognition Seeding
**Status:** 🟡 In progress — steps 2 and 3 done (2026-09-10). Step 1 (the actual `log_ownership.py log` run) is blocked until the real Week 1 slate locks and DK/FD post post-lock ownership on the contest results page.

**Prerequisites:** none blocking.

**Trigger:** found during the ownership readiness review. `scripts/log_ownership.py` — the mechanism that logs real post-lock DK/FD ownership so Session 11.1's blend-weight/temperature retuning can eventually fit against reality — was built back in Session 9.3/11.0 (2026-07-28). `data/ownership_actual_log.csv` does not exist: **zero rows have ever been logged**, across every preseason and Madden Sim slate that's happened since. Root cause: `log_ownership.py` is never mentioned anywhere in `DFS_Weekly_Process.md`, so nothing in the actual weekly routine prompts logging it. Separately, `data/name_recognition_flags.csv` — the manual fame/name-recognition ownership bonus — has exactly one row (Patrick Mahomes), explicitly labeled in the file itself as "example only."

**Scope:**
1. After a real Week 1 large-field GPP contest closes, copy its post-lock ownership results into a raw CSV and run `log_ownership.py log` for real, for the first time ever — this is the first data point toward Session 11.1's 4-6 week gate.
2. Add a step to `DFS_Weekly_Process.md` documenting this as a normal part of the weekly routine, so it doesn't lapse again.
3. Spend 15-20 minutes populating `data/name_recognition_flags.csv` with real, current Week 1 judgment calls (known chalk names, hype rookies, big names coming off injury) before lock.

**Files likely touched:** `data/ownership_actual_log.csv` (created), `data/name_recognition_flags.csv`, `DFS_Weekly_Process.md`.

**Validation:**
- [ ] `data/ownership_actual_log.csv` exists with at least one real `regular_season` row after Week 1. **Still open — requires the real Week 1 slate to lock and DK/FD to post post-lock ownership before `log_ownership.py log` can be run for the first time.**
- [ ] `log_ownership.py summary` prints a nonzero data-gate count. **Still open — depends on the row above.**
- [x] `DFS_Weekly_Process.md` has an explicit post-slate ownership-logging step. Added as Stage 6 (2026-09-10), plus a pre-lock reminder to review `name_recognition_flags.csv` under Stage 4.
- [x] `name_recognition_flags.csv` has more than the one placeholder row, with real Week 1 names. Now has 12 rows (Mahomes plus 11 real Week 1 2026 chalk/hype judgment calls, keyed to real `player_id`s off the actual Wk1 main-slate projections file), 2026-09-10.

---

### Ad Hoc Session A3 — Optimizer Saved Presets (Cash / Single-Entry-3Max GPP / MME GPP)
**Status:** ✅ Complete (2026-09-11). Backend (`data/optimizer_presets.json` + `optimizer.py --preset`) and frontend (three built-in presets in the dropdown, including a new Lambda control wired end-to-end through the Worker and dispatch workflow) are both implemented and validated live. Greg ran real click-through builds on both DK and FD for all three presets (Cash, SE-3Max, MME) on 2026-09-11 — all combinations generated successfully. Cash confirmed working mechanically; not being played this week, so no real-money Cash lineup was submitted off it, but the build itself is validated the same as the other two.

**Prerequisites:** none blocking. Independent of A1/A2/A4/A5.

**Trigger:** Greg's ask — one-click saved settings for the optimizer, so building a cash lineup vs. a single-entry/3-max GPP vs. a 20+ lineup MME GPP doesn't require re-configuring every control by hand each time. Scoped against real gaps found during the optimizer review: `--stack-mode` defaults to `none` in both the CLI and the frontend UI (confirmed: the dropdown's default option is "None," and `DFS_Weekly_Process.md`'s own documented example command doesn't stack either), and `--lambda` defaults to `0.0` (pure point-maximization, no cash/GPP risk-shaping) even though a real, measured lambda grid already exists from a 2018-2021 DK backtest (floor-seeking: 0.039-0.188; upside-seeking: -0.003 to -0.095).

**Flag bundles** (lambda values updated 2026-09-10 to A5's Session 10.5b sweep results, replacing the original placeholders):

| Setting | Cash | Single-Entry / 3-Max GPP | MME GPP (20-150) |
|---|---|---|---|
| `--n-lineups` | 1-3 | 1-3 | 20-150 |
| `--max-exposure` | 100% | 100% | 30-40% |
| `--uniqueness` | 0-1 | 2-3 | 1 |
| `--stack-mode` | none | `qb` + `--bring-back` | `qb`/`game` + `--bring-back` |
| `--randomization-pct` | 0 | 0-5% | 15-20% |
| `--lambda` | +0.063 (Session 10.5b: best beat@p44, +0.006 over 0.0, <1 SE, suggestive not conclusive) | +0.063 (Session 10.5b: best beat@p50, but no clear winner over 0.0) | -0.005 (Session 10.5b: best top@p90; positive lambda measurably hurts) |
| `--participation-floors` | default or tighter | default | default |
| `--allow-skill-vs-opp-dst` | off (keep exclusion) | off | off |

**Scope:**
1. ✅ Backend: `data/optimizer_presets.json` (`cash`/`se_gpp`/`mme_gpp`) loaded by `optimizer.py`'s new `--preset` flag — pre-scans `sys.argv` for `--preset` before the parser is built and uses the bundle's values as each flag's `default=`, so any flag also passed explicitly on the command line still overrides the preset (verified both paths).
2. ✅ Frontend: three built-in presets ("Cash", "SE / 3-Max GPP", "MME GPP (20-150)") always populated in the existing `presetSelect` dropdown (`dfs_optimizer_frontend/index.html`) — reuses the pre-existing cloud-preset Load/Save/Delete mechanism, with built-ins protected from being overwritten or deleted. Also added a "Lambda (variance penalty)" UI control that didn't previously exist, wired end-to-end (`ctrlLambda` → dispatch params → `optimizer_api.js` passthrough allowlist → `run_optimizer_dispatch.yml`'s arg-builder → `optimizer.py --lambda`) since presets setting lambda would otherwise be silently dropped on the UI path.
3. ✅ Shipped with placeholder lambda values initially; updated 2026-09-10 to A5's Session 10.5b-validated defaults (cash/se_gpp 0.063, mme_gpp -0.005) in `data/optimizer_presets.json`, the frontend's Lambda field hint text, and the built-in-preset table, replacing the FLAGGED ARBITRARY placeholders.

**Files touched:** `scripts/optimizer.py`, `dfs_optimizer_frontend/index.html`, `.github/workflows/run_optimizer_dispatch.yml`, `cloudflare_worker/optimizer_api/optimizer_api.js`, `data/optimizer_presets.json` (new).

**Validation:**
- [x] Selecting each of the three presets in the real UI and running a build produces a lineup/batch with exactly the intended flag values. Confirmed for all three presets (Cash, SE-3Max, MME) — Greg, 2026-09-11, real click-through, both DK and FD — lineups generated successfully on both sites for all three.
- [x] All three presets tested against a real, live Week 1 slate, both sites (Greg, 2026-09-11) — "everything passed with flying colors." Cash mechanically validated the same as the other two; not being played this week, so no real-money Cash entry was submitted off it.
- [x] Preset values remain easy to update in one place once A5's real lambda numbers exist. Done 2026-09-10 — `data/optimizer_presets.json` is the single source both the CLI and frontend built-ins were updated from.

---

### Ad Hoc Session A4 — In-Week Injury-Driven Role-Change & Questionable/Doubtful Discount
**Status:** 🟡 Mechanism built, unvalidated — the design question is answered and the code is in place; the only remaining gate is a real in-week OUT case, which hasn't occurred yet this season.

**Prerequisites:** A1 (the injury pipeline needs to be reliably producing fresh status data before it's worth feeding into projections). ✅ Done, see A1's own entry above.

**Trigger:** found during the projections readiness review, and already flagged honestly in this project's own code (ROADMAP.md line ~831, `volume_prior.py`'s role-change docstring): the only mechanism that raises a backup's projection when a starter is out is `role_change_participation()`, which compares DFS **salary-implied** usage share against recent-game usage share — i.e. it only works once DK/FD's own pricing has caught up to the news. There is currently no mechanism at all for the classic in-week scenario (a starter ruled OUT Thursday/Saturday/Sunday morning, after salaries already locked) — the backup's price never moves, so nothing reacts. Separately: a merely Questionable/Doubtful starter gets **zero discount** to his own projection today — `status_check.py`'s `apply` explicitly leaves `final_projection` untouched for anything short of OUT, by original design ("flags but doesn't exclude").

**Decisions (Greg, 2026-09-10):**
1. Role-change mechanism: **extend `apply_confirmed_starter_override()`**, not a standalone function. Reuses the already-validated Session 15.2 pattern (real depth chart as the signal, not inferred price) rather than a parallel code path.
2. Questionable/Doubtful discount: **leave unchanged.** `final_projection` stays undiscounted for Q/D — flag-don't-exclude remains the design, players are expected to make their own game-time-decision call. Not revisited this session.

**What was built (this session, unvalidated — see below):**
- `statline_model.load_injury_status(week)` — reads the latest real `output/player_status_{week}_*.csv` from `status_check.py pull` (picked by filename timestamp, same non-fatal-if-missing pattern as `load_depth_chart()`).
- `apply_confirmed_starter_override()` gained an optional `injury_status` param: when a depth-chart #1 has a real `status == "OUT"`, his #2 (same team+position) is boosted the identical way a returning confirmed #1 is boosted — `participation_effective -> 1.0`, every `{comp}_mu` recomputed from `mu_raw` — gated on the SAME established-own-role bar (`hist_share_raw > ROLE_CHANGE_MIN_HIST_SHARE`) so a backup with no real games of his own is deliberately left untouched rather than guessed at. Flagged via a new `role_change_injury_flag` column, kept separate from `confirmed_starter_flag` for traceability. `injury_status=None` (default) is a no-op — existing callers unaffected.
- `build_projections_statline.py` wired to call `load_injury_status(week)` and pass it through when `--confirmed-starter-override` is on; prints the count of injury-boosted backups alongside the existing confirmed-starter count.
- Smoke-tested against synthetic data only (a #1 RB flagged OUT, #2 RB with an established own share correctly boosted; the OUT starter himself and an unrelated player correctly left alone) — this is a unit-level shape check, NOT the real in-season validation below.

**Files touched:** `scripts/statline_model.py`, `scripts/build_projections_statline.py`. (`volume_prior.py`, `status_check.py` untouched — Q/D discount was decided against, and the OUT-zeroing/flagging logic in `status_check.py apply` already does its job unchanged.)

**Validation (still open — this is what keeps this card 🟡 not ✅):**
- [ ] A real, live in-week case (a starter ruled OUT mid-week after salaries locked) produces a visibly higher `final_projection` for the real depth-chart #2, traceable via `role_change_injury_flag`.
- [ ] No regression to Week-1-shaped pools (the true cold-start case, where the confirmed-starter override already has special handling — see `statline_model.py` decision #14/Session 15.2).
- [ ] Confirm `load_injury_status()` actually finds and parses a real `status_check.py pull` output file once one exists for an in-week (not pre-lock) scenario — only tested against synthetic frames this session, not a real file on disk.

---

### Ad Hoc Session A5 — Calibration Sweeps (Lambda Backtest + Ownership Retuning Trigger)
**Status:** 🟡 Lambda half done (2026-09-10) — the backtest sweep itself already ran back in Session 10.5b (2026-07-28) but was never wired downstream; this session closed that gap by carrying its results into A3's presets, the CLI help text, and the frontend. Ownership half still fully blocked: `data/ownership_actual_log.csv` still has zero rows (A2 step 1 hasn't run yet — see A2's card above).

**Prerequisites:** For the lambda half — none blocking, the historical backtest data already exists (2018-2021 DK, 65 weeks, per Session 10.5's probe A3). For the ownership half — A2 must be running and Session 11.1's existing 4-6 real regular-season week data gate must be met (see that card above in this file).

**Trigger:** two separate "the mechanism exists, the final calibration step never ran" gaps found across the lineup-construction and ownership reviews:
1. Session 10.5's mean-variance objective (`sum(mean) - lambda*sum(sigma²)`) has real, derived candidate lambda grids for both cash (floor-seeking) and GPP (upside-seeking) play, but the actual backtest sweep to pick a validated value from each grid was never run — `optimizer.py`'s own `--lambda` help text calls 0.0 "the only defensible production default until that sweep runs."
2. Session 11.1's ownership blend-weight/temperature retuning has been fully blocked since design time on `ownership_actual_log.csv` having 4-6 weeks of real data — a gate that could not even begin until Ad Hoc Session A2 above produces its first real row.

**Scope:**
1. Run Session 10.5's backtest sweep over the existing candidate lambda grids (cash and GPP separately, both sites if data allows) and land on a validated default for each of Ad Hoc Session A3's three presets, replacing the FLAGGED ARBITRARY placeholders there.
2. Once A2 has produced 4-6 real regular-season weeks of logged ownership, run Session 11.1's existing (already-designed, see that card above) regression retuning of `ownership_heuristic.py`'s blend weights and softmax temperature.
3. Not urgent to run early or all at once — the lambda half can happen independently and as soon as convenient; the ownership half is naturally gated by real-season data accumulating over several weeks regardless of when this card is picked up.

**Files likely touched:** new/existing fitter scripts per Session 10.5 and Session 11.1's own cards, `scripts/optimizer.py` (consuming the fitted lambda values), `scripts/ownership_heuristic.py` (consuming Session 11.1's fitted artifact, per that card's existing design).

**Validation:**
- [x] Lambda sweep validated against real held-out data, per Session 10.5's own backtest methodology; resulting values updated into Ad Hoc Session A3's presets. The sweep ran in Session 10.5b (2026-07-28, DK, 2018-2021, 65 weeks); this session (2026-09-10) is what actually carried its results into `data/optimizer_presets.json`, `optimizer.py`'s `--lambda` help text, and the frontend's built-in presets and hint text — previously all still said FLAGGED ARBITRARY despite the sweep having already run.
- [ ] Session 11.1's own validation checklist (holdout MAE improves over baseline, budget constraint still holds, top-5-owned rank ordering correct) — see that card above, unchanged. **Blocked**: `data/ownership_actual_log.csv` has zero rows; requires A2 step 1 (a real Week 1 slate closing and `log_ownership.py log` running for the first time) before this can even begin, then 4-6 real weeks beyond that.

---

### Ad Hoc Session A6 — Dart Exposure Cap (MME per-player floor guard)
**Status:** ✅ Complete (2026-09-13)

**Trigger:** walking a real Week 1 DK MME (20-lineup, `mme_gpp` preset) build in chat, a hand-inspection of the exposure printout found Kevin Austin Jr. — a $3,000 WR3/bring-back filler with `statline_p10 = 0.07` (roughly a coin flip on scoring anything at all) — sitting at 20% exposure (4/20 lineups), purely because he was the cheapest legal filler in several lineups, not for any real correlation reasoning. Re-running with a manually-computed `--player-exposure` override fixed that one player, but required first eyeballing the exposure table and hand-picking the offending `player_id` every time. Greg asked for this to become a permanent, automatic optimizer setting rather than a one-off manual fix.

**What was built:** two new CLI flags, classic slates only:
- `--dart-floor-threshold` (default 1.0) — a non-DST player whose `statline_p10` falls below this is a "dart."
- `--dart-exposure-cap` (default unset = off) — caps every dart-tier player at this fraction of the `--n-lineups` batch, UNLESS he's on this batch's own stack-candidate team (resolved via the same `resolve_stack_candidates()`/decision #33 team-level pool `build_multi_lineup()` already ranks). An explicit `--player-exposure` entry for a player always wins over this flag's computed cap for that same id.

Wired into `data/optimizer_presets.json`'s `mme_gpp` preset only (`dart-exposure-cap: 0.10`, `dart-floor-threshold: 1.0`) — not added to `cash`/`se_gpp`, where 1-3 lineups don't have meaningful "exposure" to spread a dart across in the first place.

**Real design correction made mid-session, not assumed:** the first version also exempted each stack-candidate team's real opponent this week (the bring-back side), on the theory that a low floor there is the correlation trade you're paying for. Testing directly against the real motivating case disproved that: with `--bring-back` on, the solver satisfies its "one opponent-team player" requirement with whichever legal name is *cheapest*, regardless of that player's own floor — so Kevin Austin Jr. himself kept showing up at full exposure even with the cap active, exempted purely for sitting on Detroit's opponent's roster, which is exactly the disguised-filler pattern this flag exists to catch. Removed the bring-back-side exemption entirely. Verified this doesn't collateral-damage a genuine bring-back: Michael Wilson (ARI), the real bring-back piece for a Herbert/LAC stack, has `statline_p10 = 2.40` and clears the floor threshold on his own merits regardless of team, so he was never at risk from the fix.

**Deliberately NOT backtested/swept.** Unlike `--lambda` (Session 10.5b's real historical grid sweep), there's no historical data pipeline for "how often should a near-zero-floor filler appear across an MME batch" — the 0.10/1.0 defaults are a heuristic guard against a concrete, observed failure mode, not a fit/validated constant. Flagged as such in both the CLI help text and the preset file's own comment; a good future retuning candidate once there's a real backtest harness for MME-portfolio-level outcomes (not just single-lineup mean/variance the way Session 10.5's sweep worked).

**Files created/modified:**
- `scripts/optimizer.py` — `compute_dart_exposure_overrides()` (new), two new CLI flags wired through `pdef()` for preset support, merge-into-`player_exposure` logic in `main()` (explicit user overrides always win), Showdown rejection + no-`--n-lineups` NOTE following existing flag conventions.
- `data/optimizer_presets.json` — `mme_gpp` preset gains `dart-exposure-cap`/`dart-floor-threshold`; top comment updated to flag these as heuristic, not swept.

**Validation:**
- [x] Real motivating case fixed and verified: Kevin Austin Jr. (DK, real Week 1 pool) drops from 4/20 (20%) to 2/20 (10%) with the flag on, seed held constant for a clean before/after.
- [x] Verified the fix doesn't touch legitimate correlation: Oronde Gadsden II (Herbert's own LAC stack teammate, `statline_p10 = 0.54`) stays at its natural 7/20 (35%) exposure throughout, both before and after the bring-back-exemption fix.
- [x] DST exemption confirmed structurally necessary and working: every DST's `statline_p10` is a flat 0.0 regardless of matchup quality (the DST sim doesn't produce real percentile bands), so without the exemption the flag would have capped the *best*-matchup defense as hard as the worst; Jaguars DST (the correct matchup play that week) stays at its natural 7/20 throughout.
- [x] Explicit `--player-exposure` precedence confirmed: an explicit `00-0037231:0.25` alongside `--dart-exposure-cap 0.10` produces Austin at 4/20, respecting the explicit 25% ceiling, not the computed 10% one.
- [x] Regression-checked: `--preset mme_gpp` with no dart flags passed and `--preset se_gpp`/`cash` both produce byte-for-byte the same "Generated" summary line as before this session (no `Dart exposure cap:` line printed, `player_exposure` param count unchanged).
- [x] CLI-level validation checked directly: out-of-range value (`1.5`) hard-errors before solving; Showdown slate hard-errors with a clear message; `--dart-exposure-cap` with no `--n-lineups` prints the same-shaped NOTE-and-ignore as `--player-exposure` already does.
- [x] Confirmed working on both sites (DK and FD real Week 1 main-slate pools) and confirmed a CLI-passed value overrides the preset's own default (`0.05` vs. preset's `0.10`), same precedence guarantee every other preset-backed flag already has.
- [ ] Not yet done: frontend UI (checkbox/inputs in `dfs_optimizer_frontend/index.html`) and the GitHub Actions dispatch passthrough (`.github/workflows/run_optimizer_dispatch.yml`, `cloudflare_worker/optimizer_api/optimizer_api.js`) — this session only shipped the CLI/preset layer Greg was directly testing against in chat. Same shape as Session 16's two flags (`player_exposure`-style passthrough key, a numeric input plus a threshold input in the MME settings panel) if/when Greg wants it live in the deployed UI.

---
