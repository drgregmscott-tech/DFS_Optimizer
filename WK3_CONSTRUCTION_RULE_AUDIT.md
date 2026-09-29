# WK3 construction-rule capture audit (2026-09-29)

Scope: the `WK3_POSTMORTEM_CHECKLIST.md` parking-lot item "[2026-09-29] Partial construction-rule-capture gap".
This is an audit and design doc. The only code added is a read-only lint script, `scripts/construction_lint.py`
(see §4). No optimizer, preset, or pipeline behavior changed.

Tier definitions used throughout:
- **Enforced**: a hard ILP constraint or a soft objective term that runs by default or through a preset.
- **Soft-warned**: something in the pipeline flags it before lock without blocking it. **Before this session, nothing
  was in this tier for either format.** The only pre-lock warnings that existed were the partial-build banner and
  infeasibility errors, and neither is a construction-rule check.
- **Informational-only**: written down in a doc, and nothing in the pipeline reads it.

---

## 1. Inventory

### 1a. Showdown (`SHOWDOWN_RULES.md` rules 1-13, "Optimizer enforcement", and mechanics)

| # | Rule | Evidence | Tier before audit | Mechanism / note |
|---|---|---|---|---|
| 1 | Highest projection wins | Supported (4/4) | Enforced | This is the ILP objective itself |
| 2 | RB/WR-only CPT restriction | Not supported (dropped) | n/a, correctly absent | QB CPT is legitimate |
| 3a | No DST captain | Supported (n=49) | Enforced (preset) | `sd-exclude-cpt-positions DST`, hard |
| 3b | No K captain | Weak (1/49) | Enforced (preset, soft) | `sd-k-cpt-penalty` |
| 3c | TE captain fine when projection supports it | Supported | n/a | No restriction needed |
| 4 | Cheap fill must be a real role player, not a 1-2 target punt | Supported (4-slate + n=142 via rule 12) | Partly enforced | The $600-1k band is covered by rule 12. "Role player" itself is informational: no role/target feature is checked |
| 5 | At most one kicker | Weak (CI spans 0) | Informational | Candidate `--max-kickers 1` was never built |
| 6 | Lean cheap DST over the expensive one | Weak, direction confirmed (-2.0 to -2.4 cash) | Informational | |
| 7 | Avoid a 4-2 split with the CPT's team on the heavy side; 3-3 is best | Supported, mild (-1.2 to -1.6) | Informational | `--max-team-players 4` was dropped |
| 8a | GPP: avoid CPTs owned under 5% | Supported on realized ownership | Informational | Pre-lock ownership corr is only 0.56 (see 10) |
| 8b | SE: don't force the single most-owned CPT; 5-15% owned is the sweet spot | Supported on realized ownership | Informational | Same ownership caveat |
| 9 | Top projection is over-projected; don't let one stud force the CPT | Weak (simulated field only) | Informational | Continuous; it's a projection-calibration issue |
| 10 | Lambda 0 | Confirmed | Enforced (preset) | `lambda: 0` in both presets |
| 11 | A QB CPT's RB/TE partner beats his WR1 | Supported | Enforced (preset, soft) | `sd-qb-partner-bonus` |
| 12 | The $600-1k FLEX tier underperforms a <=$500 punt | Weak-to-Supported (SE) / Supported (GPP) | Enforced (preset, soft) | `sd-cheap-tier-penalty` |
| 13 | A WR/TE CPT needs his own QB in the FLEX | Supported | Enforced (preset, hard) | `sd-require-cpt-qb` |
| E3 | QB CPT with 1-2 teammates, not 3-4 | Weak-to-Supported | Enforced (preset, soft) | `sd-stack-cap`/`-penalty` |
| M | Both teams represented; CPT row already carries 1.5x | Structural | Enforced (always) | Hard constraint and data hygiene |
| M | Cap exposure on 2-team slates | Mechanic | Informational | Advice to use a small N for SE |

**Showdown count** (substantive rules, excluding the dropped rule 2, rule 3c which needs no restriction, and hygiene
items): **8 enforced** (1, 3a, 3b, 10, 11, 12, 13, E3). **1 partial** (4). **0 soft-warned.** **5 informational**
(5, 6, 7, 8a/8b counted as one, 9).

