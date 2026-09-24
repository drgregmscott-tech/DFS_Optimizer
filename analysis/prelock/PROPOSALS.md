# Pre-Sunday proposals (not implemented; scripts/ and workflows untouched)

Ordered by expected impact on cash odds for 2026-09-27. Each proposal lists its evidence, the risk, and a
recommendation.

## 1. Apply status on light refreshes too (or skip the rebuild on light runs). HIGH, recommend before Saturday 12:00Z

**Problem (verified 2026-09-24 on origin/main):** in `.github/workflows/refresh_data.yml`, the refresh_slate job runs
"Rebuild projections" in every mode, but "Apply status (zero OUT players)" has
`if: needs.prepare.outputs.mode == 'full' && ...`. After the 19:55Z light run on 09-24, every Week 3 classic file had
lost `injury_status`. DK main had 72 OUT/IR players projected again (Jayden Daniels 12.7, Alec Pierce 10.0, A.J.
Brown 5.0 ...), and FD main had 64.
On Sunday, light runs fire at 15:00, 16:00 (at the same time as the 16:00 full run) and 17:00Z. So there is a real
chance that the file you build from at 16:30Z is un-zeroed.

**Fix options (smallest first):**
- (a) In the "Apply status" step, drop the `mode == 'full'` condition. The status file is already committed, so the
  step works in light mode with the latest `player_status_3_*.csv`. A one-line change. The risk is very low: it is the
  same command the full run executes.
- (b) Skip "Rebuild projections" when `mode == 'vegas_only'`. This changes the semantics (vegas moves no longer reach
  the projections between full runs).
- (c) Remove the `0 16 * * 0` entry from the light cron so it cannot race the 16:00 full run.

**Recommendation:** (a) plus (c). Validate by dispatching one light-equivalent run on Saturday and running
`python analysis/prelock/prelock_check.py` (it must show no `[FAIL] no injury_status column`). If nothing is changed,
the checklist's Fix A/B workaround covers it by hand.

## 2. status_check apply should also zero DOUBTFUL players and recompute ownership. MEDIUM

`status_check.py apply` zeroes only OUT (Doubtful players stay projected, e.g. Mason Taylor NYJ 3.9). It also never
recomputes ownership, which is the known WK2 finding that 50-80 of 900 ownership points sat on OUT players. The
prelock check on the Week 2 replay confirms it: 24-39 OUT players per slate still carried > 0.5% ownership.
**Recommendation:** after Week 3, zero Doubtful players in cash builds via `--exclude` (the checklist does this by
hand), and renormalise ownership after the status apply. Not for this Sunday (it touches the ownership code path).

## 3. Cash preset structure: add a `cash_stack` preset. MEDIUM, CLI-only, no code change

The evidence says QB+2 plus bring-back and TE-eligible FLEX improve top-25% cash
(`HANDOFF_classic_construction_replay.md` §3; `WK2_POSTMORTEM.md` within-batch diagnostic). The shipped `cash` preset
has `stack-mode none`. Proposal: add
`"cash_stack": {n-lineups 3, max-exposure 1.0, stack-mode qb, stack-size 2, bring-back true, lambda 0.063,
min-salary-pct 99}` to `data/optimizer_presets.json`.
**Recommendation:** for Sunday, just pass the flags on the CLI (checklist section 1). Add the preset after Week 3
replays confirm it (the replay harness is `scripts/replay_validation.py`, with Week 3 as the 7th-9th slates).

## 4. FD gets no props anchor. MEDIUM, after Week 3

`props_auto.py` skips `site != "dk"`, so FD classic is engine-only while DK gets the market blend. Props are
player-level and site-agnostic, so the DK snapshot for the same games could feed FD builds. `_apply_props_anchor` only
needs `props_{slate}.csv` and `events_{slate}.csv` for the slate id. **Recommendation:** after the first live DK
evaluation (Week 3 props audit versus actuals), copy or alias the DK snapshot for FD
(`--props-file data/props/props_dk_classic_wk3_main_27Sep2026.csv` on the FD build). Don't do it this Sunday: it is
unvalidated on FD scoring (half-PPR).

## 5. Moved-QB volume fix (Murray). LOW for Sunday, handled by hand

The known bias is -3.95 pts (n=31). The check's section 4 surfaces every QB 4+ points from public. Do the manual
`--thumbs-up` per checklist W2. Engine fix per the handoff item 4 (pre-scale volume).

## 6. prelock_check as a CI step. LOW

Run `analysis/prelock/prelock_check.py --slate-id <id>` at the end of each refresh_slate job and add a
`::warning::`/`::error::` annotation. It is read-only and needs git history (use checkout `fetch-depth: 0`, or the
movers section degrades gracefully). This would have caught #1 on its first occurrence.

## 7. Model QB tops run hot versus public. INVESTIGATE after Week 3

DK: Allen 29.5 vs public 24.6. FD: Allen 32.1, Purdy 26.2, Goff 23.3, each 5-8 pts above DFF. Meanwhile most cheap
QBs are 3-6 **below** public. That is the calibration-slope compression pattern already noted in `analysis/proj_c`
(slope 1.33 shipped vs 0.95 engine), and REPORT_followups #1 ("bias depends on projection size"). For Sunday's cash
builds, don't treat a 5+ pt model-only QB edge as value (checklist W2). Test after Week 3: QB bias by projection band
versus actuals.

## Not recommended before Sunday

- Hard ownership floor: rejected in replay.
- Any projection-engine change (qb_rush_scale, floor_share_fix): rejected in backtest (REPORT_followups #3, #4).
- Selection-criterion changes (`best_lineup_classic.py`): the open question is unresolved.
  `analysis/classic_diag/replay_selection_criteria_results.csv` shows floor_sum 3/6 cash (mean pct .704) vs raw
  projection 3/6 (.616) vs stack-only worst_top25 4/6 (.709). n=6, so it is not decisive.
