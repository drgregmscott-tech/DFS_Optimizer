# Showdown lineup-building rules (living doc)

Evidence base: **4 real DK Showdown slates** (DEN@KC, IND@KC, NYG@LAR, ATL@GB), 31,317 stored lineups in
`data/contest_results/`. Reproduce with `analysis/showdown_own/four_slate.py` (descriptive tables) and
`four_slate_reg.py` (logistic on top-10%, controlling for projection, sign-consistency per slate).
Four slates is tiny: **3-of-4 sign agreement is only weak evidence.** Update this file after every slate.

**Added 2026-09-26: 49 FC-history Showdown games, 2023-25** (player-level actuals + realized ownership; strategy results are vs a *simulated*
maximum-entropy field, which under-represents correlated stacks, so treat construction numbers as directional). Details, CIs and caveats:
`HANDOFF_showdown_history_findings_2026-09-26.md`. FC data is subscription data and never committed; only aggregates live in the repo.

**Added 2026-09-28: 142 REAL DK Showdown contests, 2022-26 (14.9M entries — actual lineups, actual payouts, not a simulated field).**
This is the strongest evidence in this file; it directly replaces the simulated-field construction conclusions above where they conflict.
Details: `HANDOFF_showdown_lineupstudy_findings_2026-09-28.md` (real-field cash lift/return, rule-by-rule verdicts) and
`HANDOFF_showdown_construction_detail_2026-09-28.md` (captain/partner position pairing, stack depth, punt-price granularity, split-side detail,
plus the projection-controlled re-check of the QB-partner finding and the pre-lock-ownership re-test of the chalk-tilt finding). **Five of these
findings are now live in the optimizer**, not just documented — see "Optimizer enforcement" below.

## Optimizer enforcement (2026-09-28)

Five real-field-Supported construction rules are wired into `solve_showdown_lineup()` as actual ILP constraints/objective terms (`--sd-*` flags,
see their `--help` text and the docstring on `solve_showdown_lineup()` for the exact mechanism), bundled into two new presets so building a
lineup doesn't require remembering five separate flags: **`--preset showdown_se`** (Huddle/single-entry) and **`--preset showdown_gpp`**
(150-max big-field GPP / MME). The split exists because several of these differ in strength between the two contest types — averaging them
into one preset would have diluted the stronger big-GPP evidence. See `data/optimizer_presets.json`'s own comments for the exact per-preset
values and their evidence basis.

1. **`--sd-require-cpt-qb` (hard constraint, on in both presets).** A WR/TE captain with no same-team QB in the FLEX is disallowed outright
   (only gates WR/TE captains; RB/QB captains untouched). This is the strongest, cleanest finding in the whole study (-7.6 to -7.7 cash pts,
   0.60-0.69x return, both contest types).
2. **`--sd-cheap-tier-penalty` over `--sd-cheap-tier-range` (soft, default $600-1000).** That price band underperforms a genuine <=$500 punt.
   Weighted higher in `showdown_gpp` (Supported, 4/4 seasons) than `showdown_se` (Weak-to-Supported).
3. **`--sd-stack-cap` / `--sd-stack-cap-penalty` (soft).** Penalizes same-team FLEX count (relative to the solved captain's team) beyond the
   cap. QB captains specifically do best at 1-2 teammates, not 3-4; deep stacks are flat-to-negative for every skill captain. Weak-to-Supported,
   same weight in both presets.
4. **`--sd-qb-partner-bonus` (soft reward).** Rewards same-team RB/TE FLEX players only when the solved captain is a QB — a QB captain's RB or
   TE beats his WR1 as primary partner, even after controlling for the partner's own projection and salary (the confound flagged when this was
   first found). Weighted higher in `showdown_gpp` (Supported both positions) than `showdown_se` (Supported for TE, Weak for RB).
5. **Lambda stays 0 in both presets — NOT wired to any new lever.** The realized-ownership chalk-tilt edge (+0.44 capped-return gap, most- vs
   least-owned quintile, big GPP) looked like a real, actionable finding, but a follow-up re-test substituting OUR modeled pre-lock ownership
   for that hindsight ownership collapsed it to noise (+0.08, CI crosses 0) — our Showdown ownership model only correlates 0.56 with what the
   real field does, so it mostly just re-encodes projection rather than capturing what the crowd knows. This is a genuinely dead end until the
   ownership model itself improves, not an unvalidated-but-promising idea sitting on a shelf.

These `--sd-*` weights are first-pass point-scale conversions of the study's cash-lift/return findings, not a backtested-swept calibration like
`--lambda`'s own grid (Session 10.5b). Treat them as a starting point to validate against real Wk4+ Showdown results, same as any other track-2
item — see `data/optimizer_presets.json`'s per-preset comments for exactly which weight rests on which strength of evidence.

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
5. **Kicker — WEAKENED at n=142 real contests (was Supported).** Simulated field said -7.7 pctl for 2 kickers; the real field says ~-1 to -1.5
   cash pts with the CI spanning 0 in both contest types. Keep "at most one K" as a harmless preference, not an evidence-backed rule.
