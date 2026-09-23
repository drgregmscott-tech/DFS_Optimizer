# Weekly DFS Pipeline — Standard Operating Procedure

*Step-by-step instructions for taking a slate from DK/FD posting to locked lineups. Follow in order. If you hit an error not covered here, open a conversation with Claude and paste the full error message.*

---

## Overview

| # | Stage | Who/what does it | Timing |
|---|-------|-------------------|--------|
| 1 | New slate posted | DK & FD | Tue or Wed |
| 2 | Manual weekly kickoff | **You** | Same day, once |
| 3 | Automated refresh loop | GitHub Actions + Cloudflare Worker | Runs unattended until lock |
| 4 | Build & preview lineups | **You**, via the deployed UI | Anytime before lock |
| 5 | Export & re-upload | **You**, back into DK/FD | Near lock |
| 6 | Log actual ownership | **You** | After DK/FD post contest results |

Stages 1, 2, 4, 5, and 6 are things you do. Stage 3 runs unattended once Stage 2 is complete and pushed.

---

## Choosing `--week` and `--season` values

**Updated 2026-08-05** — this section changed after a real Week 1 2026 run surfaced the actual rule. There are two *separate* concepts that used to be conflated under one `--week`/`--season` pair, and now aren't:

1. **Stats lookback** (`projections_baseline.py`, `projections_matchup.py`, and the `--season`/`--week` you pass to `build_projections_statline.py`) — which season/week of player history to average. Both scripts filter strictly to games *before* the target week, within that one season's file — there's no cross-season carryover built into them.
2. **Schedule/opponent resolution AND vegas lines** — figuring out who's actually playing whom this slate, and what the real vegas lines are. Vegas is now handled entirely separately (see below); schedule/opponent resolution is still driven by `--season`/`--week` inside `build_projections_statline.py`.

**The rule:**

