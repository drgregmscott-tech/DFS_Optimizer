# Handoff: reducing reliance on FFC public ownership data

**Filed:** 2026-10-07, during the weekly check-in session. Not started yet. Does not depend on
Week 5 results — the whole point is to test against the 5-year history, most of which never had
FFC in the first place.

## The gap, in one line
Our best ownership accuracy gains (chalk-size fix, chalk-FFC QB cut, etc.) lean on FFC's public
ownership projections as an input signal. FFC only exists for 2026 live slates with a pull — most
of the 5-year history (2021-25) and plenty of real weeks have no FFC equivalent. On those slates
we're flying on fewer signals, which caps how much the FFC-era improvements actually travel.

## Where the evidence lives
- `WK4_POSTMORTEM_CHECKLIST.md` item 1 — background on how much FFC currently buys us: "FFC
  ownership disagreements are genuine wrongness, not staleness... when FFC and our model disagree
  with FFC higher, we win ~3:1." That's the baseline to beat/match without FFC.
- `scripts/ownership_v2.py` — where `apply_chalk_ffc_seg` and the QB top-3-FFC cut
  (`DFS_OWN_CHALK_QB_CUT`) live today. Both are FFC-dependent corrections.
- `reference_free_dfs_data_sites.md` (memory) — other free DFS data sources (DFF, Fantasy Life,
  WinWithOdds, LineStar) that were scouted but never evaluated as FFC substitutes/supplements.
  Worth revisiting here specifically.
- 5-year FC history (the usual `analysis/*` gitignored pulls) — this is the test bed. Most of it
  has NO FFC column, which is exactly the "what do we do without it" population to validate against.

## The actual question to answer
On slates/history where FFC doesn't exist, what's the best achievable ownership accuracy using
only signals we always have (our own projection stack, salary, vegas lines, chalk patterns from
in-sample history, etc.)? Two sub-questions:
1. How much of the FFC-era accuracy gain (classic ownership corr .69→.89) is actually attributable
   to FFC itself vs. the other v2 model improvements that shipped alongside it (chalk-size fix v2,
   segmented correction, etc.)? Some of those non-FFC improvements may already be doing more of the
   work than FFC gets credit for — worth isolating before assuming FFC is irreplaceable.
2. Is there a free/cheap alternative public-ownership-style signal (the other sites in
   [[reference_free_dfs_data_sites]]) that could stand in on non-FFC slates, even partially?

## Scope note
This is a research/diagnostic session first (isolate what FFC is actually buying us on the slates
that have it, using history as the no-FFC control group), before any build decision. Don't start
by building a new data pull — start by quantifying the gap with what's already in hand.

## Session discipline reminder
One topic per session — this is a different question from the lineup-level ownership model
([[HANDOFF_lineup_level_ownership_2026-10-07]]), even though both are "ownership accuracy." Keep
them in separate sessions.
