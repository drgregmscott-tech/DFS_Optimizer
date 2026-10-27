# All-Weeks Ledger

**Purpose (Item 8 of `WK7_POSTMORTEM_DIAGNOSIS.md`):** a single consistent-schema table, per slate, across weeks
1–7, so each diagnosis item's result can be read across the whole sample instead of guessed at from one slate.
This file is pure compilation — every number here was already computed and logged by Items 1/2/5/6/7 of the
diagnosis doc; nothing is recomputed or newly interpreted here. No pass/fail of its own (per the diagnosis doc's
own definition of this item) — just the cross-week table other items reference.

Backfilled 2026-10-27 from existing outputs: `analysis/wk7_pipeline_attribution/all_weeks/summary_per_slate.csv`
(item 1), `analysis/wk7_postmortem_item2/tagged_main_slates.csv` (item 2), `analysis/wk7_postmortem_item5/item5_results.csv`
(item 5), `analysis/wk7_postmortem_item6/item6_pools_results.csv` (item 6), `analysis/wk7_postmortem_item7/item7_results.csv`
(item 7). Source CSVs are the source of truth; re-run this compilation if any of them change.

---

## A. Main-slate ledger (DK + FD main, weeks 1–7 — the 14-slate grain shared by items 2/5/6/7)

Columns: **i1** = pipeline attribution (item 1) restricted to this main slate — matched players, notable misses,
% notable, % of notable misses with a high/medium-confidence single-stage attribution. **i2** = floor/ceiling
tagging (item 2) counts out of that slate's notable misses. **i5** = pool reachability (item 5) — % of the
100-lineup pool that itself cashes (broad = best achievable from the pool's player universe), whether the
single highest-pre-lock-projection lineup cashed. **i6** = naive-baseline cash rate (item 6) for our pool vs.
chalk/value/vegas baselines built the same way. **i7** = winners-vs-field positioning (item 7) — Pearson
correlation of our exposure vector against the field average vs. the winning tail, and whether tail beat avg.

| site | wk | i1 matched | i1 notable | i1 %notable | i1 %hi/med-stage | i2 ceiling | i2 floor | i2 neither | i5 %pool cashes | i5 top-proj pctile | i5 top-proj cash | i6 our cash% | i6 chalk cash% | i6 value cash% | i6 vegas cash% | i7 corr-vs-avg | i7 corr-vs-tail | i7 tail>avg |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dk | 1 | 307 | 55 | 17.9% | 63.6% | 47 | 1 | 7 | 99.9% | 65.2% | N | 46% | 14% | 27% | 0% | 0.407 | 0.428 | **Y** |
| dk | 2 | 432 | 30 | 6.9% | 50.0% | 27 | 1 | 2 | 97.9% | 32.8% | N | 8% | 32% | 26% | 0% | 0.501 | 0.377 | N |
| dk | 3 | 442 | 27 | 6.1% | 55.6% | 23 | 0 | 4 | 100.0% | 35.7% | N | 6% | 2% | 5% | 0% | 0.559 | 0.507 | N |
| dk | 4 | 383 | 26 | 6.8% | 65.4% | 22 | 0 | 4 | 100.0% | 97.1% | **Y** | 52% | 30% | 24% | 1% | 0.550 | 0.513 | N |
| dk | 5 | 283 | 19 | 6.7% | 52.6% | 14 | 0 | 5 | 99.96% | 59.1% | N | 42% | 46% | 22% | 1% | 0.622 | 0.558 | N |
| dk | 6 | 243 | 18 | 7.4% | 72.2% | 13 | 0 | 5 | 100.0% | 27.9% | N | 3% | 2% | 1% | 0% | 0.476 | 0.358 | N |
| dk | 7 | 234 | 19 | 8.1% | 26.3% | 15 | 1 | 3 | 99.99% | 8.0% | N | 18.6% | 1% | 25% | 1% | 0.567 | 0.528 | N |
| fd | 1 | 275 | 51 | 18.5% | 49.0% | 43 | 1 | 7 | 99.8% | 83.8% | **Y** | 34% | 6% | 35% | 0% | 0.429 | 0.411 | N |
| fd | 2 | 282 | 27 | 9.6% | 40.7% | 25 | 0 | 2 | 99.5% | 62.9% | N | 16% | 30% | 6% | 2% | 0.451 | 0.366 | N |
| fd | 3 | 291 | 42 | 14.4% | 54.8% | 40 | 1 | 1 | 100.0% | 32.7% | N | 6% | 0% | 1% | 0% | 0.598 | 0.536 | N |
| fd | 4 | 259 | 26 | 10.0% | 65.4% | 24 | 0 | 2 | 100.0% | 42.0% | N | 11% | 30% | 19% | 2% | 0.478 | 0.381 | N |
| fd | 5 | 209 | 25 | 12.0% | 64.0% | 18 | 0 | 7 | 100.0% | 78.6% | **Y** | 20% | 6% | 26% | 0% | 0.635 | 0.627 | N |
| fd | 6 | 219 | 19 | 8.7% | 57.9% | 18 | 0 | 1 | 99.98% | 50.7% | N | 44% | 13% | 42% | 0% | 0.581 | 0.520 | N |
| fd | 7 | 204 | 27 | 13.2% | 40.7% | 22 | 3 | 2 | 99.88% | 82.8% | **Y** | 8% | 17% | 33% | 0% | 0.399 | 0.377 | N |

**Column sums/means (14 slates):** i1 — 3,863 matched players, 411 notable misses (10.6% mean), 54.1% mean
high/medium-stage attribution. i2 — 351 ceiling-miss / 8 floor-break / 52 neither (85% / 2% / 13%). i5 — mean
22.5% of pool cashes (broad), 4/14 top-proj-lineup cashes (28.6%). i6 — our pool beats chalk's cash rate in
9/14, value's in 8/14 (chalk/value beat us in 5/14 and 6/14 resp., per item 6's own framing). i7 — tail beats
avg in 1/14 (Pearson).

