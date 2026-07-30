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

### Step 2d — Choose your slate label

Pick a short, descriptive name for this slate. It can be anything — you'll type it into the UI when uploading the CSV. Use something that's unambiguous at a glance:

- **Regular season main slate:** `Classic Wk 3`
- **Early Sunday only:** `Early Wk 3`
- **Preseason:** `Preseason Wk 1`
- **Madden Sim:** `Madden Jul 30`
- **Thanksgiving:** `Thanksgiving 2026`

No format requirements — spaces are fine, anything readable works. The UI converts it to a URL-safe key internally. You can have multiple slates active at the same time (e.g. main slate + early-only slate for the same week).

---

### Step 2e — Ingest the salary file

Replace `DKSalaries.csv` with your actual filename, `2025` with the nflverse season year, and `classic_wk1` with your slate ID from Step 2d:

```
python scripts/ingest_salaries.py --site dk --raw DKSalaries.csv --season 2025 --slate-id classic_wk1
```

**Note on `--slate-id`:** This is the backend pipeline identifier used to name the output file (`salaries_dk_{slate_id}.csv`). It still follows the format from Step 2d of the old convention — e.g. `classic_wk3`, `preseason_wk1`, `madden_20260730`. It does not need to match the human-readable label you'll use in the UI (Step 4). Use something short and filesystem-safe here.

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
git commit -m "Slate {slate_id} - ingest complete"
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

**To load a slate:**
1. In the **Slates** panel, click **Choose File…** and pick `output/final_projections_dk_{week}.csv` from your local repo.
2. A name field appears pre-filled with the filename. Change it to something readable (e.g. `Classic Wk 3`, `Preseason Wk 1`) and click **Save**.
3. The slate appears in the dropdown. Click it to activate it.

Once loaded, set your desired options (stacking, exposure, lock/exclude, randomization) and run the optimizer. Review lineups using the lineup navigator. Flip through all lineups to spot-check before exporting.

**To switch between slates:** use the dropdown — multiple slates can be saved at once (e.g. main slate and early-only slate for the same week).

**To delete a slate:** select it in the dropdown and click **Delete**. This removes it from the browser and from cloud sync.

**If lineups look wrong** (garbage projections, salary not maxed, wrong players) — contact Claude before proceeding.

---

## Stage 5 — Export & re-upload

Click **Download Lineups for DraftKings Import**. This exports your lineups in DK's bulk-upload format with real player IDs attached.

Upload that file back into DK — it replaces the placeholder lineups from Step 2a with your real ones.

Lock hits. Done.

---

## Known gaps and reminders

- **`--week` and `--season` flags** refer to the nflverse data, not the calendar year. Use `--season 2025` and the actual NFL week number until nflverse updates for the 2026 season.
- **Madden Sim slates:** use `--week 1` everywhere and `madden_{YYYYMMDD}` as the slate ID. These are for pipeline testing only — projections will look reasonable but are not calibrated for Madden Sim game mechanics.
- **DK is live-validated end to end.** FD is built identically but has not been tested against a real FD salary export — treat FD output as unverified until that happens.
- **The near-lock cadence** (currently templated to Sunday 11am CT) needs updating once Preseason Week 1's actual lock time is known.
- **If any step produces an unexpected error,** paste the full error message into a Claude conversation. Don't try to debug it by guessing — the error message is the fastest path to a fix.
