# Handoff: lineup-level (joint) ownership model

**Filed:** 2026-10-07, during the weekly check-in session.

**Status: DONE, 2026-10-07 — wrong-direction, drop.** An Opus agent ran this same day. Matched the
63 pools to real field lineups and measured joint ownership directly: the joint structure is real
(QB+WR rostered together 2.7x independence, QB+TE 2.5x, bring-backs 1.4x) but carries ~zero finish
signal beyond per-player ownership, even with perfect post-lock knowledge (+.129 vs item 15's
+.133 per-player ceiling). None of stack/pair-lift, chalk co-occurrence, or a lineup-level ridge
regression beat item 15's existing log-sum-of-per-player baseline (+.111) once held out properly.
No ship, no production code touched. One minor inconclusive thread ("field near-duplication
share", +.03-.05 post-lock only, +.004 held-out) — not worth chasing further right now. Full
writeup: `analysis/lineup_level_own_model/RESULTS.md` (gitignored, FC-derived).

The rest of this doc is kept as the original brief/evidence trail, for reference.

## The gap, in one line
Our ownership model is accurate per-player (~0.8 corr) but has ~zero signal at the lineup-sum
level once projection is held fixed. Real post-lock ownership has +0.13 partial correlation with
lineup finish (controlling for projection); ours has ~0. That gap is the ceiling this item chases.

## Where the evidence lives
- `analysis/lineup_own_signal/RESULTS.md` (local, gitignored, FC-derived) — the full writeup.
  Covers all 63 built history SE3max pools (2022-25 x 3 projection arms), re-graded from
  `hist_meta`, plus 18 live-settings 2026 pools.
- `analysis/lineup_replay/hist_lineups_graded.csv`, `analysis/lineup_replay/hist_meta/*.npz`,
  `analysis/lineup_replay/builds/hist/{new,old,fc}/` — the already-graded history pools to
  train/test against (NOT under `analysis/lineup_own_signal/` — that folder only has the
  derived `slots.csv`/`players.csv` built from these by `load.py`). No new data pull needed.
- `analysis/classic_rerank/RESULTS.md` — item 12's original framing of the same gap, plus the
  re-rank test that proved the *lever* (picking by a lineup-sum ownership score) is worth ~+0.10
  percentile per pick once ownership is accurate enough at that level. That part already shipped
  (`_rank_lineups_by_proj_own` in `scripts/optimizer.py`, env `DFS_RANK_OWN_W`, default 0.75) —
  this item is about improving the *signal that feeds it*, not the re-rank mechanism itself.

## What's already been tried and ruled out (don't re-run these)
- Ranking by modeled-ownership-sum alone: wrong-direction.
- Simple re-rank blends (projection + ownership-sum, various weights): inconclusive, ~0 net on
  history, noisy on 2026.
- Confirmed this isn't a stale-model artifact for the *re-rank* test (item 15 found the 09-29
  pools carried pre-v2 ownership; re-scored with v2 the partial corr goes from -.04 to +.08/+.11 —
  real, not a fit artifact, matches held-out LOSO almost exactly).

## The actual next step (not yet attempted)
Train/score ownership **at the lineup-sum level**, not just per-player summed after the fact.
Today's model predicts each player's ownership independently and the lineup-sum signal is just
whatever falls out of adding those predictions up. The hypothesis is that real field behavior has
lineup-level structure (correlated/joint ownership choices — e.g. stacking a chalk QB WITH a chalk
WR more than independent per-player ownership would predict) that a per-player model can't capture
no matter how accurate it gets per-player.

Concrete angle to start with: on the 63 graded history pools, fit a model (or even a simple
engineered feature) that predicts lineup-sum ownership directly from lineup-level features
(stack composition, correlated-player co-occurrence, chalk-count, etc.) rather than summing
per-player predictions — then check whether its partial corr with real finish (controlling for
projection) beats the current ~0 and approaches real ownership's +0.13-0.18.

## Scope note
This is a real model-build task, not a quick lever flip — budget it as its own session (or Opus
agent session per [[feedback_opus_for_heavy_work]]). Use the existing graded history data; no new
pull or waiting on Week 5 needed to start.

## Session discipline reminder
One topic per session. If this surfaces tangents (e.g. showdown-specific joint ownership, or the
FFC-dependency question), park them — see [[feedback_session_focus_parking_lot]].
