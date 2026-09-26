# Showdown lineup-building rules (living doc)

Evidence base: **4 real DK Showdown slates** (DEN@KC, IND@KC, NYG@LAR, ATL@GB), 31,317 stored lineups in
`data/contest_results/`. Reproduce with `analysis/showdown_own/four_slate.py` (descriptive tables) and
`four_slate_reg.py` (logistic on top-10%, controlling for projection, sign-consistency per slate).
Four slates is tiny: **3-of-4 sign agreement is only weak evidence.** Update this file after every slate.

**Added 2026-09-26: 49 FC-history Showdown games, 2023-25** (player-level actuals + realized ownership; strategy results are vs a *simulated*
maximum-entropy field, which under-represents correlated stacks, so treat construction numbers as directional). Details, CIs and caveats:
`HANDOFF_showdown_history_findings_2026-09-26.md`. FC data is subscription data and never committed; only aggregates live in the repo.

## Rules, by strength of evidence

**Supported (consistent across slates)**
1. **Highest projection wins.** The only factor with the same sign in 4/4 slates (~0.8-1.1 logit per SD).
   Do not trade real projection for contrarian structure without a specific reason.
2. **RB or WR at CPT: NOT supported as a restriction (revised at n=49).** Hindsight-optimal captains: WR 39%, RB 29%, QB 18%, TE 12%, K/DST ~1%,
   about equal to the field's own shares. Forcing RB/WR CPT cost ~2 percentile pts on the #1 lineup (2025: -4.6, CI excludes 0); QB captain is legitimate.
   Keep Greg's WR tiebreak only when projections are close. (The 4-slate RB/WR result did not replicate.)
3. **Don't captain K or DST (Supported, n=49).** Optimal captain was DST 0/49, K 1/49, yet the field puts ~8% of captains on DST. TE captain is fine when
   projection supports it (12% of hindsight optima; 2025 5/18 is a sample-size flag, not a trend).
4. **Cheap fill must be a real player** (a WR with a role, e.g. Dotson/Zaccheaus-type), not a $200-$1000
   punt with ~1-2 targets (Blair-type). Only spend the salary savings on a plausible role player.

**Weak / mixed (do not treat as rules)**
5. **Kicker (now Supported as "avoid two"):** 2-K builds cost ~7.7 percentile pts (90% CI -13.7 to -1.5), only 4% of hindsight optima. The old "include a kicker" finding does NOT hold once projection is controlled (pooled ~0,
   2/4 slates). Kickers project ~8 for ~5k so the optimizer tends to include one anyway. Greg's preference:
   **at most one K** (two-kicker builds are a bet that the kicker score is high, not a supported edge).
6. **DST (Weak):** negative pooled on the 4 slates. At n=49 the pricier DST scores the same as the cheaper one (5.6 vs 5.4) for ~$1.1k more and ~4x CPT ownership; the hindsight optimum skips DST 78% of the time. Lean cheap-and-believable, or skip.
7. **Team split (Supported: avoid forcing 5-1):** forced 5-1 was -4.5 pctl on the top-20 average (CI -7.5 to -1.5); 4-2 is the modal optimal split (63%), 5-1 10% vs 16% of the field. 5-1 looked best on the first 3 real slates, then lost on ATL@GB. Not a rule to seek it. 4-2 and 3-3
   both fine. (Confounded with "favorite-heavy wins" -- needs a slate where the favorite loses.)
8. **Chalk CPT (Supported):** no clean fade (fading the chalk CPT -1.8 pctl, CI excludes 0; chalk CPT is optimal ~16%, about its ownership). Captains <5% owned did worst (-6.3 pctl #1 lineup); 5-15% fine.
9. **Top projection is over-projected (Weak, ~2 SE):** the #1 projected player per game scored ~3 pts below projection (opposite of classic stud under-projection). Don't let one stud's projection force the CPT; salary is about as predictive as FC Proj and a per-position blend helps ~2% MSE (kicker salary ranks kickers far better than FC).
10. **Ownership penalty: keep lambda 0 for Showdown SE/cash.** A flat leverage term cost 3-12 percentile pts in simulation, matching the classic finding.

## Mechanics / data hygiene
- CPT rows in `final_projections_*` **already carry the 1.5x**. Never multiply a CPT row again (this bit us
  once: inflated the "best lineup" by ~14 pts).
- One kicker per team plays. The build now projects only the highest-DK-avg kicker per team and zeroes the
  rest (`build_projections._build_kicker_projections`); if the projected kicker is OUT, `status_check apply`
  promotes the backup (`promote_backup_kickers`). Kickers are pulled from ESPN as `PK` (UNVERIFIED live as of
  2026-09-25 -- check the first Showdown status file for kicker rows). For anything the feed misses (a kicker,
  game-day inactives ~90 min pre-kickoff) add a row to `config/manual_status_overrides.csv`
  (`week,player_name,team,status,note`; only applies to that week's run).
- Optimizer exposure cap (40%) makes multi-lineup batches fall off a cliff on a 2-team slate (lineups 9-20 of a
  20-build were worth ~65 pts vs ~85 at the top). For a single entry, enumerate/rank directly or use a small N.
- Both teams must be represented (enforced). Per-row lock/exclude: `pid:CPT` / `pid:FLEX`.

## Not yet in the optimizer (candidate opt-in settings, NOT defaults, after 1-2 more slates)
`--max-kickers 1` (harmless), `--no-cpt-positions K,DST` (tiny +), `--max-team-players 4` (avoids 5-1; +3.8 pctl on the #1 lineup).
**Dropped:** `--cpt-positions RB,WR` (not supported at n=49). Existing `--exclude pid:CPT` does captain restriction by hand today. Do not make any of these defaults yet.
