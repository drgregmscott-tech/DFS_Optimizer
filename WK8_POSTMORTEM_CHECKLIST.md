# Week 8 Postmortem — Checklist (created 2026-11-02)

Session discipline (same rule as every prior postmortem): one topic per dedicated session. Tangents go in the
Parking Lot below, not chased inline.

## 1. Results (real contest exports, matched by `gmscott81`, cash assumed ≈ top 25% by rank — DK/FD min-cash
convention used in `grade_construction_week.py`; not verified against the exact prize table)

| Slate | Rank / field | Percentile | Result |
|---|---|---|---|
| DK classic main (`main_01Nov2026`) | 511 / 11,883 | top 4.3% | **Cashed, strong** |
| DK classic early (`early_01Nov2026`) | 484 / 3,557 | top 13.6% | **Cashed** |
| FD classic (file labeled "early", see Item A below) | 2,744 / 5,932 | top 46.3% | Missed — injuries (user's read) |
| DK showdown PHI/WAS (Sun/Mon, 2 identical entries) | 1,048 / 2,369 | top 44.2% | Missed |
| DK showdown CAR/GB (Thu) | 4,066 / 5,906 | top 68.9% | Missed |

**Net for the week: 2 of 5 slates cashed**, both DK classic. Both showdown slates missed — the user only
flagged the FD miss going in; the two showdown misses are a second finding, not yet discussed.

## Item A. FD file naming — ✅ RESOLVED (user error, user fixed it)
Was labeled "early," was actually the main slate. User renamed the file to
`fd_classic_wk8_main_01Nov2026_full.csv` directly; `grade_accuracy_week.py --week 8` re-run below reflects the
corrected label. No further action.

## 2. Accuracy assessment (`scripts/grade_accuracy_week.py --week 8`, full report:
`analysis/weekly_accuracy_review/out/wk8/report.txt`)

**DK, classic, week 8 corr/edge:** corr_ours 0.587 vs corr_salary 0.488 → edge **0.098** — real but the
smallest classic edge of the last 4 weeks (wk5 0.177, wk6 0.182, wk7 0.132, wk8 0.098). One week, not yet a
trend; flagged for awareness, not a conclusion.

**DK, showdown, week 8 corr/edge:** corr_ours 0.901 vs corr_salary 0.714 → edge **0.187** — the best showdown
edge of the season (prior weeks 0.056–0.259, average ~0.14). Showdown projection accuracy is not what cost the
week — the two showdown misses above are a construction/selection story, not a projection-accuracy story (see
Item B below if the user wants to open it).

**FD, classic, week 8 (the mislabeled file, Item A):** corr_ours 0.519 vs corr_salary 0.457 → edge **0.062** —
also on the low end of the season (wk5 0.117, wk6 0.153).

**One-week flags (z-scores — single week, not persistent-trend evidence):**
- DK classic `RB $7k+` bias **+5.58** (z=3.6, WEEK flag) — we over-projected expensive RBs by ~5.6 pts
  this week. Single week; needs a second data point before it's actionable.
- DK classic `RB $7k+` ownership corr only 0.364 (weak) — modeled ownership tracked real ownership poorly
  at the expensive-RB tier this week specifically.
- FD classic `RB <$5.5k` ownership z=3.4 (WEEK flag) — small absolute size (bias +1.58, MAE 1.60), likely noise.
- DK TE ownership budget under-called by -6.3 (main) / -10.4 (early) total points of ownership share; DK
  `RB $7k+` ownership budget over-called by the same mechanism's mirror (+3.66 bias, weak corr above).

**Bottom line:** classic projection edge dipped a bit this week on both sites; showdown projection edge was the
best of the season. Neither rises to "persistent problem" on one week of data — logged for the trend, not
proposed as an action item yet.

**Re-run after Item A's fix (file correctly labeled main):** DK classic edge 0.098 (unchanged — DK wasn't
affected). FD classic edge now **0.059** (was 0.062 under the wrong label — the number barely moved, since the
underlying file and its results were always correct; only the slate-type bucket it was filed under changed).

