# Sunday Week 3 pre-lock checklist (2026-09-27)

> **UPDATE (2026-09-24): props now pull EARLY.** A Sunday 08:00Z (3am CDT) full run was added, and the props step now runs `props_auto.py --lead-minutes 600 --max-credits 150`. The old 120-credit cap would have SKIPPED the 24-game main pull (est. 144 credits), so the 16:00Z pull would never have happened. The 08:00Z run pulls once (~144 of ~227 credits); later runs re-try but the credit check skips them. Sections 1-4 below can assume a props snapshot exists at 4am CDT; verify with the check script (props PASS + movers table). If the 08:00Z run failed, run by hand: `python scripts/props_auto.py --lead-minutes 3000 --max-credits 150`, commit the new `data/props/*` files, push, then dispatch a full refresh. Also: the injury-status-on-light-runs bug is FIXED (workflow now applies status on every run), so Fix A/B below are only needed if the check still fails.


Slates (from `data/current_slate.json`): `dk_classic_wk3_main_27Sep2026`, `dk_classic_wk3_early_27Sep2026`,
`fd_classic_wk3_main_27Sep2026`, `fd_classic_wk3_early_27Sep2026` all lock **17:00 UTC (12:00 CDT)**.
`fd_classic_wk3_afternoon_27Sep2026` locks **20:05 UTC (15:05 CDT)**. DK main late games: ARI@SF, MIN@TB 20:05 UTC;
BAL@DAL, LV@NO 20:25 UTC. These stay late-swappable until they kick off.
There is **no DK afternoon classic entry** in `current_slate.json`. If you want to play it, see "Manual actions".

All times are UTC, with CDT (UTC-5) in brackets.

---

## 0. READ FIRST: the light refresh leaves OUT players projected (found 2026-09-24)

