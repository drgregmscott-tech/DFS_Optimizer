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
- Evidence: `site.api.espn.com/apis/site/v2/sports/football/nfl/injuries` — the exact endpoint
  `scripts/status_check.py` already polls for the OUT/QUESTIONABLE/etc. `status` field — also returns
  `shortComment`/`longComment` fields with free-text, beat-writer-sourced role/usage analysis (e.g., "...Knight
  could begin to put himself in position for regular snaps moving forward," attributed to a named team-site
  reporter). Confirmed live via direct fetch 2026-10-26. This text is currently fetched and discarded —
  `status_check.py` only extracts `status`. Zero additional API cost or approval-gate exposure (plain HTTP,
  already in the pipeline) — a clean alternative to X/beat-writer monitoring, which is blocked by the
  Claude-in-Chrome unattended-approval wall (see [[project_x_injury_monitor_retired_2026-10-24]]).
- Proposed change: not yet scoped. Candidate direction: extract/flag forward-looking role-change language from
  these comment fields (e.g. phrases suggesting expanding/shrinking usage) as a new signal feeding the
  projection or at minimum a manual-review flag — needs real design + testing before any model input, same
  two-track discipline as every other lever here.
- Track: test-bar (worth investigating further) — confirmed the data exists and is free/automatable; nothing
  built or tested yet.
- Status: open, not yet scoped.

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
- Proposed change: `scripts/classic_field.py`'s `stack_boost` multiplier applies independently to every
  skill-slot draw (RB, RB, WR, WR, WR, TE, FLEX) when filling a lineup around a boosted QB, and was calibrated
  only against the stack≥1 rate (per the function's own doc comment) — nothing checked the higher-order stats.
  That single-parameter boost compounds across slots, correctly hitting ≥1 while overshooting ≥2/3+/4+.
  Needs recalibration against stack≥2 / 3+-from-one-team directly, likely via capping how much the boost
  compounds per additional correlated slot rather than just rescaling the one multiplier. Not yet
  designed/built.
- Track: test-bar (worth investigating further) — real, data-driven finding; no code change built or tested.
- Status: open, not yet scoped.

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
  change how well IPF converges to target ownership. Not yet designed/built.
- Track: test-bar (worth investigating further) — real, data-driven finding; no code change built or tested.
- Status: open, not yet scoped.
