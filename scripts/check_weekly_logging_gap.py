"""Flag contest-results slates missing from the weekly "learning" logs.

Stage 6 (`log_ownership.py` -> data/ownership_actual_log.csv) and Stage 7
(`log_results.py` -> data/projection_error_log.csv) in DFS_Weekly_Process.md
are manual, required-every-week steps. They silently stopped running for
5-6 weeks in 2026 (see WK8_POSTMORTEM_CHECKLIST.md Item E) with nobody
noticing until a postmortem session went looking. This script makes that
gap visible on demand instead of relying on someone remembering to check.

For every slate that has a real contest-results export in data/contest_results/
(current-week top-level *_full.csv, plus data/contest_results/<season>/Week_N/),
check whether that slate_id has any rows logged in each learning log. A slate
younger than --grace-days is not flagged (its logging step may legitimately
not have happened yet).

Usage:
    python scripts/check_weekly_logging_gap.py
    python scripts/check_weekly_logging_gap.py --grace-days 3
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CR_DIR = ROOT / "data" / "contest_results"
OWNERSHIP_LOG = ROOT / "data" / "ownership_actual_log.csv"
RESULTS_LOG = ROOT / "data" / "projection_error_log.csv"

DATE_RE = re.compile(r"(\d{2})([A-Za-z]{3})(\d{4})")
MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1
)}

# Extra real-money contest exports of the SAME slate (different entrants, same players/
# ownership/results) get a trailing suffix on the filename but are logged under the bare
# slate_id — strip it before comparing, or every one of these looks like a fake gap.
CONTEST_VARIANT_SUFFIXES = ("_mme", "_se3max")


def _slate_date(slate_id: str) -> dt.date | None:
    m = DATE_RE.search(slate_id)
    if not m:
        return None
    day, mon, year = m.groups()
    month = MONTHS.get(mon)
    if month is None:
        return None
    return dt.date(int(year), month, int(day))


def _canonical_slate_id(stem: str) -> str:
    for suffix in CONTEST_VARIANT_SUFFIXES:
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


def find_contest_result_slates() -> list[str]:
    files = list(CR_DIR.glob("*_full.csv"))
    for season_dir in CR_DIR.iterdir():
        if season_dir.is_dir():
            files.extend(season_dir.glob("Week_*/*_full.csv"))
    stems = {f.name[: -len("_full.csv")] for f in files}
    return sorted({_canonical_slate_id(s) for s in stems})


def logged_slate_ids(log_path: Path) -> set[str]:
    if not log_path.exists():
        return set()
    df = pd.read_csv(log_path, usecols=["slate_id"], low_memory=False)
    return set(df["slate_id"].unique())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grace-days", type=int, default=3,
                     help="Don't flag a slate's results as final until this many days after its date (default 3).")
    args = ap.parse_args()

    today = dt.date.today()
    slates = find_contest_result_slates()
    ownership_logged = logged_slate_ids(OWNERSHIP_LOG)
    results_logged = logged_slate_ids(RESULTS_LOG)

    ownership_gaps, results_gaps, skipped = [], [], []
    for slate_id in slates:
        slate_date = _slate_date(slate_id)
        if slate_date is not None and (today - slate_date).days < args.grace_days:
            skipped.append(slate_id)
            continue
        # FD never publishes a real post-lock ownership page (confirmed, see
        # DFS_Weekly_Process.md Stage 6's FD note) -- an FD slate missing from the
        # ownership log is the documented, correct state, not a gap.
        if not slate_id.startswith("fd_") and slate_id not in ownership_logged:
            ownership_gaps.append(slate_id)
        if slate_id not in results_logged:
            results_gaps.append(slate_id)

    print(f"Checked {len(slates)} contest-results slates ({len(skipped)} skipped, within "
          f"{args.grace_days}-day grace period).\n")

    if not ownership_gaps and not results_gaps:
        print("No logging gaps found. Stage 6/7 are current.")
        return

    if ownership_gaps:
        print(f"OWNERSHIP LOG GAP ({len(ownership_gaps)} slate(s) missing from {OWNERSHIP_LOG.name}):")
        for s in ownership_gaps:
            print(f"  - {s}")
        print()

    if results_gaps:
        print(f"RESULTS LOG GAP ({len(results_gaps)} slate(s) missing from {RESULTS_LOG.name}):")
        for s in results_gaps:
            print(f"  - {s}")
        print()

    print("Run Stage 6/Stage 7 of DFS_Weekly_Process.md for the slates above.")


if __name__ == "__main__":
    main()
