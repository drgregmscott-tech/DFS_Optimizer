# DFS Optimizer — project notes for Claude

**Weekly pipeline SOP:** [DFS_Weekly_Process.md](DFS_Weekly_Process.md) is the standing step-by-step process
for taking a slate from DK/FD posting through locked lineups to the weekly postmortem. Read it before
doing pipeline work (building projections, logging ownership/results, running a postmortem) in a session
that hasn't already seen it this conversation.

**Starting a weekly postmortem:** always open with Stage 8 in `DFS_Weekly_Process.md` — run
`python scripts/check_weekly_logging_gap.py` first, before any accuracy/construction analysis. It catches
a silently-stopped manual logging step (Stage 6/7) before it compounds across multiple weeks (see
`WK8_POSTMORTEM_CHECKLIST.md` Item E, 2026-11-02, for what happens when it isn't checked). Postmortems
happen every week, win or lose, one topic per dedicated session — see any `WK*_POSTMORTEM_CHECKLIST.md`
for the established format.

## Known gotchas (repeat mistakes this has caused before — check before you trust an assumption)

- **User's real stack is QB+1, no bring-back.** He overrides the optimizer preset's default stack size via
  the CLI on every real build. Don't assume whatever a preset or script default says about stacking —
  verify against the actual CLI invocation before drawing conclusions from a stacking-related analysis.
- **"History" means all 5 real NFL seasons (2021-2025), not just 2026.** 2026 alone is thin and should be
  treated as a secondary check, not the primary dataset, for any accuracy/backtest claim.
- **Never commit Fantasy Cruncher (FC) data.** `data/fc_history/` and similar FC-derived files are local-only,
  subscription-gated data — do not add them to git.
- **Don't fabricate or estimate FanDuel ownership.** FD has no real post-lock ownership export; nothing
  legitimate exists to derive it from. `data/ownership_actual_log.csv` staying DK-only is the correct,
  documented state, not a bug to fix.
- **User is in US Central Time.** Convert UTC or date-only timestamps to CT before judging whether a game
  or lock has passed.
