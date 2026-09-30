# HANDOFF — WK3 postmortem §4 (written Tue 2026-09-29, for the next chat)

**Read first:** `SUBAGENT_BRIEF.md` (repo root; every subagent prompt must start with "read SUBAGENT_BRIEF.md" and quote the
user's premise verbatim), `WK3_POSTMORTEM_CHECKLIST.md` (§4 outcome section at the bottom), this file.
Goal (user, RECURRING): make the system measurably MORE ACCURATE vs commercial models (FC) using the 5 yrs of FC history. Missing all
slates 3 weeks running is a bad system, not bad luck. No checklist-ticking, no weeds, no assumed causes, no "wait for more weeks" where
history can answer. User builds lineups in the **frontend UI**, whose data comes from **GitHub Actions** (`refresh_data.yml`).
Wk4 locks **Sun 2026-10-04**. FC subscription is DEAD (trial lapses 10/2) — FC history is training/comparison data only.

## State of the repo
- **Committed (74e85e8):** ownership v2 + DST model wired in (`scripts/ownership_v2.py`, `data/ownership_v2_dk_{linear,dst}.json`,
  `DFS_OWNERSHIP_V2=0` turns off; keeps `est_own_live_old` / `est_own_v2_only`), early-season salary blend code, Wk3 real ownership +
  results logged (`data/ownership_actual_log.csv`, `projection_error_log.csv`), analysis scripts, inactives tooling
  (`scripts/availability_diff.py`, `scripts/inactives_timing_log.py`), checklist §4 outcomes.
- **UNCOMMITTED (needs committing after CI-parity agent reports):** QB recalibration in `scripts/build_projections_statline.py`
  (`_apply_qb_recal`, `--qb-recal/--no-qb-recal`, `qb_recal_delta` column; QB skip added to early blend for wk>=3),
  `SUBAGENT_BRIEF.md`, this handoff, a small checklist edit.
- **NOT tracked (git-ignored, FC-derived):** blend config `data/fc_history/derived/projection_v2/early_season_blend_config.json`
  (weeks 1, 2, 7+; wk6 removed; QB 7+ zeroed) and QB recal config `data/fc_history/derived/qb_depth/qb_recal_candidate_2026-09-29.json`.
  **On Actions these are missing => blend + QB recal silently no-op in the UI path.** User said FC-derived coefficients are fine to commit.
- Never commit: `analysis/*/RESULTS.md` from FC analyses, `data/nflverse_usage/`, rebuild folders, parquet frames,
  `analysis/classic_diag/wk3_sigcov_c_roster_slots.csv` (2.5M lines).

## Two agents were RUNNING when this was written (check for their results first)
1. **CI-parity check** -> `analysis/ci_parity/RESULTS.md`. Moves both configs to a tracked path, updates defaults in
   `build_projections_statline.py`, reproduces the `refresh_data.yml` build/apply sequence from a clean checkout, confirms v2 / blend / QB
   recal actually run (not silent fallback), confirms worker/frontend still parse new columns, and that v2's inputs (weekly stats,
   prior-week outputs, ownership log) exist in CI before the build step. Ends with the exact commit file list. **Commit only after this.**
2. **Lineup-level replay** -> `analysis/lineup_replay/RESULTS.md`. Old (all 3 switches off) vs new inputs through the full optimizer on
   Wk3 (+Wk1-2 where possible), scored vs actual points and real contest cash lines; plus construction vs what cashed in FC history.
   Answers: do better inputs -> better lineups; single most valuable construction/selection fix.
If agents are not done/lost, relaunch from the descriptions above (prompt template: brief file + verbatim user quotes + restate question).

## What was established this session (details in checklist §4 and local RESULTS.md files)
- **Model vs FC (`analysis/model_vs_fc`):** projections ~parity or better vs FC (hist MAE 6.34 vs 6.69; cheap WR/TE also better). Ownership
  was the big gap (FC pre-lock corr .83 vs ours .47 on 2021-23). Cheapest-*viable* DST is under-owned by us (7.5 vs field 11.3).
