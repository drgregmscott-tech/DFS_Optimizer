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

On the DK or FD contest page, click **Export to CSV**. Save the file anywhere convenient — the repo root folder is fine. Leave the filename as whatever DK/FD named it (no need to rename it).

---

### Step 2c — Fetch the latest nflverse player data

Run this once per week before ingesting salaries. Use the most recent completed NFL season year (currently 2025):

```
python scripts/nflverse_fetch.py --season 2025
```

You should see output like `Pulled XXXXX rows for 2025 weekly stats`. If you see an error, contact Claude.

---

### Step 2d — Choose a backend slate ID

Pick a short, filesystem-safe identifier for this slate. This is used by the backend pipeline to name output files — it is separate from the human-readable label you'll assign in the UI later (Step 4). Use something lowercase with no spaces:

- **Regular season:** `classic_wk3`
- **Early Sunday only:** `early_wk3`
- **Afternoon only:** `afternoon_wk3`
- **Preseason:** `preseason_wk1`
- **Madden Sim:** `madden_20260730`
- **Thanksgiving:** `thanksgiving_2026`

You'll use this same backend slate ID in Steps 2e through 2j. It does not need to match the label you give the slate in the UI.

---

### Step 2e — Ingest the salary file

Replace `DKSalaries.csv` with your actual filename, `2025` with the nflverse season year, and `classic_wk1` with your backend slate ID from Step 2d:

```
python scripts/ingest_salaries.py --site dk --raw DKSalaries.csv --season 2025 --slate-id classic_wk1
```

**Expected output:** A match rate summary and a line saying `Wrote data\salaries_dk_{slate_id}.csv`.

**Handling unmatched players:**

The script will list any players it couldn't match. For each one:

1. Search for them in the nflverse data (replace `Smith` with their last name):
```
python -c "import pandas as pd; df = pd.read_parquet('data/weekly_stats_2025.parquet'); print(df[df['player_name'].str.contains('Smith', case=False, na=False)][['player_id','player_name','position','team']].drop_duplicates())"
```

2. If you find a clear match (right name, right position, right team), add them to `data/name_mapping.csv`:
```
Add-Content data\name_mapping.csv "dk,{DK Name},{TEAM},{POS},{player_id},matched via nflverse 2025"
```

3. If the player doesn't appear in nflverse at all (rookie, or very limited 2025 snaps), leave them unmatched — they'll project from Vegas/matchup factors only, which is fine.

4. Re-run the ingest command to confirm your additions resolved. Repeat until remaining unmatched players are all genuinely not in nflverse.

**If you get an unexpected error at this step, contact Claude.**

---

### Step 2f — Update `data/current_slate.json`

Open `data/current_slate.json` in any text editor and update it to match the slate you just ingested. Only change the `dk` block (or `fd` block if you ingested FD). Set `season` to the nflverse data year (currently 2025):

```json
{
  "_comment": "...",
  "season": 2025,
  "dk": {
    "week": 1,
    "slate_id": "classic_wk1"
  },
  "fd": {
    "week": 1,
    "slate_id": "classic_wk1"
  }
}
```

`week` is the NFL week number for real slates. For Madden Sim slates, use `1`.

---

### Step 2g — Build baseline projections

```
python scripts/projections_baseline.py --site dk --season 2025 --week 1
```

No output means success. An error means contact Claude.

---

### Step 2h — Build matchup projections

```
python scripts/projections_matchup.py --site dk --season 2025 --week 1
```

No output means success. An error means contact Claude.

---

### Step 2i — Build final projections

```
python scripts/build_projections.py --site dk --season 2025 --week 1 --slate-id classic_wk1
```

No output means success. This writes `output/final_projections_dk_{week}.csv`. An error means contact Claude.

---

### Step 2j — Commit and push

This step is critical. The automated refresh loop (Stage 3) and the UI both run against whatever is committed to the repo — nothing downstream sees your new data until it's pushed.

```
git add data/ output/
```

