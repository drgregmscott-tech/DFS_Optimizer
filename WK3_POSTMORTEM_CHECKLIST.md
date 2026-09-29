# Post-Week 3 Checklist / Roadmap (created 2026-09-27, night before)

Start here next session. This is a working roadmap, not a conclusion — nothing on this list has been root-caused yet.
Order roughly reflects dependency (can't brainstorm the "why do we keep missing" question without results in hand first),
not priority within a section.

## Project philosophy (read this too — it shapes how every section below should be judged)

**Everything is a system waiting to be found. "Judgment" is just the name we give the part we haven't systematized yet
— the goal is to keep shrinking that part, not fence it off as permanently unmodelable.** Repeatable winners aren't
running on feel; they've systematized things we haven't gotten around to systematizing. There's math underneath this,
even the parts that currently feel like judgment calls. And a proven system doesn't win every week — it wins *often*,
not always; a miss doesn't disprove the system.

This means two different bars apply to two different questions, and conflating them is the mistake to avoid:
1. **What ships to production this week** — held to a hard evidence bar (real held-out weeks, not history alone, not a
   simulated field), because real money is on the line every Sunday and an unproven idea can cost you now.
2. **What we keep actively testing** — held to a much lower bar to *enter*, because the cost of investigating a
   promising, mechanistically-sound idea is small, and the cost of never looking again is a permanently missed system.
   A pattern can be directionally strong and still fail a small-sample significance test — that's a sample-size problem,
   not proof the signal is fake.

**The failure mode to watch for is not "we shipped something unproven."** It's "we noticed a real pattern, correctly
judged it wasn't ready for track 1, and then let it die instead of routing it to track 2." Something judged
"inconclusive" is not the same as something judged "wrong direction" — only the second one should actually be dropped.
See §6 below — this is exactly the gap that section exists to close.

## Session discipline (read this too before starting any of the below)

Each numbered section below (§0-§4) is likely **multiple separate sessions**, not one sitting. Past sessions have drifted:
one topic pulls in four adjacent ones and the original thread gets diluted or dropped half-answered. Going forward:

- **One session = one topic from this list.** Pick a section (or a single bullet within one) at the start and say so.
- **New idea comes up mid-session that isn't the current topic → it goes in the Parking Lot below, not into the current
  discussion.** Don't chase it immediately, even if it feels urgent or related.
- **At the end of a session, dump anything unresolved or newly-surfaced into the Parking Lot** with enough context to
  pick back up cold, then either close the topic or explicitly hand off to a new session for it.
- Goal: focused, scientific, systematic. A session that fully resolves one narrow question beats a session that touches
  five and resolves none.

## Parking Lot (add here, don't chase inline)

- **[2026-09-29] UI Showdown builds get zero construction-rule enforcement — own dedicated session.** Found while wiring up
  `construction_lint.py` (see the follow-up note on the construction-rule-capture item below). The `--preset showdown_se` /
  `--preset showdown_gpp` levers (require-CPT-QB, DST/K-captain exclusion, cheap-tier penalty, stack cap, QB-partner bonus,
  the new heavy-side-captain penalty) only apply when `optimizer.py` is invoked with an explicit `--preset` or matching
  `--sd-*` flags. The UI's dispatch path (`cloudflare_worker/optimizer_api/optimizer_api.js` → `run_optimizer_dispatch.yml`
  → `optimizer.py`) passes neither, so **every Showdown lineup built through the UI today runs with all Showdown-specific
  rules off** — including the hard DST/K-captain ban. Only CLI builds (with an explicit preset) get them. The pre-lock lint
  will now surface this as violations on UI-built Showdown lineups, but that's a symptom check, not a fix. Needs: (a) decide
  the right default (should the UI always pass `showdown_se`/`showdown_gpp` for Showdown slates, or expose a preset picker?),
  (b) thread the choice through the frontend UI, the worker dispatch payload, and the workflow's `optimizer.py` invocation,
  (c) verify it doesn't collide with the per-request `client_id` / on-demand-run fixes shipped 2026-09-28 (§1). Frontend +
  worker + workflow change — deserves its own session, not a tack-on.
  **[RESOLVED / SHIPPED 2026-09-29]** Duplicate of the "Partial construction-rule-capture gap" item's own follow-up
  below — see that entry's resolution note for the full writeup (same gap, same fix, same session).

