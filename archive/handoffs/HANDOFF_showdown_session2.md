# Handoff: Showdown ownership/field/lineup-selection session (session 2)

Written 2026-09-22, combining two prior chats. Repo: `C:\Users\gmsco\Desktop\DFS_Optimizer`.
This session (starting from `HANDOFF_showdown_ownership.md`, session 1) built: a fitted
Showdown ownership model, a simulated Showdown field, a per-row lock/exclude UI fix, a
CPT-ownership-display bug fix, and a "pick one lineup for top-10%/top-1%" scoring method.
Read this file first, then `HANDOFF_showdown_ownership.md` (session 1, still accurate for
background/data inventory) if you need more history. `WK2_POSTMORTEM.md` has the running
log of findings (showdown section appended this session).

## 1. State: results are ready to log, not yet logged
**Greg has the NYG@LAR (2026-09-21 Mon night) DK results export now** (results + %Drafted +
lineups CSV, same shape as the wk1/wk2 files below). It has NOT been logged into
`data/ownership_actual_log.csv` yet, and the ownership model has NOT been refit on it. This
is the single most important next step: with NYG@LAR logged, the model has 3 slates instead
of 2, and the results validate (or don't) tonight's captain pick out-of-sample.
1. Log it: `python scripts/log_ownership.py log --site dk --season 2026 --week 2 --slate-id dk_showdown_wk2_NYG_LAR_21Sep2026 --slate-type regular_season --contest-type single_entry_gpp --field-size <N> --input <raw ownership CSV> --source "..."` then the equivalent `log_results.py log`. Follow the wk2 IND@KC pattern in `HANDOFF_showdown_ownership.md` section 4/6 exactly (dedupe player names first if the export has FLEX+CPT rows for each).
2. Refit: `python scripts/ownership_model_showdown.py fit --validate`.
3. Check the actual lineup played (Williams CPT / Stafford, Nabers, Adams, Rams DST,
   Parkinson -- see section 5) against the real field: did it land top-10%? Compare against
   the model's ~29-31% pre-game estimate (n=1 slate, so this updates confidence, doesn't
   settle it).
4. Re-run `analysis/showdown_own/splits.py` and `top10_drivers.py` with 3 slates instead of 2 -- the 5-1-split-is-best and chalk-CPT findings below are each from only 2 real slates.

## 2. What got built this session (all committed to `main`, pushed)
- **`scripts/ownership_model_showdown.py`** -- fitted CPT/FLEX ownership model, DK Showdown only. Ridge regression on logit-scale real ownership, 4 features (`l_exp` = logit of optimizer-exposure averaged over 15/30/50% noise x 60 lineups each, `isK`, `isD`, `isMin` = FLEX price <=$1000). Fit separately per role, water-filled to CPT=100%/FLEX=500% budgets with CPT cap 60% / FLEX cap 75%. Wired into `build_projections.py`'s `add_showdown_ownership_columns()` with a fail-safe fallback to the heuristic (kept as `estimated_ownership_pct_heuristic`). Artifact: `data/ownership_model_showdown_dk.json`. Refit command: `python scripts/ownership_model_showdown.py fit --validate`.
  - Leave-one-slate-out (2 slates): FLEX corr 0.83/0.90, chalk MAE 12.5/7.5 (heuristic was 18.9/12.9); CPT wk2 chalk MAE 6.5 (heuristic 16.3), wk1 CPT barely moves (only 4 chalk CPT rows, small-sample).
  - Known remaining miss: narrative/mid-price pass-catchers the model still underweights by ~30+ pts (wk1 Waddle 39% real vs ~0 exposure; wk2 Warren 41% vs 5%).
