# Handoff: DFS optimizer gap assessment, wrap-up (2026-11-20)

Local only, untracked. Read first: `SUBAGENT_BRIEF.md`, `DFS_Weekly_Process.md`, `CLAUDE.md`, then `HANDOFF_gap_assessment_2026-11-19.md` (the D1-D6 detail).

## Owner rules (unchanged)
- Judge on projected DK points vs actual DK points. History = 2021-25, leave-one-season-out (LOSO) first; 2026 is the second check, slate-id files only, after a roster check.
- Pre-declare every bar. Report MDE with every null. Inconclusive is not wrong-direction.
- Never commit FC-derived files or results. FC history is a teacher/comparison source, never a live input (subscription ended).
- Commits, pushes and merges need the owner's approval. The owner's standing approvals are recorded in the session log below.
- The owner wants clearly met bars taken as wins. Do not run extra tests whose only purpose is to discount a result that clears its bar.
- No FanDuel-derived training data exists. The non-linear training data was Fantasy Cruncher-derived (an earlier message said FanDuel by mistake).

## Repo state
- origin/main at or after `84ad4ed3` (this session).
- Merged to main this session: D2 (`831fe490`); cleanup of 46 stale output files (`63dcadda`); `qb_cheap_restack` (`84ad4ed3`, switch `DFS_QB_CHEAP_RESTACK`, default on, coefficients in gitignored `data/qb_cheap_restack_coef.json`).
- CI caveat: automated GitHub runs do not have the coefficient file, so they run without the restack. Local runs have it.
- Three FC-derived refit files are still tracked on main from owner commit `3a5fd777`: `data/sigma_recalibration_dk.refit-2026-09-26.json`, the FD refit, and `data/projection_stack_dk_refit_2026-09-26.json`. Owner: do not remove from history. Open: whether to take them off the tip with a new commit. Not decided.

## Workstream outcomes
| Item | Outcome |
|---|---|
| D1 simulation / QB recal | Closed. Simulator mean calibrated, joint correlated sim not shippable. Raw-simulator lineup test +5.1 pts/lineup, CI +0.2 to +9.5, one slate set, flagged never resolved. |
| D2 projection inputs | Merged to main. FD warning, Q pre-inactives discount (opt-in, off), schedule game key (bug fix), role-change (off). FD CI fallback HELD: re-score at 2026 wk14; commit only if RMSE CI excludes 0 and MAE CI includes 0 or below, else drop. |
| D3 ownership chalk identity | Closed, nothing shipped. |
| D4 calibration by position x tier | Closed, not shipped. Rerun on roster-checked slate-id frames: 3/5 seasons (needs 4); dMAE worse all 5 seasons; 2026 dRMSE -0.050 CI spans 0, MAE +0.25. Inconclusive on 2026. Props anchor stays at 0.5, recheck week 16. ECR blend opt-in, default off. |
| D5 late-swap flagger | PARKED, underpowered. Coverage: 27 late games, 20 observable; 83 events, 60 observable (13 observable T1). S4 fired: projection definition is `proj_last` (observable n=7, best-case lower bound 0.59) — stays parked. |
| D6 payout ledger | PARKED. Only measures money; DK exports lack fees/payouts; owner judged it redundant with cash tracking. |
| Cleanup | Merged (`63dcadda`). |
| Sigma recalibration | KEEP live 2014-17 `data/sigma_recalibration_dk.json`. Sigma changes sigma only, not projected points; no lineup lever (lambda 0). The `fit_sigma_recalibration.py:136` item was a stale docstring. |
| Roster check (2026 slate-id frames) | PASSED pooled: DK classic 0.75%, DK showdown 0.29%, FD classic 0.78% (DST excluded). 5 of 79 frames above 2%, mostly week 1. |