- **[2026-09-29] Partial construction-rule-capture gap — own dedicated session, user will open separately.** From §2 open
  thread 2. This session enforced 5 of the Supported/Weak Showdown construction rules as actual optimizer levers
  (`showdown_se`/`showdown_gpp` presets), but only because we happened to sanity-check that specific mechanism and catch a
  gap (21% of GPP captains landing on K/DST with nothing stopping it). Other Supported/Weak rules in `SHOWDOWN_RULES.md` —
  DST price tier (cheap vs. expensive), which side gets the heavy half of a split, chalk-CPT ownership tier — are still
  purely informational, with nothing in the build pipeline checking or warning on them. This mirrors the classic
  postmortem's "signal found, never captured at build time" gap (§4/Step 4d: strong-projection cash drivers rostered 1/18
  times vs 39/86 for otherwise-similar players) — worth asking, in the dedicated session, whether this is the SAME
  underlying failure mode showing up in both classic and Showdown (a general "rules get documented but not enforced by
  default" problem across the whole optimizer) or two unrelated instances. Needs: (a) an inventory of every Supported/Weak
  rule across both `SHOWDOWN_RULES.md` and classic's equivalent guidance, tagged enforced/soft-warned/informational-only;
  (b) a decision process for which tier each belongs in (this session used "Supported + no legitimate exception = hard,
  Weak or context-dependent = soft or manual" as a rough heuristic, not a formalized rule); (c) probably a pre-lock lint/
  warning report for the informational-only tier, similar to what's already proposed for classic's
  `auto_fallback_team_mismatch` rows, since not every rule can or should be a hard/soft optimizer term.
  **[RESOLVED / ANALYZED 2026-09-29]** See `WK3_CONSTRUCTION_RULE_AUDIT.md`. (a) Inventory: 15 enforced,
  1 partial, 0 soft-warned, 16 informational across both formats. The soft-warned tier was empty in BOTH
  formats. (b) A four-question tier rule (checkable? evidence? unseen exception? weak input like pre-lock
  ownership?). It reproduces every existing Showdown decision. It flags SD rule 7 as soft-term eligible and
  classic's hard skill-vs-own-DST as soft by the rule. (c) Answer: Showdown and classic construction rules share
  one failure mode, which is doc-to-build with no default path. The 4d 1/18 gap is a different problem
  (continuous-signal selection, not a checkable rule) with the same upstream cause. (d) Built a read-only
  `scripts/construction_lint.py` (no optimizer change). Designed but not wired: auto-run after build, a C-SEL
  pool-vs-entry report for 4d, and the ingest-trade section. Side note: `SHOWDOWN_RULES.md`'s "What's live"
  paragraph is stale (K-CPT and rule 12 are now enforced).
  **[FOLLOW-UP DONE 2026-09-29, uncommitted]** See `WK3_CONSTRUCTION_RULE_AUDIT.md` §5. (1) Rewrote `SHOWDOWN_RULES.md`
  "What's live" from the presets file. It had two wrong rule numbers, not one. (2) SD rule 7 → new soft term
  `--sd-heavy-side-cpt-penalty` 0.5 in both Showdown presets. It is small on purpose because `sd-stack-cap` already charges a
  CPT-heavy 4-2 0.75. (3) Classic skill-vs-own-DST **stays hard**: the wk2 Panthers loss came from a Bijan lock, and the constraint
  cost only 0.79 projected pts at decision time (counterfactual re-solve). The pairing has a -0.44 real correlation, so the audit's
  "soft" call was a misread. (4) `construction_lint.py` now runs after every `optimizer.py` build (log + `.lint.txt` sidecar),
  never blocking. **New gap found:** the UI dispatch passes no `--preset`/`--sd-*` flags, so UI Showdown builds get none of the
  Showdown rules. Needs its own session (frontend + worker + workflow).
  **[RESOLVED / SHIPPED 2026-09-29]** This session (dedicated, per the note above). Decision on (a): the UI always sends
  all 9 `--sd-*` flags for a Showdown pool now — never silently off — defaulting to the `showdown_se` bundle's values;
  two new built-in presets ("Showdown SE"/"Showdown GPP") let the user switch to the `showdown_gpp` weights, mirroring
  the existing Cash/SE-3Max/MME preset UX. (b) Threaded through all three layers: `index.html`'s `buildDispatchParams()`
  (new "Showdown Construction Rules" panel, shown only for Showdown pools), `optimizer_api.js`'s `passthroughKeys`
  allowlist, and `run_optimizer_dispatch.yml`'s `flag()`/`bool_flag()` calls into `optimizer.py`. (c) No collision with
  the §1 `client_id` fix — verified by leaving every existing line of those files untouched, added-only diffs. Verified
  live end-to-end, twice: a UI browser test (real Wk3 Atl/GB Showdown pool, intercepted dispatch call, confirmed all 9
  params sent with correct values for both presets, confirmed zero `sd_*` params on a classic pool) and a real GitHub
  Actions dispatch against the pushed commit (`1895a56`) — run
  [36554083874](https://github.com/drgregmscott-tech/DFS_Optimizer/actions/runs/36554083874) shows `optimizer.py`
  invoked with all 9 `--sd-*` flags, and its own `construction_lint.py` output confirms zero DST captains (the hard
  rule held) versus a same-day baseline run *before* the push showing `SD_stack_depth backstop` violations at 30% with
  no flags at all. Committed as `1895a56`. §2's two open threads are now both closed — see below.

- **[2026-09-28] Time lost to on-demand-optimizer-run debugging eating real review time —
  own dedicated session.** From §1: during the last ~20 minutes before DK main lock on
  2026-09-27, time that should have gone to actual lineup review instead went to debugging
  on-demand optimizer runs. Open question, not yet investigated: is tooling fragility under
  time pressure itself part of the "common factor" this postmortem is looking for — three
  weeks running, something has eaten review time or attention right when it matters most —
  or is this a one-off. §0's sessions are now closed, so this doesn't have a natural home to
  fold into; needs its own session starting unstructured (same approach §0 used), not assumed
  to be connected to the lineup-race or cron-reliability bugs already fixed in §1 just because
  they surfaced the same day.
  **[RESOLVED / ANALYZED 2026-09-28]** See `WK3_ROOT_CAUSE_FINDINGS.md` "Parking Lot Item: On-Demand
  Debugging Time Loss". Not a thin pool. A QB `--lock` (Bryce Young) combined with auto-selected
  `--stack-mode qb` teams can never be satisfied, because the auto top-5 ignores the lock. The error
  blamed pool thinness, so the user tried salary floor, site and excludes instead. **Recurring**:
  same player, same trap in wk2 (FD+DK, 16:20-16:45) and wk3 (16:38-16:46); wk1 clean; ~5-11 min
  lost per week. Diagnostics/logic gap, not a crash; it cost time, not a bad lineup. Unrelated to the
  cron bug. Also found a live **git push race** in `run_optimizer_dispatch.yml` (5 runs made lineups
  and then failed at push) — a sibling of the §1 overwrite race that the §1 fix didn't cover.
  **Both fixes shipped 2026-09-28**: the QB-lock/auto-stack pin (verified against the exact failing
  wk3 request) and a 5-attempt pull+push retry. See §1 above.

- **[2026-09-28] Driver-side signal coverage + killer-side bust base rate + salary/role clustering
  of misses that actually make it into submitted lineups — own dedicated session.** From Phase 1
  Step 4 (`WK3_ROOT_CAUSE_FINDINGS.md` Step 4, row-level counts): of 80 driver instances, 44% had
  no distinguishing pre-game signal in our projection (neutral z) and 26% had a projection actively
  below the position mean — i.e. most cash drivers looked ordinary or worse beforehand. Of 80 killer
  instances, 35% were players we projected strongly who then busted — real, but needs a base rate
  (how often do z>=1 plays bust in general, not just among the worst-outcome tail we flagged) before
  calling it elevated vs. normal variance. User's added angle (2026-09-28): this isn't just a signal
  quality question — it's also about which salary tier / role these misses land at, since they're
  reportedly making it into submitted lineups regularly (real losses observed the day this was
  raised, not just backtest noise). Needs: (a) the missing base rate for killer bust-rate, (b)
  whatever's common among the 35 "no signal" drivers (role change, matchup script, price-tier
  crunch), (c) cross-reference against which salary tier/role these misses actually got rostered at
  in real submitted lineups, not just whether they were flagged. Do NOT fold into Phase 2 —
  Phase 2 is a construction-shape question, this is a signal-quality-and-selection question.
  **[RESOLVED / ANALYZED 2026-09-28]** See `WK3_ROOT_CAUSE_FINDINGS.md` "Parking Lot Item: Signal
  Coverage & Selection Deep-Dive": (a) normal variance (z>=1 busts 12.5% vs 20.6% pool); (b) no
  common thread beyond cheap band / cheap QB; (c) track 2 watch: real-lineup busts cluster at
  expensive QB/studs, missed drivers at the cheap band.

- **[2026-09-28] Cheap-tier WR/TE ownership calibration — priority pointer for the standing
  ownership refit (§4 below), not a new separate workstream.** Phase 1 Step 5
  (`WK3_ROOT_CAUSE_FINDINGS.md` Step 5) found the ownership-vs-points miscalibration is not spread
  evenly across salary — it concentrates hard in the cheapest band, sharpest at WR/TE
  (corr -0.36 cheap vs. roughly -0.1 everywhere else). When §4's ownership refit work happens,
  prioritize the cheap band specifically rather than treating all salary tiers as equally in need
  of the fix.

---

## 0. The core question (do this first, unstructured)

Third straight week missing across all 6 slates (Wk1, Wk2, Wk3), with a different surface-level culprit named each time.
User's read: that pattern itself is suspicious — there's likely a shared root cause, not three unrelated bugs and not bad
luck. See memory `project_wk3_common_root_cause_investigation.md`.

**Do NOT start by explaining individual misses — that's the trap that produced a one-off patch each week instead of
catching the real thread.** Start by listing every miss across all 3 weeks side by side, unstructured, before anyone
tries to explain any of them. Only after that list exists, look for the common thread.

Needs before this can run:
- [ ] Final box scores, all Week 3 games
- [ ] Actual DK/FD contest ownership for all 6 slates (FC Rewind — trial ends 2026-10-02, pull this first, it's time-boxed)
- [ ] The actual played lineups: cash x2 variants x6 slates, SE3max pick x6 slates, both MMEs
- [ ] Hindsight-optimal lineup per slate (feed real scores into `replay_validation.py` / `analysis/classic_diag/replay_batch.py`)

Illustrative misses flagged live today (examples, not the root cause — don't fixate on any single one):
- Garrett Wilson under-owned/under-projected on the chalk side despite a low-variance signal (Adonai Mitchell OUT, same-team WR, clean target-share bump)
- Tyler Shough (DK main chalk QB) had low modeled ownership vs. what was actually chalk
- Josh Allen over-projected — flagged pre-lock in chat before this slate went final, and he still got played. Worth
  pulling the actual pre-lock chat flag verbatim: what was the specific concern, why did it get overridden/played anyway,
  and did the game play out consistent with that pre-lock warning or not. This one's different from the other two —
  it's a case where the system (or the user) correctly flagged a risk in advance and it didn't change the decision, which
  is its own process question separate from whether the projection itself was wrong.

**Additional scan to run before the miss-list is "done":** systematically check for any other players with grossly
incorrect ownership and/or projections — specifically look for a pattern of "very low projection, but got heavy real
usage, with no unexpected-injury explanation" (i.e., not explainable by a late-breaking OUT/role change we simply
didn't have — those are separate, already-tracked injury-pipeline issues). This should be a full scan across all 6
slates, not just the 3 examples above, before drawing conclusions about what's common across them.

---

## 1. Data/process bugs found today (2026-09-27) — separate from the modeling question, but compounds it under time pressure

- [x] **Michael Pittman Jr. — investigated 2026-09-28, NOT a bug.** Premise was wrong: Pittman was actually traded to
      Pittsburgh in the 2026 season. DK's own export and FantasyPros ECR both list him PIT vs CIN; $4,700 is a real
      discounted/questionable-tag price (foot injury, limited practice). No ingest collision, no substring/prefix bug.
      What's real but minor: our reference roster's GSIS ID still maps him to IND, so exact match fails and the
      name+position fallback (`scripts/ingest_salaries.py:787-794`) tags him `match_confidence=medium` — the resulting
      player ID is correct, but this will recur for every traded player until the reference roster is refreshed, and
      nothing currently surfaces these fallback matches for pre-lock review. Fix: (1) refresh reference roster from a
      current source, (2) add a pre-lock report of all `auto_fallback_team_mismatch` rows so trades are visible.
      Neither fix applied yet — low urgency, correctly-matched player IDs in the meantime.
- [x] **Optimizer lineup-file overwrite race — FIXED and deployed, 2026-09-28.** Root cause: every build (UI and CLI)
      wrote `output/lineups_multi_{site}_{slate_id}.csv` on top of the per-request file, last write wins — deliberate
      "most recent batch wins" behavior for pivot sourcing that never accounted for concurrent use, confirmed to be the
      normal usage pattern now that the user, his dad, and a friend all build on the same slate at the same time.
      Shipped: an anonymous per-browser `client_id` (auto-generated, `localStorage`, no UI/typing required) threaded
      through the dispatch worker (`cloudflare_worker/optimizer_api/optimizer_api.js`) and
      `run_optimizer_dispatch.yml` into `optimizer.py --client-id`, which now writes
      `lineups_multi_{site}_{slate_id}_{client_id}.csv` (`_multi_lineups_path()` in `scripts/optimizer.py`) instead of
      one shared file. `pivot_finder.py` and `refresh_data.yml`'s pivot gate now pick the newest-by-mtime matching file
      instead of one fixed path. Per-run retention was already solved for free (nothing cleans up
      `output/ui_requests/`) — this only needed to fix the shared "latest" pointer. No further action needed.
- [x] **GitHub Actions scheduled crons — FIXED and deployed, 2026-09-28.** Confirmed via `gh run list` for 2026-09-27
      (Sunday, cron `5 15,16,17 * * 0`, should fire ~15:05/16:05/17:05Z): **zero** `schedule` events fired in that
      window; the only two `schedule` runs that day landed at 18:57Z and 19:43Z, outside the defined hours entirely —
      GitHub's native `schedule:` was drifting/delaying by an hour-plus, not just dropping runs. Retired `schedule:`
      entirely rather than re-tuning it. First attempt (Cloudflare Cron Triggers) was abandoned mid-implementation:
      Workers Free plan caps a whole *account* (not per-Worker) at 5 cron triggers, already spoken for elsewhere on
      this account, and one needed cron string was independently rejected as invalid syntax by Cloudflare's own
      parser. Shipped instead: extended the already-reliable cron-job.org → `cloudflare_worker/scheduled_refresh.js`
      `fetch` → `repository_dispatch` relay (previously only used for the near-lock window) to cover all cadences via
      a `kind` query param (`vegas`/`full`/omitted-for-near-lock). `refresh_data.yml` has no `schedule:` block at all
      now; cadence detection reads `github.event.action`. 6 new cron-job.org jobs created and confirmed live
      (3 vegas-only: Tue-Fri 11AM CT, Sat 10AM+4PM CT, Sun 10/11/12 CT; 3 full-refresh: Thu+Mon 6PM CT, Sat 7AM CT,
      Sun 3/7/11AM+2PM CT). No further action needed.
- [x] **Time lost to on-demand-optimizer-run debugging — FIXED and deployed, 2026-09-28.** Root cause: a QB `--lock`
      combined with auto-selected `--stack-mode qb` could pin the stack to a different team than the locked QB's,
      forcing two QBs into one slot (guaranteed Infeasible) — recurring wk2 and wk3, same player, same trap, costing
      5-11 minutes per week including the last ~20 minutes before wk3's DK main lock. See the Parking Lot entry below
      for the full investigation. Shipped: `resolve_stack_candidates()` in `scripts/optimizer.py` now pins the
      auto-picked stack team to a locked QB's own team instead of ranking independently, hard-errors if locked QBs
      span multiple teams with no `--stack-team`, and warns on an explicit `--stack-team` that conflicts with a
      locked QB. Verified by re-running the exact failing wk3 request — now produces 10/10 lineups. Also fixed a
      second bug found during the same investigation: `run_optimizer_dispatch.yml`'s commit-and-push step now
      retries pull+push up to 5 times on a concurrent-push race instead of failing the run outright (sibling of the
      overwrite race above; that fix didn't cover this spot). No further action needed.

---

## 2. FC data dives — classic + showdown [NOT fully closed — open thread 1 pending Wk4 data; open thread 2 resolved 2026-09-29; classic still open, see §3]

Two FC-derived analyses landed 2026-09-26 and were discussed/acted on 2026-09-28. Both are folded into `SHOWDOWN_RULES.md` and
superseded where real data replaced simulated-field conclusions — but §2 as a whole is **not** fully closed; two threads remain,
tracked explicitly rather than left implicit:

- [x] **`HANDOFF_showdown_history_findings_2026-09-26.md`** — 49 DK Showdown slates (2023-2025), simulated-field percentiles,
      chalk/leverage strategy tests. Superseded: its lineup-level construction conclusions (§6-§8) were simulated-field-caveated,
      and this session pulled real Showdown lineup data (see §3 below) that replaces them with real-field answers.
- [ ] **Open thread 1 — `HANDOFF_showdown_ownership_refit_2026-09-26.md` (the `lsal` candidate).** Its reactivation condition
      ("2+ more real Showdowns since frozen") was still not met as of 2026-09-28 (same 4 real slates as when frozen). **We
      expect at least 2 more real Showdown slates this week (Wk4)** — re-check the condition once those are logged in
      `ownership_actual_log.csv`, and if met, re-test the candidate against them before deciding to ship. The confound this
      doc originally flagged as missing (does the QB-CPT-partner finding survive a projection/salary control?) was already
      resolved this session via `analysis/showdown_history/lineup_study_qb_partner_ctrl.py` — that part does not need redoing.
      The *chalk-tilt* idea was also independently re-tested with OUR modeled ownership and found Not supported pre-lock — that
      part is closed, only the `lsal` ownership-calibration candidate itself is still pending real Wk4 data.
- [x] **Open thread 2 — partial rule-capture gap, routed to the Parking Lot below for its own dedicated session.** This
      session built and enforced 5 real-field-Supported construction rules as actual optimizer levers (`--sd-require-cpt-qb`,
      `--sd-cheap-tier-penalty`, `--sd-stack-cap`/`-penalty`, `--sd-qb-partner-bonus`, `--sd-exclude-cpt-positions`/
      `--sd-k-cpt-penalty` — the last pair added after a real-slate sanity check caught 21% of captains landing on K/DST with
      none of the first four levers touching that). But several OTHER Supported/Weak rules in `SHOWDOWN_RULES.md` — DST price
      tier (cheap vs. expensive), which side gets the heavy half of a 4-2/3-3 split, chalk-CPT ownership tier — remain purely
      informational. Nothing in the build pipeline checks or warns on those; a build can silently violate them. Same failure
      shape as the classic postmortem's "signal found, never captured at build time" gap (§4/Step 4d).
      **[RESOLVED 2026-09-29]** The construction-rule levers themselves (5, then the DST/K pair, then this session's UI
      wiring) are now fully captured end-to-end for the enforced tier. The remaining informational-only rules (DST price
      tier, heavy-side-split, chalk-CPT ownership tier) are a separate, smaller scope — tracked in
      `WK3_CONSTRUCTION_RULE_AUDIT.md`'s inventory, not blocking this thread's close. See the Parking Lot entry below for
      the full resolution writeup (UI dispatch fix, verified live twice).

**Real work this session (superseded the FC-derived analysis above): 142 REAL DK Showdown contests, 14.9M entries, 2022-2026**
(not simulated — see §3's Showdown item). Real field cash-lift/return by construction shape, rule-by-rule verdicts against
`SHOWDOWN_RULES.md`, and a projection/salary-controlled re-check of the QB-partner finding. Committed and pushed 2026-09-29
(`9b85abf`), sanity-checked against two real slates. See `HANDOFF_showdown_lineupstudy_findings_2026-09-28.md`,
`HANDOFF_showdown_construction_detail_2026-09-28.md`, and `SHOWDOWN_RULES.md`'s "Optimizer enforcement" section.

---

## 3. FC Lineup Study extraction — pulled 2026-09-26; SHOWDOWN analyzed 2026-09-28, CLASSIC analyzed 2026-09-29

37.1M lineups across 2022-2026 (648 files, ~800MB) sitting in `data/fc_history/lineup_study/`, extracted 2026-09-26.

- [x] **Showdown slice (142 of 648 files, 14.9M entries): analyzed 2026-09-28.** See §2 above for the full writeup and what
      shipped to the optimizer. Do NOT read this as "the Lineup Study is done" — it's one contest format out of several.
- [x] **Classic slice (the remaining ~506 files, ~22M+ entries — SE/3-max/20-max/double-up, all the formats gmscott81
      actually plays most weeks): still completely unanalyzed.** This is still the single biggest untouched data asset in
      this whole postmortem. Same real-lineup advantage applies here as it did for Showdown: real ranks/scores/payouts,
      not the simulated fields the classic Phase 1/2 analysis (§0/§1) had to rely on for its construction-level questions.
      This deserves its own dedicated session, not a tack-on to whatever else is running.
      **[RESOLVED / ANALYZED 2026-09-29]** See `HANDOFF_classic_lineupstudy_findings_2026-09-29.md`. The pull has 431 classic
      files. 410 were analysed (21.9M entries): SE 140, 3MAX 66, 20MAX 139, DU 65. 5 were dropped as truncated by the row cap
      and 16 for having under 1k entries. FC per-player scores are exact on classic, so no re-solve was needed except on 6 files.
      Headline: higher realized ownership predicts cash rate and capped return after an FC-projection control, among
      ≤$500-left / top-40%-projection lineups, in every GPP format and 4/4 seasons. Among SE quality lineups, the most-owned fifth
      returned 1.20x [1.11,1.28] and the least-owned 0.80x. Uncapped, the top fifth was flat (1.04x).
      At player level, ownership predicts points beyond FC projection and salary at every position (+1.1 to +2.8 pts per SD, 4/4).
      Phase 2 at scale:
      - Hindsight chalk benchmark: confirmed.
      - QB+2: confirmed, mainly on return (1.10-1.14x), but at about 1/3 of the claimed cash lift. QB+3 is not a further gain.
      - "0 punts bad": confirmed.
      - Salary use: confirmed.
      - "Cheap QB cashes": contradicted. It is null after a projection control. The #1-owned QB is the real signal (+5 cash).
      - "More punts / more studs": contradicted.
      - TE FLEX as a cashing trait: contradicted. RB FLEX is best.
      New Supported checks: DST not facing own players; DST $2.8-3.1k over $3.6k+.
      gmscott81's own entries show a regime change. 2022-24 cashed ~63% at the 85th ownership percentile; 2025-26 cashed at base
      at the 54th (small n, directional).
      Nothing shipped. The chalk result uses post-lock ownership and needs a pre-lock re-test before any tilt.
      **Data gap: 2026 has only wk1-2 classic, so wk3 is missing. Pull it before the 10/02 trial end.**

See memory `reference_fc_lineup_study_extraction.md` for extraction mechanics and known gaps (a few big 20-max contests
only partially captured; SE_big missing a couple weeks — confirmed in the Showdown analysis that the ~25k-row cap issue
is classic-only and does NOT affect the Showdown files, which are complete).

- [ ] Trial ends **2026-10-02** — if there's anything left to pull (2026 wk3+, trimmed contest types), do that first before
      it's gone.
- [ ] First real analysis pass: what does the actual realized field's construction look like (stack rates, salary usage,
      chalk concentration) versus what our simulated fields / replay assumptions have been using? This directly bears on
      the Showdown ownership refit above (simulated field is known to under-represent real correlation/stacking) and
      potentially on the classic-side construction rules too.
- [ ] **Framing note (important, don't lose this):** the point of this analysis is NOT to study the top winning lineups
      in isolation. Focus on the general/larger trend: across many contests, what do players who *consistently cash*
      have in common that players who don't cash, don't? Look for a repeatable, general pattern in player-level behavior
      (role, usage, price tier, correlation, whatever it turns out to be) rather than reverse-engineering one-off winning
      lineups that may just be variance.
- [ ] Cross-reference against this week's actual misses once results land — does the real field's behavior explain why our
      lineups underperformed in a way the simulated-field analysis couldn't have caught?

---

## 4. Standing pick-up plan (pre-existing, still applies — from `HANDOFF_fc_history_ownership_findings_2026-09-26.md`)

Steps A-H, unchanged, still the ordered plan for ownership/projection refit work once Wk3 results land:
A) log results + real ownership, export FC Wk3 Rewind before trial ends; B) ownership refit (rebuild leak-free wk1-3,
refit both ownership models LOWO, FFC-floor test, status-apply ownership check); C) lambda re-verify on full optimizer;
D) QB1-specific stack/recal; E) sigma/yards double-count fix; F) Week 1 sentinel path (next season); G) verified
inactives source; H) FC-vs-ours wk3 re-run. Full detail in the handoff doc; don't re-derive, just execute in order.

