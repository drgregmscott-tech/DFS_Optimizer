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

**Data:** *(pending)*

---

## 3. Field-implied projection backout

**Hypothesis:** where the field's implied projection (backed out from real field ownership) diverges sharply
from ours, the field is closer to the actual outcome more often than chance (>50%).

**Data to collect:** per player where |our projection − field-implied projection| exceeds a materiality
threshold (TBD — need a number here too), record both projections and the actual result.

**Success:** across all logged weeks, field wins the divergence cases significantly more than 50% of the time
(binomial test, acknowledging small-sample weeks need pooling before this is meaningful — see
[[feedback_verify_full_history_and_power_before_concluding]]).
**Failure/inconclusive:** indistinguishable from 50/50 — no signal that the field holds information we're missing.

**Build note:** the field-implied-projection backout itself doesn't exist yet — needs to be built from FC field
ownership data before this can run.

**Data:** *(pending)*

---

## 4. classic_field.py simulation validation

**Hypothesis:** feeding our pre-lock target ownerships into `scripts/classic_field.py`'s simulator produces a
simulated field whose construction-shape stats (position counts, salary usage, stack rate, duplication) match
the real FC field for that slate within normal slate-to-slate variability.

**Data to collect:** simulated vs real field stats, plus a baseline of how much two *real* slates normally
differ on the same stats (Q5) — needed to know what counts as "beyond normal" mismatch.

**Success:** simulated-vs-real gap is within the normal real-vs-real variability band → simulation mechanics
are adequate, any ownership gap traces upstream to our input targets.
**Failure:** gap exceeds normal variability → simulation mechanics themselves don't capture real field behavior.

**Data:** *(pending)*

---

## 5. Pool-reachability check

**Hypothesis:** the full 100-lineup pool (not the one lineup played) contains at least one lineup, built only
from players/exposures already in the pool, that clears the reachability bar (Q2).

**Data to collect:** per slate, yes/no + the best qualifying lineup found (if any) + its rank/score.

**Success (system-level, across weeks):** if "yes" dominates across weeks, construction is reaching the right
combinations and the issue lies elsewhere (selection or pure variance in which single lineup wins).
**Failure:** if "no" dominates, that's evidence of a construction-stage failure — the pool never had access to
the winning combination at all.

**Data:** *(pending)*

---

## 6. Naive-baseline comparison

**Hypothesis:** our pool meaningfully outperforms naive baselines (pure-chalk, pure-salary/value,
Vegas-implied-total-only) on the actual slate results.

**Data to collect:** score each baseline lineup against actual results; record where that score ranks within
our 100-lineup pool's score distribution (see Q3).

**Success:** naive baselines rank below our pool's median in most weeks.
**Failure:** a naive baseline beats our pool's median (or our actual pick) in a majority of logged weeks — flagged
as more alarming than ordinary variance, since it suggests our model's complexity isn't earning its keep.

**Data:** *(pending)*

---

## 7. Winners-vs-field positioning

**Hypothesis:** our pool's player-exposure vector correlates more strongly with the field's winning-tail
exposure vector (Q4) than with the full-field average exposure vector.

**Data to collect:** per slate, correlation(our exposures, winning-tail exposures) vs correlation(our exposures,
full-field-average exposures).

**Success:** we consistently correlate more with the winning tail than the field average.
**Failure:** we correlate more with (or no better than) the full-field average — we look like a median field
entrant rather than a differentiated one.

**Data:** *(pending)*

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