### What "accuracy" actually means here, and how we compare to Fantasy Cruncher (user asked)
`corr` is a Spearman/Pearson rank correlation between our projection and real points, not a literal "% right."
Two more intuitive translations, both from this week's `report.txt`:
- **Variance explained (r²):** DK classic 0.587² ≈ **34%**, FD classic 0.556² ≈ **31%**, DK showdown 0.901² ≈
  **81%** this week. That 65-70% "unexplained" on classic isn't a modeling failure — individual NFL player-weeks
  are genuinely volatile (injuries mid-game, game script, TD variance), and this is the same order of magnitude
  commercial models run at (see below).
- **Edge over picking by price alone** (the `edge` column, corr_ours − corr_salary): DK classic +0.098, FD
  classic +0.059, DK showdown +0.187 — all positive, meaning the model adds real information beyond "the
  expensive guy is good," which is the more useful "are we actually accurate" read for lineup-building than the
  raw r² above.

**Vs. Fantasy Cruncher, direct historical test** (`data/fc_history/derived/proj_fc_accuracy/report.txt` — FC's
own "Lineup Rewind" projections joined to real results, 49,169 player-weeks, 2021-2026; this is local-only,
subscription data, never committed). Headline numbers, pooled:

| | n | bias | MAE | RMSE | Pearson | Spearman |
|---|---|---|---|---|---|---|
| FC (skill, proj>8) | 14,884 | +1.51 | 6.28 | 8.11 | 0.473 | 0.449 |
| Ours (skill, proj>8) | 14,884 | +0.31 | 6.64 | 8.40 | 0.397 | 0.387 |
| FC (both sides project nonzero) | 22,759 | +1.10 | 5.51 | 7.24 | 0.497 | 0.513 |
| Ours (both sides project nonzero) | 22,759 | **-0.14** | 5.27 | 7.05 | **0.516** | **0.533** |

Mixed by slice: on the broadest cut FC's raw correlation and MAE edge us slightly (a slate-bootstrap 95% CI
puts FC ahead by MAE -0.36 [-0.53,-0.22] and Spearman +0.06 [+0.04,+0.09] pts/corr) — but on the "both models
actually have a real play here" slice, which is the more relevant one for lineup decisions, **we're ahead on
both correlation and bias** (FC runs chronically ~1.1-1.8 pts high across every season 2021-2025; our bias sits
near zero every season). The one **direct, same-players 2026 live check** we have (`report.txt`'s wk1-2
PRODUCTION section, n=226, before the 2026 guard-rebuild fix) has our current pipeline beating FC on RMSE
(8.26 vs 8.56) and tying on Spearman (0.320 vs 0.320), with much smaller bias (-0.16 vs +1.19).
**Bottom line: roughly at parity with FC, slightly ahead on bias and on "real plays," slightly behind on raw
correlation pooled across all projected players** — consistent with the standing WK7 assessment
([[project_wk7_fc_parity_assessment]]). Caveat: FC's Rewind subscription lapsed Oct 2, so there's no FC
projection to compare against for week 8 itself specifically — this is the best available evidence (mostly
historical + a small 2026 sample), not a week-8-specific number.