**Phase 1/2 findings routed here (added 2026-09-28, not yet re-ordered into A-H):**
- [ ] Step B should fold in the Phase 1 mechanism corrections: FFC-unlisted ownership cliff (wk3), chalk_score
      *ranking* miscalibration (wk1-2, not the softmax temperature), softmax top-end cap (secondary, TE/top-3 WR),
      and the cheap-DST chalk_score ranking miss (recurring wk1→wk3, e.g. Jets/Titans). Prioritize the cheapest
      salary band specifically — that's where the miscalibration correlates with points (Step 5, WR/TE corr -0.36
      cheap vs. ~-0.1 elsewhere). See `WK3_ROOT_CAUSE_FINDINGS.md` Step 4a/4b/5.
- [ ] Step D (QB1-specific stack/recal) should fold in the Phase 1 + Phase 2 QB-bust finding: our top-projected
      QBs busted repeatedly (Burrow wk1, Herbert wk1, Caleb Williams wk2, Allen + Lamar wk3), and Phase 2 confirmed
      our QBs are priced above even the non-cashing field's average QB salary. Treat "QB price/bust check" as part
      of this step, not a separate workstream. See `WK3_ROOT_CAUSE_FINDINGS.md` Step 4e and Phase 2 Step 1.
- [ ] Aaron Jones-style vacated-volume reallocation (OUT teammate's carries/targets not redistributed;
      `statline_model.py` A4 path) — projection-pipeline fix, add to this plan wherever B/D land it. See
      `WK3_ROOT_CAUSE_FINDINGS.md` Step 4c.