*(This table is numbers only, already individually logged and interpreted — or explicitly held for
interpretation — in diagnosis items 1/2/5/6/7. No new conclusion is drawn here; see those sections and
`WK7_POSTMORTEM_ACTION_ITEMS.md` for what's already shipped or open.)*

---

## B. Full pipeline-attribution ledger — all slate types, weeks 1–7 (item 1's native grain)

Item 1 covers more slate types than the main-slate table above (DK early/afternoon/showdown windows too). Full
per-slate detail already lives in `analysis/wk7_pipeline_attribution/all_weeks/summary_per_slate.csv` (35 rows);
per-week rollup in `summary_per_week.csv`. Reproduced here for the cross-week read this item asks for:

| week | notable | ingest-hi | ingest-med | engine-hi | engine-med | indeterminate | %hi/med-stage | matched | %notable |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 161 | 3 | 4 | 0 | 84 | 70 | 56.5% | 916 | 17.6% |
| 2 | 94 | 0 | 6 | 0 | 38 | 50 | 46.8% | 1,083 | 8.7% |
| 3 | 93 | 3 | 1 | 10 | 36 | 43 | 53.8% | 1,070 | 8.7% |
| 4 | 80 | 0 | 5 | 2 | 46 | 27 | 66.2% | 1,033 | 7.7% |
| 5 | 67 | 0 | 0 | 5 | 34 | 28 | 58.2% | 856 | 7.8% |
| 6 | 37 | 0 | 3 | 5 | 16 | 13 | 64.9% | 506 | 7.3% |
| 7 | 62 | 0 | 0 | 3 | 17 | 42 | 32.3% | 668 | 9.3% |

7-week combined: 594 notable misses / 6,132 matched players (9.7%), 320/594 high/medium-confidence single-stage
attribution (53.9%) — below item 1's own 80% success bar; already logged as such in
`project_wk7_item1_pipeline_attribution` (memory) and the RB-decay/stud-gap action items that followed from it.

---

## C. Items without a repeatable per-slate row (narrative status only)

- **Item 3 (field-implied projection backout):** closed, no shippable fix (`[x]` analyzed, 2026-10-26). Not a
  per-slate numeric series — it's a single pooled test across 93 slates (86 history + 2026 wk1-7) plus a 4-variant
  robustness check, already fully written up in the diagnosis doc's own section 3. Nothing to backfill here beyond
  a pointer.
- **Item 4 (classic_field.py simulation validation):** closed, 2 action items logged (`[x]` analyzed, 2026-10-26).
  Only built for DK main wk1/wk2 (the two slates with clean FD-sim-compatible data) against a 134-contest real-field
  band — not a 14-slate or 7-week series, so it doesn't fit this table's columns. Full detail in the diagnosis
  doc's section 4 and `WK7_POSTMORTEM_ACTION_ITEMS.md`.

---

## D. Item 9 (alternate-parameter pool comparison)

Not started (`*(pending)*` in the diagnosis doc). Once built, its per-slate/per-variant scores belong in a
companion table here (real pool vs. variants A–E per slate), using the same 14-slate main-slate grain as section A.
