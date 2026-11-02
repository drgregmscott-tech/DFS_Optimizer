"""One-off backfill: reshape data/contest_results DK showdown exports (wk4 ATL@NO
missed slate, plus weeks 5-8) into log_ownership.py's raw showdown input shape
(player_name, roster_role, actual_ownership_pct), then call log_ownership.py
log for each slate. Mirrors scripts/_backfill_ownership_wk5_8.py (classic),
adapted for the showdown roster_role column. Scratch script, not part of the
pipeline.
"""
import subprocess
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "data"

SLATES = [
    (4, "dk_showdown_wk4_ATL_NO_05Oct2026", "data/contest_results/2026/Week_4/dk_showdown_wk4_ATL_NO_05Oct2026_full.csv"),
    (5, "dk_showdown_wk5_TB_DAL_08Oct2026", "data/contest_results/2026/Week_5/dk_showdown_wk5_TB_DAL_08Oct2026_full.csv"),
    (5, "dk_showdown_wk5_BAL_ATL_11Oct2026", "data/contest_results/2026/Week_5/dk_showdown_wk5_BAL_ATL_11Oct2026_full.csv"),
    (5, "dk_showdown_wk5_BUF_LAR_12Oct2026", "data/contest_results/2026/Week_5/dk_showdown_wk5_BUF_LAR_12Oct2026_full.csv"),
    (6, "dk_showdown_wk6_SEA_DEN_15Oct2026", "data/contest_results/2026/Week_6/dk_showdown_wk6_SEA_DEN_15Oct2026_full.csv"),
    (7, "dk_showdown_wk7_NE_CHI_22Oct2026", "data/contest_results/2026/Week_7/dk_showdown_wk7_NE_CHI_22Oct2026_full.csv"),
    (7, "dk_showdown_wk7_KC_SEA_25Oct2026", "data/contest_results/2026/Week_7/dk_showdown_wk7_KC_SEA_25Oct2026_full.csv"),
    (8, "dk_showdown_wk8_CAR_GB_29Oct2026", "data/contest_results/dk_showdown_wk8_CAR_GB_29Oct2026_full.csv"),
    (8, "dk_showdown_wk8_PHI_WAS_01Nov2026", "data/contest_results/dk_showdown_wk8_PHI_WAS_01Nov2026_full.csv"),
]

for week, slate_id, rel_path in SLATES:
    src = REPO_ROOT / rel_path
    df = pd.read_csv(src, encoding="utf-8-sig")
    n_entries = int(df["EntryId"].dropna().nunique())
    pool = df[["Player", "Roster Position", "%Drafted"]].dropna(subset=["Player", "Roster Position"]).copy()
    pool["actual_ownership_pct"] = pool["%Drafted"].str.rstrip("%").astype(float)
    grouped = pool.groupby(["Player", "Roster Position"], as_index=False)["actual_ownership_pct"].sum()
    grouped = grouped.rename(columns={"Player": "player_name", "Roster Position": "roster_role"})

    raw_path = RAW_DIR / f"ownership_raw_dk_2026_wk{week}_{slate_id}.csv"
    grouped.to_csv(raw_path, index=False)

    cmd = [
        sys.executable, "scripts/log_ownership.py", "log",
        "--site", "dk", "--season", "2026", "--week", str(week),
        "--slate-id", slate_id,
        "--slate-type", "regular_season",
        "--contest-type", "single_entry_gpp",
        "--field-size", str(n_entries),
        "--input", str(raw_path),
        "--source", f"contest_results backfill 2026-11-02 ({rel_path})",
    ]
    print("\n=== ", slate_id, " ===")
    result = subprocess.run(cmd, cwd=REPO_ROOT)
    if result.returncode != 0:
        print(f"FAILED: {slate_id}", file=sys.stderr)
