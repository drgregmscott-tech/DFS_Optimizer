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

These two flags control which historical data drives skill-player projections. They do NOT need to match the actual calendar week or year of the slate.

**`--season`:** always use the last completed NFL season year in nflverse. Currently: `2025`.

**`--week`:** must match the week number in `data/current_slate.json`, which is also the number in the most recent large `output/vegas_implied_totals_{week}.csv` file. If those two are out of sync, use `current_slate.json` as the authority.

| Slate type | `--week` to use |
|---|---|
| Real NFL regular season (e.g. Week 5) | `5` (the actual NFL week) |
| Real NFL postseason | `18` |
| Preseason | `18` |
| Madden Sim or any off-season slate | Whatever week `current_slate.json` says (currently `23`) |

**How to check the current week:** run `type data\current_slate.json` and read the `week` value from the `dk` block.

**Why this matters:** `build_projections.py` looks for `output/vegas_implied_totals_{week}.csv`. If that file doesn't exist for the week you pass, the build will fail. Always use the week that already has a Vegas file.

---

## Madden Sim slates — what to expect

Madden Sim slates are supported for pipeline testing. A few things to know:

- **Skill player projections** are 2025 season averages — historical production only, with neutral 1.0 multipliers for matchup and Vegas. The Madden matchups have no effect on skill player projections because they don't exist in real NFL schedule data.
- **DST projections** use the DK `AvgPointsPerGame` column from the salary file scaled by real Vegas lines for the opposing offense. These are real numbers.
- **Game totals panel in the UI** will show real NFL Week 1 games rather than your Madden matchups. This is cosmetic only — it has zero effect on lineup building. The optimizer uses projection values, not game groupings.
- **This is expected behavior**, not a bug. Madden Sim slates are useful for validating the pipeline and practicing lineup construction with real projections.

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

### Step 2b — Export the salary CSV

On the DK or FD contest page, click **Export to CSV**. Save the file anywhere convenient — the repo root folder is fine. Leave the filename as whatever DK/FD named it.

---

### Step 2c — Fetch the latest nflverse player data

```
python scripts/nflverse_fetch.py --season 2025
```

Expected output: `Pulled XXXXX rows for 2025 weekly stats`. If you see an error, contact Claude.

---

### Step 2d — Ingest historical data (first time each season, or if parquet files are missing)

This pulls the nflverse stats, schedules, rosters, and team stats that the projection scripts depend on. Run it once at the start of each season, and any time `build_projections.py` fails with a `.parquet not found` error.

```
python scripts/ingest_historical.py --season 2025
```

Expected output: several lines like `Wrote data\weekly_stats_2025.parquet (XXXXX rows...)`. If you see an error, contact Claude.

---

### Step 2e — Choose a backend slate ID

Pick a short, filesystem-safe identifier. This names both the salary file and the final projections output file. Use lowercase with no spaces:

| Slate type | Example slate ID |
|---|---|
| Regular season, main slate | `classic_wk3` |
| Early Sunday only | `early_wk3` |
| Afternoon only | `afternoon_wk3` |
| Preseason | `preseason_wk1` |
| Madden Sim | `madden_07312026` |
| Thanksgiving | `thanksgiving_2026` |

You'll use this same slate ID in Steps 2f through 2k. The output file will be named `output/final_projections_dk_{slate_id}.csv`.

---

### Step 2f — Ingest the salary file

Replace `DKSalaries.csv` with your actual filename and `madden_07312026` with your slate ID:

```
python scripts/ingest_salaries.py --site dk --raw DKSalaries.csv --season 2025 --slate-id madden_07312026
```

Expected output: a match rate summary and `Wrote data\salaries_dk_{slate_id}.csv`.

**Handling unmatched players:**

The script lists any players it couldn't match. For each one:

1. Search for them in nflverse (replace `Smith` with their last name):
```
python -c "import pandas as pd; df = pd.read_parquet('data/weekly_stats_2025.parquet'); print(df[df['player_name'].str.contains('Smith', case=False, na=False)][['player_id','player_name','position','team']].drop_duplicates())"
```

2. If you find a clear match, add them to `data/name_mapping.csv`:
```
Add-Content data\name_mapping.csv "dk,{DK Name},{TEAM},{POS},{player_id},matched via nflverse 2025"
```

3. Re-run the ingest command to confirm your additions resolved. Players with no nflverse match at all (rookies, very limited snaps) are fine to leave unmatched — they will project from Vegas/matchup factors only.

If you get an unexpected error, contact Claude.

---

### Step 2g — Check the current week number

Before running the projection scripts, confirm what week number to use:

```
type data\current_slate.json
```

Read the `week` value from the `dk` block. Use that number for `--week` in Steps 2h through 2j. For Madden Sim slates this is currently `23`. For real regular-season slates it will be the actual NFL week.

---

### Step 2h — Update `data/current_slate.json`

