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

## Item A. Next-man-up / cheap-filler traps — ✅ CLOSED (2026-11-09), diagnosis + redesign mockup both done;
real cheat-sheet signal confirmed, three gaps split off (D/E/F, all now also closed), optimizer-aware
flagging mockup built and validated on real Wk9 data, not yet wired into the live pipeline
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

**Redesign mockup — done this session (2026-11-09), real data, not yet shipped.** Full writeup:
`analysis/wk9_item_a_lineup_aware_flagging/RESULTS.md`. Per the user's own design instinct (and explicit
request to see real output, not a description), built a cross-reference of `pivot_finder.py`'s exact existing
input (`lineups_multi_dk_dk_classic_wk9_main_08Nov2026_shared.csv`, 20 real built lineups) against each
player's real exposure % and `final_projections`' `statline_p10` floor, using `cheat_sheet.py`'s own existing
"high bust risk" absolute floor bar (`ABS_FLOOR_HIGH_RISK=3.0`) — no new model or data source, pure
cross-reference of two things the pipeline already produces. **Flag = top-tier optimizer exposure (≥30% this
week, the same tier as true studs McCaffrey/Lamb/Kittle/Purdy/Gibbs) AND a thin absolute floor.**

Result on the real 20-lineup build: 7 flagged (Worthy, Sutton, Schultz, Dulcich, Washington, Boston,
Raridon) — 2 clean DK busts (Dulcich, Washington), 1 more "bad" (Schultz), 4 false positives that were all
fine-to-good, not disasters. **Correctly flagged zero true studs** at the same exposure tier (McCaffrey/Lamb/
Kittle/Walker/Purdy/Mahomes/Gibbs/Nacua all correctly skipped) — the real design win, since a naive
cheap-and-thin-floor rule risks exactly that false positive (an early draft using a relative bust-ratio instead
of the absolute bar incorrectly flagged George Kittle, a $6K elite TE, before switching to the absolute bar
fixed it). Missed Ollie Gordon II (busted, p10=3.94 just above the 3.0 bar) — the SAME RB-blind-spot gap
already documented above, not newly introduced or newly solved by this exercise. 9 of the original 18 named
players never appeared in this 20-lineup build at all — this flag only ever sees players the optimizer
actually rostered, a real but partial answer (doesn't address "never considered this player," a separate
question).