- [ ] Phase 2 chalk-baseline result used post-lock (hindsight) ownership. Before leaning on the 9/9-beat-us result
      as evidence for anything in B-D, rerun the same chalk-baseline construction using our own *pre-lock* modeled
      ownership, to check whether the result survives without hindsight. See `WK3_ROOT_CAUSE_FINDINGS.md` Phase 2
      Step 1.

---

## 5. Frontend / rule changes to make (not root-cause work — straightforward additions, own session)

Four items raised together 2026-09-27, unsure yet how they connect to §0-§3 but worth their own focused session:

- [ ] **Construction rule: flag/avoid 2 WRs from the same team with no correlating QB rostered.** i.e. don't let the
      optimizer (or a manual build) roster two same-team pass-catchers without their own QB unless it's a deliberate
      leverage/bring-back-less call — right now nothing warns on this.
- [ ] **Rule: prefer filling FLEX with an afternoon-slate player when possible**, for main-slate builds spanning multiple
      windows — presumably a leverage/uniqueness or information-timing rationale; get the actual reasoning nailed down
      when this gets built, not just "add the rule."
- [ ] **Show projected team totals, not just game totals**, in whatever view currently shows Vegas info — right now it's
      game-level (over/under, implied total split maybe only implicit); needs to be explicit per-team.
