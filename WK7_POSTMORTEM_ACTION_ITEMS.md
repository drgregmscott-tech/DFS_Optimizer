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

## se3max_pool pool collapsed to a single-player/single-skeleton monoculture after the Item 11 exposure-cap rebuild
- Source: Wk8 postmortem (2026-10-28), a same-day follow-up to the Item 11 rebuild above -- surfaced reviewing
  the owner's real Wk8 pool build (`output/lineups_multi_dk_dk_classic_wk8_main_01Nov2026_ea0c6653-...csv`,
  100 lineups), two days after Item 11 shipped `max-exposure` 0.5 -> 1.0 (uncapped) and `uniqueness` stayed at
  its pre-existing value of 1.
- Evidence: the real Wk8 pool put a TE in FLEX in 81/100 lineups (real DK field: 21-33% depending on
  cash/noncash and SE/MME, `WK3_ROOT_CAUSE_FINDINGS.md` line 632) and lineups #1-19 (ranked by projection --
  what the owner actually submits as #1) were near-duplicates of each other, differing only in DST and a cheap
  WR3 -- Brenton Strange ($4,000, our highest-owned TE that week, genuine value not a bug) sat at the TE slot
  in 91/100 lineups overall. Root cause: `uniqueness=1` only requires ONE different player between consecutive
  lineups, and `max-exposure=1.0` (correctly uncapped by Item 11 for QB/RB/WR) left nothing bounding a single
  thin-position player's total exposure either. Rebuilt Wk1-7 with current code (no committed analysis
  folder -- test rebuilds aren't committed per SUBAGENT_BRIEF.md hygiene; re-run via `scripts/optimizer.py
  --preset se3max_pool --slate-id <wk> --request-id <x> --client-id <y>` against each week's existing
  `final_projections_*_main_*.csv` to reproduce) and confirmed this generalizes: the single most-used TE sat
  at 24%-96% total exposure (TE slot + FLEX) across all 8 weeks tested (median ~51%), well above the real
  field's 21-33% FLEX=TE rate in every case but one (Wk2, where RB legitimately won FLEX at 0% TE -- the
  problem is intermittent-but-common, not universal, and tracks which position has the week's best raw value,
  consistent with `CLASSIC_RULES.md` rule 3's finding that RB-vs-TE in FLEX carries no real points penalty
  either direction).
  Two candidate mechanisms were tested and rejected/superseded before landing on the shipped fix: (1)
  capping just the single dominant TE by player_id (`--player-exposure`) fixed that one name but promoted the
  #2 TE to the identical ceiling (whack-a-mole, confirmed on real Wk3/Wk6/Wk8 data -- Wk3's Travis Kelce capped
  at 40% simply handed the role to Dalton Schultz at 47%); (2) `uniqueness` alone (tested at 2/3/4) reduces the
  dominant TE's exposure (Wk8: 91%->65% at uniqueness=4) but plateaus far short of the real-field rate and,
  because the uniqueness constraint never binds until a SECOND lineup exists, only fixes duplication from
  roughly lineup ~40 onward -- it does NOT fix the near-top (#1-19) duplicate-skeleton problem by itself at
  low settings (uniqueness=1), though uniqueness=3 alone DID fully fix the top-20 skeleton-uniqueness metric
  (20/20 distinct on Wk3/6/8) at a small real cost to lineup #1 (-0.3% to -0.8%, likely a solver tie-break
  effect from the added constraint rather than a truly binding one, since lineup #1 always solves before any
  previous-lineup or exposure-count constraint can bind).
- Proposed change: a new generic mechanism, not a revival of the Item 11-zeroed `cl-*` shape terms (those
  penalized a lineup's point total for a shape choice and pushed the wrong direction vs real punt-mix history
  -- this is deliberately different: it never changes a lineup's score, it only throttles how many of the 100
  lineups may repeat the same player or player-at-a-position). Added `--position-exposure POS:PCT,POS:PCT`
  to `scripts/optimizer.py` (classic only, same scope restriction as the existing `--dart-exposure-cap`):
  every player at a named position shares a max-exposure ceiling instead of `--max-exposure`'s uncapped
  default, falling back to any more specific `--player-exposure` entry (same "explicit override always wins"
  precedence `--dart-exposure-cap` already uses) -- so the cap holds regardless of which specific player is
  chalk that week, closing the whack-a-mole gap found above. Combined with raising `se3max_pool`'s own
  `uniqueness` 1 -> 3 to also fix the near-top duplication that `--position-exposure` alone leaves untouched
  (its cap doesn't start binding until a player's count is already used up, which for the dominant TE is
  usually well past lineup #20).
- Validation: tested `--position-exposure TE:0.4` alone across all 8 rebuilt weeks (Wk1-8) -- top-TE exposure
  clamped to exactly 40% in every week (vs 24-96% baseline), distinct-TE count rose in all 8, and lineup #1's
  own projection was UNCHANGED in every single week (not approximately -- bit-identical, which is also
  mathematically guaranteed by construction: every exposure-cap mechanism only locks a player out of lineups
  generated AFTER their count reaches the cap, and lineup #1 is solved first with every count still at zero,
  so it can never be constrained by any exposure cap, old or new). Tested the combined fix (uniqueness=3 +
  `TE:0.4`) on Wk3/6/8: top-20 skeleton uniqueness hit 20/20 in all three (vs 15-20/20 baseline), whole-pool
  skeleton uniqueness hit 100/100 in all three (vs 87-97/100 baseline), top-TE exposure held at 37-40% (no
  whack-a-mole -- cap spread across 11-18 distinct TEs per week instead of concentrating on a #2 player), at
  a combined lineup #1 cost of -0.3% to -0.8% (0.42-1.20 pts/lineup) -- an order of magnitude smaller than
  Item 11's own 50%-cap cost (~5-6%). No infeasibility/feasibility warnings at any tested setting across 14
  separate builds (8 weeks x baseline check + 3 weeks x 3 uniqueness levels + 3 weeks x position-exposure +
  3 weeks x combined). Smoke-tested the final shipped preset end-to-end (`--preset se3max_pool`, no manual
  flag overrides) against the real live Wk8 slate: matches the isolated test numbers exactly (top TE 93%->40%
  exposure, distinct TE count 15->18, top-20 skeleton uniqueness 15->20, lineup #1 projection 133.56->133.14).
  **Not yet validated for cash-rate impact** (time-boxed to a single session per the owner's Wk8 postmortem
  instructions, favoring a same-day ship over exhaustive backtesting) -- flagged as the next live-monitoring
  check, same standing as Item 11's own cash-rate follow-up above. The FLEX=TE *rate* itself was deliberately
  left alone (still ~76-98% on these slates even after the fix) since rule 3 already found no real positional
  penalty to correct for -- this fix only targets single-player/single-skeleton monoculture, not the
  TE-vs-RB-in-FLEX question, which stays settled.
- Track: **owner override of the hard ship bar, same standing as Item 11 above** -- the near-zero cost to
  lineup #1 (mathematically guaranteed for the position-exposure half, empirically small for the uniqueness
  half) and the generalization across 8 real weeks were judged sufficient to ship same-day rather than wait
  for a cash-rate backtest, consistent with the two-track philosophy's low bar to keep testing further.
- Status: **shipped 2026-10-28.** Added `--position-exposure` flag to `scripts/optimizer.py` (new
  `parse_position_exposure_list()`, wired into `build_multi_lineup()`'s per-player exposure-cap computation
  with position-level fallback, plus a feasibility check for a locked player whose position cap would be
  unsatisfiable). `data/optimizer_presets.json`'s `se3max_pool`: `uniqueness` 1 -> 3, `position-exposure`
  added ("TE:0.4"). Mirrored into `dfs_optimizer_frontend/index.html`'s `BUILTIN_PRESETS["SE3Max Pool (100)"]`
  (`ctrlUniqueness` 1 -> 3, new `ctrlPositionExposure` "TE:0.4") plus a new `ctrlPositionExposure` UI control,
  `PRESET_FIELDS` entry, and dispatch wiring (classic-only, guarded the same way other classic-only params
  are); every other built-in preset explicitly sets `ctrlPositionExposure: ""` so switching away from
  "SE3Max Pool (100)" can't leak a stale `TE:0.4` into a Cash/MME/Showdown build. Also added
  `position_exposure` to `cloudflare_worker/optimizer_api/optimizer_api.js`'s param allowlist and
  `.github/workflows/run_optimizer_dispatch.yml`'s flag-building logic so a live UI-dispatched build actually
  sends it through to `optimizer.py`. Live cash-rate monitoring from here, per the two-track note above.

## Aggregate FLEX=TE rate correction (same-day follow-up to the item above)
- Source: owner correction, same day (2026-10-28). The item above explicitly scoped itself away from the
  owner's actual concern ("The FLEX=TE *rate* itself was deliberately left alone... this fix only targets
  single-player/single-skeleton monoculture, not the TE-vs-RB-in-FLEX question") -- the owner's own words:
  "if we're being honest you kind of took my concern and ran with it and turned it into something different
  and fixed that instead of my concern." His actual, repeatedly-stated worry was the volume of TE-in-FLEX
  builds overweighting the real field, not single-player concentration or top-of-pool duplication (which he
  separately said he wasn't sure mattered).
- Evidence: verified directly against the real Wk8 pool, rebuilt live with the shipped item-above fix in
  place (`--preset se3max_pool`, no other changes): FLEX=TE held at 74-75% of the 100-lineup pool -- barely
  down from the pre-fix 81%, still far above the real DK field's 21-33% (`WK3_ROOT_CAUSE_FINDINGS.md` line
  632). Root cause of the gap: `--position-exposure TE:0.4` caps any ONE player's own exposure, not the
  aggregate share of the pool running ANY TE in FLEX -- with 14 different cheap TEs each individually well
  under the 40% cap, they collectively still filled 74-75% of FLEX slots. A fundamentally different lever was
  needed, not a tuning tweak to the one already shipped.
- Proposed change (owner's own framing, implemented directly): "for FLEX, put a cap on it by position. For WR
  and RB, no cap, for TE, let's say 35% to match the field." Added a new `--flex-position-cap POS:PCT` flag to
  `scripts/optimizer.py` (classic only) -- a hard ceiling on the COUNT of lineups whose FLEX slot may be
  filled by a given position AT ALL, regardless of which specific player, implemented by progressively
  narrowing the existing `--flex-positions` eligibility set once that position's quota is spent (same
  all-or-nothing FLEX-restriction mechanism `--flex-positions` already provides, just applied lineup-by-lineup
  instead of for the whole batch). This is a different mechanism from `--position-exposure` (which stays, at
  `TE:0.4`, guarding the TE *slot* itself against single-player monoculture -- a separate question from FLEX
  composition) and is still not a revival of the Item 11-zeroed `cl-*` shape terms: a lineup that happens to
  get a TE in FLEX scores exactly the same as one that doesn't; this only throttles how many times that
  outcome may repeat across the 100.
- Validation: built the real Wk8 slate with `--flex-position-cap TE:0.35` and confirmed FLEX=TE came down to
  exactly 35% (the cap value), RB/WR picked up the remaining 65/100 split roughly 55/10. Cost to lineup #1 was
  checked properly this time -- an initial unseeded before/after comparison showed a ~0.3-0.4 pt gap, which
  turned out to be pure `randomization-pct=5%` noise between separate CLI runs (no `--seed` was fixed), not a
  real cost; re-ran as a controlled fixed-seed A/B (`--seed 42`, identical command otherwise, with vs without
  the new flag) and lineup #1 came back **byte-identical** both times -- same 9 players, same 133.14
  projection. Confirmed mechanically why: the cap can never bind on lineup #1 (every position's fill count
  starts at 0 for the first lineup solved, same guarantee `--position-exposure` already relies on). Smoke-
  tested the final preset end-to-end (`--preset se3max_pool`, no manual flags): FLEX composition 35% TE / 53%
  RB / 12% WR on a clean run, matching the isolated test.
- Track: **owner override of the hard ship bar, same standing as the item above** -- zero measured cost on a
  controlled same-seed test, a direct implementation of the owner's own stated cap values, judged sufficient
  to ship same-day. Cash-rate impact still unvalidated, same live-monitoring status as every other item here.
- Status: **shipped 2026-10-28.** Added `--flex-position-cap` to `scripts/optimizer.py` (`parse_position_
  exposure_list()` reused verbatim -- identical `POS:PCT` shape --  wired into `build_multi_lineup()`'s main
  generation loop: a per-iteration `current_flex_positions` set, narrowed from the base FLEX-eligible
  positions once `flex_fill_count_by_pos` reaches `flex_cap_count_by_pos` for that position, fed into each
  lineup's `solve_lineup()` call in place of the static `flex_positions` argument; fill counts updated by
  reading each finalized lineup's own FLEX-slot position after `assign_roster_slots()`). `data/
  optimizer_presets.json`'s `se3max_pool`: `flex-position-cap` added ("TE:0.35"), alongside the existing
  `position-exposure` ("TE:0.4"). Mirrored into `dfs_optimizer_frontend/index.html`'s
  `BUILTIN_PRESETS["SE3Max Pool (100)"]` plus a new "FLEX Position Cap" UI control, `PRESET_FIELDS` entry, and
  dispatch wiring (classic-only guard, same pattern as Position Exposure); every other built-in preset
  explicitly sets `ctrlFlexPositionCap: ""` so it can't leak into a Cash/MME/Showdown build. Also added
  `flex_position_cap` to the worker's param allowlist and the dispatch workflow's flag-building logic so a
  live UI-dispatched build actually sends it through. Live cash-rate monitoring from here, same as every other
  item on this list.
