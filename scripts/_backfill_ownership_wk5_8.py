"""One-off backfill: reshape data/contest_results DK classic exports (weeks 5-8)
into log_ownership.py's raw input shape, then call log_ownership.py's log()
function directly for each slate. Scratch script, not part of the pipeline.
"""
import subprocess
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "data"

SLATES = [
    (5, "dk_classic_wk5_main_11Oct2026", "data/contest_results/2026/Week_5/dk_classic_wk5_main_11Oct2026_full.csv"),
    (5, "dk_classic_wk5_early_11Oct2026", "data/contest_results/2026/Week_5/dk_classic_wk5_early_11Oct2026_full.csv"),
    (5, "dk_classic_wk5_afternoon_11Oct2026", "data/contest_results/2026/Week_5/dk_classic_wk5_afternoon_11Oct2026_full.csv"),
    (6, "dk_classic_wk6_main_18Oct2026", "data/contest_results/2026/Week_6/dk_classic_wk6_main_18Oct2026_full.csv"),
    (7, "dk_classic_wk7_main_25Oct2026", "data/contest_results/2026/Week_7/dk_classic_wk7_main_25Oct2026_full.csv"),
    (7, "dk_classic_wk7_early_25Oct2026", "data/contest_results/2026/Week_7/dk_classic_wk7_early_25Oct2026_full.csv"),
    (8, "dk_classic_wk8_main_01Nov2026", "data/contest_results/dk_classic_wk8_main_01Nov2026_full.csv"),
    (8, "dk_classic_wk8_early_01Nov2026", "data/contest_results/dk_classic_wk8_early_01Nov2026_full.csv"),
]

for week, slate_id, rel_path in SLATES:
    src = REPO_ROOT / rel_path
    df = pd.read_csv(src, encoding="utf-8-sig")
    n_entries = int(df["EntryId"].dropna().nunique())
    pool = df[["Player", "%Drafted"]].dropna(subset=["Player"]).copy()
    pool["actual_ownership_pct"] = pool["%Drafted"].str.rstrip("%").astype(float)
    grouped = pool.groupby("Player", as_index=False)["actual_ownership_pct"].sum()
    grouped = grouped.rename(columns={"Player": "player_name"})

    raw_path = RAW_DIR / f"ownership_raw_dk_2026_wk{week}_{slate_id}.csv"
    grouped.to_csv(raw_path, index=False)

    cmd = [
        sys.executable, "scripts/log_ownership.py", "log",
        "--site", "dk", "--season", "2026", "--week", str(week),
        "--slate-id", slate_id,
        "--slate-type", "regular_season",
        "--contest-type", "3max_gpp",
        "--field-size", str(n_entries),
        "--input", str(raw_path),
        "--source", f"contest_results backfill 2026-11-02 ({rel_path})",
    ]
    print("\n=== ", slate_id, " ===")
    result = subprocess.run(cmd, cwd=REPO_ROOT)
    if result.returncode != 0:
        print(f"FAILED: {slate_id}", file=sys.stderr)