- **`scripts/showdown_field.py`** -- simulated Showdown field (`simulate_field()`): draws 1 CPT + 5 distinct FLEX per entry from CPT/FLEX ownership vectors, filters to salary cap $50k and a $48.5k floor (real entries' 10th-pct salary use), requires both teams present, and iteratively reweights (iterative proportional fitting, ~10 rounds) so the ACCEPTED lineups reproduce the input ownership (typical marginal MAE <0.3 pts). Validated in `analysis/showdown_own/validate_field.py`: built from real ownership + real points, it reproduces real lineup score quantiles (50/75/90/95/99/99.9%) within ~1-3 pts on both wk1 and wk2. Known weakness: team-split distribution isn't stack-aware (real fields lean more toward 3-3/4-2 on some slates than the iid draw produces) -- an optional `split_target` param exists to correct this but isn't used by default.
- **Frontend (`dfs_optimizer_frontend/index.html`) + optimizer (`scripts/optimizer.py`) fixes**:
  - **Per-row exclude on Showdown.** Excluding a player used to drop BOTH his CPT and FLEX rows. Now keyed like lock: `--exclude` accepts `pid:CPT`/`pid:MVP`/`pid:FLEX` (bare `pid` still excludes both); UI's X button excludes only the clicked row; bulk Exclude/Un-exclude All Shown act per row; a lock only drops if it's pinned to the excluded row. New `drop_excluded_rows()`/`parse_exclude_spec()` in optimizer.py. Classic slates unaffected (no roles).
  - **All/Captain/FLEX pool filter tab** added to the Showdown player pool UI (`#roleTabs`), combines with the existing position tabs.
  - **CPT ownership display bug fixed.** Lineup results used to join ownership by `player_id` alone, so the CPT slot showed the player's FLEX ownership number (e.g. a captain at 5% real showed the FLEX 35%). Now joined by `(player_id, roster_role)`. Also fixed in the optional ownership-CSV-override path.
- **Analysis scripts, all in `analysis/showdown_own/`** (see section 3 for the method detail Greg wants to reuse on classic):
  - `dataset.py`, `loso.py` -- ownership model feature/fit exploration (superseded by `scripts/ownership_model_showdown.py` itself, kept for reference).
  - `chalk_cpt.py` / `chalk_cpt2.py` -- chalk-captain-outcome analysis on real lineup-level exports (wk2 IND@KC / wk1 DEN@KC).
  - `splits.py` -- team-split (3-3/4-2/5-1) top-10%/top-1% lift on real lineups.
  - `top10_drivers.py` -- pooled logistic regression + lift tables for what predicts a real top-10% finish (captain position, CPT ownership tier, split, kicker/DST presence, projection/ownership/salary quartile).
  - `validate_field.py` -- simulated-field-vs-real-field validation (score quantiles, team split, salary use, kicker rate).
  - `best_single.py`, `refine_single.py`, `score_file.py`, `score_lineups.py` -- the "pick the best single lineup" pipeline; see section 3.
  - `compare_lineups.csv`/`compare_names.csv` -- the specific 11-lineup comparison run for tonight's final pick (Williams-CPT LA-heavy build vs Greg's 10 + alternates).

## 3. The method Greg wants ported to classic: "what makes a good single lineup"
Two DIFFERENT objectives were explicitly separated this session, because they favor different lineup structures:
- **Top-1% / GPP-max objective**: reward duplication-avoidance and ceiling. Chalk captains/chalk stacks get penalized even when their raw point total is fine, because the FIELD also has them (a "win" only pays if you beat lineups with the same players).
- **Top-10% objective** (what Greg actually wanted for a single-entry play): reward a genuinely higher expected percentile finish. This tolerates -- even prefers -- somewhat chalky, high-median builds, because in the real data (section 4) projection quality and structure (kicker present, right split, right captain position) mattered more than uniqueness once you're only trying to clear the 90th percentile, not the 99th.
Concretely this showed up as: the highest-top-1% lineup in one comparison (an NYG-concentrated, DST-heavy build) was near the BOTTOM on a worst-case/robustness view and was explicitly flagged as "a trap -- looks best in the raw numbers but its edge depends entirely on one modeling assumption (DST correlation)". The lineup finally played (LA 5-1, Williams CPT) ranked highest on top-10% metrics, not top-1%.

