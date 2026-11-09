# Week 9 Postmortem — Checklist (created 2026-11-09)

Session discipline (same rule as every prior postmortem): one topic per dedicated session. Tangents go in the
Parking Lot below, not chased inline.

## 0. Stage 8 gap check — ✅ DONE and fully closed this session
`check_weekly_logging_gap.py` (required first step) found 5 missing slates before any analysis started:
4 Week 8 results-log gaps (`dk_classic_wk8_early/main`, `dk_showdown_wk8_PHI_WAS`, `fd_classic_wk8_main`) and
1 Week 9 pair (`dk_showdown_wk9_JAX_BAL` — missing both ownership AND results). All backfilled from the
already-downloaded DK contest-results exports (FD via `derive_actual_results.py` per SOP) and logged via
`log_ownership.py`/`log_results.py`, committed (`0ce8e83`). This is exactly the Wk8 Item E failure mode
(manual step silently stops, nobody notices for weeks) — caught this time on the first check, which is the
point of Stage 8 existing.

**Follow-up, same session:** the user had the DK showdown TB/CHI (Sun night) contest-results export saved
under the wrong filename (it had been labeled as `BUF_MIN`); user relabeled it to
`dk_showdown_wk9_TB_CHI_08Nov2026_full.csv`. Logged both ownership and results for it (82/82 players matched
each time) — same mechanics as the JAX_BAL backfill above. Updated the Results table and Item B/C below with
the real numbers this unlocked. **Item 0 is now fully closed** — no outstanding logging gaps, every completed
Wk9 slate graded on real data.

## 1. Results (real contest exports, matched by `gmscott81`, cash assumed ≈ top 25% by rank — DK/FD min-cash
convention used in `grade_construction_week.py`; not verified against the exact prize table)

| Slate | Rank / field | Percentile | Result |
|---|---|---|---|
| DK classic main (`main_08Nov2026`) | 2,776 / 19,024 | top 14.6% | **Cashed** |
| FD classic main (`main_08Nov2026`) | 1,107 / 4,761 | top 23.3% | **Cashed** (just inside the line) |
| DK classic early (`early_08Nov2026`) | 2,452 / 3,567 | top 68.7% | Missed |
| DK showdown JAX/BAL (Thu) | 2,255 / 5,945 | top 37.9% | Missed |
| DK showdown TB/CHI (Sun night) | 38,568 / 41,617 | top 92.7% | Missed, badly |
| DK showdown BUF/MIN (Mon) | pending | — | **Not yet final — exclude from this postmortem's cash tally until it completes** |

**Net so far: 2 of 5 completed/confirmed slates cashed** (both main slates), both showdowns played so far
missed — TB/CHI particularly badly (bottom 8% of the field) — Monday's showdown still live. Matches the
user's own read exactly.

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

## Item B. Showdown misses continue — Wk9 confirms 2 more losses in the Wk5+ pattern, 1 still pending
From [[project_wk8_item_b_showdown_recurring_miss]] (Wk5-8: 1/8 cashed, 12.5%, vs Wk1-4's 71%, step-change at
Wk5, p≈0.035 one-sided, n=15, parked — every traced mechanism came back clean). This week, both completed
showdowns missed: JAX/BAL (Thu) at top 37.9%, TB/CHI (Sun night) at top 92.7% (the worst single showdown
result logged all season) — BUF/MIN (Mon) still live. That's **Wk5-9 now 1/10 cashed (10%)**, going to 1/11
(9%) if Monday also misses — the pattern is holding, not reverting.

`grade_accuracy_week.py --week 9`'s showdown edge, now with both Wk9 slates pooled, is **0.179** (corr_ours
0.738 vs corr_salary 0.559) — third-best of the season (Wk3 0.259, Wk8 0.187, Wk9 0.179), not the best as the
single-slate JAX/BAL-only number suggested earlier. Still a good-accuracy week overall, and TB/CHI's 92.7%
finish is as bad as this pattern gets — another clean data point that good projection edge does NOT translate
to showdown cash, reinforcing Wk8's Finding 2 (accuracy is not the Wk5+ showdown story) rather than reopening
it.

**No new action yet** — this stays parked per the Wk8 verdict until there's either a new candidate mechanism or
enough additional weeks to re-run the full comparison with better power. This is its own dedicated session
(per the user's sequencing), not continued inline here — refresh the 15-slate table with Wk9's 2-3 new entries
and take another look at TB/CHI specifically (worst showdown result of the season is worth a closer look even
if the broader pattern stays parked).

## Item C. Accuracy assessment (`scripts/grade_accuracy_week.py --week 9`, full report:
`analysis/weekly_accuracy_review/out/wk9/report.txt`)

**DK classic edge:** corr_ours 0.600 vs corr_salary 0.527 → edge **0.073** — mid-pack for the season (wk5
0.117, wk6 0.153, wk7 0.053, wk8 0.059, wk9 0.073). Not a standout either direction.

**DK showdown edge:** corr_ours 0.738 vs corr_salary 0.559 → edge **0.179** (both Wk9 showdowns pooled) —
third-best of the season (see Item B).

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
**Item 0 (Stage 8 logging gap) is fully closed this session** — both the original 5-slate backfill and the
TB/CHI relabel/backfill are done, nothing outstanding. Results (section 1) are confirmed for every completed
slate; only BUF/MIN (Mon) remains pending. Items A and B get their own dedicated sessions, per the user's
request, rather than being chased further in this one:
- **Item A (next-man-up/cheat-sheet)** — the week's named #1 priority. Needs a session that pulls the actual
  next-man-up cast and grades the AI-probe's calls against real outcomes before deciding anything about the
  cheat sheet.
- **Item B (showdown misses)** — refresh the 15-slate comparison table with Wk9's data (now confirmed: 2
  misses, 1 pending) and take a closer look at TB/CHI's 92.7%-finish specifically, the worst showdown result
  logged all season.
- Item C (accuracy) is reviewed and needs no further session — no multi-week trend, logged for awareness only.