## Yardstick (tier-rank, the bar we now use)
- Definition: within position x salary-tier cells, Spearman of projection vs nflverse DK actuals; pool = active QB/RB/WR/TE with max(final, FC) >= 5.0; slate-clustered bootstrap, 2000 reps, seed 20261118; MDE80 = 2.802 x SE. Files: `analysis/yardstick_rank/` (local).
- Result: ours minus FC +0.0226, CI +0.008 to +0.037, better in 5/5 seasons. Without 2023 the CI includes 0. FC minus salary-only +0.011 (CI includes 0); ours minus salary-only +0.034.
- Cell: QB under $5,500 is where FC is better (-0.125).
- Top-1 +0.42, top-5 +0.22 points: underpowered (MDE 6.5-8.6). Not evidence either way.

## Candidates tested on the yardstick
1. **`qb_cheap_restack`** (shipped, `84ad4ed3`): pooled +0.0031, CI +0.0015 to +0.0049 (bar +0.010, NOT met). QB under-$5,500 cell +0.041, CI +0.018 to +0.062, better 4/5 seasons, about a third of the FC gap closed. Other cells unchanged. RMSE -0.040. Top-5 -0.03 (sign rule not met). 2026 direction check -0.002 (underpowered). Owner approved shipping in the main chat ("just do it, i approve") as a cell-level win.
2. **Non-linear shallow-tree model** (HistGradientBoosting, depth 3, 300 iter, 33 pre-game features): pooled -0.0063, CI -0.0131 to +0.0011, MDE 0.0103. Label: inconclusive-keep-testing. Not shipped.
3. **ECR blend**: skipped by owner. No 2021-25 history; 2026 only; underpowered.

## Diagnosis of why gains are small (Opus thinker, two rounds)
- Pooled average error is already beaten vs FC every season (RMSE 7.12 vs 7.34). Little left to win there.
- Fantasy Cruncher holds independent signal. A 50/50 rank mix of ours and FC: +0.020, CI +0.012 to +0.030, 4/5 seasons. FC signal concentrates in RBs (+0.010 alone) and under-$5,500 QBs (+0.008 alone). FC's data is a teacher, not a live input. The lesson has to be recovered from free or owned sources.
- Our own inputs reweighted (salary pull, season average, tree model, distilling FC disagreement) gave nothing. Calibration is not the gap.
- Realistic headroom: about +0.01 to +0.02 rank, mostly RB and cheap QB. A one-tier fix cannot clear the pooled +0.010 bar by itself; targeted candidates need their own tier bar.
- The history tests stripped depth charts, injury news, props and weather. The live pipeline uses depth charts (`build_projections_statline.py:1425-1486`) and was never tested on history.
- Ceiling check: a cheat ranker with same-season future averages reaches 0.255 vs our 0.239. Ours mixed with that cheat: 0.279.

## Lineup side (closed for now)
- Live SE/3-Max preset (verified in code, `data/optimizer_presets.json` and `dfs_optimizer_frontend/index.html`): exposure uncapped, uniqueness 3, QB+1, randomization 5%, lambda 0, shape terms 0, position-exposure TE 0.4, flex cap TE 0.35, cheap-filler cap 25% for players at or under $3,600. The 50% cap cited in older analyses is stale (changed 2026-10-28).
- Min-salary floor: Load Preset sets $49,700 (DK) / $59,500 (FD) regardless of the stored value. A CLI build with `--preset se3max_pool` gets no floor unless passed (CLI default 0, `optimizer.py:229`). Owner should confirm which route he uses.
- Team and game caps: inactive.
- Lineup #1 is unaffected by these settings by construction. Lineups 2-100: projected cost below the detection limit; stop at step 0. Choosing which lineup to submit is a human decision, measurable only with payout data (D6, parked).
- Simulation: cannot improve mean points by construction; only top-finish rate, which needs payout or finish data we do not have.
- The earlier figures (8.7-point sacrifice, 4.9-5.4 cap cost, cash 35.8% to 20.1%, 4/14 vs 7/14) are from the old 50% setting. Stale.

