# Handoff: external projection sources + projection-accuracy ideas (2026-09-23)

Research-only session. **No pipeline code was changed.** Companion to
`HANDOFF_projections_model_review.md` (which fixed the reconciliation bug) and
`HANDOFF_ownership_model_review.md` (which integrated FFC for ownership). Greg's
framing: *"we have to get better. no excuses... we need to get them as good as
they can get."*

Two parts: (1) hands-on evaluation of the three free external projection sites,
(2) my own analysis of the real error log, with a prioritized list of ideas.

## 0. VERIFICATION (2026-09-23, same day) — R1's headline finding re-checked post-fix, direction holds, magnitude is smaller than reported below

Section 5 explicitly flagged that every number in §3 was measured on the **pre-fix**
pipeline and needed re-confirmation before trusting it further. Rebuilt all 6 real
DK wk1/wk2 classic slates with the current (post-reconciliation-fix) pipeline and
re-ran §3.1's exact ablation (same 157-row meaningful cut, same join):

| | Pearson | Spearman |
|---|---|---|
| `final_projection` pre-fix (as originally logged) | 0.383 | 0.338 |
| `final_projection` **post-fix** (as shipped now) | 0.318 | 0.430 |
| `season_avg` **post-fix** (matchup+vegas factor removed) | 0.350 | 0.468 |
| matchup-only, post-fix (vegas removed) | 0.259 | -- |
| vegas-only, post-fix (matchup removed) | 0.365 | -- |

