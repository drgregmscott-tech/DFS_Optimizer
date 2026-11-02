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