## Risk and roster selection (owner's point, Opus-confirmed as a real gap)
- The system has per-player sigma and p10/p90. Sigma correlates 0.31-0.45 with actual error; realized spread / sigma about 0.96-1.08.
- Gaps: for no-history players the p10-p90 range catches only 64% of actual scores (76-80% for players with history); no explicit role-certainty term (rookie, first-year starter, new role); risk reaches the lineup only through a global lambda (0 for cash/SE, -0.005 MME) plus two rough caps.
- Blanket risk dial: ruled out (safer lambda 0.063 lost about 5 pts in all 6 seasons, 88-slate replay).
- Targeted risk for uncertain roles: never tested.
- Test that can work: player-level, do uncertain-role players miss projections more than sigma predicts (uses all history rows). Lineup points cannot resolve this (detection 6.5-9 pts). Also: owner logs his exclude/thumbs-down calls with a reason tag, then check whether those players score below their projection vs same-tier kept players.

## Props
- 2026 prop audit files: `data/props/` (46 snapshots, weeks 2-11; not every week).
- Tested so far: plumbing correct; turning props weight up did not help on wk3-4 (`analysis/wk4_postmortem/RESULTS_item11_props_anchor.md`); early-season blend refit on wk3 only.
- Not tested: whether props improve projections at all. Props-off vs props-on rebuild on wk3-11 is possible now with existing data (no paid source needed). Historical props (2023-25) would need paid data: owner declines.

## Candidate next work (none started; each needs its own session)
1. **Depth-chart history test** (Opus top pick): pull free nflverse weekly depth charts 2022-25, rebuild history with depth charts on, grade on the yardstick, bar on RB and QB-under-$5,500 tiers. Diagnostic: does the ours+FC mix gain shrink from +0.020? Local-only results.
2. **Props on/off on 2026 wk3-11** (cheap, existing data): does the 0.5 props weight improve projections?
3. **Player-level risk test** for uncertain roles vs sigma (all history rows), and owner's exclude/thumbs-down logging with reason tags.
4. **GitHub scan**, one time-boxed session (2-3 hours), idea generation only. Look for: variance/correlation modelling, field/contest simulation, portfolio construction vs projection-max, ownership leverage, late swap. At most 5 ideas, each mapped to already-have / tested / untested. Licence: MIT ok, GPL or no licence = read only, never copy.
5. Deferred: ECR (no history), historical props (paid), D5 (underpowered), D6 (parked).

## Scrubbed test designs (Opus, 2026-11-20). Nothing has been run. Pre-declare before any scoring.

**Constraint found:** in the history frame, `roster_role` is empty and all news/vacancy/step-up fields (`wrw_*`, `role_change_injury_flag`) are zero, because news is off in the history rebuild. Usable fields: `games_played`, `usage_trend_ratio`, `participation_effective`, `sigma`, `statline_p10/p90`, `salary`. Rookie status and prior-season games must be joined from nflverse rosters and weekly stats.

**Why floor-only or ceiling-only selection is the wrong test:** the projection is already the expected value, so swapping it for floor or ceiling gives up expected points by design. The right questions are (a) is the projection biased for a defined group (value), or (b) is stated uncertainty (sigma) wrong for that group. Outcomes, per player, LOSO 2021-25, slate-clustered CIs: value = actual minus projection; stated risk = z = (actual minus projection) / sigma, and how often actuals land inside p10-p90 (about 80% if sigma is right). Each hypothesis is compared against sigma, the current model, and FC as reference.

