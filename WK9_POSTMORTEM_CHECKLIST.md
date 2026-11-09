# Week 9 Postmortem — Checklist (created 2026-11-09)

Session discipline (same rule as every prior postmortem): one topic per dedicated session. Tangents go in the
Parking Lot below, not chased inline.

## 0. Stage 8 gap check — ✅ DONE this session, gap found and closed
`check_weekly_logging_gap.py` (required first step) found 5 missing slates before any analysis started:
4 Week 8 results-log gaps (`dk_classic_wk8_early/main`, `dk_showdown_wk8_PHI_WAS`, `fd_classic_wk8_main`) and
1 Week 9 pair (`dk_showdown_wk9_JAX_BAL` — missing both ownership AND results). All backfilled from the
already-downloaded DK contest-results exports (FD via `derive_actual_results.py` per SOP) and logged via
`log_ownership.py`/`log_results.py`, committed (`0ce8e83`). Re-run confirms: **no logging gaps found.** This is
exactly the Wk8 Item E failure mode (manual step silently stops, nobody notices for weeks) — caught this time
on the first check, which is the point of Stage 8 existing.

## 1. Results (real contest exports, matched by `gmscott81`, cash assumed ≈ top 25% by rank — DK/FD min-cash
convention used in `grade_construction_week.py`; not verified against the exact prize table)

| Slate | Rank / field | Percentile | Result |
|---|---|---|---|
| DK classic main (`main_08Nov2026`) | 2,776 / 19,024 | top 14.6% | **Cashed** |
| FD classic main (`main_08Nov2026`) | 1,107 / 4,761 | top 23.3% | **Cashed** (just inside the line) |
| DK classic early (`early_08Nov2026`) | 2,452 / 3,567 | top 68.7% | Missed |
| DK showdown JAX/BAL (Thu) | 2,255 / 5,945 | top 37.9% | Missed |
| DK showdown TB/CHI (Sun night) | — (no results export downloaded yet) | — | Missed (per user; not yet numerically confirmed — **action: export/save the TB/CHI contest results CSV to `data/contest_results/` so this can be logged and graded**) |
| DK showdown BUF/MIN (Mon) | in progress at review time | — | **Not yet final — exclude from this postmortem's cash tally until it completes** |

**Net so far: 2 of 4 completed/confirmed slates cashed** (both main slates), both showdowns played so far missed,
Monday's showdown still live. Matches the user's own read exactly.

## Item A. Next-man-up / cheap-filler traps — this week's #1 topic, open for a dedicated session
User's framing: an unusually injury-heavy week created a lot of cheap next-man-up plays, many of which were
traps the raw optimizer output couldn't distinguish from the real sleepers. The user leaned on manual AI-probe
analysis (sharp/consistent/low-bust-probability filtering) rather than trusting raw projections, and wants to
(a) keep doing that every week, not just this one, and (b) look at folding more of it into the **cheat sheet**
(`scripts/cheat_sheet.py`, frontend-facing weekly top-plays list) so it's less of a manual one-off each time.

Relevant standing context already in memory, not yet fully connected to this:
- [[project_cheap_filler_pattern_recurring]] — confirmed across Wk2/4/6/7/8: cheapest-viable-WR clears the
  $/pt bar regardless of real quality, maxes salary room. This week's injury-driven cheap pool is the same
  shape at larger scale.
- [[feedback_ai_probe_crosscheck_not_exposure]] — AI-probe claims get checked against
  `season_avg`/`recent_form`/`matchup_factor`/`vegas_factor`, never lineup-pool exposure; lean probe questions
  into fringe-value + matchup-trap. This is exactly the muscle the user used manually this week.
- [[feedback_manual_judgment_on_borderline_backups]] — user already excludes/thumbs-downs suspect backups in
  small builds and rides them in MME; this week's volume of suspect backups was unusually high.
- `cheat_sheet.py` already computes `floor` (statline_p10) and `ceiling` (statline_p90) per player as composite
  factors — the raw bust-risk signal may already partly exist in the engine; worth checking whether it's
  currently legible enough on the frontend for a cheap next-man-up call, or whether the AI-probe is doing work
  the engine's own numbers could partially surface on their own.

**One concrete data point from this week's own accuracy run (below, Item C):** the Wk9 classic ownership
budget check shows RB ownership under-called by **-35.3 points of ownership share** (model said 233.3%, real
was 268.7%) — the single biggest ownership-budget miss of any position this week, consistent with a chaotic
injury week where the field piled into next-man-up RBs more than the model expected. Worth checking whether
this ties to specific named players from this week's real injury news before generalizing.

**Not yet investigated — scope for a dedicated session:**
1. Pull this week's actual next-man-up cast (the specific cheap plays the user manually screened) and check
   each one's real outcome vs. the AI-probe's thumbs-up/down/exclude verdict — did the manual screening
   actually add edge over raw projection rank this week specifically?
