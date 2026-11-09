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

## Item A. Next-man-up / cheap-filler traps — ✅ INVESTIGATED this session (2026-11-09), verdict: YES, a real
cheat-sheet signal exists; expansion direction identified; three real gaps found along the way, split into
their own items (D/E/F) rather than chased here
User's framing: an unusually injury-heavy week created a lot of cheap next-man-up plays, many of which were
traps the raw optimizer output couldn't distinguish from the real sleepers. The user named 18 specific players
he was unsure about: Tyler Allgeier, Alvin Kamara, Woody Marks, Jonah Coleman, Devin Singletary, Rhamondre
Stevenson, Ollie Gordon II, Antonio Williams, Malik Washington, Xavier Worthy, Jordan Watkins, Rashee Rice,
Cooper Kupp, Greg Dulcich, Chris Bell, Tre Tucker, Jaylen Waddle, Makai Lemon.

**Bust definition used (user's own scale, DK: <1.5x salary = BUST, 1.5-2x = bad, 2-3x = ok, 3-4x = good, 4x+ =
fire; FD compressed: <1x BUST, 1-2x bad, 2-3x ok/baseline, 3-4x fire, 4x+ elite).** Result on DK: **9 of 18
clean busts, 4 "bad," 3 "ok," 1 "good" (Jonah Coleman), 1 "fire" (Jordan Watkins)** — a real, unusually
trap-heavy cast, confirming the user's read with actual numbers rather than just intuition.

**Cheat-sheet signal check — the "Range" bust-risk line works, but only for WR/TE this week:**
Antonio Williams, Greg Dulcich, Malik Washington, Jaylen Waddle, and Rashee Rice/Xavier Worthy (FD) all got
**"high bust risk"** in their rationale's Range line — every one of them busted. For RB, the opposite: Woody
Marks, Ollie Gordon II, and Tyler Allgeier all got **"normal swing"** and all three busted; only Stevenson got
"normal swing" and did NOT bust (correctly). **Verdict: the underlying signal is real and already live on the
cheat sheet — it just under-reads RB bust risk specifically this week (n=5 RBs, one week — not yet a
confirmed persistent gap, but a clear miss worth watching).**

**Cheat-sheet expansion recommendation — first pass, user pushback incorporated, NOT ship-ready:** first
draft of this recommendation was "flag the Value-Pick-vs-high-bust-risk contradiction explicitly." User's
correction, important: **most of the original 18 weren't on the cheat sheet at all** (only Dulcich/Washington
carried the Value-Pick+high-bust-risk combo) — a badge-reconciliation tweak only touches the subset that was
already visible and does nothing for the bigger miss (Coleman, Watkins, Singletary, Kupp, Tucker, Chris Bell,
Lemon, none of which appeared on either cheat sheet). User's actual design instinct: **this needs to be aware
of what the optimizer's own lineup-building is doing** — the optimizer, working the full salary-cap
combinatorial problem, finds and locks in specific cheap plays at specific salary slots as high-floor
pay-up pieces; a per-position, optimizer-blind composite ranking (what `cheat_sheet.py` does today) is a
different and narrower lens than that. Also flagged: this can't be judged on the text description alone —
**user wants to see an actual mockup/output before concluding whether any specific redesign works.** Not
resolved this session — needs its own scoped follow-up that (a) looks at what pivot_finder.py/the optimizer's
lineup output already surfaces about which cheap plays get locked in and why (per CLAUDE.md's standing
guidance to extend existing lineup-system code, not rebuild it), (b) produces a real mockup against a past
week's data before any ship decision, and (c) likely incorporates whatever Item D's recent-trend fix adds,
since a usage-trend signal is exactly the kind of thing that separates a Coleman from a Marks/Gordon/Allgeier
in a way the current composite can't. Also noted for the record: the rationale's "Matchup" sentence (e.g.
`DET allows 1.63x league-avg to TEs`) is display-only — the composite's real `matchup_factor` is hard-coded
to a flat 1.0 project-wide, so that sentence currently carries zero weight in ranking or badging despite
reading as if it does.

