# Inactives / availability — results (2026-09-29)

Scripts: `status_calibration.py` (history), `audit_2026.py` (2026 live), prototype `scripts/availability_diff.py`.
Outputs: `calib_report.txt`, `audit_2026_report.txt`, `status_panel_2016_2025.csv`, `ourproj_gt8_status.csv`,
`audit_2026_rows.csv`, `live/availability_diff_*.csv`. Raw nflverse injuries 2016-26 + rosters 2022-23 in `raw/`.
Nothing wired into production; nothing committed.

## 1. Size of the problem

**The "FC zeroed 1,001 players we had above 8" edge mostly comes from the backtest setup, not from live play.**
The 2021-25 `ourproj` regeneration has injuries STUBBED, so every Friday-known Out/IR player stays live there.
Of the inactive proj>8 rows in 2021-25 (86 slates, 11.6/slate, ~127 projected pts/slate wasted):

| kind | per slate | fixable by |
|---|---|---|
| Friday-known (Out / Doubtful / IR) | 5.10 | already handled live by status_check apply (zeroes OUT+DOUBTFUL) |
| Active backup QB who never took a snap | 3.59 | depth/role model, not an injury feed |
| Questionable -> inactive | 1.64 | game-day inactives (T-90) or probability weighting |
| Active non-QB, no stats | 0.84 | role/depth (mostly) |
| Inactive with no designation (true surprise) | 0.34 | game-day inactives only |

**2026 production audit (last pre-lock status file vs actual, non-DST):** 0 players with final proj>8 went inactive
while left live, in wk1, wk2 or wk3. Inactives our pipeline left live all project 3-8 (backups, TE2/WR4, backup QBs), at
2 / 5 / 5 players per week with proj>5. The live misses are near-min-salary depth players, not studs.
Caveats: wk1's "pre-lock" status file was from Thu 09-10, three days stale. wk3 nflverse stats/rosters were
incomplete, so wk3 "inactive" is approximate.
Wk3 manual-news check: the Legette and Mitchell OUT overrides were right. The **Zay Flowers OUT override was wrong**:
he played and scored 15.4. Keon Coleman ACTIVE was right. Faster news helps, but "most likely out" reports are not certain.

**Cost of one inactive in a lineup:** about 11-13 projected points gone (mean proj of inactive proj>8 is 11.0).
That is 7-9% of the 2026 cash-line proxy (135-164), which usually ends cash/SE equity for that lineup.

## 2. Designation -> P(inactive) (2016-25, relevant = trailing-3 PPR >= 8; stable across eras)

| final designation | n | P(inactive) | P(<2 pts) |
|---|---|---|---|
| Out | 965 | 0.999 | 0.999 |
| IR/Reserve | 1367 | 1.000 | 0.998 |
| Doubtful | 184 | 0.984 | 0.984 |
| Questionable, practiced Full Fri | 279 | 0.10 | 0.18 |
| Questionable, Limited Fri | 1151 | 0.25 | 0.31 |
| Questionable, DNP Fri | 277 | 0.53 | 0.56 |
| No designation | 21676 | 0.043* | 0.11 |

\* mostly backup-QB DNPs and trades; a true surprise inactive is about 1%.
By position, Questionable QBs sit most often (0.43); RB 0.28, WR 0.23, TE 0.23. Thursday games run 0.33, Sunday 0.27.
Questionable players who play produce 0.79x their trailing average, vs 0.88x for undesignated players.
That is roughly a 10% haircut even when they suit up.
Out-of-sample backtest (fit 2016-20, test 2021-25, proj>8), RMSE: no status 8.12, hard Out/Doubtful 7.79 (current live rule),
probability-weighted Q by practice status 7.73. A small but real gain.
Use availability-weighted projections only for pre-news builds. Once the T-90 inactives are known, Q players are binary.

## 3. Sources — ranked (speed x reliability x cost)

1. **ESPN game roster `didNotPlay` (scripts/inactives_pull.py, exists)**: free, exact official inactives, ID-joined.
   It has never been verified to populate at T-90; it may only fill at kickoff. **Must be tested live next Sunday.**
2. **Sleeper `/v1/players/nfl`**: free, no token, non-commercial use. Verified today: it carries game-day "Out" marks
   (e.g. Jack Bech, Rico Dowdle wk3 `Out|Inactive`) and matches the nflverse sleeper_id. Docs ask for about one call a day
   on this 5MB endpoint, so allow 2-3 calls on Sunday (Fri, T-100, T-75). Latency vs the inactive release is unmeasured.
3. **ESPN team roster injuries (status_check.py, production)**: good for Wed-Fri designations. It lags on game-day
   changes: Legette/Coleman were still Questionable at T-90.
4. **nflverse injuries**: this is the historical truth set only, published after the fact. It is useless pre-lock.
5. **X (Twitter)**: the fastest human-readable source (Rapoport/Schefter/beat writers, team accounts post inactives at T-90).
   Official API is now pay-per-use only: $0.005 per post read, no free tier, account + credits + a developer app required.
   Polling ~40 accounts every 2 minutes for 2 hours on Sunday is about 2.4k reads, so ~$12/Sunday worst case and a few $ with since_id.
   Tweets are free text, so each needs name extraction plus a human confirm (see the Flowers false alarm).
   Scraping X without the API violates its ToS and breaks often. **Not recommended.**
   Paid options (RotoWire/FantasyPros/SportsDataIO feeds) are machine-readable but licensed. Not evaluated for cost.

## 4. Recommended architecture / Sunday checklist
- **Fri evening**: `status_check pull` + apply (production). Then run `availability_diff.py`: ESPN vs Sleeper vs pipeline.
  Resolve disagreements in `config/manual_status_overrides.csv`.
- **Sun T-100 (11:20 ET)**: `status_check pull` again. Wk1 ran on a 3-day-old file; add a hard age check (<3h) at build.
- **Sun T-85 to T-75 (11:35-11:45 ET)**: `inactives_pull.py` + `availability_diff.py`. A player marked OUT by any
  official-inactive source (ESPN didNotPlay / Sleeper game-day Out) goes to manual override OUT, after a human glance.
  X (Rapoport/team accounts) stays a human-read source feeding the same override file.
- Unresolved Q at build time: availability-weight (P from table above by practice status), then rebuild after T-75.
- Repeat at T-75 for 4pm and SNF/MNF slates.

## 5. Open items
- Log the timestamps at which ESPN didNotPlay and Sleeper game-day Out first appear next Sunday; that decides #1 vs #2.
- Backup-QB and depth DNPs (3.6/slate in history) are a projection/role problem. They belong in a separate session.
- Q probability weighting: implement as an opt-in in status_check apply (needs practice status; ESPN roster lacks it,
  but nflverse injuries/official report has it by Friday).
