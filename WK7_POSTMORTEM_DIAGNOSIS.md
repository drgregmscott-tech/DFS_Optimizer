# Week 7 Postmortem — Diagnosis

**Purpose:** diagnose the overall 100-lineup pool and model behavior for each Week 7 slate — not the single
lineup played. This file is collect-then-analyze: every section records data/measurements first; interpretation
only happens after all sections are populated, and only in light of all 7 weeks logged so far (see
`ALL_WEEKS_LEDGER.md`), not Week 7 in isolation.

**Status legend:** `[ ]` not started · `[~]` data collected, not yet analyzed · `[x]` analyzed, logged to ledger

**Slates covered:** (fill in once slate files are pulled — DK main/early, FD, etc.)

---

## Resolved thresholds (locked in 2026-10-26)

- **Q1 / Q3 — "notable miss" / statistical significance:** z-score = (actual points − our projection) /
  our player std_dev. Notable miss = |z| ≥ 1.5. Cross-week significance tests (items 3, 6, 7) use this same
  discipline, but **with n=7 weeks, only a 6-of-7 or 7-of-7 directional split clears a normal confidence bar** —
  4-of-7/5-of-7 is genuinely inconclusive, not a failure of the method. See protocol below.
- **Q2 — reachability bar:** item 5 is a diagnostic *read* (current rate, logged with a confidence interval given
  n=7), not graded pass/fail against a number from one week. 50%+ is the **operational target** the action-items
  file drives toward, not a bar week 7 alone is judged against.
- **Q4 — "winning tail":** primary definition = top 20% (actual cashers). Top 1% tracked separately as a
  secondary, curiosity-level comparison, not the main bar.
- **Q5 — variability baseline:** use the 7 weeks we have first. If item 4 is inconclusive, fall back to
  multi-season FC data as a secondary check only, flagged explicitly with the caveat that older seasons differ
  in contest size/rules/meta.
- **Pool used for items 5-9 ("the real pool"), resolved 2026-10-26:** historical `lineups_multi_*` files have
  multiple run-UUIDs per slate with no record of which one was actually played, and `data/ui_slates/` snapshots
  only exist for week 7 and don't capture exclusion choices anyway — so the exact played pool is **not
  forensically recoverable** for any week. Resolution: for every week (1-7), "the real pool" = Greg's stated
  exclusion rules (ownership cutoff, TE/DST salary bands, QB projection floor, game-environment lean — see item
  9) applied **strictly** to that slate's player universe from `output/final_projections_*`, same construction
  used for item 9's variant A/etc. This is a close reconstruction, not a byte-for-byte match — it won't capture
  "unless top value play" exceptions actually exercised in the moment. Acceptable; noted as a known limitation,
  not something to re-litigate if a result looks surprising.
- **Going forward (week 8+):** save the actual exclusion parameters used at lock time alongside the slate, so
  this reconstruction problem doesn't recur. Data hygiene, not a model finding — doesn't belong in the
  action-items file.

---

## Protocol when results come back inconclusive

Decided now, before any data is seen, so this can't be rationalized after the fact:

1. **Check direction before significance.** A lopsided-but-short-of-the-bar split (5-of-7, 6-of-7) triggers
   extending the sample via the multi-season FC fallback *before* concluding "no effect" — not an automatic pass.
2. **A genuinely mixed split (near 50/50) is real information, not a reason to rework the hypothesis on the
   spot.** Reworking a hypothesis is only legitimate as a new, separately logged question for a future round —
   never a retroactive reframe of the same test because it didn't come out significant (that's HARKing).
3. **Triangulate across items.** Even if no single item clears a strict bar, log whether multiple independent
   items point the same direction (e.g. pipeline-attribution clusters on construction + low pool-reachability +
   we-look-like-median-field). Convergence across independently-designed tests clears the low "worth testing
   further" bar even without any one test clearing the high "proven" bar.
4. **"Inconclusive across the board" is itself a conclusion, written down explicitly** — it means current
   measurement resolution can't detect an effect this size with this data. The next step is "get a bigger sample
   or a sharper question," stated outright, never silently dropped.

---

## 1. Pipeline-stage attribution

**Hypothesis:** every notable miss can be traced to exactly one stage (news/injury ingestion →
projections → ownership model → portfolio optimizer/pool construction → final pick) with cited evidence.