### 3a. Step 1 -- build a real simulated field (prerequisite for everything else)
`scripts/showdown_field.py`'s `simulate_field()` is Showdown-specific (CPT + 5 FLEX draw,
1.5x scoring) but the PATTERN generalizes directly to classic:
1. Draw a full valid lineup per simulated entry using per-player-per-SLOT ownership as sampling weights (classic: per position-eligible-slot ownership, same as the position_group budgets `ownership_heuristic.py` already computes).
2. Enforce the real roster-construction constraints (salary cap AND a realistic salary FLOOR -- real entries cluster near the cap, an unconstrained draw undershoots it; classic's floor would need its own real-data calibration, this session found showdown's at ~$48.5k against a $50k cap).
3. Iteratively reweight the per-slot draw weights (iterative proportional fitting, ~10 rounds, damped exponent ~0.6-0.7 per round) until the ACCEPTED (post-constraint) lineups' marginal ownership matches the target ownership -- constraints skew the raw draw away from the target, this correction is what makes the field usable.
4. VALIDATE before trusting it: with REAL ownership + REAL final points fed in, does the simulated field reproduce the real contest's actual score distribution (quantiles: 50/75/90/95/99/99.9%)? This session's showdown field matched real quantiles within ~1-3 points on both validation slates -- that's the bar to hit before using a simulated field for any lineup-selection decision. `validate_field.py` is the template.

