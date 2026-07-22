# NFL DFS Optimizer

A pipeline for building NFL Daily Fantasy Sports lineups: data ingestion →
blended projections → lineup optimization → ownership/pivot logic →
automation → frontend. See `ROADMAP.md` for the full session-by-session build
plan and `SESSION_LOG.md` for what's actually been done.

## Setup

Requires Python 3.10+ (built and verified on 3.12.3).

```bash
python3 -m venv venv
source venv/bin/activate          # on Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Verify the install:

```bash
python3 scripts/nflverse_fetch.py
```

This should print a row/column count for a pull of 2025 season weekly stats.
If it fails with a 404, see the note below — nflverse likely renamed a
release again.

## Repo structure

```
/dfs_optimizer
  /data           <- raw + processed data files
  /scripts        <- all pipeline scripts
  /output         <- generated projections, lineups
  /logs           <- session log + automation run logs
  SESSION_LOG.md
  ROADMAP.md
```

## Important: data source note

This project does **not** use `nfl_data_py`. That package is deprecated
upstream (nflverse recommends `nflreadpy` instead), and its built-in
`import_weekly_data()` / `import_schedules()` functions point at a GitHub
release path nflverse retired on 2025-08-01 — they 404 on any 2025+ season
data and there are no further updates planned upstream.

Instead, `scripts/nflverse_fetch.py` reads nflverse's published parquet
files directly (no API key required). It's a small, single-file dependency
we own and can fix ourselves if nflverse reorganizes their releases again —
see the docstring in that file for details, and update `URL_TEMPLATES` there
if a pull starts 404ing.

## Config / secrets

API keys (e.g. for The Odds API in Phase 2) live in `config/api_keys.env`,
which is gitignored. Never commit credentials.