`refresh_data.yml` rebuilds projections on **every** run, including the `light_vegas_refresh` runs. But
"Apply status (zero OUT players)" only runs when `mode == 'full'` (see the `apply_status` step's `if:`). So after
any light run, the committed `final_projections_*` file has **no `injury_status` column and projects every OUT/IR
player again**. The check was run on origin/main at 19:55Z on 09-24, after a light run: 72 OUT players had
projections > 0 on DK main (Jayden Daniels 12.7, Alec Pierce 10.0, A.J. Brown 5.0 and others). The same was true on
every Week 3 classic slate.

Sunday cron order: **12:00 full**, **15:00 light**, **16:00 full AND light (two runs, queued in either order)**,
**17:00 light**, **19:00 full**. That means:
- From 15:00 to about 16:00Z the committed files are un-zeroed.
- If the 16:00 light run finishes after the 16:00 full run, **the final pre-lock DK/FD files will be un-zeroed**.
- From 17:00 to 19:00Z, the FD afternoon file is un-zeroed.

The UI's Build button (`run_optimizer_dispatch.yml`) builds from whatever file is committed. **Always run
`prelock_check.py` right before you build.** A `[FAIL] no injury_status column` line means you must re-apply status
before building (fix A or B in section 3). A proposal to fix this in the workflow is in `PROPOSALS.md` #1.

---

## 1. Commands used below

```
git pull                                                     # get the automated refresh commits
python analysis/prelock/prelock_check.py                     # all wk3 classic slates (read-only)
python analysis/prelock/prelock_check.py --slate-id dk_classic_wk3_main_27Sep2026
python analysis/prelock/prelock_check.py > prelock_$(date -u +%H%M).txt   # keep a copy
```
Exit code 2 = at least one FAIL, 1 = WARN only, 0 = clean.

**Fix A (preferred, fixes the repo files the UI reads):** GitHub, Actions, "Refresh Data", Run workflow
(`workflow_dispatch`). This is `mode=full`: status pull, vegas, FFC, rebuild, status apply. Props re-pull only if the
slate is under 100 min to lock and the snapshot is more than 120 min old, so it will not re-buy lines just pulled at
16:00. Wk2 logs show a full run takes about 4-6 min. Then `git pull` and re-run the check.

**Fix B (local, fastest; the UI will NOT see it):**
```
ls output/player_status_3_*.csv | sort | tail -1              # latest status pull
python scripts/status_check.py apply --site dk --week 3 --status-file output/player_status_3_<LATEST>.csv --projections-file output/final_projections_dk_dk_classic_wk3_main_27Sep2026.csv
# repeat for each slate id/site; then build lineups locally with the CLI (below)
```

**Lineup builds (local CLI, reads the local files):**
```
# Cash / H2H / double-up (3 lineups, lambda 0.063, no stack): the preset as shipped
python scripts/optimizer.py --site dk --slate-id dk_classic_wk3_main_27Sep2026 --preset cash --exclude <ids>
# Evidence-backed cash variant (QB+2 stack, bring-back; see section 6): test side-by-side with the one above
python scripts/optimizer.py --site dk --slate-id dk_classic_wk3_main_27Sep2026 --preset cash --stack-mode qb --stack-size 2 --bring-back --exclude <ids>
# Single-entry / 3-max GPP
python scripts/optimizer.py --site dk --slate-id dk_classic_wk3_main_27Sep2026 --preset se_gpp --stack-size 2 --exclude <ids>
# MME (20 lineups; dart cap uses the calibrated p10)
python scripts/optimizer.py --site dk --slate-id dk_classic_wk3_main_27Sep2026 --preset mme_gpp --n-lineups 20 --exclude <ids>
```
Swap in `--site fd --slate-id fd_classic_wk3_main_27Sep2026` (and so on) for FD. `--exclude`, `--lock`,
`--thumbs-up` and `--thumbs-down` take comma-separated `player_id`s from the projections file. You can also use the
UI with the same settings (preset, lambda, flex positions, thumbs and exposure are all sent by the dispatch), but
only after Fix A, or once the check passes on the committed files.

---

## 2. 09:00 UTC (04:00 CDT): wake-up pass, about 60-90 min

The last automated build at this point is **Sat 21:00Z light**, so expect section 0's FAIL. The 12:00Z full refresh
has not run yet. Status data dates from Sat 12:00Z.

1. `git pull`, then `python analysis/prelock/prelock_check.py`.
2. **Status:** if it shows `[FAIL] no injury_status column`, run **Fix A now** (workflow_dispatch). That also gives
   you a fresh status pull, vegas and FFC. Re-run the check when it finishes (about 5 min).
3. Work through the report for each slate:
   - **Section 3, Questionable >= 5 pts:** scan news for each one (22 on DK main as of Thu). Write down who is
     trending out. **Rule:** for cash, exclude any Questionable player in a 17:00Z game whose status you cannot
     confirm before 16:50Z. Late-window Qs (20:05/20:25) can be rostered only if you will be around for late swap.
   - **DOUBTFUL still projected > 0** (e.g. Mason Taylor NYJ 3.9 on Thu): `status_check apply` zeroes only OUT, so
     **exclude every Doubtful player by hand** (`--exclude`).
   - **Section 4, QB outliers:** see weak spot W2. Josh Allen 29.5 on DK vs public 24.6, and 32.1 on FD vs DFF 23.8.
     The model's QB tops run hot versus public. Do not treat a big model-only QB edge as free value in cash.
   - **Section 5, DST:** note the cheap-and-believable list and the blow-up list (opp implied >= 26).
   - **Section 6, p10/darts:** confirm `[PASS] statline_p10 is the calibrated QR p10` (weak spot W4).
   - **Section 8, chalk:** compare the model top-10 with the FFC column (weak spot W5).
   - **Section 9, weather:** wind >= 15 mph games (none on Thu's forecast; weather refreshes on every run).
4. **Build provisional cash lineups** from the current file with the `--preset cash` command (and the stack variant).
   Treat them as a baseline to compare against after props, not as final.
5. **Build provisional SE lineups** (`--preset se_gpp`). Your SE process (WK2 post-mortem memory): min salary
   49,500, exclude RB/WR/TE with proj <= 7 and your manual thumbs-downs. **But** keep TE eligible in FLEX (section 6).
6. Do **not** upload yet. Upload after the 16:00Z pass.

## 3. 12:00 UTC (07:00 CDT): scheduled full refresh (automatic)

About 12:05-12:20Z: `git pull` and run the check. It should now PASS on status. It also has a fresh vegas pull,
status and FFC. Re-build the provisional cash/SE lineups if section 2 movers or new OUTs touch your players.
**Do not rely on this file after 15:00Z:** the 15:00Z light run un-zeroes it again (section 0).

## 4. 15:30 UTC (10:30 CDT): inactives for 13:00 ET games

Official inactives come out about 90 min before kickoff (**~15:30Z** for the 17:00Z games). The 16:00Z full refresh's
status pull should pick them up, but ESPN can lag. **Scan the news for your core players now**, so the 16:00 rebuild
is the last change and not a surprise.

## 5. 16:00-17:00 UTC (11:00-12:00 CDT): props pull, final build, upload

- About 16:00Z both runs fire. The full run's `props_auto.py` pulls DK main and DK early (lock 60 min away, less than
  100 min, so DUE). Main plus early is one union pull of about 13 games x 6 = about 78 credits. That is within
  `--max-credits 120` and the ~220 left (handoff: ~227 before the Showdown re-pull). **FD gets no props**
  (`props_auto.py` skips `site != "dk"`), so FD builds are engine-only.
- GitHub cron often starts late, and two queued runs take about 10-15 min together. **If there is no new commit by
  16:25Z, run Fix A by hand.**

Steps once the commits land (target 16:20-16:35Z):
1. `git pull`, then run `python analysis/prelock/prelock_check.py`.
2. **Status:** if there is any `[FAIL]` (the light run landed last), run **Fix A**, then re-pull and re-check by about
   16:40Z. If you are out of time, use **Fix B** locally and build with the CLI.
3. **Props (DK only, first live use, weak spot W3):**
   - The report must show `[PASS] props ... build USED it`, and the audit line must show "N players matched".
   - Review the movers table (players changing > 15% versus the last pre-props build).
4. **Rebuild:** cash (both variants), SE and MME, with the same excludes plus any new OUT/Doubtful players.
5. **Export and upload by 16:55Z.** DK: the CSV upload in the Lineups tab, or edit in-client. FD: the upload template.
   Leave 5 min of slack; the site clock is the only one that counts.
6. **Cash lineups must not contain a Questionable player in a 17:00Z game unless confirmed active**, or a late-window
   Questionable you cannot watch for late swap.

## 5b. The 100-lineup pool experiment (GPP/MME; run after the props rebuild, before upload)

**Why:** the replay (`HANDOFF_classic_construction_replay.md`, "Diversified-batch hit rate" and "pool size" tests; 6 slates) found the BEST lineup in every 100-lineup batch landed at the 98th-99.9th percentile, but average hit rate was only ~27% (field baseline 25%), and a bigger pool did NOT improve the scenario-scorer's pick (20 candidates ~61% mean percentile vs 100 candidates ~57%). The open problem is SELECTION, not generation. Treat this as an experiment, not a proven edge. Having 100 lineups does not mean 'one will hit': entries are correlated, each costs a fee, and n=6 slates.

**Steps:**
1. Build the pool with the confirmed replay settings: `--n-lineups 100 --stack-mode qb --stack-size 2 --bring-back` with randomization and a 50% max exposure (see `analysis/classic_diag/replay_batch.py` for the exact flags). Save the lineups file path.
2. In the Claude session, ask for: (a) exposure table by player/team/game, (b) pairwise overlap (flag pairs sharing 7+ of 9), (c) ownership-leverage and projected-ceiling ranking using the calibrated p10/p90, (d) flags on lineups containing a new dart, a Doubtful/Questionable player, a moved QB, or a prop-driven big mover, (e) a proposed 20-30 subset (or the size of your max-entry contest) spread across game environments so lineups do not all fail together.
3. Decide the entry count from the contest max and entry fee. State the fee/payout assumption; the replay measured percentiles, not profit.
4. Save the final entered set to a file and note the contest, fee and max entries, so after the games every entered lineup (and the un-entered pool) is graded against real results. That grading adds Week 3 as slate #7+ to the replay evidence and is what improves the selection rule. Do this even if you enter fewer lineups.
5. Cash lineups (Section 6) are built separately; do not draw cash entries from this pool.

## 6. What maximises cash odds (evidence from this repo only)

Keep in mind that "cash" evidence in this repo comes from **DK SE3max top-25% lines** (6 slates) and a **synthetic
beat@p44** backtest. Double-ups and H2H pay around the 44th-50th percentile. That is a lower bar, but the same direction.

| Lever | What to do | Evidence | Confidence |
|---|---|---|---|
| Structure: QB + 2 pass-catchers + 1 bring-back | Use the stack variant of the cash command | Replay on 6 real slates: 0/6 to 1/6 cash, better percentile on most (`HANDOFF_classic_construction_replay.md` §3). Within-lineup logistic: `stack2p` +0.16 (z 4.9), `bb1p` +0.20 (z 9.5) (`WK2_POSTMORTEM.md` "Classic cash-line diagnostic") | Moderate. The shipped `cash` preset uses `stack-mode none`, so this contradicts the preset. Build both and prefer the stacked one when projections are within ~2 pts. |
| TE eligible in FLEX | Do **not** pass `--flex-positions RB,WR` | Within our own stacked batches: TE-flex cash 29.9% (n=385), WR 27.2%, RB 19.6% (`WK2_POSTMORTEM.md` "Within-batch cash-driver diagnostic") | Moderate, and the only lever that survives with structure held fixed. It goes against your WK2 SE habit of "TE not flex". |
| Floor weighting (lambda) | Keep `lambda 0.063` (the cash preset) | beat@p44 0.8723 vs 0.8662 at lambda=0, less than 1 SE (`ROADMAP.md` Session 10.5b / A5; `data/optimizer_presets.json` comment) | Weak. Suggestive only. |
| Lean toward chalk, don't fade it | No ownership floor (rejected). Just don't fade the obvious chalk in cash. | Own-sum Q4 lift 1.31x for top-25% (`WK2_POSTMORTEM.md`). A hard ownership floor was REJECTED in replay (helped 2/6, hurt 3/6, `HANDOFF_classic_construction_replay.md`). Within-batch own_sum not significant. | Moderate for the direction; do not force it. |
| DST: cheap and believable | Pick from the report's section 5 "cheap-and-believable" list. Never use a DST facing implied >= 26 in cash. | DST ownership coef -0.16 (z -11.1) and opponent total -0.06 (z -4.1) (`WK2_POSTMORTEM.md`). Replay `analysis/classic_diag/replay_v3a_cheap_dst_results.csv`: cheapest DST 4/6 cash (mean pct .739), default 3/6 (.703), cheapest-viable 2/6 (.691). Memory rule: prefer cheap-viable over literally cheapest (blow-up tail). | Weak (n=6). Follow your standing rule. |
| Use more of the cap | `--min-salary-pct 99` (a percentage: 99 = $49,500 DK / $59,400 FD) | `sal_z` +0.09 (z 6.1) (`WK2_POSTMORTEM.md`) | Weak. |
| Calibrated p10 | Use it as a **check**, not an objective: in cash, avoid any non-stack player whose calibrated p10 is 0 **and** whose projection comes mostly from TD equity | p10 calibration LOSO 10.4% below p10 vs 16.7% (`analysis/backtest_multi/REPORT_followups.md` #2). The optimizer only uses p10 for the MME dart cap. | Speculative as a cash rule. The calibration is solid for QB/WR/TE; RB is unproven (W1). |
| Exposure in cash | 1-3 lineups sharing the same core is fine (`max-exposure 1.0`) | Preset design; no backtest | Convention |
| Stakes sizing | Not covered by any repo evidence. **Speculative:** the usual bankroll convention is at most ~10% of bankroll per slate in cash. With your SE3max record 0/6 cashes (`WK2_POSTMORTEM.md`), keep stakes flat until Week 3-4 results exist. | none | Speculative |
| Don't overreact | The model is ~5/10 projections, ~6/10 ownership (`HANDOFF_next_session_backtest_2026-09-24.md` scoreboard). Model-vs-market gaps are more often model error than edge (W2). Don't hand-edit numbers except for news-driven role changes. | | |

## 7. Known weak spots: what to check and the decision rule

**W1. RB p10 gain is unproven.** Evidence: pinball CI for RB spans 0 (-0.007), 5/8 seasons
(`analysis/backtest_multi/REPORT_followups.md` #2).
- **Check:** report section 6. Look at RBs in the "newly flagged" or "no longer flagged" dart lists.
- **Rule:** in MME, if an RB you would otherwise play is capped at 10% only because of the dart rule, override it with
  a per-player exposure cap in the UI **only if** he is a confirmed lead back (depth #1 or news). No effect on cash
  (the dart cap is MME-only).

**W2. Moved-QB under-projection.** Moved starters are under-projected by -3.95 pts (n=31,
`REPORT_followups.md` #6). Murray (MIN) is 12.8 vs public ~17.6 (DFF+WWO).
- **Check:** report section 4. Look at QBs with `|model - pub_mean| >= 4`.
- **Rule:** for a QB **new to his team this season** whose model sits 4+ below public, treat his true mean as about
  the public number. In cash, do not play the *opposing* DST because of his low projection, and do not auto-fade him.
  If you want him, use `--thumbs-up <id>`: a flat +10%, still below the market, which is conservative.
  Conversely, the model's high QB numbers (Allen, and Purdy/Goff on FD, 5+ above public) are **not** proven edges.
  In cash, don't pay up for a QB only because of a model-only gap of 5 or more.

**W3. Props: first live classic use.** Weight 0.5, clamp 0.5-1.8x (handoff).
- **Check:** section 2 must say `build USED it` with N players matched (roughly 150+ on main). Review the movers
  table.
- **Rule:** a mover of more than 25% on a player you roster should agree with the news or the market direction.
  Props moving him **down** into a cash lineup's exclusion zone: follow the props (market plus injury news is in the
  line). A large **up** move on a cheap player with no news: cap him at your normal exposure; don't lock him in cash.
  If the props step failed (`did NOT use it`, or no snapshot at 16:40Z), build from the engine-only file. Don't buy a
  manual pull at the last minute unless it is before 16:30Z (`python scripts/props_ingest.py --site dk --slate-id
  <id>`, then Fix A). Note this spends real credits.

**W4. New dart list (calibrated p10).** 22 to 21 flags in the handoff test; 14 dropped (Kelce, LaPorta, Kincaid,
Bateman), 13 new cheap TE/WR (`REPORT_followups.md` #2). With the current file the check shows about 100 flagged
players with proj >= 3, mostly cheap TE/WR. The count basis differs from the report's.
- **Check:** section 6 PASS (calibrated). Scan the newly flagged names.
- **Rule:** MME only. Accept the list. If a flagged cheap player becomes a real starter because of news (an injury
  ahead of him), lift his cap by hand. No cash effect.

**W5. Ownership: two weeks of evidence.** 10-20% "cash chalk" is the weak tier; top chalk is under-estimated by about
7 pts (memory: ownership model state; `WK2_POSTMORTEM.md`).
- **Check:** section 8 chalk table: model vs `ffc_own_pct`. Kelce is 17.6 model vs 41.4 FFC, and Gibbs 38.7 vs 55.4.
- **Rule:** in cash, assume the **higher** of model and FFC is right. Ownership matters little in cash anyway
  (section 6). In GPP, treat the model's low-owned "leverage" calls on cheap players with suspicion unless FFC also
  has them low.

## 8. 17:00-20:25 UTC (12:00-15:25 CDT): late swap and the FD afternoon slate

- **17:00Z light run:** un-zeroes the FD afternoon file (section 0). Ignore the files until 19:00Z.
- **~18:35-18:55Z:** inactives for the 20:05/20:25Z games. Check your DK main lineups' late players
  (ARI@SF, MIN@TB, BAL@DAL, LV@NO).
- **19:00Z full refresh:** status, vegas and rebuild for `fd_classic_wk3_afternoon`. No props are pulled (FD).
  About 19:10-19:20Z: `git pull` and `python analysis/prelock/prelock_check.py --slate-id fd_classic_wk3_afternoon_27Sep2026`.
  Status must PASS (if it fails, use Fix A or B). Build with `--site fd --slate-id fd_classic_wk3_afternoon_27Sep2026
  --preset cash` (and the stack variant). **Upload by 20:00Z.**
- **DK main late swap rule (cash):** swap a late player only if (a) he is ruled inactive or Doubtful-to-out, or (b) a
  teammate's inactive changes his role. Don't swap to chase what happened in the early games.
  Swap candidates: the same position, fitting the salary you have left, in a 20:05/20:25 game. Use the pivot panel in
  the UI (it reads `output/pivot_suggestions_*`).

## 9. Manual actions only you can do

- **Enter contests and upload lineups** (DK/FD). Nothing here submits anything.
- **Run Fix A (workflow_dispatch)** whenever the check FAILs on status. Most likely times: 09:00Z, and 16:15-16:40Z
  if the light run lands last.
- **DK afternoon classic:** not configured. To play it: download the DK salary CSV into
  `data/raw_salaries/dk_classic_wk3_afternoon_27Sep2026.csv` before Sunday, run `ingest_salaries.py`, add a
  `current_slate.json` entry (lock `2026-09-27T20:05:00Z`), then build (DFS_Weekly_Process.md Stage 2) and push.
  Otherwise skip it.
- **Keep secrets set up:** `ODDS_API_KEY_PROPS` (props) and `ODDS_API_KEY` (vegas) in GitHub Actions secrets. The
  props pull silently falls back to engine-only if it fails.
- **After the games (Sun/Mon):** download the DK contest results and ownership exports into `data/`
  (Week 3 is fold 3 for every retest bar; `HANDOFF_next_session_backtest_2026-09-24.md` step 2).