2. If yes, look at what signal the probe used that the engine doesn't already expose on the cheat sheet (floor/
   ceiling, recent-games participation share, a fresh-injury recency flag) and whether a lightweight version of
   that signal could be surfaced automatically — e.g. a "fresh-role, thin-track-record" badge distinct from the
   existing Value/Leverage Pick badges — rather than requiring a fresh manual AI-probe pass every week.
3. Decide, with real evidence, whether "run the AI-probe every week" is the right standing habit regardless of
   injury volume, or whether it should be reserved for weeks like this one with an unusually large next-man-up
   population.

## Item B. Showdown misses continue — Wk9 adds 2 (soon 3) more data points to the Wk5+ pattern
From [[project_wk8_item_b_showdown_recurring_miss]] (Wk5-8: 1/8 cashed, 12.5%, vs Wk1-4's 71%, step-change at
Wk5, p≈0.035 one-sided, n=15, parked — every traced mechanism came back clean). This week: JAX/BAL (Thu)
missed at top 37.9%, TB/CHI (Sun night) missed per the user (numeric confirmation pending the export above),
BUF/MIN (Mon) still live. That's **Wk5-9 now 1/10 to 1/11 cashed (9-12%)** once Monday settles — the pattern is
holding, not reverting. Thursday's `grade_accuracy_week.py --week 9` showdown edge is **0.248 — the best of the
season** (prior best was Wk8's 0.187), which is a fourth data point (after Wk6 0.118, Wk7 0.185, Wk8 0.187) that
good-to-best projection edge does NOT translate to showdown cash — reinforcing Wk8's Finding 2 (accuracy is not
the Wk5+ showdown story) rather than reopening it.

**No new action yet** — this stays parked per the Wk8 verdict until there's either a new candidate mechanism or
enough additional weeks to re-run the full comparison with better power. Worth refreshing the 15-slate table
with Wk9's entries (and BUF/MIN once final) in whichever session next revisits this.

## Item C. Accuracy assessment (`scripts/grade_accuracy_week.py --week 9`, full report:
`analysis/weekly_accuracy_review/out/wk9/report.txt`)

**DK classic edge:** corr_ours 0.600 vs corr_salary 0.527 → edge **0.073** — mid-pack for the season (wk5
0.117, wk6 0.153, wk7 0.053, wk8 0.059, wk9 0.073). Not a standout either direction.

**DK showdown edge:** corr_ours 0.735 vs corr_salary 0.488 → edge **0.248** — best of the season (see Item B).

**One-week flags (z-scores — single week, not persistent-trend evidence):**
- `RB mid` bias **+1.86** (z=3.2, WEEK flag) and `WR mid` bias **+2.24** (z=3.3, WEEK flag) — both
  over-projected this week, both single-week flags needing a second data point before acting.
- Ownership budget: RB under-called by -35.3 share-points (the standout, see Item A), TE over-called by +22.2,
  WR over-called by +13.8 — this week's injury churn moved real ownership around more than the model's budget
  allocation followed.
- Chalk sizing: 15 real chalk players (≥20% real ownership) this week — the most of any week this season
  (prior max was 13, Wk4) — consistent with the user's "unusually injury-heavy week, lots of cheap plays in
  play" read; top-10 overlap 0.2, on the low end (range 0.1-0.4 all season).

**Bottom line:** nothing here rises to a multi-week trend yet (every flag is single-week), but the RB ownership
gap and the record chalk count both corroborate the user's framing of this as a structurally unusual week, not
just a subjective impression — useful context for Item A, not a standalone action item.

## Parking Lot — carried over from Week 8, status unchanged unless noted
- **Wk8 Item B / this week's Item B** — showdown recurring miss, now tracked together above.
- **Wk8 Item E — ownership weak-spot root cause** — parked as ordinary variance after two dedicated sessions
  (every traced lead came back clean, premise itself didn't survive re-test at p=0.51). No new evidence this
  week; not reopened.
- **`recent_form` equals `season_avg` exactly, every row, every week, all season** — found as a side note during
  the Wk8 Item E investigation, still an open one-line check, not yet looked at.
- **ESPN injury-feed comment text as a role/usage signal** — still test-bar, still just accumulating snapshots.
- **Winners-vs-field positioning (Wk7 diagnosis item 7)** — still parked, "Item 9 Variant D" never opened.

## Next step
This session: Stage 8 gap closed (0), results pulled and confirmed (1), Item A scoped but not yet investigated
(needs its own session — pull the actual next-man-up cast and grade the probe's calls against real outcomes),
Item B updated with Wk9 data (still parked, pattern holding), Item C run and reviewed (no new multi-week
trend). Open items for the user to sequence: Item A (next-man-up/cheat-sheet, the week's named priority) and
getting the TB/CHI showdown results exported so Item B's tracking table and Stage 6/7 logging are complete
once BUF/MIN also finishes.
