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

**Prerequisites:** Session 8.1 complete (live enough to have real slates running), AND a real published-ownership source identified for at least one site/contest type (see Build below — this is a real open question, not a given).

**Sites:** Log per site — DK and FD price the same player differently, so their real ownership numbers for the same player are never expected to match.

**Files touched (created):**
- `/dfs_optimizer/scripts/log_ownership.py`
- `/dfs_optimizer/data/ownership_actual_log.csv` (grows weekly; columns: site, week, player_id, actual_ownership_pct, estimated_ownership_pct_at_time, source)

**Build:**
- Identify a real source of published ownership data per site. This is NOT solved by this roadmap yet — large-field GPP contests on both DK and FD sometimes have ownership published post-lock by the site itself or by third-party trackers (e.g. tools built on top of contest result exports), but availability, format, and reliability haven't been checked. First real action this session needs to take is confirming what's actually accessible, not assuming a specific source — same "verify before building on it" caution already applied to Vegas odds vendors (see "Notes on odds vendor choice") and FD's salary format.
- Once a source is confirmed, log actual-vs-estimated ownership per player/week/site, alongside the `estimated_ownership_pct` this pipeline produced for that same slate (so error can be computed later without re-deriving it).

**Validation:**
- [ ] Confirm logged actuals genuinely come from a real contest's real ownership breakdown for a spot-check sample (not a synthetic/estimated stand-in) — same "don't trust it until it's verified real" standard already applied throughout this project (see ROADMAP.md's FanDuel validation gap note, the Vegas-lines deferred-validation note, etc.)
- [ ] Confirm the DK/FD ownership numbers logged for the same real player in the same real slate are NOT expected to be equal, and aren't accidentally being logged as if they were (a copy-paste/site-mixup risk given how parallel this pipeline's DK/FD logic already is elsewhere)

**Handoff notes to log:** which real ownership source(s) were actually usable per site — if only one site has a workable source, flag that explicitly rather than letting Session 9.4 assume both sites have equal real data to retune against (same asymmetry this project already tracks for FD salary/matchup data).

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
- [ ] **`refresh_data.yml` team-stats step** — see Known Deferred Validations.

---

### Session 10.5 — Objective + Randomization Rewire (needs 10.3a's sigma)
**Prerequisites:** Session 10.3a (sigma now exists).

**⚠️ What 10.3a hands you, and the one thing it does not (2026-07-26):** `final_projections_{site}_{week}.csv` from `build_projections_statline.py` carries a `sigma` column plus `sigma_source`. That sigma is **idiosyncratic by construction** — every player is drawn independently, so it holds no team-level correlated component, which is the right kind for this card's objective, since the design keeps correlated variance in the optimizer's stacking *constraints* rather than the objective. DST sigma is real but **unconditional** (`3.25 + 0.39 × projection`, measured over 3,952 team-weeks), flagged `dst_measured_unconditional_session_10_4_pending`; conditioning it on the opponent's implied total is Session 10.4's job.

**✅ RESOLVED by Session 10.4 (2026-07-26).** DST sigma is now simulated per defense and conditioned on the opponent's implied total — `sigma_source = dst_simulated_session_10_4`, calibration ratio 0.931 (realized RMSE / mean projected sigma; 1.00 ideal), observed range 5.56–6.78 varying with the matchup rather than with the projection alone. The distributional DST is **on by default**, so this arrives without a flag. Two things to carry into this card: (a) DST sigma is NOT idiosyncratic in the same sense as a skill player's — decision #13 of `dst_model.py` deliberately builds in a within-game latent factor calibrated to a measured +0.301 correlation between a defense's points-allowed bracket and its other components, because independent draws understated total DST sigma by 11%; it is still free of any component correlated with OTHER players' outcomes, which is the property this objective actually requires. (b) A DST's sigma (~6.2) is large relative to its mean (~6.9), so a `λ·sigma` penalty will bite the DST slot harder than any other. Watch for λ driving the optimizer to the cheapest defense.

**Blocker to clear first:** `optimizer.py` selects a fixed column list and **drops `sigma`** on the way to its lineup output. It reaches the optimizer fine; it does not survive it. Carrying it through is the first task of this card.

