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

Stages 1, 2, 4, and 5 are things you do. Stage 3 runs unattended once Stage 2 is complete and pushed.

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
- **`current_slate.json` tracks one slate per site.** If you want a classic slate AND a Showdown slate both refreshing automatically at the same time for the same site (e.g. a Sunday main slate plus a Sunday/Monday-night Showdown), Stage 3's automation can only track whichever slate_id is currently set for that site — you'll need to manually re-run `build_projections_statline.py` (with the flags from Step 2i below) for the other one when you want it refreshed, or accept it'll go stale between manual runs.

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

You'll use this same slate ID in Steps 2b through 2i. The output file will be named `output/final_projections_dk_{slate_id}.csv`.

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

### Step 2g — Update `data/current_slate.json`

Open `data/current_slate.json` in any text editor. Update the `dk` (and/or `fd`) block with your week and slate ID — `week` here follows the stats-lookback table above (23 for Week 1/preseason/Madden, the real week number for Week 2+):

```json
{
  "_comment": "...",
  "season": 2025,
  "dk": {
    "week": 23,
    "slate_id": "classic_wk5"
  },
  "fd": {
    "week": 23,
    "slate_id": "classic_wk5"
  }
}
```

Only update the block for the site you ingested. `season` here stays `2025` (the stats-lookback season) even during Week 2+ of a real season — this file feeds automation that hasn't been updated to track a separate real-season value, so leave it as-is unless told otherwise.

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

### Step 2j — Commit and push

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
| Full refresh (scheduled) | Every 3 hours, Thu/Sun/Mon | Vegas + injury/active status + full projection rebuild |
| Full refresh (near-lock) | Every 10 min, final hour before lock | Same as above, fired by Cloudflare Worker |

A full refresh rebuilds `output/final_projections_{site}_{slate_id}.csv`. Players ruled OUT are zeroed. Players flagged DOUBTFUL/QUESTIONABLE are marked but not zeroed. Vegas is pulled fresh each time under the slate_id tracked in `data/current_slate.json` — DK's own slate_id is used for both sites' vegas pulls when they share one.

You don't need to do anything during Stage 3. Check the UI periodically to see projections update as injury news comes in.

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

**Participation Floors** (Session 15): a new Build panel field, on by default (`QB:0.6,RB:0.4,TE:0.4`). Excludes a player from the pool if he's barely shown up in his team's last 5 games — catches a real backup, or a player still out injured, that a point projection alone can miss. If you know a player is a legitimate exception (e.g. a starter you know is back from injury at full workload, even though his recent-games history hasn't caught up to that yet), **Lock** him in — a lock always overrides the floor. Clear the field entirely to turn the floor off for a build.

### Pivot suggestions (cash-to-GPP)

**What this is:** for every player rostered in your built lineups, a ranked list of same-position, similarly-projected, lower-owned alternatives — a starting point for differentiating your GPP entries off whatever you already built.

**Why it needs an extra step (Session 15 fix):** pivot suggestions are generated by a separate script (`pivot_finder.py`), not by the Build Lineups button itself, and — as of Session 15 — that script now correctly reads your real built-lineup file, but the file it produces still isn't picked up by the UI automatically. Two ways to get it:

1. **Wait for the automated refresh.** Once you've built lineups for a slate, the next scheduled refresh cycle (runs automatically, several times a day — see Stage 3) will detect the built-lineup file and generate `output/pivot_suggestions_{site}_{slate_id}.csv`, committed to the repo.
2. **Or run it yourself, right after building, for an immediate result:**
   ```
   python scripts/pivot_finder.py --site dk --slate-id {slate_id}
   ```
   ```
   git add output/pivot_suggestions_dk_{slate_id}.csv
   ```
   ```
   git commit -m "Pivot suggestions - slate {slate_id}"
   ```
   ```
   git push
   ```

Either way, once `output/pivot_suggestions_{site}_{slate_id}.csv` exists in the repo: download it from GitHub, then upload it into the UI the same way you uploaded your pool/lineup file (**Choose File…** in the Slates panel). The UI detects it automatically as pivot data and pairs it to the current slate — after that, clicking any roster row on a built lineup shows the pivot panel.

**If you rebuild lineups after loading pivots**, the pivot suggestions won't reflect the new batch until you regenerate and re-upload them the same way — they're not live-linked to whatever's currently on screen.

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

*(update `data/current_slate.json` with your week/slate_id)*
```
python scripts/projections_baseline.py --site dk --season {season} --week {week}
```
```
python scripts/projections_matchup.py --site dk --season {season} --week {week}
```
```
python scripts/build_projections_statline.py --site dk --season {season} --week {week} --slate-id {slate_id} --volume-prior --sigma-recalibration --dst-model distributional
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
- **Showdown + classic on the same site can't both auto-refresh at once** — `current_slate.json` tracks one slate_id per site, so pointing it at a Showdown slate stops Stage 3 from refreshing whatever classic slate was live for that site.
- **DK Showdown's column shapes are measured against a real export and a real ARI/CAR slate; FD Showdown's 1.5x MVP mechanic is confirmed against a live FD roster builder, but neither has been run through a full FD Showdown slate end to end yet.**
- **The near-lock cadence** (currently templated to Sunday 11am CT) needs updating once the actual regular-season lock time pattern is confirmed.
- **Participation Floors (Session 15) default ON for classic slates** (`QB:0.6,RB:0.4,TE:0.4`) — a player barely showing up in his team's last 5 games gets excluded from the pool automatically. If a build comes back thinner than expected at QB/RB/TE, this is the first thing to check; lock a known exception back in rather than turning the floor off broadly.
- **Pivot suggestions need an extra manual step** (build lineups → generate `pivot_suggestions_{site}_{slate_id}.csv`, automatically or via `pivot_finder.py` — Stage 4's "Pivot suggestions" section → download and re-upload into the UI). This isn't yet a single-click flow; see Stage 4 for the full sequence.
- **If any step produces an unexpected error**, paste the full error message into a Claude conversation. The error message is the fastest path to a fix.
