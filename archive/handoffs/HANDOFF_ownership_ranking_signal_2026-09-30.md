# Handoff: ownership chalk is a ranking miss, not a sizing miss (2026-09-30)

## Where this comes from

Item 7 in `WK3_POSTMORTEM_OPEN.md` is now closed. Read that entry first for the full chain. Short version:
we spent this session testing whether the $7k+ ownership gap could be fixed by (a) stud-specific features,
(b) pulling chalk toward raw FFC, or (c) sharpening/concentrating each position group's distribution. All
three failed on real held-out evidence (2021-25 history LOSO and/or 2026 wk1-3 real DK ownership from
`data/ownership_actual_log.csv`), and the failure mode was the same every time: **our model's top-ranked
players in each group aren't the players who actually become chalk.** Sharpening or resizing the tiers we
already have right does nothing for the 60-65% of real 20%+/30%+-owned players who were never in our top
tier to begin with. That's why correlation gets *worse* every time we try to make the top bigger — we're
making the wrong players bigger.

## What this means for the next session

The open question is no longer "how big should chalk be" (closed, that's not the lever) — it's **"what
signal tells us *which* players the field will pile onto that our model currently ranks too low."** This is
a genuinely different test than the killed stud-feature study: that study tested role/vacated/Vegas/price
as *size* adjustments layered on top of an already-ranked prediction. Nobody has tested whether those same
inputs (or others) improve the **ranking/classification** of who ends up in the real top 10-20% at all —
i.e., does adding a feature move the *right* players into our model's predicted top tier, not just resize
the tier we already have.

## Concretely, where to start

1. Restate this premise yourself before testing anything (standing project rule) — confirm "a ranking
   problem, not a sizing problem" is actually what the data supports before building on top of it.
2. Pull the real top-20%/30% owned players from `data/ownership_actual_log.csv` (2026 wk1-3) and from the FC
   history frame (2021-25, same frame `analysis/stud_ownership/` and `analysis/cheap_wrte_ownership/` used —
   check those scripts for how to load it). For each, check: **is that player in our model's predicted top
   tier at all**, regardless of the predicted size. That's the metric to move — not bias, not MAE, but
   "recall of the real top tier" (are they in our own top-N, y/n) before worrying about how big we make them.
3. Candidate signals to test as *ranking* inputs (not size multipliers): the same ones already tried and
   killed as size features (role/vacated usage, Vegas team/game totals, price tier, recent-week
   ownership/chalk momentum, points-per-dollar) — but scored on rank-recall, not bias/MAE. Also worth trying
   fresh: recent target-share/usage trend (not just a single-week vacated-usage snapshot), "slate
   uniqueness" (is this player the only viable option at their price/position on this slate), and public
   narrative signals if any exist in this pipeline (last-week breakout, name recognition).
4. Same evidence bar as the rest of this postmortem: leave-one-season-out on history first (cheap to test,
   5 real seasons), then a live 2026 wk1-3 leave-one-week-out check. Don't ship on history alone if FFC/live
   inputs aren't available in that candidate — same caveat that sank the temperature candidate on live data.
5. Write it up the same way as the other four: `analysis/<name>/RESULTS.md`, `DO NOT COMMIT` marker only if
   the file embeds FC-derived aggregate numbers, gitignored player-level data under
   `data/fc_history/derived/`.

## What NOT to re-test

- Stud-specific features as **size** adjustments — killed, `analysis/stud_ownership/RESULTS.md`.
- Pull-toward-FFC resizing — inconclusive/net-negative on the target tier, `analysis/chalk_size_fix/RESULTS.md`.
- Group-distribution sharpening/temperature — killed, `analysis/chalk_temperature/RESULTS.md`.
- The dead FC projected-Own benchmark — already retired project-wide, grade everything against real DK
  ownership only.

## Files from this session (committed, inert by default)

- `scripts/ownership_v2.py`: adds `apply_chalk_ffc`/`DFS_OWN_CHALK_FFC` and
  `apply_chalk_temp`/`DFS_OWN_CHALK_TEMP`, both default-off, both no-op unless explicitly enabled. Safe to
  leave as-is or repurpose if a future ranking fix wants a similar post-hoc adjustment hook.
- `analysis/chalk_size_fix/`, `analysis/chalk_temperature/` — full writeups and test scripts for the two
  killed/inconclusive sizing candidates.
- `analysis/stud_ownership/RESULTS.md` — untracked (DO NOT COMMIT), still on disk in this checkout if you
  need the $7k+ history tables; regenerate via its script if it's gone.