Note: `SHOWDOWN_RULES.md`'s own "What's live" paragraph (line 111-114) lists 3's K part and rule 12 as informational.
That is stale. The 2026-09-29 preset update enforces K-CPT through `sd-k-cpt-penalty` and rule 12 through
`sd-cheap-tier-penalty`. The paragraph also mislabels the cheap-tier rule as "6" (it is 12). That doc needs a
one-line fix; I did not change it here because it's outside this item's output scope.

### 1b. Classic (scattered across docs, code, and presets)

| Rule / finding | Source | Evidence | Tier before audit | Mechanism / note |
|---|---|---|---|---|
| Don't roster a skill player against your own DST | Decision #56, `optimizer.py:1217-1290` | Design decision (cost Panthers DST in wk2) | Enforced (default-on hard) | `--allow-skill-vs-opp-dst` turns it off |
| QB stack in every GPP build | Replay handoff §4, WK2 ("table stakes") | Supported (85-96% of the real field) | Enforced (preset) | `stack-mode qb` in se_gpp/mme/se3max |
| Stack size 2 (QB+2) | Replay handoff §4 (recommended); Phase 2 Step 2 (+3.7/+6.7pt field lift); **WK2 says "stack size 2 worse"** | Conflicting, directional | Enforced in se3max_pool only (`stack-size 2`); se_gpp and mme_gpp stay at 1 | MME at 0/40 QB+2 is the Phase 2 finding; checklist §5 item |
| Bring-back | Replay handoff (recommend); WK2 ("neutral") | Mixed | Enforced (preset) | `bring-back: true` in all GPP presets |
| Lambda 0 for cash/SE | 88-slate replay | Supported | Enforced (preset) | |
| Dart exposure cap (MME) | A6 heuristic (Kevin Austin) | Heuristic, not swept | Enforced (mme preset) | |
| Participation floors / backup-QB guard | Session 15 | Design | Enforced | Classic only |
| Don't add a min-total-ownership floor | Replay handoff §4 | Supported (negative result) | n/a, correctly absent | |
| Ownership leverage penalty doesn't help | WK2 | Supported (negative result) | n/a, correctly absent | |
| TE in FLEX (12% -> 29% top 1%) | WK2, replay handoff | Weak / case by case | Informational | User unclicks it manually |
| SE "exclude proj <= 7" filter looked harmful | WK2 | Weak (5/6, driven by one slate) | Informational | Filter is a manual UI setting |
| Pay less at QB (ours $6.3-6.7k vs cashing field ~$5.85k) | Phase 2 Step 2, Step 4e | Directional, 3 weeks | Informational | Routed to pick-up plan step D |
| At least one punt (<= $4k non-DST) in SE; 0 punts is -8.9pt | Phase 2 Step 2 | Directional (real field, our n=9) | Informational | |
| MME stack-depth mix (some share QB+2) | Phase 2, checklist §5 | Directional | Informational | Needs a new setting |
| No 2 same-team WR/TE without their QB | Checklist §5 | User preference, untested | Informational | |
| Prefer afternoon players in FLEX | Checklist §5 | Preference, rationale not written | Informational | |
| DST at 5-25% ownership facing a low implied total | Replay handoff §2 | Weak (pooled diagnostic) | Informational | Ownership-dependent |
| Game/team targeting (predict the right game) | WK2 | Biggest lever; no working predictor | Informational | Not a checkable rule |
| Fade the single most-owned CPT (classic n/a) | — | — | — | Showdown only |
| **Strong-projection cash drivers rostered 1/18 vs 39/86** | Root-cause 4d | Supported (p=0.001) as a gap; no rule exists | Informational | See §3. This is a finding, not a rule |
| "Conviction gap" (model vs crowd) | Replay handoff §5 | Idea, untested | Informational | |

**Classic count** (substantive rows, excluding the two negative-result "correctly absent" rows): **7 enforced**
(skill-vs-DST, QB stack, bring-back, lambda, dart cap, participation floors, and stack-size 2 in se3max_pool only).
**0 soft-warned.** **11 informational.** Classic has no rules doc, so these rows only exist as prose in 5+ files.

