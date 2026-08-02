# Handoff: pivot_finder.py — two separate findings from NHL Session 4.2

**Filed:** 2026-08-02, during NHL Session 4.2 work.

This doc originally covered one finding (the UI wiring gap below). NHL
Session 4.2 surfaced a second, more consequential one afterward — the
salary-tolerance logic itself, which NFL's `pivot_finder.py` runs live,
every week, right now. That one is listed first since it affects the
actual quality of suggestions your live NFL project is already producing,
not just how they're displayed.

## Finding 1 (higher priority): the salary-tolerance eligibility filter is
## likely producing bad pivot suggestions on real slates

**What NHL found:** NHL's `pivot_finder.py` was built as a direct port of
NFL's — same salary-tolerance-based eligibility filter (`SALARY_TOLERANCE
_PCT_OF_CAP`, later tried as %-of-the-cash-player's-own-salary). Real-data
testing against actual NHL slates (a full player pool, then a realistic
small slate) proved this basis unreliable at every value tried:
- Loose tolerances (10% of cap) produced technically-valid-but-useless
  "pivots" — e.g. a $8,700 center swapped for a $5,700 one, a 34% pay cut,
  not a same-tier alternative.
- Tight tolerances (1-2% of cap, or 15% of the player's own salary) left
  several real cash-lineup players with ZERO eligible candidates — not a
  thin-pool coincidence, a structural wall, since salary isn't a linear
  function of projected fantasy points (it also prices in matchup, role
  certainty, and market perception).

No setting in between fixed both problems at once, because the tolerance
was gating on the wrong variable. **The fix: filter pivot candidates by
similarity in `final_projection` instead of salary.** Salary becomes
informational-only output (still shown, just not a gate), and the
full-lineup salary-cap legality check stays exactly as-is (unchanged —
that check was always correct, it just shouldn't have doubled as a
similarity filter). NHL's version now uses `PROJECTION_TOLERANCE_PCT_OF_
CASH_PROJECTION = 25.0` (symmetric, i.e. a candidate can project a bit
higher or lower than the cash player), tested against real NHL data.

**This is very likely the same problem in NFL's live `pivot_finder.py`.**
The underlying reasoning (salary is a weak proxy for "similar projected
output") isn't NHL-specific — it's a property of any DFS site's pricing.
Worth pulling a real recent week's actual `pivot_suggestions_{site}_
{week}.csv` output and checking: are any of the suggested pivots a large
(20%+) salary swing relative to the cash player? If so, that's the same
pattern NHL found, live, in your NFL pivots right now.

**Recommended fix (next available session):**
- Change `find_pivots_for_player()`'s eligibility filter from a salary
  band to a `final_projection` band (symmetric %, off the cash player's
  own projection).
- Keep the existing full-lineup salary-cap re-check unchanged — it's a
  legality guarantee, not a similarity filter, and doesn't need to move.
- Add `salary_diff`/`salary_diff_pct` as informational output columns if
  not already present in some form.
- **Do NOT just copy NHL's 25% value** — NFL's salary distribution, pool
  sizes, and scoring are different; the right starting % needs its own
  real-data test the same way NHL ran through 15%/25%/35% against a real
  and a small slate before settling. Recommend the same test-multiple-
  values-against-real-data approach, not guessing a number.
- Also worth deciding explicitly (NFL didn't have to before, since salary
  tolerance always found *something*): what happens when a cash player
  has NO eligible pivot under a projection-based filter? NHL's answer,
  after testing, was to accept an empty result as legitimate information
  ("this player has no real same-tier alternative on this slate") rather
  than widening the tolerance until something appears. Recommend the same
  here, but worth confirming against NFL's own usage patterns.

**Validation:**
- Re-run `pivot_finder.py` for a recent real week and confirm every
  suggested pivot now has a real projection ~parity with the cash player,
  not just a legal salary swap.
- Spot-check that `leverage_score`'s behavior still makes sense once
  candidates are projection-pre-filtered (NHL found the score more
  directly tracks the ownership edge once this change is made, since
  `projection_retention` sits near 1.0 for most eligible candidates by
  construction — an intended consequence, not a bug).

## Finding 2: pivot_suggestions / chalk_scores aren't wired into the frontend

**What was checked:** `ownership_heuristic.py` (Session 4.1) and
`pivot_finder.py` (Session 4.2) both run every slate and produce validated
output:
- `output/chalk_scores_{site}_{week}.csv`
- `output/pivot_suggestions_{site}_{week}.csv`

Checked the full `SESSION_LOG.md` for any reference to either file inside
the frontend work (Sessions 7.1, 7.2, 7.2c, 7.4, 7.5 — the "Lineup Room" /
"Build a Lineup" panel). Every mention of `pivot_suggestions`/`chalk_score`
in the log is from Session 4.1/4.2's own build-and-validate entries, not
frontend work. `dfs_optimizer_frontend/index.html` has no code path that
reads either file.

**Net effect:** these two scripts have been running and validating cleanly
every week, but the only way to see a pivot suggestion or a chalk score is
to open the CSV by hand. The UI — which is otherwise the one-stop shop for
building a lineup — doesn't show either.

**Note this finding is somewhat downstream of Finding 1** — there's an
argument for fixing the eligibility logic first (Finding 1) before wiring
possibly-bad suggestions more prominently into the UI (Finding 2). Worth
sequencing accordingly rather than doing the UI work first.

## Why this matters practically

The frontend's whole value is letting you go from "cash lineup" to "GPP
lineup" without leaving the page. Right now that loop is broken in two
ways: the suggestions themselves may be lower-quality than they should be
(Finding 1), and even the good ones require tabbing out to a spreadsheet
to see at all (Finding 2). That's the multi-source workflow you're trying
to avoid, compounded by a data-quality question underneath it.

## Recommended fix for Finding 2 (next available session, after Finding 1)

**Files touched:**
- `dfs_optimizer_frontend/index.html` (modified)
- No backend/script changes needed beyond Finding 1's fix — this is
  purely a "read one more CSV" frontend addition, same pattern as how
  `lineup_single_{site}_{week}.csv` is already displayed.

**Build:**
1. On loading/refreshing a cash lineup in the Lineup Room, also fetch that
   week/site's `chalk_scores_{site}_{week}.csv` and `pivot_suggestions_
   {site}_{week}.csv`.
2. In the player pool view, bake in `estimated_ownership_pct` per player
   (chalk_scores) — same as the ownership display already noted as a goal
   for NHL's Session 6.3 card.
3. For the displayed cash lineup specifically, add a pivot panel: for each
   rostered player, show their top 2–3 pivot candidates (name, salary,
   projection, estimated_ownership_pct, leverage_score) either inline
   (expand-on-click per roster row) or in a side panel that updates with
   the currently-displayed lineup.
4. One-click "apply pivot": clicking a suggested pivot swaps that player
   into the lineup being edited (reuses whatever lock/exclude mechanism
   Session 7.2's "Build a Lineup" panel already has for manual edits) —
   this is what actually closes the loop instead of just displaying data.
5. Handle the "file not found" case gracefully — if `pivot_suggestions_
   {site}_{week}.csv` doesn't exist yet for the selected week (e.g. Session
   4.2 hasn't run for a brand-new week), the panel should say so, not error.

**Validation:**
- Pivot panel data matches the CSV exactly for a real live week, both sites.
- Clicking "apply pivot" produces a lineup that still passes salary cap /
  position validation (reuse the existing lineup validator).
- Panel degrades cleanly when `pivot_suggestions_*.csv` is missing/stale.

**Handoff note for whoever picks this up:** this is the second time this
project has built a real analytical output (Session 4.1/4.2) that sat
unconnected to the UI. Worth a quick audit of whether any other `/output`
files (e.g. exposure logs from Session 9.3's actual-ownership logging) have
the same gap before closing this one out.
