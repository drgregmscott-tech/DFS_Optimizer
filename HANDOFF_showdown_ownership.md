# Handoff: showdown ownership + lineup construction (combined, 2026-09-22)

Written to merge two parallel sessions from 2026-09-21 into one starting point for a new
session. Repo: `C:\Users\gmsco\Desktop\DFS_Optimizer`, branch `main`. This file **replaces**
the earlier `HANDOFF_showdown_ownership.md` (that handoff's job — build a showdown ownership
model — is done; see below). Read `WK2_POSTMORTEM.md` and the "Post-Week-2 Improvement Track"
at the end of `ROADMAP.md` for the classic-slate work; this file is showdown-specific plus
where lineup construction stands.

**Immediate context: results are in.** Greg has the DK contest export for last night's
NYG@LAR showdown at `C:\Users\gmsco\Downloads\results_se3max_dk_showdown_wk2_NYG_LAR_21Sep2026.csv`
(8,918 rows, same format as the classic exports: `Rank,EntryId,EntryName,TimeRemaining,Points,
Lineup,,Player,Roster Position,%Drafted,FPTS`). **Not yet logged or analyzed.** This is the
first concrete thing to do in the new session (see "Next steps" #1). Note Puka Nacua was
ruled OUT for this game (~7pm CT last night), so it's a good test of the participation fix
and props fallback for a real in-week OUT skill player, not just a normal slate.

## 1. What the FIRST session (this transcript) did — classic slates
Full detail in `WK2_POSTMORTEM.md`. Summary:
- Root-caused Weeks 1-2's poor SE3max/MME results: (a) Week 2+ price-implied volume wasn't
  discounted for players with zero games this season even when their team had played
  (fixed — `statline_model.absent_player_price_factor`); (b) ownership wasn't recomputed
  after OUT players were zeroed (fixed — `status_check.refresh_ownership`); (c) the classic
  ownership heuristic badly under-estimated chalk (fixed — layered model,
  `scripts/ownership_model.py` + `scripts/fit_ownership_model.py`,
  `data/ownership_model_dk.json`, DK classic only).
- Found and corrected a look-ahead leak in historical backtests (a rebuilt week could see its
  own stats file already populated). Clean re-measurement: the engine is roughly TIED with
  salary at skill positions (not clearly better, contrary to an earlier in-session claim),
  though the two are complementary (engine+salary beats either alone) and the engine does
  find real value vs salary (top-vs-bottom quintile by engine-minus-salary-predicted gap:
  ~4 pt/game spread).
- Tested and rejected: game-pace features, defense-vs-position features, vacated-teammate-
  usage features — each added ~0 to out-of-sample R² beyond salary+engine+recent-usage.
  Recent usage (last-4-game targets/carries/share) and market player props were the two
  signals that actually mattered.
- Built and shipped: **player-prop market anchor** (`scripts/props_ingest.py`,
  `scripts/props_auto.py`, `scripts/props_model.py` — de-vig, odds→stat-line-mean, blended
  50/50 into the engine's per-player inputs; automatic per-slate pull near lock wired into
  `refresh_data.yml`, secret `ODDS_API_KEY_PROPS`); **calibrated projection stack**
  (`scripts/projection_stack.py` + `scripts/fit_projection_stack.py`,
  `data/projection_stack_dk.json` — salary + engine + last-4-game usage, DK classic only,
  fixed most of the stud under-projection). Both fail-safe to engine-only on any error.
- Tested a flat ownership-penalty ("leverage") term in the optimizer at several strengths,
  with real/old/new ownership: **no gain at any strength**, even with perfect (real)
  ownership knowledge — accurate ownership is for informed game-theory decisions, not a
  free lineup-quality lever by itself. Greg confirmed this matches his expectation.
- A scheduled reminder fires **Monday 2026-09-28, 8:00am CT** to revisit the classic-side
  agenda (log Week 3, refit ownership, score props, start construction-setting tests, etc.).
  Still active, unaffected by this handoff.

## 2. What the SECOND session (parallel, same day) did — showdown ownership + construction scaffolding
All work lives under `analysis/showdown_own/` (throwaway/analysis scripts, not wired into
the app except the ownership model itself) plus `scripts/ownership_model_showdown.py` and
`scripts/showdown_field.py` (real pipeline additions). Findings recorded in
`WK2_POSTMORTEM.md`'s "Showdown ownership assessment (2026-09-21)" section — read that
section for the exact numbers; summary here:

### Showdown ownership model (`scripts/ownership_model_showdown.py`)
- Same signature as classic: heuristic badly under-estimates chalk (wk2 IND@KC: Walker CPT
  12% est vs 42% real; Butker FLEX 6% vs 31%; Warren FLEX 12% vs 41%).
- Model: per-role (CPT, FLEX) ridge regression on logit-scale real ownership, 4 features —
  optimizer-implied exposure (computed SEPARATELY for CPT and FLEX rows, averaged over 3
  noise levels x 60 lineups each), kicker flag, DST flag, and (v2) a "min-price" flag
  (FLEX-equivalent price ≤ $1,000 — real ownership on these is 0-2%, heuristic gave 5-12%).
  Water-filled to CPT=100%/FLEX=500% budgets with a cap (CPT 60%, FLEX 75%).
- Validated leave-one-slate-out on 2 slates (wk1 DEN@KC partial, wk2 IND@KC): CPT correlation
  0.81→0.96 and chalk MAE 16.3→3.3 on wk2; more mixed on wk1 (only 4 chalk CPT rows there).
  FLEX correlation ~0.7-0.85→0.8-0.9, chalk bias roughly halved. Still doesn't catch
  narrative/mid-price pass-catcher hype (Waddle, Warren) — no feature explains those misses.
  **Only 2 slates of real data** — refit is essential as more slates log (`python
  scripts/ownership_model_showdown.py fit --validate`). Wired into
  `add_showdown_ownership_columns()` in `build_projections.py`, fail-safe to the heuristic.
- Chalk-CPT question (the thing Greg specifically wants answered): analyzed both wk1 and wk2
  at the LINEUP level (8,845 and 4,733 real entries respectively, via
  `analysis/showdown_own/chalk_cpt.py` / `chalk_cpt2.py`). Finding across the 2 games: the
  top-owned CPT was NOT necessarily a bad captain on raw points (wk2's Walker was actually the
  4th-best CPT score), but top-1%-finishing lineups used the chalk CPT far less than its
  ownership share (wk2: 11% of top-10% lineups vs 42% field usage, 0.25% of top-1% vs 42%;
  wk1: the chalk CPT, Bo Nix, was in ZERO of 98 top-1% lineups and had the worst-performing
  CPT-ownership tier outright). Read as "chalk CPT caps your ceiling, doesn't necessarily lose
  you money" — but this is **n=2 games**, and wk1's chalk miss was driven by one specific bad
  QB outcome, not a structural pattern yet proven. Needs a 3rd+ slate (tonight's NYG@LAR is
  exactly that) before treating this as a real finding rather than early signal.

### Showdown simulated field (`scripts/showdown_field.py`, validated by `analysis/showdown_own/validate_field.py`)
- Same idea as the classic simulated field: draw a CPT from real CPT-ownership weights and 5
  distinct FLEX from real FLEX-ownership weights, salary cap $50k / floor ~$48.5k, both teams
  required, weights tuned so the accepted sample reproduces the input ownership (validated
  MAE 0.06 CPT / 0.16 FLEX). Built from REAL ownership + actual points, it reproduces real
  lineup score quantiles (50th/75th/90th/95th/99th/99.9th percentile) within ~1-2 points on
  both logged slates. Known weakness: not stack-aware (real fields lean more 3-3/4-2 than the
  simulated field does), and kicker-inclusion rate is slightly off (0.45 sim vs 0.43 real).
  This is the field used to score candidate lineups below.

### Lineup-construction scaffolding (NEW — this is the "construction" work Greg asked about)
This is real, substantial work but **analysis-only so far, not wired into `optimizer.py` or
the frontend**. Files in `analysis/showdown_own/`:
- `best_single.py` / `refine_single.py`: a scenario-based Monte Carlo evaluator for
  single-lineup showdown builds. For a candidate lineup, simulates thousands of correlated
  outcome draws (shared game-script factor, shared team-total factor per team, DST negatively
  correlated with the OPPOSING offense's total, kicker positively correlated with own team's
  total, all layered on the players' own `final_projection`/`sigma`) across 4 named scenarios
  (base / shootout / big-script / quiet-DST) and 2 ownership fields (new model vs old
  heuristic), and reports P(top 10%) and P(top 1%) against the simulated field from above.
  `best_single_results.csv` has 761 candidate lineups scored this way for the pre-Nacua-OUT
  pool (top ones by `avg_top10`, e.g. "CPT Williams | Stafford, Nabers, Adams, Rams(D),
  Parkinson [LA5/NYG1]" at ~31.3% avg top-10 rate, ~94.8 proj).
- `splits.py`, `top10_drivers.py`: real-field descriptive analysis (what actually
  distinguished top-10%/top-1% real lineups: team split, CPT position, kicker inclusion —
  see the "showdown specifics" notes carried over from the first handoff, still valid).
- `score_lineups.py`, `score_file.py`, `compare_lineups.csv` / `compare_names.csv`: after
  Nacua was ruled OUT and projections were rebuilt, 11 NAMED candidate lineups (ids in
  `compare_names.csv`, e.g. `A_WilliamsCPT_LA5`, `U5_StaffordCPT`) were re-scored against the
  refreshed pool with `score_file.py`. **The output of that final comparison (which candidate
  ranked best) was not captured to WK2_POSTMORTEM.md or any committed file** — it only printed
  to the terminal in that session. Re-run `python analysis/showdown_own/score_file.py
  output/final_projections_dk_dk_showdown_wk2_NYG_LAR_21Sep2026.csv
  analysis/showdown_own/compare_lineups.csv` if you need that comparison again (the
  projections file has since moved on with fresh automated refreshes — see caution below).
- `dataset.py`, `dataset.csv`, `loso.py`, `train.pkl`, `chalk_cpt.py`/`chalk_cpt2.py`,
  `refine_results.csv`: supporting data-prep and validation scripts for the ownership model
  and chalk-CPT analysis above.

### Frontend/optimizer changes (real pipeline, not analysis)
- `bfb4dec`: Showdown pool exclude is now per-row (`pid:CPT` / `pid:MVP` / `pid:FLEX`, bare
  `pid` still excludes both) instead of removing both rows; UI has a Captain/FLEX pool filter
  on Showdown slates. Classic behavior unchanged.
- `e2a9d5f`: Lineup Results panel shows real Captain ownership on the CPT slot (was
  joining ownership without the role, so CPT rows showed FLEX ownership); added a lineup
  scorer vs. the simulated field to the frontend/analysis path.

## 3. Next steps for the new session, in order
1. **Log last night's NYG@LAR showdown results + ownership.** Raw file is at
   `C:\Users\gmsco\Downloads\results_se3max_dk_showdown_wk2_NYG_LAR_21Sep2026.csv` (8,918
   rows). Follow the same pattern as `data/ownership_raw_dk_showdown_2026_wk2_IndKC.csv` /
   `data/results_raw_dk_showdown_2026_wk2_IndKC.csv` from the second session (split the
   export into a `player_name,roster_role,actual_ownership_pct` file and a
   `player_name,roster_role,actual_fpts` file, then `log_ownership.py log` /
   `log_results.py log` with `--slate-id dk_showdown_wk2_NYG_LAR_21Sep2026`). Note Nacua was
   OUT — his row(s) should show ~0% real ownership; check the projections handled that
   correctly (they should have, per the participation fix + OUT-zeroing this session did).
2. **Refit and re-validate the showdown ownership model** with 3 slates now
   (`python scripts/ownership_model_showdown.py fit --validate`) — first real chance to see
   if the coefficients (especially `isMin`) hold up out of sample on a 3rd game.
3. **Extend the chalk-CPT lineup-level analysis to 3 slates** (`chalk_cpt.py`/`chalk_cpt2.py`
   pattern) — this is the direct answer to "accurately determine what chalk captains missing
   means." With 3 real games this is still thin, but much better than 2. Report effect sizes
   with honest uncertainty; don't overclaim a "rule" from 3 correlated single-game draws.
4. **Grade the actual showdown build.** Whatever lineup(s) Greg played last night, look up
   their real finish, and separately score the `best_single_results.csv` / `compare_lineups.csv`
   candidates against the REAL outcome (not just the simulated field) to see if the P(top-10%)
   scenario model was predictive.
5. **Decide on formalizing lineup construction.** The scenario/Monte-Carlo scoring approach
   (`best_single.py`) is a real capability that doesn't exist in `optimizer.py` today (which
   is mean/variance-only via `--lambda`, no correlation structure, no "P(top X%) against a
   simulated field" objective). Discuss with Greg whether/how to turn this into a reusable
   tool (classic AND showdown) vs. keep it as an ad hoc analysis script. This is the
   "lineup construction" work item Greg flagged as next.
6. Lower priority, still open from the classic side (full list in ROADMAP.md's Post-Week-2
   Improvement Track): construction-setting replay tests (SE filter, TE-in-FLEX, exposure
   caps, game targeting) using `scripts/replay_validation.py` — **note: this was planned but
   NOT actually committed as a script in the first session**, only run ad hoc from a session
   scratchpad; if replay testing is wanted, it needs to be built as a real committed script
   first, mirroring the showdown field validation approach above.

## 4. Cautions
- **This repo gets automated commits constantly** (GitHub Actions refresh bot, on-demand
  optimizer runs from the frontend, UI slate saves). Always `git pull --rebase` before
  editing or pushing; expect to rebase every session.
- **There is an old, unrelated git stash** (`stash@{0}`, based on commit `b49586a`, a much
  older point in history). Not from either of today's sessions as far as either transcript
  shows. Leave it alone unless Greg says otherwise — do not pop or drop it.
- `data/current_slate.json` still lists `dk_showdown_wk2_NYG_LAR_21Sep2026` and other now-past
  Week 2 slates (all locks were before this handoff was written). Harmless (the refresh
  workflow auto-skips locked slates) but could be cleaned up next time slates are managed.
- `output/final_projections_dk_dk_showdown_wk2_NYG_LAR_21Sep2026.csv` has been rebuilt several
  times since last night by the automated refresh workflow (it keeps re-running on
  `full_refresh_dispatch` even though the slate is locked — probably still inside the
  near-lock dispatch window). Its exact contents at any given moment reflect the LAST
  automated build, not necessarily the pool `best_single_results.csv` / `compare_lineups.csv`
  were scored against. Re-derive fresh comparisons rather than assuming the committed
  projections file still matches the analysis CSVs' player set.
- Odds API credits: two accounts in play — `ODDS_API_KEY` (original, was at ~235-240
  remaining as of yesterday) and `ODDS_API_KEY_PROPS` (new, added as a GitHub secret
  yesterday, should have ~500 fresh credits). Props pulls prefer the `_PROPS` key
  automatically; no action needed, just be aware when checking usage.
