# Showdown lineup-building rules (living doc)

Evidence base: **4 real DK Showdown slates** (DEN@KC, IND@KC, NYG@LAR, ATL@GB), 31,317 stored lineups in
`data/contest_results/`. Reproduce with `analysis/showdown_own/four_slate.py` (descriptive tables) and
`four_slate_reg.py` (logistic on top-10%, controlling for projection, sign-consistency per slate).
Four slates is tiny: **3-of-4 sign agreement is only weak evidence.** Update this file after every slate.

## Rules, by strength of evidence

**Supported (consistent across slates)**
1. **Highest projection wins.** The only factor with the same sign in 4/4 slates (~0.8-1.1 logit per SD).
   Do not trade real projection for contrarian structure without a specific reason.
2. **RB or WR at CPT.** Top-10% rates pooled: RB 13.9%, WR 11.4%, QB 8.9%, TE 4.7%, K/DST ~3%. Positive in
   3/4 slates each (RB failed NYG@LAR, WR failed DEN@KC). Greg's tiebreak when no clear captain: WR (PPR).
3. **Don't captain K, DST, or (usually) TE.** Negative in 2-3 of 4 slates.
4. **Cheap fill must be a real player** (a WR with a role, e.g. Dotson/Zaccheaus-type), not a $200-$1000
   punt with ~1-2 targets (Blair-type). Only spend the salary savings on a plausible role player.

**Weak / mixed (do not treat as rules)**
5. **Kicker:** the old "include a kicker" finding does NOT hold once projection is controlled (pooled ~0,
   2/4 slates). Kickers project ~8 for ~5k so the optimizer tends to include one anyway. Greg's preference:
   **at most one K** (two-kicker builds are a bet that the kicker score is high, not a supported edge).
6. **DST:** negative pooled (3/4 slates), dominated by one slate. Lean cheap-and-believable, or skip.
7. **Team split:** 5-1 looked best on the first 3 slates, then lost on ATL@GB. Not a rule. 4-2 and 3-3
   both fine. (Confounded with "favorite-heavy wins" -- needs a slate where the favorite loses.)
8. **Chalk CPT:** no clean fade. Very low-owned captains (<5%) did worst; 10-15% best; >15% mixed.

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
`--cpt-positions RB,WR` (restrict captain by position), `--max-kickers 1`. Existing `--exclude pid:CPT`
already does this by hand today. Too early to make any of these defaults.