- [ ] **Show expected pace of play per game, if obtainable** — check what data source would even feed this (plays/game,
      neutral-script pace, etc.) before committing to it; flagged as "if possible," not confirmed feasible yet.
- [ ] **MME stack-depth setting (added 2026-09-28, from Phase 2).** All 40 of our wk2/wk3 MME entries used the
      identical QB+1-plus-one-opponent template — never QB+2 or deeper. Looks like a fixed optimizer setting, not
      a projection/player problem. The real cashing field built QB+2 (or more) roughly 30% of the time and it
      carried real lift (+3.7pt for QB+2, +6.7pt for QB+3, per Phase 2 Step 2). Add a setting/rule that allows or
      requires QB+2 in some share of an MME pool. See `WK3_ROOT_CAUSE_FINDINGS.md` Phase 2 Step 2, and
      `analysis/classic_diag/wk3_postmortem_phase2_shape.csv`.

These are frontend/product changes, not analysis — don't conflate with the §0 root-cause dig even if the impulse is to
tie them together. Give them their own session per the discipline above.

---

## 6. Revisit past "not shipped" decisions under the two-track philosophy (own dedicated session)

Prompted by the philosophy discussion 2026-09-27: several past refits were judged "inconclusive" or "not shipped" under
a single evidence bar, when some of them may actually be track-2 candidates (right direction, underpowered, not wrong
direction) that got filed away instead of kept alive. This needs a dedicated session — don't fold it into §0's Wk3
root-cause dig, they're different questions.

