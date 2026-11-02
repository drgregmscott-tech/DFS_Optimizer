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

## Item B. Both showdown slates missed cash — ✅ INVESTIGATED (2026-11-02, dedicated session), real recurring
pattern confirmed, but root cause NOT found — no fix to ship, test-bar status only, see
[[project_wk8_item_b_showdown_recurring_miss]]
PHI/WAS (RB-captain build, QB in FLEX) finished top 44.2%; CAR/GB (QB-captain, RB/RB in FLEX) finished top
68.9%. The original pass on just these 2 slates found nothing (`ctl_sign` columns 0/2 or 1/2, not consistent) —
too thin to conclude anything. Broadened to every real DK showdown contest the user entered this season
(matched by `gmscott81` in `data/contest_results/2026/Week_*/dk_showdown_*_full.csv` + the two Wk8 files,
15 entries total across 14 unique slates, Wk1-8) to settle whether this is a recurring showdown weakness or
2-slate noise.

**Finding 1 — real pattern, but it's a Week 5 split, not a steady decline.** Matching the user's own entry in
every slate (rank/field-size from the raw export) and using the project's standard top-25% cash line:

| Week | Slate | Rank/field | Top % | Result |
|---|---|---|---|---|
| 1 | DEN/KC | 1,745/8,845 | 19.7% | Cash |
| 2 | IND/KC | 1,317/4,734 | 27.8% | Miss |
| 2 | NYG/LAR | 1,421/8,869 | 16.0% | Cash |
| 3 | ATL/GB | 215/8,870 | 2.4% | Cash |
| 4 | ATL/NO | 208/8,837 | 2.4% | Cash |
| 4 | DET/CAR | 2,567/4,730 | 54.3% | Miss |
| 4 | PIT/CLE | 697/5,911 | 11.8% | Cash |
| 5 | BAL/ATL | 3,534/4,727 | 74.8% | Miss |
| 5 | BUF/LAR | 3,285/8,867 | 37.0% | Miss |
| 5 | TB/DAL | 5,729/8,874 | 64.5% | Miss |
| 6 | SEA/DEN | 2,545/8,879 | 28.7% | Miss |
| 7 | KC/SEA | 43,954/47,308 | 92.9% | Miss |
| 7 | NE/CHI | 11/5,921 | 0.2% | Cash (huge) |
| 8 | CAR/GB | 4,066/5,906 | 68.9% | Miss |
| 8 | PHI/WAS | 1,048/2,369 | 44.2% | Miss |