**Three real gaps surfaced while working through specific names, confirmed against data, NOT fixed in this
session (one topic per session) — split into Items D, E, F below:**
- Why Jonah Coleman (the week's best play, Harvey out / Dobbins not every-down, usage trending up) wasn't
  flagged anywhere → **Item D**, and the user wants this fixed, not just investigated.
- Why Allgeier/Gordon (bad matchups + unfavorable game script) busted despite a "normal swing" read →
  **Item E**, a real missing feature candidate.
- Jordan Watkins (SF's only real receiving option with McCaffrey/Kittle, target-starved role) — **Item F**,
  worth checking, not yet confirmed as the same mechanism as D.

AI-probe retooling is explicitly **not** prioritized here per the user: projections feed the probe, not the
other way around, so probe-sharpening is the last item in this family, after D/E/F are addressed — see Item G.

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

## Item D. `recent_form` == `season_avg` bug + missing recent-usage-trend signal — 🔴 TO FIX, user priority,
own dedicated session
Promoted from the Week 8 parking lot (found as an unconnected side note during the Wk8 Item E investigation)
now that it's tied to a concrete miss: re-checked this session, `recent_form` is still mathematically
identical to `season_avg` for 100% of rows, Week 9 included — the model has no way to see a player's role
trending up (or down) recently. This is exactly the signal the user used to correctly pick Jonah Coleman over
Marks/Gordon/Allgeier (usage increasing in recent weeks, on top of the Harvey-out/Dobbins-not-every-down depth
chart read). Separately, Coleman's `proj_rush_att` (7.9) was the *lowest* of the five RBs in that cluster —
the model's usage input was moving the wrong direction while the real situation moved in his favor. Likely the
same underlying mechanism as [[project_wk9_sanders_autopromote_gap_and_jsn_ownership]] (a confirmed-starter
role not flowing into the projection) — worth checking both together rather than assuming they're separate.
**User wants both halves fixed: the duplicate-field bug itself, and giving the model real ability to see a
rising/falling recent-usage trend** — not just diagnosed. Own session.

## Item E. Missing game-script/spread-direction feature for RB usage — 🟡 NEW GAP, candidate feature, own
dedicated session
Allgeier and Gordon both busted on bad matchups against top-tier defenses where the user's read was that game
script (team expected to trail) would shift volume toward passing and away from rushing, independent of the
team's own implied scoring total. Checked: Allgeier's `implied_total` (15.47) was in fact the worst of any RB
on this list, and the model did register "low-scoring" in his game-environment read — but it still badged him
Value Pick and read his Range as "normal swing" anyway, so even the signal that does exist isn't propagating
into the composite/badge correctly. More importantly, there's no spread/win-probability/favorite-vs-underdog
feature at all in the projection file — only `implied_total` and a `vegas_factor` built from it, neither of
which captures "this team is more likely to be trailing and therefore pass-heavy." Real, testable gap:
spread-direction as an RB-usage discount. Own session — test against historical data before shipping, same as
any other candidate lever.

## Item F. Target-competition / role-clarity check for Jordan Watkins-type cases — 🟡 WORTH CHECKING, lower
urgency, own session
Watkins (SF) was a clean miss on both sides — `proj_targets` was only 2.5, but in reality he, McCaffrey, and
Kittle are the *entire* real receiving corps for that team right now, no competition for volume. Possibly the
same mechanism as Item D (role/usage signal lagging real depth-chart reality), possibly a distinct "target
competition" gap specific to receiving volume rather than a recency-trend issue. Not yet confirmed either way
— scope a session to check whether this is Item D in different clothing or a separate thing worth its own fix.

## Item G. AI-probe question-template retooling — explicitly LAST in this family, after D/E/F, not before
User's correction, important to get right: **projections feed the probe, not the other way around.**
Probe-sharpening (tighter questions on role certainty, game script, recency — the "field knowledge" the user
described combining in his head) is real and worth doing eventually, but it's pointless to retool probe
questions around signals (`recent_form`, game script) that don't exist or are broken in the underlying data
yet. Sequence: fix/confirm D and E (and resolve F) first; only then revisit the probe's own templates
(`AI_PROBE_QUESTION_TEMPLATES.md`). Not scoped further than that ordering note for now.

## Parking Lot — carried over from Week 8, status unchanged unless noted
- **Wk8 Item B / this week's Item B** — showdown recurring miss, now tracked together above.
- **Wk8 Item E — ownership weak-spot root cause** — parked as ordinary variance after two dedicated sessions
  (every traced lead came back clean, premise itself didn't survive re-test at p=0.51). No new evidence this
  week; not reopened.
- **ESPN injury-feed comment text as a role/usage signal** — still test-bar, still just accumulating snapshots.
  Possibly relevant to Item D/F's role-clarity gap once those are scoped — worth a cross-reference then.
- **Winners-vs-field positioning (Wk7 diagnosis item 7)** — still parked, "Item 9 Variant D" never opened.

## Next step
**Item 0 (Stage 8 logging gap) is fully closed.** Results (section 1) confirmed for every completed slate;
only BUF/MIN (Mon) remains pending. **Item A is closed on the diagnosis side** — verdict: yes, a real
cheat-sheet bust-risk signal exists (works for WR/TE, under-reads RB this week) — but the *expansion
recommendation* is explicitly NOT ship-ready: the user correctly pushed back that most of the original 18
weren't on the cheat sheet at all, so a badge-reconciliation tweak alone doesn't address the bigger miss, and
any redesign needs to be optimizer/lineup-aware (not just a per-position composite tweak) and needs a real
mockup before judging it, not just a text description. That redesign work is deferred, not abandoned — see
the recommended sequence below.

**Recommended working order across D/E/F/G/A-redesign/B** (asked for explicitly 2026-11-09): these aren't
independent — F's answer depends on what D's fix actually captures, and the Item A redesign should incorporate
whatever Item D produces, so alphabetical-by-letter isn't the right order. Suggested sequence:
1. **Item D first** — most concrete, user explicitly wants it fixed (not just diagnosed), and it's the
   biggest likely unlock for the other items (a working recent-trend signal plus the Sanders-autopromote
   connection could resolve part of F and feed directly into the Item A redesign).
2. **Item F right after D** — quick to check once D's fix exists: does the Coleman-style trend/role fix also
   resolve the Watkins-style target-starved case, or is it genuinely separate? Cheap to answer once D lands,
   expensive to guess at blind.
3. **Item E** — independent research/feature-build track (game-script/spread), can run before or after
   D/F; doesn't block or get blocked by them.
4. **Item A redesign (cheat sheet ↔ optimizer-aware, mockup-first)** — after D (and ideally E) exist, since
   the redesign should use whatever new signals they produce and should be judged against real output, not
   described in the abstract.
5. **Item B (showdown misses)** — fully independent of all of the above; slot in whenever, no dependency
   either direction.
6. **Item G (AI-probe retooling)** — explicitly last, only after D/E/F/the Item A redesign are in place.
Item C (accuracy) is reviewed, needs no further session.
