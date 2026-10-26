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
