# Week 7 Postmortem — Action Items

**Purpose:** holds fixes/changes that come OUT of `WK7_POSTMORTEM_DIAGNOSIS.md` (and the all-weeks ledger once
it exists). Nothing gets added here until the diagnosis data is collected and analyzed — this file stays empty
during the collect phase.

Per [[project_dfs_two_track_philosophy]]: hard bar to ship into production, low bar to keep testing further.
Every item below should say which track it's on.

**Entry format:**

```
## <short title>
- Source: diagnosis item # / ledger pattern that surfaced this
- Evidence: what data showed it, across how many weeks
- Proposed change: what would actually change in the code/process
- Track: ship-bar (production-ready) | test-bar (worth investigating further) | parked (noted, not pursued)
- Status: open / in progress / shipped / rejected
```

---

## RB-vacancy decay (rank-1-only), multi-week RB replacement extension
- Source: diagnosis item 1 (pipeline-stage attribution), the RB-vacancy side-check added to it 2026-10-26.
- Evidence: 69 real "lead RB out, teammate active" situations across all of Wk1-7 2026, all slate types.
  Shipped first-week bump fires 10/10. Every continuing absence (2nd+ week, 36/36 cases — e.g. Braelon Allen
  got nothing in Wk5/6/7 despite Breece Hall still out) gets zero from the shipped mechanism. A rank-1-only
  multi-week extension already existed, built+tested 2026-10-23, parked as "inconclusive, keep testing,
  leaning positive" (21 live rows). Re-tested 2026-10-26 with 35 real rows (same direction, point estimates
  essentially unchanged: MAE -0.16 [-0.42,+0.10], RMSE -0.22 [-0.46,+0.03], CIs still cross zero) — see
  `analysis/rb_replacement_decay/RESULTS.md` and `live_2026_rerun_wk1-7_postfix_out.txt`. A real bug was found
  and fixed during the re-test: `_rb_decay_addon` matched the global OUT list without checking the vacater was
  still on the team, so 6-7 rows this week were an offseason-traded player (e.g. Pacheco→DET) incorrectly
  "vacating" for his old team (KC). Fixed in `scripts/statline_model.py` (`pid_to_team` scoping, see diff) and
  re-verified the number above is post-fix.
- Proposed change / what changed: `_rb_decay_params()` in `scripts/statline_model.py` now defaults ON
  (`DFS_RB_REPLACEMENT_DECAY` default flipped from `"0"` to `"1"`; `data/wrw_rb_decay_params.json` and the
  `wrw_decay_pts` audit column were already in place from the original build). Smoke-tested on the real Wk7
  main pool: Braelon Allen now gets +0.38 by default, 0.0 with the switch explicitly off; Wk7's existing
  first-week bumps (Bijan Robinson, etc.) unchanged either way.
- Track: **shipped on an owner override of the two-track hard-ship bar** — the result never cleared the CI
  bar on its own, but the owner's call (2026-10-26): direction has been consistent and small/positive across
  both the 10/23 and 10/26 tests (never reversed, never got worse with more data), the blast radius is small
  (2-3 RBs/slate, +0.1 to +2 pts, zero WR/TE/QB impact), and live performance from here can keep being
  monitored as more data accumulates — rather than staying parked on an effect that keeps confirming itself in
  the same direction. If a future postmortem finds this now looks wrong-direction, flag it then and revert via
  `DFS_RB_REPLACEMENT_DECAY=0`.
- Status: shipped 2026-10-26.

## ESPN injury-feed comment text as a role/usage signal (ahead of the field, not just injury status)
- Source: follow-up from diagnosis item 1's "engine" bucket — 212 of 296 points-projection misses (Wk2+, where
  we had trailing data) were real-world volume shifts that surprised us *and* DFF by about the same margin.
  Owner's framing: the goal isn't just matching the field, it's getting ahead of exactly this kind of surprise.
