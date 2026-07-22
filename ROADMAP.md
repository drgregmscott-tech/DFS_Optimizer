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
**Prerequisites:** Session 1.2 complete (need player_id matching scheme).

**Sites:** Site-agnostic — a player's injury status is the same fact regardless of which DFS site you're building for, so this session's output is shared by both.

**Files touched (created):**
- `/dfs_optimizer/scripts/status_check.py`

**Inputs:** ESPN injury API endpoint (per-team).

**Outputs:** `/output/player_status_{week}_{timestamp}.csv` — columns: player_id, status (OUT/DOUBTFUL/QUESTIONABLE/ACTIVE)

**Build:**
- ESPN injury endpoint integration
- Status filter logic (OUT excludes from optimizer input; QUESTIONABLE flags but doesn't exclude)

**Validation:**
- [ ] Cross-check pulled statuses against NFL.com's official injury report for the same day — must match
- [ ] Confirm OUT players are actually excluded from optimizer output for both sites (run optimizer with a test OUT player, confirm absence in both DK and FD results), not just flagged in a column nobody reads

**Handoff notes to log:** the exact ESPN endpoint URL used (unofficial endpoints can change without notice — note the date last verified working).

---

### Session 5.2 — Scheduling Infrastructure
**Prerequisites:** Sessions 1.3, 2.4, 5.1 complete (this orchestrates all the refresh-able scripts).

**Sites:** Automation needs to trigger the DK and FD pipeline runs separately (different salary files land at different times if the two sites post slates at different points), so the schedule/run log should be able to distinguish which site a given run covers.

**Files touched (created):**
- `/dfs_optimizer/.github/workflows/refresh_data.yml`
- `/dfs_optimizer/cloudflare_worker/scheduled_refresh.js`
- `/dfs_optimizer/logs/automation_run_log.csv` (add a `site` column)

**Inputs:** All prior scripts (this session wires them into scheduled execution, doesn't create new logic).

**Outputs:** Running automation, plus a run log recording actual fire times per site.

**Build:**
- GitHub Actions cron for regular-interval updates (every few hours on game day), run once per site
- Cloudflare Worker + external trigger (cron-job.org) for the critical near-lock window (every 5-10 min in the final hour), aware that DK and FD slates can lock at different times
- For `vegas_odds.py` specifically, this session should implement the cadence already budgeted in Session 2.3's card: Tue-Fri 1x/day, Sat 2x/day, Sunday 1x/hour from 4hrs-1hr before lock, then 1x/15min in the final hour (~121 credits/month, confirmed against the free tier's 500/month cap). This is a different (lighter) cadence than the salary/projection refreshes, since odds move less frequently than player pool/injury status close to lock.

**Validation:**
- [ ] Log actual fire times vs scheduled times over a few days for both sites — confirm GitHub Actions delay is acceptable for non-critical updates
- [ ] Confirm the Cloudflare Worker + external trigger combo fires within 1-2 minutes of scheduled time consistently, for both sites' lock windows

**Handoff notes to log:** observed delay patterns, any failures and how caught/resolved. Note if DK and FD lock times ever diverged enough to matter for scheduling.

---

## PHASE 6 — Preseason Live Dry Runs
*Target: Aug 13-29*

### Session 6.1 — Preseason Week 1 Dry Run (Aug 13-15)
**Prerequisites:** Phases 1-5 all complete.

**Sites:** Run the full pipeline for both DK and FD this week — a site that's never been dry-run isn't proven, regardless of how well its unit tests passed.

**Files touched:** None new — this is an execution/observation session. Fixes get logged as a punch list.

**Inputs:** Live preseason Week 1 slate, both sites.

**Outputs:** `/logs/dry_run_week1_issues.md` (punch list for Session 6.2, tag each issue with which site(s) it affects)

**Build:** Run the full pipeline live end to end, for DK and FD. No real money.

**Validation:**
- [ ] Full pipeline runs start to finish without manual intervention, for both sites (the actual goal of this test)
- [ ] Every failure/manual fix needed is logged, tagged by site
- [ ] Generated lineups' actual results vs projections compared, both sites (expect roughness in preseason — focus on pipeline reliability over accuracy)

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

### Session 7.1 — Basic UI + Hosting Setup
**Prerequisites:** Session 3.2 complete (need a stable lineup output format to build the UI against).

**Sites:** UI needs a DK/FD toggle or selector from the start — retrofitting a site switch after the UI is built single-site is more work than building it in.

**Files touched (created):**
- `/dfs_optimizer_frontend/` (separate repo or subfolder)

**Inputs:** `/output/lineups_multi_{site}_{week}.csv` format (as a contract, not live data yet).

**Outputs:** Deployed site on Vercel/Netlify free tier, connected to purchased domain.

**Build:** Simple frontend (upload/view players, view generated lineups) with a site selector (DK/FD) driving which data set is displayed.

**Validation:**
- [ ] Site loads on the real domain, not just localhost
- [ ] A generated lineup from the backend correctly displays with no data mismatches, for both DK and FD selections

---

### Session 7.2 — UI-Optimizer Integration
**Prerequisites:** Session 7.1 and Phase 3 (all of it) complete.

**Files touched (modified):** Frontend components + a thin API layer to trigger/read optimizer output.

**Inputs:** Live optimizer output.

**Outputs:** Interactive UI controls wired to real backend behavior.

**Build:** Connect frontend controls (exposure limits, stack rules, lock/exclude players) to the optimizer backend, respecting the site selector from 7.1 (e.g. exposure/stack controls should operate on the currently-selected site's lineups, not mix DK and FD data).

**Validation:**
- [ ] Every UI control actually changes optimizer output as expected — test each control individually, for both DK and FD selected

---

### Session 7.3 — Polish & Final Deploy
**Prerequisites:** Session 7.2 complete.

**Build:** Cleanup, mobile responsiveness, final deploy.

**Validation:**
- [ ] Full walkthrough on the live domain from a phone and a desktop browser, no broken states, for both DK and FD views

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

## Notes on sequencing
- Phases 1-3 are strictly sequential
- Phases 4 and 5 can run in parallel, both need Phase 3 done first
- Phase 6 is the real validation gate for everything before it
- Phase 7 can start as early as Phase 3 is stable
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

- **Real Vegas lines for a specific backtest week.** The Odds API's `/odds` endpoint only returns currently-listed games -- it can't retroactively supply real lines for a past week (e.g. 2025's week 10, already played) or a future week too far out for books to have posted lines yet. `vegas_odds.py`'s output for any week outside "currently listed" is necessarily synthetic or absent. **First point this closes for real:** once real preseason games are close enough that books post lines -- Preseason Week 1, Aug 13-15, 2026, per this roadmap's own milestone.
- **Real FD salary data, at all.** Flagged since Session 1.3: DK has a real, year-round CSV source to validate against (Madden Stream contests). FD has no equivalent -- there has never been a real FD NFL export to test `ingest_salaries.py --site fd` against. Every FD validation so far (Session 1.3's 10-row test, Session 2.4's 93-row scaled synthetic file) has used synthetic data built from real DK data, not a real FD download. **First point this closes for real:** whenever a real FD Classic NFL slate first opens for the 2026 season (likely Preseason Week 1, same as above, but confirm -- FD's preseason slate calendar hasn't been checked directly).
- **Session 2.4's full real end-to-end validation, both sites.** Directly follows from the two gaps above -- `build_projections.py` has now been validated mechanically (real DK salaries + real week-10 matchup/baseline data + synthetic FD salaries + synthetic vegas lines, see Session 2.4's log entry), but not with every input being simultaneously real for the same site and the same week. That combination doesn't exist yet for any week. **First point this closes for real:** Preseason Week 1, same as above -- first week where a real salary file (both sites, assuming FD's gap above also closes by then), real matchup-factor data, and real currently-posted vegas lines can all exist for the same slate at the same time.
- **Session 3.3's stacking logic, against real data -- DK closed same day (addendum), FD still open.** Re-run against the real DK Madden Stream pool (`weekly_stats_2025.parquet`, `schedules_2025.parquet`, real `vegas_implied_totals_10.csv`, real `salaries_dk_madden_20260721.csv`) confirmed the full pipeline end-to-end, matched the project's own previously-logged real numbers exactly, and surfaced + fixed a real bug (`rank_candidate_teams`/`rank_candidate_games` didn't check the OPPONENT side had real pool players -- see SESSION_LOG.md's addendum). **Still open:** FD (same pre-existing no-real-FD-data gap as everything else FD), and a full 32-team slate (this real pool only has 6 teams -- Preseason Week 1 is the first point a full-size real slate exists to re-test against).

Until Preseason Week 1: treat Session 2.4 (and by extension anything built on top of it in Phase 3+) as validated for correctness-of-logic only, not for real-world data quality. Re-run Session 2.4's validation checklist in full once real data exists for both sites.

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