**Build:** wire per-player sigma into the optimizer objective as `sum(mean) − λ·(idiosyncratic sigma)`, keeping it LINEAR (sigma as a per-player constant, so CBC is retained — no MIQP). Make randomization sigma-proportional and entry-count-scaled (off at single-entry). λ fit from the backtest on a coarse grid, per contest type, selected on realized cash-rate + top-percentile frequency — NOT hand-tuned, NOT a single "optimal" value (the tradeoff curve is the output).

**Validation:**
- [ ] λ=0 reproduces current pure-mean behavior (sanity anchor).
- [ ] λ sweep produces a sensible floor-vs-upside tradeoff curve on the backtest, per contest type.

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
- **FanDuel validation gap:** as of Session 1.3's revision, DK's ingestion path has been validated against real data (DK's Madden Stream contests provide a real, year-round CSV export for format-testing, unlike FD which has no equivalent). FD's ingestion path is validated only against synthetic test data. This should be closed out with a real FD export before Session 2.4/3.1 depend on FD data with full confidence — flag this explicitly in each session's log until it's closed.

## Known Deferred Validations (blocked until a real current-week NFL slate exists)
*Added during Session 2.4. Update this list every session that hits one of these gaps -- it's the single place to check "can this actually be validated for real yet?" instead of re-discovering the same blocker session after session.*

These are all instances of the same underlying problem: several data sources (The Odds API, live DK/FD salary exports) only exist for **games that are either currently live-listed or already happened** -- there is no real historical archive available to us, and no real future-week data exists yet. That means backtesting against a past season (e.g. 2025) and validating against real current data are two different things that can't both be true of the same run.

- **Real Vegas lines for a specific backtest week.** The Odds API's `/odds` endpoint only returns currently-listed games -- it can't retroactively supply real lines for a past week (e.g. 2025's week 10, already played) or a future week too far out for books to have posted lines yet. `vegas_odds.py`'s output for any week outside "currently listed" is necessarily synthetic or absent. **First point this closes for real:** once real preseason games are close enough that books post lines -- Preseason Week 1, Aug 13-15, 2026, per this roadmap's own milestone. **PARTIALLY RESOLVED for BACKTESTING (Session 10.1):** nflverse's `games.csv` carries real historical `spread_line`/`total_line` going back decades, so the backtest harness derives a genuinely real (not synthetic) `vegas_implied_totals_{week}.csv` for any past week using `vegas_odds.py`'s own `implied = total/2 - spread/2` formula (verified: implied totals sum to the game total every game). This closes the blocker for HISTORICAL BACKTESTING only -- the LIVE production gap (The Odds API can't supply a future/current week retroactively, and can't post lines before books do) is unchanged.
- **Real FD salary data, at all.** Flagged since Session 1.3: DK has a real, year-round CSV source to validate against (Madden Stream contests). FD has no equivalent -- there has never been a real FD NFL export to test `ingest_salaries.py --site fd` against. Every FD validation so far (Session 1.3's 10-row test, Session 2.4's 93-row scaled synthetic file) has used synthetic data built from real DK data, not a real FD download. **First point this closes for real:** whenever a real FD Classic NFL slate first opens for the 2026 season (likely Preseason Week 1, same as above, but confirm -- FD's preseason slate calendar hasn't been checked directly).
- **Session 2.4's full real end-to-end validation, both sites.** Directly follows from the two gaps above -- `build_projections.py` has now been validated mechanically (real DK salaries + real week-10 matchup/baseline data + synthetic FD salaries + synthetic vegas lines, see Session 2.4's log entry), but not with every input being simultaneously real for the same site and the same week. That combination doesn't exist yet for any week. **First point this closes for real:** Preseason Week 1, same as above -- first week where a real salary file (both sites, assuming FD's gap above also closes by then), real matchup-factor data, and real currently-posted vegas lines can all exist for the same slate at the same time.
- **Session 3.3's stacking logic, against real data -- DK closed same day (addendum), FD still open.** Re-run against the real DK Madden Stream pool (`weekly_stats_2025.parquet`, `schedules_2025.parquet`, real `vegas_implied_totals_10.csv`, real `salaries_dk_madden_20260721.csv`) confirmed the full pipeline end-to-end, matched the project's own previously-logged real numbers exactly, and surfaced + fixed a real bug (`rank_candidate_teams`/`rank_candidate_games` didn't check the OPPONENT side had real pool players -- see SESSION_LOG.md's addendum). **Still open:** FD (same pre-existing no-real-FD-data gap as everything else FD), and a full 32-team slate (this real pool only has 6 teams -- Preseason Week 1 is the first point a full-size real slate exists to re-test against).
- **Session 5.1's real OUT/DOUBTFUL game-day designations, cross-checked against NFL.com.** ESPN's per-team roster endpoint was pulled live and validated for real (all 32 teams, 919 players, real matching, real zero-out mechanism proven against a real forced-OUT player -- see SESSION_LOG.md's Session 5.1 entry) -- but every real non-empty status found on 2026-07-22 was a long-term-recovery or personal-situation designation, not a game-week one, since no real NFL game exists yet to designate a player in/out FOR. There's nothing real on NFL.com's injury report to cross-check against yet either. **First point this closes for real:** Preseason Week 1, same as the other gaps in this list.
- **Session 5.2's real weekly cron-job.org schedule + `current_slate.json`, both sites.** This one's a configuration gap rather than a data-quality gap -- the automation mechanism itself is fully built and validated (see SESSION_LOG.md's Session 5.2 entry), but the cron-job.org near-lock job (currently a Sunday-11am-CT/every-10-min *template*, approximating a typical 1:00pm ET early-slate lock) and `current_slate.json` (currently a season-2026/week-1 *placeholder*) both need hand-updating to whatever Preseason Week 1's real slate/lock times turn out to be -- there's no real value to set until that week's schedule is actually known. **First point this closes for real:** Preseason Week 1, done alongside Session 6.1's live dry run (see Session 6.1's card) -- not a separate session, just the same checkpoint.
- **Session 7.2's UI-Optimizer Integration, FD side.** DK side fully live-validated against a real Madden Sim slate this session (every control individually confirmed working on the real deployed site -- see SESSION_LOG.md's Session 7.2 entry). FD gets the exact same "no real data to point it at" gap as everything else FD in this list -- the frontend's controls, dispatch/poll flow, and instant-preview solver are all site-agnostic code (same `SITE_CONFIG`-driven logic DK and FD already share throughout this project), so this isn't expected to surface anything new once real FD data exists, but it hasn't been exercised live. **First point this closes for real:** Preseason Week 1, same as the rest of this list.
- **Session 7.3's "Download Lineups" DK/FD-import feature, FD side.** DK side fully validated against a real user-uploaded `DKEntries.csv`, including two real bugs found and fixed via that live testing (see SESSION_LOG.md's Session 7.3 entry). FD's `site_id_col` (`ingest_salaries.py`'s `SITE_CONFIGS["fd"]`, currently `"Id"`) is a documented guess based on FD's standard column layout, never confirmed against a real FD export -- inherits the same unverified status `required_columns` has carried for FD since Session 1.3. Until a real FD entries/salary file exists, treat FD's download-import output as unverified, not just untested. **First point this closes for real:** whenever a real FD Classic NFL slate first exists, same as the FD salary-data gap below.
- **Session 7.3's Game Stack QB requirement (decision #30) and multi-team/multi-game stack pinning (decision #32), full-size slate.** Both validated end-to-end against real data, but the only real test pool available this session (the DK Madden Sim slate) has just 6 teams and exactly one real two-sided game -- multi-game rotation specifically was only validated at the candidate-resolution level directly, not through a full multi-game solve, since a second real game wasn't available to solve against. **First point this closes for real:** Preseason Week 1's full 32-team slate, same as the other "thin test pool" gaps already tracked below.
- **Session 7.3's mobile responsive CSS fixes and several other late-session UI changes, live re-confirmation.** Fixed based on a real user-reported bug (Pixel 9 Pro XL layout issues), validated by static structural checks (syntax, DOM-id cross-reference, balanced grid areas) but not yet re-confirmed working live on that same device, nor has the Minimum Salary slider, the new stack team/game chip pickers, or the partial-build warning banner been exercised live yet. See SESSION_LOG.md's Session 7.3 entry, "What's validated live vs. sandbox-only" section, for the full breakdown of what has and hasn't been user-confirmed.