- **H1, thin sample (most likely to pass).** Population: rookies (years of experience 0) or fewer than 4 prior games last season, and 3 or fewer games this season. Prediction: sigma understates their spread. Earlier lead: 64% inside p10-p90 for no-games-yet players vs about 80% for 6+ games, but that mixes in week-1 veterans, so it is a lead, not a result. Bar for spread: z spread differs from 1 with CI excluding 1 in 4 of 5 seasons, and a LOSO-fitted widened sigma improves Brier score for clearing 3x salary value. Bar for value: any bias CI excludes 0 in 4 of 5 seasons, and a single shift improves affected yardstick cells without harming the pooled number. Failure: spread is fine once real rookies are split from week-1 veterans.
- **H2, role change (least likely to ship).** Population: snap share in last 2 weeks at least 15 points above the prior 4 weeks (nflverse snap counts), split rising and falling. Prediction: base model under-reacts (risers under-projected, fallers over-projected). Same value bar as H1. Failure: live step-up and vacancy layers are off on history, so this grades the base model only. Two earlier variants failed gates (Wk9 Item F decay extension; snap-role re-grade).
- **H3, cheap filler.** Population: RB/WR/TE at $3,600 or less with projection at least 5. Prediction: bust tail heavier than sigma implies (share scoring under half projection above sigma's prediction). Bar: bias or bust-tail excess CI excluding 0 in 4 of 5 seasons, and a LOSO correction improving cheap-tier yardstick cells. Failure: already absorbed by the existing cheap-filler cap (25%, at or under $3,600).
- If spread differs but bias does not, the effect matters only in tournaments and needs the 410-contest replay, not the yardstick.

**Props (46 snapshots, weeks 2-11), "looks like" defined before scoring:** coverage by position and salary tier; snapshot time against lock (Central Time); size of adjustments and how often they hit the 0.5x or 1.8x limits; agreement with engine figures. **Comparison:** every 2026 DK classic slate, weeks 3-11, with a snapshot, rebuilt from pre-lock commit at props weight 0 vs 0.5, everything else identical; roster-check each frame; score on actual DK points (props rows and full pool). **Primary:** props-on minus props-off on the yardstick, clustered by week. **Guardrail:** RMSE and MAE. **Decision rule:** keep 0.5 unless CI sits entirely below 0 (then turn down or off); raise weight only if CI excludes 0 on props rows and props help in at least 6 of 9 weeks. Descriptive: weight sweep 0/0.25/0.5/0.75/1, RB breakout. Expect about 25 slates, so the detectable gap is large; state the MDE with any null.

**GitHub scan (idea generation, own session, 2-3 hours).** Question: what do other optimizers assess about a player or lineup that ours does not, and should we? A finding counts only if: (1) it is a concrete mechanism visible in code, not a README claim; (2) it is not already in our repo or tested (check code and handoffs); (3) it can be tested on our data (history frame, 410 contests, 2026 props); (4) licence allows reading, and we re-implement rather than copy. Areas: variance and correlation modelling, field and contest simulation, choosing lineup sets by expected return, ownership leverage, late swap. Deliver at most 5 candidates, each labelled have / tested / untested. Odds (Opus): about 10% better projection ideas; about 30-35% a construction or contest idea we lack.

## Open owner decisions
1. FD CI fallback: re-score at 2026 wk14 per the rule above.
2. Three FC-derived refit files on main: leave, or take off the tip with a new commit (not history rewrite).
3. Min-salary route: confirm whether the $49,700 floor is entered after loading the preset or relied on from the Load button, and whether CLI builds need `--min-salary-pct`.
4. Checklist `CLASSIC_LINEUP_CHECKLIST.html:150` is correct on the floor; the pool settings statement there is current.
5. Whether to take the `qb_cheap_restack` CI gap (automated runs lack the coefficient file) as acceptable, or to fix it with a non-FC-derived coefficient source.

## Session log (owner approvals this session)
- Merged D2 (`831fe490`) and cleanup (`63dcadda`) on owner instruction.
- Shipped `qb_cheap_restack` (`84ad4ed3`) on the owner's "just do it, i approve".
- Skipped ECR (item 3) at owner's request.
- Items 1-2 of the 2026-11-19 gap list were run to completion (roster check passed; D4 rerun not shipped).
