# Post-Week 6 Checklist (created 2026-10-19)

Context from the user: traveling all week, built off mobile, single-entry GPP only (both sites, main
slate only — no afternoon/early, no multi-entry). No delays or errors on mobile. Missed cash on both
DK and FD main, plus Thursday's SEA/DEN showdown (also non-cash, found in contest_results independently).

**Real results (from the actual contest exports + user's own entries, matched by `gmscott81`):**
- **DK classic main:** 100.08 pts, rank 10,368 / 11,890 (bottom 13%, cash line ~top 20%). Big miss.
- **FD classic main:** 123.38 pts, rank 1,969 / 5,952 (33rd percentile, cash line ~top 20%). Close miss.
- **DK showdown SEA/DEN (Thu):** 80.14 pts, rank 2,545 / 8,917 (~71st percentile, cash line ~top 22%).
  Moderate miss, not alarming on its own — flagged by the user as a second non-cashing slate to look at.

## Session discipline (same rule as every prior postmortem, still applies)
One session = one topic from this list. A new idea that comes up mid-session goes in the Parking Lot,
not into the current discussion.

## Action items — each is its own dedicated session

Everything below is a real, scoped finding from the investigation trail in "Evidence trail" further down
this file. None of it is built yet. Pick one per session; each entry below is self-contained enough to
start cold (file/function pointers, what done looks like, where the supporting evidence lives).

### A1. Pool salary-slack lever (se3max_pool pivot room) — ✅ SHIPPED 2026-10-19 (opt-in, default off)
**Problem:** the submitted FD lineup spent $59,900 of a $60,000 cap (the pool's 20 lineups spend a median
of $59,900) — leaving no room to swap in a cheaper, similarly-projected, less-owned stud-tier alternative
even when one exists and is confirmed beneficial (pricier-vs-cheaper at the $8-9k RB tier: cheaper side is
real-owned 16.85% vs pricier 10.95%, pricier wins only 34% of 665 matched pairs, holds in 11/15 real
slates 2022/2024/2025).
**Built and shipped:** `--pool-slack-share`/`--pool-slack-amount` in `scripts/optimizer.py`'s classic
`se3max_pool` path (`build_multi_lineup()`), default OFF (0.0 = byte-identical to prior behavior), not
added to `data/optimizer_presets.json` (stays fully opt-in, same convention as `--own-penalty`) —
turn it on manually when building a pool you intend to review by hand (the SE3Max Pool (100) process).
Mechanically verified: at share=0.2/amount=$500 it legally forces ~1/5 of a 100-lineup pool under the
full cap.
**Tested, `analysis/pool_slack/RESULTS.md`:** reused the real-prize-table ROI pipeline
(`analysis/lineup_replay/`) on the same 20 real historical se3max_pool slates already validating this
item's premise. Pool-wide (all 100 lineups) mean ROI is flat (CI crosses zero, no harm shown), cash rate
improves (+4.3pp, CI excludes zero) — clears the lower ship bar this project already uses for a lever
the owner manually reviews rather than one that auto-executes
([[feedback_ship_inconclusive_when_human_reviewed]]). A first pass at this verdict wrongly graded the
lever against whether it reaches the literal #1-by-projection pick automatically — corrected after
owner pushback: that specific test is invalid (not just unfavorable) because `build_multi_lineup`'s
greedy batch loop is path-dependent (each lineup's state depends on every lineup generated before it),
so inserting slack-capped lineups anywhere reshuffles the whole batch's generation path — the #1 pick
differed in 20/20 slates, but 19 of those were just batch-path noise (same spend, different combo), not
the scoped mechanism. That invalidity is a reason to disregard that one test, not to withhold shipping.
**Open follow-up, not blocking:** if a future need arises to test this lever's effect on the
auto-selected #1 pick specifically, that needs to freeze the preceding batch state and vary only one
targeted lineup/slot's cap — not regenerate two full independent batches as done here.

### A2. Lineup pool-summary / recommendation feature (the owner's original ask) — ⛔ CLOSED 2026-10-20, don't build
**Problem (as originally scoped):** the built pool already contains better, less-chalky, higher-scoring
alternatives most weeks (proven directly: Wk6 FD lineups #9/#12/#16 beat the submission on both real points
and real ownership) — nothing surfaces them pre-lock. Every automatic selection rule tested (raw projection,
our modeled ownership, real ownership, blends, contrarian, FFC crowd data) failed to reliably beat picking
the top-projection lineup using only pre-lock information — so this was scoped as a visibility feature, not
an auto-picker.
**Closed, not built — on a much bigger sample the premise itself didn't hold up.** A 2026-10-20 session
reran `se3max_pool` on today's actual preset across all 64 usable real history slates (2022-25, not the
~21-slate/mostly-one-season sample the table above was built from) and found lineup #1 (today's default) has
the BEST cash rate in the pool, not just a tied/unclear one — 33.3% vs the pool average 28.6%, holding across
all 3 projection arms and a separate 16-slate 2026 check. 63 single-signal pre-lock rules and 9 fitted models
all cashed the same or less. There is nothing left to surface: a pool-summary view would just be dressing up
a pick that's already correct by default. Full data: `analysis/wk6_pool_selection_objective/RESULTS.md`
(item 7 below).
**Where this redirected:** the real, bigger problem it surfaced — the whole pool, including lineup #1, only
cashes 28-33% of the time, well under the ~67% needed to break even — became **A6** (new item below), after
a follow-up diagnostic (item 8 below) found the fixable driver is projection ranking accuracy (specifically
WR/TE), not ownership and not pool-selection.
**Evidence:** items 5 and 6 below (the original, now-superseded scoping work), and items 7-8 (the
2026-10-20 re-test that closed it).

### A3. Ownership-floor "near the line" transparency flag — ✅ SHIPPED 2026-10-20
**Problem:** ~7.2% of true sub-1.5%-real-owned players historically get modeled ≥2% and slip past a
manual "exclude low-ownership players" filter (not a coincidence — a real, repeatable miss rate). Moving
the filter threshold doesn't help (raising it to 3-4% cuts the miss rate only 7.2%→2.2% while excluding
28%→47% of real ≥3%-owned players — wrong-direction).
**Built and shipped:** standalone in the player pool table (`dfs_optimizer_frontend/index.html`) —
A2, the pool-summary feature this was originally scoped to piggyback on, was closed 2026-10-20 without
being built, so there was nothing to attach to. `isNearOwnFloor(p)` flags any player whose
`estimated_ownership_pct` is within `OWN_FLOOR_NEAR_PTS` (1.0pt) of the currently-set "Own %" filter;
`ownRangeHtml()` renders a blue ◆ (distinct from the existing amber ⚠ FFC-disagree flag, same row) with a
tooltip explaining the miss rate. No filter set → no flags, by construction.
**Follow-up fix, same day (real-use bug + visibility gap, both found live by the owner within minutes of
shipping):** (1) the first version only checked the Own % **Min** box — the owner filtered using the
**Max** box (a legitimate, equally common use: capping to find cheap/low-owned plays) and got zero flags,
since `ownMax` was never checked. `isNearOwnFloor()` now checks both bounds, flagging within 1pt of
whichever is set. (2) the lone per-row ◆ glyph was too easy to miss scrolling a long list ("this is like
silent flagging, i'll never see it") — added a summary banner above the list ("◆ N players shown are
within 1.0pt of your Own % filter...") plus a visible blue tint/left-border on each flagged row, not just
the small icon. Verified live in-browser against the real `dk_classic_wk6_main` slate: Min=2% flags 18/87
players (incl. Cade Otton at 2.6%, the real case this item was partly built from, and Mark Andrews at
2.4%, the other half of that same bust); Max=2% (the owner's actual filter direction) flags 26/425 players
— previously flagged zero before the fix. Banner and row tint confirmed rendering correctly in both
directions; flags/banner disappear when both bounds are cleared.
**Band-width fix, same day (owner pushback: "these decisions have to be data backed... before we settle
on 1.0 pt or whatever it should actually be"):** the shipped 1.0pt width was never actually tested — it
was a round number pulled from the original write-up's illustrative prose, not a measured value. Tested
properly on the same 2021-25 history (`analysis/own_floor_calibration/band_width.py`, n=15,028, not
committed — FC-derived): **Min-filter side, 1.0pt holds up** — recall/precision trade off smoothly across
0.5-3.0pt at every cutoff tested (1.5/2/3%) with no sharp knee, so 1.0pt is defensible (44% recall, 28%
precision vs a 12.6% base rate at the owner's usual 2% cutoff) though not uniquely optimal — list-length
is a judgment call past this point, not something the data forces. **Max-filter side, a flat 1.0pt
actively breaks at low cutoffs** — real deep-punt players pile up at ~0.3-0.8% modeled ownership, so at a
1.5% Max cutoff the old flat-1.0pt band flagged 62% of the shown pool (useless as a signal). Fixed:
Max-side width now caps at `min(1.0, maxCutoff - 1.0)` — a no-op at 2% (unchanged), narrows automatically
below that. Verified live: Max=1.5% now flags 15/414 (was ~62% pre-fix); Max=2% unchanged at 26/425.
Tooltip wording also split by direction (Min cites the real "~1 in 14" miss rate; Max no longer borrows
that Min-specific number). One honest limit no width fixes: ~half of real misses sit well above the
cutoff (median 1.17pt) — a short, scannable flag list will never catch more than roughly half of them.
**Evidence:** item 3 below, "Mechanism A."

### A4. Compounding-vacancy fix for the WR/TE/RB replacement model (Fix 2)
**Problem:** today a teammate only counts as "vacating" targets/role if he played the team's most recent
game. A player who fell off 1-2 games *before* the current OUT event (e.g. Skowronek, out a week before
Wilson, in the Germie Bernard case) is never folded into the vacancy pool for anyone. Lower priority than
it was — the already-shipped ownership recency-spike bump (see below) now covers part of this same symptom
at the ownership-output level.
**Scope:** `scripts/statline_model.py`, new helper alongside `_wrw_trailing_usage()`. New
`compounding_lookback_weeks` param (candidate `K=2`), **off by default** (`DFS_WRW_COMPOUNDING=0`) since
unvalidated. Test via `analysis/who_replaces_whom/build_frame.py` + `evaluate.py` on the real 2016-25
injury panel (`analysis/inactives/status_panel_2016_2025.csv`), LOSO, on a labeled "compounding" event
subset — expect this to be noisier (smaller subset), so an inconclusive result is an acceptable, honestly-
reported outcome here, not a failure.
**Evidence:** item 3 below, "Fix 2 (bigger, the real 'model sharpness' gap)." Note: Fix 1 (a different,
simpler approach to the same function) was already built, tested, and rejected — don't re-try it.

### A5. Ownership-model calibration at the low end (0-5% band) — the root-cause item
**Problem:** identified independently three separate times this postmortem (A3's miss-rate finding, item
5's near-zero lineup-sum ownership signal, and the cheap-dart-vs-chalk test below) as the actual
bottleneck: `estimated_ownership_pct` is too noisy below ~5% to reliably tell a play that will end up a
true dart (<2% real) from one that'll end up modest chalk (2-5% real). This is what blocks A3's flag from
being sharp, blocks ever shipping an automatic cheap-dart exclusion rule (confirmed real pattern: cheap
RB/WR/TE that end up <2% real-owned bust 35.7% of the time vs 19.4% for similar plays that end up ≥2%
real-owned — a +16.3pt gap, CI [+9.4,+23.2], holding in all 4 seasons with enough data), and blocks the
item-5 pivot rule (confirmed to work on *real* ownership) from transferring to our own modeled number
(helps 1 of 3 tested arms, hurts 2 of 3).
**Scope:** not yet specified to file/function — this needs its own investigation first: characterize what
specifically drives `estimated_ownership_pct` below ~5% (which inputs, which players) and why it's weakly
correlated with real ownership there (0.11-0.18, vs. much stronger at the chalk end), then test candidate
recalibrations against real ownership history, held out, before concluding a fix. This is the single most
valuable underlying gap in the whole postmortem if it can be resolved — treat it accordingly.
**Evidence:** item 3 below ("Mechanism A," "cheap dart vs chalk" steps 1-3) and item 5's "corrected
conclusion" / FFC-pivot-test sections.
**Clarified scope, 2026-10-20 (owner):** this item is not about raising SE `se3max_pool` cash rate directly —
item 7 below found that pool runs at lambda=0 (ownership never enters the solve), so ownership accuracy is
structurally disconnected from that number. The owner's point still stands and is the actual reason this
stays a priority: projections and ownership answer two different questions. Projection accuracy is about
picking correct/high-EV plays; ownership accuracy is about knowing when the top-projected play is ALSO the
top-owned play, in which case riding it concentrates risk with the field (no leverage if the chalk busts) —
that's the real use case for A5 (MME construction, pivot/dart flags, any future leverage-aware pick), not a
lever for raw SE cash rate.
**Diagnosis done, 2026-10-22 (`analysis/ownership_low_end_calib/RESULTS.md`, local only).** The characterization
this item asked for is complete. Headline: the raw "0.11-0.18 correlation below 5%" is mostly a slicing
artifact — any narrow ownership band looks that noisy, and FC (the system the owner cashes with) gets the
same ~.2 in the 1-5% band. The real, ranked, fixable gaps found: **#1** live train/serve pool mismatch
(scrub rows soak up ownership budget) — highest confidence. **#2** RB injury-replacement concentration.
**#3** low-band shape too flat (slope 1.37). **#4** QB low-end gap vs FC (.56 vs .84 AUC) — needs role/
projection info we don't have, lowest odds of a clean fix.
**#1 SHIPPED 2026-10-23** (commit `29fb8e5d`, `analysis/ownership_tail_floor/RESULTS.md`): tail-floor fix,
validated 7/7 real 2026 slates, MAE better every slate, budget-neutral. Same commit also turned OFF an
unrelated unvalidated "spike bump" found actively hurting accuracy as a side-finding (Pearson .920→.847) and
corrected an RB-decay default that had been flipped on by mistake. **Honest result: #1 closes only ~6% of the
1-5% band's under-call gap (2.44→2.50 modeled vs 3.35 real) — confirmed real, not the whole fix.**
**#2 and #3 triaged 2026-10-24 (this session, `analysis/a5_triage_2026-10-24/`, local only, nothing shipped):**
- **#3 (shape too flat): CLOSED, don't build.** Slope 1.36 is real and stable (5/5 seasons), but a within-band
  stretch is mathematically equivalent to just moving the owner's filter cutoff from 2.0% to ~2.2% — no new
  rank or threshold information. Live 2026 production is already near slope 1 (the FFC blend removes most of
  it). Doesn't touch the live 1-5% level gap at all.
- **#2 as originally framed ("field concentrates on one RB, we spread"): NOT CONFIRMED.** We already put ~84%
  of team RB share on the right guy, same as the field (diff +0.007, CI crosses zero, no consistent sign
  across 5 seasons). Drop this framing.
- **#2 narrowed to a specific archetype: real, not yet shippable.** When a team has an RB out (`vacated` ≥
  .4) and our model's top healthy RB on that team is modeled under 5%, it's under-called 5/5 seasons in
  history (2.58% modeled vs 5.60% real, ~1 row/slate) **and confirmed live** on the 7 real 2026 DK slates with
  contest results (wk4-6 main/early/afternoon): 2.62% modeled vs 7.18% real. **Root cause found directly, live
  only:** pure v2 is roughly unbiased on these players (mean 7.26 vs real 7.18) — it's our own FFC blend that
  cuts them ~64% after v2 gets it right, because FFC doesn't list 8 of the 10 archetype rows and the old blend
  partner model guesses low (e.g. Braelon Allen pure-v2 14.4 → blended 1.9, real 17.6). This single archetype
  accounts for ~17% of the entire live 1-5% band's under-call.
  - Built and tested two fixes, both read-only/uncommitted at the code level except as noted below: (a) an
    additive top-RB bump (history-fit, k=.5) and (b) a per-row blend-trust override (raise alpha toward v2 for
    this archetype only, cap at 5% modeled to avoid firing on chalk). **Neither clears the ship bar — n is too
    thin:** live test is only **10 rows / 6 distinct players** (Ollie Gordon ×4 slates, Braelon Allen ×2), not
    independent across shared-game weeks. (a) fixes bias in history but makes archetype MAE *worse* 5/5
    seasons there (fixes the mean, not the median); (b) can't be tested on history at all (no blend partner
    exists there) but gets closest to zero bias live (archetype bias −1.6 vs base −4.56). Both are budget-
    neutral and don't hurt non-archetype RBs.
  - **Built into `scripts/ownership_v2.py`/`scripts/build_projections.py` as switch `DFS_OWN_RB_VAC_TRUST`,
    default OFF (`RB_VAC_TRUST_DEFAULT = "0"`), committed 2026-10-24 inert** (byte-identical to unset when
    off, confirmed on all 7 slates) — approach (b), ready to flip on without rebuilding if validated. Params:
    `DFS_OWN_RB_VAC_TRUST_ALPHA` (default .9), `..._VAC_MIN` (default .4), `..._MAX_OWN` (default 5). Audit
    column `own_rb_vac_trust`.
  - **Re-test trigger, concrete (don't let this one go stale — this is the whole point of writing it down
    here instead of just leaving the switch off and moving on):** re-run
    `analysis/a5_triage_2026-10-24/h2b_live_test.py` once Wk7 DK contest results land (add wk7 main/early/
    afternoon to `SLATES`, delete the cached `h2b_live_frame.parquet`), and again after Wk8. **Ship only if**
    the direction (archetype bias shrinking toward zero, non-archetype RB MAE not hurt) holds across at least
    ~20 archetype rows from at least ~10 distinct players — roughly double today's n, enough to move past
    "6 players' worth of noise." Until then, deliberately kept off: shipping a real-money ownership number off
    6 players would violate [[project_dfs_two_track_philosophy]]'s hard ship bar, which this project has held
    to on every other item in this file (including turning OFF the RB-decay default when it didn't clear its
    own bar on 2026-10-23, same commit as the tail-floor ship).

### A6. Slate-level "why didn't we cash" autopsy, and the WR/TE projection-ranking gap it points to — ⛔ CLOSED 2026-10-22, redirected (see below)
**Result (2026-10-22 session, `analysis/wk6_wrte_autopsy/RESULTS.md`):** ran the full case-study/mock-replay
loop below across 8 historical worst-WR/TE-edge slates (n-weighted, 2 per season 2022-25) + 8 random
historical slates for the mock step + all 18 2026 DK classic Wk1-6 slates (16 replayed) against the owner's
real `gmscott81` entries. Found one real, consistent mechanism — **our WR/TE target projections are too
spread out vs. what price/target-history implies: we over-project the top TEs by ~25% above their real
target share and under-project the cheap ones** (fits the owner's actual Wk6 busts: Loveland, Pitts,
Schultz, Andrews, Otton). A TE price-weight correction built from this is a real, consistent accuracy gain
(Spearman edge +0.059, positive all 4 seasons) — **but it does not move cash rate** (pool 30.0%→29.7%,
slightly worse on the 2026 live check). Why: cash rate is driven by week-specific information (who actually
gets the targets/TDs that week), not by a better average-case ranking. A mock test nudging projections just
5% toward the real post-game answer lifted pool cash 31%→40% — confirming the room is real, but a static
projection-formula tweak can't deliver real-time information, it only redistributes an average. The WR
price-weight version is wrong-direction (FC is also worse than salary at WR — a market-wide miss, not
uniquely ours). **Two-track verdict: TE price-weight is inconclusive-keep-testing as a pure accuracy fix,
wrong-direction as a cash lever; WR price-weight is wrong-direction. Nothing from this item ships.**
**Where this redirects:** the mock-replay numbers (31%→40% from a 5% nudge toward the real answer) point
at **week-specific signals** — vacated targets from injuries, props, late news — as the next real lever,
since that's what actually carries new information a static projection can't. Not scoped or built this
session; added to the Parking Lot below as a candidate for a future dedicated item.
**Original problem, in the owner's own words (for context):** "we need to be answering the question of why didn't we cash? why
didn't the top projected line give us a winning lineup? ... sharp players cash most weeks, lets say 13 out
of 17 or something. they are doing it....which means we can do [it]. but we have to find out the answers to
how they are doing it, unlock that and implement it into our system."
**What's already established (item 7 below, `analysis/wk6_cash_rate_driver/RESULTS.md`):** across 64 real
historical `se3max_pool` slates, lineup #1 (today's pick) cashes 33.3% and the whole pool averages 28.6% —
both well under the ~67% cash rate needed to just break even at DK's 1.5x min-cash payout, confirmed by a
real mean ROI of -0.36. No pre-lock pool-selection rule fixes this (item 7/A2's finding) — every lineup in a
built pool has roughly the same expected value, so the gap is in what the pool is built FROM, not which of
the 100 we submit. The one factor found so far with a real, consistent (all 4 seasons, all 3 projection
arms, clean placebo-controlled) relationship to cash rate is **projection ranking edge over a salary-only
baseline, within position** — not raw accuracy, specifically being right where the market (salary, FC) is
wrong. We already have a real edge at RB (+0.026 today). **WR is no better than salary (+0.001) and TE is
worse than salary (-0.026)** — both move cash rate by about as much per SD as RB does, so these are the two
most fixable, highest-leverage spots identified so far.
**Scope — this is a case-study/autopsy loop, not another regression pass:** take a sample of real busted
slates (both historical and the 2026 Wk1-6 live misses), and for each one: (1) identify which specific
players we ranked wrong relative to what a sharper source got right (Vegas lines/implied team totals, real
box-score outcomes, whatever the real winning/cashing lineups in that slate's contest actually rostered —
"what did the top-1% lineups contain that ours didn't, and was it predictable pre-lock"); (2) for each miss,
figure out WHY — role change, game-script shift, injury-driven usage bump, matchup, etc. — don't assume,
test against the data per SUBAGENT_BRIEF.md's "no assumed causes" rule; (3) mock up a corrected projection
set for that slate using the real answer, rebuild the pool with the SAME optimizer/preset, and replay it
against the real contest result — did the corrected build actually cash? This directly operationalizes the
owner's "here's the solution, mock up the slate, see if it leads down a different path, did it cash or not"
loop, and should be repeated across enough slates to see whether a consistent, implementable correction
emerges (not just a one-slate story).
**Also worth checking:** benchmark against real sharp/consistently-cashing players' construction choices if
any such data is obtainable (the owner's "13 of 17 weeks" framing) rather than only against FC, since item 7
found FC is barely better than us (+0.012 edge) — FC may not be the right "sharp" bar to chase.
**Evidence:** item 7 below (`analysis/wk6_cash_rate_driver/RESULTS.md`), and item 6's pool-selection finding
(A2, now closed — see that item's note).

### A7. Mega-chalk player exclusion (ownership ceiling, not lineup-level contrarianism) — ⛔ CLOSED 2026-10-23, don't build
**Result (ceiling test, `analysis/mega_chalk_exclusion/RESULTS.md`, local only/FC-derived, not committed):**
banning mega-chalk players from the player pool entirely loses money on 4 seasons of real contests, at every
threshold the owner named (30%/40%/50% real ownership). 30%+ (n=56): cash -4.9pp [-8.0,-1.9], capped ROI -0.13
[-0.25,-0.02], both exclude zero. 40%+ (n=33): cash -3.0pp, capped ROI -0.14, top-1% rate halved, all exclude
zero. 50%+ (n=10): inconclusive, every point estimate still negative, CIs cross zero on a small sample. Held up
against controls: seed-noise alone moves metrics ~±1pp/±0.01, a placebo removing a similarly-priced non-chalk
player does nothing, head-to-head X40-vs-placebo is -3.8pp cash excl0. Not a disguised "fade the studs" effect
— only 6% of 40%+-owned players were even top-salary at their position (median ~$6.1k); the field is usually
*right* about these plays (they beat our projection by +3-5pts on average). Worst single result: removing a
whole same-team chalk stack (the Rams-type case) rather than one player, -14.5pp cash (n=11) — the single worst
number in the test. Why the owner's informal Wk6 test looked good: mega chalk only busts ~1 week in 3; exclusion
gains a little in bust weeks (+0.05 to +0.08 ROI) and loses 3-5x more in the other 2 of 3 weeks (-0.24 to -0.25)
— a one-week test on a bust week reads as a win, 4 seasons says it's a loss.
**Owner's decision, 2026-10-23: close, no further testing.** His words: *"i dont think we need to do any more
testing. seems we just have another situation that is based on feels. pivots can be good but its nuanced and
depends on the situation."* No exposure-cap follow-up, no 50%-tier revisit — treat the ceiling result as the
answer, not a reason to keep probing a softer version. On the 50% tier specifically: *"the info is what it is. i
don't think there's anything to fix or correct, rather its just info to keep in mind."*
**Game-theory note on chalk stacks (owner, not tested, not actionable today):** fading an entire multi-piece
chalk stack is a different question from fading one piece of it — *"what's the likelihood of each of a 3 piece
stack being in the optimal lineup? ... unless very specific conditions exist to streamline usage to only a few
players, its unlikely that all 3 of them will be in the optimal."* The -14.5pp full-cluster-removal result above
doesn't settle this (it tested removing the whole stack, not one piece) — logged here as a reasoning note for a
future session, not scoped or tested.
**Side finding, parked (see Parking Lot):** our own projections run ~5pts low on 40%+-owned players (FC is only
~2pts low on the same players) — a real, separate projection-accuracy gap on exactly the players that decide
slates, pointing the opposite direction from fading them. Owner: open it as its own item eventually, "but
probably not today."

<details>
<summary>Original scoping (2026-10-23, superseded by the result above)</summary>

### A7 (original scoping). Mega-chalk player exclusion (ownership ceiling, not lineup-level contrarianism) — scoped, not built, 2026-10-23
**Owner's observation:** Week 6's main-slate miss was driven partly by mega-chalk studs failing — Stafford,
Nacua, and Kyren Williams, two of them around ~50% projected ownership (same Rams stack covered in item 4
below). The owner ran an informal backtest excluding mega-chalk plays entirely from the builder and got
better results — but flagged himself that this hasn't been tested properly, just tried once.
**Why this is a real, untested gap, not a repeat of A2/item 5's rejected finding:** everything already
tested under "full chalk vs. full contrarian" (item 5, and A2's closed pool-selection work) picks *among
already-built lineups* — e.g., picking the least-owned lineup out of a pool that still contains every mega-
chalk player as an option. This is mechanically different: **excluding a mega-chalk player from the player
pool entirely**, so no lineup in the batch can roster him at all. Nobody has scoped or tested this lever.
Item 5's contrarian-lineup-picking being rejected does not transfer to this question.
**Honest caveat on the owner's own backtest:** one favorable week is not evidence — it's a legitimate
hypothesis, not a result yet. Needs the same real-history treatment as every other item here before trusting
the direction (same discipline as A1/A6 above).
**A known wrinkle to build into the test, not guess at:** Mechanism A (item 3's evidence trail, A3's
shipped flag) already found our own modeled `estimated_ownership_pct` is biased high specifically at the
top end — players modeled at 20%+ ownership are overestimated vs. real ownership 76% of the time. Any
exclusion rule built off our own modeled number for "mega chalk" is triggering off a number that already
runs hot there — could mean we'd over-exclude, or could mean the very top of our model's confidence (true
40-50%+ calls) is still trustworthy. Needs to be checked directly, not assumed either way.
**Scope — not yet run, blocked on the credit limit, next dedicated session's starting point:**
1. Define "mega chalk" by *real* ownership on the existing 64-slate real-history `se3max_pool` dataset
   (`analysis/wk6_cash_rate_driver/` / `analysis/wk6_pool_selection_objective/` already has this built) —
   test a couple thresholds (e.g. ≥25%, ≥35%).
2. **Ceiling test first** (same two-step pattern as the cheap-dart-vs-chalk item above): using real
   ownership, rebuild each historical pool with mega-chalk players removed from the player pool entirely
   (not just deprioritized), replay against the real DK prize table (`analysis/lineup_replay/`'s pipeline),
   compare mean ROI / cash rate / tail (P90, P99) to the unmodified baseline. Establishes whether the
   mechanism is real at all, with perfect hindsight.
3. **Floor test second:** repeat using *our own modeled* ownership as the pre-lock exclusion trigger (what's
   actually actionable), see how much of the ceiling-test gain survives — same honesty check used
   everywhere else in this postmortem.
4. **Isolate ownership from salary/stud tier** — mega chalk and high-salary studs correlate but aren't the
   same thing; confirm the effect (if any) is about ownership, not just "faded the studs."
**Evidence:** item 4 below (the Rams chalk stack this observation is drawn from), and item 3's Mechanism A
(the high-end modeled-ownership bias noted above).

</details>

## Evidence trail (background — the action items above are the distilled next steps; items are kept
below for the investigation history, not as a second to-do list)

1. **Injury-news accuracy while traveling.** ✅ CHECKED, NO EVIDENCE OF A PROBLEM FOUND. `git log` shows
   the automated pipeline (ESPN diff probe, scheduled injury refresh, full refresh dispatch) ran normally
   and repeatedly through the 10/16-10/19 window, including several `changed=true` snapshots (real
   updates caught). `config/manual_status_overrides.csv` has zero Week 6 entries, and every Rams/BAL/TB
   skill player involved in the two misses below was correctly marked ACTIVE (no missed OUT/Questionable
   tag). **Open:** this is a negative result (nothing wrong found), not a positive confirmation that a
   specific piece of news was right — if the user remembers a *specific* player/moment that looked wrong
   on the phone, name it and we'll trace that one directly.

2. **Optimizer/mobile performance while traveling.** ✅ CONFIRMED FINE, per the user — no delays or error
   codes. Consistent with the Wk5 mobile UI fixes (item 6, `316f18c2`) holding up under real away-from-desk
   use. No action.

3. **DK main miss — Mark Andrews (TE) + Cade Otton (FLEX) both bombed (1.4 pts each) in the same
   lineup.** Both were projected for solid roles (Andrews 9.9 pts @ 2.36% own, Otton 7.5 pts @ 2.63% own,
   `proj_targets` 5.7/4.8, both ACTIVE, no injury flag) and both cratered to 1-2 targets and 1.4 pts, same
   week, same lineup.
   - **Sustained backup-QB usage-instability candidate: tested on history, 2021-25, REJECTED**
     (`analysis/qb_sustained_variance/RESULTS.md`). Both teams (BAL/Huntley, TB) were on an established
     backup QB (not a week-1 surprise) when this happened, raising the question of whether sustained
     backup-QB situations make WR/TE usage less stable/predictable. They don't: sustained-backup
     team-weeks do NOT show higher-variance/less-predictable WR/TE usage — if anything the opposite
     (residual and raw-points variance measurably *lower*, significant for WR and WR+TE pooled, 4/5
     seasons same direction; direct trend-deviation test a clean null). This sub-question is closed.
   - **⚠️ REOPENED after owner pushback (2026-10-19) — the real question isn't the backup-QB coincidence,
     it's two sharper, testable mechanisms.** Owner's words: *"i don't think this is a backup QB issue...
     value was too high but ownerships too low, i excluded all players less than 2 percent ownership when
     i built the lineups and then we ended up getting 2 players less than 2 percent owned... on DK we
     still struggle trying to find cheap plays that do well... 2 punts, 1 too many and both in bad spots
     were other cheap punts were in better spots and out performed."* Both were tested properly, not
     assumed:
     - **Mechanism A — ownership-floor filter miscalibration, tested on history 2021-25
       (`analysis/own_floor_calibration/RESULTS.md`). Real and repeatable, but not a one-directional bias
       — no single fix.** Confirmed the filter is the frontend's "Own %" min field (`estimated_ownership_pct`,
       not real/FFC). Checked whether the model systematically overshoots real ownership right in the
       1.5-3% band the way Andrews/Otton did: **no** — that band is roughly 50/50 over/under, not biased
       high (the model's real one-directional miscalibration zones are <1% modeled, 75% too high, and
       20%+ modeled, 76% too high — already-known chalk-end problems, not this one). But the **miss rate
       is real**: about **7.2% of true sub-1.5%-real-own players historically get modeled ≥2% and would
       slip past this exact manual filter** — roughly 1 in 14, not a coincidental n=2. Raising the floor
       to 3-4% barely helps (miss rate 7.2%→4.0%→2.2%) while sharply increasing wrongly-excluded real
       players (28%→38%→47% of real ≥3%-owned players cut) — moving the threshold is wrong-direction.
       **No lever to auto-fix (the error isn't biased one way, so there's no correction to apply) — the
       actionable piece is a transparency flag:** surface players whose modeled ownership sits within
       ~1pt of whatever cutoff is in use as "near the line, model uncertain here," same manual-judgment
       pattern as borderline backups, rather than trusting the number blindly. Human-reviewed lever, not
       auto-execute — scoped, not built (could piggyback on item 6's pool-summary feature below).
     - **Mechanism B — DK cheap-tier selection quality vs FD, tested on 2026 wk1-6
       (`analysis/cheap_tier_dk_vs_fd/RESULTS.md`). Rejected — DK is not worse, it's measurably better,
       every week so far.** Data caveat stated plainly: the FC history pull is DK-only (no FD rows
       anywhere in `data/fc_history/`), so this can't get the usual 5-season held-out treatment — this is
       the only evidence that exists, one season/six weeks, in-sample, not proof at 5-year confidence.
       Within the cheap tier (bottom 45% salary by site/week, RB/WR/TE), Spearman correlation between our
       projection and real points is **higher for DK than FD in 6 of 6 weeks tested** (mean 0.571 DK vs
       0.472 FD, 95% CI on the difference [+0.056, +0.141], excludes zero). "Top-half-by-projection beats
       bottom-half" hit rate is 6/6 for both sites — no gap there either. Specifically: Otton was our
       **#2-highest-projected cheap play of 90** in the DK Wk6 pool and finished #41 — a real, large
       single-player miss, but the season-long evidence says DK's cheap-tier selection mechanism itself is
       fine (better than FD's), so this reads as an individual confident-call bust, not a site-level
       defect. Re-test if FD history ever becomes available; for now, closed on the only evidence we have.
   - **⚠️ REOPENED a second time (2026-10-19) — owner pushed back again, asking for if/then logic, not
     another "no lever found."** His words: *"i don't think we should be rostering players that are close
     to no ownership in single entry gpps... those are dart plays that should be reserved mainly for large
     mme gpps, unless somehow the model is overwhelmingly showing that play to be so strong you can't
     ignore it but i think in that case the field is probably on it a little too... we just keep missing
     on the good, cheap chalk plays... i think there's a fundamental issue with our optimizer plugging in
     cheap players, its a pattern i've seen since the beginning and its still persisting."* Restated as
     if/then and tested properly (`analysis/cheap_dart_vs_chalk/RESULTS.md`):
     - **Step 1 (ceiling test) — if real-ownership disagreement predicts busts, is that true at all?**
       **Yes, strongly confirmed.** Cheap RB/WR/TE our model projected ≥5 pts (a real role, not a scrub),
       split by what ownership they ACTUALLY ended up with: those that ended up real own <2% busted
       (actual < 50% of projection) **35.7%** of the time vs **19.4%** for those that ended up ≥2% —
       a **+16.3-point gap [95% CI +9.4, +23.2]**, holding in all 4 seasons with enough data (2022-2025,
       dart-busts-more every time). Mean projection is similar between the two groups (6.0 vs 6.7), so
       this is specifically about ending up unowned, not just "these were bad plays anyway." **The owner's
       instinct is correct and real, not a hunch.**
     - **Step 2 (floor test) — can we detect this before lock with what we have today?** **Weakly and
       inconsistently, not reliably at the 2-3% boundary this case lives in.** Same test using OUR modeled
       `estimated_ownership_pct` instead of real ownership: at a 2% cutoff the gap is +1.8pts [-5.3,+8.4]
       (not significant); at 3% (Andrews/Otton's zone) +7.2pts [-0.7,+15.0] (borderline); it only becomes
       clearly significant at a 4%+ cutoff (+10.7pts [+0.8,+19.8]) — a meaningfully higher bar than the 2%
       line actually in use.
     - **Why the floor test is weaker — it's the same gap found twice already, not a new one.**
       Correlation between modeled and real ownership in the 0-2%/2-4% modeled bands is only 0.11-0.18 —
       weak exactly where this rule would need to fire. This is Mechanism A's finding (the 1.5-3% modeled
       band is a noisy ~50/50 mix of over/under) and item 5's finding (near-zero lineup-level ownership
       signal) showing up a third time from a third angle.
     - **Logical conclusion, the if/then the owner asked for:** (1) if low real ownership on a decent
       cheap play predicts a bust → **confirmed**, his instinct is right, not a dead end; (2) if we could
       detect "will end up unowned" pre-lock → **we can't, reliably, with today's ownership model**, so a
       hard auto-exclusion rule keyed to it would misfire often (cutting plays that end up chalky, keeping
       ones that end up dart-y); (3) **therefore the fix is the ownership-model calibration gap itself**
       (specifically at the low end, 0-5%), now identified independently three times this postmortem as
       the actual bottleneck — not a construction-rule problem, and not "no lever exists." This is the
       single most valuable fixable thing this item surfaced: calibrate `estimated_ownership_pct` at the
       low end, re-run this exact test with the recalibrated number, and only then wire an SE-specific
       soft-penalty for low-estimated-ownership cheap plays (shipping it on today's number would misfire).
     - **What this does not say:** it doesn't mean "ignore cheap darts" is wrong today — it means an
       *automatic* rule isn't safe to ship yet. The near-term answer stays the owner's own manual judgment
       (checking a borderline player's role before trusting the number), which is exactly what Mechanism
       A's transparency flag already recommends — this result is a reason to prioritize that flag and the
       underlying model fix, not a reason to treat the question as closed again.
   - **Bottom line on item 3:** the Andrews/Otton bust itself has no single fixable root cause (sustained-
     backup variance: rejected; floor-filter bias direction: not found; DK-vs-FD selection quality:
     rejected) — but the deeper pattern the owner kept pushing on **is real and now proven**: cheap plays
     that end up essentially unowned bust far more than similarly-projected cheap plays that end up with
     even modest real ownership. We can't act on it reliably yet only because our own ownership model is
     too noisy at the low end to tell which is which before lock — a specific, identified, fixable gap,
     not a shrug.
   - **⚠️ REOPENED a third time (2026-10-19) — owner: "this is about model sharpness, where at least a
     portion of the field is able to find the right cheaper plays but we aren't," with the concrete
     example "playing Germie Bernard instead of Cade Otton," and an explicit instruction not to accept
     "we generally get it right" — find why we don't get it right every single week.** Traced directly
     against the real pipeline (`analysis/wrw_compounding_vacancy/RESULTS.md`), not assumed:
     - **Correction to the premise: it wasn't "a portion" of the field — it was most of it.** Germie
       Bernard's TRUE real DK ownership (DK splits one player's ownership across the roster-slot rows he
       was used in — summing them, as the official per-player total requires) was **26.4%**, not a
       sharp-minority play. Our model had him at 9.07% / 8.03 pts. This is a real, substantial
       miscalibration on exactly this kind of player, and it traces to a specific cause.
     - **The redistribution mechanism DID fire correctly — the signal was caught, just undersized.**
       PIT's WR2 (Roman Wilson, 6 tgt/wk) was on IR heading into Wk6, correctly flagged OUT in our
       injury pipeline well before lock; PIT's WR3 (Skowronek) was also OUT; Bernard had already posted
       9 targets/80 yards in Wk5 (fully visible pre-lock). Our `apply_wr_replacement`
       (`scripts/statline_model.py`) DID see Wilson's OUT status and added `wrw_wr_delta_pts=0.87` to
       Bernard's projection — it isn't that we missed the news.
     - **Why the boost was too small — two specific, identifiable gaps:** (1) the vacated-share
       calculation averages the OUT player's trailing 4 games, which included his OWN already-depressed,
       injury-affected final game (1 target vs his healthy 6/week) — diluting his true share from ~0.18
       down to the 0.139 actually used; (2) Skowronek stopped playing a week *before* Wilson, so by the
       time Wilson's OUT event fires, Skowronek's own vacancy has already fallen outside the eligibility
       window ("played the team's previous game") and is never folded in anywhere — a **compounding-
       vacancy gap**: the mechanism handles one clean "OUT this week" event well but has no concept of a
       team losing complementary skill players in close succession rather than all at once.
     - **Honest sizing: this explains PART of the miss, not most of it.** Correcting both gaps would
       raise Bernard's boost from 0.87 to roughly 1.3-1.8 points — real, but far short of closing an
       8-point-projected vs 25.7-point-actual gap. A 12-target, 11-catch, 1-TD game at a backup's prior
       usage level is a genuine outlier performance that no role-redistribution formula fully sizes in
       advance. What the compounding-vacancy gap most plausibly explains is the **ownership** miss more
       than the full points miss — 26% of the field didn't need a precise point projection, just simple
       roster logic ("he's the only healthy WR left behind the WR1"), and our ownership estimate is
       driven by the same undersized projection, so it absorbs the gap disproportionately.
     - **Verdict: real, identified, partially-fixable — not a dead end, and not "just variance."**
     - **⚠️ Owner: "yes, scope it" (2026-10-19) — both fixes below are now precisely specified
       (`analysis/wrw_compounding_vacancy/RESULTS.md` "Scope" section), not just proposed. Nothing built
       or shipped yet — spec only, per the two-track rule (test before ship).** Found real historical
       ground truth to test both on: `analysis/who_replaces_whom/build_frame.py` already built a true
       injury-status panel (`analysis/inactives/status_panel_2016_2025.csv`, 2016-2025 FRI/inactive
       designations — not a proxy) and used it to LOSO-fit the params currently shipping
       (`data/wrw_{wr,te,rb}_params.json`). Both fixes reuse that exact frame and fitting harness.
       - **Fix 1 (small, low-risk) — robust trailing share.** `scripts/statline_model.py`,
         `_wrw_trailing_usage()` (one shared helper feeding all three of
         `apply_{rb,te,wr}_replacement`, so fixing it once fixes all three positions). Add a `share_agg`
         param to each `wrw_*_params.json` (default `"sum"` = today's behavior, byte-identical;
         `"median_pergame"` = new candidate, median of each trailing game's own share instead of a pooled
         sum, so one depressed game before a player goes OUT doesn't drag his whole vacated-share estimate
         down). Test: refit `frac[pos][rank]` with `analysis/who_replaces_whom/evaluate.py` on
         `share_agg="median_pergame"`, LOSO 2016-25, compare held-out MAE/bias to today's `"sum"` fit —
         ship only if it clears the same bar the original fit used.
       - **⚠️ Owner: "build and test Fix 1" (2026-10-19) — built, tested, FAILS, NOT SHIPPED.** Built both
         `"median_pergame"` and a second candidate (drop the OUT player's single worst trailing game,
         sum the rest), refit via the real `evaluate.py` harness on the true 2016-25 injury panel, LOSO.
         **Both come back worse (not better) on the subset that matters — WR/TE OUT → remaining WR/TE
         cell MAE 4.760→4.860 and 4.760→4.811 (fri def; "inactive" def shows the same pattern). Flat at
         best on the broader "next man up" subset.** This is a clean, tested wrong-direction-drop, not a
         borderline call. **Why, conceptually (important for anyone revisiting this): the LOSO refit
         re-fits `frac[pos][rank]` from scratch on whatever vacancy numbers the frame hands it — if a new
         aggregation method just rescales the vacancy estimate by roughly a constant factor, the refit
         absorbs that into an adjusted coefficient and predictions barely change** (confirmed: both
         variants produced near-identical predictions to the baseline despite real differences in the
         underlying numbers). **A fix that only changes how one player's own rate is averaged can't move
         held-out accuracy this way — only a fix that changes WHICH players are in the vacancy pool can.**
         That's exactly what Fix 2 does (it's a structural change, not a rescaling), which is why Fix 2
         remains the live candidate, untouched by this result. Full detail:
         `analysis/wrw_compounding_vacancy/RESULTS.md` "Fix 1 — built and tested" section.
       - **⚠️ Owner, same session: "there has to be an answer... this is bigger than week 6... we have
         missed the cheap chalk on pretty much every slate."** Took that seriously and found one — a real,
         general, repeatable mechanism, not a Wk6 fix (`analysis/ownership_recency_spike/RESULTS.md`).
         **SHIP CANDIDATE, not inconclusive.** Our ownership model never looks at a player's own very
         recent usage TREND — only his projection (which itself under-reacts to a fresh role change, see
         Fix 1/Fix 2 above) and his season-to-date average (`pub_val`, structurally slow to move). Built a
         `spike` signal from data already in this repo (nflverse weekly target-share — NOT external news):
         `max(0, last_game_share - trailing_3_game_share)`. Regressed
         `logit(real_own) - logit(our_modeled_own)` on it: **positive in all 5 historical seasons
         (2021-25, b=+7.05 to +10.04 overall, +9.5 to +16.1 restricted to cheap/salary≤$4,500) and in 4 of
         5 usable 2026 live weeks checked with the real deployed model (b=+3.8 to +9.3; wk1 has no prior
         week to compare, wk2 flat at 0.00, none reversed).** This is the same mechanism behind Bernard
         (26.4% real vs 9.1% modeled) at a smaller scale across most slates, not an isolated incident —
         directly answers "why was Bernard owned well and we weren't on him" in a way that generalizes.
         **Not "the field has info we lack"** ([[feedback_no_field_has_info_excuse]]) — target-share data
         is already in the pipeline, just never fed to the ownership model. Clears the project's own
         established bar for this exact kind of question (`analysis/ownership_history_calib`'s
         methodology: history settles direction, live data sets magnitude — both legs hold here, unlike
         several candidates that methodology previously rejected).
       - **⚠️ Owner: "Build it" (2026-10-19) — BUILT, WIRED, SMOKE-TESTED. Not committed (owner's call).**
         `scripts/ownership_v2.py`: new `spike_tgt` feature (last game's targets minus trailing-3-game
         average, clipped [0,6], reusing data already loaded for `p3_tgt`) and `apply_spike_bump()`
         (same additive-log-score/budget-reallocation mechanics as the existing `apply_vac_bump`,
         `SPIKE_BUMP_K=0.33` — the conservative end of the validated range), wired into `predict_v2()`
         right after the vac bump, same WR/TE scope. `scripts/build_projections.py`: pass the new
         `own_spike_tgt`/`own_spike_bump` audit columns through to `final_projections_*.csv`. Off-switch
         `DFS_OWN_SPIKE` (default on). **Smoke-tested on real Wk6 DK data (read-only, no output/ files
         touched):** Bernard's `estimated_ownership_pct` moves **9.07% → 13.80%** toward his real 26.4%
         (deliberately conservative — about a quarter of the gap); non-spike players (Worthy, Otton) give
         up a small, proportionate share; WR/TE group budget totals are **exactly identical** with the
         bump on vs off (336.72/114.90 both ways) — confirms pure reallocation, not budget inflation.
         Honest limitation: `0.33` is a reasoned starting coefficient from only 12 historical live
         spike-cases this season — refine as more weeks accumulate, not a reason to doubt the direction
         (validated 5/5 historical seasons, 4/5 live weeks). Full detail, including the exact smoke-test
         numbers: `analysis/ownership_recency_spike/RESULTS.md` "SHIPPED" section.
       - **Fix 2 (bigger, the real "model sharpness" gap) — compounding vacancy.**
         `scripts/statline_model.py`, new helper alongside `_wrw_trailing_usage`. Today a player only
         counts as "vacating" if he played the team's most recent game (`last_g == g-1`) — a teammate who
         fell off ONE game earlier (Skowronek, a week before Wilson) is never captured by anyone, ever.
         New rule: for each OUT event, also pull in same-team RB/WR/TE whose `last_g` falls in
         `[g-1-K, g-2]` (fell off within the last K games, not the most recent) and whose trailing share —
         computed over HIS OWN games before his gap started — cleared the same eligibility gate; add his
         share to the vacancy pool with a **separately-fit** frac-by-rank (don't reuse the single-event
         coefficients unvalidated). New param `compounding_lookback_weeks` (candidate `K=2`, needs
         fitting). **Off by default** (`DFS_WRW_COMPOUNDING=0`), unlike the existing mechanisms, since
         this is unvalidated. Test: extend `build_frame.py`'s event loop to flag "compounding" events
         (using the real 2016-25 injury panel, not a proxy) as a labeled subset, fit the second
         frac-by-rank LOSO on that subset, same held-out + placebo bar as Fix 1 — **explicitly flagged as
         likely noisier** (smaller subset) so an inconclusive result here is an acceptable, honestly-
         reported outcome, not a failure.
       - **Sequencing:** Fix 1 first (lower risk, touches already-validated mechanisms). Fix 2 second,
         independently off-switched, so a null result on Fix 2 doesn't block shipping Fix 1. Neither is
         built yet — this is the next session's starting point.
   - **Construction-pattern note, not necessarily the cause:** the DK lineup rostered Andrews at TE AND
     Otton at FLEX — effectively a double-TE build, concentrating two unrelated bust risks into what reads
     as one roster slot of exposure. Worth keeping in mind for single-entry builds generally (don't stack
     two low-conviction, hard-to-predict positions in one lineup) but this didn't cause the miss — both
     individually busted on their own merits.

4. **FD main miss — Rams chalk stack (Stafford/Nacua/Kyren Williams) busted, but the Rams offense did NOT
   actually fail.** The user's framing ("Rams offense didn't show up") doesn't match the data. Rams
   implied total was 32.03 (highest or near-highest on the slate) and the offense scored plenty — combined
   real points across the roster were roughly in line with that total. **What actually happened: usage
   redistributed away from the two biggest chalk plays (Nacua 21.2 proj -> 14.0 actual, Kyren Williams 19.2
   proj -> 9.7 actual, nearly 50% under) toward backups who weren't rostered (Blake Corum 7.9 proj -> 14.0
   actual; Colby Parkinson, a $3,100 TE, 4.6 proj -> 14.1 actual).** No pregame injury/role flag existed on
   any Rams player (`injury_status` ACTIVE across the board, no `q_return_flag`/`role_change_injury_flag`)
   — nothing in available pre-game data separated this from a normal correctly-identified chalk stack that
   had a bad bounce (same category as the Wk5 BUF/LAR James Cook III case). Verdict for now:
   **unpredictable in-lineup redistribution, not a projection or ownership-model bug** — Stafford/Nacua/
   Williams being the biggest chalk was correct, FFC agreed (79.3% on Nacua/Williams, even higher than our
   55-57%), and the field that faded them to Corum/Parkinson would have needed information nobody had
   pregame. No action unless the user recalls an in-game event (injury, role change) we should check for.

5/6. **SUMMARY — goal, conclusions, and the resulting answer (read this first; the detailed trail below
   is kept for the evidence, not as the thing to read top to bottom).**

   **Original goal, the owner's own words:** "we've said that you shouldn't shy away from the chalk but
   the build on FD ended up basically being a cash lineup build and not really a single entry... I'm also
   wondering about adding a feature or two to the optimizer that allows the lineups to be assessed to
   determine which one you'd recommend playing based on all our rules."

   **Conclusions, in the order they were established (each correcting or building on the last):**
   1. The suspected mechanism (`_rank_lineups_by_proj_own` nudging the pool toward chalk) was already off
      since 2026-10-10 — ruled out immediately.
   2. On real $ payout (not percentile, which is a cash-game-shaped metric), full chalk trades away real
      tail equity; full contrarian is worse on every metric, everywhere. Neither extreme is correct.
   3. "No pivot was available this week" was wrong and retracted — the pool we already built contained
      better, less-chalky, higher-scoring alternatives the whole time (lineup #9/#12/#16 beat the
      submission on both real points and real ownership).
   4. "Pivot up in salary for leverage" looked contradicted in a first, too-pooled test, but properly
      tiered by salary it is real and confirmed specifically at the high-salary/stud tier this case lives
      in (pricier wins only 34% of matched comparisons at the $8-9k RB tier, holding in 11 of 15 real
      slates).
   5. Pivots are not rare or invented — a 20-100 lineup pool structurally contains multiple distinct,
      near-optimal plays per position. Confirmed directly: a positive-ownership-edge, near-max-projection
      alternative exists in 4 of 4 real slates checked (DK Wk4/5/6, FD Wk6).
   6. What's missing is not a better automatic SELECTION rule — every one tried (raw projection, our own
      modeled ownership, real ownership, blends, contrarian, FFC crowd data) failed to reliably beat raw
      projection using only pre-lock information. What's missing is **visibility**: the pool already
      computes these alternatives: nothing surfaces them.

   **Therefore, the logical answer to both linked questions:**
   - **Q1 (is SE over-converging to chalk?) — not a tuning bug.** The preset isn't mechanically broken
     toward chalk. The real gap is narrower and sharper: it picks the single highest-EV combination and
     shows nothing else, even though better, more differentiated options are sitting in the same pool.
   - **Q2 (recommendation feature, scoped not built) — build a pre-lock advisory view, not an
     auto-picker.** Mine the pool that's already built every week for the anchor (#1) plus its labeled
     alternate builds (full diffs, not single-slot swaps — swaps bundle 2-4 positions together in
     practice), ranked by the best ownership signal available today (our modeled ownership, or FFC for
     DK), with that signal's known weakness shown plainly. Default stays the #1 pick; the owner's own
     judgment breaks the tie, same as he already does with borderline backups. **This is the single most
     valuable, implementable next step** — it needs no new solver machinery (prototype:
     `analysis/classic_rerank_payout/mine_pool_pivots.py`), only a labeling/diff pass over existing output,
     and it does not require the ownership-model calibration gap to be fixed first to add value.

   **Design spec, finalized after further discussion with the owner (2026-10-19), replacing the first
   mining prototype's ad hoc choices with reasoned/tested ones:**
   - **Anchor = the pool lineup that scores best on BOTH projection and ownership together** (reuse the
     existing `_rank_lineups_by_proj_own`-style z(proj)+w·z(own) blend, repurposed from "pick the winner"
     — where it failed — to "identify what the field is actually building," a different and easier job).
     Pure top-projection alone is only an approximation of "the chalk/cash build," since our projections
     and the field's don't always agree.
   - **A pivot must be attributed to fading one specific, identified anchor player**, with whatever else
     changes in that alternate lineup shown as the consequence of freeing his salary, not counted as an
     independent source of credit. (The first prototype's `own_edge_total`, summed blindly across every
     differing slot, could be inflated by an unrelated low-owned bench player riding along — rejected for
     this reason.)
   - **Candidate filter: a salary-gap cap is the binding constraint, not the projection-closeness band.**
     Tested directly (`analysis/classic_rerank_payout/tol_calibration_detail.csv`, same 4 real slates,
     candidates restricted to players who actually appeared somewhere in the real 100-lineup built pool):
     widening the point tolerance from 3 to 10 points barely changes the candidate count (3.8 to 4.2 per
     anchor player) once salary gap is capped at ~$800-1,000 — the salary cap is what actually prevents an
     "$8k guy pivoting to a $6k guy" (a different play entirely, not a same-tier swap), and once it's set,
     the exact point tolerance stops mattering much. **Rule: salary gap capped at ~$800-1,000, with a
     generous (~5 point) projection band underneath it so real candidates aren't accidentally excluded.**
     This yields ~4-5 legitimate same-tier candidates per anchor chalk player on average, on real data.
   - **Show everything that passes the filter, don't rank/cut further for now** — no validated reason yet
     to prefer one candidate over another within the filtered set; that's for the owner's own judgment,
     revisit after seeing it in use.

5. **⚠️ REFINED after owner pushback (2026-10-19) — the real product question: is our single-entry build
   leaning too chalky, effectively playing like a cash-game lineup instead of a true one-shot GPP play?**
   User's own framing: "the build on FD ended up basically being a cash lineup build and not really a
   single entry."
   - **First ruled out the suspected mechanism.** `_rank_lineups_by_proj_own` (Wk4 item 12) has been **OFF by
     default since 2026-10-10** (`DFS_RANK_OWN_W=0`, confirmed nowhere else sets the env var) — the owner
     reverted it because it never cleared its own ship bar. `se3max_pool`'s live 100-lineup pool is ranked
     purely by `_rank_lineups_by_projection` (raw projection sum, descending), with `lambda=0` in the solver
     objective too. So there is no re-rank mechanism nudging the #1 slot toward "safe" — the hypothesis in
     the task brief doesn't hold for Wk6 (or any week since 10/10).
   - **Checked the actual Wk6 FD pool directly** (`output/lineups_multi_fd_fd_classic_wk6_main_18Oct2026_shared.csv`,
     20 ranked lineups, joined to `output/final_projections_fd_fd_classic_wk6_main_18Oct2026.csv` for our
     modeled ownership and to the real contest export `data/contest_results/fd_classic_wk6_main_18Oct2026_full.csv`
     for realized `%Drafted`/`FPTS`). By our own `estimated_ownership_pct`, lineup #1 (the submitted one) was
     only **middling**, 11th of 20 most-owned. But by **real** field ownership it was the single **most-owned
     (chalkiest) lineup in the entire pool** (rank 1 of 20) — our ownership model under-called exactly how
     chalky this specific combination actually was. On real points, lineup #1 scored 117.58, which is 4th-best
     of 20 (lineups 9/12/16 scored ~129, lineup 4 scored 126.38, all less-owned by the real field) — a normal
     single-slate miss, not a landslide.
   - **Then checked whether this is a systemic pattern using existing held-out history**, rather than treating
     one slate as proof either way (`analysis/classic_rerank/RESULTS.md`, Wk4 item 12's original study, 17-21
     real history pools 2022-25 + 2026 live pools). That study already tested exactly this — "pick #1 by raw
     projection vs. pick by ownership sum, vs. a projection+ownership blend, vs. deliberately leaning
     contrarian (w=-0.5)" — graded by real finish percentile, held out. **The verdict there is the opposite
     of the "we're too chalky, need more differentiation" framing:** picking the *most-owned* lineup in the
     pool by **real** ownership would have added +.10 to +.13 percentile over the current raw-projection pick
     (the chalk-leans-good finding from `CLASSIC_RULES.md` holding at the single-pick level, not just in
     aggregate). Leaning *contrarian* (w=-0.5, i.e. deliberately picking a less-owned alternative) was tested
     and is **wrong-direction** (-.17 percentile on one of the two independent 2026 pool sets, inconsistent
     sign across datasets). The only thing that doesn't work today is that **our own** `estimated_ownership_pct`
     doesn't carry real lineup-level chalk signal (that partial correlation is near zero on history, vs. +.15
     to +.22 with real ownership) — so we can't yet tell *which* lineup in the pool is the real-field's
     favorite, we just got lucky/unlucky that #1-by-projection happened to be it this week.
   - **Verdict: wrong-direction to add a "lean toward leverage/ceiling" mode to the SE #1 pick** — the held-out
     history says chalk-when-correctly-identified is good for SE, not bad, and the Wk6 FD miss was ordinary
     lineup-level variance (same category as item 4's Rams redistribution finding), not evidence of a
     structural over-chalk bug. **The real, already-identified fixable gap is calibrating `estimated_ownership_pct`
     at the lineup-sum level** (see `analysis/classic_rerank/RESULTS.md`'s own "single most valuable fixable
     thing" — train/check modeled-vs-real lineup-sum ownership correlation, controlling for projection). That
     is a projection/ownership-model task, not a construction or selection-rule task, and is not new work
     created by this session — it was already the standing open item from the Wk4 study.
   - One data caveat: `Tyquan Thornton` had no row in the real contest export (likely 0%-drafted/truncated from
     the export, not a data bug) — affects only 1 of 20 lineups' real-own sum by a small amount, doesn't change
     the ranking conclusions above.
   - **Owner's pushback, verbatim (2026-10-19): "I don't think we can just say that the chalkier the build the
     better tho....we aren't playing cash games so there has to be a balance between eating the chalk and
     making some important pivots. That's the balance we need to try and find."** Substantive gap in the
     analysis above: the original `classic_rerank` study (and my re-check of it) graded every pick rule on
     mean/median **finish percentile** — that's a cash-game-shaped metric (did we beat the average field
     entry). SE payout structures are top-heavy/convex (min-cash pays little, the real equity is in the right
     tail), so a rule can win on average percentile while being worse on actual **expected payout**, especially
     if going full-chalk correlates bust risk across the roster (exactly the pattern in item 3's double-TE
     build and item 4's Rams stack this week). Re-tested properly below rather than restating the prior finding.
   - **Re-test using real $ ROI, not percentile** (`analysis/classic_rerank_payout/payout_rerank_test.py`,
     `RESULTS.md`). `analysis/lineup_replay/hist_lineups_graded.csv` carries `roi` computed directly from each
     historical contest's **real DK prize table** (payout/cost − 1), not a synthetic curve — exactly what the
     pushback asked for, no new data needed. Same held-out history as before: 21 pools with REALIZED field
     ownership (`H`, the look-ahead ceiling case — what's possible if our ownership model were perfect) and
     17-18 pools each for 3 arms with our own pre-game MODELED ownership (`H2`, leak-free, what we can act on
     today).
     - **Full contrarian is confirmed bad on $ terms too, not just percentile.** `min_own` (pick the least-owned
       pool lineup) is worse than the current raw-projection rule on every single metric tested, in both the
       realized and modeled datasets: mean ROI -0.81 vs -0.24 (H real), tail P90 ROI -1.00 vs +2.00 (H real —
       the tail gets *worse*, not better), and cash rate 10% vs 24%. Going contrarian does not buy ceiling; it
       loses on ceiling too. This settles that half of the question.
     - **Full chalk-max is not the clean winner either — it trades away real tail equity.** `max_own` (pick the
       most-owned pool lineup, using real ownership) improves mean ROI (-0.07 vs -0.24) and nearly doubles cash
       rate (43% vs 24%) — consistent with the earlier percentile finding — but its **P99 ROI drops to +2.80
       vs the baseline's +4.60**: the single biggest-upside outcomes across the 21 slates are smaller when you
       chase the single most-chalk combination. This is the piece the percentile-only test missed, and it is
       exactly the owner's concern: leaning hard into chalk measurably costs something at the true tail, even
       though it helps on average/cash-rate.
     - **A small, specific "1-2 pivot" rule did best on every metric at once, in the realized-ownership case:**
       stay within the top 2% of the pool's own best projection (i.e., give up almost no EV), then within that
       near-max band pick the **least**-owned candidate. On the 21 real-ownership history pools this beat the
       raw-projection baseline on mean ROI (+0.07 vs -0.24), cash rate (48% vs 24%, the best of any rule
       tested, including full chalk-max), AND tail (P99 +4.40, essentially matching the baseline's +4.60, far
       above full-chalk-max's +2.80). That is a genuine, quantifiable "balance point" — not full chalk, not
       full contrarian, but a small deliberate pivot away from the single most-popular combination while
       staying near the top of the projection board. The 1%/5% versions of the same rule and the "top-10/20
       by projection, then least-owned" variants were inconsistent — the 2%-band version is the one that held
       up; this should be read as one promising calibration, not a swept/robust optimum.
     - **⚠️ CORRECTED 2026-10-20 — the "doesn't transfer" framing above overstated noise as failure.**
       Re-pulled the raw numbers from `analysis/classic_rerank_payout/payout_rerank_out.txt` instead of
       trusting this write-up's own summary, prompted by the owner catching the same mistake on item A1.
       The actual per-arm `dROI` and 90% CIs for `nearmax2pct_minown` on our modeled ownership are:
       fc +0.167 [-0.167,+0.583], new **-0.029** [-0.559,+0.471], old -0.306 [-1.000,+0.222]. The "new"
       arm was mis-cited above as -0.21 — it's actually -0.029, essentially flat. **All three CIs cross
       zero.** That's not "helps 1 of 3, hurts 2 of 3" — it's "statistically indistinguishable from zero in
       all 3 arms, with 2 of 3 point estimates non-negative." Overstating wide, zero-crossing noise as a
       directional failure is exactly the error already caught and corrected on item A1 this same session
       ([[feedback_ship_inconclusive_when_human_reviewed]]) — same root cause (grading a human-reviewed,
       opt-in signal against too strict a bar), same fix.
     - **Corrected verdict and action taken:** this is a pick suggestion for the SE3Max Pool manual review,
       not an auto-submit mechanism — the same category that already clears a lower ship bar. Shipped as
       `_tag_near_max_pivot()` in `scripts/optimizer.py` (classic `build_multi_lineup`, called after the
       existing rank functions): adds a purely additive `near_max_pivot` boolean column (plus
       `near_max_pivot_proj`/`near_max_pivot_own_sum` context columns) marking the one pool lineup, within
       2% of the pool's best projection, with the lowest summed modeled ownership — **never reorders
       `lineup_id` or changes which lineup ranks #1**, so it doesn't repeat the mistake that got
       `_rank_lineups_by_proj_own` reverted on 2026-10-10 (that one silently changed `lineup_id` sort order,
       which conflicted with the owner's explicit intent that it stay pure-projection-sorted). Smoke-tested
       on a real historical pool: correctly tagged a different, legitimately lower-owned lineup (not the #1
       pick) within the 2% band. Default on (env `DFS_NEAR_MAX_PIVOT_PCT`, 0 disables).
     - **Confidence caveat, stated plainly (unchanged, still accurate):** this is the same n as the original
       study (17-21 history slates, one pick per slate per rule) — small. On REAL ownership the rule wins on
       every metric at once (mean ROI, cash rate, near-matched tail) but even that CI is wide (+0.31 mean
       ROI, CI [-0.05, +0.67]). Directionally consistent, not proven at a strict ship bar — shipped anyway
       as a review aid per the corrected verdict above, same reasoning as item A1. Full data:
       `analysis/classic_rerank_payout/`.
     - **Also re-checked while correcting this (2026-10-20): the full-chalk (`max_own`) rejection above is
       partly built on a shaky statistic.** Its P99 ROI figures (4.60 vs 2.80) come from `np.nanpercentile`
       of only 21 values — effectively reading off the single best slate, not a stable tail estimate.
       Pulling the raw per-slate ROIs (`per_pool_picks_roi.csv`) shows that "drop" is almost entirely ONE
       slate (`h2022w04`) flipping from the best outcome under `base_proj` (ROI +5.0) to a bust under
       `max_own` (ROI -1.0) — a single-slate artifact, not a systematic tail cost. The practical call to
       prefer `nearmax2pct_minown` over full chalk still stands (it matches or beats `max_own` on every
       metric in this same data), but the *reason* given — "chasing chalk provably costs the tail" — should
       be read as unproven, not as settled evidence.
   - **Tried to make the pivot automatic/reliable using a non-circular signal, before giving up on it.** Our
     own `estimated_ownership_pct` is partly a function of our own projection (that's why the pivot rule is
     unreliable with it). FFC crowd ownership (`data/ownership_public/ffc_dk_*`, DK main only, real for all
     of 2026) is genuinely independent — the field's own consensus, not derived from our numbers. Tested the
     same near-max-2%-least-owned pivot on the 3 real 2026 DK main weeks where we have a built pool + FFC
     data + the real contest result (Wk4/5/6; `analysis/classic_rerank_payout/ffc_pivot_test.py`): **FFC
     picked the identical alternative lineup as our own model every single time** (no added discriminating
     power in this sample) and the pivot only helped 1 of 3 weeks (wk5: real points 149→185; wk4: 128→114;
     wk6: 134→120). So an automatic ownership-driven pivot is confirmed unreliable two different ways now
     (history + live 2026, two different ownership sources) — not asserted, tested.
   - **Correction (owner pushback, same session): "no pivot was available" is not a defensible claim and
     has been retracted.** The field beat us — real rosters that differed from ours scored better and
     existed, so pivots obviously existed; a few paragraphs above already proved it independent of any new
     search, because our OWN 20-lineup FD pool (the one we built, pre-lock) already contained them:
     lineup #9 (Josh Allen / James Cook III / D'Andre Swift / Tyler Warren, no Stafford-Nacua-Kyren-Likely)
     scored 129.2 real points and summed 163.7 real ownership, vs. the submitted lineup #1's 117.58 points
     and 256.5 ownership — a fully legal, already-built alternative, sitting unselected at proj-rank 9 of 20,
     the whole time. Lineups #12 and #16 are the same story (129.0 pts each, 138.5/120.9 own). **Pivots did
     not merely exist in theory, they were already sitting in our own output file.** What I actually found
     below is narrower and real but should not have been generalized: *for one specific player (Kyren
     Williams) within the one specific lineup we submitted*, the cap was spent tightly enough ($59,900/
     $60,000) that no same-tier, pricier alternative could be swapped in without exceeding it. That is true
     and worth fixing, but it describes why a **single-player swap on lineup #1** was blocked — it does
     **not** explain, and must not be read as explaining, why the field's actual winning combinations (or our
     own lineup #9/#12/#16) went unplayed. The real, still-open, and much harder problem is exactly what the
     rest of this item has been testing all along: **picking a different, already-built, better lineup out of
     the pool before lock, using only pre-game information** — not "finding a pivot" (trivial, pivots are
     everywhere in a 20-100 lineup pool by construction) but "knowing in advance which one." That is
     unresolved; see the percentile rerank, ROI rerank, and FFC tests above, all of which found this
     unreliable with current signals. The cap-constrained single-player-swap finding below still stands as a
     real, separate, narrower fact and a legitimate secondary lever — it is kept, corrected in scope.
   - **The single-player-swap finding, scoped correctly this time:** checked why the already-live
     `pivot_finder.py` tool (runs every slate, does exactly this per-player pivot search on the ONE lineup
     you actually submit) suggested zero alternatives for Kyren Williams or Isaiah Likely on lineup #1
     specifically. Not a tool bug: lineup #1 spent $59,900 of FD's $60,000 cap (and the pool's 20 lineups
     spend a median of $59,900), leaving ~$100 of slack. Every same-position, similar-projection, materially-
     less-owned alternative to Kyren Williams in the player pool (Kenneth Walker III, Bijan Robinson,
     Jonathan Taylor, Derrick Henry) costs more salary, not less — none fit in $100 of room. This is real and
     fixable (see the salary-slack/tolerance lever below), but it is a fact about swapping one player within
     one already-chosen lineup, not a statement that no better lineup existed anywhere in the pool.
   - **Owner's follow-up hypothesis — first test was too blunt, and the owner's pushback on it was right.**
     "it actually makes more sense to pivot up in salary than down. the field is going to choose the cheaper
     of two options at the same projection...so the higher up play will have natural leverage." A first pass
     (864 matched-projection-QUARTILE comparisons, all salary levels and positions pooled together) found the
     opposite — pricier more-owned on average — but pooling across the whole salary range hid real,
     tier-dependent heterogeneity. Re-tested properly with tight pairwise matching (432k pairs: same slate +
     position, projection within 5% of each other, salary gap >= $300), broken out by salary tier:
     low-salary pairs (~$3-5k): pricier is more-owned 73% of the time (own 2.74% vs 1.63%); this reverses as
     salary rises, and at high salary (~$8k+) it's close to even (49%, own 8.61% vs 9.48%). **Narrowed to the
     exact tier this case is about — RB, cheaper side priced $8,000-9,000, the Kyren Williams tier — the
     owner's mechanism is confirmed, clearly: cheap-side real ownership 16.85% vs. pricier-side 10.95%,
     pricier wins only 34% of 665 pairs, and the direction holds in 11 of 15 real slates spanning 2022, 2024,
     and 2025 (not one lucky slate).** The Kenneth Walker III/Kyren Williams comparison cited earlier as
     evidence AGAINST the hypothesis was, in hindsight, one data point going against a tier-level pattern that
     mostly supports it — the single-player anecdote is not the 665-pair tier average.
   - **Corrected conclusion: "reserve room to pivot UP" IS supported, specifically at the high-salary/stud
     tier where this case lives** (the opposite holds at low/mid salary — a separate, lower-priority pattern,
     not chased further here). This reopens the salary-slack-reservation fix in its original direction:
     reserving cap room so a lineup can pivot to a cheaper, similarly-projected stud-tier alternative is
     supported. `pivot_finder.py` itself does not need a directional fix (its candidate search was never
     restricted to one salary direction) — the real blocker, confirmed earlier, is cap exhaustion (lineup #1
     spent $59,900 of $60,000, leaving no room for any swap at all), and that is the right thing to fix. Full
     detail and the tier breakdown table: `analysis/classic_rerank_payout/RESULTS.md`.
   - **Revised verdict (two-track) — this is the real action item, not another "needs more research":**
     - **Pivots exist, provably, every week — that is not in question.** Our own 20-lineup Wk6 FD pool had
       at least three (lineup #9/#12/#16) that beat the submission on both real points and real ownership.
       The hard, unresolved problem is **selection**: knowing before lock which built lineup (or which
       player-level swap) is the better one. That is what every rule tested above (raw projection, modeled-
       own, real-own, blends, contrarian, FFC crowd data) was trying to solve, and none of them reliably
       beat picking the single highest-projection lineup, using only pre-lock information.
     - "Chalkier is always better" overstated the real finding — hard-leaning into chalk trades away real
       tail equity (P99 ROI 2.8 vs 4.6). **Full contrarian is still wrong-direction** (worse everywhere,
       confirmed on ROI, confirmed again on live 2026 data). An **automatic** ownership-based pivot rule is
       not reliable with either ownership source we have — do not ship one that auto-selects.
     - **The shippable fix is making the already-existing alternatives visible and selectable, not inventing
       new ones from scratch.** The pool already contains better options most weeks (proven above); the gap
       is that nothing surfaces them pre-lock for a human decision. Combine this with item 6: surface the
       pool's near-max-projection alternatives (ranked by real-world-plausible ownership signal, imperfect as
       it is) for the owner's own judgment, same as he already does with borderline backups. Separately, give
       the pool construction room to actually hold the kind of alternative that's supported at the elite-
       salary tier (pivot to a cheaper, similarly-projected stud — confirmed above), which a near-fully-spent
       cap currently forecloses.
     - **Next concrete step (bounded, not open-ended):** add an optional salary-slack lever to `se3max_pool`
       (e.g. a soft floor that forces some share of the 100-lineup pool to leave $300-800 unspent, next to the
       existing `max-exposure`/`lambda`/`cl-*` knobs in `data/optimizer_presets.json`/`scripts/optimizer.py`)
       so a cheaper, similarly-projected, legitimately-less-owned stud-tier alternative has somewhere to go
       even when the top-projection lineup is maxed out, then test on real history (`analysis/lineup_replay/`
       already has the real-prize-table ROI pipeline used above) before shipping it on.
     - Standing, separate item (not blocking this one): still calibrate `estimated_ownership_pct` at the
       lineup-sum level — it would make any FUTURE automatic pivot-selection smarter, but the salary-slack fix
       above doesn't need it and should go first since it's the actual blocker found this week.

6. **Lineup-recommendation feature — scoped, not built.** Revised after item 5's re-test: there IS a real,
   quantifiable (if not yet shippable) trade-off — full chalk costs real tail equity, full contrarian is
   worse everywhere, and a small near-max-projection/least-owned pivot looks like the best of both on real
   ownership, but isn't reliable yet on our own modeled ownership. So the feature isn't "pick safe vs.
   leverage"; it's a **surface the near-max alternative and let the owner's judgment break the tie**:
   - **What it should show, pre-lock, per pool:** for the current top ~10 lineups by projection, a compact
     table — projection rank, our modeled own-sum + rank within pool, our modeled own-sum's historical
     reliability caveat (we know it's weak at the lineup level today), real-rule grades from
     `grade_construction_week.py`'s rule set (`CLASSIC_RULES.md`/`SHOWDOWN_RULES.md` weights) applied to each
     candidate, and a flag for "this pick and the next-best pick differ by under X% of projection but by Y
     points of own-sum" (i.e., surface genuine near-ties where the user's own judgment/news should break the
     tie — consistent with how the user already treats borderline backups manually).
   - **What it should default to recommending:** still the #1-by-projection pick (that's what history
     supports) — the feature's value is *showing the pool* and *flagging when our own-model confidence is
     low* (e.g., when modeled own-rank and projection-rank disagree a lot, which is exactly when our ownership
     signal is least trustworthy per item 5), not overriding the pick with a different criterion.
   - **Open product question for the owner:** do you want this as a passive pre-lock view (eyeball before you
     hit submit, same workflow as today's "SE3Max Pool (100)" review) or an active one (pop a warning only
     when the top-2 picks differ meaningfully on a rule grade)? Needs the owner's call before building either.
   - **Implementable next step if the owner wants to proceed:** add a `--show-pool-summary` flag to the SE3max
     pool build path in `scripts/optimizer.py` that writes a small `*_pool_summary.csv` (proj rank, own-sum +
     rank, rule-grade columns reused from `grade_construction_week.py`) alongside the existing lineup CSV —
     pure read/report, no solver or ranking change, off by default, fails safe (prints nothing extra on error).
     This is additive to the existing pipeline and does not require resolving the ownership-model calibration
     gap first (that gap limits how *useful* the "own-sum" column is, but the rule-grade columns are useful
     today, independent of it).

7. **A2 re-opened and closed on a much bigger sample (2026-10-20).** Before building item 6's feature, the
   owner pushed back: "picking some [rules] and saying they didn't pass isn't going to work... what criteria
   are we grading it against? min cashing? top 1%?" — and separately flagged that the 21-slate table behind
   items 5/6 "seemed assumed." Both were right:
   - **The 21-slate sample was not what it looked like.** File timestamps show `hist_grade.py` ran mid-build
     on 2026-09-29 and only caught 16 slates from 2022 + 5 from 2023 (mostly one season), using an old preset
     (20% randomization, forced bring-back) that isn't today's `se3max_pool`. 63 slates sat ungraded.
   - **The real history is 64 usable slates (2022-25, all seasons) — this is all that exists**, not a 6-week-
     per-year sample as previously described. Rebuilt today's actual preset on all 64 x 3 projection arms =
     19,200 graded lineups (real $1 SE DK prize tables), plus a 16-slate 2026 check. ~90 min compute.
   - **Grading objective defined from the real prize tables, not assumed:** min-cash pays 1.5x (breakeven
     needs 67% cash rate — nowhere close to achievable), 49% of all pool profit comes from top-1% finishes.
     Owner's stated order (cash rate first, top-1% second) used directly, with real ROI as the money check.
   - **Result: lineup #1 (today's default) is the best spot in the pool for cash rate — 33.3% vs pool average
     28.6%, holding in all 3 arms and a separate 2026 check (43.8% vs 38.4%).** 63 single-signal rules and 9
     fitted scoring models all cashed the same or less. The earlier "near-max-2%, least-owned" pivot finding
     (behind the shipped `near_max_pivot` tag) does not survive this sample, even given a look-ahead real-
     ownership ceiling case (+1.0 [-4.7,+6.8], not the old +24pt figure).
   - **A2 is closed, don't build it** — there's nothing to surface; #1 is already correct. See A2's entry
     above for the full close-out note. Full data/scripts: `analysis/wk6_pool_selection_objective/RESULTS.md`.
   - **What this redirects to:** every lineup in the pool — including #1 — has roughly the same (negative)
     expected value against the real field (#1 mean ROI -0.36). The owner's reaction: "cashing 33% of the
     time means I'll lose all of my bankroll over time... what we need to do is find the mechanism that
     increases this number." That's item 8.

8. **What actually drives cash rate: projection accuracy, not ownership (2026-10-20).** Diagnostic reusing
   item 7's 64-slate dataset (no new builds) to test whether per-slate projection accuracy or per-slate
   ownership-model accuracy predicts whether a slate's pool actually cashes.
   - **Structural fact first:** `se3max_pool` runs at lambda=0 with ownership-rerank off — ownership never
     enters the solve, so it has no mechanical path to move the 33% either way.
   - **Ownership accuracy: no reliable relationship.** Correlation with pool cash rate -0.1 [-4.0,+3.6],
     flips sign by season (+9.2 in 2023, -12.3 in 2025). A5's low-end metrics (Spearman, AUC) also null here.
     Controlling for projection edge doesn't change this. (This doesn't retire A5 — see A5's 2026-10-20
     addendum above: ownership still matters for MME/pivot/leverage use cases, just not this number.)
   - **Projection "edge" — our Spearman rank-accuracy minus a salary-only baseline's, same slate — is a real,
     consistent driver: +4.9 cash points per SD [+1.9,+7.8], positive in all 4 seasons, significant in all 3
     projection arms.** Placebo-checked: FC's own edge-over-salary does NOT predict our pools' cash rate
     (-1.9, CI crosses 0), but OUR edge over FC does (+5.9 [+2.2,+9.2]) — confirms it's our skill on a given
     slate, not "this slate was easy for everyone."
   - **Sized:** slates in the worst edge-quartile cash 20% (pool)/25% (#1); best quartile cashes 36%/56%. Our
     average edge today is +0.030; breakeven is around +0.045. 12 of 64 slates were at/below zero edge.
   - **By position, the fixable gap:** RB is the strongest, most consistent driver and we already have a real
     edge there (+0.026). **WR is no better than salary (+0.001 edge) and TE is worse than salary (-0.026)**
     — both move cash rate about as much per SD as RB does. No existing checklist item covers WR/TE
     within-position ranking accuracy specifically.
   - **Rough size if closed:** lifting average edge from +0.03 to the +0.05-0.08 range looks worth +3 to +6
     pool-cash points, plausibly +5-10 on #1 — stated as an estimate from cross-slate comparison, not a
     promise, and a real stretch (we beat FC by only 0.012 edge today).
   - Full data/scripts: `analysis/wk6_cash_rate_driver/RESULTS.md`. Became **A6** (new item above).

9. **A6 case-study/mock-replay autopsy, closed (2026-10-22).** Full WR/TE miss autopsy across 8
   worst-edge historical slates + 8 random historical slates (mock step) + 2026 Wk1-6 (16 slates
   replayed). Found a real mechanism — our WR/TE target projections are over-spread vs. price/target
   history (top TEs over-projected ~25%, matches real busts Loveland/Pitts/Schultz/Andrews/Otton) — but
   correcting it (TE price-weight, Spearman edge +0.059, all 4 seasons positive) does not move cash rate
   (pool 30.0%→29.7%, worse on 2026 live). WR price-weight is wrong-direction (FC is also worse than
   salary at WR — a market-wide gap, not ours alone). Cause: cash rate is decided by week-specific
   information (who gets the targets/TDs that specific week), not by a better average-case ranking — a
   mock nudge of just 5% toward the real post-game answer lifted pool cash 31%→40%, confirming the room
   is real but not reachable by a static formula fix. **Nothing ships. Redirects to week-specific
   signals (injury-driven vacated targets, props, late news) as the next candidate lever — see Parking
   Lot.** Full data/scripts: `analysis/wk6_wrte_autopsy/RESULTS.md` (local only, FC-derived, not
   committed).

## Parking Lot (add here, don't chase inline)
- **Chalk under-projection (from A7's close-out, 2026-10-23).** Our projections run ~5pts low on 40%+
  real-owned players (95% CI [+1.3,+7.6]); FC is only ~2pts low on the same players (CI crosses zero), and our
  general bias at 10-20% owned is only ~+1.35. A real, measurable projection-accuracy gap specifically on the
  players that decide slates — not acted on this session. Owner: open as its own item eventually, not now.
- **Week-specific WR/TE signals (from A6's close-out, 2026-10-22).** A6's mock-replay showed a 5% nudge
  toward the real post-game answer lifts pool cash 31%→40% — real room that a static projection-formula
  fix (price-weighting) can't reach, because the information that actually decides cash is week-specific
  (who gets the vacated targets/TDs that week), not an average-case ranking improvement. Next candidate:
  test whether injury-driven vacated-target signals, props, or late news can close any of that gap
  pre-lock. Not scoped yet — needs its own dedicated session.
- Thursday's SEA/DEN showdown miss (rank 2,545/8,917, ~71st percentile) — not investigated this session,
  reads as a normal non-cash finish, not flagged as systemic. Revisit only if the user wants to dig in.
- `data/ownership_actual_log.csv` is only logged through week 4 (`scripts/log_ownership.py`) — weeks 5 and
  6 are missing. Routine maintenance, not an accuracy finding; catch up when convenient.