- **Ownership v2:** trained on realized ownership (not FC-as-teacher), beats live on history 5/5 seasons; Wk3 replay corr .889 / MAE 1.19
  vs live .863 / 1.40; DST real-top-in-top3 3/3 vs 0/3. Total classic ownership now ~886 not 900. FC Own not reproducible from public
  pre-lock inputs (ceiling .66). Keep scoring `est_own_v2_only` vs `est_own_live_old` vs realized each week (Wk4 = first fully OOS week).
- **Early-season blend:** Wk1 big firm gain (MAE 6.17->5.54, 4/4 seasons); Wk2 tiny; Wk3-5 fail; Wk6 zeroed; Wk7+ small gain (+0.066) shipped
  but fit WITHOUT props. **TODO before Wk7: re-check Wk7+ weights vs real Wk4-6 results with props.**
- **QB:** the "FC beats us at QB from Wk3" gap was mostly a test-engine artifact (no injuries/QB1 guard); real residual is top-QB
  compression. QB recal (wk3+, top QB per team, proj>=8): hist held-out MAE 6.21->5.99 (5/5 seasons); 2026 Wk3 CI wide, direction OK.
  QB ownership shifts from top QBs to cheap starters -> re-check ownership after Wk4.
- **Inactives:** FC's apparent edge was largely our test having injuries off. Remaining: backup-QB/depth DNPs are small after the QB1
  guard; a DNP predictor works (AUC .83) but adds ~0 accuracy => not wired. Questionable weighting available, user judges it too variable;
  **human inactives check Sunday morning is the real solver.** No paid X. Sources: ESPN per-game rosters, Sleeper (light use only).