**Totals: 15 enforced, 1 partial, 0 soft-warned, 16 informational.**

---

## 2. Decision process: which tier does a finding belong in?

Score each finding on four questions, in order. The first "no" sets the ceiling.

1. **Is it a rule at all?** It has to be a condition you can evaluate on one lineup, using only pre-lock data. If
   the answer is "it's a continuous signal about which players are good" (projection z, conviction gap, rule 9),
   then it isn't a construction rule. It belongs in projections or selection, and no lint can capture it. →
   **route to model/selection work, not this ladder.**
2. **Evidence strength.** Supported on real contests (CIs exclude 0 and signs are consistent across
   seasons/slates) → hard is eligible. Weak-to-Supported, or directional on real fields → soft at most. Weak,
   conflicting, a preference, or valid only in hindsight (realized ownership) → lint only.
3. **Is there a legitimate exception the optimizer can't see?** Injury news, a thin slate, a deliberate leverage
   call, a user lock. If exceptions are plausible and a false positive is costly (it removes the best lineup),
   cap at **soft**. If false positives are nearly free (the rule targets a clearly bad build with close
   substitutes), keep **hard**.
4. **Does it depend on a weakly-modeled input** (pre-lock ownership, corr 0.56)? If so, cap at **lint**, whatever
   evidence (2) says, because that evidence was measured on data we don't have at build time.

Then: **Hard** = Supported + binary + no legitimate exception + cheap false positive. **Soft term** = Supported
or Weak-to-Supported + an effect size that converts to points + some exceptions. **Lint (soft-warned)** = anything
else that passes Q1. Every documented rule that passes Q1 should be at least lint, never informational-only. That
default is the missing piece. **Informational-only becomes a temporary state, not a tier.**

**Sanity check against the existing Showdown decisions:**
- Rule 13 → hard ✔ (Supported, binary, a same-team WR/TE swap is always available). Reproduced.
- DST CPT → hard, K CPT → soft ✔ (Supported vs Weak). Reproduced.
- Rules 11, 12, E3 → soft ✔ (Weak-to-Supported or contest-dependent, effect sizes convert to points). Reproduced.
- Lambda 0 → falls under Q4 ✔. Reproduced.
- Rule 7 (4-2 CPT-heavy) → Supported but mild, binary, with a real exception (a one-sided game script) →
  **soft term eligible**, currently lint. It's the one place the rule says to go further than current practice.
- Rules 5, 6 → Weak → lint. Rule 8 → realized-ownership evidence, so Q4 caps it at lint. Rule 9 → fails Q1.
- Classic: skill-vs-own-DST is hard but only has design-decision evidence. The Panthers wk2 case is exactly the
  "legitimate exception, costly false positive" profile, so the rule would call it **soft**. This is the one
  contradiction with current practice. Flag it for review; don't change it here.
- Classic stack-size 2: conflicting evidence (WK2 vs replay/Phase 2) → the rule says soft or lint. The preset
  hard-codes it in se3max_pool. That's defensible because se3max_pool is a replay-matched setting, but note the
  conflict.

---

## 3. Same failure mode?

**Partly. There are two different failures, and they share one upstream cause.**

- **Showdown gap: a discrete, checkable rule gets documented, and there's no default path from the doc to the
  build.** Rules 5-8 can each be decided from the lineup CSV (plus pool ownership). The fix is mechanical: a lint,
  or a soft term. Classic has the same failure, and it's worse: 11 informational rows and no rules doc at all, so
  a finding like "0 punts -8.9pt" or "MME is always QB+1" only lives in postmortem prose. **Showdown and classic
  construction rules are the same failure mode.** Evidence: in both formats, soft-warned was empty before this
  session, and every rule enforced so far got enforced because a specific session happened to check it (the
  21% K/DST captain catch, the QB-lock trap). No standing process turns a doc line into a check.