**The direction replicates**: `season_avg` (matchup factor removed) still beats
`final_projection` post-fix, on both correlation measures, and matchup-only is
still the worst of the four variants (confirms matchup_factor, not vegas_factor,
is the problem) — same qualitative story as §3.1. **But the magnitude is
substantially smaller than what's reported below**: Pearson gap +0.032 (0.318 ->
0.350) vs. the pre-fix report's +0.098; Spearman gap +0.038 (0.430 -> 0.468) vs.
the pre-fix report's +0.122. Mean `final_projection` is now 14.31 against a real
mean of 14.64 (confirms the rebuild actually used the fix -- pre-fix mean was
10.97). Did not re-run the exponent sweep, the LOWO test, or the calibration-slope
check from §3.2/§3.4 -- only this one headline number. **R1 is still the right
first move, but size expectations should be set by this table, not the larger
pre-fix numbers in §3.1/§4.** Rebuild artifacts were not committed (reverted with
`git checkout` after this check, same discipline as `HANDOFF_projections_model_
review.md`'s own validation passes).

---

## 1. Summary

**Part 1 (external sites).** All three were actually visited today. Two are
genuinely, cleanly scrapable **right now** with no login and permissive
robots.txt: **Daily Fantasy Fuel** (server-rendered HTML, ~446 players, DK *and*
FD, plus injury tag / depth rank / implied team total) and **WinWithOdds**
(server-rendered HTML, 820 players, DK only, and it tags every player with the
**real DraftKings slate IDs** — better slate-matching than the fuzzy name+salary
match `ingest_public_ownership.py` has to do for FFC). **Fantasy Life** has the
best data of the three (floor / projection / ceiling *and* ownership, DK+FD, free,
no login) but is the only one that is **not** a reasonable scrape target: the
table is a virtualized JS grid that keeps ~11 rows in the DOM, and its only data
source is `/api/datatables/nfl-dfs-projections`, which `fantasylife.com/robots.txt`
**explicitly disallows** (`Disallow: /api/`).

**Part 2 (our own accuracy) — this is where the real finding is.** Slicing the
real error log several ways turned up something bigger than the known RB/WR
floor-share gap, and it is **not** what the handoffs point at:

> **`matchup_factor` (the defense-vs-position multiplier) is actively making
> projections worse.** Dividing it back out of the shipped projection raises
> correlation with real points on the meaningful cut from **0.402 → 0.493**
> (Pearson) and **0.356 → 0.495** (Spearman). A sweep of the exponent
> `market_factor ** alpha` is cleanly **monotone** — accuracy falls the whole way
> from alpha=0 to alpha=1.5 — and the effect **improves both folds** of a
> leave-one-week-out test. `vegas_factor` is close to harmless by comparison
> (0.402 → 0.418).

Second new finding: **the sigma / ceiling model is badly miscalibrated.** Even
after removing the (now-fixed) level bias, **17.8% of real scores land above
`statline_p90`** versus the 10% it claims, and only 68% land inside p10–p90
versus 80%. The implied sigma (~7.40) is ~19% smaller than the realized residual
std (9.12). That directly distorts every GPP ceiling/Monte-Carlo decision.

Third: the **known RB/WR floor-share gap looks like the *wrong* thing to
prioritize next.** Floor-priced DK RB/WR/TE with a logged actual show a mean
points bias of **+0.10** — essentially zero (caveat in §3.6: that measures the
floor players themselves, not the dilution they cause upstream).

Fourth, a useful **negative** result: a player's Week-1 error has **zero**
correlation with his Week-2 error (**r = -0.011**, n=99). There is no persistent
per-player bias left to learn — per-player correction factors are a dead end.

**Caveat that applies to all of §3:** every row in `data/projection_error_log.csv`
was produced by the **pre-fix** pipeline. The reconciliation fix has *not* been
re-logged. Correlation is invariant to shift and scale, so the rank-order findings
(the market-factor result above all) are **not** artifacts of the level bug — but
they still must be re-confirmed on a post-fix rebuild before anything ships. See §5.

**Correction to the brief I was given:** the error log covers **Weeks 1–2 only**,
not Weeks 1–3. There is no Week 3 data in it (2,709 rows; `dk` wk1 669 / wk2 657,
`fd` wk1 1,383). Every n below is small because of that.

---

## 2. Part 1 findings — the three free sites

Checked live on 2026-09-23. All three are serving **Week 3, 2026** data
(`start_date 2026-09-27`), so all three are current and in-season.

A useful calibration point — the three sites disagree with each other a *lot* on
the same player, which is the precondition for ensembling being worth anything:

| Jahmyr Gibbs, DET, DK $8,800 | projection |
|---|---|
| Daily Fantasy Fuel | 24.9 |
| WinWithOdds | 23.79 |
| Fantasy Life | 28.2 (floor 18.6 / ceiling 40.5) |

### 2.1 Daily Fantasy Fuel — **recommended, best scrape target**

- **URL:** `https://www.dailyfantasyfuel.com/nfl/projections/` (DK),
  `.../nfl/projections/fanduel/` (FD). Both return HTTP 200 to plain `curl`.
- **robots.txt:** `User-agent: * / Disallow: /lineup/* / Allow: /`. The
  projections path is **explicitly allowed**. Cleanest of the three.
- **Scrapable:** **Yes, trivially.** Fully server-rendered. Every player is one
  `<tr class="projections-listing">` with the numbers in `data-` attributes — no
  JS, no HTML-layout parsing, more robust than the `<td>`-position parsing
  `ingest_public_ownership.py` already does for FFC.
- **Granularity:** full slate, **446 players (DK) / 444 (FD)**, all 32 teams. Per
  player: `ppg_proj` (the projection), `value_proj`, `salary`, `team`, `opp`,
  `spread`, `ou`, **`proj_score`** (implied team total), `opp_rank` (DvP),
  `l5_avg`, `l10_avg`, `szn_avg`, **`inj`** (25 players tagged `Q` today),
  `starter_flag`, `depth_rank`, `rest` (days), `loc` (home/away).
  **Point total only — no stat-line detail** (no attempts/targets/TDs).
- **DK vs FD:** **site-specific**, two separate pages with genuinely different
  numbers (Gibbs 24.9 DK vs 22.6 FD; Josh Allen 24.0 DK vs 23.8 FD). Real scoring
  formats, not one generic number relabelled.
- **Ownership:** **none.** The `OWN` column exists but renders `--`. Matches what
  Greg said.
- **Friction:** none seen. No login, no email gate, no paywall interstitial.
- **Maintainability:** **good.** The `data-` attribute contract is the sort of
  thing that survives CSS redesigns. Risk is normal scrape risk (site rewrite).
  Caveat: it's a **whole-week** table, not per-slate — you'd match to our slate by
  name+salary the way the FFC ingest already does.

### 2.2 WinWithOdds — **recommended, and uniquely useful for slate mapping**

- **URL:** `https://www.winwithodds.com/dfs`. HTTP 200 to plain `curl`.
- **robots.txt:** `Allow: /` with a long Disallow list that **does not include
  `/dfs`**. It *does* `Disallow: /api/` and `/download/` — so scrape the HTML
  page, and **do not** use any JSON API or the `/dfs/download` CSV link.
- **Scrapable:** **Yes.** One server-rendered DataTables `<table>`, 820 rows,
  present in the raw HTML.
- **Granularity:** **820 players** (more than DFF — it goes deep into the bench),
  all 32 teams. Columns: rank, player, pos, team, game, salary, **projection**,
  value, and a **`Slates` column listing the real DraftKings slate IDs** the player
  is in (e.g. `153770,153771,153768,153769`, with the page labelling them
  `Main - 13 games`, `Thu-Mon - 16 games`, `Early Only - 9 games`, etc).
  **Point total only — no stat-line detail, no floor/ceiling.**
- **DK vs FD:** **DK only.** Salary range 2000–8800 matches DK exactly; no FD
  toggle exists on the page.
- **Ownership:** none. Matches what Greg said.
- **Friction:** none. No login or gate.
- **Two things that make it genuinely valuable beyond "another number":**
  1. The **slate-ID column removes the slate-matching guesswork** entirely —
     `ingest_public_ownership.py` currently has to fetch every FFC slate and pick
     the best name+salary overlap (`MIN_OVERLAP = 25`). WinWithOdds hands you the
     mapping directly.
  2. It **zeroes non-playing depth players outright** — Kyle Allen (BUF QB2) gets
     `0.0`, Davis Allen `0.7`, Cyrus Allen `0.73`. That is precisely the
     zero-history-bench-player problem §9 of the projections handoff flagged as
     unfixed. It is usable as a free external **depth/role prior**, which may be
     worth more to us than its point total (see recommendation R4).
- **Maintainability:** **moderate.** It's a plain DataTables HTML table, which is
  stable, but parsing is by `<td>` position, so a column insert would silently
  shift fields. Guard with a header assertion. One real caution: the page
  describes itself as built *"using player prop projected stats"* — so it is
  **prop-derived, i.e. substantially the same signal `scripts/props_model.py`
  already blends.** Expect it to be *correlated* with our props anchor, not
  independent of it. That materially weakens its value as an ensemble member,
  and is exactly the "noisier version of what props already capture" risk Greg
  asked about. Treat R4 (the depth prior) as the stronger use.

### 2.3 Fantasy Life — **best data, but do not scrape**

- **URL:** `https://www.fantasylife.com/tools/nfl-dfs-projections`.
- **robots.txt:** `Allow: /` but with `Disallow: /api/`, `/ajax/`, `/datatable/`,
  `/players/`. It also publishes an `llms.txt`.
- **What's actually there (verified in a real browser, logged out):** the richest
  table of the three — `# / Player / Salary / Opp / DVP / Fantasy Boost / **Floor**
  / **Projection** / **Ceiling** / **Own%**`, with a **DraftKings ⇄ FanDuel**
  toggle and Classic/Showdown + slate selectors. Greg was right: **free
  projections AND ownership**. Sample as rendered: Gibbs DK $8,800 — floor 18.6,
  proj 28.2, ceiling 40.5, **own 58.8%**; McCaffrey 16.1 / 21.9 / 34.0 / 10.5%.
  The floor/ceiling pair is something neither other site has and that we would
  otherwise have to model ourselves (see §3.4 — our ceiling model is wrong).
- **Scrapable:** **No, not acceptably.**
  - Plain `curl` of the page returns the SPA shell — **0 player rows** (I checked;
    "Gibbs" appears 0 times in 160 KB of HTML).
  - The Next.js RSC payload (`?_rsc=...`) also contains **0 player rows**.
  - In a real browser the data arrives from **`/api/datatables/nfl-dfs-projections`**
    — confirmed from the page's own `performance` resource entries. That path is
    **disallowed by their robots.txt** under `Disallow: /api/`. I did not call it.
  - Even ignoring robots.txt, the rendered table is **virtualized**: only ~11
    `<tbody><tr>` exist in the DOM at any time, so headless-browser scraping would
    require scripted scrolling for ~400 players per site per slate.
- **Friction:** the *data* is free and visible logged-out, but several **filters**
  (projection range, ownership range, salary range, Team, Contest Type, Slate) show
  padlock icons and are **FantasyLife+ gated**. So you can read the default
  DK/Classic/Main view for free, but you cannot freely pivot it to an arbitrary
  slate — which is exactly what an automated weekly pull would need.
- **Maintainability:** **poor / not recommended.** Headless-browser + scroll
  automation against a JS grid, to reach an endpoint the site asks bots not to
  touch, is both the most fragile option and the one with a policy problem. My
  recommendation is **don't automate this one.** If its floor/ceiling numbers are
  wanted, read them manually as an occasional sanity check (see R3), or ask
  whether FantasyLife+ offers a sanctioned export.

---

## 3. Part 2 findings — my own analysis of the real error log

Method: `data/projection_error_log.csv` restricted to `slate_format == "classic"`
(2,558 rows), joined to the original `output/final_projections_*.csv` builds for
salary / `games_played` / `sigma` / `statline_p10` / `statline_p90` /
`matchup_factor` / `vegas_factor` / `implied_total`, and **deduplicated to one row
per real player-week** (a player appears on main + early + afternoon of the same
week) → 1,384 player-weeks, of which 664 DK. "Meaningful" = `final_projection > 8`,
the same cut the other handoffs use. Reproduced the handoff's headline numbers
first as a check: DK meaningful bias **+3.28**, MAE **7.05**, corr **0.402** —
consistent with its **+3.24 / 7.36 / 0.39**, so the joins are sound.

### 3.1 THE BIG ONE: `matchup_factor` is making projections worse

`build_projections_statline.py:739` documents that
`season_avg = final_projection / market_factor`, where `market_factor =
matchup_factor × vegas_factor` (applied to the efficiency rates by decision #10 of
`statline_model.py`). So `season_avg` is **the projection with the market
adjustment divided back out** — which makes it a free, exact ablation sitting in
every output file. It is **more accurate than the shipped projection**:

| DK, meaningful (n=157) | Pearson | Spearman |
|---|---|---|
| `final_projection` (as shipped) | 0.402 | 0.356 |
| `season_avg` (= market factor removed) | **0.500** | **0.477** |
| `salary` alone | 0.418 | 0.418 |

Bootstrap (4,000 resamples): delta **+0.098 Pearson, 95% CI [+0.014, +0.189]**,
P(delta>0) = **99.0%**; **+0.122 Spearman, CI [+0.026, +0.227]**, P = **99.4%**.

Sweeping the exponent `projection = pure_usage × market_factor ** alpha`
(alpha = 1.0 is as-shipped, 0 is the factor switched off), after rescaling each
variant to the actuals' mean so the level bug can't drive MAE:

| alpha | Pearson | Spearman | MAE | RMSE |
|---|---|---|---|---|
| **0.000** | **0.5104** | 0.5009 | **6.639** | **8.530** |
| 0.125 | **0.5108** | **0.5015** | 6.679 | 8.542 |
| 0.250 | 0.5075 | 0.4952 | 6.754 | 8.570 |
| 0.500 | 0.4877 | 0.4810 | 6.919 | 8.674 |
| 0.750 | 0.4510 | 0.4437 | 7.077 | 8.836 |
| **1.000 (shipped)** | **0.4017** | **0.3555** | **7.244** | **9.051** |
| 1.500 | 0.2922 | 0.1941 | 7.653 | 9.625 |

Three things make me take this seriously rather than treat it as overfitting:

1. **It is monotone.** Accuracy degrades smoothly and without exception across the
   whole range. That is a dose-response relationship, not a lucky optimum picked
   out of noise.
2. **It survives leave-one-week-out, on both folds** (alpha chosen on the other
   week): holdout wk1 corr **0.411 → 0.531 (+0.120)**; holdout wk2 **0.369 → 0.396
   (+0.028)**. Both positive. (Contrast §3.5, where the external-blend idea fails
   one fold — I ran the same test on both, and only this one passes.)
3. **Correlation is invariant to shift and scale**, so this cannot be an artifact
   of the +3.3 level bias the reconciliation fix just removed.

**And it isolates cleanly to one of the two factors:**

| removing… | Pearson | Spearman |
|---|---|---|
| `matchup_factor` (keep vegas) | 0.402 → **0.4925** | 0.356 → **0.4950** |
| `vegas_factor` (keep matchup) | 0.402 → 0.4178 | 0.356 → 0.4184 |

**`matchup_factor` is doing nearly all of the damage. `vegas_factor` is roughly
neutral.** Per-slate Spearman, as-shipped vs factor-off: 0.357→0.645, 0.279→0.403,
0.497→0.445, 0.195→0.233 — **3 of 4 slates improve**, mean **0.332 → 0.431**.

Mechanistically this is very plausible and matches public DFS analysis: raw
defense-vs-position through Week 2 is computed on **one or two games**, so it
mostly measures *which offenses a defense happened to face*, not defensive
quality. `projections_matchup.py` already knows this — it has empirical-Bayes
shrinkage at `SHRINKAGE_K_GAMES = 4.0` (line 83, applied in `matchup_factors()`
~line 190). The finding is that **`k = 4.0` is far too weak this early**; the
observed `market_factor` still ranges **0.659 → 2.211**, i.e. it is swinging real
projections by more than 2x on one-to-two games of evidence.

### 3.2 It's a *slope* problem, not only a level problem

Regressing `actual ~ a + b × projection` on the DK meaningful cut:

| | n | slope | intercept |
|---|---|---|---|
| ALL | 157 | **1.25** | +0.41 |
| QB | 41 | **0.64** | **+9.57** |
| RB | 38 | 1.37 | −1.05 |
| WR | 46 | 1.29 | +1.49 |
| TE | 14 | 1.03 | −0.65 |

Slope > 1 means the model's spread is **compressed** — it under-separates the good
from the bad. Bias by projection decile confirms it climbs monotonically, from
≈0 in the middle deciles to **+4.40 in the top decile** (proj 14.31 → actual
18.72). This is `WK2_POSTMORTEM.md`'s "stud under-projection" measured as a
calibration slope.

**This matters for how §9 of the projections handoff should be read.** That fix
drove *mean* bias from +3.24 to +0.11 — but a mean-zero model with slope 1.25
still systematically under-projects studs and over-projects mid-tier. **Fixing the
level does not fix the slope.** Re-measuring the slope post-fix is the single
cheapest high-value check available (R1).

QB is its own pathology: slope 0.64 with a +9.57 intercept and corr **0.244** —
i.e. among meaningful QBs the model barely rank-orders at all, it just adds a
near-constant. Consistent with §8 of the projections handoff finding the week-1 QB
cause unexplained.

### 3.3 The bias lives in *established* players, not cold-start

DK meaningful, by `games_played`: **gp 1–3: bias +2.62, MAE 5.66 (n=60)** vs
**gp 9+: bias +5.07, MAE 8.52 (n=76)**. The players the model has the *most*
history on are the ones it gets most wrong — which fits the reconciliation bug
(§9 of the projections handoff) exactly, and is a good independent confirmation
that that fix was aimed at the right thing.

### 3.4 NEW: the sigma / ceiling model is miscalibrated (not covered in any handoff)

Checking real scores against the shipped `statline_p10` / `statline_p90`
(DK meaningful, n=157):

| | below p10 | above p90 | inside | (expected) |
|---|---|---|---|---|
| as shipped | 2.5% | **28.7%** | 68.8% | 10 / 10 / 80 |
| after removing the +3.28 level bias | 14.0% | **17.8%** | **68.2%** | 10 / 10 / 80 |

The level fix repairs the *shift* (2.5%→14.0% below p10) but **not the width or
the right tail**: 17.8% of real scores still beat a "90th percentile" that should
be beaten 10% of the time, and only 68% land inside an interval that claims 80%.
Mean p10–p90 width is 18.96 pts ⇒ implied sigma ≈ **7.40**, versus a realized
residual std of **9.12** — the model's uncertainty is **~19% too small**, and
skewed: real NFL scoring has a fat right tail the Monte Carlo isn't reproducing.

This is not a cosmetic issue for a GPP tool. `sigma` and the p10/p90 pair feed
ceiling/leverage reasoning and the Monte Carlo candidate pool. A too-thin right
tail systematically **understates exactly the boom outcomes tournaments pay for**.
Note `sigma_recalibration.py:119` explicitly documents that it *does not touch*
`statline_p10`/`statline_p90` — so whatever recalibration exists today does not
reach the quantiles this test is failing.

### 3.5 Ensembling: real in-sample gain, but it fails out-of-sample — do not ship yet

I could not test the three external sites historically (nobody snapshotted them
for Weeks 1–2; all three serve only the current week). But there is a **free
external projection already sitting in every DK salary file**: DraftKings'
own `AvgPointsPerGame`. That makes the ensembling question testable **today, with
zero scraping**, which is the cheap backtest Greg asked whether existed.

Blending z-scored `final_projection` with z-scored `AvgPointsPerGame` (z-scoring
makes it a pure shape/rank blend, immune to the level bug):

| weight on APPG | 0.0 | 0.25 | **0.375** | 0.5 | 0.75 | 1.0 |
|---|---|---|---|---|---|---|
| Pearson | 0.4017 | 0.4328 | **0.4385** | 0.4349 | 0.4001 | 0.3433 |

So the classic forecasting result **does** appear: the blend (0.4385) beats *both*
components (ours 0.4017, APPG alone 0.3433). Straight MAE/RMSE agree (RMSE
9.66 → 9.27 at 25% weight).

**But it does not survive honest validation.** Leave-one-week-out, picking the
weight on the other week: holdout wk1 **0.411 → 0.461 (+0.050)**; holdout wk2
**0.369 → 0.353 (−0.016)**. **One fold up, one fold down**, and the chosen weight
swung wildly between folds (0.31 vs 0.75) — the signature of fitting a blend
weight on ~70 rows. Per the project's own standard in
`feedback_rigor_over_reassurance_in_construction_testing.md`, that is
**correlational-but-untested, not confirmed.** With 2 weeks of data it is not
shippable. It *is* a strong reason to start logging external projections now so
the same test has real power by Week 6 (R2).

### 3.6 The known RB/WR floor-share gap does **not** look like the biggest lever

§9 of the projections handoff flags residual RB/WR under-projection from
zero-history floor players drawing price share. Measuring the floor players
directly (DK RB/WR/TE at salary ≤ $4,200 with a logged actual, n=329):
mean projection **2.88**, mean actual **2.98**, **bias +0.10** — essentially zero.
Across the full DK floor pool (n=1,697) mean projection is 1.87, and only 9.5%
get more than 4 points.

**Honest caveat on this one:** the handoff's mechanism is that floor players
*dilute the starters upstream*, not that the floor players themselves are
mis-projected — so this measures the symptom I can see, not the harm the handoff
describes. Isolating the dilution needs a rebuild, which was out of scope here.
What I can say: the floor players' own projections are not badly biased, and 50.2%
of them scored exactly 0, so the remaining pool inflation is small in points
terms. **On this evidence it should rank below §3.1, §3.2 and §3.4**, not above
them — which is the opposite of the current prioritization.

### 3.7 Useful negative results (so nobody spends a session on them)

- **Per-player learned corrections are a dead end.** Correlation between a
  player's Week-1 error and his Week-2 error: **r = −0.011** (n=99 players with
  both weeks). There is no persistent player-level bias to learn; the residual is
  noise.
