# SUBAGENT BRIEF — read this FIRST, before any task

You are working on a DFS (NFL DraftKings/FanDuel) optimizer for one owner. Your task prompt says WHAT to do; this file says
WHY and HOW. If the task prompt and this file seem to conflict, say so in your first lines instead of guessing.

## The goal (one sentence)
Make our projections, ownership model, and lineup construction measurably MORE ACCURATE — a top-tier usable product on par with
commercial tools (Fantasy Cruncher/FC, Stochastic) — so we cash consistently. We have missed every slate 3 weeks running in 2026.
That is a bad system, not bad luck; the owner cashes consistently using FC. Every task exists to find and fix a real accuracy gap.

## The data advantage — use it
We pulled ~5 seasons (2021-25, + 2026 wk1-3) of Fantasy Cruncher history for exactly this purpose: ownership labels, FC
projections, lineup-level data, 410 classic contests (`data/fc_history/`, `analysis/classic_history/`). History can answer most
questions with large n. FC is NOT a live input (subscription is dead) — history is training/teacher/comparison data only.
Some inputs do not exist historically (FFC ownership, injury news, props) — say plainly which questions history cannot settle.

**"History" = ALL five seasons, not 2026.** The main test frame is every season/week we have, with projections and
ownerships REBUILT with current code from the FC-data salaries (2021-25 all weeks), leave-one-season-out; 2026 Wk1-3 is only
the second check. Never scope a question to "2026 only / thin / wait for more weeks". Only truly 2026-only inputs (props,
live FFC ownership, injury news) are limited to 2026 — name which one, and test everything else on history. Using FC's
projections as a stand-in is a fallback, not the answer, when a current-code rebuild is possible. (Owner flagged this as
recurring, 2026-09-30.)

## How to work (owner's rules — non-negotiable)
1. **Restate the question first.** In your first lines, restate what you are testing in the owner's own terms. If the task prompt
   quotes the owner's premise, test THAT premise, not a paraphrase (a past run tested "min-price DST" when the premise was
   "cheapest VIABLE DST"). If unsure what is meant, say so — do not silently substitute.
2. **Head-to-head vs a commercial model.** Prefer "who is more accurate, by how much, where exactly, biggest misses, and WHY"
   over comparing our own variants to each other.
3. **No assumed causes.** If you claim a cause ("we lack news", "props not applied"), test it with data or label it a guess.
4. **No weeds, no over-analysis, no checklist-ticking.** Skip minor-consequence items. Depth on what moves accuracy.
5. **No "n too small, wait for more weeks"** where history can answer. Do state real confidence and sanity-check strong results
   (leakage, in-sample fits, artifacts of test setup — several "gaps" turned out to be test-engine artifacts).
6. **Two tracks.** Hard bar to SHIP; low bar to keep TESTING. Label results explicitly: ship / inconclusive-keep-testing /
   wrong-direction-drop. Inconclusive is not wrong.
7. **End with the single most valuable fixable thing**, plainly, with held-out numbers and an implementable wiring plan (file,
   function, parameters, off-switch). Plain language, no legalese, no excess hedging.
8. **Held-out or it did not happen.** Leave-one-season-out on history, then a check on 2026 wk1-3. Note which 2026 weeks are
   in-sample for live artifacts.

## Hygiene
- Never commit FC data or FC-derived results (`RESULTS.md` from FC analyses stays local). Never commit test rebuilds.
- Do not overwrite live artifacts or committed `output/` / `data/props`; write candidates to new dated files. Snapshot/restore
  `output/` and `data/props` if a test touches them.
- Do not commit anything unless the task says so. Put scripts + RESULTS.md in a new `analysis/<topic>/` folder.
- Prefer shipping behind an on/off switch (default per the task) with audit columns and a fail-safe no-op.

## Where context lives
`WK3_POSTMORTEM_CHECKLIST.md` (§4 outcomes), `WK3_ROOT_CAUSE_FINDINGS.md`, `SHOWDOWN_RULES.md`, `HANDOFF_*.md`,
`analysis/model_vs_fc/`, `analysis/ownership_v2/`, `analysis/projection_v2/`, `analysis/qb_depth/`, `analysis/inactives/`.