**Data to collect:** per notable miss (see Q1), a row with: player, stage, evidence citation (what in our
pipeline's own output shows the stage was wrong), confidence (high/medium/low).

**Success:** ≥80% of notable misses get a high/medium-confidence single-stage attribution.
**Failure / inconclusive:** evidence implicates multiple stages equally, or no stage — tag as `indeterminate`.
Don't force a guess to hit the 80% bar.

**Data:** *(pending)*

---

## 2. Floor/ceiling tagging

**Hypothesis:** none yet — this item is pure categorization. No lever exists in the optimizer today that this
plugs into (confirmed by reading `scripts/optimizer.py` — objective is point projection + optional sigma-mode
diversification noise, no explicit ceiling/floor-aware objective). This is descriptive data only, logged across
weeks to see if a dominant pattern exists before we ask whether a lever should be built.

**Data to collect:** per notable miss (Q1), tag as floor-break (points well below reasonable expectation despite
no red flag) / ceiling-miss (field had a high-ceiling outcome we had negligible exposure to) / neither.

**Success/failure:** N/A for a single week. Logged to ledger; only evaluated once multiple weeks are in.

**Data (2026-10-26, weeks 1-7, main slates only — DK main + FD main):**

Scope and method, agreed with owner before building (cost/rigor tradeoff discussed explicitly — see session):
exposure is the owner's *actual reconstructed pool exposure*, not our model's projected ownership. Reconstructed
real pool = owner's stated manual exclusion rules, applied strictly (no "unless top value play" override, same
convention as Item 9), fed into `se3max_pool` (100 lineups) for each of the 14 main-slate week/site
combinations. Owner's stated rules (2026-10-26): DK — exclude ownership <2%, TE salary $4,500-5,900, DST outside
$2,800-3,100, QB unless projected >20; FD — same concept, TE exclusion is salary <=$4,100 only (no upper band).
Game-environment QB lean is a judgment tie-break, not coded (same treatment as the value-play override).
Per-player exposure % = share of that slate's 100-lineup pool rostering him; <5% = negligible (ceiling-miss).
Floor-break = under-miss where Item 1's own attribution left `stage=indeterminate` (no known cause already
logged); an under already attributed to engine/ingestion (e.g. "volume/role projection wrong", "probable missed
inactive") is tagged `neither` — already explained elsewhere, not a floor/ceiling finding.
Scripts: `analysis/wk7_postmortem_item2/` (`build_exclusions.py`, `run_all.py`, `tag.py`).

**Side finding during the build, flagged not acted on:** applying the QB rule (>20 proj) strictly produced
**zero surviving QBs** in 3 of 14 slates (DK wk2, FD wk1, FD wk2) — every QB that week projected under 20, making
the build literally infeasible without invoking the override. Recovered by exempting that slate's single
highest-projected QB (as the "top value play" override would in practice); those 3 pools are n=50 lineups (the
lone QB hit the preset's 50% max-exposure cap), not n=100. This means the override isn't a rare edge case — it
was load-bearing in ~21% of these 14 slates just to field a legal lineup. Not re-litigated here per Item 9's own
"known limitation" convention; noted for whoever picks up Item 9.

**Results, 411 main-slate notable misses across 7 weeks:**

| tag | count | share |
|---|---|---|
| ceiling-miss | 351 | 85% |
| neither | 52 | 13% |
| floor-break | 8 | 2% |

By week:

| week | ceiling-miss | floor-break | neither |
|---|---|---|---|
| 1 | 90 | 2 | 14 |
| 2 | 52 | 1 | 4 |
| 3 | 63 | 1 | 5 |
| 4 | 46 | 0 | 6 |
| 5 | 32 | 0 | 12 |
| 6 | 31 | 0 | 6 |
| 7 | 37 | 4 | 5 |

By position: ceiling-miss dominates WR (139/160, 87%), TE (71/85, 84%), RB (71/82, 87%); QB is more mixed
(50 ceiling-miss / 5 neither / 3 floor-break of 58); DST/D skews floor-break-or-ceiling-miss, almost no `neither`
(21/24). Ceiling-miss salary is cheaper on average (median $5,100) than real-exposure overs tagged `neither`
(median $6,200) — consistent with the exclusion rules squeezing out cheaper/longer-tail plays specifically.

The 8 floor-breaks: 5 DST/D (Titans x2, Dolphins, Panthers x2), 3 QB (Josh Allen wk3, Brock Purdy + Bryce Young
wk7 FD) — all had real ownership/projection (not excluded), busted well below projection, and Item 1 found no
pipeline-stage cause.

**Not yet interpreted** — per this doc's own collect-then-analyze rule, held until the other items are populated
and read together.

---

## 3. Field-implied projection backout — `[x]` analyzed, 2026-10-26

**Hypothesis:** where the field's implied projection (backed out from real field ownership) diverges sharply
from ours, the field is closer to the actual outcome more often than chance (>50%).

**Materiality threshold used:** same 1.5 std_dev "notable miss" bar locked in above (no new bar invented).

**Method:** the field doesn't publish a point projection, only ownership. Per slate and position, fit real
ownership against the percentile rank of our projection with a simple monotonic (isotonic) curve, invert it —
given a player's real ownership, back out what projection-percentile the field's ownership implies, then read
that back into points using the slate's own projection distribution. That derived number is the "field-implied
projection." Scripts in `analysis/wk7_postmortem_item3/` (not committed, regenerable — see repo convention);
outputs under `data/fc_history/derived/wk7_item3/` (FC-derived, not committed).

**Primary test result (FAILED, in the wrong direction):** 93 slates (86 history 2021-25 + 2026 wk1-7), 509
divergent rows (2.0% of the pool). The field-implied projection was closer to actual points only **36.5%** of
the time (186/509, p=1e-9) — our own projection wins the "closer to actual" contest more often, not the field.
Every individual season came in between 33-41%, no season flipped the result.

**Secondary, separately-logged check (direction, not magnitude) — also did not survive a live-usable test:**
in 72% of those same divergence cases (p=6e-24, consistent 74-76% every history season), actual points moved in
the direction the field was pointing, just by much less than the implied gap suggested (realized move ≈ 40% of
implied). This looked like it might support a small corrective nudge, so it was tested four ways before any
conclusion was drawn:

| Ownership input used to build the field-implied number | Divergent rows | MAE gain, held out | 2026 clean out-of-sample |
|---|---|---|---|
| Real post-contest ownership (not available pre-lock — can't act on live) | 493 | +0.91 [+0.49, +1.28] | worse |
| FC's pre-lock *projected* ownership (genuinely pre-lock, but FC subscription is now dead) | 262 (2021-23 only) | +1.56 [+1.03, +2.14] | n/a |
| Our own live v2 ownership model — the only input actually usable at lock | 95 | +1.22 [+0.29, +2.08] | worse |
| Same, properly refit leaving out the scored season (leak removed) | 88 | +0.60 [−0.21, +1.44] — CI crosses zero | worse |

The only inputs that showed a stable effect (real ownership, FC's dead subscription) aren't accessible at lock
time. The one input we could actually use — our own ownership model — only showed the effect because it had
been trained on the slates it was tested against; once that leak was removed the effect roughly halved, the CI
no longer excludes zero, and it reversed sign in the most recent full season (2025) and in 2026. Gating attempts
(projection floors, ownership floors, field-higher-only) did not rescue it in any variant.

**Conclusion: no shippable fix from this item.** Nothing added to the action-items file — a dropped idea with no
surviving live-usable signal doesn't clear either the ship-bar or the test-bar track. The one real takeaway: a
*better* pre-lock ownership estimate (FC's dead one, or a hypothetically improved version of ours) does carry
real signal that our current one doesn't — that's a restatement of the already-tracked ownership-model-quality
gap (see `analysis/model_vs_fc/RESULTS.md` section C, `analysis/ownership_v2_refit_after_projstack/RESULTS.md`),
not a new lever this item discovered. Improving ownership-model quality remains the live lever; a projection
nudge built on top of the current model is not.

**Methodology note, worth remembering for future field-vs-us comparisons:** the 50% bar used for the primary
test is the correct null for a symmetric two-estimator "which is closer" contest (no a priori reason either
side should win more than half the time if neither carries extra information) — it is not borrowed from, and
isn't the same thing as, the unrelated top-20%-cash-line threshold used elsewhere in this doc. A caveat worth
flagging: the field-implied number is a *constructed* quantity (curve-fit + inverted), which stacks extra
modeling noise on top of whatever real signal real ownership carries, so a sub-50% result partly reflects that
the backout is a noisier instrument than our direct, mature projection model — not purely "the field has no
information." That is exactly why the direction-only secondary check was run before concluding anything, and
why its failure under a leak-free, live-usable input is the thing that actually closes this item, not the
36.5% headline number by itself.

---

## 4. classic_field.py simulation validation — `[x]` analyzed, 2026-10-26

**Hypothesis:** feeding our pre-lock target ownerships into `scripts/classic_field.py`'s simulator produces a
simulated field whose construction-shape stats (position counts, salary usage, stack rate, duplication) match
the real FC field for that slate within normal slate-to-slate variability.

**Data to collect:** simulated vs real field stats, plus a baseline of how much two *real* slates normally
differ on the same stats (Q5) — needed to know what counts as "beyond normal" mismatch.

**Success:** simulated-vs-real gap is within the normal real-vs-real variability band → simulation mechanics
are adequate, any ownership gap traces upstream to our input targets.
**Failure:** gap exceeds normal variability → simulation mechanics themselves don't capture real field behavior.

**Status: `[x]` analyzed, logged to action items (2026-10-26).**

**Data (2026-10-26):**

Scope agreed with owner: real field = **SE contests only** (`data/fc_history/lineup_study`, types `SE*`, not
showdown); duplication = share of entries whose exact 9-player set matches ≥1 other distinct entrant in the same
contest. Scripts/outputs: `analysis/wk7_postmortem_item4/` (`run_item4.py`, `compare.py`, CSVs; FC-derived, not
committed).

- **Real population:** 134 DK SE main-slate classic contests, one file = one data point (2022: 35, 2023: 31,
  2024: 25, 2025: 33, 2026: 10). 7 non-main slates dropped (2024wk4 Mon-only, 2023wk17 Thu-Sun, Fri-Mon
  Thanksgiving slates). 2026 wk2 has **5** SE contests, not 1: the `2026wk2b_*` files are 4 more SE contests on the
  same DK slate (153428).
- **Stats:** (1) mean salary per slot (QB, RB avg of 2, WR avg of 3, TE, FLEX, DST) + total salary mean/p10/p50,
  + FLEX position mix; (2) QB stack = ≥1 (and ≥2) of the 7 skill slots on the QB's team; (3) most players from one
  team in the 9 (DST included), mean and share 3+/4+; (4) duplication.
- **Band:** spread across real contests. "IN" = |sim − mean of that week's 5 real contests| ≤ p90 of
  |difference| between two real contests on different slates.
- **Sim:** `classic_field.simulate_field()` (seed 0, n=25,000), own = `estimated_ownership_pct` from
  `output/final_projections_dk_dk_classic_wk{1,2}_main_*.csv`.

**Data-quality flags:**
- Some rostered players have no team/salary in FC's data (e.g. a 26%-owned 2025 player). Affected lineups are
  dropped for stats 1-3 (kept for dup). The band uses only contests with ≤5% of lineups affected (107 of 134).
  2026 affected share: wk1 ~3%, wk2 ~8% (the wk2 comparison is still run, flagged).
- Our pre-lock targets put **30.3 (wk1) / 74.4 (wk2) ownership points on OUT-status players**, which shows up in
  16% / 52% of sim lineups. Everything was re-run with OUT players zeroed: no stat changed IN/OUT status (wk1
  stack≥1 moved to 92.9%, still IN).
- `simulate_field` keeps only one 200k batch's salary-legal draws (2-4k lineups) and resamples them **with
  replacement** up to n, so its output as returned is mostly exact copies. A second sim dup figure pools distinct
  draws from 7-13 seeds (≥26.5k distinct lineups).
- Sim's achieved ownership vs its input target: MAE 0.36 (wk1) / 0.72 (wk2) pts overall; 1.2 / 1.7 for players
  with target ≥1%.

| stat | real median [IQR] | p90 real-vs-real diff | wk1 sim / real (5 contests) / gap | wk2 sim / real (5 contests) / gap |
|---|---|---|---|---|
| QB salary | 6261 [6000-6485] | 886 | 5994 / 5966-6000 / +8 IN | 5930 / 5967-5985 / −45 IN |
| RB salary | 6507 [6253-6664] | 830 | 6639 / 6796-6853 / −186 IN | 6516 / 6804-6855 / −311 IN |
| WR salary | 5942 [5773-6062] | 492 | 5824 / 5897-5929 / −83 IN | 5913 / 5769-5784 / +139 IN |
| TE salary | 4114 [3919-4331] | 729 | 3925 / 3859-3921 / +23 IN | 3816 / 3940-3995 / −160 IN |
| FLEX salary | 5724 [5610-5859] | 503 | 5897 / 5608-5678 / +252 IN | 5934 / 5910-5948 / +5 IN |
| DST salary | 2935 [2872-3050] | 355 | 3061 / 2914-2943 / +134 IN | 3187 / 3006-3040 / +166 IN |
| total salary, mean | 49,880 [49,870-49,900] | 52 | 49,627 / 49,818-49,846 / −204 **OUT** | 49,637 / 49,866-49,884 / −239 **OUT** |
| total salary, p10 | 49,700 | 100 | 49,300 / 49,600-49,700 / −380 **OUT** | 49,300 / 49,700 / −400 **OUT** |
| total salary, p50 | 49,900 | 100 | 49,600 / 49,900-50,000 / −360 **OUT** | 49,600 / 49,900-50,000 / −340 **OUT** |
| FLEX is TE | 16.1% [12.1-20.8] | 19.5 pts | 9.3% / 19.5-21.1% / −11 IN | 6.4% / 13.3-13.8% / −7 IN |
| QB stack ≥1 | 83.8% [80.2-88.9] | 13.1 pts | 91.4% / 79.5-83.8% / +9.2 IN | 90.3% / 81.1-86.7% / +6.1 IN |
| QB stack ≥2 | 36.3% [32.4-42.3] | 16.0 pts | 69.2% / 31.7-36.4% / +35 **OUT** | 68.6% / 31.1-37.1% / +35 **OUT** |
| max-team count, mean | 2.44 [2.40-2.52] | 0.19 | 3.29 / 2.40-2.44 / +0.88 **OUT** | 3.42 / 2.38-2.43 / +1.03 **OUT** |
| share with 3+ from one team | 41.7% [38.6-47.3] | 14.1 pts | 73.2% / 38.2-41.9% / +34 **OUT** | 73.6% / 37.1-41.7% / +35 **OUT** |
| share with 4+ from one team | 5.8% [4.9-6.9] | 3.7 pts | 39.2% / 4.7-5.7% / +34 **OUT** | 44.2% / 4.6-5.6% / +39 **OUT** |

Duplication (band over all 134 contests: median 4.2% [IQR 3.0-5.3%], p5-p95 1.5-7.1%, p90 real-vs-real diff
3.9 pts; real dup rises somewhat with contest size, corr 0.29). Sim dup measured at each real contest's entry
count:

| contest (entries) | real dup | sim dup, as returned | sim dup, pooled distinct draws |
|---|---|---|---|
| wk1 Fair Catch (17,145) | 3.95% | 98.7% | 0.05% |
| wk1 Huddle (11,880) | 2.50% | 95.1% | 0.04% |
| wk1 $40K Pylon (15,830) | 3.95% | 98.2% | 0.03% |
| wk1 $20K Pylon (7,914) | 2.97% | 86.4% | 0.03% |
| wk1 Daily Dollar (17,812) | 4.23% | 98.9% | 0.06% |
| wk2 Daily Dollar (17,810) | 3.41% | 99.98% | 0.02% |
| wk2 Fair Catch (17,148) | 3.18% | 99.97% | 0.03% |
| wk2 Huddle (23,758) | 2.66% | 99.99% | 0.05% |
| wk2 $40K Pylon (15,838) | 3.25% | 99.96% | 0.03% |
| wk2 $20K Pylon (7,921) | 2.70% | 97.9% | 0.02% |

Substitute clean sim dup, **pre-resample, single batch, not multi-seed-pooled** (seed 0's own unique salary-legal
draws from its one 200k batch, deduped among themselves): wk1 **0.00%** of 3,967 draws (0.00% of 2,045 with OUT
players zeroed); wk2 **0.00%** of 2,056 draws (0.09% of 2,243 with OUT zeroed). For scale, real contests under
6,000 entries: median 3.5%, p5 1.0% (n=63). OUT of the band, same direction as the pooled number.

All clean sim dup figures are **OUT** of the band, below it (single batch 0-0.09%, pooled 0.02-0.06%, real
2.5-4.2%). The as-returned figure is OUT above it (86-100%), but that's a resampling artifact, not field behavior.

**Plain read of the measurements (no interpretation):** IN for every per-slot salary, FLEX mix, and QB stack ≥1.
OUT for total salary usage, QB stack ≥2, all max-team stats, and duplication. Same verdicts in both weeks and
with OUT players zeroed.

**Interpreted with owner 2026-10-26:**
- **Duplication** is not an actionable simulator gap. Real SE duplicates are largely syndicate/"touting"
  behavior (one lineup provider, many entrants playing it), not independent convergence — the simulator models
  no such thing and isn't expected to. Owner's view: these should arguably be treated as one entry, not N.
  No action item.
- **QB stack ≥2 / max-team concentration** and **total salary usage** are real, explained simulator gaps —
  both logged to `WK7_POSTMORTEM_ACTION_ITEMS.md` (test-bar, open, not yet scoped): (1) `stack_boost` is
  calibrated only against stack≥1 and compounds across skill slots, overshooting higher-order team
  concentration that real single-entry fields deliberately avoid (SE players spread correlation risk for a
  small edge, reserving heavy stacking for large-field MME); (2) `MIN_SALARY` ($49,300) sits well below the
  real-field practical floor (~$49,700, with a smaller real contingent at ~$49,500) — sim leaves $200-400 more
  unspent than real fields ever do on a main slate (showdown is the one format where that's normal, not
  applicable here).
- Per-slot salary, FLEX mix, and stack≥1 being IN means the simulator's baseline ownership/salary allocation
  mechanics are sound — the two gaps above are specific, scoped parameter issues, not a sign the simulation
  approach itself is broken.

---

## 5. Pool-reachability check — `[~]` data collected, not yet analyzed (2026-10-26)

**Hypothesis:** the full 100-lineup pool (not the one lineup played) contains at least one lineup, built only
from players/exposures already in the pool, that clears the reachability bar (Q2).

**Method agreed with owner 2026-10-26, before building:**
- **"Clears the reachability bar"** = cashes on actual points, using this repo's standing top-25% cash-line
  convention (same as `CLASSIC_RULES.md`, `WK3_ROOT_CAUSE_FINDINGS.md`, `analysis/lineup_replay/*`) — not a
  new bar invented for this item.
- **Two readings run side by side:**
  - **Broad** (primary, per owner's choice): pool the *player universe* across all 100 lineups in the
    reconstructed real pool, then ILP-search for ANY salary-legal, position-legal 9-man combo from that
    universe — not necessarily one the optimizer actually built — maximizing ACTUAL points. Tests whether
    construction ever had the right pieces available, isolated from selection (Items 6/7/9).
  - **Narrow** (comparison only): does any of the 100 actually-built lineups itself cash on actual points.
- **Pool used:** the same strict owner-exclusion-rule reconstruction as Items 2/4/9
  (`analysis/wk7_postmortem_item2/pools/{site}_wk{week}.csv`), weeks 1-7, DK+FD main slates (14 combos) — not
  week 7 alone, per Q2's resolution that this item is a cross-week diagnostic read with a CI, not a one-week
  grade.
- **ILP constraints:** real salary cap + exact roster-slot legality (QB/RB/RB/WR/WR/WR/TE/FLEX/DST per site),
  `exclude_skill_vs_opp_dst` OFF (that's our own house construction rule, not real roster legality, so turning
  it off keeps the broad search to "any legally draftable combo"); no stack/bring-back requirement (also an
  own-house rule, not legality) — this is deliberately a looser test than "could our actual strategy have
  reached it," i.e. the most generous version of "did construction have the pieces at all."
- Real contest files: `data/contest_results/.../*_full.csv` (DK wk2-4 use the `_se3max_full` split; every
  other site/week has one plain `_full.csv`, already single-entry — verified unique `EntryName` per row).
  Scripts: `analysis/wk7_postmortem_item5/run_item5.py` (not committed, regenerable).

**Data (2026-10-26, 14 slates, weeks 1-7, DK+FD main):**

| site | wk | pool lineups | universe size | broad cashes | % of 100 that cash | top-proj lineup pctile | top-proj cashes |
|---|---|---|---|---|---|---|---|
| dk | 1 | 50 | 25 | Y | 46.0% | 65.2% | N |
| dk | 2 | 50 | 29 | Y | 8.0% | 32.8% | N |
| dk | 3 | 100 | 49 | Y | 6.0% | 35.7% | N |
| dk | 4 | 100 | 48 | Y | 52.0% | 97.1% | Y |
| dk | 5 | 50 | 29 | Y | 42.0% | 59.1% | N |
| dk | 6 | 100 | 49 | Y | 3.0% | 27.9% | N |
| dk | 7 | 97 | 45 | Y | 18.6% | 8.0% | N |
| fd | 1 | 50 | 26 | Y | 34.0% | 83.8% | Y |
| fd | 2 | 50 | 34 | Y | 16.0% | 62.9% | N |
| fd | 3 | 100 | 58 | Y | 6.0% | 32.7% | N |
| fd | 4 | 100 | 44 | Y | 11.0% | 42.0% | N |
| fd | 5 | 100 | 52 | Y | 20.0% | 78.6% | Y |
| fd | 6 | 50 | 30 | Y | 44.0% | 50.7% | N |
| fd | 7 | 50 | 39 | Y | 8.0% | 82.8% | Y |

**Broad reachability: 14/14 slates (100%). Narrow (≥1 of the 100 cashes): 14/14 (100%).** Not a single-lineup
fluke — the share of the 100-lineup pool that itself clears the cash line ranges 3-52% (mean 22.5%, median
17.3%), so cashing lineups are typically a meaningfully-sized chunk of the pool, not one lucky draw. Universe
size (distinct players across the 100-lineup pool) ranges 25-58 per slate.

**The question that actually matters — can we FIND the cashing lineup, not just whether the pool contains
one:** the single highest-pre-lock-projection lineup in each pool (a proxy for "the one we'd actually have
picked," since the exact played lineup isn't forensically recoverable per this doc's own resolved note) cashes
in only **4/14 slates (28.6%)** — statistically indistinguishable from the 22.5% mean random-draw-from-pool
rate at n=14. **Picking by top projection shows no visible edge over blind luck at finding the cashing lineup
in this sample** — construction has access to cashing combinations essentially every week, but there is no
evidence yet that our selection step preferentially surfaces them over picking a random lineup from the same
pool. This is the same question Items 6 (naive-baseline) and 7 (winning-tail positioning) are built to test
properly with real baselines and larger samples — this is a same-session, lower-rigor echo of that question
using data already in hand, not a replacement for those items.

**Data-quality flag:** 4 of ~511 total universe-player rows (across all 14 slates) had no match in that
slate's real contest player table (`Theo Wease Jr.` wk1 FD, `Tom Kennedy` wk3 FD, `Konata Mumpfield` wk6 FD,
`Myles Price` wk7 FD) — all sub-$4k dart-throw WRs, treated as actual=0. Negligible: none of these could
plausibly have been the ILP's chosen player over a known-scoring alternative at a similar price, and a few
missed points on a deep punt can't move a lineup already sitting at 85-100th percentile.

**Not yet interpreted** — per this doc's own collect-then-analyze rule, held for discussion with owner before
any conclusion or action item.

---

## 6. Naive-baseline comparison — `[x]` analyzed, 2026-10-27

**Hypothesis:** our pool meaningfully outperforms naive baselines (pure-chalk, pure-salary/value,
Vegas-implied-total-only) on the actual slate results.

**Method (final, after two corrections — see session log for the discarded intermediate versions):** each baseline
is a full 100-lineup pool, built through the *same* production command that built our real pool
(`optimizer.py --preset se3max_pool --n-lineups 100 ...`, same stack/exposure/shape-term mechanics), with only the
optimization signal swapped — chalk = `estimated_ownership_pct`, value = `season_avg`, vegas =
`implied_total*1000 + season_avg` (team-cap 3). Universe = full slate minus `injury_status == OUT` (our pool used
the owner's band-exclusion rules instead, by design — see flag below). Confirmed no hidden ownership penalty
fights the chalk objective (own-penalty/min_total_ownership = 0, shape terms never read ownership). Cash = top 25%
of the real contest field, same convention as every other item. Scripts/data:
`analysis/wk7_postmortem_item6/run_item6_pools.py`, `RESULTS_pools.md` (not committed, regenerable).

**Pre-registered bar:** naive baseline beats our pool's median (or our pool's cash rate) in a majority of the 14
slates → failure.

**Results (14 slates, DK+FD main, weeks 1-7):**

| | pool cash rate (mean/median) | slates ≥1 cashing lineup | slates beating our cash rate | mean field % |
|---|---|---|---|---|
| **Our pool** | **22.5% / 17.3%** | 14/14 | — | 51.4% |
| Chalk (our ownership model) | 16.4% / 13.5% | 13/14 | 5/14 | 44.4% |
| Value (`season_avg`) | 20.9% / 24.5% | 14/14 | 6/14 | 47.8% |
| Vegas (implied-total) | 0.5% / 0.0% | 5/14 | 0/14 | 5.1% |

**Vegas excluded from the verdict — not a close call, structural:** even after two fixes (tie-break, then a
3-per-team cap), Vegas-as-a-pure-signal collapses into roster depth once a team's starters hit the exposure cap
(1,347/1,400 lineups rostered a scoreless no-show); confirmed this persists with randomization off. Logged as "a
single Vegas-implied-total signal cannot build a viable 100-lineup pool under this construction pipeline" — itself
a finding, not a gap to re-attempt without a materially different design (e.g. Vegas picks teams only, a real
projection fills players within them).

**Conclusion (owner-reviewed and accepted, 2026-10-27):** on the pre-registered bar, our pool clears it — neither
chalk nor value beat our pool's median or cash rate in a majority of slates (5/14 and 6/14 respectively). Taken
together with Vegas's outright failure, this is read as our model's sophistication meaningfully beating naive
single-signal strategies, not merely tied with them. Two honest caveats for the record, not re-opened: (1) value's
*median* slate (24.5%) edges our pool's median (17.3%) — the margin is real but not overwhelming, concentrated in
the mean/tail more than every individual slate; (2) chalk's pools run hotter on team concentration than ours
(62.4% of lineups with 4+ from one team vs. our 45.6%) and were not capped for consistency the way Vegas was — a
tighter chalk cap might narrow or widen the gap, left untested since the owner judged current evidence sufficient
to close this item.

---

## 7. Winners-vs-field positioning — `[~]` data collected, not yet interpreted (2026-10-27)

**Hypothesis:** our pool's player-exposure vector correlates more strongly with the field's winning-tail
exposure vector (Q4) than with the full-field average exposure vector.

**Method agreed with owner 2026-10-27, before building:**
- **Vector space:** every player who appears in any entry of the full field that slate, per slate (union with
  our own pool's players). Our exposure = 0 for a field-rostered player we didn't touch.
- **Our exposure vector:** same reconstructed real-pool files as Items 2/4/5/6/9
  (`analysis/wk7_postmortem_item2/pools/{site}_wk{week}.csv`), % of the 100 lineups rostering each player.
- **Field vectors:** parsed directly from each contest's `Lineup` text column in `data/contest_results/.../*_full.csv`
  (same files as Item 5) — full-field average = % of all entries rostering a player; winning tail = % of the
  **top 20% of entries by actual Points** rostering a player (Q4's resolved "top 20%/cashers" convention, same as
  Item 4 — not the top-1% secondary definition).
- **Correlation:** Pearson primary, Spearman reported alongside (pre-registered, since exposure distributions are
  right-skewed and a Pearson-only read risks a few chalk outliers driving the result).
- **Bar:** same discipline as other items — ~11-14/14 slates (sign-test-significant) showing tail-corr >
  field-avg-corr needed to call "we look like winners," scaled up from the n=7/"6-or-7 of 7" convention to n=14
  slates.
- **Sampling-noise control added during the build (not in the original plan, needed before trusting the sign):**
  the winning tail is a much smaller group (938-4,752 entries) than the full field (4,690-23,758), so a smaller
  sample is mechanically noisier and could show lower correlation with *anything* regardless of whether winners
  really look different. Control: 30 random subsamples of entries, same size as that slate's tail, drawn from the
  full field with no regard to points, same exposure/correlation calc. If tail-corr ≈ random-subsample-corr, the
  gap is just sample-size noise; if tail-corr is meaningfully below the random-subsample floor, that's signal.
  Script: `analysis/wk7_postmortem_item7/run_item7.py` (not committed, regenerable); output
  `analysis/wk7_postmortem_item7/item7_results.csv`.

**Data (14 slates, DK+FD main, weeks 1-7):**

| | corr vs field-avg | corr vs winning tail | corr vs random same-size subsample | tail beats avg (Pearson) |
|---|---|---|---|---|
| **Pearson, mean** | 0.5180 | 0.4633 | 0.5172 | 1/14 slates |
| **Spearman, mean** | 0.4541 | 0.4440 | 0.4553 | 4/14 slates |

- **Pearson: tail-corr > field-avg-corr in only 1/14 slates** (dk wk1) — sign test p=0.0018, clears the
  significance bar in the **opposite direction of the hypothesis**. Mean gap −0.055, median −0.057; every other
  slate's winning-tail correlation is lower than its field-average correlation, several by a wide margin (fd wk4
  −0.097, dk wk2 −0.125, dk wk6 −0.118).
- **Spearman: tail-corr > field-avg-corr in 4/14 slates** — not significant (p=0.18), but same direction on
  average (mean gap −0.010).
- **Sampling-noise control confirms this is not a sample-size artifact:** mean correlation against a random
  same-size subsample (0.5172) is essentially identical to the full-field average (0.5180) — shrinking the
  sample size alone costs almost nothing. The winning tail (0.4633) sits clearly below *both*. Tail beats the
  random-subsample floor in only 1/14 slates (Pearson, p=0.0018) — the same single slate, same margin. This
  rules out "the tail just looks different because it's a smaller sample" as the explanation.
- Per-slate numbers, including Spearman detail and the noise-floor comparison, in
  `analysis/wk7_postmortem_item7/item7_results.csv`.

**Not yet interpreted** — per this doc's own collect-then-analyze rule, held for discussion with owner before any
conclusion or action item. Flagging for that discussion: this reads as a fairly clean, consistent result in the
*failure* direction defined above (we correlate measurably more with the median field entrant than with the
winning tail, in 13/14 slates, and the noise control rules out the obvious "just noise" objection) — but per the
"check direction before significance" protocol, worth triangulating against Items 1/5/6/9 before treating it as
an independent new finding vs. a restatement of something already logged (e.g. Item 6's chalk-baseline result,
or Item 1's ceiling-miss-dominant pipeline attribution) before any action item is drafted.

---

## 8. Running ledger across all weeks

Infrastructure, not a hypothesis — every item gets appended to `ALL_WEEKS_LEDGER.md` (or equivalent) in a
consistent schema per slate, covering weeks 1–7, so patterns can be read across weeks instead of guessed at from
one slate. No pass/fail criterion of its own; success = nothing above gets interpreted before this exists.

**Data:** *(pending — backfill weeks 1–6 + week 7 going forward)*

---

## 9. Alternate-parameter pool comparison

**Hypothesis:** holding projections/ownership fixed for a slate, Greg's actual manual construction rules
produce a pool that scores competitively against structurally different construction philosophies — i.e. the
process is roughly right and any gap is a small tweak, not a sign the whole approach is miscalibrated.

**Constants across every variant (the standing SE-100 preset, not under test):** SE 100-lineup preset, stack = 1
(QB + 1 correlated player), max 3 players from the same team.

**Ground truth:** the real saved pool (post-override) used for items 5-8, used as-is.

**Variants (strict mechanical rules, no "unless top value play" judgment override — see note):**

- **A — No exclusions:** raw SE-100 preset output, no manual filters at all.
- **B — Exclude a lot more:** same structure as Greg's real rules, pushed much harder (meaningfully higher
  ownership cutoff, tighter salary bands — exact numbers TBD per slate when built).
- **C — Position-only exclusion:** apply the real exclusion logic to only one position group at a time (isolate
  which specific rule — QB floor, TE band, DST band, ownership cutoff — is doing the work vs dead weight).
- **D — Leverage-chasing / contrarian:** near-opposite of the <2%-ownership exclusion — protect/boost exposure
  to low-owned, high-projection players; cap exposure to high-chalk plays above some ownership ceiling.
- **E — Chalk-heavy / safe:** opposite of D — near-exclusively high-ownership, high-floor plays, minimal
  differentiation; a cash-style build run through the SE/MME lens.

**TE-in-FLEX toggle:** run on/off only on the **real pool (ground truth)** and **variant A (no exclusions)** —
not crossed with every variant, to keep the build count tractable on a first pass.

**Note on "unless top value play":** Greg's real rules include a judgment-call exception that can't be
mechanically generated. Variants A-E apply the rules strictly (no override) by design — the real saved pool
remains the one true ground-truth comparison that reflects what was actually played.

**Data to collect:** score every build (real pool + A-E, with the TE-FLEX pair on real/A) against actual
results. Rank them. Log which philosophy would have scored best in hindsight, per slate.

**Success:** the real pool's score is statistically indistinguishable from (or beats) the best-performing
variant across logged weeks — current process direction is sound.
**Failure:** one of the structurally different variants (D or E especially, since they're the most divergent)
beats the real pool by a notable margin consistently across weeks — evidence the manual-exclusion philosophy
itself needs rework, not just a threshold tweak.

**Data:** *(pending)*