**Shipped (2026-11-09).** Wired into `dfs_optimizer_frontend/index.html`'s existing Exposure Summary panel
(the frontend's own client-side `renderExposureSummary()`, which already tallies real built-lineup exposure
from `lineups_multi_*.csv` — no new upload, no new file, no backend change). A player gets a `RISK` tag next
to his name when his exposure is in this batch's own top tier (`>= max(20%, 75% of the batch's highest
exposure)` — relative per-batch, not a fixed number, per the mockup's recommendation) AND his
`statline_p10` (already in the uploaded final_projections pool CSV) is under 3.0, the exact same
`ABS_FLOOR_HIGH_RISK` constant `cheat_sheet.py`'s Range line already uses — reused literally, not
re-derived. DST is exempt (no floor/ceiling model, same as `cheat_sheet.py`). Verified with a standalone
Node reproduction of the exact frontend logic against the real Wk9 20-lineup build: reproduces the mockup's
7 flagged players exactly (Worthy, Sutton, Schultz, Dulcich, Washington, Boston, Raridon) with the threshold
computed dynamically (30% on this batch) rather than hand-picked. Hint text in the Exposure panel explains
the tag inline. Not yet validated live in the browser UI (no file-upload automation available this session)
or across additional weeks — watch it in real use; revisit once Item D's RB usage-trend signal matures to
see if it narrows the Gordon-type RB miss this flag still doesn't catch.

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

## Item D. `recent_form` == `season_avg` bug + missing recent-usage-trend signal — ✅ FIXED and shipped
this session (2026-11-09), own dedicated session (local_95a7901f-6ed4-4051-8a88-f03347f47108, spun off from
the main postmortem session)
Full writeup: `analysis/wk9_item_d_usage_trend/RESULTS.md`. Two separate fixes, both shipped, both committed:

1. **Duplicate-field bug: fixed, unconditional (no flag).** `recent_form` is now `season_avg * trend_ratio`,
   where `trend_ratio` compares each player's own short (last-2-game) vs longer (~5-game) recency-weighted
   usage on his position's primary volume component — falling back to `trend_ratio=1.0` (old behavior)
   whenever there's no honest basis to differ (games_played<2, missing/near-zero history). Verified on the
   real Wk9 rebuild: duplicate rate 100% → 53% overall (18.7% among players with ≥2 games, the honest
   remainder). Not wired into ranking — `cheat_sheet.py` already correctly doesn't trust this column, and
   that stays true; it's an honest, non-circular display/future-use signal, not a validated lever.
2. **The actual usage-trend fix for the Coleman-type miss: validated and shipped, flagged for rollback.**
   Investigating Coleman's real DEN backfield (Harvey OUT 2nd week, Dobbins fading 17/6/7 carries, Coleman
   rising 10/9/11) found the real mechanism: the shipped who-replaces-whom reallocation ranks RB-vacancy
   candidates by trailing carry share over each player's last 4 appearances — which favors whoever's played
   more games recently (Dobbins) over whoever's role is genuinely trending the right way with fewer games on
   record (Coleman). Tested on the same 2016-25 event population `rb_replacement_decay` was itself validated
   on (865 events, 686 clean): blending in a 70%-weighted short (last-2-appearance) window beats the
   long-window-only share at predicting real carry share in **10 of 10 leave-one-season-out folds** (n=1,770,
   ~5-7% relative MAE improvement, consistent direction/magnitude every season). The noisier "who gets ranked
   #1" question (n=40 disagreement cases) is underpowered and was correctly left alone — the rank order is
   unchanged; only the share SIZE once ranked is blended, which is what feeds `wrw_delta_pts`'s magnitude.
   Shipped in `statline_model._wrw_trailing_usage` (`sh_car` blend), default ON, `DFS_WRW_RECENCY_BLEND=0`
   rolls back to the exact prior math (verified byte-identical with the flag off). Target share showed no
   signal and was left untouched. Verified zero spillover on the trusted 86-slate real-pipeline harness: 0
   k=1 rows changed, 0 WR/TE rows changed, aggregate RB MAE/RMSE statistically unchanged (same scale as the
   original decay mechanism's own documented impact).
   **Confirmed live on the real Wk9 rebuild:** Coleman's decay add-on +0.19 → +0.64 pts (final_projection
   13.73 → 14.18); Dobbins' +0.47 → +0.00 (6.54 → 6.06) — exactly the direction the real outcome called for.
3. **Checked against [[project_wk9_sanders_autopromote_gap_and_jsn_ownership]] per the original ask:**
   different mechanism, already fixed separately (commit `bb4b0004`, 2026-11-07 — a stale Questionable-vs-OUT
   status tag, not a usage-trend gap). Unaffected by, and not regressed by, this session's fix.

**Side effect, noted for consistency, not a re-investigation:** rebuilding Wk9's slates with this fix changed
`final_projection` for the RB-vacancy-affected subset, which shifts Item C's exact numbers slightly — DK
classic edge **0.073 → 0.052** (re-run `grade_accuracy_week.py --week 9` after this fix), RB-mid bias
improving +1.86 → +1.26 (z 3.2 → 1.4). Showdown edge (Item B) is unchanged within rounding (0.179 → 0.181).
This is a single noisy week, not independent proof the fix helps broadly — the LOSO/pipeline-harness tests
above are the real evidence basis — but it's directionally consistent (less RB over-projection) and not
alarming. Item C's own investigation is not reopened.

## Item E. Missing game-script/spread-direction feature for RB usage — ✅ INVESTIGATED this session
(2026-11-09), own dedicated session (local_844c9dd7-c8a0-4b06-9eed-bd110d60b6e8, spun off from the main
postmortem session), verdict: premise was wrong (feature already exists and already fired), the specific
extension tested does not clear the bar, no fix shipped
Full writeup: `analysis/wk9_item_e_spread_direction/RESULTS.md`.

**Premise correction — the checklist's framing was wrong about the underlying model (though an honest read of
the exposed CSV columns).** `volume_prior.py`'s `vegas_anchored_team_volume()` (Session 10.3b, decision #7,
shipped long before this postmortem) already fits BOTH `implied_total` AND `spread` into predicted team-level
rush/pass/recv volume — "SPREAD drives carries ... more negative spread = more favoured = more carries ...
BOTH TERMS ARE REQUIRED TOGETHER." This is live in production (`--volume-prior` is always passed by
`DFS_Weekly_Process.md`'s SOP command and by the real `.github/workflows/refresh_data.yml` automated build,
not opt-in-and-forgotten). Confirmed on the real Wk9 rebuild: Allgeier's team (ARI, `team_spread` = +8.56, a
big underdog) got `proj_rush_att` 9.76 and `vegas_factor` 0.66 — a real, substantial discount already applied
before he busted, not a missing signal.

**What was actually new to test: does spread predict a "committee split" — the LEAD back's own share of the
team's (already-reduced) carries shrinking further under negative script, independent of the team-volume
effect already modeled?** Built a 2021-2025 team-week panel (`data/games.parquet` +
`data/weekly_stats_{season}.parquet`, n=2,319) and ran the same leave-one-season-out test Item D's RB blend
was held to. Result: **3 of 5 seasons marginally better, 2 worse — a coin flip**, mean MAE improvement
negligible (0.1161→0.1159), and the spread coefficient runs the *opposite* direction from the hypothesis
(bigger underdog → very slightly MORE lead-back share, not less). Big-underdog tail (`team_spread`>7, n=267,
matching Allgeier's actual game): mean lead-RB share 0.712 vs 0.716 overall — no detectable shift. **Does not
clear the validation bar — not shipped.**

**The propagation half (Value Pick badge + "normal swing" Range despite a "low-scoring" env note) is not a
new bug — it's the same mechanism Item A already documented** (the cheat sheet's bust-risk signal "under-reads
RB bust risk specifically this week," Allgeier is literally one of the three RBs in that exact finding, with
Marks and Gordon). Not re-investigated or duplicated here; tracked under Item A. The Value Pick badge itself
is working as designed (a documented 2026-11-03 decision: flags cheap/efficient plays, deliberately never
penalizes for bust risk on the main ranking — that's the Range line's job).

**User correction, same session — the real ask was never about projection accuracy.** Even with the discount
correctly applied, Allgeier's point estimate was still good enough ($5400/15.5 proj) to clear the optimizer's
value bar and get built into real lineups — **the optimizer works off the point estimate alone and never sees
bust risk**, so a well-calibrated mean doesn't stop a boom-or-bust play from being selected. That's a
flagging/lineup-pool-curation gap, not a projection-accuracy gap, and the user correctly expected the LOSO
test above to fail at capturing it (that methodology finds systematic statistical patterns, not the
context-specific judgment-call nuance this is actually about — a null result doesn't contradict the user's
read, it confirms this isn't a model-level fix). **This need is already scoped under Item A, not a new gap**
— Item A's redesign direction already requires the flagging layer to be "aware of what the optimizer's own
lineup-building is doing," and already names Allgeier as a case the current composite can't separate from a
real sleeper like Coleman. Parked there pending a mockup, not duplicated here.

**Bottom line:** Allgeier's real outcome (15.5 projected, 6.6 actual) is consistent with ordinary in-game
variance beyond what any pregame signal — spread included — can predict, on the narrow projection-accuracy
question this session tested. The team-level underdog discount was already applied correctly; the game just
broke worse than that number implied. No fixable gap found on accuracy. No code changed, nothing to roll
back. The user's real underlying concern (bust-risk plays still getting built by the optimizer) is tracked
under Item A, not resolved here.

## Item F. Target-competition / role-clarity check for Jordan Watkins-type cases — ✅ INVESTIGATED this session
(2026-11-09), own dedicated session (local_95a7901f-6ed4-4051-8a88-f03347f47108, spun off from the main
postmortem session), verdict: real, distinct gap confirmed; no fix clears the validation bar
Full writeup: `analysis/wk9_item_f_wr_te_decay/RESULTS.md`.

**Not Item D in different clothing — confirmed.** Item D's shipped fix is scoped to RB carry-share ranking
only; its own writeup states target share "showed no reliable signal... and was left untouched." Watkins'
problem is 100% a target-share question, so Item D's fix cannot touch it.

**Root cause, confirmed live:** by Wk9, SF's top 4 WRs (Evans, Deebo Samuel, Kirk, Pearsall) were all
OUT/IR — but none of them was a *fresh* (first-week) OUT: Evans last played wk6, Deebo wk5, Kirk/Pearsall
long-term IR. The shipped `apply_wr_replacement`/`apply_te_replacement` only fire on fresh (k=1) OUT/IR
events — a real, confirmed asymmetry with RB, which got a k≥2 "decay" extension
(`analysis/rb_replacement_decay`, shipped 2026-10-26) that WR/TE never received. Verified live:
`wrw_wr_delta_pts = 0.0` for Watkins in the real Wk9 rebuild despite the mechanism's intended trigger
condition being squarely met (just outside its k=1 window).

**Tested the obvious fix (clone the RB decay extension for WR/TE), it does NOT clear the bar:** built the
analogous 2016-25 event frame (1,009 WR + 396 TE team-week events) and fit bucket×rank fractions the same
way Item D's RB blend was fit. Per-season LOSO stability (the decisive check Item D's RB fix cleared 10/10):
**WR decay-better in only 5 of 10 seasons, TE in only 3 of 10** — a coin flip, not a signal. A simpler variant
(just extend the existing shipped k=1 fractions to also fire on k≥2) is actively worse on every metric, 0 of
10 seasons improved — it over-credits because vacated share compounds unrealistically across long-stale
absences. Consistent with this project's standing WR-redistribution findings (`role_bump_chalk_gap`: several
other WR-bleed variants also rejected as wrong-direction).

**Not abandoned, not chased further this session (time-boxed, lower-urgency item):** a different candidate —
recency-weighting the REMAINING candidate's own trailing target share (Watkins' own sh_tgt is diluted by a
thin 3-game sample including a near-zero-role early game), rather than crediting vacated share from the OUT
players — is flagged as a plausible next avenue for a future dedicated session if the user wants to pursue it.

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
only BUF/MIN (Mon) remains pending. **Item A is now fully closed** — diagnosis (yes, a real cheat-sheet
bust-risk signal exists, works for WR/TE, under-reads RB) plus a real, validated redesign mockup (optimizer
exposure × absolute floor bar, see above): correctly flags zero true studs, catches 2-3 real risky plays,
misses the already-documented Gordon-type RB gap. Not wired into the live pipeline yet — that's a short,
well-scoped follow-up (per-slate-relative exposure threshold instead of a fixed 30%, pick a surface in the
frontend), not a new open question.

**Recommended working order across D/E/F/G/A-redesign/B** (asked for explicitly 2026-11-09): these aren't
independent — F's answer depends on what D's fix actually captures, and the Item A redesign should incorporate
whatever Item D produces, so alphabetical-by-letter isn't the right order. Suggested sequence:
1. **Item D — ✅ done (2026-11-09).** Both halves fixed and shipped (see Item D above): the duplicate-field
   bug, and the validated RB-vacancy carry-share trend blend that actually fixes the Coleman-type miss. The
   Sanders connection checked out as a separate, already-fixed mechanism, not the same gap.
2. **Item F — ✅ done (2026-11-09).** Confirmed genuinely separate from Item D (target-share, not
   carry-share). Root cause confirmed (WR/TE vacancy mechanism only fires on fresh k=1 OUT, not sustained
   multi-week absences like SF's). The natural fix (clone the RB decay extension) was tested and rejected —
   coin-flip per-season stability, not the clean signal Item D's RB blend found. No fix shipped; a different
   candidate (recency-blend on the candidate's own share) flagged for a possible future session.
3. **Item E — ✅ done (2026-11-09).** Premise was wrong: the spread-anchored team-volume discount already
   existed and was already live in production (`volume_prior.py` decision #7), and had already fired on
   Allgeier before he busted. The specific extension tested (spread shrinking the lead RB's own share of team
   carries, a "committee split" effect) failed the same LOSO bar Item D's blend cleared — coin-flip stability,
   near-zero effect. No fix shipped; the propagation question folded into Item A's already-documented finding.
4. **Item A redesign — ✅ done and shipped (2026-11-09).** Mockup built and validated on the real Wk9
   20-lineup build (exposure × absolute floor bar cross-reference, see Item A above): correctly flags zero
   true studs, catches 2-3 real risky plays, misses the already-known Gordon-type RB gap. Shipped as a
   `RISK` tag in the frontend's existing Exposure Summary panel (`dfs_optimizer_frontend/index.html`) —
   client-side only, no backend/pipeline change, verified against real data via a standalone JS logic
   reproduction. Not yet seen live in the browser; watch it in real weekly use.
5. **Item B (showdown misses)** — fully independent of all of the above; slot in whenever, no dependency
   either direction.
6. **Item G (AI-probe retooling)** — explicitly last, only after D/E/F/the Item A redesign are in place.
Item C (accuracy) is reviewed, needs no further session.