| Slate type | `--season` | `--week` | Why |
|---|---|---|---|
| Preseason | `2025` | `23` | No real current-season history exists yet. Week 23 doesn't exist in nflverse's real schedule (REG goes 1–18, POST 19–22), so it's a safe sentinel that reliably forces the salary-file Game-Info fallback for opponent resolution — which correctly reads the real matchups straight off your DK/FD export. |
| Madden Sim / any off-season test slate | `2025` | `23` | Same reasoning — there's never real schedule data for these regardless of the real calendar date. |
| **Real regular season, Week 1** | `2025` | `23` | **Same as above, and this is the one easy mistake to make** — Week 1 has zero *real* same-season history no matter what year it is, so the "borrow last season's near-full history" trick is still correct here, not just for preseason. The Game-Info fallback still fires (week 23 still doesn't exist), and still correctly reads the real matchups from your salary file's own Game Info column. |
| **Real regular season, Week 2 and onward** | `2026` (the actual current season) | The actual real week number (e.g. `5`) | Once real 2026 games have been played, this becomes the CORRECT choice — real history exists, so use it directly rather than a stale 2025 proxy. This also flips schedule/opponent resolution over to nflverse's real schedule as the primary path (not the Game-Info fallback), since week 5's real games actually exist in `schedules_2026.parquet` by then. |

**Vegas is no longer tied to `--week` at all.** It's pulled fresh per-slate via `vegas_odds.py --slate-id {slate_id}` (see Step 2d below) — there's no week-matching to get wrong here anymore, and no risk of an old file under a reused week number getting silently picked up.

**How to check which convention applies:** if this is Week 1 of a real season (or preseason, or Madden Sim), use `2025`/`23`. If it's a real Week 2+ slate, use the actual current season/week.

---

## Madden Sim slates — what to expect

Madden Sim slates are supported for pipeline testing. A few things to know:

- **Skill player projections** are 2025 season averages — historical production only, with neutral 1.0 multipliers for matchup and Vegas, unless real Week 1-style Vegas lines happen to be posted and match (see the Game Totals panel note below).
- **DST projections** use the same distributional model as every other slate, with opponent correctly resolved from the salary file's own Game Info pairing (Session 13.5b bug fix — see below).
- **Game totals panel in the UI**: as of Session 13.5b, this now correctly shows the SAME game your skill players and DST agree on — either real matched vegas numbers if a line exists for that pairing, or stays legitimately empty if no matching line exists yet (common for Madden/preseason pairings that don't correspond to any real scheduled game). **This replaces an earlier note that described the panel showing "real NFL games instead of your Madden matchups" as expected/cosmetic — that was actually a bug (DST's opponent resolution bypassing the Game-Info fallback), fixed in Session 13.5b. If you ever see the panel showing a mismatched game again, that's a real bug, not expected behavior — flag it.**
- Madden Sim slates are useful for validating the pipeline and practicing lineup construction with real projections.

---

## Showdown/Single-Game slates — what to expect

Showdown (DK "Captain Mode") and Single Game (FD) slates follow the exact same Stage 1–5 flow as a classic slate, with a small number of concrete differences called out at each step below (search this doc for "Showdown" to find them all). The high-level shape:

- **Roster:** 1 Captain/MVP slot (1.5x salary AND 1.5x points) + 5 FLEX slots on DK, or 1 MVP slot + 4 FLEX slots on FD. Any position is eligible in every slot — there's no QB/RB/WR/TE/DST breakdown like classic.
- **One extra flag at ingest:** `ingest_salaries.py --format showdown` (Step 2f). This is the one step where forgetting the flag doesn't error — it silently ingests as classic instead, so it's worth double-checking.
- **Everything downstream auto-detects:** `build_projections_statline.py` and the UI both detect Showdown from the ingested file itself — no other command changes.
- **UI adapts automatically:** once a Showdown pool is loaded, the Build panel hides Stack Mode, Min Projection, Min Total Ownership, FLEX Eligible Positions, and Game Exposure Caps (none of these apply to a 2-team, no-stacking-yet Showdown pool) and shows a **Min Team Players** control instead — a floor (not a cap) on how many players must come from one team, useful for forcing a lopsided build. The Player Pool list also gets a **K** tab (kickers only show up on Showdown slates) and shows `(CPT)`/`(MVP)` badges next to a player's name, since each player appears twice in the pool — once at Captain price/points, once at FLEX price/points.
- **Bulk-upload export shape is different:** the Stage 5 download produces `CPT,FLEX,FLEX,FLEX,FLEX,FLEX` (DK) or `MVP,FLEX,FLEX,FLEX,FLEX` (FD) columns instead of classic's `QB,RB,RB,WR,WR,WR,TE,FLEX,DST`. Paste into the Showdown/Captain Mode (or FD Single Game) entries file, not the Classic one.
- **Validation status:** DK Showdown's column shapes (CPT/FLEX salary and role linking) were measured against a real DK Captain Mode export, and a real preseason ARI/CAR Showdown slate has now been run fully end to end, including a correct DST opponent/implied_total/over_under fix (Session 13.5b). FD Showdown's 1.5x MVP salary mechanic was confirmed against a live FD roster builder, but a full FD Showdown slate hasn't been run end to end through this pipeline yet — same "DK first, FD second" caution as classic slates.
- ~~**`current_slate.json` tracks one slate per site.**~~ **RESOLVED (Session 16.x).** `current_slate.json` now holds a list, so a Classic slate and a Showdown slate (or any other combination) can both refresh automatically at the same time for the same site — add a separate entry for each in Step 2g. No manual re-running needed just to keep both current.

---

## Stage 1 — New slate posted

DK and FD post the week's contests. Nothing in the pipeline reacts to this automatically — it's just your trigger to start Stage 2.

---

## Stage 2 — Manual weekly kickoff

Open PowerShell and navigate to your repo root before running any commands:

```
cd C:\Users\gmsco\Desktop\DFS_Optimizer
```

---

### Step 2a — Reserve your entries

On DK and/or FD, reserve your max entries in the target contest(s) using placeholder/dummy lineups. This holds your spot before you've built anything real.

---

### Step 2b — Export the salary CSV, and save it where the pipeline expects it

On the DK or FD contest page, click **Export to CSV**.

**Save it to `data\raw_salaries\`, renamed to match your slate ID** (chosen in Step 2c below) — e.g. `data\raw_salaries\dk_classic_wk5.csv`. This folder exists specifically for this. Renaming it up front means you can tell which file is which months from now, and matches what `ingest_salaries.py`'s own docstring already assumes.

**Showdown:** export from the DK **Captain Mode** contest page or FD **Single Game** contest page specifically — this is a separate export button from the Classic contest page, not the same file.

---

### Step 2c — Choose a backend slate ID

Pick a short, filesystem-safe identifier. This names the salary file, the vegas file, AND the final projections output file. Use lowercase with no spaces:

| Slate type | Example slate ID |
|---|---|
| Regular season, main slate | `classic_wk5` |
| Early Sunday only | `early_wk5` |
| Afternoon only | `afternoon_wk5` |
| Preseason | `preseason_wk1` |
| Madden Sim | `madden_07312026` |
| Thanksgiving | `thanksgiving_2026` |
| Showdown/Single-Game | `showdown_wk5` |

**Use the SAME slate ID for both DK and FD when they're the same real-world slate.** Vegas lines are pulled once and shared between sites via this ID (`--vegas-slate-id`, Step 2e) — if DK and FD get different slate_id strings for the same slate, you'll need to pass `--vegas-slate-id` explicitly when building FD's projections (Step 2i) to point at the same vegas pull, or you'll end up pulling and paying for vegas lines twice.

You'll use this same slate ID in Steps 2b through 2k. The output file will be named `output/final_projections_dk_{slate_id}.csv`.

---

### Step 2d — Refresh nflverse data

This pulls the nflverse stats, schedules, rosters, and team stats that the projection scripts depend on.

**Pull BOTH the stats-lookback season AND the current season in one call:**

```
python scripts/ingest_historical.py --season 2025 2026
```

Why both: `2025` drives stats lookback as always (see the table above). `2026` is needed to catch true rookies/zero-snap players — `weekly_rosters_2026.parquet` is what lets a genuine 2026 draft prospect get matched even before they've logged a single real-season snap (Session 13.5b's rookie-matching fix). Roster data populates in preseason; player-level *stats* don't exist until games are actually played, so **it's normal and expected to see a note like this for the current season before Week 1 kicks off:**

```
NOTE: no weekly stats available yet for season 2026 (season hasn't started / no games played yet) -- skipping. Re-run once games begin.
```

That's not an error — 2025 (and schedules/rosters/games for both seasons) still get written normally. Once real games start, re-running this same command will pick up 2026's stats automatically.

Run this once at the start of each season, and any time a later step fails with a `.parquet not found` error.

---

### Step 2e — Pull fresh Vegas lines

```
python scripts/vegas_odds.py --slate-id {slate_id}
```

Replace `{slate_id}` with the ID you chose in Step 2c. **Do this every time, right before ingesting the salary file** — vegas is no longer tied to a week number, so there's no "reuse an old file" risk anymore, but the lines themselves can move, so pulling fresh each time is still the right habit.

Expected output: `Wrote N team rows (M games) to output\vegas_implied_totals_{slate_id}.csv`. If you see `ERROR: ODDS_API_KEY not found`, double check `config/api_keys.env` has the line `ODDS_API_KEY=your_key_here` — if it's genuinely there and this still fails, the file may have been saved with an encoding quirk; contact Claude.

---

### Step 2f — Ingest the salary file

Replace `dk_classic_wk5.csv` with your actual filename and `classic_wk5` with your slate ID:

```
python scripts/ingest_salaries.py --site dk --raw data/raw_salaries/dk_classic_wk5.csv --season 2025 --slate-id classic_wk5
```

`--season` here stays `2025` regardless of slate type — it's the stats-lookback convention from the table above, unrelated to which real calendar year the slate is in. The script automatically looks for `data/weekly_rosters_2026.parquet` (current season) for rookie-matching — no extra flag needed as long as Step 2d already pulled it.

Expected output includes a match rate summary and, if any true rookies/zero-snap players are on this slate, a line like:

```
build_player_reference: added N roster-only player(s) with no weekly_stats row (true rookies / zero-snap players) from data\weekly_rosters_2026.parquet.
```

**This line is expected and good** — it means Session 13.5b's rookie-matching fix is working, not a warning to worry about.

**Showdown:** add `--format showdown`. This defaults to `classic` if omitted, and omitting it on a Showdown file does NOT error — it silently ingests the file as if it were a classic slate (wrong roster shape, no CPT/FLEX role linking), so double-check this flag is present:

```
python scripts/ingest_salaries.py --site dk --raw data/raw_salaries/dk_showdown_wk5.csv --season 2025 --slate-id showdown_wk5 --format showdown
```

With `--format showdown`, you may also see a warning like:
```
WARNING: 2 matched player(s) don't have both {'CPT', 'FLEX'} rows linked to the same player_id
```
This means a player's Captain-priced row and FLEX-priced row matched to different (or missing) player_ids — usually an unmatched-player issue (see below), not a bug. Resolve it the same way as any other unmatched player, then re-run and confirm the warning clears.

**Handling unmatched players:**

The script lists any players it couldn't match. As of Session 13.5b, a genuine rookie or zero-snap player should already be caught automatically — anyone still on this list is almost always a real name-spelling/nickname mismatch (e.g. a player's DK name doesn't match their nflverse name closely enough even after normalization). For each one:

1. Search for them in nflverse (replace `Smith` with their last name):
```
python -c "import pandas as pd; df = pd.read_parquet('data/weekly_stats_2025.parquet'); print(df[df['player_name'].str.contains('Smith', case=False, na=False)][['player_id','player_name','position','team']].drop_duplicates())"
```

If that comes back empty and you believe they're a real rookie, also check the current-season roster file:
```
python -c "import pandas as pd; df = pd.read_parquet('data/weekly_rosters_2026.parquet'); print(df[df['full_name'].str.contains('Smith', case=False, na=False)][['gsis_id','full_name','position','team']].drop_duplicates())"
```

2. If you find a clear match, add them to `data/name_mapping.csv`:
```
Add-Content data\name_mapping.csv "dk,{DK Name},{TEAM},{POS},{player_id},matched via nflverse 2025"
```

3. Re-run the ingest command to confirm your additions resolved. Players with genuinely no nflverse match at all are fine to leave unmatched — they will project from Vegas/matchup factors only.

If you get an unexpected error, contact Claude.

---

### Step 2g — Add this slate to `data/current_slate.json`

**Updated (Session 16.x rework):** `current_slate.json` used to hold exactly one DK slate and one FD slate at a time — that broke down as soon as you wanted to play more than one slate per site in the same week (main + early-only, or a Showdown alongside a Classic slate). It now holds a `"slates"` list with room for as many active slates as you're actually playing, across both sites, at once.

Open `data/current_slate.json` in any text editor and **add one new entry to the `"slates"` list** — don't replace the whole file, just append:

```json
{
  "slate_id": "classic_wk5",
  "site": "dk",
  "format": "classic",
  "season": 2025,
  "week": 23,
  "lock_time_utc": "2026-10-12T17:00:00Z"
}
```

Field by field:
- **`slate_id`** — the same ID you chose in Step 2c.
- **`site`** — `"dk"` or `"fd"`.
- **`format`** — `"classic"` or `"showdown"`, matching Step 2f's ingest.
- **`season`** — same meaning this field always had here: the stats-lookback season from the table above (`2025` for Week 1/preseason/Madden, the real current season for Week 2+).
- **`week`** — same meaning as before: `23` for Week 1/preseason/Madden, the real week number for Week 2+.
- **`lock_time_utc`** — new field. This slate's real lock time, converted to UTC, in the exact format shown (`YYYY-MM-DDTHH:MM:SSZ`). **DK and FD always display lock times in Eastern — you must convert to UTC before entering it here.** Eastern-to-UTC is +4 hours during Daylight Time (roughly March–November, which covers the entire NFL regular season) or +5 hours during Standard Time. Example: a 1:00 PM ET Sunday lock becomes `17:00:00Z` the same calendar day. This field controls only one thing — whether the automated refresh keeps updating this slate or treats it as done. It has no effect on when cron-job.org's near-lock ping fires (that's a separate setting, covered under Finding 2).

**If you're playing multiple slates this week** (e.g. DK Main + DK Early-only + DK Showdown), repeat this step once per slate — add a separate entry for each, all in the same `"slates"` list. There's no limit on how many can be active at once, and each is refreshed independently.

**Cleanup:** once a slate's lock has passed, you can leave its entry in place (the workflow automatically skips anything past `lock_time_utc` plus a 5-minute buffer) or remove it by hand to keep the file tidy. Neither is required.

---

### Step 2h — Build baseline and matchup projections

Use the week/season from the table above:

```
python scripts/projections_baseline.py --site dk --season 2025 --week 23
```

```
python scripts/projections_matchup.py --site dk --season 2025 --week 23
```

No output (beyond the write confirmation) means success. An error means contact Claude.

**Showdown:** no changes here — both scripts run per `--site --season --week` and don't know or care about slate format.

---

### Step 2i — Build final projections

**Session 14.0 (2026-08-06): this step now uses `build_projections_statline.py`, not `build_projections.py`.** The old script is still in the repo (kept for reference/rollback) but is no longer part of the live pipeline — `refresh_data.yml`'s automated refresh switched over in the same session, so this manual step needs to match it.

Use the same `--week`/`--season` and `--slate-id`, and **explicitly pass `--volume-prior --sigma-recalibration --dst-model distributional`** — the first two are opt-in/off-by-default in this script, and omitting them silently ships a weaker version of the engine (no price-implied volume prior, no sigma dispersion correction):

```
python scripts/build_projections_statline.py --site dk --season 2025 --week 23 --slate-id classic_wk5 --volume-prior --sigma-recalibration --dst-model distributional
```

`--vegas-slate-id` defaults to `--slate-id` automatically, so you don't need to pass it unless DK and FD ended up with different slate_id strings for the same real slate (see Step 2c) — in that case add `--vegas-slate-id {the-id-you-actually-pulled-vegas-under}` to FD's build command.

Expected output: several informational lines, no ERROR. The file `output/final_projections_dk_{slate_id}.csv` is created. Check the last few lines for validation output — `Nulls in any legacy column: 0`, `Negative final_projection: 0`, `Positive projection but zero sigma: 0`, etc. should all read 0. If any of these are nonzero, the output will now tell you exactly which column is affected — contact Claude with that detail.

**You may also see a `NOTE share reconciliation:` block listing a small number of team/component pairs needing a rescale.** This is normal and expected — it means the model is correcting for real depth-chart situations (an injury, a backup taking over). One or two teams showing up here on an ordinary week is healthy, not a bug. What's NOT normal is a `statline share reconciliation FAILED` message with `SystemExit` — that's the mandatory fail-loud stopping the run because something is structurally wrong (widespread violations across many teams at once, not one team's real situation). If you see that, stop and contact Claude with the full output rather than re-running or trying to work around it.

For Madden Sim, preseason, and real Week 1 slates you will also see:
```
NOTE: schedule has no week-23 games for slate teams -- falling back to vegas over_under pairing (decision #9, Madden Sim path).
  Inferred N game(s) from salary file: [(...), (...)]
```
**This is expected and correct for ALL of these slate types, not just Madden** — it's how Week 1 opponent resolution reliably works (see the table above). Confirm the inferred games match what you actually expect from the real slate.

If you see an error about a missing `.parquet` file, run Step 2d and retry.

**Showdown:** no flag needed here either — this script auto-detects Showdown from the `--format showdown` tag `ingest_salaries.py` stamped onto the salary file in Step 2f, and builds the CPT/MVP + FLEX pool rows automatically.

---

### Step 2i-props — Pull player-prop lines and blend them into the projections (new, Week 2 post-mortem)

Sportsbook player props (receiving yards, receptions, rushing yards, passing yards, passing TDs, anytime TD) are converted to expected stat means and blended (default 50/50) into the stat-line engine's per-player inputs. Over 2026 Weeks 1-2 the anytime-TD price alone explained more fantasy-point variance than the engine did, so this is on by default whenever a fresh snapshot exists.

**Pull the snapshot ONCE per slate, as close to lock as is practical (props move with injury news), AFTER the salary file is ingested (Step 2f):**

```
python scripts/props_ingest.py --site dk --slate-id {slate_id}
```

It reads the slate's salary file to find its games, refuses to spend if the estimate exceeds `--max-credits` (default 120) or the account is nearly out, and writes `data/props/props_{slate_id}.csv` (+ `events_{slate_id}.csv`, and timestamped raw JSON under `data/props/raw/`). Cost is 6 credits per game (6 markets x 1 region): a 16-game week is ~96 credits, a single showdown game 6. Uses `ODDS_API_KEY_PROPS` if set (env or `config/api_keys.env`), else `ODDS_API_KEY`.

**Automatic pull (in place since 2026-09-21):** `refresh_data.yml`'s shared_pull job runs `scripts/props_auto.py` on every full-mode run. It pulls props for any slate in `data/current_slate.json` that locks within ~100 minutes and has no snapshot from the last 2 hours; games shared by several slates are pulled once, and each slate is handled near its own lock (Thursday night, Sunday classic, Sunday night and Monday night are separate pulls). One-time setup: add the GitHub Actions secret `ODDS_API_KEY_PROPS` (Settings -> Secrets and variables -> Actions); without it the pull falls back to `ODDS_API_KEY`. The Sunday-night slate has no scheduled run near its lock: either add a `15 23 * * 0` cron or have the cron-job.org near-lock dispatch fire for it. Manual pull (above) still works any time.

**Then rebuild projections (Step 2i).** `build_projections_statline.py` picks up `data/props/props_{slate_id}.csv` automatically (`--props-weight 0.5` default; `--props-weight 0` turns it off). No snapshot, a snapshot older than 72 hours, or any error means "engine only" - it never blocks a build. The build prints how many players were matched and adjusted, and the output carries `props_*_engine` / `props_*_market` audit columns. Commit the props CSVs so the GitHub refresh builds use them.

---

### Step 2i-recommend — Generate the recommended lineup (new, 2026-09-23)

**This is a completely SEPARATE feature from Step 2j / "Build Lineups" below — it does not read, use, or pick from anything you build there.** `recommend_lineup.py` builds its OWN independent pool of ~80-130 candidate lineups straight from `final_projections` (a mix of unconstrained noisy solves and QB-stack-forced solves), Monte Carlo-scores every one of them across 4 correlated game-environment scenarios, and picks the single lineup with the best WORST-CASE probability of finishing top-25% of the field, restricted to real QB+teammate stack structure. "Build Lineups" and the SE/3-Max GPP preset are a different feature entirely (manual multi-lineup GPP portfolio construction) that happens to read the same `final_projections` file — that's the only thing they share.

**Only prerequisite: Step 2i (final projections) must exist for this slate.** No lineup batch, no "Build Lineups" run, nothing else needed first — this is the one difference from Step 2j's pivot suggestions, which DO need a lineup batch to exist before they'll generate.

```
python scripts/recommend_lineup.py --site dk --slate-id classic_wk5
```

Writes `output/recommended_lineup_dk_classic_wk5.csv`. Takes 15-220 seconds depending on slate size.

**You don't actually have to run this manually every week.** `refresh_data.yml`'s automated Stage 3 refresh runs it on every scheduled/near-lock cycle for every active slate in `current_slate.json` — the moment Step 2i has been pushed, the next automated run generates it with zero further action, same "keeps itself current all week" behavior pivot suggestions already have. Run it manually here only if you want to see it immediately rather than wait for the next scheduled refresh.

**Only the ownership-independent method is live right now** (`worst_top25_realstack` — 3/6 cash, 0.703 mean percentile on 6 real logged slates; see `HANDOFF_week3_lineup_system.md`). A stronger chalk-anchor + ownership-driven-pivot method tested at 4/6, 0.819 in validation, but three separate live-substitution tests (feeding it the model's own pre-lock ownership estimate instead of real post-lock data) found the pivot layer added zero value on all 6 slates — it's intentionally left out until projection/ownership model accuracy improves and it's re-validated. Don't expect to see any leverage/pivot swaps in this output — a plain single lineup with no differentiation notes is the current expected shape, not missing functionality.

---

### Step 2j — Build a first lineup batch and generate pivot suggestions (optional, recommended)

This step is optional, but doing it now — right after projections, before pushing — means Stage 3's automated refresh loop keeps your pivot suggestions current for the rest of the week without you touching anything again, right up to lock.

**Why here, not later:** `pivot_finder.py` needs a built-lineup file to work from, and the automated refresh only regenerates pivots once one already exists for a slate. Seeding that now means Stage 3 keeps both projections AND pivots fresh from here on automatically. Build a lineup batch directly (not through the deployed UI — the UI's Build Lineups button dispatches to GitHub, which only sees what's already been pushed; this runs locally, against the file Step 2i just wrote, before anything's pushed):

```
python scripts/optimizer.py --site dk --slate-id classic_wk5 --n-lineups 20
```

Then generate pivot suggestions from that batch:

```
python scripts/pivot_finder.py --site dk --slate-id classic_wk5
```

Repeat both for FD if you're building there too. `pivot_finder.py`'s output will include `WARNING`/`NOTE` lines for individual players — each line explains itself (a thin pool at that tier, or a partial candidate list) and is expected, not something to fix.

**This lineup batch is NOT your real lineup** — it's a rough, disposable batch built purely to give `pivot_finder.py` something to work from. Build your actual lineups the normal way, later, through the deployed UI (Stage 4), with your real stacking/exposure/randomization settings. Rebuilding your real lineups later doesn't invalidate anything here — it overwrites this rough batch at the same file path, and Stage 3's next automated refresh will regenerate pivots from that newer, real batch automatically.

**Once pivots exist for a slate, the UI shows them with no upload step.** As of Session 15, the deployed UI reads `output/pivot_suggestions_{site}_{slate_id}.csv` live from GitHub every time you load that slate — not a manual upload, not a cached snapshot. Generate it once here, push it in Step 2k below, and every automated refresh for the rest of the week keeps it current with zero further action from you. Click any roster row on a built lineup in the UI to see the pivot panel.

---

### Step 2j.5 — Pull public projected ownership (FFC), then rebuild projections

The layered ownership model uses Fantasy Football Calculator's free projected ownership as a feature (leave-one-week-out on wk1/wk2: corr 0.676 → 0.764, chalk bias −6.8 → −4.1). **Stage 3's automated refresh already does this for every active classic DK slate on every full run** (`refresh_data.yml` → "Pull public projected ownership (FFC)", before "Rebuild projections"), so you only need to run it by hand to see it immediately:

```
python scripts/ingest_public_ownership.py --site dk --slate-id classic_wk5
python scripts/build_projections_statline.py ...   (same command as Step 2i)
```

It saves `data/ownership_public/ffc_dk_{slate_id}.csv` (committed with `data/`). Check the printed "players match" lines: the chosen FFC slate (Main / Early Only / Afternoon Only) should be the one matching your slate. **Never required** — if the site is down, the format changes, or no slate matches, nothing is written and the build silently falls back to the model without it (look for "Ownership: using public-ownership (FFC) variant" in the build log to confirm it was used). FanDuel and Showdown are not covered.

---

### Step 2k — Commit and push

```
git add data/ output/
```

```
git commit -m "Slate classic_wk5 - ingest complete"
```

```
git push
```

Once pushed, Stage 3 takes over automatically. **This step is also required before Stage 4 works** — the optimizer runs on GitHub's servers (via the Cloudflare Worker dispatch), and only sees what's actually been pushed, not what's sitting locally on your machine. If you build lineups and get `FileNotFoundError: .../output/final_projections_....csv not found`, this is almost always the fix — you rebuilt projections locally but forgot to push.

---

## Stage 3 — Automated refresh loop

Once Stage 2 is pushed, this runs unattended until lock:

| Trigger | Cadence | What it refreshes |
|---|---|---|
| Light Vegas refresh | Tue–Fri 1x/day, Sat 2x/day, Sun hourly | Vegas lines only |
| Full refresh (scheduled) | Every 3 hours, Thu/Sun/Mon | Vegas + injury/active status + full projection rebuild, every active slate |
| Full refresh (near-lock) | Every ~10 min, during each configured near-lock window | Same as above, fired by Cloudflare Worker |

**Updated (Session 16.x rework):** a full refresh now rebuilds `output/final_projections_{site}_{slate_id}.csv` for **every slate currently listed in `data/current_slate.json`**, not just one per site — if you added three entries in Step 2g, all three get refreshed on the same run. Players ruled OUT are zeroed, per slate. Players flagged DOUBTFUL/QUESTIONABLE are marked but not zeroed.

**Vegas and injury/active status are pulled once per run, not once per slate**, and shared across every active slate that run refreshes — these are properties of the real game, not the slate, so there's no reason to pull them twice for, say, DK Main and DK Early-only covering the same Sunday games. If that shared pull fails for any reason, every slate falls back automatically to whatever Vegas/status data was last pulled successfully, and a warning is logged — a slate never goes fully unrefreshed just because one shared pull had a bad moment.

A slate whose `lock_time_utc` (Step 2g) has already passed is automatically skipped by the refresh loop — no action needed to "turn it off."

Check `logs/automation_run_log.csv` if you want to confirm a specific slate actually got refreshed on a given run — it now has a `slate_id` column so you can see each active slate's own build/apply/pivot outcome per run, not just a single pass/fail for "both sites."

You don't need to do anything during Stage 3 for **building** to benefit — every "Build Lineups" click always reads whatever's freshest on GitHub at that moment, regardless of what's in your browser. What you *see* in the UI's pool table is a different story: it's a frozen snapshot from whenever you last uploaded it (**Choose File** → **Save**, Stage 4), and does not visually update on its own. If you want the displayed numbers themselves to reflect the latest refresh — not just what a build will actually use — re-upload the current `final_projections_{site}_{slate_id}.csv` the same way. **Pivot suggestions (Step 2j) are the one exception to all of this — they display live, automatically, with no re-upload ever needed (Session 15).** The underlying file still only gets *generated* from a lineup batch that has to exist first (Step 2j creates that), but once it does, Stage 3's refreshes keep it current on GitHub and the UI always shows whatever's there.

---

## Stage 4 — Build & preview lineups

Open the deployed UI at **https://dfs-optimizer.pages.dev**.

### Loading a slate

1. In the **Slates** panel, click **Choose File…** and select your projections file — e.g. `output/final_projections_dk_classic_wk5.csv`.
2. A name field appears. Replace the pre-filled filename with a short readable label, e.g. `Week 5 Main`. This is for your own navigation only.
3. Click **Save**. The slate is stored locally and synced to the cloud.
4. It appears in the dropdown and is automatically selected.

The label has no effect on the backend. Name it anything.

### Multiple slates for the same week

Upload the same CSV multiple times with different labels. Both appear in the dropdown and are stored as completely separate entries.

### Switching between slates

Use the dropdown. Each slate loads its own player pool, projections, and any lineups already built against it. Switching is instant.

### Cross-device access

Slates sync to the cloud automatically when saved. On a second device, open the UI and wait — the slate appears in the dropdown and auto-loads.

### Deleting a slate

Select it in the dropdown and click **Delete**. Removes it from this browser and the cloud.

### Building lineups

Set your options in the Build panel and click **Build Lineups**. Review all lineups before exporting. If lineups look wrong, contact Claude before proceeding.

### Before lock — review name-recognition flags

Spend 15-20 minutes on `data/name_recognition_flags.csv` before you finalize lineups. This is the manual "fame/hype" ownership bonus (chalk names, hyped rookies, big names returning from injury) that the chalk-score model can't infer on its own. Add/update rows for this week's real judgment calls — the file ships with only one example row (Patrick Mahomes) and needs real entries to do anything useful for the current slate.

**Participation Floors** (Session 15): a new Build panel field, on by default (`QB:0.6,RB:0.4,TE:0.4`). Excludes a player from the pool if he's barely shown up in his team's last 5 games — catches a real backup, or a player still out injured, that a point projection alone can miss. If you know a player is a legitimate exception (e.g. a starter you know is back from injury at full workload, even though his recent-games history hasn't caught up to that yet), **Lock** him in — a lock always overrides the floor. Clear the field entirely to turn the floor off for a build.

### Pivot suggestions (cash-to-GPP)

Generated back in **Step 2j**, not here — see that step for how to create or refresh them. If you did that step, pivot suggestions are already showing: the UI reads `output/pivot_suggestions_{site}_{slate_id}.csv` live from GitHub every time you load a slate, no upload needed. Click any roster row on a built lineup to see the pivot panel. If nothing shows, either Step 2j hasn't been run for this slate yet, or the file hasn't been pushed (Step 2k).

### Recommended Lineup panel (new, 2026-09-23)

Shows up automatically as its own panel (open by default, above Exposure Summary) once you load a slate — reads `output/recommended_lineup_{site}_{slate_id}.csv` live from GitHub, same no-upload-needed pattern as pivot suggestions. **Completely independent of "Build Lineups" and the Build panel above** — see Step 2i-recommend for what actually generates it, why it's a separate method, and why it currently shows no pivot/leverage swaps. If the panel says nothing's been generated yet, either Step 2i (final projections) hasn't completed and been pushed for this slate, or the automated refresh hasn't run since it did — run Step 2i-recommend manually to see it immediately rather than waiting.

### Slate Overview — Game Totals panel

Shows each game's real vegas over/under, grouped from the loaded pool's own opponent/over_under columns. As of Session 13.5b, this is guaranteed consistent with DST's own opponent/implied_total/over_under — if it's empty, that means no matching vegas line exists for one or more pairings yet (common right after a slate posts, before books have lines up), not a bug. If it shows a game that clearly doesn't match your slate's real matchups, that IS a bug — contact Claude.

### Showdown slates in the UI

Loading a Showdown pool changes the Build panel and Player Pool automatically — nothing to toggle by hand:

- **Player Pool:** a **K** tab appears (kickers only show up on Showdown slates), and each player's name shows a `(CPT)` or `(MVP)` badge next to their FLEX-priced row's counterpart, since every player has 2 pool rows (Captain-priced and FLEX-priced) with different salary/projection. Locking or excluding a player applies to either role — there's no way to lock someone specifically as Captain vs. FLEX yet.
- **Build panel:** Stack Mode, Minimum Projection, Minimum Total Ownership, Participation Floors, FLEX Eligible Positions, and Game Exposure Caps all disappear (none apply to Showdown yet). **Min Team Players** appears in their place — a floor, not a cap, on how many roster spots must come from one team. Use it to force a lopsided build (e.g. floor one team at 4 of the 6 DK slots). Team Exposure Caps still works normally for Showdown.
- **Roster display:** built lineups show Captain/MVP first, then FLEX1–FLEXN, in that order.

---

## Stage 5 — Export & re-upload

Click **Download Lineups for DraftKings Import**. Upload that file back into DK to replace your placeholder lineups.

**Showdown:** the downloaded file uses `CPT,FLEX,FLEX,FLEX,FLEX,FLEX` columns on DK or `MVP,FLEX,FLEX,FLEX,FLEX` on FD — different from classic's `QB,RB,RB,WR,WR,WR,TE,FLEX,DST`. Make sure you're uploading into the Captain Mode / Single Game bulk-entry template, not the Classic one, or DK/FD will reject it.

Lock hits. Done.

---

## Stage 6 — Log actual ownership

**This is a real, required weekly step — not optional.** `scripts/log_ownership.py` builds the dataset Sessions 11.1/11.2 need to fit ownership model parameters against reality (a 4-6 week data gate). It does nothing unless you actually run it every week.

Do this once DK posts post-lock ownership percentages on the contest results page — usually within an hour or two of lock, for large-field GPPs (DK Millionaire Maker and similar). There is no API for this; it's a manual copy-paste.

**FanDuel does not publish a copyable post-lock ownership page, and there is no legitimate way to derive real ownership from anywhere else this pipeline has access to** (confirmed 2026-09-14 — real box-score stats and DK's own ownership can reconstruct FD's real *points*, see Stage 7 below, but who actually drafted which players in a real FD contest is fundamentally unobservable from here). Don't fabricate or estimate FD ownership rows to fill this gap — `data/ownership_actual_log.csv` staying DK-only is the correct, documented state, not a bug to work around. Log FD ownership only if FD itself ever starts publishing a real post-lock page.

1. **Build the raw ownership CSV.** Copy player names and ownership percentages off the results page into a new CSV under `data/`, e.g. `data/ownership_raw_dk_2026_wk5.csv`.
   - Classic slates: two columns — `player_name, actual_ownership_pct`
   - Showdown slates: three columns — `player_name, roster_role, actual_ownership_pct` (`roster_role` must be exactly `CPT`/`FLEX` for DK or `MVP`/`FLEX` for FD)
   - See `scripts/log_ownership.py`'s own module docstring for full details on the raw CSV shape.

2. **Run the logger:**

```
python scripts/log_ownership.py log --site dk --season 2026 --week 5 --slate-id classic_wk5 --slate-type regular_season --contest-type single_entry_gpp --field-size 150000 --input data/ownership_raw_dk_2026_wk5.csv --source "DK Millionaire Maker results page 2026-10-12"
```

Use the SAME `--slate-id` you used for this slate all week (Step 2c) — the script reads `output/final_projections_{site}_{slate_id}.csv` to match players. Repeat once per site/slate you played (DK and FD are logged separately; a Classic and Showdown slate in the same week are also logged separately).

3. **Check the output.** It reports match rate and prints a `DATA GATE:` line showing how many regular-season weeks are logged toward the 4-6 week minimum. Any unmatched players are written to `data/ownership_unmatched_{site}_{slate_id}.csv` — add real fixes to `data/name_mapping.csv` and re-run if it's worth resolving.

4. **Commit the result** — `data/ownership_actual_log.csv` is a growing dataset that lives in the repo, same treatment as `name_mapping.csv`:

```
git add data/ownership_actual_log.csv data/ownership_raw_dk_2026_wk5.csv
```
```
git commit -m "Log actual ownership - DK wk5"
```
```
git push
```

Run `python scripts/log_ownership.py summary` any time to see what's been logged so far without adding anything.

---

## Stage 7 — Log actual results (actual vs. projected)

**Also a real, required weekly step, same reasoning as Stage 6.** `scripts/log_results.py` (Session 9.1) builds the dataset Session 9.2 needs to eventually retune projection blend weights — it does nothing unless you run it every week.

Do this once real box scores are final for the slate.

**DK:** its own contest-results export already includes each player's actual site-scored fantasy points (DK's "Export to CSV" from a completed contest's results page has a `FPTS` column), so no separate box-score lookup is needed.

1. **Build the raw results CSV.** Two columns: `player_name, actual_fpts` — one row per player, deduped (unlike Stage 6's ownership export, DK's raw export may list a player more than once across position/FLEX rows with the *same* FPTS value each time; keep one).

**FD:** FD does not publish a results export with fantasy points either. Use `scripts/derive_actual_results.py` instead (confirmed 2026-09-14) — it computes FD's real fantasy points directly from real nflverse box-score stats via `scoring_rules.py`'s already-verified site-exact scoring tables, independent of DK's own numbers, once `ingest_historical.py --season {season}` has been re-run for the week's completed games:

```
python scripts/derive_actual_results.py --site fd --season 2026 --week 5 --slate-id fd_classic_wk5 --output data/results_raw_fd_2026_wk5.csv
```

This writes the same `player_name, actual_fpts` shape Stage 7 expects — feed it into `log_results.py` exactly like a real DK export (step 2 below). Note this only covers *results*; it cannot and does not produce FD ownership (see Stage 6's FD note).

2. **Run the logger** (same command for both sites, DK's raw CSV or FD's derived one):

```
python scripts/log_results.py log --site dk --season 2026 --week 5 --slate-id classic_wk5 --slate-type regular_season --input data/results_raw_dk_2026_wk5.csv --source "DK contest results export 2026-10-12"
```

Use the SAME `--slate-id` as Stage 6 and the rest of the week (Step 2c) — it reads `output/final_projections_{site}_{slate_id}.csv` for the projection side of the comparison. Repeat once per site/slate.

3. **Check the output.** Reports match rate, mean error, and a `DATA GATE:` line toward Session 9.2's 4-week minimum. Unmatched players go to `data/results_unmatched_{site}_{slate_id}.csv`.

4. **Commit the result:**

```
git add data/projection_error_log.csv data/results_raw_dk_2026_wk5.csv
```
```
git commit -m "Log actual results - DK wk5"
```
```
git push
```

Run `python scripts/log_results.py summary` any time to see logged error by site/position without adding anything.

---

## Quick reference — full command sequence

Replace the values in braces with your own. Use the season/week table above to pick `{season}`/`{week}` correctly (`2025`/`23` for Week 1 of anything; the real current season/week for real Week 2+).

```
python scripts/ingest_historical.py --season 2025 2026
```
```
python scripts/vegas_odds.py --slate-id {slate_id}
```
```
python scripts/ingest_salaries.py --site dk --raw data/raw_salaries/dk_{slate_id}.csv --season 2025 --slate-id {slate_id}
```
*(Showdown: add `--format showdown` to the command above)*

*(add an entry for this slate to `data/current_slate.json`'s `"slates"` list -- season/week/slate_id/site/format/lock_time_utc, see Step 2g)*
```
python scripts/projections_baseline.py --site dk --season {season} --week {week}
```
```
python scripts/projections_matchup.py --site dk --season {season} --week {week}
```
```
python scripts/build_projections_statline.py --site dk --season {season} --week {week} --slate-id {slate_id} --volume-prior --sigma-recalibration --dst-model distributional
```
*(optional -- generates immediately instead of waiting for the next automated refresh; see Step 2i-recommend)*
```
python scripts/recommend_lineup.py --site dk --slate-id {slate_id}
```
```
git add data/ output/
```
```
git commit -m "Slate {slate_id} - ingest complete"
```
```
git push
```

---

## Known gaps and reminders

- **Save raw salary exports to `data/raw_salaries/`, named `{site}_{slate_id}.csv`.** This was never stated clearly before — if you've been saving them somewhere else, that's fine too as long as `--raw` points at the real path, but this is the established convention going forward.
- **Vegas is no longer tied to `--week`.** It's pulled fresh per-slate via `--slate-id` (Step 2e) — there's no week-matching to get wrong, and no risk of an old file under a reused week number getting silently reused (this was a real bug, fixed in Session 13.5b).
- **Week 1 of ANY season (real, preseason, or Madden) uses `--season 2025 --week 23`.** Real Week 2+ switches to the actual current season/week. See the season/week table near the top of this doc.
- **`ingest_historical.py --season 2025 2026`** should be run for every slate now, not just once per season — 2026 is needed for the rookie-matching fix (Step 2d). A `NOTE: no weekly stats available yet for season 2026` message before games start is expected, not an error; other seasons in the same call still succeed independently.
- **A "roster-only player(s) added" line from `ingest_salaries.py` is expected and good** — it means a true rookie/zero-snap player was successfully matched instead of silently dropped (Session 13.5b fix).
- **`ingest_historical.py` (Step 2d)** must have been run at least once for the current season. If `build_projections_statline.py` fails with a `.parquet not found` error, run Step 2d and retry.
- **Output filenames use `--slate-id`**, not `--week`: `final_projections_dk_{slate_id}.csv`. Two slates in the same week will not overwrite each other.
- **DK is live-validated end to end** against a real preseason Showdown slate, a real Madden Sim slate, and a real Week 1 2026 regular-season classic slate (all through Session 13.5b). **FD is built identically but has not been tested against a real FD salary export.**
- **Showdown: `--format showdown` on `ingest_salaries.py` (Step 2f) is the one flag that fails silently if forgotten** — it ingests as classic instead of erroring. Everything downstream (`build_projections_statline.py`, the UI) auto-detects from there.
- ~~**Showdown + classic on the same site can't both auto-refresh at once.**~~ **RESOLVED (Session 16.x).** `current_slate.json` now tracks a list of slates, not one per site — a Showdown entry and a Classic entry (or main + early-only + afternoon) can all sit in the list and refresh together. See Step 2g above.
- **DK Showdown's column shapes are measured against a real export and a real ARI/CAR slate; FD Showdown's 1.5x MVP mechanic is confirmed against a live FD roster builder, but neither has been run through a full FD Showdown slate end to end yet.**
- **The near-lock cadence** is configured in cron-job.org, separately from `current_slate.json`. With multiple slates now possible in one week (Thursday, Sunday early/main/afternoon, Sunday night, Monday night), you may need more than one near-lock window configured there — one per distinct lock time you're actually playing that week, not just one flat weekly template. See Finding 2 / Session 16.x's cron-job.org notes for current status.
- **Participation Floors (Session 15) default ON for classic slates** (`QB:0.6,RB:0.4,TE:0.4`) — a player barely showing up in his team's last 5 games gets excluded from the pool automatically. If a build comes back thinner than expected at QB/RB/TE, this is the first thing to check; lock a known exception back in rather than turning the floor off broadly.
- **Pivot suggestions need a lineup batch to exist, generated at Step 2j, but the display itself is fully automatic (Session 15).** The UI reads `output/pivot_suggestions_{site}_{slate_id}.csv` live from GitHub every time you load a slate — no upload, no caching. As long as Step 2j has been run once for a slate and pushed, every automated refresh for the rest of the week keeps it current with zero further action.
- **The Recommended Lineup panel (Step 2i-recommend, 2026-09-23) needs NO lineup batch and is unrelated to "Build Lineups"/the SE-3Max preset** — it's a separate method that builds and Monte Carlo-scores its own candidate pool straight from `final_projections`. Only needs Step 2i to exist; the automated refresh keeps it current from there with zero further action, same as pivot suggestions. Currently ships the ownership-independent `worst_top25_realstack` rule only — no leverage/pivot differentiation yet (see that step for why).
- **If any step produces an unexpected error**, paste the full error message into a Claude conversation. The error message is the fastest path to a fix.