```
git commit -m "Slate classic_wk1 - ingest complete"
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
| Light Vegas refresh | Tue–Fri 1×/day, Sat 2×/day, Sun hourly | Vegas lines only |
| Full refresh (scheduled) | Every 3 hours, Thu/Sun/Mon | Vegas + injury/active status + full projection rebuild |
| Full refresh (near-lock) | Every 10 min, final hour before lock | Same as above, fired by Cloudflare Worker |

A full refresh rebuilds `output/final_projections_{site}_{week}.csv` — this is where projections, chalk scores, and ownership estimates all update together. Players ruled OUT are zeroed. Players flagged DOUBTFUL/QUESTIONABLE are marked but not zeroed.

You don't need to do anything during Stage 3. Just check the UI periodically to see projections update as injury news comes in.

---

## Stage 4 — Build & preview lineups

Open the deployed UI at **https://dfs-optimizer.pages.dev**.

### Loading a slate

1. In the **Slates** panel, click **Choose File…** and select `output/final_projections_dk_{week}.csv` from your local repo.
2. A name field appears, pre-filled with the filename. Replace it with a short, readable label — this is what shows in the dropdown and is just for your own navigation. Examples:
   - `Classic Wk 3`
   - `Early Wk 3`
   - `Afternoon Wk 3`
   - `Preseason Wk 1`
   - `Thanksgiving 2026`
3. Click **Save**. The slate is stored locally and synced to the cloud.
4. It now appears in the dropdown and is automatically selected and loaded.

**The label has no effect on the backend.** You can name it anything — the optimizer dispatch always uses the week number embedded in the original filename, not the label.

### Multiple slates for the same week

You can upload the same CSV multiple times with different labels and they are stored as completely separate entries. For example, if you want separate lineup builds for early and main contests on the same week, upload the file twice with two different labels. Both show in the dropdown and you can switch between them freely.

### Switching between slates

Use the dropdown to switch. Each slate loads its own player pool, projections, and any lineups already built against it. Switching is instant — data is loaded from local storage, not the cloud.

### Cross-device access (desktop → phone)

Slates sync to the cloud automatically when saved. On a second device (e.g. phone), open the UI and wait a moment — the slate will appear in the dropdown and auto-load without any manual action required.

### Deleting a slate

Select it in the dropdown and click **Delete**. Confirms before deleting. Removes it from both this browser and the cloud — it will not reappear on page reload or on other devices.

### Building lineups

Once a slate is loaded, set your options (stacking, exposure, lock/exclude, randomization) in the Build panel and click **Build Lineups**. Review all lineups in the navigator before exporting. If lineups look wrong — contact Claude before proceeding.

---

## Stage 5 — Export & re-upload

Click **Download Lineups for DraftKings Import**. This exports your lineups in DK's bulk-upload format with real player IDs attached.

Upload that file back into DK — it replaces the placeholder lineups from Step 2a with your real ones.

Lock hits. Done.

---

## Known gaps and reminders

- **`--week` and `--season` flags** refer to the nflverse data, not the calendar year. Use `--season 2025` and the actual NFL week number until nflverse updates for the 2026 season.
- **Madden Sim slates:** use `--week 1` everywhere for all backend commands. These are for pipeline testing only — projections will look reasonable but are not calibrated for Madden Sim game mechanics.
- **Multiple slates, one CSV:** the pipeline produces one `final_projections_dk_{week}.csv` per week. If you want separate lineup builds for early vs. main, upload that same file twice in the UI with two different labels. The backend slate ID and output file are shared; the UI label is the only thing that distinguishes them.
- **DK is live-validated end to end.** FD is built identically but has not been tested against a real FD salary export — treat FD output as unverified until that happens.
- **The near-lock cadence** (currently templated to Sunday 11am CT) needs updating once Preseason Week 1's actual lock time is known.
- **If any step produces an unexpected error,** paste the full error message into a Claude conversation. Don't try to debug it by guessing — the error message is the fastest path to a fix.