Until Preseason Week 1: treat Session 2.4 (and by extension anything built on top of it in Phase 3+) as validated for correctness-of-logic only, not for real-world data quality. Re-run Session 2.4's validation checklist in full once real data exists for both sites.

- **FD's salary-anchor curve cannot be fit, and is now BLOCKED rather than deferred by assumption (Session 10.2).** This one is different in kind from the other FD gaps in this list: it isn't "untested," it's "demonstrably not fittable on the data that exists." With only 2021 matched (RotoGuru has no FD before 2011 and nothing after 2021, and only 2021 was matched in Session 10.0), QB bins to 4 knots and the defense to 3, and the top-endpoint extension hits its cap at **QB, RB, WR and TE simultaneously** — WR's top bin mean is $7,045 against a $10,200 salary maximum, a $3,155 gap the extension cannot honestly span. A capped top means expensive players compress onto a near-flat anchor, which is precisely the region that decides lineups. `fit_salary_anchor.py` now treats both conditions as hard errors before writing anything, and `data/salary_anchor_fd.json` was deleted so a stale unfit curve can't be silently picked up. Note this also exposed and fixed a real hole in the fitter's own guard — it counted ROWS, not BINS, and let a 3-knot curve through twice. **First point this closes for real:** whenever enough real FD Classic slates accumulate to fit against — which for FD means live exports from Preseason Week 1 onward, not the historical bootstrap, since the bootstrap's FD coverage is what failed here.