- **Classic 4d gap (1/18 vs 39/86): a different problem.** This isn't a violated rule. It's a continuous signal
  (projection z) that is already the optimizer's objective, yet it still doesn't show up in the submitted lineup.
  No lint can check "you didn't roster the player who's about to cash." 4d itself names the likely causes:
  construction settings, pool review, or manual picks, all downstream of the objective. So it fails Q1 of §2.
  It's a selection/legibility problem: the signal is present in the pool but gets diluted by stack constraints,
  exposure caps, randomization, and the pick-one-from-100 step. The 4d-2 counts support treating it separately:
  70% of drivers had no signal or bad signal, which is projection quality, not rule capture.
- **Shared upstream cause:** both gaps come from "findings end in a doc, and nothing is tested at build time."
  For rules, the missing piece is a lint. For 4d, it's a pool-vs-submitted diagnostic: "these z>=1 players were in
  your pool at X% exposure and in 0 of your entries." That diagnostic can be built with the same lint scaffolding
  (§4 C-SEL). It's surfacing, not enforcement, and it doesn't fix the root cause, which needs its own session on
  what drops strong players between the pool and the pick.

Don't merge the two workstreams. Build one reporting surface that covers both.

---

## 4. Pre-lock lint report design

**Implemented (read-only): `scripts/construction_lint.py`.**
`python scripts/construction_lint.py output/lineups_multi_<site>_<slate>[_<client>].csv [--pool final_projections_...csv] [--contest se|gpp] [--out flags.csv]`

- Inputs are artifacts that already exist: the lineup CSV (`lineup_id, roster_slot, player_id, position, team,
  salary, opponent`, where Showdown is detected by a `CPT` roster_slot), plus optionally the matching
  `output/final_projections_*.csv` (`estimated_ownership_pct`, `roster_role`, DST salaries). The pool path is
  guessed from the lineup filename.
- Output is one row per (lineup, rule): `rule, severity, evidence, detail`. It also prints a summary showing the
  share of lineups that hit each rule. Severity: `backstop` (the rule is already enforced, so firing means the
  preset wasn't used or a lock overrode it), `warn`, and `info`. The script modifies nothing.
- **Showdown checks:** SD3 K/DST CPT, SD13 WR/TE CPT without QB, SD12 $600-1k tier, stack depth >2 (these four are
  backstops); SD5 two kickers; SD6 expensive DST; SD7 4-2 CPT-heavy; SD8 CPT <5% (gpp) or the top-owned CPT (se),
  both on modeled ownership, and labeled that way.
- **Classic checks:** skill vs rostered DST (backstop); same-team WR/TE pair without their QB (§5); stack depth
  below QB+2; no bring-back; QB > $6,000; zero punts (<= $4k non-DST, same definition as Phase 2).
- Test runs: the wk3 ATL@GB Showdown pool (20 lineups, built before the presets existed) fired SD13 on 50% of
  lineups, SD7 on 25%, and SD6 on 40%. So the backstops correctly catch pre-preset builds. The wk3 DK classic
  main (3 lineups) fired zero-punts 2/3, QB price 3/3, and no-bring-back 3/3. All were hand-verified against the
  CSV.

**Designed, not built (next session):**
- **C-SEL (4d surfacing):** for multi-lineup pools, list players with projection z >= 1 (within position) whose
  exposure in the pool is 0 or low, and whether they were in the entry you actually submitted. Needs the pool
  file plus the chosen entry, which the UI doesn't record yet. That missing link is the blocker.
- **Ingest trades:** list `match_confidence=medium` / `auto_fallback_team_mismatch` rows from
  `ingest_salaries.py`'s match output in the same report, per checklist §1. Same report, different section.
- **Wiring:** call `construction_lint.main()` at the end of `optimizer.py main()` after `to_csv` (lines ~4495-4667)
  and in `run_optimizer_dispatch.yml`, and render the summary table in the frontend next to the partial-build
  banner. Keep it non-blocking. Wiring touches production paths, so it needs its own reviewed change.
- **Process rule:** when a postmortem adds a rule to any doc, it also adds a lint check, or states why the rule
  fails Q1. That keeps "informational-only" from coming back as a resting state.
- Rules not covered by the lint: TE-in-FLEX, "proj <= 7" filter, afternoon-FLEX (rationale not written yet), DST
  ownership tier, and game targeting. These are either UI settings or not checkable yet.