**Task:** re-read the parked/rejected list and sort each item into one of two buckets — **(a) actually wrong direction,
correctly killed**, or **(b) right direction, just underpowered, should be an active track-2 item, not dead.** Candidates
already identified as worth a look:

- [ ] **Showdown ownership refit (log-FLEX-salary candidate)** — explicitly parked with a stated re-test condition
      ("ship after the candidate beats production on 2+ more real Showdowns"). Check: are we at 2+ real Showdowns yet,
      and does it still win? This one already has its own reactivation trigger, easiest to revisit first.
- [ ] **QB/projection-stack refit** — RB/WR/TE improved every season 2021-26, but the whole package was shelved because
      QB1 specifically got worse when trained on all QBs including backups. Ask: should RB/WR/TE have shipped on its own,
      separate from the QB1 problem, instead of the good and bad parts being bundled into one pass/fail decision?
- [ ] **Sigma/yards-variance refit** — the underlying mechanism was validated (sim yards-sd corrected from 1.8-2.1x too
      wide down to ~1.0), but parked as "no lineup benefit shown" at current sample size. Sample-size problem, not a
      signal problem, by this project's own read — reconsider as track 2.
- [ ] **FFC-floor / ownership model refits more broadly** — several tested "inconclusive" rather than "wrong direction";
      worth the same sort.

Output should be an explicit list per item: which bucket, and if (b), what specifically would move it to "ready to ship"
(more weeks, a narrower scope, a different cut of the data) — not just "keep an eye on it."

---

## How to use this tomorrow

1. Pull results + ownership (§0 needs-list) and §2/§3 FC exports before anything else — the Showdown items and the Lineup
   Study trial both have the 2026-10-02 deadline hanging over them.
2. Do the unstructured miss-list first (§0), resist the urge to explain as you go.
3. Only after the miss-list exists, bring in §2/§3 FC findings as evidence for or against whatever pattern emerges —
   don't let them set the frame before the miss-list does.
4. §1 process bugs run in parallel, independent of the brainstorm — pick those up whenever, they don't need results.
5. §5 frontend/rule changes also run independent of results — pick those up whenever, as their own session(s).
6. §6 (revisiting parked decisions) is independent of results too, but should wait until the philosophy framing is
   settled — no rush, but don't let it get lost either.