- Evidence: `site.api.espn.com/apis/site/v2/sports/football/nfl/injuries` returns `shortComment`/`longComment`
  free-text, beat-writer-sourced role/usage analysis (e.g., "...Knight could begin to put himself in position
  for regular snaps moving forward," attributed to a named team-site reporter). **Correction, 2026-10-28:** this
  is NOT the endpoint `scripts/status_check.py` already polls (that's the per-team roster endpoint, confirmed
  live to carry only `status`/`date`, no comment text) — it's the separate league-wide `/injuries` feed,
  the exact endpoint `status_check.py`'s own decision #1 evaluated and REJECTED for status purposes (confirmed
  still true live 2026-10-28: 8.5MB, 616/800 sampled entries `status: "Active"`, i.e. routine box-score recap,
  not a game-day designation). So "zero additional cost, already in the pipeline" was wrong — it's a genuinely
  new, large pull. Also confirmed live: this endpoint has NO historical lookback (`dates`/`week`/`season` query
  params are silently ignored, always returns today's current snapshot) — there is no way to backfill what it
  said in a past week.
- Additional scoping (2026-10-28): a related, testable proxy — "did a skill-position teammate's snap share drop
  notably the same week" as a stand-in for "team reacted to a healthy player's reduced role" — was checked
  against 108 real zero-signal projection misses (Wk2-7 2026, the ones diagnosis item 1 couldn't explain) vs. a
  300-row control sample. Result: **noise, not signal** — 67.6% of misses had such a teammate vs. 71.7% in the
  unrelated control. Generic snap-share volatility doesn't distinguish our misses from an ordinary week; if a
  signal exists here it would need to be something more specific (an intentional, stated role change) than raw
  usage movement, which is consistent with the comment-text idea but doesn't itself validate it.
- Proposed change / what was built: given no historical backfill is possible, the only way to ever get evidence
  is to start accumulating dated snapshots now. Built `scripts/espn_comment_feed.py` (collection-only: pulls the
  feed, keeps player/team/status/comment-text/date, best-effort matches to player_id via
  `ingest_salaries.py`'s existing normalize/match helpers, writes a timestamped CSV — no classification/scoring
  logic). Wired a weekly pull into `refresh_data.yml`'s `shared_pull` job (fail-safe, non-blocking). Deliberately
  NOT wired into `final_projections` or any build step — extracting "is this forward-looking role language"
  from "is this routine recap" is a real text-classification problem (most of the feed is recap), and any
  point-value sizing would be unvalidated guesswork with no historical cases to check it against. The
  classification/scoring step remains the explicit next decision, to be made only once enough real prospective
  snapshots exist to test against.
- Interim real-time answer (2026-10-28): for the case this item is actually trying to solve — "we know a player
  is getting a real usage bump this week, the pipeline isn't reacting" — `scripts/statline_model.py`'s
  `load_manual_role_overrides()`/`apply_manual_role_overrides()` already exists for exactly this
  ("real breaking news... that no data feed can reflect yet") via
  `data/manual_role_overrides_{season}_{week}.csv`, but had never been used (no such file existed). Verified
  end-to-end on the real pipeline 2026-10-28: ran the actual production build command against the real Wk7 main
  slate with a test override row, confirmed it correctly moved the targeted player's volume/`final_projection`
  without affecting other players, confirmed downstream team-volume reconciliation absorbed it safely, then
  fully reverted (file restored, git status clean). This is the recommended manual lever for a real in-week
  conviction call, independent of the comment-feed work above.
- Track: test-bar (worth investigating further) — collection now running; classification/scoring still
  unbuilt and unvalidated, same two-track discipline as every other lever here.
- Status: **scoped and partially actioned 2026-10-28.** Collection-only capture shipped and automated
  (commit 49c1cf6d). Classification/scoring into projections remains open, deferred until enough prospective
  snapshots accumulate to validate against. Manual role-override escape hatch verified working as the interim
  answer for a real in-week usage call.

## classic_field.py simulator over-concentrates team stacking beyond ≥1 correlated piece
- Source: diagnosis item 4 (classic_field.py simulation validation), 2026-10-26.
- Evidence: 134 real DK SE main-slate contests (2022-2026) vs sim (`simulate_field()`, 2026 wk1/wk2 target
  ownerships). QB stack ≥1 teammate: real 83.8% [IQR 80.2-88.9] vs sim 90.3-91.4% — inside the real-vs-real
  band, a parameter calibrated correctly on its own target stat. But QB stack ≥2: real 36.3% [32.4-42.3] vs
  sim 68.6-69.2% (+35 pts, outside); max players from one team, mean: real 2.44 vs sim 3.29-3.42 (outside);
  share with 3+ from one team: real 41.7% vs sim 73.2-73.6% (+34 pts, outside); share with 4+: real 5.8% vs
  sim 39.2-44.2% (+34-39 pts, outside). Same direction and magnitude in both weeks. Owner confirmed this
  matches real-world SE play: single-entry fields deliberately spread correlation risk (one correlated piece
  for a small edge) rather than stacking hard the way large-field MME GPPs do — the real data's low ≥2/3+/4+
  rates are expected field behavior, not noise.
- Proposed change (superseded, see Status): `scripts/classic_field.py`'s `stack_boost` multiplier applied
  independently to every skill-slot draw (RB, RB, WR, WR, WR, TE, FLEX) when filling a lineup around a boosted
  QB, and was calibrated only against the stack≥1 rate (per the function's own doc comment) — nothing checked
  the higher-order stats. That single-parameter boost compounds across slots, correctly hitting ≥1 while
  overshooting ≥2/3+/4+.
- Track: test-bar (worth investigating further) — real, data-driven finding.
- Status: **shipped 2026-10-28.** Extracted the real per-lineup exact-k teammate-count distribution (k=0..4+
  of the QB's 7 skill slots held by his own teammate) from the same 134 real contests already on disk
  (`analysis/wk7_postmortem_item4/exact_k_stack*.csv`, no new data pull) — k=0:15.8%, k=1:46.3%, k=2:33.4%,
  k=3:4.1%, k=4+:0.4%. Replaced the independent-per-slot `stack_boost` multiplier in `scripts/classic_field.py`
  with: sample k directly from this distribution per lineup, randomly choose which k of the 7 skill slots are
  "hot," hot slots draw only from the QB's own teammates, cold slots draw only from non-teammates (the first
  attempt left cold slots unboosted, which still incidentally picked the QB's own above-average-owned teammates
  and overshot stack≥2 to ~52% — the cold-slot exclusion fixed that double-counting). Revalidated against the
  same 134-contest real stats: stack≥1 82.7-85.0% (real 83.8% [80.2-88.9], IN), stack≥2 33.9-36.7% (real 36.3%
  [32.4-42.3], IN), max-team mean 2.48-2.54 (real 2.44 [2.40-2.52], IN), share 3+ one team 43.5-48.4% (real
  41.7% [38.6-47.3], borderline — one run slightly above the real upper IQR), share 4+ one team 5.9-7.6% (real
  5.8% [4.9-6.9], borderline, same pattern). All five stats moved from +34-39pt overshoots to in-band or
  near-in-band. Committed in `scripts/classic_field.py`; the derivation script and real-data outputs stay
  uncommitted (FC-derived, per repo convention).

## se3max_pool construction-mechanics rebuild (exposure cap, stack size, shape terms)
- Source: optimizer-mechanics fidelity chain, 2026-10-27 — four linked studies, see WK7_POSTMORTEM_DIAGNOSIS.md
  Item 11 for the full summary and links to each: `analysis/optimizer_fidelity_2026-10-27/`,
  `analysis/optimizer_fidelity_qb1_recheck_2026-10-27/`, `analysis/optimizer_ablation_2026-10-27/`,
  `analysis/fc_era_rebuild_2026-10-27/`, `analysis/pool_size_clean_test_2026-10-27/` (last one in progress at
  time of writing).
- Evidence: the real pool sacrifices 8.7 projected points (6.6%) vs. the best legally-buildable lineup, and
  never contains that optimum (0/14 slates). Staged decomposition: **the 50% max-exposure cap is the dominant
  cost (4.9-5.4 of 8.7 pts)**; the preset's QB+2 stack is second (~1.5 pts) — the owner's actual play is QB+1,
  no bring-back, which costs ~0.04 pts (essentially free; preset default was a long-standing, repeatedly-stated
  mismatch, see memory `user_actual_stack_qb1_no_bringback.md`); building 100 distinct lineups at all costs
  1.6-1.9 pts (unavoidable, grows with pool size); shape terms (zero/3+-punt penalties, DST bands) cost only
  ~0.3 pts but push the wrong direction — the real pool runs zero punt plays in only 26% of lineups vs. the
  owner's real FC-era history (50%) and FC's own engine's apparent behavior. Cash impact: minimal construction
  (QB+1, no cap, no shape terms) cashes 35.8% (pool) / 7 of 14 (top lineup) in hindsight on these 14 slates vs.
  the full real pool's 20.1-22.5% / 4 of 14 — a real drop, CI excludes 0. The owner's own profitable 2022-24
  FC-era lineups deviated from FC's own pure-projection optimum by 16.3% — *more* than our optimizer currently
  deviates from its own (6.6%) — and still cashed 59% vs. FC's own pure-optimum lineup's 30%: deviating from
  raw projection isn't inherently bad, this specific deviation (the exposure cap) is.
- Proposed change: in `data/optimizer_presets.json`'s `se3max_pool` preset (or via explicit CLI flags, not
  necessarily changing the live preset default): remove or substantially raise `max-exposure` above 50%;
  zero out `cl-zero-punt-penalty` and `cl-three-plus-punt-penalty` (and the other `cl-*` shape terms, which cost
  little either way); keep `stack-size: 1` (confirm the owner's actual CLI override matches, since the bare
  preset default is still 2); **keep `n-lineups` at 100 — resolved by `pool_size_clean_test` (2026-10-27):** at
  stage-3's minimal settings, N=20/50/100 are nested (deterministic at 0% randomization) and cost only
  1.13/1.54/1.88 pts respectively — pool size barely matters once the cap/shape terms are gone. Top-lineup cash
  is identical (7/14) at every N, but N=100 holds a casher in its pool on 13/14 slates vs. N=20's 12/14 (FD wk3's
  only casher sits in lineups 21-50) — a small, real edge for staying at 100, not 20.
- Track: **owner override of the hard ship bar, same standing as RB-vacancy decay** — converging evidence across
  4 independent studies (the staged ablation, the personal FC-era comparison, the owner's own stated historical
  method, and the punt-mix cross-check) was judged sufficient to act now rather than wait for more backtesting,
  which is capped at the same 14 historical slates either way. Live cash-rate monitoring going forward is the
  real next test, not more backtesting.
- Status: **shipped 2026-10-28.** `data/optimizer_presets.json`'s `se3max_pool` preset updated: `max-exposure`
  0.5 -> 1.0 (effectively uncapped at n-lineups=100, matching the validated "no cap" test config, not a partial
  raise), `stack-size` 2 -> 1, every `cl-*` shape term -> 0.0 (dst-band-bonus, dst-expensive-penalty,
  zero-punt-penalty, three-plus-punt-penalty, same-pos-punt-penalty, four-wr-no-stud-penalty). `n-lineups` held
  at 100 per the resolved pool-size question. `stack-positions` deliberately left at its default (`WR,TE`), not
  broadened to `RB,WR,TE` as the ablation study's isolated QB1 test used internally — that broadening was never
  itself proposed or owner-approved, only `stack-size` was. Smoke-tested on the real Wk7 main slate
  (post-change): builds successfully, 100 feasible lineups, salary $49,700-$50,000 (near the real-field floor),
  `CL_stack_depth_lt2` lint now fires on 61% of lineups as expected (QB+1 is the new baseline, not a defect).
  Live cash-rate monitoring from here, per the owner's override decision above.

## Manual ownership/TE/DST/QB exclusion rules dropped for current build
- Source: diagnosis item 9 (alternate-parameter pool comparison), 2026-10-27.
- Evidence: isolating any one of the three rules (ownership <2% cutoff, TE salary band, QB floor >20 projected)
  and removing it alone raised backtest mean cash rate from 22.5% to 28-30% on 8-9 of 14 slates; removing all
  three together (27.9%) did not do meaningfully better than removing just one — the rules cost similarly and
  don't stack, so no single rule is "the" culprit. DST band not implicated (near-neutral). Deliberate
  leverage-chasing or chalk-heavy construction (explicit alternatives) did not help either. None of this cleared
  the strict 11+/14 significance bar at n=14, but 5 independently-built variants converged on the same direction.
- Proposed change: stop applying the manual ownership/TE/DST/QB exclusion rules when building the current pool.
  Simplicity was chosen over cherry-picking a single rule to drop, since no rule was shown to be worse than the
  others.
- Track: **owner override of the hard ship bar** — same standing as RB-vacancy decay and the construction-
  mechanics rebuild above: directionally consistent across 5 independent variants, judged sufficient to act on
  this week rather than wait for significance that n=14 historical slates can't supply. Stacks with the
  construction-mechanics change above, so if results move this week, the two changes can't be cleanly
  separated without further live tracking.
- Status: **actioned 2026-10-28 — no code change exists to make.** Checked: these three rules
  (ownership <2%, TE salary band, QB floor >20 projected) are not enforced anywhere in the pipeline — there is
  no hardcoded ownership/TE/QB threshold in `scripts/optimizer.py` or elsewhere (confirmed by search; the only
  hardcoded band is the DST $2,800-3,100 preset term, already zeroed above). They are the owner's own manual
  habit when hand-picking players to feed the optimizer's generic `--exclude` mechanism. The action is a process
  change, not a software one: stop applying these three filters when building the pool going forward. Nothing
  left to implement.

## classic_field.py simulator under-uses the salary cap vs real fields
- Source: diagnosis item 4 (classic_field.py simulation validation), 2026-10-26.
- Evidence: 134 real DK SE main-slate contests: total lineup salary mean $49,880 [IQR 49,870-49,900], p10
  ≈$49,700, p50 ≈$49,900 (real-vs-real p90 diff only ~$52-100 — a tight, consistent real-field floor). Sim
  (`MIN_SALARY` = $49,300) came in $200-400 light in both 2026 wk1/wk2: mean $49,627-49,637, p10 sitting right
  on the $49,300 floor, p50 $49,600 — outside the real-vs-real band in both weeks. Owner's read from
  commercial-optimizer experience: ~$49,700 is the common practical floor for real main-slate classic builds
  (a smaller contingent deliberately uses ~$49,500 as a diversification lever, but leaving $500+ unspent with
  no reason is generally a mistake — pay up somewhere instead); showdown is the one format where leaving up to
  ~$1,000 unspent is normal, which doesn't apply here.
- Proposed change: raise `MIN_SALARY` in `scripts/classic_field.py` from $49,300 toward ~$49,700 to match the
  dominant real-field floor, possibly with a configurable lower option (~$49,500) for the smaller real
  contingent that uses it as a diversification choice. Check how raising the floor interacts with the IPF
  ownership-correction step before just changing the constant — a tighter salary-legal pool per batch could
  change how well IPF converges to target ownership.
- Test (2026-10-28): reran `simulate_field()` on the same 2026 wk1/wk2 pools at $49,500 and $49,700 against
  the same 134-contest real baseline (`analysis/wk7_postmortem_item4/min_salary_test.py` + `.csv`, not
  committed, FC-derived). $49,700 closes the mean-salary gap almost entirely (wk1 +$11, wk2 -$36, vs -$204/
  -$258 at the old $49,300) and roughly halves the p50 gap (-$140/-$160 vs -$340/-$360); $49,500 only
  partially closes it (-$90/-$144 mean, -$240/-$260 p50). Cost: `own_MAE_vs_target` (IPF ownership-match
  error) rises ~9-10% relative at $49,700 vs $49,300 (wk1 0.360->0.393, wk2 0.684->0.735) — real but modest,
  judged acceptable. p50 still sits ~$150 under real (real fields concentrate even tighter near the cap than
  one floor bump captures) — a known residual, not claimed as fully closed.
- Track: test-bar finding, shipped on the strength of the single-parameter test above (owner approved
  2026-10-28) rather than the stricter construction-mechanics-style multi-study bar — low complexity, easily
  reverted via the constant if live results disagree.
- Status: **shipped 2026-10-28.** `MIN_SALARY` raised 49300 -> 49700 in `scripts/classic_field.py`.