## Item B. Both showdown slates missed cash — confirmed by the user as a real miss, not previously tracked
PHI/WAS (RB-captain build, QB in FLEX) finished top 44.2%; CAR/GB (QB-captain, RB/RB in FLEX) finished top
68.9%. `grade_construction_week.py --week 8` ran the standard construction-rule drift check against both real
fields — nothing jumps out as a single dominant rule violation (sample is 2 slates, most `ctl_sign` columns are
0/2 or 1/2, i.e. not consistent). This needs its own dedicated session if the user wants to chase it — on 2
slates there isn't enough here yet to diagnose, just to flag that it happened two weeks in a row now worth a
look (Wk6 also had a non-cashing Thursday showdown per `WK6_POSTMORTEM_CHECKLIST.md`'s parking lot).

## Item C. AI-probe process — ✅ SHIPPED (2026-11-02): reporting-format fix applied
Fixed: added a "Closing report format" section to `AI_PROBE_QUESTION_TEMPLATES.md` right after the per-claim
verdict definitions. Every cross-check report must now end with three mandatory lists — **Thumbs up:**,
**Thumbs down:**, **Exclude (high-risk trap):** — each entry a player + one-line reason, mapped directly from
verdict (disagree-underprojected → thumbs up, disagree-overprojected → thumbs down, trap-confirmed → exclude,
agree/trap-not-confirmed → no action). The narrative writeup can still precede the lists, but the lists are
mandatory and must be last. No code change — instruction/template edit only, since the probe runs as an ad-hoc
chat session (no scheduled task found for it) reading this doc directly.

**Original diagnosis (user, 2026-11-02), preserved for context: it's a reporting-format problem, not
a missing pipeline**
**Original framing was wrong.** The frontend's thumbs-up/down and exclude toggles already exist and work
(confirmed) — but the real gap isn't that probe verdicts have nowhere to go. **It's that the probe's final
report reads like a confirmation of our own modeling approach ("I agree with the chat's read, here's why our
numbers support it") instead of a direct instruction the user can act on in the frontend.** Looking at a real
example from this week's process (the "Midmorning Sunday Week 8 AI-probe handoff" session): the actual output
is narrative agree/disagree prose per player, with no explicit "thumbs-up these, thumbs-down/exclude those"
line. The user has to re-read the narrative and infer which specific action to take in the UI for each name.
**User's framing of the fix:** small prompt/reporting change — make explicit that the ask is "tell me which
players to thumb up (confirmed trap-not-confirmed / genuinely under-projected) or thumb down / exclude (real
trap-confirmed / over-projected) in the frontend," not just "does our modeling approach hold up." Candidate
fix (not yet made — needs the user's go-ahead on wording/scope): add a closing "Frontend actions" section to
the cross-check instructions in `AI_PROBE_QUESTION_TEMPLATES.md` (and whatever session prompt runs the
cross-check) that forces the final answer into three short lists — **Thumbs up:** [players], **Thumbs
down:** [players], **Exclude (high-risk trap):** [players] — each with a one-line reason, instead of leaving
that translation to the user. Low-risk, no code change, just an instruction/template edit.

## Item D. Parked items carried over from the last week of sessions (scan of session transcripts + the WK7
postmortem docs, since no single running "Parking Lot" list exists for Wk7 — it used ship-bar/test-bar/parked
tracks instead)
- **ESPN injury-feed comment text as a role/usage signal** — `WK7_POSTMORTEM_ACTION_ITEMS.md`, "test-bar."
  Collection-only script (`scripts/espn_comment_feed.py`) is live and pulling weekly snapshots into
  `refresh_data.yml`, but classification ("is this forward-looking role language" vs. routine recap) and any
  point-value sizing are explicitly deferred until enough prospective snapshots accumulate to validate against.
  Nothing to decide yet — just tracking that the data is quietly accumulating for a future test.
- **Winners-vs-field positioning (diagnosis item 7)** — `WK7_POSTMORTEM_DIAGNOSIS.md`, marked "parked, cause
  still unknown" 2026-10-28. Confirmed finding: our pool correlates more with the field average than with the
  winning tail on 13/14 real slates (not what we'd want). Noise was ruled out. The diagnosis doc points at
  "Item 9 Variant D" as the most promising next thread but it was never opened. Candidate for a dedicated
  session if the user wants to pick it back up.
- The user mentioned recalling "a thing or two" parked — these are the two concrete items this scan found
  written down. If something else was discussed live and not yet captured in a doc, it would be in a session
  from the last ~10 days not surfaced by this search; happy to dig further on a specific memory/keyword if the
  user has one.

## Parking Lot (add here, don't chase inline)
- (none yet)

## Next step
Nothing above has been shipped or changed — this is the list to review. Pick which items (A–D, plus anything
else the user wants added) become dedicated sessions, same one-topic-per-session discipline as every prior
postmortem.