- **WR/TE target-share/snap/route model:** real (-9% target MAE) but ~0.03 DK-pt MAE => not shipped. Props already applied at 0.5.
- **Ruled out (don't retry):** flatter logistic scale, mid-tier x1.3-1.45, history-tuned joint layer, rank features, min-price DST flag,
  FFC floor a=0.7 (also argues against the Sunday rule's blanket "use higher of model/FFC"). Inconclusive: FFC cliff removal, mid x1.15.

## Open items, in order
1. Read agent results (above); commit per CI-parity file list (configs to tracked path, QB recal, brief, handoff). Then re-verify a Wk4 build
   the way Actions does it. Make sure last week's stats are ingested BEFORE the Wk4 projections build (v2 needs them).
2. **Sunday Wk4 morning:** run `python scripts/inactives_timing_log.py --season 2026 --week 4` (logs when ESPN/Sleeper first show
   inactives); user does human inactives check; run `status_check pull` + apply, `availability_diff.py`.
3. **Mon 10/5:** log Wk4 real ownership + results (contest_results *_full.csv %Drafted, summed per player incl. FLEX; see
   `scripts/log_ownership.py`, `log_results.py`; wk3 raw files in `data/` show the format), score v2 vs live vs realized; re-check QB ownership.
4. **Cheap WR/TE ownership root cause** (v2 corr .65 vs FC .81): targeted look at role / vacated-usage features; not yet understood.
5. **Lineup-level FC comparison** (does not exist yet beyond agent 2): FC-style lineups vs ours on the same slates.
6. Before Wk7: Wk7+ blend re-check with props (see above). Around Wk6: refit layered ownership with more 2026 weeks.
7. Parking lot (don't chase mid-session): see checklist Parking Lot; tangents go there.

## Risks flagged (from the "does prior agent analysis change with context?" review)
- Older narrow-brief agents (3-week ownership refit, history-calibration) — verdicts mostly superseded by v2; low risk.
- Accuracy != cashing: nothing had run through the full optimizer before agent 2. Treat "more accurate" as unproven for lineups until then.
- The Phase 1/2 postmortem (`WK3_ROOT_CAUSE_FINDINGS.md`) predates the accuracy framing; worth a second look for things dismissed as
  variance (e.g., "killer bust share is normal variance").
- Top-QB selection in QB recal uses projections, not depth charts (tie/mis-ranked backup => treated as starter).
- v2 falls back to the old model silently if inputs are missing (see CI-parity).

---

## UPDATE (Wed 2026-09-30) — supersedes the "State of the repo" and "RUNNING agents" sections above
Everything below is committed AND pushed (origin/main at 69dcf11). The two agents from earlier are done and folded in.

**Shipped / on in production (Actions + UI):**
- Ownership v2 + DST model (blended with live FFC at 0.45). Verify "Ownership v2: ON" in the Wk4 Actions log; loud-fallback
  annotations (`DFS_LOUD_FALLBACKS=0` to silence) appear if v2 / QB recal fall back.
- QB recalibration (wk3+, top QB per team, proj>=8). Config now tracked: `data/qb_recal_config.json`. Lineup replay: better or
  equal on every preset (cash build 135.3 -> 146.4). KEEP.
- Best-first lineup ranking: `scripts/optimizer.py::_rank_lineups_by_projection` renumbers lineup_id by total projection (lineup 1 =
  top pick). `DFS_RANK_LINEUPS=0` turns off. Tested on the real Wk3 CSV; not yet exercised through the UI.
- `se3max_pool` randomization-pct 20 -> **5** (sweep: pool/top-5 clearly better; #1 pick unchanged; 3 vs 5 a coin flip, history leans 5;
  uniqueness 3 inconclusive). Flags still worth glancing at on the top 1-5 lineups (backups, stack, punts, ownership, news).

**Disabled:** early-season salary blend (`data/early_season_blend_config.json`, weeks={}; old weights kept under
`weeks_disabled_2026-09-29`). Lineup replay: wk1-2 pools got WORSE with props on (weights were fit without props; likely double-counts
salary). Wk7+ weights had the same flaw, so the earlier "re-check Wk7+ before Wk7" TODO is now "REFIT WITH PROPS ON before
re-enabling anything". Latent bug: on a Wk1 build the blend lifts no-history players (sigma 0) above 0 and sigma recalibration errors.

**Wk4 setup done:** Wk3 stats fully ingested (1,114 rows); `output/matchup_factors_dk_2026_4.csv` built; Wk4 DK salaries ingested and
slates added to `data/current_slate.json` (main + early lock 2026-10-04T17:00Z; PIT@CLE Thursday showdown lock 2026-10-02T00:15Z).
No FD Wk4 salaries and no afternoon slate yet — add when files exist (`ingest_salaries.py --site ... --season 2026 --slate-id ...`,
then a `current_slate.json` entry; showdown needs `--format showdown`). User reorganized `data/raw_salaries/` (Wk3 files now under
`26_27_Season_Salary_Archives/Week_3/`).

**Key result from the lineup replay (`analysis/lineup_replay/RESULTS.md`, local only):** we match FC at the top of the board (top 3
lineups: FC no better, -0.7 pts) but lose deeper in the 100-lineup pool (FC +6.3 pts/lineup, cash 25% vs 18%). Biggest leak was HOW we
pick from the SE3max pool, not the inputs; top-projected lineup cashed ~44% on 2026; the pool average 20-25%. Ownership v2 has no
lineup effect at lambda 0 (SE presets) — it matters for MME/GPP presets. "Top-projected pick" = the single #1 lineup per batch; top-5:
avg cash 29% (new) / 39% (old), at least one of top 5 cashes 78%.

**Other findings this session:** the QB gap and the "FC zeroed 1,001 inactives" gap were mostly test-engine artifacts (injuries/QB1
guard off); backup-QB/depth DNP predictor works (AUC .83) but adds ~0 accuracy, not wired. Cheap-WR/TE and FC-lineup comparison items
remain (below).

**Open items, updated order:**
1. Sunday Wk4 morning: run `python scripts/inactives_timing_log.py --season 2026 --week 4` (logs when ESPN/Sleeper show inactives),
   user does the human inactives check, `status_check pull` + apply, `availability_diff.py`. Confirm "Ownership v2: ON" + QB recal lines
   in the Actions log; first real UI test of the best-first ranking.
2. Mon 10/5: log Wk4 real ownership + results (see wk3 raw files in `data/` for the format; `scripts/log_ownership.py`, `log_results.py`);
   score `est_own_v2_only` vs shipped blend vs `est_own_live_old` vs realized; re-check QB ownership shift; check QB recal on Wk4.
3. Refit the early-season blend with props ON (only then consider re-enabling); fix the Wk1 sigma-0 bug first.
4. Cheap WR/TE ownership root cause (v2 corr .65 vs FC .81, role/vacated-usage group added signal; not understood).
5. FC-lineup construction comparison beyond the replay; pool selection beyond "take the top" (uniqueness 3 inconclusive; MME/GPP
   presets untested with the new inputs).
6. Ownership refit with more 2026 weeks around Wk6.
7. Parking lot: anything else goes in the checklist Parking Lot, not mid-session.

---

## UPDATE 2 (Wed 2026-09-30, end of the QB / WR-TE ownership session) — supersedes open items 4 and 5 above
Committed and pushed: `8391432` (QB auto-promote), `84f88bf` (ownership fixes + checklist). Both §4 parking-lot items are CLOSED.

**Shipped, on in production (Actions + UI):**
- **QB auto-promote** (`_apply_qb_autopromote`, `scripts/build_projections_statline.py`): team with a real game and no QB projected >=8 gets its
  highest-priced non-OUT QB (>= $4,500, proj > 0) set to a salary-implied projection. Quiet; audit cols `qb_autopromoted`, `qb_autopromote_delta`.
  Off: `DFS_QB_AUTOPROMOTE=0`. Why: QB gap vs FC is closed on known starters (we win 5.99 vs 6.32); the whole residual is ~2 surprise starters/slate.
- **Teammate-OUT WR/TE ownership bump** (`apply_vac_bump`, `scripts/ownership_v2.py`), k=1.0, ON. Off: `DFS_OWN_VAC_BUMP=0`. Audit cols `own_vac_bump`,
  `own_vacated`. 2026 replay corr .876->.880, MAE 1.194->1.179.
**Wired, default OFF:** true-pool coefficients (`data/ownership_v2_dk_{linear,dst}_truepool.json`, `DFS_OWN_V2_COEF=truepool`); live 2026 replay slightly worse.
**Root causes found:** (1) 2021-25 ownership training frame pooled off-slate teams (labels exist only for main-slate teams) -> flat slopes; fixed in
`analysis/ownership_v2/build.py hist()`; earlier "v2 .61 vs FC .83" was inflated by it. (2) teammate-OUT usage bump never reached ownership. NOT causes: model shape,
role/Vegas/depth features. Never say "the field has info we lack" (memory feedback_no_field_has_info_excuse).

**Open items, in order:**
1. **Sunday Wk4 morning:** `python scripts/inactives_timing_log.py --season 2026 --week 4`; user human inactives check; `status_check pull` + apply; `availability_diff.py`.
   In the Actions log confirm "Ownership v2: ON", QB recal line, any "QB auto-promote" line; first UI test of best-first ranking.
2. **Mon 10/5:** log Wk4 real ownership + results; score est_own_v2_only vs shipped vs old vs realized; score the vac bump and truepool coefs (re-run
   `analysis/wrte_chalk_root_cause/replay_2026.py` with Wk4 added); check QB auto-promote hits/misses.
3. **Track 2 (own sessions):** truepool default decision (Wk4-5); vac-bump k; "who replaces whom" projection reallocation (Aaron Jones item);
   `--own-penalty` leverage flag (default 0); early-season blend refit with props ON (+ Wk1 sigma-0 bug); lineup-replay of the ownership changes (impact unmeasured);
   stale reference roster (135/659 fallback matches); FC-lineup construction comparison; ownership refit ~Wk6 with more 2026 weeks.

## UPDATE 3 (Wed 2026-09-30, track-2 closing session) — see checklist "Track-2 closing session outcomes"
Pushed: 2ed0730 (blend zero-sigma fix + matcher team refresh), 8ca1ebc (RB who-replaces-whom, ON, `DFS_WRW_RB=0` off), edde6ed (`--own-penalty`, default 0; SUBAGENT_BRIEF "history = all five seasons").
Dropped: blend refit, QB salary blend, cheap-player salary pull, own-penalty fading. Inconclusive/track 2: WR/TE replacement, chalk tilt -0.05 (needs better ownership), stud-level harness-vs-live gap ($6.5k+).
Next: (1) Sunday Wk4 morning tasks above (unchanged) + confirm wrw audit columns in Actions; (2) Mon 10/5 scoring incl. RB replacement; (3) FC-lineup construction comparison (projections/selection gap ~6 pts/100-lineup pool); (4) stud-level gap; (5) history ownership accuracy (.66) then re-test chalk tilt.