- **"Did the player even play" is not the meaningful-cut problem.** At
  `final_projection > 8`, `actual == 0` rows are 1.9% of DK rows and 3.1% of total
  absolute error. (Across the *whole* DK pool it's 28.6% of rows / 17.6% of error;
  on FD, 66.1% of rows / 35.5% of error — so it matters for pool hygiene and FD
  especially, but it is not what's wrong with the top plays.)
- **Game environment is a weak, non-monotone slice.** Bias by implied-total
  quartile: +3.95 / +6.08 / +1.95 / +1.22. Bias is *largest in the middle*, which
  is not a clean "we under-rate shootouts" story.
- **`season_avg` and `recent_form` are identical in 100% of rows** — but this is
  **documented and intentional**, not a bug (`build_projections_statline.py:36`:
  *"same value. There is no second recency scheme"*). I flag it only so the next
  person doesn't rediscover it and treat it as a finding. It does mean any model
  consuming both as separate features is getting one feature twice.

---

## 4. Prioritized recommendations

Ranked by (measured evidence strength) × (expected gain) ÷ (effort & risk).

### R1 — Shrink `matchup_factor` hard, and re-measure the calibration slope. **Do this first.**
- **What / why:** §3.1 — removing the matchup multiplier raises meaningful-cut
  correlation 0.402 → 0.493 Pearson / 0.356 → 0.495 Spearman, monotonically in the
  exponent, positive on both LOWO folds, bootstrap P=99%. `vegas_factor` is fine;
  it's specifically the DvP term. Root cause is almost certainly that
  `SHRINKAGE_K_GAMES = 4.0` is far too weak when only 1–2 games of the season
  exist, letting `market_factor` swing 0.66–2.21 on near-zero evidence.
- **Where:** `scripts/projections_matchup.py` — constant `SHRINKAGE_K_GAMES`
  (line 83), applied in `matchup_factors()` (~line 190). The right change is
  almost certainly **making k a function of games played this season** (strong
  shrinkage in Weeks 1–4, relaxing as the sample grows) rather than hard-coding a
  bigger constant, so the factor can still do real work in Week 12. A global
  exponent on `market_factor` inside `statline_model.py` decision #10 is the
  cruder alternative — prefer fixing the shrinkage, since that's where the
  statistical error actually is.
- **Validate:** three gates, all cheap. (a) Rebuild the 6 real DK wk1/wk2 classic
  slates and re-run the §3.1 exponent sweep — the shipped alpha should now sit at
  the top of the curve, not the bottom. (b) Re-run the LOWO test; require **both**
  folds non-negative, not just the mean. (c) **Re-measure the calibration slope
  from §3.2 at the same time** — it is the same rebuild and it answers whether
  §9's bias fix left a slope problem behind. Report Spearman per-slate, not just
  pooled, since lineup building is a within-slate ranking problem.
- **Effort/risk:** **quick win.** One constant / one small function, one rebuild
  pass, no new data source, no new dependency. Main risk is over-correcting for a
  2-week sample — which is exactly why the fix should be games-played-dependent
  and why gate (b) requires both folds.
- **Loop-back:** per §0 of both handoffs, this changes `final_projection` again and
  would need flagging to the Week 3+ lineup session before the 1/6 / 0.583 rescore
  is trusted further.

### R2 — Start logging Daily Fantasy Fuel (and WinWithOdds) weekly, as **data collection only**
- **What / why:** §3.5 shows ensembling gives a real in-sample gain that **fails
  out-of-sample on 2 weeks**. The blocker is sample size, not the idea. Nobody has
  historical snapshots of these sites and they only serve the current week — so
  **every week we don't log is permanently lost**. Start the archive now; decide
  whether to blend later, when the LOWO test has power.
- **Where:** a new `scripts/ingest_public_projections.py`, modelled directly on
  `scripts/ingest_public_ownership.py` (same `requests` + `BeautifulSoup`, same
  `norm_key(name, salary)` matcher, same `data/…/{site}_{slate_id}.csv` layout,
  new dir `data/projections_public/`). DFF is the easier parse — one regex over
  `<tr class="projections-listing">` `data-` attributes. Wire into
  `.github/workflows/refresh_data.yml` next to the existing FFC ingest step.
  **Explicitly do NOT wire it into `build_projections_statline.py` yet.**
- **Validate:** after ~4 more weeks, re-run §3.5's exact LOWO protocol with the
  external projection in place of `AvgPointsPerGame`, and require **every fold**
  to improve (the standard the FFC ownership work actually met: .639 → .764 with
  every slate improving). Only then consider a `_apply_public_projection_anchor()`
  alongside `_apply_props_anchor()` in `build_projections_statline.py`.
- **Effort/risk:** **quick win to build (~half a session), zero model risk**,
  because nothing consumes it yet. This is the "cheap way to start before
  recommending a live integration" — the cost of waiting is irreversible.
- **Caveat to carry:** WinWithOdds self-describes as prop-derived, so it likely
  **correlates with our existing props anchor** rather than adding independent
  signal. DFF (with its own L5/L10/season splits) is the better bet for
  independence. Log both; test them separately before blending either.

### R3 — Fix the sigma / ceiling calibration
- **What / why:** §3.4 — 17.8% of real scores exceed `statline_p90` after removing
  the level bias (should be 10%), only 68% land inside p10–p90 (should be 80%),
  implied sigma ~19% below realized residual std, right tail too thin. For a GPP
  tool this distorts ceiling and leverage directly.
- **Where:** the quantiles are produced in `scripts/statline_model.py` ~lines
  2338–2339 (`np.percentile(pts, 90/10)` over the Monte Carlo draws), so the
  miscalibration is in the **simulated distribution's shape**, not a post-hoc
  scaler. Note `scripts/sigma_recalibration.py:119` explicitly documents that it
  **does not touch** p10/p90 — so today's recalibration cannot fix this. Likely
  candidates: TD outcomes drawn with too little dispersion, and/or per-component
  variances treated as independent when real big games are correlated
  (yards *and* TDs spike together).
- **Validate:** a **PIT / coverage test** is the right instrument and it is cheap —
  for each logged player-week compute where the actual falls in the simulated
  distribution and check the histogram is flat. Ship only when p10/p90 coverage
  lands near 10/80/10 on held-out weeks. Do this **after R1**, since R1 changes the
  mean the distribution is built around and would invalidate a variance fit done
  first.
- **Effort/risk:** **medium-to-major.** Touches the Monte Carlo core, and a wrong
  widening makes every ceiling worse. But it is measurable with a clear pass/fail
  target, which is more than most of this list.

### R4 — Use WinWithOdds (or DFF `depth_rank`/`starter_flag`) as a free external depth/role prior
- **What / why:** §2.2 — WinWithOdds zeroes non-playing depth players outright
  (Kyle Allen 0.0), and DFF ships `starter_flag` / `depth_rank` / `inj` per player.
  That is an independent, free read on exactly the question §9 of the projections
  handoff left open: which floor-priced players are real contributors. It is a
  **more direct fix than re-fitting the `share_from_salary()` curves**, which that
  handoff correctly called a bigger, riskier change to fitted artifacts
  (`data/volume_prior_dk.json`, fit on 2014–2021 data).
- **Where:** feed it into `apply_volume_prior()` in `scripts/statline_model.py`
  through the **same `depth_chart` parameter the §8 QB fix already added** — that
  plumbing exists, so this is extending an established mechanism, not inventing
  one. It would generalize the QB-only suppression to RB/WR using an external
  opinion instead of a depth chart.
- **Validate:** the §7 precedent is the warning — the naive "zero the non-starters"
  RB fix **made things worse** (ratio 0.74→0.68, MAE 5.07→5.80) because the
  team-sum normalization only ever scales *down*. So any version of this **must**
  renormalize among eligible players, and must be checked against real rush
  attempts/targets the same way §7 did, before touching points.
- **Effort/risk:** **medium**, and explicitly gated behind R2 (need the feed
  first). Lower priority than R1–R3 because §3.6 suggests the floor-share gap is
  worth less than currently assumed.

### R5 — Do **not** pursue these (tested or reasoned, negative)
- **Per-player learned bias corrections** — §3.7, wk1→wk2 error correlation
  −0.011. No signal to learn.
- **Scraping Fantasy Life** — §2.3. Robots-disallowed API, virtualized DOM,
  gated filters. Best data of the three, worst integration target. If its
  floor/ceiling is wanted, read it by hand as an occasional sanity check against
  R3's work, or ask them about a sanctioned export.
- **Availability / "did he play" modelling for the meaningful cut** — §3.7, 1.9%
  of rows and 3.1% of error at `proj > 8`. (Worth revisiting for the FD pool
  specifically, where 66% of logged rows are zeros.)
- **Blending `AvgPointsPerGame` into the live build right now** — §3.5, fails one
  of two LOWO folds. Revisit under R2 when there's power.

---

## 5. What I did NOT get to / could not verify

- **Everything in §3 is measured on PRE-FIX builds.** `data/projection_error_log.csv`
  contains only the old pipeline's output; §9's fix has not been re-logged, and
  §9 explicitly says the validation rebuilds were reverted and not committed. I
  deliberately did **not** rebuild, both because the brief was research-only and
  because a parallel session is live in `analysis/proj_recheck/`. Correlation is
  shift/scale invariant so the rank-order findings (R1 above all) should carry
  over — **but "should" is not "did."** Re-running §3.1's sweep and §3.2's slope
  on a post-fix rebuild is the first thing the next session should do, and it is
  the same rebuild for both.
- **Sample sizes are small and this is 2 weeks.** The DK meaningful cut is
  **n=157** player-weeks across 2 weeks; per-position cells are 14–46. The
  bootstrap CI in §3.1 is genuinely informative and the monotone sweep plus
  both-folds-positive LOWO is about as much as 2 weeks can support — but it is 2
  weeks. **No Week 3 data exists in the log yet** (contrary to the brief).
- **No historical external projections exist**, from any of the three sites, so
  the "would blending an external source have helped in Weeks 1–2" question is
  **unanswerable today**. §3.5 uses DK `AvgPointsPerGame` as the closest available
  stand-in; that is a proxy, not the real test. This is the entire reason R2 is
  ranked where it is.
- **FanDuel `AvgPointsPerGame` was not tested** — the FD salary files use a
  different schema (`FPPG`, no `player_id` column), so §3.5's benchmark covers DK
  only (48% coverage of the deduped rows).
- **I did not isolate the RB/WR dilution harm** (§3.6) — measuring it properly
  needs a rebuild with and without the floor players in the price-share pool.
  My +0.10 number measures the floor players' own bias, which is related but not
  the same quantity.
- **I did not check DFF or WinWithOdds for a Showdown/single-game view**, or for
  historical/archive URLs. If either archives past weeks, that would immediately
  unblock R2's validation without waiting — **worth 10 minutes before building the
  ingest script.**
- **`props_model.py` remains untested end-to-end against live market data**, per
  §9 of the projections handoff. Nothing here changes that, and my §3 data
  predates both `props_model.py` and `projection_stack.py` (committed 2026-09-21),
  so **none of my numbers say anything about either mechanism.**