Weeks 1-4: **5/7 cashed (71%)**. Weeks 5-8: **1/8 cashed (12.5%)**, that one cash being a blowout 0.2%-percentile
week (NE/CHI). The split lands exactly at Week 5 — not a gradual decline, a step change. Fisher's exact test on
the 7-vs-8 split: one-sided p≈0.035 (two-sided ≈0.06-0.07) — suggestive of a real regime change, but n=15 total
is thin ([[feedback_verify_full_history_and_power_before_concluding]]): this is a real, worth-tracking pattern,
not proof. Also resolves the WK6 parking-lot note (SEA/DEN's miss) and confirms it's part of the same Wk5+
pattern, not a one-off.

**Finding 2 — ruled out, projection accuracy.** `grade_accuracy_week.py` showdown edge by week: Wk1 0.056, Wk2
0.133, Wk3 0.259, Wk4 0.132, Wk5 **0.067**, Wk6 0.118, Wk7 0.185, Wk8 **0.187 (best of season)**. If accuracy
were the driver, Wk6-8 (good-to-best edge) should have cashed fine. They didn't — Wk6-8 combined 0/6. Only Wk5
(0.067, worst of season) lines up with an accuracy story, and even there only partially (3/3 missed that week).
Confirms the postmortem's original framing for Wk8 specifically, and extends it: **accuracy is not the Wk5-8
story.**

**Finding 3 — ruled out, construction-rule violations.** Ran `grade_construction_week.py --week 1-8
--skip-classic` (all 14 real slates together) and inspected both the pooled `mine_share` column and the
per-contest breakdown. The entered lineups show **no excess rule violations in Wk5-8 vs Wk1-4** — if anything
cleaner: `heavy_cpt` (CPT's team is the 4+ "heavy" side) only ever triggered in Wk2 (both of which cashed);
`stack_over3` (3+ same-team FLEX, the rule whose penalty was changed 2026-10-05, see below) only triggered once
all season, also Wk2, also cashed. Every Wk5-8 miss was a plain 3-3 split or a QB-captain-with-partner build —
exactly the shapes the rules call best-practice. The hard rule (`wrte_cpt_noqb`) was never violated in any
week. This is not a construction-rule-drift story either.

**Finding 4 — the one real candidate (timing of the 2026-10-05 stack-cap change) checked and rejected.** The
Wk4 construction review (`976f3350`, Mon 2026-10-05, right before Wk5's slates) changed
`sd-stack-cap-penalty` 0.75→0 and `sd-heavy-side-cpt-penalty` 0.5→1.25 in `showdown_se`, which lines up
suspiciously well with the Week 5 step-change timing. But Finding 3 already shows `stack_over3` never
triggered in any Wk5-8 slate, so this lever couldn't have driven those misses — the lineups it would affect
simply didn't occur. Independently, `analysis/wk8_showdown_altparam/RESULTS_firstpass_wrong_baseline.md`
(an earlier session, Wk8-only) already reran both Wk8 slates with the pre-10/5 stack-cap-penalty restored
(Alt4) and found it produced an **identical #1 lineup** on both slates — no effect. Two independent checks
agree: this specific change is not the cause.

**Finding 5 — entered-lineup team-split shows no pattern either.** Pulled each entered lineup's actual
CPT-side player count (0-6) from the real DK salary files (`TeamAbbrev` column) for every slate with a salary
file available (Wk8's two slates weren't matchable this way). Splits ranged 2/6 to 5/6 across both cashes and
misses with no consistent direction — e.g. Wk2 NYG/LAR went 5/6 (heavy stack) and cashed at 16%; Wk5-7's misses
were mostly plain 3-3. Stacking shape doesn't separate the cashes from the misses.

**Verdict — test-bar/parked, no fix to ship.** The Week 5 step-change in showdown cash rate is real and worth
continued tracking, but every candidate mechanism checked (accuracy, construction-rule drift, the Oct-5
stack-cap change specifically, team-split shape) comes back clean for Wk6-8, and only partially explains Wk5.
With n=15 and no identified lever, there's nothing to ship — this is consistent with ordinary high-variance
streakiness in a contest format where one captain pick (at 1.5x) can swing the whole lineup, not a diagnosable
pipeline defect. Recommend: no action now; re-run this same 15-slate (soon 17+) comparison after a few more
weeks to see if Wk5-8's 12.5% cash rate persists as more real data accumulates, or reverts toward Wk1-4's 71%
— that would be the next real signal either way.

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

## Item E. Ownership/projection "learning" pipelines had silently stopped logging — found and partly fixed in
a parallel session today (2026-11-02), explicitly flagged for this postmortem
Two gaps, same root cause (a required-every-week manual logging step silently stopped running):
- **Ownership refit (`fit_ownership_model.py`), commit `a1404cc7`:** `data/ownership_actual_log.csv` stopped
  being updated after Week 2 even though real contest results kept landing — the live
  `data/ownership_model_dk.json` ran on a Wk1-2-only fit through all of Week 8. Backfilled Wk5-8 (98-100%
  match rate) and refit; LOWO validation shows the refit beats the stale model on correlation and chalk-bias
  in all 8/8 weeks — shipped. **Directly relevant here: the refit's own LOWO report flags Weeks 7-8 as the
  two worst-performing weeks (corr ~0.76-0.77 vs 0.82-0.88 for weeks 2-6, chalk bias -13 to -15), and says
  explicitly "logged for the next postmortem to check."** That's this one. Ties to the ownership flags already
  in section 2 above (DK `RB $7k+` weak ownership corr 0.364, TE ownership under-called -6.3/-10.4) — not yet
  connected to a root cause, just two independent signals pointing at the same two weeks being ownership-model
  weak points. Worth a dedicated session if the user wants to dig into why Wk7-8 specifically fit worse.
- **Projection-stack log (`log_results.py`/`fit_projection_stack.py`):** separately found `projection_error_log.csv`
  missing Weeks 4-7 (DK classic/showdown, FD classic). Backfilled and logged (commit `95949263`), but the refit
  itself was correctly **not shipped** — tested in a sandbox first, moved R² by only +0.001 to +0.006, no
  material gain. No action needed here; already resolved today, included for completeness.
- **Process gap — ✅ FIXED (2026-11-02):** both sessions note this happened because Stage 6/7 of
  `DFS_Weekly_Process.md` (the manual weekly logging steps) stopped being run and nobody noticed for 5-6
  weeks. Fixed in this session: added `scripts/check_weekly_logging_gap.py` (compares real contest-results
  slates against both logs, flags any gap), ran it and backfilled 4 more pre-existing gaps it caught
  (`dk_showdown_wk2_Ind_KC`, `dk_showdown_wk8_CAR_GB`, `fd_classic_wk2_main`, `fd_classic_wk3_main`), and
  codified a new **Stage 8 — Weekly postmortem** in `DFS_Weekly_Process.md` that opens every week's
  postmortem with that check. Added `CLAUDE.md` so any new session auto-loads the SOP and the Stage 8
  requirement without it needing to be pasted in each week.

- **Wk7-8 ownership weak-spot — investigated this session (3 bounded Opus subagents, read-only), root
  mechanism traced:**
  - The "Wk7-8 worst LOWO weeks" flag above was measuring the wrong code path. Most real DK slates have an
    FFC public-ownership table and ship via a *different* path than `fit_ownership_model.py`'s LOWO script
    scores: a blend of `est_own_v2_only` with an older layered model (`est_own_live_old`) that runs on a
    **separate FFC-variant artifact** (`data/ownership_model_dk_ffc.json`), which is still fit on Week 1-2
    data from September — untouched by today's `a1404cc7` refit (that refit only updated the non-FFC
    artifact). Any future LOWO validation should score the actual shipped FFC-blended estimate, not the
    non-FFC path.
  - **Root driver (medium-high confidence):** that older model leans on our own optimizer-exposure feature
    (`l_exp`), and its correlation with real ownership degraded in Wk6-8 (0.87-0.91 in Wk3-5 → 0.70-0.79 in
    Wk6-8). On mid-priced ($4.5k-7.5k) chalk specifically, optimizer exposure collapsed (32%→24%→13%→17%,
    Wk5-8) as exposure shifted toward **sub-$4k cheap fillers** whose points-per-dollar rose in those weeks —
    this is the same already-flagged [[project_cheap_filler_pattern_recurring]] cheap-filler pattern, now
    shown to have a second-order effect on ownership prediction, not just roster construction. Confirmed not
    a feedback loop (exposure doesn't read ownership output).
  - Ruled out: our own point projections (track FantasyPros consensus closely all season, actually slightly
    *more* accurate than consensus on the specific miss players); the field "knowing something" (only 6/14
    big-miss players actually beat our projection — close to a coin flip); today's refit itself (confirmed
    pre-existing, the shipped path runs on the untouched FFC artifact).
  - Not traced: why cheap fillers' points-per-dollar rose in Wk7-8 specifically — that's the cheap-filler
    pattern's own open root cause, not new to this thread.
  - **Candidate (d) tested 2026-11-02 (dedicated session), RULED OUT — tail-floor fix (shipped 2026-10-23,
    commit `29fb8e5d`), the one code change that lines up with the exact Wk6→Wk7 boundary.** Confirmed via
    `git log` that `apply_tail_floor` is the *only* ownership-pipeline change between the Wk6 build (games
    2026-10-18) and the Wk7 build (games 2026-10-25) — verified two ways: (1) no other `ownership_v2.py` /
    `ownership_model.py` commit falls in that window (full chronological list checked), and (2) the Wk6
    `output/final_projections_dk_dk_classic_wk6_main_*.csv` has no `own_tail_floor` column at all, while Wk7/8's
    do — direct proof the feature was absent from Wk6's build and present in Wk7/8's. Tested the counterfactual
    directly from each week's own audit column (`estimated_ownership_pct − own_tail_floor` = what Wk7/8 would
    have shipped without it) against real logged ownership (`data/ownership_actual_log.csv`), chalk = real
    ownership ≥20% (same threshold `fit_ownership_model.py` uses): **removing tail-floor makes Wk7/8 chalk bias
    slightly WORSE, not better** (Wk7 main −10.60 → −10.99, Wk7 early −8.29 → −8.63, Wk8 main −11.15 → −11.40,
    Wk8 early −6.15 → −6.48; correlation essentially unchanged). Tail-floor is reallocating mass *toward* chalk,
    the opposite direction of the problem, so it cannot be the cause — and its own validation (7/7 real slates
    MAE-better) stands unchallenged. This closes off the only code-level lead the previous two sessions hadn't
    checked.
  - **Re-examined the "Wk7-8 degraded vs Wk2-6" premise itself, RULED OUT as the wrong frame —
    [[feedback_dont_jump_to_conclusions_on_results]].** The original flag came from `fit_ownership_model.py`'s
    LOWO script, already shown (prior session) to score the wrong, non-FFC-blended path. Re-scored properly:
    pulled every DK classic slate's *actual shipped* `estimated_ownership_pct` from its
    `output/final_projections_*.csv` and matched it to the real per-slate log in `ownership_actual_log.csv`
    (same chalk ≥20% definition), one bias/corr number per real slate, all 20 real DK classic slates Wk1-8:

    | Week | Slate | n chalk | Chalk bias |
    |---|---|---|---|
    | 1 | main/early/afternoon | 6/7/14 | −16.7 / −6.9 / −16.4 |
    | 2 | main/early/afternoon | 7/11/17 | −19.0 / −18.4 / −14.4 |
    | 3 | main/early/afternoon | 5/11/17 | −6.3 / −3.5 / −4.0 |
    | 4 | main/early/afternoon | 7/10/15 | −8.5 / −5.2 / −3.8 |
    | 5 | main/early/afternoon | 9/10/19 | −9.4 / −5.8 / −0.2 |
    | 6 | main | 10 | −1.0 |
    | 7 | main/early | 9/11 | −10.6 / −8.3 |
    | 8 | main/early | 9/8 | −11.2 / −6.2 |

    Per-slate bias: **Wk2-6 mean −7.65 (sd 6.12, 13 slates) vs Wk7-8 mean −9.05 (sd 2.30, 4 slates) — Welch
    t=0.68, p=0.51, not remotely significant**, and Wk7-8 sits well inside Wk2-6's own spread (which ranges
    −0.2 to −19.0). **Wk1-2 is actually the worst stretch of the season** (mean −15.3), well beyond Wk7-8 — the
    opposite of "Wk2-6 tight, Wk7-8 broke." Correlation shows the same mild, not-dramatic pattern (pooled by
    week: wk1 .70, wk2 .65, wk3 .85, wk4 .90, wk5 .90, wk6 .86, wk7 .82, wk8 .80 — Wk7-8 a little below the
    Wk3-6 plateau, comfortably above Wk1-2). Caveat: this is still n=4 slates for Wk7-8 and 9-20 chalk players
    per slate ([[feedback_verify_full_history_and_power_before_concluding]]) — too thin to prove a null, only
    to say there's no positive evidence of a Wk7-8-specific break, and the one code change in that window
    (tail-floor, above) pushes the wrong direction to explain it anyway.
  - **Verdict — parked, not a diagnosable regression.** Every traced lead across two sessions (stale FFC fit,
    blend weight, dropping `l_exp`, the FFC-variant refit, and now tail-floor) comes back clean, and the
    underlying "Wk7-8 regressed" premise itself doesn't survive being measured on the real shipped path with
    real per-slate ownership. Most likely explanation: Wk3-6 was an unusually tight stretch (for reasons not
    pinned down — possibly the chalk-seg/QB-cut/RB-cut fixes landing in quick succession Oct 5-12, each
    validated on exactly that window), and Wk7-8 is reverting toward ordinary variance (same ballpark as Wk1-2,
    before most of this season's ownership fixes existed), not degrading from a new defect. No further action;
    re-run this same per-slate check after a few more weeks if the user wants another data point, but nothing
    here clears the ship bar or needs a dedicated session on its own.

  - **Candidate (b) tested in sandbox 2026-11-02, RULED OUT — don't ship.** Refit the FFC-variant artifact
    on all 8 weeks (feats = `FEATURES + FFC_FEATURES`, the path `fit_ownership_model.py`'s own comment already
    documented), validated through the real shipped blended path (`ownership_v2.predict_v2`, not the simpler
    LOWO `fit_ownership_model.py` itself scores). Result: no measurable benefit — Wk7 chalk bias -9.3→-10.2,
    Wk8 -8.8→-8.9, correlation essentially flat (Wk8 +0.012, everything else flat or worse). **Wk6 was never
    actually broken** (bias ~-0.6 to -1.4, n=10 chalk players, i.e. the earlier "worst 2 weeks" framing was
    partly a small-n artifact for Wk6). Decisively: **both halves of the blend miss Wk7-8 chalk the same
    way** — v2-alone -12.0/-8.4, old-model-alone -8.4→-10.2/-11.2→-11.4 (stale→refit) — so neither the stale
    fit nor the 0.45/0.55 blend weight (tested 0.30/0.60 too, no fix) is the cause. Points at a **shared
    input or a post-blend step** (chalk/allocation layers, or `l_exp`/`l_est` directly feeding both v2 and the
    old model) as the real locus — not yet found. The refit also leans harder into `l_exp` (standardized
    weight 0.51→0.64, same concerning direction as today's non-FFC refit), and dropping `l_exp` entirely gave
    a mixed result (helps Wk7, hurts Wk8) — exposure stays a suspect, not a confirmed cause. **Candidates (a)
    and (c) above are effectively folded into "look at shared inputs / post-blend steps" now — the three were
    never fully independent.** No fix shipped; this needs a fresh dedicated session if pursued further, given
    today's pattern of each traced lead opening a narrower one rather than landing on a shippable fix.
## Parking Lot (add here, don't chase inline)
- `recent_form` equals `season_avg` exactly for every row, every week, all season, in the ownership-model
  training frame — found as a side note during the Item E Wk7-8 investigation (2026-11-02). Season-wide, not
  specific to Wk7-8; may be by design. Worth a one-line check in a later session.
- **Stevenson Wk8 ownership "mismatch" — ✅ RESOLVED (2026-11-02), not a bug.** The raw contest export
  (`data/contest_results/dk_classic_wk8_main_01Nov2026_full.csv`) lists Stevenson on two rows because DK's
  export breaks a flex-eligible player's ownership out by roster slot: 28.03% drafted at dedicated RB,
  9.96% drafted at FLEX. The real total ownership (any lineup that rostered him in either slot) is the sum,
  37.99% — which is exactly what `scripts/_backfill_ownership_wk5_8.py`'s `groupby("Player").sum()` computes,
  correctly. Checked for a week-to-week methodology inconsistency (the worry that the sum-across-slots
  approach might be new/only applied to the Wk5-8 backfill): pulled the `actual_ownership_pct` totals from
  `data/ownership_raw_dk_2026_wk{3,5,8}_*.csv` — all three sum to ~899-900% (the classic slate's 9-roster-slot
  budget), confirming every week, early and late, has always summed flex-slot ownership the same way. No
  broader logging bug; closed.

## Next step
Status as of 2026-11-02, session complete: A resolved (user fixed the file label). B confirmed as a real
2-slate miss, reviewed, not yet diagnosed — candidate for a dedicated session, not enough data on 2 slates
alone. C shipped (AI-probe reporting-format fix). D reviewed (2 carried-over parked items, no new action). E:
process gap found and fixed (Stage 8 + `check_weekly_logging_gap.py` now codified so this can't silently
recur); the Wk7-8 ownership weak-spot was investigated across two dedicated sessions (3 subagents, then a
follow-up) — every traced lead (FFC-variant refit, blend weight, dropping `l_exp`, and finally tail-floor, the
one real code candidate) came back clean, and a direct re-test on the actual shipped path showed the
"Wk7-8 regressed vs Wk2-6" premise itself doesn't hold up (p=0.51, within Wk2-6's own noise, nowhere near as
bad as Wk1-2) — parked as ordinary variance, not a diagnosable defect. Stevenson ownership "mismatch" resolved
(correct flex-slot summation, not a bug). One loose end remains on the Parking Lot (`recent_form` duplication).

**This closes the checklist's content** — every item from the original scope (results, accuracy assessment,
AI-probe revisit, parked-item scan, "anything else") has been reviewed or shipped. What's left is entirely the
user's call: whether to open dedicated sessions for B (showdown misses) or E's unresolved ownership root cause,
or to leave both as known, tracked, not-yet-actioned weak spots and move on to Week 9.