### 3b. Step 2 -- generate a large, diverse candidate pool
`best_single.py::candidates()`: don't just take the optimizer's single "best" lineup.
Generate hundreds of candidates by (a) many noisy-projection solves (captures point-estimate
uncertainty), (b) solves with each plausible captain forced in turn (covers captain choice
directly, since it's the highest-leverage single decision), (c) solves with team-split /
stack constraints forced (covers structure choices directly). This session used ~750-760
candidates from ~250 noisy solves + ~30 solves per forced captain (top 12 captains) + ~30
solves per forced split.

### 3c. Step 3 -- score every candidate against the simulated field under SEVERAL correlated-outcome scenarios
`best_single.py::evaluate()` / `refine_single.py`: for each candidate lineup, simulate N
(1500-8000) draws of a full correlated slate outcome and compute P(candidate's percentile in
the simulated field >= 90%) = P(top 10%), and similarly for top 1%. Outcome draws use a small
factor model per player: `z = a*(game total factor) + b*(own-team offense factor) + noise`,
with position-specific rules for K (correlates with own-team factor only, no game factor) and
DST (negative correlation with the OPPOSING offense's factor). Score under MULTIPLE scenarios
(varying the game-total-factor weight for "shootout" vs not, adding a game-MARGIN factor that
shifts the winning team's mean up and the losing team's down for "big favorite" scripts,
zeroing DST correlation for a "quiet DST" variant) and report the AVERAGE across scenarios
AND the WORST-case (min) across scenarios -- the worst-case number is what caught the "trap"
lineup above; a lineup that's great in one scenario and bad in another is a bet on that
scenario being true, not a genuine edge. Also score under 2 different field-ownership
variants (the fitted model's ownership vs the old heuristic's) to check the pick isn't an
artifact of one ownership estimate.

### 3d. Step 4 -- cross-check against what ACTUALLY predicted a top-10% finish in real fields
`top10_drivers.py`: this is the reality check on the simulation above, run once real
lineup-level data exists (2 slates here, thin -- do this again with 3+). Pooled logistic
regression (simple IRLS, no library needed) on real top-10% outcome against: captain
position dummies, kicker-present, DST-present, split (3-3/4-2/5-1) dummies, and standardized
projection/ownership/salary. This session's real-data result (2 slates, treat as directional
not settled): projection quality was the strongest predictor (z~12), a 5-1 split was strongly
positive (z~11) and 3-3 negative (z~-5) -- i.e. **lean into the favorite's side more than
"balanced" stacking wisdom suggests**, a kicker in the lineup was positive (z~7.5), a DST
was negative (z~-11) after controlling for projection, and WR captains underperformed while
RB/TE captains overperformed (QB captains were roughly neutral). These real-data lifts were
used to BREAK TIES between simulation-scored candidates that were within noise of each other,
not to override the simulation outright.

### 3e. Porting this to classic -- what's already there vs what's new
- Classic already has: the ownership model (`ownership_model.py`), optimizer-exposure
  features, a heuristic to fall back to, and `optimizer.solve_lineup`/`randomize_projections`
  for candidate generation (no forced-captain concept, but forced-stack-team/game already
  exists via `--stack-team`/`--stack-game`).
- Missing for classic: (1) a validated simulated classic field (session 1's handoff
  mentions this was built informally last session via `analysis/wk2_session_scripts/
  fieldsim.py`/`fieldsim2.py` -- check if those already clear the quantile-matching bar, or
  redo properly using the showdown_field.py pattern above generalized to a full
  position-slotted roster); (2) the outcome-correlation factor model generalized to a full
  classic roster (QB-stack correlation matters more explicitly there than in showdown); (3)
  a `top10_drivers.py`-equivalent run against real classic contest lineup-level exports
  (Greg has at least wk1/wk2 main-slate `results_se3max_dk_classic_*` files per
  `analysis/wk2_session_scripts/load.py` -- reuse that loader).

## 4. Real-data findings this session added (on top of session 1's section 5)
- **wk1 DEN@KC full lineup-level analysis** (8,845 lineups, previously only had the
  player-ownership table): chalk CPT Bo Nix (20.2% CPT / 58% FLEX) was a clear miss -- 0 of 98
  top-1% lineups, 0.6% reached top-10%, mean 62.6 pts vs 71.6 field average. Every top-1%
  lineup that game had a KC captain (Walker 89% of top-1%, Mahomes the other 11%). The >15%
  CPT-ownership tier had the WORST outcomes of any tier.
- **Both showdown slates**: chalk captain was bad in wk1 (Nix), roughly average-on-points
  but ceiling-capped in wk2 (Walker -- 4th best CPT score on the slate by points, but only 5
  of 47 top-1% lineups used him at CPT vs 42% field usage). Two games is not enough to call
  "fade chalk captains" settled; it needs 3+ slates.
- **Team split (3-3/4-2/5-1) top-10% lift** (see `splits.py`, 2 slates): 5-1 lift 1.6-1.9x,
  4-2 roughly neutral (0.6-1.1x, NOT reliably good despite session 1's handoff calling it a
  good default), 3-3 lift 0.7-0.9x (below field average both times). Caveat: KC was the
  favorite in both real slates and KC-heavy builds won both times, so this could be
  "favorite-heavy wins" dressed up as "5-1 wins" -- needs a slate where the favorite doesn't
  cover to separate the two theories.
- **Kicker/DST real base rates**: kickers in 88-100% of wk2 top-10% lineups vs 38-43% of the
  full field; DST in 0-7% of top lineups vs ~50% of the bottom half. `top10_drivers.py`'s
  pooled regression confirms both directions hold after controlling for projection/split.

## 5. Tonight's (2026-09-21 NYG@LAR) final decision, for the record
Puka Nacua was ruled OUT before final lineups; pool was rebuilt/re-projected after that
(`output/final_projections_dk_dk_showdown_wk2_NYG_LAR_21Sep2026.csv`, refreshed ~18:14 CT).
With Nacua out, the field's ownership concentrated hard onto Stafford/Williams/Adams (FLEX
own ~42/51/46%), and the top-10%-optimized search flipped from an NYG-lean (pre-Nacua-news
pick) to an LA-heavy 5-1 lean. Final lineup played (chosen over Greg's own 10 generated
lineups, none of which scored as well): **CPT Kyren Williams | FLEX Matthew Stafford, Malik
Nabers, Davante Adams, Rams DST, Colby Parkinson** ($50,000, projected 94.8, estimated
~29-31% chance of a top-10% finish across scenarios, worst-case ~20%, ownership sum ~191 --
chalkier than the alternative "Adams CPT" build Greg also considered, which scored slightly
lower at ~29% and had a HIGHER ownership sum of ~205 despite Adams' own lower captain
ownership -- Williams/Corum's FLEX ownership drove that difference). **This is the lineup to
check against the real results once logged (section 1).**

## 6. Other open items carried from session 1, still true
- DET@BUF (wk2 Thu) results export: still not obtained. Ask Greg again if convenient, low priority now that 3 slates (wk1, wk2 IND@KC, wk2 NYG@LAR) will exist once section 1's step is done.
- Classic-lesson caution applies here too: a flat ownership/leverage penalty hurt classic lineups even with perfect ownership (session 1 finding). No such rule has been added to Showdown construction this session -- the lineup-selection method in section 3 scores candidates from the EXISTING optimizer's natural output, it doesn't add a leverage penalty to the solver itself. If ever tempted to add one, replay-test it first per that lesson.
- Automation / scheduled reminder (Mon 2026-09-28 8am CT, revisit whole agenda after Week 3) from session 1 is still pending and unrelated to this session's work.
- Repo hygiene: `git pull --rebase` before pushing (automated refresh commits land on `main` constantly). A few harmless untracked status/log files normally sit in the working tree.
