# History data snapshot (2026-10-02)

Zipped, chunked (under 100MB each) snapshot of two local working folders used for backtesting
this project's projections/ownership/construction models:

- `hist/` — multi-season per-slate contest/ownership/projection exports (2021-2026) and derived
  research outputs, used as the held-out history frame for every accuracy test in this repo.
- `work/` — scratch analysis scripts, intermediate CSVs/logs, and RESULTS.md writeups from
  individual backtest sessions.

A handful of large, purely-regenerable cache files were left out on purpose (they rebuild from
the data that IS included here, so excluding them doesn't lose anything).

## Why this exists
These folders are gitignored locally (they churn constantly and aren't needed for the app to
run), but they represent real, time-consuming-to-rebuild research work and a dataset obtained
from a now-inaccessible source. This is a one-time backup snapshot, committed at the owner's
request, not a live-tracked folder — don't expect it to stay in sync with the working copies.

## To restore
```
cd archive/history_data
mkdir -p ../../data/fc_history   # or wherever you want hist/ unpacked
for f in hist/*.zip; do unzip -o "$f" -d ../../data/fc_history; done
mkdir -p ../../analysis
for f in work/*.zip; do unzip -o "$f" -d ../../analysis; done
```
