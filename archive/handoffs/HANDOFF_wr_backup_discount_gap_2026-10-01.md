# HANDOFF -- WR/TE role-change gap: returning Questionable starter doesn't discount hot backup (found 2026-10-01)

Found while walking the Week 4 DK Classic SE3Max Pool build (HOU main slate). Not yet fixed -- this is a
writeup to pick up fresh, not a completed task.

## The symptom
In the Wk4 main-slate 100-lineup pool (`output/lineups_multi_dk_dk_classic_wk4_main_04Oct2026_ea0c6653...csv`,
built from `output/final_projections_dk_dk_classic_wk4_main_04Oct2026.csv`), the top-projected lineup rostered
Xavier Hutchinson (HOU WR2/3, $4,300) over the more natural play, with Nico Collins (HOU WR1, $7,200,
**QUESTIONABLE**, presumably active/probable) projected lower and barely owned. Our own optimizer plays
Hutchinson in 20% of the 100-lineup pool and Dalton Schultz (HOU TE/FLEX) in 32%, while the ownership model
pegs both under 6% real-field ownership -- internally inconsistent (our solver likes them, our ownership model
says the field won't touch them).

User's read, confirmed correct: Collins is "back" (active again after missing time), and the projection
doesn't properly reduce Hutchinson's inflated role now that the real starter has returned. Ownership looked
more trustworthy than the projection here, not the other way around.

## The data that confirms it
From `final_projections_dk_dk_classic_wk4_main_04Oct2026.csv`:

| | Nico Collins | Xavier Hutchinson |
|---|---|---|
| games_played (this season) | 1.0 | 3.0 |
| participation_effective | **0.3333** | 1.0 |
| season_avg | 10.1 (from that 1 game) | 7.4 |
| proj_targets | **3.29** | **5.80** |
| final_projection | 11.4 | 8.3 |
| injury_status | QUESTIONABLE | ACTIVE |
| role_change_injury_flag | False | False |

Collins missed most of the season (only 1 game played), Hutchinson started in his place for 3 games at full
weight. Collins is back this week but the model still gives Hutchinson more volume (5.8 vs 3.3 targets) than
the presumed-returning starter -- backwards from what a real-world read of "WR1 is back" would expect.

## Root cause (two separate, compounding things -- read both)

**1. WR target-vacating reallocation is deliberately off, and that's correct, not the bug.**
`apply_rb_replacement()` (RB) and `apply_te_replacement()` (TE) in `scripts/statline_model.py` redistribute a
hurt player's vacated carries/targets to the remaining players at that position. There is **no WR version**.
`apply_te_replacement()`'s own docstring (statline_model.py:2488) says explicitly: *"WR/RB bleed deliberately
0 -- it hurt held-out [testing]."* This was tested and rejected on 2016-25 backtests. So when Collins was
fully OUT, nothing artificially pushed his target share onto Hutchinson -- Hutchinson's bump is 100% organic,
from real snaps/targets in games he actually played as the starter. **This part is working as intended; do
not try to add a WR vacated-target mechanism without re-reading why it was rejected (`analysis/role_bump_chalk_gap/RESULTS.md`
has the TE version's backtest; the WR version's own rejection evidence should be found/reread before touching this).**

**2. The real gap: nothing discounts a hot backup once a Questionable-but-active starter returns.**
`scripts/statline_model.py` has two separate override blocks that adjust `participation_effective`:
- Lines ~1890-1936 (`confirmed_starter_flag` / `role_change_injury_flag`): boosts a confirmed starter from
  **exactly zero** participation back to 1.0 (a player who was fully out and is now playing), and separately
  boosts a backup of a starter who is OUT this week. Neither path applies to Collins -- his participation
  isn't zero (he's partially credited already), and he isn't a backup.
- Lines ~1939-1983 (`clean_starter_partial`): boosts a confirmed starter sitting at **partial** participation
  (not zero) back to 1.0 -- this is the one that *should* apply to Collins. But it explicitly requires
  `clean_injury_report` (every current `injury_status != "ACTIVE"` is excluded) -- see the comment at
  statline_model.py:1955-1965 explaining this was a deliberate choice (to not conflate a genuinely healthy
  returning starter with one still flagged on today's report). Collins is QUESTIONABLE, so he's excluded from
  this boost by design.

  The same comment block says a flagged player is "left to whatever partial credit the existing role-change
  override already gives him" -- **but that existing override only ever adds weight to a backup when the
  starter is OUT; it never reduces the backup's weight when the starter comes back, and it never applies to
  the starter himself in the Questionable case.** There is no lever anywhere in this pipeline that pulls a
  hot backup's trailing stats back down to reflect a returning-but-still-banged-up starter reclaiming snaps.

## What needs to happen (not done yet -- pick this up fresh)
1. Decide the right behavior for a confirmed starter who is QUESTIONABLE (not a clean report, not zero
   participation) but expected to play close to normal: does he get full participation, partial, or something
   in between? Today he gets neither the zero-to-full boost nor the partial-to-full boost -- he's stuck at
   whatever his own thin trailing sample says (which is 0.33 here, likely too low for a player who's actually
   playing this week).
2. Separately, decide whether/how a backup's (Hutchinson's) trailing-stat-driven projection should be
   discounted once the real starter is back and playing, even partially. This doesn't need to be the
   rejected WR-vacated-target mechanism from item 1 above -- it's a different direction (removing inflated
   recent-role weight from a backup), not redistributing a currently-out starter's share.
3. Check whether this same gap affects RB/TE too, or whether apply_rb_replacement/apply_te_replacement's
   OUT-only trigger has a similar blind spot for a Questionable-but-returning starter at those positions.
4. Before shipping anything: backtest the fix the same way the existing WR-rejection and TE-acceptance were
   tested (held-out 2016-25 by position, judged at the lineup level per [[project-dfs-two-track-philosophy]]
   standing principles, not just RMSE/Spearman).

## Why this matters beyond this one lineup
This is the kind of case the user flagged as a recurring pattern ("we seem to be missing this again" --
cheap, low-projected-ownership complementary pieces riding stale trailing stats). The ownership-model
undercounting issue from `HANDOFF_fc_history_ownership_findings_2026-09-26.md` is a separate, already-known,
already-parked issue (10-20% tier undercounted, $5.5-7k band undercounted) -- don't conflate the two. This
handoff is specifically about the **projection** side: a returning-starter participation gap with no backup
discount, confirmed via the Collins/Hutchinson data above, not a calibration guess.

## Files involved
- `scripts/statline_model.py` (the override blocks, ~lines 1860-1990; `apply_rb_replacement` ~2403;
  `apply_te_replacement` ~2486)
- `scripts/build_projections_statline.py` (`_apply_wrw_rb`/`_apply_wrw_te` call sites ~1118-1120)
- `output/final_projections_dk_dk_classic_wk4_main_04Oct2026.csv` (the real data used above -- Wk4 main slate,
  HOU @ DAL game, Collins/Hutchinson rows)
