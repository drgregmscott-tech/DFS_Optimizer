"""
archive_ecr.py -- keep a per-slate copy of the FantasyPros ECR scrape (DynastyProcess mirror).

Why: scripts/ecr_blend.py caches a single overwritten file (data/ecr/fp_latest_weekly.csv, gitignored), so
there is no history and ECR can never be back-tested as an ownership or projection input. The same
"every un-logged week is lost" logic as scripts/ingest_public_projections.py applies.

Writes data/ecr_archive/ecr_{slate_id}.csv (slim columns, all positions/pages). Overwritten on each full run,
so the last pull before lock is what is kept. DATA ONLY: nothing reads it. Fail-safe: on any error nothing is
written and the exit code is 0 so it can never block a build.

Run:  python scripts/archive_ecr.py --slate-id dk_classic_wk3_main_27Sep2026
"""
import argparse
import io
import sys
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "ecr_archive"
URL = "https://github.com/dynastyprocess/data/raw/master/files/fp_latest_weekly.csv"
KEEP = ["page", "scrape_date", "fantasypros_id", "player_name", "pos", "team", "rank", "ecr", "sd", "best",
        "worst", "player_owned_avg", "player_opponent", "player_game_kickoff_ts", "pos_rank", "r2p_pts"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slate-id", required=True)
    a = ap.parse_args()
    try:
        r = requests.get(URL, headers={"User-Agent": "dfs-optimizer/ecr-archive"}, timeout=30)
        r.raise_for_status()
        df = pd.read_csv(io.BytesIO(r.content))
        if df.empty or "scrape_date" not in df.columns:
            print("ECR archive: empty/unexpected file; nothing written")
            return 0
        df = df[[c for c in KEEP if c in df.columns]]
        OUT.mkdir(parents=True, exist_ok=True)
        p = OUT / f"ecr_{a.slate_id}.csv"
        df.to_csv(p, index=False)
        print(f"ECR archive: {len(df)} rows, scrape_date {df['scrape_date'].max()} -> {p.name}")
    except Exception as exc:  # noqa: BLE001
        print(f"ECR archive skipped: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