Open `data/current_slate.json` in any text editor. Update the `dk` block with your week and slate ID. For Madden Sim slates, `week` stays at whatever `current_slate.json` already says (currently 23):

```json
{
  "_comment": "...",
  "season": 2025,
  "dk": {
    "week": 23,
    "slate_id": "madden_07312026"
  },
  "fd": {
    "week": 1,
    "slate_id": "classic_wk1"
  }
}
```

Only update the block for the site you ingested.

---

### Step 2i — Build baseline projections

Use the week number from Step 2g:

```
python scripts/projections_baseline.py --site dk --season 2025 --week 23
```

No output means success. For week 23 (post-season), this writes `baseline_recent_form_dk_2025_23.csv` with full 2025 season history for all players. An error means contact Claude.

---

### Step 2j — Build matchup projections

```
python scripts/projections_matchup.py --site dk --season 2025 --week 23
```

No output means success. An error means contact Claude.

---

### Step 2k — Build final projections

Use the same `--week` and `--slate-id`:

```
python scripts/build_projections.py --site dk --season 2025 --week 23 --slate-id madden_07312026
```

Expected output: several informational lines, no ERROR. The file `output/final_projections_dk_madden_07312026.csv` is created.

For Madden Sim slates you will also see:
```
NOTE: schedule has no week-23 games for slate teams -- falling back to salary file Game Info pairing
  Inferred 3 game(s) from salary file: [('ARI', 'HOU'), ('BAL', 'CHI'), ('CAR', 'NYJ')]
```
This is expected and correct. If you see an error about a missing `.parquet` file, run Step 2d and retry.

---

### Step 2l — Commit and push

```
git add data/ output/
```

```
git commit -m "Slate madden_07312026 - ingest complete"
```

```
git push
```

Once pushed, Stage 3 takes over automatically.

---

## Stage 3 — Automated refresh loop

Once Stage 2 is pushed, this runs unattended until lock:

| Trigger | Cadence | What it refreshes |
|---|---|---|
| Light Vegas refresh | Tue–Fri 1x/day, Sat 2x/day, Sun hourly | Vegas lines only |
| Full refresh (scheduled) | Every 3 hours, Thu/Sun/Mon | Vegas + injury/active status + full projection rebuild |
| Full refresh (near-lock) | Every 10 min, final hour before lock | Same as above, fired by Cloudflare Worker |

A full refresh rebuilds `output/final_projections_{site}_{slate_id}.csv`. Players ruled OUT are zeroed. Players flagged DOUBTFUL/QUESTIONABLE are marked but not zeroed.

You don't need to do anything during Stage 3. Check the UI periodically to see projections update as injury news comes in.

---

## Stage 4 — Build & preview lineups

Open the deployed UI at **https://dfs-optimizer.pages.dev**.

### Loading a slate

1. In the **Slates** panel, click **Choose File…** and select your projections file — e.g. `output/final_projections_dk_madden_07312026.csv`.
2. A name field appears. Replace the pre-filled filename with a short readable label, e.g. `Madden 7/31`. This is for your own navigation only.
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

---

## Stage 5 — Export & re-upload

Click **Download Lineups for DraftKings Import**. Upload that file back into DK to replace your placeholder lineups.

Lock hits. Done.

---

## Quick reference — full command sequence

Replace the values in braces with your own. For Madden Sim, use the week from `current_slate.json` (currently 23):

```
python scripts/nflverse_fetch.py --season 2025
```
```
python scripts/ingest_historical.py --season 2025
```
```
python scripts/ingest_salaries.py --site dk --raw DKSalaries.csv --season 2025 --slate-id {slate_id}
```
*(check `type data\current_slate.json` for the week number, then update it)*
```
python scripts/projections_baseline.py --site dk --season 2025 --week {week}
```
```
python scripts/projections_matchup.py --site dk --season 2025 --week {week}
```
```
python scripts/build_projections.py --site dk --season 2025 --week {week} --slate-id {slate_id}
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

- **`--week` must match `current_slate.json`** and the existing `vegas_implied_totals_{week}.csv`. Do not guess or use an arbitrary number.
- **`ingest_historical.py` (Step 2d)** must have been run at least once for the current season. If `build_projections.py` fails with a `.parquet not found` error, run Step 2d and retry.
- **Output filenames use `--slate-id`**, not `--week`: `final_projections_dk_{slate_id}.csv`. Two slates in the same week will not overwrite each other.
- **Madden Sim game totals panel** shows real NFL games, not Madden matchups. This is cosmetic only and does not affect lineup building.
- **DK is live-validated end to end.** FD is built identically but has not been tested against a real FD salary export.
- **The near-lock cadence** (currently templated to Sunday 11am CT) needs updating once Preseason Week 1's actual lock time is known.
- **If any step produces an unexpected error**, paste the full error message into a Claude conversation. The error message is the fastest path to a fix.