6. **DST (Weak, confirmed direction at n=142):** the expensive DST is -2.0 to -2.4 cash pts (4/4, 3/4 seasons), return 0.86-0.91x, for the same
   points as the cheap one. No DST at all is mildly positive in SE (+1.3, CI touches 0). Lean cheap-and-believable, or skip.
7. **Team split — WEAKENED at n=142 real contests (was Supported as "avoid forcing 5-1").** Real 5-1 is no worse than 4-2 (both mildly negative,
   CI spans 0 for 5-1). The specific thing that IS mildly bad (Supported, -1.2 to -1.6 cash pts) is a **4-2 split with the CPT's own team on the
   heavy side** — 3-3 is the best split on average. The simulated-field -4.5 pctl penalty on 5-1 specifically was a field artifact, not real.
   **Dropped:** the `--max-team-players 4` candidate that existed to enforce this — it has no evidence base left.
8. **Chalk CPT — refined by contest type at n=142.** Big GPP: Supported, avoid <5%-owned captains (-3.0 cash, 4/4 seasons); >=15%-owned is
   fine (+2.6). **SE: different shape** — the #1 chalk captain specifically under-returns (0.89x return, top-1% lift -0.37 CI excludes 0), and
   5-15%-owned is the sweet spot (return 1.14x). Don't fade chalk broadly in either format; in SE specifically don't force the single most-owned
   captain either.
9. **Top projection is over-projected (Weak, ~2 SE, simulated-field only — not re-tested on real contests).** the #1 projected player per game
   scored ~3 pts below projection (opposite of classic stud under-projection). Don't let one stud's projection force the CPT; salary is about as
   predictive as FC Proj and a per-position blend helps ~2% MSE (kicker salary ranks kickers far better than FC).
10. **Ownership penalty: keep lambda 0 for Showdown, both SE and GPP — CONFIRMED twice at n=142 real contests.** The simulated-field finding
    held on the real field with realized/hindsight ownership (a genuine chalk edge exists after lock), but died when re-tested with our own
    modeled pre-lock ownership (gap collapses from +0.44 to +0.08, CI crosses 0 — our model only correlates 0.56 with the real field). Not
    actionable pre-lock until the ownership model itself improves. See "Optimizer enforcement" above.
11. **NEW (Supported, n=142): a QB captain's RB or TE beats his WR1 as primary partner**, even controlling for the partner's own projection and
    salary. See "Optimizer enforcement" item 4 — this is live via `--sd-qb-partner-bonus`.
12. **NEW (Weak-to-Supported, n=142): the $600-1k FLEX price tier underperforms a genuine <=$500 punt.** See "Optimizer enforcement" item 2 —
    live via `--sd-cheap-tier-penalty`.
13. **NEW (Supported, n=142): a WR/TE captain needs his own team's QB in the FLEX**, sharper than rule 2's original "keep it in mind" framing —
    a WR/TE captain paired with another same-team WR/TE and no QB is the single worst skill build found. See "Optimizer enforcement" item 1 —
    this one is a hard constraint, not just a preference.

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

## Not yet in the optimizer (candidate opt-in settings, no evidence base yet or not worth the complexity)
`--max-kickers 1` (harmless, no real edge at n=142 — see rule 5), `--no-cpt-positions K,DST` (rule 3's DST-captain exclusion is now handled by
`--sd-require-cpt-qb`'s effect on WR/TE captains plus manual `--exclude pid:CPT` for K/DST; a dedicated flag hasn't been built since the
existing exclude mechanism already covers it).
**Dropped, no evidence base left:** `--max-team-players 4` (was meant to enforce "avoid 5-1" — see rule 7, real contests show no 5-1-specific
penalty) and `--cpt-positions RB,WR` (not supported at either n=49 or n=142). Existing `--exclude pid:CPT` does manual captain restriction today.

## What's live vs. what's still just a documented preference
As of 2026-09-28, rules 1 (require CPT's own QB — hard), 6 (cheap-tier penalty), the QB-stack-depth cap, and 11 (QB+RB/TE partner bonus) are
enforced in the optimizer via `--preset showdown_se` / `--preset showdown_gpp` (see "Optimizer enforcement" above) — building a lineup with
one of those presets applies them automatically, no per-rule flag to remember. Every other numbered rule above (2, 3's TE/K parts, 4, 5, 7-10,
12) is informational only — nothing in the build pipeline currently checks or warns on them. That gap (a rule can be "Supported" here and still
silently ignored at build time) is a known, separate problem — see the WK3 postmortem's construction-rule-capture discussion.