- **`refresh_data.yml` needs a current-season team-stats pull (opened by Session 10.4, and the workflow edit can be made NOW).** A live-automation gap, not a data-quality one. Because the distributional DST is the DEFAULT, `data/team_stats_{season}.parquet` is an input to every projection build including the unattended GitHub Actions refresh, and nothing in that workflow pulls it.

  **The pre-kickoff wrinkle, verified 2026-07-26:** nflverse does NOT publish `stats_team_week_{season}.parquet` until that season's first games are played — the 2026 asset 404s today while `games.parquet` already carries all 272 scheduled 2026 games with null scores. So the refresh step cannot simply pull the current season and assume success. `dst_model.py`'s decision #19 handles this: a missing current-season file is legitimate when `season_has_started()` is False (no game has a score yet) and a hard error once it is True, so the two states are told apart by data rather than by a calendar guess. Verified end-to-end — 2026 week 1 builds 32 defenses on 2025 carryover alone, projections 6.62–7.89, sigma 5.92–6.22.

  **What this means concretely:** `data/team_stats_2025.parquet` is a REQUIRED commit for the 2026 season (it is the carryover source), and `team_stats_2026.parquet` only becomes fetchable after Preseason/Week 1 games are played. The workflow step must tolerate a 404 on the current season without failing the run.

  **Fix (doable now):** add a step to `refresh_data.yml` ahead of `build_projections.py` that pulls the current season's team stats and does not fail the job on a 404, plus commit `team_stats_2025.parquet`. **First point the current-season half matters for real:** once 2026 games have actually been played — Preseason Week 1, alongside the other Session 6.1 checkpoint items.

- **FD's DST model is unverified end-to-end, but is NOT blocked (Session 10.4).** Worth distinguishing from the FD salary anchor, which is *demonstrably not fittable* on available data. The DST model's FD exposure is much smaller: the scoring table is verified against real graded FD 2021 actuals (87.5% exact, mean bias −0.178, the same residual shape as DK), the model is site-parameterised at every call site with no branching on site, and `dst_model.json` is fit on stat lines and game outcomes rather than on anything site-specific — so unlike the anchor there is nothing here that *cannot* be fit for FD. What has never happened is a real FD Classic export running end-to-end through it. Note this compounds with the FD DST column-name bug below, which would bite first. **First point this closes for real:** whenever a real FD Classic export first exists.

- **FD DST projection path reads the wrong column name (found during Session 10.0).** `build_projections.py`'s `build_dst_projections()` reads `salaries["AvgPointsPerGame"]` for BOTH sites, but a real FanDuel export names that column `FPPG`, and `ingest_salaries.py`'s `load_raw_salary_csv()` doesn't rename it — so FD's DST path would `KeyError` or silently null on a real FD export. Not fixed in Session 10.0 (separate decision about FD's real column contract, still unverified — same root as the standing FD gaps above). Session 10.0's RotoGuru FD files emit `AvgPointsPerGame` so the bootstrap/harness aren't blocked, but the real-FD-export gap is open. **First point this closes for real:** whenever a real FD Classic export first exists, alongside the other FD gaps.

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

